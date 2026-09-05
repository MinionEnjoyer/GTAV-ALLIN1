using System;
using System.Diagnostics;
using System.IO;
using System.Threading;

namespace ALLIN1
{
    /// <summary>
    /// Observes Reactor V's process-specific native-to-managed F9 ownership
    /// boundary. If no native bootstrap contract exists, standalone/legacy
    /// ALLIN1 remains usable. Once the native event exists, input fails closed
    /// until native confirms RuntimeReady and a physical F9 release.
    /// </summary>
    internal sealed class ReactorF9HandoffGate : IDisposable
    {
        internal const string OwnershipReleasedEventPrefix =
            @"Local\ReactorV.F9OwnershipReleased.";
        internal const string StartupIntentActiveEventPrefix =
            @"Local\ReactorV.DefaultMenuIntentActive.";
        internal const string StartupIntentCancelledEventPrefix =
            @"Local\ReactorV.DefaultMenuIntentCancelled.";
        internal const string BootstrapCloseEventPrefix =
            @"Local\ReactorV.BootstrapHostClose.";

        private readonly string _eventName;
        private readonly string _startupIntentCancelledEventName;
        private readonly Func<long> _clockMilliseconds;
        private readonly long _startupIntentRetryIntervalMilliseconds;
        private readonly long _startupIntentRetryWindowMilliseconds;
        private EventWaitHandle _releaseEvent;
        private EventWaitHandle _startupIntentCancelledEvent;
        private bool _contractObserved;
        private bool _released;
        private bool _startupIntentWindowStarted;
        private bool _startupIntentCheckInFlight;
        private bool _startupIntentCheckCompleted;
        private long _startupIntentDeadlineMilliseconds;
        private long _nextStartupIntentCheckMilliseconds;
        private long _startupIntentPresentationGeneration;

        internal const int StartupIntentRetryIntervalMilliseconds = 250;
        internal const int StartupIntentRetryWindowMilliseconds = 5_000;

        internal ReactorF9HandoffGate()
            : this(Process.GetCurrentProcess().Id)
        {
        }

        internal ReactorF9HandoffGate(int processId)
            : this(
                processId,
                MonotonicMilliseconds,
                StartupIntentRetryIntervalMilliseconds,
                StartupIntentRetryWindowMilliseconds)
        {
        }

        internal ReactorF9HandoffGate(
            int processId,
            Func<long> clockMilliseconds,
            int startupIntentRetryIntervalMilliseconds,
            int startupIntentRetryWindowMilliseconds)
        {
            if (processId <= 0)
                throw new ArgumentOutOfRangeException(nameof(processId));
            if (clockMilliseconds == null)
                throw new ArgumentNullException(nameof(clockMilliseconds));
            if (startupIntentRetryIntervalMilliseconds <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(startupIntentRetryIntervalMilliseconds));
            if (startupIntentRetryWindowMilliseconds <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(startupIntentRetryWindowMilliseconds));
            _eventName = OwnershipEventName(processId);
            _startupIntentCancelledEventName =
                StartupIntentCancelledEventName(processId);
            _clockMilliseconds = clockMilliseconds;
            _startupIntentRetryIntervalMilliseconds =
                startupIntentRetryIntervalMilliseconds;
            _startupIntentRetryWindowMilliseconds =
                startupIntentRetryWindowMilliseconds;
        }

        internal static string OwnershipEventName(int processId)
        {
            if (processId <= 0)
                throw new ArgumentOutOfRangeException(nameof(processId));
            return OwnershipReleasedEventPrefix + processId;
        }

        internal static string StartupIntentActiveEventName(int processId)
        {
            if (processId <= 0)
                throw new ArgumentOutOfRangeException(nameof(processId));
            return StartupIntentActiveEventPrefix + processId;
        }

        internal static string StartupIntentCancelledEventName(int processId)
        {
            if (processId <= 0)
                throw new ArgumentOutOfRangeException(nameof(processId));
            return StartupIntentCancelledEventPrefix + processId;
        }

        internal static string BootstrapCloseEventName(int processId)
        {
            if (processId <= 0)
                throw new ArgumentOutOfRangeException(nameof(processId));
            return BootstrapCloseEventPrefix + processId;
        }

        internal bool CanHandleF9()
        {
            if (_released)
                return true;

            if (_releaseEvent == null && !TryOpenReleaseEvent())
                return !_contractObserved;

            try
            {
                if (!_releaseEvent.WaitOne(0))
                    return false;
                _released = true;
                _releaseEvent.Dispose();
                _releaseEvent = null;
                return true;
            }
            catch (ObjectDisposedException)
            {
                // An observed native contract must never fail open because a
                // handle was unexpectedly disposed. Re-open it on the next
                // check and keep native ownership for this one.
                _releaseEvent = null;
                return false;
            }
        }

        internal bool CanDispatch(bool isPhysicalF9)
        {
            // The native bootstrap owns only keyboard F9. Controller chords
            // are a separate input channel and remain available throughout
            // startup without risking one key press reaching two owners.
            if (!isPhysicalF9)
                return true;
            if (!CanHandleF9())
                return false;

            CompleteIfStartupIntentCancelled();

            // Release of native key ownership is necessary but not sufficient:
            // a delayed SHVDN KeyDown from that same opening press may arrive
            // after the native high-bit release. Keep physical F9 fail-closed
            // until the typed startup intent has been presented, explicitly
            // cancelled, or its bounded lookup window has conclusively
            // expired. On successful presentation GbayToggleInputGate
            // continues ownership through first paint and its settle barrier.
            return !_contractObserved || _startupIntentCheckCompleted;
        }

