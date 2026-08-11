"""Validation and merging for GBAY vehicle preview captures."""

from __future__ import annotations

import logging
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageStat

log = logging.getLogger("allin1.preview_assets")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PreviewMergeResult:
    copied: int
    rejected: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class PreviewQuality:
    valid: bool
    reasons: tuple[str, ...]
    width: int
    height: int
    visible_fraction: float
    contrast: float


def inspect_preview(path: Path, *, minimum_width: int = 512,
                    minimum_height: int = 288) -> PreviewQuality:
    """Detect empty, transparent, flat, undersized, and badly framed captures."""
    reasons: list[str] = []
    with Image.open(path) as source:
        image = source.convert("RGBA")
    width, height = image.size
    if width < minimum_width or height < minimum_height:
        reasons.append(f"resolution {width}x{height} is below {minimum_width}x{minimum_height}")
    alpha = image.getchannel("A")
    visible = sum(alpha.histogram()[9:])
    visible_fraction = visible / max(1, width * height)
    if visible_fraction < 0.05:
        reasons.append("image is almost entirely transparent")
    rgb = image.convert("RGB")
    contrast = sum(ImageStat.Stat(rgb).stddev) / 3.0
    if contrast < 4.0:
        reasons.append("image is blank or has extremely low contrast")
    bbox = alpha.point(lambda value: 255 if value > 8 else 0).getbbox()
    if bbox and visible_fraction < 0.99:
        object_width = bbox[2] - bbox[0]; object_height = bbox[3] - bbox[1]
        if object_width < width * 0.12 or object_height < height * 0.12:
            reasons.append("visible subject occupies too little of the frame")
        if bbox[0] == 0 or bbox[1] == 0 or bbox[2] == width or bbox[3] == height:
            reasons.append("visible subject touches the frame edge")
    return PreviewQuality(not reasons, tuple(reasons), width, height,
                          visible_fraction, contrast)


def audit_previews(directory: Path, models: list[str]) -> dict[str, PreviewQuality]:
    """Return quality results for known model PNGs in a directory."""
    results = {}
    for model in models:
        path = directory / f"{model.lower()}.png"
        if path.is_file():
            try:
                results[model.lower()] = inspect_preview(path)
            except (OSError, ValueError) as exc:
                results[model.lower()] = PreviewQuality(False, (str(exc),), 0, 0, 0, 0)
    return results


def png_dimensions(path: Path) -> tuple[int, int]:
    """Return PNG dimensions after validating its signature and IHDR."""
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise ValueError("not a valid PNG")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1:
        raise ValueError("PNG has invalid dimensions")
    return width, height


def merge_previews(
    sources: list[Path], destination: Path, models: list[str]
) -> PreviewMergeResult:
    """Merge valid captures, with later sources overriding earlier sources.

    Only known vehicle model names are accepted. This keeps texture names in
    sync with ``VehicleList.PreviewDict`` and prevents unrelated screenshots
    from being packed into the DLC.
    """
    known = {model.lower(): model.lower() for model in models}
    destination.mkdir(parents=True, exist_ok=True)
    rejected: list[str] = []
    copied_models: set[str] = set()

    for source in sources:
        if not source.is_dir():
            continue
        for image in sorted(source.glob("*.png")):
            model = image.stem.lower()
            if model not in known:
                rejected.append(f"{image.name}: unknown vehicle model")
                continue
            try:
                png_dimensions(image)
                quality = inspect_preview(image)
                if not quality.valid:
                    raise ValueError("; ".join(quality.reasons))
            except (OSError, ValueError) as exc:
                rejected.append(f"{image.name}: {exc}")
                continue
            shutil.copy2(image, destination / f"{model}.png")
            copied_models.add(model)

    for reason in rejected:
        log.warning("Rejected preview capture: %s", reason)
    missing = tuple(sorted(set(known) - copied_models))
    return PreviewMergeResult(len(copied_models), tuple(rejected), missing)
