"""Same-origin FastAPI submission website and protected teacher API."""
from __future__ import annotations

import ast
from pathlib import Path
import secrets
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from .locale_api import (LanguageHeadersMiddleware, language_for, localize_replay,
                         localize_rules, localize_state, translate, translate_detail)
from .store import Store
from .tournament import CompetitionError, Tournament

ROOT = Path(__file__).resolve().parents[1]
STARTER = '''import sys

while True:
    line = sys.stdin.readline()
    if not line:
        break
    x, y, checkpoint_x, checkpoint_y, distance, angle = map(int, line.split())
    opponent = sys.stdin.readline()
    if not opponent:
        break
    opponent_x, opponent_y = map(int, opponent.split())
    thrust = 100 if abs(angle) < 90 else 0
    print(checkpoint_x, checkpoint_y, thrust, flush=True)
'''


class JSONModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Submission(JSONModel):
    alias: str = Field(min_length=1, max_length=24)
    code: str = Field(min_length=1, max_length=32768)
    claim_token: str | None = Field(default=None, max_length=128)

    @field_validator("alias")
    @classmethod
    def alias_valid(cls, value):
        if not value.strip() or any(not (c.isalpha() or c.isdigit() or c in " _-") for c in value):
            raise ValueError("Alias must contain 1–24 letters, digits, spaces, underscores or hyphens.")
        return value

    @field_validator("code")
    @classmethod
    def syntax_valid(cls, value):
        try:
            source_bytes = value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Python source must contain valid Unicode text.") from None
        if len(source_bytes) > 32768:
            raise ValueError("Python code must be at most 32 KiB.")
        try:
            ast.parse(value, filename="submission.py")
        except SyntaxError as exc:
            raise ValueError(f"Python syntax error at line {exc.lineno}: {exc.msg}") from None
        except (ValueError, RecursionError, MemoryError):
            raise ValueError("Python source could not be parsed safely.") from None
        return value


class SessionStart(JSONModel):
    duration_seconds: StrictInt = Field(default=7200, ge=1, le=86400)


class Reset(JSONModel):
    confirm: str


