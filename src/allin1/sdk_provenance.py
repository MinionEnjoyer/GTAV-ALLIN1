"""Optional SDK artifact lineage attached to existing Launcher install receipts.

Untraced packages still install normally. A present but invalid SDK envelope is
an error, never silently downgraded to an untraced package. No upload or asset
discovery outside the selected package occurs.
"""
import hashlib
from pathlib import Path

from allin1.artifact_contract import validate_manifest
from allin1.release_paths import contained, no_links, strict_json, tree_files

ARTIFACT_FILE = "sdk-artifact.json"


def file_hash(file):
    with no_links(file).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def read(manifest, edition):
    root = no_links(manifest.package_root)
    envelope = contained(root, ARTIFACT_FILE)
    if not envelope.exists():
        return None
    if envelope.stat().st_size > 4*1024**2:
        raise ValueError("SDK artifact envelope exceeds 4 MiB")
    data = envelope.read_bytes()
    artifact = validate_manifest(strict_json(data))
    if artifact["edition"] is not None and artifact["edition"].casefold() != edition.casefold():
        raise ValueError("SDK artifact was built for a different GTA edition")
    files = tree_files(root)
    if set(files)-{ARTIFACT_FILE} != set(artifact["outputs"]):
        raise ValueError("SDK artifact does not cover this exact package inventory")
    for name, expected in artifact["outputs"].items():
        if file_hash(files[name]) != expected:
            raise ValueError(f"SDK artifact payload changed: {name}")
    for item in (*manifest.files, *manifest.rpf_entries):
        if item.source.as_posix() not in artifact["outputs"]:
            raise ValueError("Install source is outside the SDK artifact inventory")
    return {"artifact":artifact,"envelope_sha256":hashlib.sha256(data).hexdigest()}


def installed(provenance, manifest, records, rpf_records):
    if provenance is None:
        return None
    artifact = provenance["artifact"]
    loose, members = [], []
    if len(manifest.files)!=len(records) or len(manifest.rpf_entries)!=len(rpf_records):
        raise ValueError("Installation evidence is incomplete for the SDK artifact")
    for authored, actual in zip(manifest.files,records):
        source = authored.source.as_posix()
        if artifact["outputs"][source] != actual["sha256"] or authored.destination.as_posix()!=actual["destination"]:
            raise ValueError("Installed file differs from the reviewed SDK artifact")
        loose.append({"source":source,"destination":actual["destination"],"sha256":actual["sha256"],"verification":"installed_bytes"})
    for authored, actual in zip(manifest.rpf_entries,rpf_records):
        source = authored.source.as_posix()
        if (artifact["outputs"][source]!=actual["sha256"] or authored.archive.as_posix()!=actual["archive"] or authored.entry.as_posix()!=actual["entry"]):
            raise ValueError("Installed RPF member differs from the reviewed SDK artifact")
        members.append({"source":source,"archive":actual["archive"],"entry":actual["entry"],"sha256":actual["sha256"],"verification":"extracted_member_bytes"})
    return {"schema_version":1,"kind":"sdk_install_lineage",**provenance,
            "artifact_id":artifact["artifact_id"],"build_fingerprint":artifact["build"]["build_fingerprint"],
            "files":loose,"rpf_members":members,
            "scope":"Hashes verified at installation, not proof of subsequent startup/loading or crash causality. Local content identities are not publisher signatures."}
