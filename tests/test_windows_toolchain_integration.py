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
        pytest.fail("Opt-in toolchain check requires a built RpfPatcher.exe")

    previews = tmp_path / "previews"
    previews.mkdir()
    # An asymmetric deterministic pixel fixture catches corrupt scanlines and
    # channel swaps without depending on the retired bundled artwork folder or
    # downloading the optional default-preview pack.
    source = previews / "alpha.png"
    fixture = Image.new("RGB", (128, 64))
    fixture.putdata([
        (x * 2, y * 4, 220 if x < 48 and y > 24 else 30)
        for y in range(64) for x in range(128)
    ])
    fixture.save(source)
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
    assert struct.unpack("<I", output.read_bytes()[:4])[0] == 0x52504637
