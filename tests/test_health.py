import hashlib
import json
import os
import struct

import pytest

import allin1.health as health
from allin1.health import (
    consume_rpf_canary,
    inspect_windows_binary,
    is_rpf_canary_authorized,
    scan_installation,
    scan_launch_hazards,
    sha256_file,
)


def _write_pe(path, *, size=4096, machine=0x8664):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, machine)
    path.write_bytes(payload)


def _game(tmp_path, enhanced=False):
    (tmp_path / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).touch()
    _write_pe(tmp_path / "ScriptHookV.dll")
    for name in health.SHVDN_REQUIRED_BINARIES:
        _write_pe(tmp_path / name)
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


def test_health_blocks_missing_reactor_only_backend_and_warns_for_auto(tmp_path):
    scripts = _game(tmp_path)
    config = (
        "[general]\n"
        "gta_path = 'auto'\n"
        "[traffic]\n"
        "[vehicles]\n"
        "[script]\n"
        "gbay_menu_enabled = true\n"
        "gbay_ui_backend = 'reactor'\n"
    )
    (scripts / "ALLIN1.toml").write_text(config, encoding="utf-8")

    report = scan_installation(tmp_path)
    issue = next(item for item in report.issues
                 if item.code == "gbay_reactor_unavailable")
    assert issue.severity == "error"
    assert report.launch_safe is False

    (scripts / "ALLIN1.toml").write_text(
        config.replace("'reactor'", "'auto'"), encoding="utf-8",
    )
    report = scan_installation(tmp_path)
    issue = next(item for item in report.issues
                 if item.code == "gbay_reactor_unavailable")
    assert issue.severity == "warning"
    assert report.launch_safe is True


@pytest.mark.parametrize(
    ("backend", "severity", "launch_safe"),
    (("reactor", "error", False), ("auto", "warning", True)),
)
def test_health_checks_selected_reactor_backend_when_legacy_alias_is_disabled(
    tmp_path, backend, severity, launch_safe,
):
    scripts = _game(tmp_path)
    (scripts / "ALLIN1.toml").write_text(
        "[general]\n[traffic]\n[vehicles]\n[script]\n"
        "gbay_menu_enabled = false\n"
        f"gbay_ui_backend = '{backend}'\n",
        encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issue = next(item for item in report.issues
                 if item.code == "gbay_reactor_unavailable")
    assert issue.severity == severity
    assert report.launch_safe is launch_safe


def test_health_does_not_require_reactor_for_legacy_backend(tmp_path):
    scripts = _game(tmp_path)
    (scripts / "ALLIN1.toml").write_text(
        "[general]\n[traffic]\n[vehicles]\n[script]\n"
        "gbay_menu_enabled = false\n"
        "gbay_ui_backend = 'legacy'\n",
        encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    assert not any(
        issue.code == "gbay_reactor_unavailable" for issue in report.issues
    )
    assert report.launch_safe is True


def test_health_accepts_anycpu_reactor_core_with_x64_script_and_bridge(tmp_path):
    scripts = _game(tmp_path)
    reactor = scripts / "ReactorV"
    reactor.mkdir()
    _write_pe(reactor / "ALLIN1.ReactorBridge.plugin")
    _write_pe(reactor / "RageWebUI.Script.dll")
    _write_pe(reactor / "RageWebUI.Core.dll", machine=0x014C)
    (reactor / "ReactorV.contract.json").write_text(json.dumps({
        "schema_version": 1,
        "product": "reactor-v",
        "runtime_version": "0.2.0",
        "extension_api_version": 1,
        "capabilities": [
            "story.menu-presentation",
            "story.menu-bound-parameters",
        ],
    }), encoding="utf-8")
    (scripts / "ALLIN1.toml").write_text(
        "[general]\n[traffic]\n[vehicles]\n[script]\n"
        "gbay_menu_enabled = true\n"
        "gbay_ui_backend = 'reactor'\n",
        encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    assert not any(issue.code == "gbay_reactor_unavailable"
                   for issue in report.issues)
    assert report.launch_safe is True


def test_health_blocks_older_reactor_contract_without_menu_presentation(tmp_path):
    scripts = _game(tmp_path)
    reactor = scripts / "ReactorV"
    reactor.mkdir()
    _write_pe(reactor / "ALLIN1.ReactorBridge.plugin")
    _write_pe(reactor / "RageWebUI.Script.dll")
    _write_pe(reactor / "RageWebUI.Core.dll", machine=0x014C)
    (reactor / "ReactorV.contract.json").write_text(json.dumps({
        "schema_version": 1,
        "product": "reactor-v",
        "extension_api_version": 1,
        "capabilities": ["story.menus"],
    }), encoding="utf-8")
    (scripts / "ALLIN1.toml").write_text(
        "[general]\n[traffic]\n[vehicles]\n[script]\n"
        "gbay_menu_enabled = true\n"
        "gbay_ui_backend = 'reactor'\n",
        encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issue = next(item for item in report.issues
                 if item.code == "gbay_reactor_unavailable")
    assert issue.severity == "error"
    assert issue.path.endswith("ReactorV.contract.json")
    assert report.launch_safe is False


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


def test_health_ignores_allin1_dll_copies_in_non_loading_backup_roots(tmp_path):
    _game(tmp_path, enhanced=True)
    for relative in (
        "allin1_backups/previous/ALLIN1.dll",
        ".reactorv-backups/session/quarantined/ALLIN1.dll",
    ):
        backup = tmp_path / relative
        backup.parent.mkdir(parents=True)
        backup.write_bytes(b"historical backup")

    report = scan_installation(tmp_path)

    assert "duplicate_mod" not in {item.code for item in report.issues}


def test_health_unknown_empty_directory(tmp_path):
    report = scan_installation(tmp_path)
    assert report.edition == "unknown" and not report.launch_safe
    assert sum(issue.code == "dependency_missing" for issue in report.issues) == 4


def test_health_blocks_incomplete_shvdn_runtime(tmp_path):
    _game(tmp_path)
    (tmp_path / "MinHook.x64.dll").unlink()

    report = scan_installation(tmp_path)

    issue = next(
        item for item in report.issues
        if item.code == "dependency_missing" and "MinHook.x64.dll" in item.message
    )
    assert issue.path.endswith("MinHook.x64.dll")
    assert report.launch_safe is False


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


def test_health_accepts_rageopenv_for_both_editions(tmp_path):
    for enhanced in (False, True):
        game = tmp_path / ("enhanced" if enhanced else "legacy")
        game.mkdir()
        _game(game, enhanced=enhanced)
        old_plugin = game / ("OpenRPF.asi" if enhanced else "OpenIV.asi")
        old_plugin.unlink()
        _write_pe(game / "RageOpenV.asi")

        codes = {issue.code for issue in scan_installation(game).issues}

        assert "rpf_loader_missing" not in codes
        assert "rpf_loader_corrupt" not in codes
        assert "rpf_loader_conflict" not in codes


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


def test_launch_hazard_scan_is_limited_to_blocking_rpf_roots(tmp_path):
    dlcpacks = tmp_path / "mods/update/x64/dlcpacks"
    (dlcpacks / "allin1_future").mkdir(parents=True)
    unrelated = tmp_path / "large-tree/deep/ALLIN1.dll"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"not inspected on launch")

    issues = scan_launch_hazards(tmp_path)

    assert [issue.code for issue in issues] == ["rpf_pack_incomplete"]


def _write_performance_isolation_state(
    gta_path, *, status="active", session="session-123", stage="baseline",
):
    root = gta_path / "allin1_backups/PerformanceIsolation"
    manifest = root / session / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "session_id": session,
        "current_stage": stage,
        "status": status,
    }), encoding="utf-8")
    (root / "active-session.json").write_text(json.dumps({
        "session_id": session,
        "manifest": str(manifest),
    }), encoding="utf-8")
    return manifest


