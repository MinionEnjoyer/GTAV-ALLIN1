using Xunit;

namespace ALLIN1.Tests
{
    public sealed class YachtMapResidencyTests
    {
        [Fact]
        public void No_generic_official_map_group_is_session_resident()
        {
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.Yacht));
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.Grapeseed));
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.Davis));
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.Harmony));
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.Paleto));
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.GarmentFactory));
        }
    }
}
