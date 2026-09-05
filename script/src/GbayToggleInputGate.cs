using System;

namespace ALLIN1
{
    internal enum GbayToggleHandoffTransition
    {
        None,
        PresentationObserved,
        Settled,
        TimedOut,
    }

    internal enum GbayMenuToggleDecision
    {
        Open,
        Close,
        OpeningNotReady,
        DismissalPending,
    }

    /// <summary>
    /// Converts SHVDN KeyDown and the physical-key fallback into one logical
    /// menu edge. The physical high bit is authoritative once available, so a
    /// noisy managed KeyUp cannot release a key that is still physically held.
    ///
    /// A native startup F9 is claimed as its own generation when it is
    /// converted into the first GBAY presentation. That generation remains
    /// consumed until the key has been released and the new presentation has
    /// been active for a short settle interval. This prevents the opening key
    /// from crossing the native-to-managed handoff and closing the surface it
    /// just requested.
    /// </summary>
    internal sealed class GbayToggleInputGate
    {
        internal const int DefaultDebounceMilliseconds = 300;
        internal const int DefaultWatchdogMilliseconds = 1500;
        internal const int DefaultHandoffSettleMilliseconds = 350;
        internal const int DefaultHandoffVisibilityTimeoutMilliseconds = 5000;

        private readonly int _debounceMilliseconds;
        private readonly int _watchdogMilliseconds;
        private readonly int _handoffSettleMilliseconds;
        private readonly int _handoffVisibilityTimeoutMilliseconds;
        private bool _pressLatched;
        private bool _managedDown;
        private long _nextAllowedAt;
        private long _lastDownSignalAt;
        private bool _physicalStateObserved;
        private bool _physicalDown;
        private bool _handoffBarrierActive;
        private bool _handoffReleaseObserved;
        private bool _handoffPresentationObserved;
        private long _handoffReadyAt;
        private long _handoffDeadline;
        private long _handoffGeneration;
        private bool _handoffSuppressionPending;
        private bool _menuDismissalPending;

        internal GbayToggleInputGate(
            int debounceMilliseconds = DefaultDebounceMilliseconds,
            int watchdogMilliseconds = DefaultWatchdogMilliseconds,
            int handoffSettleMilliseconds = DefaultHandoffSettleMilliseconds,
            int handoffVisibilityTimeoutMilliseconds =
                DefaultHandoffVisibilityTimeoutMilliseconds)
        {
            _debounceMilliseconds = debounceMilliseconds < 0
                ? 0
                : debounceMilliseconds;
            _watchdogMilliseconds = watchdogMilliseconds < 1
                ? 1
                : watchdogMilliseconds;
            _handoffSettleMilliseconds = handoffSettleMilliseconds < 0
                ? 0
                : handoffSettleMilliseconds;
            _handoffVisibilityTimeoutMilliseconds =
                handoffVisibilityTimeoutMilliseconds < 1
                    ? 1
                    : handoffVisibilityTimeoutMilliseconds;
        }

        internal bool StartupHandoffActive => _handoffBarrierActive;
        internal long StartupHandoffGeneration => _handoffGeneration;

        internal bool ConsumeHandoffSuppression()
        {
            bool pending = _handoffSuppressionPending;
            _handoffSuppressionPending = false;
            return pending;
        }

        /// <summary>
        /// Serializes opposite menu transitions independently from the key
        /// latch. Reactor reports a presentation as logically active as soon
        /// as it accepts an open request, but it is not safe to dismiss that
        /// generation until the browser has acknowledged its first ready
        /// frame. Likewise, an accepted dismiss must reach hidden before a
        /// later press can start a replacement generation.
        /// </summary>
        internal GbayMenuToggleDecision BeginMenuToggle(
            bool isMenuActive,
            bool isMenuReady)
        {
            ObserveMenuLifecycle(isMenuActive);
            if (!isMenuActive)
                return GbayMenuToggleDecision.Open;
            if (_menuDismissalPending)
                return GbayMenuToggleDecision.DismissalPending;
            if (!isMenuReady)
                return GbayMenuToggleDecision.OpeningNotReady;

            _menuDismissalPending = true;
            return GbayMenuToggleDecision.Close;
        }

