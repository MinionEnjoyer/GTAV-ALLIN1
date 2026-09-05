using Xunit;

namespace ALLIN1.Tests
{
    public sealed class MapBackedDeliveryPolicyTests
    {
        [Theory]
        [InlineData(1)]
        [InlineData(3)]
        [InlineData(5)]
        [InlineData(7)]
        public void Custom_garages_and_yacht_require_the_registered_map_pack(
            int destination)
        {
            Assert.True(StandaloneMapPack.IsMapBackedDeliveryDestination(
                destination));
            Assert.False(StandaloneMapPack.IsDeliveryDestinationAvailable(
                destination, false));
            Assert.True(StandaloneMapPack.IsDeliveryDestinationAvailable(
                destination, true));
        }

        [Theory]
        [InlineData(2)]
        [InlineData(4)]
        public void Isolated_bridges_require_exact_phase_b_not_just_the_pack(
            int destination)
        {
            Assert.True(StandaloneMapPack.IsMapBackedDeliveryDestination(
                destination));
            Assert.False(StandaloneMapPack.IsDeliveryDestinationAvailable(
                destination, false));
            Assert.False(StandaloneMapPack.IsDeliveryDestinationAvailable(
                destination, true));
        }

        [Theory]
        [InlineData(0)]
        [InlineData(6)]
        [InlineData(8)]
        public void Base_world_destinations_remain_available_without_the_map_pack(
            int destination)
        {
            Assert.False(StandaloneMapPack.IsMapBackedDeliveryDestination(
                destination));
            Assert.True(StandaloneMapPack.IsDeliveryDestinationAvailable(
                destination, false));
        }

        [Fact]
        public void Missing_map_guidance_is_actionable_and_consistent()
        {
            Assert.Equal("Map content unavailable; run Install / Repair",
                StandaloneMapPack.DeliveryUnavailableStatusForLayout(
                    StandaloneMapPackLayout.Missing));
            Assert.Equal(
                "Map content temporarily disabled for startup stability",
                StandaloneMapPack.DeliveryUnavailableStatusForLayout(
                    StandaloneMapPackLayout.Unregistered));
            Assert.Equal(
                "Map content temporarily disabled for startup stability",
                StandaloneMapPack.DeliveryUnavailableStatusForLayout(
                    StandaloneMapPackLayout.Deferred));
            Assert.Equal(
                "Map content temporarily disabled for startup stability",
                StandaloneMapPack.DeliveryUnavailableStatusForLayout(
                    StandaloneMapPackLayout.StartupRegisteredIpl));
            Assert.Equal(
                "Map content temporarily disabled for startup stability",
                StandaloneMapPack.DeliveryUnavailableStatusForLayout(
                    StandaloneMapPackLayout.StartupRegisteredIpl, true));
            Assert.Equal("Map content unavailable; run Install / Repair",
                StandaloneMapPack.DeliveryUnavailableStatusForLayout(
                    StandaloneMapPackLayout.OfficialReferenceBridge));
        }

        [Theory]
        [InlineData(false, false, false)]
        [InlineData(true, false, false)]
        [InlineData(true, true, false)]
        [InlineData(false, true, true)]
        public void World_property_requires_unowned_state_and_map_content(
            bool alreadyOwned, bool mapPackInstalled, bool expected)
        {
            Assert.Equal(expected,
                StandaloneMapPack.IsWorldPropertyPurchaseAvailable(
                    alreadyOwned, mapPackInstalled));
        }
    }
}
