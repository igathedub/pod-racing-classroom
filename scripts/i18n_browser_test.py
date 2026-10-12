"""Real Edge/HTTP i18n acceptance test; never touches the classroom on port 8765.

Run: .venv/Scripts/python.exe scripts/i18n_browser_test.py
Uses an isolated real uvicorn server, real API submissions, and genuine trusted
reference-engine races (never executes submitted student source on the host).
Screenshots and the JSON report are retained in Hermes scratch.
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
sys.path.insert(0, str(ROOT))
KEY = "synthetic-i18n-browser-test-only"


def ready(page, language="en"):
    expected = "Server connected" if language == "en" else "Server verbunden"
    page.wait_for_function("value => document.querySelector('#connection-text').textContent === value", arg=expected)


def language(page, value):
    with page.expect_response(lambda response: response.url.endswith('/api/state') and response.request.headers.get('accept-language') == value):
        page.locator("#language-switch").select_option(value)
    page.wait_for_function("value => document.documentElement.lang === value", arg=value)
    ready(page, value)
    page.wait_for_function("value => document.body.dataset.stateLanguage === value", arg=value)


def seek(page, position):
    page.locator("#scrubber").evaluate("(el, position) => { el.value = position; el.dispatchEvent(new Event('input', {bubbles:true})); }", position)


def main():
    scratch = Path(os.environ.get("POD_TEST_SCRATCH", Path.home() / "AppData/Local/hermes/cache/scratch"))
    scratch.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="pod-i18n-evidence-", dir=scratch))
    with tempfile.TemporaryDirectory(prefix="pod-i18n-data-", dir=scratch) as folder:
        data = Path(folder) / "data"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        assert port != 8765
        env = {**os.environ, "POD_DATA_DIR": str(data), "POD_ADMIN_TOKEN": KEY}
        base = f"http://127.0.0.1:{port}"
        errors, requests, screenshots = [], [], []
        with (evidence / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "arena.app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            client = httpx.Client(base_url=base, timeout=30)
            try:
                for _ in range(120):
                    try:
                        client.get("/api/state").raise_for_status()
                        break
                    except httpx.ConnectError:
                        time.sleep(.2)
                else:
                    raise TimeoutError("Isolated server failed to start")
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel="msedge", headless=True)
                    context = browser.new_context(viewport={"width": 1440, "height": 1000})
                    def track(page):
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("request", lambda request: requests.append({"url": request.url, "method": request.method, "lang": request.headers.get("accept-language"), "admin": "x-admin-token" in request.headers}) if "/api/" in request.url else None)
                    def shot(page, name):
                        page.screenshot(path=str(evidence / name), full_page=True)
                        screenshots.append(name)
                    teacher = context.new_page()
                    track(teacher)
                    teacher.goto(base + "/teacher")
                    ready(teacher)
                    assert teacher.locator("#countdown-label").inner_text() == "Coding session"
                    assert teacher.locator("#start-session").inner_text() == "Open coding session"
                    teacher.locator("#admin-token").fill(KEY)
                    language(teacher, "de")
                    assert teacher.locator("#admin-token").input_value() == KEY  # unsaved key preserved
                    assert teacher.locator("#start-session").inner_text() == "Programmierphase starten"
                    assert teacher.locator("#countdown-label").inner_text() == "Programmierphase"
                    assert teacher.locator("#replay-select").inner_text() == "Noch keine Rennen"
                    assert teacher.locator("#inspect-select").text_content() == "Noch keine Abgaben"
                    teacher.locator("#admin-auth button[type=submit]").click()
                    teacher.locator("#start-session").click()
                    teacher.wait_for_function("document.querySelector('#session-status').textContent === 'Abgabe ist geöffnet'")
                    assert client.get("/api/state").json()["session"]["duration_seconds"] == 7200
                    teacher.locator("#reset").click()
                    assert teacher.locator("#reset-dialog").is_visible()
                    assert "RESET" in teacher.locator("label[for=reset-confirm]").inner_text()
                    language(teacher, "en")
                    assert teacher.locator("#reset-dialog").is_visible()
                    teacher.locator("#cancel-reset").click()  # No reset request
                    language(teacher, "de")
                    shot(teacher, "teacher-de.png")
                    teacher.reload()
                    ready(teacher, "de")
                    assert teacher.locator("#admin-token").input_value() == KEY

                    student = context.new_page()
                    track(student)
                    student.goto(base + "/")  # shared localStorage, no query override
                    ready(student, "de")
                    assert student.title() == "Pod Lab · Rennarena für Lernende"
                    alias = "Student Teacher Final"
                    code = "# Student Teacher Final BOOST input() RESET\nprint('0 0 100', flush=True)\n"
                    student.locator("#alias").fill(alias)
                    student.locator("#code").evaluate("el => el.reportValidity()")
                    assert student.locator("#code").evaluate("el => el.validationMessage") == "Füge deinen Python-Code ein."
                    language(student, "en")
                    assert student.locator("#code").evaluate("el => el.validationMessage") == "Paste your Python code."
                    (evidence / "draft.py").write_text(code, encoding="utf-8")
                    student.locator("#code-file").set_input_files(evidence / "draft.py")
                    student.wait_for_function("document.querySelector('#code').value.includes('Student Teacher Final')")
                    assert student.locator("#code").evaluate("el => el.validationMessage") == ""
                    student.locator("#code").fill(code)
                    language(student, "en")
                    assert student.locator("#alias").input_value() == alias
                    assert student.locator("#code").input_value() == code
                    language(student, "de")
                    student.locator("#alias").fill("bad!")
                    student.locator("#submit-bot").click()
                    assert "Verwende" in student.locator("#submission-message").inner_text()
                    language(student, "en")
                    assert "Use 1–24" in student.locator("#submission-message").inner_text()
                    language(student, "de")
                    student.locator("#alias").fill(alias)
                    student.locator("#code").fill("if !!!")
                    student.locator("#submit-bot").click()
                    student.wait_for_function("document.querySelector('#submission-message').textContent.includes('Syntaxfehler')")
                    language(student, "en")
                    assert "syntax error" in student.locator("#submission-message").inner_text()
                    language(student, "de")
                    assert "Syntaxfehler" in student.locator("#submission-message").inner_text()
                    student.locator("#code").fill(code)
                    student.locator("#submit-bot").click()
                    student.wait_for_function("document.querySelector('#submission-message').textContent.includes('Version 1')")
                    token = student.locator("#claim-token").input_value()
                    assert token and student.evaluate("localStorage.getItem('pod-lab:claim:student teacher final')") == token
                    language(student, "en")
                    assert "version 1" in student.locator("#submission-message").inner_text()
                    assert student.locator("#claim-token").input_value() == token
                    assert student.locator("#alias").input_value() == alias
                    assert student.locator("#code").input_value() == code
                    student.reload()
                    ready(student, "en")
                    assert student.locator("#alias").input_value() == alias
                    assert student.evaluate("localStorage.getItem('pod-lab:claim:student teacher final')") == token
                    student.goto(base + "/?lang=de")
                    ready(student, "de")
                    assert student.evaluate("localStorage.getItem('pod-lab:language')") == "de"
                    assert student.locator("a[download='starter.py']").get_attribute("href") == "/api/starter?lang=de"
                    with student.expect_download() as downloading:
                        student.locator("a[download='starter.py']").click()
                    downloading.value.save_as(evidence / "starter-de.py")
                    assert "Lies" in (evidence / "starter-de.py").read_text(encoding="utf-8")
                    student.locator("details").first.locator("summary").click()
                    guide = student.locator("details").first
                    assert "nächsten Gegner" in guide.inner_text()
                    assert "x y checkpoint_x checkpoint_y distance relative_angle" in guide.inner_text()
                    assert "target_x target_y thrust" in guide.inner_text()
                    student.locator("#rules-toggle").click()
                    student.wait_for_function("document.querySelector('#rules-content').dataset.loaded === 'true'")
                    de_rules = student.locator("#rules-content").inner_text()
                    language(student, "en")
                    student.wait_for_function("document.querySelector('#rules-content').dataset.loaded === 'true'")
                    assert student.locator("#rules-content").inner_text() != de_rules
                    language(student, "de")
                    shot(student, "student-de.png")

                    # Genuine trusted engine data, not invented replay frames/rankings.
                    from arena.store import Store
                    from arena.tournament import Tournament
                    from arena.engine import make_tracks, run_race
                    from arena.bots import ReferenceRunner
                    store = Store(data)
                    entered = store.submissions()[0]
                    other = store.submit("Reference ghost", code)
                    references = [{"id": entered["id"], "alias": alias, "kind": "reference", "code": "racer"}, {"id": other["id"], "alias": "Reference ghost", "kind": "reference", "code": "cautious"}]
                    tournament = Tournament(store)
                    tournament._qualify(references, make_tracks())
                    class TrustedInvalidRunner:
                        def act(self, observation, first=False):
                            return "invalid trusted test command"
                        def close(self):
                            pass
                    def invalid_race(entries, track, **kwargs):
                        return run_race(entries, track, runner_factory=lambda entry: TrustedInvalidRunner() if entry['id'] == entered['id'] else ReferenceRunner(entry), **kwargs)
                    dq_replay = Tournament(store, race_fn=invalid_race)._race(references, make_tracks()[0], "qualification", alias + " · Wide Circuit", False)
                    tournament._final(references, make_tracks(seed=2026, count=1)[0])
                    state = client.get("/api/state").raise_for_status().json()
                    final_id = state["active_replay_id"]
                    replay = client.get("/api/replays/" + final_id).raise_for_status().json()
                    assert len(replay["frames"]) > 20
                    assert state["champion"] is not None
                    projector = context.new_page()
                    track(projector)
                    projector.goto(base + "/projector?lang=de")
                    ready(projector, "de")
                    projector.wait_for_function("!document.querySelector('#scrubber').disabled")
                    seek(projector, 10)
                    projector.locator("#speed").select_option("4")
                    assert projector.locator("#play-pause").inner_text() == "Abspielen"
                    before = projector.locator("#scrubber").input_value()
                    language(projector, "en")
                    projector.wait_for_timeout(500)
                    assert projector.locator("#replay-select").input_value() == final_id
                    assert projector.locator("#scrubber").input_value() == before
                    assert projector.locator("#speed").input_value() == "4"
                    assert projector.locator("#play-pause").inner_text() == "Play"
                    assert projector.locator("#champion-label").inner_text() == "Final result revealed at the finish."
                    assert "Winner:" not in projector.locator("#replay-select").inner_text()
                    assert alias in projector.locator("#rankings").inner_text()
                    assert "Reference ghost" in projector.locator("#rankings").inner_text()  # student alias, not baseline
                    language(projector, "de")
                    projector.wait_for_timeout(500)
                    assert projector.locator("#scrubber").input_value() == before
                    assert "Finale" in projector.locator("#race-heading").inner_text()
                    assert projector.locator("#track-name").inner_text() == "Breiter Rundkurs"
                    shot(projector, "projector-de.png")
                    qualification_id = next(item["id"] for item in state["replays"] if item["kind"] == "qualification")
                    projector.locator("#replay-select").select_option(qualification_id)
                    projector.wait_for_function("!document.querySelector('#scrubber').disabled")
                    seek(projector, 5)
                    assert "Referenz-Bot" in projector.locator("#rankings").inner_text()
                    language(projector, "en")
                    assert projector.locator("#replay-select").input_value() == qualification_id
                    assert projector.locator("#follow-live").get_attribute("aria-pressed") == "false"
                    projector.locator("#replay-select").select_option(dq_replay['id'])
                    projector.wait_for_function("!document.querySelector('#scrubber').disabled")
                    seek(projector, 5)
                    assert "DQ" in projector.locator("#rankings").inner_text()
                    assert "invalid command" in projector.locator("#rankings").inner_text()
                    language(projector, "de")
                    projector.wait_for_function("document.querySelector('#rankings').textContent.includes('ungültigen Befehl')")
                    language(projector, "en")
                    projector.locator("#replay-select").select_option(final_id)
                    projector.wait_for_function("document.querySelector('#race-format').textContent.includes('contact')")
                    seek(projector, projector.locator("#scrubber").get_attribute("max"))
                    assert projector.locator("#winner-overlay").is_visible()
                    winner = projector.locator("#winner-name").inner_text()
                    language(projector, "de")
                    assert projector.locator("#winner-name").inner_text() == winner
                    assert "RENNSIEGER" in projector.locator("#winner-overlay").inner_text()
                    # Keyboard semantics remain protocol keys, not translated labels.
                    projector.locator("#restart").click()
                    projector.locator("#race-heading").click()
                    projector.keyboard.press("Space")
                    assert projector.locator("#play-pause").inner_text() == "Pause"
                    projector.keyboard.press("Space")
                    assert projector.locator("#play-pause").inner_text() == "Abspielen"
                    projector.locator("#fullscreen").click()
                    projector.wait_for_function("!!document.fullscreenElement")
                    projector.wait_for_function("document.querySelector('#fullscreen').textContent === 'Vollbild verlassen'")
                    projector.locator("#language-switch").evaluate("el => { el.value='en'; el.dispatchEvent(new Event('change', {bubbles:true})); }")
                    assert projector.locator("#fullscreen").inner_text() == "Exit fullscreen"
                    projector.locator("#fullscreen").click()
                    projector.wait_for_function("!document.fullscreenElement")

                    for page, role in ((teacher, "teacher"), (student, "student"), (projector, "projector")):
                        language(page, "de")
                        assert not any(word in page.locator("body").inner_text().lower() for word in ("two-hour", "2-hour", "twohour"))
                        page.set_viewport_size({"width": 390, "height": 844})
                        page.wait_for_timeout(100)
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), role
                        shot(page, role + "-mobile-de.png")
                        page.set_viewport_size({"width": 320, "height": 844})
                        page.wait_for_timeout(100)
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), role + " at 320px"
                    # Requests are real browser requests. Public reads never carry teacher keys.
                    assert any(item["lang"] == "de" and item["url"].endswith("/api/state") for item in requests)
                    assert any(item["lang"] == "en" and "/api/replays/" in item["url"] for item in requests)
                    assert not any(item["admin"] and "/api/admin/" not in item["url"] for item in requests)
                    assert not any("/api/admin/reset" in item["url"] for item in requests)
                    assert not errors, errors
                    # Storage-denied locale changes stay functional (no credential overwrite).
                    blocked = browser.new_context(viewport={"width": 390, "height": 844})
                    blocked.add_init_script("Storage.prototype.getItem = Storage.prototype.setItem = Storage.prototype.removeItem = () => { throw new Error('storage blocked'); };")
                    blocked_page = blocked.new_page()
                    track(blocked_page)
                    blocked_page.goto(base + "/?lang=de")
                    ready(blocked_page, "de")
                    language(blocked_page, "en")
                    assert not errors, errors
                    browser.close()
                report = {"passed": True, "browser": "msedge", "isolated_port": port, "real_reference_frames": len(replay["frames"]), "language_persistence": True, "shared_link_override": True, "claim_and_teacher_keys_preserved": True, "replay_transport_preserved": True, "storage_denied_fallback": True, "page_errors": errors, "screenshots": screenshots, "evidence_directory": str(evidence)}
                (evidence / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps(report, indent=2))
            finally:
                client.close()
                server.terminate()
                server.wait(timeout=15)


if __name__ == "__main__":
    main()