        /// <summary>
        /// Releases a failed close immediately. Successful closes remain
        /// serialized until the bridge observes the logical presentation as
        /// hidden, including when the actual close came from an in-menu click.
        /// </summary>
        internal void CompleteMenuToggle(
            GbayMenuToggleDecision decision,
            bool accepted)
        {
            if (decision == GbayMenuToggleDecision.Close && !accepted)
                _menuDismissalPending = false;
        }

        internal void ObserveMenuLifecycle(bool isMenuActive)
        {
            if (!isMenuActive)
                _menuDismissalPending = false;
        }

        /// <summary>
        /// Records a managed KeyDown. Managed input is the fallback until the
        /// Windows physical-key query has produced a usable sample. After
        /// that point the physical high-bit transition owns every logical
        /// edge; a delayed SHVDN KeyDown may update managed state, but cannot
        /// reopen or close the menu a second time.
        /// </summary>
        internal bool TryPress(long nowMilliseconds)
        {
            _lastDownSignalAt = nowMilliseconds;
            TryCompleteHandoff(nowMilliseconds);
            bool repeatedManagedDown = _managedDown;
            _managedDown = true;
            if (repeatedManagedDown)
                return false;

            // SHVDN can deliver KeyDown after the physical polling path has
            // already observed both the press and its release. Once physical
            // state is available, dispatch only from ObservePhysicalState so
            // those delayed copies cannot become a second logical F9 edge.
            // Before the first usable physical sample, keep the managed-only
            // fallback for hosts where GetAsyncKeyState is unavailable.
            if (_physicalStateObserved)
            {
                // Preserve handoff diagnostics even though this managed copy
                // is no longer allowed to participate in edge arbitration.
                if (_handoffBarrierActive)
                    _handoffSuppressionPending = true;
                return false;
            }

            return TryLatchPress(nowMilliseconds, physicalSource: false);
        }

        internal bool ObservePhysicalState(
            long nowMilliseconds,
            bool stateAvailable,
            bool isPhysicallyDown)
        {
            if (stateAvailable)
            {
                bool risingEdge = isPhysicallyDown &&
                    (!_physicalStateObserved || !_physicalDown);
                _physicalStateObserved = true;
                _physicalDown = isPhysicallyDown;

                if (!isPhysicallyDown)
                {
                    // The physical high bit is authoritative. It repairs a
                    // missed managed KeyUp and releases a claimed startup F9.
                    _managedDown = false;
                    if (_handoffBarrierActive)
                        _handoffReleaseObserved = true;
                    ReleaseLatch();
                    return false;
                }

                _lastDownSignalAt = nowMilliseconds;
                if (!risingEdge)
                    return false;
                return TryLatchPress(nowMilliseconds, physicalSource: true);
            }

            if (!_pressLatched && !_handoffBarrierActive)
                return false;

            // GetAsyncKeyState should be available on supported Windows
            // hosts. If it is not, recover only after both KeyUp and repeated
            // KeyDown have been absent for a bounded interval.
            if (ElapsedAtLeast(
                    nowMilliseconds,
                    _lastDownSignalAt,
                    _watchdogMilliseconds))
            {
                _managedDown = false;
                if (_handoffBarrierActive)
                    _handoffReleaseObserved = true;
                ReleaseLatch();
            }
            return false;
        }

        /// <summary>
        /// Records SHVDN KeyUp without trusting it over a physical high bit.
        /// This closes the race where KeyUp releases the logical latch while
        /// GetAsyncKeyState still proves that the same key is held.
        /// </summary>
        internal void ObserveManagedRelease(long nowMilliseconds)
        {
            _managedDown = false;
            if (_physicalStateObserved && _physicalDown)
                return;

            if (_handoffBarrierActive)
                _handoffReleaseObserved = true;
            ReleaseLatch();
        }

        // Compatibility helper for focused policy tests and non-Windows
        // callers that have no physical-state source.
        internal void Release()
        {
            ObserveManagedRelease(0);
        }

