"""Preview dictionary planning and release artifact verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from allin1.generators.vehiclelist import TEXTURES_PER_YTD, YTD_PREFIX


@dataclass(frozen=True)
class PreviewArtifactReport:
    expected_dicts: tuple[str, ...]
    present_dicts: tuple[str, ...]
    missing_dicts: tuple[str, ...]
    unexpected_dicts: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing_dicts and not self.unexpected_dicts


def expected_dictionary(model_index: int,
                        textures_per_ytd: int = TEXTURES_PER_YTD) -> str:
    if model_index < 0 or textures_per_ytd < 1:
        raise ValueError("invalid preview dictionary index")
    return f"{YTD_PREFIX}_{model_index // textures_per_ytd + 1:02d}"


def verify_ytd_set(directory: Path, model_count: int,
                   textures_per_ytd: int = TEXTURES_PER_YTD) -> PreviewArtifactReport:
    count = (model_count + textures_per_ytd - 1) // textures_per_ytd
    expected = {f"{YTD_PREFIX}_{index:02d}" for index in range(1, count + 1)}
    present = {path.stem for path in directory.glob(f"{YTD_PREFIX}_*.ytd")
               if path.is_file() and path.stat().st_size > 0}
    return PreviewArtifactReport(
        tuple(sorted(expected)), tuple(sorted(present)),
        tuple(sorted(expected - present)), tuple(sorted(present - expected)),
    )
