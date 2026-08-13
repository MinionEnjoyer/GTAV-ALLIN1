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
    }
}
