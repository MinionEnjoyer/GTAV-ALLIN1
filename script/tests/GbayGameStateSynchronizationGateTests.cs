using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GbayGameStateSynchronizationGateTests
    {
        [Fact]
        public void VisibleMenuSynchronizesImmediatelyThenAtBoundedIntervals()
        {
            var gate = new GbayGameStateSynchronizationGate(1000);

            Assert.True(gate.TryBegin(100, menuActive: true));
            gate.Complete(100, succeeded: true);
            Assert.False(gate.TryBegin(1099, menuActive: true));
            Assert.True(gate.TryBegin(1100, menuActive: true));
        }

        [Fact]
        public void ClosingMenuMakesNextPresentationSynchronizeImmediately()
        {
            var gate = new GbayGameStateSynchronizationGate(1000);
            Assert.True(gate.TryBegin(100, menuActive: true));
            gate.Complete(100, succeeded: true);

            Assert.False(gate.TryBegin(200, menuActive: false));
            Assert.True(gate.TryBegin(201, menuActive: true));
        }

        [Fact]
        public void FailedSynchronizationUsesBoundedShortRetry()
        {
            var gate = new GbayGameStateSynchronizationGate(1000);
            Assert.True(gate.TryBegin(100, menuActive: true));
            gate.Complete(100, succeeded: false);

            Assert.False(gate.TryBegin(599, menuActive: true));
            Assert.True(gate.TryBegin(600, menuActive: true));
        }
    }
}
