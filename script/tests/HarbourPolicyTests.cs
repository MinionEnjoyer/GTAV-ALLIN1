using Xunit;

namespace ALLIN1.Tests
{
    public sealed class HarbourPolicyTests
    {
        [Theory]
        [InlineData("longfin")]
        [InlineData("DINGHY5")]
        [InlineData("patrolboat")]
        [InlineData("tug")]
        public void Accepts_boats_from_the_vehicle_catalog(string model)
        {
            Assert.True(HarbourPolicy.IsEligible(model));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("tailgater")]
        [InlineData("swift2")]
        [InlineData("raiju")]
        public void Rejects_non_boats(string model)
        {
            Assert.False(HarbourPolicy.IsEligible(model));
        }
    }
}
