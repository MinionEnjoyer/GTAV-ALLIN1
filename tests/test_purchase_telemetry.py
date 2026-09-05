"""Producer and diagnostic consumer agree without parsing display wording."""
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from allin1.reliability import analyze_client_log


@pytest.mark.parametrize("message,fields,expected", [
    ("weapon_purchase_completed", {"event_schema": 1, "weapon": "WEAPON_VECTOR", "unit_price": 10, "quantity": 2, "total_price": 20}, True),
    ("weapon_purchase_completed", {"event_schema": 2, "weapon": "WEAPON_VECTOR", "unit_price": 10, "quantity": 2, "total_price": 20}, False),
    ("weapon_purchase_completed", {"event_schema": 1, "weapon": "WEAPON_VECTOR", "unit_price": 10, "quantity": 0, "total_price": 20}, False),
    ("weapon_purchase_completed", {}, False),
    ("GiveWeapon: WEAPON_VECTOR, unit=$10, quantity=2, total=$20", {}, True),
    ("GiveWeapon: WEAPON_VECTOR, price=$20", {}, True),
    ("GiveWeapon: rejected unavailable weapon WEAPON_VECTOR, price=$20", {}, False),
    ("GiveWeapon: WEAPON_VECTOR, unit=$10, quantity=0, total=$0", {}, False),
])
def test_purchase_versions_and_failed_grants(tmp_path, message, fields, expected):
    stamp = datetime.now(timezone.utc)
    base = {"ts": stamp.isoformat(), "session": "fixture", "level": "INFO"}
    events = [{**base, "component": "Client", "message": "session_started"}, {**base, "component": "GBAY", "message": message, **fields}]
    path = tmp_path / "client.log"; path.write_text("\n".join(json.dumps(e) for e in events))
    assert next(c.passed for c in analyze_client_log(path, now=stamp).checks if c.name == "weapon_grant") is expected


def test_real_producer_emits_contract_after_verified_grant():
    source = (Path(__file__).resolve().parents[1] / "script/src/GbayShop.cs").read_text()
    success = source.index('ClientLog.Info("GBAY", "weapon_purchase_completed"')
    assert success > source.index('"weapon_purchase_empty_grant"')
    for field in ['"event_schema", 1', '"weapon", weaponName', '"unit_price", quote.UnitPrice', '"quantity", chargedQuantity', '"total_price", totalPrice']:
        assert field in source[success:success + 500]
