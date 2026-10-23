"""Opt-in input framing, configuration, and race-level protocol stability."""
import pytest

from arena.engine import Pod, observation, run_race, make_tracks


def test_checkpoint_only_observation_is_one_signed_six_integer_line():
    pod = Pod("one", "One", -100, -200, angle=0)
    opponent = Pod("two", "Two", 50, 60)
    text = observation(pod, [pod, opponent], [[0, 0], [-400, -600]],
                       input_protocol="checkpoint-only")
    assert text == "-100 -200 -400 -600 500 -127\n"
    assert len(text.splitlines()) == 1
    assert len([int(field) for field in text.split()]) == 6


@pytest.mark.parametrize("ambient,value,expected", [
    (None, None, "legacy"),
    ("legacy", None, "legacy"),
    ("checkpoint-only", None, "checkpoint-only"),
    ("checkpoint-only", "legacy", "legacy"),
    ("invalid", "checkpoint-only", "checkpoint-only"),
    ("", "legacy", "legacy"),
])
def test_configured_protocol_defaults_and_explicit_overrides(monkeypatch, tmp_path,
                                                           ambient, value, expected):
    from arena.protocol import configured_input_protocol

    monkeypatch.delenv("POD_INPUT_PROTOCOL", raising=False)
    if ambient is not None:
        monkeypatch.setenv("POD_INPUT_PROTOCOL", ambient)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POD_DATA_DIR", str(tmp_path / "must-not-be-created"))
    assert configured_input_protocol(value) == expected
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("ambient,invalid", [
    (ambient, invalid)
    for invalid in ("", " ", "checkpoint_only", "LEGACY", "legacy\n", 0, False, [], {})
    for ambient in (False, True) if not ambient or isinstance(invalid, str)
])
def test_configured_protocol_rejects_invalid_values(monkeypatch, tmp_path, invalid, ambient):
    from arena.protocol import configured_input_protocol

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POD_DATA_DIR", str(tmp_path / "must-not-be-created"))
    if ambient:
        monkeypatch.setenv("POD_INPUT_PROTOCOL", invalid)
        value = None
    else:
        monkeypatch.setenv("POD_INPUT_PROTOCOL", "legacy")
        value = invalid
    with pytest.raises(ValueError, match="POD_INPUT_PROTOCOL"):
        configured_input_protocol(value)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("ambient,explicit,expected", [
    (None, None, "-100 -200 -400 -600 500 -127\n50 60\n"),
    ("checkpoint-only", None, "-100 -200 -400 -600 500 -127\n"),
    ("checkpoint-only", "legacy", "-100 -200 -400 -600 500 -127\n50 60\n"),
    ("invalid", "legacy", "-100 -200 -400 -600 500 -127\n50 60\n"),
])
def test_observation_uses_configured_protocol(monkeypatch, ambient, explicit, expected):
    monkeypatch.delenv("POD_INPUT_PROTOCOL", raising=False)
    if ambient is not None:
        monkeypatch.setenv("POD_INPUT_PROTOCOL", ambient)
    pod = Pod("one", "One", -100, -200)
    opponent = Pod("two", "Two", 50, 60)
    assert observation(pod, [pod, opponent], [[0, 0], [-400, -600]],
                       input_protocol=explicit) == expected


@pytest.mark.parametrize("ambient,explicit", [("", None), ("invalid", None), ("legacy", "")])
def test_observation_rejects_invalid_protocol(monkeypatch, ambient, explicit):
    monkeypatch.setenv("POD_INPUT_PROTOCOL", ambient)
    pod = Pod("one", "One", 0, 0)
    with pytest.raises(ValueError, match="POD_INPUT_PROTOCOL"):
        observation(pod, [pod], [[0, 0], [1000, 0]], input_protocol=explicit)


