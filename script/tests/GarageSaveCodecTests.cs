using System.IO;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GarageSaveCodecTests
    {
        private static readonly string[] Keys = { "michael", "franklin", "trevor" };

        [Fact]
        public void Parse_accepts_complete_vehicle_state()
        {
            const string json = @"{
                ""_schema_v2"": [],
                ""michael"": [{
                    ""model"": ""furoregt"", ""modelHash"": -1089039904,
                    ""slot"": 2, ""color1"": 12, ""color2"": 34,
                    ""plate"": ""ABC123"", ""mods"": [-1,4],
                    ""modToggles"": [0,1], ""neonColor"": [1,2,3]
                }],
                ""franklin"": [],
                ""trevor"": []
            }";

            var parsed = GarageSaveCodec.Parse(json, Keys, 10);

            var vehicle = Assert.Single(parsed["michael"]);
            Assert.Equal("furoregt", vehicle.Model);
            Assert.Equal(-1089039904, vehicle.ModelHash);
            Assert.Equal(2, vehicle.Slot);
            Assert.Equal("ABC123", vehicle.PlateText);
            Assert.Equal(new[] { -1, 4 }, vehicle.Mods);
            Assert.Equal(new[] { false, true }, vehicle.ModToggles);
            Assert.Equal(new[] { 1, 2, 3 }, vehicle.NeonColor);
        }

        [Theory]
        [InlineData("")]
        [InlineData("{\"michael\":[]")]
        [InlineData("[]")]
        [InlineData("{\"michael\":[],\"franklin\":[]}")]
        public void Parse_rejects_incomplete_or_malformed_documents(string json)
        {
            Assert.Throws<InvalidDataException>(() => GarageSaveCodec.Parse(json, Keys, 10));
        }

        [Fact]
        public void Parse_rejects_duplicate_or_out_of_range_slots()
        {
            const string duplicate = @"{
                ""michael"": [{""model"":""adder"",""slot"":1},{""model"":""zentorno"",""slot"":1}],
                ""franklin"": [], ""trevor"": []
            }";
            const string outOfRange = @"{
                ""michael"": [{""model"":""adder"",""slot"":10}],
                ""franklin"": [], ""trevor"": []
            }";

            Assert.Throws<InvalidDataException>(() => GarageSaveCodec.Parse(duplicate, Keys, 10));
            Assert.Throws<InvalidDataException>(() => GarageSaveCodec.Parse(outOfRange, Keys, 10));
        }

        [Fact]
        public void Parse_rejects_partial_vehicle_records_and_invalid_arrays()
        {
            const string missingModel = @"{
                ""michael"": [{""slot"":0}], ""franklin"": [], ""trevor"": []
            }";
            const string invalidRgb = @"{
                ""michael"": [{""model"":""adder"",""slot"":0,""neonColor"":[1,2]}],
                ""franklin"": [], ""trevor"": []
            }";
            const string invalidToggle = @"{
                ""michael"": [{""model"":""adder"",""slot"":0,""modToggles"":[2]}],
                ""franklin"": [], ""trevor"": []
            }";

            Assert.Throws<InvalidDataException>(() => GarageSaveCodec.Parse(missingModel, Keys, 10));
            Assert.Throws<InvalidDataException>(() => GarageSaveCodec.Parse(invalidRgb, Keys, 10));
            Assert.Throws<InvalidDataException>(() => GarageSaveCodec.Parse(invalidToggle, Keys, 10));
        }
    }
}
