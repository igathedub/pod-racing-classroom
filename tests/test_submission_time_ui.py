"""Chromium exercises configurable coding windows through the real test API."""
import json

import pytest
from playwright.sync_api import expect

from test_api import AUTH
from test_moderation_ui import moderation_browser, teacher_sign_in


@pytest.mark.parametrize('base', ['', '/backup'])
def test_teacher_selects_minutes_and_updates_remaining_time(tmp_path, monkeypatch, base):
    with moderation_browser(tmp_path, monkeypatch, base) as (app, client, context, errors, _):
        page = context.new_page()
        page.goto('https://classroom.test' + base + '/teacher?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        field = page.locator('#submission-duration')
        expect(field).to_have_count(1, timeout=3000)
        expect(field).to_be_disabled()
        expect(field).to_have_value('120')
        teacher_sign_in(page)
        expect(field).to_be_enabled()
        field.fill('35')
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/admin/session/start')) as response:
            page.locator('#start-session').click()
        assert response.value.status == 200
        state = client.get(base + '/api/state').json()
        assert state['session']['duration_seconds'] == 35 * 60
        assert 0 < state['session']['deadline'] - state['server_time'] <= 35 * 60
        expect(page.locator('#start-session')).to_have_text('Restzeit setzen')
        field.fill('12')
        with page.expect_response(lambda r: r.request.method == 'GET' and r.url.endswith('/api/state')):
            page.wait_for_timeout(2200)
        expect(field).to_have_value('12')
        page.locator('#language-switch').select_option('en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        expect(field).to_have_value('12')
        expect(page.locator('#start-session')).to_have_text('Set remaining time')
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/admin/session/start')):
            page.locator('#start-session').click()
        state = client.get(base + '/api/state').json()
        assert state['session']['duration_seconds'] == 12 * 60
        assert 0 < state['session']['deadline'] - state['server_time'] <= 12 * 60
        assert not errors


def test_invalid_minutes_do_not_send_session_request(tmp_path, monkeypatch):
    with moderation_browser(tmp_path, monkeypatch) as (app, client, context, errors, _):
        page = context.new_page()
        requests = []
        page.on('request', lambda request: requests.append(request.post_data) if request.method == 'POST' and request.url.endswith('/api/admin/session/start') else None)
        page.goto('https://classroom.test/backup/teacher?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        expect(page.locator('#submission-duration')).to_have_count(1, timeout=3000)
        teacher_sign_in(page)
        for value in ('', '0', '-1', '1.5', '1441'):
            page.locator('#submission-duration').fill(value)
            page.locator('#start-session').click()
            expect(page.locator('#admin-message')).to_have_text('Wähle ganze Minuten von 1 bis 1440.')
        assert not requests and app.state.store.get('session')['status'] == 'waiting'
        for minutes in (1, 1440):
            page.locator('#submission-duration').fill(str(minutes))
            with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/admin/session/start')):
                page.locator('#start-session').click()
            assert json.loads(requests[-1]) == {'duration_seconds': minutes * 60}
        assert not errors


@pytest.mark.parametrize('seconds,minutes', [(45 * 60, 45), (45 * 60 + 1, 46)])
def test_existing_duration_prefills_and_frozen_competition_stays_locked(tmp_path, monkeypatch, seconds, minutes):
    with moderation_browser(tmp_path, monkeypatch) as (app, client, context, errors, _):
        assert client.post('/backup/api/admin/session/start', headers=AUTH, json={'duration_seconds': seconds}).status_code == 200
        page = context.new_page()
        page.goto('https://classroom.test/backup/teacher?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        expect(page.locator('#submission-duration')).to_have_value(str(minutes), timeout=3000)
        teacher_sign_in(page)
        app.state.store.update(session={'status': 'qualified', 'deadline': None, 'duration_seconds': seconds},
                               snapshot=app.state.store.submissions(private=True))
        page.locator('#language-switch').select_option('en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        expect(page.locator('#submission-duration')).to_be_disabled()
        expect(page.locator('#start-session')).to_be_disabled()
        before = app.state.store.get('session')
        assert client.post('/backup/api/admin/session/start', headers=AUTH, json={'duration_seconds': 10 * 60}).status_code == 409
        assert app.state.store.get('session') == before
        assert not errors
