"""HTTP validation, ownership, persistence, authorization and job transitions."""
import ast
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from test_tournament import fake_race, sandbox_ready, tracks_fn

# Keep uvicorn's required module-level app from creating a real classroom in tests.
_import_data = tempfile.TemporaryDirectory(prefix="pod-api-import-", dir=os.environ.get("TMPDIR"))
with patch.dict(os.environ, {"POD_DATA_DIR": _import_data.name, "POD_ADMIN_TOKEN": "test-import-only"}):
    create_app = importlib.import_module("arena.app").create_app

TOKEN = "teacher-test-secret"
AUTH = {"X-Admin-Token": TOKEN}
CODE = "print('private-student-source')"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("POD_ADMIN_TOKEN", TOKEN)
    app = create_app(tmp_path / "data", race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    with TestClient(app) as client:
        yield client, app
        worker = app.state.tournament.worker
        if worker:
            worker.join(10)
            assert not worker.is_alive()


def open_session(client):
    response = client.post("/api/admin/session/start", headers=AUTH, json={"duration_seconds": 7200})
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, alias="Pilot", code=CODE, **extra):
    return client.post("/api/submissions", content=json.dumps({"alias": alias, "code": code, **extra}, ensure_ascii=False).encode("utf-8", errors="backslashreplace"), headers={"Content-Type": "application/json"})


def wait(app):
    app.state.tournament.worker.join(10)
    assert not app.state.tournament.worker.is_alive()
    assert app.state.store.get("job")["status"] == "finished", app.state.store.get("job")


