"""Synthetic private data only; Docker operations are always mocked."""
import importlib
import os
from contextlib import closing
import json
import sqlite3
import shutil
from types import SimpleNamespace
from pathlib import Path


APP_ID = "a" * 64
GATE_ID = "b" * 64
HELPER_ID = "c" * 64
IMAGE_ID = "sha256:" + "d" * 64


class DockerBoundary:
    """Simulate only Docker transport; files/SQLite/manifest checks are real."""
    def __init__(self, data):
        self.data = data
        self.calls = []
        self.endpoint = "unix:///synthetic/docker.sock"
        self.os_type = "linux"
        self.containers = {
            APP_ID: {"Id": APP_ID, "Image": IMAGE_ID, "Config": {
                "Image": "trusted-app:local", "Labels": {"com.docker.compose.project": "classroom"}},
                "Mounts": [{"Type": "volume", "Name": "exact_data", "Destination": "/data"}],
                "NetworkSettings": {"Ports": {"8765/tcp": None}},
                "HostConfig": {"PortBindings": {}},
                "State": {"Running": True, "Health": {"Status": "healthy"}}},
            GATE_ID: {"Id": GATE_ID, "Config": {"Labels": {"com.docker.compose.project": "classroom"}},
                      "State": {"Running": True}},
        }
        self.stats_override = []
        self.volumes = {}
        self.fail = None

    def __call__(self, args, **kwargs):
        assert isinstance(args, list) and not kwargs.get("shell", False)
        assert kwargs["capture_output"] and kwargs["text"]
        self.calls.append(args)
        assert args[:3] == ["docker", "--context", "reserve"]
        cmd = args[3:]
        if self.fail and self.fail(cmd):
            return SimpleNamespace(returncode=1, stdout="SYNTHETIC-SECRET", stderr="SYNTHETIC-SECRET")
        value = ""
        if cmd[:2] == ["context", "inspect"]:
            value = [{"Endpoints": {"docker": {"Host": self.endpoint}}}]
        elif cmd[0] == "info":
            value = "linux" if self.os_type == "linux" else self.os_type
        elif cmd[:2] == ["container", "inspect"]:
            target = {"app": APP_ID, "gate": GATE_ID}.get(cmd[2], cmd[2])
            value = [self.containers[target]]
        elif cmd[0] == "exec":
            value = self.stats_override.pop(0) if self.stats_override else module().snapshot_stats(self.data)
        elif cmd[0] in ("stop", "start"):
            self.containers[cmd[-1]]["State"]["Running"] = cmd[0] == "start"
        elif cmd[0] == "cp":
            source, destination = cmd[1:]
            if source.split(":", 1)[0] in self.containers:
                source_root = self.data if source.startswith(APP_ID) else self.restored_data
                shutil.copytree(source_root, destination, dirs_exist_ok=True)
            else:
                shutil.copytree(source.rstrip("/."), self.restored_data, dirs_exist_ok=True)
        elif cmd[:2] == ["image", "inspect"]:
            value = [{"Id": IMAGE_ID}]
        elif cmd[:2] == ["volume", "ls"]:
            value = "\n".join(self.volumes)
        elif cmd[:2] == ["volume", "create"]:
            name = cmd[-1]
            label = cmd[cmd.index("--label") + 1].split("=", 1)
            self.volumes[name] = {"Name": name, "Labels": dict([label])}
            value = name
        elif cmd[:2] == ["volume", "inspect"]:
            value = [self.volumes[cmd[-1]]]
        elif cmd[0] == "create":
            label = cmd[cmd.index("--label") + 1].split("=", 1)
            volume = cmd[cmd.index("--mount") + 1].split("src=", 1)[1].split(",")[0]
            self.containers[HELPER_ID] = {"Id": HELPER_ID, "Config": {"Labels": dict([label])},
                "Image": IMAGE_ID, "HostConfig": {"NetworkMode": "none"},
                "Mounts": [{"Type": "volume", "Name": volume, "Destination": "/data"}]}
            self.restored_data = self.data.parent / "restored"
            self.restored_data.mkdir()
            value = HELPER_ID
        elif cmd[:2] == ["container", "ls"]:
            target = cmd[-1].split("=", 1)[1]
            value = target if target in self.containers else ""
        elif cmd[0] == "rm":
            del self.containers[cmd[-1]]
        else:
            raise AssertionError(cmd)
        return SimpleNamespace(returncode=0, stdout=json.dumps(value) if not isinstance(value, str) else value, stderr="")

