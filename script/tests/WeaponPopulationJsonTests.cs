using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class WeaponPopulationJsonTests
    {
        private static double ReadChance(Dictionary<string, object> document)
        {
            return (double)typeof(WeaponPopulationInjector).GetMethod("Number",
                BindingFlags.Static | BindingFlags.NonPublic).Invoke(null,
                new object[] { document, "replacement_chance", 0d, 1d });
        }

        private static bool ReadMissionPreference(string json)
        {
            var document = (Dictionary<string, object>)PortableJsonParser.Parse(json);
            return (bool)typeof(WeaponPopulationInjector).GetMethod("OptionalBoolean",
                BindingFlags.Static | BindingFlags.NonPublic).Invoke(null,
                new object[] { document, "active_during_missions" });
        }

        [Theory]
        [InlineData("{}", false)]
        [InlineData("{\"active_during_missions\":false}", false)]
        [InlineData("{\"active_during_missions\":true}", true)]
        public void Mission_preference_supports_legacy_and_explicit_json(string json,
            bool expected)
        {
            Assert.Equal(expected, ReadMissionPreference(json));
        }

        [Theory]
        [InlineData("null")]
        [InlineData("0")]
        [InlineData("1")]
        [InlineData("\"true\"")]
        [InlineData("\"false\"")]
        [InlineData("[]")]
        [InlineData("{}")]
        public void Mission_preference_rejects_non_boolean_json(string raw)
        {
            var failure = Assert.Throws<TargetInvocationException>(() =>
                ReadMissionPreference("{\"active_during_missions\":" + raw + "}"));
            Assert.IsType<InvalidDataException>(failure.InnerException);
        }

        [Theory]
        [InlineData("", true)]
        [InlineData(",\"active_during_missions\":true", true)]
        [InlineData(",\"mission_override\":true", false)]
        [InlineData(",\"active_during_missions\":true,\"extra\":false", false)]
        public void Only_the_mission_preference_is_an_optional_root_field(string extra,
            bool valid)
        {
            var document = (Dictionary<string, object>)PortableJsonParser.Parse(
                "{\"schema_version\":1,\"enabled\":false," +
                "\"replacement_chance\":0,\"entries\":[]" + extra + "}");
            Action check = () => typeof(WeaponPopulationInjector).GetMethod("ExactFields",
                BindingFlags.Static | BindingFlags.NonPublic).Invoke(null,
                new object[] { document,
                    new[] { "schema_version", "enabled", "replacement_chance", "entries" },
                    new[] { "active_during_missions" } });
            if (valid) check();
            else Assert.IsType<InvalidDataException>(
                Assert.Throws<TargetInvocationException>(check).InnerException);
        }

        [Theory]
        [InlineData("schema_version")]
        [InlineData("enabled")]
        [InlineData("replacement_chance")]
        [InlineData("entries")]
        public void Optional_mission_preference_does_not_relax_required_fields(string field)
        {
            var document = (Dictionary<string, object>)PortableJsonParser.Parse(
                "{\"schema_version\":1,\"enabled\":false," +
                "\"replacement_chance\":0,\"entries\":[],\"active_during_missions\":true}");
            document.Remove(field);
            var failure = Assert.Throws<TargetInvocationException>(() =>
                typeof(WeaponPopulationInjector).GetMethod("ExactFields",
                    BindingFlags.Static | BindingFlags.NonPublic).Invoke(null,
                    new object[] { document,
                        new[] { "schema_version", "enabled", "replacement_chance", "entries" },
                        new[] { "active_during_missions" } }));
            Assert.IsType<InvalidDataException>(failure.InnerException);
        }

        [Theory]
        [InlineData("0.5", 0.5)]
        [InlineData("0.0", 0.0)]
        [InlineData("1.0", 1.0)]
        [InlineData("0", 0.0)]
        [InlineData("1", 1.0)]
        [InlineData("5e-1", 0.5)]
        [InlineData("0.25", 0.25)]
        public void Launcher_json_numbers_reach_the_runtime_chance(string number,
            double expected)
        {
            var document = (Dictionary<string, object>)PortableJsonParser.Parse(
                "{\"schema_version\":1,\"enabled\":true,\"entries\":[]," +
                "\"replacement_chance\":" + number + "}");
            Assert.Equal(expected, ReadChance(document));
        }

        [Theory]
        [InlineData("\"0.5\"")]
        [InlineData("true")]
        [InlineData("null")]
        [InlineData("[]")]
        [InlineData("{}")]
        [InlineData("-0.01")]
        [InlineData("1.01")]
        [InlineData("2147483648")]
        public void Non_numeric_or_out_of_bounds_json_remains_rejected(string value)
        {
            var document = (Dictionary<string, object>)PortableJsonParser.Parse(
                "{\"replacement_chance\":" + value + "}");
            var failure = Assert.Throws<TargetInvocationException>(() => ReadChance(document));
            Assert.IsType<InvalidDataException>(failure.InnerException);
        }

        [Theory]
        [InlineData(double.NaN)]
        [InlineData(double.PositiveInfinity)]
        [InlineData(double.NegativeInfinity)]
        public void Non_finite_values_are_rejected(double value)
        {
            var document = new Dictionary<string, object> { ["replacement_chance"] = value };
            var failure = Assert.Throws<TargetInvocationException>(() => ReadChance(document));
            Assert.IsType<InvalidDataException>(failure.InnerException);
        }

        [Fact]
        public void Missing_chance_is_rejected()
        {
            var failure = Assert.Throws<TargetInvocationException>(() =>
                ReadChance(new Dictionary<string, object>()));
            Assert.IsType<InvalidDataException>(failure.InnerException);
        }
    }
}
