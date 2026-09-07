using Xunit;

namespace RealisticSuppressors.Tests
{
    public sealed class VectorSuppressorProfileTests
    {
        [Fact]
        public void Vector_resolves_its_own_identity_and_installed_stock_can()
        {
            var vector = SuppressorProfileDiscovery.Parse(SuppressorProfileDiscoveryTests.VectorJson)[0];
            Assert.Equal("WEAPON_A1_KRISS_VECTOR", vector.WeaponName);
            Assert.Equal(0xC304849Au, vector.ComponentHash);
            Assert.Equal(SuppressorWeaponClass.SubmachineGun, vector.WeaponClass);
            Assert.Contains("approximation", vector.ThermalBasis);
            Assert.True(SuppressorThermalProfiles.TryGet(0x2BE6766Bu, out var smg));
            Assert.NotEqual(smg.WeaponName, vector.WeaponName);
            Assert.NotSame(smg, vector);
        }

        [Fact]
        public void Vector_heats_cools_and_wears_without_changing_the_donor()
        {
            var vector = SuppressorProfileDiscovery.Parse(SuppressorProfileDiscoveryTests.VectorJson)[0];
            var step = SuppressorThermalPolicy.ApplyShots(vector,
                SuppressorThermalPolicy.AmbientCelsius, 1f, 30, true, 1f);
            Assert.Equal(89f, step.TemperatureCelsius, 3);
            Assert.True(step.DurabilityLost > 0);
            Assert.False(step.Broke);
            Assert.Equal(54.5f, SuppressorThermalPolicy.CoolTemperature(
                step.TemperatureCelsius, 240000, vector.CoolingHalfLifeSeconds), 3);
            var hot = SuppressorThermalPolicy.ApplyShots(vector,
                SuppressorThermalPolicy.AmbientCelsius, 1f, 100, true, 1f);
            for (int burst = 1; burst < 3; burst++)
                hot = SuppressorThermalPolicy.ApplyShots(vector,
                    hot.TemperatureCelsius, hot.Durability, 100, true, 1f);
            Assert.True(hot.TemperatureCelsius > vector.CriticalCelsius);
            Assert.True(hot.DurabilityLost > step.DurabilityLost);
        }
    }
}
