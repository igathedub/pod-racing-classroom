"""Real Chromium proves initial textarea content and preservation while editing."""
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
import pytest

from test_base_path import prefixed

SOURCE = (Path(__file__).resolve().parents[1]/'examples/starters/05_Nadja.py').read_text(encoding='utf-8')


@pytest.mark.parametrize('base', ['', '/backup'])
def test_browser_nadja_default_and_edits_survive_language_change(tmp_path, monkeypatch, base):
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base, POD_CLASS_ACCESS_REQUIRED=0)
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context()
        page = context.new_page()
        errors, hosts = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def serve(route):
            req=route.request
            url=urlsplit(req.url)
            hosts.append(url.netloc)
            assert url.netloc=='classroom.test', 'No third-party runtime dependency allowed'
            response=client.request(req.method,url.path+('?' + url.query if url.query else ''),headers=req.headers,content=req.post_data_buffer)
            route.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
        context.route('**/*',serve)
        page.goto('https://classroom.test'+base+'/?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        assert page.locator('#code').input_value()==SOURCE
        assert '1,6 / 32 KiB' in page.locator('#code-size').inner_text()
        edited=SOURCE.replace('BREMS_DISTANZ = 900','BREMS_DISTANZ = 777')
        page.locator('#code').fill(edited)
        page.locator('#language-switch').select_option('en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        assert page.locator('#code').input_value()==edited
        assert errors==[]
        assert hosts
        browser.close()
