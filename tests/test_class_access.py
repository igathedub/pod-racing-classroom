"""Isolated classroom access behavior tests."""
import time
import pytest
from fastapi.testclient import TestClient
from test_api import create_app, AUTH, TOKEN
from test_tournament import fake_race, tracks_fn, sandbox_ready


def gated(tmp_path, monkeypatch, **settings):
    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    monkeypatch.setenv('POD_CLASS_ACCESS_REQUIRED', '1')
    for key, value in settings.items():
        monkeypatch.setenv(key, str(value))
    return create_app(tmp_path / 'data', race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)


@pytest.mark.parametrize('name,value', [
    ('POD_CLASS_ACCESS_REQUIRED', 'yes'), ('POD_CLASS_COOKIE_SECURE', 'false'),
    ('POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE', '0'), ('POD_PARTICIPANT_PRACTICE_PER_MINUTE', '1.5'),
    ('POD_JOIN_PER_MINUTE', '10001')])
def test_invalid_settings_fail_before_store(tmp_path, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        create_app(tmp_path / 'never-created')
    assert not (tmp_path / 'never-created').exists()


def test_explicit_insecure_cookie_for_isolated_http(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch, POD_CLASS_COOKIE_SECURE=0)
    with TestClient(app) as client:
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        result = client.post('/api/join', json={'code': code})
        assert 'Secure' not in result.headers['set-cookie']
        assert client.get('/api/state').status_code == 200


def test_participant_quota_is_not_shared_ip(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch, POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE=2,
                POD_PARTICIPANT_PRACTICE_PER_MINUTE=1)
    with TestClient(app, base_url='https://testserver') as one, TestClient(app, base_url='https://testserver') as two:
        one.post('/api/admin/session/start', json={}, headers=AUTH)
        code = one.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        for client in (one, two):
            client.post('/api/join', json={'code': code})
        payload = {'alias': 'One', 'code': 'print(1)'}
        claim = one.post('/api/submissions', json=payload).json()
        payload['claim_token'] = claim['claim_token']
        assert one.post('/api/submissions', json=payload).status_code == 200
        denied = one.post('/api/submissions', json=payload, headers={'X-Forwarded-For': 'random'})
        assert denied.status_code == 429 and int(denied.headers['Retry-After']) > 0
        assert two.post('/api/submissions', json={'alias': 'Two', 'code': 'print(2)'}).status_code == 200
        assert one.post('/api/submissions', json=payload, headers=AUTH).status_code == 200
        practice = {'alias': 'One', 'claim_token': claim['claim_token']}
        assert one.post('/api/practice', json=practice).status_code == 200
        assert one.post('/api/practice', json=practice).status_code == 429
        assert two.post('/api/practice', json=practice).status_code == 200
        assert app.state.store.replays() == []  # practice stays private


def test_join_attempt_budget_bounded(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch, POD_JOIN_PER_MINUTE=2)
    with TestClient(app) as client:
        for _ in range(2):
            assert client.post('/api/join', json={'code': 'wrong'}).status_code == 401
        response = client.post('/api/join', json={'code': 'different'}, headers={'X-Forwarded-For': 'spoofed'})
        assert response.status_code == 429 and int(response.headers['Retry-After']) > 0
        assert not app.state.store.get('class_access')


def test_public_health_has_no_classroom_data(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post('/api/admin/demo', json={}, headers=AUTH)
        response = client.get('/api/health')
        assert response.status_code == 200
        assert response.json() == {'sandbox': {'available': True}}
        assert 'Demo' not in response.text and TOKEN not in response.text
        assert response.headers['cache-control'] == 'no-store'
        assert "script-src 'self'" in response.headers['content-security-policy']


def test_access_defaults_and_private_error_output(tmp_path, monkeypatch, capsys):
    from arena.class_access import settings
    flags, limits = settings()
    assert flags == {'POD_CLASS_ACCESS_REQUIRED': False, 'POD_CLASS_COOKIE_SECURE': True}
    assert limits == {'POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE': 30,
                      'POD_PARTICIPANT_PRACTICE_PER_MINUTE': 6, 'POD_JOIN_PER_MINUTE': 120}
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://testserver') as client:
        created = client.post('/api/admin/access/invitation', json={}, headers=AUTH)
        code = created.json()['code']
        assert 7190 < created.json()['expires_at'] - time.time() <= 7200
        rejected = client.post('/api/join', json={'code': code, 'unexpected': code})
        assert rejected.status_code == 422 and code not in rejected.text
        assert client.post('/api/join?code=' + code, json={}).status_code == 422
        for path in ('/api/access', '/api/health', '/api/state'):
            assert code not in client.get(path).text
        assert code not in capsys.readouterr().out


def test_compose_wires_access_settings():
    from pathlib import Path
    content = (Path(__file__).resolve().parents[1] / 'compose.yaml').read_text(encoding='utf-8')
    for name, default in [('POD_CLASS_ACCESS_REQUIRED', 0), ('POD_CLASS_COOKIE_SECURE', 1),
                          ('POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE', 30),
                          ('POD_PARTICIPANT_PRACTICE_PER_MINUTE', 6), ('POD_JOIN_PER_MINUTE', 120)]:
        assert f'{name}: "${{{name}:-{default}}}"' in content


def test_healthcheck_uses_public_health(monkeypatch):
    import io
    from scripts import container_entrypoint
    urls = []
    def open_health(url, timeout):
        urls.append(url)
        return io.BytesIO(b'{"sandbox":{"available":true}}')
    monkeypatch.setattr(container_entrypoint, 'urlopen', open_health)
    container_entrypoint.healthcheck()
    assert urls == ['http://127.0.0.1:8765/api/health']


def test_sessions_bounded_rejoin_and_expiry(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://testserver') as client:
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        client.post('/api/join', json={'code': code})
        token = client.cookies.get('pod_participant')
        assert client.post('/api/join', json={'code': code}).status_code == 200
        assert client.cookies.get('pod_participant') == token
        for _ in range(99):
            client.cookies.clear()
            assert client.post('/api/join', json={'code': code}).status_code == 200
        assert len(app.state.store.get('class_access')['sessions']) == 100
        assert client.post('/api/join', json={'code': code}).status_code == 200
        client.cookies.clear()
        assert client.post('/api/join', json={'code': code}).status_code == 429
        state = app.state.store.get('class_access')
        next(iter(state['sessions'].values()))['expires_at'] = time.time() - 1
        app.state.store.update(class_access=state)
        assert client.post('/api/join', json={'code': code}).status_code == 200
        assert len(app.state.store.get('class_access')['sessions']) == 100
        state = app.state.store.get('class_access')
        state['expires_at'] = time.time() - 1
        app.state.store.update(class_access=state)
        assert client.get('/api/state').status_code == 401
        assert client.post('/api/join', json={'code': code}).status_code == 401


def test_active_cookie_tamper_generation_and_session_expiry(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://testserver') as client:
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        client.post('/api/join', json={'code': code})
        token = client.cookies.get('pod_participant')
        state = app.state.store.get('class_access')
        assert token not in str(state) and code not in str(state)
        assert client.get('/api/state', headers={'Cookie': 'pod_participant=' + token + 'x'}).status_code == 401
        assert client.get('/api/state').status_code == 200
        record = next(iter(state['sessions'].values()))
        record['generation'] -= 1
        app.state.store.update(class_access=state)
        assert client.get('/api/state').status_code == 401
        record['generation'] += 1
        record['expires_at'] = time.time() - 1
        app.state.store.update(class_access=state)
        assert client.get('/api/state').status_code == 401
        assert client.post('/api/join', json={'code': code}).status_code == 200
        assert client.cookies.get('pod_participant') != token
        for path, payload in [('/api/admin/session/start', {}), ('/api/admin/session/close', {}),
                              ('/api/admin/qualify', {}), ('/api/admin/final', {}), ('/api/admin/demo', {}),
                              ('/api/admin/reset', {'confirm': 'RESET'}), ('/api/admin/access/invitation', {}),
                              ('/api/admin/access/revoke', {})]:
            assert client.post(path, json=payload).status_code == 401
        assert client.get('/api/admin/submissions/missing').status_code == 401


def test_rejoin_does_not_reset_quota(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch, POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE=1)
    with TestClient(app, base_url='https://testserver') as client:
        client.post('/api/admin/session/start', json={}, headers=AUTH)
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        client.post('/api/join', json={'code': code})
        claim = client.post('/api/submissions', json={'alias': 'Pilot', 'code': 'print(1)'}).json()
        client.post('/api/join', json={'code': code})
        payload = {'alias': 'Pilot', 'code': 'print(2)', 'claim_token': claim['claim_token']}
        assert client.post('/api/submissions', json=payload).status_code == 429
        restarted = gated(tmp_path, monkeypatch, POD_PARTICIPANT_SUBMISSIONS_PER_MINUTE=1)
        with TestClient(restarted, base_url='https://testserver') as other:
            other.cookies.update(client.cookies)
            assert other.post('/api/submissions', json=payload).status_code == 429
        state = app.state.store.get('class_access')
        next(iter(state['sessions'].values()))['budgets']['/api/submissions'][0] = time.time() - 1
        app.state.store.update(class_access=state)
        assert client.post('/api/submissions', json=payload).status_code == 200


def test_default_off_access_and_mutations_compatible(tmp_path, monkeypatch):
    monkeypatch.setenv('POD_CLASS_ACCESS_REQUIRED', '0')
    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    app = create_app(tmp_path / 'data', race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    with TestClient(app) as client:
        assert client.get('/api/access').json() == {'required': False, 'authorized': True}
        assert client.get('/api/state').status_code == 200
        assert client.get('/api/replays/missing').status_code == 404
        client.post('/api/admin/session/start', json={}, headers=AUTH)
        claim = client.post('/api/submissions', json={'alias': 'Pilot', 'code': 'print(1)'}).json()
        assert client.post('/api/practice', json={'alias': 'Pilot', 'claim_token': claim['claim_token']}).status_code == 200
        assert client.post('/api/admin/session/close', json={}).status_code == 401


def test_access_changes_preserve_finished_replays_and_frozen_state(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://testserver') as client:
        client.post('/api/admin/session/start', json={}, headers=AUTH)
        for alias in ('Pilot A', 'Pilot B'):
            assert client.post('/api/submissions', json={'alias': alias, 'code': 'print(1)'}, headers=AUTH).status_code == 200
        app.state.tournament.start_qualification()
        app.state.tournament.worker.join(10)
        assert app.state.store.get('job')['status'] == 'finished'
        def snapshot():
            with app.state.store.connection() as db:
                config = dict(db.execute("SELECT key,value FROM config WHERE key != 'class_access'"))
            return config, app.state.store.submissions(private=True), app.state.store.replays(), {
                path.name: path.read_bytes() for path in app.state.store.replay_dir.glob('*.json')}
        before = snapshot()
        code = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        client.post('/api/join', json={'code': code})
        replay_id = app.state.store.replays()[0]['id']
        assert client.get('/api/replays/' + replay_id).status_code == 200
        client.post('/api/admin/access/invitation', json={}, headers=AUTH)
        assert client.get('/api/replays/' + replay_id).status_code == 401
        assert client.get('/api/replays/' + replay_id, headers=AUTH).status_code == 200
        assert client.post('/api/admin/access/revoke', json={}, headers=AUTH).status_code == 200
        assert snapshot() == before


def test_gate_denies_classroom_reads_before_join(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.get('/api/state').status_code == 401
        assert client.get('/api/access').json() == {'required': True, 'authorized': False}
        assert client.get('/api/state', headers=AUTH).status_code == 200


def test_invitation_join_gates_mutations_and_replays(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://testserver') as client:
        client.post('/api/admin/session/start', json={}, headers=AUTH)
        assert client.post('/api/submissions', json={'alias': 'Pilot', 'code': 'print(1)'}).status_code == 401
        assert client.post('/api/practice', json={'alias': 'Pilot', 'claim_token': 'wrong'}).status_code == 401
        assert client.get('/api/replays/missing').status_code == 401
        assert not app.state.store.submissions()
        assert client.post('/api/admin/access/invitation', json={}).status_code == 401
        created = client.post('/api/admin/access/invitation', json={}, headers=AUTH)
        assert created.status_code == 200
        code = created.json()['code']
        assert len(code) >= 32
        assert code not in str(app.state.store.get('class_access'))
        assert client.post('/api/join', json={'code': 'wrong'}).status_code == 401
        joined = client.post('/api/join', json={'code': code})
        assert joined.status_code == 200
        cookie = joined.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Secure' in cookie
        assert client.get('/api/access').json() == {'required': True, 'authorized': True}
        assert client.get('/api/state').status_code == 200
        assert client.post('/api/submissions', json={'alias': 'Pilot', 'code': 'print(1)'}).status_code == 200
        assert client.post('/api/admin/session/close', json={}).status_code == 401
        assert client.get('/api/admin/access/invitation').status_code == 401
        status = client.get('/api/admin/access/invitation', headers=AUTH)
        assert status.status_code == 200 and code not in status.text


def test_rotate_revoke_restart_preserve_competition(tmp_path, monkeypatch):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://testserver') as client:
        client.post('/api/admin/session/start', json={}, headers=AUTH)
        first = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        client.post('/api/join', json={'code': first})
        saved = client.post('/api/submissions', json={'alias': 'Pilot', 'code': 'print(1)'}).json()
        cookie = client.cookies.get('pod_participant')
        second = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()['code']
        assert client.get('/api/state').status_code == 401
        assert client.post('/api/join', json={'code': first}).status_code == 401
        assert client.post('/api/join', json={'code': second}).status_code == 200
        assert client.cookies.get('pod_participant') != cookie
        restart = gated(tmp_path, monkeypatch)
        with TestClient(restart, base_url='https://testserver') as other:
            other.cookies.update(client.cookies)
            assert other.get('/api/state').status_code == 200
            assert other.post('/api/admin/access/revoke', headers=AUTH, json={}).status_code == 200
            assert client.get('/api/state').status_code == 401
            assert other.post('/api/join', json={'code': second}).status_code == 401
            state = other.get('/api/state', headers=AUTH).json()
            assert state['session']['status'] == 'open'
            assert state['submissions'][0]['id'] == saved['id']
            assert restart.state.store.claimed_submission('Pilot', saved['claim_token'])['code'] == 'print(1)'
            other.cookies.set('pod_participant', 'tampered')
            assert other.get('/api/state').status_code == 401
        with TestClient(gated(tmp_path, monkeypatch), base_url='https://testserver') as after_revoke:
            after_revoke.cookies.update(client.cookies)
            assert after_revoke.get('/api/state').status_code == 401
            assert after_revoke.post('/api/join', json={'code': second}).status_code == 401


@pytest.mark.parametrize('duration', [0, -1, 86401, True, '7200', 1.5])
def test_invitation_duration_is_strict(tmp_path, monkeypatch, duration):
    app = gated(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.post('/api/admin/access/invitation', json={'duration_seconds': duration}, headers=AUTH).status_code == 422
