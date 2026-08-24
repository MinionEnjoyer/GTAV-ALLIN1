using System.Collections.Generic;
using System.IO;
using Xunit;

namespace RealisticSuppressors.Tests
{
    public sealed class PortableJsonTests
    {
        [Fact]
        public void NestedObjectsNumbersAndEscapesRoundTrip()
        {
            var source = new Dictionary<string, object>
            {
                { "schema_version", 1 },
                { "enabled", true },
                { "message", "orange\n\"glow\"" },
                { "state", new Dictionary<string, object>
                    {
                        { "temperature", 525.5f },
                        { "durability", 0.75f },
                    }
                },
            };

            Dictionary<string, object> parsed = PortableJson.ParseObject(
                PortableJson.Serialize(source));

            Assert.Equal(1, parsed["schema_version"]);
            Assert.Equal(true, parsed["enabled"]);
            Assert.Equal("orange\n\"glow\"", parsed["message"]);
            var state = Assert.IsType<Dictionary<string, object>>(
                parsed["state"]);
            Assert.Equal(525.5d, Assert.IsType<double>(
                state["temperature"]), 3);
        }

        [Theory]
        [InlineData("{\"a\":1,\"a\":2}")]
        [InlineData("{\"a\":1} trailing")]
        [InlineData("[01]")]
        [InlineData("{\"a\":NaN}")]
        public void MalformedOrAmbiguousInputIsRejected(string json)
        {
            Assert.Throws<InvalidDataException>(() =>
                PortableJson.Parse(json));
        }

        [Fact]
        public void UnsupportedAndNonFiniteValuesAreRejected()
        {
            Assert.Throws<InvalidDataException>(() =>
                PortableJson.Serialize(double.NaN));
            Assert.Throws<InvalidDataException>(() =>
                PortableJson.Serialize(new object()));
        }
    }
}
