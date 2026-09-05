using System;
using System.Collections.Generic;
using System.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class OfficialGarageStreamingTransitionTests
    {
        [Fact]
        public void Entry_holds_fade_through_map_and_interior_readiness()
        {
            long now = 100;
            int fadeOuts = 0;
            int fadeIns = 0;
            int rollbacks = 0;
            var events = new List<OfficialGarageTransitionEvent>();
            var transition = new OfficialGarageTransitionCoordinator(
                "davis", "entry", () => now, events.Add,
                () => rollbacks++, () => fadeIns++);

            now = 110;
            transition.HoldFade(() => fadeOuts++);
            now = 130;
            transition.Advance(
                OfficialGarageTransitionPhase.LeaseRequested);
            now = 180;
            transition.Advance(OfficialGarageTransitionPhase.IplReady);
            now = 260;
            transition.Advance(OfficialGarageTransitionPhase.InteriorReady);
            now = 320;
            transition.Complete(
                OfficialGarageTransitionPhase.Occupied,
                () => fadeIns++);
            transition.Dispose();

            Assert.Equal(1, fadeOuts);
            Assert.Equal(1, fadeIns);
            Assert.Equal(0, rollbacks);
            Assert.False(transition.FadeHeld);
            Assert.True(transition.IsTerminal);
            Assert.Equal(OfficialGarageTransitionPhase.Occupied,
                transition.Phase);
            Assert.Equal(new[]
            {
                OfficialGarageTransitionPhase.Idle,
                OfficialGarageTransitionPhase.FadeHeld,
                OfficialGarageTransitionPhase.LeaseRequested,
                OfficialGarageTransitionPhase.IplReady,
                OfficialGarageTransitionPhase.InteriorReady,
                OfficialGarageTransitionPhase.Occupied,
            }, events.Select(value => value.Phase).ToArray());
            Assert.Equal(220,
                events.Last().TotalElapsedMilliseconds);
            Assert.Equal(60,
                events.Last().PhaseElapsedMilliseconds);
            Assert.True(events.Last().Terminal);
        }

        [Fact]
        public void Entry_can_finish_streaming_before_acquiring_the_fade()
        {
            int fadeOuts = 0;
            int fadeIns = 0;
            var events = new List<OfficialGarageTransitionEvent>();
            var transition = new OfficialGarageTransitionCoordinator(
                "davis", "entry", () => events.Count, events.Add,
                () => { }, () => fadeIns++);

            transition.Advance(
                OfficialGarageTransitionPhase.LeaseRequested);
            transition.Advance(OfficialGarageTransitionPhase.IplReady);
            transition.Advance(OfficialGarageTransitionPhase.InteriorReady);

            Assert.Equal(0, fadeOuts);
            Assert.False(transition.FadeHeld);

            transition.HoldFade(() => fadeOuts++);
            transition.Complete(
                OfficialGarageTransitionPhase.Occupied,
                () => fadeIns++);

            Assert.Equal(1, fadeOuts);
            Assert.Equal(1, fadeIns);
            Assert.Equal(OfficialGarageTransitionPhase.Occupied,
                transition.Phase);
            Assert.Equal(new[]
            {
                OfficialGarageTransitionPhase.Idle,
                OfficialGarageTransitionPhase.LeaseRequested,
                OfficialGarageTransitionPhase.IplReady,
                OfficialGarageTransitionPhase.InteriorReady,
                OfficialGarageTransitionPhase.FadeHeld,
                OfficialGarageTransitionPhase.Occupied,
            }, events.Select(value => value.Phase).ToArray());
        }

        [Fact]
        public void Failure_rolls_back_and_restores_visibility_exactly_once()
        {
            long now = 0;
            int fadeIns = 0;
            int rollbacks = 0;
            var events = new List<OfficialGarageTransitionEvent>();
            var transition = new OfficialGarageTransitionCoordinator(
                "davis", "entry", () => now, events.Add,
                () => rollbacks++, () => fadeIns++);

            transition.HoldFade(() => { });
            now = 25;
            transition.Advance(
                OfficialGarageTransitionPhase.LeaseRequested);
            now = 75;
            transition.Fail("map_activation_failed");
            transition.Fail("duplicate_failure");
            transition.Dispose();

            Assert.Equal(1, rollbacks);
            Assert.Equal(1, fadeIns);
            Assert.False(transition.FadeHeld);
            Assert.True(transition.IsTerminal);
            Assert.Equal(OfficialGarageTransitionPhase.FailedRecovery,
                transition.Phase);
            Assert.Equal("map_activation_failed", events.Last().Detail);
            Assert.Equal(75, events.Last().TotalElapsedMilliseconds);
        }

        [Fact]
        public void Disposing_an_incomplete_faded_entry_recovers_automatically()
        {
            int fadeIns = 0;
            int rollbacks = 0;
            var transition = new OfficialGarageTransitionCoordinator(
                "davis", "entry", () => 10, _ => { },
                () => rollbacks++, () => fadeIns++);

            transition.HoldFade(() => { });
            transition.Dispose();

            Assert.Equal(1, rollbacks);
            Assert.Equal(1, fadeIns);
            Assert.Equal(OfficialGarageTransitionPhase.FailedRecovery,
                transition.Phase);
        }

        [Fact]
        public void Invalid_phase_jump_is_rejected_before_side_effects()
        {
            var transition = new OfficialGarageTransitionCoordinator(
                "davis", "entry", () => 0, _ => { },
                () => { }, () => { });

            InvalidOperationException error = Assert.Throws<InvalidOperationException>(
                () => transition.Advance(
                    OfficialGarageTransitionPhase.InteriorReady));

            Assert.Contains("Idle -> InteriorReady", error.Message);
            Assert.Equal(OfficialGarageTransitionPhase.Idle,
                transition.Phase);
        }

        [Fact]
        public void Telemetry_failure_never_changes_transition_or_fade_cleanup()
        {
            int fadeIns = 0;
            var transition = new OfficialGarageTransitionCoordinator(
                "davis", "entry", () => 0,
                _ => throw new InvalidOperationException("log unavailable"),
                () => { }, () => fadeIns++);

            transition.HoldFade(() => { });
            transition.Advance(OfficialGarageTransitionPhase.LeaseRequested);
            transition.Fail("fixture_failure");

            Assert.True(transition.IsTerminal);
            Assert.Equal(OfficialGarageTransitionPhase.FailedRecovery,
                transition.Phase);
            Assert.Equal(1, fadeIns);
        }

        [Theory]
        [InlineData(false, 5000f, false)]
        [InlineData(false, 901f, false)]
        [InlineData(false, 900f, true)]
        [InlineData(true, 900f, true)]
        [InlineData(true, 1200f, true)]
        [InlineData(true, 1201f, false)]
        public void Yacht_streaming_uses_near_acquire_and_far_release_hysteresis(
            bool alreadyAcquired, float distance, bool expected)
        {
            Assert.Equal(expected,
                YachtStreamingPolicy.ShouldAcquire(
                    alreadyAcquired, distance, 900f, 1200f));
        }

        [Fact]
        public void Yacht_does_not_activate_at_an_ordinary_story_start_distance()
        {
            Assert.False(YachtStreamingPolicy.ShouldAcquire(
                currentlyAcquired: false, distance: 5000f,
                acquireDistance: 900f, releaseDistance: 1200f));
        }
    }
}
