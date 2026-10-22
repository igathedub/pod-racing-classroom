"""Reproducible source archive or digest-pinned, allowlisted Docker runtime ZIP."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import argparse
import hashlib
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {"arena", "web", "sandbox", "examples", "scripts", "tests"}
FILES = {"README.md", "README.de.md", "LICENSE", "SPEC.md", "pyproject.toml", "uv.lock", "launch.py", "Setup.cmd", "Start-classroom.cmd", "Docker-start.cmd", "Docker-start.sh", "Dockerfile", "compose.yaml", ".dockerignore", ".gitattributes", ".gitignore", "VERIFICATION.md"}
RUNTIME = ('Start.cmd', 'Stop.cmd', 'Start.command', 'Stop.command', 'Start.sh', 'Stop.sh',
           'classroom.sh', 'classroom.ps1', 'compose.yaml', 'compose.defaults', 'README.txt')


def private_path(path):
    parts = [part.lower() for part in Path(path).parts]
    return any(p in {'data', 'artifacts', '.venv', '.git', '__pycache__', 'node_modules',
                     '.pytest_cache', '.ruff_cache', 'teacher-private.log', '.classroom-project'} or p.startswith('.env') or
               any(word in p for word in ('secret', 'credential', 'replay', 'handoff', 'localreport', 'local-report', 'local_report'))
               for p in parts) or Path(path).suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.db-wal', '.db-shm', '.sqlite3-wal', '.sqlite3-shm', '.pyc', '.pem', '.key'}


def safe_file(root, relative):
    path = root / relative
    if any(p.is_symlink() or (getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
           for p in (path, *path.parents) if p != root.parent):
        raise ValueError('Symlinks/junctions are not distributable: ' + str(relative))
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes source tree')
    return path.read_bytes()


def write_zip(output, entries):
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, body in sorted(entries.items()):
            info = ZipInfo('Pod-Racing-Classroom/' + name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if name.endswith(('.sh', '.command')) else 0o100644) << 16
            archive.writestr(info, body)
    return output


def package_runtime(root, output, version, app_digest, bot_digest):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('Expected release version vMAJOR.MINOR.PATCH')
    if not all(re.fullmatch(r'sha256:[0-9a-f]{64}', d) for d in (app_digest, bot_digest)):
        raise ValueError('Both immutable multiarch image digests are required')
    entries = {name: safe_file(root, Path('distribution') / name).replace(b'\r\n', b'\n') for name in RUNTIME}
    for name in entries:
        if name.endswith('.cmd'):
            entries[name] = entries[name].replace(b'\n', b'\r\n')
    entries['compose.yaml'] = entries['compose.yaml'].replace(b'APP_DIGEST', app_digest.encode()).replace(b'BOT_DIGEST', bot_digest.encode())
    entries['LICENSE'] = safe_file(root, Path('LICENSE')).replace(b'\r\n', b'\n')
    entries['VERSION'] = (version + '\n').encode()
    archive = write_zip(output / ('Pod-Racing-Classroom-' + version + '.zip'), entries)
    (output / 'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='ascii')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--version', default='v1.0.0')
    parser.add_argument('--app-digest')
    parser.add_argument('--bot-digest')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts')
    args = parser.parse_args()
    if args.runtime:
        print(package_runtime(ROOT, args.output, args.version, args.app_digest or '', args.bot_digest or ''))
        return
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True).stdout
    entries = {}
    for raw in tracked.split(b'\0'):
        if not raw:
            continue
        name = raw.decode('utf-8')
        relative = Path(name)
        if private_path(relative) or (relative.parts[0] not in DIRECTORIES and name not in FILES):
            continue
        entries[name] = safe_file(ROOT, relative)
    print(write_zip(args.output / 'Pod-Racing-Classroom.zip', entries))


if __name__ == '__main__':
    main()
