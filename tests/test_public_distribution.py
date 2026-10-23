"""Public runtime archive contracts; no production containers are touched."""
import hashlib
import importlib.util
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def package_module():
    spec = importlib.util.spec_from_file_location('public_package', ROOT / 'scripts/package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_archive_is_pinned_reproducible_and_allowlisted(tmp_path):
    module = package_module()
    root = tmp_path / 'source'
    import shutil
    shutil.copytree(ROOT / 'distribution', root / 'distribution')
    (root / 'LICENSE').write_text('MIT')
    for name in ('.env', '.env.local', 'secret.txt', 'replays.json', 'classroom.db'):
        (root / 'distribution' / name).write_text('PRIVATE')
    output = tmp_path / 'out'
    args = (root, output, 'v1.0.0', 'sha256:' + 'a'*64, 'sha256:' + 'b'*64)
    first = module.package_runtime(*args)
    original = first.read_bytes()
    for file in (root / 'distribution').iterdir():
        if file.is_file():
            file.write_bytes(file.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    assert module.package_runtime(*args).read_bytes() == original
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert not any(n.endswith(('.env', '.db', 'secret.txt', 'replays.json')) for n in names)
        compose = archive.read('Pod-Racing-Classroom/compose.yaml').decode()
        assert 'app@sha256:' + 'a'*64 in compose
        assert 'bot@sha256:' + 'b'*64 in compose
        assert 'build:' not in compose
        assert 'checkpoint-only' in compose and '127.0.0.1' in compose
    assert hashlib.sha256(original).hexdigest() in (output / 'SHA256SUMS').read_text()


def test_runtime_rejects_mutable_images_and_shell_version(tmp_path):
    import pytest
    pkg = package_module()
    for version, app, bot in [('v1.0.0', 'latest', 'sha256:'+'b'*64),
                              ('v1.0.0;touch owned', 'sha256:'+'a'*64, 'sha256:'+'b'*64)]:
        with pytest.raises(ValueError):
            pkg.package_runtime(ROOT, tmp_path, version, app, bot)
    assert not list(tmp_path.glob('*.zip'))


def test_runtime_refuses_symlink_allowlist_member(tmp_path):
    import shutil
    import pytest
    root = tmp_path/'source'
    shutil.copytree(ROOT/'distribution', root/'distribution')
    (root/'LICENSE').write_text('MIT')
    private = tmp_path/'private'
    private.write_text('DO NOT EXPORT')
    launch = root/'distribution/Start.sh'
    launch.unlink()
    try:
        launch.symlink_to(private)
    except OSError:
        pytest.skip('Creating symlinks is not permitted by this Windows host')
    with pytest.raises(ValueError, match='Symlinks'):
        package_module().package_runtime(root, tmp_path/'out', 'v1.0.0', 'sha256:'+'a'*64, 'sha256:'+'b'*64)


def test_runtime_refuses_windows_junction_to_inside_tree(tmp_path):
    import os
    import shutil
    import subprocess
    import pytest
    if os.name != 'nt':
        pytest.skip('Windows junction-specific regression')
    root = tmp_path/'source'
    shutil.copytree(ROOT/'distribution', root/'payload')
    (root/'LICENSE').write_text('MIT')
    subprocess.run(['cmd.exe','/c','mklink','/J',str(root/'distribution'),str(root/'payload')],
                   capture_output=True, check=True)
    with pytest.raises(ValueError, match='Symlinks'):
        package_module().package_runtime(root, tmp_path/'out', 'v1.0.0', 'sha256:'+'a'*64, 'sha256:'+'b'*64)
