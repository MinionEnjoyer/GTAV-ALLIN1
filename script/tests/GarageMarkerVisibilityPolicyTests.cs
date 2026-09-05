using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GarageMarkerVisibilityPolicyTests
    {
        [Theory]
        [InlineData(false, false, true)]
        [InlineData(true, false, false)]
        [InlineData(false, true, false)]
        [InlineData(true, true, false)]
        public void Map_locations_follow_authoritative_story_state(
            bool missionActive, bool gameTransitionActive, bool expected)
        {
            Assert.Equal(expected,
                GarageMarkerVisibilityPolicy.ShouldShowMapLocations(
                    missionActive, gameTransitionActive));
        }

        [Theory]
        [InlineData(false, false, false, true)]
        [InlineData(true, false, false, false)]
        [InlineData(false, true, false, false)]
        [InlineData(true, true, false, false)]
        [InlineData(true, false, true, true)]
        [InlineData(false, true, true, true)]
        public void Story_state_suppresses_only_exterior_service(
            bool missionActive, bool gameTransitionActive,
            bool playerAlreadyInside, bool expected)
        {
            Assert.Equal(expected,
                GarageMarkerVisibilityPolicy.ShouldServiceExterior(
                    missionActive, gameTransitionActive,
                    playerAlreadyInside));
        }

        [Fact]
        public void Every_garage_and_storage_blip_uses_the_shared_visibility_update()
        {
            string source = ReadSource("GarageManager.cs");
            string method = ExtractMethod(source,
                "UpdateLocationBlipVisibility");
            string[] blips =
            {
                "_entranceBlip",
                "_pedEntranceBlip",
                "_floorGarageEntranceBlip",
                "_floorGaragePedBlip",
                "_davisVehicleBlip",
                "_davisPedBlip",
                "_garmentVehicleBlip",
                "_garmentPedBlip",
                "_ruralVehicleBlip",
                "_ruralPedBlip",
                "_paletoVehicleBlip",
                "_paletoPedBlip",
                "_helipadAccessBlip",
                "_helipadVehicleBlip",
                "_harbourAccessBlip",
                "_harbourVehicleBlip",
                "_marinaAccessBlip",
                "_marinaVehicleBlip",
            };

            foreach (string blip in blips)
                Assert.Contains($"SetBlipVisibility({blip}, visible)", method);
            Assert.Contains("IsMissionActive()", method);
            Assert.Contains("IsUnsafeGarageTransitionActive()", method);
        }

        [Fact]
        public void Every_exterior_marker_loop_uses_the_shared_story_gate()
        {
            var methods = new Dictionary<string, string>
            {
                ["GarageManager.cs"] = "OnTick",
                ["GarageManager.cs#floor"] = "OnFloorGarageTick",
                ["GarageManager.Davis.cs"] = "OnDavisGarageTick",
                ["GarageManager.GarmentFactory.cs"] =
                    "OnGarmentGarageTick",
                ["GarageManager.Rural.cs"] = "OnRuralGarageTick",
                ["GarageManager.Paleto.cs"] = "OnPaletoGarageTick",
                ["GarageManager.Helipad.cs"] = "OnHelipadTick",
                ["GarageManager.Harbour.cs"] = "OnHarbourTick",
                ["GarageManager.Yacht.cs"] = "OnYachtHelipadTick",
            };

            foreach (KeyValuePair<string, string> item in methods)
            {
                string file = item.Key.Split('#')[0];
                string method = ExtractMethod(ReadSource(file), item.Value);
                Assert.Contains("ShouldServiceGarageExterior()", method);
            }
        }

        [Fact]
        public void Garage_mission_state_excludes_ambient_getaway_prep_threads()
        {
            string garage = ExtractMethod(ReadSource("GarageManager.cs"),
                "IsMissionActive");
            Assert.Contains("Hash.GET_MISSION_FLAG", garage);
            Assert.DoesNotContain("GetawayVehicleCompatibility.DetectMission()",
                garage);

            // The specialized detector remains available to the getaway
            // compatibility feature, but it must never become global Story
            // mission state for garage markers or exterior interactions.
            string getaway = ReadSource("GetawayVehicleCompatibility.cs");
            Assert.Contains("agency_prep2amb", getaway);
            Assert.Contains("fbi4_prep3amb", getaway);
            Assert.Contains("finale_heist_prepeamb", getaway);
            Assert.Contains(
                "GET_NUMBER_OF_THREADS_RUNNING_THE_SCRIPT_WITH_THIS_HASH",
                getaway);
        }

        [Fact]
        public void Visibility_updates_log_the_authoritative_state_transition()
        {
            string method = ExtractMethod(ReadSource("GarageManager.cs"),
                "UpdateLocationBlipVisibility");
            Assert.Contains("location_visibility_changed", method);
            Assert.Contains("mission_active", method);
            Assert.Contains("transition_active", method);
            Assert.Contains("visible", method);
        }

        private static string ReadSource(string fileName)
        {
            return File.ReadAllText(Path.Combine(
                RepositoryRoot(), "script", "src", fileName));
        }

        private static string RepositoryRoot()
        {
            DirectoryInfo cursor = new DirectoryInfo(AppContext.BaseDirectory);
            while (cursor != null)
            {
                if (Directory.Exists(Path.Combine(
                        cursor.FullName, "script", "src")))
                    return cursor.FullName;
                cursor = cursor.Parent;
            }
            throw new DirectoryNotFoundException(
                "Could not locate the ALLIN1 repository root.");
        }

        private static string ExtractMethod(string source, string methodName)
        {
            Match declaration = Regex.Match(source,
                @"(?:private|internal|public)\s+static\s+[^\r\n(]+\s+" +
                Regex.Escape(methodName) + @"\s*\(");
            Assert.True(declaration.Success,
                $"Missing method {methodName}.");
            int name = declaration.Index;
            int open = source.IndexOf('{', declaration.Index);
            Assert.True(open >= 0, $"Missing body for {methodName}.");
            int depth = 0;
            for (int index = open; index < source.Length; index++)
            {
                if (source[index] == '{') depth++;
                else if (source[index] == '}' && --depth == 0)
                    return source.Substring(name, index - name + 1);
            }
            throw new InvalidDataException(
                $"Unterminated body for {methodName}.");
        }
    }
}
