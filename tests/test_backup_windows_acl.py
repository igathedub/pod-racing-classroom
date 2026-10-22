"""Native ACL regression: mkdir(0700) uses Windows OWNER RIGHTS."""
import json
import os
import subprocess

import pytest
from scripts import classroom_backup as backup


@pytest.mark.skipif(os.name != 'nt', reason='native Windows ACLs only')
def test_native_private_mkdir_owner_rights_is_accepted(tmp_path):
    # mkdir(mode=0700) builds an owner-rights ACL, not an ordinary user ACE.
    path = tmp_path / 'private-owner-rights'
    path.mkdir(mode=0o700)
    backup.require_private(path)


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