        /// <summary>
        /// Claims the native startup edge after it has been atomically
        /// consumed and queued as GBAY. The claim is tied to the handoff
        /// generation allocated by ReactorF9HandoffGate.
        /// </summary>
        internal void ClaimStartupHandoff(
            long nowMilliseconds,
            long handoffGeneration)
        {
            if (handoffGeneration <= 0)
                throw new ArgumentOutOfRangeException(nameof(handoffGeneration));

            _handoffBarrierActive = true;
            _handoffGeneration = handoffGeneration;
            _handoffSuppressionPending = false;
            _handoffPresentationObserved = false;
            _handoffReleaseObserved = _physicalStateObserved
                ? !_physicalDown
                : !_managedDown;
            _handoffReadyAt = long.MaxValue;
            _handoffDeadline = SaturatingAdd(
                nowMilliseconds,
                _handoffVisibilityTimeoutMilliseconds);

            // Consume the opening edge even when managed input never saw it.
            _pressLatched = true;
            _lastDownSignalAt = nowMilliseconds;
            long debouncedUntil = SaturatingAdd(
                nowMilliseconds, _debounceMilliseconds);
            if (_nextAllowedAt < debouncedUntil)
                _nextAllowedAt = debouncedUntil;
        }

        /// <summary>
        /// Observes the first active GBAY surface and releases the startup
        /// claim only after both physical release and a paint-settle barrier.
        /// A bounded timeout prevents a failed presentation host from owning
        /// F9 forever, but a still-held key is never allowed through.
        /// </summary>
        internal GbayToggleHandoffTransition ObserveStartupPresentation(
            long nowMilliseconds,
            bool isPresentationActive)
        {
            if (!_handoffBarrierActive)
                return GbayToggleHandoffTransition.None;

            if (isPresentationActive && !_handoffPresentationObserved)
            {
                _handoffPresentationObserved = true;
                _handoffReadyAt = SaturatingAdd(
                    nowMilliseconds, _handoffSettleMilliseconds);
                return GbayToggleHandoffTransition.PresentationObserved;
            }

            return TryCompleteHandoff(nowMilliseconds);
        }

        private bool TryLatchPress(long nowMilliseconds, bool physicalSource)
        {
            if (_handoffBarrierActive)
            {
                // A new rising edge after release is allowed only if the
                // visible/timeout settle barrier already completed. An edge
                // arriving during the barrier is consumed and must itself be
                // released before the gate can settle.
                if (TryCompleteHandoff(nowMilliseconds) ==
                    GbayToggleHandoffTransition.None)
                {
                    if (physicalSource || !_physicalStateObserved ||
                        _physicalDown)
                        _handoffReleaseObserved = false;
                    _pressLatched = true;
                    _handoffSuppressionPending = true;
                    return false;
                }
            }

            if (_pressLatched)
                return false;

            _pressLatched = true;
            if (nowMilliseconds < _nextAllowedAt)
                return false;

            _nextAllowedAt = SaturatingAdd(
                nowMilliseconds, _debounceMilliseconds);
            return true;
        }

        private GbayToggleHandoffTransition TryCompleteHandoff(
            long nowMilliseconds)
        {
            if (!_handoffBarrierActive || !_handoffReleaseObserved)
                return GbayToggleHandoffTransition.None;

            GbayToggleHandoffTransition transition;
            if (_handoffPresentationObserved &&
                nowMilliseconds >= _handoffReadyAt)
            {
                transition = GbayToggleHandoffTransition.Settled;
            }
            else if (nowMilliseconds >= _handoffDeadline)
            {
                transition = GbayToggleHandoffTransition.TimedOut;
            }
            else
            {
                return GbayToggleHandoffTransition.None;
            }

            _handoffBarrierActive = false;
            _handoffPresentationObserved = false;
            _handoffReleaseObserved = false;
            _pressLatched = false;
            return transition;
        }

        private void ReleaseLatch()
        {
            _pressLatched = false;
            _lastDownSignalAt = 0;
        }

        private static bool ElapsedAtLeast(long now, long then, int interval)
        {
            // Game.GameTime is a signed counter. Treat a wrap/restart as an
            // elapsed interval instead of leaving the input permanently held.
            return now < then || now - then >= interval;
        }

        private static long SaturatingAdd(long value, long delta)
        {
            return value > long.MaxValue - delta
                ? long.MaxValue
                : value + delta;
        }
    }
}
