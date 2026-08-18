using ALLIN1;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class NpcPhysicsExperimentPolicyTests
    {
        [Fact]
        public void Ambient_human_with_fresh_weapon_damage_can_react()
        {
            Assert.True(ShouldReact());
        }

        [Theory]
        [InlineData(false, true, true, true, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, false, true, true, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, false, true, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, false, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, true, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, true, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, true, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, false, true, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, false, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, true, 200, 200, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, true, 200, 201, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, true, 200, 180, 899)]
        public void Unsafe_or_stale_candidates_are_excluded(
            bool enabled, bool exists, bool human, bool alive, bool player,
            bool mission, bool persistent, bool inVehicle, bool weaponDamage,
            int oldHealth, int newHealth, int elapsed)
        {
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReact(
                enabled, exists, human, alive, player, mission, persistent,
                inVehicle, weaponDamage, oldHealth, newHealth, elapsed));
        }

        [Theory]
        [InlineData(31086, (int)NpcPhysicsBodyRegion.Head)]
        [InlineData(39317, (int)NpcPhysicsBodyRegion.Neck)]
        [InlineData(23553, (int)NpcPhysicsBodyRegion.Gut)]
        [InlineData(18905, (int)NpcPhysicsBodyRegion.Arm)]
        [InlineData(63931, (int)NpcPhysicsBodyRegion.Leg)]
        [InlineData(24817, (int)NpcPhysicsBodyRegion.Torso)]
        public void Damage_bones_map_to_region_specific_reactions(
            int bone, int expected)
        {
            Assert.Equal((NpcPhysicsBodyRegion)expected,
                NpcPhysicsExperimentPolicy.ClassifyBone(bone));
        }

        [Theory]
        [InlineData(18905)]
        [InlineData(57005)]
        [InlineData(60309)]
        [InlineData(28422)]
        [InlineData(36029)]
        [InlineData(6286)]
        public void Skeletal_physics_and_ik_hand_bones_trigger_disarm_logic(
            int bone)
        {
            Assert.True(NpcPhysicsExperimentPolicy.IsWeaponHandBone(bone));
        }

        [Fact]
        public void Forearm_and_torso_hits_are_not_mistaken_for_hand_hits()
        {
            Assert.False(NpcPhysicsExperimentPolicy.IsWeaponHandBone(61163));
            Assert.False(NpcPhysicsExperimentPolicy.IsWeaponHandBone(31086));
            Assert.False(NpcPhysicsExperimentPolicy.IsWeaponHandBone(0));
        }

        [Fact]
        public void Weapon_recovery_waits_until_the_officer_is_safe_and_free()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldAttemptWeaponRecovery(
                true, true, true, false, false, false, false,
                5000, 4200, 18000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldAttemptWeaponRecovery(
                true, true, true, false, false, false, true,
                5000, 4200, 18000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldAttemptWeaponRecovery(
                true, true, true, false, false, true, false,
                5000, 4200, 18000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldAttemptWeaponRecovery(
                true, true, true, false, true, false, false,
                5000, 4200, 18000));
        }

        [Fact]
        public void Weapon_scavenging_only_accepts_nearby_safe_upgrades()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldTakeSafeWeapon(
                10, 30, true, 8f));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldTakeSafeWeapon(
                30, 10, true, 8f));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldTakeSafeWeapon(
                10, 30, false, 8f));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldTakeSafeWeapon(
                10, 30, true, 13f));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldTakeSafeWeapon(
                0, 0, true, 2f));
        }

        [Fact]
        public void Fresh_lethal_damage_can_receive_a_death_reaction()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldReactToLethalDamage(
                true, true, false, false, false, false, true,
                100, 0, true, 1000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReactToLethalDamage(
                true, true, false, true, false, false, true,
                100, 0, true, 1000));
        }

        [Fact]
        public void Slow_close_vehicle_contact_can_balance_without_a_shot()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldReactToVehicleBump(
                true, true, true, false, true, true,
                2.5f, 1.5f, 800));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReactToVehicleBump(
                true, true, true, false, true, true,
                0.2f, 1.5f, 800));
        }

        [Theory]
        [InlineData(0.35f, false)]
        [InlineData(2.5f, false)]
        [InlineData(6.99f, false)]
        [InlineData(7.0f, true)]
        [InlineData(12.0f, true)]
        public void Only_high_speed_vehicle_impacts_force_script_ragdoll(
            float vehicleSpeed, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.ShouldForceVehicleImpactRagdoll(
                    vehicleSpeed));
        }

        [Fact]
        public void Armor_only_damage_counts_as_fresh_vitality_loss()
        {
            Assert.True(NpcPhysicsExperimentPolicy.HasFreshVitalityLoss(
                200, 100, 200, 80));
            Assert.False(NpcPhysicsExperimentPolicy.HasFreshVitalityLoss(
                200, 100, 200, 100));
        }

        [Fact]
        public void Fire_damage_and_close_player_pushes_can_react()
        {
            Assert.True(
                NpcPhysicsExperimentPolicy.ShouldReactToEnvironmentalDamage(
                    true, true, true, false, true, true, false, 1000));
            Assert.True(NpcPhysicsExperimentPolicy.ShouldReactToPedPush(
                true, true, true, false, true, 1.2f, 1.0f, 1000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReactToPedPush(
                true, true, true, false, true, 0.2f, 1.0f, 1000));
        }

        [Theory]
        [InlineData(0.20f, 0.10f, 0.35f, true)]
        [InlineData(0.20f, -4.00f, 0.35f, false)]
        [InlineData(0.75f, 0.00f, 0.35f, false)]
        [InlineData(0.20f, 0.10f, 0.95f, false)]
        public void Ground_injury_requires_ground_contact_not_just_a_fall(
            float height, float verticalSpeed, float uprightValue, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.IsPhysicallyGrounded(
                    height, verticalSpeed, uprightValue));
        }

        [Fact]
        public void Follow_on_reaction_damage_is_not_an_ambiguous_miss()
        {
            Assert.Equal("follow_on_active_reaction",
                NpcPhysicsExperimentPolicy.ClassifyUnreactedVitalityLoss(
                    true, false, false, false, false, false,
                    true, false, 100));
            Assert.Equal("missing_damage_provenance",
                NpcPhysicsExperimentPolicy.ClassifyUnreactedVitalityLoss(
                    true, false, false, false, false, true,
                    false, false, 1200));
        }

        [Fact]
        public void Blast_reaction_requires_fresh_damage_near_an_explosion()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldReactToBlast(
                true, true, true, false, true, true, 1000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReactToBlast(
                true, true, true, false, true, false, 1000));
        }

        [Fact]
        public void Trauma_chances_are_repeatable_for_the_same_event()
        {
            bool first = NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 30);
            bool second = NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 30);
            Assert.Equal(first, second);
            Assert.False(NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 0));
            Assert.True(NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 100));
        }

        [Fact]
        public void Injured_ally_rescue_requires_a_live_grounded_ambient_casualty()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldRequestCohesionAid(
                true, true, true, false, true, true,
                45, 100, 20000, 0, 3));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldRequestCohesionAid(
                true, true, true, false, true, false,
                45, 100, 20000, 0, 3));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldRequestCohesionAid(
                true, true, true, false, true, true,
                69, 100, 20000, 0, 3));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldRequestCohesionAid(
                true, true, true, false, true, true,
                45, 100, 20000, 3, 3));
        }

        [Theory]
        [InlineData(false, 0, true)]
        [InlineData(false, 1, true)]
        [InlineData(true, 4, true)]
        [InlineData(false, 2, false)]
        [InlineData(false, 3, false)]
        [InlineData(false, 4, false)]
        [InlineData(false, 5, false)]
        public void Rescue_roles_require_an_actual_ally(
            bool sameGroup, int relationship, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.IsCohesionAlly(
                    sameGroup, relationship));
        }

        [Fact]
        public void Responder_must_be_healthy_close_and_available()
        {
            Assert.True(NpcPhysicsExperimentPolicy.CanProvideCohesionAid(
                true, true, false, false, false, true,
                70, 100, 12f));
            Assert.False(NpcPhysicsExperimentPolicy.CanProvideCohesionAid(
                true, true, false, false, false, true,
                50, 100, 12f));
            Assert.False(NpcPhysicsExperimentPolicy.CanProvideCohesionAid(
                true, true, false, false, true, true,
                70, 100, 12f));
            Assert.False(NpcPhysicsExperimentPolicy.CanProvideCohesionAid(
                true, true, false, false, false, true,
                70, 100, 23f));
        }

        [Theory]
        [InlineData(true, false, false, false, false, false, true)]
        [InlineData(true, false, false, true, true, false, false)]
        [InlineData(true, false, false, true, true, true, true)]
        [InlineData(false, false, false, false, false, true, false)]
        [InlineData(true, true, false, false, false, true, false)]
        [InlineData(true, false, true, false, false, true, false)]
        public void Open_world_hostile_law_can_override_runtime_entity_flags(
            bool human, bool player, bool dead, bool persistent,
            bool missionEntity, bool lawOverride, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.CanUseCohesionEntity(
                    human, player, dead, persistent, missionEntity,
                    lawOverride));
        }

        [Fact]
        public void Stabilization_is_bounded_and_never_revives_a_dead_ped()
        {
            Assert.Equal(58,
                NpcPhysicsExperimentPolicy.StabilizedHealth(20, 100));
            Assert.Equal(100,
                NpcPhysicsExperimentPolicy.StabilizedHealth(95, 100));
            Assert.Equal(0,
                NpcPhysicsExperimentPolicy.StabilizedHealth(0, 100));
        }

        [Theory]
        [InlineData(0, true)]
        [InlineData(1, true)]
        [InlineData(2, false)]
        [InlineData(7, false)]
        public void Rappel_task_status_is_detected_without_animation_guessing(
            int status, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.IsRappelTaskActive(status));
        }

        [Fact]
        public void Story_and_cutscene_rappellers_are_not_overridden()
        {
            Assert.True(NpcPhysicsExperimentPolicy.CanTrackFastRopeFall(
                true, true, true, false, false, false, false));
            Assert.False(NpcPhysicsExperimentPolicy.CanTrackFastRopeFall(
                true, true, true, false, false, true, false));
            Assert.False(NpcPhysicsExperimentPolicy.CanTrackFastRopeFall(
                true, true, true, false, false, false, true));
        }

        [Fact]
        public void Only_an_airborne_rappel_task_exit_is_uncontrolled()
        {
            Assert.True(NpcPhysicsExperimentPolicy.IsUncontrolledRappelExit(
                true, true, false, 4f, -3f, true, false));
            Assert.False(NpcPhysicsExperimentPolicy.IsUncontrolledRappelExit(
                true, true, false, 0.3f, 0f, false, false));
            Assert.False(NpcPhysicsExperimentPolicy.IsUncontrolledRappelExit(
                false, true, false, 4f, -3f, true, false));
        }

        [Theory]
        [InlineData(true, false, 0.1f, 0f, false, false, true)]
        [InlineData(false, true, 5f, -0.4f, false, false, true)]
        [InlineData(false, true, 5f, 1.2f, false, false, false)]
        [InlineData(false, true, 0.3f, -3f, true, true, false)]
        [InlineData(false, false, 5f, -3f, true, true, false)]
        public void Rappel_helicopter_proximity_recovers_missed_native_tasks(
            bool nativeTask, bool nearbyHelicopter, float height,
            float verticalSpeed, bool falling, bool ragdoll,
            bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.IsLikelyFastRopeDescent(
                    nativeTask, nearbyHelicopter, height,
                    verticalSpeed, falling, ragdoll));
        }

        [Fact]
        public void Unsafe_seated_rappel_is_cancelled_only_in_an_active_fire_zone()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldCancelUnsafeRappelTask(
                true, false, false, 4, true, 55f, true, true));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldCancelUnsafeRappelTask(
                true, false, false, 4, false, 55f, true, true));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldCancelUnsafeRappelTask(
                true, false, false, 4, true, 100f, true, true));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldCancelUnsafeRappelTask(
                true, true, false, 4, true, 55f, true, true));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldCancelUnsafeRappelTask(
                true, false, false, 4, true, 55f, false, true));
        }

        [Theory]
        [InlineData(true, false, false, 3, true, 70f, true, true)]
        [InlineData(true, false, false, 4, false, 70f, true, true)]
        [InlineData(true, false, false, 3, false, 70f, true, false)]
        [InlineData(true, false, false, 4, false, 106f, true, false)]
        [InlineData(true, true, false, 4, true, 70f, true, false)]
        public void Rappel_departure_is_locked_before_the_exit_task_commits(
            bool enabled, bool mission, bool cutscene, int wanted,
            bool activeFireZone, float distance, bool seated, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.ShouldBlockUnsafeRappelInsertion(
                    enabled, mission, cutscene, wanted, activeFireZone,
                    distance, seated));
        }

        [Fact]
        public void Ambient_rappel_requests_are_redirected_to_a_tactical_zone()
        {
            Assert.True(NpcPhysicsExperimentPolicy
                .ShouldRedirectRappelToTacticalZone(
                    true, false, false, 3, true, true));
            Assert.False(NpcPhysicsExperimentPolicy
                .ShouldRedirectRappelToTacticalZone(
                    true, true, false, 3, true, true));
            Assert.False(NpcPhysicsExperimentPolicy
                .ShouldRedirectRappelToTacticalZone(
                    true, false, false, 1, true, true));
            Assert.False(NpcPhysicsExperimentPolicy
                .ShouldRedirectRappelToTacticalZone(
                    true, false, false, 3, true, false));
        }

        [Theory]
        [InlineData(12f, true, 8f, true)]
        [InlineData(7.9f, true, 8f, false)]
        [InlineData(12f, false, 8f, false)]
        [InlineData(12f, true, 18.1f, false)]
        public void Just_started_unsafe_rappel_is_recovered_into_its_seat(
            float helicopterHeight, bool seatFree,
            float distance, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.ShouldRecoverUnsafeRappelExit(
                    helicopterHeight, seatFree, distance));
        }

        [Theory]
        [InlineData(false, 600, 100f, 0f, false, true)]
        [InlineData(true, 600, 100f, 0f, false, false)]
        [InlineData(true, 4000, 20f, 0f, false, true)]
        [InlineData(true, 6000, 100f, 40f, false, false)]
        [InlineData(true, 4000, 100f, 0f, true, true)]
        [InlineData(true, 10000, 100f, 0f, false, false)]
        [InlineData(true, 16000, 100f, 0f, false, false)]
        public void Aerial_orbit_commands_advance_by_state_not_guard_ticks(
            bool hasTarget, int age, float targetDistance,
            float anchorShift, bool unsafeDrift, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.ShouldIssueAerialOrbitCommand(
                    hasTarget, age, targetDistance,
                    anchorShift, unsafeDrift));
        }

        [Theory]
        [InlineData(true, false, 18000, 12000, 50f, true)]
        [InlineData(true, false, 17000, 12000, 50f, false)]
        [InlineData(true, false, 18000, 11000, 50f, false)]
        [InlineData(true, false, 18000, 12000, 35f, false)]
        [InlineData(true, true, 30000, 30000, 80f, false)]
        [InlineData(false, false, 30000, 30000, 80f, false)]
        public void Stalled_aerial_leg_relinquishes_script_control(
            bool hasTarget, bool relinquished, int age,
            int noProgress, float targetDistance, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy
                    .ShouldRelinquishAerialOrbitControl(
                        hasTarget, relinquished, age,
                        noProgress, targetDistance));
        }

        [Theory]
        [InlineData(true, 14f, 52f, false, 1f, true)]
        [InlineData(true, 14f, 52f, true, 0.9f, true)]
        [InlineData(true, 14f, 30f, false, 1f, false)]
        [InlineData(true, 5f, 52f, false, 1f, false)]
        [InlineData(true, 14f, 52f, true, 0.4f, false)]
        [InlineData(false, 14f, 52f, false, 1f, false)]
        public void Rappel_insertions_require_a_screened_rear_zone(
            bool line, float depth, float threatDistance,
            bool rooftop, float normalZ, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.CanUseAerialInsertionZone(
                    line, depth, threatDistance, rooftop, normalZ));
        }

        [Theory]
        [InlineData(8f, 16f, 3f, 1000, true)]
        [InlineData(11f, 16f, 3f, 1000, false)]
        [InlineData(8f, 6f, 3f, 1000, false)]
        [InlineData(8f, 16f, 7f, 1000, false)]
        [InlineData(8f, 16f, 3f, 999, false)]
        public void Rappel_crew_release_only_from_a_stable_hover(
            float horizontalDistance, float height,
            float speed, int stableMs, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.ShouldReleaseRappelCrew(
                    horizontalDistance, height, speed, stableMs));
        }

        [Fact]
        public void Hard_fast_rope_landing_gets_recovery_but_normal_dismount_does_not()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldApplyFastRopeRecovery(
                true, true, true, false, 0.2f,
                -4.5f, 2.2f, true, 750));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldApplyFastRopeRecovery(
                true, false, true, false, 0.2f,
                -4.5f, 2.2f, true, 750));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldApplyFastRopeRecovery(
                true, true, true, false, 0.2f,
                -1.4f, 0.7f, false, 750));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldApplyFastRopeRecovery(
                true, true, true, false, 1.2f,
                -5f, 3f, true, 750));
        }

        [Fact]
        public void Fast_rope_recovery_duration_scales_but_remains_bounded()
        {
            Assert.Equal(2600,
                NpcPhysicsExperimentPolicy.FastRopeRecoveryDuration(
                    -1f, 0.4f));
            Assert.InRange(
                NpcPhysicsExperimentPolicy.FastRopeRecoveryDuration(
                    -5f, 2.5f), 2601, 5199);
            Assert.Equal(5200,
                NpcPhysicsExperimentPolicy.FastRopeRecoveryDuration(
                    -20f, 20f));
        }

        [Fact]
        public void Aerial_recon_requires_open_world_hostile_law_aircraft_with_visual_contact()
        {
            Assert.True(NpcPhysicsExperimentPolicy.CanAssignAerialRecon(
                true, false, false, 2, true, true, true,
                true, true, true, true));
            Assert.False(NpcPhysicsExperimentPolicy.CanAssignAerialRecon(
                true, true, false, 2, true, true, true,
                true, true, true, true));
            Assert.False(NpcPhysicsExperimentPolicy.CanAssignAerialRecon(
                true, false, false, 0, true, true, true,
                true, true, true, true));
            Assert.False(NpcPhysicsExperimentPolicy.CanAssignAerialRecon(
                true, false, false, 2, true, true, true,
                true, true, true, false));
            Assert.False(NpcPhysicsExperimentPolicy.CanAssignAerialRecon(
                true, false, false, 2, true, true, false,
                true, true, true, true));
        }

        [Theory]
        [InlineData(true, false, false, 1, true, false, 0, true)]
        [InlineData(true, false, false, 0, true, false, 0, false)]
        [InlineData(true, false, false, 5, false, false, 0, false)]
        [InlineData(true, false, false, 5, true, true, 0, false)]
        [InlineData(true, false, false, 5, true, false, 1, false)]
        [InlineData(true, true, false, 5, true, false, 0, false)]
        [InlineData(true, false, true, 5, true, false, 0, false)]
        public void Dedicated_casevac_spawns_only_for_a_waiting_casualty(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool casualtyWaiting, bool active,
            int cooldownRemaining, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.ShouldSpawnDedicatedCasevac(
                    enabled, missionActive, cutsceneActive,
                    wantedLevel, casualtyWaiting, active,
                    cooldownRemaining));
        }

        [Theory]
        [InlineData(true, false, true, 0f, true)]
        [InlineData(true, false, true, 18f, true)]
        [InlineData(true, false, true, 18.1f, false)]
        [InlineData(false, false, true, 0f, false)]
        [InlineData(true, true, true, 0f, false)]
        [InlineData(true, false, false, 0f, false)]
        public void Casevac_batches_only_waiting_casualties_at_the_same_zone(
            bool waiting, bool assigned, bool freeSeat,
            float landingDistance, bool expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.CanBatchCasevacCasualty(
                    waiting, assigned, freeSeat, landingDistance));
        }

        [Fact]
        public void Dedicated_casevac_despawns_after_its_flyout()
        {
            Assert.False(
                NpcPhysicsExperimentPolicy.ShouldDespawnDedicatedCasevac(
                    true, true, 180f, 5000));
            Assert.True(
                NpcPhysicsExperimentPolicy.ShouldDespawnDedicatedCasevac(
                    true, true,
                    NpcPhysicsExperimentPolicy.
                        DedicatedCasevacDespawnDistance,
                    5000));
            Assert.True(
                NpcPhysicsExperimentPolicy.ShouldDespawnDedicatedCasevac(
                    true, true, 180f, 15000));
            Assert.False(
                NpcPhysicsExperimentPolicy.ShouldDespawnDedicatedCasevac(
                    true, false, 500f, 15000));
        }

        [Theory]
        [InlineData(120, 100, false, 120)]
        [InlineData(120, 100, true, 100)]
        [InlineData(120, 135, false, 120)]
        [InlineData(120, 120, false, 120)]
        [InlineData(0, 0, false, 0)]
        public void Stabilization_pins_passive_changes_but_accepts_damage(
            int holdingHealth, int currentHealth,
            bool directDamage, int expected)
        {
            Assert.Equal(expected,
                NpcPhysicsExperimentPolicy.ResolveStabilizedHoldingHealth(
                    holdingHealth, currentHealth, directDamage));
        }

        private static bool ShouldReact()
        {
            return NpcPhysicsExperimentPolicy.ShouldReact(
                enabled: true,
                exists: true,
                isHuman: true,
                isAlive: true,
                isPlayer: false,
                isMissionEntity: false,
                isPersistent: false,
                isInVehicle: false,
                hasWeaponDamage: true,
                previousHealth: 200,
                currentHealth: 180,
                elapsedSinceReactionMs: 1000);
        }
    }
}
