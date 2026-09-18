"""Traffic population editor review/apply and isolated persistence."""
import copy
import json

import pytest

from allin1.desktop_service import population_backend
from allin1.launcher_api import LauncherAPI, contract
from tests.test_desktop_service import service  # synthetic game fixture only


MODULE, KIND = "vehicle_manager", "traffic"


def test_inspect_review_apply_roundtrip(service):
    api = LauncherAPI(service, allow_writes=True)
    before = service.tree_identity(service.game(service.config()))
    result = api.read("inspect", {"module": MODULE})
    assert result["read_only"] is True
    assert before == service.tree_identity(service.game(service.config()))
    state = result[KIND + "_population"]
    document = copy.deepcopy(state["document"])
    document["enabled"] = not document["enabled"]
    document["replacement_chance"] = 0.25
    review = api.review({"action": KIND + "_population_save", "document": document,
                         "expected_document_sha256": state["document_sha256"]})
    assert review[KIND + "_population"]["after"] == document
    assert before == service.tree_identity(service.game(service.config()))
    payload = {"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True}
    applied = api.apply(payload)
    assert applied["executed"] is True
    refreshed = api.read("inspect", {"module": MODULE})[KIND + "_population"]
    assert refreshed["document"] == document
    assert refreshed["document_sha256"] != state["document_sha256"]
    with pytest.raises(ValueError, match="expired or already used"):
        api.apply(payload)


def test_rejects_stale_review_and_post_review_mutation(service):
    state = service.inspect({"module": MODULE})[KIND + "_population"]
    fields = {"action": KIND + "_population_save", "document": state["document"],
              "expected_document_sha256": "0" * 64}
    with pytest.raises(ValueError, match="changed"):
        service.review(fields)
    fields["expected_document_sha256"] = state["document_sha256"]
    review = service.review(fields)
    document = copy.deepcopy(state["document"])
    document["replacement_chance"] = 0.5
    population_backend(KIND).save_population(service.game(service.config()), document, state["document_sha256"])
    with pytest.raises(ValueError, match="Files changed"):
        service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})


def test_closed_game_and_authority_are_required(service):
    state = service.inspect({"module": MODULE})[KIND + "_population"]
    fields = {"action": KIND + "_population_save", "document": state["document"],
              "expected_document_sha256": state["document_sha256"]}
    service.allow_game_writes = False
    with pytest.raises(ValueError, match="game-write authority"):
        service.review(fields)
    service.allow_game_writes = True
    review = service.review(fields)
    before = service.tree_identity(service.game(service.config()))
    def running():
        raise ValueError("Close GTA V before applying Launcher changes")
    service.require_closed = running
    with pytest.raises(ValueError, match="Close GTA"):
        service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert before == service.tree_identity(service.game(service.config()))


def test_agent_plan_roundtrip_and_transport_rejects_unknown_fields(service):
    api = LauncherAPI(service, allow_writes=True)
    state = api.read("inspect", {"module": MODULE})[KIND + "_population"]
    fields = {"action": KIND + "_population_save", "document": state["document"],
              "expected_document_sha256": state["document_sha256"]}
    with pytest.raises(ValueError, match="parameters"):
        api.review({**fields, "bypass_checks": True})
    plan = api.plan(fields)
    result = api.apply_plan(json.loads(json.dumps(plan)), plan["approval_sha256"], confirmed=True)
    assert result["executed"] is True
    assert any(action["name"] == fields["action"] for action in contract()["actions"])


def test_invalid_document_never_persists(service):
    state = service.inspect({"module": MODULE})[KIND + "_population"]
    before = service.tree_identity(service.game(service.config()))
    for bad in ({}, {**state["document"], "replacement_chance": float("nan")},
                {**state["document"], "enabled": 1}):
        with pytest.raises(ValueError):
            service.review({"action": KIND + "_population_save", "document": bad,
                            "expected_document_sha256": state["document_sha256"]})
    assert before == service.tree_identity(service.game(service.config()))
