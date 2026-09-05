from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from lxml import etree

import allin1.cli as cli
import allin1.map_canary as canary
import allin1.map_startup_canary as startup_canary
from allin1.generators import dlc_maps


def _game(tmp_path: Path, *, enhanced: bool = True) -> Path:
    game = tmp_path / "game"
    game.mkdir(parents=True)
    executable = "GTA5_Enhanced.exe" if enhanced else "GTA5.exe"
    (game / executable).write_bytes(b"exe")
    (game / "mods/update/update.rpf").parent.mkdir(parents=True)
    (game / "mods/update/update.rpf").write_bytes(b"mods update fixture")
    source = game / "update/x64/dlcpacks/mptuner/dlc.rpf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"mptuner fixture")
    return game


def _dlclist(items: list[str]) -> bytes:
    root = etree.Element("SMandatoryPacksData")
    paths = etree.SubElement(root, "Paths")
    for value in items:
        etree.SubElement(paths, "Item").text = value
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )


class FakeRpfTool:
    def __init__(self, payload: bytes, *, fail: str | None = None) -> None:
        self.payload = payload
        self.fail = fail
        self.commands: list[list[str]] = []

    def __call__(
        self, _patcher: Path, arguments: list[str | Path], *,
        operation: str, timeout: int = 600,
    ) -> None:
        del operation, timeout
        args = [str(value) for value in arguments]
        self.commands.append(args)
        command = args[0]
        if self.fail == command:
            raise RuntimeError(f"injected {command} failure")
        if command == "extract-entries":
            manifest = Path(args[3])
            output = Path(args[4])
            for raw in manifest.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                _source, destination = raw.split("\t", 1)
                path = output.joinpath(*destination.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                if destination.endswith("interiorProxies.meta"):
                    document = etree.Element("SInteriorOrderData")
                    etree.SubElement(document, "startFrom").set(
                        "value", "1116"
                    )
                    etree.SubElement(document, "filePathHash").set(
                        "value", "0"
                    )
                    proxies = etree.SubElement(document, "proxies")
                    etree.SubElement(proxies, "Item").text = (
                        "unrelated_proxy"
                    )
                    etree.SubElement(proxies, "Item").text = (
                        startup_canary.DAVIS_PROXY_NAME
                    )
                    path.write_bytes(etree.tostring(
                        document, xml_declaration=True, encoding="UTF-8",
                    ))
                else:
                    path.write_bytes(
                        ("rpf:" + destination).encode("utf-8")
                    )
        elif command == "build-dlc":
            Path(args[2]).write_bytes(b"davis canary archive")
        elif command == "extract-entry":
            Path(args[4]).write_bytes(self.payload)
        elif command == "register-dlc":
            root = etree.fromstring(self.payload)
            paths = root.find("Paths")
            assert paths is not None
            etree.SubElement(paths, "Item").text = canary.PACK_ENTRY
            self.payload = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8",
                pretty_print=True,
            )
        elif command == "replace-entry":
            self.payload = Path(args[4]).read_bytes()
        elif command in {"open-rpfs", "verify-map-dlc"}:
            return
        else:  # pragma: no cover - catches accidental scope expansion
            raise AssertionError(f"Unexpected RPF operation: {command}")


def _install_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail: str | None = None,
) -> tuple[Path, Path, FakeRpfTool, bytes, bytes]:
    game = _game(tmp_path)
    state = tmp_path / "state"
    patcher = tmp_path / "RpfPatcher.exe"
    patcher.write_bytes(b"tool")
    original_dlclist = _dlclist(["dlcpacks:/mpheist/"])
    original_pack = game / "mods/update/x64/dlcpacks/allin1_maps"
    original_pack.mkdir(parents=True)
    (original_pack / "dlc.rpf").write_bytes(b"quarantined full pack")
    (original_pack / "allin1_maps.active").write_text(
        "layout=pruned-local-v4-unregistered\n"
        "archive_registration=disabled\n",
        encoding="utf-8",
    )
    original_marker = (original_pack / "allin1_maps.active").read_bytes()
    tool = FakeRpfTool(original_dlclist, fail=fail)
    monkeypatch.setattr(canary, "_run_tool", tool)
    return game, state, tool, original_dlclist, original_marker


