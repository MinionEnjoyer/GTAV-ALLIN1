"""Opt-in integration test for the real Windows preview packaging tools."""

import os
import platform
import struct
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from allin1.generators import dlc_previews, ytd_builder


@pytest.mark.windows_integration
def test_real_preview_toolchain_builds_nonempty_artifacts(tmp_path):
    if platform.system() != "Windows" or os.environ.get("ALLIN1_RUN_TOOL_INTEGRATION") != "1":
        pytest.skip("set ALLIN1_RUN_TOOL_INTEGRATION=1 on Windows")
    root = Path(__file__).resolve().parents[1]
    tools = root / "tools"
    rpf_patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        pytest.skip("RpfPatcher.exe has not been built")

    previews = tmp_path / "previews"
    previews.mkdir()
    # Use a real source image so the test verifies the BC3 payload visually,
    # not merely the resource and archive headers.
    bundled = root / "script" / "dist" / "previews"
    source = next(bundled.glob("*.png"))
    (previews / "alpha.png").write_bytes(source.read_bytes())
    built = ytd_builder.build_ytd_files(
        previews, None, tmp_path / "ytd", tools, ["alpha"]
    )
    assert built and built[0].stat().st_size > 0
    converted = subprocess.run(
        [str(rpf_patcher), "convert-gen9", str(built[0].parent)],
        capture_output=True, text=True, timeout=300,
    )
    assert converted.returncode == 0, converted.stderr
    unpacked = tmp_path / "unpacked"
    unpack = subprocess.run(
        [str(rpf_patcher), "unpack-ytd", str(built[0]), str(unpacked), "gen9"],
        capture_output=True, text=True, timeout=300,
    )
    assert unpack.returncode == 0, unpack.stderr
    with Image.open(source) as expected, Image.open(unpacked / "alpha.dds") as actual:
        expected_rgb = expected.convert("RGB")
        actual_rgb = actual.convert("RGB")
        assert actual_rgb.size == expected_rgb.size
        difference = ImageChops.difference(expected_rgb, actual_rgb)
        assert max(ImageStat.Stat(difference).mean) < 20
    dlc_root, staging = dlc_previews.create_dlc_pack(built, tmp_path / "dlc")
    assert (dlc_root / "content.xml").exists()
    assert list(staging.glob("*.ytd"))
    output = tmp_path / "dlc.rpf"
    result = subprocess.run([
        str(rpf_patcher), "build-dlc", str(dlc_root), str(output),
        "--embed-rpf", str(staging), "x64/textures/textures.rpf",
    ], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    assert output.stat().st_size > 0
