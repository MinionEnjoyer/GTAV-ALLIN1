from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from click import ClickException
from click.testing import CliRunner

import allin1.assistant_manager as assistant_manager
import allin1.cli as cli
import allin1.mods as mods
import allin1.sdk_manager as sdk_manager
import allin1.settings_assistant as settings_assistant
from allin1.config import Config
from allin1.extensions import ExtensionManifest, ExtensionRegistry


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FIXTURE = ROOT / "tests" / "contract_fixtures" / "mod_packages" / "schema_v1"
ONLINE_DESCRIPTOR = (
    ROOT / "content" / "allin1-online-content" / "allin1.content.json"
)


@pytest.fixture(autouse=True)
def _quiet_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)


def _game(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "GTA5_Enhanced.exe").write_bytes(b"exe")
    return path


def _invoke(
    runner: CliRunner, tmp_path: Path, args: list[str], *, input: str | None = None,
):
    return runner.invoke(
        cli.main, ["--config", str(tmp_path / "missing-config.toml"), *args], input=input,
    )


def _zip_fixture(archive: Path, *, unsafe: bool = False) -> None:
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for source in PACKAGE_FIXTURE.rglob("*"):
            if source.is_file():
                package.write(
                    source,
                    "source-repository/package/" + source.relative_to(PACKAGE_FIXTURE).as_posix(),
                )
        if unsafe:
            package.writestr("../outside.txt", "must never be extracted")


def _healthy_sdk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "SDK"
    root.mkdir(exist_ok=True)
    (root / "ALLIN1-SDK-Agent.exe").write_bytes(b"MZagent")
    monkeypatch.setattr(
        sdk_manager,
        "read_sdk_status",
        lambda: SimpleNamespace(root=root, healthy=True),
    )
    return root


def _completed(payload: object | None, *, stderr: str = "") -> SimpleNamespace:
    stdout = "" if payload is None else json.dumps(payload) + "\n"
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)


def test_content_zip_install_requires_confirmation_and_rejects_traversal(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    game = _game(tmp_path / "game")
    archive = tmp_path / "nested-package.zip"
    _zip_fixture(archive)

    refused = _invoke(
        runner,
        tmp_path,
        ["content", "install-package", str(archive), "--gta-path", str(game)],
        input="n\n",
    )
    assert refused.exit_code == 1
    assert "Aborted" in refused.output
    assert not (game / "scripts" / "ContractV1.dll").exists()

    installed = _invoke(
        runner,
        tmp_path,
        [
            "content", "install-package", str(archive), "--gta-path", str(game),
            "--yes",
        ],
    )
    assert installed.exit_code == 0, installed.output
    assert "Installed Cross-repository schema v1 contract 1.0.0" in installed.output
    assert (game / "scripts" / "ContractV1.dll").is_file()

    unsafe = tmp_path / "unsafe.zip"
    _zip_fixture(unsafe, unsafe=True)
    blocked_game = _game(tmp_path / "blocked-game")
    blocked = _invoke(
        runner,
        tmp_path,
        [
            "content", "install-package", str(unsafe), "--gta-path",
            str(blocked_game), "--yes",
        ],
    )
    assert blocked.exit_code != 0
    assert isinstance(blocked.exception, ValueError)
    assert "traversal" in str(blocked.exception)
    assert not (tmp_path / "outside.txt").exists()
    assert not (blocked_game / "scripts" / "ContractV1.dll").exists()


def test_content_listing_and_descriptor_validation_failure_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    monkeypatch.setattr(
        cli, "ExtensionCatalog",
        lambda _root: SimpleNamespace(discover=lambda: []),
    )
    monkeypatch.setattr(
        cli, "_content_game_path",
        lambda _ctx, _path: (_ for _ in ()).throw(ClickException("not detected")),
    )

    machine = _invoke(runner, tmp_path, ["content", "list", "--json-output"])
    assert machine.exit_code == 0, machine.output
    assert json.loads(machine.output) == {"api_version": 1, "bundled": [], "installed": []}
    text = _invoke(runner, tmp_path, ["content", "list"])
    assert text.exit_code == 0
    assert "No ALLIN1 content descriptors" in text.output

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    rejected = _invoke(
        runner, tmp_path, ["content", "list", "--gta-path", str(explicit)],
    )
    assert rejected.exit_code == 1
    assert "not detected" in rejected.output

    validated = _invoke(
        runner, tmp_path, ["content", "validate", str(ONLINE_DESCRIPTOR)],
    )
    assert validated.exit_code == 0, validated.output
    assert "PASS: allin1.online-content API 1" in validated.output


def test_content_list_translates_registry_read_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(tmp_path / "game")
    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)
    monkeypatch.setattr(
        cli, "ExtensionCatalog",
        lambda _root: SimpleNamespace(discover=lambda: []),
    )

    class BrokenRegistry:
        def __init__(self, _game: Path) -> None:
            pass

        def installed(self):
            raise OSError("registry unreadable")

    monkeypatch.setattr(cli, "ExtensionRegistry", BrokenRegistry)
    result = _invoke(CliRunner(), tmp_path, ["content", "list"])
    assert result.exit_code == 1
    assert "Could not read the installed content registry: registry unreadable" in result.output


