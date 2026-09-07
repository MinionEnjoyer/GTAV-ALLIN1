using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Xunit;

namespace ALLIN1.Tests
{
    public class TrailerHitchTests
    {
        private static Dictionary<string, object> Point(string id = "rear", string mode = "native") => new Dictionary<string, object> {
            ["id"] = id, ["mode"] = mode, ["bone"] = "attach_female", ["coupler_bone"] = "attach_male",
            ["position"] = new[] { 0, 0, 0 }, ["rotation"] = new[] { 0, 0, 0 }, ["coupler_offset"] = new[] { 0, 0, 0 },
            ["compatible_models"] = new[] { "trailers" }, ["connect_distance"] = 1, ["break_force"] = 10000,
        };
        private static object Document(Dictionary<string, object> point) => PortableJsonParser.Parse(JsonConvert.SerializeObject(new {
            schema_version = 1, vehicle_model = "testcar", points = new[] { point },
        }));
        [Fact]
        public void ReadsSdkCompatibleProfile()
        {
            var p = TrailerHitchProfile.Parse(Document(Point()), "testcar").Points[0];
            Assert.False(p.Experimental); Assert.Equal("rear", p.Id); Assert.Equal("trailers", p.CompatibleModels[0]);
        }
        [Theory]
        [InlineData("connect_distance", 3)]
        [InlineData("connect_distance", true)]
        [InlineData("break_force", 0)]
        [InlineData("mode", "rigid")]
        [InlineData("bone", "../chassis")]
        [InlineData("id", "middle")]
        [InlineData("unknown", "value")]
        public void InvalidProfilesAreRejected(string key, object value)
        {
            var p = Point(); p[key] = value;
            Assert.Throws<InvalidDataException>(() => TrailerHitchProfile.Parse(Document(p), "testcar"));
        }
        [Fact]
        public void NativeOffsetsRejectedPhysicalOffsetsAccepted()
        {
            var p = Point(); p["position"] = new[] { 0, 2, 0 };
            Assert.Throws<InvalidDataException>(() => TrailerHitchProfile.Parse(Document(p), "testcar"));
            p["mode"] = "physical"; p["id"] = "front";
            Assert.True(TrailerHitchProfile.Parse(Document(p), "testcar").Points[0].Experimental);
        }
        [Fact]
        public void ModelMismatchAndDuplicateSlotsRejected()
        {
            Assert.Throws<InvalidDataException>(() => TrailerHitchProfile.Parse(Document(Point()), "different"));
            var duplicate = PortableJsonParser.Parse(JsonConvert.SerializeObject(new { schema_version = 1, vehicle_model = "testcar", points = new[] { Point(), Point() } }));
            Assert.Throws<InvalidDataException>(() => TrailerHitchProfile.Parse(duplicate, "testcar"));
        }
        [Theory]
        [InlineData(false, true, false, true, true, false, 0, 0, .5f, false, false)]
        [InlineData(true, false, false, true, true, false, 0, 0, .5f, false, false)]
        [InlineData(true, true, true, true, true, false, 0, 0, .5f, false, false)]
        [InlineData(true, true, false, false, true, false, 0, 0, .5f, false, false)]
        [InlineData(true, true, false, true, false, false, 0, 0, .5f, false, false)]
        [InlineData(true, true, false, true, true, true, 0, 0, .5f, false, false)]
        [InlineData(true, true, false, true, true, false, 1, 0, .5f, false, false)]
        [InlineData(true, true, false, true, true, false, 0, 1, .5f, false, false)]
        [InlineData(true, true, false, true, true, false, 0, 0, 2, false, false)]
        [InlineData(true, true, false, true, true, false, 0, 0, .5f, true, false)]
        public void UnsafeCouplingIsDenied(bool story, bool driver, bool occupied, bool compatible, bool bones, bool attached,
            float speed, float otherSpeed, float distance, bool experimental, bool confirmed)
        {
            Assert.NotNull(TrailerHitchPolicy.Denial(story, driver, occupied, compatible, bones, attached, speed, otherSpeed, distance, 1, experimental, confirmed));
        }
        [Fact]
        public void StationaryCloseAndConfirmedAreAllowed()
        {
            Assert.Null(TrailerHitchPolicy.Denial(true, true, false, true, true, false, 0, 0, .5f, 1, true, true));
            Assert.Null(TrailerHitchPolicy.Denial(true, true, false, true, true, false, 0, 0, .5f, 1, false, false));
            Assert.NotNull(TrailerHitchPolicy.Denial(true, true, false, true, true, false, float.NaN, 0, .5f, 1, false, false));
        }
    }
}
