using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GarageEntryPolicyTests
    {
        private static readonly GarageEntryRules Rules = new GarageEntryRules(
            disableDuringMissions: true,
            blockWantedLevel: true,
            blockStoryOwnedVehicles: true,
            maximumVehicleSizeTier: 1);

        [Fact]
        public void MissionDenialHasPriority()
        {
            Assert.Equal(GarageEntryDenial.MissionActive,
                GarageEntryPolicy.Evaluate(
                    Rules, true, true, 5, false, true, true, true, 2));
        }

        [Fact]
        public void GameTransitionDenialPreventsInteriorMapSwitches()
        {
            Assert.Equal(GarageEntryDenial.GameTransitionActive,
                GarageEntryPolicy.Evaluate(
                    Rules, false, true, 0, false,
                    false, false, false, 0));
        }

        [Theory]
        [InlineData(0, false, (int)GarageEntryDenial.None)]
        [InlineData(1, false, (int)GarageEntryDenial.WantedLevel)]
        [InlineData(5, false, (int)GarageEntryDenial.WantedLevel)]
        [InlineData(5, true, (int)GarageEntryDenial.None)]
        public void Wanted_level_blocks_entry_unless_override_is_enabled(
            int wantedLevel, bool alwaysAccessible, int expected)
        {
            Assert.Equal((GarageEntryDenial)expected,
                GarageEntryPolicy.Evaluate(
                    Rules, false, false, wantedLevel, alwaysAccessible,
                    false, false, false, 0));
        }

        [Fact]
        public void StoryVehicleIsDeniedBeforeSize()
        {
            Assert.Equal(GarageEntryDenial.StoryOwnedVehicle,
                GarageEntryPolicy.Evaluate(
                    Rules, false, false, 0, false, true, true, true, 2));
        }

        [Fact]
        public void SpecializedVehicleTypesAreDeniedBeforeSize()
        {
            Assert.Equal(GarageEntryDenial.UnsupportedVehicleType,
                GarageEntryPolicy.Evaluate(
                    Rules, false, false, 0, false,
                    true, false, true, 2, true));
        }

        [Theory]
        [InlineData("swift2")]
        [InlineData("raiju")]
        [InlineData("streamer216")]
        [InlineData("dinghy5")]
        [InlineData("conada2")]
        [InlineData("thruster")]
        public void AircraftAndBoatsRequireSpecializedStorage(string model)
        {
            Assert.True(
                GarageVehicleTypePolicy.RequiresSpecializedStorage(model));
            Assert.False(GarageVehicleTypePolicy.IsRegularGarageEligible(model));
        }

        [Theory]
        [InlineData("tailgater")]
        [InlineData("bati")]
        [InlineData("benson2")]
        [InlineData("oppressor2")]
        public void LandVehiclesRemainEligibleForRegularGarages(string model)
        {
            Assert.False(
                GarageVehicleTypePolicy.RequiresSpecializedStorage(model));
            Assert.True(GarageVehicleTypePolicy.IsRegularGarageEligible(model));
        }

        [Theory]
        [InlineData(true, true, 2, (int)GarageEntryDenial.VehicleTooLarge)]
        [InlineData(true, true, 1, (int)GarageEntryDenial.None)]
        [InlineData(true, false, 99, (int)GarageEntryDenial.None)]
        [InlineData(false, true, 99, (int)GarageEntryDenial.None)]
        public void SizeRuleOnlyAppliesToKnownPresentVehicles(
            bool present, bool known, int tier, int expected)
        {
            Assert.Equal((GarageEntryDenial)expected,
                GarageEntryPolicy.Evaluate(
                    Rules, false, false, 0, false,
                    present, false, known, tier));
        }

        [Theory]
        [InlineData(0, 2.0f, 4.5f, 0)]
        [InlineData(0, 2.6f, 4.5f, 1)]
        [InlineData(0, 2.0f, 6.1f, 1)]
        [InlineData(0, 3.5f, 4.5f, 2)]
        [InlineData(0, 2.0f, 8.6f, 2)]
        [InlineData(2, 2.0f, 4.5f, 2)]
        public void EffectiveSizeTierCannotBeUnderstatedByCatalogMetadata(
            int configured, float width, float length, int expected)
        {
            Assert.Equal(expected,
                GarageManager.ResolveEffectiveGarageSizeTier(
                    configured, width, length));
        }

        [Fact]
        public void MissingRulesFailClosed()
        {
            Assert.Equal(GarageEntryDenial.MissionActive,
                GarageEntryPolicy.Evaluate(
                    null, false, false, 0, false, false, false, false, 0));
        }

        [Fact]
        public void GarageVehiclesCommitWhenStorySaveStarts()
        {
            var observed = new System.DateTime(2026, 8, 14, 1, 0, 0,
                System.DateTimeKind.Utc);
            Assert.True(GarageStorySavePolicy.HasSaveEvent(
                true, false, observed, observed));
        }

        [Fact]
        public void GarageVehiclesCommitWhenStorySaveFileAdvances()
        {
            var observed = new System.DateTime(2026, 8, 14, 1, 0, 0,
                System.DateTimeKind.Utc);
            Assert.True(GarageStorySavePolicy.HasSaveEvent(
                false, false, observed.AddSeconds(1), observed));
        }

        [Fact]
        public void GarageVehiclesDoNotCommitDuringOrdinaryGameplay()
        {
            var observed = new System.DateTime(2026, 8, 14, 1, 0, 0,
                System.DateTimeKind.Utc);
            Assert.False(GarageStorySavePolicy.HasSaveEvent(
                false, false, observed, observed));
            Assert.False(GarageStorySavePolicy.HasSaveEvent(
                true, true, observed, observed));
        }

        [Fact]
        public void EnhancedInteriorFallbackAcceptsAStableResolvedInterior()
        {
            Assert.False(GarageInteriorReadinessPolicy.IsUsable(
                95234, false, false, false, 999, 1000));
            Assert.True(GarageInteriorReadinessPolicy.IsUsable(
                95234, false, false, false, 1000, 1000));
        }

        [Fact]
        public void OnlineInteriorFallbackStillRequiresItsIpl()
        {
            Assert.False(GarageInteriorReadinessPolicy.IsUsable(
                275457, true, false, false, 5000, 1500));
            Assert.True(GarageInteriorReadinessPolicy.IsUsable(
                275457, true, true, false, 1500, 1500));
        }

        [Fact]
        public void NativeReadySignalDoesNotNeedFallbackDelay()
        {
            Assert.True(GarageInteriorReadinessPolicy.IsUsable(
                275457, true, true, true, 0, 1500));
            Assert.False(GarageInteriorReadinessPolicy.IsUsable(
                0, true, true, true, 5000, 1500));
        }

        [Theory]
        [InlineData(1000, 1000, true)]
        [InlineData(999, 1000, false)]
        [InlineData(1200, 1000, true)]
        [InlineData(int.MinValue + 5, int.MaxValue - 5, true)]
        public void Periodic_garage_work_uses_wrap_safe_deadlines(
            int now, int scheduledAt, bool expected)
        {
            Assert.Equal(expected,
                GarageManager.PeriodicWorkDue(now, scheduledAt));
        }

        [Theory]
        [InlineData(0f, 0f, 0f, 0f, 0f, 0f, true)]
        [InlineData(250f, 0f, 0f, 0f, 0f, 0f, true)]
        [InlineData(250.01f, 0f, 0f, 0f, 0f, 0f, false)]
        [InlineData(0f, 0f, 251f, 0f, 0f, 0f, false)]
        public void Exterior_garage_handlers_sleep_outside_marker_range(
            float playerX, float playerY, float playerZ,
            float markerX, float markerY, float markerZ, bool expected)
        {
            Assert.Equal(expected, GarageManager.ShouldServiceExteriorMarker(
                new GTA.Math.Vector3(playerX, playerY, playerZ),
                new GTA.Math.Vector3(markerX, markerY, markerZ)));
        }
    }
}
