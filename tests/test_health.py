import hashlib

from allin1.health import scan_installation, sha256_file


def _game(tmp_path, enhanced=False):
    (tmp_path / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).touch()
    (tmp_path / "ScriptHookV.dll").touch(); (tmp_path / "ScriptHookVDotNet.asi").touch()
    (tmp_path / ("OpenRPF.asi" if enhanced else "OpenIV.asi")).write_bytes(b"asi")
    (tmp_path / ("xinput1_4.dll" if enhanced else "dinput8.dll")).write_bytes(b"loader")
    scripts = tmp_path / "scripts"; scripts.mkdir()
    (scripts / "ALLIN1.dll").write_bytes(b"dll")
    (scripts / "ALLIN1.version").write_text("0.2.0\n")
    return scripts


def test_healthy_install_and_checksum(tmp_path):
    scripts = _game(tmp_path); expected = hashlib.sha256(b"dll").hexdigest()
    report = scan_installation(tmp_path, expected_hashes={"scripts/ALLIN1.dll": expected})
    assert report.launch_safe and report.edition == "legacy"
    assert report.installed_version == "0.2.0" and report.to_dict()["launch_safe"] is True
    assert sha256_file(scripts / "ALLIN1.dll") == expected


def test_health_finds_conflicts(tmp_path):
    scripts = _game(tmp_path, enhanced=True); (tmp_path / "OpenRPF.asi").unlink()
    (tmp_path / "ALLIN1.asi").touch(); (tmp_path / "PackfileLimitAdjuster.asi").touch()
    duplicate = tmp_path / "mods" / "ALLIN1.dll"; duplicate.parent.mkdir(); duplicate.touch()
    (scripts / "ALLIN1.version").write_text("bad")
    report = scan_installation(tmp_path, expected_hashes={"scripts/ALLIN1.dll": "0" * 64})
    codes = {issue.code for issue in report.issues}
    assert {"rpf_loader_missing", "duplicate_mod", "legacy_file", "review_conflict",
            "checksum_mismatch", "version_invalid"} <= codes
    assert not report.launch_safe


def test_health_unknown_empty_directory(tmp_path):
    report = scan_installation(tmp_path)
    assert report.edition == "unknown" and not report.launch_safe
    assert sum(issue.code == "dependency_missing" for issue in report.issues) == 2


def test_health_blocks_enhanced_openrpf_conflicts_and_legacy_preview_pack(tmp_path):
    _game(tmp_path, enhanced=True)
    (tmp_path / "OpenIV.asi").write_bytes(b"legacy")
    legacy = tmp_path / "mods/update/x64/dlcpacks/allin1_previews"
    legacy.mkdir(parents=True)
    report = scan_installation(tmp_path)
    codes = {issue.code for issue in report.issues}
    assert {"rpf_loader_conflict", "legacy_preview_dlc"} <= codes
    assert not report.launch_safe


def test_health_rejects_empty_openrpf_and_missing_asi_loader(tmp_path):
    _game(tmp_path, enhanced=True)
    (tmp_path / "OpenRPF.asi").write_bytes(b"")
    (tmp_path / "xinput1_4.dll").unlink()
    codes = {issue.code for issue in scan_installation(tmp_path).issues}
    assert {"rpf_loader_corrupt", "asi_loader_missing"} <= codes
