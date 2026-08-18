import hashlib
import json
import os
import struct

from allin1.health import consume_rpf_canary, scan_installation, sha256_file


def _write_pe(path, *, size=4096):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


def _game(tmp_path, enhanced=False):
    (tmp_path / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).touch()
    _write_pe(tmp_path / "ScriptHookV.dll"); _write_pe(tmp_path / "ScriptHookVDotNet.asi")
    _write_pe(tmp_path / ("OpenRPF.asi" if enhanced else "OpenIV.asi"))
    _write_pe(tmp_path / ("xinput1_4.dll" if enhanced else "dinput8.dll"))
    scripts = tmp_path / "scripts"; scripts.mkdir()
    _write_pe(scripts / "ALLIN1.dll")
    (scripts / "ALLIN1.version").write_text("0.2.0\n")
    return scripts


def test_healthy_install_and_checksum(tmp_path):
    scripts = _game(tmp_path)
    expected = hashlib.sha256((scripts / "ALLIN1.dll").read_bytes()).hexdigest()
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


def test_health_blocks_enhanced_openrpf_conflicts_and_incomplete_preview_pack(tmp_path):
    _game(tmp_path, enhanced=True)
    (tmp_path / "OpenIV.asi").write_bytes(b"legacy")
    preview = tmp_path / "mods/update/x64/dlcpacks/allin1_previews"
    preview.mkdir(parents=True)
    report = scan_installation(tmp_path)
    codes = {issue.code for issue in report.issues}
    assert {"rpf_loader_conflict", "preview_dlc_invalid"} <= codes
    assert not report.launch_safe


def test_health_accepts_complete_preview_pack(tmp_path):
    _game(tmp_path, enhanced=True)
    preview = tmp_path / "mods/update/x64/dlcpacks/allin1_previews"
    preview.mkdir(parents=True)
    (preview / "dlc.rpf").write_bytes(b"rpf")
    codes = {issue.code for issue in scan_installation(tmp_path).issues}
    assert "preview_dlc_invalid" not in codes


def test_health_rejects_empty_openrpf_and_missing_asi_loader(tmp_path):
    _game(tmp_path, enhanced=True)
    (tmp_path / "OpenRPF.asi").write_bytes(b"")
    (tmp_path / "xinput1_4.dll").unlink()
    codes = {issue.code for issue in scan_installation(tmp_path).issues}
    assert {"rpf_loader_corrupt", "asi_loader_missing"} <= codes


def test_health_rejects_placeholder_or_wrong_architecture_dependencies(tmp_path):
    scripts = _game(tmp_path, enhanced=True)
    (tmp_path / "ScriptHookV.dll").write_bytes(b"placeholder")
    payload = bytearray((scripts / "ALLIN1.dll").read_bytes())
    struct.pack_into("<H", payload, 0x84, 0x014C)
    (scripts / "ALLIN1.dll").write_bytes(payload)

    report = scan_installation(tmp_path)
    codes = {issue.code for issue in report.issues}
    assert {"dependency_corrupt", "mod_corrupt"} <= codes
    assert report.launch_safe is False


def test_health_blocks_rpf_archive_from_older_game_build(tmp_path):
    _game(tmp_path, enhanced=True)
    base = tmp_path / "update/update.rpf"
    mods = tmp_path / "mods/update/update.rpf"
    base.parent.mkdir(parents=True); mods.parent.mkdir(parents=True)
    base.write_bytes(b"new"); mods.write_bytes(b"old")
    os.utime(mods, ns=(1_000_000_000, 1_000_000_000))
    os.utime(base, ns=(5_000_000_000, 5_000_000_000))

    report = scan_installation(tmp_path)
    assert "rpf_mod_archive_stale" in {issue.code for issue in report.issues}
    assert not report.launch_safe


def test_health_ignores_allin1_backup_copies(tmp_path):
    _game(tmp_path)
    backup = tmp_path / "allin1_backups/Playtests/old/ALLIN1.dll"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"old")

    report = scan_installation(tmp_path)
    assert "duplicate_mod" not in {issue.code for issue in report.issues}


def test_health_blocks_quarantined_and_incomplete_allin1_rpf_packs(tmp_path):
    _game(tmp_path, enhanced=True)
    dlcpacks = tmp_path / "mods/update/x64/dlcpacks"
    smoke = dlcpacks / "allin1_smoke"
    broken = dlcpacks / "allin1_future"
    smoke.mkdir(parents=True)
    (smoke / "dlc.rpf").write_bytes(b"readable-but-runtime-unsafe")
    broken.mkdir()

    report = scan_installation(tmp_path)

    codes = {issue.code for issue in report.issues}
    assert {"rpf_pack_quarantined", "rpf_pack_incomplete"} <= codes
    assert report.launch_safe is False


def test_health_allows_exact_smoke_canary_once(tmp_path):
    _game(tmp_path, enhanced=True)
    archive = (
        tmp_path / "mods/update/x64/dlcpacks/allin1_smoke/dlc.rpf"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"schema-correct-canary")
    marker_path = tmp_path / "scripts/ALLIN1_colored_smoke_weapons.json"
    marker_path.write_text(json.dumps({
        "schema": 2,
        "pack_id": "allin1_smoke",
        "canary_state": "pending",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }))

    pending = scan_installation(tmp_path)
    pending_codes = {issue.code for issue in pending.issues}
    assert "rpf_pack_canary" in pending_codes
    assert "rpf_pack_quarantined" not in pending_codes
    assert pending.launch_safe is True

    assert consume_rpf_canary(tmp_path, "allin1_smoke") is True
    consumed = json.loads(marker_path.read_text())
    assert consumed["canary_state"] == "attempted"
    attempted = scan_installation(tmp_path)
    assert "rpf_pack_quarantined" in {
        issue.code for issue in attempted.issues
    }
    assert attempted.launch_safe is False


def test_health_rejects_smoke_canary_hash_mismatch(tmp_path):
    _game(tmp_path, enhanced=True)
    archive = (
        tmp_path / "mods/update/x64/dlcpacks/allin1_smoke/dlc.rpf"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"actual")
    (tmp_path / "scripts/ALLIN1_colored_smoke_weapons.json").write_text(
        json.dumps({
            "schema": 2,
            "pack_id": "allin1_smoke",
            "canary_state": "pending",
            "archive_sha256": hashlib.sha256(b"different").hexdigest(),
        })
    )

    report = scan_installation(tmp_path)
    assert "rpf_pack_quarantined" in {
        issue.code for issue in report.issues
    }
    assert report.launch_safe is False
