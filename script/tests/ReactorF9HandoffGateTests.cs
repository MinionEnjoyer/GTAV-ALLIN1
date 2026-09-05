using System;
using System.Threading;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class ReactorF9HandoffGateTests
    {
        [Fact]
        public void MissingNativeContractLeavesStandaloneAllin1Usable()
        {
            var processId = UniqueProcessId();
            using var gate = new ReactorF9HandoffGate(processId);

            Assert.True(gate.CanHandleF9());
        }

        [Fact]
        public void ExistingContractBlocksUntilNativeSignalsRelease()
        {
            var processId = UniqueProcessId();
            using var release = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var gate = new ReactorF9HandoffGate(processId);

            Assert.False(gate.CanHandleF9());
            release.Set();
            Assert.True(gate.CanHandleF9());
            Assert.True(gate.CanHandleF9());
        }

        [Fact]
        public void NativeF9OwnershipNeverBlocksControllerShortcut()
        {
            var processId = UniqueProcessId();
            using var release = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var gate = new ReactorF9HandoffGate(processId);

            Assert.True(gate.CanDispatch(isPhysicalF9: false));
            Assert.False(gate.CanDispatch(isPhysicalF9: true));
        }

        [Fact]
        public void NativeF9OwnershipNeverBlocksARemappedKeyboardShortcut()
        {
            var processId = UniqueProcessId();
            using var release = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var gate = new ReactorF9HandoffGate(processId);

            // GbayShop passes false for every configured key except the
            // physical F9 key, so remapping GBAY to F8 remains independent of
            // Reactor's native F9 ownership contract.
            Assert.True(gate.CanDispatch(isPhysicalF9: false));
            Assert.False(gate.CanDispatch(isPhysicalF9: true));
        }

        [Fact]
        public void NativeReleaseDoesNotReplayOpeningF9BeforeIntentResolution()
        {
            var processId = UniqueProcessId();
            long now = 10_000;
            using var release = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var gate = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);

            // Native has released the physical high bit, but a delayed SHVDN
            // KeyDown from that same opening press must not dispatch.
            Assert.False(gate.CanDispatch(isPhysicalF9: true));
            Assert.True(gate.TryBeginStartupIntentCheck());
            Assert.Equal(1,
                gate.CompleteStartupIntentCheck(consumedAndPresented: true));

            // The managed presentation latch now owns this generation.
            Assert.True(gate.CanDispatch(isPhysicalF9: true));
        }

        [Fact]
        public void MissingIntentEventuallyReleasesManagedF9Dispatch()
        {
            var processId = UniqueProcessId();
            long now = 20_000;
            using var release = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var gate = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);

            Assert.False(gate.CanDispatch(isPhysicalF9: true));
            Assert.True(gate.TryBeginStartupIntentCheck());
            Assert.Equal(0,
                gate.CompleteStartupIntentCheck(consumedAndPresented: false));

            now += 5_000;
            Assert.False(gate.TryBeginStartupIntentCheck());
            Assert.True(gate.CanDispatch(isPhysicalF9: true));
        }

        [Fact]
        public void OwnershipContractIsProcessSpecific()
        {
            var firstProcessId = UniqueProcessId();
            var secondProcessId = firstProcessId + 1;
            using var release = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(firstProcessId));
            using var first = new ReactorF9HandoffGate(firstProcessId);
            using var second = new ReactorF9HandoffGate(secondProcessId);

            Assert.False(first.CanHandleF9());
            Assert.True(second.CanHandleF9());
        }

        [Fact]
        public void StartupIntentCheckWaitsForHandoffAndCompletesOnSuccess()
        {
            var processId = UniqueProcessId();
            long now = 1_000;
            using var release = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var gate = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);

            Assert.False(gate.TryBeginStartupIntentCheck());
            Assert.False(gate.TryBeginStartupIntentCheck());
            release.Set();
            Assert.True(gate.TryBeginStartupIntentCheck());
            Assert.Equal(1,
                gate.CompleteStartupIntentCheck(consumedAndPresented: true));
            Assert.Equal(0,
                gate.CompleteStartupIntentCheck(consumedAndPresented: true));
            Assert.False(gate.TryBeginStartupIntentCheck());
            Assert.False(gate.TryBeginStartupIntentCheck());
        }

        [Fact]
        public void ReleaseBeforeIntentArmRetriesThenCompletesExactlyOnce()
        {
            var processId = UniqueProcessId();
            long now = 10_000;
            using var release = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var cancelled = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.StartupIntentCancelledEventName(
                    processId));
            using var gate = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);

            // Native has already released ownership, but the preloader UI
            // thread has not armed DefaultMenuIntent yet.
            Assert.True(gate.TryBeginStartupIntentCheck());
            gate.CompleteStartupIntentCheck(consumedAndPresented: false);

            now += 249;
            Assert.False(gate.TryBeginStartupIntentCheck());

            // The intent appears after the initial miss. The next throttled
            // bridge opportunity consumes/presents it exactly once.
            now += 1;
            Assert.True(gate.TryBeginStartupIntentCheck());
            Assert.Equal(1,
                gate.CompleteStartupIntentCheck(consumedAndPresented: true));
            now += 10_000;
            Assert.False(gate.TryBeginStartupIntentCheck());
        }

        [Fact]
        public void CancelledIntentBecomesTerminalOnlyAfterNativeRelease()
        {
            var processId = UniqueProcessId();
            long now = 15_000;
            using var release = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var cancelled = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.StartupIntentCancelledEventName(
                    processId));
            using var gate = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);

            Assert.False(gate.CanDispatch(isPhysicalF9: true));
            Assert.False(gate.TryBeginStartupIntentCheck());

            release.Set();
            Assert.True(gate.CanDispatch(isPhysicalF9: true));
            Assert.False(gate.TryBeginStartupIntentCheck());
        }

        [Fact]
        public void CancellationAfterInitialMissStopsRetryImmediately()
        {
            var processId = UniqueProcessId();
            long now = 17_000;
            using var release = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var cancelled = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.StartupIntentCancelledEventName(
                    processId));
            using var gate = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);

            Assert.True(gate.TryBeginStartupIntentCheck());
            Assert.Equal(0,
                gate.CompleteStartupIntentCheck(consumedAndPresented: false));

            cancelled.Set();
            now += 250;
            Assert.False(gate.TryBeginStartupIntentCheck());
            Assert.True(gate.CanDispatch(isPhysicalF9: true));
        }

        [Fact]
        public void MissingStartupIntentStopsPermanentlyAtRetryDeadline()
        {
            var processId = UniqueProcessId();
            long now = 20_000;
            using var release = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.OwnershipEventName(processId));
            using var gate = new ReactorF9HandoffGate(
                processId, () => now, 250, 5_000);

            Assert.True(gate.TryBeginStartupIntentCheck());
            gate.CompleteStartupIntentCheck(consumedAndPresented: false);
            now += 4_999;
            Assert.True(gate.TryBeginStartupIntentCheck());
            gate.CompleteStartupIntentCheck(consumedAndPresented: false);
            now += 1;
            Assert.False(gate.TryBeginStartupIntentCheck());
            now += 50_000;
            Assert.False(gate.TryBeginStartupIntentCheck());
        }

        [Fact]
        public void ActiveInitializerCanCloseBeforeOptionalMenuBridgeRegisters()
        {
            int processId = UniqueProcessId();
            using var active = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                ReactorF9HandoffGate.StartupIntentActiveEventName(processId));
            using var close = new EventWaitHandle(
                false,
                EventResetMode.AutoReset,
                ReactorF9HandoffGate.BootstrapCloseEventName(processId));
            using var gate = new ReactorF9HandoffGate(processId);

            Assert.True(gate.TryRequestStartupIntentClose(processId));
            Assert.True(close.WaitOne(0));
            active.Reset();
            Assert.False(gate.TryRequestStartupIntentClose(processId));
        }

        [Fact]
        public void InvalidProcessIdIsRejected()
        {
            Assert.Throws<ArgumentOutOfRangeException>(
                () => new ReactorF9HandoffGate(0));
        }

        private static int UniqueProcessId()
        {
            return 1_600_000_000 +
                (int)((uint)Guid.NewGuid().GetHashCode() % 100_000_000U);
        }
    }
}
