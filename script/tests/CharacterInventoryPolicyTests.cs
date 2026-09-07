using ALLIN1;
using System.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class CharacterInventoryPolicyTests
    {
        [Fact]
        public void Unequipped_attachment_survives_serialization_and_reequips_without_losing_ownership()
        {
            var state = new CharacterInventory.WeaponCustomization();
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 123, 10, true);
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 456, 20, true);
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 123, 10, false);
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 123, 10, false);
            Assert.Contains(123, state.owned_components);
            Assert.Equal(new[] { 123 }, state.unequipped_components);
            Assert.False(state.active_components.ContainsKey("10"));
            Assert.Equal(456, state.active_components["20"]);
            state = Newtonsoft.Json.JsonConvert.DeserializeObject<CharacterInventory.WeaponCustomization>(
                Newtonsoft.Json.JsonConvert.SerializeObject(state));
            Assert.Contains(123, state.unequipped_components);
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 123, 10, true);
            Assert.Empty(state.unequipped_components);
            Assert.Equal(123, state.active_components["10"]);
            Assert.Equal(2, state.owned_components.Count);
        }

        [Fact]
        public void Removing_stale_component_does_not_clear_its_replacement()
        {
            var state = new CharacterInventory.WeaponCustomization();
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 123, 10, true);
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 456, 10, true);
            CharacterInventory.SetWeaponComponentEquippedInMemory(state, 123, 10, false);
            Assert.Equal(456, state.active_components["10"]);
            Assert.Contains(123, state.owned_components);
        }
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
        public void Death_consumes_all_gear_without_touching_other_purchases()
        {
            var inventory = new CharacterInventory.Inventory();
            inventory.gear.AddRange(GearList.All);
            inventory.equipped_gear.AddRange(GearList.All);
            inventory.weapons.Add("WEAPON_PISTOL");
            inventory.weapon_ammo["WEAPON_PISTOL"] = 42;
            inventory.weapon_customizations["WEAPON_PISTOL"] =
                new CharacterInventory.WeaponCustomization();
            inventory.properties.Add("ALLIN1_YACHT");
            inventory.smoke_grenades["green"] = 3;

            var removed = CharacterInventory.
                ConsumeAllGearAfterDeathInMemory(inventory);

            Assert.Equal(GearList.All, removed);
            Assert.Empty(inventory.gear);
            Assert.Empty(inventory.equipped_gear);
            Assert.Equal(new[] { "WEAPON_PISTOL" }, inventory.weapons);
            Assert.Equal(42, inventory.weapon_ammo["WEAPON_PISTOL"]);
            Assert.True(inventory.weapon_customizations.ContainsKey(
                "WEAPON_PISTOL"));
            Assert.Equal(new[] { "ALLIN1_YACHT" }, inventory.properties);
            Assert.Equal(3, inventory.smoke_grenades["green"]);
        }

        [Fact]
        public void Repeated_death_gear_consumption_is_idempotent()
        {
            var inventory = new CharacterInventory.Inventory();
            inventory.gear.Add("ARMOR_HEAVY");
            inventory.equipped_gear.Add("ARMOR_HEAVY");

            Assert.Single(CharacterInventory.
                ConsumeAllGearAfterDeathInMemory(inventory));
            Assert.Empty(CharacterInventory.
                ConsumeAllGearAfterDeathInMemory(inventory));
        }

        [Theory]
        [InlineData(true, 0, true)]
        [InlineData(true, 300000, true)]
        [InlineData(true, -1, false)]
        [InlineData(true, 300001, false)]
        [InlineData(false, 1000, false)]
        public void Only_a_recent_observed_death_preserves_staging_across_load(
            bool deathObserved, int timeSinceDeathMs, bool expected)
        {
            Assert.Equal(expected, CharacterInventory.
                ShouldPreserveDeathAcrossLoading(
                    deathObserved, timeSinceDeathMs));
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
        public void Unavailable_managed_weapons_keep_dependent_state()
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

            inventory.managed = true;
            var result = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                inventory.weapons, weapon => weapon == "WEAPON_PISTOL",
                (_, __) => true, _ => { });

            Assert.Equal(new[] { "WEAPON_PISTOL" }, result.Restored);
            Assert.Equal("weapon_not_ready", result.Deferred["WEAPON_BROKEN_ADDON"]);
            Assert.Contains("WEAPON_BROKEN_ADDON", inventory.weapons);
            Assert.Equal(42, inventory.weapon_ammo["WEAPON_PISTOL"]);
            Assert.Equal(99, inventory.weapon_ammo["WEAPON_BROKEN_ADDON"]);
            Assert.True(inventory.weapon_customizations.ContainsKey(
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
