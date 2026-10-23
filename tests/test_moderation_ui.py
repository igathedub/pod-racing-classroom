"""Actual Chromium contracts for teacher-only, explicit moderation controls."""
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from tournament_wait import wait_tournament
from playwright.sync_api import expect, sync_playwright

from test_api import TOKEN
from test_base_path import prefixed


@contextmanager
def moderation_browser(tmp_path, monkeypatch, base='/backup'):
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base, POD_CLASS_ACCESS_REQUIRED=0)
    for alias in ('Delete Pilot', 'Keep Pilot', 'Another Pilot'):
        app.state.store.submit(alias, 'print(1)')
    with TestClient(app, base_url='https://classroom.test') as client, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, chromium_sandbox=True)
        errors, deletes = [], []
        def serve(route):
            request = route.request
            url = urlsplit(request.url)
            assert url.netloc == 'classroom.test'
            if request.method == 'DELETE':
                deletes.append(url.path)
            response = client.request(request.method, url.path + ('?' + url.query if url.query else ''),
                                      headers=request.headers, content=request.post_data_buffer)
            route.fulfill(status=response.status_code, body=response.content, headers=dict(response.headers))
        context = browser.new_context()
        context.route('**/*', serve)
        context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
        try:
            yield app, client, context, errors, deletes
        finally:
            browser.close()


def teacher_sign_in(page):
    page.locator('#admin-token').fill(TOKEN)
    page.locator('#admin-auth button[type=submit]').click()
    expect(page.locator('.delete-submission').first).to_be_enabled()


def test_teacher_delete_requires_key_and_explicit_confirmation(tmp_path, monkeypatch):
    with moderation_browser(tmp_path, monkeypatch) as (app, client, context, errors, deletes):
        page = context.new_page()
        page.goto('https://classroom.test/backup/teacher?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        expect(page.locator('.delete-submission')).to_have_count(3, timeout=3000)
        expect(page.locator('.delete-submission').first).to_be_disabled()
        teacher_sign_in(page)
        page.locator('.delete-submission').first.click()
        expect(page.locator('#delete-dialog')).to_be_visible()
        expect(page.locator('#delete-alias')).to_have_text('Delete Pilot')
        expect(page.locator('#confirm-delete')).to_have_text('Abgabe endgültig löschen')
        page.locator('#cancel-delete').click()
        expect(page.locator('#delete-dialog')).not_to_be_visible()
        assert not deletes
        assert len(app.state.store.submissions()) == 3
        page.locator('#language-switch').select_option('en')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
        expect(page.locator('.delete-submission').first).to_have_text('Delete')
        app.state.store.update(job={'status': 'running', 'phase': 'qualification', 'completed': 0, 'total': 9, 'message': ''})
        expect(page.locator('.delete-submission').first).to_be_disabled(timeout=6000)
        assert not errors


def test_student_and_projector_have_no_submission_delete_controls(tmp_path, monkeypatch):
    with moderation_browser(tmp_path, monkeypatch) as (_, client, context, errors, deletes):
        for path in ('/', '/projector'):
            page = context.new_page()
            page.goto('https://classroom.test/backup' + path)
            page.wait_for_function("() => document.body.dataset.stateLanguage === 'en'")
            assert page.locator('.delete-submission').count() == 0
            page.close()
        assert not deletes and not errors


@pytest.mark.parametrize('base', ['', '/backup'])
def test_delete_updates_teacher_and_cached_projector_without_reset(tmp_path, monkeypatch, base):
    from test_api import AUTH
    with moderation_browser(tmp_path, monkeypatch, base) as (app, client, context, errors, deletes):
        assert client.post(base + '/api/admin/qualify', json={}, headers=AUTH).status_code == 202
        wait_tournament(app)
        assert app.state.store.get('job')['status'] == 'finished'
        assert client.post(base + '/api/admin/final', json={}, headers=AUTH).status_code == 202
        wait_tournament(app)
        assert app.state.store.get('job')['status'] == 'finished'
        champion = app.state.store.get('champion')
        assert champion and len(app.state.store.replays()) == 12  # Nine qualifiers plus three finals.
        target = next(entry for entry in app.state.store.submissions() if entry['id'] == champion['id'])
        teacher = context.new_page()
        teacher.goto('https://classroom.test' + base + '/teacher?lang=de')
        teacher.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        teacher_sign_in(teacher)
        projector = context.new_page()
        projector.goto('https://classroom.test' + base + '/projector?lang=de')
        projector.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        expect(projector.locator('#scrubber')).to_be_enabled()
        expect(projector.locator('#rankings')).to_contain_text(target['alias'])
        teacher.locator('#code-inspection summary').click()
        teacher.locator('#inspect-select').select_option(target['id'])
        teacher.locator('#inspect-code').click()
        expect(teacher.locator('#inspected-code')).to_be_visible()
        teacher.get_by_role('button', name='Abgabe von ' + target['alias'] + ' löschen', exact=True).click()
        teacher.locator('#confirm-delete').click()
        expect(teacher.locator('.delete-submission')).to_have_count(2, timeout=10000)
        expect(teacher.locator('#delete-dialog')).not_to_be_visible()
        expect(teacher.locator('#inspected-code')).not_to_be_visible()
        expect(projector.locator('#rankings')).not_to_contain_text(target['alias'], timeout=8000)
        expect(projector.locator('#champion-label')).not_to_contain_text(target['alias'])
        expect(projector.locator('#race-heading')).not_to_contain_text(target['alias'])
        state = client.get(base + '/api/state').json()
        assert len(state['submissions']) == 2
        assert state['session']['status'] == 'finished'
        assert target['alias'] not in str(state)
        assert len(deletes) == 1 and deletes[0] == base + '/api/admin/submissions/' + target['id']
        assert not errors


def test_teacher_can_browse_100_submissions_on_mobile_without_page_overflow(tmp_path, monkeypatch):
    with moderation_browser(tmp_path, monkeypatch) as (app, client, context, errors, deletes):
        for index in range(97):
            app.state.store.submit(f'Load Pilot {index:03d}', 'print(1)')
        page = context.new_page()
        page.set_viewport_size({'width': 390, 'height': 844})
        page.goto('https://classroom.test/backup/teacher?lang=de')
        page.wait_for_function("() => document.body.dataset.stateLanguage === 'de'")
        expect(page.locator('#roster > li')).to_have_count(100)
        expect(page.locator('#inspect-select > option')).to_have_count(100)
        expect(page.locator('#roster-count')).to_have_text('100')
        teacher_sign_in(page)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert page.locator('#roster').evaluate('(list) => list.scrollHeight > list.clientHeight')
        assert not errors and not deletes
