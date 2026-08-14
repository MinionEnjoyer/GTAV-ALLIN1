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
    }
}
