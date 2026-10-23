"""CI diagnostics must not disclose descriptors, paths, identities or errors."""
import json
import subprocess
import sys
import traceback
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('stage', ['create', 'mkdir', 'startup', 'timeout', 'cleanup', 'cleanup_success', 'nonzero'])
def test_probe_lifecycle_failures_are_redacted(stage, monkeypatch, tmp_path, capsys):
    from scripts import ci_windows_acl_probe as probe

    canary = 'PRIVATE_PATH_OUTPUT_EXCEPTION_CANARY'
    base = tmp_path / canary
    base.mkdir()
    monkeypatch.setattr(probe, 'os', SimpleNamespace(name='nt', environ={'TMPDIR': str(base)}))
    real_temporary_directory = probe.tempfile.TemporaryDirectory

    class Fixture:
        def __init__(self, **kwargs):
            if stage == 'create':
                raise OSError(canary)
            self.temporary = real_temporary_directory(**kwargs)

        def __enter__(self):
            return self.temporary.__enter__()

        def __exit__(self, *args):
            self.temporary.__exit__(*args)
            if stage in {'cleanup', 'cleanup_success'}:
                raise OSError(canary)

    monkeypatch.setattr(probe.tempfile, 'TemporaryDirectory', Fixture)
    if stage == 'mkdir':
        def fail_mkdir(*args, **kwargs):
            raise OSError(canary)
        monkeypatch.setattr(probe.Path, 'mkdir', fail_mkdir)

    def run(*args, **kwargs):
        if stage == 'startup':
            raise OSError(canary)
        if stage == 'timeout':
            raise subprocess.TimeoutExpired(canary, 60, output=canary, stderr=canary)
        if stage == 'cleanup_success':
            rows = [{'method': method, 'result': 'ok'} for method in sorted(EXPECTED_METHODS)]
            return SimpleNamespace(returncode=0, stdout=json.dumps(rows), stderr=canary)
        return SimpleNamespace(returncode=1, stdout=canary, stderr=canary)

    monkeypatch.setattr(probe.subprocess, 'run', run)
    try:
        probe.main()
    except BaseException as error:
        # Model the CLI: SystemExit prints its message, other exceptions print a traceback.
        if isinstance(error, SystemExit):
            print(str(error), file=sys.stderr)
        else:
            traceback.print_exception(error)
        captured = capsys.readouterr()
        assert canary not in captured.out + captured.err
        assert isinstance(error, SystemExit)
        assert captured.err == 'Isolated ACL diagnostic failed; raw diagnostics suppressed\n'
        assert error.__suppress_context__
        assert error.__cause__ is None
        assert captured.out == ''
    else:
        pytest.fail('Diagnostic unexpectedly succeeded')


def test_probe_report_filters_private_details():
    from scripts.ci_windows_acl_probe import public_report
    report = public_report({'method': 'set_acl', 'result': 'failed', 'hresult': -1,
                            'owner_matches': False, 'dacl_unchanged': True,
                            'sid': 'PRIVATE_IDENTITY', 'path': 'PRIVATE_PATH',
                            'stderr': 'PRIVATE_DIAGNOSTIC'})
    assert report == {'method': 'set_acl', 'result': 'failed', 'hresult': -1,
                      'owner_matches': False, 'dacl_unchanged': True}


@pytest.mark.parametrize('bad', ['PRIVATE_DIAGNOSTIC', {'unsafe': True}, [1, 2]])
def test_probe_report_rejects_non_numeric_error(bad):
    from scripts.ci_windows_acl_probe import public_report
    with pytest.raises(ValueError):
        public_report({'method': 'set_acl', 'result': 'failed', 'hresult': bad})


EXPECTED_METHODS = {'set_acl', 'owner_only_dotnet', 'owner_only_win32', 'owner_and_dacl_win32'}


def test_probe_supports_all_four_methods():
    from scripts.ci_windows_acl_probe import METHODS, public_report
    assert METHODS == EXPECTED_METHODS
    for method in EXPECTED_METHODS:
        assert public_report({'method': method, 'result': 'ok', 'owner_rights_preserved': True}) == {
            'method': method, 'result': 'ok', 'owner_rights_preserved': True,
        }


