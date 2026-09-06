"""Launcher automation commands, available in source and the portable sidecar."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import click

from allin1.desktop_service import LauncherService, serializable
from allin1.launcher_api import LauncherAPI, READS
from allin1.release_paths import no_links, strict_json
from allin1.runtime_resources import frozen_identity, resource_root


def emit(result):
    click.echo(json.dumps(serializable(result), allow_nan=False))


def document(path):
    source = no_links(path)
    if source.stat().st_size > 1024 * 1024: raise ValueError("Request exceeds 1 MiB")
    result = strict_json(source.read_bytes())
    if not isinstance(result, dict): raise ValueError("Request must be a JSON object")
    return result


@click.group()
@click.option("--project-root", type=click.Path(path_type=Path), default=None)
@click.option("--state-root", type=click.Path(path_type=Path), default=None, help="Explicit isolated preferences and managed-library root.")
@click.option("--allow-writes", is_flag=True, help="Allow explicitly confirmed mutations and external application opens.")
@click.option("--allow-game-writes", is_flag=True, help="Grant writes to the selected GTA installation; GTA must be closed.")
@click.option("--allow-launch", is_flag=True, help="Grant launching GTA after review and confirmation.")
@click.pass_context
def launcher(ctx, project_root, state_root, allow_writes, allow_game_writes, allow_launch):
    """Inspect, review and apply Launcher workflows. Read-only by default."""
    project = (project_root or resource_root()).resolve()
    identity = frozen_identity(project)
    from allin1.sdk_manager import default_sdk_root
    from allin1.mods import default_package_library_root
    from allin1.assistant_manager import default_assistant_root
    service = LauncherService(project,
        (state_root or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ALLIN1/Launcher").resolve(),
        allow_game_writes=allow_game_writes, allow_launch=allow_launch,
        sdk_root=None if state_root else default_sdk_root(),
        package_library_root=None if state_root else default_package_library_root(),
        assistant_root=None if state_root else default_assistant_root())
    service.build_identity = identity
    ctx.obj = LauncherAPI(service, allow_writes=allow_writes)


@launcher.command("catalog")
@click.pass_obj
def catalog(api):
    """List versioned operations, action parameters, risks and SDK handoff flow."""
    emit(api.read("catalog", {}))


@launcher.command("inspect")
@click.option("--module", default="setup", type=click.Choice(["setup", "gameplay", "input", "content", "mods", "package", "characters", "sdk", "activity", "help", "assistant_hardware"]))
@click.option("--source", type=click.Path(path_type=Path))
@click.option("--config-json", type=click.Path(exists=True, path_type=Path))
@click.pass_obj
def inspect(api, module, source, config_json):
    """Read a workspace or an SDK-exported ZIP/manifest; never install it."""
    emit(api.read("inspect", {"module": module, **({"source": str(source.resolve())} if source else {}),
        **({"config": document(config_json)} if config_json else {})}))


@launcher.command("request")
@click.argument("operation", type=click.Choice(list(READS)))
@click.option("--payload", type=click.Path(exists=True, path_type=Path), help="JSON object containing the operation parameters.")
@click.pass_obj
def request(api, operation, payload):
    """Execute a cataloged read operation."""
    emit(api.read(operation, document(payload) if payload else {}))


@launcher.command("review")
@click.option("--request", "request_file", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", type=click.Path(path_type=Path), help="New file for a five-minute, single-use approval plan.")
@click.pass_obj
def review(api, request_file, output):
    """Validate a proposed action and print a plan without executing it."""
    result = api.plan(document(request_file))
    if output:
        with no_links(output).open("x", encoding="utf-8") as stream:
            json.dump(result, stream, allow_nan=False, indent=2)
    emit(result)


@launcher.command("apply")
@click.option("--plan", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--approval-sha256", required=True)
@click.option("--confirm", is_flag=True, help="Acknowledge the exact reviewed changes.")
@click.pass_obj
def apply(api, plan, approval_sha256, confirm):
    """Apply a current plan with explicit process authority and approval."""
    emit(api.apply_plan(document(plan), approval_sha256, confirmed=confirm))


@launcher.command("agent-api")
@click.pass_obj
def agent_api(api):
    """Serve schema-v1 JSON lines over stdio; keep this process alive for reviews."""
    from allin1.desktop_host import serve
    serve(api, sys.stdin, sys.stdout)


def main(args=None):
    try:
        launcher.main(args=args, prog_name="allin1 launcher", standalone_mode=False)
    except (OSError, ValueError, click.ClickException) as error:
        emit({"schema_version": 1, "kind": "error", "message": str(error),
              "retry_policy": "Do not replay an interrupted apply; inspect files and receipts first."})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
