"""Opt-in path isolation; all state and credentials are synthetic."""
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from test_api import AUTH, TOKEN, create_app
from test_tournament import fake_race, sandbox_ready, tracks_fn


@pytest.mark.parametrize('value', [
    '/', 'backup', '/backup/', '//backup', '/backup//nested', '/.', '/..',
    '/backup/../teacher', '/backup/.', '/back.up', '/backup?x=1', '/backup#x',
    '/%62ackup', '/backup%2Fteacher', '/back\\up', '/backup\n', ' /backup',
    '/bäckup', '/backup:443', '/backup/ space',
])
def test_invalid_base_path_fails_before_store(tmp_path, monkeypatch, value):
    monkeypatch.setenv('POD_BASE_PATH', value)
    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    data = tmp_path / 'never-created'
    with pytest.raises(ValueError, match='POD_BASE_PATH'):
        create_app(data)
    assert not data.exists()


def prefixed(tmp_path, monkeypatch, **settings):
    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    monkeypatch.setenv('POD_BASE_PATH', '/backup')
    monkeypatch.setenv('POD_CLASS_ACCESS_REQUIRED', '1')
    for name, value in settings.items():
        monkeypatch.setenv(name, str(value))
    return create_app(tmp_path / 'data', race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)


def test_prefix_routes_only_expose_internal_health_outside_namespace(tmp_path, monkeypatch):
    app = prefixed(tmp_path, monkeypatch)
    with TestClient(app) as client:
        for path in ('/backup/', '/backup/teacher', '/backup/projector', '/backup/assets/app.js',
                     '/backup/api/starter', '/backup/api/health', '/api/health'):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "script-src 'self'" in response.headers['content-security-policy']
            if '/api/' in path:
                assert response.headers.get('cache-control') == 'no-store'
        for path in ('/', '/teacher', '/projector', '/assets/app.js', '/api/starter', '/api/access',
                     '/api/state', '/api/admin/access/invitation', '/backup-other/api/access', '/openapi.json'):
            assert client.get(path).status_code == 404, path
        assert client.post('/api/admin/session/start', json={}, headers=AUTH).status_code == 404
        assert client.post('/api/health', json={}).status_code == 405
        assert client.get('/backup/api/state').status_code == 401
        assert client.post('/backup/api/admin/session/start', json={}).status_code == 401
        assert client.post('/backup/api/admin/session/start', json={}, headers=AUTH).status_code == 200
        assert client.get('/api/health').json() == {'sandbox': {'available': True}}
        redirect = client.get('/backup?lang=de', follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers['location'] == 'http://testserver/backup/?lang=de'


@pytest.mark.parametrize('base', ['/backup', '/campus/Backup_2-live'])
def test_html_links_and_config_stay_in_base_path(tmp_path, monkeypatch, base):
    app = prefixed(tmp_path, monkeypatch, POD_BASE_PATH=base)

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []
            self.base = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'body':
                self.base = attrs.get('data-base-path')
            self.urls.extend(attrs[key] for key in ('src', 'href') if attrs.get(key, '').startswith('/'))

    with TestClient(app) as client:
        for view in ('/', '/teacher', '/projector'):
            response = client.get(base + view)
            assert response.status_code == 200
            links = Links()
            links.feed(response.text)
            assert links.base == base
            assert set(links.urls) == {base + suffix for suffix in (
                '/assets/styles.css', '/assets/i18n.js', '/assets/app.js', '/', '/teacher', '/projector', '/api/starter')}
            for url in links.urls:
                assert client.get(url).status_code == 200


@pytest.mark.parametrize('secure', [0, 1])
def test_prefixed_cookie_is_host_only_path_scoped_and_name_isolated(tmp_path, monkeypatch, secure):
    app = prefixed(tmp_path, monkeypatch, POD_CLASS_COOKIE_SECURE=secure)
    with TestClient(app, base_url='https://testserver') as client:
        code = client.post('/backup/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        response = client.post('/backup/api/join', json={'code': code})
        assert response.status_code == 200
        cookie = response.headers['set-cookie']
        assert cookie.startswith('pod_participant_backup=')
        assert 'Path=/backup;' in cookie
        assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie
        assert ('Secure' in cookie) == bool(secure)
        assert 'Domain=' not in cookie
        token = client.cookies.get('pod_participant_backup')
        assert client.get('/backup/api/state').status_code == 200
        assert client.get('/backup/api/state', headers={'Cookie': 'pod_participant=' + token}).status_code == 401
        assert client.post('/backup/api/admin/access/revoke', json={}, headers=AUTH).status_code == 200
        assert client.get('/backup/api/state').status_code == 401
        assert client.post('/backup/api/join', json={'code': code}).status_code == 401

        monkeypatch.setenv('POD_BASE_PATH', '')
        root = create_app(tmp_path / 'data', race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
        with TestClient(root, base_url='https://testserver') as root_client:
            code = root_client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
            root_join = root_client.post('/api/join', json={'code': code})
            assert root_join.headers['set-cookie'].startswith('pod_participant=')
            assert 'Path=/;' in root_join.headers['set-cookie']
            root_token = root_client.cookies.get('pod_participant')
            assert root_client.get('/api/state').status_code == 200
            assert client.get('/backup/api/state', headers={'Cookie': 'pod_participant=' + root_token}).status_code == 401
            # Same test store deliberately makes a token valid in both apps;
            # only each application's own cookie NAME can supply it.
            assert root_client.get('/api/state', headers={'Cookie': 'pod_participant_backup=' + root_token}).status_code == 401


def test_participant_mutation_quotas_are_mount_relative(tmp_path, monkeypatch):
    app = prefixed(tmp_path, monkeypatch, POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE=1,
                   POD_PARTICIPANT_PRACTICE_PER_MINUTE=1)
    with TestClient(app, base_url='https://testserver') as client:
        client.post('/backup/api/admin/session/start', json={}, headers=AUTH)
        code = client.post('/backup/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        client.post('/backup/api/join', json={'code': code})
        saved = client.post('/backup/api/submissions', json={'alias': 'Pilot', 'code': 'print(1)'}).json()
        payload = {'alias': 'Pilot', 'code': 'print(2)', 'claim_token': saved['claim_token']}
        denied = client.post('/backup/api/submissions', json=payload)
        assert denied.status_code == 429
        assert int(denied.headers['retry-after']) > 0
        assert client.post('/backup/api/submissions', json=payload, headers=AUTH).status_code == 200
        practice = {'alias': 'Pilot', 'claim_token': saved['claim_token']}
        assert client.post('/backup/api/practice', json=practice).status_code == 200
        assert client.post('/backup/api/practice', json=practice).status_code == 429
        assert client.post('/backup/api/join', json={'code': code}).status_code == 200
        assert client.post('/backup/api/submissions', json=payload).status_code == 429
        participant = next(iter(app.state.store.get('class_access')['sessions'].values()))
        assert set(participant['budgets']) == {'/api/submissions', '/api/practice'}


@pytest.mark.parametrize('path,setting', [
    ('/api/join', 'POD_JOIN_PER_MINUTE'),
    ('/api/submissions', 'POD_SUBMISSIONS_PER_MINUTE'),
    ('/api/practice', 'POD_PRACTICE_PER_MINUTE'),
])
def test_http_request_budget_runs_inside_mount(tmp_path, monkeypatch, path, setting):
    app = prefixed(tmp_path, monkeypatch, **{setting: 1})
    with TestClient(app) as client:
        assert client.post(path, json={}).status_code == 404
        assert client.post('/backup' + path, json={}, headers={'Origin': 'https://evil.test'}).status_code == 403
        assert client.post('/backup' + path, json={}).status_code in (401, 422)
        response = client.post('/backup' + path, json={})
        assert response.status_code == 429
        assert int(response.headers['retry-after']) > 0
        assert set(app.state.request_budget.windows) == {path}
