using System;

namespace ALLIN1
{
    /// <summary>
    /// Bounds live Reactor projections to one refresh per interval while the
    /// menu is visible. Closing the menu resets the gate so the next open gets
    /// an immediate state check instead of inheriting an old deadline.
    /// </summary>
    internal sealed class GbayGameStateSynchronizationGate
    {
        internal const int DefaultIntervalMilliseconds = 1000;
        internal const int FailureRetryMilliseconds = 500;

        private readonly int _intervalMilliseconds;
        private long _nextAttemptAt;
        private bool _active;

        internal GbayGameStateSynchronizationGate(
            int intervalMilliseconds = DefaultIntervalMilliseconds)
        {
            if (intervalMilliseconds <= 0)
                throw new ArgumentOutOfRangeException(
                    nameof(intervalMilliseconds));
            _intervalMilliseconds = intervalMilliseconds;
        }

        internal bool TryBegin(long gameTime, bool menuActive)
        {
            long now = Math.Max(0, gameTime);
            if (!menuActive)
            {
                _active = false;
                _nextAttemptAt = 0;
                return false;
            }

            if (!_active)
            {
                _active = true;
                return true;
            }

            if (now < _nextAttemptAt)
                return false;
            return true;
        }

        internal void Complete(long gameTime, bool succeeded)
        {
            long delay = succeeded
                ? _intervalMilliseconds
                : FailureRetryMilliseconds;
            _nextAttemptAt = Math.Max(0, gameTime) + delay;
        }
    }
}
