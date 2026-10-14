"""Exercise the installed CLI process, not just imported helpers."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from tests.test_classroom_backup import make_backup, module

ROOT = Path(__file__).resolve().parents[1]


def invoke(*args):
    return subprocess.run([sys.executable, str(ROOT / 'scripts/classroom_backup.py'), *map(str, args)], capture_output=True, text=True, timeout=20)


def test_help_executes_real_entry_point():
    result = invoke('--help')
    assert result.returncode == 0
    assert 'backup' in result.stdout and 'restore' in result.stdout


def test_check_process_reports_verified_counts(tmp_path, monkeypatch):
    _, _, _, backup = make_backup(tmp_path, monkeypatch)
    result = invoke('check', '--backup', backup)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['counts']['submissions'] == 1
    assert 'SECRET' not in result.stdout


def test_check_process_corruption_returns_failure_without_private_data(tmp_path, monkeypatch):
    _, _, _, backup = make_backup(tmp_path, monkeypatch)
    (backup / 'data' / 'changed').write_text('SYNTHETIC-PRIVATE-DATA')
    result = invoke('check', '--backup', backup)
    assert result.returncode != 0
    assert 'error' in json.loads(result.stderr)
    assert 'SYNTHETIC-PRIVATE-DATA' not in result.stderr


def test_missing_arguments_do_not_succeed_silently():
    result = invoke('backup')
    assert result.returncode != 0
    assert 'required' in result.stderr


def test_windows_acl_queries_use_sids_not_account_names(tmp_path, monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, 'WINDOWS', True)
    def acl_run(args, **kwargs):
        script = args[-1]
        assert 'GetOwner' in script and 'Translate' in script
        assert kwargs['env']['CLASSROOM_PRIVATE_ACL_PATH'] == str(tmp_path)
        return subprocess.CompletedProcess(args, 0, json.dumps({'owner':'S-1-5-21-100','user':'S-1-5-21-100','allow':['S-1-5-21-100','S-1-5-18','S-1-5-32-544']}), '')
    monkeypatch.setattr(mod.subprocess, 'run', acl_run)
    mod.require_private(tmp_path)


def test_windows_acl_rejects_public_principals(tmp_path, monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, 'WINDOWS', True)
    monkeypatch.setattr(mod.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, json.dumps({'owner':'S-1-5-21-100','user':'S-1-5-21-100','allow':['S-1-1-0']}), ''))
    with pytest.raises(mod.BackupError, match='ACL'):
        mod.require_private(tmp_path)
