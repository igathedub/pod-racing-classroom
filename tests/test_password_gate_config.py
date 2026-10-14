"""Password-gate contracts; opt-in real Docker HTTP acceptance (no app writes)."""
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_compose_gate_is_only_loopback_ingress():
    path = ROOT / 'compose.password.yaml'
    assert path.exists(), 'password deployment override is missing'
    config = path.read_text(encoding='utf-8')
    assert 'ports: !reset []' in config
    assert '127.0.0.1:8766:8080' in config
    assert '${POD_SITE_PASSWORD_HASH:?' in config
    assert '${POD_SITE_USER:-igor}' in config
    assert 'caddy:2.11.6-alpine@sha256:' in config
    assert 'read_only: true' in config
    assert 'cap_drop: [ALL]' in config
    assert 'no-new-privileges:true' in config
    assert 'cpus:' in config and 'mem_limit:' in config
    assert 'create_host_path: false' in config
    assert 'read_only: true' in config
    assert 'docker.sock' not in config
    assert 'classroom-data' not in config  # Inherit the existing named volume.
    assert 'POD_CLASS_ACCESS_REQUIRED' not in config



def test_caddy_whole_site_hash_only_gate():
    path = ROOT / 'deploy/Caddyfile.password'
    assert path.exists(), 'whole-site password gate template is missing'
    config = path.read_text(encoding='utf-8')
    assert 'admin off' in config
    assert 'auto_https off' in config
    assert 'basic_auth argon2id' in config
    assert '{$POD_SITE_USER} {$POD_SITE_PASSWORD_HASH}' in config
    assert 'reverse_proxy classroom:8765' in config
    assert 'header_up -Authorization' in config
    assert 'http://:8080' in config
    assert '@' not in config  # No path matcher or health bypass.
    assert 'X-Admin-Token' not in config  # Leave independent teacher authentication intact.


# No access logging and no credential values recorded by the stub.
STUB = '''
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
hits = []
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == '/_hits':
            payload = hits
        else:
            payload = dict(path=self.path, authorization_present='Authorization' in self.headers,
                           admin=self.headers.get('X-Admin-Token'), cookie=self.headers.get('Cookie'),
                           host=self.headers.get('Host'))
            hits.append(payload)
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Set-Cookie', 'pod_class=test; HttpOnly; Secure; SameSite=Lax')
        self.end_headers()
        self.wfile.write(body)
    do_POST = do_GET
HTTPServer(('0.0.0.0', 8765), Handler).serve_forever()
'''


def docker(*args, input=None, env=None, check=True):
    result = subprocess.run(['docker', *args], input=input.encode() if input is not None else None,
                            env=env, capture_output=True, timeout=90)
    result.stdout = result.stdout.decode('utf-8', errors='replace')
    result.stderr = result.stderr.decode('utf-8', errors='replace')
    if check and result.returncode:
        pytest.fail(f'Docker operation {args[0]} failed (exit {result.returncode}); '
                    'output suppressed to avoid exposing credentials')
    return result


def cleanup_gate_resources(containers, network, label, original_error=None):
    """Remove only this run's inspected IDs; never let one failure abort readback."""
    key, value = label.split('=', 1)
    failures = []
    targets = [('container', name) for name in containers] + [('network', network)]
    owned = {}

    def operation(*args):
        try:
            return docker(*args, check=False)
        except (subprocess.TimeoutExpired, OSError) as error:
            failures.append(f'{args[0]} operation: {type(error).__name__}')
            return None

    def inspect(kind, name):
        result = operation(kind, 'inspect', name)
        if result is None:
            return None
        if result.returncode:
            missing_network = (kind == 'network' and result.stderr.strip().lower() ==
                               f'error response from daemon: network {name} not found'.lower())
            if not missing_network and not any(text in result.stderr.lower() for text in
                                               ('no such object', 'no such container', 'no such network')):
                failures.append(f'{kind} inspection failed')
            return None
        try:
            record = json.loads(result.stdout)[0]
            labels = record['Config'].get('Labels') if kind == 'container' else record.get('Labels')
            return record['Id'] if (labels or {}).get(key) == value else None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            failures.append(f'{kind} inspection returned invalid metadata')
            return None

    for kind, name in targets:
        resource_id = inspect(kind, name)
        if resource_id is not None:
            owned[(kind, name)] = resource_id
            args = ('rm', '-f', resource_id) if kind == 'container' else ('network', 'rm', resource_id)
            result = operation(*args)
            if result is not None and result.returncode:
                failures.append(f'{kind} removal failed')

    # Read back every planned target, including partial creation / failed inspections.
    for kind, name in targets:
        if inspect(kind, owned.get((kind, name), name)) is not None:
            failures.append(f'owned {kind} remains')
    for args, kind in [(('ps', '-aq', '--filter', 'label=' + label), 'containers'),
                       (('network', 'ls', '-q', '--filter', 'label=' + label), 'networks')]:
        result = operation(*args)
        if result is not None:
            if result.returncode:
                failures.append(f'{kind} leak verification failed')
            elif result.stdout.strip():
                failures.append(f'owned {kind} remain')
    if failures:
        message = 'password-gate cleanup failed: ' + '; '.join(failures)
        if original_error is not None:
            original_error.add_note(message)
        else:
            pytest.fail(message)


