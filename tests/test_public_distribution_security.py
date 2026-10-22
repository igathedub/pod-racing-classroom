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


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell launcher')
def test_windows_launcher_preserves_project_and_refuses_shell_text(tmp_path):
    shutil.copytree(ROOT/'distribution', tmp_path/'bundle')
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
    env = dict(os.environ, PATH=str(bindir)+os.pathsep+os.environ['PATH'], CALLS=str(calls))
    bundle = tmp_path/'bundle'
    (bundle/'.env').write_text('COMPOSE_PROJECT_NAME=production\nPOD_RELEASE_SOCKET=evil\n')
    for action in ('start','stop','start'):
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                        str(bundle/'classroom.ps1'),action], cwd=bundle, env=env, check=True)
    project = (bundle/'.classroom-project').read_text().strip()
    assert calls.read_text().count('--project-name '+project) == 7
    (bundle/'.classroom-project').write_text('pod-public-foo & echo OWNED > OWNED')
    result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                             str(bundle/'classroom.ps1'),'start'], cwd=bundle, env=env)
    assert result.returncode != 0
    assert not (bundle/'OWNED').exists()
