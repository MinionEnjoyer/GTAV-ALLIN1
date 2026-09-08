"""Read-only OIV operation planning and explicit managed-package conversion."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping
from xml.etree import ElementTree as ET

from allin1.addon_importer import (
    MAX_XML_BYTES,
    AddonPackageInspector,
    PackageAssetReader,
    _local_name,
    _parse_xml,
    _safe_member_path,
)


@dataclass(frozen=True)
class OivFinding:
    severity: str
    code: str
    message: str
    operation: int | None = None


@dataclass(frozen=True)
class OivOperation:
    number: int
    kind: str
    source: str
    target: str
    archives: tuple[str, ...]
    supported: bool
    detail: str


@dataclass(frozen=True)
class OivPlan:
    source: Path
    name: str
    version: str
    author: str
    editions: tuple[str, ...]
    operations: tuple[OivOperation, ...]
    findings: tuple[OivFinding, ...]
    package_format: str = "oiv"
    selection: tuple[str, ...] = ()

    @property
    def add_operations(self) -> tuple[OivOperation, ...]:
        return tuple(item for item in self.operations if item.kind == "add")

    @property
    def translatable(self) -> bool:
        return bool(self.add_operations) and not any(
            not item.supported for item in self.operations
        ) and not any(item.severity == "error" for item in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source), "name": self.name,
            "version": self.version, "author": self.author,
            "editions": list(self.editions),
            "package_format": self.package_format,
            "selection": list(self.selection),
            "translatable": self.translatable,
            "operations": [asdict(item) for item in self.operations],
            "findings": [asdict(item) for item in self.findings],
        }

    def to_markdown(self) -> str:
        result = "MANAGED EXPORT READY" if self.translatable else "REVIEW REQUIRED"
        lines = [
            f"# OIV operation plan: {self.name}", "",
            f"- Source: `{self.source}`",
            f"- Version: `{self.version or 'unknown'}`",
            f"- Author: `{self.author or 'unknown'}`",
            f"- Editions: {', '.join(value.title() for value in self.editions)}",
            f"- Package format: `{self.package_format}`",
            f"- Result: **{result}**", "",
            "## Ordered operations", "",
            "| # | Action | Archive | Source | Target | Translation |",
            "|---:|---|---|---|---|---|",
        ]
        for item in self.operations:
            archive = " → ".join(item.archives) or "filesystem"
            status = "managed" if item.supported else "manual review"
            lines.append(
                f"| {item.number} | {item.kind} | `{archive}` | "
                f"`{item.source or '-'}` | `{item.target or '-'}` | {status} |"
            )
        if self.selection:
            lines.extend(["", "## Flattened selection", ""])
            lines.extend(f"- `{value}`" for value in self.selection)
        lines.extend(["", "## Findings", ""])
        if not self.findings:
            lines.append("No recipe blockers were found.")
        for item in self.findings:
            location = f" (operation {item.operation})" if item.operation else ""
            lines.append(
                f"- **{item.severity.upper()} `{item.code}`**{location}: {item.message}"
            )
        lines.extend([
            "", "## Safety boundary", "",
            "This report does not execute the OIV. Managed export is available only "
            "when every declared operation can be represented as an owned file copy "
            "or exact RPF-entry transaction. Deletes, arbitrary text edits, XPath/PSO "
            "merges, deeply nested archives, and unknown commands remain blocked.", "",
        ])
        return "\n".join(lines)

    def write_report(self, destination: str | Path) -> Path:
        path = Path(destination).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
        path.with_suffix(".json").write_text(
            json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8",
        )
        return path


class OivWorkbench:
    """Parse actual OIV 2.x operations without executing package code."""

    _UNSUPPORTED = {"delete", "text", "xml", "pso", "defragmentation"}

    _COMPONENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")

    def inspect(
        self, source: str | Path, *, selection: str | None = None,
    ) -> OivPlan:
        package = Path(source).expanduser().resolve()
        scan = AddonPackageInspector().inspect(package)
        errors = [item for item in scan.findings if item.severity == "error"]
        if errors:
            raise ValueError(errors[0].message)
        entries = {item.path.casefold() for item in scan.entries}
        manifest_name = "super.xml" if (
            package.suffix.casefold() == ".oivs"
            or "super.xml" in entries
        ) else "assembly.xml"
        try:
            assembly = PackageAssetReader(package).read(
                manifest_name, limit=MAX_XML_BYTES,
            )
        except FileNotFoundError as exc:
            raise ValueError(
                f"OIV package does not contain root {manifest_name}"
            ) from exc
        root = _parse_xml(assembly.data, manifest_name)
        if manifest_name == "super.xml":
            return self._inspect_oivs(package, root, entries, selection)
        if selection:
            raise ValueError("--select is available only for .oivs packages")
        if _local_name(root.tag).casefold() != "package":
            raise ValueError("OIV assembly.xml root must be <package>")

        metadata = self._child(root, "metadata")
        name = self._text(metadata, "name") or package.stem
        version_node = self._child(metadata, "version")
        major = self._text(version_node, "major")
        minor = self._text(version_node, "minor")
        tag = self._text(version_node, "tag")
        version = ".".join(value for value in (major, minor) if value) or tag
        author_node = self._child(metadata, "author")
        author = self._text(author_node, "displayName")
        game_version = next((
            (item.text or "").strip().casefold() for item in root.iter()
            if _local_name(item.tag).casefold() == "gameversion"
        ), "")
        editions = (
            ("enhanced",) if game_version in {"enhanced", "gen9"}
            else ("legacy",) if game_version in {"legacy", "gen8"}
            else ("legacy", "enhanced")
        )

        operations: list[OivOperation] = []
        findings: list[OivFinding] = []
        content = self._child(root, "content")
        if content is None:
            findings.append(OivFinding(
                "error", "missing_content", "assembly.xml has no <content> recipe.",
            ))
        else:
            for child in content:
                self._walk(child, (), entries, operations, findings)
        if not any(item.kind == "add" for item in operations):
            findings.append(OivFinding(
                "warning", "no_managed_payload",
                "The recipe contains no file additions that ALLIN1 can own.",
            ))
        return OivPlan(
            package, name, version, author, editions,
            tuple(operations), tuple(findings),
        )

    def _inspect_oivs(
        self, package: Path, root: ET.Element, entries: set[str],
        selection_spec: str | None,
    ) -> OivPlan:
        if _local_name(root.tag).casefold() != "superpackage":
            raise ValueError("OIVS super.xml root must be <superpackage>")
        metadata = self._child(root, "metadata")
        name = self._text(metadata, "name") or package.stem
        version_node = self._child(metadata, "version")
        major = self._text(version_node, "major")
        minor = self._text(version_node, "minor")
        tag = self._text(version_node, "tag")
        version = ".".join(value for value in (major, minor) if value) or tag
        author = self._text(self._child(metadata, "author"), "displayName")
        game_version = self._text(root, "gameversion").casefold()
        editions = (
            ("enhanced",) if game_version in {"enhanced", "gen9"}
            else ("legacy",) if game_version in {"legacy", "gen8"}
            else ("legacy", "enhanced")
        )

        modules_parent = self._child(root, "modules")
        groups_parent = self._child(root, "groups")
        modules = [item for item in (() if modules_parent is None else modules_parent)
                   if _local_name(item.tag).casefold() == "module"]
        groups = [item for item in (() if groups_parent is None else groups_parent)
                  if _local_name(item.tag).casefold() == "group"]
        module_by_id = self._indexed_components(modules, "module")
        group_by_id = self._indexed_components(groups, "group")
        requested_modules, requested_groups = self._parse_oivs_selection(
            selection_spec, module_by_id, group_by_id,
        )

        chosen: list[tuple[str, ET.Element]] = []
        selection: list[str] = []
        for key, module in module_by_id.items():
            required = self._bool_attr(module, "required", False)
            enabled = required or key in requested_modules
            if enabled:
                chosen.append((f"module:{key}", module))
                selection.append(f"module:{key}" + (" (required)" if required else ""))

        for key, group in group_by_id.items():
            options = [item for item in group
                       if _local_name(item.tag).casefold() == "option"]
            option_by_id = self._indexed_components(options, f"option in group {key}")
            choice = requested_groups[key]
            allow_none = self._bool_attr(group, "allowNone", True)
            if choice == "none":
                if not allow_none:
                    raise ValueError(f"OIVS group '{key}' does not allow none")
                selection.append(f"group:{key}=none")
                continue
            option = option_by_id.get(choice)
            if option is None:
                raise ValueError(f"Unknown OIVS option '{choice}' for group '{key}'")
            chosen.append((f"group:{key}={choice}", option))
            selection.append(f"group:{key}={choice}")

        operations: list[OivOperation] = []
        findings: list[OivFinding] = []
        for label, component in chosen:
            install = self._child(component, "install")
            if install is None:
                findings.append(OivFinding(
                    "warning", "empty_component",
                    f"Selected OIVS component has no install recipe: {label}",
                ))
                continue
            for instruction in install:
                kind = _local_name(instruction.tag).casefold()
                if kind == "content":
                    for child in instruction:
                        self._walk(child, (), entries, operations, findings)
                elif kind == "folder":
                    self._expand_oivs_folder(
                        instruction.attrib.get("source", ""), entries,
                        operations, findings,
                    )
                else:
                    number = len(operations) + 1
                    operations.append(OivOperation(
                        number, kind, "", "", (), False,
                        "Unknown OIVS install instruction",
                    ))
                    findings.append(OivFinding(
                        "error", "unknown_oivs_instruction",
                        f"Unknown OIVS install instruction <{kind}> is blocked.",
                        number,
                    ))
        if not any(item.kind == "add" for item in operations):
            findings.append(OivFinding(
                "warning", "no_managed_payload",
                "The selected OIVS components contain no file additions that ALLIN1 can own.",
            ))
        return OivPlan(
            package, name, version, author, editions,
            tuple(operations), tuple(findings), "oivs", tuple(selection),
        )

    def _indexed_components(
        self, nodes: Iterable[ET.Element], label: str,
    ) -> dict[str, ET.Element]:
        result: dict[str, ET.Element] = {}
        for node in nodes:
            raw_id = node.attrib.get("id", "").strip()
            if not self._COMPONENT_ID.fullmatch(raw_id):
                raise ValueError(f"OIVS {label} has an invalid id: {raw_id or '<empty>'}")
            key = raw_id.casefold()
            if key in result:
                raise ValueError(f"OIVS {label} id is duplicated: {raw_id}")
            result[key] = node
        return result

    @staticmethod
    def _bool_attr(node: ET.Element, name: str, default: bool) -> bool:
        value = node.attrib.get(name)
        if value is None or not value.strip():
            return default
        if value.strip().casefold() not in {"true", "false"}:
            raise ValueError(f"OIVS {name} must be true or false")
        return value.strip().casefold() == "true"

    def _parse_oivs_selection(
        self, spec: str | None, modules: dict[str, ET.Element],
        groups: dict[str, ET.Element],
    ) -> tuple[set[str], dict[str, str]]:
        enabled = {
            key for key, module in modules.items()
            if self._bool_attr(module, "default", False)
        }
        choices = {
            key: group.attrib.get("default", "none").strip().casefold() or "none"
            for key, group in groups.items()
        }
        if spec is None:
            return enabled, choices
        explicit_groups: set[str] = set()
        for raw in re.split(r"[,;]", spec):
            token = raw.strip()
            if not token:
                continue
            if "=" in token:
                raw_group, raw_choice = token.split("=", 1)
                group = raw_group.strip().casefold()
                choice = raw_choice.strip().casefold()
                if group not in groups:
                    raise ValueError(f"Unknown OIVS group in selection: {raw_group.strip()}")
                if not choice or group in explicit_groups:
                    raise ValueError(f"Invalid or duplicate OIVS group selection: {token}")
                choices[group] = choice
                explicit_groups.add(group)
            else:
                disable = token.startswith(("-", "!"))
                module = (token[1:] if disable else token).strip().casefold()
                if module not in modules:
                    raise ValueError(f"Unknown OIVS module in selection: {token}")
                if disable:
                    enabled.discard(module)
                else:
                    enabled.add(module)
        return enabled, choices

    def _expand_oivs_folder(
        self, raw_source: str, entries: set[str],
        operations: list[OivOperation], findings: list[OivFinding],
    ) -> None:
        try:
            source = _safe_member_path(raw_source).as_posix()
        except ValueError as exc:
            findings.append(OivFinding(
                "error", "unsafe_folder_source", str(exc), len(operations) + 1,
            ))
            return
        prefix = f"content/{source}/".casefold()
        members = sorted(entry for entry in entries if entry.startswith(prefix))
        if not members:
            findings.append(OivFinding(
                "error", "missing_oivs_folder",
                f"OIVS folder source is absent or empty: content/{source}",
                len(operations) + 1,
            ))
            return
        for member in members:
            target = member[len(prefix):]
            number = len(operations) + 1
            supported = bool(target) and self._managed_file_target(target)
            operations.append(OivOperation(
                number, "add", member, target, (), supported,
                "Managed file copy from selected OIVS folder",
            ))
            if not supported:
                findings.append(OivFinding(
                    "error", "unsupported_destination",
                    f"The OIVS folder destination is outside ALLIN1's managed roots: {target}",
                    number,
                ))

    def _walk(
        self, node: ET.Element, archives: tuple[str, ...], entries: set[str],
        operations: list[OivOperation], findings: list[OivFinding],
    ) -> None:
        kind = _local_name(node.tag).casefold()
        number = len(operations) + 1
        if kind == "archive":
            raw_path = node.attrib.get("path", "").strip()
            path = self._target_path(raw_path, mods=not archives)
            create = node.attrib.get("createIfNotExist", "false").casefold() == "true"
            nested = archives + ((path or raw_path),)
            supported = bool(path) and len(nested) <= 2 and path.casefold().endswith(".rpf")
            operations.append(OivOperation(
                number, kind, "", path, archives, supported,
                "RPF operation container" + (
                    "; ALLIN1 clones the stock archive when missing" if create else ""
                ),
            ))
            if not supported:
                code = "nested_archive" if len(nested) > 2 else "unsafe_archive"
                findings.append(OivFinding(
                    "error", code,
                    "Only stock top-level archives and one bounded nested RPF member "
                    "can be translated into an exact transaction.", number,
                ))
            for child in node:
                self._walk(child, nested, entries, operations, findings)
            return

        source = node.attrib.get("source", "").strip() if kind == "add" else ""
        target = (node.text or "").strip() if kind in {"add", "delete"} else (
            node.attrib.get("path", "").strip()
        )
        supported = False
        detail = "OIV operation requires manual review"
        if kind == "add":
            try:
                source_path = _safe_member_path(source).as_posix()
                member = f"content/{source_path}".casefold()
                target_path = self._target_path(target, mods=not archives)
                supported = bool(target_path) and member in entries and len(archives) <= 2
                if not archives and target_path and not self._managed_file_target(target_path):
                    supported = False
                    findings.append(OivFinding(
                        "error", "unsupported_destination",
                        f"The destination is outside ALLIN1's managed roots: {target_path}",
                        number,
                    ))
                source = f"content/{source_path}"
                target = target_path
                detail = "Managed file copy" if not archives else "Exact RPF entry replacement"
                if member not in entries:
                    findings.append(OivFinding(
                        "error", "missing_oiv_source",
                        f"Recipe source is absent from the package: content/{source_path}",
                        number,
                    ))
                if not target_path:
                    findings.append(OivFinding(
                        "error", "unsafe_target", "Recipe target is empty or unsafe.", number,
                    ))
            except ValueError as exc:
                findings.append(OivFinding(
                    "error", "unsafe_source", str(exc), number,
                ))
        elif kind == "text" and self._managed_dlclist_insert(node, target, archives):
            target = self._target_path(target, mods=False)
            supported = True
            detail = "DLC registration is represented by the managed dlc_packs declaration"
        elif kind in self._UNSUPPORTED:
            findings.append(OivFinding(
                "error", f"unsupported_{kind}",
                f"The {kind} operation cannot be represented by the managed package schema.",
                number,
            ))
        else:
            findings.append(OivFinding(
                "error", "unknown_operation",
                f"Unknown OIV operation <{kind}> is blocked.", number,
            ))
        operations.append(OivOperation(
            number, kind, source, target, archives, supported, detail,
        ))

    @staticmethod
    def _target_path(value: str, *, mods: bool) -> str:
        normalized = value.replace("\\", "/").strip(" /\t\r\n")
        try:
            path = _safe_member_path(normalized).as_posix()
        except ValueError:
            return ""
        lowered = path.casefold()
        if mods and not lowered.startswith("mods/") and (
            lowered.startswith(("update/", "x64/")) or lowered.endswith(".rpf")
        ):
            path = f"mods/{path}"
        return path

    @classmethod
    def _managed_dlclist_insert(
        cls, node: ET.Element, target: str, archives: tuple[str, ...],
    ) -> bool:
        normalized = target.replace("\\", "/").strip(" /").casefold()
        if normalized != "common/data/dlclist.xml" or len(archives) != 1:
            return False
        children = list(node)
        if not children:
            return False
        pattern = re.compile(r"^<Item>dlcpacks:/[a-z0-9._-]+/</Item>$", re.I)
        return all(
            _local_name(child.tag).casefold() == "insert"
            and child.attrib.get("where", "").casefold() == "before"
            and child.attrib.get("condition", "").casefold() == "mask"
            and "</paths>" in child.attrib.get("line", "").casefold()
            and bool(pattern.fullmatch((child.text or "").strip()))
            for child in children
        )

    @staticmethod
    def _managed_file_target(value: str) -> bool:
        path = PurePosixPath(value)
        lowered = tuple(part.casefold() for part in path.parts)
        if len(lowered) == 1:
            return path.suffix.casefold() in {
                ".asi", ".dll", ".ini", ".toml", ".addon", ".addon64", ".md",
            }
        return lowered[0] in {"scripts", "mods", "reshade-shaders", "customshaders"}

    @staticmethod
    def _child(parent: ET.Element | None, name: str) -> ET.Element | None:
        if parent is None:
            return None
        expected = name.casefold()
        return next((
            item for item in parent
            if _local_name(item.tag).casefold() == expected
        ), None)

    @classmethod
    def _text(cls, parent: ET.Element | None, name: str) -> str:
        child = cls._child(parent, name)
        return (child.text or "").strip() if child is not None else ""

    def export_managed_package(
        self, plan: OivPlan, destination: str | Path, *,
        nested_original_sha256: Mapping[tuple[str, str], str] | None = None,
    ) -> Path:
        """Extract only proven add sources and emit a validated local package."""
        if not plan.translatable:
            raise ValueError("OIV recipe still contains unsupported or unsafe operations")
        root = Path(destination).expanduser().resolve()
        if root.exists() and any(root.iterdir()):
            raise ValueError("Managed-package destination must be empty")
        root.mkdir(parents=True, exist_ok=True)
        payload = root / "payload"
        payload.mkdir()

        files: list[tuple[str, str, str]] = []
        entries: list[tuple[str, str, str, str, str | None]] = []
        for index, operation in enumerate(plan.add_operations, start=1):
            name = PurePosixPath(operation.source).name
            relative = f"payload/{index:03d}_{name}"
            output = root / Path(*PurePosixPath(relative).parts)
            self._copy_member(plan.source, operation.source, output)
            digest = self._sha256(output)
            if operation.archives:
                entry = operation.target
                original = None
                if len(operation.archives) == 2:
                    entry = f"{operation.archives[1]}!{entry}"
                    original = (nested_original_sha256 or {}).get(
                        (operation.archives[0], entry)
                    )
                    if not original or not re.fullmatch(r"[0-9a-f]{64}", original):
                        raise ValueError(
                            "Nested RPF export requires the exact original member checksum: "
                            f"{operation.archives[0]}/{entry}"
                        )
                entries.append((relative, operation.archives[0], entry, digest, original))
            else:
                files.append((relative, operation.target, digest))

        dlc_packs = []
        pattern = re.compile(
            r"^mods/update/x64/dlcpacks/([a-z0-9._-]+)/dlc\.rpf$", re.I,
        )
        for _, target, _ in files:
            match = pattern.fullmatch(target)
            if match:
                dlc_packs.append(match.group(1))
        dependencies = ["openrpf"] if entries or any(
            target.casefold().startswith("mods/") for _, target, _ in files
        ) else []
        mod_type = self._mod_type(files, entries)
        mod_id = re.sub(r"[^a-z0-9._-]+", "-", plan.name.casefold()).strip("-._")
        mod_id = (mod_id or "imported-oiv")[:64]
        schema_version = 4 if any(item[4] for item in entries) else 1
        lines = [
            f"schema_version = {schema_version}", f"id = {json.dumps(mod_id)}",
            f"name = {json.dumps(plan.name)}",
            f"version = {json.dumps(plan.version or '1.0')}",
            f"type = {json.dumps(mod_type)}",
            "description = \"Converted from a fully translatable OIV recipe; review before installation.\"",
            "editions = [" + ", ".join(json.dumps(value) for value in plan.editions) + "]",
            "dependencies = [" + ", ".join(json.dumps(value) for value in dependencies) + "]",
            "dlc_packs = [" + ", ".join(json.dumps(value) for value in dlc_packs) + "]",
        ]
        for source, target, digest in files:
            lines.extend([
                "", "[[files]]", f"source = {json.dumps(source)}",
                f"destination = {json.dumps(target)}", f"sha256 = {json.dumps(digest)}",
            ])
        for source, archive, entry, digest, original in entries:
            lines.extend([
                "", "[[rpf_entries]]", f"source = {json.dumps(source)}",
                f"archive = {json.dumps(archive)}", f"entry = {json.dumps(entry)}",
                f"sha256 = {json.dumps(digest)}",
            ])
            if original:
                lines.append(f"original_sha256 = {json.dumps(original)}")
        manifest = root / "mod.toml"
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        from allin1.mods import ModManifest
        ModManifest.load(manifest)
        return manifest

    @staticmethod
    def _mod_type(
        files: Iterable[tuple[str, str, str]],
        entries: Iterable[tuple[str, str, str, str, str | None]],
    ) -> str:
        file_list = list(files)
        if list(entries):
            return "mixed" if file_list else "rpf"
        destinations = [PurePosixPath(item[1]) for item in file_list]
        if destinations and all(path.parts[0].casefold() == "scripts" for path in destinations):
            return "script"
        if destinations and all(len(path.parts) == 1 for path in destinations):
            return "asi"
        if destinations and all(
            path.parts[0].casefold() == "mods" and path.suffix.casefold() == ".rpf"
            for path in destinations
        ):
            return "rpf"
        return "mixed"

    @staticmethod
    def _copy_member(source: Path, member: str, destination: Path) -> None:
        relative = _safe_member_path(member).as_posix()
        if source.is_dir():
            candidate = source.joinpath(*PurePosixPath(relative).parts).resolve()
            if not candidate.is_relative_to(source) or not candidate.is_file():
                raise FileNotFoundError(f"OIV source disappeared: {relative}")
            shutil.copyfile(candidate, destination)
            return
        with zipfile.ZipFile(source) as package:
            matches = [item for item in package.infolist() if not item.is_dir() and
                       _safe_member_path(item.filename).as_posix().casefold() == relative.casefold()]
            if len(matches) != 1 or matches[0].flag_bits & 1:
                raise ValueError(f"OIV source is missing, ambiguous, or encrypted: {relative}")
            with package.open(matches[0]) as input_stream, destination.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
