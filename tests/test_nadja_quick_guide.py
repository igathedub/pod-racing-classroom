"""The checkpoint-only quick guide uses Nadja's real variable names."""
import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit
import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from test_base_path import prefixed


@pytest.mark.parametrize('base', ['', '/backup'])
def test_nadja_guide_input_output_and_language_switch(tmp_path, monkeypatch, base):
    monkeypatch.setenv('POD_INPUT_PROTOCOL', 'checkpoint-only')
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base, POD_CLASS_ACCESS_REQUIRED=0)
    nadja = (Path(__file__).resolve().parents[1] / 'examples/starters/05_Nadja_checkpoint.py').read_text()
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, chromium_sandbox=True)
        try:
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def serve(route):
                req = route.request
                url = urlsplit(req.url)
                assert url.netloc == 'classroom.test'
                response = client.request(req.method, url.path + ('?' + url.query if url.query else ''), headers=req.headers, content=req.post_data_buffer)
                route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))
            page.route('**/*', serve)
            page.goto('https://classroom.test' + base + '/?lang=de')
            page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
            guide = page.locator('#student-panel details.help-block').first
            guide.locator('summary').click()
            snippets = guide.locator('pre').all_text_contents()
            assert snippets[0] == 'x y next_checkpoint_x next_checkpoint_y next_checkpoint_dist winkel'
            assignment = 'x, y, next_checkpoint_x, next_checkpoint_y, next_checkpoint_dist, winkel = [abs(int(i)) for i in input().split()]'
            output = 'print(next_checkpoint_x, next_checkpoint_y, schub)'
            assert assignment in snippets and assignment in nadja
            assert output in snippets and output in nadja
            assert '7000 2000 100' in snippets
            assert 'opponent_x' not in guide.inner_text()
            assert 'eine Zeile' in guide.inner_text()
            assert 'Betrag des Winkels' in guide.inner_text()
            assert 'boost_verfuegbar = False' in guide.inner_text()
            assert page.locator('#code').input_value() == nadja
            page.locator('#language-switch').select_option('en')
            page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
            assert 'absolute value of the angle' in guide.inner_text()
            assert 'one line' in guide.inner_text()
            assert page.locator('#code').input_value() == nadja
            assert not errors
        finally:
            browser.close()


@pytest.mark.parametrize('base', ['', '/backup'])
def test_page_versions_assets_by_their_actual_content(tmp_path, monkeypatch, base):
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base, POD_CLASS_ACCESS_REQUIRED=0)
    root = Path(__file__).resolve().parents[1]
    with TestClient(app) as client:
        page = client.get(base + '/').text
        for name in ['app.js', 'i18n.js', 'styles.css']:
            digest = hashlib.sha256((root / 'web' / name).read_bytes()).hexdigest()[:16]
            pattern = r'(?:src|href)="(' + re.escape(base + '/assets/' + name) + r'\?v=' + digest + r')"'
            match = re.search(pattern, page)
            assert match, f'{name} must bypass stale CDN/browser content by version'
            assert client.get(match[1]).content == (root / 'web' / name).read_bytes()
