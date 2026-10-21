"""Deterministic orchestration tests: fake engine only, no student execution."""
import json
import threading
import uuid

import pytest

from arena.store import Store
from arena.tournament import CompetitionError, Tournament, rank_results


def tracks_fn(seed=2026, count=3):
    return [{"id": f"track-{i}", "name": f"Track {i}", "checkpoints": [[1000, 1000], [8000, 4000], [1000, 8000]]} for i in range(count)]


def sandbox_ready():
    return {"available": True, "detail": "Test sandbox", "image": "pod-classroom-bot:local"}


def fake_race(entries, track, *, laps=2, max_turns=700, collisions=False, on_frame=None):
    rows = []
    for index, entry in enumerate(entries):
        invalid = entry["alias"] == "Crash"
        finished = not invalid and entry["alias"] != "DNF"
        rows.append({"id": entry["id"], "alias": entry["alias"], "place": index + 1, "finished": finished,
                     "disqualified": invalid, "error": "crash: secret-source-do-not-expose" if invalid else None,
                     "turns": 20 + index if finished else max_turns, "passed": 6 if finished else 2, "distance_to_checkpoint": 10})
    frames = [{"turn": turn, "pods": [{**row, "x": 1000 + turn, "y": 1000, "vx": 1, "vy": 0, "angle": 0, "next_checkpoint": 1, "boost_available": True, "code": entry["code"]} for row, entry in zip(rows, entries)]} for turn in range(2)]
    for frame in frames:
        if on_frame:
            on_frame(frame)
    winner = next((row["id"] for row in rows if row["finished"]), None)
    return {"id": str(uuid.uuid4()), "track": track, "laps": laps, "max_turns": max_turns, "collisions": collisions,
            "status": "finished", "winner_id": winner, "entries": entries, "frames": frames, "results": rows, "code": "private"}


@pytest.fixture
def tournament(tmp_path, monkeypatch):
    monkeypatch.setenv("POD_ADMIN_TOKEN", "test-teacher")
    return Tournament(Store(tmp_path), race_fn=fake_race, tracks_fn=tracks_fn, sandbox_fn=sandbox_ready)


def seed(tournament, names):
    tournament.start_session(7200)
    return [tournament.submit(name, "print('private source')", None) for name in names]


def join(tournament):
    tournament.worker.join(timeout=10)
    assert not tournament.worker.is_alive()
    assert tournament.store.get("job")["status"] == "finished", tournament.store.get("job")


def test_public_sandbox_cache_and_fresh_job_preflight(tournament):
    calls = []
    available = [True]

    def probe():
        calls.append(True)
        return {"available": available[0], "detail": "Test sandbox", "image": "test"}

    tournament.sandbox_fn = probe
    first = tournament.sandbox_status()
    first["detail"] = "must not change cached state"
    assert tournament.sandbox_status()["detail"] == "Test sandbox"
    assert len(calls) == 1
    seed(tournament, ["Pilot"])
    available[0] = False
    with pytest.raises(CompetitionError) as error:
        tournament.start_qualification()
    assert error.value.status == 503
    assert len(calls) == 2
    assert tournament.store.get("snapshot") is None
    assert tournament.session()["status"] == "open"


