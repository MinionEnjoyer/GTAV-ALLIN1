"""Privacy-aware diagnostic bundle generation."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def _redact(text: str) -> str:
    text = re.sub(r'(?im)^(gta_path\s*=\s*)"[^"]*"', r'\1"<redacted>"', text)
    text = re.sub(r"(?i)(?:[A-Z]:\\Users\\|/Users/|/home/)[^/\\\s\"]+", "<user>", text)
    return text


def create_diagnostic_bundle(output: Path, project_root: Path,
                             scripts_dir: Path | None = None) -> Path:
    """Create a redacted zip containing configuration, logs, and a manifest."""
    candidates = [project_root / "config.toml", project_root / "config.example.toml",
                  project_root / "allin1.log"]
    if scripts_dir:
        candidates.extend(scripts_dir / name for name in (
            "ALLIN1.toml", "ALLIN1_client.log", "ALLIN1_client.log.1",
            "ALLIN1_gbay.log", "ALLIN1_garage.json", "ALLIN1_floor_garage.json",
            "ALLIN1_davis_garage.json", "ALLIN1_davis_customization.json",
            "ALLIN1_garment_factory_garage.json", "ALLIN1_rural_garage.json",
            "ALLIN1_floor_themes.json",
            "ALLIN1_characters.json", "ALLIN1_smoke_report.json",
            "ALLIN1.version", "ALLIN1_session.lock", "ALLIN1_gbay_preferences.json",
            "ALLIN1_garage.quarantine.json", "ALLIN1_qualification.json",
            "ALLIN1_vehicle_grounding.json",
        ))
    files = [path for path in candidates if path.is_file()]
    manifest = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "files": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            raw = path.read_bytes()
            name = f"files/{path.name}"
            if path.suffix.lower() in {".toml", ".json", ".log", ".lock"}:
                raw = _redact(raw.decode("utf-8", errors="replace")).encode()
            archive.writestr(name, raw)
            manifest["files"].append({
                "name": path.name, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    return output
