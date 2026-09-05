from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

from allin1 import cli
from allin1 import assistant_manager as manager
from allin1.assistant_manager import (
    ASSISTANT_CHECKSUMS,
    ASSISTANT_MANIFEST,
    AssistantConfig,
    AssistantDownload,
    AssistantHardwareSnapshot,
    AssistantSource,
    assistant_source,
    assess_assistant_hardware,
    default_assistant_root,
    inspect_assistant_archive,
    install_assistant_archive,
    install_qwen_source,
    load_assistant_config,
    read_assistant_status,
    save_assistant_config,
    uninstall_assistant,
    verify_assistant_install,
)


def _package_bytes(
    *, profile: str = "low", runtime: bytes = b"MZruntime",
    model: bytes = b"GGUFmodel", manifest_changes: dict | None = None,
    omit: str | None = None, corrupt: str | None = None,
) -> bytes:
    manifest = {
        "schema": 1,
        "product": "ALLIN1-Assistant",
        "package_id": "allin1.test-model",
        "version": "0.5.1",
        "display_name": "ALLIN1 Test Model",
        "profile": profile,
        "runtime": {
            "provider": "llama.cpp", "backend": "cpu",
            "path": "runtime/llama-server.exe",
        },
        "model": {
            "path": "models/test.gguf", "name": "test-model",
            "family": "test", "quantization": "Q4_K_M",
        },
        "requirements": {"minimum_ram_gb": 8, "recommended_ram_gb": 12},
        "licenses": ["licenses/runtime.txt", "licenses/model.txt"],
    }
    if manifest_changes:
        manifest.update(manifest_changes)
    payload = {
        ASSISTANT_MANIFEST: json.dumps(manifest).encode(),
        "runtime/llama-server.exe": runtime,
        "models/test.gguf": model,
        "licenses/runtime.txt": b"runtime license",
        "licenses/model.txt": b"model license",
    }
    if omit:
        payload.pop(omit)
    checksums = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in payload.items()
    }
    if corrupt:
        checksums[corrupt] = "0" * 64
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
        archive.writestr(ASSISTANT_CHECKSUMS, json.dumps(checksums))
    return output.getvalue()


def _write_package(path: Path, **kwargs) -> Path:
    path.write_bytes(_package_bytes(**kwargs))
    return path


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _hardware(
    *, system: str = "Windows", architecture: str = "AMD64",
    ram: int = 32, disk: int = 80, cpus: int = 12,
    avx: bool | None = True, avx2: bool | None = True,
) -> AssistantHardwareSnapshot:
    return AssistantHardwareSnapshot(
        system, architecture, ram * manager.GIB, disk * manager.GIB,
        cpus, avx, avx2,
    )


def test_default_root_and_configuration_round_trip(tmp_path: Path) -> None:
    assert default_assistant_root({"LOCALAPPDATA": str(tmp_path)}) == (
        tmp_path / "ALLIN1" / "Assistant"
    ).resolve()
    assert load_assistant_config(tmp_path).mode == "disabled"
    config = AssistantConfig(
        mode="compatible_api", profile="custom",
        endpoint="http://127.0.0.1:9000/v1", model_name="local-model",
        api_key_env="ALLIN1_TEST_KEY", workflow="diagnostic",
        context_tokens=4096, temperature=0.25,
        capabilities=(
            manager.CAPABILITY_JSON_SCHEMA,
            manager.CAPABILITY_THINKING_TEMPLATE,
        ),
        thinking="disabled", llama_cpp_revision="b10595",
    )
    written = save_assistant_config(config, tmp_path)
    assert written == tmp_path.resolve() / "config.json"
    assert load_assistant_config(tmp_path) == config
    assert "secret" not in written.read_text(encoding="utf-8")
    assert default_assistant_root({}).parts[-2:] == (".allin1", "Assistant")


