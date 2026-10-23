"""Pod contact must never change a classroom bot's trajectory."""
from copy import deepcopy
from dataclasses import asdict
from inspect import signature

import pytest

from arena.engine import Pod, advance_turn, make_tracks, run_race


@pytest.mark.parametrize('protocol', ['legacy', 'checkpoint-only'])
def test_new_races_cannot_enable_collisions_and_report_the_rule(protocol):
    assert 'collisions' not in signature(run_race).parameters
    assert 'collisions' not in signature(advance_turn).parameters
    entries = [{'id': str(i), 'alias': str(i), 'kind': 'reference', 'code': 'baseline'}
               for i in range(5)]
    replay = run_race(entries, make_tracks()[0], input_protocol=protocol)
    assert replay['collisions'] is False
    assert replay['input_protocol'] == protocol
    assert all(row['finished'] and not row['disqualified'] for row in replay['results'])


@pytest.mark.parametrize('initial', [
    [Pod('a', 'A', 0, 0, vx=1000), Pod('b', 'B', 1500, 0, next_checkpoint=0)],
    [Pod('a', 'A', 0, 0, vx=500), Pod('b', 'B', 500, 0, vx=-500)],
    [Pod('a', 'A', 0, 0, vx=0.49999999999999994),
     Pod('b', 'B', 898, 0, vx=3)],  # Another pod's checkpoint must not perturb rounding.
    [Pod(str(i), str(i), -500 + 250 * i, 0, vx=1000 - 500 * i,
         shield_turns=3 if i == 0 else 0) for i in range(5)],
])
def test_other_pods_cannot_change_trajectory_or_checkpoint_progress(initial):
    checkpoints = [[-10000, 0], [1500, 0], [4000, 0]]
    together = deepcopy(initial)
    isolated = deepcopy(initial)
    for turn in range(1, 5):
        advance_turn(together, checkpoints, turn=turn)
        for individual in isolated:
            advance_turn([individual], checkpoints, turn=turn)
        assert [asdict(pod) for pod in together] == [asdict(pod) for pod in isolated]
