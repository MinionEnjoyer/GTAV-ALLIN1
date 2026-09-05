"""Shared test isolation for repository-local state."""

import pytest

import allin1.detector as detector


@pytest.fixture(autouse=True)
def isolate_detector_cache(tmp_path, monkeypatch):
    """Never let path detection tests overwrite the real .gta_path marker."""
    monkeypatch.setattr(detector, "_project_root", lambda: tmp_path)


@pytest.fixture(autouse=True)
def isolate_user_preferences_and_game_detection(tmp_path, monkeypatch, request):
    for name in ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path / "isolated-user" / name))
    monkeypatch.delenv("ALLIN1_GTA_PATH", raising=False)
    # Detector unit tests provide their own isolated registry and Steam fixtures.
    if request.node.path.name != "test_detector.py":
        monkeypatch.setattr(detector, "_detect_windows", lambda: None)
        monkeypatch.setattr(detector, "_detect_linux", lambda: None)
