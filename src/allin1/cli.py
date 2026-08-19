"""Command-line interface for GTA V ALLIN1."""

from __future__ import annotations

import logging
import json
from pathlib import Path

import click

from allin1.config import Config
from allin1 import __version__
from allin1.installer import install, uninstall
from allin1.logging import setup_logging
from allin1.vehicles.database import VehicleDatabase

# Resolve project root (where data/ lives) relative to this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CONFIG = PROJECT_ROOT / "config.toml"
VEHICLES_DB = DATA_DIR / "vehicles.toml"

log = logging.getLogger("allin1.cli")


@click.group()
@click.option(
    "--config", "-c",
    type=click.Path(exists=False),
    default=str(DEFAULT_CONFIG),
    help="Path to config.toml",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (debug) output")
@click.version_option(__version__, prog_name="GTA V ALLIN1")
@click.pass_context
def main(ctx: click.Context, config: str, verbose: bool) -> None:
    """ALLIN1 - GTA V Story Mode mod manager and add-on content tool."""
    setup_logging(project_root=PROJECT_ROOT, verbose=verbose)
    log.info("ALLIN1 started")

    ctx.ensure_object(dict)
    config_path = Path(config)
    if config_path.exists():
        ctx.obj["config"] = Config.load(config_path)
        log.info("Loaded config from %s", config_path)
    else:
        ctx.obj["config"] = Config.default()
        log.info("No config.toml found — using defaults")
    ctx.obj["config_path"] = config_path


@main.command()
@click.pass_context
def install_cmd(ctx: click.Context) -> None:
    """Install MP vehicles into your GTA V single player."""
    config: Config = ctx.obj["config"]
    db = VehicleDatabase.load(VEHICLES_DB)

    click.echo(f"Loaded {len(db)} vehicles from database.")
    click.echo()

    try:
        result = install(config, db)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    click.echo(f"GTA V path: {result.gta_path}")
    click.echo(f"Edition: {'Enhanced' if result.is_enhanced else 'Legacy'}")

    for warning in result.warnings:
        click.echo(f"  {warning}")

    click.echo()
    if result.dll_deployed:
        click.echo("ALLIN1.dll deployed to scripts/ folder.")
    else:
        click.echo("WARNING: ALLIN1.dll not found — build it or download from Releases.")

    if not result.scripthookv_found:
        click.echo()
        click.echo("WARNING: ScriptHookV not found in your GTA V folder.")
        click.echo("ALLIN1 requires ScriptHookV. Install it from:")
        click.echo("  http://www.dev-c.com/gtav/scripthookv/")
    else:
        click.echo("ScriptHookV detected.")

    if not result.shvdn_found:
        click.echo()
        click.echo("WARNING: ScriptHookVDotNet not found in your GTA V folder.")
        click.echo("ALLIN1 requires ScriptHookVDotNet Enhanced. Install it from:")
        click.echo("  https://github.com/Chiheb-Bacha/scripthookvdotnetenhanced/releases")
    else:
        click.echo("ScriptHookVDotNet detected.")

    if not result.openrpf_found:
        click.echo()
        if result.is_enhanced:
            click.echo("OpenRPF not detected. This is optional; GBAY will use safe placeholders.")
            click.echo("For GBAY preview artwork, install it manually from:")
        else:
            click.echo("Legacy RPF loader not detected. This is optional for vehicle artwork.")
    else:
        asi_name = "Enhanced RPF loader" if result.is_enhanced else "Legacy RPF loader"
        click.echo(f"{asi_name} detected (optional artwork loader).")
    if result.rpf_previews_deployed:
        click.echo("GBAY RPF preview textures deployed.")

    click.echo()
    click.echo("To play: launch GTA V normally. DLC vehicles will appear in traffic.")


# Register with a user-friendly name
install_cmd.name = "install"


@main.command()
@click.pass_context
def uninstall_cmd(ctx: click.Context) -> None:
    """Remove ALLIN1 files from GTA V directory."""
    config: Config = ctx.obj["config"]

    try:
        restored = uninstall(config)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    click.echo(f"Removed {len(restored)} files:")
    for f in restored:
        click.echo(f"  - {f}")
    click.echo("Uninstall complete.")


uninstall_cmd.name = "uninstall"


@main.command()
@click.option("--class", "-c", "vehicle_class", default=None, help="Filter by vehicle class")
@click.pass_context
def list_cmd(ctx: click.Context, vehicle_class: str | None) -> None:
    """List all available MP vehicles."""
    db = VehicleDatabase.load(VEHICLES_DB)

    if vehicle_class:
        vehicles = db.by_class(vehicle_class)
        if not vehicles:
            click.echo(f"No vehicles found in class '{vehicle_class}'.")
            click.echo(f"Available classes: {', '.join(db.classes)}")
            return
    else:
        vehicles = db.all_vehicles

    # Group by class for display
    by_class: dict[str, list] = {}
    for v in vehicles:
        by_class.setdefault(v.vehicle_class, []).append(v)

    total = 0
    for cls in sorted(by_class.keys()):
        group = by_class[cls]
        click.echo(f"\n  {cls.upper()} ({len(group)})")
        click.echo(f"  {'─' * 40}")
        for v in sorted(group, key=lambda x: x.name):
            click.echo(f"    {v.model:<24} {v.name}")
            total += 1

    click.echo(f"\n  Total: {total} vehicles")


list_cmd.name = "list"


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current installation status."""
    config: Config = ctx.obj["config"]

    click.echo("Configuration:")
    click.echo(f"  Config file: {ctx.obj['config_path']}")
    click.echo(f"  GTA path: {config.general.gta_path}")
    click.echo(f"  Free GBAY purchases: {config.script.gbay_free_mode}")
    click.echo(f"  Traffic: {'enabled' if config.traffic.enabled else 'disabled'}")
    click.echo("  Garage wanted-level override: "
               f"{'enabled' if config.script.garages_always_accessible else 'disabled'}")
    click.echo(f"  Enable all: {config.vehicles.enable_all}")

    if config.vehicles.disabled_classes:
        click.echo(f"  Disabled classes: {', '.join(config.vehicles.disabled_classes)}")
    if config.vehicles.disabled_vehicles:
        click.echo(f"  Disabled vehicles: {len(config.vehicles.disabled_vehicles)} models")

    db = VehicleDatabase.load(VEHICLES_DB)
    click.echo(f"\nVehicle database: {len(db)} vehicles across {len(db.classes)} classes")


@main.group("sdk")
def sdk_group() -> None:
    """Inspect and link declarative GTA V add-on integrations."""


@sdk_group.command("list")
def sdk_list() -> None:
    """List the add-on examples included with the ALLIN1 SDK."""
    from allin1.addon_sdk import AddonSdkCatalog

    manifests = AddonSdkCatalog(PROJECT_ROOT).discover()
    if not manifests:
        click.echo("No sdk/examples/*/addon.json manifests found.")
        return
    for manifest in manifests:
        click.echo(
            f"{manifest.addon_id:<32} {manifest.version:<10} {manifest.name}"
        )


def _load_sdk_manifest(path: Path):
    from allin1.addon_sdk import AddonManifest

    resolved = path.resolve()
    root = PROJECT_ROOT if resolved.is_relative_to(PROJECT_ROOT) else resolved.parent
    return AddonManifest.load(resolved, source_root=root)


@sdk_group.command("validate")
@click.argument("manifest", type=click.Path(exists=True, path_type=Path))
def sdk_validate(manifest: Path) -> None:
    """Validate fields and cross-file references in addon.json."""
    from allin1.addon_sdk import AddonLinker

    report = AddonLinker().link(_load_sdk_manifest(manifest))
    click.echo(
        f"{'PASS' if report.valid else 'FAIL'}: "
        f"{len(report.manifest.nodes)} nodes, "
        f"{sum(item.valid for item in report.references)}/"
        f"{len(report.references)} references, "
        f"{report.error_count} errors, {report.warning_count} warnings"
    )
    for issue in report.issues:
        subject = f" [{issue.subject}]" if issue.subject else ""
        click.echo(f"{issue.severity.upper()} {issue.code}{subject}: {issue.message}")
    if not report.valid:
        raise SystemExit(1)


@sdk_group.command("link")
@click.argument("manifest", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), required=True)
def sdk_link(manifest: Path, output: Path) -> None:
    """Write a human-readable linked integration and install-plan report."""
    from allin1.addon_sdk import AddonLinker

    report = AddonLinker().link(_load_sdk_manifest(manifest))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.to_markdown(), encoding="utf-8")
    click.echo(f"Wrote {'passing' if report.valid else 'failing'} link report: {output}")
    if not report.valid:
        raise SystemExit(1)


@sdk_group.command("import-package")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path))
def sdk_import_package(source: Path, output: Path | None) -> None:
    """Scan a loose DLC folder or OIV/ZIP/RAR/7z and generate a reviewable draft."""
    from allin1.addon_importer import AddonDraftBuilder, AddonPackageInspector
    from allin1.addon_sdk import AddonLinker, AddonManifest

    source = source.resolve()
    try:
        scan = AddonPackageInspector().inspect(source)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"Scanned {len(scan.entries)} files ({scan.total_bytes} bytes): "
        f"{len(scan.weapons)} weapons, {len(scan.ammo)} ammo records, "
        f"{len(scan.animation_weapons)} animation mappings, "
        f"{len(scan.shop_weapons)} shop mappings; "
        f"{len(scan.vehicles)} vehicles, {len(scan.handlings)} handling records, "
        f"{len(scan.variations)} variation records, and {len(scan.kits)} tuning kits."
    )
    click.echo(
        "Detected package shape(s): " + ", ".join(scan.package_kinds) + "; "
        f"{len(scan.binary_plugins)} compiled plug-ins, "
        f"{len(scan.replacement_assets)} replacement assets, and "
        f"{len(scan.shader_assets)} shaders."
    )
    click.echo(f"Edition tag: {scan.edition_tag}")
    if scan.edition_hints:
        click.echo("Edition layout hints: " + ", ".join(scan.edition_hints))
    if scan.plugin_details:
        click.echo(
            "Plug-in headers: " + ", ".join(
                f"{item.path}={item.architecture}"
                + ("/.NET" if item.managed else "")
                for item in scan.plugin_details
            )
        )
    if scan.installation_targets:
        click.echo(
            "Inferred target(s): " + ", ".join(scan.installation_targets[:8])
        )
    for finding in scan.findings:
        location = f" [{finding.path}]" if finding.path else ""
        click.echo(
            f"{finding.severity.upper()} {finding.code}{location}: "
            f"{finding.message}"
        )
    if not scan.valid:
        raise click.ClickException(
            "Package contains safety errors; no SDK draft was written."
        )

    if output is None:
        output = (
            source / "addon.json" if source.is_dir()
            else source.with_name(f"{source.stem}.addon.json")
        )
    output = output.resolve()
    if source.is_dir() and output.parent != source:
        raise click.ClickException(
            "A loose-folder draft must be written at the package root so "
            "relative source links remain valid."
        )

    try:
        written = AddonDraftBuilder().build(scan).write(output)
        manifest = AddonManifest.load(
            written, source_root=source if source.is_dir() else written.parent,
        )
        report = AddonLinker().link(manifest)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote review-only SDK draft: {written}")
    click.echo(
        f"Draft linker: {report.error_count} errors, "
        f"{report.warning_count} warnings."
    )
    click.echo(
        "Resolve every required link and rollback step, then run "
        "'allin1 sdk validate' before packaging or installation."
    )


@sdk_group.command("oiv-plan")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), required=True)
@click.option(
    "--managed-package", type=click.Path(file_okay=False, path_type=Path),
    help="Extract proven add sources into a new reviewed mod.toml package.",
)
def sdk_oiv_plan(
    source: Path, output: Path, managed_package: Path | None,
) -> None:
    """Preview an OIV recipe without executing it or touching the game."""
    from allin1.oiv_workbench import OivWorkbench

    workbench = OivWorkbench()
    try:
        plan = workbench.inspect(source)
        written = plan.write_report(output)
        click.echo(
            f"OIV plan: {len(plan.operations)} operations; "
            f"{'managed export ready' if plan.translatable else 'manual review required'}."
        )
        click.echo(f"Wrote OIV operation report and JSON: {written}")
        if managed_package is not None:
            manifest = workbench.export_managed_package(plan, managed_package)
            click.echo(f"Wrote validated managed package: {manifest}")
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@sdk_group.command("dlc-inventory")
@click.argument(
    "gta_path", type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--output", "-o", type=click.Path(path_type=Path), required=True)
def sdk_dlc_inventory(gta_path: Path, output: Path) -> None:
    """Inventory DLC folders, registrations, ownership, and stale entries."""
    from allin1.dlc_inventory import DlcInventory

    try:
        report = DlcInventory(PROJECT_ROOT).scan(gta_path)
        written = report.write(output)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"{report.edition}: {len(report.packs)} DLC packages, "
        f"{report.issue_count} reconciliation findings."
    )
    click.echo(f"Wrote read-only DLC inventory and JSON: {written}")


@sdk_group.command("compile-vehicle-data")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir", "-o", type=click.Path(file_okay=False, path_type=Path),
    required=True,
)
def sdk_compile_vehicle_data(source: Path, output_dir: Path) -> None:
    """Join vehicle, handling, variation, tuning, asset, and registration data."""
    from allin1.rage_data_compiler import RageVehicleDataCompiler

    try:
        report = RageVehicleDataCompiler().compile(source)
        written = report.write_bundle(output_dir)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Compiled {len(report.vehicles)} vehicles: {report.error_count} errors, "
        f"{report.warning_count} warnings."
    )
    click.echo(f"Wrote JSON, CSV, XLSX, and Markdown: {written[-1].parent}")


@sdk_group.command("inspect-rpf")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--gta-path", type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="GTA V root used to select the correct Legacy/Enhanced archive keys.",
)
@click.option("--output", "-o", type=click.Path(path_type=Path))
def sdk_inspect_rpf(
    archive: Path, gta_path: Path | None, output: Path | None,
) -> None:
    """Inspect a loose RPF with the edition-aware read-only helper."""
    from allin1.detector import detect_gta_path
    from allin1.processes import run_hidden

    if archive.suffix.casefold() != ".rpf":
        raise click.ClickException("inspect-rpf requires a loose .rpf archive")
    game = gta_path.resolve() if gta_path else detect_gta_path()
    if game is None:
        raise click.ClickException(
            "GTA V was not detected; pass --gta-path so the correct archive keys are used."
        )
    patcher = PROJECT_ROOT / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    if not patcher.is_file():
        raise click.ClickException(
            "RpfPatcher.exe is missing; run runtools.ps1 to build the SDK helper."
        )
    completed = run_hidden(
        [patcher, "inspect", game, archive.resolve()],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "unknown helper error").strip()
        raise click.ClickException(f"RPF inspection failed: {detail}")
    report = completed.stdout
    if output is None:
        click.echo(report, nl=False)
        return
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    click.echo(f"Wrote RPF inventory: {output}")


@sdk_group.command("index-rpf")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--gta-path", type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="GTA V root used for the correct Legacy/Enhanced archive keys.",
)
@click.option("--output", "-o", required=True, type=click.Path(path_type=Path))
def sdk_index_rpf(archive: Path, gta_path: Path | None, output: Path) -> None:
    """Export a structured, searchable RPF index as JSON and CSV."""
    from allin1.detector import detect_gta_path
    from allin1.rpf_tools import RpfExplorerService

    game = gta_path.resolve() if gta_path else detect_gta_path()
    if game is None:
        raise click.ClickException(
            "GTA V was not detected; pass --gta-path so archive keys are correct."
        )
    try:
        index = RpfExplorerService(PROJECT_ROOT, game).index(archive)
        json_path, csv_path = index.export(output)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Indexed {len(index.entries):,} entries across {len(index.archives)} archive(s): "
        f"{json_path} and {csv_path}"
    )


@sdk_group.command("extract-rpf-entry")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("entry_path")
@click.option("--archive-path", default="", help="Nested virtual archive path from index-rpf.")
@click.option(
    "--gta-path", type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--output", "-o", required=True, type=click.Path(path_type=Path))
def sdk_extract_rpf_entry(
    archive: Path, entry_path: str, archive_path: str,
    gta_path: Path | None, output: Path,
) -> None:
    """Extract one exact root or nested-RPF entry without modifying the archive."""
    from allin1.detector import detect_gta_path
    from allin1.rpf_tools import RpfExplorerService

    game = gta_path.resolve() if gta_path else detect_gta_path()
    if game is None:
        raise click.ClickException("GTA V was not detected; pass --gta-path.")
    service = RpfExplorerService(PROJECT_ROOT, game)
    try:
        index = service.index(archive)
        matches = [
            item for item in index.entries
            if item.archive_path.casefold() == archive_path.casefold()
            and item.path.casefold() == entry_path.replace("\\", "/").strip("/").casefold()
        ]
        if len(matches) != 1:
            raise ValueError(
                "Entry was not found uniquely; export index-rpf and use its exact archive/path."
            )
        written = service.extract(index, matches[0], output)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Extracted read-only copy: {written}")


@sdk_group.command("plan-rpf-replacement")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("entry_path")
@click.argument("payload", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--archive-path", default="", help="Nested virtual archive path from index-rpf.")
@click.option(
    "--gta-path", type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--output", "-o", required=True, type=click.Path(path_type=Path))
def sdk_plan_rpf_replacement(
    archive: Path, entry_path: str, payload: Path, archive_path: str,
    gta_path: Path | None, output: Path,
) -> None:
    """Create a checksummed replacement plan; perform no RPF writes."""
    from allin1.detector import detect_gta_path
    from allin1.rpf_tools import RpfExplorerService

    game = gta_path.resolve() if gta_path else detect_gta_path()
    if game is None:
        raise click.ClickException("GTA V was not detected; pass --gta-path.")
    service = RpfExplorerService(PROJECT_ROOT, game)
    try:
        index = service.index(archive)
        normalized = entry_path.replace("\\", "/").strip("/").casefold()
        matches = [
            item for item in index.entries
            if item.archive_path.casefold() == archive_path.casefold()
            and item.path.casefold() == normalized
        ]
        if len(matches) != 1:
            raise ValueError(
                "Entry was not found uniquely; export index-rpf and use its exact archive/path."
            )
        plan = service.replacement_plan(index, matches[0], payload)
        destination = output.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote plan only; no archive was changed: {destination}")


@sdk_group.command("inspect-package-rpfs")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir", "-o", type=click.Path(file_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--gta-path", type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="GTA V root used to select the correct Legacy/Enhanced archive keys.",
)
def sdk_inspect_package_rpfs(
    source: Path, output_dir: Path, gta_path: Path | None,
) -> None:
    """Extract only packaged RPFs to temporary storage and inspect them read-only."""
    import re
    import tempfile

    from allin1.addon_importer import AddonPackageInspector, PackageAssetReader
    from allin1.detector import detect_gta_path
    from allin1.processes import run_hidden

    game = gta_path.resolve() if gta_path else detect_gta_path()
    if game is None:
        raise click.ClickException(
            "GTA V was not detected; pass --gta-path so the correct archive keys are used."
        )
    patcher = PROJECT_ROOT / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    if not patcher.is_file():
        raise click.ClickException(
            "RpfPatcher.exe is missing; run runtools.ps1 to build the SDK helper."
        )
    try:
        scan = AddonPackageInspector().inspect(source)
        reader = PackageAssetReader(source)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    archives = [entry for entry in scan.entries if entry.suffix == ".rpf"]
    if not archives:
        raise click.ClickException("Package contains no loose RPF members")
    if len(archives) > 20:
        raise click.ClickException("Package contains more than 20 RPF members to inspect safely")
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="allin1-package-rpf-") as temporary:
        temporary_root = Path(temporary)
        for index, entry in enumerate(archives, start=1):
            if entry.size > 512 * 1024 * 1024:
                raise click.ClickException(
                    f"RPF member exceeds the 512 MiB inspection limit: {entry.path}"
                )
            content = reader.read(entry.path, limit=entry.size + 1)
            if content.truncated or len(content.data) != entry.size:
                raise click.ClickException(
                    f"Could not read the complete RPF member: {entry.path}"
                )
            outer = temporary_root / f"outer-{index}.rpf"
            outer.write_bytes(content.data)
            inspected = run_hidden(
                [patcher, "inspect", game, outer], capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            if inspected.returncode:
                detail = (inspected.stderr or inspected.stdout or "unknown error").strip()
                raise click.ClickException(
                    f"RPF inspection failed for {entry.path}: {detail}"
                )
            report_parts = [
                f"PACKAGE MEMBER: {entry.path}\n",
                inspected.stdout,
            ]
            nested_names = []
            for line in inspected.stdout.splitlines():
                match = re.match(r"^\s+([^/\\]+\.rpf)\s+\[[^]]+\]\s*$", line)
                if match and match.group(1).casefold() not in {
                    name.casefold() for name in nested_names
                }:
                    nested_names.append(match.group(1))
            for nested_index, nested_name in enumerate(nested_names[:20], start=1):
                nested = temporary_root / f"outer-{index}-nested-{nested_index}.rpf"
                extracted = run_hidden(
                    [patcher, "extract-entry", game, outer, nested_name, nested],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                if extracted.returncode or not nested.is_file():
                    detail = (
                        extracted.stderr or extracted.stdout or "nested extraction failed"
                    ).strip()
                    report_parts.append(
                        f"\nNESTED RPF NOT INSPECTED: {nested_name}\n{detail}\n"
                    )
                    continue
                nested_report = run_hidden(
                    [patcher, "inspect", game, nested], capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )
                report_parts.extend([
                    f"\nNESTED PACKAGE MEMBER: {nested_name}\n",
                    nested_report.stdout if nested_report.returncode == 0 else (
                        nested_report.stderr or "nested inspection failed"
                    ),
                ])
            safe_name = "".join(
                character if character.isalnum() or character in "._-" else "-"
                for character in Path(entry.path).stem
            ).strip("-.") or f"archive-{index}"
            report_path = destination / f"{index:02d}-{safe_name}-rpf-report.txt"
            report_body = "".join(report_parts)
            resource_versions = sorted({
                int(value) for value in re.findall(r"\(res v(\d+)\)", report_body)
            })
            summary = (
                "ALLIN1 PACKAGE RPF SUMMARY\n"
                f"Source member: {entry.path}\n"
                f"Nested RPFs inspected: {len(nested_names[:20])}\n"
                "Resource versions observed: "
                + (", ".join(str(value) for value in resource_versions) or "none")
                + "\nCompatibility: verify these resource versions against the "
                "declared Legacy/Enhanced payload before packaging.\n\n"
            )
            report_path.write_text(summary + report_body, encoding="utf-8")
            written.append(report_path)
    click.echo(
        f"Inspected {len(written)} package RPF member(s) without installing them: "
        f"{destination}"
    )


@sdk_group.command("audit-folder")
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), required=True)
@click.option(
    "--draft-dir", type=click.Path(file_okay=False, path_type=Path),
    help="Optionally retain one generated review-only addon.json draft per package.",
)
def sdk_audit_folder(folder: Path, output: Path, draft_dir: Path | None) -> None:
    """Audit every supported package archive in a test/mod staging folder."""
    import tempfile

    from allin1.addon_importer import AddonDraftBuilder, AddonPackageInspector
    from allin1.addon_sdk import AddonLinker, AddonManifest

    root = folder.resolve()
    supported = {".oiv", ".zip", ".rar", ".7z"}
    archives = sorted(
        (item for item in root.iterdir() if item.is_file()
         and item.suffix.casefold() in supported),
        key=lambda item: item.name.casefold(),
    )
    incomplete = sorted(
        (item for item in root.iterdir() if item.is_file()
         and item.name.casefold().endswith(".crdownload")),
        key=lambda item: item.name.casefold(),
    )
    if not archives and not incomplete:
        raise click.ClickException("Folder contains no supported package archives")
    retained = draft_dir.resolve() if draft_dir else None
    if retained:
        retained.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str, str, int, int]] = []
    sections: list[str] = []
    for archive in archives:
        safe_stem = "".join(
            character if character.isalnum() or character in "._-" else "-"
            for character in archive.stem
        ).strip("-.") or "package"
        try:
            scan = AddonPackageInspector().inspect(archive)
            if retained:
                draft_path = retained / f"{safe_stem}.addon.json"
                AddonDraftBuilder().build(scan).write(draft_path)
                manifest = AddonManifest.load(draft_path)
                report = AddonLinker().link(manifest)
            else:
                with tempfile.TemporaryDirectory(prefix="allin1-sdk-audit-") as temporary:
                    draft_path = Path(temporary) / "addon.json"
                    AddonDraftBuilder().build(scan).write(draft_path)
                    manifest = AddonManifest.load(draft_path)
                    report = AddonLinker().link(manifest)
            status = "REVIEW" if scan.valid else "UNSAFE"
            rows.append((
                archive.name, status, scan.edition_tag, ", ".join(scan.package_kinds),
                scan.warning_count, report.error_count,
            ))
            sections.extend([
                f"## {archive.name}", "",
                f"- Status: **{status}**",
                f"- Package shapes: {', '.join(scan.package_kinds)}",
                f"- Inventory: {len(scan.entries):,} files / {scan.total_bytes:,} bytes",
                f"- Edition hints: {', '.join(scan.edition_hints) or 'unresolved'}",
                f"- Dependency hints: {', '.join(scan.dependency_hints) or 'unresolved'}",
                "- Plug-in headers: " + (
                    ", ".join(
                        f"{item.path}={item.architecture}"
                        + ("/.NET" if item.managed else "")
                        for item in scan.plugin_details
                    ) or "none"
                ),
                f"- Inferred targets: {', '.join(scan.installation_targets) or 'unresolved'}",
                f"- Linker: {report.error_count} errors / {report.warning_count} warnings",
                "",
            ])
            for finding in scan.findings:
                location = f" [{finding.path}]" if finding.path else ""
                sections.append(
                    f"- {finding.severity.upper()} `{finding.code}`{location}: "
                    f"{finding.message}"
                )
            for issue in report.issues:
                subject = f" [{issue.subject}]" if issue.subject else ""
                sections.append(
                    f"- LINK {issue.severity.upper()} `{issue.code}`{subject}: "
                    f"{issue.message}"
                )
            sections.append("")
        except (OSError, ValueError) as exc:
            rows.append((archive.name, "SCAN ERROR", "Unresolved", "unknown", 0, 1))
            sections.extend([
                f"## {archive.name}", "",
                "- Status: **SCAN ERROR**",
                f"- Error: {exc}", "",
            ])

    for partial in incomplete:
        rows.append((
            partial.name, "INCOMPLETE", "Unresolved", "partial download", 0, 1,
        ))
        sections.extend([
            f"## {partial.name}", "",
            "- Status: **INCOMPLETE DOWNLOAD**",
            "- The file was not parsed. Finish or remove the browser download first.",
            "",
        ])

    lines = [
        "# ALLIN1 SDK package-folder audit", "",
        f"Source: `{root}`", "",
        "| Package | Status | Edition | Detected shapes | Scan warnings | Link errors |",
        "|---|---:|---|---|---:|---:|",
    ]
    for name, status, edition, shapes, warnings, errors in rows:
        display_name = name.replace("|", "\\|")
        display_shapes = shapes.replace("|", "\\|")
        lines.append(
            f"| {display_name} | {status} | {edition} | "
            f"{display_shapes} | {warnings} | {errors} |"
        )
    lines.extend(["", *sections])
    destination = output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    click.echo(
        f"Audited {len(archives)} complete package(s) and "
        f"{len(incomplete)} incomplete download(s): {destination}"
    )


@main.command("export-catalog")
@click.option("--output", "-o", default=None, help="Output path (default: catalog/vehicles.json)")
@click.pass_context
def export_catalog(ctx: click.Context, output: str | None) -> None:
    """Export vehicle database as JSON for the web catalog."""
    import json

    from allin1.config import load_prices

    db = VehicleDatabase.load(VEHICLES_DB)
    prices = load_prices(PROJECT_ROOT / "prices_vehicles.toml")

    data = []
    for v in db.all_vehicles:
        entry = {
            "model": v.model,
            "name": v.name,
            "class": v.vehicle_class,
            "manufacturer": v.manufacturer,
            "price": prices.get(v.model, 0),
            "traffic": v.traffic,
        }
        data.append(entry)

    out_path = Path(output) if output else PROJECT_ROOT / "catalog" / "vehicles.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    click.echo(f"Exported {len(data)} vehicles to {out_path}")


@main.command("generate-vehiclelist")
@click.option("--output", "-o", default=None,
              help="Output path (default: script/src/VehicleList.cs)")
@click.pass_context
def generate_vehiclelist(ctx: click.Context, output: str | None) -> None:
    """Regenerate VehicleList.cs with display names and prices."""
    from allin1.generators.vehiclelist import generate_file

    out_path = (
        Path(output) if output
        else PROJECT_ROOT / "script" / "src" / "VehicleList.cs"
    )
    count = generate_file(VEHICLES_DB, PROJECT_ROOT / "prices_vehicles.toml", out_path)
    click.echo(f"Generated VehicleList.cs with {count} vehicles at {out_path}")


@main.command("generate-weaponlist")
@click.option("--output", "-o", default=None,
              help="Output path (default: script/src/WeaponList.cs)")
@click.pass_context
def generate_weaponlist(ctx: click.Context, output: str | None) -> None:
    """Regenerate WeaponList.cs from weapons.toml + prices_weapons.toml."""
    from allin1.generators.weaponlist import generate_file

    out_path = (
        Path(output) if output
        else PROJECT_ROOT / "script" / "src" / "WeaponList.cs"
    )
    count = generate_file(
        DATA_DIR / "weapons.toml",
        PROJECT_ROOT / "prices_weapons.toml",
        out_path,
    )
    click.echo(f"Generated WeaponList.cs with {count} weapons at {out_path}")


@main.command("import-previews")
@click.argument("source", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--kind",
    type=click.Choice(("vehicle", "weapon", "equipment"), case_sensitive=False),
    default="vehicle",
    show_default=True,
    help="Catalog whose captures should be imported.",
)
def import_previews(source: Path, kind: str) -> None:
    """Validate and import curated catalog preview PNGs."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    from allin1.preview_assets import GEAR_PREVIEW_ITEMS, merge_previews

    kind = kind.lower()
    if kind == "vehicle":
        item_ids = [vehicle.model for vehicle in VehicleDatabase.load(VEHICLES_DB)]
        destination_name = "previews"
    elif kind == "weapon":
        weapon_data = tomllib.loads((DATA_DIR / "weapons.toml").read_text())
        item_ids = [weapon["name"] for weapon in weapon_data.get("weapons", [])]
        destination_name = "weapon_previews"
    else:
        item_ids = list(GEAR_PREVIEW_ITEMS)
        destination_name = "equipment_previews"

    destination = PROJECT_ROOT / "script" / "dist" / destination_name
    result = merge_previews([source], destination, item_ids)
    click.echo(f"Imported {result.copied} valid {kind} preview(s).")
    if result.rejected:
        click.echo(f"Rejected {len(result.rejected)} invalid or unknown file(s).")
        for reason in result.rejected:
            click.echo(f"  - {reason}")


@main.command("audit-previews")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def audit_preview_quality(directory: Path) -> None:
    """Inspect captured previews for blank, transparent, or poor framing."""
    from allin1.preview_assets import audit_previews
    models = [vehicle.model for vehicle in VehicleDatabase.load(VEHICLES_DB)]
    results = audit_previews(directory, models)
    failed = {model: quality for model, quality in results.items() if not quality.valid}
    click.echo(f"Inspected {len(results)} preview(s); {len(failed)} need recapture.")
    for model, quality in failed.items():
        click.echo(f"  {model}: {'; '.join(quality.reasons)}", err=True)
    if failed:
        raise SystemExit(1)


@main.command("verify-preview-artifacts")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def verify_preview_artifacts(directory: Path) -> None:
    """Verify that a built YTD directory covers the complete vehicle catalog."""
    from allin1.preview_artifacts import verify_ytd_set

    report = verify_ytd_set(directory, len(VehicleDatabase.load(VEHICLES_DB)))
    if not report.valid:
        if report.missing_dicts:
            click.echo("Missing: " + ", ".join(report.missing_dicts), err=True)
        if report.unexpected_dicts:
            click.echo("Unexpected: " + ", ".join(report.unexpected_dicts), err=True)
        raise SystemExit(1)
    click.echo(f"Verified {len(report.present_dicts)} preview dictionaries.")


@main.command("analyze-client-log")
@click.argument("log_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--edition", type=click.Choice(["legacy", "enhanced"]), required=True)
@click.option("--output", type=click.Path(path_type=Path), default="ALLIN1_smoke_report.json")
def analyze_client_log_cmd(log_file: Path, edition: str, output: Path) -> None:
    """Convert an in-game structured client log into a smoke-test report."""
    from allin1.reliability import analyze_client_log, write_smoke_report

    analysis = analyze_client_log(log_file)
    passed = write_smoke_report(output, edition, analysis)
    click.echo(f"Smoke report: {output} ({'PASS' if passed else 'FAIL'})")
    if not passed:
        raise SystemExit(1)


@main.command("health-check")
@click.argument("gta_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--json-output", type=click.Path(path_type=Path))
def health_check_cmd(gta_path: Path, json_output: Path | None) -> None:
    """Run the pre-launch dependency, duplicate, and integrity scanner."""
    import json
    from allin1.health import scan_installation

    report = scan_installation(gta_path)
    click.echo(f"Edition: {report.edition}; launch safe: {report.launch_safe}")
    for issue in report.issues:
        click.echo(f"[{issue.severity.upper()}] {issue.message}")
    if json_output:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    if not report.launch_safe:
        raise SystemExit(1)


@main.command("repair-garage")
@click.argument("garage_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def repair_garage_cmd(garage_file: Path) -> None:
    """Repair slots and quarantine invalid entries in an ALLIN1 garage save."""
    from allin1.customization import GarageSaveStore

    models = {vehicle.model for vehicle in VehicleDatabase.load(VEHICLES_DB)}
    report = GarageSaveStore(garage_file, models).repair()
    click.echo(f"Kept {report.kept}; reassigned {report.reassigned}; quarantined {report.quarantined}.")


@main.command("qualification-report")
@click.argument("output", type=click.Path(path_type=Path))
@click.option("--coverage-report", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--minimum-coverage", type=float, default=91.0)
@click.option("--script-assembly", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--smoke-report", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
def qualification_report_cmd(output: Path, coverage_report: Path, minimum_coverage: float,
                             script_assembly: Path, smoke_report: Path) -> None:
    """Create a release qualification dashboard JSON file."""
    from allin1.qualification import build_report, checks_from_artifacts

    try:
        checks, metrics = checks_from_artifacts(
            coverage_report, script_assembly, smoke_report,
            minimum_coverage=minimum_coverage,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    report = build_report(output, checks, metrics=metrics)
    click.echo(f"Qualification: {'PASS' if report['passed'] else 'FAIL'} ({output})")
    if not report["passed"]:
        raise SystemExit(1)


@main.command("apply-update")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("destination", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--backup-dir", type=click.Path(path_type=Path), required=True)
def apply_update_cmd(archive: Path, destination: Path, backup_dir: Path) -> None:
    """Apply a local checksum-verified release archive transactionally."""
    from allin1.updater import deploy_release
    result = deploy_release(archive, destination, backup_dir)
    click.echo(f"Deployed {len(result.deployed)} files; rollback stored at {result.backup}.")


@main.command("rollback-update")
@click.argument("destination", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("backup", type=click.Path(exists=True, file_okay=False, path_type=Path))
def rollback_update_cmd(destination: Path, backup: Path) -> None:
    """Restore the files saved by the last transactional update."""
    from allin1.updater import rollback_update
    restored = rollback_update(destination, backup)
    click.echo(f"Restored {len(restored)} files.")


@main.command("build-release")
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output ZIP (default: output/GTAV-ALLIN1-<version>.zip)",
)
def build_release_cmd(output: Path | None) -> None:
    """Build and verify the minimal public Windows release archive."""
    from allin1.release import build_public_release

    destination = output or PROJECT_ROOT / "output" / f"GTAV-ALLIN1-{__version__}.zip"
    report = build_public_release(PROJECT_ROOT, destination)
    size = report.unpacked_bytes / (1024 * 1024)
    click.echo(
        f"Built ALLIN1 {report.version}: {report.file_count} files, "
        f"{size:.1f} MiB unpacked -> {report.archive}"
    )


@main.command("verify-release")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def verify_release_cmd(archive: Path) -> None:
    """Verify a public release ZIP without extracting or installing it."""
    from allin1.release import verify_public_release

    report = verify_public_release(archive)
    click.echo(f"Verified ALLIN1 {report.version} public release ({report.file_count} files).")


@main.command("diagnostics")
@click.option("--output", "-o", type=click.Path(path_type=Path),
              default="ALLIN1_diagnostics.zip")
@click.option("--scripts-dir", type=click.Path(path_type=Path), default=None)
def diagnostics_cmd(output: Path, scripts_dir: Path | None) -> None:
    """Create a redacted troubleshooting bundle for bug reports."""
    from allin1.diagnostics import create_diagnostic_bundle
    created = create_diagnostic_bundle(output, PROJECT_ROOT, scripts_dir)
    click.echo(f"Diagnostic bundle created: {created}")


if __name__ == "__main__":
    main()
