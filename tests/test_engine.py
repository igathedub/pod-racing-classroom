import json
import math

import pytest

from arena.bots import BotOutputLimit, BotTimeout, ReferenceRunner
from arena.engine import (
    Pod, advance_turn, apply_command, make_tracks, observation,
    parse_command, run_race,
)


class FakeRunner:
    def __init__(self, command="10000 0 100", error=None):
        self.command = command
        self.error = error
        self.closed = False
        self.inputs = []

    def act(self, obs, first=False):
        self.inputs.append((obs, first))
        if self.error:
            raise self.error
        return self.command

    def close(self):
        self.closed = True


def pod(**kwargs):
    return Pod("one", "One", kwargs.pop("x", 0), kwargs.pop("y", 0), **kwargs)


def entries(n=2):
    return [{"id": str(i), "alias": f"Pilot {i}", "kind": "reference", "code": "baseline"}
            for i in range(n)]


def test_tracks_are_seeded_local_and_separated():
    import random
    state = random.getstate()
    tracks = make_tracks()
    assert tracks == make_tracks()
    assert tracks != make_tracks(seed=42)
    assert random.getstate() == state
    assert len(tracks) == 3
    for track in tracks:
        points = track["checkpoints"]
        assert all(600 <= x <= 15400 and 600 <= y <= 8400 for x, y in points)
        assert all(math.dist(a, b) > 1200 for i, a in enumerate(points) for b in points[i + 1:])


def test_rotation_first_unrestricted_then_eighteen_degrees():
    p = pod()
    apply_command(p, (0, 1000, 0), first=True)
    assert p.angle == 90
    apply_command(p, (1000, 0, 0))
    assert p.angle == 72
    p.angle = 355
    apply_command(p, (10000, 0, 0))
    assert p.angle == 0


@pytest.mark.parametrize("text,expected", [
    ("1 2 999 label", (1, 2, 100)), ("1 2 -99", (1, 2, 0)),
    ("1 2 BOOST", (1, 2, "BOOST")), ("1 2 SHIELD", (1, 2, "SHIELD")),
])
def test_command_numeric_clamping_and_labels(text, expected):
    assert parse_command(text) == expected


@pytest.mark.parametrize("text", ["", "1 2", "1 2 nope", "nan 2 10", "1 2 0.5", "1 2 5\n2 3 4", "10000001 0 100"])
def test_malformed_command_rejected(text):
    from arena.bots import BotMalformed
    with pytest.raises(BotMalformed):
        parse_command(text)


def test_boost_only_once():
    p = pod()
    apply_command(p, (1000, 0, "BOOST"), first=True)
    assert p.vx == 650 and not p.boost_available
    apply_command(p, (1000, 0, "BOOST"))
    assert p.vx == 750


def test_shield_compatibility_duration_and_no_boost_consumption():
    p = pod()
    apply_command(p, (10000, 0, "SHIELD"))
    assert p.shield_turns == 3
    for expected in (2, 1, 0):
        apply_command(p, (10000, 0, "BOOST"))
        assert p.vx == 0 and p.boost_available
        advance_turn([p], [[-10000, 0], [10000, 0]])
        assert p.shield_turns == expected
    apply_command(p, (10000, 0, "BOOST"))
    assert p.vx == 650


def test_swept_checkpoint_not_just_endpoint():
    p = pod(vx=3000)
    advance_turn([p], [[-5000, 0], [1000, 0], [9000, 0]])
    assert p.x == 3000
    assert abs(p.x - 1000) > 600
    assert p.passed == 1 and p.next_checkpoint == 2
    assert p.vx == 2550


def test_multiple_checkpoints_in_one_turn():
    p = pod(vx=3000)
    advance_turn([p], [[-5000, 0], [1000, 0], [2400, 0]])
    assert p.passed == 2 and p.next_checkpoint == 0


def test_rounding_and_friction_truncate_toward_zero():
    p = pod(x=0.5, y=-0.5, vx=0, vy=0)
    advance_turn([p], [[5000, 0], [10000, 0]])
    assert p.x == 1 and p.y == -1
    p.vx, p.vy = 10.9, -10.9
    advance_turn([p], [[5000, 0], [10000, 0]])
    assert p.vx == 9 and p.vy == -9


def test_other_pod_does_not_prevent_checkpoint_crossing():
    a = pod(vx=1000)
    b = Pod("two", "Two", 1500, 0, next_checkpoint=0)
    advance_turn([a, b], [[-10000, 0], [1500, 0], [4000, 0]])
    assert a.passed == 1 and a.x == 1000
    assert b.x == 1500
    assert a.vx == 850 and b.vx == 0


def test_checkpoint_is_counted_despite_nearby_pod():
    a = pod(vx=1000)
    b = Pod("two", "Two", 1500, 0, next_checkpoint=0)
    advance_turn([a, b], [[-10000, 0], [1000, 0], [4000, 0]])
    assert a.passed == 1 and a.x == 1000


def test_head_on_pods_keep_their_own_velocity():
    a, b = pod(vx=500), Pod("two", "Two", 1600, 0, vx=-500)
    advance_turn([a, b], [[-10000, 0], [10000, 0]])
    assert (a.x, b.x, a.vx, b.vx) == (500, 1100, 425, -425)


