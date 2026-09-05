using System;
using System.Threading;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class PostHandoffF9OwnershipTests
    {
        [Fact]
        public void SettledPhysicalEdgesHaveOneOwnerAndAlternateCloseReopen()
        {
            int processId = UniqueProcessId();
            long now = 10_000;
            using var nativeOwnershipReleased = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var handoff = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);
            var input = new GbayToggleInputGate(
                debounceMilliseconds: 100,
                watchdogMilliseconds: 1_000,
                handoffSettleMilliseconds: 100,
                handoffVisibilityTimeoutMilliseconds: 1_000);

            // Native owns the opening edge, while the managed physical poll
            // establishes an authoritative released baseline without dispatch.
            Assert.False(input.ObservePhysicalState(
                now, stateAvailable: true, isPhysicallyDown: false));
            Assert.False(handoff.CanDispatch(isPhysicalF9: true));

            // Native releases ownership only after forwarding one typed menu
            // intent. ALLIN1 claims that exact generation through first paint.
            nativeOwnershipReleased.Set();
            Assert.True(handoff.TryBeginStartupIntentCheck());
            long generation = handoff.CompleteStartupIntentCheck(
                consumedAndPresented: true);
            Assert.Equal(1, generation);
            input.ClaimStartupHandoff(now, generation);
            Assert.Equal(
                GbayToggleHandoffTransition.PresentationObserved,
                input.ObserveStartupPresentation(
                    now, isPresentationActive: true));
            now += 100;
            Assert.Equal(
                GbayToggleHandoffTransition.Settled,
                input.ObserveStartupPresentation(
                    now, isPresentationActive: true));
            Assert.True(handoff.CanDispatch(isPhysicalF9: true));

            bool menuActive = true;
            bool menuReady = true;
            var expected = new[]
            {
                GbayMenuToggleDecision.Close,
                GbayMenuToggleDecision.Open,
                GbayMenuToggleDecision.Close,
                GbayMenuToggleDecision.Open,
            };

            foreach (var expectedDecision in expected)
            {
                now += 400;
                Assert.True(input.ObservePhysicalState(
                    now, stateAvailable: true, isPhysicallyDown: true));
                Assert.True(handoff.CanDispatch(isPhysicalF9: true));

                // A delayed SHVDN copy is not a second dispatcher once the
                // physical source owns the edge.
                Assert.False(input.TryPress(now + 1));

                var decision = input.BeginMenuToggle(menuActive, menuReady);
                Assert.Equal(expectedDecision, decision);
                input.CompleteMenuToggle(decision, accepted: true);

                if (decision == GbayMenuToggleDecision.Close)
                {
                    input.ObserveMenuLifecycle(isMenuActive: false);
                    menuActive = false;
                    menuReady = false;
                }
                else
                {
                    input.ObserveMenuLifecycle(isMenuActive: true);
                    menuActive = true;
                    menuReady = true;
                }

                Assert.False(input.ObservePhysicalState(
                    now + 10, stateAvailable: true, isPhysicallyDown: false));
            }
        }

        private static int UniqueProcessId()
        {
            return 1_500_000_000 +
                (int)((uint)Guid.NewGuid().GetHashCode() % 100_000_000U);
        }
    }
}
