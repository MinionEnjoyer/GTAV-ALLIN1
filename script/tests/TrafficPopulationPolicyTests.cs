using System;
using System.IO;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class TrafficPopulationPolicyTests
    {
        private const string Valid = "{\"schema_version\":1,\"enabled\":true,\"replacement_chance\":0.4,\"entries\":[{\"package_id\":\"acme.traffic\",\"model\":\"acme_car\",\"enabled\":true,\"weight\":2.5},{\"package_id\":\"acme.traffic\",\"model\":\"off_car\",\"enabled\":false,\"weight\":1}]}";

        [Fact]
        public void Valid_document_overrides_only_enabled_matching_package_entries()
        {
            TrafficPopulationConfiguration configuration =
                TrafficPopulationPolicy.Parse(Valid);

            Assert.True(configuration.Enabled);
            Assert.Equal(0.4d, configuration.ReplacementChance);
            Assert.True(configuration.TryGetEnabledWeight("ACME.TRAFFIC",
                "ACME_CAR", out double weight));
            Assert.Equal(2.5d, weight);
            Assert.False(configuration.TryGetEnabledWeight("acme.traffic",
                "off_car", out _));
            Assert.False(configuration.TryGetEnabledWeight("other.package",
                "acme_car", out _));
        }

        [Theory]
        [InlineData("{\"schema_version\":1,\"enabled\":true,\"replacement_chance\":0,\"entries\":[],\"extra\":false}")]
        [InlineData("{\"schema_version\":1,\"enabled\":true,\"replacement_chance\":1.1,\"entries\":[]}")]
        [InlineData("{\"schema_version\":1,\"enabled\":true,\"replacement_chance\":0,\"entries\":[{\"package_id\":\"acme.traffic\",\"model\":\"car\",\"enabled\":true,\"weight\":0.01}]}")]
        [InlineData("{\"schema_version\":1,\"enabled\":true,\"enabled\":false,\"replacement_chance\":0,\"entries\":[]}")]
        public void Malformed_or_ambiguous_document_is_rejected(string json)
        {
            Assert.Throws<InvalidDataException>(() =>
                TrafficPopulationPolicy.Parse(json));
        }

        [Fact]
        public void Missing_document_preserves_legacy_behavior_but_bad_file_fails_closed()
        {
            string path = Path.Combine(Path.GetTempPath(),
                "allin1-traffic-policy-" + Guid.NewGuid().ToString("N") + ".json");
            try
            {
                Assert.True(TrafficPopulationPolicy.TryLoad(path, out _,
                    out bool absent, out _));
                Assert.False(absent);
                File.WriteAllText(path, "{not json");
                Assert.False(TrafficPopulationPolicy.TryLoad(path, out _,
                    out bool present, out string error));
                Assert.True(present);
                Assert.NotEmpty(error);
            }
            finally
            {
                if (File.Exists(path)) File.Delete(path);
            }
        }

        [Theory]
        [InlineData(true, true, true, true)]
        [InlineData(true, true, false, false)]
        [InlineData(true, false, true, false)]
        [InlineData(false, true, true, false)]
        public void Master_population_switch_pauses_the_existing_runtime(
            bool packageEnabled, bool legacyEnabled, bool populationEnabled,
            bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.ShouldAttachRuntimeHandlers(
                    packageEnabled, legacyEnabled) &&
                !TrafficSpawner.ShouldPauseForPopulationConfiguration(
                    true, true, populationEnabled));
        }
    }
}
