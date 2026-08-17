using Xunit;

namespace ALLIN1.Tests
{
    public sealed class WeaponCustomizationPolicyTests
    {
        [Theory]
        [InlineData("Clip", "Extended Magazine", 2500)]
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
    }
}
