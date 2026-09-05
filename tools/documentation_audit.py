"""Offline documentation inventory/link checks and source-derived references.

Only project-owned manuals are in scope; independent mods and vendored tools
retain their own documentation. No URLs are fetched and no CLI action is run.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import importlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from allin1.release_paths import contained, strict_json


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_cli(product):
    import click
    package = "allin1" if product == "launcher" else "allin1_sdk"
    group = importlib.import_module(package + ".cli").main
    version = importlib.import_module(package).__version__
    executable = "allin1" if product == "launcher" else "allin1-sdk"
    output = [f"# {executable} command reference — {version}", "",
        "Generated from the Click command tree by `documentation_audit.py`; do not edit individual rows.", "",
        f"Use `{executable} COMMAND --help` for argument types, choices, defaults and complete safety requirements.",
        "Listing a command here does not authorize execution, imply React UI parity, or qualify a game write.", "",
        "| Command | Purpose | Parameters |", "| --- | --- | --- |"]
    def visit(command, prefix):
        params = [" / ".join(getattr(p, "opts", []) + getattr(p, "secondary_opts", [])) or p.name for p in command.params]
        output.append(f"| `{prefix}` | {cell(command.get_short_help_str(limit=200))} | {cell(', '.join(params))} |")
        if isinstance(command, click.Group):
            with click.Context(command) as context:
                for name in command.list_commands(context):
                    visit(command.get_command(context, name), prefix + " " + name)
    visit(group, executable)
    return "\n".join(output) + "\n"


def render_config():
    from allin1 import __version__
    from allin1.config import Config
    config = Config.default()
    output = [f"# Launcher configuration reference — {__version__}", "",
        "Generated from `Config.default()` by `documentation_audit.py`; these are source defaults, not your saved settings.", "",
        "The UI and `Config.validate()` enforce accepted ranges and combinations. Unknown or invalid values are not a migration shortcut.",
        "Use reviewed profile/configuration actions; edit live game configuration only with the game closed and a recoverable backup.", "",
        "The deprecated `gbay_menu_enabled` field exists for old configurations. New configurations use `gbay_ui_backend` (`auto`, `reactor`, `legacy`).",
        "`auto` prefers Reactor with a compatibility fallback; `reactor` does not silently select the legacy renderer."]
    for section in fields(config):
        value = getattr(config, section.name)
        output += ["", f"## [{section.name}]", "", "| Field | Type | Default |", "| --- | --- | --- |"]
        for item in fields(value):
            default = getattr(value, item.name)
            output.append(f"| `{item.name}` | `{cell(item.type)}` | `{cell(json.dumps(default, ensure_ascii=False))}` |")
    return "\n".join(output) + "\n"


def prose(text):
    # Code examples can contain deliberately nonexistent paths and markdown.
    return re.sub(r"(?ms)^\s*(```|~~~)[^\n]*\n.*?^\s*\1[^\n]*(?:\n|$)", "", text)


def local_links(text):
    text = prose(text)
    for match in re.finditer(r"!?\[[^\]\n]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+\"[^\"]*\")?\)", text):
        yield match.group(1) or match.group(2)
    for match in re.finditer(r'(?im)^\s*\[[^\]]+\]:\s*<?([^\s>]+)>?', text):
        yield match.group(1)
    for match in re.finditer(r'<(?:img|a)\b[^>]*\b(?:src|href)="([^"]+)"', text):
        yield match.group(1)


def anchors(text):
    found, counts = set(), {}
    for title in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", prose(text)):
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        index = counts.get(slug, 0); counts[slug] = index + 1
        found.add(slug if not index else f"{slug}-{index}")
    found.update(re.findall(r'<(?:a|h[1-6])\b[^>]*\bid="([^"]+)"', text))
    return found


def audit(root, *, expected_references=None):
    catalog = strict_json((root / "docs/catalog.json").read_bytes())
    if type(catalog.get("schema_version")) is not int or catalog["schema_version"] != 1:
        raise ValueError("Unknown documentation catalog schema")
    documents = catalog["documents"]
    if not isinstance(documents, dict) or not documents:
        raise ValueError("Empty documentation catalog")
    discovered = {path.relative_to(root).as_posix()
                  for base in ("docs", "examples", "runtime/VehicleWorkbenchAxles", "sdk/examples")
                  for path in (root / base).rglob("*.md")
                  if not {"build", "out", "bin", "obj", ".git"}.intersection(path.relative_to(root).parts)}
    discovered.update(name for name in ("README.md", "RELEASE_NOTES.md", "CODE_SIGNING_POLICY.md", "RELEASE_SIGNING.md", "desktop/README.md", "tests/IN_GAME_CHECKLIST.md", "mods/README.md", "native/map-host/README.md") if (root / name).is_file())
    errors, history = [], []
    if discovered - set(documents): errors.append("Unclassified documents: " + ", ".join(sorted(discovered - set(documents))))
    for name, status in documents.items():
        source = contained(root, name)
        if status not in {"current", "reference", "architecture", "historical", "separate-product"}:
            errors.append(f"{name}: unknown documentation status"); continue
        if not source.is_file(): errors.append(f"{name}: missing document"); continue
        text = source.read_text(encoding="utf-8")
        if status == "historical":
            if "historical" not in text[:650].lower(): errors.append(f"{name}: missing prominent historical notice")
            history.append(name)
            continue  # Preserve historical evidence, not its obsolete local fixture links.
        for link in local_links(text):
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc: continue
            path = unquote(parsed.path)
            target = (source.parent / path).resolve() if path else source
            if not target.is_relative_to(root):
                errors.append(f"{name}: link leaves repository: {link}"); continue
            if not target.exists(): errors.append(f"{name}: broken local link: {link}"); continue
            if target.suffix == ".md" and parsed.fragment and unquote(parsed.fragment) not in anchors(target.read_text(encoding="utf-8")):
                errors.append(f"{name}: missing heading: {link}")
    for name, expected in (expected_references or {}).items():
        path = contained(root, name)
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            errors.append(f"{name}: generated reference differs from current source")
    return {"schema_version": 1, "kind": "documentation_audit", "status": "FAIL" if errors else "PASS",
            "documents": len(documents), "historical": history, "errors": errors,
            "external_urls": "NOT TESTED", "release_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", choices=("launcher", "sdk"), default="launcher")
    parser.add_argument("--sdk-source", type=Path)
    parser.add_argument("--render", choices=("cli", "config"))
    options = parser.parse_args()
    root = ROOT
    if options.product == "sdk":
        if options.sdk_source is None: parser.error("SDK requires an explicit --sdk-source")
        root = options.sdk_source.resolve(strict=True); sys.path.insert(0, str(root / "src"))
    if options.render:
        if options.render == "config" and options.product != "launcher": parser.error("Configuration reference is Launcher-owned")
        print(render_config() if options.render == "config" else render_cli(options.product), end="")
        return 0
    references = {"docs/cli-reference.md": render_cli(options.product)}
    if options.product == "launcher": references["docs/configuration-reference.md"] = render_config()
    result = audit(root, expected_references=references)
    print(json.dumps(result, indent=2))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
