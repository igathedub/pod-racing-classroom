"""Real Docker/HTTP/Chromium security smoke test; never publish or reset live data."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
PRESERVED = ("session", "submissions", "leaderboard", "job", "replays", "active_replay_id", "finalists", "champion")


def docker(*args, check=True, **kwargs):
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True,
                          errors="replace", timeout=180, **kwargs)


def request(base, path, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    merged = {"Content-Type": "application/json", **(headers or {})}
    req = Request(base + path, data=data, headers=merged)
    try:
        response = urlopen(req, timeout=90)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        return response.status, response.headers, json.loads(body)


def live_state(url):
    return request(url, "/api/state")[2] if url else None


def wait_for_job(base):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = request(base, "/api/state")[2]
        if state["job"]["status"] == "finished":
            return state
        assert state["job"]["status"] != "failed", "Isolated tournament failed."
        time.sleep(0.2)
    raise RuntimeError("Isolated tournament timed out.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-url", help="Optional read-only live state comparison.")
    args = parser.parse_args()
    before = live_state(args.live_url)
    tag = uuid.uuid4().hex[:12]
    image, container, volume = f"pod-http-security:{tag}", f"pod-http-security-{tag}", f"pod-http-security-data-{tag}"
    label = f"pod-http-security-check={tag}"
    report = {}
    try:
        docker("build", "-t", image, ".", cwd=ROOT)
        docker("volume", "create", "--label", label, volume)
        admin = "test-only-" + secrets.token_urlsafe(24)
        env = {**os.environ, "POD_ADMIN_TOKEN": admin}
        docker("run", "-d", "--name", container, "--label", label,
               "-p", "127.0.0.1::8765", "--mount", f"type=volume,source={volume},target=/data",
               "--mount", "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
               "-e", "POD_ADMIN_TOKEN", "-e", "POD_PUBLIC_ORIGINS=https://codeweek-wi.de",
               "-e", "POD_ALLOWED_HOSTS=codeweek-wi.de,127.0.0.1,localhost",
               "-e", "POD_SUBMISSIONS_PER_MINUTE=20", "-e", "POD_PRACTICE_PER_MINUTE=2",
               image, env=env)
        published = docker("port", container, "8765/tcp").stdout.strip()
        assert published.startswith("127.0.0.1:")
        base = "http://" + published
        deadline = time.monotonic() + 90
        while True:
            try:
                if request(base, "/api/state")[2]["sandbox"]["available"]:
                    break
            except (OSError, ValueError):
                pass
            assert time.monotonic() < deadline, "Isolated server failed readiness."
            time.sleep(0.5)
        public = {"Host": "codeweek-wi.de", "Origin": "https://codeweek-wi.de"}
        auth = {**public, "X-Admin-Token": admin}
        status, headers, initial = request(base, "/api/state")
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert "unsafe-eval" not in headers["Content-Security-Policy"]
        assert request(base, "/api/state", headers={"Host": "attacker.example"})[0] == 400
        assert request(base, "/api/admin/session/start", {"duration_seconds": 7200}, public)[0] == 401
        assert request(base, "/api/admin/session/start", {"duration_seconds": 7200},
                       {**auth, "Origin": "https://attacker.example"})[0] == 403
        assert request(base, "/api/state")[2]["session"] == initial["session"]
        assert request(base, "/api/admin/session/start", {"duration_seconds": 7200}, auth)[0] == 200
        code = (ROOT / "examples/cruise.py").read_text(encoding="utf-8")
        def submit(index):
            return request(base, "/api/submissions", {"alias": f"Security Demo {index:02d}", "code": code}, public)
        with ThreadPoolExecutor(max_workers=10) as executor:
            submissions = list(executor.map(submit, range(20)))
        assert all(response[0] == 200 for response in submissions)
        status, blocked_headers, _ = request(base, "/api/submissions", {"alias": "Blocked burst", "code": code},
                                            {**public, "CF-Connecting-IP": "203.0.113.9"})
        assert status == 429 and int(blocked_headers["Retry-After"]) >= 1
        entry = submissions[0][2]
        frames = []
        for _ in range(2):
            status, _, replay = request(base, "/api/practice", {"alias": entry["alias"], "claim_token": entry["claim_token"]}, public)
            assert status == 200 and replay["kind"] == "practice" and replay["frames"]
            frames.append(len(replay["frames"]))
        assert request(base, "/api/practice", {"alias": entry["alias"], "claim_token": entry["claim_token"]}, public)[0] == 429
        assert request(base, "/api/state")[2]["replays"] == []
        assert request(base, "/api/admin/qualify", {}, auth)[0] == 202
        qualified = wait_for_job(base)
        assert len(qualified["replays"]) == len(submissions) * 3
        assert request(base, "/api/admin/final", {}, auth)[0] == 202
        finished = wait_for_job(base)
        from playwright.sync_api import sync_playwright
        views = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for path in ("/", "/teacher", "/projector"):
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.expose_function("recordCSP", lambda directive: errors.append(directive))
                page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSP(e.effectiveDirective))")
                page.goto(base + path + "?lang=de")
                page.wait_for_function("() => document.body.dataset.hasReplay === 'true'")
                assert page.locator("#follow-live").inner_text() == "Automatisch folgen: AN"
                assert not errors, errors
                views.append(path)
                page.close()
            browser.close()
        after = live_state(args.live_url)
        if before is not None:
            assert all(before[key] == after[key] for key in PRESERVED), "Live classroom changed during isolated test."
        report = {"passed": True, "simultaneous_submissions": len(submissions), "practice_frame_counts": frames,
                  "qualification_replays": len(qualified["replays"]), "final_replays": len(finished["replays"]),
                  "browser_views": views, "csp_violations": 0, "origin_denied": True, "unknown_host_denied": True,
                  "submission_and_practice_429_verified": True, "live_state_unchanged": True if before is not None else None}
    finally:
        for kind, name in (("container", container), ("volume", volume)):
            inspected = docker(kind, "inspect", name, check=False)
            if inspected.returncode == 0:
                record = json.loads(inspected.stdout)[0]
                labels = record.get("Config", {}).get("Labels", {}) if kind == "container" else record.get("Labels", {})
                assert (labels or {}).get("pod-http-security-check") == tag, "Refusing cleanup of unrelated resource."
                docker("rm", "-f", name) if kind == "container" else docker("volume", "rm", name)
        docker("image", "rm", image, check=False)
    out = ROOT / "artifacts/http-security-smoke.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Verification report:", out)


if __name__ == "__main__":
    main()
