"""Browser -> HTTP -> Docker -> final replay acceptance test, isolated test data.

Run with the project's Playwright install. Uses installed Edge or Chrome, with
bundled Chromium as a last fallback. Screenshots/evidence go under artifacts/.
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
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    scratch = Path(os.environ.get("TMPDIR", ROOT / "artifacts"))
    scratch.mkdir(parents=True, exist_ok=True)
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pod-browser-", dir=scratch) as folder:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update(POD_DATA_DIR=str(Path(folder) / "data"), POD_ADMIN_TOKEN="synthetic-browser-test-only")
        base_url = f"http://127.0.0.1:{port}"
        with (Path(folder) / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "arena.app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            started = time.monotonic()
            client = httpx.Client(base_url=base_url, timeout=30)
            try:
                for _ in range(100):
                    try:
                        state = client.get("/api/state").raise_for_status().json()
                        break
                    except httpx.ConnectError:
                        time.sleep(0.2)
                else:
                    raise TimeoutError("Test server did not start")
                assert state["sandbox"]["available"], state["sandbox"]
                with sync_playwright() as playwright:
                    browser = None
                    for channel in ("msedge", "chrome", None):
                        try:
                            browser = playwright.chromium.launch(channel=channel, headless=True)
                            break
                        except Exception:
                            continue
                    if browser is None:
                        raise RuntimeError("No browser available for Playwright verification")
                    context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
                    teacher = context.new_page()
                    page_errors = []
                    console_errors = []
                    for page in (teacher,):
                        page.on("pageerror", lambda error: page_errors.append(str(error)))
                        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" and "status of 422" not in msg.text else None)
                    teacher.on("dialog", lambda dialog: dialog.accept())
                    teacher.goto(base_url + "/teacher")
                    teacher.wait_for_function("document.querySelector('#connection-text').textContent === 'Server connected'")
                    teacher.locator("#admin-token").fill("synthetic-browser-test-only")
                    teacher.locator("#admin-auth button[type=submit]").click()
                    teacher.locator("#start-session").click()
                    teacher.wait_for_function("document.querySelector('#session-status').textContent === 'Submissions are open'")
                    student_context = browser.new_context(viewport={"width": 1280, "height": 1000})
                    student = student_context.new_page()
                    student.on("pageerror", lambda error: page_errors.append(str(error)))
                    student.goto(base_url + "/")
                    student.wait_for_function("!document.querySelector('#submit-bot').disabled")
                    student.locator("#alias").fill("Browser Pilot 1")
                    student.locator("#code").fill("if !!!")
                    student.locator("#submit-bot").click()
                    student.wait_for_function("document.querySelector('#submission-message').textContent.includes('syntax error')")
                    student.locator("#code").fill((ROOT / "examples" / "starter.py").read_text(encoding="utf-8"))
                    student.locator("#submit-bot").click()
                    student.wait_for_function("document.querySelector('#submission-message').textContent.includes('version 1')")
                    student.reload()
                    student.wait_for_function("!document.querySelector('#submit-bot').disabled")
                    student.locator("#alias").fill("Browser Pilot 1")
                    student.locator("#code").fill((ROOT / "examples" / "starter.py").read_text(encoding="utf-8"))
                    student.locator("#submit-bot").click()
                    student.wait_for_function("document.querySelector('#submission-message').textContent.includes('version 2')")
                    for index, name in enumerate(("boost", "cautious", "cornering", "momentum", "sprinter"), 2):
                        student.locator("#alias").fill(f"Browser Pilot {index}")
                        student.locator("#code").fill((ROOT / "examples" / f"{name}.py").read_text(encoding="utf-8"))
                        student.locator("#submit-bot").click()
                        student.wait_for_function("document.querySelector('#submission-message').textContent.includes('version 1')")
                    student.screenshot(path=str(artifacts / "student-submission.png"), full_page=True)
                    teacher.wait_for_function("document.querySelector('#entry-count').textContent === '6'")
                    teacher.locator("#qualify").click()
                    teacher.wait_for_function("document.querySelector('#session-status').textContent === 'Qualification complete'", timeout=480000)
                    qualified = client.get("/api/state").raise_for_status().json()
                    assert len(qualified["finalists"]) == 5
                    assert len(qualified["leaderboard"]) == 6
                    teacher.screenshot(path=str(artifacts / "teacher-qualified.png"), full_page=True)
                    teacher.locator("#run-final").click()
                    teacher.wait_for_function("document.querySelector('#session-status').textContent === 'Classroom final complete'", timeout=180000)
                    final_state = client.get("/api/state").raise_for_status().json()
                    assert final_state["champion"] is not None, final_state
                    replay = client.get("/api/replays/" + final_state["active_replay_id"]).raise_for_status().json()
                    assert len(replay["entries"]) == 5 and len(replay["frames"]) > 10
                    projector = context.new_page()
                    projector.on("pageerror", lambda error: page_errors.append(str(error)))
                    projector.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                    projector.goto(base_url + "/projector")
                    projector.wait_for_function("document.querySelector('#race-format').textContent.includes('5 pods')")
                    if projector.locator("#play-pause").inner_text() == "Pause":
                        projector.locator("#play-pause").click()
                    projector.locator("#scrubber").evaluate("el => { el.value = Math.min(60, Number(el.max)); el.dispatchEvent(new Event('input', {bubbles: true})); }")
                    projector.wait_for_timeout(300)
                    assert "Winner:" not in projector.locator("#replay-select").inner_text()
                    assert projector.locator("#champion-label").inner_text() == "Final result revealed at the finish."
                    projector.screenshot(path=str(artifacts / "projector-race.png"), full_page=True)
                    projector.locator("#scrubber").evaluate("el => { el.value = el.max; el.dispatchEvent(new Event('input', {bubbles: true})); }")
                    projector.wait_for_function("!document.querySelector('#winner-overlay').hidden")
                    assert final_state["champion"]["alias"] in projector.locator("#winner-name").inner_text()
                    projector.screenshot(path=str(artifacts / "projector-winner.png"), full_page=True)
                    for page in (student, teacher, projector):
                        page.set_viewport_size({"width": 390, "height": 844})
                        page.wait_for_timeout(100)
                        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), page.url
                    student.screenshot(path=str(artifacts / "student-mobile.png"), full_page=True)
                    assert not page_errors, page_errors
                    assert not console_errors, console_errors
                    # Read back same SQLite data in a freshly started server process.
                    server.terminate()
                    server.wait(timeout=15)
                    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "arena.app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                    for _ in range(100):
                        try:
                            restored = client.get("/api/state").raise_for_status().json()
                            break
                        except httpx.HTTPError:
                            time.sleep(0.2)
                    else:
                        raise TimeoutError("Server restart failed")
                    assert restored["champion"] == final_state["champion"]
                    assert restored["leaderboard"] == final_state["leaderboard"]
                    assert client.get("/api/replays/" + replay["id"]).raise_for_status().json() == replay
                    report = {"passed": True, "elapsed_seconds": round(time.monotonic() - started, 2), "students": 6, "finalists": len(replay["entries"]), "champion": final_state["champion"]["alias"], "final_frames": len(replay["frames"]), "page_errors": page_errors, "console_errors": console_errors, "restart_persistence": True, "screenshots": ["student-submission.png", "teacher-qualified.png", "projector-race.png", "projector-winner.png", "student-mobile.png"]}
                    (artifacts / "browser-result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                    print(json.dumps(report, indent=2), flush=True)
                    student_context.close()
                    context.close()
                    browser.close()
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