def test_davis_subset_has_zero_startup_rpfs_and_one_property_group(tmp_path):
    assets = tuple(
        asset for asset in dlc_maps.MAP_ASSETS
        if asset.change_set_key == "davis"
    )
    root = dlc_maps.create_dlc_pack(
        tmp_path, assets=assets, layout=dlc_maps.DEFERRED_PACK_LAYOUT,
    )

    topology = canary.inspect_davis_topology(root)

    assert topology["asset_count"] == 2
    assert topology["startup_rpf_enable_count"] == 0
    assert topology["groups"] == ["GROUP_STARTUP", "ALLIN1_MAP_DAVIS"]
    assert topology["changesets"] == [
        "ALLIN1_MAPS_AUTOGEN", "ALLIN1_MAPS_DAVIS",
    ]


def test_install_status_and_external_rollback_preserve_exact_state(
    tmp_path, monkeypatch,
):
    game, state, tool, original_dlclist, original_marker = _install_fixture(
        tmp_path, monkeypatch,
    )
    patcher = tmp_path / "RpfPatcher.exe"
    writes: list[str] = []
    real_write = canary._write_json_atomic

    def record_write(payload, destination):
        writes.append(Path(destination).name)
        real_write(payload, destination)

    monkeypatch.setattr(canary, "_write_json_atomic", record_write)

    receipt = canary.install_davis_registration_canary(
        game,
        confirmation=canary.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )

    destination = game / "mods/update/x64/dlcpacks/allin1_maps"
    assert receipt["status"] == "installed_registration_only"
    assert receipt["asset_count"] == 2
    assert receipt["startup_rpf_enable_count"] == 0
    assert receipt["native_host_installed"] is False
    assert receipt["native_group_execution_enabled"] is False
    assert receipt["gameconfig_changed"] is False
    assert writes[-1] == "install-receipt.json"
    assert (destination / "dlc.rpf").read_bytes() == b"davis canary archive"
    assert not (destination / canary.RUNTIME_RECEIPT).exists()
    assert all("gameconfig" not in " ".join(command).casefold()
               for command in tool.commands)
    assert [command[0] for command in tool.commands].count(
        "extract-entries"
    ) == 1
    extracted_manifest = (state / "davis-assets.tsv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(extracted_manifest) == 2
    assert all("mptuner" not in line.casefold() for line in extracted_manifest)
    assert any("dlc_int_01_tr.rpf" in line for line in extracted_manifest)
    assert any("int_placement_tr.rpf" in line for line in extracted_manifest)

    status = canary.read_davis_registration_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["registration_count"] == 1
    assert status["checks"]["native_host_absent"] is True
    assert status["checks"]["zero_startup_rpfs"] is True

    rolled_back = canary.rollback_davis_registration_canary(
        game,
        confirmation=canary.ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )

    assert rolled_back["status"] == "rolled_back"
    assert tool.payload == original_dlclist
    assert (destination / "dlc.rpf").read_bytes() == b"quarantined full pack"
    assert (destination / "allin1_maps.active").read_bytes() == original_marker
    assert canary.rollback_davis_registration_canary(
        game,
        confirmation=canary.ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    ) == rolled_back


def test_registration_failure_auto_restores_pack_and_dlclist(
    tmp_path, monkeypatch,
):
    game, state, tool, original_dlclist, original_marker = _install_fixture(
        tmp_path, monkeypatch, fail="register-dlc",
    )

    with pytest.raises(RuntimeError, match="injected register-dlc failure"):
        canary.install_davis_registration_canary(
            game,
            confirmation=canary.INSTALL_CONFIRMATION,
            state_root=state,
            patcher=tmp_path / "RpfPatcher.exe",
            process_probe=lambda: set(),
        )

    destination = game / "mods/update/x64/dlcpacks/allin1_maps"
    assert tool.payload == original_dlclist
    assert (destination / "dlc.rpf").read_bytes() == b"quarantined full pack"
    assert (destination / "allin1_maps.active").read_bytes() == original_marker
    assert not (state / "install-receipt.json").exists()


def test_install_fails_closed_for_legacy_running_game_and_native_host(
    tmp_path, monkeypatch,
):
    patcher = tmp_path / "RpfPatcher.exe"
    patcher.write_bytes(b"tool")
    legacy = _game(tmp_path / "legacy", enhanced=False)
    with pytest.raises(ValueError, match="Enhanced"):
        canary.install_davis_registration_canary(
            legacy,
            confirmation=canary.INSTALL_CONFIRMATION,
            state_root=tmp_path / "legacy-state",
            patcher=patcher,
            process_probe=lambda: set(),
        )

    game = _game(tmp_path / "enhanced")
    with pytest.raises(RuntimeError, match="must be closed"):
        canary.install_davis_registration_canary(
            game,
            confirmation=canary.INSTALL_CONFIRMATION,
            state_root=tmp_path / "running-state",
            patcher=patcher,
            process_probe=lambda: {"GTA5_Enhanced.exe"},
        )

    (game / "ALLIN1MapHost-Enhanced-DISABLED-SCAFFOLD.asi").write_bytes(
        b"host"
    )
    with pytest.raises(RuntimeError, match="experimental map host"):
        canary.install_davis_registration_canary(
            game,
            confirmation=canary.INSTALL_CONFIRMATION,
            state_root=tmp_path / "host-state",
            patcher=patcher,
            process_probe=lambda: set(),
        )


def test_receipt_has_no_machine_paths_and_status_detects_runtime_expansion(
    tmp_path, monkeypatch,
):
    game, state, _tool, _original_dlclist, _marker = _install_fixture(
        tmp_path, monkeypatch,
    )
    receipt = canary.install_davis_registration_canary(
        game,
        confirmation=canary.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=tmp_path / "RpfPatcher.exe",
        process_probe=lambda: set(),
    )
    serialized = json.dumps(receipt)
    assert str(tmp_path) not in serialized
    assert "nivea" not in serialized.casefold()

    runtime = game / "mods/update/x64/dlcpacks/allin1_maps" / canary.RUNTIME_RECEIPT
    runtime.write_text("{}", encoding="utf-8")
    status = canary.read_davis_registration_canary_status(
        game,
        state_root=state,
        patcher=tmp_path / "RpfPatcher.exe",
        process_probe=lambda: set(),
    )
    assert status["healthy"] is False
    assert status["checks"]["runtime_receipt_absent"] is False


def test_hidden_cli_requires_exact_authorization_before_calling_service(
    tmp_path, monkeypatch,
):
    game = _game(tmp_path)
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run")

    monkeypatch.setattr(
        canary, "install_davis_registration_canary", unexpected,
    )
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    runner = CliRunner()
    result = runner.invoke(
        cli.main,
        [
            "--config", str(tmp_path / "missing.toml"),
            "map-canary", "install", "--gta-path", str(game), "--yes",
            "--confirm-canary", "wrong",
        ],
    )

    assert result.exit_code != 0
    assert "requires --yes" in result.output
    assert called is False


def test_canary_source_has_no_native_execution_or_game_launch_surface():
    source = Path(canary.__file__).read_text(encoding="utf-8")
    assert "EXECUTE_CONTENT_CHANGESET" not in source
    assert "REVERT_CONTENT_CHANGESET" not in source
    assert "launch_gta" not in source
    assert "nativeCall" not in source
    assert '"register-dlc"' in source
    assert '"build-dlc"' in source


def test_streaming_v2_installs_exact_verified_davis_runtime_contract(
    tmp_path, monkeypatch,
):
    game, _v1_state, tool, original_dlclist, original_marker = (
        _install_fixture(tmp_path, monkeypatch)
    )
    state = tmp_path / "streaming-v2-state"
    patcher = tmp_path / "RpfPatcher.exe"

    receipt = canary.install_davis_streaming_canary(
        game,
        confirmation=canary.STREAMING_INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )

    destination = game / "mods/update/x64/dlcpacks/allin1_maps"
    runtime_path = destination / canary.RUNTIME_RECEIPT
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    expected_references = [
        asset.filename for asset in canary._davis_assets()
    ]
    assert receipt["status"] == "installed_streaming_verified"
    assert receipt["properties"] == ["davis"]
    assert receipt["native_group_execution_enabled"] is True
    assert runtime == {
        "schema": 2,
        "status": "verified",
        "package_id": "allin1.online-content",
        "pack_name": "allin1_maps",
        "edition": "enhanced",
        "layout": dlc_maps.DEFERRED_PACK_LAYOUT,
        "runtime_contract": "allin1-isolated-property-v1",
        "archive_bytes": (destination / "dlc.rpf").stat().st_size,
        "archive_sha256": canary._sha256(destination / "dlc.rpf"),
        "asset_count": 2,
        "startup_rpf_enable_count": 0,
        "properties": ["davis"],
        "declared_groups": ["GROUP_STARTUP", "ALLIN1_MAP_DAVIS"],
        "declared_changesets": [
            "ALLIN1_MAPS_AUTOGEN", "ALLIN1_MAPS_DAVIS",
        ],
        "groups": [{
            "property": "davis",
            "group": "ALLIN1_MAP_DAVIS",
            "changesets": ["ALLIN1_MAPS_DAVIS"],
            "references": expected_references,
            "routes": [{
                "changeset": "ALLIN1_MAPS_DAVIS",
                "requires_loading_screen": False,
                "use_cache_loader": False,
                "loading_screen_context": "",
                "files_to_invalidate": [],
                "files_to_disable": [],
                "files_to_enable": expected_references,
            }],
        }],
        "source_archives": runtime["source_archives"],
        "sources": runtime["sources"],
    }
    assert runtime["source_archives"] == [{
        "pack": "mptuner",
        "archive": "dlc.rpf",
        "source": "stock",
        "path": "update/x64/dlcpacks/mptuner/dlc.rpf",
        "size": (game / "update/x64/dlcpacks/mptuner/dlc.rpf").stat().st_size,
        "mtime_ns": (
            game / "update/x64/dlcpacks/mptuner/dlc.rpf"
        ).stat().st_mtime_ns,
        "sha256": canary._sha256(
            game / "update/x64/dlcpacks/mptuner/dlc.rpf"
        ),
    }]
    assert len(runtime["sources"]) == 2
    assert all(item["source_asset_bytes"] > 0 for item in runtime["sources"])
    assert all(len(item["source_asset_sha256"]) == 64
               for item in runtime["sources"])
    assert str(tmp_path) not in json.dumps(runtime)
    marker = (destination / dlc_maps.ACTIVE_MARKER).read_text(encoding="utf-8")
    assert f"receipt={canary.RUNTIME_RECEIPT}" in marker
    assert "runtime_contract=allin1-isolated-property-v1" in marker
    assert "property_scope=davis" in marker

    status = canary.read_davis_streaming_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["registration_count"] == 1
    assert all(status["checks"].values())

    rolled_back = canary.rollback_davis_streaming_canary(
        game,
        confirmation=canary.STREAMING_ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert rolled_back["status"] == "rolled_back"
    assert tool.payload == original_dlclist
    assert (destination / "dlc.rpf").read_bytes() == b"quarantined full pack"
    assert (destination / dlc_maps.ACTIVE_MARKER).read_bytes() == original_marker


def test_streaming_v2_runtime_tamper_is_unhealthy_and_blocks_rollback(
    tmp_path, monkeypatch,
):
    game, _state, _tool, _dlclist, _marker = _install_fixture(
        tmp_path, monkeypatch,
    )
    state = tmp_path / "streaming-v2-state"
    patcher = tmp_path / "RpfPatcher.exe"
    canary.install_davis_streaming_canary(
        game,
        confirmation=canary.STREAMING_INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    runtime = (
        game / "mods/update/x64/dlcpacks/allin1_maps"
        / canary.RUNTIME_RECEIPT
    )
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    payload["properties"] = ["davis", "harmony"]
    runtime.write_text(json.dumps(payload), encoding="utf-8")

    status = canary.read_davis_streaming_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is False
    assert status["checks"]["runtime_receipt_verified"] is False
    with pytest.raises(RuntimeError, match="changed after installation"):
        canary.rollback_davis_streaming_canary(
            game,
            confirmation=canary.STREAMING_ROLLBACK_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )


def test_streaming_v2_registration_failure_restores_exact_baseline(
    tmp_path, monkeypatch,
):
    game, _state, tool, original_dlclist, original_marker = _install_fixture(
        tmp_path, monkeypatch, fail="register-dlc",
    )
    state = tmp_path / "streaming-v2-state"

    with pytest.raises(RuntimeError, match="injected register-dlc failure"):
        canary.install_davis_streaming_canary(
            game,
            confirmation=canary.STREAMING_INSTALL_CONFIRMATION,
            state_root=state,
            patcher=tmp_path / "RpfPatcher.exe",
            process_probe=lambda: set(),
        )

    destination = game / "mods/update/x64/dlcpacks/allin1_maps"
    assert tool.payload == original_dlclist
    assert (destination / "dlc.rpf").read_bytes() == b"quarantined full pack"
    assert (destination / dlc_maps.ACTIVE_MARKER).read_bytes() == original_marker
    assert not (state / "install-receipt.json").exists()


def test_streaming_v2_checkpoint_and_cli_are_separate_and_fail_closed(
    tmp_path, monkeypatch,
):
    game = _game(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert canary._state_root(game) != canary._streaming_state_root(game)
    assert "DavisMapStreamingV2" in str(canary._streaming_state_root(game))

    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("streaming service must not run")

    monkeypatch.setattr(canary, "install_davis_streaming_canary", unexpected)
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        cli.main,
        [
            "--config", str(tmp_path / "missing.toml"),
            "map-canary", "streaming-install",
            "--gta-path", str(game), "--yes",
            "--confirm-canary", "wrong",
        ],
    )
    assert result.exit_code != 0
    assert "requires --yes" in result.output
    assert called is False


def test_streaming_receipt_refuses_loading_screen_or_broader_topology(tmp_path):
    assets = tuple(
        asset for asset in dlc_maps.MAP_ASSETS
        if asset.change_set_key == "davis"
    )
    root = dlc_maps.create_dlc_pack(
        tmp_path, assets=assets, layout=dlc_maps.DEFERRED_PACK_LAYOUT,
    )
    content = etree.parse(str(root / "content.xml"))
    loading = content.xpath(
        "//contentChangeSets/Item[changeSetName='ALLIN1_MAPS_DAVIS']/"
        "requiresLoadingScreen"
    )[0]
    loading.set("value", "true")
    content.write(
        str(root / "content.xml"), encoding="UTF-8", xml_declaration=True,
    )

    with pytest.raises(RuntimeError, match="topology failed closed"):
        canary.inspect_davis_topology(root)


def test_startup_v3_topology_is_two_rpfs_proxy_and_only_startup(tmp_path):
    assets = startup_canary._davis_assets()
    root = dlc_maps.create_dlc_pack(
        tmp_path,
        assets=assets,
        layout=dlc_maps.STARTUP_IPL_PACK_LAYOUT,
    )

    topology = startup_canary.inspect_davis_startup_topology(root)

    assert topology["asset_count"] == 3
    assert topology["startup_rpf_enable_count"] == 2
    assert topology["startup_file_enable_count"] == 3
    assert topology["changesets"] == ["ALLIN1_MAPS_AUTOGEN"]
    assert topology["groups"] == ["GROUP_STARTUP"]
    assert topology["custom_property_groups"] == []
    assert topology["group_map_binding"] is False
    assert [asset.file_type for asset in assets] == [
        "RPF_FILE", "RPF_FILE", "INTERIOR_PROXY_ORDER_FILE",
    ]
    content = (root / "content.xml").read_text(encoding="utf-8")
    setup = (root / "setup2.xml").read_text(encoding="utf-8")
    assert "ALLIN1_MAP_DAVIS" not in content + setup
    assert "GROUP_MAP" not in content + setup


def test_startup_v3_accepts_uppercase_sha256_fingerprints():
    assert startup_canary._is_sha256("ABCDEF0123456789" * 4) is True
    assert startup_canary._is_sha256("G" * 64) is False


def test_startup_v3_public_install_is_quarantined_before_mutation(tmp_path):
    state = tmp_path / "startup-v3-state"

    with pytest.raises(RuntimeError) as exc_info:
        startup_canary.install_davis_startup_canary(
            tmp_path / "not-a-game",
            confirmation=startup_canary.INSTALL_CONFIRMATION,
            state_root=state,
            patcher=tmp_path / "missing-patcher.exe",
            process_probe=lambda: {"GTA5_Enhanced.exe"},
        )

    message = str(exc_info.value)
    assert "quarantined after repeatable live GTA V Enhanced crashes" in message
    assert "write-to-null before SHVDNE or ALLIN1 initialized" in message
    assert "startup-status and startup-rollback remain available" in message
    assert not state.exists()


def test_startup_v3_historical_install_status_and_rollback_are_exact(
    tmp_path, monkeypatch,
):
    game, _old_state, tool, original_dlclist, original_marker = (
        _install_fixture(tmp_path, monkeypatch)
    )
    state = tmp_path / "startup-v3-state"
    patcher = tmp_path / "RpfPatcher.exe"

    receipt = startup_canary._install_davis_startup_canary_forensic(
        game,
        confirmation=startup_canary.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )

    destination = game / "mods/update/x64/dlcpacks/allin1_maps"
    runtime_path = destination / dlc_maps.RUNTIME_RECEIPT
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    references = [asset.filename for asset in startup_canary._davis_assets()]
    assert receipt["status"] == "installed_startup_ipl_verified"
    assert receipt["startup_rpf_enable_count"] == 2
    assert receipt["native_group_execution_enabled"] is False
    assert receipt["startup_archive_registration_enabled"] is True
    assert runtime["schema"] == 3
    assert runtime["canary_id"] == startup_canary.CANARY_ID
    assert runtime["runtime_contract"] == (
        "allin1-isolated-startup-ipl-v1"
    )
    assert runtime["layout"] == dlc_maps.STARTUP_IPL_PACK_LAYOUT
    assert runtime["activation"] == (
        "startup-file-registration-plus-request-ipl"
    )
    assert runtime["property_scope"] == "davis"
    assert runtime["properties"] == ["davis"]
    assert runtime["ipls"] == [
        "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_",
    ]
    assert runtime["archive_registration"] == "startup"
    assert runtime["asset_count"] == 3
    assert runtime["startup_rpf_enable_count"] == 2
    assert runtime["startup_file_enable_count"] == 3
    assert runtime["declared_changesets"] == ["ALLIN1_MAPS_AUTOGEN"]
    assert runtime["declared_groups"] == ["GROUP_STARTUP"]
    assert runtime["custom_property_groups"] == []
    assert runtime["group_map_binding"] is False
    assert runtime["groups"] == [{
        "group": "GROUP_STARTUP",
        "changesets": ["ALLIN1_MAPS_AUTOGEN"],
        "references": references,
    }]
    assert len(runtime["source_archives"]) == 1
    assert runtime["source_archives"][0]["path"] == (
        "update/x64/dlcpacks/mptuner/dlc.rpf"
    )
    assert len(runtime["sources"]) == 3
    assert runtime["proxy_filters"] == [{
        "destination_path": (
            "common/data/allin1/mptuner_davis_interiorProxies.meta"
        ),
        "proxy_names": [
            "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_",
        ],
        "start_from": 1117,
        "entry_count": 1,
    }]
    proxy_source = runtime["sources"][-1]
    assert proxy_source["source_path"] == "common/data/interiorProxies.meta"
    assert proxy_source["proxy_start_from"] == 1117
    assert proxy_source["source_asset_bytes"] > 0
    assert len(proxy_source["source_asset_sha256"]) == 64
    assert str(tmp_path) not in json.dumps(runtime)
    marker = (destination / dlc_maps.ACTIVE_MARKER).read_text(
        encoding="utf-8"
    )
    assert f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}" in marker
    assert "archive_registration=startup" in marker
    assert "activation=startup-file-registration-plus-request-ipl" in marker
    assert "startup_rpf_enable_count=2" in marker
    assert "startup_file_enable_count=3" in marker
    assert "reference_count=3" in marker
    assert "custom_property_groups=0" in marker

    status = startup_canary.read_davis_startup_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["registration_count"] == 1
    assert all(status["checks"].values())

    rolled_back = startup_canary.rollback_davis_startup_canary(
        game,
        confirmation=startup_canary.ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert rolled_back["status"] == "rolled_back"
    assert tool.payload == original_dlclist
    assert (destination / "dlc.rpf").read_bytes() == b"quarantined full pack"
    assert (destination / dlc_maps.ACTIVE_MARKER).read_bytes() == original_marker


def test_startup_v3_fails_closed_for_extra_asset_or_custom_group(tmp_path):
    assets = startup_canary._davis_assets()
    root = dlc_maps.create_dlc_pack(
        tmp_path,
        assets=assets,
        layout=dlc_maps.STARTUP_IPL_PACK_LAYOUT,
    )
    content = etree.parse(str(root / "content.xml"))
    data_files = content.xpath("//dataFiles")[0]
    extra = etree.SubElement(data_files, "Item")
    etree.SubElement(extra, "filename").text = "dlc_allin1_maps:/extra.rpf"
    etree.SubElement(extra, "fileType").text = "RPF_FILE"
    etree.SubElement(extra, "disabled").set("value", "true")
    content.write(
        str(root / "content.xml"), encoding="UTF-8", xml_declaration=True,
    )
    with pytest.raises(RuntimeError, match="topology failed closed"):
        startup_canary.inspect_davis_startup_topology(root)

    root = dlc_maps.create_dlc_pack(
        tmp_path / "custom-group",
        assets=assets,
        layout=dlc_maps.STARTUP_IPL_PACK_LAYOUT,
    )
    setup = etree.parse(str(root / "setup2.xml"))
    groups = setup.xpath("//contentChangeSetGroups")[0]
    group = etree.SubElement(groups, "Item")
    etree.SubElement(group, "NameHash").text = "ALLIN1_MAP_DAVIS"
    etree.SubElement(group, "ContentChangeSets")
    setup.write(
        str(root / "setup2.xml"), encoding="UTF-8", xml_declaration=True,
    )
    with pytest.raises(RuntimeError, match="topology failed closed"):
        startup_canary.inspect_davis_startup_topology(root)


def test_startup_v3_historical_registration_failure_restores_baseline(
    tmp_path, monkeypatch,
):
    game, _state, tool, original_dlclist, original_marker = _install_fixture(
        tmp_path, monkeypatch, fail="register-dlc",
    )
    state = tmp_path / "startup-v3-state"

    with pytest.raises(RuntimeError, match="injected register-dlc failure"):
        startup_canary._install_davis_startup_canary_forensic(
            game,
            confirmation=startup_canary.INSTALL_CONFIRMATION,
            state_root=state,
            patcher=tmp_path / "RpfPatcher.exe",
            process_probe=lambda: set(),
        )

    destination = game / "mods/update/x64/dlcpacks/allin1_maps"
    assert tool.payload == original_dlclist
    assert (destination / "dlc.rpf").read_bytes() == b"quarantined full pack"
    assert (destination / dlc_maps.ACTIVE_MARKER).read_bytes() == original_marker
    assert not (state / "install-receipt.json").exists()


def test_startup_v3_tamper_and_cli_authorization_fail_closed(
    tmp_path, monkeypatch,
):
    game, _state, _tool, _dlclist, _marker = _install_fixture(
        tmp_path, monkeypatch,
    )
    state = tmp_path / "startup-v3-state"
    patcher = tmp_path / "RpfPatcher.exe"
    startup_canary._install_davis_startup_canary_forensic(
        game,
        confirmation=startup_canary.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    runtime = (
        game / "mods/update/x64/dlcpacks/allin1_maps"
        / dlc_maps.RUNTIME_RECEIPT
    )
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    payload["declared_groups"] = ["GROUP_STARTUP", "ALLIN1_MAP_DAVIS"]
    runtime.write_text(json.dumps(payload), encoding="utf-8")
    status = startup_canary.read_davis_startup_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is False
    assert status["checks"]["runtime_receipt_verified"] is False
    with pytest.raises(RuntimeError, match="changed after installation"):
        startup_canary.rollback_davis_startup_canary(
            game,
            confirmation=startup_canary.ROLLBACK_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )

    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("v3 service must not run")

    monkeypatch.setattr(
        startup_canary, "install_davis_startup_canary", unexpected,
    )
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        cli.main,
        [
            "--config", str(tmp_path / "missing.toml"),
            "map-canary", "startup-install",
            "--gta-path", str(game), "--yes",
            "--confirm-canary", "wrong",
        ],
    )
    assert result.exit_code != 0
    assert "requires --yes" in result.output
    assert called is False
