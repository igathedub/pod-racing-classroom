"""Uniform new-race rules without rewriting existing replay history."""
from copy import deepcopy
import uuid

from arena.store import Store
from arena.tournament import Tournament
from test_tournament import fake_race, join, sandbox_ready, seed, tracks_fn


def test_practice_qualifiers_final_and_live_archives_are_collision_free(tmp_path, monkeypatch):
    monkeypatch.setenv('POD_ADMIN_TOKEN', 'synthetic-teacher')
    store = Store(tmp_path)
    writes = []
    original_write = store.write_replay

    def record_write(replay_id, replay):
        writes.append(deepcopy(replay))
        original_write(replay_id, replay)

    monkeypatch.setattr(store, 'write_replay', record_write)
    # A genuinely old collision-enabled final remains historical, not relabelled.
    old_id = str(uuid.uuid4())
    store.add_replay(old_id, 'Historical final', 'final')
    original_write(old_id, {'id': old_id, 'collisions': True, 'status': 'finished', 'frames': []})
    old_path = store.directory / 'replays' / (old_id + '.json')
    old_bytes = old_path.read_bytes()
    calls = []

    def race(entries, track, **kwargs):
        calls.append(dict(kwargs))
        # Deliberately support the old option to isolate orchestration metadata.
        return fake_race(entries, track, **{**kwargs, 'collisions': False})

    tournament = Tournament(store, race_fn=race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    submitted = seed(tournament, ['A', 'B'])
    practice = tournament.practice('A', submitted[0]['claim_token'])
    assert practice['collisions'] is False
    tournament.start_qualification()
    join(tournament)
    tournament.start_final()
    join(tournament)
    assert len(calls) == 10  # Private practice, six qualifiers, three finals.
    assert len(store.get('final_replay_ids')) == 3
    assert all(replay['collisions'] is False for replay in writes)
    assert all('collisions' not in kwargs for kwargs in calls)
    assert store.get('champion') is not None
    assert old_path.read_bytes() == old_bytes
    assert store.read_replay(old_id)['collisions'] is True
    assert all(store.read_replay(row['id'])['collisions'] is False
               for row in store.replays() if row['id'] != old_id)
