using ALLIN1;
using System.Linq;
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

        [Fact]
        public void Smoke_colours_have_independent_purchasable_stock()
        {
            var inventory = new CharacterInventory.Inventory();

            Assert.Equal(5, CharacterInventory.AddSmokeInMemory(
                inventory, "red", 5));
            Assert.Equal(3, CharacterInventory.AddSmokeInMemory(
                inventory, "blue", 3));

            Assert.Equal(5, inventory.smoke_grenades["red"]);
            Assert.Equal(3, inventory.smoke_grenades["blue"]);
            Assert.Equal(8, CharacterInventory.SmokeTotalInMemory(inventory));
            Assert.Equal("blue", inventory.active_smoke_color);
        }

        [Fact]
        public void Failed_smoke_grant_can_roll_back_only_the_new_bundle()
        {
            var inventory = new CharacterInventory.Inventory();
            CharacterInventory.AddSmokeInMemory(inventory, "white", 5);
            CharacterInventory.AddSmokeInMemory(inventory, "red", 5);

            Assert.Equal(5, CharacterInventory.RemoveSmokeInMemory(
                inventory, "white", 5));

            Assert.False(inventory.smoke_grenades.ContainsKey("white"));
            Assert.Equal(5, inventory.smoke_grenades["red"]);
            Assert.Equal(5, CharacterInventory.SmokeTotalInMemory(inventory));
        }

        [Fact]
        public void Smoke_stock_is_capped_at_five_per_colour()
        {
            var inventory = new CharacterInventory.Inventory();

            Assert.Equal(5, CharacterInventory.AddSmokeInMemory(
                inventory, "purple", 99));
            Assert.Equal(0, CharacterInventory.AddSmokeInMemory(
                inventory, "purple", 1));
            Assert.Equal(SmokeGrenadeCatalog.MaximumPerColor,
                inventory.smoke_grenades["purple"]);
        }

        [Fact]
        public void Invalid_managed_weapons_are_removed_with_dependent_state()
        {
            var inventory = new CharacterInventory.Inventory();
            inventory.weapons.AddRange(new[]
            {
                "WEAPON_PISTOL", "WEAPON_BROKEN_ADDON"
            });
            inventory.weapon_ammo["WEAPON_PISTOL"] = 42;
            inventory.weapon_ammo["WEAPON_BROKEN_ADDON"] = 99;
            inventory.weapon_customizations["WEAPON_BROKEN_ADDON"] =
                new CharacterInventory.WeaponCustomization();

            var removed = CharacterInventory.RemoveInvalidWeaponsInMemory(
                inventory, weapon => weapon == "WEAPON_PISTOL");

            Assert.Equal(new[] { "WEAPON_BROKEN_ADDON" }, removed);
            Assert.Equal(new[] { "WEAPON_PISTOL" }, inventory.weapons);
            Assert.Equal(42, inventory.weapon_ammo["WEAPON_PISTOL"]);
            Assert.False(inventory.weapon_ammo.ContainsKey(
                "WEAPON_BROKEN_ADDON"));
            Assert.False(inventory.weapon_customizations.ContainsKey(
                "WEAPON_BROKEN_ADDON"));
        }

        [Fact]
        public void Smoke_cycle_skips_colours_without_stock()
        {
            var inventory = new CharacterInventory.Inventory();
            CharacterInventory.AddSmokeInMemory(inventory, "red", 2);
            CharacterInventory.AddSmokeInMemory(inventory, "purple", 1);

            Assert.Equal("red",
                CharacterInventory.CycleSmokeColorInMemory(inventory));
            Assert.Equal("purple",
                CharacterInventory.CycleSmokeColorInMemory(inventory));
        }

        [Fact]
        public void Throwing_smoke_consumes_selected_colour_and_advances()
        {
            var inventory = new CharacterInventory.Inventory();
            CharacterInventory.AddSmokeInMemory(inventory, "orange", 1);
            CharacterInventory.AddSmokeInMemory(inventory, "green", 2);
            inventory.active_smoke_color = "orange";

            Assert.True(CharacterInventory.TryConsumeSmokeInMemory(
                inventory, out string consumed));

            Assert.Equal("orange", consumed);
            Assert.False(inventory.smoke_grenades.ContainsKey("orange"));
            Assert.Equal("green", inventory.active_smoke_color);
            Assert.Equal(2, CharacterInventory.SmokeTotalInMemory(inventory));
        }

        [Fact]
        public void Independent_smoke_weapon_consumes_only_its_own_ammo_pool()
        {
            var inventory = new CharacterInventory.Inventory();
            CharacterInventory.AddSmokeInMemory(inventory, "red", 3);
            CharacterInventory.AddSmokeInMemory(inventory, "blue", 4);

            Assert.True(CharacterInventory.TryConsumeSmokeColorInMemory(
                inventory, "red", out string color, out int remaining));

            Assert.Equal("red", color);
            Assert.Equal(2, remaining);
            Assert.Equal(2, inventory.smoke_grenades["red"]);
            Assert.Equal(4, inventory.smoke_grenades["blue"]);
        }

        [Fact]
        public void Smoke_catalog_exposes_all_seven_gbay_colours()
        {
            Assert.Equal(7, SmokeGrenadeCatalog.Products.Length);
            Assert.Equal(5, SmokeGrenadeCatalog.MaximumPerColor);
            Assert.Equal("WEAPON_SMOKEGRENADE",
                SmokeGrenadeCatalog.NativeWeaponName);
            Assert.True(SmokeGrenadeCatalog.IsProduct(
                "ALLIN1_SMOKE_WHITE"));
            Assert.True(SmokeGrenadeCatalog.IsProduct(
                "allin1_smoke_purple"));
            Assert.False(SmokeGrenadeCatalog.IsProduct("WEAPON_BZGAS"));
            Assert.Equal(7, SmokeGrenadeCatalog.Products.Select(
                product => product.WeaponName).Distinct().Count());
            Assert.Equal(7, SmokeGrenadeCatalog.Products.Select(
                product => product.AmmoName).Distinct().Count());
            Assert.All(SmokeGrenadeCatalog.Products, product =>
                Assert.StartsWith("WEAPON_ALLIN1_SMOKE_",
                    product.WeaponName));
        }
    }
}
