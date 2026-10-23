"""Submission capacity and teacher moderation; no untrusted code execution."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import uuid

import pytest

from arena.store import Store
from arena.tournament import CompetitionError, Tournament
from test_api import AUTH, CODE, api as api, open_session, submit
from test_tournament import fake_race, join, sandbox_ready, seed, tracks_fn


def test_store_accepts_100_rejects_101_and_updates_at_capacity(tmp_path):
    store = Store(tmp_path)
    entries = [store.submit(f"Pilot {i}", "pass") for i in range(100)]
    assert len(store.submissions()) == 100
    with pytest.raises(OverflowError, match="100"):
        store.submit("Overflow", "pass")
    updated = store.submit(entries[0]["alias"], "print('updated')", entries[0]["claim_token"])
    assert updated["id"] == entries[0]["id"] and updated["version"] == 2


def test_concurrent_stores_never_exceed_100(tmp_path):
    stores = [Store(tmp_path) for _ in range(4)]
    for index in range(95):
        stores[0].submit(f"Initial {index}", "pass")

    def submit(index):
        try:
            stores[index % 4].submit(f"Concurrent {index}", "pass")
            return True
        except OverflowError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(submit, range(20))) == 5
    assert len(stores[0].submissions()) == 100


def test_rules_advertise_shared_100_capacity(api):
    client, _ = api
    assert client.get('/api/rules').json()['limits']['submissions'] == 100


def test_teacher_delete_revokes_source_claim_and_preserves_other_data(api):
    client, app = api
    open_session(client)
    target = submit(client, 'Offensive').json()
    other = submit(client, 'Other').json()
    store = app.state.store
    role_data = {'generation': 3, 'sessions': {'opaque': {'role': 'participant'}}}
    store.update(class_access=role_data)
    session = store.get('session')
    url = f"/api/admin/submissions/{target['id']}"
    response = client.delete(url, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json() == {'deleted_id': target['id'], 'removed_replays': [], 'moderation_revision': 1}
    assert CODE not in response.text and target['claim_token'] not in response.text
    assert client.get(url, headers=AUTH).status_code == 404
    assert store.get('class_access') == role_data
    assert store.get('session') == session
    assert store.admin_token == AUTH['X-Admin-Token']
    assert [entry['id'] for entry in store.submissions()] == [other['id']]
    state = client.get('/api/state').json()
    assert state['moderation_revision'] == 1
    assert 'Offensive' not in str(state)
    with pytest.raises(PermissionError):
        store.claimed_submission('Offensive', target['claim_token'])
    replacement = submit(client, 'Offensive').json()
    assert replacement['id'] != target['id']
    assert replacement['claim_token'] != target['claim_token']
    assert submit(client, 'Offensive', claim_token=target['claim_token']).status_code == 409
    assert client.delete(url, headers=AUTH).status_code == 404
    assert Store(store.directory).get('moderation_revision') == 1


@pytest.mark.parametrize('headers', [{}, {'X-Admin-Token': 'wrong'}, {'X-Admin-Token': 'student-claim'}])
def test_delete_requires_teacher_token(api, headers):
    client, app = api
    entry = app.state.store.submit('Offensive', CODE)
    if headers.get('X-Admin-Token') == 'student-claim':
        headers = {'X-Admin-Token': entry['claim_token']}
    assert client.delete(f"/api/admin/submissions/{entry['id']}", headers=headers).status_code == 401
    assert len(app.state.store.submissions()) == 1


@pytest.mark.parametrize('extra', [{'Origin': 'https://evil.example'}, {'Origin': 'null'},
                                  {'Sec-Fetch-Site': 'cross-site'}, {'Referer': 'https://evil.example/path'}])
def test_delete_obeys_existing_origin_policy(api, extra):
    client, app = api
    entry = app.state.store.submit('Offensive', CODE)
    assert client.delete(f"/api/admin/submissions/{entry['id']}", headers={**AUTH, **extra}).status_code == 403
    assert len(app.state.store.submissions()) == 1


@pytest.mark.parametrize('submission_id,status', [('not-a-uuid', 422),
                          ('00000000-0000-0000-0000-000000000000', 404)])
def test_delete_validates_identifier(api, submission_id, status):
    client, app = api
    assert client.delete(f'/api/admin/submissions/{submission_id}', headers=AUTH).status_code == status
    assert app.state.store.get('moderation_revision', 0) == 0


@pytest.mark.parametrize('practice', [False, True])
def test_delete_rejects_busy_without_mutation(api, practice):
    client, app = api
    store, tournament = app.state.store, app.state.tournament
    entry = store.submit('Offensive', CODE)
    if practice:
        tournament._practice_active = True
    else:
        store.update(job={**store.initial_job(), 'status': 'running'})
    before = store.submissions(private=True)
    try:
        response = client.delete(f"/api/admin/submissions/{entry['id']}", headers=AUTH)
        assert response.status_code == 409
        assert store.submissions(private=True) == before
        assert store.get('moderation_revision', 0) == 0
    finally:
        tournament._practice_active = False
        store.update(job=store.initial_job())


@pytest.mark.parametrize('finished', [False, True])
def test_frozen_delete_purges_snapshot_rankings_and_only_affected_replays(tmp_path, finished):
    tournament = Tournament(Store(tmp_path), race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    entries = seed(tournament, ['Offensive'] + [f'Pilot {i}' for i in range(6)])
    target = entries[0]
    tournament.start_qualification()
    join(tournament)
    if finished:
        tournament.start_final()
        join(tournament)
        assert tournament.store.get('champion')['id'] == target['id']
    store = tournament.store
    old_session, old_job = store.get('session'), store.get('job')
    before_files = {row['id']: (store.replay_dir / f"{row['id']}.json").read_bytes() for row in store.replays()}
    affected = {key for key in before_files if any(entry['id'] == target['id'] for entry in store.read_replay(key)['entries'])}
    unaffected = set(before_files) - affected
    result = tournament.delete_submission(target['id'])
    assert set(result['removed_replays']) == affected
    assert result['moderation_revision'] == 1
    assert store.get('session') == old_session and store.get('job') == old_job
    assert store.get('champion') is None
    assert [row['rank'] for row in store.get('leaderboard')] == list(range(1, 7))
    assert len(store.get('snapshot')) == 6
    assert set(row['id'] for row in store.replays()) == unaffected
    for replay_id in affected:
        assert store.read_replay(replay_id) is None
        assert not (store.replay_dir / f'{replay_id}.json').exists()
    for replay_id in unaffected:
        assert (store.replay_dir / f'{replay_id}.json').read_bytes() == before_files[replay_id]
    if finished:
        assert store.get('active_replay_id') is None
        assert store.get('final_replay_ids') == [] and store.get('final_leaderboard') == []
        assert len(store.get('finalists')) == 4  # Do not pretend another bot raced the final.
    else:
        assert len(store.get('finalists')) == 5  # Qualification promotes next eligible pilot.
        tournament.start_final()
        join(tournament)
        assert len(store.read_replay(store.get('active_replay_id'))['entries']) == 5
    for value in (store.get('snapshot'), store.get('leaderboard'), store.get('finalists'), store.get('champion'), store.replays()):
        assert target['id'] not in json.dumps(value) and target['alias'] not in json.dumps(value)
    for path in store.replay_dir.rglob('*'):
        if path.is_file():
            assert target['alias'] not in path.read_text()


def test_delete_after_case_change_cleans_earlier_alias_and_orphan_replay(tmp_path):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    store.submit('OFFENSIVE', CODE, target['claim_token'])
    orphan_id = str(uuid.uuid4())
    store.write_replay(orphan_id, {'id': orphan_id, 'entries': [{'id': target['id'], 'alias': 'Offensive'}], 'frames': [], 'results': []})
    result = Tournament(store).delete_submission(target['id'])
    assert result['removed_replays'] == [orphan_id]
    assert store.read_replay(orphan_id) is None


@pytest.mark.parametrize('invalid', ['{broken', '[]', '{"entries": "bad"}', '{"frames": [{"pods": "bad"}]}',
    '{"entries": [], "results": [], "frames": [{"pods": [{"id": 3, "alias": []}]}]}',
    '{"entries": [], "entries": [], "results": [], "frames": []}',
    '{"entries": [], "results": [], "frames": [], "invalid": NaN}',
    '{"entries": [], "results": [], "frames": [], "nested": ' + '[' * 1100 + '0' + ']' * 1100 + '}'])
def test_invalid_persisted_replay_fails_closed_before_any_changes(api, invalid):
    client, app = api
    store = app.state.store
    target = store.submit('Offensive', CODE)
    replay_id = str(uuid.uuid4())
    store.add_replay(replay_id, 'Offensive · Track', 'qualification')
    path = store.replay_dir / f'{replay_id}.json'
    path.write_text(invalid)
    before = store.submissions(private=True), store.replays(), path.read_bytes()
    response = client.delete(f"/api/admin/submissions/{target['id']}", headers=AUTH)
    assert response.status_code == 409
    assert CODE not in response.text and invalid not in response.text
    assert (store.submissions(private=True), store.replays(), path.read_bytes()) == before
    assert store.get('moderation_revision', 0) == 0


def archive(store, target):
    replay_id = str(uuid.uuid4())
    store.add_replay(replay_id, f"{target['alias']} · Track", 'qualification')
    store.write_replay(replay_id, {'id': replay_id, 'entries': [{'id': target['id'], 'alias': target['alias']}], 'frames': [], 'results': []})
    return replay_id


@pytest.mark.parametrize('committed', [False, True])
def test_restart_recovers_staged_moderation_using_committed_revision(tmp_path, committed):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    replay_id = archive(store, target)
    path = store.replay_dir / f'{replay_id}.json'
    original = path.read_bytes()
    os.replace(path, path.with_suffix('.moderating'))
    journal = store.replay_dir / '.moderation-journal'
    journal.write_text(json.dumps({'revision': 1, 'replay_ids': [replay_id]}))
    if committed:
        with store.connection() as db:
            db.execute('DELETE FROM submissions WHERE id=?', (target['id'],))
            db.execute('DELETE FROM replays WHERE id=?', (replay_id,))
            store._set(db, 'moderation_revision', 1)
    restored = Store(tmp_path)
    assert not journal.exists()
    assert not path.with_suffix('.moderating').exists()
    if committed:
        assert restored.read_replay(replay_id) is None
        assert restored.submissions() == []
    else:
        assert path.read_bytes() == original
        assert restored.submissions()[0]['id'] == target['id']


def test_cleanup_failure_keeps_committed_deletion_hidden_and_recoverable(tmp_path, monkeypatch):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    replay_id = archive(store, target)
    original_unlink = Path.unlink

    def fail_cleanup(path, *args, **kwargs):
        if path.suffix == '.moderating':
            raise OSError('simulated disk cleanup failure')
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', fail_cleanup)
        result = Tournament(store).delete_submission(target['id'])
        assert result['moderation_revision'] == 1
        assert store.submissions() == [] and store.replays() == []
        assert store.read_replay(replay_id) is None
        assert (store.replay_dir / '.moderation-journal').exists()
    Store(tmp_path)
    assert not list(store.replay_dir.glob('*.moderating'))
    assert not (store.replay_dir / '.moderation-journal').exists()


def test_moderation_revision_survives_reset_and_increases(tmp_path):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    assert Tournament(store).delete_submission(target['id'])['moderation_revision'] == 1
    store.reset()
    assert store.get('moderation_revision') == 1
    target = store.submit('Other', CODE)
    assert Tournament(store).delete_submission(target['id'])['moderation_revision'] == 2


@pytest.mark.parametrize('failure', ['rename', 'database'])
def test_delete_rolls_back_files_and_database_on_failure(tmp_path, monkeypatch, failure):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    ids = [archive(store, target) for _ in range(2)]
    before = {key: (store.replay_dir / f'{key}.json').read_bytes() for key in ids}
    original_replace, original_set = os.replace, store._set
    renamed = []

    def fail_rename(source, destination):
        if str(destination).endswith('.moderating'):
            renamed.append(source)
            if len(renamed) == 2:
                raise OSError('simulated rename failure')
        return original_replace(source, destination)

    def fail_database(db, key, value):
        if key == 'moderation_revision':
            raise sqlite3.OperationalError('simulated database failure')
        return original_set(db, key, value)

    if failure == 'rename':
        monkeypatch.setattr(os, 'replace', fail_rename)
    else:
        monkeypatch.setattr(store, '_set', fail_database)
    with pytest.raises(CompetitionError) as error:
        Tournament(store).delete_submission(target['id'])
    assert error.value.status == 409
    assert store.submissions()[0]['id'] == target['id']
    assert len(store.replays()) == 2
    assert store.get('moderation_revision', 0) == 0
    for key, payload in before.items():
        assert (store.replay_dir / f'{key}.json').read_bytes() == payload


def test_moderation_purges_interrupted_replay_temp_files(tmp_path):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    replay_id = archive(store, target)
    path = store.replay_dir / f'{replay_id}.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(path.read_bytes())
    orphan_id = str(uuid.uuid4())
    orphan = store.replay_dir / f'{orphan_id}.tmp'
    orphan.write_bytes(path.read_bytes().replace(replay_id.encode(), orphan_id.encode()))
    result = Tournament(store).delete_submission(target['id'])
    assert set(result['removed_replays']) == {replay_id, orphan_id}
    assert not temporary.exists() and not orphan.exists() and not path.exists()


def test_delete_removes_title_only_metadata_reference(tmp_path):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    replay_id = str(uuid.uuid4())
    store.add_replay(replay_id, 'Offensive', 'qualification')
    assert Tournament(store).delete_submission(target['id'])['removed_replays'] == [replay_id]
    assert store.replays() == []


def test_delete_never_overwrites_unjournaled_staged_file(tmp_path):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    replay_id = archive(store, target)
    staged = store.replay_dir / f'{replay_id}.moderating'
    staged.write_text('important existing data')
    with pytest.raises(CompetitionError) as error:
        Tournament(store).delete_submission(target['id'])
    assert error.value.status == 409
    assert staged.read_text() == 'important existing data'
    assert len(store.submissions()) == 1 and len(store.replays()) == 1


@pytest.mark.parametrize('unsafe_id', ['../outside', '../../outside', '/outside', 'not-uuid'])
def test_invalid_replay_metadata_cannot_delete_arbitrary_paths(tmp_path, unsafe_id):
    store = Store(tmp_path / 'classroom')
    target = store.submit('Offensive', CODE)
    sentinel = tmp_path / 'outside.json'
    sentinel.write_text('unrelated private file')
    with store.connection() as db:
        db.execute('INSERT INTO replays VALUES (?,?,?,?,?)', (unsafe_id, 'Offensive', 'final', 0, 'Offensive'))
    with pytest.raises(CompetitionError) as error:
        Tournament(store).delete_submission(target['id'])
    assert error.value.status == 409
    assert sentinel.read_text() == 'unrelated private file'
    assert store.submissions()[0]['id'] == target['id']


def test_symlink_archive_fails_closed_without_touching_external_file(tmp_path):
    store = Store(tmp_path / 'classroom')
    target = store.submit('Offensive', CODE)
    replay_id = archive(store, target)
    path = store.replay_dir / f'{replay_id}.json'
    external = tmp_path / 'external.json'
    external.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(CompetitionError):
        Tournament(store).delete_submission(target['id'])
    assert path.is_symlink() and external.exists()
    assert store.submissions()[0]['id'] == target['id']


@pytest.mark.parametrize('committed', [False, True])
def test_real_process_crash_preserves_recoverable_moderation(tmp_path, committed):
    store = Store(tmp_path)
    target = store.submit('Offensive', CODE)
    replay_id = archive(store, target)
    payload = (store.replay_dir / f'{replay_id}.json').read_bytes()
    # Trusted test program, not submitted source. Kill at actual persistence boundaries.
    script = '''
import os, sys
from arena.store import Store
store = Store(sys.argv[1])
committed = sys.argv[3] == 'True'
if committed:
    recover = store._recover_moderation
    def crash_after_commit():
        if store.get('moderation_revision', 0) == 1:
            os._exit(29)
        recover()
    store._recover_moderation = crash_after_commit
else:
    sync = store._sync_replay_dir
    def crash_before_commit():
        sync()
        if list(store.replay_dir.glob('*.moderating')):
            os._exit(29)
    store._sync_replay_dir = crash_before_commit
store.delete_submission(sys.argv[2])
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), target['id'], str(committed)], capture_output=True, timeout=10)
    assert result.returncode == 29, result.stderr.decode()
    restored = Store(tmp_path)
    if committed:
        assert restored.submissions() == [] and restored.replays() == []
        assert restored.read_replay(replay_id) is None
    else:
        assert restored.submissions()[0]['id'] == target['id']
        assert (restored.replay_dir / f'{replay_id}.json').read_bytes() == payload
    assert not (store.replay_dir / '.moderation-journal').exists()


def test_active_practice_blocks_moderation_until_runner_finishes(api):
    client, app = api
    open_session(client)
    target = submit(client, 'Offensive').json()
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return fake_race(*args, **kwargs)

    app.state.tournament.race_fn = blocked
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/practice', json={'alias': target['alias'], 'claim_token': target['claim_token']})
        try:
            assert entered.wait(2)
            assert client.delete(f"/api/admin/submissions/{target['id']}", headers=AUTH).status_code == 409
            assert app.state.store.submissions()[0]['id'] == target['id']
            assert app.state.store.get('moderation_revision', 0) == 0
        finally:
            release.set()
        assert future.result().status_code == 200
    assert client.delete(f"/api/admin/submissions/{target['id']}", headers=AUTH).status_code == 200


def test_participant_cookie_never_grants_moderation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from test_class_access import gated

    app = gated(tmp_path, monkeypatch)
    with TestClient(app, base_url='https://testserver') as client:
        open_session(client)
        invitation = client.post('/api/admin/access/invitation', json={}, headers=AUTH).json()
        assert client.post('/api/join', json={'code': invitation['code']}).status_code == 200
        target = submit(client, 'Offensive').json()
        before_access = app.state.store.get('class_access')
        url = f"/api/admin/submissions/{target['id']}"
        assert client.delete(url).status_code == 401
        assert client.delete(url, headers={'X-Admin-Token': target['claim_token']}).status_code == 401
        assert client.delete(url, headers={**AUTH, 'Origin': 'https://testserver'}).status_code == 200
        assert app.state.store.get('class_access') == before_access
        assert client.get('/api/state').status_code == 200