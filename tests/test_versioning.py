"""Version tracking tests."""

import io
import json

import pytest

from allin1.versioning import (
    fetch_latest_release,
    is_newer,
    normalize_version,
    read_installed_version,
    write_installed_version,
)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_normalize_and_compare_versions():
    assert normalize_version("v1.2.3") == (1, 2, 3, 0)
    assert normalize_version("1.2.3-beta.1") == (1, 2, 3, 0)
    assert is_newer("1.10.0", "1.9.9") is True
    assert is_newer("1.2.0", "1.2") is False
    with pytest.raises(ValueError):
        normalize_version("latest")


def test_installed_version_round_trip(tmp_path):
    assert read_installed_version(None) is None
    assert read_installed_version(tmp_path) is None
    marker = write_installed_version(tmp_path, "v2.3.4")
    assert marker.read_text() == "v2.3.4\n"
    assert read_installed_version(tmp_path) == "2.3.4"


def test_invalid_installed_version_is_reported(tmp_path):
    (tmp_path / "ALLIN1.version").write_text("broken")
    with pytest.raises(ValueError):
        read_installed_version(tmp_path)


def test_fetch_latest_release_uses_github_payload():
    payload = json.dumps({
        "tag_name": "v0.3.0",
        "html_url": "https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/tag/v0.3.0",
        "name": "More Story Mode content",
    }).encode()
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _Response(payload)

    release = fetch_latest_release("0.2.0", timeout=1.5, opener=opener)
    assert release.version == "0.3.0"
    assert release.update_available is True
    assert release.name == "More Story Mode content"
    assert seen["timeout"] == 1.5
    assert seen["url"].endswith("/releases/latest")
