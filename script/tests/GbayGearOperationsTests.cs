using System;
using System.Linq;
using System.Reflection;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GbayGearOperationsTests
    {
        [Fact]
        public void Every_catalog_gear_item_has_the_data_required_by_validated_operations()
        {
            Assert.Equal(11, GearList.All.Length);
            Assert.Equal(GearList.All.Length,
                GearList.All.Distinct(StringComparer.OrdinalIgnoreCase).Count());
            Assert.All(GearList.All, gear =>
            {
                Assert.True(GearList.Prices.ContainsKey(gear), gear);
                Assert.True(GearList.DisplayNames.ContainsKey(gear), gear);
                Assert.True(GearList.CategoryNames.ContainsKey(gear), gear);
            });
        }

        [Fact]
        public void Gear_runtime_entry_points_are_present_for_purchase_equip_remove_and_restore()
        {
            Type shop = typeof(GbayShop);
            BindingFlags flags = BindingFlags.Instance | BindingFlags.Static |
                BindingFlags.NonPublic;
            Assert.NotNull(shop.GetMethod("GiveGearValidated", flags));
            Assert.NotNull(shop.GetMethod("EquipGearValidated", flags));
            Assert.NotNull(shop.GetMethod("UnequipGearValidated", flags));
            Assert.NotNull(shop.GetMethod("RestoreGearValidated", flags));
            Assert.NotNull(shop.GetMethod("IsGearPlayerReady", flags));
        }

        [Fact]
        public void Transaction_runner_rolls_back_only_after_native_apply_when_persistence_fails()
        {
            var calls = new System.Collections.Generic.List<string>();
            bool completed = GearOperationTransaction.Run(
                () => { calls.Add("apply"); return true; },
                () => { calls.Add("persist"); return false; },
                () => calls.Add("rollback"));

            Assert.False(completed);
            Assert.Equal(new[] { "apply", "persist", "rollback" }, calls);
        }

        [Fact]
        public void Transaction_runner_contains_throwing_and_failed_paths()
        {
            var calls = new System.Collections.Generic.List<string>();
            Assert.False(GearOperationTransaction.Run(
                () => { calls.Add("apply"); throw new InvalidOperationException(); },
                () => { calls.Add("persist"); return true; },
                () => calls.Add("rollback")));
            Assert.Equal(new[] { "apply", "rollback" }, calls);

            calls.Clear();
            Assert.False(GearOperationTransaction.Run(
                () => { calls.Add("apply"); return false; },
                () => { calls.Add("persist"); return true; },
                () => calls.Add("rollback")));
            Assert.Equal(new[] { "apply", "rollback" }, calls);

            calls.Clear();
            Assert.True(GearOperationTransaction.Run(
                () => { calls.Add("apply"); return true; },
                () => { calls.Add("persist"); return true; },
                () => calls.Add("rollback")));
            Assert.Equal(new[] { "apply", "persist" }, calls);

            Assert.False(GearOperationTransaction.Run(
                () => true, () => false,
                () => throw new InvalidOperationException()));
        }

        [Fact]
        public void Purchase_equip_and_remove_paths_call_the_shared_transaction_runner()
        {
            MethodInfo runner = typeof(GearOperationTransaction).GetMethod("Run",
                BindingFlags.Static | BindingFlags.NonPublic);
            byte[] token = BitConverter.GetBytes(runner.MetadataToken);
            foreach (string name in new[] { "GiveGearValidated",
                "EquipGearValidated", "UnequipGearValidated" })
            {
                byte[] il = typeof(GbayShop).GetMethod(name,
                    BindingFlags.Instance | BindingFlags.NonPublic)
                    .GetMethodBody().GetILAsByteArray();
                Assert.True(Contains(il, token), name + " must call Run.");
            }
        }

        private static bool Contains(byte[] source, byte[] value)
        {
            for (int index = 0; source != null && index <= source.Length - value.Length;
                index++)
            {
                bool match = true;
                for (int offset = 0; offset < value.Length; offset++)
                    if (source[index + offset] != value[offset]) { match = false; break; }
                if (match) return true;
            }
            return false;
        }
    }
}
