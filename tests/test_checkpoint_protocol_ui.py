"""Chromium verifies the backup-only protocol guide and new editor source."""
from pathlib import Path
from urllib.parse import urlsplit
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from test_base_path import prefixed


def test_chromium_checkpoint_only_editor_and_guide_match_backend(tmp_path,monkeypatch):
    monkeypatch.setenv('POD_INPUT_PROTOCOL','checkpoint-only')
    app=prefixed(tmp_path,monkeypatch,POD_CLASS_ACCESS_REQUIRED=0)
    source=(Path(__file__).resolve().parents[1]/'examples/starters/05_Nadja_checkpoint.py').read_text()
    with TestClient(app,base_url='https://classroom.test') as client,sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,chromium_sandbox=True)
        page=browser.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def serve(route):
            req=route.request
            url=urlsplit(req.url)
            assert url.netloc=='classroom.test'
            response=client.request(req.method,url.path+('?' + url.query if url.query else ''),headers=req.headers,content=req.post_data_buffer)
            route.fulfill(status=response.status_code,body=response.content,headers=dict(response.headers))
        page.route('**/*',serve)
        page.goto('https://classroom.test/backup/?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        assert page.locator('body').get_attribute('data-input-protocol')=='checkpoint-only'
        assert page.locator('#code').input_value()==source
        assert 'Einzeilen-Test' in page.locator('#protocol-notice').inner_text()
        guide=page.locator('#student-panel details.help-block').first
        guide.locator('summary').click()
        assert len(guide.locator('pre').first.inner_text().splitlines())==1
        assert 'opponent_x' not in guide.inner_text()
        assert 'eine Zeile' in guide.inner_text()
        page.locator('#code').fill(source+'\n# mein Entwurf\n')
        page.locator('#language-switch').select_option('en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        assert page.locator('#code').input_value().endswith('# mein Entwurf\n')
        assert 'one line' in guide.inner_text()
        assert not errors
        browser.close()
