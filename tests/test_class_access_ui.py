"""Real Chromium + isolated FastAPI; fake race/sandbox, actual CSP retained."""
import time
import pytest
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from test_api import AUTH, TOKEN
from test_class_access import gated


@pytest.mark.parametrize('language', ['de', 'en'])
def test_chromium_teacher_invitation_controls(tmp_path, monkeypatch, language):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        errors, reads = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.expose_function('recordCSPViolation', lambda directive: errors.append('CSP: ' + directive))
        page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSPViolation(e.effectiveDirective))")
        def serve(route):
            req = route.request
            url = urlsplit(req.url)
            if url.path == '/api/state':
                reads.append(req.headers.get('x-admin-token'))
            client.cookies.clear()
            response = client.request(req.method, url.path + ('?' + url.query if url.query else ''),
                                      headers=req.headers, content=req.post_data_buffer)
            route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))
        context.route('**/*', serve)
        page.goto(f'https://classroom.test/teacher?lang={language}')
        page.wait_for_function("() => document.body.dataset.access === 'unauthorized'")
        assert reads == []
        page.locator('#admin-token').fill(TOKEN)
        page.locator('#admin-auth button[type=submit]').click()
        page.wait_for_function("value => document.body.dataset.stateLanguage === value", arg=language)
        assert reads and all(value == TOKEN for value in reads)
        assert page.locator('#invitation-controls').get_attribute('open') is None
        app.state.store.update(job={'status': 'running', 'phase': 'qualification', 'completed': 0, 'total': 1, 'message': ''})
        page.wait_for_function("value => document.querySelector('#job-heading').textContent === value", arg='Qualifikation läuft' if language == 'de' else 'Qualification running')
        page.locator('#invitation-controls summary').click()
        assert page.locator('#create-invitation').is_enabled()
        page.locator('#create-invitation').click()
        page.wait_for_function("() => document.querySelector('#invitation-code').textContent.length >= 32")
        first = page.locator('#invitation-code').inner_text()
        assert first not in str(app.state.store.get('class_access'))
        page.locator('#create-invitation').click()
        page.wait_for_function("value => document.querySelector('#invitation-code').textContent !== value", arg=first)
        second = page.locator('#invitation-code').inner_text()
        assert second and second != first
        page.locator('#revoke-invitation').click()
        page.wait_for_function("() => document.querySelector('#invitation-code').textContent === ''")
        assert not client.get('/api/admin/access/invitation', headers=AUTH).json()['active']
        page.locator('#teacher-access summary').click()
        page.locator('#forget-key').click()
        assert page.locator('#invitation-code').inner_text() == ''
        assert not page.locator('#create-invitation').is_enabled()
        assert errors == []
        browser.close()


@pytest.mark.parametrize('language,label', [('de', 'Der Klasse beitreten'), ('en', 'Join classroom')])
def test_chromium_projector_join_and_expiry(tmp_path, monkeypatch, language, label):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def serve(route):
            req = route.request
            url = urlsplit(req.url)
            client.cookies.clear()
            response = client.request(req.method, url.path + ('?' + url.query if url.query else ''), headers=req.headers, content=req.post_data_buffer)
            route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))
        page.route('**/*', serve)
        page.goto(f'https://classroom.test/projector?lang={language}')
        page.wait_for_function("() => document.body.dataset.access === 'unauthorized'")
        assert page.locator('#join-form button').inner_text() == label
        assert not page.locator('.race-panel').is_visible()
        page.locator('#join-code').fill(code)
        page.locator('#join-form button').click()
        page.wait_for_function("() => document.body.dataset.stateLanguage !== undefined")
        assert page.locator('.race-panel').is_visible()
        assert not page.locator('#student-panel').is_visible()
        assert not page.locator('#teacher-panel').is_visible()
        state = app.state.store.get('class_access')
        state['expires_at'] = time.time() - 1
        app.state.store.update(class_access=state)
        page.wait_for_function("() => document.body.dataset.access === 'unauthorized'")
        assert page.locator('#join-form').is_visible()
        assert not page.locator('.race-panel').is_visible()
        assert errors == []
        browser.close()