@pytest.mark.parametrize('field', ['owner_matches', 'before_owner_matches', 'dacl_unchanged',
                                   'owner_rights_preserved', 'hresult', 'native_error_code'])
@pytest.mark.parametrize('bad', [None, 'PRIVATE_CANARY', 1.5])
def test_probe_report_rejects_invalid_field_types(field, bad):
    from scripts.ci_windows_acl_probe import public_report
    with pytest.raises(ValueError):
        public_report({'method': 'set_acl', 'result': 'failed', field: bad})


@pytest.mark.parametrize('field,bad', [('owner_matches', 1), ('dacl_unchanged', 0),
                                      ('hresult', True), ('native_error_code', False)])
def test_probe_report_does_not_confuse_bool_with_int(field, bad):
    from scripts.ci_windows_acl_probe import public_report
    with pytest.raises(ValueError):
        public_report({'method': 'set_acl', 'result': 'failed', field: bad})


@pytest.mark.parametrize('field', ['method', 'result'])
def test_probe_report_rejects_invalid_method_or_result(field):
    from scripts.ci_windows_acl_probe import public_report
    row = {'method': 'set_acl', 'result': 'ok', field: 'PRIVATE_CANARY'}
    with pytest.raises(ValueError):
        public_report(row)


@pytest.mark.parametrize('payload', [
    'PRIVATE_CANARY', 'null', '["PRIVATE_CANARY"]', '{"PRIVATE_CANARY": true}',
    '[]',
    json.dumps([{'method': 'set_acl', 'result': 'ok'}]),
    json.dumps([{'method': 'set_acl', 'result': 'ok'}] * 4),
    json.dumps([{'method': method, 'result': 'ok'} for method in sorted(EXPECTED_METHODS)]
               + [{'method': 'set_acl', 'result': 'ok'}]),
])
def test_probe_rejects_malformed_or_incomplete_output(payload, monkeypatch, tmp_path, capsys):
    from scripts import ci_windows_acl_probe as probe
    monkeypatch.setattr(probe, 'os', SimpleNamespace(name='nt', environ={'TMPDIR': str(tmp_path)}))
    monkeypatch.setattr(probe.subprocess, 'run', lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout=payload, stderr='PRIVATE_CANARY'))
    with pytest.raises(SystemExit) as raised:
        probe.main()
    assert 'PRIVATE_CANARY' not in str(raised.value)
    assert raised.value.__suppress_context__
    assert raised.value.__cause__ is None
    assert capsys.readouterr() == ('', '')
    assert list(tmp_path.iterdir()) == []


def test_probe_emits_only_complete_filtered_report_after_cleanup(monkeypatch, tmp_path, capsys):
    from scripts import ci_windows_acl_probe as probe
    monkeypatch.setattr(probe, 'os', SimpleNamespace(name='nt', environ={'TMPDIR': str(tmp_path)}))
    rows = [{'method': method, 'result': 'ok', 'owner_rights_preserved': True,
             'path': 'PRIVATE_CANARY'} for method in sorted(EXPECTED_METHODS)]
    monkeypatch.setattr(probe.subprocess, 'run', lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout=json.dumps(rows), stderr='PRIVATE_CANARY'))
    assert probe.main() == 0
    captured = capsys.readouterr()
    assert 'PRIVATE_CANARY' not in captured.out + captured.err
    assert json.loads(captured.out) == [{k: v for k, v in row.items() if k != 'path'} for row in rows]
    assert captured.err == ''
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != 'win32', reason='Requires native Windows ACL APIs')
def test_probe_native_four_fresh_fixtures(monkeypatch, tmp_path, capsys):
    from scripts import ci_windows_acl_probe as probe
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.setenv('TMPDIR', str(tmp_path))
    assert probe.main() == 0
    captured = capsys.readouterr()
    rows = json.loads(captured.out)
    assert {row['method'] for row in rows} == EXPECTED_METHODS
    assert len(rows) == len(EXPECTED_METHODS)
    for row in rows:
        assert type(row['owner_rights_preserved']) is bool
        assert type(row['dacl_unchanged']) is bool
    assert captured.err == ''
    assert list(tmp_path.iterdir()) == []
