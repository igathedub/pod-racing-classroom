"""Generated launcher state must stay private even without a local database."""
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, check=True)


@pytest.mark.parametrize('name', ['teacher-private.log', '.classroom-project',
                                  'scripts/nested/teacher-private.log', 'scripts/nested/.classroom-project'])
@pytest.mark.parametrize('consumer', ['checker', 'package', 'gitignore'])
def test_generated_state_is_private_without_database(tmp_path, name, consumer):
    git(tmp_path, 'init', '-q')
    (tmp_path / 'scripts').mkdir()
    for script in ('check_distribution.py', 'package.py'):
        shutil.copyfile(ROOT / 'scripts' / script, tmp_path / 'scripts' / script)
    shutil.copyfile(ROOT / '.gitignore', tmp_path / '.gitignore')
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('PRIVATE-GENERATED-STATE\n')
    assert not (tmp_path / 'data').exists()
    if consumer == 'gitignore':
        result = subprocess.run(['git', '-C', str(tmp_path), 'check-ignore', name], capture_output=True, text=True)
        assert result.returncode == 0
        return
    git(tmp_path, 'add', '-f', name)
    if consumer == 'checker':
        result = subprocess.run([sys.executable, str(tmp_path / 'scripts/check_distribution.py')],
                                capture_output=True, text=True)
        assert result.returncode != 0
        assert 'Private/generated file is staged:' in result.stderr
        assert 'PRIVATE-GENERATED-STATE' not in result.stderr + result.stdout
    else:
        subprocess.run([sys.executable, str(tmp_path / 'scripts/package.py'), '--output', str(tmp_path / 'out')],
                       capture_output=True, text=True, check=True)
        with zipfile.ZipFile(tmp_path / 'out/Pod-Racing-Classroom.zip') as archive:
            assert 'Pod-Racing-Classroom/' + name not in archive.namelist()
            assert all(b'PRIVATE-GENERATED-STATE' not in archive.read(entry) for entry in archive.namelist())
