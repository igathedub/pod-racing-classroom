"""Deterministic expiry, concurrency and classroom fairness checks."""
from concurrent.futures import ThreadPoolExecutor
from test_api import AUTH, CODE, open_session
from test_api import api as api
from arena.http_security import RequestBudget


def test_request_budget_reopens_after_window_and_keeps_categories_separate():
    clock = [10.0]
    budget = RequestBudget({"/api/submissions": 1, "/api/practice": 1}, clock=lambda: clock[0])
    assert budget.retry_after("/api/submissions") == 0
    assert budget.retry_after("/api/submissions") == 60
    assert budget.retry_after("/api/practice") == 0
    clock[0] = 70.0
    assert budget.retry_after("/api/submissions") == 0
    assert budget.retry_after("/api/state") == 0
    assert len(budget.windows) == 2


def test_concurrent_requests_cannot_exceed_shared_budget():
    budget = RequestBudget({"/api/submissions": 5}, clock=lambda: 0.0)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: budget.retry_after("/api/submissions"), range(40)))
    assert results.count(0) == 5
    assert results.count(60) == 35


def test_twenty_students_sharing_one_client_address_can_submit(api):
    client, _ = api
    open_session(client)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda index: client.post("/api/submissions", json={"alias": f"Pilot {index}", "code": CODE}), range(20)))
    assert all(response.status_code == 200 for response in results)


def test_forwarded_headers_do_not_authorize_an_untrusted_origin(api):
    client, app = api
    response = client.post("/api/admin/session/start", json={"duration_seconds": 7200},
                           headers={**AUTH, "Origin": "https://attacker.example",
                                    "X-Forwarded-Host": "attacker.example", "X-Forwarded-Proto": "https",
                                    "Forwarded": 'host=attacker.example;proto=https'})
    assert response.status_code == 403
    assert app.state.store.get("session")["status"] == "waiting"
