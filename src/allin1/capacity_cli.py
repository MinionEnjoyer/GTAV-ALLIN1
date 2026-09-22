"""Export-only content capacity profiles; never install into game archives."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import click

from allin1.capacity_profiles import build_profile, inspect_config, preset_targets


def read_text(raw: bytes) -> str:
    """Decode capacity XML for parsing without changing its audit bytes."""

    try:
        return raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ValueError("Gameconfig is not valid UTF-8") from exc


def _read_raw_source(path: Path) -> bytes:
    """Read bounded source bytes without losing their audit representation."""

    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("Gameconfig exceeds the 4 MiB input limit")
    return path.read_bytes()


def read_source(path: Path) -> str:
    """Read source XML as BOM-free, LF-normalized UTF-8 text."""

    return read_text(_read_raw_source(path))


@click.group("capacity")
def capacity():
    """Inspect gameconfig and build unqualified, export-only pool profiles."""


@capacity.command("inspect")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def inspect_command(source):
    """Inspect an extracted stock gameconfig.xml without changing it."""
    try:
        raw = _read_raw_source(source)
        xml = read_text(raw)
        report = inspect_config(xml)
        # The user-facing fingerprint authenticates the exact extracted file,
        # including a BOM and original line endings, not our parse normalization.
        report["source_sha256"] = sha256(raw).hexdigest()
        click.echo(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@capacity.command("build")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--edition", required=True, type=click.Choice(["legacy", "enhanced"]))
@click.option("--game-build", required=True, help="Game version recorded for this candidate; not a compatibility certification.")
@click.option("--source-sha256", required=True, help="Fingerprint returned by capacity inspect.")
@click.option("--preset", default="stock", show_default=True, type=click.Choice(["stock", "addon-headroom"]))
@click.option("--pool", multiple=True, metavar="NAME=SIZE", help="Explicit target; never lowers an existing value.")
@click.option("--output", required=True, type=click.Path(path_type=Path), help="New export directory; existing destinations are refused.")
def build_command(source, edition, game_build, source_sha256, preset, pool, output):
    """Export a candidate, original source, and audit receipt. Does not install."""
    try:
        targets = dict(preset_targets(edition, preset))
        seen = set()
        for override in pool:
            name, separator, value = override.partition("=")
            if not separator or not name or name in seen:
                raise ValueError("Each --pool must be a unique NAME=SIZE")
            seen.add(name)
            targets[name] = int(value)
        raw_source = _read_raw_source(source)
        original = read_text(raw_source)
        raw_source_sha256 = sha256(raw_source).hexdigest()
        if raw_source_sha256 != source_sha256.lower():
            raise ValueError("source SHA-256 does not match expected_source_sha256")
        candidate, receipt = build_profile(original, edition=edition, game_build=game_build,
            targets=targets,
            # ``build_profile`` is a text transformer; authenticate its input
            # after the CLI has bound this request to the original raw bytes.
            expected_source_sha256=sha256(original.encode("utf-8")).hexdigest())
        receipt["source_sha256"] = raw_source_sha256
        receipt["output_sha256"] = sha256(candidate.encode("utf-8")).hexdigest()
        # Reject links in every existing ancestor, not just at the destination.
        for ancestor in (output.absolute(), *output.absolute().parents):
            if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
                raise ValueError("Export destination must not traverse links")
        output.mkdir(parents=False, exist_ok=False)
        (output / "stock-gameconfig.xml").write_bytes(raw_source)
        for name, content in (("gameconfig.xml", candidate),
                              ("profile.json", json.dumps(receipt, indent=2, sort_keys=True) + "\n")):
            with (output / name).open("x", encoding="utf-8", newline="") as stream:
                stream.write(content)
        click.echo(f"Exported unqualified candidate to {output}. No game files changed.")
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
