using Xunit;

namespace ALLIN1.Tests
{
    public class YachtHelipadPolicyTests
    {
        [Theory]
        [InlineData("swift2")]
        [InlineData("SWIFT2")]
        [InlineData("supervolito2")]
        public void Accepts_only_the_two_gta_online_yacht_helicopters(string model)
        {
            Assert.True(YachtHelipadPolicy.IsEligible(model));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("swift")]
        [InlineData("supervolito")]
        [InlineData("buzzard")]
        [InlineData("akula")]
        [InlineData("dinghy4")]
        public void Rejects_general_personal_aircraft_and_support_boats(string model)
        {
            Assert.False(YachtHelipadPolicy.IsEligible(model));
        }

        [Theory]
        [InlineData(true, false, false, false, true)]
        [InlineData(false, false, false, true, false)]
        [InlineData(false, true, false, false, false)]
        [InlineData(false, true, false, true, true)]
        [InlineData(false, true, true, false, true)]
        public void Helipad_tick_is_quiet_offsite_but_keeps_live_aircraft_serviced(
            bool liveHandle, bool worldReady, bool playerNearby,
            bool intervalElapsed, bool expected)
        {
            Assert.Equal(expected, GarageManager.ShouldServiceYachtHelipad(
                liveHandle, worldReady, playerNearby, intervalElapsed));
        }

        [Theory]
        [InlineData(false, 1000)]
        [InlineData(true, 5000)]
        public void Yacht_streaming_health_poll_relaxes_after_activation(
            bool streamed, int expected)
        {
            Assert.Equal(expected,
                YachtManager.GetStreamingPollInterval(streamed));
        }
    }
}
