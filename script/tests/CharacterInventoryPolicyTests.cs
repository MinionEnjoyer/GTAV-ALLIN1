using ALLIN1;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class CharacterInventoryPolicyTests
    {
        [Fact]
        public void Unequipping_gear_removes_ownership_and_equipped_state()
        {
            var inventory = new CharacterInventory.Inventory();
            inventory.gear.Add("ARMOR_HEAVY");
            inventory.gear.Add("GADGET_PARACHUTE");
            inventory.equipped_gear.Add("ARMOR_HEAVY");
            inventory.equipped_gear.Add("GADGET_PARACHUTE");

            Assert.True(CharacterInventory.RemoveOwnedGearInMemory(
                inventory, "armor_heavy"));
            Assert.DoesNotContain("ARMOR_HEAVY", inventory.gear);
            Assert.DoesNotContain("ARMOR_HEAVY", inventory.equipped_gear);
            Assert.Contains("GADGET_PARACHUTE", inventory.gear);
            Assert.Contains("GADGET_PARACHUTE", inventory.equipped_gear);
        }

        [Fact]
        public void Equipping_new_armor_consumes_displaced_armor()
        {
            var inventory = new CharacterInventory.Inventory();
            inventory.gear.Add("ARMOR_SUPER_HEAVY");
            inventory.gear.Add("ARMOR_HEAVY");
            inventory.equipped_gear.Add("ARMOR_SUPER_HEAVY");

            CharacterInventory.SetEquippedInMemory(
                inventory, "ARMOR_HEAVY", true);

            Assert.DoesNotContain("ARMOR_SUPER_HEAVY", inventory.gear);
            Assert.DoesNotContain("ARMOR_SUPER_HEAVY", inventory.equipped_gear);
            Assert.Contains("ARMOR_HEAVY", inventory.gear);
            Assert.Contains("ARMOR_HEAVY", inventory.equipped_gear);
        }

        [Fact]
        public void Purchasing_gear_records_ownership_before_equipped_normalization()
        {
            var inventory = new CharacterInventory.Inventory();

            Assert.True(CharacterInventory.RecordOwnedGearInMemory(
                inventory, "ARMOR_SUPER_HEAVY"));
            Assert.Contains("ARMOR_SUPER_HEAVY", inventory.gear);
            Assert.Contains("ARMOR_SUPER_HEAVY", inventory.equipped_gear);

            Assert.False(CharacterInventory.RecordOwnedGearInMemory(
                inventory, "armor_super_heavy"));
            Assert.Single(inventory.gear);
            Assert.Single(inventory.equipped_gear);
        }

        [Fact]
        public void World_asset_catalog_keeps_yacht_out_of_vehicle_delivery()
        {
            Assert.True(WorldAssetList.IsWorldAsset(WorldAssetList.SuperYacht));
            Assert.Equal("Galaxy Super Yacht",
                WorldAssetList.DisplayName(WorldAssetList.SuperYacht));
            Assert.Equal(8000000, WorldAssetList.Price(WorldAssetList.SuperYacht));
            Assert.Equal("allin1_asset_01",
                WorldAssetList.PreviewDict[WorldAssetList.SuperYacht]);
            Assert.False(WorldAssetList.IsWorldAsset("caracara3"));
        }
    }
}
