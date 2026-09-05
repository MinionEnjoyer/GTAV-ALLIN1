using Xunit;

namespace ALLIN1.Tests
{
    public sealed class OfficialMapContentPolicyTests
    {
        [Theory]
        [InlineData(0)]
        [InlineData(1)]
        [InlineData(3)]
        [InlineData(5)]
        [InlineData(6)]
        [InlineData(7)]
        public void Every_official_destination_is_available_with_verified_bridge(
            int index)
        {
            Assert.True(
                OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                    index, true));
        }

        [Fact]
        public void Isolated_bridges_remain_unavailable_until_phase_b_is_verified()
        {
            Assert.False(
                OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                    2, true));
            Assert.False(DavisStockReferenceBridgePolicy
                .IsCurrentRuntimeActivationAuthorized);
            Assert.False(
                OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                    4, true));
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsCurrentRuntimeActivationAuthorized);
        }

        [Theory]
        [InlineData(0, true)]
        [InlineData(1, false)]
        [InlineData(2, false)]
        [InlineData(3, false)]
        [InlineData(4, false)]
        [InlineData(5, false)]
        [InlineData(6, true)]
        [InlineData(7, false)]
        public void Only_base_world_destinations_survive_missing_bridge(
            int index, bool expected)
        {
            Assert.Equal(expected,
                OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                    index, false));
        }

        [Theory]
        [InlineData(-1)]
        [InlineData(8)]
        public void Unknown_destination_fails_closed(int index)
        {
            Assert.False(
                OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                    index, true));
        }

        [Fact]
        public void World_property_requires_verified_bridge_and_unowned_state()
        {
            Assert.True(
                OfficialMapContentPolicy.IsWorldPropertyPurchaseAvailable(
                    false, true));
            Assert.False(
                OfficialMapContentPolicy.IsWorldPropertyPurchaseAvailable(
                    true, true));
            Assert.False(
                OfficialMapContentPolicy.IsWorldPropertyPurchaseAvailable(
                    false, false));
        }
    }
}
