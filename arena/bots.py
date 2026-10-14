"""Trusted reference policies and a fail-closed Docker-only student runner.

Uploaded code is never compiled or executed in this process. The container receives
its source as JSON on stdin, not via a shell, command interpolation, or host mount.
"""
from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid

def configured_image():
    """Trusted operator setting, never derived from submitted code or HTTP."""
    value = os.environ.get('POD_BOT_IMAGE', 'pod-classroom-bot:local')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/@:-]{0,254}', value) or '://' in value:
        raise ValueError('POD_BOT_IMAGE must be a single Docker image reference without whitespace or options.')
    return value


IMAGE = configured_image()
MAX_SOURCE_BYTES = 32768
MAX_LINE_BYTES = 1024
MAX_STDOUT_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 65536
STARTUP_TIMEOUT = 15.0
TURN_TIMEOUT = 0.5
FIRST_TURN_TIMEOUT = 2.0
READY = "__POD_CLASSROOM_READY__"


class BotError(Exception):
    """A deliberately short, safe-to-publish bot failure."""
    kind = "crash"

    def __init__(self, message: str = "Bot process stopped"):
        super().__init__(message)


class BotTimeout(BotError):
    kind = "timeout"


class BotOutputLimit(BotError):
    kind = "output_limit"


class BotCrash(BotError):
    kind = "crash"


class BotMalformed(BotError):
    kind = "malformed"


class SandboxUnavailable(BotError):
    kind = "sandbox_unavailable"


def _docker_env() -> dict:
    # Git Bash must not rewrite Docker's Linux paths on Windows.
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    return env


def sandbox_status() -> dict:
    if not shutil.which("docker"):
        return {"available": False, "detail": "Docker is not installed or not on PATH.", "image": IMAGE}
    try:
        daemon = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, timeout=5, env=_docker_env(),
        )
        if daemon.returncode != 0 or not daemon.stdout.strip():
            return {"available": False, "detail": "Docker daemon is unavailable. Start Docker Desktop.", "image": IMAGE}
        image = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
            capture_output=True, timeout=5, env=_docker_env(),
        )
        if image.returncode != 0:
            return {"available": False, "detail": "Sandbox image is missing; build sandbox/Dockerfile first.", "image": IMAGE}
        return {"available": True, "detail": "Restricted Docker sandbox ready.", "image": IMAGE}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "detail": "Docker availability check failed or timed out.", "image": IMAGE}


def container_command(name: str) -> list[str]:
    return [
        "docker", "run", "--rm", "--pull=never", "--name", name,
        "--interactive", "--network=none", "--read-only", "--log-driver=none", "--restart=no",
        "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
        "--user=65534:65534", "--pids-limit=32", "--memory=64m",
        "--memory-swap=64m", "--cpus=0.5", "--ulimit", "nofile=64:64",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777",
        IMAGE,
    ]


