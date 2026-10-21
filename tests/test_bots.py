from io import BytesIO
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from arena import bots
from arena.bots import (
    BotCrash, BotMalformed, BotOutputLimit, BotTimeout, DockerRunner,
    ReferenceRunner, SandboxUnavailable, container_command, make_runner, sandbox_status,
)
from arena.engine import make_tracks, parse_command, run_race

ROOT = Path(__file__).resolve().parents[1]
OBSERVATION = "2000 2000 13000 2000 11000 0\n2000 2850\n"
LOOP_CODE = """while True:
    try:
        x, y, cx, cy, distance, angle = map(int, input().split())
        ox, oy = map(int, input().split())
    except EOFError:
        break
    print(cx, cy, 100, flush=True)
"""


def raw_runner():
    runner = DockerRunner.__new__(DockerRunner)
    runner._failure = None
    runner._failure_lock = threading.Lock()
    runner._lines = queue.Queue(maxsize=32)
    runner._closed = False
    return runner


def test_container_has_all_restrictions_and_no_shell_or_mount():
    command = container_command("pod-bot-fixed")
    assert command[:2] == ["docker", "run"]
    for flag in ("--network=none", "--read-only", "--cap-drop=ALL", "--user=65534:65534",
                 "--pids-limit=32", "--memory=64m", "--memory-swap=64m", "--cpus=0.5",
                 "--security-opt=no-new-privileges:true", "--pull=never", "--log-driver=none"):
        assert flag in command
    assert not any(value in command for value in ("sh", "bash", "-c", "--volume", "-v", "--mount"))
    assert command[-1] == bots.IMAGE
    assert bots.STARTUP_TIMEOUT >= 10


def test_status_checks_daemon_and_image_without_build_or_pull(monkeypatch):
    calls = []
    monkeypatch.setattr(bots.shutil, "which", lambda _: "docker")
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=b"exists", stderr=b"")
    monkeypatch.setattr(bots.subprocess, "run", run)
    assert sandbox_status()["available"]
    assert len(calls) == 2
    assert calls[0][1] == "version" and calls[1][1:3] == ["image", "inspect"]


@pytest.mark.parametrize("failure", ["missing", "daemon", "image", "timeout"])
def test_status_fail_closed(monkeypatch, failure):
    monkeypatch.setattr(bots.shutil, "which", lambda _: None if failure == "missing" else "docker")
    def run(command, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 5)
        failed = failure == "daemon" or (failure == "image" and command[1] == "image")
        return SimpleNamespace(returncode=int(failed), stdout=b"exists", stderr=b"private host info")
    monkeypatch.setattr(bots.subprocess, "run", run)
    state = sandbox_status()
    assert not state["available"] and state["image"] == bots.IMAGE
    assert "private host info" not in state["detail"]


def test_student_factory_never_falls_back_to_reference(monkeypatch):
    monkeypatch.setattr(bots, "DockerRunner", lambda _: (_ for _ in ()).throw(SandboxUnavailable("off")))
    with pytest.raises(SandboxUnavailable):
        make_runner({"code": "print('do not execute on host')"})
    assert isinstance(make_runner({"kind": "reference", "code": "baseline"}), ReferenceRunner)


def test_reference_runner_only_fixed_policy_not_exec():
    runner = ReferenceRunner({"code": "raise RuntimeError('must not execute')"})
    assert parse_command(runner.act(OBSERVATION)) == (13000, 2000, "BOOST")


@pytest.mark.parametrize("code", [None, 1, "x" * 32769, "\U0001f680" * 8193],
                         ids=["null", "integer", "oversize-ascii", "oversize-unicode"])
def test_source_limit_before_process_start(monkeypatch, code):
    monkeypatch.setattr(bots.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not create process"))
    with pytest.raises(BotMalformed):
        DockerRunner({"code": code})


@pytest.mark.parametrize("payload,stdout,error", [
    (b"x" * 1025, True, BotOutputLimit),
    (b"x" * 1025 + b"\n", True, BotOutputLimit),
    (b"1 2 3\n" * 33, True, BotOutputLimit),
    (b"\xff\n", True, BotMalformed),
    (b"x" * (65536 + 1), False, BotOutputLimit),
], ids=["long-partial", "long-line", "unsolicited", "invalid-utf8", "stderr-cap"])
def test_output_draining_is_bounded(payload, stdout, error):
    runner = raw_runner()
    runner._drain(BytesIO(payload), stdout)
    assert isinstance(runner._failure, error)


def test_total_stdout_cap_independent_of_line_limit(monkeypatch):
    monkeypatch.setattr(bots, "MAX_STDOUT_BYTES", 20)
    runner = raw_runner()
    runner._drain(BytesIO(b"1 2 3\n" * 4), True)
    assert isinstance(runner._failure, BotOutputLimit)


def test_unbuffered_read_deadline():
    runner = raw_runner()
    start = time.monotonic()
    with pytest.raises(BotTimeout):
        runner._read(0.04)
    assert time.monotonic() - start < 0.5


def test_unexpected_eof_is_crash():
    runner = raw_runner()
    runner._drain(BytesIO(b""), True)
    with pytest.raises(BotCrash):
        runner._read(0.1)


def test_examples_are_seven_distinct_valid_python_sources():
    import ast
    files = sorted((ROOT / "examples").glob("*.py"))
    assert len(files) == 7
    sources = [file.read_text(encoding="utf-8") for file in files]
    assert len(set(sources)) == 7
    for source in sources:
        ast.parse(source)
        assert "flush=True" in source


@pytest.fixture
def docker_ready():
    state = sandbox_status()
    if not state["available"]:
        pytest.skip(state["detail"])


def assert_removed(name):
    result = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10)
    assert result.returncode != 0, f"Sandbox container leaked: {name}"


