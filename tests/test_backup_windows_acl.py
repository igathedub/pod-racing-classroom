"""Native ACL regression: mkdir(0700) uses Windows OWNER RIGHTS."""
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest
from scripts import classroom_backup as backup


@pytest.mark.skipif(os.name != 'nt', reason='native NTFS junctions only')
@pytest.mark.parametrize('location', ['root', 'descendant'])
def test_native_junction_rejected_before_any_owner_update(tmp_path, monkeypatch, location):
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'untouched'
    sentinel.write_bytes(b'fixture')
    root = tmp_path / 'tree'
    if location == 'root':
        junction = root
    else:
        root.mkdir()
        (root / 'ordinary').write_bytes(b'fixture')
        junction = root / 'junction'
    env = dict(os.environ, CLASSROOM_JUNCTION=str(junction),
               CLASSROOM_JUNCTION_TARGET=str(outside))
    result = subprocess.run([
        'powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction "
        "-Path $env:CLASSROOM_JUNCTION -Target $env:CLASSROOM_JUNCTION_TARGET | Out-Null",
    ], capture_output=True, timeout=10, env=env)
    assert result.returncode == 0, 'Native junction fixture creation failed'
    calls, reads, queries, hashes = [], [], [], []
    original_open = Path.open
    original_sha256 = backup.hashlib.sha256

    def open_file(path, *args, **kwargs):
        reads.append(path)
        return original_open(path, *args, **kwargs)

    def sha256(*args, **kwargs):
        hashes.append(True)
        return original_sha256(*args, **kwargs)

    monkeypatch.setattr(backup, 'WINDOWS', True)
    monkeypatch.setattr(backup, '_windows_set_current_owner', calls.append)
    monkeypatch.setattr(backup, 'require_private', queries.append)
    monkeypatch.setattr(Path, 'open', open_file)
    monkeypatch.setattr(backup.hashlib, 'sha256', sha256)
    try:
        info = junction.lstat()
        assert stat.S_ISDIR(info.st_mode)
        assert info.st_file_attributes & 0x400
        assert info.st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
        with pytest.raises(backup.BackupError, match='link|reparse'):
            backup.privatize(root)
        assert calls == []
        assert reads == []
        assert hashes == []
        assert queries == []
        assert sentinel.read_bytes() == b'fixture'
    finally:
        junction.rmdir()  # Remove only the junction, never its target.


@pytest.mark.parametrize('operation', ['privatize', 'embedded_inventory'])
@pytest.mark.parametrize('location', ['root', 'descendant'])
@pytest.mark.parametrize('mode,attributes,tag', [
    (stat.S_IFDIR, 0x400, 0xA0000003),  # IO_REPARSE_TAG_MOUNT_POINT
    (stat.S_IFDIR, 0x400, 0xA000000C),  # IO_REPARSE_TAG_SYMLINK
    (stat.S_IFREG, 0x400, 0x80000042),  # Unsupported file reparse point
    (stat.S_IFLNK, 0, 0),  # POSIX symlink metadata, including mocked Windows
])
def test_reparse_metadata_rejected_before_access_or_owner_update(
        tmp_path, monkeypatch, location, mode, attributes, tag, operation):
    import inspect
    root = tmp_path / 'tree'
    root.mkdir()
    unsafe = root if location == 'root' else root / 'reparse'
    if unsafe != root:
        unsafe.mkdir() if stat.S_ISDIR(mode) else unsafe.write_bytes(b'fixture')
        (root / 'aaa-ordinary').write_bytes(b'fixture')
    original_lstat = Path.lstat
    original_iterdir = Path.iterdir
    original_open = Path.open
    original_sha256 = backup.hashlib.sha256
    accesses, owners, hashes, queries = [], [], [], []

    def sha256(*args, **kwargs):
        hashes.append(True)
        return original_sha256(*args, **kwargs)

    def lstat(path, *args, **kwargs):
        if path == unsafe:
            return SimpleNamespace(st_mode=mode, st_file_attributes=attributes,
                                   st_reparse_tag=tag, st_nlink=1, st_size=7)
        return original_lstat(path, *args, **kwargs)

    def iterdir(path):
        if path == unsafe:
            accesses.append(path)
            return iter(())
        return original_iterdir(path)

    def open_file(path, *args, **kwargs):
        if path == root or root in path.parents:
            accesses.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'lstat', lstat)
    monkeypatch.setattr(Path, 'iterdir', iterdir)
    monkeypatch.setattr(Path, 'open', open_file)
    monkeypatch.setattr(backup.hashlib, 'sha256', sha256)
    monkeypatch.setattr(backup, 'WINDOWS', True)
    monkeypatch.setattr(backup, '_windows_set_current_owner', owners.append)
    monkeypatch.setattr(backup, 'require_private', queries.append)
    if operation == 'embedded_inventory':
        namespace = {'stat': stat, 'hashlib': backup.hashlib, 'BackupError': backup.BackupError}
        exec(inspect.getsource(backup.inventory), namespace)
        validate = namespace['inventory']
    else:
        validate = backup.privatize
    with pytest.raises(backup.BackupError, match='link|reparse'):
        validate(root)
    assert owners == []
    assert accesses == []
    assert hashes == []
    assert queries == []


@pytest.mark.parametrize('kind', ['file', 'missing'])
def test_inventory_requires_existing_directory_root(tmp_path, kind):
    root = tmp_path / 'root'
    if kind == 'file':
        root.write_bytes(b'fixture')
        expected = backup.BackupError
    else:
        expected = FileNotFoundError
    with pytest.raises(expected):
        backup.inventory(root)


def test_existing_private_mkdir_rejected_before_owner_update(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(backup, 'WINDOWS', True)
    monkeypatch.setattr(backup, '_windows_set_current_owner', calls.append)
    with pytest.raises(FileExistsError):
        backup.private_mkdir(tmp_path)
    assert calls == []


def test_embedded_inventory_has_no_new_helper_dependencies(tmp_path):
    import hashlib
    import inspect
    root = tmp_path / 'tree'
    root.mkdir()
    (root / 'empty').mkdir()
    (root / 'file').write_bytes(b'fixture')
    namespace = {'stat': stat, 'hashlib': hashlib, 'BackupError': backup.BackupError}
    exec(inspect.getsource(backup.inventory), namespace)
    assert namespace['inventory'](root) == {
        'empty': {'directory': True},
        'file': {'size': 7, 'sha256': hashlib.sha256(b'fixture').hexdigest()},
    }


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
