"""Three-track championship contracts; never execute uploaded source."""
from copy import deepcopy
import json
import math
import uuid

import pytest

from arena.engine import make_tracks, run_race
from arena.store import Store
from arena.tournament import CompetitionError, Tournament, rank_final_results
from test_tournament import fake_race, join, sandbox_ready, seed


@pytest.fixture
def competition(tmp_path):
    return Tournament(Store(tmp_path), race_fn=fake_race, tracks_fn=make_tracks, sandbox_fn=sandbox_ready)


def qualify(tournament, names=('A', 'B', 'C')):
    entries = seed(tournament, names)
    tournament.start_qualification()
    join(tournament)
    return entries


def test_qualification_freezes_one_six_track_collection_and_retry_preserves_it(competition):
    entries = seed(competition, ['A', 'B'])
    collections = []

    def collection(**kwargs):
        collections.append(kwargs)
        return make_tracks(**kwargs)

    def broken(*args, **kwargs):
        raise RuntimeError('private source')

    competition.tracks_fn = collection
    competition.race_fn = broken
    assert competition.start_qualification()['total'] == 6
    competition.worker.join(5)
    store = competition.store
    assert store.get('job')['status'] == 'failed'
    assert collections == [{'seed': 2026, 'count': 6}]
    tracks, final_tracks, snapshot = store.get('tracks'), store.get('final_tracks'), store.get('snapshot')
    assert tracks == make_tracks(count=6)[:3]
    assert final_tracks == make_tracks(count=6)[3:]
    assert store.get('final_format') == 'three-track-total-time-v1'
    # Even a private edit cannot change the competition's immutable source snapshot.
    store.submit('A', 'new private source', entries[0]['claim_token'])
    competition.tracks_fn = lambda **kwargs: pytest.fail('must not regenerate frozen tracks')
    competition.race_fn = fake_race
    competition.start_qualification()
    join(competition)
    assert store.get('snapshot') == snapshot
    assert store.get('tracks') == tracks
    assert store.get('final_tracks') == final_tracks
    assert len(store.replays()) == 7  # Failed archive retained, then six fresh races.


def timed_race(times, observations=None, store=None):
    """Use orchestration's real publication path with deterministic simulated times."""
    def race(entries, track, **kwargs):
        index = int(track['id'].rsplit('-', 1)[1]) - 4
        if observations is not None:
            observations.append({key: store.get(key) for key in ('job', 'final_leaderboard', 'final_replay_ids', 'champion')})
        result = fake_race(entries, track, **kwargs)
        for row in result['results']:
            value = times[row['alias']][index]
            row.update(finish_time=value, turns=math.ceil(value) if value and math.isfinite(value) else 700,
                       finished=value is not None, disqualified=False)
        result['results'].sort(key=lambda row: (row['finish_time'] is None, row['finish_time'] or 0, row['alias'].casefold(), row['id']))
        result['winner_id'] = next((row['id'] for row in result['results'] if row['finished']), None)
        return result
    return race


def test_final_champion_is_sum_winner_not_first_or_last_race_winner(competition):
    qualify(competition)
    times = {'A': [1.25, 50.5, 50.5], 'B': [10.125, 10.25, 10.5], 'C': [50.5, 50.5, 1.125]}
    observed = []
    store = competition.store
    competition.race_fn = timed_race(times, observed, store)
    job = competition.start_final()
    assert job == {'status': 'running', 'phase': 'final', 'completed': 0, 'total': 3,
                   'message': 'Racing 3 finalists over three different tracks.'}
    join(competition)
    assert [state['job']['completed'] for state in observed] == [0, 1, 2]
    assert [len(state['final_replay_ids']) for state in observed] == [1, 2, 3]
    for completed, state in enumerate(observed):
        assert state['champion'] is None
        for row in state['final_leaderboard']:
            assert row['completed_tracks'] == completed
            assert row['total_time'] is None
            assert len(row['race_times']) == 3
        if completed:
            assert state['job']['message'] == f'Final {completed} of 3 complete.'
    board = store.get('final_leaderboard')
    assert [row['alias'] for row in board] == ['B', 'C', 'A']
    for rank, row in enumerate(board, 1):
        assert set(row) == {'id', 'alias', 'rank', 'completed_tracks', 'disqualified', 'race_times', 'total_time'}
        assert row['rank'] == rank and row['completed_tracks'] == 3 and not row['disqualified']
        assert row['race_times'] == times[row['alias']]
        assert row['total_time'] == sum(times[row['alias']])
    assert store.get('champion') == {'id': board[0]['id'], 'alias': 'B'}
    replays = [store.read_replay(key) for key in store.get('final_replay_ids')]
    assert len(replays) == 3
    assert [replay['track'] for replay in replays] == store.get('final_tracks')
    assert [replay['series_index'] for replay in replays] == [1, 2, 3]
    assert all(replay['series_total'] == 3 and replay['collisions'] is False for replay in replays)
    assert [replay['title'] for replay in replays] == [
        f"Final {index}/3 · {track['name']} · 3 pods" for index, track in enumerate(store.get('final_tracks'), 1)]
    assert [next(row['alias'] for row in replay['results'] if row['id'] == replay['winner_id']) for replay in replays] == ['A', 'B', 'C']
    assert [row['title'] for row in store.replays() if row['kind'] == 'final'] == [
        f"Final {index}/3 · {track['name']} · 3 pods" for index, track in enumerate(store.get('final_tracks'), 1)]
    assert store.get('job')['completed'] == store.get('job')['total'] == 3
    assert store.get('job')['message'] == 'Three-track final complete.'


