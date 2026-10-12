"""Developer acceptance test: unique Compose project, disposable volume, real Docker.

Run: uv run python scripts/deployment_test.py
Installation itself needs only Docker; this optional developer test uses stdlib Python.
Never removes shared sandbox images or other projects' containers/volumes.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    project = "pod-deploy-test-" + uuid.uuid4().hex[:12]
    port = free_port()
    env = os.environ.copy()
    env.update(POD_PORT=str(port), POD_BIND="127.0.0.1", MSYS_NO_PATHCONV="1", MSYS2_ARG_CONV_EXCL="*")
    command = ["docker", "compose", "--project-name", project, "--file", str(ROOT / "compose.yaml")]

    def compose(*args, timeout=180):
        result = subprocess.run(command + list(args), cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout.strip()

    def printed_key_digest():
        log = compose("logs", "--no-log-prefix", "classroom")
        prefix = "Teacher admin token (save this privately): "
        keys = [line.split(prefix, 1)[1].strip() for line in log.splitlines() if prefix in line]
        assert keys, "Generated teacher token was not printed in classroom logs"
        assert len(set(keys)) == 1, "Teacher key changed across launches"
        return hashlib.sha256(keys[-1].encode()).hexdigest()

    def wait_healthy():
        until = time.monotonic() + 120
        while time.monotonic() < until:
            container = compose("ps", "--quiet", "classroom")
            result = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
                                    env=env, text=True, capture_output=True, timeout=15)
            if result.stdout.strip() == "healthy":
                return
            time.sleep(1)
        raise TimeoutError("Classroom did not become healthy")

    print(f"Testing unique project {project}, localhost:{port}", flush=True)
    summary = {"project": project, "port": port}
    started = time.monotonic()
    try:
        compose("up", "--build", "-d", "--wait", "--wait-timeout", "180", timeout=900)
        wait_healthy()
        with urlopen(f"http://127.0.0.1:{port}/api/state", timeout=30) as response:
            assert json.load(response)["sandbox"]["available"]
        with urlopen(f"http://127.0.0.1:{port}/api/rules?lang=de", timeout=30) as response:
            assert response.headers["Content-Language"] == "de"
            assert "Programmierkurs" in json.load(response)["title"]
        with urlopen(f"http://127.0.0.1:{port}/teacher?lang=de", timeout=30) as response:
            page = response.read().decode("utf-8")
            assert "language-switch" in page and "/assets/i18n.js" in page
        with urlopen(f"http://127.0.0.1:{port}/api/starter?lang=de", timeout=30) as response:
            assert "Lies in jedem Spielzug" in response.read().decode("utf-8")
        summary["german_interface_and_api"] = "passed"
        version = compose("exec", "-T", "classroom", "docker", "version", "--format", "{{.Client.Version}}/{{.Server.Version}}")
        assert "29.8.2/" in version, version
        summary["docker_client_server"] = version
        printed_key = printed_key_digest()
        runtime = json.loads(compose("exec", "-T", "classroom", "python", "-c",
            "import json,sys,shutil,importlib.util; "
            "print(json.dumps({'python':sys.version.split()[0], "
            "'dev_tools':{n:bool(shutil.which(n)) for n in ('uv','node','npm')}, "
            "'dev_packages':{n:bool(importlib.util.find_spec(n)) for n in ('pytest','playwright','ruff')}}))"))
        assert not any(runtime["dev_tools"].values()) and not any(runtime["dev_packages"].values()), runtime
        summary["runtime"] = runtime
        container = compose("ps", "--quiet", "classroom")
        inspected = subprocess.run(["docker", "inspect", container], env=env, text=True,
                                   capture_output=True, check=True, timeout=15)
        info = json.loads(inspected.stdout)[0]
        assert {mount["Destination"] for mount in info["Mounts"]} == {"/data", "/var/run/docker.sock"}
        assert info["NetworkSettings"]["Ports"]["8765/tcp"][0]["HostIp"] == "127.0.0.1"
        image = info["Image"]
        missing = subprocess.run(["docker", "run", "--rm", "--network=none", "--entrypoint", "python", image,
                                 "-c", "from arena.bots import sandbox_status; assert not sandbox_status()['available']; "
                                 "print('no-socket availability fails closed')"], env=env,
                                capture_output=True, text=True, check=True, timeout=30)
        assert "fails closed" in missing.stdout
        summary["no_socket_preflight"] = "passed"
        result = compose("exec", "-T", "classroom", "python", "scripts/deployment_probe.py", timeout=900)
        summary["tournament"] = json.loads(result)
        print(result, flush=True)
        compose("restart", "classroom")
        wait_healthy()
        summary["restart"] = json.loads(compose("exec", "-T", "classroom", "python", "scripts/deployment_probe.py", "--persisted"))
        assert printed_key_digest() == printed_key
        # Recreate verifies the data isn't merely saved in the old writable layer.
        compose("up", "-d", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "180", "classroom")
        wait_healthy()
        summary["recreation"] = json.loads(compose("exec", "-T", "classroom", "python", "scripts/deployment_probe.py", "--persisted"))
        assert printed_key_digest() == printed_key
        summary["secret_in_logs"] = "generated, retained, printed on every launch"
        # Exercise launchers without opening a browser or exposing key output.
        launcher_env = env | {"COMPOSE_PROJECT_NAME": project, "POD_NO_BROWSER": "1", "POD_NO_PAUSE": "1"}
        launchers = [["sh", "Docker-start.sh"]]
        if os.name == "nt":
            launchers.append(["cmd", "/d", "/c", "Docker-start.cmd"])
        summary["launchers"] = []
        for launcher in launchers:
            launched = subprocess.run(launcher, cwd=ROOT, env=launcher_env, text=True,
                                      capture_output=True, timeout=300)
            # Do not echo captured logs: they include the private test teacher key.
            assert launched.returncode == 0, f"Launcher {launcher[-1]} failed ({launched.returncode})"
            assert f"http://localhost:{port}/teacher" in launched.stdout, "Launcher printed incorrect published port"
            wait_healthy()
            assert printed_key_digest() == printed_key
            compose("exec", "-T", "classroom", "python", "scripts/deployment_probe.py", "--persisted")
            summary["launchers"].append(launcher[-1])
        summary["seconds"] = round(time.monotonic() - started, 2)
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        (artifacts / "deployment-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        # Scope destruction to the random test project. Never use global prune.
        compose("down", "--volumes", "--remove-orphans")
        remaining = subprocess.run(["docker", "ps", "-a", "--filter", "label=com.docker.compose.project=" + project,
                                    "--format", "{{.ID}}"], env=env, text=True, capture_output=True, check=True)
        volumes = subprocess.run(["docker", "volume", "ls", "--filter", "label=com.docker.compose.project=" + project,
                                  "--format", "{{.Name}}"], env=env, text=True, capture_output=True, check=True)
        assert not remaining.stdout.strip() and not volumes.stdout.strip(), "Test project cleanup incomplete"
        print("Unique test project containers and volume removed; shared sandbox image retained.", flush=True)


if __name__ == "__main__":
    main()