import pytest


def module():
    return importlib.import_module("scripts.classroom_backup")


@pytest.fixture(autouse=True)
def isolated_backup_lock_namespace(tmp_path, monkeypatch):
    monkeypatch.setattr(module(), "LOCK_ROOT", tmp_path / "locks")


def sample_data(root):
    root.mkdir(parents=True)
    with closing(sqlite3.connect(root / "classroom.sqlite3")) as db, db:
        db.executescript("CREATE TABLE config(key TEXT PRIMARY KEY,value TEXT);"
                         "CREATE TABLE submissions(id TEXT,claim_token TEXT);"
                         "CREATE TABLE replays(id TEXT,title TEXT);")
        db.executemany("INSERT INTO config VALUES (?,?)", [
            ("admin_token", json.dumps("SYNTHETIC-TEACHER-SECRET")),
            ("session", json.dumps({"status": "closed"})),
            ("job", json.dumps({"status": "idle"})),
        ])
        db.execute("INSERT INTO submissions VALUES ('student', 'SYNTHETIC-STUDENT-SECRET')")
        db.execute("INSERT INTO replays VALUES ('replay','Synthetic title')")
    (root / "replays").mkdir()
    (root / "replays/replay.json").write_text('{"status":"finished","frames":[]}')
    (root / "empty").mkdir()
    return root


def test_snapshot_returns_only_counts_and_safe_statuses(tmp_path):
    data = sample_data(tmp_path / "data")
    before = (data / "classroom.sqlite3").read_bytes()
    result = module().snapshot_stats(data)
    assert result == {"counts": {"config": 3, "submissions": 1, "replays": 1},
                      "replay_files": 1, "session": "closed", "job": "idle"}
    assert "SECRET" not in json.dumps(result)
    assert (data / "classroom.sqlite3").read_bytes() == before


def test_inspect_uses_explicit_local_context_and_only_safe_metadata(tmp_path):
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    docker = module().Docker("reserve", fake.endpoint, run=fake)
    result = module().inspect_app(docker, "classroom", "app", "exact_data")
    assert result["counts"]["submissions"] == 1
    assert result["image"] == IMAGE_ID
    assert "SECRET" not in json.dumps(result)
    assert not any(call[3] in ("stop", "start", "create", "cp") for call in fake.calls)


@pytest.mark.parametrize("endpoint,os_type", [
    ("tcp://localhost:2375", "linux"), ("ssh://localhost", "linux"),
    ("unix:///different.sock", "linux"), ("unix:///synthetic/docker.sock", "windows")])
def test_context_guard_refuses_unexpected_or_nonlocal_daemon(tmp_path, endpoint, os_type):
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    fake.endpoint, fake.os_type = endpoint, os_type
    with pytest.raises(module().BackupError):
        module().Docker("reserve", "unix:///synthetic/docker.sock", run=fake)
    assert not any(call[3] == "exec" for call in fake.calls)


