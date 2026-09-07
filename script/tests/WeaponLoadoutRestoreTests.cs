using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class WeaponLoadoutRestoreTests
    {
        private const string G3 = "WEAPON_A1_EQ_G3A3";
        private const string Qbz = "WEAPON_A1_EQ_QBZ97";

        private static CharacterInventory.Inventory Saved(params string[] weapons)
        {
            var inventory = new CharacterInventory.Inventory();
            inventory.weapons.AddRange(weapons);
            foreach (string weapon in weapons) inventory.weapon_ammo[weapon] = 42;
            return inventory;
        }

        [Fact]
        public void Save_roundtrip_restores_stock_and_custom_weapons_ammo_and_upgrades()
        {
            var inventory = Saved("WEAPON_PISTOL", G3, Qbz);
            inventory.weapon_customizations[G3] = new CharacterInventory.WeaponCustomization();
            inventory.weapon_customizations[G3].active_components["scope"] = 123;
            inventory = JsonConvert.DeserializeObject<CharacterInventory.Inventory>(
                JsonConvert.SerializeObject(inventory));
            var grants = new Dictionary<string, int>();
            var customized = new List<string>();
            var result = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                inventory.weapons, _ => true,
                (weapon, ammo) => { grants[weapon] = ammo; return true; },
                weapon => {
                    customized.Add(weapon);
                    if (weapon == G3) Assert.Equal(123, inventory.weapon_customizations[weapon].active_components["scope"]);
                });
            Assert.Equal(inventory.weapons, result.Restored);
            Assert.Empty(result.Deferred);
            Assert.Equal(inventory.weapons, customized);
            Assert.All(grants.Values, ammo => Assert.Equal(42, ammo));
            Assert.False(inventory.managed); // GBAY purchases do not require managed mode.
        }

        [Fact]
        public void Unavailable_pack_preserves_purchase_ammo_and_customization()
        {
            var inventory = Saved(G3);
            inventory.weapon_customizations[G3] = new CharacterInventory.WeaponCustomization();
            string before = JsonConvert.SerializeObject(inventory);
            var result = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                WeaponList.All, _ => throw new Exception("Must not call GTA for disabled add-ons"),
                (_, __) => false, _ => Assert.True(false));
            Assert.Empty(result.Restored);
            Assert.Equal("catalog_unavailable", result.Deferred[G3]);
            Assert.Equal(before, JsonConvert.SerializeObject(inventory));
        }

        [Fact]
        public void Deferred_retry_does_not_regrant_successes_or_reset_their_ammo()
        {
            var inventory = Saved(G3, Qbz);
            var ammo = new Dictionary<string, int>();
            bool ready = false;
            Func<string, int, bool> grant = (weapon, count) => { ammo[weapon] = count; return true; };
            var first = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                inventory.weapons, weapon => weapon == G3 || ready, grant, _ => { });
            Assert.Equal(new[] { G3 }, first.Restored);
            Assert.Equal("weapon_not_ready", first.Deferred[Qbz]);
            ammo[G3] = 30; // Player fired after G3 was restored.
            ready = true;
            var second = WeaponLoadoutRestore.Restore(inventory, first.Deferred.Keys,
                inventory.weapons, _ => ready, grant, _ => { });
            Assert.Equal(new[] { Qbz }, second.Restored);
            Assert.Equal(30, ammo[G3]);
            Assert.Equal(42, ammo[Qbz]);
            Assert.Empty(second.Deferred);
        }

        [Fact]
        public void Reenabled_pack_can_restore_the_original_purchase()
        {
            var inventory = Saved(G3);
            var first = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                WeaponList.All, _ => true, (_, __) => true, _ => { });
            var second = WeaponLoadoutRestore.Restore(inventory, first.Deferred.Keys,
                new[] { G3 }, _ => true, (_, ammo) => ammo == 42, _ => { });
            Assert.Equal(new[] { G3 }, second.Restored);
        }

        [Fact]
        public void Failed_native_grant_is_not_reported_restored_or_customized()
        {
            var inventory = Saved(G3);
            var result = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                inventory.weapons, _ => true, (_, __) => false, _ => Assert.True(false));
            Assert.Empty(result.Restored);
            Assert.Equal("grant_not_confirmed", result.Deferred[G3]);
            Assert.Contains(G3, inventory.weapons);
        }

        [Fact]
        public void One_failing_weapon_does_not_block_the_rest()
        {
            var inventory = Saved(G3, Qbz);
            var result = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                inventory.weapons, _ => true,
                (weapon, _) => weapon == G3 ? throw new InvalidOperationException() : true,
                _ => { });
            Assert.Equal(new[] { Qbz }, result.Restored);
            Assert.Equal("restore_failed:InvalidOperationException", result.Deferred[G3]);
        }

        [Theory]
        [InlineData(0, 0)]
        [InlineData(-5, 0)]
        [InlineData(75, 75)]
        public void Restore_uses_saved_ammo_including_empty_weapons(int saved, int expected)
        {
            var inventory = Saved(G3);
            inventory.weapon_ammo[G3] = saved;
            var result = WeaponLoadoutRestore.Restore(inventory, inventory.weapons,
                inventory.weapons, _ => true,
                (_, ammo) => { Assert.Equal(expected, ammo); return true; }, _ => { });
            Assert.Single(result.Restored);
        }

        [Fact]
        public void Character_switch_never_grants_another_characters_saved_or_deferred_weapon()
        {
            var trevor = Saved(G3);
            var michael = Saved(Qbz);
            var all = new[] { G3, Qbz };
            var grants = new List<string>();
            Func<string, int, bool> grant = (weapon, _) => { grants.Add(weapon); return true; };
            var pending = WeaponLoadoutRestore.Restore(trevor, trevor.weapons, all,
                _ => false, grant, _ => { });
            WeaponLoadoutRestore.Restore(michael, pending.Deferred.Keys, all, _ => true, grant, _ => { });
            Assert.Empty(grants);
            WeaponLoadoutRestore.Restore(michael, michael.weapons, all, _ => true, grant, _ => { });
            Assert.Equal(new[] { Qbz }, grants);
        }

        [Fact]
        public void Catalog_entries_alone_do_not_grant_unpurchased_weapons_and_duplicates_grant_once()
        {
            var inventory = Saved(G3, G3.ToLowerInvariant());
            int grants = 0;
            var result = WeaponLoadoutRestore.Restore(inventory, new[] { G3, G3, Qbz },
                new[] { G3, Qbz }, _ => true, (_, __) => { grants++; return true; }, _ => { });
            Assert.Equal(1, grants);
            Assert.Single(result.Restored);
        }
    }
}
