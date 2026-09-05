"""Independent drafts retain their original file/target identities across refresh."""
import copy
import json

import pytest

from allin1.desktop_service import serializable
from tests.test_desktop_service import apply, service


def test_saving_one_document_does_not_invalidate_the_other_original_identity(service):
    session = service.inspect({"module": "characters"})
    loadouts = copy.deepcopy(session["loadouts"])
    loadouts["michael"]["progress"]["money"] = 42
    apply(service, "characters_save", document=loadouts, expected_document_sha256=session["document_sha256"]["loadouts"])
    garages = copy.deepcopy(session["garages"])
    garages["michael"] = [{"slot": 0, "model": session["models"][0]}]
    apply(service, "garages_save", document=garages, expected_document_sha256=session["document_sha256"]["garages"])
    assert service.inspect({"module": "characters"})["garages"] == garages


def test_refresh_cannot_rebase_an_existing_garage_draft_onto_external_changes(service):
    original = service.inspect({"module": "characters"})
    target = service.game(service.config()) / "scripts/ALLIN1_garage.json"
    target.parent.mkdir()
    external = {"michael": [{"slot": 0, "model": original["models"][0]}]}
    target.write_text(json.dumps(external))
    refreshed = service.inspect({"module": "characters"})
    assert refreshed["document_sha256"]["garages"] != original["document_sha256"]["garages"]
    with pytest.raises(ValueError, match="changed"):
        service.review({"action": "garages_save", "document": original["garages"],
                        "expected_document_sha256": original["document_sha256"]["garages"]})
    assert json.loads(target.read_text()) == external


def test_document_identity_includes_selected_game_root(service, tmp_path):
    session = service.inspect({"module": "characters"})
    other = tmp_path / "Another disposable game"; other.mkdir()
    (other / "GTA5_Enhanced.exe").write_bytes(b"not executable")
    config = serializable(service.config()); config["general"]["gta_enhanced_path"] = str(other)
    with pytest.raises(ValueError, match="changed"):
        service.review({"action": "characters_save", "config": config, "document": session["loadouts"],
                        "expected_document_sha256": session["document_sha256"]["loadouts"]})
    assert list(other.iterdir()) == [other / "GTA5_Enhanced.exe"]


def test_inspection_refuses_a_document_changed_while_loading(service, monkeypatch):
    from allin1.customization import LoadoutStore
    original = LoadoutStore.load
    def mutate(store):
        value = original(store)
        path = service.game(service.config()) / "scripts/ALLIN1_characters.json"
        path.parent.mkdir(exist_ok=True); path.write_text('{"external": true}')
        return value
    monkeypatch.setattr(LoadoutStore, "load", mutate)
    with pytest.raises(ValueError, match="during inspection"):
        service.inspect({"module": "characters"})