def test_initial_closed_auth_and_public_boundaries(api):
    client, app = api
    state = client.get("/api/state")
    assert state.status_code == 200
    body = state.json()
    assert body["session"] == {"status": "waiting", "deadline": None, "duration_seconds": 7200}
    assert submit(client).status_code == 409
    paths = [("/api/admin/session/start", {"duration_seconds": 7200}), ("/api/admin/session/close", {}),
             ("/api/admin/qualify", {}), ("/api/admin/final", {}), ("/api/admin/demo", {}),
             ("/api/admin/reset", {"confirm": "RESET"})]
    for path, payload in paths:
        assert client.post(path, json=payload).status_code == 401
        assert client.post(path, json=payload, headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.get("/api/admin/submissions/unknown").status_code == 401
    assert TOKEN not in state.text and "admin_token" not in state.text and "claim_token" not in state.text
    assert client.get("/api/state", headers={"Origin": "https://attacker.example"}).headers.get("access-control-allow-origin") is None


def test_submit_update_casefold_claims_teacher_source(api):
    client, app = api
    session = open_session(client)
    assert session["deadline"] > client.get("/api/state").json()["server_time"]
    result = submit(client, "Élodie Racer").json()
    assert result["version"] == 1 and result["claim_token"]
    assert submit(client, "éLODIE racer").status_code == 409
    assert submit(client, "éLODIE racer", claim_token="wrong").status_code == 409
    assert submit(client, "éLODIE racer", claim_token="é").status_code == 409
    assert submit(client, "éLODIE racer", claim_token="é\ud800").status_code == 422
    response = submit(client, "éLODIE racer", "print('new-private-source')", claim_token=result["claim_token"])
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == result["id"] and updated["claim_token"] == result["claim_token"] and updated["version"] == 2
    public = client.get("/api/state")
    assert len(public.json()["submissions"]) == 1
    assert public.json()["submissions"][0]["version"] == 2
    assert result["claim_token"] not in public.text and "new-private-source" not in public.text
    source_url = f"/api/admin/submissions/{result['id']}"
    assert client.get(source_url).status_code == 401
    source = client.get(source_url, headers=AUTH).json()
    assert source["code"] == "print('new-private-source')" and "claim_token" not in source


@pytest.mark.parametrize("alias", ["", " " * 24, "x" * 25, "<script>", "a/b", "a\nb", "🙂"])
def test_bad_alias(api, alias):
    client, _ = api
    open_session(client)
    assert submit(client, alias).status_code == 422


def test_syntax_bytes_ast_only_and_validation_no_source_echo(api, tmp_path):
    client, _ = api
    open_session(client)
    response = submit(client, "Syntax", "if PRIVATE_SOURCE !!!", claim_token="PRIVATE_CLAIM")
    assert response.status_code == 422
    assert "PRIVATE_SOURCE" not in response.text and "PRIVATE_CLAIM" not in response.text
    assert "syntax error" in response.text.lower()
    assert submit(client, "Null", "a=1\x00").status_code == 422
    assert submit(client, "Surrogate", "#\ud800").status_code == 422
    assert submit(client, "Large", "#" + "é" * 20000).status_code == 422
    assert submit(client, "Boundary", "#" + "a" * 32767).status_code == 200
    marker = tmp_path / "never-execute"
    dangerous_but_valid = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    assert submit(client, "AST only", dangerous_but_valid).status_code == 200
    assert not marker.exists()
    oversized = client.post("/api/submissions", content='{"code":"' + "x" * 70000 + '"}', headers={"Content-Type": "application/json"})
    assert oversized.status_code == 413
    assert client.post("/api/submissions", content=json.dumps({"alias": "X", "code": CODE}), headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/submissions", json={"alias": "X", "code": CODE, "kind": "reference"}).status_code == 422


def test_deadline_restart_and_admin_token_not_overwritten(api, monkeypatch, capsys):
    client, app = api
    session = open_session(client)
    submitted = submit(client).json()
    store = app.state.store
    store.update(session={**session, "deadline": 1.0})
    assert client.get("/api/state").json()["session"]["status"] == "closed"
    assert submit(client, "Late").status_code == 409
    monkeypatch.setenv("POD_ADMIN_TOKEN", "replacement-must-not-work")
    capsys.readouterr()
    restarted = create_app(store.directory, race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    assert TOKEN in capsys.readouterr().out  # Returning teachers can retrieve the same key from the console.
    with TestClient(restarted) as other:
        state = other.get("/api/state").json()
        assert state["session"]["deadline"] == 1.0
        assert state["submissions"][0]["id"] == submitted["id"]
        assert other.post("/api/admin/session/start", headers={"X-Admin-Token": "replacement-must-not-work"}, json={"duration_seconds": 7200}).status_code == 401
        assert other.post("/api/admin/session/start", headers=AUTH, json={"duration_seconds": 7200}).status_code == 200


def test_capacity_and_concurrent_claim_protection(api):
    client, app = api
    open_session(client)
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(lambda _: submit(client, "Concurrent"), range(8)))
    assert sum(response.status_code == 200 for response in responses) == 1
    assert sum(response.status_code == 409 for response in responses) == 7
    for index in range(99):
        assert submit(client, f"Pilot {index}").status_code == 200
    assert len(client.get("/api/state").json()["submissions"]) == 100
    assert submit(client, "Overflow").status_code == 409
    entry = next(response.json() for response in responses if response.status_code == 200)
    assert submit(client, "Concurrent", claim_token=entry["claim_token"]).status_code == 200


def test_student_practice_runs_current_owned_bot_without_mutating_classroom(api):
    client, app = api
    open_session(client)
    saved = submit(client, "Practice pilot", "print('current private practice source')").json()

    response = client.post("/api/practice", json={"alias": saved["alias"], "claim_token": saved["claim_token"]})

    assert response.status_code == 200, response.text
    replay = response.json()
    assert replay["kind"] == "practice" and replay["status"] == "finished"
    assert replay["collisions"] is False and len(replay["entries"]) == 2
    assert replay["entries"][0]["id"] == saved["id"]
    assert "current private practice source" not in response.text and saved["claim_token"] not in response.text
    state = client.get("/api/state").json()
    assert state["replays"] == [] and state["active_replay_id"] is None
    assert state["job"]["status"] == "idle" and state["session"]["status"] == "open"
    assert app.state.store.submissions(private=True)[0]["version"] == 1

    denied = client.post("/api/practice", json={"alias": saved["alias"], "claim_token": "wrong-token"})
    assert denied.status_code == 409
    assert "current private practice source" not in denied.text and saved["claim_token"] not in denied.text


def test_http_qualification_final_replay_persistence_reset(api):
    client, app = api
    open_session(client)
    for alias in [f"Pilot {index}" for index in range(6)] + ["Crash"]:
        assert submit(client, alias).status_code == 200
    assert client.post("/api/admin/qualify", headers=AUTH).status_code == 202
    wait(app)
    qualified = client.get("/api/state").json()
    assert qualified["session"]["status"] == "qualified"
    assert qualified["job"]["completed"] == qualified["job"]["total"] == 21
    assert len(qualified["leaderboard"]) == 7 and len(qualified["finalists"]) == 5
    assert qualified["leaderboard"][-1]["alias"] == "Crash"
    assert submit(client, "Frozen").status_code == 409
    assert client.post("/api/admin/session/start", headers=AUTH, json={"duration_seconds": 7200}).status_code == 409
    assert client.post("/api/admin/qualify", headers=AUTH).status_code == 409
    assert client.post("/api/admin/final", headers=AUTH).status_code == 202
    wait(app)
    finished = client.get("/api/state").json()
    assert finished["session"]["status"] == "finished" and finished["champion"]
    assert finished['job']['completed'] == finished['job']['total'] == 3
    assert len(finished['replays']) == 24
    assert len([row for row in finished['replays'] if row['kind'] == 'final']) == 3
    replay_id = finished["active_replay_id"]
    replay = client.get(f"/api/replays/{replay_id}")
    assert replay.status_code == 200
    assert replay.json()["collisions"] is False and len(replay.json()["entries"]) == 5
    assert replay.json()['series_index'] == replay.json()['series_total'] == 3
    assert all(isinstance(row['finish_time'], float) for row in replay.json()['results'])
    assert "private-student-source" not in replay.text and "claim_token" not in replay.text and '"code"' not in replay.text
    assert TOKEN not in replay.text and "secret-source" not in replay.text
    assert client.get("/api/replays/not-a-uuid").status_code == 404
    restored = create_app(app.state.store.directory, sandbox_fn=sandbox_ready)
    with TestClient(restored) as other:
        assert other.get("/api/state").json()["champion"] == finished["champion"]
        assert other.get(f"/api/replays/{replay_id}").json() == replay.json()
    assert client.post("/api/admin/final", headers=AUTH).status_code == 409
    assert client.post("/api/admin/reset", headers=AUTH, json={"confirm": "no"}).status_code == 422
    assert client.post("/api/admin/reset", headers=AUTH, json={"confirm": "RESET"}).status_code == 200
    reset = client.get("/api/state").json()
    assert reset["session"]["status"] == "waiting" and reset["submissions"] == [] and reset["replays"] == []
    assert reset["champion"] is None and reset["job"]["status"] == "idle"
    assert client.get(f"/api/replays/{replay_id}").status_code == 404
    assert app.state.store.admin_token == TOKEN


def test_offline_failure_keeps_submissions_open(api):
    client, app = api
    open_session(client)
    assert submit(client).status_code == 200
    app.state.tournament.sandbox_fn = lambda: {"available": False, "detail": "offline", "image": "test"}
    assert client.post("/api/admin/qualify", headers=AUTH).status_code == 503
    state = client.get("/api/state").json()
    assert state["session"]["status"] == "open" and state["job"]["status"] == "idle"
    assert submit(client, "Still open").status_code == 200


def test_live_replay_readable_and_reset_race_blocked(api):
    client, app = api
    open_session(client)
    submit(client, "A")
    submit(client, "B")
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return fake_race(*args, **kwargs)

    app.state.tournament.race_fn = blocked
    assert client.post("/api/admin/qualify", headers=AUTH).status_code == 202
    assert entered.wait(2)
    try:
        state = client.get("/api/state").json()
        replay = client.get(f"/api/replays/{state['active_replay_id']}").json()
        assert replay["status"] == "running" and "code" not in replay["entries"][0]
        assert client.post("/api/admin/reset", headers=AUTH, json={"confirm": "RESET"}).status_code == 409
        assert client.post("/api/admin/final", headers=AUTH).status_code == 409
        assert client.post("/api/admin/qualify", headers=AUTH).status_code == 409
    finally:
        release.set()
        wait(app)


def test_demo_real_examples_only_empty_waiting_no_autorun(api):
    client, app = api
    example_count = len(list((Path(__file__).resolve().parents[1] / "examples").glob("*.py")))
    response = client.post("/api/admin/demo", headers=AUTH)
    if example_count < 6:
        assert response.status_code == 503
        assert client.get("/api/state").json()["submissions"] == []
        return
    assert response.status_code == 200 and response.json()["inserted"] == 6
    state = client.get("/api/state").json()
    assert len(state["submissions"]) == 6 and state["session"]["status"] == "waiting"
    assert state["leaderboard"] == [] and state["replays"] == [] and state["job"]["status"] == "idle"
    assert app.state.tournament.worker is None
    for entry in app.state.store.submissions(private=True):
        ast.parse(entry["code"])
    assert client.post("/api/admin/demo", headers=AUTH).status_code == 409


def test_starter_rules_and_site_contract(api):
    client, _ = api
    starter = client.get("/api/starter")
    assert starter.status_code == 200 and "starter.py" in starter.headers["content-disposition"]
    ast.parse(starter.text)
    rules = client.get("/api/rules").json()
    assert rules["qualification_tracks"] == 3 and rules["final_pods"] == 5
    assert "Nearest" in rules["protocol"]["opponent"]
    web = Path(__file__).resolve().parents[1] / "web"
    if (web / "index.html").exists():
        for route in ("/", "/teacher", "/projector"):
            assert client.get(route).status_code == 200
        assert 'id="test-bot"' in (web / "index.html").read_text(encoding="utf-8")
        for asset in ("app.js", "styles.css"):
            if (web / asset).exists():
                assert client.get(f"/assets/{asset}").status_code == 200