@pytest.mark.parametrize('foreign_labels', [{}, {'pod.password-gate-test': 'other-run'}])
def test_cleanup_never_removes_foreign_name_collisions(monkeypatch, foreign_labels):
    calls = []

    def fake_docker(*args, **kwargs):
        calls.append(args)
        if 'inspect' in args:
            config = {'Labels': foreign_labels}
            record = {'Id': 'foreign-id', 'Config': config, **config}
            return subprocess.CompletedProcess(args, 0, json.dumps([record]), '')
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(__import__(__name__, fromlist=['docker']), 'docker', fake_docker)
    cleanup_gate_resources(['collision-container'], 'collision-network', 'pod.password-gate-test=this-run')
    assert not any('rm' in args for args in calls), calls
    assert any('inspect' in args and 'collision-container' in args for args in calls)
    assert any('inspect' in args and 'collision-network' in args for args in calls)


@pytest.mark.parametrize('original_failure', [False, True])
@pytest.mark.parametrize('error_type', [subprocess.TimeoutExpired, OSError])
@pytest.mark.parametrize('failed_operation', ['inspect', 'remove', 'readback'])
def test_cleanup_continues_after_operation_errors(monkeypatch, error_type, failed_operation, original_failure):
    calls = []
    inspections = {}
    remaining = {'first', 'second', 'network'}
    raised = False

    def fake_docker(*args, **kwargs):
        nonlocal raised
        calls.append(args)
        name = args[-1]
        inspecting = 'inspect' in args
        if inspecting:
            inspections[name] = inspections.get(name, 0) + 1
        should_raise = (
            name == 'first' and (
                (failed_operation == 'inspect' and inspecting and inspections[name] == 1) or
                (failed_operation == 'remove' and 'rm' in args) or
                (failed_operation == 'readback' and inspecting and inspections[name] == 2)))
        if should_raise and not raised:
            raised = True
            if error_type is subprocess.TimeoutExpired:
                raise error_type('docker', 90)
            raise error_type('cannot launch docker')
        if inspecting:
            if name not in remaining:
                return subprocess.CompletedProcess(args, 1, '', 'Error: No such object: ' + name)
            labels = {'pod.password-gate-test': 'this-run'}
            return subprocess.CompletedProcess(args, 0,
                                               json.dumps([{'Id': name, 'Config': {'Labels': labels},
                                                            'Labels': labels}]), '')
        if 'rm' in args:
            remaining.discard(name)
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(__import__(__name__, fromlist=['docker']), 'docker', fake_docker)
    original = AssertionError('original acceptance failure')
    if original_failure:
        cleanup_gate_resources(['first', 'second'], 'network', 'pod.password-gate-test=this-run', original)
        assert str(original) == 'original acceptance failure'
        assert any('cleanup' in note and error_type.__name__ in note for note in original.__notes__)
    else:
        with pytest.raises(pytest.fail.Exception, match='cleanup.*' + error_type.__name__):
            cleanup_gate_resources(['first', 'second'], 'network', 'pod.password-gate-test=this-run')
    assert raised, calls
    assert ('rm', '-f', 'second') in calls
    assert ('network', 'rm', 'network') in calls
    assert inspections.get('first', 0) >= 2
    assert inspections.get('second', 0) >= 2
    assert inspections.get('network', 0) >= 2
    assert ('ps', '-aq', '--filter', 'label=pod.password-gate-test=this-run') in calls
    assert ('network', 'ls', '-q', '--filter', 'label=pod.password-gate-test=this-run') in calls


