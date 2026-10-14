"""Trusted container startup and stdlib HTTP/Docker readiness probe."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from urllib.request import urlopen

# Running a script sets sys.path[0] to scripts/, not the application root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def healthcheck() -> None:
    with urlopen("http://127.0.0.1:8765/api/health", timeout=12) as response:
        state = json.load(response)
    if not state["sandbox"]["available"]:
        raise SystemExit("Docker sandbox unavailable")


def main() -> None:
    if sys.argv[1:] == ["--healthcheck"]:
        healthcheck()
        return
    from arena.bots import sandbox_status

    deadline = time.monotonic() + 90
    while True:
        status = sandbox_status()
        if status["available"]:
            break
        if time.monotonic() >= deadline:
            raise SystemExit(status["detail"])
        print("Waiting for sandbox: " + status["detail"], flush=True)
        time.sleep(2)
    print("Docker sandbox ready. One classroom server worker; data: /data", flush=True)
    print("Teacher: http://localhost:<published-port>/teacher", flush=True)
    print("Projector: http://localhost:<published-port>/projector", flush=True)
    print("Trusted private LAN only: app Docker socket access equals host administration.", flush=True)
    # Exec keeps signal delivery direct; the backend prints its persisted token.
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "arena.app:app",
                             "--host", "0.0.0.0", "--port", "8765", "--workers", "1"])


if __name__ == "__main__":
    main()