@pytest.mark.docker
def test_docker_real_python_loop_and_restrictions(docker_ready):
    runner = DockerRunner({"code": LOOP_CODE})
    try:
        details = json.loads(subprocess.run(["docker", "inspect", runner.name],
                             capture_output=True, timeout=10, check=True).stdout)[0]
        config = details["HostConfig"]
        assert config["NetworkMode"] == "none"
        assert config["ReadonlyRootfs"]
        assert config["CapDrop"] == ["ALL"]
        assert config["PidsLimit"] == 32
        assert config["Memory"] == 64 * 1024 * 1024
        assert config["NanoCpus"] == 500000000
        assert config["LogConfig"]["Type"] == "none"
        assert details["Config"]["User"] == "65534:65534"
        assert not config.get("Binds")
        assert all(mount["Type"] != "bind" for mount in details.get("Mounts", []))
        for turn in range(3):
            assert runner.act(OBSERVATION, first=turn == 0) == "13000 2000 100"
    finally:
        runner.close()
    assert_removed(runner.name)


@pytest.mark.docker
@pytest.mark.parametrize("source,error", [
    ("while True: pass", BotTimeout),
    ("raise RuntimeError('private bot traceback')", BotCrash),
    ("import sys\nwhile True: sys.stdout.write('x' * 4096); sys.stdout.flush()", BotOutputLimit),
    ("import sys\nwhile True: sys.stderr.write('x' * 4096); sys.stderr.flush()", BotOutputLimit),
])
def test_docker_bad_bots_deadlines_caps_and_cleanup(docker_ready, source, error):
    runner = None
    start = time.monotonic()
    try:
        with pytest.raises(error):
            runner = DockerRunner({"code": source}, first_turn_timeout=0.4)
            runner.act(OBSERVATION, first=True)
    finally:
        if runner:
            runner.close()
            assert_removed(runner.name)
    assert time.monotonic() - start < 25


@pytest.mark.docker
def test_docker_malformed_command_disqualified_and_container_removed(docker_ready):
    created = []
    source = "while True:\n    input()\n    input()\n    print('bad action', flush=True)\n"
    def factory(entry):
        runner = DockerRunner(entry)
        created.append(runner.name)
        return runner
    replay = run_race([{"id": "bad", "alias": "Bad", "code": source}], make_tracks()[0],
                      runner_factory=factory)
    assert replay["winner_id"] is None
    assert replay["results"][0]["error"].startswith("malformed:")
    for name in created:
        assert_removed(name)


@pytest.mark.docker
def test_docker_stdlib_imports_files_network_and_no_source_injection(docker_ready, tmp_path):
    marker = tmp_path / "host-only-marker.txt"
    marker.write_text("HOST_PRIVATE", encoding="utf-8")
    source = f'''import math, os, socket
# Shell-looking text is just source text, not a Docker startup command.
shell_text = "$(touch /tmp/injected); ' ; echo INJECTED"
assert math.sqrt(9) == 3
assert os.getuid() == 65534
assert not os.path.exists({str(marker)!r})
assert not os.path.exists('/tmp/injected')
try:
    open('/runner/forbidden-write', 'w')
except OSError:
    pass
else:
    raise RuntimeError('root filesystem writable')
with open('/tmp/allowed.txt', 'w') as f:
    f.write('temporary container file')
socket.setdefaulttimeout(0.25)
try:
    socket.create_connection(('1.1.1.1', 443))
except OSError:
    pass
else:
    raise RuntimeError('network available')
{LOOP_CODE}
'''
    runner = DockerRunner({"code": source})
    try:
        assert runner.act(OBSERVATION, first=True) == "13000 2000 100"
    finally:
        runner.close()
    assert_removed(runner.name)
    assert marker.read_text(encoding="utf-8") == "HOST_PRIVATE"


@pytest.mark.docker
@pytest.mark.parametrize("track", make_tracks(), ids=lambda track: track["id"])
@pytest.mark.parametrize("filename", ["starter.py", "cruise.py", "cautious.py", "boost.py",
                                      "cornering.py", "momentum.py", "sprinter.py"])
def test_docker_examples_actually_finish_races(docker_ready, filename, track):
    code = (ROOT / "examples" / filename).read_text(encoding="utf-8")
    replay = run_race([
        {"id": "student", "alias": filename, "code": code},
        {"id": "reference", "alias": "Baseline", "kind": "reference", "code": "baseline"},
    ], track)
    student = next(result for result in replay["results"] if result["id"] == "student")
    assert not student["disqualified"], student["error"]
    assert student["finished"], student
    assert replay["winner_id"] is not None
    json.dumps(replay, allow_nan=False)


@pytest.mark.docker
def test_docker_five_real_pods_race_without_contact_and_produce_a_winner(docker_ready):
    filenames = ["boost.py", "cornering.py", "momentum.py", "sprinter.py", "cautious.py"]
    entries = [{"id": str(index), "alias": filename,
                "code": (ROOT / "examples" / filename).read_text(encoding="utf-8")}
               for index, filename in enumerate(filenames)]
    replay = run_race(entries, make_tracks()[0])
    assert replay["winner_id"] is not None
    assert len(replay["frames"][-1]["pods"]) == 5
    assert all(not item["disqualified"] for item in replay["results"])
    assert all(item["finished"] for item in replay["results"])