@pytest.mark.parametrize('invalid', [None, float('nan'), float('inf'), -float('inf'), 0, -1, True, '0.5', 10 ** 1000])
def test_invalid_finish_times_cannot_win_or_break_publication(competition, invalid):
    qualify(competition, ['A', 'B'])
    normal = timed_race({'A': [0.5, 0.5, 0.5], 'B': [20.25, 20.25, 20.25]})

    def race(entries, track, **kwargs):
        result = normal(entries, track, **kwargs)
        if track == competition.store.get('final_tracks')[1]:
            next(row for row in result['results'] if row['alias'] == 'A')['finish_time'] = invalid
        return result

    competition.race_fn = race
    competition.start_final()
    join(competition)
    board = competition.store.get('final_leaderboard')
    assert [row['alias'] for row in board] == ['B', 'A']
    assert board[1]['race_times'] == [0.5, None, 0.5]
    assert board[1]['completed_tracks'] == 2 and board[1]['total_time'] is None
    assert competition.store.get('champion')['alias'] == 'B'
    json.dumps(board, allow_nan=False)


def test_sum_overflow_is_not_a_valid_championship_time():
    entries = [{'id': 'a', 'alias': 'A'}, {'id': 'b', 'alias': 'B'}]
    results = {'a': [{'finished': True, 'finish_time': 1e308}] * 3,
               'b': [{'finished': True, 'finish_time': 10.0}] * 3}
    board = rank_final_results(entries, results)
    assert [row['alias'] for row in board] == ['B', 'A']
    assert board[1]['total_time'] is None
    json.dumps(board, allow_nan=False)


@pytest.mark.parametrize('legacy_status', ['qualified', 'failed-final', 'finished'])
def test_legacy_data_is_not_migrated_until_an_explicit_new_final(competition, legacy_status):
    qualify(competition, ['A', 'B'])
    store = competition.store
    legacy_id = str(uuid.uuid4())
    store.add_replay(legacy_id, 'Historical final', 'final')
    old_replay = {'id': legacy_id, 'track': store.get('tracks')[0], 'collisions': True, 'status': 'finished',
                  'entries': [], 'results': [], 'frames': [], 'winner_id': None}
    store.write_replay(legacy_id, old_replay)
    with store.connection() as db:
        db.execute("DELETE FROM config WHERE key IN ('final_tracks','final_format','final_replay_ids','final_leaderboard')")
    session_status = 'final' if legacy_status == 'failed-final' else legacy_status
    job = {**store.initial_job(), 'phase': 'final', 'status': 'failed' if legacy_status == 'failed-final' else 'finished'}
    store.update(session={**competition.session(), 'status': session_status}, job=job,
                 active_replay_id=legacy_id, champion={'id': 'historical-champion', 'alias': 'Historical'})
    original = (store.replay_dir / f'{legacy_id}.json').read_bytes()
    with store.connection() as db:
        before = [tuple(row) for row in db.execute('SELECT * FROM config ORDER BY key')]
    restored = Store(store.directory)
    competition = Tournament(restored, race_fn=fake_race, tracks_fn=make_tracks, sandbox_fn=sandbox_ready)
    with restored.connection() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM config ORDER BY key')] == before
    assert restored.get('final_tracks') is None
    if legacy_status != 'finished':
        competition.start_final()
        join(competition)
        assert restored.get('final_tracks') == make_tracks(count=6)[3:]
        assert restored.get('final_format') == 'three-track-total-time-v1'
        assert len(restored.get('final_replay_ids')) == 3
        assert legacy_id not in restored.get('final_replay_ids')
    assert (restored.replay_dir / f'{legacy_id}.json').read_bytes() == original


