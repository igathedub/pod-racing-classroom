"""Request-local series copy; no running worker, bot execution or live data."""
from copy import deepcopy

import pytest

from arena.locale_api import localize_replay, localize_rules, localize_state, translate


@pytest.mark.parametrize(('english', 'german'), [
    ('Racing 5 finalists over three different tracks.', '5 Finalisten fahren auf drei anderen Strecken.'),
    ('Final 2 of 3 complete.', 'Finalrennen 2 von 3 abgeschlossen.'),
    ('Three-track final complete.', 'Das Drei-Strecken-Finale ist abgeschlossen.'),
    ('Three-track final complete; no bot finished all three tracks, so no champion was crowned.',
     'Das Drei-Strecken-Finale ist abgeschlossen. Kein Bot hat alle drei Strecken beendet, deshalb gibt es keinen Gesamtsieger.'),
])
def test_series_job_copy(english, german):
    assert translate(english, 'de') == german
    assert translate(english, 'en') == english


def test_new_track_names_titles_and_optional_state_fields_do_not_mutate_archives():
    names = [('Hairpin Run', 'Haarnadelkurs'), ('Diamond Loop', 'Diamantrunde'), ('Technical Loop', 'Technikrunde')]
    for index, (english, german) in enumerate(names, 1):
        replay = {'id': 'fixture', 'track': {'id': f'track-2026-{index + 2}', 'name': english},
                  'series_index': index, 'series_total': 3, 'frames': [], 'results': []}
        original = deepcopy(replay)
        assert localize_replay(replay, 'de')['track']['name'] == german
        assert replay == original
        state = {'job': {'message': 'Final 2 of 3 complete.'}, 'sandbox': {'detail': ''},
                 'leaderboard': [], 'final_format': 'three-track-total-time-v1',
                 'final_tracks': [replay['track']], 'final_replay_ids': ['fixture'],
                 'final_leaderboard': [{'id': 'pilot', 'alias': 'Hairpin Run', 'error': 'Bot disqualified.', 'race_times': [1.125, None, None]}],
                 'replays': [{'kind': 'final', 'title': f'Final {index}/3 · {english} · 5 pods'}]}
        saved = deepcopy(state)
        translated = localize_state(state, 'de')
        assert translated['replays'][0]['title'] == f'Finale {index}/3 · {german} · 5 Pods'
        assert translated['final_tracks'][0]['name'] == german
        assert translated['final_leaderboard'][0]['alias'] == 'Hairpin Run'
        assert translated['final_leaderboard'][0]['error'] == 'Der Bot wurde disqualifiziert.'
        assert translated['final_replay_ids'] == ['fixture']
        assert state == saved


def test_optional_final_scoring_rules_preserve_legacy_and_unknown_fields():
    rules = {'title': '', 'racing': '', 'qualification': '', 'ranking': '',
             'final': 'Up to five eligible snapshot bots race on three different final tracks without collisions. At least two needed. Only a bot finishing all three can become champion.',
             'physics': '', 'security': '', 'protocol': {}, 'final_tracks': 3, 'time_unit': 'simulated_turns',
             'final_scoring': 'Lowest sum of the three final race times wins. Qualification times are excluded. All three final tracks must be finished without disqualification. Ties use case-folded alias then UUID. Times are simulated turns, not wall-clock seconds.',
             'historical_extra': {'preserved': True}}
    original = deepcopy(rules)
    translated = localize_rules(rules, 'de')
    assert 'Spielzüge' in translated['final_scoring']
    assert 'Qualifikation' in translated['final_scoring']
    assert translated['final_tracks'] == 3
    assert translated['time_unit'] == 'simulated_turns'
    assert 'drei anderen Finalstrecken' in translated['final']
    assert translated['historical_extra'] == rules['historical_extra']
    assert rules == original
    del rules['final_scoring']
    assert 'final_scoring' not in localize_rules(rules, 'de')
    assert localize_state({'job': {}, 'sandbox': {'detail': ''}, 'leaderboard': [], 'replays': []}, 'de')
    assert translate('Racing 2 finalists simultaneously.', 'de') == '2 Finalisten fahren gleichzeitig.'
