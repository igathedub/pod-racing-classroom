"""Opt-in REAL local Docker backup/restore acceptance with synthetic data only.

POD_BACKUP_ACCEPTANCE_CONTEXT, POD_BACKUP_ACCEPTANCE_ENDPOINT and
POD_BACKUP_ACCEPTANCE_IMAGE must be supplied explicitly. Never selects a
production container, opens a host port or connects to Cloudflare.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest
from arena.store import Store
from scripts.classroom_backup import Docker, inventory

ROOT = Path(__file__).resolve().parents[1]
KEYS = ['POD_BACKUP_ACCEPTANCE_CONTEXT','POD_BACKUP_ACCEPTANCE_ENDPOINT','POD_BACKUP_ACCEPTANCE_IMAGE']


@pytest.mark.docker
@pytest.mark.skipif(not all(os.environ.get(key) for key in KEYS), reason='explicit isolated local Docker acceptance not selected')
@pytest.mark.parametrize('prefix', ['', '/backup'], ids=['primary-root','backup-prefix'])
def test_real_backup_cli_cold_copy_restore_and_application_readback(tmp_path, prefix):
    context, endpoint, image = [os.environ[key] for key in KEYS]
    docker = Docker(context, endpoint)
    owner = uuid.uuid4().hex
    project = 'pod-backup-proof-' + owner
    label = 'pod.backup-acceptance.owner'
    source_volume, restored_volume = project+'-source', project+'-restored'
    containers, volumes = [], []
    seed = tmp_path / 'seed'
    seed.mkdir(mode=0o700)
    store = Store(seed)
    store.update(session={"status":"closed","deadline":None,"duration_seconds":7200}, job=Store.initial_job())
    with store.connection() as db:
        db.execute("UPDATE config SET value=? WHERE key='admin_token'", (json.dumps('SYNTHETIC-ACCEPTANCE-TEACHER'),))
        db.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?,?)", ('synthetic-student','Synthetic Bot','synthetic bot','print(1)','SYNTHETIC-CLAIM',1,1.0))
        db.execute("INSERT INTO replays VALUES (?,?,?,?,?)", ('synthetic-replay','Synthetic Replay','practice',1.0,'Synthetic Bot'))
    (seed/'replays/synthetic-replay.json').write_text('{"status":"finished","frames":[],"synthetic":true}')
    expected = inventory(seed)
    private = tmp_path / 'synthetic-private.env'
    private.write_text('SYNTHETIC-OPERATOR-SETTING=private-test-only\n')
    private.chmod(0o600)
    cli = [sys.executable,str(ROOT/'scripts/classroom_backup.py'),'--context',context,'--expected-endpoint',endpoint]
    def invoke(*args, success=True):
        result = subprocess.run(cli+list(map(str,args)),capture_output=True,text=True,timeout=180)
        if success:
            assert result.returncode == 0, 'Real CLI operation failed: '+result.stderr
            return json.loads(result.stdout)
        assert result.returncode != 0, 'Unsafe operation was not refused'
        assert 'SYNTHETIC-CLAIM' not in result.stderr
    def create_app(volume, name):
        cid = docker.call('create','--name',name,'--label',f'{label}={owner}','--label',f'com.docker.compose.project={project}',
            '--network','none','--mount',f'type=volume,src={volume},dst=/data','--env','POD_DATA_DIR=/data',
            '--env',f'POD_BASE_PATH={prefix}','--health-cmd',f"python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765{prefix}/api/health')\"",
            '--health-interval','1s','--health-timeout','3s','--health-retries','20','--entrypoint','python',image,
            '-m','uvicorn','arena.app:create_app','--factory','--host','0.0.0.0','--port','8765').strip()
        containers.append(cid)
        return cid
    def healthy(cid):
        deadline = time.monotonic()+60
        while time.monotonic() < deadline:
            item = docker.container(cid)
            if item['State'].get('Health',{}).get('Status')=='healthy':
                return item
            time.sleep(0.5)
        pytest.fail('Synthetic test application did not become healthy; diagnostics withheld')
    try:
        for volume in [source_volume]:
            assert volume not in docker.call('volume','ls','--format','{{.Name}}').splitlines()
            docker.call('volume','create','--label',f'{label}={owner}',volume)
            volumes.append(volume)
        app = create_app(source_volume, project+'-app')
        docker.call('cp',str(seed)+os.sep+'.',f'{app}:/data/.')
        docker.call('start',app)
        original = healthy(app)
        gate = docker.call('create','--name',project+'-gate','--label',f'{label}={owner}',
            '--label',f'com.docker.compose.project={project}','--network','none','--entrypoint','python',image,
            '-c','import time; time.sleep(3600)').strip()
        containers.append(gate)
        docker.call('start',gate)
        before = invoke('inspect','--project',project,'--container',app,'--volume',source_volume)
        assert before['counts']['submissions']==1 and before['counts']['replays']==1
        backup = tmp_path / 'verified-backup'
        saved = invoke('backup','--project',project,'--container',app,'--volume',source_volume,
            '--gate-container',gate,'--output',backup,'--private-file',private)
        assert saved['counts']==before['counts']
        assert inventory(backup/'data')==expected
        assert invoke('check','--backup',backup)['status']=='verified'
        after = healthy(app)
        assert (after['Id'],after['Image'],after['Config'])==(original['Id'],original['Image'],original['Config'])
        assert docker.container(gate)['State']['Running']
        restored = invoke('restore','--backup',backup,'--new-volume',restored_volume,'--image',image)
        volumes.append(restored_volume)
        assert restored['counts']==saved['counts']
        # Exactly the volume returned by restore; root and prefixed apps both read it.
        restored_app = create_app(restored_volume,project+'-restored-app')
        docker.call('start',restored_app)
        healthy(restored_app)
        actual = invoke('inspect','--project',project,'--container',restored_app,'--volume',restored_volume)
        assert actual['counts']==saved['counts']
        token_check = "import sqlite3,json; db=sqlite3.connect('/data/classroom.sqlite3'); assert json.loads(db.execute(\"SELECT value FROM config WHERE key='admin_token'\").fetchone()[0])=='SYNTHETIC-ACCEPTANCE-TEACHER'; assert db.execute('SELECT claim_token FROM submissions').fetchone()[0]=='SYNTHETIC-CLAIM'"
        docker.call('exec',restored_app,'python','-c',token_check)
        invoke('restore','--backup',backup,'--new-volume',restored_volume,'--image',image,success=False)
        assert not docker.call('container','ls','--all','--quiet','--filter',f'label=classroom.private-backup.owner').strip()
    finally:
        # Only our exact IDs and labeled volumes. No compose down/prune commands.
        for cid in reversed(containers):
            item = docker.container(cid)
            assert item['Config'].get('Labels',{}).get(label)==owner
            docker.call('rm','--force',cid)
        for volume in volumes:
            item = docker.json('volume','inspect',volume)[0]
            assert item.get('Labels',{}).get(label)==owner or item.get('Labels',{}).get('classroom.private-backup.owner')
            docker.call('volume','rm',volume)
        # Retain a failed restore volume for private diagnosis, exactly as CLI promises.