@pytest.mark.parametrize('bad_tracks', ['short', 'reused-geometry', 'reused-id'])
def test_final_refuses_invalid_or_overlapping_frozen_courses_before_mutation(competition, bad_tracks):
    qualify(competition, ['A', 'B'])
    store = competition.store
    tracks = store.get('final_tracks')
    if bad_tracks == 'short':
        tracks.pop()
    elif bad_tracks == 'reused-geometry':
        tracks[0]['checkpoints'] = store.get('tracks')[0]['checkpoints']
    else:
        tracks[0]['id'] = store.get('tracks')[0]['id']
    store.update(final_tracks=tracks)
    before = {key: store.get(key) for key in ('session', 'job', 'champion', 'final_replay_ids', 'final_leaderboard')}
    with pytest.raises(CompetitionError) as error:
        competition.start_final()
    assert error.value.status == 409
    assert {key: store.get(key) for key in before} == before
    assert store.get('final_tracks') == tracks


def test_fractional_sums_win_even_when_integer_ceilings_favor_another_bot(competition):
    qualify(competition, ['A', 'B'])
    times = {'A': [9.99, 9.99, 10.99], 'B': [10.01, 10.01, 10.01]}
    assert sum(map(math.ceil, times['A'])) < sum(map(math.ceil, times['B']))
    competition.race_fn = timed_race(times)
    competition.start_final()
    join(competition)
    board = competition.store.get('final_leaderboard')
    assert [row['alias'] for row in board] == ['B', 'A']
    assert board[0]['total_time'] == sum(times['B'])
    assert competition.store.get('champion')['alias'] == 'B'


def test_final_ties_use_casefold_alias_then_uuid_not_input_or_qualification_order():
    entries = [{'id': str(uuid.UUID(int=index)), 'alias': alias}
               for index, alias in [(3, 'zed'), (2, 'ADA'), (1, 'Ada')]]
    results = {entry['id']: [{'finished': True, 'finish_time': 10.125}] * 3 for entry in entries}
    expected = [entries[2]['id'], entries[1]['id'], entries[0]['id']]
    for order in (entries, list(reversed(entries))):
        board = rank_final_results(order, results)
        assert [row['id'] for row in board] == expected
        assert [row['rank'] for row in board] == [1, 2, 3]


def test_no_champion_unless_one_bot_finishes_every_track_without_dq(competition):
    qualify(competition)
    normal = timed_race({'A': [10.5, None, 10.5], 'B': [None, 10.5, 10.5], 'C': [1.0, 1.0, 1.0]})
    calls = []

    def race(entries, track, **kwargs):
        calls.append([entry['id'] for entry in entries])
        result = normal(entries, track, **kwargs)
        if track == competition.store.get('final_tracks')[2]:
            next(row for row in result['results'] if row['alias'] == 'C').update(
                disqualified=True, error='crash: PRIVATE SOURCE SECRET')
        return result

    competition.race_fn = race
    competition.start_final()
    join(competition)
    store = competition.store
    assert len(calls) == 3 and calls[0] == calls[1] == calls[2]
    board = store.get('final_leaderboard')
    assert store.get('champion') is None
    assert all(row['completed_tracks'] == 2 and row['total_time'] is None for row in board)
    assert board[-1]['disqualified'] and board[-1]['race_times'] == [1.0, 1.0, None]
    assert 'SECRET' not in json.dumps(board)
    assert store.get('job')['message'] == 'Three-track final complete; no bot finished all three tracks, so no champion was crowned.'


