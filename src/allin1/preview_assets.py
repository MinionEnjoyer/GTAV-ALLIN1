"""Validation and merging for GBAY vehicle preview captures."""

from __future__ import annotations

import logging
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("allin1.preview_assets")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PreviewMergeResult:
    copied: int
    rejected: tuple[str, ...]
    missing: tuple[str, ...]


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
            except (OSError, ValueError) as exc:
                rejected.append(f"{image.name}: {exc}")
                continue
            shutil.copy2(image, destination / f"{model}.png")
            copied_models.add(model)

    for reason in rejected:
        log.warning("Rejected preview capture: %s", reason)
    missing = tuple(sorted(set(known) - copied_models))
    return PreviewMergeResult(len(copied_models), tuple(rejected), missing)