def test_cold_backup_preserves_bytes_secrets_and_exact_container_configuration(tmp_path, monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, "LOCK_ROOT", tmp_path / "locks", raising=False)
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    first = tmp_path / "private-one"
    second = tmp_path / "private-two"
    first.mkdir(); second.mkdir()
    (first / "credential.json").write_text('SYNTHETIC-FIRST')
    (second / "credential.json").write_text('SYNTHETIC-SECOND')
    output = tmp_path / "backup"
    result = mod.backup(mod.Docker("reserve", fake.endpoint, run=fake), "classroom", "app", "exact_data",
                        output, gate_container="gate", private_files=[first / "credential.json", second / "credential.json"])
    assert result["counts"] == {"config": 3, "submissions": 1, "replays": 1}
    assert "SECRET" not in json.dumps(result) and "sha256" not in json.dumps(result)
    assert (output / "data/classroom.sqlite3").read_bytes() == (fake.data / "classroom.sqlite3").read_bytes()
    assert sorted(p.read_text() for p in (output / "secrets").iterdir()) == ['SYNTHETIC-FIRST', 'SYNTHETIC-SECOND']
    assert not (output / ".incomplete").exists()
    manifest = mod.check_backup(output)
    assert manifest["source"]["image"] == IMAGE_ID
    assert manifest["source"]["context"] == "reserve"
    assert len(manifest["private_files"]) == 2
    assert not list((tmp_path / "locks").iterdir())
    lifecycle = [call[3:] for call in fake.calls if call[3] in ("stop", "start", "cp", "exec")]
    assert [call[:2] for call in lifecycle] == [
        ["exec", APP_ID], ["stop", "--time"], ["exec", APP_ID], ["stop", "--time"],
        ["cp", f"{APP_ID}:/data/."], ["start", APP_ID], ["start", GATE_ID]]
    assert lifecycle[1][-1] == GATE_ID and lifecycle[3][-1] == APP_ID
    assert all("compose" not in call for call in fake.calls)
    for path in [output, *output.rglob("*")]:
        if mod.WINDOWS:
            mod.require_private(path)
        else:
            assert path.stat().st_mode & 0o077 == 0


def make_backup(tmp_path, monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, "LOCK_ROOT", tmp_path / "locks")
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    docker = mod.Docker("reserve", fake.endpoint, run=fake)
    root = tmp_path / "backup"
    mod.backup(docker, "classroom", "app", "exact_data", root, gate_container="gate")
    fake.calls.clear()
    return mod, fake, docker, root


def test_restore_creates_only_new_volume_and_isolated_owned_stopped_helper(tmp_path, monkeypatch):
    mod, fake, docker, root = make_backup(tmp_path, monkeypatch)
    result = mod.restore(docker, root, "new_private_data", "trusted-app:local")
    assert result == {"volume": "new_private_data", "counts": {"config": 3, "submissions": 1, "replays": 1}, "replay_files": 1}
    assert mod.inventory(fake.restored_data) == mod.inventory(root / "data")
    assert HELPER_ID not in fake.containers
    assert "new_private_data" in fake.volumes
    create = next(call[3:] for call in fake.calls if call[3] == "create")
    assert create[create.index("--network") + 1] == "none"
    assert "--read-only" in create and "--cap-drop" in create
    assert "docker.sock" not in " ".join(create) and "SECRET" not in " ".join(create)
    assert IMAGE_ID in create
    assert not any(call[3] in ("start", "run", "stop", "compose") for call in fake.calls)
    with sqlite3.connect(fake.restored_data / "classroom.sqlite3") as db:
        assert json.loads(db.execute("SELECT value FROM config WHERE key='admin_token'").fetchone()[0]) == "SYNTHETIC-TEACHER-SECRET"
        assert db.execute("SELECT claim_token FROM submissions").fetchone()[0] == "SYNTHETIC-STUDENT-SECRET"
        assert db.execute("SELECT id,title FROM replays").fetchone() == ("replay", "Synthetic title")


def test_restore_establishes_owner_of_new_audit_directory(tmp_path, monkeypatch):
    import subprocess
    mod, fake, docker, root = make_backup(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, 'WINDOWS', True)
    user = 'S-1-5-21-100'
    owned = set()
    audit_roots = set()

    def native_acl(command, **kwargs):
        path = Path(kwargs['env']['CLASSROOM_PRIVATE_ACL_PATH'])
        if 'SetOwner(' in command[-1]:
            owned.add(path)
            return subprocess.CompletedProcess(command, 0, '', '')
        owner = user
        if path.name.startswith('classroom-verify-'):
            audit_roots.add(path)
            if path not in owned:
                owner = mod._WIN_ADMINS
        return subprocess.CompletedProcess(command, 0, json.dumps(
            {'owner': owner, 'user': user, 'allow': ['S-1-3-4']}), '')

    monkeypatch.setattr(mod.subprocess, 'run', native_acl)
    result = mod.restore(docker, root, 'new_private_data', 'trusted-app:local')
    assert result['counts']['submissions'] == 1
    assert audit_roots and audit_roots <= owned
    assert len(audit_roots) == 1
    audit = next(iter(audit_roots))
    assert owned == {audit, audit / 'data', *(
        audit / 'data' / name for name in mod.inventory(root / 'data'))}
    assert not any(path == root or root in path.parents for path in owned)
    assert HELPER_ID not in fake.containers


