"""Portable protected deployment contracts; no production secrets or resources."""
from pathlib import Path
import json
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_release_profiles_require_explicit_existing_volume_and_images():
    common = ROOT / 'deploy/compose.codeweek-common.yaml'
    assert common.exists(), 'Portable protected release profile missing'
    text = common.read_text()
    assert '${POD_APP_IMAGE:?' in text
    assert '${POD_BOT_IMAGE:?' in text
    assert '${POD_DATA_VOLUME:?' in text
    assert 'external: true' in text
    assert 'ports: !reset []' in text
    assert '127.0.0.1' not in text  # gate ports inherited only from protected overlay
    primary = (ROOT / 'deploy/compose.codeweek-primary.yaml').read_text()
    backup = (ROOT / 'deploy/compose.codeweek-backup.yaml').read_text()
    assert 'POD_BASE_PATH: ""' in primary
    assert 'POD_BASE_PATH: /backup' in backup
    assert "POD_CLASS_COOKIE_SECURE: '1'" in primary and "POD_CLASS_COOKIE_SECURE: '1'" in backup
    assert 'POD_BACKUP_EDGE_SECRET:?' in backup
    assert 'Caddyfile.backup' in backup
    assert '/Users/' not in primary + backup + text
    assert 'external: true' in text


def test_custom_bot_image_is_configured_without_dockerfile_source_rewriting(monkeypatch):
    from arena import bots
    assert hasattr(bots, 'configured_image'), 'Trusted bot image setting missing'
    monkeypatch.delenv('POD_BOT_IMAGE', raising=False)
    assert bots.configured_image() == 'pod-classroom-bot:local'
    monkeypatch.setenv('POD_BOT_IMAGE', 'pod-classroom-backup-bot:release-test')
    assert bots.configured_image() == 'pod-classroom-backup-bot:release-test'
    for value in ['', '-v', 'image with spaces', 'image\nother', 'image;command']:
        monkeypatch.setenv('POD_BOT_IMAGE', value)
        with pytest.raises(ValueError):
            bots.configured_image()


def test_backup_cloudflare_inventory_has_no_credentials():
    data = json.loads((ROOT / 'deploy/cloudflare/topology.json').read_text())
    assert data['primary']['hostname'] == 'codeweek-wi.de'
    assert data['primary']['service'] == 'http://127.0.0.1:8766'
    assert data['backup']['route_pattern'] == 'codeweek-wi.de/backup*'
    assert data['backup']['service'] == 'http://127.0.0.1:8766'
    assert data['backup']['worker'] == 'pod-classroom-mac-backup'
    assert set(data['private_artifacts']) >= {'primary_tunnel_token','backup_tunnel_token','primary_data_backup','backup_data_backup','website_passwords_and_hashes','teacher_tokens'}
    assert '217.160.0.94' not in json.dumps(data)


def test_compose_contracts_run_in_the_docker_ci_job():
    # A CLI on PATH must not opt hosted jobs into the dedicated Docker contracts.
    for contract in (test_effective_profiles_have_only_loopback_gate_port,
                     test_release_profiles_forward_input_protocol_without_silent_fallback):
        assert 'docker' in {mark.name for mark in contract.pytestmark}


@pytest.mark.docker
@pytest.mark.skipif(not __import__('shutil').which('docker'), reason='Compose CLI unavailable')
def test_effective_profiles_have_only_loopback_gate_port(tmp_path):
    # Config parsing only, never connects to any daemon or changes external state.
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('POD_') or key.startswith('COMPOSE_'):
            env.pop(key)
    private = tmp_path / 'synthetic.env'
    private.write_text("POD_APP_IMAGE=pod-test-app:synthetic\nPOD_BOT_IMAGE=pod-test-bot:synthetic\nPOD_DATA_VOLUME=synthetic-external-volume\nPOD_SITE_PASSWORD_HASH='synthetic-validation-only'\nPOD_BACKUP_EDGE_SECRET=synthetic-validation-only\n")
    for role in ('primary','backup'):
        args = ['docker','compose','--project-name','synthetic-'+role,'--project-directory',str(ROOT),'--env-file',str(private),'-f',str(ROOT/'compose.yaml'),'-f',str(ROOT/'compose.password.yaml'),'-f',str(ROOT/'deploy/compose.codeweek-common.yaml'),'-f',str(ROOT/('deploy/compose.codeweek-'+role+'.yaml')),'config','--format','json']
        result = subprocess.run(args,env=env,capture_output=True,text=True,timeout=30)
        assert result.returncode == 0, 'Compose configuration failed (output withheld)'
        config = json.loads(result.stdout)
        assert not config['services']['classroom'].get('ports')
        assert config['services']['password-gate']['ports'][0]['host_ip']=='127.0.0.1'
        assert config['services']['password-gate']['ports'][0]['published']=='8766'
        assert config['services']['classroom']['environment']['POD_BOT_IMAGE']=='pod-test-bot:synthetic'
        assert config['services']['sandbox']['image']=='pod-test-bot:synthetic'
        assert config['volumes']['classroom-data']['external'] is True
        assert config['volumes']['classroom-data']['name']=='synthetic-external-volume'


@pytest.mark.docker
@pytest.mark.skipif(not __import__('shutil').which('docker'), reason='Compose CLI unavailable')
@pytest.mark.parametrize('role', ['primary', 'backup'])
@pytest.mark.parametrize('requested', [None, 'checkpoint-only', 'legacy', '', 'invalid-mode'])
def test_release_profiles_forward_input_protocol_without_silent_fallback(tmp_path, role, requested):
    # Parse synthetic configuration only: no daemon, live env, or real secrets.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('POD_', 'COMPOSE_'))}
    if requested is not None:
        env['POD_INPUT_PROTOCOL'] = requested
    private = tmp_path / 'synthetic.env'
    private.write_text('POD_APP_IMAGE=pod-test-app:synthetic\nPOD_BOT_IMAGE=pod-test-bot:synthetic\n'
                       'POD_DATA_VOLUME=synthetic-volume\nPOD_SITE_PASSWORD_HASH=synthetic-only\n'
                       'POD_BACKUP_EDGE_SECRET=synthetic-only\n')
    args = ['docker', 'compose', '--project-name', 'synthetic-' + role,
            '--project-directory', str(ROOT), '--env-file', str(private)]
    for name in ['compose.yaml', 'compose.password.yaml', 'deploy/compose.codeweek-common.yaml',
                 'deploy/compose.codeweek-' + role + '.yaml']:
        args.extend(['-f', str(ROOT / name)])
    result = subprocess.run(args + ['config', '--format', 'json'], env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'Synthetic Compose parsing failed (output withheld)'
    actual = json.loads(result.stdout)['services']['classroom']['environment']
    assert actual.get('POD_INPUT_PROTOCOL') == ('legacy' if requested is None else requested)
