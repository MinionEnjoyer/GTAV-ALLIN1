using Xunit;

namespace ALLIN1.Tests
{
    public sealed class WeaponCustomizationPolicyTests
    {
        [Fact]
        public void Ammo_or_a_single_mandatory_magazine_is_not_customization()
        {
            Assert.False(WeaponCustomizationPolicy.HasChoices(new WeaponComponentDefaults.Entry[0], 0));
            Assert.False(WeaponCustomizationPolicy.HasChoices(new[] {
                new WeaponComponentDefaults.Entry(1, unchecked((int)GTA.WeaponAttachmentPoint.Clip), true) }, 1));
            Assert.True(WeaponCustomizationPolicy.HasChoices(new[] {
                new WeaponComponentDefaults.Entry(1, unchecked((int)GTA.WeaponAttachmentPoint.Clip), true),
                new WeaponComponentDefaults.Entry(2, unchecked((int)GTA.WeaponAttachmentPoint.Clip), false) }, 0));
            Assert.True(WeaponCustomizationPolicy.HasChoices(new WeaponComponentDefaults.Entry[0], 2));
        }

        [Theory]
        [InlineData(true, false)]
        [InlineData(false, true)]
        public void Single_scope_is_a_choice_only_if_optional(bool mandatory, bool expected)
        {
            Assert.Equal(expected, WeaponCustomizationPolicy.HasChoices(new[] {
                new WeaponComponentDefaults.Entry(4, (int)GTA.WeaponAttachmentPoint.Scope, mandatory) }, 0));
        }

        [Theory]
        [InlineData(GTA.WeaponAttachmentPoint.Scope, true)]
        [InlineData(GTA.WeaponAttachmentPoint.Scope2, true)]
        [InlineData(GTA.WeaponAttachmentPoint.Supp, true)]
        [InlineData(GTA.WeaponAttachmentPoint.Supp2, true)]
        [InlineData(GTA.WeaponAttachmentPoint.Grip, true)]
        [InlineData(GTA.WeaponAttachmentPoint.FlashLaser2, true)]
        [InlineData(GTA.WeaponAttachmentPoint.Clip, false)]
        [InlineData(GTA.WeaponAttachmentPoint.Barrel, false)]
        [InlineData(GTA.WeaponAttachmentPoint.GunRoot, false)]
        [InlineData(GTA.WeaponAttachmentPoint.Invalid, false)]
        public void Only_optional_accessory_slots_can_be_unequipped(GTA.WeaponAttachmentPoint point, bool allowed)
        {
            Assert.Equal(allowed, WeaponCustomizationPolicy.CanUnequipComponent(unchecked((int)point)));
        }
        [Theory]
        [InlineData("Clip", "Extended Magazine", 2500)]
        [InlineData("Unknown", "Extended Clip", 2500)]
        [InlineData("Scope", "Large Scope", 3500)]
        [InlineData("Muzzle", "Suppressor", 5000)]
        [InlineData("Barrel", "Heavy Barrel", 6000)]
        [InlineData("FlashLaser", "Flashlight", 2000)]
        [InlineData("GunGripR", "Grip", 2500)]
        [InlineData("GunRoot", "Digital Camo", 7500)]
        [InlineData("Unknown", "Upgrade", 3000)]
        public void ComponentPrices_AreStableByUpgradeFamily(
            string point, string name, int expected)
        {
            Assert.Equal(expected,
                WeaponCustomizationPolicy.ComponentPrice(point, name));
        }

        [Fact]
        public void DefaultTintIsFree_AndPremiumTintsScale()
        {
            Assert.Equal(0, WeaponCustomizationPolicy.TintPrice(0));
            Assert.Equal(1500, WeaponCustomizationPolicy.TintPrice(1));
            Assert.Equal(3000, WeaponCustomizationPolicy.TintPrice(7));
        }

        [Fact]
        public void DefaultLiveryColorIsFree_AndPremiumColorsScale()
        {
            Assert.Equal(0, WeaponCustomizationPolicy.ComponentTintPrice(0));
            Assert.Equal(875, WeaponCustomizationPolicy.ComponentTintPrice(1));
            Assert.Equal(4625, WeaponCustomizationPolicy.ComponentTintPrice(31));
        }

        [Theory]
        [InlineData(100, 0, true, true, false, true)]
        [InlineData(100, 100, false, false, false, true)]
        [InlineData(100, 200, false, false, false, false)]
        [InlineData(100, 100, false, true, false, false)]
        [InlineData(100, 0, false, false, true, true)]
        [InlineData(100, 0, false, true, true, false)]
        public void Equipped_component_prefers_live_then_saved_then_default(
            int component, int saved, bool live, bool anyLive,
            bool isDefault, bool expected)
        {
            Assert.Equal(expected, WeaponCustomizationPolicy.IsComponentEquipped(
                component, saved, live, anyLive, isDefault));
        }

        [Theory]
        [InlineData("Component 0x62CFAF46", true)]
        [InlineData("Extended Clip", false)]
        [InlineData("", true)]
        public void Opaque_component_labels_are_detected(
            string label, bool expected)
        {
            Assert.Equal(expected,
                WeaponCustomizationPolicy.IsOpaqueComponentLabel(label));
        }

        [Theory]
        [InlineData("Receiver", "Receiver upgrade")]
        [InlineData("Weapon upgrade", "Weapon upgrade")]
        [InlineData("", "Weapon upgrade")]
        public void Opaque_components_get_a_readable_family_label(
            string detail, string expected)
        {
            Assert.Equal(expected,
                WeaponCustomizationPolicy.FallbackComponentLabel(detail));
        }
    }
}
