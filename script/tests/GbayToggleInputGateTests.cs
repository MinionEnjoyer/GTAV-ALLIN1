using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GbayToggleInputGateTests
    {
        [Fact]
        public void RepeatingKeyDownProducesOneToggleUntilRelease()
        {
            var gate = new GbayToggleInputGate();

            Assert.True(gate.TryPress(1000));
            for (var index = 0; index < 20; index++)
                Assert.False(gate.TryPress(1001 + index * 200));

            gate.Release();
            Assert.True(gate.TryPress(6000));
        }

        [Fact]
        public void NoisyReleaseAndRepressRemainsDebounced()
        {
            var gate = new GbayToggleInputGate();

            Assert.True(gate.TryPress(1000));
            gate.Release();
            Assert.False(gate.TryPress(1100));
            gate.Release();
            Assert.True(gate.TryPress(1300));
        }

        [Fact]
        public void PhysicalKeyUpRepairsAMissedKeyUpEvent()
        {
            var gate = new GbayToggleInputGate();

            Assert.True(gate.TryPress(1000));
            gate.ObservePhysicalState(1010, stateAvailable: true,
                isPhysicallyDown: true);
            Assert.False(gate.TryPress(1200));

            gate.ObservePhysicalState(1400, stateAvailable: true,
                isPhysicallyDown: false);
            Assert.True(gate.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void PhysicalRisingEdgeDispatchesExactlyOnce()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1100, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(gate.ObservePhysicalState(
                1200, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(gate.TryPress(1210));
        }

        [Fact]
        public void DelayedManagedKeyDownAfterPhysicalReleaseIsIgnored()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1100, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(gate.ObservePhysicalState(
                1200, stateAvailable: true, isPhysicallyDown: false));

            // SHVDN delivered a copy of the already-completed physical press.
            Assert.False(gate.TryPress(1350));

            // A genuinely new physical press still owns the next edge.
            Assert.True(gate.ObservePhysicalState(
                1500, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void ManagedOnlyInputWorksBeforePhysicalStateIsAvailable()
        {
            var gate = new GbayToggleInputGate();

            Assert.True(gate.TryPress(1000));
            Assert.False(gate.TryPress(1100));
            gate.ObserveManagedRelease(1200);
            Assert.True(gate.TryPress(1400));
        }

        [Fact]
        public void ManagedAndPhysicalInterleavingProducesOneLogicalEdge()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));

            // KeyDown arrives just before the polling tick. Because a usable
            // physical source is known, it waits for that source to dispatch.
            Assert.False(gate.TryPress(1100));
            Assert.True(gate.ObservePhysicalState(
                1110, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(gate.TryPress(1120));
            Assert.False(gate.ObservePhysicalState(
                1130, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void WatchdogRepairsMissedKeyUpWhenPhysicalQueryIsUnavailable()
        {
            var gate = new GbayToggleInputGate(
                debounceMilliseconds: 300,
                watchdogMilliseconds: 1000);

            Assert.True(gate.TryPress(1000));
            gate.ObservePhysicalState(1999, stateAvailable: false,
                isPhysicallyDown: false);
            Assert.False(gate.TryPress(1999));

            gate.ObservePhysicalState(2999, stateAvailable: false,
                isPhysicallyDown: false);
            Assert.True(gate.TryPress(2999));
        }

        [Fact]
        public void RepeatedKeyDownExtendsFallbackWatchdogLatch()
        {
            var gate = new GbayToggleInputGate(
                debounceMilliseconds: 300,
                watchdogMilliseconds: 1000);

            Assert.True(gate.TryPress(1000));
            Assert.False(gate.TryPress(1800));
            gate.ObservePhysicalState(2500, stateAvailable: false,
                isPhysicallyDown: false);
            Assert.False(gate.TryPress(2500));

            gate.ObservePhysicalState(3500, stateAvailable: false,
                isPhysicallyDown: false);
            Assert.True(gate.TryPress(3500));
        }

        [Fact]
        public void PhysicalHoldNeverExpiresThroughFallbackTimeout()
        {
            var gate = new GbayToggleInputGate(
                debounceMilliseconds: 300,
                watchdogMilliseconds: 1000);

            Assert.True(gate.TryPress(1000));
            gate.ObservePhysicalState(10000, stateAvailable: true,
                isPhysicallyDown: true);

            Assert.False(gate.TryPress(10001));
        }

        [Fact]
        public void PhysicalRisingEdgeRepairsAMissedManagedKeyDown()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void PhysicalHoldProducesOnlyOneFallbackPress()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(gate.ObservePhysicalState(
                2000, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(gate.ObservePhysicalState(
                5000, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void ManagedKeyDownAndPhysicalPollDeduplicateEitherOrdering()
        {
            var managedFirst = new GbayToggleInputGate();

            Assert.True(managedFirst.TryPress(1000));
            Assert.False(managedFirst.ObservePhysicalState(
                1010, stateAvailable: true, isPhysicallyDown: true));

            var physicalFirst = new GbayToggleInputGate();
            Assert.False(physicalFirst.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(physicalFirst.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(physicalFirst.TryPress(1410));
        }

        [Fact]
        public void PhysicalReleaseAllowsTheNextPressToReopen()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
            Assert.False(gate.ObservePhysicalState(
                1500, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1800, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void ManagedKeyUpCannotUnlockAStillHeldPhysicalKey()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                900, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: true));

            // A noisy/out-of-order SHVDN KeyUp cannot create a second edge
            // while the Windows high bit still proves the key is held.
            gate.ObserveManagedRelease(1100);
            Assert.False(gate.TryPress(1400));
            Assert.False(gate.ObservePhysicalState(
                1500, stateAvailable: true, isPhysicallyDown: true));

            Assert.False(gate.ObservePhysicalState(
                1600, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1900, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void StartupHandoffConsumesOpeningEdgeUntilVisibleAndSettled()
        {
            var gate = new GbayToggleInputGate(
                debounceMilliseconds: 100,
                watchdogMilliseconds: 1000,
                handoffSettleMilliseconds: 350,
                handoffVisibilityTimeoutMilliseconds: 5000);

            // Native already observed the opening F9 release before the
            // managed provider accepted its queued presentation.
            Assert.False(gate.ObservePhysicalState(
                900, stateAvailable: true, isPhysicallyDown: false));
            gate.ClaimStartupHandoff(1000, handoffGeneration: 7);

            Assert.True(gate.StartupHandoffActive);
            Assert.Equal(7, gate.StartupHandoffGeneration);
            Assert.False(gate.TryPress(1050));
            Assert.True(gate.ConsumeHandoffSuppression());
            gate.ObserveManagedRelease(1060);

            Assert.Equal(
                GbayToggleHandoffTransition.PresentationObserved,
                gate.ObserveStartupPresentation(
                    1100, isPresentationActive: true));
            Assert.Equal(
                GbayToggleHandoffTransition.None,
                gate.ObserveStartupPresentation(
                    1449, isPresentationActive: true));
            Assert.True(gate.StartupHandoffActive);
            Assert.Equal(
                GbayToggleHandoffTransition.Settled,
                gate.ObserveStartupPresentation(
                    1450, isPresentationActive: true));
            Assert.False(gate.StartupHandoffActive);

            // A later, distinct press remains a normal close/open request.
            Assert.True(gate.ObservePhysicalState(
                1600, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void HeldOpeningF9CannotCrossStartupHandoff()
        {
            var gate = new GbayToggleInputGate(
                debounceMilliseconds: 100,
                watchdogMilliseconds: 1000,
                handoffSettleMilliseconds: 200,
                handoffVisibilityTimeoutMilliseconds: 1000);

            Assert.True(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: true));
            gate.ClaimStartupHandoff(1010, handoffGeneration: 3);
            Assert.Equal(
                GbayToggleHandoffTransition.PresentationObserved,
                gate.ObserveStartupPresentation(
                    1020, isPresentationActive: true));

            // Neither a managed repeat nor expiry of the visibility timeout
            // can release a key that is still physically held.
            Assert.False(gate.TryPress(1300));
            Assert.False(gate.ObservePhysicalState(
                2500, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayToggleHandoffTransition.None,
                gate.ObserveStartupPresentation(
                    2500, isPresentationActive: true));
            Assert.True(gate.StartupHandoffActive);

            gate.ObserveManagedRelease(2510);
            Assert.True(gate.StartupHandoffActive);
            Assert.False(gate.ObservePhysicalState(
                2520, stateAvailable: true, isPhysicallyDown: false));
            Assert.Equal(
                GbayToggleHandoffTransition.Settled,
                gate.ObserveStartupPresentation(
                    2520, isPresentationActive: true));

            Assert.True(gate.ObservePhysicalState(
                2700, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void FailedPresentationReleasesOnlyAfterReleaseAndTimeout()
        {
            var gate = new GbayToggleInputGate(
                debounceMilliseconds: 100,
                watchdogMilliseconds: 1000,
                handoffSettleMilliseconds: 200,
                handoffVisibilityTimeoutMilliseconds: 500);

            Assert.False(gate.ObservePhysicalState(
                900, stateAvailable: true, isPhysicallyDown: false));
            gate.ClaimStartupHandoff(1000, handoffGeneration: 9);
            Assert.Equal(
                GbayToggleHandoffTransition.None,
                gate.ObserveStartupPresentation(
                    1499, isPresentationActive: false));
            Assert.Equal(
                GbayToggleHandoffTransition.TimedOut,
                gate.ObserveStartupPresentation(
                    1500, isPresentationActive: false));

            Assert.True(gate.ObservePhysicalState(
                1700, stateAvailable: true, isPhysicallyDown: true));
        }

        [Fact]
        public void StartupPresentationMustBeReadyBeforeFirstF9Close()
        {
            var gate = new GbayToggleInputGate(
                debounceMilliseconds: 100,
                watchdogMilliseconds: 1000,
                handoffSettleMilliseconds: 100,
                handoffVisibilityTimeoutMilliseconds: 1000);

            Assert.False(gate.ObservePhysicalState(
                900, stateAvailable: true, isPhysicallyDown: false));
            gate.ClaimStartupHandoff(1000, handoffGeneration: 11);

            Assert.Equal(
                GbayMenuToggleDecision.OpeningNotReady,
                gate.BeginMenuToggle(
                    isMenuActive: true,
                    isMenuReady: false));
            Assert.Equal(
                GbayToggleHandoffTransition.PresentationObserved,
                gate.ObserveStartupPresentation(
                    1100, isPresentationActive: true));
            Assert.Equal(
                GbayToggleHandoffTransition.Settled,
                gate.ObserveStartupPresentation(
                    1200, isPresentationActive: true));

            Assert.True(gate.ObservePhysicalState(
                1300, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayMenuToggleDecision.Close,
                gate.BeginMenuToggle(
                    isMenuActive: true,
                    isMenuReady: true));
        }

        [Fact]
        public void AcceptedCloseMustReachHiddenBeforeF9CanReopen()
        {
            var gate = new GbayToggleInputGate();

            GbayMenuToggleDecision close = gate.BeginMenuToggle(
                isMenuActive: true,
                isMenuReady: true);
            Assert.Equal(GbayMenuToggleDecision.Close, close);
            gate.CompleteMenuToggle(close, accepted: true);

            Assert.Equal(
                GbayMenuToggleDecision.DismissalPending,
                gate.BeginMenuToggle(
                    isMenuActive: true,
                    isMenuReady: true));

            gate.ObserveMenuLifecycle(isMenuActive: false);
            Assert.Equal(
                GbayMenuToggleDecision.Open,
                gate.BeginMenuToggle(
                    isMenuActive: false,
                    isMenuReady: false));
        }

        [Fact]
        public void PressBeforePresentationReadyIsConsumedThenLaterPressCloses()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayMenuToggleDecision.Open,
                gate.BeginMenuToggle(
                    isMenuActive: false,
                    isMenuReady: false));
            Assert.False(gate.ObservePhysicalState(
                1500, stateAvailable: true, isPhysicallyDown: false));

            Assert.True(gate.ObservePhysicalState(
                1800, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayMenuToggleDecision.OpeningNotReady,
                gate.BeginMenuToggle(
                    isMenuActive: true,
                    isMenuReady: false));
            Assert.False(gate.ObservePhysicalState(
                1900, stateAvailable: true, isPhysicallyDown: false));

            Assert.True(gate.ObservePhysicalState(
                2200, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayMenuToggleDecision.Close,
                gate.BeginMenuToggle(
                    isMenuActive: true,
                    isMenuReady: true));
        }

        [Fact]
        public void ClickCloseAllowsNextReleasedPhysicalPressToReopen()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayMenuToggleDecision.Open,
                gate.BeginMenuToggle(
                    isMenuActive: false,
                    isMenuReady: false));
            Assert.False(gate.ObservePhysicalState(
                1500, stateAvailable: true, isPhysicallyDown: false));

            // The menu's close button hides Reactor without a keyboard edge.
            gate.ObserveMenuLifecycle(isMenuActive: true);
            gate.ObserveMenuLifecycle(isMenuActive: false);

            Assert.True(gate.ObservePhysicalState(
                1800, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayMenuToggleDecision.Open,
                gate.BeginMenuToggle(
                    isMenuActive: false,
                    isMenuReady: false));
        }

        [Fact]
        public void RepeatedKeySignalsCannotBypassLifecycleSerialization()
        {
            var gate = new GbayToggleInputGate();

            Assert.False(gate.ObservePhysicalState(
                1000, stateAvailable: true, isPhysicallyDown: false));
            Assert.True(gate.ObservePhysicalState(
                1400, stateAvailable: true, isPhysicallyDown: true));
            Assert.Equal(
                GbayMenuToggleDecision.Open,
                gate.BeginMenuToggle(
                    isMenuActive: false,
                    isMenuReady: false));

            for (var index = 0; index < 10; index++)
            {
                Assert.False(gate.TryPress(1410 + index));
                Assert.False(gate.ObservePhysicalState(
                    1420 + index,
                    stateAvailable: true,
                    isPhysicallyDown: true));
            }
        }

        [Fact]
        public void InvalidStartupHandoffGenerationIsRejected()
        {
            var gate = new GbayToggleInputGate();

            Assert.Throws<System.ArgumentOutOfRangeException>(
                () => gate.ClaimStartupHandoff(1000, 0));
        }
    }
}
