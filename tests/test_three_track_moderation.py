"""Moderation invalidates a current final aggregate without inventing a champion."""
import json

import pytest

from arena.engine import make_tracks
from arena.store import Store
from arena.tournament import CompetitionError, Tournament
from test_tournament import fake_race, join, sandbox_ready, seed


@pytest.fixture
def finished(tmp_path):
    tournament = Tournament(Store(tmp_path), race_fn=fake_race, tracks_fn=make_tracks, sandbox_fn=sandbox_ready)
    seed(tournament, [f'Pilot {index}' for index in range(7)])
    tournament.start_qualification()
    join(tournament)
    tournament.start_final()
    join(tournament)
    return tournament


def test_deleting_nonchampion_finalist_invalidates_whole_current_series(finished):
    store = finished.store
    target = store.get('final_leaderboard')[-1]
    assert target['id'] != store.get('champion')['id']
    current_ids = set(store.get('final_replay_ids'))
    before = {row['id']: (store.replay_dir / f"{row['id']}.json").read_bytes() for row in store.replays()}
    job, session, tracks = store.get('job'), store.get('session'), store.get('final_tracks')
    result = finished.delete_submission(target['id'])
    assert current_ids <= set(result['removed_replays'])
    assert len(result['removed_replays']) == 6  # Three qualifiers and all three finals.
    assert store.get('champion') is None  # Even though the previous winner remains submitted.
    assert store.get('final_leaderboard') == []
    assert store.get('final_replay_ids') == []
    assert store.get('active_replay_id') is None
    assert store.get('final_tracks') == tracks and store.get('final_format') == 'three-track-total-time-v1'
    assert store.get('job') == job and store.get('session') == session
    for key, payload in before.items():
        if key not in result['removed_replays']:
            assert (store.replay_dir / f'{key}.json').read_bytes() == payload
    restored = Store(store.directory)
    assert restored.get('final_leaderboard') == [] and restored.get('champion') is None
    assert target['id'] not in json.dumps({key: restored.get(key) for key in ('snapshot', 'leaderboard', 'finalists', 'final_leaderboard')})


def test_removing_only_one_current_replay_invalidates_sum_but_preserves_other_archives(finished):
    store = finished.store
    target = store.submit('Historical-only pilot', 'private source')
    ids = store.get('final_replay_ids')
    first = store.read_replay(ids[0])
    first['entries'].append({'id': target['id'], 'alias': target['alias']})
    store.write_replay(ids[0], first)
    retained = {key: (store.replay_dir / f'{key}.json').read_bytes() for key in ids[1:]}
    result = finished.delete_submission(target['id'])
    assert result['removed_replays'] == [ids[0]]
    assert store.get('champion') is None and store.get('final_leaderboard') == []
    assert store.get('final_replay_ids') == []
    for key, payload in retained.items():
        assert (store.replay_dir / f'{key}.json').read_bytes() == payload


def test_reset_discards_all_new_configuration_keys(finished):
    finished.reset()
    for key in ('final_tracks', 'final_format', 'final_replay_ids', 'final_leaderboard'):
        assert finished.store.get(key) is None


def test_deleting_nonfinalist_preserves_unaffected_current_series(finished):
    store = finished.store
    target = store.get('leaderboard')[-1]
    keys = ('final_replay_ids', 'final_leaderboard', 'champion', 'active_replay_id')
    before = {key: store.get(key) for key in keys}
    payloads = {key: (store.replay_dir / f'{key}.json').read_bytes() for key in before['final_replay_ids']}
    result = finished.delete_submission(target['id'])
    assert len(result['removed_replays']) == 3
    assert {key: store.get(key) for key in keys} == before
    for key, payload in payloads.items():
        assert (store.replay_dir / f'{key}.json').read_bytes() == payload


@pytest.mark.parametrize('key,value', [
    ('final_leaderboard', {}), ('final_leaderboard', [None]),
    ('final_leaderboard', [{'id': 'bad'}]), ('final_replay_ids', {}),
    ('final_replay_ids', ['not-a-uuid']), ('final_replay_ids', [None]),
])
def test_malformed_new_derived_references_fail_closed(finished, key, value):
    store = finished.store
    target = store.submissions()[0]
    store.update(**{key: value})
    before = store.submissions(private=True), store.replays(), store.get('moderation_revision', 0)
    payloads = {path: path.read_bytes() for path in store.replay_dir.glob('*.json')}
    with pytest.raises(CompetitionError) as error:
        finished.delete_submission(target['id'])
    assert error.value.status == 409
    assert (store.submissions(private=True), store.replays(), store.get('moderation_revision', 0)) == before
    assert store.get(key) == value
    assert all(path.read_bytes() == payload for path, payload in payloads.items())
