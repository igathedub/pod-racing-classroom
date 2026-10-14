"""Owner-private, cold classroom backups. Never prints Docker diagnostics or secrets."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import inspect
import os
import re
import subprocess
import sys
import argparse

WINDOWS = os.name == "nt"
PROJECT_LABEL = "com.docker.compose.project"


class Docker:
    def __init__(self, context, expected_endpoint, run=None):
        self.context, self.endpoint = context, expected_endpoint
        self.run = run or subprocess.run
        if not context or context.startswith("-") or not (
                expected_endpoint.startswith("unix:///") or expected_endpoint.startswith("npipe:////./pipe/")):
            raise BackupError("An explicit local unix/npipe context endpoint is required")
        actual = self.json("context", "inspect", context)[0]["Endpoints"]["docker"]["Host"]
        if actual != expected_endpoint:
            raise BackupError("Docker context endpoint does not match")
        if self.call("info", "--format", "{{.OSType}}").strip() != "linux":
            raise BackupError("A Linux Docker engine is required")

    def call(self, *args):
        # Remove ambient endpoint/context overrides; all calls target the inspected context.
        env = {k: v for k, v in os.environ.items() if k not in {"DOCKER_HOST", "DOCKER_CONTEXT"}}
        try:
            result = self.run(["docker", "--context", self.context, *map(str, args)],
                              capture_output=True, text=True, timeout=180, env=env)
        except (OSError, subprocess.SubprocessError):
            raise BackupError("Docker operation failed; private diagnostics suppressed") from None
        if result.returncode:
            raise BackupError("Docker operation failed; private diagnostics suppressed")
        return result.stdout

    def json(self, *args):
        try:
            return json.loads(self.call(*args))
        except (ValueError, TypeError):
            raise BackupError("Invalid Docker response; private diagnostics suppressed") from None

    def container(self, name):
        if not name or name.startswith("-"):
            raise BackupError("Invalid container identifier")
        item = self.json("container", "inspect", name)[0]
        if not re.fullmatch(r"[0-9a-f]{64}", item["Id"]):
            raise BackupError("Docker did not return an exact container ID")
        return item

    def stats(self, item):
        if not item["State"]["Running"]:
            raise BackupError("Read-only live inspection requires a running app")
        source = "from pathlib import Path\nimport sqlite3,json\n" + inspect.getsource(BackupError) + "\n" + inspect.getsource(snapshot_stats)
        source += "\nprint(json.dumps(snapshot_stats(Path('/data'))))"
        return self.json("exec", item["Id"], "python", "-c", source)


def app_identity(docker, project, container, volume):
    item = docker.container(container)
    if item["Config"].get("Labels", {}).get(PROJECT_LABEL) != project:
        raise BackupError("Compose project label does not match")
    mounts = [mount for mount in item["Mounts"] if mount["Destination"] == "/data"]
    if len(mounts) != 1 or mounts[0]["Type"] != "volume" or mounts[0].get("Name") != volume:
        raise BackupError("Exact named /data volume does not match")
    return item


def inspect_app(docker, project, container, volume):
    item = app_identity(docker, project, container, volume)
    return {"project": project, "volume": volume, "image": item["Image"], **docker.stats(item)}


class BackupError(Exception):
    """An operator-safe error, never populated with subprocess output."""


def snapshot_stats(root):
    """Read SQLite without application startup (which would mutate job state)."""
    from contextlib import closing
    root = Path(root)
    with closing(sqlite3.connect((root / "classroom.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise BackupError("SQLite integrity check failed")
        counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                  for table in ("config", "submissions", "replays")}
        statuses = {}
        for key in ("session", "job"):
            row = db.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            value = json.loads(row[0])["status"] if row else "unknown"
            statuses[key] = value if value in {"waiting", "open", "closed", "qualified", "finished", "idle", "running", "failed"} else "unknown"
    return {"counts": counts, "replay_files": len(list((root / "replays").glob("*.json"))), **statuses}


def safe_json(result):
    """Only emit operator-relevant metadata without hashes, keys, or inventory."""
    if isinstance(result, dict) and "counts" in result:
        return {"counts": result.get("counts"), "replay_files": result.get("replay_files"),
                "session": result.get("session"), "job": result.get("job")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", dest="context")
    parser.add_argument("--expected-endpoint", dest="endpoint")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "backup"):
        command = subparsers.add_parser(name)
        for flag in ("--project", "--container", "--volume"):
            command.add_argument(flag, required=True)
        if name == "backup":
            command.add_argument("--gate-container")
            command.add_argument("--output", required=True)
            command.add_argument("--private-file", action="append")
    command = subparsers.add_parser("restore")
    for flag in ("--backup", "--new-volume", "--image"):
        command.add_argument(flag, required=True)
    subparsers.add_parser("check").add_argument("--backup", required=True)
    args = parser.parse_args(argv)
    if args.command != "check" and (not args.context or not args.endpoint):
        parser.error("--context and --expected-endpoint are required for Docker operations")
    try:
        result = None
        if args.command == "inspect":
            docker = Docker(args.context, args.endpoint)
            result = inspect_app(docker, args.project, args.container, args.volume)
            json.dump(safe_json(result), sys.stdout, indent=2)
        elif args.command == "backup":
            docker = Docker(args.context, args.endpoint)
            files = sorted(args.private_file or ())
            result = backup(docker, args.project, args.container, args.volume, Path(args.output),
                           gate_container=args.gate_container, private_files=files)
            sys.stdout.write(json.dumps(safe_json(result), indent=2))
        elif args.command == "restore":
            docker = Docker(args.context, args.endpoint)
            result = restore(docker, args.backup, args.new_volume, args.image)
            json.dump(safe_json(result), sys.stdout, indent=2)
        else:
            manifest = check_backup(Path(args.backup))
            json.dump({"status": "verified", **safe_json(manifest["stats"])}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except BackupError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        print(json.dumps({"error": "Invalid backup, configuration or filesystem; private diagnostics suppressed"}), file=sys.stderr)
        return 1


import hashlib
import shutil
import stat
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
LOCK_ROOT = Path.home() / ".classroom-backup-locks"


def outside_repo(path):
    path = Path(path).absolute()
    if path.is_symlink() or REPO in path.resolve().parents or path.resolve() == REPO or any(
            (parent / ".git").exists() for parent in [path.resolve(), *path.resolve().parents]):
        raise BackupError("Private paths must be outside repositories and not symbolic links")
    return path.resolve()


def require_private(path):
    if WINDOWS:
        _windows_require_private_acl(path)
        return
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise BackupError("Owner-private permissions (0700 directories / 0600 files) are required")


_WIN_SYSTEM = "S-1-5-18"
_WIN_ADMINS = "S-1-5-32-544"


def _windows_require_private_acl(path):
    """Validate Windows ACL via PowerShell so owner-only access is enforced."""
    env = {k: v for k, v in os.environ.items()}
    env["CLASSROOM_PRIVATE_ACL_PATH"] = str(path)
    script = (
        "$acl = Get-Acl $env:CLASSROOM_PRIVATE_ACL_PATH; "
        "$owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value; $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
        "$allow = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Allow' } | ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }); "
        "ConvertTo-Json @{owner=$owner; user=$user; allow=$allow}"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=10, env=env)
    if result.returncode:
        raise BackupError("Windows ACL query failed; private diagnostics suppressed")
    acl = json.loads(result.stdout)
    if acl["owner"] != acl["user"]:
        raise BackupError("Windows ACL owner does not match current user; path is not private")
    # OWNER RIGHTS denotes the object's current owner, already checked above.
    # Python's native mkdir(0700) uses this SID on Windows.
    unexpected = set(acl.get("allow", [])) - {acl["user"], _WIN_SYSTEM, _WIN_ADMINS, "S-1-3-4"}
    if unexpected:
        raise BackupError(
            "Windows ACL grants access to unintended principals; require owner-only ownership"
        )


def privatize(root):
    inventory(root)  # Reject symlinks BEFORE chmod or following any private file.
    for path in [root, *root.rglob("*")]:
        if not WINDOWS:
            path.chmod(0o700 if path.is_dir() else 0o600)
        require_private(path)


def private_mkdir(path):
    path.mkdir(mode=0o700)
    require_private(path)


def inventory(root):
    entries = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        name = path.relative_to(root).as_posix()
        if stat.S_ISDIR(info.st_mode):
            entries[name] = {"directory": True}
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            entries[name] = {"size": info.st_size, "sha256": digest.hexdigest()}
        else:
            raise BackupError("Backup contains a link or nonregular file")
    return entries


def quiescent(stats):
    if stats["session"] not in {"waiting", "closed", "qualified", "finished"} or stats["job"] not in {"idle", "failed", "finished"}:
        raise BackupError("Refusing backup: coding phase is open, tournament running, or state unknown")


def check_backup(backup_dir):
    root = outside_repo(backup_dir)
    require_private(root)
    if (root / ".incomplete").exists():
        raise BackupError("Backup is incomplete; retained for private diagnosis")
    actual = inventory(root)
    for path in root.rglob("*"):
        require_private(path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    actual.pop("manifest.json", None)
    if manifest["version"] != 1 or actual != manifest["inventory"]:
        raise BackupError("Backup integrity verification failed")
    if snapshot_stats(root / "data") != manifest["stats"]:
        raise BackupError("Backup SQLite metadata verification failed")
    return manifest


def resume(docker, app, gate):
    if app and app["State"]["Running"]:
        for attempt in range(3):
            try:
                docker.call("start", app["Id"])
                break
            except BackupError:
                if attempt == 2:
                    raise BackupError("App restart failed; lock retained, gate remains stopped") from None
        deadline = time.monotonic() + 90
        while True:
            state = docker.container(app["Id"])["State"]
            if state["Running"] and state.get("Health", {}).get("Status") == "healthy":
                break
            if time.monotonic() >= deadline:
                raise BackupError("App not healthy; lock retained, gate remains stopped")
            time.sleep(1)
    if gate and gate["State"]["Running"]:
        docker.call("start", gate["Id"])
        if not docker.container(gate["Id"])["State"]["Running"]:
            raise BackupError("Gate restart failed; lock retained")


def backup(docker, project, container, volume, output, gate_container=None, private_files=()):
    output = outside_repo(output)
    if output.exists() or not output.parent.is_dir():
        raise BackupError("Output must be a new directory with an existing parent")
    if os.name != "nt" and output.parent.stat().st_mode & 0o022:
        raise BackupError("Output parent must not be group/world writable")
    files = [outside_repo(path) for path in private_files]
    if any(not path.is_file() for path in files):
        raise BackupError("Private file must be a regular file outside repositories")
    app = app_identity(docker, project, container, volume)
    if any(app.get("NetworkSettings", {}).get("Ports", {}).values()) or any(app.get("HostConfig", {}).get("PortBindings", {}).values()):
        raise BackupError("Protected backup refuses published app host ports")
    gate = docker.container(gate_container) if gate_container else None
    if gate and (gate["Id"] == app["Id"] or gate["Config"].get("Labels", {}).get(PROJECT_LABEL) != project):
        raise BackupError("Gate must be a different exact container in the same Compose project")
    if not LOCK_ROOT.exists():
        private_mkdir(LOCK_ROOT)
    require_private(LOCK_ROOT)
    lock = LOCK_ROOT / hashlib.sha256((docker.endpoint + "\0" + volume).encode()).hexdigest()
    try:
        private_mkdir(lock)
    except FileExistsError:
        raise BackupError("Exclusive backup lock exists; investigate privately, never overwrite") from None
    owner = uuid.uuid4().hex
    (lock / "owner").write_text(owner)
    privatize(lock)
    private_mkdir(output)
    (output / ".incomplete").write_text("Incomplete backup; lock retained on failure.\n")
    privatize(output)
    app_attempted = gate_attempted = False
    try:
        if app["State"]["Running"]:
            quiescent(docker.stats(app))
        if gate and gate["State"]["Running"]:
            gate_attempted = True
            docker.call("stop", "--time", "30", gate["Id"])
            if docker.container(gate["Id"])["State"]["Running"]:
                raise BackupError("Gate did not stop")
        if app["State"]["Running"]:
            quiescent(docker.stats(app))  # Close the accepted-work race after gate shutdown.
            app_attempted = True
            docker.call("stop", "--time", "30", app["Id"])
        if docker.container(app["Id"])["State"]["Running"]:
            raise BackupError("App did not stop; cold copy forbidden")
        private_mkdir(output / "data")
        docker.call("cp", f"{app['Id']}:/data/.", output / "data")
        privatize(output)
        stats = snapshot_stats(output / "data")
        quiescent(stats)
        private_mkdir(output / "secrets")
        refs = []
        for index, path in enumerate(files):
            target = output / "secrets" / f"{index:04d}-{path.name}"
            shutil.copyfile(path, target)
            refs.append(target.relative_to(output).as_posix())
        privatize(output)
        manifest = {"version": 1, "source": {"context": docker.context, "endpoint": docker.endpoint,
                    "project": project, "volume": volume, "image": app["Image"],
                    "image_reference": app["Config"].get("Image"), "container_id": app["Id"]},
                    "stats": stats, "private_files": refs, "inventory": inventory(output)}
        manifest["inventory"].pop(".incomplete")
    finally:
        resume(docker, app if app_attempted else None, gate if gate_attempted else None)
    temporary = output / "manifest.pending"
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    privatize(output)
    temporary.replace(output / "manifest.json")
    (output / ".incomplete").unlink()
    check_backup(output)
    if (lock / "owner").read_text() != owner:
        raise BackupError("Lock ownership changed; lock retained")
    (lock / "owner").unlink()
    lock.rmdir()
    return {"status": "verified", **stats}


OWNERSHIP_LABEL = "classroom.private-backup.owner"


def owned_helper(docker, helper, owner, volume, image):
    item = docker.container(helper)
    if (item["Id"] != helper or item["Config"].get("Labels", {}).get(OWNERSHIP_LABEL) != owner
            or item["Image"] != image or item["HostConfig"]["NetworkMode"] != "none"
            or item["Mounts"] != [{"Type": "volume", "Name": volume, "Destination": "/data"}]):
        # Real Docker supplies extra mount fields; compare the safety-relevant subset below.
        mounts = item.get("Mounts", [])
        if (item["Id"] != helper or item["Config"].get("Labels", {}).get(OWNERSHIP_LABEL) != owner
                or item["Image"] != image or item["HostConfig"]["NetworkMode"] != "none"
                or len(mounts) != 1 or any(m.get(k) != v for k, v in
                    {"Type": "volume", "Name": volume, "Destination": "/data"}.items() for m in mounts)):
            raise BackupError("Restore helper ownership or isolation does not match; not removed")
    return item


def restore(docker, backup_dir, new_volume, image):
    manifest = check_backup(backup_dir)  # Verify before creating ANY resources.
    root = outside_repo(backup_dir)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", new_volume):
        raise BackupError("A unique valid new Docker volume name is required")
    if not image or image.startswith("-"):
        raise BackupError("An existing trusted app image is required")
    if new_volume in docker.call("volume", "ls", "--format", "{{.Name}}").splitlines():
        raise BackupError("Target volume already exists; even empty volumes are refused")
    image_id = docker.json("image", "inspect", image)[0]["Id"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise BackupError("Trusted local image did not resolve to an immutable image ID")
    owner, helper = uuid.uuid4().hex, None
    try:
        docker.call("volume", "create", "--label", f"{OWNERSHIP_LABEL}={owner}", new_volume)
        if docker.json("volume", "inspect", new_volume)[0].get("Labels", {}).get(OWNERSHIP_LABEL) != owner:
            raise BackupError("Volume creation race or ownership mismatch")
        helper = docker.call("create", "--name", f"classroom-restore-{owner}", "--label",
            f"{OWNERSHIP_LABEL}={owner}", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--mount", f"type=volume,src={new_volume},dst=/data",
            "--entrypoint", "python", image_id, "-c", "import time; time.sleep(3600)").strip()
        owned_helper(docker, helper, owner, new_volume, image_id)
        docker.call("cp", str(root / "data") + os.sep + ".", f"{helper}:/data/.")
        owned_helper(docker, helper, owner, new_volume, image_id)
        import tempfile
        with tempfile.TemporaryDirectory(prefix="classroom-verify-", dir=root.parent) as temporary:
            audit = Path(temporary)
            require_private(audit)
            private_mkdir(audit / "data")
            docker.call("cp", f"{helper}:/data/.", audit / "data")
            privatize(audit)
            if inventory(audit / "data") != inventory(root / "data") or snapshot_stats(audit / "data") != manifest["stats"]:
                raise BackupError("Restored bytes or SQLite verification failed")
    except Exception:
        raise BackupError(f"Restore failed; target volume {new_volume} may exist and is retained for private diagnosis") from None
    finally:
        if helper:
            owned_helper(docker, helper, owner, new_volume, image_id)
            docker.call("rm", helper)
            if docker.call("container", "ls", "--all", "--quiet", "--no-trunc", "--filter", f"id={helper}").strip():
                raise BackupError("Restore helper removal unverified; target volume retained")
    return {"volume": new_volume, "counts": manifest["stats"]["counts"], "replay_files": manifest["stats"]["replay_files"]}


if __name__ == "__main__":
    raise SystemExit(main())
