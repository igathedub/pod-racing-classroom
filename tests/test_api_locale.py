"""Locale negotiation and API copy tests; source, aliases and protocol stay literal."""
import ast
from copy import deepcopy

import pytest

from arena.locale_api import localize_replay, localize_state, select_language, translate
from test_api import AUTH, TOKEN, api as base_api, open_session, submit, wait

api = base_api  # Reuse the existing isolated API fixture without a live classroom import.


@pytest.mark.parametrize("query,header,expected", [
    (None, "", "en"), ("de", "en-US", "de"), ("en", "de-DE", "en"),
    (None, "de-DE,de;q=0.9,en;q=0.8", "de"),
    (None, "de;q=0.1,en;q=0.9", "en"), (None, "fr, de;q=0.5", "de"),
    (None, "de;q=0,en;q=0.1", "en"), ("unknown", "de;q=bad,en", "en"),
])
def test_locale_selection(query, header, expected):
    assert select_language(query, header) == expected


def test_german_auth_errors_and_validation_never_echo_source(api):
    client, _ = api
    denied = client.post("/api/admin/session/start", headers={"Accept-Language": "de"}, json={})
    assert denied.status_code == 401
    assert denied.headers["content-language"] == "de"
    assert "Lehrkraft" in denied.json()["detail"]
    open_session(client)
    response = client.post("/api/submissions", headers={"Accept-Language": "de"}, json={"alias": "Test", "code": "if PRIVATE_SOURCE !!!", "claim_token": "PRIVATE_TOKEN"})
    assert response.status_code == 422
    assert "Syntaxfehler" in response.text
    assert "PRIVATE_SOURCE" not in response.text and "PRIVATE_TOKEN" not in response.text
    english = client.post("/api/submissions?lang=en", headers={"Accept-Language": "de"}, json={"alias": "Test", "code": "if !!!"})
    assert "syntax error" in english.text
    assert english.headers["content-language"] == "en"
    oversized = client.post("/api/submissions", headers={"Accept-Language": "de", "Content-Type": "application/json"}, content=b"x" * 70000)
    assert oversized.status_code == 413 and "Grenze" in oversized.json()["detail"]


def test_rules_and_starter_german_keep_programming_identifiers(api):
    client, _ = api
    en = client.get("/api/rules").json()
    response = client.get("/api/rules?lang=de")
    de = response.json()
    assert response.headers["content-language"] == "de"
    assert "Programmierkurs" in de["title"]
    assert de["protocol"]["input"] == en["protocol"]["input"]
    assert de["protocol"]["output"] == en["protocol"]["output"]
    assert de["limits"] == en["limits"]
    assert de["laps"] == en["laps"]
    source_de = client.get("/api/starter?lang=de").text
    source_en = client.get("/api/starter?lang=en").text
    assert "Lies in jedem Spielzug" in source_de
    assert ast.dump(ast.parse(source_de)) == ast.dump(ast.parse(source_en))


def test_state_and_replay_localization_never_mutates_saved_data():
    alias = "Bot process crashed."
    state = {"session": {"status": "finished"}, "job": {"phase": "final", "status": "finished", "message": "Final complete."}, "sandbox": {"detail": "Restricted Docker sandbox ready.", "available": True}, "submissions": [{"id": "literal-id", "alias": alias}], "leaderboard": [{"id": "literal-id", "alias": alias, "error": "Bot process crashed."}], "finalists": [{"id": "literal-id", "alias": alias}], "champion": {"id": "literal-id", "alias": alias}, "replays": [{"kind": "qualification", "title": alias + " · Wide Circuit", "winner_alias": alias}, {"kind": "final", "title": "Final · 5 pods"}]}
    before = deepcopy(state)
    result = localize_state(state, "de")
    assert state == before
    assert result["champion"] == before["champion"]
    assert result["submissions"] == before["submissions"]
    assert result["leaderboard"][0]["alias"] == alias
    assert result["leaderboard"][0]["error"] == "Das Bot-Programm ist abgestürzt."
    assert result["replays"][0]["title"] == alias + " · Breiter Rundkurs"
    assert result["replays"][0]["winner_alias"] == alias
    replay = {"track": {"id": "track-2026-1", "name": "Wide Circuit", "checkpoints": [[1, 2], [3, 4]]}, "winner_id": "literal-id", "entries": [{"id": "literal-id", "alias": alias}], "frames": [{"turn": 1, "pods": [{"id": "literal-id", "alias": alias, "error": "Bot process crashed.", "x": 42}]}], "results": [{"id": "literal-id", "alias": alias, "error": "Bot process crashed."}]}
    replay_before = deepcopy(replay)
    localized = localize_replay(replay, "de")
    assert replay == replay_before
    assert localized["entries"] == replay["entries"]
    assert localized["frames"][0]["pods"][0]["alias"] == alias
    assert localized["frames"][0]["pods"][0]["x"] == 42
    assert localized["track"]["name"] == "Breiter Rundkurs"


def test_german_competition_errors_and_default_english(api):
    client, _ = api
    response = client.post("/api/submissions", headers={"Accept-Language": "de"}, json={"alias": "Test", "code": "print(1)"})
    assert response.status_code == 409 and "Einreichungsphase" in response.json()["detail"]
    assert "Submissions are closed" in client.post("/api/submissions", json={"alias": "Test", "code": "print(1)"}).json()["detail"]
    assert TOKEN not in client.get("/api/state?lang=de").text
    assert "claim_token" not in client.get("/api/state?lang=de").text
    assert translate("Qualified 12 of 18 races.", "de") == "12 von 18 Qualifikationsrennen abgeschlossen."
    assert translate("Racing 5 finalists simultaneously.", "de") == "5 Finalisten fahren gleichzeitig."


def test_actual_state_locale_reads_do_not_change_champion_or_ownership(api):
    client, app = api
    open_session(client)
    first = submit(client, "Orbit").json()
    submit(client, "Vector")
    client.post("/api/admin/qualify", headers=AUTH)
    wait(app)
    client.post("/api/admin/final", headers=AUTH)
    wait(app)
    english = client.get("/api/state").json()
    german = client.get("/api/state?lang=de").json()
    assert english["champion"] == german["champion"]
    assert english["session"] == german["session"]
    assert english["submissions"] == german["submissions"]
    assert first["claim_token"] not in str(german)
    replay_id = english["active_replay_id"]
    en_replay = client.get(f"/api/replays/{replay_id}").json()
    de_replay = client.get(f"/api/replays/{replay_id}?lang=de").json()
    assert en_replay["entries"] == de_replay["entries"]
    assert en_replay["winner_id"] == de_replay["winner_id"]
