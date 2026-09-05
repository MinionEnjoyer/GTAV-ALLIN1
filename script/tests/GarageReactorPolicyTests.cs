using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GarageReactorPolicyTests
    {
        [Theory]
        [InlineData("vespucci-helipad")]
        [InlineData("VESPUCCI-HELIPAD")]
        [InlineData("harbour")]
        public void Specialized_list_locations_are_retrieval_only(
            string locationId)
        {
            Assert.True(
                GarageReactorPolicy.IsRetrievalOnlyLocation(locationId));
        }

        [Theory]
        [InlineData("eclipse")]
        [InlineData("davis")]
        [InlineData("yacht-helipad")]
        [InlineData("")]
        public void Other_locations_are_not_retrieval_only(string locationId)
        {
            Assert.False(
                GarageReactorPolicy.IsRetrievalOnlyLocation(locationId));
        }

        [Fact]
        public void Retrieval_flag_supersedes_sale_on_detached_listing()
        {
            var listing = new Allin1GarageVehicleListing
            {
                Sellable = true,
                Retrievable = true,
            };

            Assert.True(listing.Retrievable);
            Assert.False(listing.Sellable);
        }

        [Theory]
        [InlineData("davis", "customizable")]
        [InlineData("eclipse", "fixed")]
        [InlineData("harmony", "fixed")]
        [InlineData("vespucci-helipad", "specialized")]
        [InlineData("harbour", "specialized")]
        public void Interior_modes_are_explicit(
            string locationId, string expected)
        {
            Assert.Equal(expected,
                GarageReactorPolicy.InteriorMode(locationId));
            Assert.False(string.IsNullOrWhiteSpace(
                GarageReactorPolicy.InteriorStatus(locationId)));
        }
    }
}
