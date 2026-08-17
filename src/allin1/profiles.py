"""Named launcher configuration profiles."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from allin1.config import Config

_VALID_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,47}\Z")


class ProfileStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def validate_name(name: str) -> str:
        name = name.strip()
        if not _VALID_NAME.fullmatch(name) or ".." in name:
            raise ValueError("Profile names must be 1-48 safe characters")
        return name

    def path_for(self, name: str) -> Path:
        return self.directory / (self.validate_name(name) + ".toml")

    def list(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(path.stem for path in self.directory.glob("*.toml"))

    def save(self, name: str, config: Config) -> Path:
        path = self.path_for(name)
        config.save(path)
        return path

    def load(self, name: str) -> Config:
        path = self.path_for(name)
        if not path.is_file():
            raise FileNotFoundError(path)
        return Config.load(path)

    def delete(self, name: str) -> None:
        self.path_for(name).unlink()

    def export(self, name: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path_for(name), destination)
        return destination
