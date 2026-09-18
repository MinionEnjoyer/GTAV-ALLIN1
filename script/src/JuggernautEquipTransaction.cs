using System;

namespace ALLIN1
{
    /// <summary>
    /// Native-facing surface for the staged Juggernaut equip transaction.
    /// Implementations own all GTA calls, validation, and outfit snapshots.
    /// </summary>
    internal interface IJuggernautEquipTarget
    {
        bool IsSafe { get; }
        bool IsSamePlayer { get; }
        bool AnimationLoaded { get; }
        bool CanCommit { get; }
        void PreflightAndCapture();
        void RequestAnimation();
        void ApplyOutfit();
        void ApplyEffects();
        void Restore(bool rollback);
        void Commit();
        void ReleaseAnimation();
        void Trace(string stage, string detail);
    }

    /// <summary>
    /// Keeps all yield-free state transitions for Juggernaut equip separate
    /// from the GTA native adapter.  The adapter is responsible for making
    /// each native operation safe; this controller never calls GTA directly.
    /// </summary>
    internal sealed class JuggernautEquipTransaction
    {
        internal const long AnimationTimeoutMs = 3000;

        private IJuggernautEquipTarget _target;
        private long _animationRequestedAt;
        private bool _animationRequested;
        private bool _mutated;

        internal bool Pending { get; private set; }
        internal bool Active { get; private set; }

        internal bool Begin(IJuggernautEquipTarget target, long nowMs)
        {
            if (target == null || Pending || Active) return false;
            try
            {
                if (!target.IsSafe) return false;
            }
            catch (Exception error)
            {
                SafeTrace(target, "begin_rejected", Describe(error));
                return false;
            }

            _target = target;
            Pending = true;
            _animationRequestedAt = nowMs;
            SafeTrace(target, "begin", "pending");
            return true;
        }

        internal void Tick(long nowMs)
        {
            try
            {
                TickCore(nowMs);
            }
            catch (Exception error)
            {
                if (Pending)
                {
                    SafeTrace(_target, "tick_failed", Describe(error));
                    CancelPending("tick_failed");
                }
                else if (Active)
                {
                    // A transient target/property fault must not restore onto
                    // an uncertain ped or silently erase a valid active suit.
                    SafeTrace(_target, "active_tick_failed", Describe(error));
                }
            }
        }

        private void TickCore(long nowMs)
        {
            if (Active)
            {
                // A different (or dead) player must never inherit a saved
                // outfit.  Temporary safety gates such as loading or a garage
                // transition keep the active state intact; the adapter simply
                // skips its per-tick effects until that gate clears.
                if (_target == null || !_target.IsSamePlayer)
                    Clear("player_replaced");
                return;
            }

            if (!Pending || _target == null) return;
            IJuggernautEquipTarget target = _target;

            if (!target.IsSafe || !target.IsSamePlayer)
            {
                CancelPending("unsafe_target");
                return;
            }

            if (!_animationRequested)
            {
                try
                {
                    target.PreflightAndCapture();
                    // Treat entry to RequestAnimation as the lifecycle
                    // boundary.  If the adapter throws after issuing its
                    // request, cleanup must still release exactly once.
                    _animationRequested = true;
                    target.RequestAnimation();
                    _animationRequestedAt = nowMs;
                    SafeTrace(target, "animation_requested", "pending");
                }
                catch (Exception error)
                {
                    FailPending("preflight_or_request_failed", error);
                }
                return;
            }

            // The deadline is authoritative even if the stream reports loaded
            // on a late polling tick; never commit an expired request.
            if (ElapsedAtLeast(nowMs, _animationRequestedAt,
                    AnimationTimeoutMs))
            {
                CancelPending("animation_timeout");
                return;
            }
            if (!target.AnimationLoaded)
            {
                return;
            }

            if (!target.IsSafe || !target.IsSamePlayer || !target.CanCommit)
            {
                CancelPending("commit_gate_rejected");
                return;
            }

            try
            {
                // The target must recapture after the asynchronous load: a
                // player/outfit can change while animation streaming advances.
                target.PreflightAndCapture();
                if (!target.IsSafe || !target.IsSamePlayer ||
                    !target.CanCommit || !target.AnimationLoaded)
                {
                    CancelPending("commit_revalidation_rejected");
                    return;
                }

                SafeTrace(target, "commit_begin", "animation_loaded");
                // Mark before the first setter: ApplyOutfit can throw after
                // applying earlier slots, and that partial state must roll
                // back on the same safe target.
                _mutated = true;
                target.ApplyOutfit();
                target.ApplyEffects();
                target.Commit();
                Active = true;
                Pending = false;
                _mutated = false;
                SafeTrace(target, "commit_complete", "active");
            }
            catch (Exception error)
            {
                FailCommit(error);
            }
        }

