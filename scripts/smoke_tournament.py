"""Real API-to-Docker acceptance test in a disposable classroom database.

Run: uv run python scripts/smoke_tournament.py
Creates only test data. Does not modify the actual classroom database.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def code_for(index: int) -> str:
    return f'''import sys
while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
        ox, oy = map(int, input().split())
    except EOFError:
        break
    thrust = {100 - index * 5} if abs(angle) < {85 - index * 3} else 0
    print(cx, cy, thrust, flush=True)
'''


def main() -> None:
    scratch = Path(os.environ.get("TMPDIR", ROOT / "artifacts"))
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pod-acceptance-", dir=scratch) as directory:
        port = free_port()
        admin_token = "synthetic-acceptance-test-only"
        env = os.environ.copy()
        env["POD_DATA_DIR"] = str(Path(directory) / "data")
        env["POD_ADMIN_TOKEN"] = admin_token
        logfile = Path(directory) / "server.log"
        with logfile.open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "arena.app:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)
            headers = {"X-Admin-Token": admin_token}
            try:
                for _ in range(120):
                    if server.poll() is not None:
                        raise RuntimeError("Server failed to start: " + logfile.read_text(encoding="utf-8"))
                    try:
                        state = client.get("/api/state").raise_for_status().json()
                        break
                    except httpx.ConnectError:
                        time.sleep(0.25)
                else:
                    raise TimeoutError("Server startup timed out")
                assert state["session"]["status"] == "waiting", state
                assert state["sandbox"]["available"], state["sandbox"]
                assert client.post("/api/admin/session/start", json={"duration_seconds": 7200}).status_code in (401, 403)
                client.post("/api/admin/session/start", headers=headers, json={"duration_seconds": 7200}).raise_for_status()
                submitted = []
                for index in range(6):
                    response = client.post("/api/submissions", json={"alias": f"Smoke Pilot {index + 1}", "code": code_for(index)})
                    response.raise_for_status()
                    submitted.append(response.json())
                response = client.post("/api/submissions", json={"alias": "Smoke Crash", "code": "raise RuntimeError('deliberate test crash')"})
                response.raise_for_status()
                assert client.post("/api/submissions", json={"alias": "Smoke Pilot 1", "code": code_for(0)}).status_code in (401, 403, 409)
                assert client.post("/api/submissions", json={"alias": "Syntax Error", "code": "if !!!"}).status_code in (400, 422)
                assert "claim_token" not in client.get("/api/state").text
                assert admin_token not in client.get("/api/state").text
                client.post("/api/admin/qualify", headers=headers).raise_for_status()
                locked = client.post("/api/submissions", json={"alias": "Late Pilot", "code": code_for(0)})
                assert locked.status_code in (403, 409, 423), locked.text

                def wait_job(phase: str) -> dict:
                    until = time.monotonic() + 480
                    previous = None
                    while time.monotonic() < until:
                        current = client.get("/api/state").raise_for_status().json()
                        job = current["job"]
                        progress = (job["completed"], job["total"], job["status"])
                        if progress != previous:
                            print(phase, progress, job.get("message", ""), flush=True)
                            previous = progress
                        if job["status"] == "failed":
                            raise AssertionError(job)
                        if job["status"] == "finished":
                            return current
                        time.sleep(0.4)
                    raise TimeoutError(f"{phase} exceeded acceptance test timeout")

                qualified = wait_job("qualification")
                assert len(qualified["leaderboard"]) == 7, qualified
                assert len(qualified["finalists"]) == 5, qualified
                assert all(entry["alias"] != "Smoke Crash" for entry in qualified["finalists"])
                first_ids = [entry["id"] for entry in qualified["leaderboard"] if not entry["disqualified"]][:5]
                assert first_ids == [entry["id"] for entry in qualified["finalists"]]
                client.post("/api/admin/final", headers=headers).raise_for_status()
                final_state = wait_job("final")
                assert final_state["champion"] is not None, final_state
                final_metadata = next(item for item in reversed(final_state["replays"]) if item["kind"] == "final")
                replay = client.get(f"/api/replays/{final_metadata['id']}").raise_for_status().json()
                assert replay["status"] == "finished"
                assert len(replay["entries"]) == 5
                assert len(replay["frames"]) > 5
                assert replay["winner_id"] == final_state["champion"]["id"]
                assert replay["collisions"] is False
                assert all("code" not in entry for entry in replay["entries"])
                result = {
                    "submission_count": len(final_state["submissions"]),
                    "qualification_results": len(qualified["leaderboard"]),
                    "finalists": [entry["alias"] for entry in final_state["finalists"]],
                    "champion": final_state["champion"],
                    "final_frames": len(replay["frames"]),
                    "final_results": replay["results"],
                    "checks": ["admin authorization", "alias ownership", "syntax validation", "frozen submissions", "public secret exclusion", "real Docker qualifiers", "invalid bot exclusion", "top-five selection", "real five-pod collision-free final", "persisted replay"],
                }
                artifacts = ROOT / "artifacts"
                artifacts.mkdir(exist_ok=True)
                (artifacts / "smoke-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                (artifacts / "smoke-final-replay.json").write_text(json.dumps(replay), encoding="utf-8")
                print(json.dumps(result, indent=2), flush=True)
            finally:
                client.close()
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)


if __name__ == "__main__":
    main()