def test_launch_hazard_blocks_active_performance_isolation_in_both_scans(
    tmp_path,
):
    _game(tmp_path, enhanced=True)
    manifest = _write_performance_isolation_state(
        tmp_path, session="20260829T164308389Z", stage="baseline",
    )

    issue = next(
        item for item in scan_launch_hazards(tmp_path)
        if item.code == "performance_isolation_active"
    )

    assert issue.severity == "error"
    assert "20260829T164308389Z" in issue.message
    assert "baseline" in issue.message
    assert "mod-matrix.ps1 -Action restore" in issue.message
    assert issue.path == str(manifest.resolve())
    report = scan_installation(tmp_path)
    assert "performance_isolation_active" in {
        item.code for item in report.issues
    }
    assert report.launch_safe is False


def test_launch_hazard_allows_inactive_performance_isolation_states(tmp_path):
    for status in ("inactive", "completed", "restored"):
        game = tmp_path / status
        game.mkdir()
        _write_performance_isolation_state(game, status=status)

        codes = {item.code for item in scan_launch_hazards(game)}

        assert "performance_isolation_active" not in codes
        assert "performance_isolation_invalid" not in codes


def test_launch_hazard_fails_closed_for_malformed_isolation_metadata(tmp_path):
    root = tmp_path / "allin1_backups/PerformanceIsolation"
    root.mkdir(parents=True)
    pointer = root / "active-session.json"
    pointer.write_text("{not-json", encoding="utf-8")

    issue = next(item for item in scan_launch_hazards(tmp_path)
                 if item.code == "performance_isolation_invalid")
    assert issue.severity == "error"
    assert issue.path == str(pointer)
    assert "mod-matrix.ps1 -Action restore" in issue.message

    manifest = root / "session-123/manifest.json"
    manifest.parent.mkdir()
    manifest.write_text("[]", encoding="utf-8")
    pointer.write_text(json.dumps({"manifest": str(manifest)}), encoding="utf-8")

    issue = next(item for item in scan_launch_hazards(tmp_path)
                 if item.code == "performance_isolation_invalid")
    assert "manifest is not a JSON object" in issue.message


def test_launch_hazard_rejects_manifest_path_traversal_without_reading_it(
    tmp_path,
):
    root = tmp_path / "allin1_backups/PerformanceIsolation"
    root.mkdir(parents=True)
    outside = tmp_path / "outside-manifest.json"
    outside.write_text(json.dumps({
        "status": "active",
        "session_id": "outside-session-must-not-be-read",
        "current_stage": "outside-stage-must-not-be-read",
    }), encoding="utf-8")
    pointer = root / "active-session.json"
    pointer.write_text(json.dumps({
        "manifest": str(root / ".." / ".." / "outside-manifest.json"),
    }), encoding="utf-8")

    issues = scan_launch_hazards(tmp_path)
    issue = next(item for item in issues
                 if item.code == "performance_isolation_invalid")

    assert issue.severity == "error"
    assert issue.path == str(pointer)
    assert "outside-session-must-not-be-read" not in issue.message
    assert not any(item.code == "performance_isolation_active"
                   for item in issues)


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


def test_binary_inspection_rejects_each_malformed_header(tmp_path):
    missing_signature = tmp_path / "missing-signature.dll"
    missing_signature.write_bytes(b"x" * 4096)
    assert inspect_windows_binary(missing_signature).reason == "missing DOS/PE signature"

    bad_offset = tmp_path / "bad-offset.dll"
    payload = bytearray(4096)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 1)
    bad_offset.write_bytes(payload)
    assert inspect_windows_binary(bad_offset).reason == "invalid PE header offset"

    bad_pe = tmp_path / "bad-pe.dll"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    bad_pe.write_bytes(payload)
    assert inspect_windows_binary(bad_pe).reason == "missing PE signature"


def test_binary_inspection_reports_unreadable_file(tmp_path, monkeypatch):
    target = tmp_path / "locked.dll"
    target.write_bytes(b"x" * 4096)
    original_open = type(target).open

    def fail_open(path, *args, **kwargs):
        if path == target:
            raise OSError("locked")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(type(target), "open", fail_open)
    assert "unreadable" in inspect_windows_binary(target).reason


