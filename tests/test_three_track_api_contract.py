"""Public three-track final contracts; synthetic datasets only."""
import uuid

import pytest
from fastapi.testclient import TestClient
from tournament_wait import wait_tournament

from test_api import TOKEN, create_app
from test_tournament import fake_race, sandbox_ready, tracks_fn


@pytest.mark.parametrize('base', ['', '/backup'])
def test_public_state_exposes_final_series_without_migrating_legacy_data(tmp_path, monkeypatch, base):
    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    monkeypatch.setenv('POD_BASE_PATH', base)
    monkeypatch.setenv('POD_CLASS_ACCESS_REQUIRED', '0')
    app = create_app(tmp_path, race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    store = app.state.store
    with store.connection() as db:
        before = [tuple(row) for row in db.execute('SELECT * FROM config ORDER BY key')]
    with TestClient(app) as client:
        state = client.get(base + '/api/state').json()
        assert state['final_format'] is None
        assert state['final_tracks'] == []
        assert state['final_leaderboard'] == []
        assert state['final_replay_ids'] == []
        with store.connection() as db:
            assert [tuple(row) for row in db.execute('SELECT * FROM config ORDER BY key')] == before
        replay_ids = [str(uuid.uuid4()) for _ in range(3)]
        rows = [{'id': str(uuid.uuid4()), 'alias': 'Synthetic', 'rank': 1,
                 'completed_tracks': 3, 'disqualified': False,
                 'race_times': [10.25, 20.5, 30.75], 'total_time': 61.5}]
        tracks = tracks_fn(count=3)
        store.update(final_format='three-track-total-time-v1', final_tracks=tracks,
                     final_replay_ids=replay_ids, final_leaderboard=rows)
        state = client.get(base + '/api/state').json()
        assert state['final_format'] == 'three-track-total-time-v1'
        assert state['final_replay_ids'] == replay_ids
        assert state['final_tracks'] == tracks
        assert state['final_leaderboard'] == rows
        assert TOKEN not in client.get(base + '/api/state').text
        assert client.post(base + '/api/admin/final', json={}).status_code == 401


def test_rules_explain_final_sum_not_qualification_or_wall_clock(tmp_path, monkeypatch):
    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    monkeypatch.setenv('POD_CLASS_ACCESS_REQUIRED', '0')
    app = create_app(tmp_path, race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    with TestClient(app) as client:
        rules = client.get('/api/rules?lang=en').json()
        assert rules['qualification_tracks'] == rules['final_tracks'] == 3
        assert rules['time_unit'] == 'simulated_turns'
        assert 'Qualification times are excluded.' in rules['final_scoring']
        assert 'All three final tracks must be finished' in rules['final_scoring']
        assert 'wall-clock seconds' in rules['final_scoring']
        assert 'without collisions' in rules['final']


def test_real_series_wait_allows_progress_beyond_one_join_budget():
    from types import SimpleNamespace

    elapsed = 0.0
    job = {'status': 'running', 'completed': 0, 'total': 3}

    class Worker:
        def join(self, timeout):
            nonlocal elapsed
            elapsed += timeout
            job['completed'] = min(3, int(elapsed // 6))
            if job['completed'] == 3:
                job['status'] = 'finished'

        def is_alive(self):
            return job['status'] == 'running'

    app = SimpleNamespace(state=SimpleNamespace(
        tournament=SimpleNamespace(worker=Worker()),
        store=SimpleNamespace(get=lambda key: dict(job))))
    wait_tournament(app, monotonic=lambda: elapsed)
    assert elapsed == 18.0
    assert job['completed'] == job['total']


def test_real_series_wait_rejects_stalled_worker_with_bounded_joins():
    from types import SimpleNamespace

    elapsed = 0.0
    joins = []
    job = {'status': 'running', 'completed': 1, 'total': 18}

    class Worker:
        def join(self, timeout):
            nonlocal elapsed
            joins.append(timeout)
            elapsed += timeout

        def is_alive(self):
            return True

    app = SimpleNamespace(state=SimpleNamespace(
        tournament=SimpleNamespace(worker=Worker()),
        store=SimpleNamespace(get=lambda key: dict(job))))
    with pytest.raises(AssertionError, match='no progress'):
        wait_tournament(app, monotonic=lambda: elapsed)
    assert elapsed == 10.0
    assert joins == [1.0] * 10


@pytest.mark.parametrize('job', [
    {'status': 'failed', 'completed': 2, 'total': 3},
    {'status': 'finished', 'completed': 2, 'total': 3},
])
def test_real_series_wait_rejects_unsuccessful_terminal_job(job):
    from types import SimpleNamespace

    app = SimpleNamespace(state=SimpleNamespace(
        tournament=SimpleNamespace(worker=SimpleNamespace(is_alive=lambda: False)),
        store=SimpleNamespace(get=lambda key: dict(job))))
    with pytest.raises(AssertionError):
        wait_tournament(app, monotonic=lambda: 0.0)


@pytest.mark.parametrize('base', ['', '/backup'])
@pytest.mark.parametrize('protocol', ['legacy', 'checkpoint-only'])
def test_real_referee_final_series_through_http(tmp_path, monkeypatch, base, protocol):
    from arena.bots import ReferenceRunner
    from arena.engine import make_tracks, run_race
    from scripts.deployment_probe import verify_final_series
    from test_api import AUTH
    from time import monotonic

    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    monkeypatch.setenv('POD_BASE_PATH', base)
    monkeypatch.setenv('POD_CLASS_ACCESS_REQUIRED', '0')
    monkeypatch.setenv('POD_INPUT_PROTOCOL', protocol)

    def trusted_race(entries, track, **kwargs):
        # Never execute synthetic submission source on the host; only predefined policy.
        return run_race(entries, track, input_protocol=protocol,
                        runner_factory=lambda entry: ReferenceRunner({**entry, 'code': 'racer'}), **kwargs)

    app = create_app(tmp_path, race_fn=trusted_race, tracks_fn=make_tracks, sandbox_fn=sandbox_ready)
    with TestClient(app) as client:
        assert client.post(base + '/api/admin/session/start', headers=AUTH,
                           json={'duration_seconds': 7200}).status_code == 200
        for index in range(6):
            assert client.post(base + '/api/submissions', json={
                'alias': 'Synthetic ' + str(index), 'code': 'print("never executed on host")'}).status_code == 200
        original_sources = app.state.store.submissions(private=True)
        assert client.post(base + '/api/admin/qualify', headers=AUTH, json={}).status_code == 202
        wait_tournament(app, monotonic=monotonic)
        qualified = client.get(base + '/api/state').json()
        assert qualified['job']['completed'] == qualified['job']['total'] == 18
        assert len(qualified['final_tracks']) == 3
        assert client.post(base + '/api/admin/final', headers=AUTH, json={}).status_code == 202
        wait_tournament(app, monotonic=monotonic)
        state = client.get(base + '/api/state').json()
        assert state['job']['completed'] == state['job']['total'] == 3
        assert len(state['replays']) == 21
        result = verify_final_series(state, lambda replay_id: client.get(
            base + '/api/replays/' + replay_id).json())
        assert result['aggregate_verified'] and result['champion_id']
        assert app.state.store.submissions(private=True) == original_sources
        text = client.get(base + '/api/state').text
        assert TOKEN not in text and 'never executed on host' not in text


@pytest.mark.parametrize('series_index', [1, 2, 3])
def test_final_replay_references_are_published_only_after_initial_archive(tmp_path, monkeypatch, series_index):
    import threading
    from test_api import AUTH, wait

    monkeypatch.setenv('POD_ADMIN_TOKEN', TOKEN)
    monkeypatch.setenv('POD_CLASS_ACCESS_REQUIRED', '0')
    app = create_app(tmp_path, race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    with TestClient(app) as client:
        assert client.post('/api/admin/session/start', headers=AUTH, json={}).status_code == 200
        for alias in ('A', 'B'):
            assert client.post('/api/submissions', json={'alias': alias, 'code': 'print(1)'}).status_code == 200
        assert client.post('/api/admin/qualify', headers=AUTH, json={}).status_code == 202
        wait(app)
        store = app.state.store
        entered, release = threading.Event(), threading.Event()
        original_write = store.write_replay

        def blocked_initial_write(replay_id, replay):
            if replay.get('series_index') == series_index and not replay['frames']:
                entered.set()
                assert release.wait(10)
            original_write(replay_id, replay)

        monkeypatch.setattr(store, 'write_replay', blocked_initial_write)
        assert client.post('/api/admin/final', headers=AUTH, json={}).status_code == 202
        try:
            assert entered.wait(3)
            active = store.get('active_replay_id')
            assert active is None or store.read_replay(active) is not None
            assert all(store.read_replay(replay_id) is not None
                       for replay_id in store.get('final_replay_ids', []))
            response = client.get('/api/state')
            assert response.status_code == 200
            state = response.json()
            assert len(state['final_replay_ids']) == series_index - 1
            assert state['active_replay_id'] == (state['final_replay_ids'][-1] if series_index > 1 else None)
            for replay_id in state['final_replay_ids']:
                archive = client.get('/api/replays/' + replay_id)
                assert archive.status_code == 200
                assert archive.json()['status'] == 'finished'
        finally:
            release.set()
            wait(app)
        state = client.get('/api/state').json()
        assert len(state['final_replay_ids']) == 3
        assert all(client.get('/api/replays/' + replay_id).status_code == 200
                   for replay_id in state['final_replay_ids'])
