"""Independent mod tests must never discover a real game or user profile."""
import pytest

import allin1.detector as detector


@pytest.fixture(autouse=True)
def isolated_machine(tmp_path, monkeypatch):
    monkeypatch.setattr(detector, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(detector, "_detect_windows", lambda: None)
    monkeypatch.setattr(detector, "_detect_linux", lambda: None)
    monkeypatch.delenv("ALLIN1_GTA_PATH", raising=False)
    for name in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / "isolated-user" / name))
