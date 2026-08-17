"""Build .ytd texture dictionaries from PNG preview images.

Pipeline: PNG folder -> Pillow BC3 DDS -> RpfPatcher/CodeWalker -> .ytd

The old YTDToolio PNG path corrupts scanlines on current Windows systems.
Pillow provides a standards-compliant BC3 encoder, while CodeWalker writes
the resource dictionary and performs the later Enhanced conversion.

This module is called at install time on the user's Windows gaming PC.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PIL import Image

from allin1.generators.vehiclelist import TEXTURES_PER_YTD, YTD_PREFIX
from allin1.processes import run_hidden

log = logging.getLogger("allin1.generators.ytd_builder")


def _run(cmd: list[str | Path], label: str, cwd: Path | None = None) -> None:
    """Run a subprocess, raising on failure."""
    log.debug("Running: %s", " ".join(str(c) for c in cmd))
    result = run_hidden(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    if result.stdout:
        log.debug("%s stdout: %s", label, result.stdout.strip())
    if result.stderr:
        log.debug("%s stderr: %s", label, result.stderr.strip())
    if result.returncode != 0:
        log.error("%s failed (rc=%d):\n%s", label, result.returncode, result.stderr)
        raise RuntimeError(f"{label} failed: {result.stderr[:500]}")
    if result.stderr and "exception" in result.stderr.lower():
        log.error("%s crashed:\n%s", label, result.stderr)
        raise RuntimeError(f"{label} crashed: {result.stderr[:500]}")


def _encode_dds_files(png_dir: Path, dds_dir: Path) -> int:
    """Encode every PNG as a standards-compliant single-level BC3 DDS."""
    dds_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for png_path in sorted(png_dir.glob("*.png")):
        with Image.open(png_path) as source:
            rgba = source.convert("RGBA")
            rgba.save(dds_dir / f"{png_path.stem}.dds", pixel_format="DXT5")
        count += 1
    return count


def _pack_ytd(png_dir: Path, output_path: Path, rpf_patcher: Path) -> None:
    """Encode a PNG folder and build a Legacy YTD through CodeWalker."""
    dds_dir = png_dir.with_name(f"{png_dir.name}_dds")
    try:
        if _encode_dds_files(png_dir, dds_dir) == 0:
            raise RuntimeError(f"No PNG images found in {png_dir}")
        _run(
            [rpf_patcher, "build-ytd", dds_dir, output_path, "legacy"],
            f"RpfPatcher build-ytd ({output_path.name})",
            cwd=rpf_patcher.parent,
        )
    finally:
        shutil.rmtree(dds_dir, ignore_errors=True)


def _build_preview_group(
    previews_dir: Path,
    output_dir: Path,
    rpf_patcher: Path,
    item_ids: list[str],
    prefix: str,
    textures_per_ytd: int,
) -> list[Path]:
    """Build stable, chunked dictionaries for one preview catalog."""
    built: list[Path] = []
    sorted_items = sorted(item_ids)
    for chunk_idx in range(0, len(sorted_items), textures_per_ytd):
        chunk = sorted_items[chunk_idx : chunk_idx + textures_per_ytd]
        dict_num = chunk_idx // textures_per_ytd + 1
        dict_name = f"{prefix}_{dict_num:02d}"
        log.info("Building %s (%d possible textures)...", dict_name, len(chunk))

        png_dir = output_dir / f"_tmp_{dict_name}"
        png_dir.mkdir(parents=True, exist_ok=True)
        try:
            copied = 0
            for item_id in chunk:
                texture_name = item_id.lower()
                png = previews_dir / f"{texture_name}.png"
                if not png.exists():
                    log.warning("Missing preview: %s", png)
                    continue
                shutil.copy2(png, png_dir / f"{texture_name}.png")
                copied += 1

            # Dictionary numbering is tied to the complete source catalog so
            # a missing capture never shifts the mappings that follow it.
            if copied == 0:
                log.warning("Skipping empty texture dictionary %s", dict_name)
                continue

            ytd_path = output_dir / f"{dict_name}.ytd"
            _pack_ytd(png_dir, ytd_path, rpf_patcher)
            if not ytd_path.exists():
                log.error("RpfPatcher reported success but %s not found", ytd_path)
                search_locations = [
                    Path.cwd() / f"{dict_name}.ytd",
                    png_dir / f"{dict_name}.ytd",
                    png_dir.parent / f"{dict_name}.ytd",
                    output_dir / f"_tmp_{dict_name}.ytd",
                ]
                found = next((path for path in search_locations if path.exists()), None)
                if found:
                    log.info("Found .ytd at %s, moving to %s", found, ytd_path)
                    shutil.move(str(found), str(ytd_path))
                else:
                    raise FileNotFoundError(f"{ytd_path} was not created")
            built.append(ytd_path)
            log.info("Created %s (%d bytes)", ytd_path.name, ytd_path.stat().st_size)
        finally:
            shutil.rmtree(png_dir, ignore_errors=True)
    return built


def _build_native_logo(
    source: Path,
    output_dir: Path,
    rpf_patcher: Path,
    dictionary_name: str,
    texture_name: str,
) -> Path:
    """Pack one logo without passing it through the preview resizer."""
    logo_dir = output_dir / f"_tmp_{dictionary_name}"
    logo_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, logo_dir / f"{texture_name}.png")
        ytd_path = output_dir / f"{dictionary_name}.ytd"
        _pack_ytd(logo_dir, ytd_path, rpf_patcher)
        return ytd_path
    finally:
        shutil.rmtree(logo_dir, ignore_errors=True)


def build_ytd_files(
    previews_dir: Path,
    logo_path: Path | None,
    output_dir: Path,
    tools_dir: Path,
    models: list[str],
    textures_per_ytd: int = TEXTURES_PER_YTD,
    brand_logo_path: Path | None = None,
    preview_groups: list[tuple[str, Path, list[str]]] | None = None,
) -> list[Path]:
    """Build .ytd files from PNG previews.

    Args:
        previews_dir: Directory containing ``<model>.png`` files.
        logo_path: Path to the PHAT loading-screen PNG (or None to skip).
        output_dir: Where to write the .ytd files.
        tools_dir: Directory containing ``RpfPatcher/RpfPatcher.exe``.
        models: List of model names (will be sorted alphabetically).
        textures_per_ytd: Max textures per .ytd file.
        brand_logo_path: Optional ALLIN1 logo for the About page. Each logo is
            packed into its own dictionary at the source PNG's native size.
        preview_groups: Optional additional ``(prefix, directory, item IDs)``
            catalogs, such as weapon and equipment captures.

    Returns:
        List of created .ytd file paths.
    """
    rpf_patcher = tools_dir / "RpfPatcher" / "RpfPatcher.exe"

    if not rpf_patcher.exists():
        raise FileNotFoundError(f"RpfPatcher.exe not found at {rpf_patcher}")

    output_dir.mkdir(parents=True, exist_ok=True)
    ytd_files = _build_preview_group(
        previews_dir, output_dir, rpf_patcher, models,
        YTD_PREFIX, textures_per_ytd,
    )
    for prefix, group_dir, item_ids in preview_groups or []:
        ytd_files.extend(_build_preview_group(
            group_dir, output_dir, rpf_patcher, item_ids,
            prefix, textures_per_ytd,
        ))

    # Keep both artwork assets independent. _pack_ytd encodes the source PNG
    # directly, preserving its native dimensions instead of applying the
    # catalog-card 512x288 resize used by merge_previews().
    if logo_path and logo_path.exists():
        log.info("Building native-resolution phat_logo.ytd...")
        ytd_files.append(_build_native_logo(
            logo_path, output_dir, rpf_patcher, "phat_logo", "phat"
        ))
    if brand_logo_path and brand_logo_path.exists():
        log.info("Building native-resolution allin1_logo.ytd...")
        ytd_files.append(_build_native_logo(
            brand_logo_path, output_dir, rpf_patcher, "allin1_logo", "allin1"
        ))

    log.info("Built %d .ytd files total", len(ytd_files))
    return ytd_files
