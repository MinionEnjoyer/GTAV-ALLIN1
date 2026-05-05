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
    prices = load_prices(PROJECT_ROOT / "prices.toml")

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


if __name__ == "__main__":
    main()
