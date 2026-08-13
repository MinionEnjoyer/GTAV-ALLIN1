using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GarageEntryPolicyTests
    {
        private static readonly GarageEntryRules Rules = new GarageEntryRules(
            disableDuringMissions: true,
            blockStoryOwnedVehicles: true,
            maximumVehicleSizeTier: 1);

        [Fact]
        public void MissionDenialHasPriority()
        {
            Assert.Equal(GarageEntryDenial.MissionActive,
                GarageEntryPolicy.Evaluate(Rules, true, true, true, true, 2));
        }

        [Fact]
        public void StoryVehicleIsDeniedBeforeSize()
        {
            Assert.Equal(GarageEntryDenial.StoryOwnedVehicle,
                GarageEntryPolicy.Evaluate(Rules, false, true, true, true, 2));
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
                GarageEntryPolicy.Evaluate(Rules, false, present, false, known, tier));
        }

        [Fact]
        public void MissingRulesFailClosed()
        {
            Assert.Equal(GarageEntryDenial.MissionActive,
                GarageEntryPolicy.Evaluate(null, false, false, false, false, 0));
        }
    }
}
