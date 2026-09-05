using System;
using System.Collections.Generic;

namespace ALLIN1
{
    /// <summary>
    /// Observable phases shared by the official garage streaming adapters.
    /// The state machine deliberately contains no GTA-native calls so its
    /// ordering and recovery guarantees remain unit-testable.
    /// </summary>
    internal enum OfficialGarageTransitionPhase
    {
        Idle,
        FadeHeld,
        LeaseRequested,
        IplReady,
        InteriorReady,
        Occupied,
        ExitFadeHeld,
        WorldReady,
        Released,
        FailedRecovery,
    }

    internal sealed class OfficialGarageTransitionEvent
    {
        internal string TransitionId { get; set; }
        internal string GarageId { get; set; }
        internal string Direction { get; set; }
        internal OfficialGarageTransitionPhase PreviousPhase { get; set; }
        internal OfficialGarageTransitionPhase Phase { get; set; }
        internal long PhaseElapsedMilliseconds { get; set; }
        internal long TotalElapsedMilliseconds { get; set; }
        internal string Detail { get; set; }
        internal bool Terminal { get; set; }
    }

    internal static class OfficialGarageTransitionPolicy
    {
        internal static bool CanAdvance(
            OfficialGarageTransitionPhase current,
            OfficialGarageTransitionPhase next)
        {
            if (next == OfficialGarageTransitionPhase.FailedRecovery)
            {
                return current != OfficialGarageTransitionPhase.Released &&
                    current != OfficialGarageTransitionPhase.FailedRecovery;
            }

            switch (current)
            {
                case OfficialGarageTransitionPhase.Idle:
                    return next == OfficialGarageTransitionPhase.FadeHeld ||
                        next == OfficialGarageTransitionPhase.LeaseRequested ||
                        next == OfficialGarageTransitionPhase.ExitFadeHeld;
                case OfficialGarageTransitionPhase.FadeHeld:
                    return next == OfficialGarageTransitionPhase.LeaseRequested ||
                        next == OfficialGarageTransitionPhase.Occupied;
                case OfficialGarageTransitionPhase.LeaseRequested:
                    return next == OfficialGarageTransitionPhase.IplReady;
                case OfficialGarageTransitionPhase.IplReady:
                    return next == OfficialGarageTransitionPhase.InteriorReady;
                case OfficialGarageTransitionPhase.InteriorReady:
                    return next == OfficialGarageTransitionPhase.FadeHeld ||
                        next == OfficialGarageTransitionPhase.Occupied;
                case OfficialGarageTransitionPhase.Occupied:
                    return next == OfficialGarageTransitionPhase.ExitFadeHeld;
                case OfficialGarageTransitionPhase.ExitFadeHeld:
                    return next == OfficialGarageTransitionPhase.WorldReady;
                case OfficialGarageTransitionPhase.WorldReady:
                    return next == OfficialGarageTransitionPhase.Released;
                default:
                    return false;
            }
        }
    }

    /// <summary>
    /// Owns a single official-garage transition's black-screen lifetime and
    /// failure cleanup. A held fade can leave the player apparently frozen, so
    /// every non-terminal disposal performs rollback and a forced fade-in.
    /// </summary>
    internal sealed class OfficialGarageTransitionCoordinator : IDisposable
    {
        private readonly string _garageId;
        private readonly string _direction;
        private readonly string _transitionId;
        private readonly Func<long> _clock;
        private readonly Action<OfficialGarageTransitionEvent> _telemetry;
        private readonly Action _rollback;
        private readonly Action _forceFadeIn;
        private readonly long _startedAt;
        private long _phaseStartedAt;
        private bool _fadeHeld;
        private bool _terminal;

        internal OfficialGarageTransitionCoordinator(
            string garageId,
            string direction,
            Func<long> clock,
            Action<OfficialGarageTransitionEvent> telemetry,
            Action rollback,
            Action forceFadeIn)
        {
            _garageId = string.IsNullOrWhiteSpace(garageId)
                ? "unknown" : garageId.Trim();
            _direction = string.IsNullOrWhiteSpace(direction)
                ? "unknown" : direction.Trim();
            _transitionId = Guid.NewGuid().ToString("N");
            _clock = clock ?? throw new ArgumentNullException(nameof(clock));
            _telemetry = telemetry;
            _rollback = rollback;
            _forceFadeIn = forceFadeIn;
            _startedAt = _clock();
            _phaseStartedAt = _startedAt;
            Phase = OfficialGarageTransitionPhase.Idle;
            Emit(Phase, Phase, "created", false, _startedAt);
        }

