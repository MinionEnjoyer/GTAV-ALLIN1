from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from allin1.generators import dlc_maps


ROOT = Path(__file__).resolve().parents[1]
MAP_HOST = ROOT / "native" / "map-host"


def _native_allowlist() -> list[tuple[str, str, str, bool]]:
    pattern = re.compile(
        r'^ALLIN1_MAP_GROUP\([^,]+,\s*"([^"]+)",\s*"([^"]+)",'
        r'\s*"([^"]+)",\s*(true|false)\)$'
    )
    rows: list[tuple[str, str, str, bool]] = []
    for raw in (MAP_HOST / "include/allin1/map_host_allowlist.inc").read_text(
        encoding="utf-8"
    ).splitlines():
        match = pattern.match(raw.strip())
        if match:
            rows.append(
                (
                    match.group(1),
                    match.group(2),
                    match.group(3),
                    match.group(4) == "true",
                )
            )
    return rows


def test_native_map_host_allowlist_matches_generated_deferred_groups():
    native = _native_allowlist()
    generated = [
        (item.key, item.group_name, item.name, item.key == "yacht")
        for item in dlc_maps.MAP_CHANGESETS
    ]
    assert native == generated


def test_native_map_host_is_disabled_and_hash_free_by_default():
    cmake = (MAP_HOST / "CMakeLists.txt").read_text(encoding="utf-8")
    plugin = (MAP_HOST / "src/plugin_entry.cpp").read_text(encoding="utf-8")
    header = (MAP_HOST / "include/allin1/map_host.hpp").read_text(
        encoding="utf-8"
    )
    assert "ALLIN1_MAP_HOST_BUILD_DISABLED_SCRIPTHOOK_STUBS" in cmake
    assert re.search(
        r"option\(ALLIN1_MAP_HOST_BUILD_DISABLED_SCRIPTHOOK_STUBS\s+"
        r'"[^"]+"\s+OFF\)',
        cmake,
    )
    assert "HostOptions" in header and "bool enabled = false" in header
    assert "groupHash" not in header
    assert not re.search(r"0x[0-9A-Fa-f]{8,}", plugin)
    assert "nativeInit" not in plugin
    assert "nativePush64" not in plugin
    assert "nativeCall" not in plugin
    assert "SetEnabled(true)" not in plugin
    assert "Prepare(" not in plugin
    assert plugin.count("return false;") >= 2


def test_native_map_host_documents_verified_global_abi_without_wiring_it():
    readme = (MAP_HOST / "README.md").read_text(encoding="utf-8")
    plugin = (MAP_HOST / "src/plugin_entry.cpp").read_text(encoding="utf-8")

    assert "0x6BEDF5769AC2DC07" in readme
    assert "void EXECUTE_CONTENT_CHANGESET_GROUP_FOR_ALL(Hash hash)" in readme
    assert "0x3C1978285B036B25" in readme
    assert "void REVERT_CONTENT_CHANGESET_GROUP_FOR_ALL(Hash hash)" in readme
    assert "global group hash" in readme
    assert "live Enhanced" in readme
    assert "deliberately unwired" in plugin


def _resolve_sdk_layout(tmp_path: Path, sdk_root: Path) -> tuple[Path, Path]:
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is unavailable")

    script = tmp_path / "resolve-sdk.cmake"
    result = tmp_path / "resolved.txt"
    module = MAP_HOST / "cmake/ResolveScriptHookVSdk.cmake"
    script.write_text(
        'include("${MODULE}")\n'
        'allin1_resolve_scripthookv_sdk("${SDK_ROOT}" HEADER LIBRARY)\n'
        'file(WRITE "${RESULT_FILE}" "${HEADER}\\n${LIBRARY}\\n")\n',
        encoding="utf-8",
    )
    subprocess.run(
        [
            cmake,
            f"-DMODULE={module}",
            f"-DSDK_ROOT={sdk_root}",
            f"-DRESULT_FILE={result}",
            "-P",
            str(script),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = result.read_text(encoding="utf-8").splitlines()
    return Path(lines[0]), Path(lines[1])


def test_scripthook_sdk_resolver_prefers_stock_lib_directory(tmp_path):
    sdk = tmp_path / "SDK with spaces"
    header = sdk / "inc/main.h"
    stock_library = sdk / "lib/ScriptHookV.lib"
    flat_library = sdk / "ScriptHookV.lib"
    header.parent.mkdir(parents=True)
    stock_library.parent.mkdir(parents=True)
    header.write_text("// fixture", encoding="utf-8")
    stock_library.write_bytes(b"stock")
    flat_library.write_bytes(b"flat")

    resolved_header, resolved_library = _resolve_sdk_layout(tmp_path, sdk)

    assert resolved_header == header
    assert resolved_library == stock_library


def test_scripthook_sdk_resolver_accepts_flat_library_fallback(tmp_path):
    sdk = tmp_path / "flat-sdk"
    header = sdk / "inc/main.h"
    flat_library = sdk / "ScriptHookV.lib"
    header.parent.mkdir(parents=True)
    header.write_text("// fixture", encoding="utf-8")
    flat_library.write_bytes(b"flat")

    resolved_header, resolved_library = _resolve_sdk_layout(tmp_path, sdk)

    assert resolved_header == header
    assert resolved_library == flat_library


def test_scripthook_sdk_resolver_fails_closed_for_incomplete_sdk(tmp_path):
    sdk = tmp_path / "incomplete-sdk"
    sdk.mkdir()

    resolved_header, resolved_library = _resolve_sdk_layout(tmp_path, sdk)

    assert str(resolved_header) == "."
    assert str(resolved_library) == "."

    cmake = (MAP_HOST / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "if(NOT ALLIN1_SCRIPTHOOKV_MAIN_HEADER OR" in cmake
    assert "lib/ScriptHookV.lib" in cmake
    assert "flat fallback" in cmake


def test_native_map_host_is_not_part_of_public_release_inputs():
    release = (ROOT / "src/allin1/release.py").read_text(encoding="utf-8")
    assert "native/map-host" not in release
