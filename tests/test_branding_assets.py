from pathlib import Path

from PIL import Image


ASSETS = Path(__file__).resolve().parents[1] / "src" / "allin1" / "assets"


def test_launcher_header_logo_has_real_transparency():
    with Image.open(ASSETS / "ALLIN1.png") as logo:
        assert logo.mode == "RGBA"
        alpha = logo.getchannel("A")
        assert alpha.getextrema() == (0, 255)
        assert all(
            logo.getpixel(point)[3] == 0
            for point in (
                (0, 0), (logo.width - 1, 0),
                (0, logo.height - 1), (logo.width - 1, logo.height - 1),
            )
        )


def test_launcher_icon_bundle_includes_high_dpi_sizes():
    with Image.open(ASSETS / "ALLIN1-icon.png") as icon:
        assert icon.mode == "RGBA"
        assert icon.size == (256, 256)
    with Image.open(ASSETS / "ALLIN1.ico") as icon:
        assert {(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)} <= \
            icon.ico.sizes()