        /// <summary>
        /// Closes a still-active native initializer even when the optional
        /// Reactor menu bridge has not registered yet. This is a typed close
        /// request only; it never replays F9 or invents a menu action.
        /// </summary>
        internal bool TryRequestStartupIntentClose()
        {
            return TryRequestStartupIntentClose(
                Process.GetCurrentProcess().Id);
        }

        internal bool TryRequestStartupIntentClose(int processId)
        {
            if (processId <= 0)
                throw new ArgumentOutOfRangeException(nameof(processId));
            try
            {
                using (var active = EventWaitHandle.OpenExisting(
                           StartupIntentActiveEventName(processId)))
                {
                    if (!active.WaitOne(0)) return false;
                }
                using (var close = EventWaitHandle.OpenExisting(
                           BootstrapCloseEventName(processId)))
                    return close.Set();
            }
            catch (WaitHandleCannotBeOpenedException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
            catch (IOException) { return false; }
        }

        /// <summary>
        /// Opens a throttled, bounded opportunity to consume the native
        /// startup-menu intent, and only after native has released F9. A
        /// short retry window covers the ordering where native releases F9
        /// immediately before the preloader UI thread arms the typed intent.
        /// The inexpensive in-memory gate may be polled each game tick, but
        /// the caller reaches the named intent event at most four times per
        /// second and stops permanently after success, cancellation, or
        /// expiry.
        /// </summary>
        internal bool TryBeginStartupIntentCheck()
        {
            if (_startupIntentCheckCompleted ||
                _startupIntentCheckInFlight ||
                !CanHandleF9())
                return false;

            if (CompleteIfStartupIntentCancelled())
                return false;

            long now = _clockMilliseconds();
            if (!_startupIntentWindowStarted)
            {
                _startupIntentWindowStarted = true;
                _startupIntentDeadlineMilliseconds = SaturatingAdd(
                    now, _startupIntentRetryWindowMilliseconds);
                _nextStartupIntentCheckMilliseconds = now;
            }

            if (now >= _startupIntentDeadlineMilliseconds)
            {
                _startupIntentCheckCompleted = true;
                return false;
            }
            if (now < _nextStartupIntentCheckMilliseconds)
                return false;

            _startupIntentCheckInFlight = true;
            _nextStartupIntentCheckMilliseconds = SaturatingAdd(
                now, _startupIntentRetryIntervalMilliseconds);
            return true;
        }

        /// <summary>
        /// Reports the result of the one bridge check opened above. A
        /// successful consume/presentation completes the handoff immediately;
        /// absence remains retryable only inside the bounded window.
        /// </summary>
        internal long CompleteStartupIntentCheck(bool consumedAndPresented)
        {
            if (!_startupIntentCheckInFlight)
                return 0;

            _startupIntentCheckInFlight = false;
            if (CompleteIfStartupIntentCancelled())
                return 0;
            if (consumedAndPresented)
            {
                // Allocate the generation at the exact atomic boundary where
                // the native intent has been consumed and its GBAY
                // presentation has been accepted. The managed input latch
                // uses this id to consume the opening F9 through first paint.
                if (_startupIntentPresentationGeneration < long.MaxValue)
                    _startupIntentPresentationGeneration++;
                _startupIntentCheckCompleted = true;
                return _startupIntentPresentationGeneration;
            }

            if (
                _clockMilliseconds() >= _startupIntentDeadlineMilliseconds)
            {
                _startupIntentCheckCompleted = true;
            }
            return 0;
        }

        private static long MonotonicMilliseconds()
        {
            return (long)(Stopwatch.GetTimestamp() * 1000.0 /
                Stopwatch.Frequency);
        }

        private static long SaturatingAdd(long value, long delta)
        {
            return value > long.MaxValue - delta
                ? long.MaxValue
                : value + delta;
        }

        private bool TryOpenReleaseEvent()
        {
            try
            {
                _releaseEvent = EventWaitHandle.OpenExisting(_eventName);
                _contractObserved = true;
                return true;
            }
            catch (WaitHandleCannotBeOpenedException)
            {
                // Reactor's native bootstrap is optional. Absence means there
                // is no competing native F9 owner.
                return false;
            }
            catch (UnauthorizedAccessException)
            {
                _contractObserved = true;
                return false;
            }
            catch (IOException)
            {
                _contractObserved = true;
                return false;
            }
        }

        private bool CompleteIfStartupIntentCancelled()
        {
            if (_startupIntentCheckCompleted || !_contractObserved)
                return _startupIntentCheckCompleted;

            try
            {
                if (_startupIntentCancelledEvent == null)
                {
                    _startupIntentCancelledEvent =
                        EventWaitHandle.OpenExisting(
                            _startupIntentCancelledEventName);
                }
                if (!_startupIntentCancelledEvent.WaitOne(0))
                    return false;

                _startupIntentCheckCompleted = true;
                _startupIntentCancelledEvent.Dispose();
                _startupIntentCancelledEvent = null;
                return true;
            }
            catch (WaitHandleCannotBeOpenedException)
            {
                // A genuine release-before-arm ordering remains retryable.
                // Older Reactor contracts also do not publish this event.
                return false;
            }
            catch (ObjectDisposedException)
            {
                _startupIntentCancelledEvent = null;
                return false;
            }
            catch (UnauthorizedAccessException) { return false; }
            catch (IOException) { return false; }
        }

        public void Dispose()
        {
            _releaseEvent?.Dispose();
            _releaseEvent = null;
            _startupIntentCancelledEvent?.Dispose();
            _startupIntentCancelledEvent = null;
        }
    }
}