def test_canary_rejects_bad_marker_hash_and_archive_read_failure(
    tmp_path, monkeypatch,
):
    archive = tmp_path / "mods/update/x64/dlcpacks/allin1_smoke/dlc.rpf"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"canary")
    marker = tmp_path / "scripts/ALLIN1_colored_smoke_weapons.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({
        "schema": 2, "pack_id": "allin1_smoke", "canary_state": "pending",
        "archive_sha256": 123,
    }))
    assert is_rpf_canary_authorized(tmp_path, "allin1_smoke", archive) is False

    payload = json.loads(marker.read_text())
    payload["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    marker.write_text(json.dumps(payload))
    monkeypatch.setattr(health, "sha256_file", lambda _path: (_ for _ in ()).throw(OSError("locked")))
    assert is_rpf_canary_authorized(tmp_path, "allin1_smoke", archive) is False


def test_consume_canary_handles_marker_race_and_write_failure(tmp_path, monkeypatch):
    archive = tmp_path / "mods/update/x64/dlcpacks/allin1_smoke/dlc.rpf"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"canary")
    marker = tmp_path / "scripts/ALLIN1_colored_smoke_weapons.json"
    marker.parent.mkdir()
    payload = {
        "schema": 2, "pack_id": "allin1_smoke", "canary_state": "pending",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    marker.write_text(json.dumps(payload))

    real_reader = health._read_canary_marker
    calls = 0

    def disappearing_marker(path):
        nonlocal calls
        calls += 1
        return real_reader(path) if calls == 1 else None

    monkeypatch.setattr(health, "_read_canary_marker", disappearing_marker)
    assert consume_rpf_canary(tmp_path, "allin1_smoke") is False

    monkeypatch.setattr(health, "_read_canary_marker", real_reader)
    path_type = type(marker)
    original_write = path_type.write_text

    def fail_temporary_write(path, *args, **kwargs):
        if path.name.endswith(".tmp"):
            raise OSError("read-only")
        return original_write(path, *args, **kwargs)

    monkeypatch.setattr(path_type, "write_text", fail_temporary_write)
    assert consume_rpf_canary(tmp_path, "allin1_smoke") is False


def test_health_flags_incomplete_standalone_map_pack(tmp_path):
    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    report = scan_installation(tmp_path)
    assert "standalone_map_dlc_invalid" in {issue.code for issue in report.issues}


def test_health_reports_unknown_map_layout_without_promising_streaming(tmp_path):
    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    (maps / "dlc.rpf").write_bytes(b"map archive")
    (maps / "allin1_maps.active").write_text(
        "layout=pruned-local-v3-deferred\n", encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issue = next(
        issue for issue in report.issues
        if issue.code == "standalone_map_dlc_outdated"
    )
    assert issue.severity == "warning"
    assert "Install / Repair" in issue.message
    assert "quarantine" in issue.message


def test_health_reports_unregistered_map_layout_as_safe_but_unavailable(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    (maps / "dlc.rpf").write_bytes(b"map archive")
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.PACK_LAYOUT}\n"
        "archive_registration=disabled\n", encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issues = {issue.code: issue for issue in report.issues}
    assert "standalone_map_dlc_outdated" not in issues
    issue = issues["standalone_map_dlc_unregistered"]
    assert issue.severity == "info"
    assert "safely excluded from startup registration" in issue.message
    assert "remain unavailable" in issue.message


def test_health_recognizes_guarded_davis_registration_canary(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    (maps / "dlc.rpf").write_bytes(b"davis registration canary")
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.DEFERRED_PACK_LAYOUT}\n"
        "archive_registration=property-groups\n"
        "activation=property-group-native-host-required\n"
        "asset_count=2\n",
        encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issues = {item.code: item for item in report.issues}
    assert "standalone_map_dlc_outdated" not in issues
    canary = issues["standalone_map_dlc_registration_canary"]
    assert canary.severity == "info"
    assert "zero startup RPF enables" in canary.message
    assert "remains dormant" in canary.message


def test_health_recognizes_isolated_davis_runtime_receipt(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    archive = maps / "dlc.rpf"
    archive.write_bytes(b"isolated davis runtime")
    archive_hash = "A" * 64
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.DEFERRED_PACK_LAYOUT}\n"
        "archive_registration=property-groups\n"
        "activation=property-group-native-host-required\n"
        "asset_count=2\n"
        f"receipt={dlc_maps.RUNTIME_RECEIPT}\n"
        "runtime_contract=allin1-isolated-property-v1\n"
        "property_scope=davis\n"
        f"archive_sha256={archive_hash}\n",
        encoding="utf-8",
    )
    (maps / dlc_maps.RUNTIME_RECEIPT).write_text(json.dumps({
        "schema": 2,
        "status": "verified",
        "package_id": "allin1.online-content",
        "pack_name": "allin1_maps",
        "edition": "enhanced",
        "layout": dlc_maps.DEFERRED_PACK_LAYOUT,
        "runtime_contract": "allin1-isolated-property-v1",
        "properties": ["davis"],
        "asset_count": 2,
        "startup_rpf_enable_count": 0,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_hash,
    }), encoding="utf-8")

    report = scan_installation(tmp_path)

    issues = {item.code: item for item in report.issues}
    ready = issues["davis_isolated_map_runtime_ready"]
    assert ready.severity == "info"
    assert "stream only Davis on demand" in ready.message
    assert "standalone_map_dlc_registration_canary" not in issues


def _stock_mptuner_bridge_health_fixture(tmp_path):
    from allin1 import map_stock_bridge_canary as bridge

    tmp_path.mkdir(parents=True, exist_ok=True)
    _game(tmp_path, enhanced=True)
    source = tmp_path / "update/x64/dlcpacks/mptuner/dlc.rpf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"effective stock mptuner metadata archive")
    source_stat = source.stat()
    archive = (
        tmp_path / "mods/update/x64/dlcpacks" /
        bridge.PACK_NAME / "dlc.rpf"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"zero-payload stock mptuner bridge")
    semantics = {
        "associated_maps": ["MO_JIM_L11"],
        "files_to_invalidate": [],
        "files_to_disable": [],
        "files_to_enable": list(bridge._EXPECTED_MAP_FILES),
        "requires_loading_screen": True,
        "loading_screen_context": "LOADINGSCREEN_CONTEXT_LAST_FRAME",
        "use_cache_loader": True,
    }
    source_attestation = {
        "pack": "mptuner",
        "archive": "dlc.rpf",
        "source": "stock",
        "path": "update/x64/dlcpacks/mptuner/dlc.rpf",
        "size": source_stat.st_size,
        "mtime_ns": source_stat.st_mtime_ns,
        "archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "content_xml_bytes": 4096,
        "content_xml_sha256": "1" * 64,
        "setup2_xml_bytes": 2048,
        "setup2_xml_sha256": "2" * 64,
        "device_name": "dlc_mpTuner",
        "device_name_sha256": hashlib.sha256(
            b"dlc_mpTuner"
        ).hexdigest(),
        "setup_order": 37,
        "stock_startup_group": "GROUP_STARTUP",
        "stock_startup_changeset": "MPTUNER_AUTOGEN",
        "stock_startup_changeset_sha256": "3" * 64,
        "stock_proxy": "dlc_mpTuner:/common/data/interiorProxies.meta",
        "stock_map_group": "GROUP_MAP",
        "stock_map_group_changesets": [
            "MPTUNER_MAP_UPDATE", "MPTUNER_MAP_UPDATE_NAVMESH_ONLY",
        ],
        "changeset_name": "MPTUNER_MAP_UPDATE",
        "changeset_sha256": "4" * 64,
        "official_semantics": semantics,
    }
    receipt = bridge._runtime_receipt(archive, source_attestation)
    receipt_path = archive.parent / bridge.RUNTIME_RECEIPT_NAME
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    marker_path = archive.parent / bridge.MARKER_NAME
    bridge._write_marker(marker_path, archive)
    return archive.parent, marker_path, receipt_path, receipt, source


def test_health_allows_exact_pending_stock_mptuner_phase_a_bridge(tmp_path):
    _stock_mptuner_bridge_health_fixture(tmp_path)

    launch_issues = {
        item.code: item for item in scan_launch_hazards(tmp_path)
    }

    ready = launch_issues["stock_mptuner_bridge_phase_a_ready"]
    assert ready.severity == "info"
    assert "metadata-only" in ready.message
    assert "dormant" in ready.message
    assert "stock_mptuner_bridge_phase_a_invalid" not in launch_issues
    report = scan_installation(tmp_path)
    assert report.launch_safe is True
    assert "stock_mptuner_bridge_phase_a_ready" in {
        item.code for item in report.issues
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "installed_boot_only_pending"),
        ("asset_count", 1),
        ("data_file_count", 1),
        ("activation", "property-group-native"),
        ("groups", [{
            "property": "davis",
            "group": "ALLIN1_STOCK_MPTUNER_DAVIS_V1",
            "changesets": ["MPTUNER_MAP_UPDATE"],
            "activation_enabled": True,
        }]),
        ("native_group_execution_enabled", True),
        ("runtime_ipl_requests_enabled", True),
        ("gameconfig_changed", True),
        ("native_host_installed", True),
    ),
)
def test_health_blocks_stock_mptuner_phase_a_receipt_authority_drift(
    tmp_path, field, value,
):
    _, _, receipt_path, receipt, _ = (
        _stock_mptuner_bridge_health_fixture(tmp_path)
    )
    receipt[field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"
    assert "stock_mptuner_bridge_phase_a_ready" not in issues


def test_health_blocks_stock_mptuner_phase_a_unknown_receipt_field(tmp_path):
    _, _, receipt_path, receipt, _ = (
        _stock_mptuner_bridge_health_fixture(tmp_path)
    )
    receipt["future_runtime_authority"] = "disabled"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"
    assert "stock_mptuner_bridge_phase_a_ready" not in issues


def test_health_blocks_stock_mptuner_phase_a_marker_registration_drift(
    tmp_path,
):
    _, marker_path, _, _, _ = _stock_mptuner_bridge_health_fixture(tmp_path)
    marker_path.write_text(
        marker_path.read_text(encoding="utf-8").replace(
            "archive_registration=metadata-only",
            "archive_registration=startup-assets",
        ),
        encoding="utf-8",
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"
    assert "stock_mptuner_bridge_phase_a_ready" not in issues


def test_health_blocks_stock_mptuner_phase_a_archive_or_payload_drift(tmp_path):
    root, _, _, _, _ = _stock_mptuner_bridge_health_fixture(tmp_path)
    (root / "unexpected_payload.rpf").write_bytes(b"must not be accepted")

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"

    (root / "unexpected_payload.rpf").unlink()
    (root / "dlc.rpf").write_bytes(b"changed after receipt")
    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"


def test_health_blocks_stock_mptuner_phase_a_source_or_host_drift(tmp_path):
    _, _, _, _, source = _stock_mptuner_bridge_health_fixture(tmp_path)
    source.write_bytes(b"mptuner changed after bridge attestation")

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"

    # Rebuild the exact fixture, then prove that installing a native host also
    # invalidates Phase A even though the receipt still says it is absent.
    other = tmp_path / "host"
    _stock_mptuner_bridge_health_fixture(other)
    (other / "CommunityMapHost.Experimental.asi").write_bytes(b"native host")
    issues = {item.code: item for item in scan_launch_hazards(other)}
    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"


@pytest.mark.parametrize("setup_order", (-1, 72, 100, True))
def test_health_blocks_stock_mptuner_phase_a_unsafe_setup_order(
    tmp_path, setup_order,
):
    _, _, receipt_path, receipt, _ = (
        _stock_mptuner_bridge_health_fixture(tmp_path)
    )
    receipt["source_attestation"]["setup_order"] = setup_order
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"
    assert "stock_mptuner_bridge_phase_a_ready" not in issues


def test_health_blocks_stock_mptuner_phase_a_missing_or_duplicate_metadata(
    tmp_path,
):
    _, marker_path, receipt_path, _, _ = (
        _stock_mptuner_bridge_health_fixture(tmp_path)
    )
    receipt_path.unlink()
    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"

    # Restore the fixture in a fresh root and append a duplicate security key;
    # the strict marker reader must not silently let the last value win.
    other = tmp_path / "duplicate"
    _, duplicate_marker, _, _, _ = _stock_mptuner_bridge_health_fixture(other)
    duplicate_marker.write_text(
        duplicate_marker.read_text(encoding="utf-8")
        + "native_group_execution_enabled=false\n",
        encoding="utf-8",
    )
    issues = {item.code: item for item in scan_launch_hazards(other)}
    assert issues["stock_mptuner_bridge_phase_a_invalid"].severity == "error"


def _promote_stock_mptuner_health_fixture_to_phase_b(tmp_path):
    from allin1 import map_stock_bridge_black_canary as phase_b

    root, _marker, _receipt_path, phase_a_receipt, _source = (
        _stock_mptuner_bridge_health_fixture(tmp_path)
    )
    archive = root / "dlc.rpf"
    phase_a_receipt.update({
        "transaction_id": "a" * 32,
        "archive_sha256": hashlib.sha256(
            archive.read_bytes()
        ).hexdigest().upper(),
        "marker_sha256": "b" * 64,
        "runtime_receipt_sha256": "c" * 64,
    })
    phase_a_receipt["source_attestation"]["archive_sha256"] = (
        phase_a_receipt["source_attestation"]["archive_sha256"].upper()
    )
    receipt = phase_b._runtime_receipt(
        archive, phase_a_receipt, "d" * 64,
    )
    (root / phase_b.RUNTIME_RECEIPT_NAME).write_text(
        json.dumps(receipt), encoding="utf-8",
    )
    (root / phase_b.MARKER_NAME).write_text(
        phase_b._marker_text(receipt), encoding="utf-8",
    )
    return root, receipt


def test_health_allows_exact_stock_mptuner_phase_b_contract(tmp_path):
    _promote_stock_mptuner_health_fixture_to_phase_b(tmp_path)

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    ready = issues["stock_mptuner_bridge_phase_b_ready"]
    assert ready.severity == "info"
    assert "black transition" in ready.message
    assert "Proximity activation remains disabled" in ready.message
    assert "stock_mptuner_bridge_phase_a_invalid" not in issues
    assert "stock_mptuner_bridge_phase_b_invalid" not in issues
    assert scan_installation(tmp_path).launch_safe is True


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("proximity_activation_enabled", True),
        ("black_transition_required", False),
        ("keep_resident", False),
        ("release_on_exit", True),
        ("activation_scope", "proximity"),
        ("native_host_installed", True),
    ),
)
def test_health_blocks_stock_mptuner_phase_b_authority_drift(
    tmp_path, field, value,
):
    from allin1 import map_stock_bridge_black_canary as phase_b

    root, receipt = _promote_stock_mptuner_health_fixture_to_phase_b(tmp_path)
    receipt[field] = value
    (root / phase_b.RUNTIME_RECEIPT_NAME).write_text(
        json.dumps(receipt), encoding="utf-8",
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues["stock_mptuner_bridge_phase_b_invalid"].severity == "error"
    assert "stock_mptuner_bridge_phase_b_ready" not in issues


def test_health_blocks_stock_mptuner_phase_b_unknown_field(tmp_path):
    from allin1 import map_stock_bridge_black_canary as phase_b

    root, receipt = _promote_stock_mptuner_health_fixture_to_phase_b(tmp_path)
    receipt["future_authority"] = False
    (root / phase_b.RUNTIME_RECEIPT_NAME).write_text(
        json.dumps(receipt), encoding="utf-8",
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues["stock_mptuner_bridge_phase_b_invalid"].severity == "error"


def _stock_mpheist_grapeseed_health_fixture(tmp_path):
    from allin1 import map_grapeseed_stock_bridge_canary as bridge

    tmp_path.mkdir(parents=True, exist_ok=True)
    if not (tmp_path / "GTA5_Enhanced.exe").is_file():
        _game(tmp_path, enhanced=True)
    source = tmp_path / "update/x64/dlcpacks/mpheist/dlc.rpf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"effective stock mpheist metadata archive")
    source_stat = source.stat()
    archive = (
        tmp_path / "mods/update/x64/dlcpacks" /
        bridge.PACK_NAME / "dlc.rpf"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"zero-payload stock mpheist Grapeseed bridge")
    source_attestation = {
        "pack": "mpheist",
        "archive": "dlc.rpf",
        "source": "stock",
        "path": "update/x64/dlcpacks/mpheist/dlc.rpf",
        "size": source_stat.st_size,
        "mtime_ns": source_stat.st_mtime_ns,
        "archive_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "content_xml_bytes": 4096,
        "content_xml_sha256": "1" * 64,
        "setup2_xml_bytes": 2048,
        "setup2_xml_sha256": "2" * 64,
        "device_name": bridge.STOCK_DEVICE,
        "device_name_sha256": hashlib.sha256(
            bridge.STOCK_DEVICE.encode("utf-8")
        ).hexdigest(),
        "setup_order": 10,
        "stock_startup_group": "GROUP_STARTUP",
        "stock_startup_changesets": list(
            bridge._EXPECTED_STOCK_GROUP_STARTUP
        ),
        "stock_startup_changeset": bridge.STOCK_STARTUP_CHANGESET,
        "stock_startup_changeset_sha256": "3" * 64,
        "stock_proxy": bridge.STOCK_PROXY,
        "stock_map_group": "GROUP_MAP",
        "stock_map_group_changesets": list(bridge._EXPECTED_STOCK_GROUP_MAP),
        "changeset_name": bridge.STOCK_CHANGESET,
        "changeset_sha256": "4" * 64,
        "official_semantics": {
            "associated_maps": ["MO_JIM_L11"],
            "files_to_invalidate": list(bridge._EXPECTED_MAP_INVALIDATIONS),
            "files_to_disable": [],
            "files_to_enable": list(bridge._EXPECTED_MAP_FILES),
            "requires_loading_screen": True,
            "loading_screen_context": "LOADINGSCREEN_CONTEXT_LAST_FRAME",
            "use_cache_loader": True,
        },
    }
    receipt = bridge._runtime_receipt(archive, source_attestation)
    receipt_path = archive.parent / bridge.RUNTIME_RECEIPT_NAME
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    marker_path = archive.parent / bridge.MARKER_NAME
    bridge._write_marker(marker_path, receipt)
    return archive.parent, marker_path, receipt_path, receipt, source


def _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(tmp_path):
    from allin1 import map_grapeseed_stock_bridge_black_canary as phase_b

    root, _marker, _receipt_path, phase_a_runtime, _source = (
        _stock_mpheist_grapeseed_health_fixture(tmp_path)
    )
    archive = root / "dlc.rpf"
    phase_a_install = {
        **phase_a_runtime,
        "transaction_id": "a" * 32,
        "archive_sha256": hashlib.sha256(
            archive.read_bytes()
        ).hexdigest().upper(),
        "marker_sha256": "B" * 64,
        "runtime_receipt_sha256": "C" * 64,
    }
    receipt = phase_b._runtime_receipt(
        archive, phase_a_install, "D" * 64,
    )
    (root / phase_b.RUNTIME_RECEIPT_NAME).write_text(
        json.dumps(receipt), encoding="utf-8",
    )
    (root / phase_b.MARKER_NAME).write_text(
        phase_b._marker_text(receipt), encoding="utf-8",
    )
    return root, receipt


def _stub_grapeseed_launch_registration(
    monkeypatch, tmp_path, entries,
):
    """Expose an exact extracted dlclist without creating developer state."""
    from allin1 import map_grapeseed_stock_bridge_canary as phase_a

    tool = tmp_path / "fake-rpf-patcher.exe"
    tool.write_bytes(b"test tool")
    items = "".join(f"<Item>{entry}</Item>" for entry in entries)
    payload = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<SMandatoryPacksData><Paths>"
        f"{items}"
        "</Paths></SMandatoryPacksData>"
    ).encode("utf-8")

    def current_dlclist(_game, _patcher, output):
        output.write_bytes(payload)
        return payload

    monkeypatch.setattr(phase_a, "_tool_path", lambda _patcher: tool)
    monkeypatch.setattr(phase_a, "_current_dlclist", current_dlclist)


def test_health_ignores_absent_stock_mpheist_grapeseed_bridge(tmp_path):
    _game(tmp_path, enhanced=True)

    issues = scan_launch_hazards(tmp_path)

    assert not any("mpheist_grapeseed_bridge" in item.code for item in issues)


def test_health_allows_exact_pending_stock_mpheist_grapeseed_phase_a(tmp_path):
    _stock_mpheist_grapeseed_health_fixture(tmp_path)

    launch_issues = {
        item.code: item for item in scan_launch_hazards(tmp_path)
    }

    ready = launch_issues[
        "stock_mpheist_grapeseed_bridge_phase_a_ready"
    ]
    assert ready.severity == "info"
    assert "metadata-only" in ready.message
    assert "dormant" in ready.message
    assert scan_installation(tmp_path).launch_safe is True


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("activation", "property-group-native"),
        ("property_scope", "davis"),
        ("stock_changesets", ["GROUP_MAP"]),
        ("ipls", ["different_ipl"]),
        ("groups", [{
            "property": "grapeseed",
            "group": "ALLIN1_STOCK_MPHEIST_GRAPESEED_V1",
            "changesets": ["MPHEIST_GTA5_CITYE_HOLLYWOOD_01"],
            "ipls": ["hei_hw1_blimp_interior_v_garagem_milo_"],
            "activation_enabled": True,
        }]),
        ("native_group_execution_enabled", True),
        ("runtime_ipl_requests_enabled", True),
        ("gameconfig_changed", True),
        ("native_host_installed", True),
    ),
)
def test_health_blocks_stock_mpheist_grapeseed_phase_a_authority_drift(
    tmp_path, field, value,
):
    _, _, receipt_path, receipt, _ = (
        _stock_mpheist_grapeseed_health_fixture(tmp_path)
    )
    receipt[field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_a_invalid"
    ].severity == "error"
    assert "stock_mpheist_grapeseed_bridge_phase_a_ready" not in issues