def test_content_enable_disable_routes_and_missing_package_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(tmp_path / "game")
    entries = [
        {"id": "built.in", "name": "Built in", "source": "built-in"},
        {"id": "external.mod", "name": "External", "source": "package"},
    ]
    calls: list[tuple[str, str, bool]] = []

    class Registry:
        def __init__(self, _game: Path) -> None:
            pass

        def installed(self):
            return entries

        def set_builtin_enabled(self, extension_id: str, enabled: bool) -> None:
            calls.append(("built-in", extension_id, enabled))

    class Service:
        def __init__(self, _game: Path) -> None:
            pass

        def set_enabled(self, extension_id: str, enabled: bool) -> None:
            calls.append(("package", extension_id, enabled))

    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)
    monkeypatch.setattr(cli, "ExtensionRegistry", Registry)
    monkeypatch.setattr(mods, "ModIntegrationService", Service)
    runner = CliRunner()

    enabled = _invoke(
        runner, tmp_path, ["content", "enable", "built.in", "--gta-path", str(game), "--yes"],
    )
    disabled = _invoke(
        runner, tmp_path,
        ["content", "disable", "external.mod", "--gta-path", str(game), "--yes"],
    )
    missing = _invoke(
        runner, tmp_path, ["content", "enable", "MISSING", "--gta-path", str(game), "--yes"],
    )

    assert enabled.exit_code == disabled.exit_code == 0
    assert calls == [("built-in", "built.in", True), ("package", "external.mod", False)]
    assert missing.exit_code == 1
    assert "Content package is not installed: missing" in missing.output


def test_content_set_restores_every_tracked_file_after_writer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(tmp_path / "game")
    scripts = game / "scripts"
    scripts.mkdir()
    (scripts / "ALLIN1.dll").write_bytes(b"runtime")
    manifest = ExtensionManifest.load(ONLINE_DESCRIPTOR)
    registry = ExtensionRegistry(game)
    registry.register_builtin(manifest)
    config = Config.default()
    config.general.gta_path = str(game)
    config_path = tmp_path / "config.toml"
    config.save(config_path)
    runtime_config = scripts / "ALLIN1.toml"
    config.save(runtime_config)
    tracked = [config_path, runtime_config, registry.registry_path]
    before = {path: path.read_bytes() for path in tracked}

    def fail_after_partial_write(self, *_args, **_kwargs):
        self.settings.path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.path.write_text('{"partial": true}', encoding="utf-8")
        self.registry_path.write_text('{"partial": true}', encoding="utf-8")
        raise RuntimeError("simulated settings writer failure")

    monkeypatch.setattr(ExtensionRegistry, "set_setting", fail_after_partial_write)
    result = CliRunner().invoke(cli.main, [
        "--config", str(config_path), "content", "set", "allin1.online-content",
        "traffic_enabled", "false", "--gta-path", str(game), "--yes",
    ])

    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert config_path.read_bytes() == before[config_path]
    assert runtime_config.read_bytes() == before[runtime_config]
    original_registry = json.loads(before[registry.registry_path])
    restored_registry = json.loads(registry.registry_path.read_text(encoding="utf-8"))
    original_registry.pop("generated_at", None)
    restored_registry.pop("generated_at", None)
    assert restored_registry == original_registry
    assert not registry.settings.path.exists()
    assert not list(tmp_path.rglob("*.content-set-rollback"))


