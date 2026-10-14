"""Real Chromium layout regressions; isolated classroom state, no live writes."""
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

from test_api import api, open_session  # noqa: F401 -- imports the isolated pytest fixture


@pytest.fixture
def ui_page(api):
    client, app = api
    open_session(client)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.expose_function("recordCSPViolation", lambda directive: errors.append("CSP violation: " + directive))
        page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSPViolation(e.effectiveDirective))")

        def serve(route):
            url = urlsplit(route.request.url)
            assert route.request.method == "GET", "UI checks must not mutate the live classroom."
            response = client.get(url.path + ("?" + url.query if url.query else ""), headers=route.request.headers)
            route.fulfill(status=response.status_code, body=response.content,
                          headers=dict(response.headers))

        page.route("**/*", serve)
        yield page, client, app
        assert errors == []
        browser.close()


@pytest.mark.parametrize("view", ["/", "/teacher", "/projector"])
@pytest.mark.parametrize("language,on,off", [("de", "Automatisch folgen: AN", "Automatisch folgen: AUS"),
                                            ("en", "Auto-follow: ON", "Auto-follow: OFF")])
def test_follow_switch_has_explicit_state(ui_page, view, language, on, off):
    page, _, _ = ui_page
    page.goto(f"http://classroom.test{view}?lang={language}")
    page.wait_for_function("() => document.body.dataset.stateLanguage !== undefined")
    toggle = page.locator("#follow-live")
    assert toggle.inner_text() == on
    assert toggle.get_attribute("aria-pressed") == "true"
    expected_tip = "Automatisch zum nächsten Klassenrennen wechseln." if language == "de" else "Automatically switch to the next classroom race."
    assert toggle.get_attribute("title") == expected_tip
    toggle.click()
    assert toggle.inner_text() == off
    assert toggle.get_attribute("aria-pressed") == "false"
    toggle.focus()
    page.keyboard.press("Space")
    assert toggle.inner_text() == on
    assert toggle.get_attribute("aria-pressed") == "true"


