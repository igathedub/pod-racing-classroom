"""Regression boundaries found during parent integration review."""
from unittest.mock import patch
import sqlite3

import pytest
from fastapi import HTTPException

from arena.class_access import ClassAccess
from arena.locale_api import translate
from arena.store import Store
from arena.tournament import Tournament
from test_tournament import fake_race, join, sandbox_ready, seed, tracks_fn


def test_gated_class_accepts_100_distinct_students_and_rejects_101(tmp_path):
    access = ClassAccess(Store(tmp_path))
    code = access.rotate(7200)['code']
    tokens = [access.join(code, None)[0] for _ in range(100)]
    assert len(set(tokens)) == 100
    assert access.join(code, tokens[0])[0] == tokens[0]
    with pytest.raises(HTTPException) as error:
        access.join(code, None)
    assert error.value.status_code == 429
    assert all(access.valid(token) for token in tokens)


@pytest.mark.parametrize('alias', ['finished', 'Final', 'checkpoint-only', 'Reference ghost'])
def test_alias_equal_to_protocol_metadata_never_removes_unrelated_archives(tmp_path, alias):
    tournament = Tournament(Store(tmp_path), race_fn=fake_race, tracks_fn=tracks_fn,
                            sandbox_fn=sandbox_ready, input_protocol='checkpoint-only')
    entries = seed(tournament, [alias, 'A1', 'A2', 'A3', 'A4', 'A5', 'A6'])
    target = entries[0]
    tournament.start_qualification()
    join(tournament)
    tournament.start_final()
    join(tournament)
    before = {row['id']: (tournament.store.replay_dir / (row['id'] + '.json')).read_bytes()
              for row in tournament.store.replays()}
    expected = {key for key in before if any(entry['id'] == target['id']
                for entry in tournament.store.read_replay(key)['entries'])}
    result = tournament.delete_submission(target['id'])
    assert set(result['removed_replays']) == expected
    for key in set(before) - expected:
        assert (tournament.store.replay_dir / (key + '.json')).read_bytes() == before[key]


def test_windows_does_not_attempt_unsupported_posix_directory_fsync(tmp_path):
    store = Store(tmp_path)
    with patch('arena.store.os', wraps=__import__('os')) as system:
        system.name = 'nt'
        system.open.side_effect = AssertionError('Windows cannot use POSIX directory fsync')
        store._sync_replay_dir()
        system.open.assert_not_called()


@pytest.mark.parametrize('message', [
    'The classroom already has 100 submissions.',
    'Invalid submission ID.',
    'Submission could not be deleted safely. Check stored competition data and retry.',
])
def test_new_moderation_errors_have_german_copy(message):
    assert translate(message, 'de') != message


def test_commit_failure_after_archive_staging_restores_complete_state(tmp_path, monkeypatch):
    from test_submission_moderation import archive
    from arena.tournament import CompetitionError
    store = Store(tmp_path)
    target = store.submit('Remove Pilot', 'pass')
    other = store.submit('Keep Pilot', 'pass')
    ids = [archive(store, target), archive(store, other)]
    before = {key: (store.replay_dir / (key + '.json')).read_bytes() for key in ids}
    submissions = store.submissions(private=True)
    connect = sqlite3.connect
    injected = []

    class CommitFailure(sqlite3.Connection):
        def __exit__(self, error_type, error, traceback):
            if error_type is None and self.in_transaction and not injected and list(store.replay_dir.glob('*.moderating')):
                injected.append(True)
                self.rollback()
                raise sqlite3.OperationalError('injected commit failure after staging')
            return super().__exit__(error_type, error, traceback)

    def failing_connection(*args, **kwargs):
        return connect(*args, factory=CommitFailure, **kwargs)

    with monkeypatch.context() as change:
        change.setattr(sqlite3, 'connect', failing_connection)
        with pytest.raises(CompetitionError) as error:
            Tournament(store).delete_submission(target['id'])
        assert error.value.status == 409
    assert injected == [True]
    assert store.submissions(private=True) == submissions
    assert {row['id'] for row in store.replays()} == set(ids)
    assert store.get('moderation_revision', 0) == 0
    for key in ids:
        assert (store.replay_dir / (key + '.json')).read_bytes() == before[key]
    assert not list(store.replay_dir.glob('*.moderating'))
    assert not (store.replay_dir / '.moderation-journal').exists()
