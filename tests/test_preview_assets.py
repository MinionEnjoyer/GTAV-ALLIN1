"""Tests for importing screenshots produced by the in-game capture tool."""

import struct

import pytest
from PIL import Image, ImageDraw

from allin1.preview_assets import audit_previews, inspect_preview, merge_previews, png_dimensions


def _png(path, width=1920, height=1080):
    if width < 1 or height < 1:
        path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height))
        return
    image = Image.new("RGBA", (width, height), (30, 30, 30, 255))
    ImageDraw.Draw(image).rectangle((width // 4, height // 4, width * 3 // 4, height * 3 // 4), fill=(210, 80, 40, 255))
    image.save(path)


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


def test_preview_quality_rejects_blank_transparent_and_small_images(tmp_path):
    blank = tmp_path / "blank.png"
    Image.new("RGBA", (800, 450), (0, 0, 0, 255)).save(blank)
    assert "low contrast" in " ".join(inspect_preview(blank).reasons)
    transparent = tmp_path / "transparent.png"
    Image.new("RGBA", (800, 450), (0, 0, 0, 0)).save(transparent)
    assert "transparent" in " ".join(inspect_preview(transparent).reasons)
    small = tmp_path / "small.png"; _png(small, 320, 180)
    assert "resolution" in " ".join(inspect_preview(small).reasons)
    good = tmp_path / "good.png"; _png(good, 800, 450)
    assert inspect_preview(good).valid


def test_audit_previews_reports_known_images_and_decode_errors(tmp_path):
    _png(tmp_path / "alpha.png", 800, 450)
    (tmp_path / "beta.png").write_bytes(b"not an image")
    results = audit_previews(tmp_path, ["alpha", "beta", "missing"])
    assert results["alpha"].valid
    assert not results["beta"].valid and results["beta"].width == 0
    assert "missing" not in results