def test_health_blocks_stock_mpheist_grapeseed_phase_a_unknown_or_duplicate_field(
    tmp_path,
):
    _, _, receipt_path, receipt, _ = (
        _stock_mpheist_grapeseed_health_fixture(tmp_path)
    )
    receipt["future_runtime_authority"] = "disabled"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_a_invalid"
    ].severity == "error"

    other = tmp_path / "duplicate"
    _, _, duplicate_receipt, duplicate_payload, _ = (
        _stock_mpheist_grapeseed_health_fixture(other)
    )
    serialized = json.dumps(duplicate_payload)
    duplicate_receipt.write_text(
        serialized[:-1] + ',"native_host_installed":false}',
        encoding="utf-8",
    )
    issues = {item.code: item for item in scan_launch_hazards(other)}
    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_a_invalid"
    ].severity == "error"


def test_health_blocks_stock_mpheist_grapeseed_phase_a_layout_and_source_drift(
    tmp_path,
):
    root, _, _, _, source = _stock_mpheist_grapeseed_health_fixture(tmp_path)
    (root / "unexpected_payload.rpf").write_bytes(b"must not be accepted")
    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_a_invalid"
    ].severity == "error"

    other = tmp_path / "source"
    _, _, _, _, changed_source = _stock_mpheist_grapeseed_health_fixture(other)
    changed_source.write_bytes(b"mpheist identity changed after attestation")
    issues = {item.code: item for item in scan_launch_hazards(other)}
    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_a_invalid"
    ].severity == "error"

    # Ensure the first fixture's source is used, which also keeps linters from
    # mistaking this intentionally staged file for an unused fixture return.
    assert source.is_file()


