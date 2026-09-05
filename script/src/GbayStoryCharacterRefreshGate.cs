using System;

namespace ALLIN1
{
    /// <summary>
    /// Turns the per-frame Story protagonist observation into one logical
    /// cache-refresh edge. Unsupported/transient player models are ignored so
    /// GTA's switch animation cannot publish an empty identity between the two
    /// supported protagonists.
    /// </summary>
    internal sealed class GbayStoryCharacterRefreshGate
    {
        internal const int RetryDelayMilliseconds = 500;
        internal const int MaximumAttemptsPerCharacter = 3;

        private string _characterId = "";
        private string _pendingCharacterId = "";
        private int _pendingAttempts;
        private long _lastAttemptAt;

        internal string CharacterId => _characterId;

        internal void Seed(string characterId)
        {
            if (TryNormalize(characterId, out string normalized))
            {
                _characterId = normalized;
                ClearPending();
            }
        }

        internal bool TryBegin(
            string characterId, long nowMilliseconds,
            out string normalized)
        {
            if (!TryNormalize(characterId, out normalized))
                return false;
            if (string.Equals(_characterId, normalized,
                    StringComparison.Ordinal))
            {
                ClearPending();
                return false;
            }

            if (!string.Equals(_pendingCharacterId, normalized,
                    StringComparison.Ordinal))
            {
                _pendingCharacterId = normalized;
                _pendingAttempts = 0;
                _lastAttemptAt = 0;
            }

            if (_pendingAttempts >= MaximumAttemptsPerCharacter ||
                _pendingAttempts > 0 && !ElapsedAtLeast(
                    nowMilliseconds, _lastAttemptAt,
                    RetryDelayMilliseconds))
                return false;

            _pendingAttempts++;
            _lastAttemptAt = nowMilliseconds;
            return true;
        }

        internal void Complete(string characterId, bool succeeded)
        {
            if (!succeeded || !TryNormalize(
                    characterId, out string normalized) ||
                !string.Equals(_pendingCharacterId, normalized,
                    StringComparison.Ordinal))
                return;

            _characterId = normalized;
            ClearPending();
        }

        internal static bool TryNormalize(
            string characterId, out string normalized)
        {
            normalized = (characterId ?? "").Trim().ToLowerInvariant();
            if (normalized == "michael" || normalized == "franklin" ||
                normalized == "trevor")
                return true;

            normalized = "";
            return false;
        }

        private void ClearPending()
        {
            _pendingCharacterId = "";
            _pendingAttempts = 0;
            _lastAttemptAt = 0;
        }

        private static bool ElapsedAtLeast(
            long nowMilliseconds, long startedAt, long duration)
        {
            // GTA's session clock can reset between loads. A backwards jump
            // should release a pending retry rather than suppress it forever.
            return nowMilliseconds < startedAt ||
                nowMilliseconds - startedAt >= duration;
        }
    }
}