@pytest.mark.parametrize(
    ("contents", "message"),
    [("not-json", "Invalid settings proposal JSON"), ("[]", "must be a JSON object")],
)
def test_settings_proposal_reader_rejects_malformed_or_non_object_json(
    tmp_path: Path, contents: str, message: str,
) -> None:
    proposal = tmp_path / "proposal.json"
    proposal.write_text(contents, encoding="utf-8")
    result = _invoke(
        CliRunner(), tmp_path,
        ["content", "settings-preview", str(proposal), "--gta-path", str(_game(tmp_path / "game"))],
    )
    assert result.exit_code == 1
    assert message in result.output


def test_settings_cli_translates_catalog_preview_and_apply_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(tmp_path / "game")
    proposal = tmp_path / "proposal.json"
    proposal.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)
    runner = CliRunner()

    monkeypatch.setattr(settings_assistant, "build_settings_catalog", lambda *_a: {"count": 1})
    catalog = _invoke(runner, tmp_path, ["content", "settings-catalog", "package"])
    assert catalog.exit_code == 0
    assert json.loads(catalog.output) == {"count": 1}
    monkeypatch.setattr(
        settings_assistant, "build_settings_catalog",
        lambda *_a: (_ for _ in ()).throw(KeyError("missing package")),
    )
    failed_catalog = _invoke(runner, tmp_path, ["content", "settings-catalog", "package"])
    assert failed_catalog.exit_code == 1
    assert "missing package" in failed_catalog.output

    monkeypatch.setattr(
        settings_assistant, "preview_settings_proposal",
        lambda *_a: (_ for _ in ()).throw(ValueError("stale proposal")),
    )
    failed_preview = _invoke(
        runner, tmp_path, ["content", "settings-preview", str(proposal)],
    )
    assert failed_preview.exit_code == 1
    assert "stale proposal" in failed_preview.output

    preview = {
        "proposal_id": "proposal-123", "package_id": "package",
        "requires_explicit_apply": True,
    }
    monkeypatch.setattr(settings_assistant, "preview_settings_proposal", lambda *_a: preview)
    wrong_mode = _invoke(
        runner, tmp_path,
        ["content", "settings-apply", str(proposal), "--confirm-proposal-id", "proposal-123"],
    )
    assert wrong_mode.exit_code == 1
    assert "valid only with --yes" in wrong_mode.output
    refused = _invoke(
        runner, tmp_path, ["content", "settings-apply", str(proposal)], input="n\n",
    )
    assert refused.exit_code == 1
    assert "Aborted" in refused.output

    seen: list[str | None] = []

    def apply_ok(_game: Path, _raw: dict, *, confirmed_proposal_id: str | None):
        seen.append(confirmed_proposal_id)
        return {"applied": True}

    monkeypatch.setattr(settings_assistant, "apply_settings_proposal", apply_ok)
    accepted = _invoke(
        runner, tmp_path, ["content", "settings-apply", str(proposal)], input="y\n",
    )
    assert accepted.exit_code == 0, accepted.output
    assert seen == ["proposal-123"]

    monkeypatch.setattr(
        settings_assistant, "apply_settings_proposal",
        lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("write denied")),
    )
    failed_apply = _invoke(
        runner, tmp_path, [
            "content", "settings-apply", str(proposal), "--yes",
            "--confirm-proposal-id", "proposal-123",
        ],
    )
    assert failed_apply.exit_code == 1
    assert "write denied" in failed_apply.output