def test_health_blocks_stock_mpheist_grapeseed_phase_a_legacy_and_map_host(
    tmp_path,
):
    _stock_mpheist_grapeseed_health_fixture(tmp_path)
    (tmp_path / "GTA5_Enhanced.exe").unlink()
    (tmp_path / "GTA5.exe").write_bytes(b"legacy")
    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_a_invalid"
    ].severity == "error"

    other = tmp_path / "host"
    _stock_mpheist_grapeseed_health_fixture(other)
    (other / "CommunityMapHost.Experimental.asi").write_bytes(b"native host")
    issues = {item.code: item for item in scan_launch_hazards(other)}
    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_a_invalid"
    ].severity == "error"


def test_health_allows_exact_stock_mpheist_grapeseed_phase_b(
    tmp_path, monkeypatch,
):
    from allin1 import map_grapeseed_stock_bridge_canary as phase_a

    _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(tmp_path)
    _stub_grapeseed_launch_registration(
        monkeypatch, tmp_path, ["dlcpacks:/mpheist/", phase_a.PACK_ENTRY],
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    ready = issues["stock_mpheist_grapeseed_bridge_phase_b_ready"]
    assert ready.severity == "info"
    assert "black transition" in ready.message
    assert "Proximity activation remains disabled" in ready.message
    assert "resident" in ready.message
    assert scan_installation(tmp_path).launch_safe is True


@pytest.mark.parametrize(
    ("entries", "failed_check"),
    (
        (["dlcpacks:/mpheist/"], "grapeseed_registration_exact"),
        (
            [
                "dlcpacks:/mpheist/",
                "dlcpacks:/allin1_mpheist_grapeseed_bridge/",
                "dlcpacks:/allin1_mpheist_grapeseed_bridge/",
            ],
            "grapeseed_registration_exact",
        ),
        (
            [
                "dlcpacks:/mpheist/",
                "dlcpacks:/allin1_mpheist_grapeseed_bridge/",
                "dlcpacks:/allin1_maps/",
            ],
            "retired_allin1_maps_entry_absent",
        ),
    ),
    ids=("missing", "duplicate", "retired"),
)
def test_health_blocks_grapeseed_phase_b_registration_drift(
    tmp_path, monkeypatch, entries, failed_check,
):
    _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(tmp_path)
    _stub_grapeseed_launch_registration(
        monkeypatch, tmp_path, entries,
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    invalid = issues["stock_mpheist_grapeseed_bridge_phase_b_invalid"]
    assert invalid.severity == "error"
    assert failed_check in invalid.message
    assert "stock_mpheist_grapeseed_bridge_phase_b_ready" not in issues


def test_health_blocks_grapeseed_phase_b_retired_pack_path(
    tmp_path, monkeypatch,
):
    from allin1 import map_grapeseed_stock_bridge_canary as phase_a
    from allin1 import map_grapeseed_stock_bridge_black_canary as phase_b

    _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(tmp_path)
    (tmp_path / "mods/update/x64/dlcpacks/allin1_maps").mkdir(
        parents=True,
    )
    _stub_grapeseed_launch_registration(
        monkeypatch, tmp_path, ["dlcpacks:/mpheist/", phase_a.PACK_ENTRY],
    )

    ready, _detail, checks = (
        phase_b.validate_phase_b_launch_registration_contract(tmp_path)
    )
    assert ready is False
    assert checks["retired_allin1_maps_paths_absent"] is False

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    invalid = issues["stock_mpheist_grapeseed_bridge_phase_b_invalid"]
    assert "retired allin1_maps pack is present" in invalid.message
    assert "stock_mpheist_grapeseed_bridge_phase_b_ready" not in issues


def test_health_allows_grapeseed_phase_b_with_unrelated_registration(
    tmp_path, monkeypatch,
):
    from allin1 import map_grapeseed_stock_bridge_canary as phase_a

    _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(tmp_path)
    _stub_grapeseed_launch_registration(
        monkeypatch,
        tmp_path,
        [
            "dlcpacks:/mpheist/",
            "dlcpacks:/unrelated_legitimate_mod/",
            phase_a.PACK_ENTRY,
        ],
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert "stock_mpheist_grapeseed_bridge_phase_b_ready" in issues
    assert "stock_mpheist_grapeseed_bridge_phase_b_invalid" not in issues


def test_health_grapeseed_phase_b_does_not_require_developer_state(
    tmp_path, monkeypatch,
):
    from allin1 import map_grapeseed_stock_bridge_canary as phase_a

    _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(tmp_path)
    developer_root = tmp_path / "absent-local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(developer_root))
    _stub_grapeseed_launch_registration(
        monkeypatch, tmp_path, ["dlcpacks:/mpheist/", phase_a.PACK_ENTRY],
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert "stock_mpheist_grapeseed_bridge_phase_b_ready" in issues
    assert not developer_root.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("activation_scope", "proximity"),
        ("property_scope", "davis"),
        ("proximity_activation_enabled", True),
        ("black_transition_required", False),
        ("keep_resident", False),
        ("release_on_exit", True),
        ("native_host_installed", True),
    ),
)
def test_health_blocks_stock_mpheist_grapeseed_phase_b_authority_drift(
    tmp_path, field, value,
):
    root, receipt = _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(
        tmp_path,
    )
    receipt[field] = value
    from allin1 import map_grapeseed_stock_bridge_black_canary as phase_b
    (root / phase_b.RUNTIME_RECEIPT_NAME).write_text(
        json.dumps(receipt), encoding="utf-8",
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_b_invalid"
    ].severity == "error"
    assert "stock_mpheist_grapeseed_bridge_phase_a_invalid" not in issues


def test_health_keeps_corrupt_stock_mpheist_grapeseed_phase_b_classification(
    tmp_path,
):
    root, _ = _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(
        tmp_path,
    )
    from allin1 import map_grapeseed_stock_bridge_black_canary as phase_b
    receipt_path = root / phase_b.RUNTIME_RECEIPT_NAME
    receipt_path.write_text(
        '{"canary_id":"' + phase_b.CANARY_ID + '", broken',
        encoding="utf-8",
    )

    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}

    assert issues[
        "stock_mpheist_grapeseed_bridge_phase_b_invalid"
    ].severity == "error"
    assert "stock_mpheist_grapeseed_bridge_phase_a_invalid" not in issues


def test_health_grapeseed_launch_scan_never_uses_full_source_hash(
    tmp_path, monkeypatch,
):
    from allin1 import map_grapeseed_stock_bridge_canary as phase_a

    _stock_mpheist_grapeseed_health_fixture(tmp_path)

    def forbidden_full_source_hash(*_args, **_kwargs):
        raise AssertionError("launch health attempted the full mpheist SHA")

    monkeypatch.setattr(
        phase_a, "_source_attestation_current", forbidden_full_source_hash,
    )
    issues = {item.code: item for item in scan_launch_hazards(tmp_path)}
    assert "stock_mpheist_grapeseed_bridge_phase_a_ready" in issues

    other = tmp_path / "phase-b"
    _promote_stock_mpheist_grapeseed_health_fixture_to_phase_b(other)
    _stub_grapeseed_launch_registration(
        monkeypatch, other, ["dlcpacks:/mpheist/", phase_a.PACK_ENTRY],
    )
    issues = {item.code: item for item in scan_launch_hazards(other)}
    assert "stock_mpheist_grapeseed_bridge_phase_b_ready" in issues


def test_health_reports_davis_and_grapeseed_bridges_independently(tmp_path):
    _stock_mptuner_bridge_health_fixture(tmp_path)
    _stock_mpheist_grapeseed_health_fixture(tmp_path)

    codes = {item.code for item in scan_launch_hazards(tmp_path)}

    assert "stock_mptuner_bridge_phase_a_ready" in codes
    assert "stock_mpheist_grapeseed_bridge_phase_a_ready" in codes


def _davis_startup_ipl_health_fixture(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    archive = maps / "dlc.rpf"
    archive.write_bytes(b"exact isolated Davis startup IPL archive")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    davis_ipl = (
        "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_"
    )
    references = [
        "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/"
        "dlc_int_01_tr.rpf",
        "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/"
        "int_placement_tr.rpf",
        "dlc_allin1_maps:/common/data/allin1/"
        "mptuner_davis_interiorProxies.meta",
    ]
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n"
        "archive_registration=startup\n"
        "group_map_binding=false\n"
        "activation=startup-file-registration-plus-request-ipl\n"
        "asset_count=3\n"
        "startup_rpf_enable_count=2\n"
        "startup_file_enable_count=3\n"
        "reference_count=3\n"
        f"receipt={dlc_maps.RUNTIME_RECEIPT}\n"
        "runtime_contract=allin1-isolated-startup-ipl-v1\n"
        "property_scope=davis\n"
        "custom_property_groups=0\n"
        f"archive_bytes={archive.stat().st_size}\n"
        f"archive_sha256={archive_hash}\n",
        encoding="utf-8",
    )
    receipt = {
        "schema": 3,
        "status": "verified",
        "canary_id": "davis-enhanced-isolated-startup-ipl-v3",
        "package_id": "allin1.online-content",
        "pack_name": "allin1_maps",
        "edition": "enhanced",
        "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
        "runtime_contract": "allin1-isolated-startup-ipl-v1",
        "archive_registration": "startup",
        "activation": "startup-file-registration-plus-request-ipl",
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_hash,
        "asset_count": 3,
        "startup_rpf_enable_count": 2,
        "startup_file_enable_count": 3,
        "property_scope": "davis",
        "properties": ["davis"],
        "ipls": [davis_ipl],
        "declared_changesets": ["ALLIN1_MAPS_AUTOGEN"],
        "declared_groups": ["GROUP_STARTUP"],
        "groups": [{
            "group": "GROUP_STARTUP",
            "changesets": ["ALLIN1_MAPS_AUTOGEN"],
            "references": references,
        }],
        "custom_property_groups": [],
        "group_map_binding": False,
        "source_archives": [{
            "pack": "mptuner",
            "archive": "dlc.rpf",
            "source": "stock",
            "path": "update/x64/dlcpacks/mptuner/dlc.rpf",
            "size": 8192,
            "mtime_ns": 123456789,
            "sha256": "b" * 64,
        }],
        "sources": [
            {
                "source_pack": "mptuner",
                "source_archive": "dlc.rpf",
                "source_path": (
                    "x64/levels/gta5/interiors/dlc_int_01_tr.rpf"
                ),
                "destination_path": (
                    "x64/levels/gta5/interiors/dlc_int_01_tr.rpf"
                ),
                "source_asset_bytes": 1024,
                "source_asset_sha256": "c" * 64,
            },
            {
                "source_pack": "mptuner",
                "source_archive": "dlc.rpf",
                "source_path": (
                    "x64/levels/gta5/interiors/int_placement_tr.rpf"
                ),
                "destination_path": (
                    "x64/levels/gta5/interiors/int_placement_tr.rpf"
                ),
                "source_asset_bytes": 1024,
                "source_asset_sha256": "d" * 64,
            },
            {
                "source_pack": "mptuner",
                "source_archive": "dlc.rpf",
                "source_path": "common/data/interiorProxies.meta",
                "destination_path": (
                    "common/data/allin1/"
                    "mptuner_davis_interiorProxies.meta"
                ),
                "source_asset_bytes": 1024,
                "source_asset_sha256": "e" * 64,
                "proxy_names": [davis_ipl],
                "proxy_start_from": 1117,
            },
        ],
        "proxy_filters": [{
            "destination_path": (
                "common/data/allin1/"
                "mptuner_davis_interiorProxies.meta"
            ),
            "proxy_names": [davis_ipl],
            "start_from": 1117,
            "entry_count": 1,
        }],
    }
    receipt_path = maps / dlc_maps.RUNTIME_RECEIPT
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return maps, receipt_path, receipt


def test_health_blocks_even_exact_davis_startup_ipl_v3_receipt(tmp_path):
    _davis_startup_ipl_health_fixture(tmp_path)

    report = scan_installation(tmp_path)

    issues = {item.code: item for item in report.issues}
    unsafe = issues["standalone_map_dlc_unsafe_registration"]
    assert unsafe.severity == "error"
    assert "exact, receipt-verified" in unsafe.message
    assert "repeatable live GTA V Enhanced crashes" in unsafe.message
    assert "write-to-null before SHVDNE or ALLIN1" in unsafe.message
    assert "davis_isolated_startup_ipl_ready" not in issues
    assert report.launch_safe is False


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("properties", ["davis", "yacht"]),
        ("ipls", ["tr_int_placement_tr_interior_0_wrong"]),
        ("declared_groups", ["GROUP_STARTUP", "ALLIN1_MAP_DAVIS"]),
        ("custom_property_groups", ["ALLIN1_MAP_DAVIS"]),
        ("archive_sha256", "0" * 64),
    ),
)
def test_health_blocks_davis_startup_ipl_v3_receipt_scope_drift(
    tmp_path, field, invalid_value,
):
    _, receipt_path, receipt = _davis_startup_ipl_health_fixture(tmp_path)
    receipt[field] = invalid_value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = scan_installation(tmp_path)

    issues = {item.code: item for item in report.issues}
    assert "davis_isolated_startup_ipl_ready" not in issues
    assert issues["standalone_map_dlc_unsafe_registration"].severity == "error"
    assert report.launch_safe is False


