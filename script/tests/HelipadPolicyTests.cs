using Xunit;

namespace ALLIN1.Tests
{
    public sealed class HelipadPolicyTests
    {
        [Theory]
        [InlineData("conada")]
        [InlineData("MAVERICK2")]
        [InlineData("akula")]
        [InlineData("cargobob5")]
        [InlineData("conada2")]
        [InlineData("swift")]
        [InlineData("seasparrow2")]
        public void Accepts_helicopters_from_the_vehicle_catalog(string model)
        {
            Assert.True(HelipadPolicy.IsEligible(model));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("tailgater")]
        [InlineData("raiju")]
        [InlineData("oppressor2")]
        [InlineData("not_a_listed_helicopter")]
        public void Rejects_non_helicopters_and_unlisted_models(string model)
        {
            Assert.False(HelipadPolicy.IsEligible(model));
        }
    }
}
