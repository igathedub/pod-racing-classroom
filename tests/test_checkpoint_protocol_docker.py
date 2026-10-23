"""Opt-in real Docker protocol comparisons; never touches live classroom state."""
import json
import os
from pathlib import Path

import pytest

pytestmark=[pytest.mark.docker,pytest.mark.skipif(os.environ.get('POD_CHECKPOINT_DOCKER_TEST')!='1',reason='opt in to local isolated protocol acceptance')]
ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def sandbox(monkeypatch):
    from scripts.classroom_backup import Docker
    from arena import bots
    context=os.environ['POD_CHECKPOINT_CONTEXT']
    endpoint=os.environ['POD_CHECKPOINT_ENDPOINT']
    image=os.environ['POD_CHECKPOINT_BOT_IMAGE']
    docker=Docker(context,endpoint)
    assert docker.json('image','inspect',image)[0]['Id'].startswith('sha256:')
    monkeypatch.delenv('DOCKER_HOST',raising=False)
    monkeypatch.setenv('DOCKER_CONTEXT',context)
    monkeypatch.setattr(bots,'IMAGE',image)
    assert bots.sandbox_status()['available']
    return docker


def record(row):
    target=os.environ.get('POD_CHECKPOINT_REPORT')
    if target:
        with Path(target).open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(row)+'\n')


def race(sandbox,source,protocol,track,max_turns=700):
    from arena.engine import run_race
    from arena.bots import make_runner,DockerRunner
    names=[]
    def factory(entry):
        runner=make_runner(entry)
        if isinstance(runner,DockerRunner):
            names.append(runner.name)
        return runner
    replay=run_race([{'id':'candidate','alias':'Synthetic candidate','code':source},{'id':'ghost','alias':'Reference ghost','kind':'reference','code':'baseline'}],track,laps=2,max_turns=max_turns,input_protocol=protocol,runner_factory=factory)
    for name in names:
        assert not sandbox.call('container','ls','--all','--quiet','--filter','name=^/'+name+'$').strip()
    return next(row for row in replay['results'] if row['id']=='candidate')


@pytest.mark.parametrize('version,protocol,path',[
    ('legacy','legacy','examples/starters/05_Nadja.py'),
    ('checkpoint-only','checkpoint-only','examples/starters/05_Nadja_checkpoint.py')])
@pytest.mark.parametrize('track_index',[0,1,2])
def test_real_nadja_comparison_on_identical_tracks(sandbox,version,protocol,path,track_index):
    from arena.engine import make_tracks
    track=make_tracks()[track_index]
    result=race(sandbox,(ROOT/path).read_text(encoding='utf-8'),protocol,track)
    record({'kind':'nadja','version':version,'track':track['name'],**result})
    assert not result['disqualified'],result['error']
    assert result['finished'], 'Nadja must finish; max-turn exhaustion is not acceptance'
    assert result['turns']>1


def test_two_line_legacy_bot_is_rejected_by_one_line_protocol_without_host_execution(sandbox):
    from arena.engine import make_tracks
    result=race(sandbox,(ROOT/'examples/starters/05_Nadja.py').read_text(), 'checkpoint-only',make_tracks()[0],max_turns=5)
    assert result['disqualified']
    assert result['error'].startswith(('timeout:','crash:'))
    record({'kind':'expected-incompatibility',**result})


@pytest.mark.parametrize('name',['boost','cautious','cornering','cruise','momentum','sprinter','starter'])
def test_checkpoint_demo_sources_use_real_single_line_sandbox(sandbox,name):
    source=(ROOT/'examples/checkpoint_only'/f'{name}.py').read_text()
    track={'id':'protocol-proof','name':'Synthetic straight track','checkpoints':[[1000,4500],[6000,4500]]}
    result=race(sandbox,source,'checkpoint-only',track,max_turns=200)
    record({'kind':'demo','example':name,**result})
    assert not result['disqualified'],result['error']
