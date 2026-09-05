"""Capture a non-qualifying, hash-bound local architecture audit snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from allin1.release_paths import contained, no_links


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture(root):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], encoding="utf-8", timeout=30).strip()
    inputs = {}
    for name in sorted(set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0"))):
        if not name or name.startswith(("build/", ".work/")):
            continue
        path = contained(root, name)
        if path.is_file(): inputs[name] = sha(path)
        elif path.is_dir():
            inputs[name] = {"gitlink_commit": subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], encoding="utf-8", timeout=30).strip()}
        else: inputs[name] = None
    artifacts = {}
    for directory in ("build/reports", "desktop/dist", "script/dist"):
        base = root / directory
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_file(): artifacts[path.relative_to(root).as_posix()] = sha(no_links(path))
    # Compiler outputs can be hard links. These are read, never changed.
    for name in ("desktop/src-tauri/target/debug/allin1-launcher-desktop.exe", "desktop/src-tauri/target/release/allin1-sdk-desktop.exe"):
        path = root / name
        if path.is_file(): artifacts[name] = sha(path)
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "source_tree_sha256": hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "source_inputs": inputs, "observed_artifacts": artifacts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = no_links(args.output.absolute())
    report = {"schema_version": 1, "kind": "architecture_audit_snapshot", "release_ready": False,
              "captured_at": datetime.now(timezone.utc).isoformat(),
              "caveat": "Observed native SDK artifacts may predate these sources. This is not a sealed build or live acceptance.",
              "python": {"version": sys.version, "sha256": sha(Path(sys.executable))},
              "launcher": capture(ROOT), "sdk": capture(no_links(args.sdk_source.absolute()))}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"file": str(output), "sha256": sha(output), "release_ready": False}))