@pytest.mark.parametrize('restart', [False, True])
def test_final_retry_is_fresh_series_with_frozen_sources_tracks_and_historical_archives(competition, restart):
    submitted = qualify(competition, ['A', 'B'])
    store = competition.store
    snapshot, tracks = store.get('snapshot'), store.get('final_tracks')
    normal = timed_race({'A': [10.125, 10.25, 10.5], 'B': [11.0, 11.0, 11.0]})

    def partial(entries, track, **kwargs):
        if track == tracks[1]:
            raise RuntimeError('PRIVATE TRACEBACK SOURCE SECRET')
        return normal(entries, track, **kwargs)

    competition.race_fn = partial
    competition.start_final()
    competition.worker.join(5)
    assert store.get('job')['status'] == 'failed'
    assert store.get('job')['completed'] == 1
    old_ids = store.get('final_replay_ids')
    assert len(old_ids) == 2
    assert all(row['completed_tracks'] == 1 and row['total_time'] is None for row in store.get('final_leaderboard'))
    assert 'SECRET' not in json.dumps(store.get('job'))
    if restart:
        # Reproduce a process death at the same boundary instead of a caught error.
        active = store.read_replay(old_ids[-1])
        store.write_replay(old_ids[-1], {**active, 'status': 'running'})
        store.update(job={**store.get('job'), 'status': 'running'})
        store = Store(store.directory)
        assert store.read_replay(old_ids[-1])['status'] == 'interrupted'
    historical = {key: (store.replay_dir / f'{key}.json').read_bytes() for key in old_ids}
    store.submit('A', 'changed private source', submitted[0]['claim_token'])
    store.update(champion={'id': 'obsolete', 'alias': 'Must be cleared'})
    calls, observed = [], []

    def fresh(entries, track, **kwargs):
        calls.append(deepcopy((entries, track, kwargs)))
        return timed_race({'A': [10.125, 10.25, 10.5], 'B': [11.0, 11.0, 11.0]}, observed, store)(entries, track, **kwargs)

    competition = Tournament(store, race_fn=fresh, sandbox_fn=sandbox_ready,
                             tracks_fn=lambda **kwargs: pytest.fail('frozen tracks must not regenerate'))
    competition.start_final()
    join(competition)
    assert observed[0]['final_leaderboard'] == [] and observed[0]['champion'] is None
    assert len(observed[0]['final_replay_ids']) == 1
    new_ids = store.get('final_replay_ids')
    assert len(new_ids) == 3 and set(new_ids).isdisjoint(old_ids)
    assert store.get('snapshot') == snapshot and store.get('final_tracks') == tracks
    assert [track for _, track, _ in calls] == tracks
    assert all(entries == snapshot for entries, _, _ in calls)
    assert all('collisions' not in kwargs for _, _, kwargs in calls)
    assert store.get('final_leaderboard')[0]['total_time'] == sum([10.125, 10.25, 10.5])
    assert store.get('champion')['alias'] == 'A'
    for key, payload in historical.items():
        assert (store.replay_dir / f'{key}.json').read_bytes() == payload


@pytest.mark.parametrize('mode', ['callback-frames', 'callback-pods', 'return-frames', 'return-pods'])
def test_partial_final_replay_bounds_fail_secret_safely(competition, mode):
    qualify(competition, ['A', 'B'])
    store = competition.store

    def oversized(entries, track, **kwargs):
        result = fake_race(entries, track, **kwargs)
        if track == store.get('final_tracks')[1]:
            frame = result['frames'][0]
            if mode.endswith('frames'):
                frames = [frame] * 702
            else:
                frame['pods'] *= 3
                frames = [frame]
            if mode.startswith('callback'):
                for item in frames:
                    kwargs['on_frame'](item)
            result['frames'] = frames
        return result

    competition.race_fn = oversized
    competition.start_final()
    competition.worker.join(5)
    assert store.get('job')['status'] == 'failed' and store.get('job')['completed'] == 1
    assert store.get('champion') is None
    assert all(row['total_time'] is None for row in store.get('final_leaderboard'))
    assert len(store.get('final_replay_ids')) == 2
    replay = store.read_replay(store.get('active_replay_id'))
    assert replay['status'] == 'failed'
    assert len(replay['frames']) <= 701
    assert all(len(frame['pods']) <= 5 for frame in replay['frames'])
    assert 'private source' not in json.dumps(replay)


