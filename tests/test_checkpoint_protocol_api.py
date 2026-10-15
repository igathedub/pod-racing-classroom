"""Backup protocol opt-in must be reflected consistently in API and starter."""
from fastapi.testclient import TestClient
import pytest
from test_base_path import prefixed


@pytest.mark.parametrize('base', ['', '/backup'])
def test_checkpoint_only_rules_describe_exactly_one_input_line(tmp_path, monkeypatch, base):
    monkeypatch.setenv('POD_INPUT_PROTOCOL','checkpoint-only')
    app=prefixed(tmp_path,monkeypatch,POD_BASE_PATH=base,POD_CLASS_ACCESS_REQUIRED=0)
    with TestClient(app) as client:
        rules=client.get(base+'/api/rules?lang=de').json()
        assert rules['protocol']['input']==['x y checkpoint_x checkpoint_y distance relative_angle']
        assert 'opponent' not in rules['protocol']
        assert rules['protocol']['name']=='checkpoint-only'


@pytest.mark.parametrize('language', ['de','en'])
def test_checkpoint_starter_has_one_input_and_only_documented_typo_fix(tmp_path, monkeypatch, language):
    from pathlib import Path
    import ast
    import hashlib
    monkeypatch.setenv('POD_INPUT_PROTOCOL','checkpoint-only')
    app=prefixed(tmp_path,monkeypatch,POD_CLASS_ACCESS_REQUIRED=0)
    expected=(Path(__file__).resolve().parents[1]/'examples/starters/05_Nadja_checkpoint.py').read_bytes()
    assert hashlib.sha256(expected).hexdigest()=='b06a10acd7d40ca9bcfc32fa2ba78033e1e25d3fe7c4d4e66d4cb18743fec1f6'
    tree=ast.parse(expected.decode())
    assert sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='input' for n in ast.walk(tree))==1
    with TestClient(app) as client:
        response=client.get('/backup/api/starter?lang='+language)
        assert response.content.endswith(expected)
        assert ('eine Zeile' if language=='de' else 'one line') in response.text


def test_invalid_protocol_refused_before_store_creation(tmp_path,monkeypatch):
    from arena.app import create_app
    monkeypatch.setenv('POD_INPUT_PROTOCOL','guess-by-source')
    monkeypatch.setenv('POD_ADMIN_TOKEN','synthetic-test-only')
    data=tmp_path/'must-not-exist'
    with pytest.raises(ValueError,match='POD_INPUT_PROTOCOL'):
        create_app(data)
    assert not data.exists()


def test_checkpoint_demo_sources_do_not_read_opponent_line(tmp_path,monkeypatch):
    import ast
    from test_api import AUTH
    monkeypatch.setenv('POD_INPUT_PROTOCOL','checkpoint-only')
    app=prefixed(tmp_path,monkeypatch,POD_CLASS_ACCESS_REQUIRED=0)
    with TestClient(app) as client:
        result=client.post('/backup/api/admin/demo',json={},headers=AUTH)
        assert result.status_code==200 and result.json()['inserted']==6
        saved=app.state.store.submissions(private=True)
        assert len(saved)==6
        for entry in saved:
            calls=[n for n in ast.walk(ast.parse(entry['code'])) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='input']
            assert len(calls)==1


def test_archived_checkpoint_replays_keep_protocol_identifier(tmp_path,monkeypatch):
    from test_api import AUTH
    monkeypatch.setenv('POD_INPUT_PROTOCOL','checkpoint-only')
    app=prefixed(tmp_path,monkeypatch,POD_CLASS_ACCESS_REQUIRED=0)
    with TestClient(app) as client:
        assert client.post('/backup/api/admin/demo',json={},headers=AUTH).status_code==200
        assert client.post('/backup/api/admin/qualify',json={},headers=AUTH).status_code==202
        app.state.tournament.worker.join(timeout=5)
        assert app.state.store.get('job')['status']=='finished'
        replays=app.state.store.replays()
        assert len(replays)==18
        for replay in replays:
            payload=client.get('/backup/api/replays/'+replay['id']).json()
            assert payload.get('input_protocol')=='checkpoint-only'