class DockerRunner:
    """Persistent stdin/stdout bot with bounded queues, output and wall time.

    Stderr is drained concurrently and never returned to the browser (it may
    contain secrets). Limits are cumulative per race; stdout lines are 1 KiB.
    close() always force-removes the named container, including failed startup.
    """
    def __init__(self, entry: dict, *, startup_timeout: float = STARTUP_TIMEOUT,
                 turn_timeout: float = TURN_TIMEOUT, first_turn_timeout: float = FIRST_TURN_TIMEOUT):
        code = entry.get("code", "")
        if not isinstance(code, str) or len(code.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise BotMalformed("Source must be text of at most 32 KiB")
        self.name = "pod-bot-" + uuid.uuid4().hex
        self.turn_timeout = turn_timeout
        self.first_turn_timeout = first_turn_timeout
        self._lines: queue.Queue = queue.Queue(maxsize=32)
        self._failure: BotError | None = None
        self._failure_lock = threading.Lock()
        self._closed = False
        self._process = None
        self._threads: list[threading.Thread] = []
        try:
            self._process = subprocess.Popen(
                container_command(self.name), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                env=_docker_env(),
            )
            for stream, stdout in ((self._process.stdout, True), (self._process.stderr, False)):
                thread = threading.Thread(target=self._drain, args=(stream, stdout), daemon=True)
                self._threads.append(thread)
                thread.start()
            self._send(json.dumps({"code": code}, ensure_ascii=True) + "\n", startup_timeout)
            if self._read(startup_timeout) != READY:
                raise BotCrash("Sandbox startup handshake failed")
        except FileNotFoundError:
            self.close()
            raise SandboxUnavailable("Docker executable is unavailable") from None
        except Exception:
            self.close()
            raise

    def _fail(self, error: BotError) -> None:
        with self._failure_lock:
            if self._failure is None:
                self._failure = error

    def _drain(self, stream, stdout: bool) -> None:
        total = 0
        partial = bytearray()
        discard = False
        try:
            while True:
                block = stream.read(4096)
                if not block:
                    if stdout:
                        self._fail(BotCrash("Bot exited before producing a complete command"))
                    return
                if discard:
                    # Keep draining until container termination. Stopping here
                    # fills the attached Docker CLI pipe and can delay removal.
                    continue
                total += len(block)
                cap = MAX_STDOUT_BYTES if stdout else MAX_STDERR_BYTES
                if total > cap:
                    self._fail(BotOutputLimit("Bot exceeded its output limit"))
                    discard = True
                    partial.clear()
                    continue
                if not stdout:
                    continue
                partial.extend(block)
                while b"\n" in partial:
                    line, _, rest = partial.partition(b"\n")
                    partial = bytearray(rest)
                    if len(line) > MAX_LINE_BYTES:
                        self._fail(BotOutputLimit("Command line exceeds 1 KiB"))
                        discard = True
                        break
                    try:
                        decoded = line.rstrip(b"\r").decode("utf-8")
                    except UnicodeDecodeError:
                        self._fail(BotMalformed("Command output must be UTF-8 text"))
                        discard = True
                        break
                    try:
                        self._lines.put_nowait(decoded)
                    except queue.Full:
                        self._fail(BotOutputLimit("Too many unsolicited command lines"))
                        discard = True
                        break
                if len(partial) > MAX_LINE_BYTES:
                    self._fail(BotOutputLimit("Command line exceeds 1 KiB"))
                    discard = True
                if discard:
                    partial.clear()
        except (OSError, ValueError):
            if not self._closed:
                self._fail(BotCrash("Bot output stream failed"))

    def _read(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        while True:
            if self._failure:
                raise self._failure
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BotTimeout("Bot exceeded its response deadline")
            try:
                return self._lines.get(timeout=min(remaining, 0.02))
            except queue.Empty:
                pass

    def _send(self, text: str, timeout: float) -> None:
        # Pipe writes can block if a bot stops reading. A bounded writer plus
        # forced container removal handles even that failure without host hangs.
        complete = threading.Event()
        errors = []

        def write():
            try:
                self._process.stdin.write(text.encode("utf-8"))
                self._process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                errors.append(True)
            finally:
                complete.set()

        thread = threading.Thread(target=write, daemon=True)
        thread.start()
        if not complete.wait(timeout):
            raise BotTimeout("Bot stopped reading its input")
        if errors:
            raise BotCrash("Bot input stream closed")

    def act(self, observation: str, first: bool = False) -> str:
        if self._closed:
            raise BotCrash("Bot runner is closed")
        timeout = self.first_turn_timeout if first else self.turn_timeout
        deadline = time.monotonic() + timeout
        self._send(observation, timeout)
        return self._read(max(0.0, deadline - time.monotonic()))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Removal, not just killing the Docker CLI, terminates all bot children.
        try:
            subprocess.run(["docker", "rm", "--force", self.name], capture_output=True,
                           timeout=10, env=_docker_env())
        except (OSError, subprocess.TimeoutExpired):
            pass
        if self._process is not None:
            if self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    try:
                        self._process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        pass
            for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        for thread in self._threads:
            thread.join(timeout=0.2)
        # --rm cleanup can briefly be asynchronous, especially when an attached
        # process flooded a pipe. Verify the exact name rather than trusting the
        # remove command's exit status, and retry after terminating the CLI.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                exists = subprocess.run(["docker", "container", "inspect", self.name],
                                        capture_output=True, timeout=2, env=_docker_env())
                if exists.returncode != 0:
                    break
                subprocess.run(["docker", "rm", "--force", self.name],
                               capture_output=True, timeout=2, env=_docker_env())
            except (OSError, subprocess.TimeoutExpired):
                break
            time.sleep(0.05)


class ReferenceRunner:
    """Only predefined, trusted Python policies; never evaluates entry.code.

    Set kind='reference', code='baseline' (or 'cautious', 'racer'). Unknown code
    selects baseline for backwards-compatible reference opponent construction.
    """
    def __init__(self, entry: dict):
        self.style = entry.get("strategy", entry.get("code", "baseline"))
        self.boost = True
        self.previous: tuple[int, int] | None = None

    def act(self, observation: str, first: bool = False) -> str:
        lines = observation.splitlines()
        x, y, cx, cy, distance, angle = map(int, lines[0].split())
        if self.style == "cautious":
            thrust = 40 if abs(angle) > 45 else 80
        else:
            thrust = max(15, round(100 * max(0, math.cos(math.radians(angle))) ** 2))
            if distance < 1800:
                thrust = min(thrust, 45)
        tx, ty = cx, cy
        if self.style == "racer" and self.previous is not None:
            tx -= 3 * (x - self.previous[0])
            ty -= 3 * (y - self.previous[1])
        self.previous = (x, y)
        if self.boost and distance > 6000 and abs(angle) < 5:
            self.boost = False
            return f"{tx} {ty} BOOST"
        return f"{tx} {ty} {thrust}"

    def close(self) -> None:
        pass


def make_runner(entry: dict):
    return ReferenceRunner(entry) if entry.get("kind", "student") == "reference" else DockerRunner(entry)
