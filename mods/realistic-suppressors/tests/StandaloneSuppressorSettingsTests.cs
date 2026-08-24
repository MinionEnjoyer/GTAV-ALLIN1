using System;
using System.IO;
using Xunit;

namespace RealisticSuppressors.Tests
{
    public sealed class StandaloneSuppressorSettingsTests
    {
        [Fact]
        public void Missing_config_uses_safe_launcher_equivalent_defaults()
        {
            string path = Path.Combine(Path.GetTempPath(),
                Guid.NewGuid().ToString("N") + ".ini");
            StandaloneSuppressorSettings settings =
                StandaloneSuppressorSettings.Load(path);

            Assert.True(settings.StealthEnabled);
            Assert.True(settings.BreakageEnabled);
            Assert.True(settings.HeatSmokeEnabled);
            Assert.False(settings.TemperatureDebugEnabled);
            Assert.Equal(1f, settings.DurabilityScale);
            Assert.Equal(1f, settings.HeatSmokeIntensity);
            Assert.Empty(settings.Warnings);
        }

        [Fact]
        public void First_launch_creates_config_without_overwriting_edits()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "realistic-suppressors-create-" +
                Guid.NewGuid().ToString("N"));
            string path = Path.Combine(root,
                StandaloneSuppressorSettings.FileName);
            try
            {
                Assert.Equal("", StandaloneSuppressorSettings
                    .EnsureDefaultFile(path));
                Assert.Contains("[RealisticSuppressors]",
                    File.ReadAllText(path));

                File.WriteAllText(path,
                    "temperature_debug = true\n");
                Assert.Equal("", StandaloneSuppressorSettings
                    .EnsureDefaultFile(path));
                Assert.Equal("temperature_debug = true\n",
                    File.ReadAllText(path));
            }
            finally
            {
                if (Directory.Exists(root))
                    Directory.Delete(root, true);
            }
        }

        [Fact]
        public void Ini_values_are_case_insensitive_and_invariant()
        {
            WithConfig(
                "[RealisticSuppressors]\n" +
                "REALISTIC_SUPPRESSOR_STEALTH = off\n" +
                "suppressor_wear_and_breakage = no\n" +
                "suppressor_heat_smoke = 0\n" +
                "temperature_debug = yes\n" +
                "suppressor_durability_multiplier = 2.25\n" +
                "heat_smoke_intensity = 1.75\n",
                settings =>
                {
                    Assert.False(settings.StealthEnabled);
                    Assert.False(settings.BreakageEnabled);
                    Assert.False(settings.HeatSmokeEnabled);
                    Assert.True(settings.TemperatureDebugEnabled);
                    Assert.Equal(2.25f, settings.DurabilityScale);
                    Assert.Equal(1.75f,
                        settings.HeatSmokeIntensity);
                    Assert.Empty(settings.Warnings);
                });
        }

        [Fact]
        public void Numeric_settings_are_clamped_without_disabling_runtime()
        {
            WithConfig(
                "suppressor_durability_multiplier = 99\n" +
                "heat_smoke_intensity = 0.1\n",
                settings =>
                {
                    Assert.Equal(3f, settings.DurabilityScale);
                    Assert.Equal(0.5f,
                        settings.HeatSmokeIntensity);
                    Assert.Equal(2, settings.Warnings.Count);
                });
        }

        [Fact]
        public void Invalid_values_keep_defaults_and_report_warnings()
        {
            WithConfig(
                "[Ignored]\n" +
                "temperature_debug = true\n" +
                "[RealisticSuppressors]\n" +
                "suppressor_heat_smoke = perhaps\n" +
                "heat_smoke_intensity = 1,5\n" +
                "broken line\n",
                settings =>
                {
                    Assert.False(settings.TemperatureDebugEnabled);
                    Assert.True(settings.HeatSmokeEnabled);
                    Assert.Equal(1f,
                        settings.HeatSmokeIntensity);
                    Assert.Equal(3, settings.Warnings.Count);
                });
        }

        private static void WithConfig(
            string content, Action<StandaloneSuppressorSettings> assertion)
        {
            string root = Path.Combine(Path.GetTempPath(),
                "realistic-suppressors-settings-" +
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            string path = Path.Combine(root,
                StandaloneSuppressorSettings.FileName);
            try
            {
                File.WriteAllText(path, content);
                assertion(StandaloneSuppressorSettings.Load(path));
            }
            finally
            {
                if (Directory.Exists(root))
                    Directory.Delete(root, true);
            }
        }
    }
}