class BoundedJSONMiddleware:
    """Bound all HTTP mutation bodies, including chunked requests."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        media_type = headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
        # Empty admin action bodies are allowed, but any provided body must be JSON.
        payload = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(payload) + len(chunk) > 65536:
                language = language_for(Request(scope))
                return await JSONResponse({"detail": translate("Request exceeds the 64 KiB limit.", language)}, status_code=413)(scope, receive, send)
            payload.extend(chunk)
            if not message.get("more_body", False):
                break
        if payload and media_type != b"application/json":
            language = language_for(Request(scope))
            return await JSONResponse({"detail": translate("Send a JSON request with Content-Type: application/json.", language)}, status_code=415)(scope, receive, send)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(payload), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(data_dir=None, *, race_fn=None, tracks_fn=None, sandbox_fn=None):
    store = Store(data_dir)
    tournament = Tournament(store, race_fn=race_fn, tracks_fn=tracks_fn, sandbox_fn=sandbox_fn)
    application = FastAPI(title="Pod Racing Classroom", docs_url=None, redoc_url=None)
    application.state.store = store
    application.state.tournament = tournament
    application.add_middleware(BoundedJSONMiddleware)
    application.add_middleware(LanguageHeadersMiddleware)
    # Print on every server launch so a returning teacher can sign in after restart.
    # This goes only to the teacher's local server console, never a public endpoint.
    print(f"Teacher admin token (save this privately): {store.admin_token}", flush=True)

    @application.exception_handler(CompetitionError)
    async def competition_error(request: Request, exc: CompetitionError):
        return JSONResponse({"detail": translate(exc.message, language_for(request))}, status_code=exc.status)

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": translate_detail(exc.detail, language_for(request))}, status_code=exc.status_code, headers=exc.headers)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # FastAPI's default validation response echoes rejected code and claim tokens.
        language = language_for(request)
        issues = [{"field": ".".join(str(v) for v in error["loc"]), "message": translate(error["msg"], language)} for error in exc.errors()]
        return JSONResponse({"detail": issues}, status_code=422)

    def admin(x_admin_token: str | None = Header(default=None)):
        if not x_admin_token or not secrets.compare_digest(x_admin_token.encode("utf-8"), store.admin_token.encode("utf-8")):
            raise HTTPException(401, "Teacher token required.")

    @application.get("/api/state")
    def state(request: Request):
        with tournament.lock:
            result = {"session": tournament.session(), "submissions": store.submissions(),
                      "leaderboard": store.get("leaderboard", []), "job": store.get("job", store.initial_job()),
                      "active_replay_id": store.get("active_replay_id"), "replays": store.replays(),
                      "finalists": store.get("finalists", []), "champion": store.get("champion"), "server_time": time.time()}
        result["sandbox"] = tournament.sandbox_status()
        return localize_state(result, language_for(request))

    @application.post("/api/submissions")
    def submit(body: Submission):
        return tournament.submit(body.alias, body.code, body.claim_token)

    @application.get("/api/starter")
    def starter(request: Request):
        introduction = "# Lies in jedem Spielzug zwei Zeilen und gib einen Fahrbefehl aus.\n# Ändere den Schub und die Zielkoordinaten, um deinen Bot zu verbessern.\n" if language_for(request) == "de" else "# Read two lines each turn and print one driving command.\n# Change the thrust and target coordinates to improve your bot.\n"
        return PlainTextResponse(introduction + STARTER, media_type="text/x-python", headers={"Content-Disposition": 'attachment; filename="starter.py"'})

    @application.get("/api/rules")
    def rules(request: Request):
        result = {"title": "Classroom one-pod racing", "protocol": {
                    "input": ["x y checkpoint_x checkpoint_y distance relative_angle", "opponent_x opponent_y"],
                    "output": "target_x target_y thrust", "thrust": "integer 0–100, BOOST once per race, or SHIELD",
                    "opponent": "Nearest other pod, including in the simultaneous final.",
                    "flush": "Flush stdout after every command; no bootstrap input."},
                "laps": 2, "max_turns": 700, "qualification_tracks": 3, "final_pods": 5,
                "qualification": "Same three tracks and starting positions against a reference ghost; collisions disabled.",
                "ranking": "Disqualified entries last; completed tracks descending, total turns ascending (DNF costs 700), aggregate checkpoint progress descending, case-folded alias then UUID.",
                "final": "Up to five eligible snapshot bots race simultaneously with collisions. At least two needed. Only a valid finisher can become champion.",
                "physics": "Classroom variant, not the official CodinGame engine: width 16000, height 9000, checkpoint radius 600, pod radius 400, rotation 18 degrees/turn, friction 0.85, BOOST 650. SHIELD lasts three turns with no thrust and heavier mass.",
                "security": "Python syntax checked without execution; bot execution only in restricted Docker.",
                "limits": {"code_bytes": 32768, "submissions": 60, "alias_characters": 24}}
        return localize_rules(result, language_for(request))

    @application.get("/api/replays/{replay_id}")
    def replay(replay_id: str, request: Request):
        result = store.read_replay(replay_id)
        if result is None:
            raise HTTPException(404, "Replay not found.")
        return localize_replay(result, language_for(request))

    @application.post("/api/admin/session/start", dependencies=[Depends(admin)])
    def session_start(body: SessionStart):
        return tournament.start_session(body.duration_seconds)

    @application.post("/api/admin/session/close", dependencies=[Depends(admin)])
    def session_close():
        return tournament.close_session()

    @application.post("/api/admin/qualify", dependencies=[Depends(admin)], status_code=202)
    def qualify(request: Request):
        job = tournament.start_qualification()
        return {**job, "message": translate(job["message"], language_for(request))}

    @application.post("/api/admin/final", dependencies=[Depends(admin)], status_code=202)
    def final(request: Request):
        job = tournament.start_final()
        return {**job, "message": translate(job["message"], language_for(request))}

    @application.get("/api/admin/submissions/{submission_id}", dependencies=[Depends(admin)])
    def submission_source(submission_id: str):
        with tournament.lock:
            entry = next((s for s in store.submissions(private=True) if s["id"] == submission_id), None)
            if entry is None:
                raise HTTPException(404, "Submission not found.")
            return {k: entry[k] for k in ("id", "alias", "code", "version", "submitted_at")}

    @application.post("/api/admin/demo", dependencies=[Depends(admin)])
    def demo(request: Request):
        with tournament.lock:
            tournament.require_idle()
            if tournament.session()["status"] != "waiting" or store.submissions():
                raise HTTPException(409, "Demo requires an empty waiting classroom. Reset first.")
            paths = sorted((ROOT / "examples").glob("*.py"))
            if len(paths) < 6:
                raise HTTPException(503, "Six demo example files are not installed.")
            entries = []
            for index, path in enumerate(paths[:6], 1):
                code = path.read_text(encoding="utf-8")
                alias = f"Demo {index} {path.stem.replace('_', ' ')[:16]}"[:24]
                Submission(alias=alias, code=code)
                entries.append((alias, code))
            store.seed(entries)
            message = "Six genuine example bots inserted. Start qualification to race them; no results have been fabricated."
            return {"inserted": 6, "message": translate(message, language_for(request))}

    @application.post("/api/admin/reset", dependencies=[Depends(admin)])
    def reset(body: Reset):
        if body.confirm != "RESET":
            raise HTTPException(422, "Type RESET to confirm clearing the classroom.")
        return tournament.reset()

    # The same SPA branches by pathname; assets are entirely local.
    application.mount("/assets", StaticFiles(directory=ROOT / "web", check_dir=False), name="assets")

    @application.get("/")
    @application.get("/teacher")
    @application.get("/projector")
    def index():
        path = ROOT / "web" / "index.html"
        if not path.is_file():
            raise HTTPException(503, "Classroom frontend is not installed.")
        return FileResponse(path, media_type="text/html")

    return application


app = create_app()