def test_shield_does_not_transfer_impulse_to_another_pod():
    a = pod(vx=50, shield_turns=3)
    b = Pod("two", "Two", 800, 0, vx=-50)
    advance_turn([a, b], [[-10000, 0], [10000, 0]])
    assert (a.x, b.x, a.vx, b.vx) == (50, 750, 42, -42)
    assert a.shield_turns == 2


def test_degenerate_overlaps_finite_and_no_zero_time_loop():
    pods = [Pod(str(i), str(i), 0, 0, vx=i * 25) for i in range(5)]
    advance_turn(pods, [[0, 0], [0, 0]], laps=2)
    assert all(p.finished and p.passed == 4 for p in pods)
    assert all(math.isfinite(p.x) and math.isfinite(p.vx) for p in pods)


def test_finish_time_is_fractional_and_counts_two_laps():
    p = pod(x=0, vx=1000, passed=3, next_checkpoint=0)
    advance_turn([p], [[1000, 0], [6000, 0]], laps=2, turn=5)
    assert p.finished and p.passed == 4 and p.turns == 5
    assert p.finish_time == pytest.approx(4.4)
    assert p.x == 400


def test_beginner_observation_nearest_opponent_and_two_lines():
    a = pod(x=100, y=100)
    b = Pod("two", "Two", 5000, 0)
    c = Pod("three", "Three", 200, 100)
    text = observation(a, [a, b, c], [[0, 0], [1100, 100]])
    assert text == "100 100 1100 100 1000 0\n200 100\n"


def test_replay_determinism_real_trusted_policies_and_finite_records():
    first = run_race(entries(5), make_tracks()[0])
    second = run_race(entries(5), make_tracks()[0])
    assert first["collisions"] is False
    first.pop("id")
    second.pop("id")
    assert first == second
    assert len(first["frames"]) <= 701
    assert first["winner_id"] is not None
    assert all(result["finished"] for result in first["results"])
    json.dumps(first, allow_nan=False)


@pytest.mark.parametrize("track", make_tracks())
def test_baseline_finishes_all_qualification_tracks_within_limit(track):
    replay = run_race(entries(), track)
    assert all(result["finished"] and not result["disqualified"] for result in replay["results"])
    assert replay["winner_id"] in {"0", "1"}


def test_invalid_bot_dq_and_cleanup_while_good_bot_continues():
    good = ReferenceRunner({"code": "baseline"})
    bad = FakeRunner("not an action")
    closed = []
    original_close = good.close
    good.close = lambda: (closed.append(True), original_close())
    replay = run_race(entries(), make_tracks()[0],
                      runner_factory=lambda e: good if e["id"] == "0" else bad)
    assert replay["winner_id"] == "0"
    assert replay["results"][0]["finished"]
    assert replay["results"][1]["disqualified"]
    assert replay["results"][1]["error"].startswith("malformed:")
    assert bad.closed and closed
    assert bad.inputs[0][1] is True


@pytest.mark.parametrize("error,prefix", [(BotTimeout("deadline"), "timeout:"),
                                          (BotOutputLimit("cap"), "output_limit:")])
def test_failure_classification(error, prefix):
    runner = FakeRunner(error=error)
    replay = run_race(entries(1), make_tracks()[0], runner_factory=lambda _: runner)
    assert replay["results"][0]["error"].startswith(prefix)
    assert runner.closed
    assert replay["winner_id"] is None


def test_callback_exception_always_closes_every_runner():
    runners = [FakeRunner(), FakeRunner()]
    def callback(frame):
        raise RuntimeError("stop replay storage")
    with pytest.raises(RuntimeError, match="stop replay storage"):
        run_race(entries(), make_tracks()[0], runner_factory=lambda e: runners[int(e["id"])],
                 on_frame=callback)
    assert all(runner.closed for runner in runners)


def test_startup_error_does_not_leak_arbitrary_exception_or_abort_others():
    def factory(entry):
        if entry["id"] == "1":
            raise RuntimeError("host secret must not be public")
        return ReferenceRunner(entry)
    replay = run_race(entries(), make_tracks()[0], runner_factory=factory)
    assert replay["results"][1]["error"] == "crash: Bot runner failed"
    assert replay["winner_id"] == "0"


def test_dnf_never_wins_and_progress_ranked_before_dq():
    replay = run_race(entries(), make_tracks()[0], max_turns=2,
                      runner_factory=lambda e: FakeRunner("bad" if e["id"] == "0" else "13000 2000 100"))
    assert replay["winner_id"] is None
    assert replay["results"][0]["id"] == "1"
    assert not replay["results"][0]["finished"]


def test_same_turn_finish_order_by_continuous_finish_time():
    # A deliberately short course: two different starts/commands finish on the
    # same discrete turn, yet their fractional finish times decide placement.
    p1 = Pod("slow", "Slow", 0, 0, vx=1000, passed=1, next_checkpoint=0)
    p2 = Pod("fast", "Fast", 0, 100, vx=1500, passed=1, next_checkpoint=0)
    advance_turn([p1, p2], [[1000, 0], [6000, 0]], laps=1)
    assert p1.turns == p2.turns == 1
    assert p2.finish_time < p1.finish_time


@pytest.mark.parametrize("track", [
    {"checkpoints": [[0, 0]]}, {"checkpoints": [[0, 0], [float("nan"), 0]]},
    {"checkpoints": [[0, 0], [float("inf"), 0]]},
])
def test_invalid_track_rejected_before_runners_created(track):
    with pytest.raises(ValueError):
        run_race(entries(), track, runner_factory=lambda _: pytest.fail("runner should not start"))
