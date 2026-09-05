"""Assistant UI boundary tests with synthetic packs and in-memory downloads."""
from dataclasses import replace

import pytest

from allin1 import assistant_manager as manager
from allin1.desktop_service import serializable
from tests.test_desktop_service import apply, service
from tests.test_assistant_manager import _write_package, _hardware, _source_fixture, _Response


@pytest.fixture
def hardware(monkeypatch):
    report = manager.AssistantHardwareReport("low", True, "low", 8, 12, 1, (), (), _hardware())
    monkeypatch.setattr(manager, "assess_assistant_hardware", lambda *a, **k: report)
    return report


def test_passive_status_and_hardware_do_not_write_or_connect(service, tmp_path, hardware, monkeypatch):
    monkeypatch.setattr(manager, "urlopen", lambda *a, **k: pytest.fail("Passive status connected to a provider"))
    before = service.tree_identity(tmp_path)
    result = service.inspect({"module": "sdk"})["assistant"]
    assert result["status"]["config"]["mode"] == "disabled"
    assert len(result["sources"]) == 2
    assert service.inspect({"module": "assistant_hardware", "profile": "low"})["hardware"]["compatible"]
    assert service.tree_identity(tmp_path) == before


def test_assistant_pack_configuration_and_removal_without_sdk_or_game_authority(service, tmp_path, hardware):
    service.allow_game_writes = False
    archive = _write_package(tmp_path / "assistant with spaces.zip")
    before = service.tree_identity(service.game(service.config()))
    apply(service, "assistant_install_archive", source=str(archive))
    assert manager.verify_assistant_install(service.assistant_root).package_id == "allin1.test-model"
    assert not manager.read_assistant_status(service.assistant_root).enabled
    config = serializable(manager.AssistantConfig(mode="managed_local", profile="low"))
    apply(service, "assistant_save", assistant_config=config)
    assert manager.read_assistant_status(service.assistant_root).enabled
    custom = service.assistant_root / "user-notes.txt"; custom.write_bytes(b"preserve")
    apply(service, "assistant_uninstall")
    status = manager.read_assistant_status(service.assistant_root)
    assert not status.installed and not status.enabled
    assert custom.read_bytes() == b"preserve"
    assert service.tree_identity(service.game(service.config())) == before
    assert not service.sdk_root.exists()


@pytest.mark.parametrize("field,value", [("schema", True), ("context_tokens", "8192"), ("temperature", True),
                                         ("model_name", "bad\nname"), ("capabilities", "bad"), ("mode", "unknown")])
def test_invalid_configuration_rejected_before_review(service, field, value):
    config = serializable(manager.AssistantConfig()); config[field] = value
    with pytest.raises(ValueError): service.review({"action": "assistant_save", "assistant_config": config})
    assert not service.reviews and not service.assistant_root.exists()


def test_stale_assistant_configuration_preserves_external_changes(service):
    config = serializable(manager.AssistantConfig())
    review = service.review({"action": "assistant_save", "assistant_config": config})
    manager.save_assistant_config(manager.AssistantConfig(context_tokens=4096), service.assistant_root)
    with pytest.raises(ValueError, match="changed"):
        service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert manager.load_assistant_config(service.assistant_root).context_tokens == 4096


def test_blocked_hardware_cannot_issue_install_review(service, tmp_path, hardware, monkeypatch):
    monkeypatch.setattr(manager, "assess_assistant_hardware", lambda *a, **k: replace(hardware, compatible=False, blockers=("insufficient memory",)))
    archive = _write_package(tmp_path / "assistant.zip")
    for action, fields in [("assistant_install_qwen", {"profile": "low"}), ("assistant_install_archive", {"source": str(archive)})]:
        with pytest.raises(ValueError, match="insufficient memory"):
            service.review({"action": action, **fields})
    assert not service.reviews and not service.assistant_root.exists()


def test_reviewed_qwen_download_uses_pinned_source_and_real_lifecycle(service, hardware, monkeypatch):
    source, payloads = _source_fixture()
    monkeypatch.setattr(manager, "ASSISTANT_SOURCES", (source,))
    original = manager.install_qwen_source
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        return _Response(payloads[request.full_url])
    monkeypatch.setattr(manager, "install_qwen_source", lambda *args, **kwargs: original(*args, **kwargs, opener=opener))
    review = service.review({"action": "assistant_install_qwen", "profile": "low", "url": "https://untrusted.invalid"})
    assert review["assistant_download"]["model"]["sha256"] == source.model.sha256
    assert calls == [] and not service.assistant_root.exists()
    service.apply({"confirmed": True, "review_id": review["review_id"], "review_sha256": review["review_sha256"]})
    assert calls == [source.runtime.url, source.runtime_license.url, source.model_license.url, source.model.url]
    assert manager.verify_assistant_install(service.assistant_root).package_id == source.package_id
    assert not manager.read_assistant_status(service.assistant_root).enabled


def test_source_catalog_change_invalidates_qwen_review(service, hardware, monkeypatch):
    source, _ = _source_fixture()
    monkeypatch.setattr(manager, "ASSISTANT_SOURCES", (source,))
    review = service.review({"action": "assistant_install_qwen", "profile": "low"})
    monkeypatch.setattr(manager, "ASSISTANT_SOURCES", (replace(source, version="9.0.0"),))
    with pytest.raises(ValueError, match="changed"):
        service.apply({"confirmed": True, "review_id": review["review_id"], "review_sha256": review["review_sha256"]})
    assert not service.assistant_root.exists()
