"""Exercise the actual SDK ZIP producer against Launcher lifecycle consumers.

This is an explicit cross-checkout developer test, never a runtime dependency.
All payloads are synthetic non-executable bytes in a disposable directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile

LAUNCHER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAUNCHER / "src"))
from allin1.sdk_manager import install_sdk_archive, read_sdk_status, uninstall_sdk
from allin1.release_paths import no_links


def verify(sdk_source: Path) -> dict:
    sdk_source = no_links(sdk_source).resolve(strict=True)
    sys.path.insert(0, str(sdk_source / "src"))
    producer = runpy.run_path(str(sdk_source / "scripts/desktop_candidate.py"))["write_portable"]
    identity = {"schema_version": 1, "kind": "sdk_build_identity", "sdk_version": "0.6.4", "build_id": "cross-repo-synthetic"}
    with tempfile.TemporaryDirectory(prefix="allin1-cross-repo-") as directory:
        root = Path(directory)
        values = {
            "build-identity.json": json.dumps(identity).encode(),
            "allin1-sdk-desktop.exe": b"MZ synthetic shell; must never execute",
            "sidecar/ALLIN1-SDK-Desktop-Sidecar.exe": b"MZ synthetic sidecar; must never execute",
        }
        values["resource-checksums.json"] = json.dumps({"build-identity.json": hashlib.sha256(values["build-identity.json"]).hexdigest()}).encode()
        actual, expected = {}, {}
        for name, content in values.items():
            source = root / "source" / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(content)
            actual[name] = source
            expected[name] = hashlib.sha256(content).hexdigest()
        archive = root / "SDK portable.zip"
        package = producer(archive, expected, actual, identity=identity)
        installation = root / "User directory with spaces/SDK"
        assert install_sdk_archive(archive, installation).healthy
        canary = installation / "user-project.txt"
        canary.write_text("keep user data", encoding="utf-8")
        (installation / "sidecar/ALLIN1-SDK-Desktop-Sidecar.exe").write_bytes(b"tampered")
        assert not read_sdk_status(installation).healthy
        assert install_sdk_archive(archive, installation).healthy
        assert canary.read_text(encoding="utf-8") == "keep user data"
        assert uninstall_sdk(installation)
        retired = next(installation.parent.glob("SDK.uninstalled-*"))
        assert (retired / "user-project.txt").read_text(encoding="utf-8") == "keep user data"
        return {"schema_version": 1, "kind": "cross_repository_contract_test", "synthetic": True,
                "result": "PASS", "package": package, "live_acceptance": "NOT TESTED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-source", type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().sdk_source), indent=2))
