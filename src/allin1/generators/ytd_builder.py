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
import subprocess
from pathlib import Path

from PIL import Image

from allin1.generators.vehiclelist import TEXTURES_PER_YTD, YTD_PREFIX

log = logging.getLogger("allin1.generators.ytd_builder")


def _run(cmd: list[str | Path], label: str, cwd: Path | None = None) -> None:
    """Run a subprocess, raising on failure."""
    log.debug("Running: %s", " ".join(str(c) for c in cmd))
    result = subprocess.run(
        [str(c) for c in cmd],
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


def build_ytd_files(
    previews_dir: Path,
    logo_path: Path | None,
    output_dir: Path,
    tools_dir: Path,
    models: list[str],
    textures_per_ytd: int = TEXTURES_PER_YTD,
    brand_logo_path: Path | None = None,
) -> list[Path]:
    """Build .ytd files from PNG previews.

    Args:
        previews_dir: Directory containing ``<model>.png`` files.
        logo_path: Path to the ALLIN1 brand PNG (or None to skip).
        output_dir: Where to write the .ytd files.
        tools_dir: Directory containing ``RpfPatcher/RpfPatcher.exe``.
        models: List of model names (will be sorted alphabetically).
        textures_per_ytd: Max textures per .ytd file.
        brand_logo_path: Optional ALLIN1 logo for the About page.

    Returns:
        List of created .ytd file paths.
    """
    rpf_patcher = tools_dir / "RpfPatcher" / "RpfPatcher.exe"

    if not rpf_patcher.exists():
        raise FileNotFoundError(f"RpfPatcher.exe not found at {rpf_patcher}")

    output_dir.mkdir(parents=True, exist_ok=True)
    sorted_models = sorted(models)
    ytd_files: list[Path] = []

    # Split models into chunks and build preview .ytd files
    for chunk_idx in range(0, len(sorted_models), textures_per_ytd):
        chunk = sorted_models[chunk_idx : chunk_idx + textures_per_ytd]
        dict_num = chunk_idx // textures_per_ytd + 1
        dict_name = f"{YTD_PREFIX}_{dict_num:02d}"

        log.info("Building %s (%d textures)...", dict_name, len(chunk))

        # Create temp folder with PNGs for this chunk
        png_dir = output_dir / f"_tmp_{dict_name}"
        png_dir.mkdir(parents=True, exist_ok=True)

        try:
            copied = 0
            for model in chunk:
                png = previews_dir / f"{model}.png"
                if not png.exists():
                    log.warning("Missing preview: %s", png)
                    continue
                shutil.copy2(png, png_dir / f"{model}.png")
                copied += 1

            # Keep dictionary numbering tied to the complete vehicle catalog,
            # but do not ask the resource builder to pack an empty directory.
            if copied == 0:
                log.warning("Skipping empty texture dictionary %s", dict_name)
                continue

            ytd_path = output_dir / f"{dict_name}.ytd"
            _pack_ytd(png_dir, ytd_path, rpf_patcher)
            if not ytd_path.exists():
                log.error("RpfPatcher reported success but %s not found", ytd_path)
                # Search for the .ytd file in likely locations
                search_locations = [
                    Path.cwd() / f"{dict_name}.ytd",
                    png_dir / f"{dict_name}.ytd",
                    png_dir.parent / f"{dict_name}.ytd",
                    # Historical packers might name it after the folder.
                    output_dir / f"_tmp_{dict_name}.ytd",
                ]
                # Also list what's actually in the output directory
                log.debug("Files in %s: %s", output_dir,
                          [f.name for f in output_dir.iterdir()] if output_dir.exists() else "DIR NOT FOUND")
                log.debug("Files in %s: %s", png_dir.parent,
                          [f.name for f in png_dir.parent.iterdir()] if png_dir.parent.exists() else "DIR NOT FOUND")

                found = None
                for loc in search_locations:
                    if loc.exists():
                        found = loc
                        break
                if found:
                    log.info("Found .ytd at %s, moving to %s", found, ytd_path)
                    shutil.move(str(found), str(ytd_path))
                else:
                    raise FileNotFoundError(f"{ytd_path} was not created")
            ytd_files.append(ytd_path)
            log.info("Created %s (%d bytes)", ytd_path.name, ytd_path.stat().st_size)
        finally:
            shutil.rmtree(png_dir, ignore_errors=True)

    # Build logo .ytd
    if logo_path and logo_path.exists():
        log.info("Building allin1_logo.ytd...")
        logo_dir = output_dir / "_tmp_allin1_logo"
        logo_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Keep the historical texture key so older clients can use new
            # branded packs without a coordinated runtime migration.
            shutil.copy2(logo_path, logo_dir / "phat.png")
            if brand_logo_path and brand_logo_path.exists():
                shutil.copy2(brand_logo_path, logo_dir / "allin1.png")

            ytd_path = output_dir / "allin1_logo.ytd"
            _pack_ytd(logo_dir, ytd_path, rpf_patcher)
            ytd_files.append(ytd_path)
            log.info("Created allin1_logo.ytd")
        finally:
            shutil.rmtree(logo_dir, ignore_errors=True)

    log.info("Built %d .ytd files total", len(ytd_files))
    return ytd_files
