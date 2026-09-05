"""Optional, provider-neutral AI assistant component lifecycle.

The assistant is deliberately separate from the launcher and SDK payloads.  A
managed local package may contain a llama.cpp-compatible runtime and one GGUF
model, while advanced users may point at existing local files or a compatible
API.  Configuration never stores API secrets and defaults to disabled.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from allin1 import __version__
from allin1.versioning import normalize_version
from allin1.release_paths import contained, no_links, relative_path, strict_json, tree_files, unique_paths


ASSISTANT_PRODUCT = "ALLIN1-Assistant"
ASSISTANT_MANIFEST = "assistant-package.json"
ASSISTANT_CHECKSUMS = "checksums.json"
ASSISTANT_CONFIG = "config.json"
ASSISTANT_COMPONENT = "component"
ASSISTANT_PROFILES = ("low", "recommended")
ASSISTANT_MODES = ("disabled", "managed_local", "custom_local", "compatible_api")
CAPABILITY_JSON_SCHEMA = "structured_output.json_schema"
CAPABILITY_THINKING_REASONING = "thinking.reasoning_effort"
CAPABILITY_THINKING_TEMPLATE = "thinking.chat_template_kwargs"
CAPABILITY_THINKING_QWEN = "thinking.enable_thinking"
CAPABILITY_PROMPT_CACHE = "prompt_cache"
ASSISTANT_CAPABILITIES = frozenset({
    CAPABILITY_JSON_SCHEMA, CAPABILITY_THINKING_REASONING,
    CAPABILITY_THINKING_TEMPLATE, CAPABILITY_THINKING_QWEN,
    CAPABILITY_PROMPT_CACHE,
})
THINKING_CAPABILITIES = frozenset({
    CAPABILITY_THINKING_REASONING,
    CAPABILITY_THINKING_TEMPLATE,
    CAPABILITY_THINKING_QWEN,
})
LOCAL_LLAMA_CAPABILITIES = (
    CAPABILITY_JSON_SCHEMA, CAPABILITY_THINKING_TEMPLATE, CAPABILITY_PROMPT_CACHE,
)
GIB = 1024 ** 3
MAX_ASSISTANT_ARCHIVE_BYTES = 12 * 1024 * 1024 * 1024
MAX_ASSISTANT_EXTRACTED_BYTES = 16 * 1024 * 1024 * 1024
MAX_ASSISTANT_FILES = 2_000
_PACKAGE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class AssistantPackageInfo:
    package_id: str
    version: str
    display_name: str
    profile: str
    provider: str
    backend: str
    runtime_path: str
    model_path: str
    model_name: str
    model_family: str
    quantization: str
    minimum_ram_gb: int
    recommended_ram_gb: int
    file_count: int
    unpacked_size: int


@dataclass(frozen=True)
class AssistantDownload:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class AssistantSource:
    profile: str
    package_id: str
    version: str
    display_name: str
    model_name: str
    model_family: str
    quantization: str
    minimum_ram_gb: int
    recommended_ram_gb: int
    runtime_version: str
    runtime: AssistantDownload
    runtime_license: AssistantDownload
    model: AssistantDownload
    model_license: AssistantDownload
    runtime_project_url: str
    model_project_url: str
    base_model_project_url: str = ""

    @property
    def total_download_bytes(self) -> int:
        return sum((
            self.runtime.size, self.runtime_license.size,
            self.model.size, self.model_license.size,
        ))


_LLAMA_RUNTIME = AssistantDownload(
    name="llama-b10595-bin-win-cpu-x64.zip",
    url=(
        "https://github.com/ggml-org/llama.cpp/releases/download/b10595/"
        "llama-b10595-bin-win-cpu-x64.zip"
    ),
    size=18_136_128,
    sha256="b217d938baa442aac2808c0cb4b440fbd74882cc19ec8c2d3105e6c1d9cac4a8",
)
_LLAMA_LICENSE = AssistantDownload(
    name="llama.cpp-LICENSE.txt",
    url="https://raw.githubusercontent.com/ggml-org/llama.cpp/b10595/LICENSE",
    size=1_078,
    sha256="94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d",
)
_QWEN_LICENSE_SHA256 = (
    "bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a"
)
ASSISTANT_SOURCES: tuple[AssistantSource, ...] = (
    AssistantSource(
        profile="low", package_id="allin1.qwen3.5-4b", version="3.5.0",
        display_name="Qwen3.5 4B (Q4_K_M)", model_name="Qwen3.5-4B-Q4_K_M",
        model_family="Qwen3.5", quantization="Q4_K_M",
        minimum_ram_gb=8, recommended_ram_gb=12,
        runtime_version="b10595", runtime=_LLAMA_RUNTIME,
        runtime_license=_LLAMA_LICENSE,
        model=AssistantDownload(
            name="Qwen3.5-4B-Q4_K_M.gguf",
            url=(
                "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/"
                "e87f176479d0855a907a41277aca2f8ee7a09523/"
                "Qwen3.5-4B-Q4_K_M.gguf?download=true"
            ),
            size=2_740_937_888,
            sha256="00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4",
        ),
        model_license=AssistantDownload(
            name="Qwen-LICENSE.txt",
            url=(
                "https://huggingface.co/Qwen/Qwen3.5-4B/resolve/"
                "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/LICENSE?download=true"
            ),
            size=11_544, sha256=_QWEN_LICENSE_SHA256,
        ),
        runtime_project_url="https://github.com/ggml-org/llama.cpp",
        model_project_url="https://huggingface.co/unsloth/Qwen3.5-4B-GGUF",
        base_model_project_url="https://huggingface.co/Qwen/Qwen3.5-4B",
    ),
    AssistantSource(
        profile="recommended", package_id="allin1.qwen3.5-9b", version="3.5.0",
        display_name="Qwen3.5 9B (Q4_K_M)", model_name="Qwen3.5-9B-Q4_K_M",
        model_family="Qwen3.5", quantization="Q4_K_M",
        minimum_ram_gb=16, recommended_ram_gb=24,
        runtime_version="b10595", runtime=_LLAMA_RUNTIME,
        runtime_license=_LLAMA_LICENSE,
        model=AssistantDownload(
            name="Qwen3.5-9B-Q4_K_M.gguf",
            url=(
                "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/"
                "3885219b6810b007914f3a7950a8d1b469d598a5/"
                "Qwen3.5-9B-Q4_K_M.gguf?download=true"
            ),
            size=5_680_522_464,
            sha256="03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
        ),
        model_license=AssistantDownload(
            name="Qwen-LICENSE.txt",
            url=(
                "https://huggingface.co/Qwen/Qwen3.5-9B/resolve/"
                "c202236235762e1c871ad0ccb60c8ee5ba337b9a/LICENSE?download=true"
            ),
            size=11_544, sha256=_QWEN_LICENSE_SHA256,
        ),
        runtime_project_url="https://github.com/ggml-org/llama.cpp",
        model_project_url="https://huggingface.co/unsloth/Qwen3.5-9B-GGUF",
        base_model_project_url="https://huggingface.co/Qwen/Qwen3.5-9B",
    ),
)


@dataclass(frozen=True)
class AssistantConfig:
    schema: int = 1
    mode: str = "disabled"
    workflow: str = "installer"
    profile: str = "recommended"
    endpoint: str = "http://127.0.0.1:8080/v1"
    model_name: str = ""
    api_key_env: str = ""
    runtime_path: str = ""
    model_path: str = ""
    context_tokens: int = 8192
    temperature: float = 0.1
    capabilities: tuple[str, ...] = ()
    thinking: str = "provider_default"
    model_sha256: str = ""
    llama_cpp_revision: str = ""

    def __post_init__(self) -> None:
        if self.mode in {"managed_local", "custom_local"} and not self.capabilities:
            object.__setattr__(self, "capabilities", LOCAL_LLAMA_CAPABILITIES)
        if (
            self.thinking == "provider_default"
            and set(self.capabilities) & THINKING_CAPABILITIES
        ):
            object.__setattr__(self, "thinking", "disabled")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "AssistantConfig":
        if int(payload.get("schema", 0)) != 1:
            raise ValueError("Unsupported assistant configuration schema")
        raw_capabilities = payload.get("capabilities", [])
        if (
            not isinstance(raw_capabilities, list)
            or not all(isinstance(item, str) for item in raw_capabilities)
        ):
            raise ValueError("Assistant capabilities must be an array of names")
        config = cls(
            schema=1,
            mode=str(payload.get("mode", "disabled")),
            workflow=str(payload.get("workflow", "installer")),
            profile=str(payload.get("profile", "recommended")),
            endpoint=str(payload.get("endpoint", "")),
            model_name=str(payload.get("model_name", "")),
            api_key_env=str(payload.get("api_key_env", "")),
            runtime_path=str(payload.get("runtime_path", "")),
            model_path=str(payload.get("model_path", "")),
            context_tokens=int(payload.get("context_tokens", 8192)),
            temperature=float(payload.get("temperature", 0.1)),
            capabilities=tuple(raw_capabilities),
            thinking=str(payload.get("thinking", "provider_default")),
            model_sha256=str(payload.get("model_sha256", "")),
            llama_cpp_revision=str(payload.get("llama_cpp_revision", "")),
        )
        config.validate()
        return config

    def validate(self, root: Path | None = None) -> None:
        if self.mode not in ASSISTANT_MODES:
            raise ValueError(f"Unsupported assistant mode: {self.mode}")
        if self.workflow not in {"installer", "diagnostic"}:
            raise ValueError("Assistant workflow must be installer or diagnostic")
        if self.profile not in {*ASSISTANT_PROFILES, "custom"}:
            raise ValueError(f"Unsupported assistant profile: {self.profile}")
        if not 2048 <= self.context_tokens <= 32768:
            raise ValueError("Assistant context must be between 2,048 and 32,768 tokens")
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("Assistant temperature must be between 0.0 and 1.0")
        if (
            not isinstance(self.capabilities, tuple)
            or not all(isinstance(item, str) and item for item in self.capabilities)
        ):
            raise ValueError("Assistant capabilities must be an array of names")
        unknown = sorted(set(self.capabilities) - ASSISTANT_CAPABILITIES)
        if unknown:
            raise ValueError("Unsupported assistant capability: " + ", ".join(unknown))
        thinking_controls = set(self.capabilities) & THINKING_CAPABILITIES
        if len(thinking_controls) > 1:
            raise ValueError("Assistant provider declares ambiguous thinking controls")
        if self.thinking not in {"disabled", "enabled", "provider_default"}:
            raise ValueError(f"Unsupported assistant thinking setting: {self.thinking}")
        if self.thinking != "provider_default" and not thinking_controls:
            raise ValueError("Assistant thinking setting requires a declared control")
        if self.model_sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", self.model_sha256):
            raise ValueError("Assistant model_sha256 must be a SHA-256 digest")
        if self.api_key_env and not _ENV_NAME.fullmatch(self.api_key_env):
            raise ValueError("API-key environment variable name is invalid")
        if self.mode == "compatible_api":
            parsed = urlparse(self.endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Compatible API endpoint must be an HTTP(S) URL")
            if not self.model_name.strip():
                raise ValueError("Compatible API mode requires a model name")
            if CAPABILITY_JSON_SCHEMA not in self.capabilities:
                raise ValueError("Compatible API must declare JSON Schema capability")
            if len(thinking_controls) != 1:
                raise ValueError("Compatible API must declare one thinking-control style")
        if self.mode == "custom_local":
            _validate_runtime(Path(self.runtime_path), "Custom runtime")
            _validate_model(Path(self.model_path), "Custom model")
        if self.mode == "managed_local" and root is not None:
            status = read_assistant_status(root, validate_config=False)
            if not status.healthy:
                raise ValueError("Managed local assistant is not installed and healthy")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AssistantStatus:
    root: Path
    component_root: Path
    installed: bool
    healthy: bool
    enabled: bool
    detail: str
    package: AssistantPackageInfo | None
    config: AssistantConfig


@dataclass(frozen=True)
class AssistantHardwareSnapshot:
    system: str
    architecture: str
    total_ram_bytes: int
    free_disk_bytes: int
    logical_cpus: int
    avx: bool | None
    avx2: bool | None


@dataclass(frozen=True)
class AssistantHardwareReport:
    profile: str
    compatible: bool
    recommended_profile: str | None
    minimum_ram_gb: int
    recommended_ram_gb: int
    required_free_disk_bytes: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    snapshot: AssistantHardwareSnapshot

    @property
    def summary(self) -> str:
        if self.blockers:
            return "Not compatible: " + "; ".join(self.blockers)
        recommendation = (
            f" Recommended pack: {self.recommended_profile}."
            if self.recommended_profile else ""
        )
        if self.warnings:
            return "Compatible with cautions: " + "; ".join(self.warnings) + recommendation
        return "Hardware check passed." + recommendation

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "compatible": self.compatible,
            "recommended_profile": self.recommended_profile,
            "minimum_ram_gb": self.minimum_ram_gb,
            "recommended_ram_gb": self.recommended_ram_gb,
            "required_free_disk_bytes": self.required_free_disk_bytes,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "snapshot": asdict(self.snapshot),
        }


ProgressCallback = Callable[[str, int, int], None]


def _total_physical_memory() -> int:
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        return page_size * pages
    except (AttributeError, OSError, TypeError, ValueError):
        return 0


def _processor_feature(feature: int) -> bool | None:
    if os.name != "nt":
        return None
    try:
        import ctypes

        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(feature))
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _disk_probe(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def read_assistant_hardware(
    root: Path | None = None,
) -> AssistantHardwareSnapshot:
    """Read only the local resources relevant to the CPU-based managed packs."""
    target = (root or default_assistant_root()).resolve()
    try:
        free_disk = shutil.disk_usage(_disk_probe(target)).free
    except OSError:
        free_disk = 0
    return AssistantHardwareSnapshot(
        system=platform.system() or os.name,
        architecture=platform.machine() or "unknown",
        total_ram_bytes=_total_physical_memory(),
        free_disk_bytes=free_disk,
        logical_cpus=os.cpu_count() or 0,
        avx=_processor_feature(39),
        avx2=_processor_feature(40),
    )


def assess_assistant_hardware(
    profile: str,
    root: Path | None = None,
    *,
    archive_size: int = 0,
    unpacked_size: int = 0,
    package: AssistantPackageInfo | None = None,
    snapshot: AssistantHardwareSnapshot | None = None,
) -> AssistantHardwareReport:
    """Assess a managed model pack without probing or requiring a discrete GPU."""
    if profile not in ASSISTANT_PROFILES:
        raise ValueError(f"Unsupported assistant profile: {profile}")
    minimum_ram = package.minimum_ram_gb if package else (8 if profile == "low" else 16)
    recommended_ram = (
        package.recommended_ram_gb if package else (12 if profile == "low" else 24)
    )
    estimated_install = unpacked_size or (5 * GIB if profile == "low" else 10 * GIB)
    # During a managed release install the downloaded archive and extracted
    # component coexist until verification completes. Keep rollback/temp room.
    required_disk = estimated_install + archive_size + 2 * GIB
    hardware = snapshot or read_assistant_hardware(root)
    blockers: list[str] = []
    warnings: list[str] = []
    system = hardware.system.casefold()
    architecture = hardware.architecture.casefold()
    if system != "windows":
        blockers.append("managed packs currently require 64-bit Windows")
    elif architecture not in {"amd64", "x86_64", "x64"}:
        blockers.append("managed packs require an x64 Windows processor")
    ram_gb = hardware.total_ram_bytes / GIB
    if not hardware.total_ram_bytes:
        warnings.append("physical memory could not be detected")
    elif ram_gb + 0.05 < minimum_ram:
        blockers.append(f"{minimum_ram} GB RAM is required ({ram_gb:.1f} GB detected)")
    elif ram_gb + 0.05 < recommended_ram:
        warnings.append(
            f"{recommended_ram} GB RAM is recommended ({ram_gb:.1f} GB detected)"
        )
    if not hardware.free_disk_bytes:
        blockers.append("free disk space could not be verified")
    elif hardware.free_disk_bytes < required_disk:
        blockers.append(
            f"{required_disk / GIB:.1f} GB free disk space is required "
            f"({hardware.free_disk_bytes / GIB:.1f} GB detected)"
        )
    minimum_cpus = 4 if profile == "low" else 6
    if hardware.logical_cpus and hardware.logical_cpus < 2:
        blockers.append("at least 2 logical CPU threads are required")
    elif not hardware.logical_cpus:
        warnings.append("CPU thread count could not be detected")
    elif hardware.logical_cpus < minimum_cpus:
        warnings.append(
            f"{minimum_cpus} or more logical CPU threads are recommended "
            f"({hardware.logical_cpus} detected)"
        )
    if hardware.avx is False:
        warnings.append("AVX acceleration is unavailable; responses may be very slow")
    elif hardware.avx2 is False:
        warnings.append("AVX2 acceleration is unavailable; responses may be slower")
    recommended_profile: str | None = None
    if not blockers:
        recommended_profile = (
            "recommended" if ram_gb >= 24 and hardware.logical_cpus >= 8 else "low"
        )
    return AssistantHardwareReport(
        profile=profile,
        compatible=not blockers,
        recommended_profile=recommended_profile,
        minimum_ram_gb=minimum_ram,
        recommended_ram_gb=recommended_ram,
        required_free_disk_bytes=required_disk,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        snapshot=hardware,
    )


def require_assistant_hardware(report: AssistantHardwareReport) -> None:
    if not report.compatible:
        raise ValueError("Assistant hardware check failed: " + "; ".join(report.blockers))


def default_assistant_root(environment: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environment is None else environment
    base = values.get("LOCALAPPDATA") or values.get("XDG_DATA_HOME")
    if base:
        return Path(base).expanduser().resolve() / "ALLIN1" / "Assistant"
    return Path.home().resolve() / ".allin1" / "Assistant"


def assistant_config_path(root: Path | None = None) -> Path:
    return contained(root or default_assistant_root(), ASSISTANT_CONFIG)


def load_assistant_config(root: Path | None = None) -> AssistantConfig:
    path = assistant_config_path(root)
    if not path.is_file():
        return AssistantConfig()
    try:
        payload = strict_json(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Assistant configuration is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Assistant configuration must be a JSON object")
    return AssistantConfig.from_dict(payload)


def save_assistant_config(
    config: AssistantConfig, root: Path | None = None,
) -> Path:
    target_root = no_links(root or default_assistant_root())
    config.validate(target_root)
    path = contained(target_root, ASSISTANT_CONFIG)
    target_root.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".writing")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(config.to_dict(), indent=2, allow_nan=False) + "\n")
        temporary.replace(no_links(path))
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _validate_runtime(path: Path, label: str) -> None:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} was not found: {resolved}")
    try:
        with resolved.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError(f"{label} is not a Windows executable")
    except OSError as exc:
        raise ValueError(f"{label} cannot be read: {exc}") from exc


def _validate_model(path: Path, label: str) -> None:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"{label} was not found: {resolved}")
    try:
        with resolved.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                raise ValueError(f"{label} is not a GGUF model")
    except OSError as exc:
        raise ValueError(f"{label} cannot be read: {exc}") from exc


def _safe_member(info: zipfile.ZipInfo) -> PurePosixPath:
    try:
        # zipfile normalizes Windows separators and truncates NUL-containing
        # names on construction; inspect the original archive spelling too.
        original = info.orig_filename
        if original != info.filename:
            raise ValueError("Archive member was normalized by zipfile")
        path = relative_path(original[:-1] if original.endswith("/") else original)
    except ValueError as exc:
        raise ValueError(f"Unsafe assistant package member: {info.filename}") from exc
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f"Assistant package contains a symbolic link: {info.filename}")
    if info.flag_bits & 0x1:
        raise ValueError(f"Assistant package contains an encrypted member: {info.filename}")
    return path


def _archive_entries(archive: zipfile.ZipFile):
    entries = archive.infolist()
    if len(entries) > MAX_ASSISTANT_FILES:
        raise ValueError("Assistant package contains too many files")
    if sum(entry.file_size for entry in entries) > MAX_ASSISTANT_EXTRACTED_BYTES:
        raise ValueError("Assistant package expands beyond the allowed size")
    planned = [(_safe_member(entry).as_posix(), entry) for entry in entries]
    seen = set()
    files = []
    for name, entry in planned:
        if name.casefold() in seen:
            raise ValueError("Assistant package contains duplicate file names")
        seen.add(name.casefold())
        if not entry.is_dir(): files.append(name)
    unique_paths(files)
    file_names = {name.casefold() for name in files}
    for name, entry in planned:
        if entry.is_dir() and any(part.as_posix().casefold() in file_names
                                 for part in (PurePosixPath(name), *PurePosixPath(name).parents)):
            raise ValueError("Assistant file/directory destination collision")
    return planned


def _package_info(
    manifest: Mapping[str, object], file_count: int, unpacked_size: int,
) -> AssistantPackageInfo:
    try:
        if manifest.get("product") != ASSISTANT_PRODUCT:
            raise ValueError("Assistant manifest names the wrong product")
        if type(manifest.get("schema")) is not int or manifest["schema"] != 1:
            raise ValueError("Unsupported assistant package schema")
        package_id = str(manifest["package_id"])
        if not _PACKAGE_ID.fullmatch(package_id):
            raise ValueError("Assistant package id is invalid")
        version = str(manifest["version"]).lstrip("vV")
        normalize_version(version)
        profile = str(manifest["profile"])
        if profile not in ASSISTANT_PROFILES:
            raise ValueError("Managed assistant profile must be low or recommended")
        runtime = manifest["runtime"]
        model = manifest["model"]
        requirements = manifest["requirements"]
        if not isinstance(runtime, dict) or not isinstance(model, dict):
            raise ValueError("Assistant runtime and model metadata must be objects")
        if not isinstance(requirements, dict):
            raise ValueError("Assistant requirements metadata must be an object")
        provider = str(runtime["provider"])
        if provider != "llama.cpp":
            raise ValueError("Managed assistant runtime provider must be llama.cpp")
        runtime_path = str(runtime["path"])
        model_path = str(model["path"])
        for value, label in ((runtime_path, "runtime"), (model_path, "model")):
            try:
                relative_path(value)
            except ValueError as exc:
                raise ValueError(f"Assistant {label} path is unsafe") from exc
        minimum_ram = int(requirements["minimum_ram_gb"])
        recommended_ram = int(requirements["recommended_ram_gb"])
        if not 1 <= minimum_ram <= recommended_ram <= 256:
            raise ValueError("Assistant RAM requirements are invalid")
        return AssistantPackageInfo(
            package_id=package_id,
            version=version,
            display_name=str(manifest["display_name"]),
            profile=profile,
            provider=provider,
            backend=str(runtime["backend"]),
            runtime_path=runtime_path,
            model_path=model_path,
            model_name=str(model["name"]),
            model_family=str(model["family"]),
            quantization=str(model["quantization"]),
            minimum_ram_gb=minimum_ram,
            recommended_ram_gb=recommended_ram,
            file_count=file_count,
            unpacked_size=unpacked_size,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Assistant"):
            raise
        raise ValueError(f"Assistant package metadata is invalid: {exc}") from exc


def inspect_assistant_archive(path: Path) -> AssistantPackageInfo:
    archive_path = no_links(path.expanduser())
    if archive_path.stat().st_size > MAX_ASSISTANT_ARCHIVE_BYTES:
        raise ValueError("Assistant package exceeds the allowed download size")
    with zipfile.ZipFile(archive_path) as archive:
        return _inspect_assistant_zip(archive)


def _inspect_assistant_zip(archive: zipfile.ZipFile) -> AssistantPackageInfo:
    files = [entry for _, entry in _archive_entries(archive) if not entry.is_dir()]
    if len(files) > MAX_ASSISTANT_FILES:
        raise ValueError("Assistant package contains too many files")
    unpacked_size = sum(entry.file_size for entry in files)
    if unpacked_size > MAX_ASSISTANT_EXTRACTED_BYTES:
        raise ValueError("Assistant package expands beyond the allowed size")
    names = {_safe_member(entry).as_posix(): entry for entry in files}
    if len(names) != len(files):
        raise ValueError("Assistant package contains duplicate file names")
    required = {ASSISTANT_MANIFEST, ASSISTANT_CHECKSUMS}
    missing = required - names.keys()
    if missing:
        raise ValueError("Assistant package is missing: " + ", ".join(sorted(missing)))
    try:
        manifest = strict_json(
            archive.read(names[ASSISTANT_MANIFEST]).decode("utf-8")
        )
        checksums = strict_json(
            archive.read(names[ASSISTANT_CHECKSUMS]).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Assistant package metadata is invalid: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(checksums, dict):
        raise ValueError("Assistant manifest and checksums must be objects")
    unique_paths(list(checksums))
    payload_names = set(names) - {ASSISTANT_CHECKSUMS}
    if set(checksums) != payload_names:
        raise ValueError("Assistant checksums must exactly match the package payload")
    for name, expected in checksums.items():
        digest = str(expected).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid assistant checksum for {name}")
        actual = hashlib.sha256()
        with archive.open(names[name]) as stream:
            while chunk := stream.read(1024 * 1024):
                actual.update(chunk)
        if actual.hexdigest() != digest:
            raise ValueError(f"Assistant package checksum mismatch: {name}")
    info = _package_info(manifest, len(payload_names), unpacked_size)
    if info.runtime_path not in names or info.model_path not in names:
        raise ValueError("Assistant package runtime or model payload is missing")
    licenses = manifest.get("licenses", [])
    if not isinstance(licenses, list) or not licenses:
        raise ValueError("Assistant package must retain runtime and model licenses")
    for license_path in licenses:
        relative_path(license_path)
        if license_path not in names:
            raise ValueError(f"Assistant license file is missing: {license_path}")
    with archive.open(names[info.runtime_path]) as runtime_stream:
        if runtime_stream.read(2) != b"MZ":
            raise ValueError("Assistant runtime is not a Windows executable")
    with archive.open(names[info.model_path]) as model_stream:
        if model_stream.read(4) != b"GGUF":
            raise ValueError("Assistant model is not a GGUF file")
    return info


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_installed_package(
    component_root: Path, *, verify_hashes: bool = False,
) -> AssistantPackageInfo:
    component_root = no_links(component_root)
    manifest_path = contained(component_root, ASSISTANT_MANIFEST)
    if not manifest_path.is_file():
        raise ValueError("Assistant installation metadata is missing")
    try:
        manifest = strict_json(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Assistant installation metadata is invalid: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Assistant installation metadata must be an object")
    checksums_path = contained(component_root, ASSISTANT_CHECKSUMS)
    try:
        checksums = strict_json(checksums_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Assistant installation checksums are invalid: {exc}") from exc
    if not isinstance(checksums, dict):
        raise ValueError("Assistant installation checksums must be an object")
    unique_paths(list(checksums))
    inventory = tree_files(component_root)
    files = list(inventory.values())
    payload = {name: path for name, path in inventory.items() if name != ASSISTANT_CHECKSUMS}
    if set(checksums) != set(payload):
        raise ValueError("Assistant installation checksums do not match its files")
    for name, path in payload.items():
        expected = str(checksums[name]).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Invalid installed assistant checksum for {name}")
        if verify_hashes and _file_sha256(path) != expected:
            raise ValueError(f"Installed assistant checksum mismatch: {name}")
    info = _package_info(manifest, len(files), sum(path.stat().st_size for path in files))
    runtime = contained(component_root, info.runtime_path)
    model = contained(component_root, info.model_path)
    _validate_runtime(runtime, "Managed assistant runtime")
    _validate_model(model, "Managed assistant model")
    return info


def verify_assistant_install(root: Path | None = None) -> AssistantPackageInfo:
    """Perform a full on-disk hash verification of the managed component."""
    target_root = no_links(root or default_assistant_root())
    component = target_root / ASSISTANT_COMPONENT
    if not component.is_dir():
        raise ValueError("No managed local assistant is installed")
    return _read_installed_package(component, verify_hashes=True)


def read_assistant_status(
    root: Path | None = None, *, validate_config: bool = True,
) -> AssistantStatus:
    target_root = no_links(root or default_assistant_root())
    component = target_root / ASSISTANT_COMPONENT
    try:
        config = load_assistant_config(target_root)
    except ValueError as exc:
        config = AssistantConfig()
        return AssistantStatus(
            target_root, component, component.is_dir(), False, False, str(exc), None,
            config,
        )
    installed = component.is_dir()
    package: AssistantPackageInfo | None = None
    healthy = False
    detail = "No managed local assistant is installed"
    if installed:
        try:
            package = _read_installed_package(component)
            healthy = True
            detail = f"{package.display_name} {package.version} is ready"
        except (OSError, ValueError) as exc:
            detail = str(exc)
    enabled = config.mode != "disabled"
    if validate_config and enabled:
        try:
            config.validate(target_root)
        except ValueError as exc:
            healthy = False
            detail = str(exc)
        else:
            if config.mode in {"custom_local", "compatible_api"}:
                healthy = True
                detail = (
                    "Custom local runtime is configured"
                    if config.mode == "custom_local" else "Compatible API is configured"
                )
    elif config.mode in {"custom_local", "compatible_api"}:
        healthy = True
        detail = (
            "Custom local runtime is configured"
            if config.mode == "custom_local" else "Compatible API is configured"
        )
    return AssistantStatus(
        target_root, component, installed, healthy, enabled, detail, package, config,
    )


def _transaction_paths(target_root: Path) -> tuple[Path, Path, Path]:
    component = contained(target_root, ASSISTANT_COMPONENT)
    pending = contained(target_root, f".{ASSISTANT_COMPONENT}.installing")
    backup = contained(target_root, f".{ASSISTANT_COMPONENT}.previous")
    return component, pending, backup


def _validate_transaction_roots(target_root: Path) -> tuple[Path, Path, Path]:
    paths = _transaction_paths(target_root)
    # Validate every root before the first cleanup, rename or destination write.
    for path in paths:
        if path.exists(): tree_files(path)
    return paths


def _remove_component_tree(target_root: Path, path: Path) -> None:
    if path not in _transaction_paths(target_root):
        raise ValueError("Assistant cleanup is outside its component roots")
    if path.exists():
        tree_files(path)
        shutil.rmtree(path)


def _prepare_assistant_transaction(target_root: Path) -> tuple[Path, Path, Path]:
    component, pending, backup = _validate_transaction_roots(target_root)
    if backup.exists() and not component.exists():
        _read_installed_package(backup, verify_hashes=True)
    target_root.mkdir(parents=True, exist_ok=True)
    if pending.exists():
        _remove_component_tree(target_root, pending)
    if backup.exists():
        if component.exists():
            _remove_component_tree(target_root, backup)
        else:
            backup.replace(component)
    pending.mkdir()
    return component, pending, backup


def _activate_assistant_transaction(
    target_root: Path, pending: Path, expected: AssistantPackageInfo,
) -> AssistantStatus:
    component, expected_pending, backup = _validate_transaction_roots(target_root)
    if pending != expected_pending or not pending.is_dir():
        raise RuntimeError("Assistant staging directory is not valid")
    installed = _read_installed_package(pending, verify_hashes=True)
    if installed.package_id != expected.package_id or installed.version != expected.version:
        raise RuntimeError("Assistant package changed during installation")
    if component.exists():
        component.replace(backup)
    try:
        pending.replace(component)
        status = read_assistant_status(target_root, validate_config=False)
        if not status.installed or not status.healthy:
            raise RuntimeError("Assistant installation failed its post-install validation")
    except Exception:
        if component.exists():
            _remove_component_tree(target_root, component)
        if backup.exists():
            backup.replace(component)
        raise
    if backup.exists():
        _remove_component_tree(target_root, backup)
    return status


def install_assistant_archive(
    archive_path: Path, root: Path | None = None, *,
    enforce_hardware: bool = True,
) -> AssistantStatus:
    target_root = no_links(root or default_assistant_root())
    archive_path = no_links(archive_path.expanduser())
    if archive_path.stat().st_size > MAX_ASSISTANT_ARCHIVE_BYTES:
        raise ValueError("Assistant package exceeds the allowed download size")
    # Keep the validated archive handle open through extraction. Never reopen a
    # different pathname's bytes after a successful preflight.
    with zipfile.ZipFile(archive_path) as archive:
        info = _inspect_assistant_zip(archive)
        if enforce_hardware:
            require_assistant_hardware(assess_assistant_hardware(
                info.profile, target_root, archive_size=archive_path.stat().st_size,
                unpacked_size=info.unpacked_size, package=info))
        _component, pending, _backup = _prepare_assistant_transaction(target_root)
        try:
            for name, entry in _archive_entries(archive):
                target = contained(pending, name)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, no_links(target).open("xb") as output:
                        shutil.copyfileobj(source, output)
            return _activate_assistant_transaction(target_root, pending, info)
        except Exception:
            _remove_component_tree(target_root, pending)
            raise


def uninstall_assistant(root: Path | None = None) -> bool:
    target_root = no_links(root or default_assistant_root())
    component, pending, backup = _validate_transaction_roots(target_root)
    contained(target_root, ASSISTANT_CONFIG)
    logs = [contained(target_root, name) for name in ("runtime.log", "runtime-state.json")]
    keys = [no_links(path) for path in target_root.glob(".runtime-api-key-*.txt")]
    try:
        config = load_assistant_config(target_root)
    except ValueError:
        # A corrupt configuration must not make the independently managed
        # runtime/model impossible to remove. Preserve the bad file for review.
        config = None
    managed_artifacts = (component, pending, backup)
    removed = any(path.exists() for path in managed_artifacts)
    for path in managed_artifacts:
        if path.exists():
            _remove_component_tree(target_root, path)
    for log_path in logs:
        if log_path.is_file():
            log_path.unlink()
            removed = True
    for key_path in keys:
        if key_path.is_file():
            key_path.unlink()
            removed = True
    if config is not None and config.mode == "managed_local":
        save_assistant_config(
            AssistantConfig(
                workflow=config.workflow, profile=config.profile,
                context_tokens=config.context_tokens, temperature=config.temperature,
            ),
            target_root,
        )
    return removed


def assistant_source(profile: str) -> AssistantSource:
    selected = profile.casefold()
    for source in ASSISTANT_SOURCES:
        if source.profile == selected:
            return source
    raise ValueError(f"Unsupported assistant profile: {profile}")


def _download_request(url: str) -> Request:
    return Request(url, headers={
        "Accept": "application/octet-stream",
        "User-Agent": f"GTAV-ALLIN1/{__version__}",
    })


def _download_verified(
    download: AssistantDownload, destination: Path, *,
    opener=urlopen, timeout: float,
    progress: ProgressCallback | None,
    completed: int, total: int, label: str,
) -> int:
    digest = hashlib.sha256()
    received = 0
    destination = no_links(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with opener(_download_request(download.url), timeout=timeout) as response:
        with destination.open("xb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > download.size:
                    raise ValueError(f"{download.name} exceeds its published size")
                output.write(chunk)
                digest.update(chunk)
                if progress:
                    progress(label, completed + received, total)
    if received != download.size:
        raise ValueError(
            f"{download.name} size mismatch: expected {download.size}, received {received}"
        )
    if digest.hexdigest() != download.sha256:
        raise ValueError(f"{download.name} failed SHA-256 verification")
    return completed + received


def _extract_runtime_archive(archive_path: Path, runtime_root: Path) -> None:
    with zipfile.ZipFile(no_links(archive_path)) as archive:
        planned = [(contained(runtime_root, name), entry) for name, entry in _archive_entries(archive)]
        for target, entry in planned:
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, no_links(target).open("xb") as output:
                shutil.copyfileobj(source, output)
    _validate_runtime(runtime_root / "llama-server.exe", "Managed assistant runtime")


def _source_manifest(source: AssistantSource) -> dict[str, object]:
    return {
        "schema": 1,
        "product": ASSISTANT_PRODUCT,
        "package_id": source.package_id,
        "version": source.version,
        "display_name": source.display_name,
        "profile": source.profile,
        "runtime": {
            "provider": "llama.cpp", "backend": "cpu",
            "path": "runtime/llama-server.exe", "version": source.runtime_version,
        },
        "model": {
            "path": f"models/{source.model.name}", "name": source.model_name,
            "family": source.model_family, "quantization": source.quantization,
        },
        "requirements": {
            "minimum_ram_gb": source.minimum_ram_gb,
            "recommended_ram_gb": source.recommended_ram_gb,
        },
        "licenses": [
            f"licenses/{source.runtime_license.name}",
            f"licenses/{source.model_license.name}",
        ],
        "provenance": {
            "distribution": "upstream-direct",
            "runtime_project": source.runtime_project_url,
            "runtime_archive": source.runtime.url,
            "runtime_sha256": source.runtime.sha256,
            "model_project": source.model_project_url,
            "base_model_project": source.base_model_project_url,
            "model_file": source.model.url,
            "model_sha256": source.model.sha256,
        },
    }


def install_qwen_source(
    profile: str, root: Path | None = None, *,
    timeout: float = 1800.0, opener=urlopen,
    progress: ProgressCallback | None = None,
    source: AssistantSource | None = None,
) -> AssistantStatus:
    """Download Qwen and llama.cpp from their pinned upstream sources."""
    selected = source or assistant_source(profile)
    if selected.profile != profile.casefold():
        raise ValueError("Assistant source profile does not match the selected profile")
    target_root = no_links(root or default_assistant_root())
    require_assistant_hardware(assess_assistant_hardware(
        selected.profile, target_root,
        archive_size=selected.total_download_bytes,
        unpacked_size=selected.model.size + selected.runtime.size,
    ))
    _component, pending, _backup = _prepare_assistant_transaction(target_root)
    runtime_archive = pending / ".runtime-download.zip"
    total = selected.total_download_bytes
    completed = 0
    try:
        completed = _download_verified(
            selected.runtime, runtime_archive, opener=opener, timeout=timeout,
            progress=progress, completed=completed, total=total,
            label="Downloading llama.cpp runtime",
        )
        _extract_runtime_archive(runtime_archive, pending / "runtime")
        runtime_archive.unlink()
        completed = _download_verified(
            selected.runtime_license,
            pending / "licenses" / selected.runtime_license.name,
            opener=opener, timeout=timeout, progress=progress,
            completed=completed, total=total, label="Downloading runtime license",
        )
        completed = _download_verified(
            selected.model_license,
            pending / "licenses" / selected.model_license.name,
            opener=opener, timeout=timeout, progress=progress,
            completed=completed, total=total, label="Downloading model license",
        )
        completed = _download_verified(
            selected.model, pending / "models" / selected.model.name,
            opener=opener, timeout=timeout, progress=progress,
            completed=completed, total=total, label=f"Downloading {selected.display_name}",
        )
        manifest_path = pending / ASSISTANT_MANIFEST
        manifest_path.write_text(
            json.dumps(_source_manifest(selected), indent=2) + "\n", encoding="utf-8",
        )
        checksums: dict[str, str] = {}
        for path in pending.rglob("*"):
            if path.is_file() and path.name != ASSISTANT_CHECKSUMS:
                relative = path.relative_to(pending).as_posix()
                checksums[relative] = (
                    selected.model.sha256
                    if relative == f"models/{selected.model.name}"
                    else _file_sha256(path)
                )
        (pending / ASSISTANT_CHECKSUMS).write_text(
            json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        expected = _package_info(
            _source_manifest(selected), len(checksums),
            sum(path.stat().st_size for path in pending.rglob("*") if path.is_file()),
        )
        if progress:
            progress("Verifying managed assistant", total, total)
        return _activate_assistant_transaction(target_root, pending, expected)
    except Exception:
        _remove_component_tree(target_root, pending)
        raise
