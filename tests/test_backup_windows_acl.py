"""Native ACL regression: mkdir(0700) uses Windows OWNER RIGHTS."""
import json
import os
import subprocess

import pytest
from scripts import classroom_backup as backup


@pytest.mark.skipif(os.name != 'nt', reason='native Windows ACLs only')
def test_native_private_mkdir_owner_rights_is_accepted(tmp_path):
    # Elevated tokens can default to an Administrators owner; creation must
    # establish the user owner before accepting Python's OWNER RIGHTS ACE.
    path = tmp_path / 'private-owner-rights'
    backup.private_mkdir(path)
    backup.require_private(path)
    leaf = path / 'new-file'
    leaf.write_bytes(b'fixture')
    backup.privatize(path)
    backup.require_private(leaf)


@pytest.mark.parametrize('operation', ['mkdir', 'privatize'])
def test_new_private_paths_establish_current_user_owner(tmp_path, monkeypatch, operation):
    """Elevated Windows may default the owner to BUILTIN Administrators."""
    monkeypatch.setattr(backup, 'WINDOWS', True)
    user = 'S-1-5-21-100'
    owners = {}
    queries = []

    def native_acl(command, **kwargs):
        path = kwargs['env']['CLASSROOM_PRIVATE_ACL_PATH']
        script = command[-1]
        if 'SetOwner(' in script:
            assert 'WindowsIdentity]::GetCurrent().User' in script
            assert 'Set-Acl' in script
            owners[path] = user
            return subprocess.CompletedProcess(command, 0, '', '')
        queries.append(path)
        response = {'owner': owners.get(path, backup._WIN_ADMINS),
                    'user': user, 'allow': ['S-1-3-4']}
        return subprocess.CompletedProcess(command, 0, json.dumps(response), '')

    monkeypatch.setattr(backup.subprocess, 'run', native_acl)
    root = tmp_path / 'new-private'
    if operation == 'mkdir':
        backup.private_mkdir(root)
        expected = {str(root)}
    else:
        root.mkdir()
        child = root / 'data'
        child.mkdir()
        leaf = child / 'snapshot'
        leaf.write_bytes(b'fixture')
        backup.privatize(root)
        expected = {str(root), str(child), str(leaf)}
    assert set(queries) == expected
    assert owners == dict.fromkeys(expected, user)


@pytest.mark.parametrize('failure', [OSError('SYNTHETIC-SECRET'),
                                     subprocess.TimeoutExpired('powershell', 10)])
def test_owner_update_transport_failure_is_safe_and_closed(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(backup, 'WINDOWS', True)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(backup.subprocess, 'run', fail)
    with pytest.raises(backup.BackupError, match='ownership update failed') as exc:
        backup.private_mkdir(tmp_path / 'new-private')
    assert 'SYNTHETIC-SECRET' not in str(exc.value)


@pytest.mark.parametrize('returncode,owner,allow,error', [
    (1, 'S-1-5-21-100', ['S-1-3-4'], 'ownership update failed'),
    (0, backup._WIN_ADMINS, ['S-1-3-4'], 'owner does not match'),
    (0, 'S-1-5-21-100', ['S-1-3-4', 'S-1-1-0'], 'unintended principals'),
])
def test_owner_update_failure_or_unsafe_readback_is_rejected(
        tmp_path, monkeypatch, returncode, owner, allow, error):
    monkeypatch.setattr(backup, 'WINDOWS', True)
    calls = []

    def native_acl(command, **kwargs):
        calls.append(command[-1])
        if 'SetOwner(' in command[-1]:
            assert "$ErrorActionPreference = 'Stop'" in command[-1]
            return subprocess.CompletedProcess(command, returncode, '', 'SYNTHETIC-SECRET')
        return subprocess.CompletedProcess(command, 0, json.dumps(
            {'owner': owner, 'user': 'S-1-5-21-100', 'allow': allow}), '')

    monkeypatch.setattr(backup.subprocess, 'run', native_acl)
    with pytest.raises(backup.BackupError, match=error) as exc:
        backup.private_mkdir(tmp_path / 'new-private')
    assert 'SYNTHETIC-SECRET' not in str(exc.value)
    assert len(calls) == (1 if returncode else 2)


def test_snapshot_releases_sqlite_file_for_native_cleanup(tmp_path):
    import gc
    import sqlite3
    root = tmp_path / 'snapshot'
    root.mkdir()
    path = root / 'classroom.sqlite3'
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE config(key TEXT,value TEXT); CREATE TABLE submissions(id TEXT); CREATE TABLE replays(id TEXT);")
    db.close()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        backup.snapshot_stats(root)
        # Windows refuses unlink while the reader still owns an open handle.
        path.unlink()
    finally:
        if was_enabled:
            gc.enable()


@pytest.mark.parametrize('owner,allow,accepted', [
    ('S-1-5-21-100', ['S-1-3-4', 'S-1-5-18', 'S-1-5-32-544'], True),
    ('S-1-5-21-200', ['S-1-3-4'], False),
    ('S-1-5-21-100', ['S-1-3-4', 'S-1-1-0'], False),
    ('S-1-5-21-100', ['S-1-3-4', 'S-1-5-32-545'], False),
])
def test_owner_rights_does_not_bypass_owner_or_public_ace_checks(tmp_path, monkeypatch, owner, allow, accepted):
    monkeypatch.setattr(backup, 'WINDOWS', True)
    response={'owner':owner,'user':'S-1-5-21-100','allow':allow}
    monkeypatch.setattr(backup.subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a[0],0,json.dumps(response),''))
    if accepted:
        backup.require_private(tmp_path)
    else:
        with pytest.raises(backup.BackupError):
            backup.require_private(tmp_path)
