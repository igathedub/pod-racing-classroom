"""Security-focused distribution tests (configuration and CLI shims only)."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location('distcheck', ROOT / 'scripts/check_distribution.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.mark.parametrize('name', ['web/nested/.env.local', 'examples/nested/replays.json',
    'scripts/operator-handoff.md', 'arena/nested/local-report.txt', 'web/nested/classroom.DB'])
def test_staged_security_policy_rejects_nested_private_files(name):
    assert module().private_path(Path(name))


def test_digest_release_compose_config(tmp_path):
    spec = importlib.util.spec_from_file_location('pkg', ROOT / 'scripts/package.py')
    pkg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pkg)
    output = pkg.package_runtime(ROOT, tmp_path, 'v1.0.0', 'sha256:'+'a'*64, 'sha256:'+'b'*64)
    import zipfile
    with zipfile.ZipFile(output) as archive:
        archive.extractall(tmp_path / 'expanded')
    env = dict(os.environ, POD_RELEASE_SOCKET='/var/run/docker.sock')
    command = ['docker', 'compose', '--project-name', 'pod-public-config-test', '--env-file',
               'compose.defaults', '-f', 'compose.yaml', 'config', '--format', 'json']
    result = subprocess.run(command, cwd=tmp_path/'expanded/Pod-Racing-Classroom', env=env,
                            capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data['services']['classroom']['ports'][0]['host_ip'] == '127.0.0.1'
    assert 'build' not in data['services']['classroom']
    assert len(data['services']['sandbox'].get('volumes', [])) == 0
    assert data['services']['classroom']['environment']['POD_INPUT_PROTOCOL'] == 'checkpoint-only'
    assert data['volumes']['classroom-data']['name'] == 'pod-public-config-test_classroom-data'


@pytest.mark.skipif(not shutil.which('sh'), reason='POSIX shell required')
def test_posix_launcher_persists_identity_and_rejects_injection(tmp_path):
    shutil.copytree(ROOT/'distribution', tmp_path/'bundle')
    bindir = tmp_path/'bin'
    bindir.mkdir()
    shim = bindir/'docker'
    shim.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
'context show') echo desktop-linux;;
'context inspect desktop-linux --format {{.Endpoints.docker.Host}}') echo unix:///run/user/1000/docker.sock;;
*'info --format {{.OSType}}') echo linux;;
*'info --format {{.OperatingSystem}}') echo Debian;;
esac
''')
    shim.chmod(0o755)
    calls = tmp_path/'calls'
    env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'], CALLS=str(calls))
    bundle = tmp_path/'bundle'
    (bundle/'.env').write_text('POD_RELEASE_SOCKET=$(touch OWNED)\nCOMPOSE_PROJECT_NAME=production\n')
    for action in ('start','stop','start'):
        subprocess.run(['sh','classroom.sh',action], cwd=bundle, env=env, check=True)
    project = (bundle/'.classroom-project').read_text().strip()
    assert project.startswith('pod-public-')
    assert calls.read_text().count('--project-name '+project) == 7
    (bundle/'.classroom-project').write_text('pod-public-$(touch OWNED)')
    assert subprocess.run(['sh','classroom.sh','start'], cwd=bundle, env=env).returncode != 0
    assert not (bundle/'OWNED').exists()


@pytest.fixture
def incompatible_windows_modules(tmp_path):
    from scripts.classroom_backup import private_mkdir

    modules = tmp_path / 'core-only-modules'
    private_mkdir(modules)
    module = modules / 'Microsoft.PowerShell.Security'
    module.mkdir()
    # Trusted synthetic manifest only: reproduces Core/Windows module mismatch
    # without PowerShell 7, network access, or executing any foreign module code.
    (module / 'Microsoft.PowerShell.Security.psd1').write_text(
        "@{RootModule='Missing.CoreOnly.dll';ModuleVersion='99.0';"
        "GUID='bbff8ad2-6bae-4a03-9b1f-b2b66b57faf2';"
        "CmdletsToExport=@('Get-Acl','Set-Acl')}", encoding='utf-8')
    return modules


def windows_launcher_command(bundle, action, entrypoint):
    if entrypoint == 'cmd':
        return ['cmd.exe', '/d', '/c', str(bundle / (action.title() + '.cmd'))]
    return ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(bundle / 'classroom.ps1'), action]


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell launcher')
@pytest.mark.parametrize('entrypoint', ['script', 'cmd'])
@pytest.mark.parametrize('saved_project', [False, True])
def test_windows_launcher_preserves_project_and_refuses_shell_text(
        tmp_path, incompatible_windows_modules, entrypoint, saved_project):
    from scripts.classroom_backup import private_mkdir, privatize, require_private

    private_mkdir(tmp_path/'bundle')
    shutil.copytree(ROOT/'distribution', tmp_path/'bundle', dirs_exist_ok=True)
    bindir = tmp_path/'bin'
    bindir.mkdir()
    (bindir/'docker.cmd').write_text('''@echo off
>>"%CALLS%" echo %*
if "%~1"=="context" if "%~2"=="show" echo desktop-linux
if "%~1"=="context" if "%~2"=="inspect" echo npipe:////./pipe/dockerDesktopLinuxEngine
if "%~3"=="info" if "%~5"=="{{.OSType}}" echo linux
if "%~3"=="info" if "%~5"=="{{.OperatingSystem}}" echo Docker Desktop
exit /b 0
''')
    calls = tmp_path/'calls'
    env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'], CALLS=str(calls),
               PSModulePath=str(incompatible_windows_modules), POD_NO_PAUSE='1')
    bundle = tmp_path/'bundle'
    # Prove that this environment actually breaks native module autoloading.
    probe = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                            "$ErrorActionPreference='Stop'; Get-Acl -LiteralPath ."],
                           cwd=bundle, env=env, capture_output=True, text=True, errors='replace')
    assert probe.returncode != 0
    assert 'Microsoft.PowerShell.Security' in probe.stderr
    (bundle/'.env').write_text('COMPOSE_PROJECT_NAME=production\nPOD_RELEASE_SOCKET=evil\n')
    project = 'pod-public-' + 'a' * 32 if saved_project else None
    state = bundle/'.classroom-project'
    if saved_project:
        state.write_text(project + '\n')
    privatize(bundle)
    for action in ('start','stop','start'):
        result = subprocess.run(windows_launcher_command(bundle, action, entrypoint),
                                cwd=bundle, env=env, capture_output=True, text=True, errors='replace')
        assert result.returncode == 0, result.stdout + result.stderr
        if project is None:
            project = state.read_text().strip()
            assert project.startswith('pod-public-')
        assert state.read_text().strip() == project
        require_private(state)
        require_private(bundle/'teacher-private.log')
    assert env['PSModulePath'] == str(incompatible_windows_modules)
    assert calls.read_text().count('--project-name '+project) == 7
    state.write_text('pod-public-foo & echo OWNED > OWNED')
    before = calls.read_text()
    result = subprocess.run(windows_launcher_command(bundle, 'start', entrypoint),
                            cwd=bundle, env=env, capture_output=True, text=True, errors='replace')
    assert result.returncode != 0
    assert 'Invalid project file' in result.stderr
    assert all('compose' not in line or line.endswith('compose version')
               for line in calls.read_text()[len(before):].splitlines())
    assert not (bundle/'OWNED').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell launcher')
@pytest.mark.parametrize('entrypoint', ['script', 'cmd'])
@pytest.mark.parametrize('action', ['start', 'stop'])
def test_windows_launcher_rejects_remote_context_before_daemon_access(
        tmp_path, incompatible_windows_modules, entrypoint, action):
    shutil.copytree(ROOT/'distribution', tmp_path/'bundle')
    bundle = tmp_path/'bundle'
    bindir = tmp_path/'bin'
    bindir.mkdir()
    (bindir/'docker.cmd').write_text('''@echo off
>>"%CALLS%" echo %*
if "%~1"=="context" if "%~2"=="show" echo remote-test
if "%~1"=="context" if "%~2"=="inspect" echo tcp://remote.invalid:2375
exit /b 0
''')
    calls = tmp_path/'calls'
    env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'], CALLS=str(calls),
               PSModulePath=str(incompatible_windows_modules), POD_NO_PAUSE='1',
               DOCKER_HOST='tcp://untrusted.invalid:2375', DOCKER_CONTEXT='untrusted')
    state = bundle/'.classroom-project'
    state.write_text('pod-public-' + 'b' * 32 + '\n')
    teacher = bundle/'teacher-private.log'
    teacher.write_text('synthetic-private-sentinel\n')
    result = subprocess.run(windows_launcher_command(bundle, action, entrypoint),
                            cwd=bundle, env=env, capture_output=True, text=True, errors='replace')
    assert result.returncode != 0
    assert 'Only local Docker Desktop/Unix contexts are supported' in result.stderr
    assert calls.read_text().splitlines() == [
        'context show', 'context inspect remote-test --format {{.Endpoints.docker.Host}}']
    assert state.read_text() == 'pod-public-' + 'b' * 32 + '\n'
    assert teacher.read_text() == 'synthetic-private-sentinel\n'
