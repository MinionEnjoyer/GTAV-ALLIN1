"""Pinned, image-only GBAY fallback packs. Generated/custom artwork always wins.

No model extraction, rendering, game launch, or generated-image deletion. The
desktop review boundary supplies game-write authority and closed-game checks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

from allin1.launch_cancellation import checkpoint
from allin1.prelaunch_previews import atomic, contained, document, no_links, png, sha

CATEGORIES = ("weapons", "vehicles", "gear")
OWNER = "allin1.default-previews"
BASE = "plugins/ReactorV/ui/assets/allin1"
MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_IMAGE = 4 * 1024 * 1024
FILENAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\.[0-9a-f]{64}\.png")


def plan(project, categories=None):
    categories = list(CATEGORIES) if categories is None else categories
    if not isinstance(categories, list) or not categories or any(not isinstance(c, str) or c not in CATEGORIES for c in categories) or len(categories) != len(set(categories)):
        raise ValueError("Choose weapons, vehicles and/or gear once each")
    manifest = document(contained(project, "data/default_previews.json"), 64 * 1024)
    if manifest.get("schema_version") != 1 or not re.fullmatch(r"gbay-previews-[0-9-]+", manifest.get("version", "")):
        raise ValueError("Invalid default preview manifest")
    assets = []
    for category in categories:
        asset = manifest["categories"][category]
        expected = f'https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/download/{manifest["version"]}/gbay-{category}.zip'
        if asset.get("url") != expected or not re.fullmatch(r"[0-9a-f]{64}", asset.get("sha256", "")):
            raise ValueError("Invalid pinned preview download")
        if type(asset.get("bytes")) is not int or not 0 < asset["bytes"] <= MAX_ARCHIVE:
            raise ValueError("Invalid preview download size")
        if type(asset.get("count")) is not int or not 0 < asset["count"] <= 2048:
            raise ValueError("Invalid preview count")
        assets.append({**asset, "category": category})
    return {"version": manifest["version"], "assets": assets, "bytes": sum(a["bytes"] for a in assets),
            "count": sum(a["count"] for a in assets)}


def validate_archive(path, asset):
    """Check the whole archive before any game write; never extract paths."""
    if path.stat().st_size != asset["bytes"] or sha(path) != asset["sha256"]:
        raise ValueError("Preview archive size/SHA-256 mismatch")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        names = [m.filename for m in members]
        if len(names) != asset["count"] + 1 or len(names) != len(set(names)) or "index.json" not in names:
            raise ValueError("Unexpected preview archive members")
        for member in members:
            if member.filename != "index.json" and not FILENAME.fullmatch(member.filename):
                raise ValueError("Invalid preview archive path")
            mode = (member.external_attr >> 16) & 0o170000
            if mode not in (0, 0o100000) or member.flag_bits & 1:
                raise ValueError("Links and encrypted previews are not supported")
            limit = 512 * 1024 if member.filename == "index.json" else MAX_IMAGE
            if not 0 < member.file_size <= limit:
                raise ValueError("Preview archive member exceeds limit")
        from allin1.release_paths import strict_json
        index = strict_json(archive.read("index.json"))
        if index.get("schema_version") != 1 or index.get("owner") != OWNER:
            raise ValueError("Invalid default preview ownership")
        images, hashes = index.get("images"), index.get("image_sha256")
        if not isinstance(images, dict) or not isinstance(hashes, dict) or len(images) != asset["count"]:
            raise ValueError("Invalid default preview inventory")
        if set(images.values()) != set(names) - {"index.json"} or set(hashes) != set(images.values()):
            raise ValueError("Unlisted or missing preview images")
        for identity, filename in images.items():
            if not re.fullmatch(re.escape(identity) + r"\.[0-9a-f]{64}\.png", filename):
                raise ValueError("Preview identity mismatch")
            data = png(archive.read(filename))
            if hashlib.sha256(data).hexdigest() != hashes[filename]:
                raise ValueError("Preview image SHA-256 mismatch")
        return index


def _download(asset, target, progress, *, opener=urlopen):
    request = Request(asset["url"], headers={"User-Agent": "ALLIN1-Launcher-Previews"})
    with opener(request, timeout=30) as response, target.open("xb") as stream:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}:
            raise ValueError("Unexpected preview download redirect")
        received = 0
        while True:
            checkpoint()
            chunk = response.read(1024 * 1024)
            if not chunk: break
            received += len(chunk)
            if received > asset["bytes"]: raise ValueError("Preview download exceeds pinned size")
            stream.write(chunk)
            progress(received)
        if received != asset["bytes"]: raise ValueError("Incomplete preview download")


def install(project, game, cache_root, *, categories=None, progress=lambda *_: None):
    report = plan(project, categories)
    cache = no_links(Path(cache_root))
    cache.mkdir(parents=True, exist_ok=True)
    validated = []
    done = 0
    # Cache complete verified ZIPs for the other edition / offline reinstall.
    for asset in report["assets"]:
        archive = contained(cache, asset["sha256"] + ".zip")
        if not archive.exists() or archive.stat().st_size != asset["bytes"] or sha(archive) != asset["sha256"]:
            with tempfile.TemporaryDirectory(prefix="download-", dir=cache) as temporary:
                incoming = Path(temporary) / "pack.zip"
                _download(asset, incoming, lambda n: progress(int(90 * (done + n) / report["bytes"]), f'Downloading {asset["category"]} previews'))
                validate_archive(incoming, asset)
                import os
                os.replace(incoming, archive)
        index = validate_archive(archive, asset)
        destination = contained(game, BASE + "/default-" + asset["category"])
        index_path = contained(destination, "index.json")
        if index_path.exists() and document(index_path).get("owner") != OWNER:
            raise ValueError("Default preview index belongs to another owner")
        for filename in index["images"].values():
            target = contained(destination, filename)
            if target.exists() and sha(target) != index["image_sha256"][filename]:
                raise ValueError("Existing default preview was modified; no files overwritten")
        validated.append((archive, destination, index))
        done += asset["bytes"]
    # All downloads and destination conflicts checked before publication.
    for archive, destination, index in validated:
        with zipfile.ZipFile(archive) as source:
            for filename in index["images"].values():
                checkpoint()
                target = contained(destination, filename)
                if not target.exists(): atomic(target, source.read(filename))
        atomic(contained(destination, "index.json"), json.dumps(index, sort_keys=True).encode())
    progress(100, f'Installed {report["count"]} vanilla default previews; generated artwork preserved')
    return {"version": report["version"], "counts": {a["category"]: a["count"] for a in report["assets"]},
            "generated_preserved": True}