def test_assistant_hardware_cli_reports_incompatibility_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = SimpleNamespace(compatible=False, to_dict=lambda: {"compatible": False})
    monkeypatch.setattr(assistant_manager, "assess_assistant_hardware", lambda *_a: report)
    incompatible = _invoke(
        CliRunner(), tmp_path, ["assistant", "hardware-check", "--root", str(tmp_path / "assistant")],
    )
    assert incompatible.exit_code == 1
    assert json.loads(incompatible.output)["compatible"] is False

    monkeypatch.setattr(
        assistant_manager, "assess_assistant_hardware",
        lambda *_a: (_ for _ in ()).throw(ValueError("unsupported hardware")),
    )
    failed = _invoke(CliRunner(), tmp_path, ["assistant", "hardware-check"])
    assert failed.exit_code == 1
    assert "unsupported hardware" in failed.output


def test_assistant_prompt_forwards_every_optional_grounding_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk_root = _healthy_sdk(tmp_path, monkeypatch)
    game = _game(tmp_path / "game")
    config = Config.default()
    config.general.gta_path = str(game)
    config_path = tmp_path / "config.toml"
    config.save(config_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest = tmp_path / "mod.toml"
    source = tmp_path / "source.cpp"
    telemetry = tmp_path / "game.log"
    for path in (manifest, source, telemetry):
        path.write_text("fixture", encoding="utf-8")
    captured: dict = {}

    def run(_command, **options):
        captured["request"] = json.loads(options["input"])
        captured["cwd"] = options["cwd"]
        return _completed({"ok": True, "result": {"output": "grounded"}})

    monkeypatch.setattr(subprocess, "run", run)
    result = CliRunner().invoke(cli.main, [
        "--config", str(config_path), "assistant", "prompt", "diagnose", "this",
        "--repository-root", str(tmp_path), "--workspace-root", str(workspace),
        "--manifest", str(manifest), "--source", str(source), "--symbol", "Render::Tick",
        "--telemetry", str(telemetry), "--telemetry-pattern", "window checks",
        "--operation-mode", "planning", "--root", str(tmp_path / "assistant"),
    ])

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "grounded"
    args = captured["request"]["args"]
    for option in (
        "--workspace-root", "--manifest", "--gta-path", "--source", "--symbol",
        "--telemetry", "--telemetry-pattern",
    ):
        assert option in args
    assert args[args.index("--operation-mode") + 1] == "planning"
    assert captured["cwd"] == sdk_root


@pytest.mark.parametrize(
    ("payload", "stderr", "message"),
    [
        (None, "agent unavailable", "agent unavailable"),
        ({"ok": False, "error": "policy denied"}, "", "policy denied"),
        ({"ok": False, "result": {"output": "model refused"}}, "", "model refused"),
        ({"ok": False}, "", "assistant prompt failed"),
    ],
)
def test_assistant_prompt_fails_closed_on_agent_protocol_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    payload: object | None, stderr: str, message: str,
) -> None:
    _healthy_sdk(tmp_path, monkeypatch)
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _completed(payload, stderr=stderr))
    result = _invoke(CliRunner(), tmp_path, ["assistant", "prompt", "question"])
    assert result.exit_code == 1
    assert message in result.output


@pytest.mark.parametrize("failure", [OSError("cannot execute"), subprocess.TimeoutExpired("agent", 1)])
def test_assistant_prompt_translates_subprocess_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception,
) -> None:
    _healthy_sdk(tmp_path, monkeypatch)
    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(failure),
    )
    result = _invoke(CliRunner(), tmp_path, ["assistant", "prompt", "question"])
    assert result.exit_code == 1
    assert "Could not contact the SDK assistant" in result.output


def test_assistant_prompt_rejects_malformed_agent_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _healthy_sdk(tmp_path, monkeypatch)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *_a, **_k: SimpleNamespace(stdout="not-json\n", stderr="", returncode=0),
    )
    result = _invoke(CliRunner(), tmp_path, ["assistant", "prompt", "question"])
    assert result.exit_code == 1
    assert "Could not contact the SDK assistant" in result.output


