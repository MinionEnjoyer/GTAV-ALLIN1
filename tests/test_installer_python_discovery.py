"""Run real CMD discovery without allowing prerequisite or game installation."""
import os
from pathlib import Path
import shutil
import subprocess
import venv

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows CMD entrypoint')


@pytest.mark.parametrize('version', ['Python312', 'Python313'])
def test_real_python_default_location_with_ampersand(tmp_path, version):
    app = tmp_path / 'installer & test'
    app.mkdir()
    shutil.copy2(ROOT / 'install.bat', app / 'install.bat')
    local = tmp_path / 'account & test'
    runtime = local / 'Programs' / 'Python' / version
    # Real interpreter/stdlib, no fake successful python executable.
    venv.EnvBuilder(with_pip=False).create(runtime)
    # Standard Python install layout uses python.exe at the root. A venv uses
    # Scripts; copy its launcher beside pyvenv.cfg to exercise the real layout.
    shutil.copy2(runtime / 'Scripts/python.exe', runtime / 'python.exe')
    env = os.environ.copy()
    env.update(LOCALAPPDATA=str(local),
               PATH=str(Path(os.environ['SystemRoot']) / 'System32'))
    result = subprocess.run([os.environ['COMSPEC'], '/d', '/c', 'call install.bat --check-python'],
                            cwd=app, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(runtime / 'python.exe') in result.stdout
    assert not (app / '.venv').exists()
    assert 'starting winget' not in (app / 'allin1.log').read_text()


def test_missing_python_check_is_non_mutating(tmp_path):
    shutil.copy2(ROOT / 'install.bat', tmp_path / 'install.bat')
    env = os.environ.copy()
    env.update(LOCALAPPDATA=str(tmp_path / 'empty'),
               PATH=str(Path(os.environ['SystemRoot']) / 'System32'))
    # Remove the real-machine search only in this copied fixture: CMD restores
    # ProgramFiles on startup, so environment overrides cannot isolate it.
    script = tmp_path / 'install.bat'
    script.write_text(script.read_text().replace(' "!ProgramFiles!\\Python*"', ''))
    result = subprocess.run([os.environ['COMSPEC'], '/d', '/c', 'call install.bat --check-python'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert 'was not found' in result.stdout
    assert 'starting winget' not in (tmp_path / 'allin1.log').read_text()
    assert not (tmp_path / '.venv').exists()


def test_prerequisite_install_requires_confirmation():
    script = (ROOT / 'install.bat').read_text()
    prompt = script.index('choice /c YN')
    assert prompt < script.index('winget install --exact')
    assert 'if errorlevel 2 (' in script[prompt:script.index('winget install --exact')]
    assert 'call :try_python "' not in script
    assert '"!ProgramFiles!\\Python*"' in script