@pytest.mark.parametrize("ambient,explicit", [
    ("", None), ("invalid", None), ("legacy", ""), ("legacy", "typo"),
    ("legacy", False), ("legacy", []),
])
def test_invalid_race_protocol_fails_before_any_runner(monkeypatch, ambient, explicit):
    monkeypatch.setenv("POD_INPUT_PROTOCOL", ambient)
    created = []

    def factory(entry):
        created.append(entry)
        pytest.fail("Invalid protocol must not create any runner")

    with pytest.raises(ValueError, match="POD_INPUT_PROTOCOL"):
        run_race(_entries(), make_tracks()[0], runner_factory=factory,
                 input_protocol=explicit)
    assert created == []


def _entries():
    return [{"id": "one", "alias": "One", "kind": "reference", "code": "baseline"}]


class FramingRunner:
    def __init__(self, line_count):
        self.line_count = line_count
        self.inputs = []
        self.closed = False

    def act(self, text, first=False):
        self.inputs.append((text, first))
        assert text.endswith("\n")
        assert len(text.splitlines()) == self.line_count
        x, y, cx, cy, distance, angle = map(int, text.splitlines()[0].split())
        return f"{cx} {cy} 0"

    def close(self):
        self.closed = True


@pytest.mark.parametrize("ambient,explicit,expected", [
    (None, None, "legacy"),
    ("checkpoint-only", None, "checkpoint-only"),
    ("legacy", "checkpoint-only", "checkpoint-only"),
    ("checkpoint-only", "legacy", "legacy"),
    ("invalid", "checkpoint-only", "checkpoint-only"),
])
def test_race_freezes_protocol_before_startup_for_every_frame(monkeypatch, ambient, explicit, expected):
    monkeypatch.delenv("POD_INPUT_PROTOCOL", raising=False)
    if ambient is not None:
        monkeypatch.setenv("POD_INPUT_PROTOCOL", ambient)
    runner = FramingRunner(1 if expected == "checkpoint-only" else 2)

    def factory(entry):
        monkeypatch.setenv("POD_INPUT_PROTOCOL", "legacy" if expected == "checkpoint-only" else "checkpoint-only")
        return runner

    def callback(frame):
        monkeypatch.setenv("POD_INPUT_PROTOCOL", "invalid-during-race")

    replay = run_race(_entries(), make_tracks()[0], max_turns=4,
                      runner_factory=factory, on_frame=callback, input_protocol=explicit)
    assert replay["input_protocol"] == expected
    assert not replay["results"][0]["disqualified"]
    assert runner.closed
    assert len(runner.inputs) == len(replay["frames"]) - 1 == 4
    assert [first for _, first in runner.inputs] == [True, False, False, False]
    for (text, _), frame in zip(runner.inputs, replay["frames"]):
        state = frame["pods"][0]
        pod = Pod(state["id"], state["alias"], state["x"], state["y"],
                  angle=state["angle"], next_checkpoint=state["next_checkpoint"])
        assert text == observation(pod, [pod], replay["track"]["checkpoints"],
                                   input_protocol=expected)


@pytest.mark.parametrize("track", make_tracks(), ids=lambda track: track["id"])
@pytest.mark.parametrize("source", ["explicit", "environment"])
def test_builtin_reference_finishes_all_tracks_in_checkpoint_only(monkeypatch, track, source):
    monkeypatch.setenv("POD_INPUT_PROTOCOL", "checkpoint-only" if source == "environment" else "legacy")
    if source == "explicit":
        replay = run_race(_entries(), track, input_protocol="checkpoint-only")
    else:
        replay = run_race(_entries(), track)
    assert replay["input_protocol"] == "checkpoint-only"
    assert replay["winner_id"] == "one"
    assert all(row["finished"] and not row["disqualified"] for row in replay["results"])

    legacy = run_race(_entries(), track, input_protocol="legacy")
    assert legacy["input_protocol"] == "legacy"
    for result in (replay, legacy):
        result.pop("id")
        result.pop("input_protocol")
    assert replay == legacy