        internal void CancelPending(string reason)
        {
            if (!Pending) return;
            IJuggernautEquipTarget target = _target;
            Pending = false;
            _mutated = false;
            SafeTrace(target, "pending_cancelled", reason ?? "cancelled");
            ReleaseAnimationOnce();
            if (!Active) _target = null;
        }

        internal bool Remove()
        {
            CancelPending("removed");
            if (!Active) return true;

            IJuggernautEquipTarget target = _target;
            if (target == null || !target.IsSamePlayer)
            {
                Clear("player_replaced");
                return false;
            }
            if (!target.IsSafe)
            {
                SafeTrace(target, "remove_deferred", "unsafe_target");
                return false;
            }

            try
            {
                SafeTrace(target, "remove_begin", "active");
                target.Restore(false);
                SafeTrace(target, "remove_complete", "active");
            }
            catch (Exception error)
            {
                SafeTrace(target, "remove_failed", Describe(error));
                // Retain the same snapshot, target, and animation request so
                // the caller can retry rather than treating an incomplete
                // restore as an equipped-state removal.
                return false;
            }

            Active = false;
            _mutated = false;
            ReleaseAnimationOnce();
            _target = null;
            return true;
        }

        /// <summary>Drop every retained state without touching a replacement ped.</summary>
        internal void Clear(string reason)
        {
            if (Pending) CancelPending(reason ?? "cleared");
            if (!Active) return;

            SafeTrace(_target, "active_dropped", reason ?? "cleared");
            Active = false;
            _mutated = false;
            ReleaseAnimationOnce();
            _target = null;
        }

        private void FailPending(string stage, Exception error)
        {
            SafeTrace(_target, stage, Describe(error));
            CancelPending(stage);
        }

        private void FailCommit(Exception error)
        {
            IJuggernautEquipTarget target = _target;
            SafeTrace(target, "commit_failed", Describe(error));
            try
            {
                if (_mutated && target != null && target.IsSafe &&
                    target.IsSamePlayer)
                {
                    SafeTrace(target, "rollback_begin", Describe(error));
                    target.Restore(true);
                    SafeTrace(target, "rollback_complete", "restored");
                }
                else if (_mutated)
                    SafeTrace(target, "rollback_dropped", "unsafe_target");
            }
            catch (Exception rollbackError)
            {
                SafeTrace(target, "rollback_failed", Describe(rollbackError));
            }
            finally
            {
                Pending = false;
                Active = false;
                _mutated = false;
                ReleaseAnimationOnce();
                _target = null;
            }
        }

        private void ReleaseAnimationOnce()
        {
            if (!_animationRequested) return;
            _animationRequested = false;
            try
            {
                _target?.ReleaseAnimation();
            }
            catch (Exception error)
            {
                SafeTrace(_target, "animation_release_failed", Describe(error));
            }
        }

        private static bool ElapsedAtLeast(long nowMs, long thenMs, long durationMs)
        {
            return nowMs >= thenMs && nowMs - thenMs >= durationMs;
        }

        private static string Describe(Exception error)
        {
            return error == null ? "unknown" : error.GetType().Name + ": " +
                (error.Message ?? "");
        }

        private static void SafeTrace(IJuggernautEquipTarget target,
            string stage, string detail)
        {
            try { target?.Trace(stage, detail); }
            catch { }
        }
    }
}
