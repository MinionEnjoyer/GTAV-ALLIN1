"""Command-line interface for GTA V ALLIN1."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from allin1.config import Config
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
@click.pass_context
def main(ctx: click.Context, config: str, verbose: bool) -> None:
    """GTA V ALLIN1 - Unlock all GTA Online vehicles in single player."""
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
            click.echo("WARNING: OpenRPF could not be installed automatically.")
            click.echo("Download it manually and place OpenRPF.asi in your GTA V folder:")
        else:
            click.echo("WARNING: OpenIV.asi not found in your GTA V folder.")
            click.echo("ALLIN1 requires OpenIV for vehicle preview textures:")
        click.echo("  https://www.gta5-mods.com/tools/openrpf-openiv-asi-for-gta-v-enhanced")
    else:
        asi_name = "OpenRPF" if result.is_enhanced else "OpenIV.asi"
        click.echo(f"{asi_name} installed.")

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
    click.echo(f"  Free mode: {config.general.free_mode}")
    click.echo(f"  Traffic: {'enabled' if config.traffic.enabled else 'disabled'}")
    click.echo(f"  Enable all: {config.vehicles.enable_all}")

    if config.vehicles.disabled_classes:
        click.echo(f"  Disabled classes: {', '.join(config.vehicles.disabled_classes)}")
    if config.vehicles.disabled_vehicles:
        click.echo(f"  Disabled vehicles: {len(config.vehicles.disabled_vehicles)} models")

    db = VehicleDatabase.load(VEHICLES_DB)
    click.echo(f"\nVehicle database: {len(db)} vehicles across {len(db.classes)} classes")


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
def import_previews(source: Path) -> None:
    """Validate and import PNGs made by the in-game preview capture tool."""
    from allin1.preview_assets import merge_previews

    db = VehicleDatabase.load(VEHICLES_DB)
    destination = PROJECT_ROOT / "script" / "dist" / "previews"
    result = merge_previews([source], destination, [v.model for v in db])
    click.echo(f"Imported {result.copied} valid vehicle preview(s).")
    if result.rejected:
        click.echo(f"Rejected {len(result.rejected)} invalid or unknown file(s).")
        for reason in result.rejected:
            click.echo(f"  - {reason}")


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

    checks = analyze_client_log(log_file)
    passed = write_smoke_report(output, edition, checks)
    click.echo(f"Smoke report: {output} ({'PASS' if passed else 'FAIL'})")
    if not passed:
        raise SystemExit(1)


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
