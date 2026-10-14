"""HTTP hardening without exposing credentials or changing live classroom data."""
import pytest
from fastapi.testclient import TestClient
from test_api import AUTH, CODE, TOKEN, create_app, open_session
from test_tournament import fake_race, sandbox_ready, tracks_fn
from test_api import api as api


@pytest.mark.parametrize("path", ["/", "/teacher", "/projector", "/assets/app.js", "/api/state", "/api/replays/missing"])
def test_responses_include_security_headers(api, path):
    client, _ = api
    response = client.get(path)
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "no-referrer"
    policy = response.headers.get("content-security-policy", "")
    assert "script-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    assert response.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"


def test_classroom_and_secret_api_responses_are_not_cacheable(api):
    client, _ = api
    assert client.get("/api/state").headers.get("cache-control") == "no-store"
    assert client.get("/api/admin/submissions/missing").headers.get("cache-control") == "no-store"


@pytest.mark.parametrize("origin", ["https://attacker.example", "http://testserver.attacker.example", "null"])
def test_cross_origin_admin_mutations_are_rejected_before_state_changes(api, origin):
    client, app = api
    before = app.state.store.get("session")
    response = client.post("/api/admin/session/start?lang=de", headers={**AUTH, "Origin": origin},
                           json={"duration_seconds": 7200})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-language"] == "de"
    assert app.state.store.get("session") == before


def test_configured_https_origin_works_behind_http_tunnel(tmp_path, monkeypatch):
    monkeypatch.setenv("POD_PUBLIC_ORIGINS", "https://codeweek-wi.de")
    with TestClient(create_app(tmp_path / "data")) as client:
        response = client.post("/api/admin/session/start", json={"duration_seconds": 7200},
                               headers={"Origin": "https://codeweek-wi.de", "X-Admin-Token": client.app.state.store.admin_token})
        assert response.status_code == 200


@pytest.mark.parametrize("value", ["*", "https://example.com/path", "https://user@example.com", "null"])
def test_invalid_public_origin_config_fails_before_creating_data(tmp_path, monkeypatch, value):
    monkeypatch.setenv("POD_PUBLIC_ORIGINS", value)
    with pytest.raises(ValueError, match="POD_PUBLIC_ORIGINS"):
        create_app(tmp_path / "data")
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("headers", [{"Sec-Fetch-Site": "cross-site"}, {"Referer": "https://attacker.example/page"}])
def test_browser_cross_site_mutations_without_origin_are_denied(api, headers):
    client, app = api
    response = client.post("/api/admin/session/start", json={"duration_seconds": 7200}, headers={**AUTH, **headers})
    assert response.status_code == 403
    assert app.state.store.get("session")["status"] == "waiting"


@pytest.mark.parametrize("headers", [{"Origin": "http://testserver"}, {"Referer": "http://testserver/teacher"}, {}])
def test_same_origin_browser_and_machine_clients_remain_compatible(api, headers):
    client, _ = api
    assert client.post("/api/admin/session/start", json={"duration_seconds": 7200}, headers={**AUTH, **headers}).status_code == 200


def test_configured_host_allowlist_rejects_unknown_hosts(tmp_path, monkeypatch):
    monkeypatch.setenv("POD_ALLOWED_HOSTS", "codeweek-wi.de,127.0.0.1,testserver")
    monkeypatch.setenv("POD_ADMIN_TOKEN", TOKEN)
    with TestClient(create_app(tmp_path / "data", sandbox_fn=sandbox_ready)) as client:
        assert client.get("/api/state", headers={"Host": "attacker.example"}).status_code == 400
        assert client.get("/api/state", headers={"Host": "127.0.0.1:8765"}).status_code == 200
        assert client.get("/api/state", headers={"Host": "codeweek-wi.de"}).status_code == 200


@pytest.mark.parametrize("value", ["*", "https://codeweek-wi.de", "codeweek-wi.de:443", "example..com"])
def test_invalid_allowed_hosts_config_fails_before_data_creation(tmp_path, monkeypatch, value):
    monkeypatch.setenv("POD_ALLOWED_HOSTS", value)
    with pytest.raises(ValueError, match="POD_ALLOWED_HOSTS"):
        create_app(tmp_path / "data")
    assert not (tmp_path / "data").exists()


def test_submission_budget_stops_burst_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("POD_ADMIN_TOKEN", TOKEN)
    monkeypatch.setenv("POD_SUBMISSIONS_PER_MINUTE", "2")
    app = create_app(tmp_path / "data", sandbox_fn=sandbox_ready)
    with TestClient(app) as client:
        open_session(client)
        for alias in ("First", "Second"):
            assert client.post("/api/submissions", json={"alias": alias, "code": CODE}).status_code == 200
        response = client.post("/api/submissions?lang=de", json={"alias": "Blocked", "code": CODE},
                               headers={"X-Forwarded-For": "203.0.113.1", "CF-Connecting-IP": "203.0.113.2"})
        assert response.status_code == 429
        assert 1 <= int(response.headers["retry-after"]) <= 60
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-language"] == "de"
        assert len(app.state.store.submissions()) == 2
        assert client.get("/api/state").status_code == 200
        assert client.post("/api/admin/session/close", headers=AUTH).status_code == 200


def test_practice_budget_stops_burst_before_race_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("POD_ADMIN_TOKEN", TOKEN)
    monkeypatch.setenv("POD_PRACTICE_PER_MINUTE", "2")
    calls = []

    def counted_race(entries, track, **kwargs):
        calls.append(entries[0]["id"])
        return fake_race(entries, track, **kwargs)

    app = create_app(tmp_path / "data", race_fn=counted_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)
    with TestClient(app) as client:
        open_session(client)
        entry = client.post("/api/submissions", json={"alias": "Pilot", "code": CODE}).json()
        for _ in range(2):
            assert client.post("/api/practice", json={"alias": "Pilot", "claim_token": entry["claim_token"]}).status_code == 200
        response = client.post("/api/practice", json={"alias": "Pilot", "claim_token": entry["claim_token"]})
        assert response.status_code == 429
        assert len(calls) == 2
        assert app.state.store.replays() == []


@pytest.mark.parametrize("value", ["0", "-1", "nan", "10001"])
def test_invalid_request_budget_config_fails_closed(tmp_path, monkeypatch, value):
    monkeypatch.setenv("POD_SUBMISSIONS_PER_MINUTE", value)
    with pytest.raises(ValueError, match="POD_SUBMISSIONS_PER_MINUTE"):
        create_app(tmp_path / "data")
    assert not (tmp_path / "data").exists()