@pytest.mark.parametrize('language', ['de', 'en'])
def test_chromium_archival_replays_return_after_rejoin(tmp_path, monkeypatch, language):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        assert client.post('/api/admin/session/start', json={}, headers=AUTH).status_code == 200
        for alias in ('Pilot A', 'Pilot B'):
            assert client.post('/api/submissions', json={'alias': alias, 'code': 'print(1)'}, headers=AUTH).status_code == 200
        app.state.tournament.start_qualification()
        app.state.tournament.worker.join(10)
        assert not app.state.tournament.worker.is_alive()
        assert app.state.store.get('job')['status'] == 'finished'
        stored = app.state.store.replays()
        assert len(stored) == 6
        assert all(replay['kind'] == 'qualification' for replay in stored)
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.expose_function('recordCSPViolation', lambda directive: errors.append('CSP: ' + directive))
        page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSPViolation(e.effectiveDirective))")

        def serve(route):
            req = route.request
            url = urlsplit(req.url)
            client.cookies.clear()
            response = client.request(req.method, url.path + ('?' + url.query if url.query else ''),
                                      headers=req.headers, content=req.post_data_buffer)
            route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))
            client.cookies.clear()

        context.route('**/*', serve)
        document = page.goto(f'https://classroom.test/?lang={language}')
        assert "script-src 'self'" in document.headers['content-security-policy']
        page.evaluate("() => window.rejoinDocumentMarker = 'same document'")
        page.wait_for_function("() => document.body.dataset.access === 'unauthorized'")
        page.locator('#join-code').fill(code)
        page.locator('#join-form button').click()
        page.wait_for_function("() => document.querySelector('#replay-select').options.length === 6 && document.body.dataset.hasReplay === 'true'")
        options = page.locator('#replay-select').evaluate("el => Array.from(el.options, option => [option.value, option.textContent])")
        signature = page.locator('#replay-select').get_attribute('data-signature')
        assert {value for value, _ in options} == {replay['id'] for replay in stored}
        assert signature
        assert client.post('/api/admin/access/revoke', json={}, headers=AUTH).status_code == 200
        page.wait_for_function("() => document.body.dataset.access === 'unauthorized'")
        assert page.locator('#join-panel').is_visible()
        assert not page.locator('#student-panel').is_visible()
        assert not page.locator('.race-panel').is_visible()
        assert page.locator('#replay-select option').count() == 0
        locked_signature = page.locator('#replay-select').get_attribute('data-signature')
        assert errors == []
        renewed = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        assert renewed != code
        page.locator('#join-code').fill(renewed)
        page.locator('#join-form button').click()
        page.wait_for_function("() => document.body.dataset.access === 'authorized' && document.body.dataset.hasReplay === 'true'")
        restored = page.locator('#replay-select').evaluate("el => ({signature: el.dataset.signature, options: Array.from(el.options, option => [option.value, option.textContent])})")
        assert errors == []
        assert restored['options'] == options, (
            f"Replay options missing after rejoin: length={len(restored['options'])}; "
            f"unchanged_signature={restored['signature'] == signature}; "
            f"locked_signature_unchanged={locked_signature == signature}"
        )
        page.locator('#follow-live').click()
        for replay_id, title in options:
            with page.expect_response(lambda response: urlsplit(response.url).path == '/api/replays/' + replay_id) as loaded:
                page.locator('#replay-select').select_option(replay_id)
            assert loaded.value.status == 200
            replay = loaded.value.json()
            assert replay['id'] == replay_id and len(replay['frames']) == 2
            page.wait_for_function("title => document.querySelector('#race-heading').textContent === title && !document.querySelector('#restart').disabled && document.body.dataset.hasReplay === 'true'", arg=title)
            assert page.locator('#replay-select').input_value() == replay_id
            assert page.locator('#track-name').inner_text() == replay['track']['name']
            assert page.locator('#replay-error').is_hidden()
        assert page.evaluate("() => window.rejoinDocumentMarker") == 'same document'
        assert page.url == f'https://classroom.test/?lang={language}'
        assert app.state.store.replays() == stored
        assert errors == []
        browser.close()