        internal OfficialGarageTransitionPhase Phase { get; private set; }
        internal string TransitionId => _transitionId;
        internal bool FadeHeld => _fadeHeld;
        internal bool IsTerminal => _terminal;

        internal void HoldFade(Action acquireFade)
        {
            if (acquireFade == null)
                throw new ArgumentNullException(nameof(acquireFade));
            EnsureActive();
            if (!OfficialGarageTransitionPolicy.CanAdvance(
                    Phase, OfficialGarageTransitionPhase.FadeHeld))
                throw InvalidAdvance(OfficialGarageTransitionPhase.FadeHeld);

            // Mark ownership before the call. If the native fade begins and
            // then throws, Fail still knows it must restore visibility.
            _fadeHeld = true;
            try
            {
                acquireFade();
                Advance(OfficialGarageTransitionPhase.FadeHeld,
                    "black_screen_acquired");
            }
            catch
            {
                Fail("black_screen_acquire_failed");
                throw;
            }
        }

        internal void Advance(
            OfficialGarageTransitionPhase next, string detail = null)
        {
            EnsureActive();
            if (!OfficialGarageTransitionPolicy.CanAdvance(Phase, next))
                throw InvalidAdvance(next);
            MoveTo(next, detail, false);
        }

        internal void Complete(
            OfficialGarageTransitionPhase terminalPhase,
            Action releaseFade,
            string detail = null)
        {
            EnsureActive();
            if (terminalPhase != OfficialGarageTransitionPhase.Occupied &&
                terminalPhase != OfficialGarageTransitionPhase.Released)
                throw new ArgumentOutOfRangeException(nameof(terminalPhase));
            if (!OfficialGarageTransitionPolicy.CanAdvance(
                    Phase, terminalPhase))
                throw InvalidAdvance(terminalPhase);
            if (_fadeHeld && releaseFade == null)
                throw new ArgumentNullException(nameof(releaseFade));

            try
            {
                if (_fadeHeld) releaseFade();
                _fadeHeld = false;
                _terminal = true;
                MoveTo(terminalPhase, detail ?? "completed", true);
            }
            catch
            {
                Fail("completion_failed");
                throw;
            }
        }

        internal void Fail(string detail)
        {
            if (_terminal) return;

            var cleanupErrors = new List<string>();
            try { _rollback?.Invoke(); }
            catch (Exception ex)
            {
                cleanupErrors.Add("rollback:" + ex.GetType().Name);
            }

            if (_fadeHeld)
            {
                try { _forceFadeIn?.Invoke(); }
                catch (Exception ex)
                {
                    cleanupErrors.Add("fade_in:" + ex.GetType().Name);
                }
            }

            _fadeHeld = false;
            _terminal = true;
            string finalDetail = string.IsNullOrWhiteSpace(detail)
                ? "failed" : detail.Trim();
            if (cleanupErrors.Count > 0)
                finalDetail += "; cleanup=" + string.Join(",", cleanupErrors);
            MoveTo(OfficialGarageTransitionPhase.FailedRecovery,
                finalDetail, true);
        }

        public void Dispose()
        {
            if (!_terminal && _fadeHeld)
                Fail("scope_disposed_before_completion");
        }

        private void MoveTo(
            OfficialGarageTransitionPhase next,
            string detail,
            bool terminal)
        {
            long now = _clock();
            OfficialGarageTransitionPhase previous = Phase;
            Phase = next;
            Emit(previous, next, detail, terminal, now);
            _phaseStartedAt = now;
        }

        private void Emit(
            OfficialGarageTransitionPhase previous,
            OfficialGarageTransitionPhase current,
            string detail,
            bool terminal,
            long now)
        {
            if (_telemetry == null) return;
            var observation = new OfficialGarageTransitionEvent
            {
                TransitionId = _transitionId,
                GarageId = _garageId,
                Direction = _direction,
                PreviousPhase = previous,
                Phase = current,
                PhaseElapsedMilliseconds = Math.Max(0, now - _phaseStartedAt),
                TotalElapsedMilliseconds = Math.Max(0, now - _startedAt),
                Detail = detail ?? string.Empty,
                Terminal = terminal,
            };
            // Telemetry is observational. A disk/logging failure must never
            // strand the player behind a fade or change transition behavior.
            try { _telemetry(observation); }
            catch { }
        }

        private void EnsureActive()
        {
            if (_terminal)
                throw new InvalidOperationException(
                    "The garage transition is already terminal.");
        }

        private InvalidOperationException InvalidAdvance(
            OfficialGarageTransitionPhase next) =>
            new InvalidOperationException(
                $"Invalid official garage transition: {Phase} -> {next}.");
    }
}