def test_current_replay_references_are_published_under_state_lock(competition, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    qualify(competition, ['A', 'B'])
    store = competition.store
    original_update = store.update
    published = []

    def can_acquire_state_lock():
        acquired = competition.lock.acquire(blocking=False)
        if acquired:
            competition.lock.release()
        return acquired

    def update(**values):
        replay_id = values.get('active_replay_id')
        if replay_id is not None:
            assert store.read_replay(replay_id) is not None
            with ThreadPoolExecutor(max_workers=1) as observer:
                assert not observer.submit(can_acquire_state_lock).result(timeout=3)
            published.append(replay_id)
        return original_update(**values)

    monkeypatch.setattr(store, 'update', update)
    competition.start_final()
    join(competition)
    assert published == store.get('final_replay_ids')
    assert len(published) == 3


def test_final_retains_attempt_metadata_without_publishing_an_unwritable_archive(competition, monkeypatch):
    qualify(competition, ['A', 'B'])
    store = competition.store
    snapshot, tracks = store.get('snapshot'), store.get('final_tracks')
    original_write = store.write_replay

    def fail_initial(replay_id, replay):
        if replay.get('series_index') == 1:
            raise OSError('PRIVATE DISK PATH SECRET')
        original_write(replay_id, replay)

    monkeypatch.setattr(store, 'write_replay', fail_initial)
    competition.start_final()
    competition.worker.join(5)
    assert not competition.worker.is_alive()
    assert store.get('job')['status'] == 'failed'
    assert store.get('job')['completed'] == 0
    assert store.get('final_replay_ids') == []
    assert store.get('active_replay_id') is None
    attempted = [row for row in store.replays() if row['kind'] == 'final']
    assert len(attempted) == 1
    assert store.read_replay(attempted[0]['id']) is None
    assert store.get('champion') is None and store.get('final_leaderboard') == []
    assert 'SECRET' not in json.dumps(store.get('job'))

    monkeypatch.setattr(store, 'write_replay', original_write)
    competition.tracks_fn = lambda **kwargs: pytest.fail('frozen tracks must not regenerate')
    competition.start_final()
    join(competition)
    assert store.get('snapshot') == snapshot and store.get('final_tracks') == tracks
    assert len(store.get('final_replay_ids')) == 3
    assert attempted[0]['id'] not in store.get('final_replay_ids')
    assert attempted[0] in store.replays()


@pytest.mark.parametrize('series_index', [1, 2])
def test_initial_archive_error_retains_failed_body_without_publishing_attempt(competition, monkeypatch, series_index):
    qualify(competition, ['A', 'B'])
    store = competition.store
    snapshot, tracks = store.get('snapshot'), store.get('final_tracks')
    original_write = store.write_replay
    attempted = []

    def fail_once(replay_id, replay):
        if replay.get('series_index') == series_index and not attempted:
            attempted.append(replay_id)
            raise OSError('PRIVATE DISK PATH SECRET')
        original_write(replay_id, replay)

    monkeypatch.setattr(store, 'write_replay', fail_once)
    competition.start_final()
    competition.worker.join(5)
    assert not competition.worker.is_alive()
    assert store.get('job')['status'] == 'failed'
    assert store.get('job')['completed'] == series_index - 1
    assert 'SECRET' not in json.dumps(store.get('job'))
    assert len(attempted) == 1
    failed = store.read_replay(attempted[0])
    assert failed is not None and failed['status'] == 'failed'
    assert failed['frames'] == failed['results'] == [] and failed['winner_id'] is None
    ids = store.get('final_replay_ids')
    assert len(ids) == series_index - 1 and attempted[0] not in ids
    assert store.get('active_replay_id') == (ids[-1] if ids else None)
    assert store.get('champion') is None
    historical = {row['id']: store.read_replay(row['id']) for row in store.replays() if row['kind'] == 'final'}
    assert len(historical) == series_index
    assert all(body is not None for body in historical.values())

    competition.tracks_fn = lambda **kwargs: pytest.fail('frozen tracks must not regenerate')
    competition.start_final()
    join(competition)
    assert store.get('snapshot') == snapshot and store.get('final_tracks') == tracks
    assert len(store.get('final_replay_ids')) == 3
    assert set(store.get('final_replay_ids')).isdisjoint(historical)
    assert {key: store.read_replay(key) for key in historical} == historical


def test_trusted_engine_runs_five_pods_on_all_three_final_courses(competition):
    from arena.bots import ReferenceRunner

    def trusted(entries, track, **kwargs):
        return run_race(entries, track, runner_factory=lambda entry: ReferenceRunner({**entry, 'code': 'racer'}), **kwargs)

    competition.race_fn = trusted
    qualify(competition, [f'Pilot {index}' for index in range(6)])
    competition.start_final()
    join(competition)
    store = competition.store
    assert len(store.get('finalists')) == 5
    board = store.get('final_leaderboard')
    assert len(board) == 5 and all(row['completed_tracks'] == 3 for row in board)
    assert store.get('champion') == {key: board[0][key] for key in ('id', 'alias')}
    assert all(row['total_time'] == sum(row['race_times']) for row in board)
    for index, replay_id in enumerate(store.get('final_replay_ids'), 1):
        replay = store.read_replay(replay_id)
        assert replay['series_index'] == index and replay['series_total'] == 3
        assert len(replay['entries']) == len(replay['results']) == 5
        assert 20 < len(replay['frames']) <= 701 and replay['collisions'] is False
        assert all(row['finished'] and row['finish_time'] > 0 for row in replay['results'])
        json.dumps(replay, allow_nan=False)
