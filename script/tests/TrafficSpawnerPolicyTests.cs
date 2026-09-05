using ALLIN1;
using GTA;
using GTA.Math;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class TrafficSpawnerPolicyTests
    {
        [Theory]
        [InlineData(0f, 20f)]
        [InlineData(0.5f, 20f)]
        [InlineData(8f, 12f)]
        [InlineData(18f, 18f)]
        [InlineData(45f, 30f)]
        public void Replacement_drivers_always_receive_a_useful_cruise_speed(
            float captured, float expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.GetTrafficCruiseSpeed(captured));
        }

        [Theory]
        [InlineData(true, true, true)]
        [InlineData(true, false, false)]
        [InlineData(false, false, true)]
        public void Moving_source_is_never_committed_without_its_driver(
            bool sourceHadDriver, bool driverTransferred, bool expected)
        {
            Assert.Equal(expected, TrafficSpawner.CanCommitReplacement(
                sourceHadDriver, driverTransferred));
        }

        [Theory]
        [InlineData(true, true, 15f, true)]
        [InlineData(true, true, 0f, true)]
        [InlineData(false, false, 0f, true)]
        [InlineData(false, false, 0.75f, true)]
        [InlineData(false, false, 0.76f, false)]
        [InlineData(false, true, 0f, false)]
        [InlineData(false, false, float.NaN, false)]
        public void Driven_and_stationary_sources_remain_replaceable_without_ghosts(
            bool hasDriver, bool hasAnyOccupant, float speed, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.CanStageSourceReplacement(
                    hasDriver, hasAnyOccupant, speed));
        }

        [Theory]
        [InlineData(0, false)]
        [InlineData(1, true)]
        [InlineData(4, true)]
        public void Empty_replacements_do_not_yield_for_nonexistent_clones(
            int occupants, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.RequiresCloneSettlement(occupants));
        }

        [Theory]
        [InlineData(true, true, true, 0)]
        [InlineData(false, true, true, 1)]
        [InlineData(false, false, false, 1)]
        [InlineData(true, false, true, 2)]
        [InlineData(true, true, false, 3)]
        public void Replacement_validation_distinguishes_normal_source_churn(
            bool occupantsCloned, bool commitAllowed, bool sourceUnchanged,
            int expected)
        {
            Assert.Equal(
                (TrafficSpawner.ReplacementValidationOutcome)expected,
                TrafficSpawner.EvaluateReplacementValidation(
                    occupantsCloned, commitAllowed, sourceUnchanged));
        }

        [Theory]
        [InlineData(1000, int.MinValue, true)]
        [InlineData(1000, 1000, false)]
        [InlineData(30999, 1000, false)]
        [InlineData(31000, 1000, true)]
        public void Source_churn_diagnostics_are_rate_limited(
            int now, int lastDiagnosticTime, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.ShouldEmitSourceChangeDiagnostic(
                    now, lastDiagnosticTime));
        }

        [Theory]
        [InlineData(false, 24)]
        [InlineData(true, 12)]
        public void Replacement_scan_work_is_strictly_bounded(
            bool throttled, int expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.GetScanCandidateBudget(throttled));
        }

        [Theory]
        [InlineData(14999, false, false)]
        [InlineData(15000, false, true)]
        [InlineData(29999, true, false)]
        [InlineData(30000, true, true)]
        public void Expensive_traffic_work_uses_one_shared_staggered_budget(
            int elapsed, bool throttled, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.IsTrafficWorkDue(elapsed, 0, throttled));
        }

        [Theory]
        [InlineData(false, false, false, 0)]
        [InlineData(true, false, false, 1)]
        [InlineData(false, true, false, 2)]
        [InlineData(true, true, false, 1)]
        [InlineData(true, true, true, 2)]
        public void Due_traffic_paths_alternate_instead_of_bursting_together(
            bool drivenDue, bool replacementDue, bool preferReplacement,
            int expected)
        {
            Assert.Equal((TrafficSpawner.TrafficWorkKind)expected,
                TrafficSpawner.SelectTrafficWork(
                    drivenDue, replacementDue, preferReplacement));
        }

        [Theory]
        [InlineData(false, true, false, false, false, false, false, false, 1)]
        [InlineData(true, true, false, false, false, false, false, false, 1)]
        [InlineData(true, true, true, false, false, false, false, false, 1)]
        [InlineData(true, true, true, true, true, true, false, false, 1)]
        [InlineData(true, true, true, true, false, true, false, false, 2)]
        [InlineData(true, true, true, true, false, true, true, false, 0)]
        [InlineData(true, true, true, true, false, false, false, true, 1)]
        [InlineData(true, true, true, true, false, false, false, false, 0)]
        [InlineData(true, false, false, false, false, false, false, false, 0)]
        public void Managed_traffic_releases_normal_occupancy_changes_without_deleting(
            bool vehicleExists, bool requiresDriver, bool driverExists,
            bool driverInSeat, bool claimedByPlayer, bool purge,
            bool vehicleOnScreen, bool tooFar, int expected)
        {
            Assert.Equal((TrafficSpawner.ManagedTrafficAction)expected,
                TrafficSpawner.DecideManagedTrafficAction(
                    vehicleExists, requiresDriver, driverExists, driverInSeat,
                    claimedByPlayer, purge, vehicleOnScreen, tooFar));
        }

        [Theory]
        [InlineData("mission_active", true)]
        [InlineData("cutscene_active", true)]
        [InlineData("player_switch", true)]
        [InlineData("interior", true)]
        [InlineData("wanted_level", true)]
        [InlineData("player_unavailable", false)]
        [InlineData("garage_transition", false)]
        [InlineData("", false)]
        public void Unsafe_gameplay_transitions_release_managed_traffic_pairs(
            string suppression, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.ShouldPurgeManagedTraffic(suppression));
        }

        [Theory]
        [InlineData(-807.7f, 187.0f, 72.5f, true)]
        [InlineData(-25.3f, -1431.1f, 30.8f, true)]
        [InlineData(13.5f, 549.2f, 175.7f, true)]
        [InlineData(1977.0f, 3823.0f, 32.5f, true)]
        [InlineData(0f, 0f, 30f, false)]
        [InlineData(-807.7f, 187.0f, 100f, false)]
        public void Only_story_safehouse_parking_zones_are_spatially_protected(
            float x, float y, float z, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.IsInsideSafehouseGarageZone(new Vector3(x, y, z)));
        }

        [Theory]
        [InlineData(false, false, false)]
        [InlineData(false, true, false)]
        [InlineData(true, false, false)]
        [InlineData(true, true, true)]
        public void Package_traffic_requires_item_and_package_opt_in(
            bool itemEnabled, bool packageEnabled, bool expected)
        {
            Assert.Equal(expected, TrafficSpawner.IsPackageTrafficEnabled(
                itemEnabled, packageEnabled));
        }

        [Theory]
        [InlineData(false, false, 1)]
        [InlineData(true, false, 0)]
        [InlineData(false, true, 2)]
        [InlineData(true, true, 2)]
        public void Selected_models_are_probed_once_or_rejected_from_quarantine(
            bool validated, bool quarantined, int expected)
        {
            Assert.Equal(
                (TrafficSpawner.SelectedModelValidationAction)expected,
                TrafficSpawner.DecideSelectedModelValidation(
                    validated, quarantined));
        }

        [Fact]
        public void Selected_model_cache_validates_once_and_quarantines_failures()
        {
            var cache = new TrafficSpawner.SelectedModelValidationCache();

            Assert.Equal(TrafficSpawner.SelectedModelValidationAction.ProbeOnce,
                cache.GetAction("edition_model"));
            cache.MarkValidated("edition_model");
            Assert.Equal(
                TrafficSpawner.SelectedModelValidationAction.UseCachedValidation,
                cache.GetAction("EDITION_MODEL"));
            Assert.True(cache.Quarantine("edition_model"));
            Assert.False(cache.Quarantine("edition_model"));
            Assert.Equal(
                TrafficSpawner.SelectedModelValidationAction.RejectQuarantined,
                cache.GetAction("edition_model"));
        }

        [Theory]
        [InlineData(0, 5000, false)]
        [InlineData(4999, 5000, false)]
        [InlineData(5000, 5000, true)]
        [InlineData(5001, 5000, true)]
        public void Model_streaming_uses_one_bounded_deadline(
            long elapsedMilliseconds, int timeoutMilliseconds, bool expected)
        {
            Assert.Equal(expected, TrafficSpawner.HasModelLoadTimedOut(
                elapsedMilliseconds, timeoutMilliseconds));
        }

        [Theory]
        [InlineData(false, false, false)]
        [InlineData(false, true, false)]
        [InlineData(true, false, false)]
        [InlineData(true, true, true)]
        public void Traffic_disabled_baseline_registers_no_runtime_handlers(
            bool packageEnabled, bool trafficEnabled, bool expected)
        {
            Assert.Equal(expected,
                TrafficSpawner.ShouldAttachRuntimeHandlers(
                    packageEnabled, trafficEnabled));
        }

        [Fact]
        public void Package_traffic_candidate_is_default_off_without_opt_in()
        {
            var decision = TrafficSpawner.EvaluatePackageTrafficCandidate(
                false, "package_model", "sports",
                true, true, VehicleClass.Sports, out _);

            Assert.Equal(
                TrafficSpawner.PackageTrafficCandidateDecision.TrafficDisabled,
                decision);
        }

        [Theory]
        [InlineData("compacts", VehicleClass.Compacts)]
        [InlineData("coupes", VehicleClass.Coupes)]
        [InlineData("sedans", VehicleClass.Sedans)]
        [InlineData("suvs", VehicleClass.SUVs)]
        [InlineData("muscle", VehicleClass.Muscle)]
        [InlineData("sports", VehicleClass.Sports)]
        [InlineData("sportsclassics", VehicleClass.SportsClassics)]
        [InlineData("super", VehicleClass.Super)]
        [InlineData("offroad", VehicleClass.OffRoad)]
        [InlineData("motorcycles", VehicleClass.Motorcycles)]
        [InlineData("vans", VehicleClass.Vans)]
        public void Package_road_categories_map_to_their_exact_native_class(
            string category, VehicleClass expected)
        {
            Assert.True(TrafficSpawner.TryMapPackageRoadCategory(
                category, out VehicleClass actual));
            Assert.Equal(expected, actual);
        }

        [Theory]
        [InlineData("boats")]
        [InlineData("helicopters")]
        [InlineData("planes")]
        [InlineData("openwheel")]
        [InlineData("emergency")]
        [InlineData("")]
        public void Non_road_package_categories_are_rejected(string category)
        {
            var decision = TrafficSpawner.EvaluatePackageTrafficCandidate(
                true, "package_model", category,
                true, true, VehicleClass.Boats, out _);

            Assert.Equal(
                TrafficSpawner.PackageTrafficCandidateDecision
                    .UnsupportedCategory,
                decision);
        }

        [Fact]
        public void Package_vehicle_class_must_match_its_declared_category()
        {
            var decision = TrafficSpawner.EvaluatePackageTrafficCandidate(
                true, "package_model", "sports",
                true, true, VehicleClass.Super, out VehicleClass declared);

            Assert.Equal(VehicleClass.Sports, declared);
            Assert.Equal(
                TrafficSpawner.PackageTrafficCandidateDecision.ClassMismatch,
                decision);
        }

        [Fact]
        public void Unavailable_package_vehicle_is_rejected_before_pooling()
        {
            var decision = TrafficSpawner.EvaluatePackageTrafficCandidate(
                true, "missing_addon_model", "sports",
                false, true, VehicleClass.Sports, out _);

            Assert.Equal(
                TrafficSpawner.PackageTrafficCandidateDecision.ModelUnavailable,
                decision);
        }

        [Fact]
        public void Enabled_available_matching_package_vehicle_is_eligible()
        {
            var decision = TrafficSpawner.EvaluatePackageTrafficCandidate(
                true, "package_model", "sports",
                true, true, VehicleClass.Sports, out VehicleClass declared);

            Assert.Equal(VehicleClass.Sports, declared);
            Assert.Equal(
                TrafficSpawner.PackageTrafficCandidateDecision.Eligible,
                decision);
        }
    }
}