def test_settings_propose_rejects_host_request_and_missing_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(tmp_path / "game")
    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)
    monkeypatch.setattr(
        settings_assistant, "build_settings_request",
        lambda *_a: (_ for _ in ()).throw(ValueError("catalog invalid")),
    )
    failed_catalog = _invoke(
        CliRunner(), tmp_path, ["assistant", "settings-propose", "package", "make", "changes"],
    )
    assert failed_catalog.exit_code == 1
    assert "catalog invalid" in failed_catalog.output

    monkeypatch.setattr(settings_assistant, "build_settings_request", lambda *_a: {"request": 1})
    sdk_root = tmp_path / "unhealthy-sdk"
    sdk_root.mkdir()
    monkeypatch.setattr(
        sdk_manager, "read_sdk_status",
        lambda: SimpleNamespace(root=sdk_root, healthy=False),
    )
    missing = _invoke(
        CliRunner(), tmp_path, ["assistant", "settings-propose", "package", "make", "changes"],
    )
    assert missing.exit_code == 1
    assert "SDK Agent is not installed and healthy" in missing.output


@pytest.mark.parametrize(
    ("payload", "stderr", "message"),
    [
        (None, "no response", "no response"),
        ({"ok": False, "error": "proposal denied"}, "", "proposal denied"),
        ({"ok": True, "result": {"output": "not-json"}}, "", "invalid proposal"),
    ],
)
def test_settings_propose_fails_closed_on_agent_protocol_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    payload: object | None, stderr: str, message: str,
) -> None:
    game = _game(tmp_path / "game")
    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)
    monkeypatch.setattr(settings_assistant, "build_settings_request", lambda *_a: {"request": 1})
    _healthy_sdk(tmp_path, monkeypatch)
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _completed(payload, stderr=stderr))
    result = _invoke(
        CliRunner(), tmp_path, ["assistant", "settings-propose", "package", "make", "changes"],
    )
    assert result.exit_code == 1
    assert message in result.output


def test_settings_propose_translates_subprocess_failure_and_prints_validated_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = _game(tmp_path / "game")
    monkeypatch.setattr(cli, "_content_game_path", lambda _ctx, _path: game)
    monkeypatch.setattr(settings_assistant, "build_settings_request", lambda *_a: {"request": 1})
    _healthy_sdk(tmp_path, monkeypatch)
    monkeypatch.setattr(
        subprocess, "run",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("agent launch failed")),
    )
    failed = _invoke(
        CliRunner(), tmp_path, ["assistant", "settings-propose", "package", "change"],
    )
    assert failed.exit_code == 1
    assert "Could not contact the SDK assistant" in failed.output

    monkeypatch.setattr(
        subprocess, "run",
        lambda *_a, **_k: _completed({"ok": True, "result": {"output": "{}"}}),
    )
    monkeypatch.setattr(
        settings_assistant,
        "validate_settings_proposal",
        lambda *_a: SimpleNamespace(to_dict=lambda: {"proposal_id": "validated"}),
    )
    printed = _invoke(
        CliRunner(), tmp_path, ["assistant", "settings-propose", "package", "change"],
    )
    assert printed.exit_code == 0, printed.output
    assert json.loads(printed.output)["proposal_id"] == "validated"


def test_assistant_configure_covers_disabled_mode_and_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "assistant"
    configured = _invoke(
        CliRunner(), tmp_path,
        ["assistant", "configure", "--root", str(root), "--mode", "disabled", "--yes"],
    )
    assert configured.exit_code == 0, configured.output
    saved = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert saved["capabilities"] == []
    assert saved["thinking"] == "provider_default"

    monkeypatch.setattr(
        assistant_manager, "load_assistant_config",
        lambda *_a: (_ for _ in ()).throw(ValueError("configuration corrupt")),
    )
    failed = _invoke(
        CliRunner(), tmp_path, ["assistant", "configure", "--root", str(root), "--yes"],
    )
    assert failed.exit_code == 1
    assert "configuration corrupt" in failed.output