def test_cleanup_accepts_docker_network_not_found_readback(monkeypatch):
    def fake_docker(*args, **kwargs):
        if args[:2] == ('network', 'inspect'):
            return subprocess.CompletedProcess(args, 1, '[]',
                                               'Error response from daemon: network absent-network not found')
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(__import__(__name__, fromlist=['docker']), 'docker', fake_docker)
    cleanup_gate_resources([], 'absent-network', 'pod.password-gate-test=this-run')


@pytest.mark.skipif(os.environ.get('POD_GATE_DOCKER_TEST') != '1',
                    reason='opt in to isolated Docker acceptance with POD_GATE_DOCKER_TEST=1')
def test_real_caddy_password_gate():
    stub_image = os.environ.get('POD_GATE_TEST_STUB_IMAGE')
    assert stub_image, 'Set POD_GATE_TEST_STUB_IMAGE to an existing image with Python; no image is built'
    image = re.search(r'image: (\S+)', (ROOT / 'compose.password.yaml').read_text()).group(1)
    prefix = 'pod-gate-test-' + uuid.uuid4().hex[:12]
    network, upstream, gate = prefix + '-net', prefix + '-stub', prefix + '-caddy'
    label = 'pod.password-gate-test=' + prefix
    password = secrets.token_urlsafe(32)
    env = os.environ.copy()
    env.pop('POD_SITE_PASSWORD_HASH', None)
    env['POD_SITE_USER'] = 'igor'
    env['GOMAXPROCS'] = '1'
    mount = f'type=bind,source={(ROOT / "deploy/Caddyfile.password").as_posix()},target=/etc/caddy/Caddyfile,readonly'
    limits = ['--label', label, '--cpus', '0.25', '--memory', '192m', '--read-only',
              '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true']
    caddy_entry = ['--tmpfs', '/run:rw,exec,nosuid,size=64m,mode=0755', '--entrypoint', '/bin/sh']
    caddy_copy = 'cp /usr/bin/caddy /run/caddy; exec /run/caddy '
    temporary = []
    opener = build_opener(ProxyHandler({}))

    def request(path, credentials=None, method='GET'):
        headers = {'Host': 'classroom.test', 'X-Admin-Token': 'ephemeral-admin',
                   'Cookie': 'pod_class=ephemeral-cookie'}
        if credentials is not None:
            headers['Authorization'] = 'Basic ' + base64.b64encode(credentials.encode()).decode()
        try:
            response = opener.open(Request(base + path, headers=headers, method=method), timeout=5)
        except HTTPError as error:
            response = error
        return response.status, response.headers, response.read()

    def wait_gate():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if request('/')[0] == 401:
                    return
            except (URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(0.1)
        logs = docker('logs', gate, check=False)
        pytest.fail('isolated gate did not become ready: ' + logs.stderr.replace(hashed, '<hash>'))

    def hits():
        result = docker('exec', upstream, 'python', '-c',
                        "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/_hits').read().decode())")
        return json.loads(result.stdout)

    try:
        hash_name = prefix + '-hash'
        temporary.append(hash_name)
        hashed = docker('run', '--rm', '-i', '--name', hash_name, *limits, '-e', 'GOMAXPROCS',
                        *caddy_entry, image, '-ec', caddy_copy + 'hash-password --algorithm argon2id',
                        input=password + '\n', env=env).stdout.strip()
        assert hashed.startswith('$argon2id$'), 'hash-password did not return Argon2id'
        env['POD_SITE_PASSWORD_HASH'] = hashed
        compose_args = ['compose', '--project-directory', str(ROOT), '--env-file', os.devnull,
                        '-f', str(ROOT / 'compose.yaml'), '-f', str(ROOT / 'compose.password.yaml'),
                        'config', '--format', 'json']
        merged = json.loads(docker(*compose_args, env=env).stdout)
        assert not merged['services']['classroom'].get('ports')
        service = merged['services']['password-gate']
        assert service['entrypoint'] == ['/bin/sh', '-ec']
        assert service['command'] == [caddy_copy + 'run --config /etc/caddy/Caddyfile --adapter caddyfile']
        assert service['tmpfs'] == ['/run:rw,exec,nosuid,size=64m,mode=0755']
        assert service['cap_drop'] == ['ALL']
        assert service['read_only'] is True
        assert service['security_opt'] == ['no-new-privileges:true']
        assert len(service['ports']) == 1
        assert service['ports'][0]['host_ip'] == '127.0.0.1'
        assert str(service['ports'][0]['published']) == '8766'
        assert len(service['volumes']) == 1 and service['volumes'][0]['read_only'] is True
        assert merged['services']['classroom']['volumes'][0]['source'] == 'classroom-data'
        absent = env.copy()
        absent.pop('POD_SITE_PASSWORD_HASH')
        assert docker(*compose_args, env=absent, check=False).returncode != 0
        for index, value in enumerate((hashed, '', 'not-an-argon2id-hash')):
            validation_env = env.copy()
            validation_env['POD_SITE_PASSWORD_HASH'] = value
            name = prefix + '-validate-' + str(index)
            temporary.append(name)
            result = docker('run', '--rm', '--name', name, *limits, '--mount', mount,
                            '-e', 'POD_SITE_USER', '-e', 'POD_SITE_PASSWORD_HASH', '-e', 'GOMAXPROCS',
                            *caddy_entry, image, '-ec', caddy_copy +
                            'validate --config /etc/caddy/Caddyfile --adapter caddyfile',
                            env=validation_env, check=False)
            assert (result.returncode == 0) == (index == 0), f'hash validation case {index}'
        docker('network', 'create', '--label', label, network)
        docker('run', '-d', '--name', upstream, *limits, '--network', network,
               '--network-alias', 'classroom', '--entrypoint', 'python', stub_image, '-u', '-c', STUB)
        docker('run', '-d', '--name', gate, *limits, '--network', network,
               '-p', '127.0.0.1::8080', '--mount', mount, '-e', 'POD_SITE_USER',
               '-e', 'POD_SITE_PASSWORD_HASH', '-e', 'GOMAXPROCS', *caddy_entry, image, '-ec',
               caddy_copy + 'run --config /etc/caddy/Caddyfile --adapter caddyfile', env=env)
        port_result = docker('port', gate, '8080/tcp', check=False)
        if port_result.returncode:
            logs = docker('logs', gate, check=False)
            pytest.fail('gate startup/port failed: ' + (logs.stderr + port_result.stderr).replace(hashed, '<hash>'))
        port = port_result.stdout.strip().rsplit(':', 1)[1]
        base = 'http://127.0.0.1:' + port
        wait_gate()
        paths = ['/', '/assets/app.js', '/health', '/healthz', '/api/state', '/teacher',
                 '/projector', '/api/admin/access/invitation', '/api/submissions']
        for path in paths:
            for credential in (None, 'igor:wrong', 'wrong:' + password):
                status, headers, _ = request(path, credential)
                assert status == 401, path
                assert headers.get('WWW-Authenticate', '').startswith('Basic ')
        assert hits() == [], 'unauthorized requests reached upstream'
        for path in paths:
            status, headers, body = request(path, 'igor:' + password)
            assert status == 200, path
            record = json.loads(body)
            assert record == dict(path=path, authorization_present=False, admin='ephemeral-admin',
                                  cookie='pod_class=ephemeral-cookie', host='classroom.test')
            assert headers.get('Set-Cookie') == 'pod_class=test; HttpOnly; Secure; SameSite=Lax'
        before = len(hits())
        assert request('/api/submissions', method='POST')[0] == 401
        assert len(hits()) == before
        assert request('/api/submissions', 'igor:' + password, method='POST')[0] == 200
        docker('restart', gate)
        port = docker('port', gate, '8080/tcp').stdout.strip().rsplit(':', 1)[1]
        base = 'http://127.0.0.1:' + port
        wait_gate()
        before = len(hits())
        assert request('/api/state', 'igor:wrong')[0] == 401
        assert len(hits()) == before
        assert request('/api/state', 'igor:' + password)[0] == 200
    finally:
        cleanup_gate_resources([gate, upstream, *temporary], network, label, sys.exc_info()[1])
