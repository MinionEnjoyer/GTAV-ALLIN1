"""Build .ytd texture dictionaries from PNG preview images.

Pipeline: PNG -> DDS (texconv.exe) -> YTD (YTDToolio.exe)

Both tools are Windows CLI binaries bundled in the project's tools/ directory.
This module is called at install time on the user's Windows gaming PC.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from allin1.generators.vehiclelist import TEXTURES_PER_YTD, YTD_PREFIX

log = logging.getLogger("allin1.generators.ytd_builder")


def _run(cmd: list[str | Path], label: str) -> None:
    """Run a subprocess, raising on failure."""
    log.debug("Running: %s", " ".join(str(c) for c in cmd))
    result = subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error("%s failed (rc=%d):\n%s", label, result.returncode, result.stderr)
        raise RuntimeError(f"{label} failed: {result.stderr[:500]}")


def _convert_png_to_dds(
    png_path: Path,
    output_dir: Path,
    texconv: Path,
    *,
    fmt: str = "DXT1",
    width: int = 512,
    height: int = 256,
) -> Path:
    """Convert a single PNG to DDS using texconv.exe."""
    _run(
        [
            texconv,
            "-f", fmt,
            "-m", "1",          # no mipmaps
            "-w", str(width),
            "-h", str(height),
            "-y",               # overwrite
            "-o", output_dir,
            png_path,
        ],
        f"texconv ({png_path.name})",
    )
    return output_dir / png_path.with_suffix(".dds").name


def _pack_ytd(dds_dir: Path, output_path: Path, ytdtool: Path) -> None:
    """Pack a folder of DDS files into a .ytd using YTDToolio.exe."""
    _run(
        [ytdtool, "pack", dds_dir, "-d", output_path],
        f"YTDToolio ({output_path.name})",
    )


def build_ytd_files(
    previews_dir: Path,
    logo_path: Path | None,
    output_dir: Path,
    tools_dir: Path,
    models: list[str],
    textures_per_ytd: int = TEXTURES_PER_YTD,
) -> list[Path]:
    """Build .ytd files from PNG previews.

    Args:
        previews_dir: Directory containing ``<model>.png`` files.
        logo_path: Path to PHAT.png logo (or None to skip).
        output_dir: Where to write the .ytd files.
        tools_dir: Directory containing texconv.exe and YTDToolio.exe.
        models: List of model names (will be sorted alphabetically).
        textures_per_ytd: Max textures per .ytd file.

    Returns:
        List of created .ytd file paths.
    """
    texconv = tools_dir / "texconv.exe"
    ytdtool = tools_dir / "YTDToolio.exe"

    if not texconv.exists():
        raise FileNotFoundError(f"texconv.exe not found at {texconv}")
    if not ytdtool.exists():
        raise FileNotFoundError(f"YTDToolio.exe not found at {ytdtool}")

    output_dir.mkdir(parents=True, exist_ok=True)
    sorted_models = sorted(models)
    ytd_files: list[Path] = []

    # Split models into chunks and build preview .ytd files
    for chunk_idx in range(0, len(sorted_models), textures_per_ytd):
        chunk = sorted_models[chunk_idx : chunk_idx + textures_per_ytd]
        dict_num = chunk_idx // textures_per_ytd + 1
        dict_name = f"{YTD_PREFIX}_{dict_num:02d}"

        log.info("Building %s (%d textures)...", dict_name, len(chunk))

        # Create temp DDS folder for this chunk
        dds_dir = output_dir / f"_tmp_{dict_name}"
        dds_dir.mkdir(parents=True, exist_ok=True)

        try:
            for model in chunk:
                png = previews_dir / f"{model}.png"
                if not png.exists():
                    log.warning("Missing preview: %s", png)
                    continue
                _convert_png_to_dds(png, dds_dir, texconv)

            ytd_path = output_dir / f"{dict_name}.ytd"
            _pack_ytd(dds_dir, ytd_path, ytdtool)
            ytd_files.append(ytd_path)
            log.info("Created %s", ytd_path.name)
        finally:
            shutil.rmtree(dds_dir, ignore_errors=True)

    # Build logo .ytd (DXT5 for alpha, original dimensions)
    if logo_path and logo_path.exists():
        log.info("Building allin1_logo.ytd...")
        logo_dds_dir = output_dir / "_tmp_allin1_logo"
        logo_dds_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Rename to "phat.png" so the texture name inside .ytd is "phat"
            logo_copy = logo_dds_dir / "phat.png"
            shutil.copy2(logo_path, logo_copy)
            _convert_png_to_dds(
                logo_copy, logo_dds_dir, texconv,
                fmt="DXT5", width=512, height=512,
            )
            # Remove the PNG copy, keep only DDS
            logo_copy.unlink(missing_ok=True)

            ytd_path = output_dir / "allin1_logo.ytd"
            _pack_ytd(logo_dds_dir, ytd_path, ytdtool)
            ytd_files.append(ytd_path)
            log.info("Created allin1_logo.ytd")
        finally:
            shutil.rmtree(logo_dds_dir, ignore_errors=True)

    log.info("Built %d .ytd files total", len(ytd_files))
    return ytd_files