@pytest.mark.parametrize("view", ["/", "/teacher"])
def test_role_work_panel_precedes_race_and_hides_empty_standings(ui_page, view):
    page, _, _ = ui_page
    page.goto(f"http://classroom.test{view}?lang=de")
    page.wait_for_function("() => document.body.dataset.stateLanguage !== undefined")
    role = page.locator("#student-panel" if view == "/" else "#teacher-panel").bounding_box()
    race = page.locator(".race-panel").bounding_box()
    assert role["x"] < race["x"], "Primary work belongs before the race monitor on desktop"
    assert page.evaluate("""() => {
        const role = document.querySelector('#' + (document.body.dataset.view === 'student' ? 'student-panel' : 'teacher-panel'));
        return Boolean(role.compareDocumentPosition(document.querySelector('.race-panel')) & Node.DOCUMENT_POSITION_FOLLOWING);
    }"""), "Keyboard/DOM order must match the visual work-first order"
    assert not page.locator(".rank-panel").is_visible(), "Do not show a blank results panel"
    assert not page.locator(".site-footer").is_visible()
    assert not page.locator(".transport").is_visible(), "Playback controls need an actual replay"
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.locator("#student-panel" if view == "/" else "#teacher-panel").bounding_box()["y"] < page.locator(".race-panel").bounding_box()["y"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_teacher_setup_is_collapsed_and_twenty_submissions_remain_accessible(ui_page):
    page, client, _ = ui_page
    for index in range(20):
        assert client.post("/api/submissions", json={"alias": f"Demo {index:02d}", "code": "print(1)"}).status_code == 200
    page.goto("http://classroom.test/teacher?lang=de")
    page.wait_for_function("() => document.querySelector('#entry-count').textContent === '20'")
    assert not page.locator("#reset").is_visible(), "Reset is secondary, not an everyday action"
    assert not page.locator("#seed-demo").is_visible()
    assert page.locator("#teacher-access").get_attribute("open") is not None
    assert page.locator("#roster-panel").get_attribute("open") is not None
    assert page.locator("#teacher-panel #roster-panel").count() == 1
    assert page.locator("#roster li").count() == 20
    assert page.locator("#roster-count").inner_text() == "20"
    assert page.locator("#inspect-select option").count() == 20
    page.locator("#classroom-setup summary").click()
    assert page.locator("#reset").is_visible()
    page.goto("http://classroom.test/?lang=de")
    page.wait_for_function("() => document.querySelector('#entry-count').textContent === '20'")
    assert page.locator("#roster-panel").get_attribute("open") is None
    assert not page.locator("#roster").is_visible()
    page.locator("#roster-panel summary").click()
    assert page.locator("#roster").is_visible()


@pytest.mark.parametrize("view", ["/", "/teacher", "/projector"])
def test_replay_controls_and_results_return_when_races_exist(ui_page, view):
    page, client, app = ui_page
    for alias in ("Pilot A", "Pilot B"):
        assert client.post("/api/submissions", json={"alias": alias, "code": "print(1)"}).status_code == 200
    app.state.tournament.start_qualification()
    app.state.tournament.worker.join(10)
    assert app.state.store.get("job")["status"] == "finished"
    page.emulate_media(reduced_motion="reduce")
    page.goto(f"http://classroom.test{view}?lang=de")
    page.wait_for_function("() => document.body.dataset.hasReplay === 'true'")
    assert page.locator(".rank-panel").is_visible()
    assert page.locator(".transport").is_visible()
    assert page.locator("#race-canvas").bounding_box()["height"] >= 250
    page.locator("#replay-select").select_option(index=0)
    assert page.locator("#follow-live").inner_text() == "Automatisch folgen: AUS"
    page.locator("#follow-live").click()
    assert page.locator("#follow-live").inner_text() == "Automatisch folgen: AN"
    page.locator("#language-switch").select_option("en")
    assert page.locator("#follow-live").inner_text() == "Auto-follow: ON"
    if view == "/projector":
        assert not page.locator("#student-panel").is_visible()
        assert not page.locator("#teacher-panel").is_visible()
        assert not page.locator("#roster-panel").is_visible()
        assert page.locator("#playback-help").get_attribute("open") is None
        assert not page.locator("#playback-help p").first.is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_practice_replay_focuses_race_positions(ui_page):
    page, client, _ = ui_page

    def submit_to_isolated_api(route):
        if route.request.method != "POST":
            route.fallback()
            return
        response = client.post(urlsplit(route.request.url).path, json=route.request.post_data_json)
        route.fulfill(status=response.status_code, body=response.content, content_type="application/json")

    page.route("**/api/**", submit_to_isolated_api)
    page.goto("http://classroom.test/?lang=de")
    page.wait_for_function("() => !document.getElementById('test-bot').disabled")
    page.locator("#alias").fill("Practice pilot")
    page.locator("#code").fill("print(1)")
    page.locator("#test-bot").click()
    page.wait_for_function("() => document.querySelector('#submission-message').textContent === 'Testaufzeichnung ist bereit.'")
    assert page.locator("#tab-race").get_attribute("aria-selected") == "true"
    assert page.locator("#rankings tbody tr").count() == 2
    assert page.locator("#follow-live").inner_text() == "Automatisch folgen: AUS"
    assert client.get("/api/state").json()["replays"] == []


def test_twenty_results_do_not_stretch_the_student_editor(ui_page):
    page, client, app = ui_page
    for index in range(20):
        assert client.post("/api/submissions", json={"alias": f"Pilot {index:02d}", "code": "print(1)"}).status_code == 200
    app.state.tournament.start_qualification()
    app.state.tournament.worker.join(10)
    page.goto("http://classroom.test/?lang=de")
    page.wait_for_function("() => document.body.dataset.hasReplay === 'true'")
    assert page.locator("#rankings tbody tr").count() == 20
    assert page.locator("#rankings").bounding_box()["height"] <= 560
    panel = page.locator("#student-panel").bounding_box()
    last_help = page.locator("#student-panel .help-block").last.bounding_box()
    assert panel["y"] + panel["height"] <= last_help["y"] + last_help["height"] + 3
    page.locator("#rankings tbody tr").last.scroll_into_view_if_needed()
    assert page.locator("#rankings").evaluate("e => e.scrollTop > 0")


def test_saved_teacher_access_collapses_without_hiding_controls(ui_page):
    page, _, _ = ui_page
    page.add_init_script("sessionStorage.setItem('pod-lab:admin', 'teacher-test-secret')")
    page.goto("http://classroom.test/teacher?lang=de")
    page.wait_for_function("() => document.body.dataset.stateLanguage !== undefined")
    assert page.locator("#teacher-access").get_attribute("open") is None
    assert not page.locator("#admin-token").is_visible()
    assert page.locator("#start-session").is_enabled()
    page.locator("#teacher-access summary").click()
    page.locator("#forget-key").click()
    assert page.locator("#admin-token").is_visible()
    assert not page.locator("#start-session").is_enabled()


@pytest.mark.parametrize("width,height,language", [(1366, 768, "de"), (1920, 1080, "en"),
                                                   (1024, 768, "de"), (390, 844, "de")])
def test_open_session_student_actions_are_not_clipped(api, width, height, language):
    client, _ = api
    open_session(client)
    assert client.post("/api/submissions", json={"alias": "Existing pilot", "code": "print(1)"}).status_code == 200
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.expose_function("recordCSPViolation", lambda directive: errors.append("CSP violation: " + directive))
        page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSPViolation(e.effectiveDirective))")

        def serve(route):
            url = urlsplit(route.request.url)
            assert route.request.method == "GET", "Layout tests must never submit student code."
            response = client.get(url.path + ("?" + url.query if url.query else ""), headers=route.request.headers)
            route.fulfill(status=response.status_code, body=response.content,
                          headers=dict(response.headers))

        page.route("**/*", serve)
        page.goto(f"http://classroom.test/?lang={language}")
        page.wait_for_function("() => !document.getElementById('submit-bot').disabled")
        label = "Deinen Bot abgeben" if language == "de" else "Submit your bot"
        assert page.locator("#submit-bot").inner_text() == label
        page.locator("#alias").fill("Existing pilot")
        assert page.locator("#submit-bot").inner_text() == label
        for identifier in ("submit-bot", "test-bot"):
            button = page.locator(f"#{identifier}")
            box = button.bounding_box()
            panel = page.locator("#student-panel").bounding_box()
            assert box["y"] + box["height"] <= panel["y"] + panel["height"], (
                f"{identifier} is clipped below the student panel")
            assert box["y"] + box["height"] <= height, (
                f"{identifier} should be visible before scrolling through the code editor")
            assert button.is_enabled()
            assert button.evaluate("""e => {
                const r = e.getBoundingClientRect();
                return e.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
            }"""), f"{identifier} is not reachable by a pointer"
        assert page.locator("#code").bounding_box()["height"] >= 400
        assert errors == []
        browser.close()
