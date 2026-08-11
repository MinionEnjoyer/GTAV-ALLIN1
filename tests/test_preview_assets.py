"""Tests for importing screenshots produced by the in-game capture tool."""

import struct

import pytest

from allin1.preview_assets import PNG_SIGNATURE, merge_previews, png_dimensions


def _png(path, width=1920, height=1080):
    path.write_bytes(PNG_SIGNATURE + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height))


def test_png_dimensions_validates_header_and_dimensions(tmp_path):
    image = tmp_path / "car.png"
    _png(image, 800, 450)
    assert png_dimensions(image) == (800, 450)
    image.write_bytes(b"not png")
    with pytest.raises(ValueError, match="valid PNG"):
        png_dimensions(image)
    _png(image, 0, 1)
    with pytest.raises(ValueError, match="dimensions"):
        png_dimensions(image)


def test_merge_previews_filters_unknown_and_invalid_and_overrides(tmp_path):
    bundled = tmp_path / "bundled"
    captured = tmp_path / "captured"
    output = tmp_path / "output"
    bundled.mkdir()
    captured.mkdir()
    _png(bundled / "alpha.png", 640, 360)
    _png(captured / "ALPHA.png", 1920, 1080)
    (captured / "beta.png").write_bytes(b"broken")
    _png(captured / "not-a-model.png")

    result = merge_previews([bundled, captured], output, ["alpha", "beta", "gamma"])

    assert result.copied == 1
    assert png_dimensions(output / "alpha.png") == (1920, 1080)
    assert len(result.rejected) == 2
    assert result.missing == ("beta", "gamma")


def test_merge_previews_ignores_absent_sources(tmp_path):
    result = merge_previews([tmp_path / "missing"], tmp_path / "out", ["alpha"])
    assert result.copied == 0
    assert result.rejected == ()
    assert result.missing == ("alpha",)
