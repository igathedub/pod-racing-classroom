"""Real Chromium views with actual CSP and isolated synthetic TestClient apps."""
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from test_base_path import prefixed
from test_api import AUTH, TOKEN


@pytest.mark.parametrize('base', ['', '/backup', '/campus/Backup_2-live'])
def test_chromium_prefixed_views_and_api_urls(tmp_path, monkeypatch, base):
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base, POD_CLASS_ACCESS_REQUIRED=0)
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context()
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.expose_function('recordCSPViolation', lambda directive: errors.append('CSP: ' + directive))
        page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSPViolation(e.effectiveDirective))")

        def serve(route):
            request = route.request
            url = urlsplit(request.url)
            requests.append(url.path)
            client.cookies.clear()
            response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                                      headers=request.headers, content=request.post_data_buffer)
            route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))

        context.route('**/*', serve)
        for view, suffix in [('student', '/'), ('teacher', '/teacher'), ('projector', '/projector')]:
            document = page.goto('https://classroom.test' + base + suffix + '?lang=de')
            assert "script-src 'self'" in document.headers['content-security-policy']
            page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
            assert page.locator('body').get_attribute('data-view') == view
            assert page.locator(f'nav [data-view="{view}"]').get_attribute('aria-current') == 'page'
            assert page.locator(f'#{view}-panel').is_visible()
            assert urlsplit(page.locator('[download="starter.py"]').get_attribute('href')).path == base + '/api/starter'
        page.locator('nav [data-view="student"]').click()
        page.wait_for_url('https://classroom.test' + base + '/?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage !== undefined")
        assert page.evaluate("async () => (await fetch(document.querySelector('[download=\"starter.py\"]').href)).status") == 200
        assert {base + '/api/access', base + '/api/state', base + '/api/starter',
                base + '/assets/app.js', base + '/assets/i18n.js', base + '/assets/styles.css'} <= set(requests)
        assert all(path.startswith(base + '/') for path in requests)
        assert errors == []
        browser.close()


def test_chromium_backup_storage_does_not_reuse_or_overwrite_root_claims_or_admin(tmp_path, monkeypatch):
    app = prefixed(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context()
        context.add_init_script("""
            localStorage.setItem('pod-lab:claim:pilot', 'root-claim-sentinel');
            localStorage.setItem('pod-lab:last-alias', 'Root Pilot');
            sessionStorage.setItem('pod-lab:admin', 'teacher-test-secret');
        """)
        page = context.new_page()
        errors, reads = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.expose_function('recordCSPViolation', lambda directive: errors.append('CSP: ' + directive))
        page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSPViolation(e.effectiveDirective))")

        def serve(route):
            req = route.request
            url = urlsplit(req.url)
            if url.path == '/backup/api/state':
                reads.append(req.headers.get('x-admin-token'))
            client.cookies.clear()
            response = client.request(req.method, url.path + ('?' + url.query if url.query else ''),
                                      headers=req.headers, content=req.post_data_buffer)
            route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))

        context.route('**/*', serve)
        page.goto('https://classroom.test/backup/teacher?lang=en')
        page.wait_for_function("() => document.body.dataset.access !== 'pending'")
        assert page.locator('body').get_attribute('data-access') == 'unauthorized'
        assert reads == []
        page.locator('#admin-token').fill(TOKEN)
        page.locator('#admin-auth button[type=submit]').click()
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        assert reads and all(value == TOKEN for value in reads)
        assert page.evaluate("sessionStorage.getItem('pod-lab:/backup:admin')") == TOKEN
        page.locator('#invitation-controls summary').click()
        page.locator('#create-invitation').click()
        page.wait_for_function("() => document.querySelector('#invitation-code').textContent.length >= 32")
        code = page.locator('#invitation-code').inner_text()
        page.locator('#start-session').click()
        page.wait_for_function("() => !document.querySelector('#close-session').disabled")
        page.goto('https://classroom.test/backup/?lang=en')
        page.wait_for_function("() => document.body.dataset.access === 'unauthorized'")
        assert page.locator('#alias').input_value() == ''
        page.locator('#join-code').fill(code)
        page.locator('#join-form button').click()
        page.wait_for_function("() => !document.querySelector('#submit-bot').disabled")
        page.locator('#alias').fill('Pilot')
        assert page.locator('#export-claim').is_disabled()
        page.locator('#code').fill('print(1)')
        page.locator('#submit-bot').click()
        page.wait_for_function("() => document.querySelector('#submission-message').textContent.includes('version 1')")
        claim = page.evaluate("localStorage.getItem('pod-lab:/backup:claim:pilot')")
        assert claim and claim != 'root-claim-sentinel'
        assert page.evaluate("localStorage.getItem('pod-lab:claim:pilot')") == 'root-claim-sentinel'
        assert page.evaluate("localStorage.getItem('pod-lab:last-alias')") == 'Root Pilot'
        assert page.evaluate("localStorage.getItem('pod-lab:/backup:last-alias')") == 'Pilot'
        page.reload()
        page.wait_for_function("() => !document.querySelector('#submit-bot').disabled")
        assert page.locator('#alias').input_value() == 'Pilot'
        assert page.locator('#export-claim').is_enabled()
        page.locator('#code').fill('print(2)')
        page.locator('#submit-bot').click()
        page.wait_for_function("() => document.querySelector('#submission-message').textContent.includes('version 2')")
        assert client.post('/backup/api/admin/access/revoke', json={}, headers=AUTH).status_code == 200
        page.wait_for_function("() => document.body.dataset.access === 'unauthorized'")
        page.goto('https://classroom.test/backup/teacher?lang=en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        page.locator('#teacher-access summary').click()
        page.locator('#forget-key').click()
        assert page.evaluate("sessionStorage.getItem('pod-lab:/backup:admin')") is None
        assert page.evaluate("sessionStorage.getItem('pod-lab:admin')") == TOKEN
        assert errors == []
        browser.close()