def test_common_tracks_top_five_and_immutable_versions(tournament):
    submissions = seed(tournament, [f"Pilot {i}" for i in range(6)] + ["Crash"])
    first = submissions[0]
    tournament.submit(first["alias"], "print('updated private source')", first["claim_token"])
    calls = []

    def recorder(entries, track, **kwargs):
        calls.append((entries, track, kwargs))
        return fake_race(entries, track, **kwargs)

    tournament.race_fn = recorder
    job = tournament.start_qualification()
    assert job["total"] == 21
    join(tournament)
    assert len(calls) == 21
    assert all("collisions" not in kwargs for _, _, kwargs in calls)
    for submission in submissions:
        student_calls = [(entries, track) for entries, track, _ in calls if entries[0]["id"] == submission["id"]]
        assert [track["id"] for _, track in student_calls] == ["track-0", "track-1", "track-2"]
        assert all(entries[1]["kind"] == "reference" for entries, _ in student_calls)
    snapshot = tournament.store.get("snapshot")
    assert next(entry for entry in snapshot if entry["id"] == first["id"])["version"] == 2
    with pytest.raises(CompetitionError):
        tournament.submit(first["alias"], "print('late')", first["claim_token"])
    with pytest.raises(CompetitionError):
        tournament.start_qualification()
    board = tournament.store.get("leaderboard")
    assert len(board) == 7 and board[-1]["alias"] == "Crash"
    assert board[-1]["disqualified"]
    tournament.start_final()
    join(tournament)
    assert len(calls[-1][0]) == 5
    assert "collisions" not in calls[-1][2]
    assert [entry["id"] for entry in calls[-1][0]] == [row["id"] for row in board if not row["disqualified"]][:5]
    assert tournament.store.get("snapshot") == snapshot
    assert tournament.store.get("champion")["id"] == calls[-1][0][0]["id"]
    replay = tournament.store.read_replay(tournament.store.get("active_replay_id"))
    assert len(replay["frames"]) == 2 and len(replay["entries"]) == 5
    serialized = json.dumps(replay)
    assert "private source" not in serialized and "claim_token" not in serialized and '"code"' not in serialized
    assert "secret-source-do-not-expose" not in json.dumps([tournament.store.read_replay(row["id"]) for row in tournament.store.replays()])


def test_job_lock_blocks_reset_final_and_duplicate_qualifiers(tournament):
    seed(tournament, ["A", "B"])
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return fake_race(*args, **kwargs)

    tournament.race_fn = blocked
    tournament.start_qualification()
    assert entered.wait(2)
    try:
        for action in (tournament.start_qualification, tournament.start_final, tournament.reset, lambda: tournament.start_session(7200)):
            with pytest.raises(CompetitionError) as exc:
                action()
            assert exc.value.status == 409
    finally:
        release.set()
        join(tournament)


def test_offline_docker_changes_nothing(tournament):
    seed(tournament, ["A", "B"])
    before = tournament.store.get("session")
    tournament.sandbox_fn = lambda: {"available": False, "detail": "offline", "image": "test"}
    with pytest.raises(CompetitionError) as exc:
        tournament.start_qualification()
    assert exc.value.status == 503
    assert tournament.store.get("snapshot") is None
    assert tournament.store.get("session") == before
    assert tournament.store.get("job")["status"] == "idle"
    assert tournament.worker is None


def test_final_requires_two_and_can_never_crown_dnf(tournament):
    seed(tournament, ["Only", "Crash"])
    tournament.start_qualification()
    join(tournament)
    with pytest.raises(CompetitionError) as exc:
        tournament.start_final()
    assert exc.value.status == 409
    tournament.reset()
    seed(tournament, ["A", "B"])
    tournament.start_qualification()
    join(tournament)

    def no_finish(entries, track, **kwargs):
        result = fake_race(entries, track, **kwargs)
        for row in result["results"]:
            row["finished"] = False
        # Even a buggy engine winner_id is not allowed to crown an unfinished bot.
        return result

    tournament.race_fn = no_finish
    tournament.start_final()
    join(tournament)
    assert tournament.store.get("champion") is None
    assert tournament.store.read_replay(tournament.store.get("active_replay_id"))["winner_id"] is None


def test_worker_failure_is_publicly_safe_and_retry_uses_snapshot(tournament):
    seed(tournament, ["A", "B"])

    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE TRACEBACK SECRET")

    tournament.race_fn = broken
    tournament.start_qualification()
    tournament.worker.join(5)
    assert tournament.store.get("job")["status"] == "failed"
    assert "PRIVATE" not in json.dumps(tournament.store.get("job"))
    assert tournament.store.read_replay(tournament.store.get("active_replay_id"))["status"] == "failed"
    snapshot = tournament.store.get("snapshot")
    tournament.race_fn = fake_race
    tournament.start_qualification()
    join(tournament)
    assert tournament.store.get("snapshot") == snapshot


