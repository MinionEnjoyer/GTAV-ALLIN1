using System;
using System.IO;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class PedPopulationPolicyTests
    {
        [Theory]
        [InlineData("disabled", 0, true)]
        [InlineData("add", 1, true)]
        [InlineData("replace", 2, true)]
        [InlineData("sell", 0, false)]
        public void Modes_are_closed_and_explicit(string value,
            int expected, bool accepted)
        {
            PedPopulationMode actual;
            Assert.Equal(accepted, PedPopulationPolicy.TryParseMode(value, out actual));
            Assert.Equal((PedPopulationMode)expected, actual);
        }

        [Theory]
        [InlineData(false, true, false, false, false, false, false, false, false)]
        [InlineData(true, true, false, false, false, false, false, false, true)]
        [InlineData(false, false, false, false, false, false, false, false, true)]
        [InlineData(false, true, true, false, false, false, false, false, true)]
        [InlineData(false, true, false, true, false, false, false, false, true)]
        [InlineData(false, true, false, false, true, false, false, false, true)]
        [InlineData(false, true, false, false, false, true, false, false, true)]
        [InlineData(false, true, false, false, false, false, true, false, true)]
        [InlineData(false, true, false, false, false, false, false, true, true)]
        public void Unsafe_story_states_always_suppress_population(
            bool loading, bool player, bool wanted, bool mission, bool cutscene,
            bool switching, bool interior, bool garage, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.IsSuppressed(loading,
                player, wanted, mission, cutscene, switching, interior, garage));
        }

        [Theory]
        [InlineData(true, true, false, false, false, false, false, false, "game loading")]
        [InlineData(false, false, false, false, false, false, false, false, "player unavailable")]
        [InlineData(false, true, true, false, false, false, false, false, "wanted level active")]
        [InlineData(false, true, false, true, false, false, false, false, "mission active")]
        [InlineData(false, true, false, false, true, false, false, false, "cutscene active")]
        [InlineData(false, true, false, false, false, true, false, false, "player switch in progress")]
        [InlineData(false, true, false, false, false, false, true, false, "player is indoors")]
        [InlineData(false, true, false, false, false, false, false, true, "garage transition in progress")]
        [InlineData(false, true, false, false, false, false, false, false, "")]
        public void Population_pause_reason_matches_the_closed_safety_gate(
            bool loading, bool player, bool wanted, bool mission, bool cutscene,
            bool switching, bool interior, bool garage, string expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.SuppressionReason(loading,
                player, wanted, mission, cutscene, switching, interior, garage));
        }

        [Theory]
        [InlineData(false, false, false, false, false, false, false, false, false, false, false, false, 1, true)]
        [InlineData(true, false, false, false, false, false, false, false, false, false, false, false, 1, false)]
        [InlineData(false, true, false, false, false, false, false, false, false, false, false, false, 1, false)]
        [InlineData(false, false, true, false, false, false, false, false, false, false, false, false, 1, false)]
        [InlineData(false, false, false, true, false, false, false, false, false, false, false, false, 1, false)]
        [InlineData(false, false, false, false, true, false, false, false, false, false, false, false, 1, false)]
        [InlineData(false, false, false, false, false, true, false, false, false, false, false, false, 1, false)]
        [InlineData(false, false, false, false, false, false, true, false, false, false, false, false, 1, false)]
        [InlineData(false, false, false, false, false, false, false, true, false, false, false, false, 1, false)]
        [InlineData(false, false, false, false, false, false, false, false, true, false, false, false, 1, false)]
        [InlineData(false, false, false, false, false, false, false, false, false, true, false, false, 1, false)]
        [InlineData(false, false, false, false, false, false, false, false, false, false, true, false, 1, false)]
        [InlineData(false, false, false, false, false, false, false, false, false, false, false, true, 1, false)]
        [InlineData(false, false, false, false, false, false, false, false, false, false, false, false, 0, false)]
        [InlineData(false, false, false, false, false, false, false, false, false, false, false, false, 6, false)]
        public void Only_offscreen_noninteractive_ambient_peds_are_candidates(
            bool player, bool persistent, bool mission, bool vehicle, bool combat,
            bool dead, bool injured, bool ragdoll, bool fleeing, bool shooting,
            bool onScreen, bool tooNear, int populationType, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.IsAmbientCandidate(player,
                persistent, mission, vehicle, combat, dead, injured, ragdoll,
                fleeing, shooting, onScreen, tooNear, populationType));
        }

        [Fact]
        public void Scripted_scenario_tasks_are_not_ambient_candidates()
        {
            Assert.False(PedPopulationPolicy.IsAmbientCandidate(false, false,
                false, false, false, false, false, false, false, false,
                false, false, 1, true));
        }

        [Theory]
        [InlineData(true, true, true, true)]
        [InlineData(false, true, true, false)]
        [InlineData(true, false, true, false)]
        [InlineData(true, true, false, false)]
        public void Replacement_never_deletes_source_before_a_safe_commit(
            bool targetReady, bool sourceEligible, bool offscreen, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanCommitReplacement(
                targetReady, sourceEligible, offscreen));
        }

        [Theory]
        [InlineData(true, true, true, true, true)]
        [InlineData(false, true, true, true, false)]
        [InlineData(true, false, true, true, false)]
        [InlineData(true, true, false, true, false)]
        [InlineData(true, true, true, false, false)]
        public void Streaming_rechecks_world_source_and_destination_before_create(
            bool worldSafe, bool sourceEligible, bool destinationFar,
            bool destinationExterior, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanCreateAfterStreaming(
                worldSafe, sourceEligible, destinationFar, destinationExterior));
        }

        [Theory]
        [InlineData(true, true, true, true, true, true)]
        [InlineData(true, true, false, true, true, false)]
        [InlineData(true, false, true, true, true, false)]
        [InlineData(true, true, true, false, true, false)]
        [InlineData(true, true, true, true, false, false)]
        public void Hidden_staged_ped_also_requires_an_off_camera_coordinate(
            bool exists, bool entityOffScreen, bool coordinateOffCamera,
            bool safeDestination, bool exterior, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.IsStagedDestinationSafe(
                exists, entityOffScreen, coordinateOffCamera, safeDestination,
                exterior));
        }

        [Theory]
        [InlineData(true, true, true)]
        [InlineData(false, true, false)]
        [InlineData(true, false, false)]
        public void Suppression_cleanup_only_releases_the_matching_owned_ped(
            bool exists, bool expectedModel, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanReleaseTrackedPed(
                exists, expectedModel));
        }

        [Fact]
        public void Cleanup_never_relinquishes_a_tracked_ped_claimed_by_a_mission()
        {
            Assert.True(PedPopulationPolicy.CanReleaseTrackedPed(true, true, false));
            Assert.False(PedPopulationPolicy.CanReleaseTrackedPed(true, true, true));
        }

        [Theory]
        [InlineData(true, true, true, true)]
        [InlineData(false, true, true, false)]
        [InlineData(true, false, true, false)]
        [InlineData(true, true, false, false)]
        public void Retained_ped_is_only_relinquished_when_this_script_still_owns_it(
            bool exists, bool expectedModel, bool belongsToThisScript, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanRelinquishOwnedPed(
                exists, expectedModel, belongsToThisScript));
        }

        [Theory]
        [InlineData(1000, 1000, 90000, true)]
        [InlineData(91000, 1000, 90000, true)]
        [InlineData(91001, 1000, 90000, false)]
        [InlineData(int.MinValue + 10, int.MaxValue - 20, 40, true)]
        [InlineData(int.MinValue + 21, int.MaxValue - 20, 40, false)]
        public void Added_peds_are_retained_until_the_bounded_ownership_window_expires(
            int now, int addedAt, int retentionMilliseconds, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.ShouldRetainTrackedPed(
                now, addedAt, retentionMilliseconds));
        }

        [Theory]
        [InlineData(false, true, true, false)]
        [InlineData(true, false, true, false)]
        [InlineData(true, true, false, false)]
        [InlineData(true, true, true, true)]
        public void Human_ped_validation_happens_after_the_model_has_loaded(
            bool loaded, bool isPed, bool isHumanPed, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanUseLoadedPedModel(
                loaded, isPed, isHumanPed));
        }

        [Theory]
        [InlineData(0, 0, false)]
        [InlineData(0, 1, true)]
        [InlineData(19, 20, true)]
        [InlineData(20, 20, false)]
        [InlineData(20, 99, false)]
        public void Added_population_is_hard_capped(int active, int maximum,
            bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanAdd(active, maximum));
        }

        [Theory]
        [InlineData(false, 4)]
        [InlineData(true, 2)]
        public void Scans_are_bounded_under_normal_and_throttled_load(
            bool throttled, int expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CandidateBudget(throttled));
        }

        [Theory]
        [InlineData(false, 0, 3000, false, false, false, 0)]
        [InlineData(false, 2999, 3000, false, false, false, 0)]
        [InlineData(false, 3000, 3000, false, false, false, 3)]
        [InlineData(true, 10, 3000, true, true, true, 2)]
        [InlineData(false, 10, 3000, true, false, true, 2)]
        [InlineData(false, 10, 3000, true, true, false, 2)]
        [InlineData(false, 10, 3000, true, true, true, 1)]
        public void Pending_streaming_operation_is_incremental_and_fails_closed(
            bool cancelled, long elapsed, int timeout, bool loaded, bool usable,
            bool revalidated, int expected)
        {
            Assert.Equal((PedPopulationPendingAction)expected,
                PedPopulationPolicy.AdvancePending(cancelled, elapsed, timeout,
                    loaded, usable, revalidated));
        }

        [Theory]
        [InlineData(false, false, false, false, 0, 3, true, 0)]
        [InlineData(false, true, true, true, 0, 3, true, 1)]
        [InlineData(false, true, false, false, 0, 3, true, 2)]
        [InlineData(false, true, true, false, 2, 3, true, 2)]
        [InlineData(false, true, false, false, 3, 3, true, 3)]
        [InlineData(false, true, false, false, 0, 3, false, 0)]
        [InlineData(true, true, true, true, 0, 3, true, 4)]
        public void Model_metadata_retries_are_bounded_and_never_bypass_human_gate(
            bool cancelled, bool loaded, bool isPed, bool isHumanPed,
            int priorFailures, int maximumRetries, bool retryDue, int expected)
        {
            Assert.Equal((PedPopulationMetadataAction)expected,
                PedPopulationPolicy.DecideModelMetadata(cancelled, loaded, isPed,
                    isHumanPed, priorFailures, maximumRetries, retryDue));
        }

        [Theory]
        [InlineData(1, 100)]
        [InlineData(2, 200)]
        [InlineData(3, 400)]
        [InlineData(9, 400)]
        public void Invalid_metadata_backoff_is_tick_bounded(int failure,
            int expectedMilliseconds)
        {
            Assert.Equal(expectedMilliseconds,
                PedPopulationPolicy.MetadataRetryDelayMilliseconds(failure));
        }

        [Theory]
        [InlineData(1000, 0, true)]
        [InlineData(1099, 1100, false)]
        [InlineData(1100, 1100, true)]
        [InlineData(int.MinValue + 10, int.MaxValue - 20, true)]
        public void Metadata_rechecks_wait_for_their_backoff_tick(int now,
            int retryNotBefore, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.IsMetadataRetryDue(now,
                retryNotBefore));
        }

        [Theory]
        [InlineData(true, true, true, true, true, true, true)]
        [InlineData(false, true, true, true, true, true, false)]
        [InlineData(true, false, true, true, true, true, false)]
        [InlineData(true, true, false, true, true, true, false)]
        [InlineData(true, true, true, false, true, true, false)]
        public void Pending_create_rejects_disappeared_or_stale_source_before_native_create(
            bool exists, bool exactModel, bool eligible, bool worldSafe,
            bool far, bool exterior, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanRevalidatePendingSource(
                exists, exactModel, eligible, worldSafe, far, exterior));
        }

        [Theory]
        [InlineData(2, true)]
        [InlineData(3, false)]
        public void Per_window_native_work_budget_prevents_scan_spikes(long elapsed,
            bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.WithinWorkBudget(elapsed));
        }

        [Theory]
        [InlineData(0, 4, false, true)]
        [InlineData(1, 4, false, false)]
        [InlineData(1, 4, true, true)]
        [InlineData(4, 4, true, false)]
        public void Slow_nearby_query_still_allows_one_unseen_candidate(
            int inspected, int budget, bool withinBudget, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.CanInspectCandidate(
                inspected, budget, withinBudget));
        }

        [Theory]
        [InlineData(false, 3000, 0, true)]
        [InlineData(false, 2999, 0, false)]
        [InlineData(true, 6000, 0, true)]
        [InlineData(true, 5999, 0, false)]
        public void Work_cadence_is_three_seconds_normally_and_six_when_throttled(
            bool throttled, int now, int lastWork, bool expected)
        {
            Assert.Equal(expected, PedPopulationPolicy.IsWorkDue(now, lastWork,
                throttled));
        }

        [Fact]
        public void Ped_catalog_requires_exact_schema_and_declared_dlc_pack()
        {
            const string json = "{\"schema_version\":1,\"id\":\"peds\",\"name\":\"Peds\",\"peds\":[{\"model\":\"acme_ped\",\"name\":\"ACME Ped\",\"source_pack\":\"acmepack\"}]}";
            var records = RuntimePedCatalog.ParseForTests(json, "acme.peds",
                "peds", new[] { "acmepack" });
            Assert.Single(records);
            Assert.Equal("acme_ped", records[0].Model);
            Assert.Throws<InvalidDataException>(() => RuntimePedCatalog.ParseForTests(
                json, "acme.peds", "peds", Array.Empty<string>()));
            Assert.Throws<InvalidDataException>(() => RuntimePedCatalog.ParseForTests(
                json.Replace("\"name\":\"ACME Ped\",", ""),
                "acme.peds", "peds", new[] { "acmepack" }));
        }
    }
}