def test_inspect_output_strips_sha256_images(tmp_path, monkeypatch):
    mod = module()
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    docker = mod.Docker("reserve", fake.endpoint, run=fake)
    result = mod.inspect_app(docker, "classroom", "app", "exact_data")
    assert result["counts"]["submissions"] == 1
    assert result["image"] == IMAGE_ID and result["volume"] == "exact_data"
    safe = mod.safe_json(result)
    assert "IMAGE" not in json.dumps(safe) and "sha256" not in json.dumps(safe)
    assert not any(text in json.dumps(safe) for text in ("SECRET", "admin_token", "claim_token"))


def test_check_refuses_corrupted_backup(tmp_path, monkeypatch):
    mod = module()
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    docker = mod.Docker("reserve", fake.endpoint, run=fake)
    root = tmp_path / "backup"
    mod.backup(docker, "classroom", "app", "exact_data", root, gate_container="gate")
    assert mod.check_backup(root) is not None
    (root / "data" / "corrupted.txt").write_text("modified file content")
    with pytest.raises(mod.BackupError):
        mod.check_backup(root)


def test_restore_refuses_preexisting_volume(tmp_path, monkeypatch):
    mod = module()
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    docker = mod.Docker("reserve", fake.endpoint, run=fake)
    root = tmp_path / "backup"
    mod.backup(docker, "classroom", "app", "exact_data", root, gate_container="gate")
    fake.volumes["new_private_data"] = {"Name": "new_private_data"}
    with pytest.raises(mod.BackupError, match="already exists"):
        mod.restore(docker, root, "new_private_data", "trusted-app:local")


def test_backup_refuses_published_host_ports(tmp_path, monkeypatch):
    mod = module()
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    fake.containers[APP_ID]["HostConfig"]["PortBindings"] = {"8765/tcp": [{"HostIp": "", "HostPort": "8080"}]}
    with pytest.raises(mod.BackupError, match="published"):
        mod.backup(mod.Docker("reserve", fake.endpoint, run=fake), "classroom", "app", "exact_data",
                   tmp_path / "backup")


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits do not represent native Windows ACLs")
def test_backup_owns_output_and_refuses_writable_parent(tmp_path, monkeypatch):
    import os as _os
    mod = module()
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    docker = mod.Docker("reserve", fake.endpoint, run=fake)
    bad = tmp_path / "world-writable"
    bad.mkdir(); _os.chmod(bad, 0o777)
    with pytest.raises(mod.BackupError, match="group/world"):
        mod.backup(docker, "classroom", "app", "exact_data", bad / "output")


def test_backup_preserves_original_app_on_failure_and_retains_lock(tmp_path, monkeypatch):
    mod = module()
    LOCK_ROOT_PATH = tmp_path / "locks"
    monkeypatch.setattr(mod, "LOCK_ROOT", LOCK_ROOT_PATH)
    fake = DockerBoundary(sample_data(tmp_path / "data"))
    fake.fail = lambda cmd: cmd[0] == "cp"
    docker = mod.Docker("reserve", fake.endpoint, run=fake)
    with pytest.raises(mod.BackupError):
        mod.backup(docker, "classroom", "app", "exact_data", tmp_path / "fail_backup", gate_container="gate")
    assert LOCK_ROOT_PATH.exists() and any(LOCK_ROOT_PATH.iterdir())
    lock = next(LOCK_ROOT_PATH.iterdir())
    assert (lock / 'owner').is_file()
    assert fake.containers[APP_ID]['State']['Running']
    assert fake.containers[GATE_ID]['State']['Running']
    assert (tmp_path / 'fail_backup' / '.incomplete').is_file()





