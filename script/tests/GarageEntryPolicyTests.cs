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
                    Rules, true, 5, false, true, true, true, 2));
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
                    Rules, false, wantedLevel, alwaysAccessible,
                    false, false, false, 0));
        }

        [Fact]
        public void StoryVehicleIsDeniedBeforeSize()
        {
            Assert.Equal(GarageEntryDenial.StoryOwnedVehicle,
                GarageEntryPolicy.Evaluate(
                    Rules, false, 0, false, true, true, true, 2));
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
                    Rules, false, 0, false,
                    present, false, known, tier));
        }

        [Fact]
        public void MissingRulesFailClosed()
        {
            Assert.Equal(GarageEntryDenial.MissionActive,
                GarageEntryPolicy.Evaluate(
                    null, false, 0, false, false, false, false, 0));
        }
    }
}
