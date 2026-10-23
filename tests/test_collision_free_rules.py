"""Public rules must describe the same collision-free game in both protocols."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_base_path import prefixed


@pytest.mark.parametrize('protocol', ['legacy', 'checkpoint-only'])
@pytest.mark.parametrize('language', ['en', 'de'])
def test_public_rules_describe_collision_free_races_with_compatible_commands(tmp_path, monkeypatch, protocol, language):
    app = prefixed(tmp_path, monkeypatch, POD_INPUT_PROTOCOL=protocol)
    with TestClient(app) as client:
        response = client.get('/backup/api/rules?lang=' + language)
        assert response.status_code == 200
        rules = response.json()
        assert ('without collisions' if language == 'en' else 'ohne Kollisionen') in rules['final']
        assert rules['racing'] == (
            'Practice, qualification and final all run without collisions. Pods pass through each other.'
            if language == 'en' else
            'Testläufe, Qualifikation und Finale laufen immer ohne Kollisionen. Pods fahren durcheinander hindurch.')
        assert 'BOOST' in rules['protocol']['thrust'] and 'SHIELD' in rules['protocol']['thrust']
        assert len(rules['protocol']['input']) == (1 if protocol == 'checkpoint-only' else 2)
        assert rules['protocol']['output'] == 'target_x target_y thrust'
        assert rules['laps'] == 2 and rules['max_turns'] == 700
        assert '650' in rules['physics'] and '0.85' in rules['physics'].replace('0,85', '0.85')
        assert ('no collision effect' if language == 'en' else 'keine Kollisionswirkung') in rules['physics']


def test_documented_contract_has_no_collision_option_and_preserves_historical_evidence():
    root = Path(__file__).resolve().parents[1]
    for filename, rule, obsolete in (
        ('README.md', 'Practice, qualification and final all run without collisions.', 'collisions enabled'),
        ('README.de.md', 'Testläufe, Qualifikation und Finale laufen immer ohne Kollisionen.', 'gemeinsam mit Kollisionen'),
    ):
        text = (root / filename).read_text()
        assert rule in text
        assert obsolete not in text
    spec = (root / 'SPEC.md').read_text()
    for name in ('run_race', 'advance_turn'):
        signature = re.search(r'`' + name + r'\([^`]+`', spec)
        assert signature, name
        assert 'collisions' not in signature.group()
    assert '`collisions:false`' in spec
    assert 'collisionsTrue' not in spec
    verification = (root / 'VERIFICATION.md').read_text()
    assert 'Historical verification only' in verification
    assert 'not evidence for the collision-free release' in verification
