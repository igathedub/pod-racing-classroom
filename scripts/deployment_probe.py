"""Stdlib acceptance probe inside a DISPOSABLE Compose classroom only.

Called by deployment_test.py, never run against a classroom with real students.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DATA = Path(os.environ.get("POD_DATA_DIR", "/data"))
EVIDENCE = DATA / "deployment-acceptance.json"
BASE = "http://127.0.0.1:8765"


def teacher_token() -> str:
    with sqlite3.connect(DATA / "classroom.sqlite3") as db:
        return json.loads(db.execute("SELECT value FROM config WHERE key='admin_token'").fetchone()[0])


def request(path: str, payload=None, *, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Admin-Token"] = token
    with urlopen(Request(BASE + path, data=data, headers=headers), timeout=30) as response:
        return json.load(response)


def code_for(index: int) -> str:
    return f'''while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
        ox, oy = map(int, input().split())
    except EOFError:
        break
    thrust = {100 - index * 5} if abs(angle) < {85 - index * 3} else 0
    print(cx, cy, thrust, flush=True)
'''


def verify_restrictions() -> dict:
    # Inspect an exact container created by this probe, never somebody else's bot.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from arena.bots import DockerRunner

    runner = DockerRunner({"code": code_for(0)})
    try:
        result = subprocess.run(["docker", "inspect", runner.name], capture_output=True,
                                text=True, check=True, timeout=15)
        info = json.loads(result.stdout)[0]
        host = info["HostConfig"]
        assert info["Config"]["User"] == "65534:65534"
        assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"] is True
        assert host["CapDrop"] == ["ALL"]
        assert "no-new-privileges:true" in host["SecurityOpt"]
        assert host["Memory"] == 64 * 1024 * 1024 and host["NanoCpus"] == 500_000_000
        assert host["PidsLimit"] == 32 and host["LogConfig"]["Type"] == "none"
        assert not host["Binds"] and not host.get("Mounts")
        assert all(mount["Type"] == "tmpfs" and mount["Destination"] == "/tmp" for mount in info["Mounts"])
        assert "/tmp" in host["Tmpfs"] and "noexec" in host["Tmpfs"]["/tmp"]
        assert runner.act("0 0 10000 4000 10000 0\n1000 1000\n", first=True) == "10000 4000 100"
    finally:
        runner.close()
    removed = subprocess.run(["docker", "container", "inspect", runner.name],
                             capture_output=True, timeout=15)
    assert removed.returncode != 0, "Exact probe bot was not removed"
    return {"nonroot": True, "network": "none", "host_mounts": 0, "read_only": True,
            "cap_drop": ["ALL"], "memory_mib": 64, "cpu": 0.5, "pids": 32,
            "socket_absent": True, "cleanup": "passed"}


def wait_job(phase: str) -> dict:
    until = time.monotonic() + 600
    while time.monotonic() < until:
        state = request("/api/state")
        job = state["job"]
        assert job["status"] != "failed", job
        if job["status"] == "finished":
            assert job["phase"] == phase, job
            return state
        time.sleep(0.5)
    raise TimeoutError(phase + " exceeded 600 seconds")


def main() -> None:
    token = teacher_token()
    assert "POD_ADMIN_TOKEN" not in os.environ, "Test must exercise a generated teacher secret"
    digest = hashlib.sha256(token.encode()).hexdigest()
    assert len(token) >= 32
    if sys.argv[1:] == ["--persisted"]:
        evidence = json.loads(EVIDENCE.read_text())
        state = request("/api/state")
        assert digest == evidence["secret_sha256"], "Teacher secret changed"
        assert state["sandbox"]["available"]
        assert state["champion"] == evidence["champion"]
        assert state["session"] == evidence["session"]
        assert state["leaderboard"] == evidence["leaderboard"]
        assert state["submissions"] == evidence["submissions"]
        assert state["replays"] == evidence["replays"]
        replay = request("/api/replays/" + evidence["final_replay_id"])
        assert replay["winner_id"] == evidence["champion"]["id"]
        assert len(replay["frames"]) == evidence["final_frames"]
        # The persisted key also still authorizes protected teacher reads.
        request("/api/admin/submissions/" + state["submissions"][0]["id"], token=token)
        print(json.dumps({"persistence": "passed", "champion": state["champion"],
                          "final_frames": len(replay["frames"])}))
        return
    assert not sys.argv[1:], "Unknown probe option"
    state = request("/api/state")
    assert state["session"]["status"] == "waiting" and not state["submissions"], "Refuse non-empty classroom"
    assert state["sandbox"]["available"], state["sandbox"]
    restrictions = verify_restrictions()
    try:
        request("/api/admin/session/start", {"duration_seconds": 7200})
    except HTTPError as exc:
        assert exc.code in (401, 403)
    else:
        raise AssertionError("Missing teacher authorization accepted")
    request("/api/admin/session/start", {"duration_seconds": 7200}, token=token)
    for index in range(6):
        request("/api/submissions", {"alias": f"Compose Pilot {index + 1}", "code": code_for(index)})
    assert len(request("/api/state")["submissions"]) == 6
    request("/api/admin/qualify", {}, token=token)
    qualified = wait_job("qualification")
    assert len(qualified["leaderboard"]) == 6
    assert all(not item["disqualified"] for item in qualified["leaderboard"]), qualified["leaderboard"]
    assert len(qualified["finalists"]) == 5
    assert [x["id"] for x in qualified["leaderboard"][:5]] == [x["id"] for x in qualified["finalists"]]
    request("/api/admin/final", {}, token=token)
    state = wait_job("final")
    assert state["champion"] is not None
    metadata = next(x for x in reversed(state["replays"]) if x["kind"] == "final")
    replay = request("/api/replays/" + metadata["id"])
    assert replay["status"] == "finished" and replay["collisions"] is True
    assert len(replay["entries"]) == 5 and len(replay["frames"]) > 5
    assert replay["winner_id"] == state["champion"]["id"]
    assert token not in json.dumps(state)
    assert all("code" not in x and "claim_token" not in x for x in state["submissions"])
    evidence = {key: state[key] for key in ("session", "leaderboard", "submissions", "replays", "champion")}
    evidence.update(secret_sha256=digest, final_replay_id=metadata["id"], final_frames=len(replay["frames"]))
    EVIDENCE.write_text(json.dumps(evidence), encoding="utf-8")
    print(json.dumps({"qualification_entries": 6, "restrictions": restrictions,
                      "finalists": [x["alias"] for x in state["finalists"]],
                      "champion": state["champion"], "final_frames": len(replay["frames"]),
                      "final_results": replay["results"]}))


if __name__ == "__main__":
    main()
