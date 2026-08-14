using Xunit;

namespace ALLIN1.Tests
{
    public sealed class DlcMapLeaseRegistryTests
    {
        [Fact]
        public void FirstAcquireAndLastReleaseRequestNativeTransitions()
        {
            var registry = new DlcMapLeaseRegistry();

            Assert.True(registry.Acquire(GarageDefinitions.ThreeFloor));
            Assert.False(registry.Acquire(GarageDefinitions.ThreeFloor));
            Assert.False(registry.Acquire(GarageDefinitions.Davis));
            Assert.True(registry.IsAcquired(GarageDefinitions.ThreeFloor));
            Assert.True(registry.IsAcquired(GarageDefinitions.Davis));

            Assert.False(registry.Release(GarageDefinitions.ThreeFloor));
            Assert.True(registry.Release(GarageDefinitions.Davis));
            Assert.False(registry.Release(GarageDefinitions.Davis));
        }

        [Fact]
        public void StoryMapGarageDoesNotAcquireMultiplayerMap()
        {
            var registry = new DlcMapLeaseRegistry();
            Assert.False(registry.Acquire(GarageDefinitions.Eclipse));
            Assert.False(registry.IsAcquired(GarageDefinitions.Eclipse));
            Assert.False(registry.ReleaseAll());
        }

        [Fact]
        public void ReleaseAllOnlyRequestsRestoreWhenALeaseExists()
        {
            var registry = new DlcMapLeaseRegistry();
            Assert.True(registry.Acquire(GarageDefinitions.Davis));
            Assert.True(registry.ReleaseAll());
            Assert.False(registry.IsAcquired(GarageDefinitions.Davis));
            Assert.False(registry.ReleaseAll());
        }

        [Fact]
        public void CasinoGarageUsesTheMultiplayerMapLease()
        {
            var registry = new DlcMapLeaseRegistry();
            Assert.True(GarageDefinitions.Paleto.RequiresMultiplayerMap);
            Assert.True(registry.Acquire(GarageDefinitions.Paleto));
            Assert.True(registry.IsAcquired(GarageDefinitions.Paleto));
            Assert.True(registry.Release(GarageDefinitions.Paleto));
        }

        [Fact]
        public void WorldAssetLeaseSharesTheGlobalMapTransition()
        {
            var registry = new DlcMapLeaseRegistry();

            Assert.True(registry.Acquire("world_asset_super_yacht"));
            Assert.False(registry.Acquire(GarageDefinitions.Paleto));
            Assert.True(registry.IsAcquired("world_asset_super_yacht"));
            Assert.False(registry.Release("world_asset_super_yacht"));
            Assert.True(registry.Release(GarageDefinitions.Paleto));
        }

        [Theory]
        [InlineData(false, 899f, true)]
        [InlineData(false, 901f, false)]
        [InlineData(true, 1199f, true)]
        [InlineData(true, 1201f, false)]
        public void YachtStreamingUsesHysteresis(
            bool acquired, float distance, bool expected)
        {
            Assert.Equal(expected, YachtStreamingPolicy.ShouldAcquire(
                acquired, distance, 900f, 1200f));
        }
    }
}