def test_assistant_package_install_authorization_and_failure_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "assistant.zip"
    archive.write_bytes(b"fixture")
    runner = CliRunner()
    denied = _invoke(runner, tmp_path, ["assistant", "install-package", str(archive)])
    assert denied.exit_code == 1
    assert "requires --yes" in denied.output

    monkeypatch.setattr(
        assistant_manager, "inspect_assistant_archive",
        lambda *_a: (_ for _ in ()).throw(ValueError("bad checksum")),
    )
    invalid = _invoke(
        runner, tmp_path, ["assistant", "install-package", str(archive), "--yes"],
    )
    assert invalid.exit_code == 1
    assert "bad checksum" in invalid.output

    package = SimpleNamespace(profile="low", unpacked_size=100)
    monkeypatch.setattr(assistant_manager, "inspect_assistant_archive", lambda *_a: package)
    monkeypatch.setattr(
        assistant_manager, "assess_assistant_hardware",
        lambda *_a, **_k: SimpleNamespace(summary="Hardware check passed."),
    )
    monkeypatch.setattr(
        assistant_manager, "install_assistant_archive",
        lambda *_a: SimpleNamespace(package=None),
    )
    incomplete = _invoke(
        runner, tmp_path, ["assistant", "install-package", str(archive), "--yes"],
    )
    assert incomplete.exit_code == 1
    assert "did not produce a valid package" in incomplete.output


def test_qwen_install_verify_and_uninstall_failure_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = SimpleNamespace(
        profile="low", total_download_bytes=10,
        model=SimpleNamespace(size=6), runtime=SimpleNamespace(size=4),
    )
    monkeypatch.setattr(assistant_manager, "assistant_source", lambda *_a: selected)
    monkeypatch.setattr(
        assistant_manager, "assess_assistant_hardware",
        lambda *_a, **_k: SimpleNamespace(summary="Hardware check passed."),
    )

    def incomplete_install(*_args, progress, **_kwargs):
        progress("download", 1, 100)
        progress("download", 2, 100)
        return SimpleNamespace(package=None)

    monkeypatch.setattr(assistant_manager, "install_qwen_source", incomplete_install)
    incomplete = _invoke(
        CliRunner(), tmp_path, ["assistant", "install-qwen", "--profile", "low", "--yes"],
    )
    assert incomplete.exit_code == 1
    assert "did not produce a valid package" in incomplete.output
    assert incomplete.output.count("download:") == 1

    monkeypatch.setattr(
        assistant_manager, "install_qwen_source",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("download failed")),
    )
    failed_download = _invoke(
        CliRunner(), tmp_path, ["assistant", "install-qwen", "--profile", "low", "--yes"],
    )
    assert failed_download.exit_code == 1
    assert "download failed" in failed_download.output

    monkeypatch.setattr(
        assistant_manager, "verify_assistant_install",
        lambda *_a: (_ for _ in ()).throw(ValueError("checksum mismatch")),
    )
    verify = _invoke(CliRunner(), tmp_path, ["assistant", "verify"])
    assert verify.exit_code == 1
    assert "checksum mismatch" in verify.output

    denied = _invoke(CliRunner(), tmp_path, ["assistant", "uninstall"])
    assert denied.exit_code == 1
    assert "requires --yes" in denied.output
    monkeypatch.setattr(
        assistant_manager, "uninstall_assistant",
        lambda *_a: (_ for _ in ()).throw(OSError("remove failed")),
    )
    failed_remove = _invoke(CliRunner(), tmp_path, ["assistant", "uninstall", "--yes"])
    assert failed_remove.exit_code == 1
    assert "remove failed" in failed_remove.output
    monkeypatch.setattr(assistant_manager, "uninstall_assistant", lambda *_a: False)
    absent = _invoke(CliRunner(), tmp_path, ["assistant", "uninstall", "--yes"])
    assert absent.exit_code == 0
    assert "No managed assistant is installed" in absent.output