def test_chromium_join_submit_private_practice_and_revoke(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        client.post('/api/admin/session/start', json={}, headers=AUTH)
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.expose_function('recordCSPViolation', lambda directive: errors.append('CSP: ' + directive))
        page.add_init_script("addEventListener('securitypolicyviolation', e => window.recordCSPViolation(e.effectiveDirective))")
        def serve(route):
            req = route.request
            url = urlsplit(req.url)
            requests.append((req.method, url.path, 'x-admin-token' in req.headers))
            client.cookies.clear()
            response = client.request(req.method, url.path + ('?' + url.query if url.query else ''),
                                      headers=req.headers, content=req.post_data_buffer)
            route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))
            client.cookies.clear()
        context.route('**/*', serve)
        page.goto('https://classroom.test/?lang=de')
        assert page.locator('#join-form').is_visible(timeout=3000)
        assert not page.locator('#student-panel').is_visible()
        assert not any(path == '/api/state' for _, path, _ in requests)
        page.locator('#join-code').fill('wrong')
        page.locator('#join-form button').click()
        page.wait_for_function("() => document.querySelector('#join-message').textContent.length > 0")
        assert not page.locator('#student-panel').is_visible()
        page.locator('#join-code').fill(code)
        page.locator('#join-form button').click()
        page.wait_for_function("() => !document.querySelector('#submit-bot').disabled")
        page.locator('#alias').fill('Browser pilot')
        page.locator('#code').fill('print(1) # preserved editor')
        assert page.locator('#submit-bot').inner_text() == 'Deinen Bot abgeben'
        assert page.locator('#code').bounding_box()['height'] >= 400
        page.locator('#submit-bot').click()
        page.wait_for_function("() => localStorage.getItem('pod-lab:claim:browser pilot') !== null")
        claim = page.evaluate("() => localStorage.getItem('pod-lab:claim:browser pilot')")
        original = app.state.store.submissions(private=True)[0]
        assert original['version'] == 1
        page.locator('#test-bot').click()
        page.wait_for_function("() => document.querySelector('#submission-message').textContent === 'Testaufzeichnung ist bereit.'")
        assert page.locator('#follow-live').inner_text() == 'Automatisch folgen: AUS'
        assert app.state.store.replays() == []
        before_revoke = app.state.store.submissions(private=True)[0]
        # Test this code saves once more before requesting its private race.
        assert before_revoke['id'] == original['id']
        assert before_revoke['version'] == original['version'] + 1
        assert errors == []
        client.post('/api/admin/access/revoke', json={}, headers=AUTH)
        page.wait_for_function("() => !document.querySelector('#join-panel').hidden")
        assert not page.locator('#student-panel').is_visible()
        assert not page.locator('.race-panel').is_visible()
        assert page.locator('#code').input_value() == 'print(1) # preserved editor'
        assert page.evaluate("() => localStorage.getItem('pod-lab:claim:browser pilot')") == claim
        assert app.state.store.submissions(private=True) == [before_revoke]
        # Keep this classroom open: qualification would correctly reject resubmission.
        assert app.state.store.get('session')['status'] == 'open'
        renewed = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        assert renewed != code
        page.evaluate("() => window.rejoinDocumentMarker = 'same document'")
        page.locator('#join-code').fill(renewed)
        page.locator('#join-form button').click()
        page.wait_for_function("() => document.body.dataset.access === 'authorized' && !document.querySelector('#submit-bot').disabled")
        assert page.locator('#student-panel').is_visible()
        assert page.locator('#alias').input_value() == 'Browser pilot'
        assert page.locator('#code').input_value() == 'print(1) # preserved editor'
        assert page.evaluate("() => localStorage.getItem('pod-lab:claim:browser pilot')") == claim
        with page.expect_response(lambda response: response.request.method == 'POST' and urlsplit(response.url).path == '/api/submissions') as submitted:
            page.locator('#submit-bot').click()
        response = submitted.value
        assert response.request.post_data_json['claim_token'] == claim
        assert response.status == 200
        result = response.json()
        assert result['id'] == original['id']
        assert result['version'] == before_revoke['version'] + 1
        updated = app.state.store.submissions(private=True)
        assert len(updated) == 1
        assert updated[0]['id'] == original['id']
        assert updated[0]['version'] == 3
        assert app.state.store.claimed_submission('Browser pilot', claim)['id'] == original['id']
        assert page.locator('#code').input_value() == original['code']
        assert page.evaluate("() => localStorage.getItem('pod-lab:claim:browser pilot')") == claim
        assert page.evaluate("() => window.rejoinDocumentMarker") == 'same document'
        assert app.state.store.replays() == []
        assert not any(admin for _, _, admin in requests)
        assert errors == []
        browser.close()
