"""Execute both launchers against recording CLI shims, never a real daemon."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=['posix', 'windows'])
def launcher(request, tmp_path):
    kind = request.param
    if kind == 'windows' and os.name != 'nt':
        pytest.skip('Windows PowerShell required')
    if kind == 'posix' and not shutil.which('sh'):
        pytest.skip('POSIX shell required')
    bundle = tmp_path / 'bundle'
    shutil.copytree(ROOT / 'distribution', bundle)
    (bundle / '.classroom-project').write_text('pod-public-' + 'a' * 32 + '\n')
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    (bindir / 'docker').write_text('''#!/bin/sh
printf '%s|%s\\n' "$*" "$POD_RELEASE_SOCKET" >> "$CALLS"
case "$*" in
'context show') [ "$FAIL" != context ] || exit 7; echo selected;;
'context inspect selected --format {{.Endpoints.docker.Host}}') [ "$FAIL" != inspect ] || exit 7; printf '%s\\n' "$ENDPOINT";;
*'info --format {{.OSType}}') [ "$FAIL" != info ] || exit 7; printf '%s\\n' "$OSTYPE_REPLY";;
*'info --format {{.OperatingSystem}}') [ "$FAIL" != server ] || exit 7; printf '%s\\n' "$SERVER_OS";;
*'compose version') [ "$FAIL" != compose ] || exit 7;;
esac
''')
    (bindir / 'docker').chmod(0o755)
    (bindir / 'docker.cmd').write_text('''@echo off
>>"%CALLS%" echo %*^|%POD_RELEASE_SOCKET%
if "%~1"=="context" if "%~2"=="show" (
 if "%FAIL%"=="context" exit /b 7
 echo selected
)
if "%~1"=="context" if "%~2"=="inspect" (
 if "%FAIL%"=="inspect" exit /b 7
 powershell.exe -NoProfile -Command "[Console]::WriteLine($env:ENDPOINT)"
)
if "%~3"=="info" (
 if "%FAIL%"=="info" exit /b 7
 if "%~5"=="{{.OSType}}" echo %OSTYPE_REPLY%
 if "%~5"=="{{.OperatingSystem}}" (
  if "%FAIL%"=="server" exit /b 7
  powershell.exe -NoProfile -Command "[Console]::WriteLine($env:SERVER_OS)"
 )
)
if "%~3"=="compose" if "%~4"=="version" if "%FAIL%"=="compose" exit /b 7
exit /b 0
''')
    calls = tmp_path / 'calls'

    def run(endpoint, server='Docker Desktop', ostype='linux', fail=''):
        env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
                   CALLS=str(calls), ENDPOINT=endpoint, SERVER_OS=server,
                   OSTYPE_REPLY=ostype, FAIL=fail, POD_RELEASE_SOCKET='poison')
        command = (['sh', 'classroom.sh', 'stop'] if kind == 'posix' else
                   ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(bundle / 'classroom.ps1'), 'stop'])
        result = subprocess.run(command, cwd=bundle, env=env, capture_output=True, text=True)
        return result, calls.read_text() if calls.exists() else ''
    return run


@pytest.mark.parametrize('endpoint', [
    'npipe:////remote-host/pipe/docker_engine', 'npipe://remote-host/pipe/docker_engine',
    'npipe:////localhost/pipe/docker_engine', 'npipe:////./pipe/',
    'npipe:////./pipe/docker_engine/extra', 'npipe:////./pipe/../docker_engine',
    'npipe:////./pipe/docker_engine?remote=x', 'npipe:////./pipe/docker_engine\nextra',
    'tcp://127.0.0.1:2375', 'ssh://localhost', 'unix://remote/path',
    'unix:////remote/path', 'unix:///tmp/../docker.sock', 'unix:///tmp/docker.sock?x',
])
def test_invalid_endpoint_refused_before_daemon(launcher, endpoint):
    result, calls = launcher(endpoint)
    assert result.returncode != 0
    assert ' info ' not in calls
    assert ' compose ' not in calls


@pytest.mark.parametrize('endpoint,server,socket', [
    ('unix:///Users/teacher/.docker/run/docker.sock', 'Docker Desktop', '/var/run/docker.sock'),
    ('unix:///home/teacher/.docker/desktop/docker.sock', 'Docker Desktop', '/var/run/docker.sock'),
    ('npipe:////./pipe/dockerDesktopLinuxEngine', 'Docker Desktop', '/var/run/docker.sock'),
    ('npipe:////./pipe/docker_engine', 'Docker Desktop', '/var/run/docker.sock'),
    ('unix:///var/run/docker.sock', 'Ubuntu 24.04 LTS', '/var/run/docker.sock'),
    ('unix:///run/user/1000/docker.sock', 'Debian GNU/Linux 12 (bookworm)', '/run/user/1000/docker.sock'),
])
def test_daemon_side_socket_mapping(launcher, endpoint, server, socket):
    result, calls = launcher(endpoint, server=server)
    assert result.returncode == 0, result.stderr
    assert 'info --format {{.OperatingSystem}}' in calls
    assert ' stop|' + socket in calls
    assert 'poison' not in calls.split(' compose ')[-1]


@pytest.mark.parametrize('endpoint,server,ostype,fail', [
    ('npipe:////./pipe/docker_engine', 'Ubuntu', 'linux', ''),
    ('unix:///var/run/docker.sock', '', 'linux', ''),
    ('unix:///var/run/docker.sock', '<no value>', 'linux', ''),
    ('unix:///var/run/docker.sock', 'Docker Desktop', 'windows', ''),
    *[('unix:///var/run/docker.sock', 'Docker Desktop', 'linux', failure)
      for failure in ('context', 'inspect', 'info', 'server', 'compose')],
])
def test_preflight_failure_never_runs_project_compose(launcher, endpoint, server, ostype, fail):
    result, calls = launcher(endpoint, server=server, ostype=ostype, fail=fail)
    assert result.returncode != 0
    assert '--project-name' not in calls