def test_configuration_and_status_report_malformed_files(tmp_path: Path) -> None:
    root = tmp_path / "assistant"
    root.mkdir()
    (root / "config.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="configuration is invalid"):
        load_assistant_config(root)
    status = read_assistant_status(root)
    assert not status.healthy and "configuration is invalid" in status.detail
    (root / "config.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_assistant_config(root)
    (root / "config.json").write_text('{"schema":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        load_assistant_config(root)
    with pytest.raises(ValueError, match="not installed"):
        AssistantConfig(mode="managed_local", profile="low").validate(root)


@pytest.mark.parametrize("changes,match", [
    ({"mode": "unknown"}, "Unsupported assistant mode"),
    ({"workflow": "chat"}, "installer or diagnostic"),
    ({"profile": "huge"}, "Unsupported assistant profile"),
    ({"context_tokens": 1000}, "2,048"),
    ({"temperature": 2.0}, "between 0.0 and 1.0"),
    ({"api_key_env": "BAD-NAME"}, "environment variable"),
    ({"mode": "compatible_api", "endpoint": "file:///model", "model_name": "x"},
     "HTTP"),
    ({"mode": "compatible_api", "model_name": ""}, "model name"),
])
def test_configuration_rejects_invalid_values(changes: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        replace(AssistantConfig(), **changes).validate()


def test_provider_capabilities_default_locally_and_fail_closed_for_api() -> None:
    local = AssistantConfig(mode="custom_local")
    assert local.capabilities == manager.LOCAL_LLAMA_CAPABILITIES
    assert local.thinking == "disabled"

    with pytest.raises(ValueError, match="JSON Schema capability"):
        AssistantConfig(
            mode="compatible_api", profile="custom",
            endpoint="https://example.invalid/v1", model_name="qwen",
        ).validate()
    with pytest.raises(ValueError, match="Unsupported assistant capability"):
        replace(AssistantConfig(), capabilities=("schema-ish",)).validate()
    with pytest.raises(ValueError, match="one thinking-control style"):
        AssistantConfig(
            mode="compatible_api", profile="custom",
            endpoint="https://example.invalid/v1", model_name="qwen",
            capabilities=(manager.CAPABILITY_JSON_SCHEMA,),
        ).validate()


def test_custom_local_configuration_checks_file_headers(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime.exe"
    model = tmp_path / "model.gguf"
    runtime.write_bytes(b"MZtest")
    model.write_bytes(b"GGUFtest")
    config = AssistantConfig(
        mode="custom_local", profile="custom",
        runtime_path=str(runtime), model_path=str(model),
    )
    save_assistant_config(config, tmp_path / "settings")
    assert read_assistant_status(tmp_path / "settings").healthy
    runtime.write_bytes(b"bad")
    with pytest.raises(ValueError, match="Windows executable"):
        config.validate()
    runtime.unlink()
    with pytest.raises(ValueError, match="was not found"):
        config.validate()
    runtime.write_bytes(b"MZtest")
    model.write_bytes(b"bad")
    with pytest.raises(ValueError, match="GGUF"):
        config.validate()


def test_hardware_reader_and_unknown_values(tmp_path: Path, monkeypatch) -> None:
    nested = tmp_path / "missing" / "assistant"
    snapshot = manager.read_assistant_hardware(nested)
    assert snapshot.system and snapshot.architecture
    assert snapshot.free_disk_bytes > 0
    assert snapshot.logical_cpus > 0
    monkeypatch.setattr(manager.shutil, "disk_usage", lambda _path: (_ for _ in ()).throw(OSError("disk")))
    assert manager.read_assistant_hardware(nested).free_disk_bytes == 0


def test_archive_install_status_and_independent_uninstall(tmp_path: Path) -> None:
    archive = _write_package(tmp_path / "assistant.zip")
    info = inspect_assistant_archive(archive)
    assert info.package_id == "allin1.test-model"
    assert info.model_name == "test-model"
    root = tmp_path / "installed"
    status = install_assistant_archive(archive, root, enforce_hardware=False)
    assert status.healthy and status.installed and not status.enabled
    external = root / "user-model.gguf"
    external.write_bytes(b"GGUFexternal")
    save_assistant_config(
        AssistantConfig(mode="managed_local", profile="low"), root,
    )
    (root / "runtime.log").write_text("managed log")
    (root / "runtime-state.json").write_text("{}")
    (root / ".runtime-api-key-test.txt").write_text("secret")
    assert read_assistant_status(root).enabled
    assert uninstall_assistant(root)
    assert external.is_file()
    assert not (root / "runtime.log").exists()
    assert not (root / "runtime-state.json").exists()
    assert not (root / ".runtime-api-key-test.txt").exists()
    assert load_assistant_config(root).mode == "disabled"
    assert not uninstall_assistant(root)


def test_install_replaces_existing_pack_and_cleans_transient_folders(tmp_path: Path) -> None:
    archive = _write_package(tmp_path / "assistant.zip")
    root = tmp_path / "managed"
    install_assistant_archive(archive, root, enforce_hardware=False)
    (root / "component" / "stale.txt").write_text("old")
    (root / ".component.installing").mkdir()
    (root / ".component.previous").mkdir()
    status = install_assistant_archive(archive, root, enforce_hardware=False)
    assert status.healthy
    assert not (root / "component" / "stale.txt").exists()
    assert not (root / ".component.installing").exists()
    assert not (root / ".component.previous").exists()


def test_install_blocks_incompatible_hardware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _write_package(tmp_path / "assistant.zip")
    failed = manager.AssistantHardwareReport(
        "low", False, None, 8, 12, 1, ("unsupported",), (), _hardware(),
    )
    monkeypatch.setattr(manager, "assess_assistant_hardware", lambda *_a, **_k: failed)
    with pytest.raises(ValueError, match="hardware check failed"):
        install_assistant_archive(archive, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_status_reports_broken_component_and_validation_modes(tmp_path: Path) -> None:
    root = tmp_path / "assistant"
    component = root / "component"
    component.mkdir(parents=True)
    status = read_assistant_status(root)
    assert status.installed and not status.healthy
    assert "metadata is missing" in status.detail
    (component / ASSISTANT_MANIFEST).write_text("not-json")
    assert "metadata is invalid" in read_assistant_status(root).detail
    (component / ASSISTANT_MANIFEST).write_text("[]")
    assert "must be an object" in read_assistant_status(root).detail

    runtime = tmp_path / "custom.exe"
    model = tmp_path / "custom.gguf"
    runtime.write_bytes(b"MZx")
    model.write_bytes(b"GGUFx")
    save_assistant_config(AssistantConfig(
        mode="custom_local", profile="custom",
        runtime_path=str(runtime), model_path=str(model),
    ), root)
    unchecked = read_assistant_status(root, validate_config=False)
    assert unchecked.healthy and "Custom local" in unchecked.detail


def test_uninstall_removes_component_even_with_invalid_config(tmp_path: Path) -> None:
    root = tmp_path / "assistant"
    (root / "component").mkdir(parents=True)
    (root / "config.json").write_text("invalid")
    assert uninstall_assistant(root)
    assert (root / "config.json").is_file()
    assert not (root / "component").exists()


@pytest.mark.parametrize("kwargs,match", [
    ({"runtime": b"ELF"}, "Windows executable"),
    ({"model": b"bad"}, "GGUF"),
    ({"omit": "licenses/model.txt"}, "license file is missing"),
    ({"corrupt": "models/test.gguf"}, "checksum mismatch"),
    ({"manifest_changes": {"product": "Other"}}, "wrong product"),
    ({"manifest_changes": {"profile": "huge"}}, "profile"),
    ({"manifest_changes": {"licenses": []}}, "retain"),
])
def test_archive_rejects_invalid_packages(
    tmp_path: Path, kwargs: dict, match: str,
) -> None:
    archive = _write_package(tmp_path / "bad.zip", **kwargs)
    with pytest.raises(ValueError, match=match):
        inspect_assistant_archive(archive)


def test_archive_rejects_unsafe_and_extra_members(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.zip"
    path.write_bytes(_package_bytes())
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("../escape", b"bad")
    with pytest.raises(ValueError, match="Unsafe"):
        inspect_assistant_archive(path)


@pytest.mark.parametrize("name,external,flags,match", [
    ("folder\\file", 0, 0, "Unsafe"),
    ("C:/escape", 0, 0, "Unsafe"),
    ("link", 0o120777 << 16, 0, "symbolic link"),
    ("encrypted", 0, 1, "encrypted"),
])
def test_member_validation_rejects_platform_unsafe_entries(
    name: str, external: int, flags: int, match: str,
) -> None:
    entry = zipfile.ZipInfo("safe")
    entry.filename = name
    entry.orig_filename = name
    entry.external_attr = external
    entry.flag_bits = flags
    with pytest.raises(ValueError, match=match):
        manager._safe_member(entry)


@pytest.mark.parametrize("changes,match", [
    ({"schema": 2}, "schema"),
    ({"package_id": "!"}, "id is invalid"),
    ({"version": "bad"}, "metadata is invalid"),
    ({"runtime": []}, "must be objects"),
    ({"requirements": []}, "must be an object"),
    ({"runtime": {"provider": "other", "backend": "cpu", "path": "runtime/x.exe"}},
     "provider"),
    ({"runtime": {"provider": "llama.cpp", "backend": "cpu", "path": "../x.exe"}},
     "path is unsafe"),
    ({"requirements": {"minimum_ram_gb": 20, "recommended_ram_gb": 10}},
     "RAM requirements"),
])
def test_archive_rejects_invalid_manifest_contract(
    tmp_path: Path, changes: dict, match: str,
) -> None:
    archive = _write_package(tmp_path / "contract.zip", manifest_changes=changes)
    with pytest.raises(ValueError, match=match):
        inspect_assistant_archive(archive)


def test_archive_rejects_missing_or_malformed_metadata(tmp_path: Path) -> None:
    missing = tmp_path / "missing.zip"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("readme.txt", b"x")
    with pytest.raises(ValueError, match="is missing"):
        inspect_assistant_archive(missing)

    malformed = tmp_path / "malformed.zip"
    with zipfile.ZipFile(malformed, "w") as archive:
        archive.writestr(ASSISTANT_MANIFEST, b"not-json")
        archive.writestr(ASSISTANT_CHECKSUMS, b"{}")
    with pytest.raises(ValueError, match="metadata is invalid"):
        inspect_assistant_archive(malformed)

    wrong_shape = tmp_path / "shape.zip"
    manifest = b"[]"
    with zipfile.ZipFile(wrong_shape, "w") as archive:
        archive.writestr(ASSISTANT_MANIFEST, manifest)
        archive.writestr(
            ASSISTANT_CHECKSUMS,
            json.dumps({ASSISTANT_MANIFEST: hashlib.sha256(manifest).hexdigest()}),
        )
    with pytest.raises(ValueError, match="must be objects"):
        inspect_assistant_archive(wrong_shape)


def test_archive_resource_and_checksum_contracts(tmp_path: Path, monkeypatch) -> None:
    archive = _write_package(tmp_path / "limits.zip")
    monkeypatch.setattr(manager, "MAX_ASSISTANT_ARCHIVE_BYTES", 1)
    with pytest.raises(ValueError, match="allowed download size"):
        inspect_assistant_archive(archive)
    monkeypatch.setattr(manager, "MAX_ASSISTANT_ARCHIVE_BYTES", 10_000_000)
    monkeypatch.setattr(manager, "MAX_ASSISTANT_FILES", 1)
    with pytest.raises(ValueError, match="too many files"):
        inspect_assistant_archive(archive)
    monkeypatch.setattr(manager, "MAX_ASSISTANT_FILES", 100)
    monkeypatch.setattr(manager, "MAX_ASSISTANT_EXTRACTED_BYTES", 1)
    with pytest.raises(ValueError, match="expands beyond"):
        inspect_assistant_archive(archive)


def test_archive_rejects_unlisted_payload_and_invalid_digest(tmp_path: Path) -> None:
    extra = tmp_path / "extra.zip"
    extra.write_bytes(_package_bytes())
    with zipfile.ZipFile(extra, "a") as archive:
        archive.writestr("extra.bin", b"x")
    with pytest.raises(ValueError, match="exactly match"):
        inspect_assistant_archive(extra)

    invalid = tmp_path / "digest.zip"
    content = _package_bytes()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(invalid, "w") as target:
        for entry in source.infolist():
            if entry.filename == ASSISTANT_CHECKSUMS:
                checksums = json.loads(source.read(entry))
                checksums[ASSISTANT_MANIFEST] = "invalid"
                target.writestr(entry.filename, json.dumps(checksums))
            else:
                target.writestr(entry, source.read(entry))
    with pytest.raises(ValueError, match="Invalid assistant checksum"):
        inspect_assistant_archive(invalid)

    no_runtime = _write_package(
        tmp_path / "no-runtime.zip", omit="runtime/llama-server.exe",
    )
    with pytest.raises(ValueError, match="payload is missing"):
        inspect_assistant_archive(no_runtime)

    duplicate = tmp_path / "duplicate.zip"
    duplicate.write_bytes(_package_bytes())
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(duplicate, "a") as target:
            target.writestr(ASSISTANT_MANIFEST, b"duplicate")
    with pytest.raises(ValueError, match="duplicate file names"):
        inspect_assistant_archive(duplicate)


def test_hardware_assessment_blocks_and_recommends_profiles(tmp_path: Path) -> None:
    good = assess_assistant_hardware(
        "recommended", tmp_path, snapshot=_hardware(),
    )
    assert good.compatible
    assert good.recommended_profile == "recommended"
    assert good.to_dict()["snapshot"]["logical_cpus"] == 12
    assert "passed" in good.summary

    weak = assess_assistant_hardware(
        "low", tmp_path,
        snapshot=_hardware(system="Linux", architecture="x86", ram=4, disk=2, cpus=1),
    )
    assert not weak.compatible
    assert len(weak.blockers) >= 4
    assert weak.recommended_profile is None
    assert "Not compatible" in weak.summary

    caution = assess_assistant_hardware(
        "low", tmp_path,
        snapshot=_hardware(ram=10, cpus=3, avx2=False),
    )
    assert caution.compatible and len(caution.warnings) == 3
    assert caution.recommended_profile == "low"

    unknown = assess_assistant_hardware(
        "recommended", tmp_path,
        snapshot=_hardware(ram=0, disk=0, cpus=0, avx=None, avx2=None),
    )
    assert not unknown.compatible
    assert "could not be detected" in " ".join((*unknown.blockers, *unknown.warnings))

    wrong_arch = assess_assistant_hardware(
        "low", tmp_path, snapshot=_hardware(architecture="ARM64", avx=False),
    )
    assert not wrong_arch.compatible
    assert "x64" in wrong_arch.summary and "AVX" in " ".join(wrong_arch.warnings)


def test_hardware_assessment_validates_profile() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        assess_assistant_hardware("giant", snapshot=_hardware())
    with pytest.raises(ValueError, match="hardware check failed"):
        manager.require_assistant_hardware(
            assess_assistant_hardware("low", snapshot=_hardware(ram=2))
        )


def _source_fixture(*, profile: str = "low", corrupt_model_hash: bool = False):
    runtime_stream = io.BytesIO()
    with zipfile.ZipFile(runtime_stream, "w") as archive:
        archive.writestr("llama-server.exe", b"MZruntime")
        archive.writestr("ggml.dll", b"runtime dependency")
    payloads = {
        "https://test/runtime.zip": runtime_stream.getvalue(),
        "https://test/runtime-license": b"runtime license",
        "https://test/model.gguf": b"GGUFmodel",
        "https://test/model-license": b"model license",
    }

    def item(name: str, url: str) -> AssistantDownload:
        content = payloads[url]
        digest = hashlib.sha256(content).hexdigest()
        if corrupt_model_hash and name.endswith(".gguf"):
            digest = "0" * 64
        return AssistantDownload(name, url, len(content), digest)

    source = AssistantSource(
        profile, f"allin1.test-qwen-{profile}", "3.0.0", "Test Qwen",
        "test-qwen", "Qwen3", "Q4_K_M", 8, 12, "test-runtime",
        item("runtime.zip", "https://test/runtime.zip"),
        item("runtime.txt", "https://test/runtime-license"),
        item("model.gguf", "https://test/model.gguf"),
        item("model.txt", "https://test/model-license"),
        "https://test/runtime-project", "https://test/model-project",
    )
    return source, payloads


def test_upstream_source_catalog_is_pinned_and_separate() -> None:
    low = assistant_source("LOW")
    recommended = assistant_source("recommended")
    assert low.model_project_url.startswith("https://huggingface.co/unsloth/")
    assert low.base_model_project_url.startswith("https://huggingface.co/Qwen/")
    assert recommended.model_family == "Qwen3.5"
    assert recommended.model_name == "Qwen3.5-9B-Q4_K_M"
    assert recommended.model.size > low.model.size > 2 * manager.GIB
    assert len(low.model.sha256) == 64
    assert low.runtime.url.startswith("https://github.com/ggml-org/llama.cpp/")
    with pytest.raises(ValueError, match="Unsupported"):
        assistant_source("giant")


def test_upstream_download_verifies_installs_and_fully_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, payloads = _source_fixture()
    passed = manager.AssistantHardwareReport(
        "low", True, "low", 8, 12, 1, (), (), _hardware(),
    )
    monkeypatch.setattr(manager, "assess_assistant_hardware", lambda *_a, **_k: passed)
    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout, request.headers["User-agent"]))
        return _Response(payloads[request.full_url])

    progress = []
    root = tmp_path / "assistant"
    status = install_qwen_source(
        "low", root, source=source, timeout=3, opener=opener,
        progress=lambda *values: progress.append(values),
    )
    assert status.healthy and status.package.model_name == "test-qwen"
    assert verify_assistant_install(root).package_id == source.package_id
    manifest = json.loads((root / "component" / ASSISTANT_MANIFEST).read_text())
    assert manifest["provenance"]["distribution"] == "upstream-direct"
    assert len(calls) == 4 and all(call[1] == 3 for call in calls)
    assert progress[-1] == ("Verifying managed assistant", source.total_download_bytes,
                            source.total_download_bytes)


@pytest.mark.parametrize("failure", ["hash", "size", "profile"])
def test_upstream_install_rejects_invalid_source_and_preserves_previous_install(
    failure: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "assistant"
    install_assistant_archive(
        _write_package(tmp_path / "old.zip"), root, enforce_hardware=False,
    )
    source, payloads = _source_fixture(corrupt_model_hash=failure == "hash")
    if failure == "size":
        source = replace(source, model=replace(source.model, size=source.model.size + 1))
    if failure == "profile":
        source = replace(source, profile="recommended")
    passed = manager.AssistantHardwareReport(
        "low", True, "low", 8, 12, 1, (), (), _hardware(),
    )
    monkeypatch.setattr(manager, "assess_assistant_hardware", lambda *_a, **_k: passed)

    def opener(request, timeout):
        return _Response(payloads[request.full_url])

    with pytest.raises(ValueError):
        install_qwen_source("low", root, source=source, opener=opener)
    assert read_assistant_status(root).package.package_id == "allin1.test-model"
    assert not (root / ".component.installing").exists()


def test_full_verification_detects_tampering(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No managed"):
        verify_assistant_install(tmp_path / "missing")
    root = tmp_path / "assistant"
    install_assistant_archive(
        _write_package(tmp_path / "assistant.zip"), root, enforce_hardware=False,
    )
    (root / "component" / "models" / "test.gguf").write_bytes(b"GGUFtampered")
    assert read_assistant_status(root).healthy
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_assistant_install(root)


def test_assistant_cli_configuration_hardware_and_package_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    root = tmp_path / "assistant"
    runner = CliRunner()
    denied = runner.invoke(cli.main, [
        "assistant", "configure", "--root", str(root), "--mode", "disabled",
    ])
    assert denied.exit_code == 1 and "requires --yes" in denied.output
    configured = runner.invoke(cli.main, [
        "assistant", "configure", "--root", str(root), "--yes",
        "--mode", "compatible_api", "--profile", "custom",
        "--endpoint", "http://localhost:9000/v1", "--model-name", "test",
    ])
    assert configured.exit_code == 0
    status = runner.invoke(cli.main, ["assistant", "status", "--root", str(root)])
    assert status.exit_code == 0
    assert json.loads(status.output)["configuration"]["mode"] == "compatible_api"

    passed = manager.AssistantHardwareReport(
        "low", True, "low", 8, 12, 1, (), (), _hardware(),
    )
    monkeypatch.setattr(manager, "assess_assistant_hardware", lambda *_a, **_k: passed)
    hardware = runner.invoke(cli.main, [
        "assistant", "hardware-check", "--root", str(root), "--profile", "low",
    ])
    assert hardware.exit_code == 0
    assert json.loads(hardware.output)["compatible"] is True

    archive = _write_package(tmp_path / "assistant.zip")
    installed = runner.invoke(cli.main, [
        "assistant", "install-package", str(archive), "--root", str(root), "--yes",
    ])
    assert installed.exit_code == 0 and "remains disabled" in installed.output
    package_status = runner.invoke(
        cli.main, ["assistant", "status", "--root", str(root)],
    )
    assert json.loads(package_status.output)["package"]["model"] == "test-model"

    runtime = tmp_path / "runtime.exe"
    model = tmp_path / "model.gguf"
    runtime.write_bytes(b"MZlocal")
    model.write_bytes(b"GGUFcustom")
    custom = runner.invoke(cli.main, [
        "assistant", "configure", "--root", str(root), "--yes",
        "--mode", "custom_local", "--profile", "custom",
        "--runtime-path", str(runtime), "--model-path", str(model),
        "--workflow", "diagnostic", "--context-tokens", "4096",
        "--temperature", "0.2", "--api-key-env", "LOCAL_MODEL_KEY",
    ])
    assert custom.exit_code == 0

    current_status = read_assistant_status(root, validate_config=False)
    def fake_qwen_install(profile, selected_root, source, progress):
        progress("Downloading test", 0, 0)
        progress("Downloading test", 1, 10)
        return current_status

    monkeypatch.setattr(manager, "install_qwen_source", fake_qwen_install)
    qwen_install = runner.invoke(cli.main, [
        "assistant", "install-qwen", "--profile", "low",
        "--root", str(root), "--yes",
    ])
    assert qwen_install.exit_code == 0 and "Installed" in qwen_install.output
    assert "Downloading test: 0%" in qwen_install.output

    denied_download = runner.invoke(cli.main, [
        "assistant", "install-qwen", "--profile", "low", "--root", str(root),
    ])
    assert denied_download.exit_code == 1 and "requires --yes" in denied_download.output
    verified = runner.invoke(cli.main, [
        "assistant", "verify", "--root", str(root),
    ])
    assert verified.exit_code == 0 and "Verified" in verified.output
    removed = runner.invoke(cli.main, [
        "assistant", "uninstall", "--root", str(root), "--yes",
    ])
    assert removed.exit_code == 0 and "removed" in removed.output


def test_launcher_console_forwards_prompt_to_managed_sdk_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from allin1.sdk_manager import SdkStatus
    import allin1.sdk_manager as sdk_manager

    sdk_root = tmp_path / "SDK"
    sdk_root.mkdir()
    executable = sdk_root / "ALLIN1-SDK-Desktop.exe"
    agent = sdk_root / "ALLIN1-SDK-Agent.exe"
    executable.write_bytes(b"MZsdk")
    agent.write_bytes(b"MZagent")
    monkeypatch.setattr(
        sdk_manager, "read_sdk_status",
        lambda: SdkStatus(sdk_root, executable, "0.5.1", True, "ready"),
    )
    seen = {}

    def run(command, **options):
        seen["command"] = command
        seen["options"] = options
        request = json.loads(options["input"])
        assert request["command"] == "assistant"
        assert request["args"][:4] == ["prompt", "How", "does", "this"]
        assert "--repository-root" in request["args"]
        assert request["args"][request["args"].index("--operation-mode") + 1] == "advisory"
        response = {
            "protocol": "1.0", "id": request["id"], "ok": True,
            "risk": "read_only", "result": {
                "exit_code": 0, "output": "Qwen console response\n",
            },
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(response) + "\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    result = CliRunner().invoke(cli.main, [
        "assistant", "prompt", "How", "does", "this", "work?",
        "--root", str(tmp_path / "assistant"), "--max-tokens", "200",
    ])
    assert result.exit_code == 0 and "Qwen console response" in result.output
    assert seen["command"] == [str(agent)]
    assert "shell" not in seen["options"]

    agent.unlink()
    missing = CliRunner().invoke(cli.main, ["assistant", "prompt", "hello"])
    assert missing.exit_code == 1 and "not installed and healthy" in missing.output


def test_configuration_contract_covers_capability_and_thinking_failures() -> None:
    with pytest.raises(ValueError, match="array of names"):
        AssistantConfig.from_dict({"schema": 1, "capabilities": "schema"})
    with pytest.raises(ValueError, match="array of names"):
        AssistantConfig(capabilities=[manager.CAPABILITY_JSON_SCHEMA]).validate()
    with pytest.raises(ValueError, match="ambiguous thinking controls"):
        AssistantConfig(capabilities=(
            manager.CAPABILITY_THINKING_REASONING,
            manager.CAPABILITY_THINKING_TEMPLATE,
        )).validate()
    with pytest.raises(ValueError, match="thinking setting"):
        AssistantConfig(
            capabilities=(manager.CAPABILITY_THINKING_TEMPLATE,),
            thinking="sometimes",
        ).validate()
    with pytest.raises(ValueError, match="requires a declared control"):
        AssistantConfig(
            capabilities=(manager.CAPABILITY_PROMPT_CACHE,), thinking="enabled",
        ).validate()
    with pytest.raises(ValueError, match="SHA-256"):
        AssistantConfig(model_sha256="not-a-digest").validate()

    warned = manager.AssistantHardwareReport(
        "low", True, "low", 8, 12, 1, (), ("slow",), _hardware(),
    )
    assert warned.summary == "Compatible with cautions: slow Recommended pack: low."


def test_hardware_and_file_probes_fail_closed_on_unavailable_os_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager.os, "name", "posix")
    monkeypatch.setattr(
        manager.os, "sysconf",
        lambda key: 4096 if key == "SC_PAGE_SIZE" else 1024,
        raising=False,
    )
    assert manager._total_physical_memory() == 4096 * 1024
    assert manager._processor_feature(39) is None
    monkeypatch.setattr(
        manager.os, "sysconf",
        lambda _key: (_ for _ in ()).throw(OSError("unavailable")),
    )
    assert manager._total_physical_memory() == 0

    runtime = tmp_path / "runtime.exe"
    model = tmp_path / "model.gguf"
    runtime.write_bytes(b"MZruntime")
    model.write_bytes(b"GGUFmodel")
    original_runtime_open = Path.open
    monkeypatch.setattr(
        Path, "open",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(OSError("locked"))
        if self == runtime.resolve() else original_runtime_open(self, *args, **kwargs),
    )
    with pytest.raises(ValueError, match="cannot be read"):
        manager._validate_runtime(runtime, "Runtime")
    monkeypatch.setattr(Path, "open", original_runtime_open)

    original_open = Path.open
    monkeypatch.setattr(
        Path, "open",
        lambda self, *args, **kwargs: (_ for _ in ()).throw(OSError("locked"))
        if self == model.resolve() else original_open(self, *args, **kwargs),
    )
    with pytest.raises(ValueError, match="cannot be read"):
        manager._validate_model(model, "Model")


def test_installed_package_rejects_corrupt_checksum_authority(tmp_path: Path) -> None:
    root = tmp_path / "assistant"
    install_assistant_archive(
        _write_package(tmp_path / "assistant.zip"), root, enforce_hardware=False,
    )
    component = root / "component"
    checksums_path = component / ASSISTANT_CHECKSUMS
    original = checksums_path.read_text(encoding="utf-8")

    checksums_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="checksums are invalid"):
        manager._read_installed_package(component)
    checksums_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        manager._read_installed_package(component)
    checksums_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="do not match its files"):
        manager._read_installed_package(component)

    checksums = json.loads(original)
    checksums[next(iter(checksums))] = "invalid"
    checksums_path.write_text(json.dumps(checksums), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid installed assistant checksum"):
        manager._read_installed_package(component)


def test_transaction_recovery_rejects_changed_or_unhealthy_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _write_package(tmp_path / "assistant.zip")
    expected = inspect_assistant_archive(archive)
    donor = tmp_path / "donor"
    install_assistant_archive(archive, donor, enforce_hardware=False)

    recovered = tmp_path / "recovered"
    backup = recovered / ".component.previous"
    shutil.copytree(donor / "component", backup)
    component, pending, _ = manager._prepare_assistant_transaction(recovered)
    assert verify_assistant_install(recovered).package_id == expected.package_id
    assert pending.is_dir()
    with pytest.raises(RuntimeError, match="staging directory"):
        manager._activate_assistant_transaction(
            recovered, recovered / "wrong", expected,
        )

    changed = tmp_path / "changed"
    _, changed_pending, _ = manager._prepare_assistant_transaction(changed)
    changed_pending.rmdir()
    shutil.copytree(donor / "component", changed_pending)
    with pytest.raises(RuntimeError, match="changed during installation"):
        manager._activate_assistant_transaction(
            changed, changed_pending, replace(expected, version="9.9.9"),
        )

    rollback = tmp_path / "rollback"
    old_component = rollback / "component"
    old_component.mkdir(parents=True)
    (old_component / "old.txt").write_text("preserve", encoding="utf-8")
    _, rollback_pending, _ = manager._prepare_assistant_transaction(rollback)
    rollback_pending.rmdir()
    shutil.copytree(donor / "component", rollback_pending)
    unhealthy = type("Status", (), {"installed": False, "healthy": False})()
    monkeypatch.setattr(manager, "read_assistant_status", lambda *_a, **_k: unhealthy)
    with pytest.raises(RuntimeError, match="post-install validation"):
        manager._activate_assistant_transaction(rollback, rollback_pending, expected)
    assert (old_component / "old.txt").read_text(encoding="utf-8") == "preserve"


def test_archive_cleanup_download_overflow_and_runtime_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _write_package(tmp_path / "assistant.zip")
    root = tmp_path / "cleanup"
    monkeypatch.setattr(
        manager, "_activate_assistant_transaction",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("activation failed")),
    )
    with pytest.raises(RuntimeError, match="activation failed"):
        install_assistant_archive(archive, root, enforce_hardware=False)
    assert not (root / ".component.installing").exists()

    download = AssistantDownload(
        "oversized.bin", "https://example.invalid/oversized.bin", 1,
        hashlib.sha256(b"xx").hexdigest(),
    )
    with pytest.raises(ValueError, match="exceeds its published size"):
        manager._download_verified(
            download, tmp_path / "download.bin",
            opener=lambda *_a, **_k: _Response(b"xx"), timeout=1,
            progress=None, completed=0, total=1, label="Downloading",
        )

    runtime_archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(runtime_archive, "w") as bundle:
        bundle.writestr("folder/", b"")
        bundle.writestr("llama-server.exe", b"MZruntime")
    monkeypatch.setattr(manager, "MAX_ASSISTANT_FILES", 1)
    with pytest.raises(ValueError, match="too many files"):
        manager._extract_runtime_archive(runtime_archive, tmp_path / "too-many")
    monkeypatch.setattr(manager, "MAX_ASSISTANT_FILES", 10)
    runtime_root = tmp_path / "runtime"
    manager._extract_runtime_archive(runtime_archive, runtime_root)
    assert (runtime_root / "folder").is_dir()
    assert (runtime_root / "llama-server.exe").is_file()
