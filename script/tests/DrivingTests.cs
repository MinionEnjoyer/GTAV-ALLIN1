using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public class DrivingTests
    {
        [Theory]
        [InlineData(true, false, true, true)]
        [InlineData(true, true, true, false)]
        [InlineData(false, false, false, false)]
        [InlineData(false, true, false, false)]
        public void MissionRestrictsControlsNotReadOnlyHud(bool scene, bool mission, bool hud, bool controls)
        {
            var actual = DrivingPolicy.Availability(scene, mission);
            Assert.Equal(hud, actual.Hud);
            Assert.Equal(controls, actual.Controls);
        }
        [Theory]
        [InlineData(10, "kmh", 36)]
        [InlineData(10, "mph", 22.369363)]
        [InlineData(-1, "kmh", 0)]
        public void Units(float speed, string units, float expected) => Assert.InRange(DrivingPolicy.DisplaySpeed(speed, units), expected - .0001f, expected + .0001f);
        [Fact]
        public void InvalidNumbersAreNotEmitted()
        {
            Assert.Null(DrivingPolicy.Number(float.NaN)); Assert.Null(DrivingPolicy.Number(float.PositiveInfinity));
            Assert.Equal(0, DrivingPolicy.DisplaySpeed(float.NaN, "mph"));
        }
        [Theory]
        [InlineData(0, 6, "R")]
        [InlineData(3, 6, "3")]
        [InlineData(0, 0, "?")]
        [InlineData(9, 6, "?")]
        [InlineData(-1, 6, "?")]
        public void GearReadout(int actual, int count, string expected) => Assert.Equal(expected, DrivingPolicy.Gear(actual, count));
        [Theory]
        [InlineData(359, -1)]
        [InlineData(-359, 1)]
        [InlineData(180, -180)]
        public void YawWrap(float angle, float expected) => Assert.Equal(expected, DrivingPolicy.Angle(angle));
        [Theory]
        [InlineData("auto", false, false, "builtin")]
        [InlineData("auto", true, true, "rex")]
        [InlineData("rex", false, true, "builtin")]
        [InlineData("lefix", true, true, "lefix")]
        [InlineData("off", true, true, "off")]
        [InlineData("builtin", true, true, "builtin")]
        public void ExternalProviderFallback(string requested, bool rex, bool lefix, string expected) => Assert.Equal(expected, DrivingPolicy.Provider(requested, rex, lefix));
        [Theory]
        [InlineData(1, -1, 6, .3f, 1)]
        [InlineData(6, 1, 6, .5f, 6)]
        [InlineData(2, 1, 6, .4f, 3)]
        [InlineData(3, -1, 6, .8f, 3)]
        [InlineData(3, -1, 6, .6f, 2)]
        [InlineData(0, 1, 6, .3f, 0)]
        public void SequentialBounds(int gear, int direction, int count, float rpm, int expected) => Assert.Equal(expected, DrivingPolicy.Shift(gear, direction, count, rpm));
        [Fact]
        public void EveryHoldGateFailsClosed()
        {
            Assert.True(DrivingPolicy.CanHold(true, true, true, false, true, 1, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(false, true, true, false, true, 1, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(true, false, true, false, true, 1, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(true, true, false, false, true, 1, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(true, true, true, true, true, 1, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(true, true, true, false, false, 1, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(true, true, true, false, true, 0, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(true, true, true, false, true, 7, 6, .3f));
            Assert.False(DrivingPolicy.CanHold(true, true, true, false, true, 1, 0, .3f));
            Assert.False(DrivingPolicy.CanHold(true, true, true, false, true, 1, 6, float.NaN));
        }
        [Fact]
        public void SettingsAreScopedAndStrict()
        {
            var options = DrivingOptions.Parse(new[] { "[other]", "speedometer_units = \"invalid\"", "[script]", "speedometer_units = \"mph\" # comment", "shift_controls_enabled = false", "driving_telemetry = \"all\"", "speedometer_provider = \"lefix\"" });
            Assert.Equal("mph", options.Units); Assert.False(options.ShiftControls); Assert.Equal("all", options.Telemetry); Assert.Equal("lefix", options.Provider);
            Assert.Throws<InvalidDataException>(() => DrivingOptions.Parse(new[] { "[script]", "shift_controls_enabled = 1" }));
            Assert.Throws<InvalidDataException>(() => DrivingOptions.Parse(new[] { "[script]", "speedometer_provider = \"private-api\"" }));
            Assert.Throws<InvalidDataException>(() => DrivingOptions.Parse(new[] { "[script]", "driving_telemetry = \"yes\"" }));
        }
        [Fact]
        public void LoggerDrainsAndWritesValidDetachedJson()
        {
            string dir = Path.Combine(Path.GetTempPath(), "allin1-driving-test-" + Guid.NewGuid().ToString("N"));
            string path = Path.Combine(dir, "driving.jsonl");
            try
            {
                using (var log = new DrivingTelemetryLog(path))
                {
                    var data = new Dictionary<string, object> { ["speed_mps"] = 3f, ["unavailable"] = null };
                    log.Record("sample", data); data["speed_mps"] = 99;
                    log.Record("session_ended");
                }
                var rows = File.ReadAllLines(path).Select(JObject.Parse).ToArray();
                Assert.Equal(2, rows.Length); Assert.Equal(3, (float)rows[0]["speed_mps"]);
                Assert.Equal("sample", (string)rows[0]["kind"]); Assert.Equal(1, (int)rows[0]["schema"]);
                Assert.Equal(rows[0]["session"], rows[1]["session"]);
            }
            finally { if (Directory.Exists(dir)) Directory.Delete(dir, true); }
        }
        [Fact]
        public void LoggerRotatesOnlyItsThreeArchives()
        {
            string dir = Path.Combine(Path.GetTempPath(), "allin1-driving-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir); string path = Path.Combine(dir, "driving.jsonl");
            try
            {
                File.WriteAllText(path, "old"); File.WriteAllText(path + ".1", "older");
                File.WriteAllText(path + ".2", "older2"); File.WriteAllText(path + ".3", "oldest");
                File.WriteAllText(Path.Combine(dir, "unrelated.txt"), "keep");
                using (var log = new DrivingTelemetryLog(path, 1)) log.Record("sample");
                Assert.Equal("old", File.ReadAllText(path + ".1")); Assert.Equal("older2", File.ReadAllText(path + ".3"));
                Assert.False(File.Exists(path + ".4")); Assert.Equal("keep", File.ReadAllText(Path.Combine(dir, "unrelated.txt")));
            }
            finally { Directory.Delete(dir, true); }
        }
    }
}
