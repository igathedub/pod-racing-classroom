"""Real Chromium layout regressions; isolated classroom state, no live writes."""
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

from test_api import api, open_session  # noqa: F401 -- imports the isolated pytest fixture


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

        def serve(route):
            url = urlsplit(route.request.url)
            assert route.request.method == "GET", "Layout tests must never submit student code."
            response = client.get(url.path + ("?" + url.query if url.query else ""))
            route.fulfill(status=response.status_code, body=response.content,
                          content_type=response.headers.get("content-type", "text/plain"))

        page.route("**/*", serve)
        page.goto(f"http://classroom.test/?lang={language}")
        page.wait_for_function("!document.getElementById('submit-bot').disabled")
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
