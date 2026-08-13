using ALLIN1;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class TrafficSpawnerPolicyTests
    {
        [Theory]
        [InlineData(0f, 20f)]
        [InlineData(0.5f, 20f)]
        [InlineData(8f, 12f)]
        [InlineData(18f, 18f)]
        [InlineData(45f, 30f)]
        public void Replacement_drivers_always_receive_a_useful_cruise_speed(
            float captured, float expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.GetTrafficCruiseSpeed(captured));
        }

        [Theory]
        [InlineData(true, true, true)]
        [InlineData(true, false, false)]
        [InlineData(false, false, true)]
        public void Moving_source_is_never_committed_without_its_driver(
            bool sourceHadDriver, bool driverTransferred, bool expected)
        {
            Assert.Equal(expected, TrafficSpawner.CanCommitReplacement(
                sourceHadDriver, driverTransferred));
        }

        [Theory]
        [InlineData(false, true, false, false, false, false, false, false, 1)]
        [InlineData(true, true, false, false, false, false, false, false, 2)]
        [InlineData(true, true, true, false, false, false, false, false, 2)]
        [InlineData(true, true, true, true, true, true, false, false, 1)]
        [InlineData(true, true, true, true, false, true, false, false, 2)]
        [InlineData(true, true, true, true, false, true, true, false, 0)]
        [InlineData(true, true, true, true, false, false, false, true, 1)]
        [InlineData(true, true, true, true, false, false, false, false, 0)]
        [InlineData(true, false, false, false, false, false, false, false, 0)]
        public void Managed_traffic_never_keeps_a_driverless_moving_vehicle(
            bool vehicleExists, bool requiresDriver, bool driverExists,
            bool driverInSeat, bool claimedByPlayer, bool purge,
            bool vehicleOnScreen, bool tooFar, int expected)
        {
            Assert.Equal((TrafficSpawner.ManagedTrafficAction)expected,
                TrafficSpawner.DecideManagedTrafficAction(
                    vehicleExists, requiresDriver, driverExists, driverInSeat,
                    claimedByPlayer, purge, vehicleOnScreen, tooFar));
        }

        [Theory]
        [InlineData("mission_active", true)]
        [InlineData("cutscene_active", true)]
        [InlineData("player_switch", true)]
        [InlineData("interior", true)]
        [InlineData("wanted_level", true)]
        [InlineData("player_unavailable", false)]
        [InlineData("", false)]
        public void Unsafe_gameplay_transitions_release_managed_traffic_pairs(
            string suppression, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.ShouldPurgeManagedTraffic(suppression));
        }
    }
}