def test_restart_recovers_running_job_and_retains_secret(tournament, monkeypatch):
    store = tournament.store
    seed(tournament, ["A"])
    replay_id = str(uuid.uuid4())
    store.add_replay(replay_id, "Test", "qualification")
    store.write_replay(replay_id, {"id": replay_id, "status": "running", "frames": []})
    store.update(job={"status": "running", "phase": "qualification", "completed": 0, "total": 3, "message": "working"}, active_replay_id=replay_id)
    monkeypatch.setenv("POD_ADMIN_TOKEN", "must-not-replace-existing")
    recovered = Store(store.directory)
    assert recovered.admin_token == "test-teacher"
    assert recovered.get("job")["status"] == "failed"
    assert recovered.read_replay(replay_id)["status"] == "interrupted"
    assert recovered.get("session")["deadline"] == store.get("session")["deadline"]
    assert len(recovered.submissions()) == 1


def test_replay_live_writes_are_throttled_and_bounds_enforced(tournament, monkeypatch):
    seed(tournament, ["A", "B"])
    writes = []
    original = tournament.store.write_replay

    def record(replay_id, replay):
        writes.append((replay_id, len(replay["frames"])))
        original(replay_id, replay)

    monkeypatch.setattr(tournament.store, "write_replay", record)
    monkeypatch.setattr("arena.tournament.time.monotonic", lambda: 1.0)
    tournament.start_qualification()
    join(tournament)
    # Initial empty + final write only; no per-turn serialization.
    assert len(writes) == 12
    assert sorted(set(count for _, count in writes)) == [0, 2]
    with pytest.raises(ValueError):
        original("../../outside", {})
    with pytest.raises(ValueError):
        original(str(uuid.uuid4()), {"x": float("nan")})


def test_rank_penalties_valid_before_invalid_and_deterministic_ties():
    snapshot = [{"id": str(uuid.uuid4()), "alias": alias} for alias in ("Zed", "Ada", "Bad", "Slow")]
    rows = {}
    for entry in snapshot:
        rows[entry["id"]] = [{"finished": True, "disqualified": entry["alias"] == "Bad", "turns": 10 if entry["alias"] != "Slow" else 50, "passed": 6, "distance_to_checkpoint": 0}] * 3
    board = rank_results(snapshot, rows)
    assert [row["alias"] for row in board] == ["Ada", "Zed", "Slow", "Bad"]
    assert board[-1]["completed_tracks"] == 0 and board[-1]["total_turns"] == 2100
    assert [row["rank"] for row in board] == [1, 2, 3, 4]


def test_real_engine_contract_with_trusted_runner_injection(tournament):
    from arena.bots import ReferenceRunner
    from arena.engine import make_tracks, run_race

    def trusted_race(entries, track, **kwargs):
        # Deliberately ignore uploaded code; inject ONLY the predefined reference policy.
        return run_race(entries, track, runner_factory=lambda entry: ReferenceRunner({**entry, "code": "racer"}), **kwargs)

    tournament.race_fn = trusted_race
    tournament.tracks_fn = make_tracks
    seed(tournament, [f"Actual physics {index}" for index in range(6)])
    tournament.start_qualification()
    join(tournament)
    board = tournament.store.get("leaderboard")
    assert len(board) == 6 and all(row["completed_tracks"] == 3 for row in board)
    tournament.start_final()
    join(tournament)
    assert tournament.store.get("champion") is not None
    replay = tournament.store.read_replay(tournament.store.get("active_replay_id"))
    assert len(replay["frames"]) > 20 and len(replay["entries"]) == 5
    assert replay["collisions"] is False
    assert len(replay["frames"]) <= 701
