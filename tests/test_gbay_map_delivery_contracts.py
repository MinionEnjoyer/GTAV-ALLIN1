"""Repository contracts for on-demand official map-backed GBAY delivery."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_both_gbay_frontends_use_the_shared_official_destination_guard():
    reactor = (ROOT / "script/src/GbayReactorContracts.cs").read_text()
    legacy = (ROOT / "script/src/GbayBrowser.cs").read_text()

    assert "OfficialMapContentPolicy.IsDeliveryDestinationAvailable(" in reactor
    assert "StandaloneMapPack" not in reactor
    assert "DeliveryDestinationAvailable(_deliveryGarageIndex)" in legacy
    assert "OfficialMapContentPolicy.IsDeliveryDestinationAvailable" in legacy
    assert "StandaloneMapPack" not in legacy


def test_delivery_authority_rechecks_all_map_backed_destinations():
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    expected_guards = {
        'RejectUnavailableMapDestination(1, "Harmony Garage")',
        'RejectUnavailableMapDestination(2, "Davis Auto Shop")',
        'RejectUnavailableMapDestination(3, "Garment Factory")',
        'RejectUnavailableMapDestination(4, "Grapeseed Garage")',
        'RejectUnavailableMapDestination(5, "Paleto Bay Garage")',
        'RejectUnavailableMapDestination(7, "Yacht Helipad")',
    }
    for guard in expected_guards:
        assert guard in shop


def test_map_backed_destinations_require_the_verified_story_bridge():
    policy = (ROOT / "script/src/OfficialMapContentPolicy.cs").read_text()
    map_pack = (ROOT / "script/src/StandaloneMapPack.cs").read_text()

    assert "index >= 0 && index <= 7" in policy
    assert "metadata-only garage map bridge" in policy
    assert "StandaloneMapPack.IsDeliveryDestinationAvailable(" in policy
    assert "IsMapBackedDeliveryDestination" in map_pack
    assert "(index >= 1 && index <= 5) || index == 7" in map_pack
    assert "!IsMapBackedDeliveryDestination(index) ||" in map_pack
    assert "(mapPackInstalled &&" in map_pack
    assert "index != 2 || DavisStockReferenceBridgePolicy" in map_pack