def test_health_blocks_davis_startup_ipl_v3_reference_expansion(tmp_path):
    _, receipt_path, receipt = _davis_startup_ipl_health_fixture(tmp_path)
    receipt["groups"][0]["references"].append(
        "dlc_allin1_maps:/%PLATFORM%/levels/gta5/yacht/extra.rpf"
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = scan_installation(tmp_path)

    issues = {item.code: item for item in report.issues}
    assert "davis_isolated_startup_ipl_ready" not in issues
    assert issues["standalone_map_dlc_unsafe_registration"].severity == "error"
    assert report.launch_safe is False


def test_health_blocks_davis_startup_ipl_v3_provenance_drift(tmp_path):
    _, receipt_path, receipt = _davis_startup_ipl_health_fixture(tmp_path)
    receipt["sources"][2]["destination_path"] = (
        "common/data/allin1/unfiltered_interiorProxies.meta"
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    report = scan_installation(tmp_path)

    issues = {item.code: item for item in report.issues}
    assert "davis_isolated_startup_ipl_ready" not in issues
    assert issues["standalone_map_dlc_unsafe_registration"].severity == "error"
    assert report.launch_safe is False


def test_health_reports_legacy_monolithic_as_outdated(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=False)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    (maps / "dlc.rpf").write_bytes(b"map archive")
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.LEGACY_PACK_LAYOUT}\n", encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issues = {issue.code: issue for issue in report.issues}
    issue = issues["standalone_map_dlc_outdated"]
    assert issue.severity == "warning"
    assert "quarantine" in issue.message


def test_health_rejects_legacy_monolithic_layout_on_enhanced(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    (maps / "dlc.rpf").write_bytes(b"map archive")
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.LEGACY_PACK_LAYOUT}\n", encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issues = {issue.code: issue for issue in report.issues}
    assert "standalone_map_dlc_legacy_monolithic" not in issues
    assert issues["standalone_map_dlc_outdated"].severity == "warning"


def test_health_blocks_deprecated_startup_registered_map_layout(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    (maps / "dlc.rpf").write_bytes(b"map archive")
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n"
        "archive_registration=startup\n", encoding="utf-8",
    )

    report = scan_installation(tmp_path)

    issue = next(
        item for item in report.issues
        if item.code == "standalone_map_dlc_unsafe_registration"
    )
    assert issue.severity == "error"
    assert report.launch_safe is False


def test_health_blocks_even_verified_startup_registered_map_layout(tmp_path):
    from allin1.generators import dlc_maps

    _game(tmp_path, enhanced=True)
    maps = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    maps.mkdir(parents=True)
    archive = maps / "dlc.rpf"
    archive.write_bytes(b"verified map archive")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    gameconfig_hash = hashlib.sha256(b"full gameconfig").hexdigest()
    (maps / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n"
        "archive_registration=startup\n"
        "activation=verified-startup-registration\n"
        f"receipt={dlc_maps.RUNTIME_RECEIPT}\n"
        "asset_count=15\n"
        f"archive_bytes={archive.stat().st_size}\n"
        f"archive_sha256={archive_hash}\n"
        f"gameconfig_sha256={gameconfig_hash}\n",
        encoding="utf-8",
    )
    (maps / dlc_maps.RUNTIME_RECEIPT).write_text(json.dumps({
        "schema": 1,
        "status": "verified",
        "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
        "edition": "enhanced",
        "gameconfig_entry": "common/data/gameconfig.xml",
        "asset_count": 15,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_hash,
        "gameconfig_sha256": gameconfig_hash,
        "pools": {"FragmentStore": {"before": 42000, "after": 52000}},
    }), encoding="utf-8")

    report = scan_installation(tmp_path)

    issues = {issue.code: issue for issue in report.issues}
    issue = issues["standalone_map_dlc_unsafe_registration"]
    assert issue.severity == "error"
    assert "quarantined" in issue.message
    assert report.launch_safe is False
