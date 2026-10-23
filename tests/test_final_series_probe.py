"""Operator probes must verify aggregate winners, not the last heat winner."""
from copy import deepcopy
from uuid import uuid4

import pytest

from scripts import deployment_probe


def fixture_series():
    pilots = [{'id': str(uuid4()), 'alias': name} for name in ('A', 'B', 'C')]
    times = [[10.25, 100.25, 100.25], [20.125, 20.125, 20.125], [40.5, 40.5, 1.0]]
    tracks = [{'id': 'final-' + str(i), 'name': 'Final ' + str(i),
               'checkpoints': [[1000, 1000 + i * 1000], [9000, 8000]]} for i in range(3)]
    replays = {}
    for course in range(3):
        replay_id = str(uuid4())
        winner = min(range(3), key=lambda i: times[i][course])
        replays[replay_id] = {'id': replay_id, 'series_index': course + 1, 'series_total': 3,
                              'collisions': False, 'status': 'finished', 'track': tracks[course],
                              'entries': pilots, 'winner_id': pilots[winner]['id'],
                              'results': [{**pilot, 'finished': True, 'disqualified': False,
                                           'finish_time': times[i][course]} for i, pilot in enumerate(pilots)]}
    board = sorted([{**pilot, 'race_times': times[i], 'total_time': sum(times[i]),
                     'completed_tracks': 3, 'disqualified': False}
                    for i, pilot in enumerate(pilots)], key=lambda row: row['total_time'])
    state = {'job': {'status': 'finished', 'total': 3, 'completed': 3},
             'final_format': 'three-track-total-time-v1', 'final_tracks': tracks,
             'final_replay_ids': list(replays), 'finalists': pilots,
             'final_leaderboard': board,
             'replays': [{'id': key, 'kind': 'final'} for key in replays],
             'champion': {'id': board[0]['id'], 'alias': board[0]['alias']}}
    return state, replays


def test_probe_accepts_overall_winner_different_from_first_and_last_heat():
    state, replays = fixture_series()
    assert replays[state['final_replay_ids'][0]]['winner_id'] != state['champion']['id']
    assert replays[state['final_replay_ids'][-1]]['winner_id'] != state['champion']['id']
    result = deployment_probe.verify_final_series(state, replays.__getitem__)
    assert result['tracks'] == 3
    assert result['champion_id'] == state['champion']['id']


@pytest.mark.parametrize('corruption', ['wrong_champion', 'wrong_sum', 'duplicate_replay', 'collisions'])
def test_probe_rejects_inconsistent_final_series(corruption):
    state, replays = fixture_series()
    state = deepcopy(state)
    if corruption == 'wrong_champion':
        state['champion'] = state['finalists'][0]
    elif corruption == 'wrong_sum':
        state['final_leaderboard'][0]['total_time'] = 1.0
    elif corruption == 'duplicate_replay':
        state['final_replay_ids'][2] = state['final_replay_ids'][0]
    else:
        replays[state['final_replay_ids'][0]]['collisions'] = True
    with pytest.raises(AssertionError):
        deployment_probe.verify_final_series(state, replays.__getitem__)
