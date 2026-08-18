// NpcPhysicsExperiment.cs -- opt-in GTA IV/RDR-style ambient ped reactions.
//
// Runtime NaturalMotion messages provide the per-impact reactions. Optional
// archive tuning (physicstasks.ymt and behaviours.xml) complements this script
// for global fall, balance, impact, and bailout behavior.

using System;
using System.Collections.Generic;
using System.IO;
using GTA;
using GTA.Math;
using GTA.NaturalMotion;
using GTA.Native;

namespace ALLIN1
{
    internal enum NpcPhysicsBodyRegion
    {
        Torso,
        Gut,
        Head,
        Neck,
        Arm,
        Leg,
    }

    internal enum AerialSupportRole
    {
        Recon,
        Casevac,
    }

    internal static class NpcPhysicsExperimentPolicy
    {
        internal const int ReactionCooldownMs = 900;
        internal const int VehicleBumpCooldownMs = 700;
        internal const int PedPushCooldownMs = 850;
        internal const int CohesionRequestCooldownMs = 18000;
        internal const float HighSpeedVehicleImpactThreshold = 7f;
        internal const float InjuredAidHealthRatio = 0.68f;
        internal const float MinimumResponderHealthRatio = 0.65f;
        internal const float HardRappelLandingSpeed = -3.25f;
        internal const float HardRappelLandingDrop = 1.75f;
        internal const int WeaponRecoveryDelayMs = 4200;
        internal const int WeaponRecoveryTimeoutMs = 18000;
        internal const int AerialOrbitMinimumLegMs = 3000;
        internal const float AerialOrbitArrivalDistance = 24f;
        internal const int AerialOrbitStallMinimumAgeMs = 18000;
        internal const int AerialOrbitNoProgressMs = 12000;
        internal const float AerialOrbitProgressDistance = 5f;
        internal const int DedicatedCasevacSpawnCooldownMs = 20000;
        internal const float DedicatedCasevacDespawnDistance = 220f;

        internal static bool ShouldSpawnDedicatedCasevac(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool casualtyWaiting,
            bool casevacAlreadyActive, int spawnCooldownRemainingMs)
        {
            return enabled && !missionActive && !cutsceneActive &&
                wantedLevel > 0 && casualtyWaiting &&
                !casevacAlreadyActive &&
                spawnCooldownRemainingMs <= 0;
        }

        internal static bool CanBatchCasevacCasualty(
            bool awaitingCasevac, bool alreadyAssigned,
            bool freeSeat, float landingPointDistance)
        {
            return awaitingCasevac && !alreadyAssigned && freeSeat &&
                landingPointDistance <= 18f;
        }

        internal static bool ShouldDespawnDedicatedCasevac(
            bool dedicatedCasevac, bool departing,
            float distanceFromScene, int departureElapsedMs)
        {
            return dedicatedCasevac && departing &&
                (distanceFromScene >= DedicatedCasevacDespawnDistance ||
                 departureElapsedMs >= 15000);
        }

        internal static bool HasFreshVitalityLoss(
            int previousHealth, int previousArmor,
            int currentHealth, int currentArmor)
        {
            return currentHealth + Math.Max(0, currentArmor) <
                previousHealth + Math.Max(0, previousArmor);
        }

        internal static bool ShouldReact(
            bool enabled, bool exists, bool isHuman, bool isAlive,
            bool isPlayer, bool isMissionEntity, bool isPersistent,
            bool isInVehicle, bool hasWeaponDamage, int previousHealth,
            int currentHealth, int elapsedSinceReactionMs)
        {
            return enabled && exists && isHuman && isAlive && !isPlayer &&
                !isMissionEntity && !isPersistent && !isInVehicle &&
                hasWeaponDamage && currentHealth < previousHealth &&
                elapsedSinceReactionMs >= ReactionCooldownMs;
        }

        internal static bool ShouldReactToLethalDamage(
            bool enabled, bool isHuman, bool isPlayer, bool isMissionEntity,
            bool isPersistent, bool isInVehicle, bool wasAlive, int previousHealth,
            int currentHealth, bool hasWeaponDamage, int elapsedMs)
        {
            return enabled && isHuman && !isPlayer && !isMissionEntity &&
                !isPersistent && !isInVehicle && wasAlive && previousHealth > 0 &&
                currentHealth <= 0 && hasWeaponDamage &&
                elapsedMs >= ReactionCooldownMs;
        }

        internal static bool ShouldReactToVehicleBump(
            bool enabled, bool safeAmbientPed, bool isAlive,
            bool isInVehicle, bool collided, bool vehicleExists,
            float vehicleSpeed, float distance, int elapsedMs)
        {
            return enabled && safeAmbientPed && isAlive && !isInVehicle &&
                collided && vehicleExists && vehicleSpeed >= 0.35f &&
                distance <= 3.25f && elapsedMs >= VehicleBumpCooldownMs;
        }

        internal static bool ShouldForceVehicleImpactRagdoll(float vehicleSpeed)
        {
            return vehicleSpeed >= HighSpeedVehicleImpactThreshold;
        }

        internal static bool ShouldReactToBlast(
            bool enabled, bool safeAmbientPed, bool isAlive,
            bool isInVehicle, bool freshHealthLoss, bool nearExplosion,
            int elapsedMs)
        {
            return enabled && safeAmbientPed && isAlive && !isInVehicle &&
                freshHealthLoss && nearExplosion &&
                elapsedMs >= ReactionCooldownMs;
        }

        internal static bool ShouldReactToEnvironmentalDamage(
            bool enabled, bool safeAmbientPed, bool wasAlive,
            bool isInVehicle, bool freshVitalityLoss, bool onFire,
            bool nearExplosion, int elapsedMs)
        {
            return enabled && safeAmbientPed && wasAlive && !isInVehicle &&
                freshVitalityLoss && (onFire || nearExplosion) &&
                elapsedMs >= ReactionCooldownMs;
        }

        internal static bool ShouldReactToPedPush(
            bool enabled, bool safeAmbientPed, bool isAlive,
            bool isInVehicle, bool collided, float playerSpeed,
            float distance, int elapsedMs)
        {
            return enabled && safeAmbientPed && isAlive && !isInVehicle &&
                collided && playerSpeed >= 0.65f && distance <= 1.65f &&
                elapsedMs >= PedPushCooldownMs;
        }

        internal static bool IsPhysicallyGrounded(
            float heightAboveGround, float verticalSpeed, float uprightValue)
        {
            return heightAboveGround <= 0.45f &&
                Math.Abs(verticalSpeed) <= 1.25f && uprightValue <= 0.55f;
        }

        internal static bool ShouldRequestCohesionAid(
            bool enabled, bool safeAmbientPed, bool alive, bool inVehicle,
            bool activeDamageReaction, bool physicallyDown,
            int health, int maxHealth, int elapsedSinceRequestMs,
            int activeResponses, int maximumResponses)
        {
            if (!enabled || !safeAmbientPed || !alive || inVehicle ||
                !activeDamageReaction || !physicallyDown || maxHealth <= 0 ||
                health <= 0 || activeResponses >= maximumResponses ||
                elapsedSinceRequestMs < CohesionRequestCooldownMs)
                return false;
            return health <= Math.Max(1,
                (int)Math.Floor(maxHealth * InjuredAidHealthRatio));
        }

        internal static bool IsCohesionAlly(
            bool sameRelationshipGroup, int relationship)
        {
            // 0 and 1 are Rockstar's respect/like relationships.  Value 2 is
            // ignore, so it is intentionally not strong enough for rescue.
            return sameRelationshipGroup || relationship == 0 ||
                relationship == 1;
        }

        internal static bool CanProvideCohesionAid(
            bool safeAmbientPed, bool alive, bool inVehicle,
            bool physicallyDown, bool alreadyAssigned, bool allied,
            int health, int maxHealth, float distance)
        {
            return safeAmbientPed && alive && !inVehicle && !physicallyDown &&
                !alreadyAssigned && allied && maxHealth > 0 &&
                health >= Math.Ceiling(maxHealth *
                    MinimumResponderHealthRatio) &&
                distance <= 22f;
        }

        internal static bool CanUseCohesionEntity(
            bool human, bool player, bool dead,
            bool persistent, bool missionEntity,
            bool openWorldHostileLaw)
        {
            if (!human || player || dead) return false;
            return (!persistent && !missionEntity) || openWorldHostileLaw;
        }

        internal static int StabilizedHealth(int currentHealth, int maxHealth)
        {
            if (currentHealth <= 0 || maxHealth <= 0) return currentHealth;
            int minimumRecovery = currentHealth + 20;
            int stableFloor = (int)Math.Ceiling(maxHealth * 0.58f);
            return Math.Min(maxHealth, Math.Max(minimumRecovery, stableFloor));
        }

        internal static int ResolveStabilizedHoldingHealth(
            int stabilizedHealth, int currentHealth,
            bool directDamageObserved)
        {
            if (currentHealth <= 0 || stabilizedHealth <= 0)
                return currentHealth;
            if (directDamageObserved)
                return Math.Min(stabilizedHealth, currentHealth);
            return stabilizedHealth;
        }

        internal static bool IsRappelTaskActive(int taskStatus)
        {
            // Rockstar task status 0 is waiting-to-start and 1 is running.
            return taskStatus == 0 || taskStatus == 1;
        }

        internal static bool IsLikelyFastRopeDescent(
            bool nativeTaskActive, bool nearRappellingHelicopter,
            float heightAboveGround, float verticalSpeed,
            bool falling, bool ragdoll)
        {
            return nativeTaskActive ||
                (nearRappellingHelicopter && heightAboveGround > 0.65f &&
                 (verticalSpeed < 0.5f || falling || ragdoll));
        }

        internal static bool ShouldCancelUnsafeRappelTask(
            bool enhancedPoliceAi, bool missionActive,
            bool cutsceneActive, int wantedLevel,
            bool playerAggressive, float distanceToPlayer,
            bool occupantStillInHelicopter, bool rappelTaskActive)
        {
            return enhancedPoliceAi && !missionActive && !cutsceneActive &&
                wantedLevel >= 2 && playerAggressive &&
                distanceToPlayer <= 90f && occupantStillInHelicopter &&
                rappelTaskActive;
        }

        internal static bool ShouldBlockUnsafeRappelInsertion(
            bool enhancedPoliceAi, bool missionActive,
            bool cutsceneActive, int wantedLevel,
            bool activeFireZone, float distanceToPlayer,
            bool occupantStillInHelicopter)
        {
            return enhancedPoliceAi && !missionActive && !cutsceneActive &&
                wantedLevel >= 2 && (activeFireZone || wantedLevel >= 4) &&
                distanceToPlayer <= 105f && occupantStillInHelicopter;
        }

        internal static bool ShouldRedirectRappelToTacticalZone(
            bool enhancedPoliceAi, bool missionActive,
            bool cutsceneActive, int wantedLevel,
            bool occupantStillInHelicopter, bool rappelTaskActive)
        {
            return enhancedPoliceAi && !missionActive && !cutsceneActive &&
                wantedLevel >= 2 && occupantStillInHelicopter &&
                rappelTaskActive;
        }

        internal static bool ShouldRecoverUnsafeRappelExit(
            float helicopterHeight, bool originalSeatFree,
            float distanceToHelicopter)
        {
            return helicopterHeight >= 8f && originalSeatFree &&
                distanceToHelicopter <= 18f;
        }

        internal static bool ShouldIssueAerialOrbitCommand(
            bool hasMissionTarget, int commandAgeMs,
            float distanceToTarget, float anchorShift,
            bool unsafePerimeterDrift)
        {
            if (!hasMissionTarget) return true;
            if (unsafePerimeterDrift &&
                commandAgeMs >= AerialOrbitMinimumLegMs)
                return true;
            if (distanceToTarget <= AerialOrbitArrivalDistance &&
                commandAgeMs >= AerialOrbitMinimumLegMs)
                return true;
            // TASK_HELI_MISSION type 4 is a one-shot GoTo task.  Reissuing a
            // stale absolute waypoint can fight the ambient pilot AI and pin
            // the aircraft in a hover, so anchor age/shift are deliberately
            // not command triggers.
            return false;
        }

        internal static bool ShouldRelinquishAerialOrbitControl(
            bool hasMissionTarget, bool alreadyRelinquished,
            int commandAgeMs, int noProgressMs, float distanceToTarget)
        {
            return hasMissionTarget && !alreadyRelinquished &&
                commandAgeMs >= AerialOrbitStallMinimumAgeMs &&
                noProgressMs >= AerialOrbitNoProgressMs &&
                distanceToTarget > AerialOrbitArrivalDistance * 1.5f;
        }

        internal static bool CanUseAerialInsertionZone(
            bool firingLineEstablished, float depthBehindLine,
            float distanceFromThreat, bool rooftop,
            float surfaceNormalZ)
        {
            return firingLineEstablished && depthBehindLine >= 8f &&
                distanceFromThreat >= 40f &&
                (!rooftop || surfaceNormalZ >= 0.70f);
        }

        internal static bool ShouldReleaseRappelCrew(
            float horizontalDistanceToInsertion,
            float heightAboveInsertion, float helicopterSpeed,
            int stableElapsedMs)
        {
            return horizontalDistanceToInsertion <= 10f &&
                heightAboveInsertion >= 8f &&
                heightAboveInsertion <= 24f &&
                helicopterSpeed <= 6f && stableElapsedMs >= 1000;
        }

        internal static bool CanTrackFastRopeFall(
            bool enabled, bool human, bool alive, bool player,
            bool inVehicle, bool missionActive, bool cutsceneActive)
        {
            // Open-world wanted-service rappellers are often marked persistent
            // or as script entities.  The global story/cutscene guard protects
            // authored sequences without excluding those ambient responders.
            return enabled && human && alive && !player && !inVehicle &&
                !missionActive && !cutsceneActive;
        }

        internal static bool IsUncontrolledRappelExit(
            bool rappelWasObserved, bool taskWasActive,
            bool taskIsActive, float heightAboveGround,
            float verticalSpeed, bool falling, bool ragdoll)
        {
            return rappelWasObserved && taskWasActive && !taskIsActive &&
                heightAboveGround > 0.65f &&
                (ragdoll || falling || verticalSpeed < -1.0f);
        }

        internal static bool ShouldApplyFastRopeRecovery(
            bool rappelWasObserved, bool uncontrolledFall, bool alive,
            bool inVehicle, float heightAboveGround,
            float minimumVerticalSpeed, float verticalDrop,
            bool landedRagdolled, int fallElapsedMs)
        {
            if (!rappelWasObserved || !uncontrolledFall || !alive ||
                inVehicle || heightAboveGround > 0.48f ||
                fallElapsedMs < 100 || fallElapsedMs > 7000)
                return false;
            return landedRagdolled ||
                minimumVerticalSpeed <= HardRappelLandingSpeed ||
                verticalDrop >= HardRappelLandingDrop;
        }

        internal static int FastRopeRecoveryDuration(
            float minimumVerticalSpeed, float verticalDrop)
        {
            float speedSeverity = Math.Max(0f,
                Math.Abs(Math.Min(0f, minimumVerticalSpeed)) - 2.5f);
            float dropSeverity = Math.Max(0f, verticalDrop - 0.75f);
            int duration = 2600 + (int)Math.Round(
                speedSeverity * 320f + dropSeverity * 220f);
            return Math.Max(2600, Math.Min(5200, duration));
        }

        internal static bool CanAssignAerialRecon(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool helicopter, bool driveable,
            bool airborne, bool pilotAlive, bool lawCrew, bool hostileToPlayer,
            bool hasLineOfSight)
        {
            return enabled && !missionActive && !cutsceneActive &&
                wantedLevel > 0 && helicopter && driveable && pilotAlive &&
                airborne && lawCrew && hostileToPlayer && hasLineOfSight;
        }

        internal static string ClassifyUnreactedVitalityLoss(
            bool isHuman, bool isPlayer, bool isMissionEntity,
            bool isPersistent, bool isInVehicle, bool isAlive,
            bool activeReaction, bool weaponDamage, int elapsedMs)
        {
            if (!isHuman) return "non_human";
            if (isPlayer) return "player";
            if (isInVehicle) return "vehicle_occupant";
            if (activeReaction) return "follow_on_active_reaction";
            if (isMissionEntity) return "mission_entity";
            if (isPersistent) return "persistent_entity";
            if (!isAlive) return "dead_without_fresh_weapon_evidence";
            if (elapsedMs < ReactionCooldownMs) return "reaction_cooldown";
            if (!weaponDamage) return "missing_damage_provenance";
            return "unclassified";
        }

        internal static NpcPhysicsBodyRegion ClassifyBone(int bone)
        {
            switch (bone)
            {
                case 31086: return NpcPhysicsBodyRegion.Head;
                case 39317: return NpcPhysicsBodyRegion.Neck;
                case 11816:
                case 23553: return NpcPhysicsBodyRegion.Gut;
                case 64729:
                case 10706:
                case 45509:
                case 40269:
                case 61163:
                case 28252:
                case 18905:
                case 57005: return NpcPhysicsBodyRegion.Arm;
                case 58271:
                case 51826:
                case 63931:
                case 36864:
                case 14201:
                case 52301:
                case 2108:
                case 20781: return NpcPhysicsBodyRegion.Leg;
                default: return NpcPhysicsBodyRegion.Torso;
            }
        }

        internal static bool IsWeaponHandBone(int bone)
        {
            switch (bone)
            {
                case 18905: // SKEL_L_Hand
                case 57005: // SKEL_R_Hand
                case 60309: // PH_L_Hand
                case 28422: // PH_R_Hand
                case 36029: // IK_L_Hand
                case 6286:  // IK_R_Hand
                    return true;
                default:
                    return false;
            }
        }

        internal static bool ShouldAttemptWeaponRecovery(
            bool enabled, bool safeAmbientPed, bool alive, bool inVehicle,
            bool physicallyDown, bool assignedToTactics,
            bool exposedToThreat, int now, int eligibleAt, int expiresAt)
        {
            return enabled && safeAmbientPed && alive && !inVehicle &&
                !physicallyDown && !assignedToTactics && !exposedToThreat &&
                unchecked(now - eligibleAt) >= 0 &&
                unchecked(expiresAt - now) > 0;
        }

        internal static bool ShouldTakeSafeWeapon(
            int currentPriority, int candidatePriority,
            bool pickupValid, float distance)
        {
            return pickupValid && candidatePriority > 0 &&
                candidatePriority > currentPriority && distance <= 12f;
        }

        internal static bool DeterministicChance(
            int handle, int sequence, int percentage)
        {
            if (percentage <= 0) return false;
            if (percentage >= 100) return true;
            uint mixed = unchecked((uint)(handle * 397) ^
                (uint)(sequence * 7919) ^ 0x9E3779B9u);
            return mixed % 100u < (uint)percentage;
        }
    }

    public sealed class NpcPhysicsExperiment : Script
    {
        private static NpcPhysicsExperiment _current;
        private const float ScanRadius = 70f;
        private const int ScanIntervalMs = 50;
        private const int ReactionDurationMs = 4500;
        private const int VehicleBumpDurationMs = 3200;
        private const int StateRetentionMs = 10000;
        private const int MaxCandidatesPerScan = 64;
        private const int HeartbeatIntervalMs = 5000;
        private const int PedPushDurationMs = 2200;
        private const int LiveBalanceReinforcementDelayMs = 90;
        private const int CohesionDiscoveryIntervalMs = 350;
        private const int CohesionApproachTimeoutMs = 6500;
        private const int CohesionTurnDurationMs = 450;
        private const int CohesionTreatmentDurationMs = 3000;
        private const int CohesionCoverSeekDurationMs = 1800;
        private const int CohesionResponseTimeoutMs = 11000;
        private const int CollectionResponseTimeoutMs = 45000;
        private const int CollectionRouteTimeoutMs = 14000;
        private const int CollectionRouteRefreshMs = 2200;
        private const int MaximumCohesionResponses = 3;
        private const float CohesionResponseRadius = 22f;
        private const float CohesionThreatRadius = 45f;
        private const int FastRopeTrackingTimeoutMs = 10000;
        private const int FastRopeRecoveryReassertDelayMs = 300;
        private const int MaximumFastRopeRecoveryReassertions = 8;
        private const int AerialSupportScanIntervalMs = 350;
        private const int AerialMissionRefreshMs = 3500;
        private const int AerialIntelRelayIntervalMs = 1250;
        private const int AerialContactMemoryMs = 20000;
        private const int PlayerAggressionMemoryMs = 12000;
        private const int CohesionSmokeCoverDelayMs = 2700;
        private const float UnsafeReconOrbitRadius = 112f;
        private const float UnsafeReconOrbitHeight = 65f;
        private const float UnsafeReconInnerRadius = 86f;
        private const float RappelInsertionHoverHeight = 16f;
        private const int RappelInsertionMissionRefreshMs = 10000;
        private const int RappelInsertionApproachTimeoutMs = 24000;
        private const int RappelInsertionCompletionTimeoutMs = 14000;
        private const int AerialDeferralLogIntervalMs = 5000;
        private const int DedicatedCasevacModelLoadTimeoutMs = 2000;
        private const float DedicatedCasevacSpawnDistance = 135f;
        private const float DedicatedCasevacSpawnHeight = 65f;
        private const float AerialSupportRadius = 165f;
        private const float AerialOrbitRadius = 58f;
        private const float AerialOrbitHeight = 42f;
        private const int WeaponRecoveryScanIntervalMs = 750;
        private const int WeaponRecoveryApproachTimeoutMs = 6000;
        private const float WeaponRecoveryRadius = 12f;
        private const int CasevacMissionRefreshMs = 3200;
        private const int CasevacBoardingTimeoutMs = 9000;
        private const int CasevacDepartureDurationMs = 10000;
        private const int StabilizationCorrectionLogIntervalMs = 1500;
        private const float LiveBodyRelaxation = 25f;
        private const float LethalBodyRelaxation = 70f;
        private static readonly int[] ObservationDelaysMs = { 200, 1000, 3000 };

        private static readonly int StunGunHash =
            Game.GenerateHash("WEAPON_STUNGUN");
        private static readonly int StunGunMpHash =
            Game.GenerateHash("WEAPON_STUNGUN_MP");
        private static readonly int RappelFromHeliTaskHash =
            Game.GenerateHash("SCRIPT_TASK_RAPPEL_FROM_HELI");
        private static readonly int HeliMissionTaskHash =
            Game.GenerateHash("SCRIPT_TASK_HELI_MISSION");
        private static readonly int CopRelationshipGroupHash =
            Game.GenerateHash("COP");
        private static readonly int ArmyRelationshipGroupHash =
            Game.GenerateHash("ARMY");
        private static readonly WeaponRecoveryOption[] SafeRecoveryWeapons =
        {
            new WeaponRecoveryOption("WEAPON_PISTOL", 10),
            new WeaponRecoveryOption("WEAPON_COMBATPISTOL", 12),
            new WeaponRecoveryOption("WEAPON_PISTOL_MK2", 14),
            new WeaponRecoveryOption("WEAPON_APPISTOL", 16),
            new WeaponRecoveryOption("WEAPON_PUMPSHOTGUN", 20),
            new WeaponRecoveryOption("WEAPON_PUMPSHOTGUN_MK2", 22),
            new WeaponRecoveryOption("WEAPON_COMBATSHOTGUN", 24),
            new WeaponRecoveryOption("WEAPON_MICROSMG", 26),
            new WeaponRecoveryOption("WEAPON_SMG", 28),
            new WeaponRecoveryOption("WEAPON_SMG_MK2", 30),
            new WeaponRecoveryOption("WEAPON_COMBATPDW", 31),
            new WeaponRecoveryOption("WEAPON_CARBINERIFLE", 36),
            new WeaponRecoveryOption("WEAPON_CARBINERIFLE_MK2", 39),
            new WeaponRecoveryOption("WEAPON_SPECIALCARBINE", 38),
            new WeaponRecoveryOption("WEAPON_SPECIALCARBINE_MK2", 40),
        };
        private static readonly string ScriptDirectory =
            AppDomain.CurrentDomain.BaseDirectory;
        private static readonly string ConfigPath = Path.Combine(
            ScriptDirectory, "ALLIN1.toml");
        private static readonly string ArchiveMarkerPath = Path.Combine(
            ScriptDirectory, "ALLIN1_euphoria_tuning.json");

        private readonly Dictionary<int, PedState> _states =
            new Dictionary<int, PedState>();
        private readonly Dictionary<int, CohesionResponse> _cohesionResponses =
            new Dictionary<int, CohesionResponse>();
        private readonly Dictionary<int, AerialSupportState>
            _aerialSupportStates =
                new Dictionary<int, AerialSupportState>();
        private readonly List<Vehicle> _observedRappelHelicopters =
            new List<Vehicle>();
        private readonly Dictionary<int, RappelCrewLockState>
            _rappelLockedCrew =
                new Dictionary<int, RappelCrewLockState>();
        private bool _enabled;
        private bool _enhancedPoliceAi;
        private bool _debug;
        private int _lastHeartbeatAt;
        private int _lastCohesionDiscoveryAt;
        private int _lastAerialSupportScanAt;
        private int _playerAggressiveUntilAt;
        private int _nextDedicatedCasevacSpawnAt;
        private long _scans;
        private long _candidates;
        private long _newStates;
        private long _healthLosses;
        private long _damageReactions;
        private long _blastReactions;
        private long _vehicleReactions;
        private long _fireReactions;
        private long _pedPushReactions;
        private long _reactionObservations;
        private long _excludedPlayer;
        private long _excludedNonHuman;
        private long _excludedMission;
        private long _excludedPersistent;
        private long _excludedVehicle;
        private long _excludedDead;
        private long _cooldowns;
        private long _noDamageEvidence;
        private long _candidateTruncations;
        private long _prunedStates;
        private long _exceptions;
        private long _followOnDamage;
        private long _ambiguousDamageLosses;
        private long _cohesionRequests;
        private long _cohesionCoverAssignments;
        private long _cohesionRescuesCompleted;
        private long _cohesionRescuesCancelled;
        private long _cohesionCandidatesEvaluated;
        private long _cohesionLawFlagOverrides;
        private long _cohesionRejectedEntityFlags;
        private long _cohesionRejectedNotDown;
        private long _cohesionRejectedInactiveReaction;
        private long _cohesionRejectedHealth;
        private long _cohesionRejectedNoResponder;
        private long _fastRopeTracks;
        private long _fastRopeUncontrolledFalls;
        private long _fastRopeRecoveries;
        private long _fastRopeRecoveryReassertions;
        private long _unsafeRappelTasksCancelled;
        private long _unsafeRappelCrewLocks;
        private long _unsafeRappelCrewReseats;
        private long _unsafeRappelExitsIntercepted;
        private long _rappelRequestsInferredFromExit;
        private long _safeRappelInsertionsPlanned;
        private long _safeRappelInsertionsCompleted;
        private long _safeRappelInsertionsAborted;
        private long _safeRappelPlanDeferrals;
        private long _aerialReconAssignments;
        private long _aerialIntelRelays;
        private long _aerialOrbitCommands;
        private long _aerialReconLegsCompleted;
        private long _aerialReconLegStalls;
        private long _aerialReconControlRelinquished;
        private long _aerialReconReleases;
        private long _aerialRoleSwitches;
        private long _dedicatedCasevacSpawnAttempts;
        private long _dedicatedCasevacSpawns;
        private long _dedicatedCasevacSpawnFailures;
        private long _dedicatedCasevacBatchAssignments;
        private long _dedicatedCasevacPassengersLoaded;
        private long _dedicatedCasevacDespawns;
        private long _handDisarms;
        private long _weaponRecoverySearches;
        private long _weaponRecoveryCommands;
        private long _weaponRecoveries;
        private long _weaponRecoveryFailures;
        private long _collectionRoutesStarted;
        private long _collectionArrivals;
        private long _casevacAssignments;
        private long _casevacBoardings;
        private long _casevacCompletions;
        private long _casevacFailures;
        private long _casevacDeferrals;
        private long _stabilizedPassiveLossPrevented;
        private long _stabilizedHealingPrevented;
        private long _stabilizedDamageAccepted;

        private sealed class WeaponRecoveryOption
        {
            internal readonly int WeaponHash;
            internal readonly int ModelHash;
            internal readonly int Priority;

            internal WeaponRecoveryOption(string weaponName, int priority)
            {
                WeaponHash = Game.GenerateHash(weaponName);
                ModelHash = Function.Call<int>(
                    Hash.GET_WEAPONTYPE_MODEL, WeaponHash);
                Priority = priority;
            }
        }

        private enum CohesionPhase
        {
            Approach,
            Turn,
            Treat,
            EvacuateToCollection,
            AwaitCasevac,
            BoardingCasevac,
        }

        private sealed class CohesionResponse
        {
            internal Ped Casualty;
            internal Ped Rescuer;
            internal Ped Coverer;
            internal Ped Threat;
            internal CohesionPhase Phase;
            internal int StartedAt;
            internal int PhaseStartedAt;
            internal int LastApproachCommandAt;
            internal bool CoverEngaged;
            internal int PreviousCoverMovement = 2;
            internal bool HasCollectionPoint;
            internal Vector3 CollectionPoint;
            internal Vector3 CasevacLandingPoint;
            internal int CollectionSquadId;
            internal int LastCollectionCommandAt;
            internal int CasevacHelicopterHandle;
            internal int CasevacBoardingStartedAt;
            internal bool SmokeDeployed;
            internal int ApproachDeferredUntilAt;
            internal int LastCasevacDeferralAt;
            internal string LastCasevacDeferralReason;
            internal int StabilizedHoldingHealth;
            internal int StabilizationDirectDamageAt;
            internal int LastStabilizationCorrectionLogAt;
        }

        private sealed class RappelCrewLockState
        {
            internal Ped Crew;
            internal Vehicle Helicopter;
            internal int Seat = -2;
            internal bool RappelTaskWasActive;
            internal bool RappelRequested;
        }

        private sealed class RooftopInsertionDiagnostics
        {
            internal int Candidates;
            internal int RayMisses;
            internal int SlopeRejected;
            internal int ElevationRejected;
            internal int NavmeshRejected;
            internal int ThreatRejected;
            internal int Accepted;
        }

        private sealed class AerialSupportState
        {
            internal Vehicle Helicopter;
            internal Ped Pilot;
            internal AerialSupportRole Role;
            internal Vector3 LastKnownPlayerPosition;
            internal int AssignedAt;
            internal int LastVisualContactAt;
            internal int LastIntelRelayAt;
            internal int LastMissionCommandAt;
            internal Vector3 LastMissionTarget;
            internal Vector3 LastMissionAnchor;
            internal bool HasMissionTarget;
            internal bool LastMissionWasUnsafeEgress;
            internal float BestMissionDistance = float.MaxValue;
            internal int LastMissionProgressAt;
            internal bool ReconControlRelinquished;
            internal int LastRappelDeferralLogAt;
            internal string LastRappelDeferralReason;
            internal float OrbitPhase;
            internal readonly Dictionary<int, Ped> ReducedFireCrew =
                new Dictionary<int, Ped>();
            internal int CasevacCasualtyHandle;
            internal int CasevacDepartingUntilAt;
            internal int CasevacDepartureStartedAt;
            internal Vector3 CasevacDepartureTarget;
            internal bool DedicatedCasevac;
            internal bool RappelInsertionActive;
            internal bool RappelReleaseAuthorized;
            internal bool RappelInsertionRooftop;
            internal int RappelInsertionSquadId;
            internal int RappelInsertionStartedAt;
            internal int RappelInsertionStableAt;
            internal int RappelReleaseAt;
            internal Vector3 RappelInsertionPoint;
            internal readonly Dictionary<int, Ped> RappelInsertionCrew =
                new Dictionary<int, Ped>();
        }

        private sealed class ReactionSnapshot
        {
            internal bool Exists;
            internal bool IsRagdoll;
            internal bool RunningRagdollTask;
            internal bool CanRagdoll;
            internal bool Dead;
            internal int Health;
            internal float HeightAboveGround;
            internal float UprightValue;
            internal float Speed;
            internal float VerticalSpeed;
            internal Vector3 Position;
        }

        private sealed class PedState
        {
            internal int LastHealth;
            internal int LastArmor;
            internal bool WasAlive;
            internal int LastReactionAt = int.MinValue / 2;
            internal int LastVehicleBumpAt = int.MinValue / 2;
            internal int LastPedPushAt = int.MinValue / 2;
            internal int LastSeenAt;
            internal int ReactionSequence;
            internal int ObservationStartedAt;
            internal int ObservationIndex = -1;
            internal string ObservationKind = "";
            internal ReactionSnapshot ObservationBaseline;
            internal int ActiveReactionUntilAt;
            internal string ActiveReactionKind = "";
            internal int BalanceReinforcementAt;
            internal int BalanceReinforcementSequence;
            internal int BalanceReinforcementDuration;
            internal int LastCohesionRequestAt = int.MinValue / 2;
            internal bool RappelObserved;
            internal bool RappelTaskActiveLastScan;
            internal bool RappelUncontrolledFall;
            internal int RappelObservedAt;
            internal int RappelFallStartedAt;
            internal Vector3 RappelFallStartedPosition;
            internal float RappelMinimumVerticalSpeed;
            internal int RappelRecoveryUntilAt;
            internal int RappelLastRecoveryCommandAt;
            internal int RappelRecoveryReassertions;
            internal int DroppedWeaponHash;
            internal int WeaponRecoveryEligibleAt;
            internal int WeaponRecoveryExpiresAt;
            internal int NextWeaponRecoveryScanAt;
            internal int WeaponRecoveryCommandedAt;
            internal Prop WeaponRecoveryPickup;
            internal int WeaponRecoveryPickupHash;
        }

        public NpcPhysicsExperiment()
        {
            _current = this;
            _enabled = ReadBooleanSetting("gta_iv_npc_physics", false);
            _enhancedPoliceAi = ReadBooleanSetting(
                "enhanced_police_ai", true);
            _debug = ReadBooleanSetting("gta_iv_npc_physics_debug", true);
            // Keep diagnostics available when configuration unexpectedly
            // disables the experiment; otherwise a path/parser failure hides
            // the evidence needed to diagnose itself.
            PhysicsExperimentLog.Configure(_debug);
            Interval = (_enabled || _enhancedPoliceAi)
                ? ScanIntervalMs : 1000;
            Tick += OnTick;
            Aborted += OnAborted;
            PhysicsExperimentLog.Info("configuration_loaded",
                new Dictionary<string, object>
                {
                    { "enabled", _enabled }, { "debug", _debug },
                    { "enhanced_police_ai", _enhancedPoliceAi },
                    { "scan_interval_ms", Interval },
                    { "scan_radius", ScanRadius },
                    { "candidate_budget", MaxCandidatesPerScan },
                    { "config_path", ConfigPath },
                    { "archive_marker_exists", File.Exists(ArchiveMarkerPath) },
                    { "archive_marker_path", ArchiveMarkerPath },
                });
            if (_enabled && !File.Exists(ArchiveMarkerPath))
                PhysicsExperimentLog.Warn("archive_tuning_not_installed",
                    new Dictionary<string, object>
                    {
                        { "expected_marker", ArchiveMarkerPath },
                        { "runtime_reactions_still_active", true },
                    });
            ClientLog.Info("NPC-PHYSICS", _enabled
                ? "Expanded Euphoria runtime experiment enabled"
                : "Runtime experiment disabled");
        }

        internal static bool ReadBooleanSetting(string requestedKey,
            bool defaultValue)
        {
            if (!File.Exists(ConfigPath)) return defaultValue;
            try
            {
                string section = "";
                foreach (string rawLine in File.ReadAllLines(ConfigPath))
                {
                    string line = rawLine.Trim();
                    if (line.Length == 0 || line.StartsWith("#")) continue;
                    if (line.StartsWith("[") && line.EndsWith("]"))
                    {
                        section = line.Substring(1, line.Length - 2)
                            .Trim().ToLowerInvariant();
                        continue;
                    }
                    if (section != "script") continue;
                    int equals = line.IndexOf('=');
                    if (equals < 0) continue;
                    string key = line.Substring(0, equals).Trim()
                        .ToLowerInvariant();
                    if (key != requestedKey) continue;
                    string value = line.Substring(equals + 1).Trim();
                    int comment = value.IndexOf('#');
                    if (comment >= 0)
                        value = value.Substring(0, comment).Trim();
                    return string.Equals(value, "true",
                        StringComparison.OrdinalIgnoreCase);
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("NPC-PHYSICS", "ReadBooleanSetting", ex);
                PhysicsExperimentLog.Error("configuration_read_failed", ex,
                    new Dictionary<string, object> { { "key", requestedKey } });
            }
            return defaultValue;
        }

        internal static string ReadStringSetting(string requestedKey,
            string defaultValue)
        {
            if (!File.Exists(ConfigPath)) return defaultValue;
            try
            {
                string section = "";
                foreach (string rawLine in File.ReadAllLines(ConfigPath))
                {
                    string line = rawLine.Trim();
                    if (line.Length == 0 || line.StartsWith("#")) continue;
                    if (line.StartsWith("[") && line.EndsWith("]"))
                    {
                        section = line.Substring(1, line.Length - 2)
                            .Trim().ToLowerInvariant();
                        continue;
                    }
                    if (section != "script") continue;
                    int equals = line.IndexOf('=');
                    if (equals < 0) continue;
                    string key = line.Substring(0, equals).Trim()
                        .ToLowerInvariant();
                    if (key != requestedKey) continue;
                    string value = line.Substring(equals + 1).Trim();
                    int comment = value.IndexOf('#');
                    if (comment >= 0)
                        value = value.Substring(0, comment).Trim();
                    if (value.Length >= 2 && value[0] == '"' &&
                        value[value.Length - 1] == '"')
                        value = value.Substring(1, value.Length - 2);
                    return value.Length == 0 ? defaultValue : value;
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("NPC-PHYSICS", "ReadStringSetting", ex);
                PhysicsExperimentLog.Error("configuration_read_failed", ex,
                    new Dictionary<string, object> { { "key", requestedKey } });
            }
            return defaultValue;
        }

        private void OnTick(object sender, EventArgs args)
        {
            if ((!_enabled && !_enhancedPoliceAi) || Game.IsLoading) return;
            try
            {
                Ped player = Game.Player.Character;
                if (player == null || !player.Exists() || player.IsDead) return;
                int now = Game.GameTime;
                if (_enhancedPoliceAi && Function.Call<bool>(
                        Hash.IS_PED_SHOOTING, player.Handle))
                    _playerAggressiveUntilAt = unchecked(now +
                        PlayerAggressionMemoryMs);
                Ped[] nearby = World.GetNearbyPeds(player, ScanRadius);
                Array.Sort(nearby, (left, right) =>
                {
                    if (left == null || !left.Exists()) return 1;
                    if (right == null || !right.Exists()) return -1;
                    return left.Position.DistanceTo(player.Position).CompareTo(
                        right.Position.DistanceTo(player.Position));
                });
                _scans++;
                _candidates += nearby.Length;
                int budget = Math.Min(nearby.Length, MaxCandidatesPerScan);
                if (nearby.Length > budget)
                    _candidateTruncations += nearby.Length - budget;
                for (int i = 0; i < budget; i++)
                    InspectPed(nearby[i], player.Handle, now);
                UpdateCohesionResponses(now);
                if (unchecked(now - _lastCohesionDiscoveryAt) >=
                    CohesionDiscoveryIntervalMs)
                {
                    DiscoverCohesionResponses(
                        nearby, budget, player, now);
                    _lastCohesionDiscoveryAt = now;
                }
                if (unchecked(now - _lastAerialSupportScanAt) >=
                    AerialSupportScanIntervalMs)
                {
                    UpdateAerialSupport(player, now);
                    _lastAerialSupportScanAt = now;
                }
                PruneOldStates(now);
                if (unchecked(now - _lastHeartbeatAt) >= HeartbeatIntervalMs)
                {
                    WriteHeartbeat(now, nearby.Length, budget);
                    _lastHeartbeatAt = now;
                }
            }
            catch (Exception ex)
            {
                _exceptions++;
                ClientLog.Error("NPC-PHYSICS", "OnTick", ex);
                PhysicsExperimentLog.Error("tick_failed", ex);
            }
        }

        private void OnAborted(object sender, EventArgs args)
        {
            var casualties = new List<int>(_cohesionResponses.Keys);
            foreach (int handle in casualties)
                CancelCohesionResponse(handle, "script_aborted");
            var helicopters = new List<int>(_aerialSupportStates.Keys);
            foreach (int handle in helicopters)
                ReleaseAerialSupport(handle, "script_aborted");
            _observedRappelHelicopters.Clear();
            ReleaseAllRappelDepartureLocks();
            if (ReferenceEquals(_current, this)) _current = null;
        }

        internal static bool IsPedReservedForCohesion(int handle)
        {
            NpcPhysicsExperiment current = _current;
            if (current == null || handle == 0) return false;
            foreach (CohesionResponse response in
                current._cohesionResponses.Values)
            {
                if ((response.Casualty != null &&
                        response.Casualty.Handle == handle) ||
                    (response.Rescuer != null &&
                        response.Rescuer.Handle == handle) ||
                    (response.Coverer != null &&
                        response.Coverer.Handle == handle))
                    return true;
            }
            return false;
        }

        internal static bool IsPedInFastRopeSequence(int handle)
        {
            NpcPhysicsExperiment current = _current;
            if (current == null || handle == 0 ||
                !current._states.TryGetValue(handle,
                    out PedState state)) return false;
            return state.RappelObserved ||
                (state.RappelRecoveryUntilAt != 0 && unchecked(
                    state.RappelRecoveryUntilAt - Game.GameTime) > 0);
        }

        private void InspectPed(Ped ped, int playerHandle, int now)
        {
            if (ped == null || !ped.Exists()) return;
            int handle = ped.Handle;
            int health = ped.Health;
            int armor = ped.Armor;
            bool alive = !ped.IsDead && health > 0;
            bool firstScanWithoutDamage = false;
            if (!_states.TryGetValue(handle, out PedState state))
            {
                state = new PedState
                {
                    LastHealth = health,
                    LastArmor = armor,
                    WasAlive = alive,
                    LastSeenAt = now,
                };
                _states[handle] = state;
                _newStates++;
                bool alreadyDamaged = ped.HasBeenDamagedByAnyWeapon() ||
                    ped.HasBeenDamagedByAnyMeleeWeapon();
                if (!alreadyDamaged)
                    firstScanWithoutDamage = true;
                else
                {
                    state.LastHealth = Math.Max(health + 1, ped.MaxHealth);
                    // A lethal hit can create the ped wrapper after death.
                    // Preserve evidence that it was alive immediately before
                    // that hit so the first scan can dispatch the reaction.
                    state.WasAlive = true;
                    PhysicsExperimentLog.Info(
                        "damaged_ped_discovered_on_first_scan",
                        new Dictionary<string, object>
                        {
                            { "ped", handle }, { "health", health },
                            { "max_health", ped.MaxHealth },
                            { "armor", armor },
                        });
                }
            }
            state.LastSeenAt = now;
            WriteDueReactionObservation(ped, state, now);
            bool clearDamageFlags = false;

            try
            {
                bool missionEntity = Function.Call<bool>(
                    Hash.IS_ENTITY_A_MISSION_ENTITY, handle);
                bool human = ped.IsHuman;
                bool player = handle == playerHandle;
                bool persistent = ped.IsPersistent;
                bool safeAmbient = human && !player && !missionEntity &&
                    !persistent;
                bool inVehicle = ped.IsInVehicle();
                UpdateFastRopeRecovery(ped, state, now, human, player,
                    alive, inVehicle, Game.IsMissionActive,
                    Game.IsCutsceneActive);
                if (firstScanWithoutDamage) return;
                ApplyDueLiveBalanceReinforcement(ped, state, now,
                    safeAmbient, alive, inVehicle);
                UpdateWeaponRecovery(ped, state, Game.Player.Character,
                    now, safeAmbient, alive, inVehicle);
                bool freshVitalityLoss =
                    NpcPhysicsExperimentPolicy.HasFreshVitalityLoss(
                        state.LastHealth, state.LastArmor, health, armor);
                clearDamageFlags = safeAmbient && freshVitalityLoss;
                if (freshVitalityLoss) _healthLosses++;
                bool meleeDamage = freshVitalityLoss &&
                    ped.HasBeenDamagedByAnyMeleeWeapon();
                bool weaponDamage = freshVitalityLoss &&
                    (ped.HasBeenDamagedByAnyWeapon() || meleeDamage);
                int elapsed = unchecked(now - state.LastReactionAt);
                bool onFire = Function.Call<bool>(Hash.IS_ENTITY_ON_FIRE,
                    handle);
                bool nearExplosion = !weaponDamage && freshVitalityLoss &&
                    WasNearExplosion(ped.Position);
                if (freshVitalityLoss)
                    RecordStabilizationDamageEvidence(
                        ped, weaponDamage, onFire, nearExplosion, now);
                bool environmentReaction = !weaponDamage &&
                    NpcPhysicsExperimentPolicy.ShouldReactToEnvironmentalDamage(
                        _enabled, safeAmbient, state.WasAlive, inVehicle,
                        freshVitalityLoss, onFire, nearExplosion, elapsed);
                bool blastReaction = environmentReaction && nearExplosion;
                bool liveReaction = NpcPhysicsExperimentPolicy.ShouldReact(
                    _enabled, true, ped.IsHuman, alive,
                    handle == playerHandle, missionEntity, ped.IsPersistent,
                    inVehicle, weaponDamage,
                    state.LastHealth + Math.Max(0, state.LastArmor),
                    health + Math.Max(0, armor), elapsed);
                bool lethalReaction =
                    NpcPhysicsExperimentPolicy.ShouldReactToLethalDamage(
                        _enabled, ped.IsHuman, handle == playerHandle,
                        missionEntity, ped.IsPersistent, inVehicle, state.WasAlive,
                        state.LastHealth + Math.Max(0, state.LastArmor),
                        health + Math.Max(0, armor), weaponDamage, elapsed);

                if (liveReaction || lethalReaction || environmentReaction)
                {
                    clearDamageFlags = true;
                    state.ReactionSequence++;
                    ReactionSnapshot baseline = CaptureReactionSnapshot(ped);
                    int damageBone = GetLastDamageBone(ped);
                    NpcPhysicsBodyRegion region =
                        NpcPhysicsExperimentPolicy.ClassifyBone(damageBone);
                    bool grounded =
                        NpcPhysicsExperimentPolicy.IsPhysicallyGrounded(
                            baseline.HeightAboveGround,
                            baseline.VerticalSpeed,
                            baseline.UprightValue);
                    bool taser = WasDamagedBy(ped, StunGunHash) ||
                        WasDamagedBy(ped, StunGunMpHash);
                    bool armed = Function.Call<bool>(Hash.IS_PED_ARMED,
                        handle, 4);
                    bool handHit =
                        NpcPhysicsExperimentPolicy.IsWeaponHandBone(
                            damageBone);
                    int selectedWeapon = armed ? Function.Call<int>(
                        Hash.GET_SELECTED_PED_WEAPON, handle) : 0;
                    if (blastReaction) _blastReactions++;
                    else if (environmentReaction) _fireReactions++;
                    else _damageReactions++;
                    string reactionKind = blastReaction ? "blast" :
                        environmentReaction ? "fire" :
                        lethalReaction ? "lethal_weapon" :
                        meleeDamage ? "melee" : "weapon";
                    PhysicsExperimentLog.Info("reaction_triggered",
                        new Dictionary<string, object>
                        {
                            { "ped", handle },
                            { "reaction", reactionKind },
                            { "previous_health", state.LastHealth },
                            { "current_health", health },
                            { "previous_armor", state.LastArmor },
                            { "current_armor", armor },
                            { "damage_bone", damageBone },
                            { "body_region", region.ToString() },
                            { "grounded", grounded }, { "taser", taser },
                            { "on_fire", onFire }, { "armed", armed },
                            { "weapon_hand_hit", handHit },
                            { "was_ragdoll", baseline.IsRagdoll },
                            { "was_running_ragdoll_task",
                                baseline.RunningRagdollTask },
                            { "height_above_ground",
                                baseline.HeightAboveGround },
                            { "upright_value", baseline.UprightValue },
                            { "vertical_speed", baseline.VerticalSpeed },
                            { "sequence", state.ReactionSequence },
                        });
                    ApplyDamageReaction(ped, region, meleeDamage, taser,
                        onFire, grounded, lethalReaction, armed,
                        state.ReactionSequence, blastReaction, reactionKind,
                        handHit);
                    if (handHit && armed && !lethalReaction &&
                        selectedWeapon != 0)
                        ScheduleWeaponRecovery(ped, state, selectedWeapon,
                            damageBone, now);
                    PhysicsExperimentLog.Info("reaction_dispatched",
                        BuildOutcomeFields(ped, handle, state.ReactionSequence));
                    state.LastReactionAt = now;
                    ScheduleReactionObservation(state, now, reactionKind,
                        ReactionDurationMs, baseline);
                    if (liveReaction && !grounded && !taser && !onFire &&
                        !blastReaction)
                        ScheduleLiveBalanceReinforcement(state, now,
                            state.ReactionSequence, ReactionDurationMs);
                }
                else if (_enabled && alive && safeAmbient && !inVehicle)
                {
                    if (!TryApplyVehicleBump(ped, state, now))
                        TryApplyPedPush(ped, state, now,
                            Game.Player.Character);
                }

                if (freshVitalityLoss &&
                    !(liveReaction || lethalReaction || environmentReaction))
                {
                    bool activeReaction = HasActiveReaction(state, now);
                    string disposition =
                        NpcPhysicsExperimentPolicy.ClassifyUnreactedVitalityLoss(
                            human, player, missionEntity, persistent, inVehicle,
                            alive, activeReaction, weaponDamage, elapsed);
                    CountUnreactedDisposition(disposition);
                    var fields = new Dictionary<string, object>
                    {
                        { "ped", handle }, { "disposition", disposition },
                        { "human", human }, { "player", player },
                        { "mission_entity", missionEntity },
                        { "persistent", persistent },
                        { "in_vehicle", inVehicle }, { "alive", alive },
                        { "previous_health", state.LastHealth },
                        { "current_health", health },
                        { "previous_armor", state.LastArmor },
                        { "current_armor", armor },
                        { "weapon_damage", weaponDamage },
                        { "melee_damage", meleeDamage },
                        { "cooldown_elapsed_ms", elapsed },
                        { "active_reaction", activeReaction },
                        { "active_reaction_kind", state.ActiveReactionKind },
                        { "active_reaction_remaining_ms", activeReaction
                            ? unchecked(state.ActiveReactionUntilAt - now) : 0 },
                    };
                    bool ambiguous = disposition == "missing_damage_provenance" ||
                        disposition == "dead_without_fresh_weapon_evidence" ||
                        disposition == "unclassified";
                    if (ambiguous)
                        PhysicsExperimentLog.Warn("health_loss_not_reacted",
                            fields);
                    else
                        PhysicsExperimentLog.Info("health_loss_not_reacted",
                            fields);
                }
            }
            catch (Exception ex)
            {
                _exceptions++;
                ClientLog.Error("NPC-PHYSICS",
                    $"InspectPed handle={handle}", ex);
                PhysicsExperimentLog.Error("ped_inspection_failed", ex,
                    new Dictionary<string, object> { { "ped", handle } });
            }
            finally
            {
                if (clearDamageFlags && ped.Exists())
                    Function.Call(Hash.CLEAR_ENTITY_LAST_WEAPON_DAMAGE,
                        handle);
                state.LastHealth = health;
                state.LastArmor = armor;
                state.WasAlive = alive;
            }
        }

        private void UpdateFastRopeRecovery(
            Ped ped, PedState state, int now, bool human, bool player,
            bool alive, bool inVehicle, bool missionActive,
            bool cutsceneActive)
        {
            bool canTrack = NpcPhysicsExperimentPolicy.CanTrackFastRopeFall(
                _enabled || _enhancedPoliceAi,
                human, alive, player, inVehicle,
                missionActive, cutsceneActive);
            if (!canTrack)
            {
                if (state.RappelObserved || state.RappelRecoveryUntilAt != 0)
                {
                    PhysicsExperimentLog.Info("fast_rope_tracking_cancelled",
                        FastRopeFields(ped, state, now,
                            new Dictionary<string, object>
                            {
                                { "mission_active", missionActive },
                                { "cutscene_active", cutsceneActive },
                                { "alive", alive },
                                { "in_vehicle", inVehicle },
                            }));
                    ResetFastRopeState(state, true);
                }
                return;
            }

            int taskStatus = Function.Call<int>(
                Hash.GET_SCRIPT_TASK_STATUS,
                ped.Handle, RappelFromHeliTaskHash);
            bool nativeTaskActive =
                NpcPhysicsExperimentPolicy.IsRappelTaskActive(taskStatus);
            float height = Function.Call<float>(
                Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND, ped.Handle);
            float verticalSpeed = ped.Velocity.Z;
            bool ragdoll = ped.IsRagdoll || Function.Call<bool>(
                Hash.IS_PED_RUNNING_RAGDOLL_TASK, ped.Handle);
            bool falling = ped.IsFalling;
            bool nearRappellingHelicopter =
                IsNearObservedRappelHelicopter(ped);
            bool taskActive =
                NpcPhysicsExperimentPolicy.IsLikelyFastRopeDescent(
                    nativeTaskActive, nearRappellingHelicopter,
                    height, verticalSpeed, falling, ragdoll);

            if (taskActive)
            {
                if (!state.RappelObserved)
                {
                    state.RappelObserved = true;
                    state.RappelObservedAt = now;
                    state.RappelMinimumVerticalSpeed =
                        Math.Min(0f, verticalSpeed);
                    _fastRopeTracks++;
                    PhysicsExperimentLog.Info("fast_rope_rappel_observed",
                        FastRopeFields(ped, state, now,
                            new Dictionary<string, object>
                            {
                                { "task_status", taskStatus },
                                { "observation_source", nativeTaskActive
                                    ? "native_task" :
                                    "rappelling_helicopter_proximity" },
                                { "near_rappelling_helicopter",
                                    nearRappellingHelicopter },
                                { "height_above_ground", height },
                            }));
                }

                state.RappelMinimumVerticalSpeed = Math.Min(
                    state.RappelMinimumVerticalSpeed, verticalSpeed);
                if (!state.RappelUncontrolledFall &&
                    height > 0.65f &&
                    (ragdoll || (falling && verticalSpeed < -1.0f)))
                {
                    BeginUncontrolledFastRopeFall(
                        ped, state, now, "during_rappel_task");
                }
            }
            else if (NpcPhysicsExperimentPolicy.IsUncontrolledRappelExit(
                    state.RappelObserved,
                    state.RappelTaskActiveLastScan, taskActive,
                    height, verticalSpeed, falling, ragdoll))
            {
                BeginUncontrolledFastRopeFall(
                    ped, state, now, "rappel_task_ended_airborne");
            }
            else if (state.RappelObserved &&
                state.RappelTaskActiveLastScan && height <= 0.65f &&
                !state.RappelUncontrolledFall)
            {
                PhysicsExperimentLog.Info("fast_rope_normal_dismount",
                    FastRopeFields(ped, state, now,
                        new Dictionary<string, object>
                        {
                            { "task_status", taskStatus },
                            { "height_above_ground", height },
                        }));
                ResetFastRopeState(state, false);
            }
            state.RappelTaskActiveLastScan = taskActive;

            if (state.RappelObserved && state.RappelUncontrolledFall)
            {
                state.RappelMinimumVerticalSpeed = Math.Min(
                    state.RappelMinimumVerticalSpeed, verticalSpeed);
                float verticalDrop = Math.Max(0f,
                    state.RappelFallStartedPosition.Z - ped.Position.Z);
                int fallElapsed = unchecked(now -
                    state.RappelFallStartedAt);
                bool recover =
                    NpcPhysicsExperimentPolicy.ShouldApplyFastRopeRecovery(
                        true, true, alive, inVehicle, height,
                        state.RappelMinimumVerticalSpeed, verticalDrop,
                        ragdoll, fallElapsed);
                if (recover)
                {
                    StartFastRopeImpactRecovery(
                        ped, state, now, height, verticalDrop);
                    ResetFastRopeObservation(state);
                }
                else if (height <= 0.48f && fallElapsed >= 100)
                {
                    PhysicsExperimentLog.Info(
                        "fast_rope_soft_landing_preserved",
                        FastRopeFields(ped, state, now,
                            new Dictionary<string, object>
                            {
                                { "height_above_ground", height },
                                { "vertical_drop", verticalDrop },
                                { "minimum_vertical_speed",
                                    state.RappelMinimumVerticalSpeed },
                                { "fall_elapsed_ms", fallElapsed },
                            }));
                    ResetFastRopeObservation(state);
                }
            }

            if (state.RappelObserved && unchecked(now -
                    state.RappelObservedAt) > FastRopeTrackingTimeoutMs)
            {
                PhysicsExperimentLog.Info("fast_rope_tracking_timed_out",
                    FastRopeFields(ped, state, now, null));
                ResetFastRopeObservation(state);
            }

            MaintainFastRopeImpactRecovery(ped, state, now);
        }

        private bool IsNearObservedRappelHelicopter(Ped ped)
        {
            foreach (Vehicle helicopter in _observedRappelHelicopters)
            {
                if (helicopter == null || !helicopter.Exists()) continue;
                float horizontal = HorizontalDistance2D(
                    helicopter.Position, ped.Position);
                float vertical = helicopter.Position.Z - ped.Position.Z;
                if (horizontal <= 12f && vertical >= -2f &&
                    vertical <= 38f)
                    return true;
            }
            return false;
        }

        private void BeginUncontrolledFastRopeFall(
            Ped ped, PedState state, int now, string reason)
        {
            if (state.RappelUncontrolledFall) return;
            state.RappelUncontrolledFall = true;
            state.RappelFallStartedAt = now;
            state.RappelFallStartedPosition = ped.Position;
            state.RappelMinimumVerticalSpeed = Math.Min(
                state.RappelMinimumVerticalSpeed, ped.Velocity.Z);
            _fastRopeUncontrolledFalls++;
            PhysicsExperimentLog.Info("fast_rope_uncontrolled_fall",
                FastRopeFields(ped, state, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "start_x", state.RappelFallStartedPosition.X },
                        { "start_y", state.RappelFallStartedPosition.Y },
                        { "start_z", state.RappelFallStartedPosition.Z },
                    }));
        }

        private void StartFastRopeImpactRecovery(
            Ped ped, PedState state, int now,
            float heightAboveGround, float verticalDrop)
        {
            int duration = NpcPhysicsExperimentPolicy.FastRopeRecoveryDuration(
                state.RappelMinimumVerticalSpeed, verticalDrop);
            state.RappelRecoveryUntilAt = unchecked(now + duration);
            state.RappelLastRecoveryCommandAt = now;
            state.RappelRecoveryReassertions = 0;
            state.ReactionSequence++;
            int sequence = state.ReactionSequence;
            SendNaturalMotionStage(ped, "fast_rope", sequence,
                "fast_rope_impact_ragdoll", () =>
                {
                    ped.CanRagdoll = true;
                    ped.Ragdoll(duration, RagdollType.ScriptControl);
                });
            SendNaturalMotionStage(ped, "fast_rope", sequence,
                "fast_rope_ground_relaxation", () =>
                ApplyLowStiffnessAndFriction(
                    ped, duration, 1.12f, 55f, 5f));
            _fastRopeRecoveries++;
            PhysicsExperimentLog.Info("fast_rope_impact_recovery_started",
                FastRopeFields(ped, state, now,
                    new Dictionary<string, object>
                    {
                        { "duration_ms", duration },
                        { "height_above_ground", heightAboveGround },
                        { "vertical_drop", verticalDrop },
                        { "minimum_vertical_speed",
                            state.RappelMinimumVerticalSpeed },
                        { "sequence", sequence },
                    }));
        }

        private void MaintainFastRopeImpactRecovery(
            Ped ped, PedState state, int now)
        {
            if (state.RappelRecoveryUntilAt == 0) return;
            int remaining = unchecked(state.RappelRecoveryUntilAt - now);
            if (remaining <= 0)
            {
                PhysicsExperimentLog.Info("fast_rope_recovery_completed",
                    FastRopeFields(ped, state, now, null));
                state.RappelRecoveryUntilAt = 0;
                state.RappelLastRecoveryCommandAt = 0;
                state.RappelRecoveryReassertions = 0;
                return;
            }
            if (IsPedPhysicallyDown(ped) ||
                state.RappelRecoveryReassertions >=
                    MaximumFastRopeRecoveryReassertions ||
                unchecked(now - state.RappelLastRecoveryCommandAt) <
                    FastRopeRecoveryReassertDelayMs)
                return;

            ped.CanRagdoll = true;
            ped.Ragdoll(Math.Max(400, remaining),
                RagdollType.ScriptControl);
            state.RappelLastRecoveryCommandAt = now;
            state.RappelRecoveryReassertions++;
            _fastRopeRecoveryReassertions++;
            PhysicsExperimentLog.Info("fast_rope_recovery_reasserted",
                FastRopeFields(ped, state, now,
                    new Dictionary<string, object>
                    {
                        { "remaining_ms", remaining },
                        { "reassertion",
                            state.RappelRecoveryReassertions },
                    }));
        }

        private static void ResetFastRopeObservation(PedState state)
        {
            state.RappelObserved = false;
            state.RappelTaskActiveLastScan = false;
            state.RappelUncontrolledFall = false;
            state.RappelObservedAt = 0;
            state.RappelFallStartedAt = 0;
            state.RappelFallStartedPosition = Vector3.Zero;
            state.RappelMinimumVerticalSpeed = 0f;
        }

        private static void ResetFastRopeState(
            PedState state, bool cancelRecovery)
        {
            ResetFastRopeObservation(state);
            if (!cancelRecovery) return;
            state.RappelRecoveryUntilAt = 0;
            state.RappelLastRecoveryCommandAt = 0;
            state.RappelRecoveryReassertions = 0;
        }

        private static Dictionary<string, object> FastRopeFields(
            Ped ped, PedState state, int now,
            Dictionary<string, object> fields)
        {
            fields = fields ?? new Dictionary<string, object>();
            fields["ped"] = ped?.Handle ?? 0;
            fields["observed"] = state != null && state.RappelObserved;
            fields["uncontrolled_fall"] =
                state != null && state.RappelUncontrolledFall;
            fields["vertical_speed"] = ped != null && ped.Exists()
                ? ped.Velocity.Z : 0f;
            fields["tracked_elapsed_ms"] = state == null ||
                state.RappelObservedAt == 0 ? 0 :
                unchecked(now - state.RappelObservedAt);
            fields["recovery_remaining_ms"] = state == null ||
                state.RappelRecoveryUntilAt == 0 ? 0 :
                Math.Max(0, unchecked(state.RappelRecoveryUntilAt - now));
            return fields;
        }

        private void UpdateAerialSupport(Ped player, int now)
        {
            _observedRappelHelicopters.Clear();
            if (Game.IsMissionActive || Game.IsCutsceneActive ||
                Game.Player.WantedLevel <= 0)
            {
                ReleaseAllAerialSupport(Game.IsMissionActive
                    ? "mission_active" : Game.IsCutsceneActive
                    ? "cutscene_active" : "wanted_level_cleared");
                ReleaseAllRappelDepartureLocks();
                return;
            }

            Vehicle[] nearby = World.GetNearbyVehicles(
                player, AerialSupportRadius, new Model[0]);
            var eligibleHandles = new HashSet<int>();
            if (Function.Call<bool>(Hash.IS_PED_SHOOTING, player.Handle))
                _playerAggressiveUntilAt = unchecked(now +
                    PlayerAggressionMemoryMs);
            bool playerAggressive = unchecked(
                _playerAggressiveUntilAt - now) > 0;
            foreach (Vehicle helicopter in nearby)
            {
                if (helicopter == null || !helicopter.Exists() ||
                    !helicopter.Model.IsHelicopter) continue;
                Ped pilot = helicopter.Driver;
                if (pilot == null || !pilot.Exists()) continue;
                bool rappelling = Function.Call<bool>(
                    Hash.IS_ANY_PED_RAPPELLING_FROM_HELI,
                    helicopter.Handle);
                if (rappelling)
                    _observedRappelHelicopters.Add(helicopter);
                int pilotGroup = Function.Call<int>(
                    Hash.GET_PED_RELATIONSHIP_GROUP_HASH, pilot.Handle);
                int relationship = Function.Call<int>(
                    Hash.GET_RELATIONSHIP_BETWEEN_PEDS,
                    pilot.Handle, player.Handle);
                bool lawCrew = pilotGroup == CopRelationshipGroupHash ||
                    pilotGroup == ArmyRelationshipGroupHash;
                bool hostile = relationship == 4 || relationship == 5 ||
                    pilot.IsInCombatAgainst(player);
                float distanceToPlayer = HorizontalDistance2D(
                    helicopter.Position, player.Position);
                _aerialSupportStates.TryGetValue(
                    helicopter.Handle, out AerialSupportState existingState);
                if (existingState != null && existingState.DedicatedCasevac)
                {
                    eligibleHandles.Add(helicopter.Handle);
                    continue;
                }
                if (lawCrew && hostile)
                    CancelUnsafeRappelTasks(helicopter, pilot,
                        playerAggressive, distanceToPlayer, now,
                        existingState != null &&
                        existingState.RappelReleaseAuthorized);
                bool airborne = Function.Call<float>(
                    Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND,
                    helicopter.Handle) >= 8f;
                bool lineOfSight = Function.Call<bool>(
                    Hash.HAS_ENTITY_CLEAR_LOS_TO_ENTITY,
                    helicopter.Handle, player.Handle, 17);
                bool activeCasevac = existingState != null &&
                    (existingState.CasevacCasualtyHandle != 0 ||
                     unchecked(existingState.CasevacDepartingUntilAt - now) > 0);
                bool baseEligible =
                    NpcPhysicsExperimentPolicy.CanAssignAerialRecon(
                        _enabled || _enhancedPoliceAi, false, false,
                        Game.Player.WantedLevel,
                        true, helicopter.IsDriveable,
                        airborne || activeCasevac,
                        !pilot.IsDead && pilot.Health > 0,
                        lawCrew, hostile, true);
                if (!baseEligible) continue;
                eligibleHandles.Add(helicopter.Handle);

                if (!_aerialSupportStates.TryGetValue(
                        helicopter.Handle, out AerialSupportState state))
                {
                    bool canAssign =
                        NpcPhysicsExperimentPolicy.CanAssignAerialRecon(
                            _enabled || _enhancedPoliceAi, false, false,
                            Game.Player.WantedLevel, true,
                            helicopter.IsDriveable, airborne,
                            !pilot.IsDead && pilot.Health > 0,
                            lawCrew, hostile,
                            lineOfSight || playerAggressive);
                    if (rappelling || !canAssign)
                        continue;
                    state = new AerialSupportState
                    {
                        Helicopter = helicopter,
                        Pilot = pilot,
                        Role = AerialSupportRole.Recon,
                        LastKnownPlayerPosition = player.Position,
                        AssignedAt = now,
                        LastVisualContactAt = now,
                        LastIntelRelayAt = int.MinValue / 2,
                        LastMissionCommandAt = int.MinValue / 2,
                        OrbitPhase = (helicopter.Handle % 360) *
                            ((float)Math.PI / 180f),
                    };
                    _aerialSupportStates.Add(
                        helicopter.Handle, state);
                    _aerialReconAssignments++;
                    PhysicsExperimentLog.Info("aerial_recon_assigned",
                        AerialSupportFields(state, now,
                            new Dictionary<string, object>
                            {
                                { "wanted_level",
                                    Game.Player.WantedLevel },
                                { "relationship", relationship },
                                { "pilot_group", pilotGroup },
                            }));
                }

                state.Helicopter = helicopter;
                state.Pilot = pilot;
                // Ambient law helicopters remain recon/transport aircraft.
                // Casualty evacuation uses its own script-spawned helicopter.
                if (state.Role != AerialSupportRole.Recon)
                    ChangeAerialSupportRole(state,
                        AerialSupportRole.Recon, now,
                        "ambient_aircraft_reserved_for_recon");
                UpdateAerialReconState(state, player,
                    lineOfSight, playerAggressive, now);
            }

            PruneRappelDepartureLocks(now);
            TryAssignCasevacRequest(player, now);
            UpdateDedicatedCasevacSupport(player, now, eligibleHandles);
            var assigned = new List<int>(_aerialSupportStates.Keys);
            foreach (int handle in assigned)
            {
                if (!_aerialSupportStates.TryGetValue(handle,
                        out AerialSupportState state)) continue;
                if (!eligibleHandles.Contains(handle))
                {
                    ReleaseAerialSupport(handle, "aircraft_unavailable");
                    continue;
                }
                if (state.DedicatedCasevac) continue;
                bool casevacActive = state.CasevacCasualtyHandle != 0 ||
                    unchecked(state.CasevacDepartingUntilAt - now) > 0;
                if (!casevacActive && unchecked(
                        now - state.LastVisualContactAt) >
                    AerialContactMemoryMs)
                    ReleaseAerialSupport(handle, "visual_contact_expired");
            }
        }

        private bool TrySpawnDedicatedCasevac(
            CohesionResponse response, Ped player, int now)
        {
            _dedicatedCasevacSpawnAttempts++;
            _nextDedicatedCasevacSpawnAt = unchecked(now +
                NpcPhysicsExperimentPolicy.DedicatedCasevacSpawnCooldownMs);
            var helicopterModel = new Model("polmav");
            var pilotModel = new Model("s_m_y_pilot_01");
            Vehicle helicopter = null;
            var createdCrew = new List<Ped>();
            try
            {
                helicopterModel.Request(DedicatedCasevacModelLoadTimeoutMs);
                pilotModel.Request(DedicatedCasevacModelLoadTimeoutMs);
                DateTime deadline = DateTime.UtcNow.AddMilliseconds(
                    DedicatedCasevacModelLoadTimeoutMs);
                while ((!helicopterModel.IsLoaded || !pilotModel.IsLoaded) &&
                    DateTime.UtcNow <= deadline)
                    Script.Wait(0);
                if (!helicopterModel.IsLoaded || !pilotModel.IsLoaded)
                    throw new InvalidOperationException(
                        "dedicated CASEVAC model load timed out");

                Vector3 outward = NormalizeHorizontalVector(
                    response.CasevacLandingPoint - player.Position,
                    player.ForwardVector * -1f);
                Vector3 spawn = response.CasevacLandingPoint +
                    outward * DedicatedCasevacSpawnDistance +
                    new Vector3(0f, 0f, DedicatedCasevacSpawnHeight);
                float ground = World.GetGroundHeight(spawn);
                if (ground > 0f)
                    spawn.Z = Math.Max(spawn.Z,
                        ground + DedicatedCasevacSpawnHeight);
                Vector3 towardLanding = NormalizeHorizontalVector(
                    response.CasevacLandingPoint - spawn,
                    player.ForwardVector);
                float heading = (float)(Math.Atan2(
                    -towardLanding.X, towardLanding.Y) * 180.0 / Math.PI);
                helicopter = World.CreateVehicle(
                    helicopterModel, spawn, heading);
                if (helicopter == null || !helicopter.Exists())
                    throw new InvalidOperationException(
                        "dedicated CASEVAC helicopter creation failed");
                helicopter.IsPersistent = true;
                Function.Call(Hash.SET_VEHICLE_ENGINE_ON,
                    helicopter.Handle, true, true, false);
                Function.Call(Hash.SET_HELI_BLADES_FULL_SPEED,
                    helicopter.Handle);

                Ped pilot = Function.Call<Ped>(
                    Hash.CREATE_PED_INSIDE_VEHICLE,
                    helicopter.Handle, 26, pilotModel.Hash,
                    -1, true, true);
                if (pilot == null || !pilot.Exists())
                    throw new InvalidOperationException(
                        "dedicated CASEVAC pilot creation failed");
                createdCrew.Add(pilot);
                ConfigureDedicatedCasevacPilot(pilot);

                var state = new AerialSupportState
                {
                    Helicopter = helicopter,
                    Pilot = pilot,
                    Role = AerialSupportRole.Casevac,
                    DedicatedCasevac = true,
                    CasevacCasualtyHandle = response.Casualty.Handle,
                    LastKnownPlayerPosition = player.Position,
                    AssignedAt = now,
                    LastVisualContactAt = now,
                    LastIntelRelayAt = int.MinValue / 2,
                    LastMissionCommandAt = int.MinValue / 2,
                    LastMissionProgressAt = now,
                };
                _aerialSupportStates.Add(helicopter.Handle, state);
                response.CasevacHelicopterHandle = helicopter.Handle;
                response.LastCasevacDeferralAt = 0;
                response.LastCasevacDeferralReason = null;
                _casevacAssignments++;
                _dedicatedCasevacSpawns++;
                PhysicsExperimentLog.Info("dedicated_casevac_spawned",
                    AerialSupportFields(state, now,
                        new Dictionary<string, object>
                        {
                            { "casualty", response.Casualty.Handle },
                            { "collection_squad",
                                response.CollectionSquadId },
                            { "model", "polmav" },
                            { "passenger_capacity",
                                Function.Call<int>(Hash.
                                    GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS,
                                    helicopter.Handle) },
                            { "spawn_x", spawn.X },
                            { "spawn_y", spawn.Y },
                            { "spawn_z", spawn.Z },
                            { "landing_x",
                                response.CasevacLandingPoint.X },
                            { "landing_y",
                                response.CasevacLandingPoint.Y },
                            { "landing_z",
                                response.CasevacLandingPoint.Z },
                        }));
                return true;
            }
            catch (Exception ex)
            {
                _dedicatedCasevacSpawnFailures++;
                _nextDedicatedCasevacSpawnAt = unchecked(now + 10000);
                PhysicsExperimentLog.Error(
                    "dedicated_casevac_spawn_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "casualty", response?.Casualty?.Handle ?? 0 },
                        { "crew_created", createdCrew.Count },
                    });
                DeleteDedicatedCasevacEntities(helicopter, createdCrew);
                return false;
            }
            finally
            {
                helicopterModel.MarkAsNoLongerNeeded();
                pilotModel.MarkAsNoLongerNeeded();
            }
        }

        private static void ConfigureDedicatedCasevacPilot(Ped pilot)
        {
            pilot.IsPersistent = true;
            Function.Call(Hash.SET_PED_RELATIONSHIP_GROUP_HASH,
                pilot.Handle, CopRelationshipGroupHash);
            Function.Call(Hash.REMOVE_ALL_PED_WEAPONS,
                pilot.Handle, true);
            Function.Call(Hash.SET_PED_KEEP_TASK, pilot.Handle, true);
            Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                pilot.Handle, 3, false); // never leave the aircraft
            Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                pilot.Handle, true);
        }

        private void UpdateDedicatedCasevacSupport(
            Ped player, int now, HashSet<int> eligibleHandles)
        {
            var handles = new List<int>(_aerialSupportStates.Keys);
            foreach (int handle in handles)
            {
                if (!_aerialSupportStates.TryGetValue(handle,
                        out AerialSupportState state) ||
                    !state.DedicatedCasevac) continue;
                if (state.Helicopter == null ||
                    !state.Helicopter.Exists() ||
                    !state.Helicopter.IsDriveable ||
                    state.Pilot == null || !state.Pilot.Exists() ||
                    state.Pilot.IsDead)
                {
                    ReleaseAerialSupport(handle,
                        "dedicated_casevac_aircraft_unavailable");
                    continue;
                }
                eligibleHandles.Add(handle);
                UpdateAerialCasevac(state, player, now);
            }
        }

        private static void DeleteDedicatedCasevacEntities(
            Vehicle helicopter, IEnumerable<Ped> crew)
        {
            if (crew != null)
                foreach (Ped member in crew)
                    if (member != null && member.Exists())
                    {
                        member.IsPersistent = true;
                        member.Delete();
                    }
            if (helicopter != null && helicopter.Exists())
            {
                helicopter.IsPersistent = true;
                helicopter.Delete();
            }
        }

        private void UpdateAerialReconState(
            AerialSupportState state, Ped player,
            bool lineOfSight, bool playerAggressive, int now)
        {
            if (lineOfSight)
            {
                state.LastKnownPlayerPosition = player.Position;
                state.LastVisualContactAt = now;
                if (unchecked(now - state.LastIntelRelayAt) >=
                    AerialIntelRelayIntervalMs)
                {
                    Function.Call(Hash.REPORT_POLICE_SPOTTED_PLAYER,
                        Game.Player.Handle);
                    state.LastIntelRelayAt = now;
                    _aerialIntelRelays++;
                    PhysicsExperimentLog.Info("aerial_intel_relayed",
                        AerialSupportFields(state, now,
                            new Dictionary<string, object>
                            {
                                { "line_of_sight", true },
                                { "last_known_x",
                                    state.LastKnownPlayerPosition.X },
                                { "last_known_y",
                                    state.LastKnownPlayerPosition.Y },
                                { "last_known_z",
                                    state.LastKnownPlayerPosition.Z },
                            }));
                }
            }

            ReduceAerialCrewFire(state);
            if (state.CasevacCasualtyHandle != 0 ||
                unchecked(state.CasevacDepartingUntilAt - now) > 0)
            {
                UpdateAerialCasevac(state, player, now);
                return;
            }
            if (state.RappelInsertionActive ||
                TryStartSafeRappelInsertion(state, player, now))
            {
                UpdateSafeRappelInsertion(state, player, now);
                return;
            }
            bool rappelling = Function.Call<bool>(
                Hash.IS_ANY_PED_RAPPELLING_FROM_HELI,
                state.Helicopter.Handle);
            bool unsafeInsertionZone = playerAggressive ||
                Game.Player.WantedLevel >= 4;
            int commandAge = unchecked(now - state.LastMissionCommandAt);
            float distanceToTarget = state.HasMissionTarget
                ? state.Helicopter.Position.DistanceTo(
                    state.LastMissionTarget) : float.MaxValue;
            float anchorShift = state.HasMissionTarget
                ? HorizontalDistance2D(state.LastKnownPlayerPosition,
                    state.LastMissionAnchor) : float.MaxValue;
            float distanceToPlayer = HorizontalDistance2D(
                state.Helicopter.Position, player.Position);
            bool unsafePerimeterDrift = unsafeInsertionZone &&
                distanceToPlayer < UnsafeReconInnerRadius;

            if (state.HasMissionTarget &&
                (state.BestMissionDistance == float.MaxValue ||
                 distanceToTarget <= state.BestMissionDistance -
                    NpcPhysicsExperimentPolicy.AerialOrbitProgressDistance))
            {
                state.BestMissionDistance = distanceToTarget;
                state.LastMissionProgressAt = now;
            }
            int noProgressMs = state.LastMissionProgressAt == 0
                ? commandAge : unchecked(now - state.LastMissionProgressAt);
            if (NpcPhysicsExperimentPolicy.ShouldRelinquishAerialOrbitControl(
                    state.HasMissionTarget,
                    state.ReconControlRelinquished, commandAge,
                    noProgressMs, distanceToTarget))
            {
                int taskStatus = Function.Call<int>(
                    Hash.GET_SCRIPT_TASK_STATUS, state.Pilot.Handle,
                    HeliMissionTaskHash);
                // End only our scripted pilot task.  A non-immediate clear lets
                // Rockstar's ambient helicopter intelligence resume instead of
                // repeatedly replacing it with the same failed waypoint.
                Function.Call(Hash.CLEAR_PED_TASKS, state.Pilot.Handle);
                state.ReconControlRelinquished = true;
                state.HasMissionTarget = false;
                state.LastMissionWasUnsafeEgress = false;
                _aerialReconLegStalls++;
                _aerialReconControlRelinquished++;
                PhysicsExperimentLog.Warn(
                    "aerial_recon_leg_stalled",
                    AerialSupportFields(state, now,
                        new Dictionary<string, object>
                        {
                            { "command_age_ms", commandAge },
                            { "no_progress_ms", noProgressMs },
                            { "best_target_distance",
                                state.BestMissionDistance },
                            { "target_distance", distanceToTarget },
                            { "distance_to_player", distanceToPlayer },
                            { "helicopter_speed",
                                state.Helicopter.Speed },
                            { "pilot_task_status", taskStatus },
                            { "target_x", state.LastMissionTarget.X },
                            { "target_y", state.LastMissionTarget.Y },
                            { "target_z", state.LastMissionTarget.Z },
                            { "control_relinquished", true },
                        }));
                return;
            }
            if (state.ReconControlRelinquished)
            {
                if (!unsafePerimeterDrift) return;
                state.ReconControlRelinquished = false;
                state.HasMissionTarget = false;
                state.BestMissionDistance = float.MaxValue;
                state.LastMissionProgressAt = now;
                PhysicsExperimentLog.Info(
                    "aerial_recon_control_reacquired",
                    AerialSupportFields(state, now,
                        new Dictionary<string, object>
                        {
                            { "reason", "unsafe_perimeter_drift" },
                            { "distance_to_player", distanceToPlayer },
                        }));
            }
            bool needsUnsafeEgress = unsafePerimeterDrift &&
                !state.LastMissionWasUnsafeEgress;
            if (rappelling ||
                !NpcPhysicsExperimentPolicy.ShouldIssueAerialOrbitCommand(
                    state.HasMissionTarget, commandAge,
                    distanceToTarget, anchorShift,
                    needsUnsafeEgress)) return;

            float orbitRadius = unsafeInsertionZone
                ? UnsafeReconOrbitRadius :
                AerialOrbitRadius;
            float orbitHeight = unsafeInsertionZone
                ? UnsafeReconOrbitHeight :
                AerialOrbitHeight;
            string commandReason;
            Vector3 radial;
            if (unsafePerimeterDrift)
            {
                radial = NormalizeHorizontalVector(
                    state.Helicopter.Position -
                        state.LastKnownPlayerPosition,
                    state.Helicopter.ForwardVector);
                commandReason = "unsafe_perimeter_drift";
            }
            else
            {
                bool waypointReached = state.HasMissionTarget &&
                    distanceToTarget <= NpcPhysicsExperimentPolicy
                        .AerialOrbitArrivalDistance;
                if (waypointReached) _aerialReconLegsCompleted++;
                state.OrbitPhase += 0.90f;
                radial = new Vector3(
                    (float)Math.Cos(state.OrbitPhase),
                    (float)Math.Sin(state.OrbitPhase), 0f);
                commandReason = !state.HasMissionTarget
                    ? "initial_assignment" :
                    waypointReached
                    ? "waypoint_reached" :
                    "state_transition";
            }
            Vector3 target = state.LastKnownPlayerPosition +
                radial * orbitRadius + new Vector3(0f, 0f, orbitHeight);
            Function.Call(Hash.TASK_HELI_MISSION,
                state.Pilot.Handle, state.Helicopter.Handle,
                0, 0, target.X, target.Y, target.Z,
                4, 28f, 35f, -1f, 38, 70, -1f, 0);
            state.LastMissionCommandAt = now;
            state.LastMissionTarget = target;
            state.LastMissionAnchor = state.LastKnownPlayerPosition;
            state.HasMissionTarget = true;
            state.LastMissionWasUnsafeEgress = unsafePerimeterDrift;
            state.BestMissionDistance = state.Helicopter.Position.DistanceTo(
                target);
            state.LastMissionProgressAt = now;
            state.ReconControlRelinquished = false;
            _aerialOrbitCommands++;
            PhysicsExperimentLog.Info("aerial_recon_orbit_commanded",
                AerialSupportFields(state, now,
                    new Dictionary<string, object>
                    {
                        { "target_x", target.X },
                        { "target_y", target.Y },
                        { "target_z", target.Z },
                        { "rappelling", false },
                        { "unsafe_insertion_guard",
                            unsafeInsertionZone },
                        { "command_reason", commandReason },
                        { "command_age_ms", commandAge },
                        { "previous_target_distance", distanceToTarget },
                        { "previous_anchor_shift", anchorShift },
                        { "distance_to_player", distanceToPlayer },
                    }));
        }

        private void CancelUnsafeRappelTasks(
            Vehicle helicopter, Ped pilot, bool playerAggressive,
            float distanceToPlayer, int now,
            bool approvedInsertionRelease)
        {
            foreach (Ped occupant in helicopter.Occupants)
            {
                if (occupant == null || !occupant.Exists() ||
                    occupant.IsDead || occupant.Handle == pilot.Handle)
                    continue;
                int taskStatus = Function.Call<int>(
                    Hash.GET_SCRIPT_TASK_STATUS,
                    occupant.Handle, RappelFromHeliTaskHash);
                bool taskActive =
                    NpcPhysicsExperimentPolicy.IsRappelTaskActive(
                        taskStatus);
                if (approvedInsertionRelease)
                {
                    if (_rappelLockedCrew.ContainsKey(occupant.Handle))
                        RestoreRappelDepartureLock(occupant.Handle);
                    continue;
                }
                bool blockInsertion =
                    NpcPhysicsExperimentPolicy.ShouldBlockUnsafeRappelInsertion(
                        _enhancedPoliceAi, Game.IsMissionActive,
                        Game.IsCutsceneActive, Game.Player.WantedLevel,
                        playerAggressive, distanceToPlayer,
                        occupant.IsInVehicle()) ||
                    NpcPhysicsExperimentPolicy
                        .ShouldRedirectRappelToTacticalZone(
                            _enhancedPoliceAi, Game.IsMissionActive,
                            Game.IsCutsceneActive, Game.Player.WantedLevel,
                            occupant.IsInVehicle(), taskActive);
                if (blockInsertion)
                {
                    Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                        occupant.Handle, 3, false);
                    Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                        occupant.Handle, true);
                    if (!_rappelLockedCrew.TryGetValue(occupant.Handle,
                            out RappelCrewLockState lockState))
                    {
                        lockState = new RappelCrewLockState
                        {
                            Crew = occupant,
                            Helicopter = helicopter,
                            Seat = FindPedVehicleSeat(helicopter, occupant),
                        };
                        _rappelLockedCrew[occupant.Handle] = lockState;
                        _unsafeRappelCrewLocks++;
                        PhysicsExperimentLog.Info(
                            "aerial_unsafe_rappel_departure_locked",
                            new Dictionary<string, object>
                            {
                                { "helicopter", helicopter.Handle },
                                { "ped", occupant.Handle },
                                { "distance_to_player", distanceToPlayer },
                                { "player_aggressive", playerAggressive },
                                { "wanted_level", Game.Player.WantedLevel },
                                { "seat", lockState.Seat },
                            });
                    }
                    else
                    {
                        lockState.Crew = occupant;
                        lockState.Helicopter = helicopter;
                        if (lockState.Seat < 0)
                            lockState.Seat = FindPedVehicleSeat(
                                helicopter, occupant);
                    }
                    bool cancelTask =
                        taskActive && blockInsertion;
                    bool taskJustStarted = taskActive &&
                        !lockState.RappelTaskWasActive;
                    if (taskActive) lockState.RappelRequested = true;
                    lockState.RappelTaskWasActive = taskActive;
                    if (cancelTask && taskJustStarted)
                    {
                        ForceRappelCrewIntoSeat(lockState, now,
                            "committed_task_cancelled");
                        _unsafeRappelTasksCancelled++;
                        PhysicsExperimentLog.Warn(
                            "aerial_unsafe_rappel_task_cancelled",
                            new Dictionary<string, object>
                            {
                                { "helicopter", helicopter.Handle },
                                { "ped", occupant.Handle },
                                { "task_status", taskStatus },
                                { "distance_to_player", distanceToPlayer },
                                { "game_time_ms", now },
                            });
                    }
                }
                else if (_rappelLockedCrew.ContainsKey(occupant.Handle))
                {
                    RestoreRappelDepartureLock(occupant.Handle);
                }
            }
        }

        private static int FindPedVehicleSeat(
            Vehicle vehicle, Ped ped)
        {
            if (vehicle == null || !vehicle.Exists() ||
                ped == null || !ped.Exists()) return -2;
            int maximumPassengers = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS,
                vehicle.Handle);
            for (int seat = 0; seat < maximumPassengers; seat++)
            {
                int occupant = Function.Call<int>(
                    Hash.GET_PED_IN_VEHICLE_SEAT,
                    vehicle.Handle, seat, false);
                if (occupant == ped.Handle) return seat;
            }
            return -2;
        }

        private void ForceRappelCrewIntoSeat(
            RappelCrewLockState state, int now, string reason)
        {
            Ped crew = state?.Crew;
            Vehicle helicopter = state?.Helicopter;
            if (crew == null || !crew.Exists() || crew.IsDead ||
                helicopter == null || !helicopter.Exists() ||
                state.Seat < 0) return;
            int seatedPed = Function.Call<int>(
                Hash.GET_PED_IN_VEHICLE_SEAT,
                helicopter.Handle, state.Seat, false);
            if (seatedPed != 0 && seatedPed != crew.Handle) return;
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, crew.Handle);
            if (seatedPed != crew.Handle)
            {
                Function.Call(Hash.SET_PED_INTO_VEHICLE,
                    crew.Handle, helicopter.Handle, state.Seat);
                _unsafeRappelCrewReseats++;
                PhysicsExperimentLog.Warn(
                    "aerial_unsafe_rappel_exit_intercepted",
                    new Dictionary<string, object>
                    {
                        { "helicopter", helicopter.Handle },
                        { "ped", crew.Handle },
                        { "seat", state.Seat },
                        { "reason", reason },
                    });
            }
        }

        private void PruneRappelDepartureLocks(int now)
        {
            if (_rappelLockedCrew.Count == 0) return;
            var release = new List<int>();
            foreach (KeyValuePair<int, RappelCrewLockState> pair in
                _rappelLockedCrew)
            {
                RappelCrewLockState state = pair.Value;
                Ped crew = state.Crew;
                Vehicle helicopter = state.Helicopter;
                if (crew == null || !crew.Exists() || crew.IsDead ||
                    helicopter == null || !helicopter.Exists())
                {
                    release.Add(pair.Key);
                    continue;
                }
                bool stillInHelicopter = Function.Call<bool>(
                    Hash.IS_PED_IN_VEHICLE, crew.Handle,
                    helicopter.Handle, false);
                if (stillInHelicopter) continue;
                float helicopterHeight = Function.Call<float>(
                    Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND,
                    helicopter.Handle);
                bool seatFree = state.Seat >= 0 && Function.Call<bool>(
                    Hash.IS_VEHICLE_SEAT_FREE,
                    helicopter.Handle, state.Seat, false);
                float distanceToHelicopter = crew.Position.DistanceTo(
                    helicopter.Position);
                if (NpcPhysicsExperimentPolicy.ShouldRecoverUnsafeRappelExit(
                        helicopterHeight, seatFree,
                        distanceToHelicopter))
                {
                    // Some ambient police exits never expose
                    // SCRIPT_TASK_RAPPEL_FROM_HELI as active.  The airborne
                    // seat departure is itself the reliable intent signal.
                    if (!state.RappelRequested)
                    {
                        state.RappelRequested = true;
                        _rappelRequestsInferredFromExit++;
                        PhysicsExperimentLog.Info(
                            "aerial_rappel_request_inferred_from_exit",
                            new Dictionary<string, object>
                            {
                                { "helicopter", helicopter.Handle },
                                { "ped", crew.Handle },
                                { "seat", state.Seat },
                                { "helicopter_height", helicopterHeight },
                                { "distance_to_helicopter",
                                    distanceToHelicopter },
                                { "helicopter_speed", helicopter.Speed },
                                { "game_time_ms", now },
                                { "wanted_level", Game.Player.WantedLevel },
                            });
                    }
                    ForceRappelCrewIntoSeat(
                        state, now, "airborne_exit_recovered");
                    _unsafeRappelExitsIntercepted++;
                    continue;
                }
                release.Add(pair.Key);
            }
            foreach (int handle in release)
                RestoreRappelDepartureLock(handle);
        }

        private void RestoreRappelDepartureLock(int handle)
        {
            if (!_rappelLockedCrew.TryGetValue(handle,
                    out RappelCrewLockState state)) return;
            _rappelLockedCrew.Remove(handle);
            Ped crew = state.Crew;
            if (crew == null || !crew.Exists() || crew.IsDead) return;
            Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                crew.Handle, 3, true);
            Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                crew.Handle, false);
        }

        private void ReleaseAllRappelDepartureLocks()
        {
            var handles = new List<int>(_rappelLockedCrew.Keys);
            foreach (int handle in handles)
                RestoreRappelDepartureLock(handle);
        }

        private bool TryStartSafeRappelInsertion(
            AerialSupportState state, Ped player, int now)
        {
            if (state == null || state.Helicopter == null ||
                !state.Helicopter.Exists() || state.RappelInsertionActive)
                return false;
            var requestedCrew = new List<RappelCrewLockState>();
            foreach (RappelCrewLockState lockState in
                _rappelLockedCrew.Values)
                if (lockState.RappelRequested &&
                    lockState.Helicopter != null &&
                    lockState.Helicopter.Exists() &&
                    lockState.Helicopter.Handle == state.Helicopter.Handle)
                    requestedCrew.Add(lockState);
            if (requestedCrew.Count == 0) return false;

            if (!PoliceTacticsCoordinator.TryGetAerialInsertionRearZone(
                    state.Helicopter.Position, out Vector3 rearPoint,
                    out Vector3 awayFromThreat, out Vector3 formationRight,
                    out Vector3 threatPosition, out int squadId))
            {
                LogSafeRappelDeferral(state, player, now,
                    "no_established_firing_line", requestedCrew.Count,
                    null);
                return false;
            }

            bool rooftop = TryResolveRooftopInsertion(
                state.Helicopter, rearPoint, awayFromThreat,
                formationRight, threatPosition,
                out Vector3 insertionPoint, out float surfaceNormalZ,
                out RooftopInsertionDiagnostics diagnostics);
            float distanceFromThreat = HorizontalDistance2D(
                insertionPoint, threatPosition);
            if (!NpcPhysicsExperimentPolicy.CanUseAerialInsertionZone(
                    true, 14f, distanceFromThreat,
                    rooftop, surfaceNormalZ))
            {
                LogSafeRappelDeferral(state, player, now,
                    "rear_zone_failed_safety", requestedCrew.Count,
                    diagnostics);
                return false;
            }

            state.RappelInsertionActive = true;
            state.RappelReleaseAuthorized = false;
            state.RappelInsertionRooftop = rooftop;
            state.RappelInsertionSquadId = squadId;
            state.RappelInsertionStartedAt = now;
            state.RappelInsertionStableAt = 0;
            state.RappelReleaseAt = 0;
            state.RappelInsertionPoint = insertionPoint;
            state.RappelInsertionCrew.Clear();
            foreach (RappelCrewLockState lockState in requestedCrew)
                state.RappelInsertionCrew[lockState.Crew.Handle] =
                    lockState.Crew;
            state.HasMissionTarget = false;
            state.LastMissionCommandAt = int.MinValue / 2;
            state.LastRappelDeferralLogAt = 0;
            state.LastRappelDeferralReason = null;
            CommandSafeRappelApproach(state, now);
            _safeRappelInsertionsPlanned++;
            PhysicsExperimentLog.Info("aerial_safe_rappel_planned",
                AerialSupportFields(state, now,
                    new Dictionary<string, object>
                    {
                        { "squad", squadId },
                        { "rooftop", rooftop },
                        { "selection", rooftop ? "rooftop" :
                            "rear_ground" },
                        { "insertion_x", insertionPoint.X },
                        { "insertion_y", insertionPoint.Y },
                        { "insertion_z", insertionPoint.Z },
                        { "surface_normal_z", surfaceNormalZ },
                        { "distance_from_threat", distanceFromThreat },
                        { "crew", requestedCrew.Count },
                        { "rooftop_candidates", diagnostics.Candidates },
                        { "rooftop_ray_misses", diagnostics.RayMisses },
                        { "rooftop_slope_rejected",
                            diagnostics.SlopeRejected },
                        { "rooftop_elevation_rejected",
                            diagnostics.ElevationRejected },
                        { "rooftop_navmesh_rejected",
                            diagnostics.NavmeshRejected },
                        { "rooftop_threat_rejected",
                            diagnostics.ThreatRejected },
                        { "rooftop_accepted", diagnostics.Accepted },
                    }));
            return true;
        }

        private void LogSafeRappelDeferral(
            AerialSupportState state, Ped player, int now, string reason,
            int requestedCrew, RooftopInsertionDiagnostics diagnostics)
        {
            _safeRappelPlanDeferrals++;
            bool sameReason = string.Equals(
                state.LastRappelDeferralReason, reason,
                StringComparison.Ordinal);
            if (sameReason && unchecked(now -
                    state.LastRappelDeferralLogAt) <
                AerialDeferralLogIntervalMs) return;
            state.LastRappelDeferralLogAt = now;
            state.LastRappelDeferralReason = reason;
            diagnostics = diagnostics ?? new RooftopInsertionDiagnostics();
            PhysicsExperimentLog.Info("aerial_safe_rappel_deferred",
                AerialSupportFields(state, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "requested_crew", requestedCrew },
                        { "wanted_level", Game.Player.WantedLevel },
                        { "distance_to_player", player == null ? -1f :
                            HorizontalDistance2D(
                                state.Helicopter.Position,
                                player.Position) },
                        { "rooftop_candidates", diagnostics.Candidates },
                        { "rooftop_ray_misses", diagnostics.RayMisses },
                        { "rooftop_slope_rejected",
                            diagnostics.SlopeRejected },
                        { "rooftop_elevation_rejected",
                            diagnostics.ElevationRejected },
                        { "rooftop_navmesh_rejected",
                            diagnostics.NavmeshRejected },
                        { "rooftop_threat_rejected",
                            diagnostics.ThreatRejected },
                    }));
        }

        private static bool TryResolveRooftopInsertion(
            Vehicle helicopter, Vector3 rearPoint,
            Vector3 awayFromThreat, Vector3 formationRight,
            Vector3 threatPosition, out Vector3 insertionPoint,
            out float surfaceNormalZ,
            out RooftopInsertionDiagnostics diagnostics)
        {
            insertionPoint = rearPoint;
            surfaceNormalZ = 1f;
            diagnostics = new RooftopInsertionDiagnostics();
            float[] depths = { 3f, 12f, 22f };
            float[] lateralOffsets = { 0f, 18f, -18f, 30f, -30f };
            float bestDistance = float.MaxValue;
            bool found = false;
            foreach (float depth in depths)
            {
                foreach (float lateral in lateralOffsets)
                {
                    diagnostics.Candidates++;
                    Vector3 sample = rearPoint + awayFromThreat * depth +
                        formationRight * lateral;
                    RaycastResult raycast = World.Raycast(
                        sample + new Vector3(0f, 0f, 75f),
                        sample - new Vector3(0f, 0f, 12f),
                        IntersectFlags.Map, helicopter);
                    if (!raycast.DidHit)
                    {
                        diagnostics.RayMisses++;
                        continue;
                    }
                    if (raycast.SurfaceNormal.Z < 0.70f)
                    {
                        diagnostics.SlopeRejected++;
                        continue;
                    }
                    if (raycast.HitPosition.Z < rearPoint.Z + 4f ||
                        raycast.HitPosition.Z > rearPoint.Z + 65f)
                    {
                        diagnostics.ElevationRejected++;
                        continue;
                    }
                    Vector3 safe = World.GetSafeCoordForPed(
                        raycast.HitPosition + new Vector3(0f, 0f, 0.35f),
                        true, 0);
                    if (safe == Vector3.Zero ||
                        safe.DistanceTo(raycast.HitPosition) > 7f ||
                        Math.Abs(safe.Z - raycast.HitPosition.Z) > 2.5f)
                    {
                        diagnostics.NavmeshRejected++;
                        continue;
                    }
                    float threatDistance = HorizontalDistance2D(
                        safe, threatPosition);
                    if (!NpcPhysicsExperimentPolicy.CanUseAerialInsertionZone(
                            true, 14f + depth, threatDistance,
                            true, raycast.SurfaceNormal.Z))
                    {
                        diagnostics.ThreatRejected++;
                        continue;
                    }
                    diagnostics.Accepted++;
                    float aircraftDistance = HorizontalDistance2D(
                        helicopter.Position, safe);
                    if (aircraftDistance >= bestDistance) continue;
                    bestDistance = aircraftDistance;
                    insertionPoint = safe;
                    surfaceNormalZ = raycast.SurfaceNormal.Z;
                    found = true;
                }
            }
            return found;
        }

        private void UpdateSafeRappelInsertion(
            AerialSupportState state, Ped player, int now)
        {
            if (!state.RappelInsertionActive) return;
            if (state.Helicopter == null || !state.Helicopter.Exists() ||
                state.Pilot == null || !state.Pilot.Exists() ||
                state.Pilot.IsDead)
            {
                AbortSafeRappelInsertion(state, now,
                    "aircraft_unavailable");
                return;
            }
            SyncPendingRappelCrew(state);
            if (!state.RappelReleaseAuthorized)
            {
                int approachElapsed = unchecked(
                    now - state.RappelInsertionStartedAt);
                if (approachElapsed >= RappelInsertionApproachTimeoutMs)
                {
                    AbortSafeRappelInsertion(state, now,
                        "approach_timeout");
                    return;
                }
                if (unchecked(now - state.LastMissionCommandAt) >=
                    RappelInsertionMissionRefreshMs)
                    CommandSafeRappelApproach(state, now);

                float horizontalDistance = HorizontalDistance2D(
                    state.Helicopter.Position,
                    state.RappelInsertionPoint);
                float heightAboveInsertion =
                    state.Helicopter.Position.Z -
                    state.RappelInsertionPoint.Z;
                bool stableGeometry = horizontalDistance <= 10f &&
                    heightAboveInsertion >= 8f &&
                    heightAboveInsertion <= 24f &&
                    state.Helicopter.Speed <= 6f;
                if (!stableGeometry)
                {
                    state.RappelInsertionStableAt = 0;
                    return;
                }
                if (state.RappelInsertionStableAt == 0)
                    state.RappelInsertionStableAt = now;
                int stableElapsed = unchecked(
                    now - state.RappelInsertionStableAt);
                if (!NpcPhysicsExperimentPolicy.ShouldReleaseRappelCrew(
                        horizontalDistance, heightAboveInsertion,
                        state.Helicopter.Speed, stableElapsed)) return;

                int released = 0;
                var crew = new List<Ped>(
                    state.RappelInsertionCrew.Values);
                foreach (Ped member in crew)
                {
                    if (member == null || !member.Exists() ||
                        member.IsDead || !Function.Call<bool>(
                            Hash.IS_PED_IN_VEHICLE, member.Handle,
                            state.Helicopter.Handle, false)) continue;
                    RestoreRappelDepartureLock(member.Handle);
                    Function.Call(Hash.TASK_RAPPEL_FROM_HELI,
                        member.Handle, 8f);
                    released++;
                }
                if (released == 0)
                {
                    AbortSafeRappelInsertion(state, now,
                        "no_eligible_crew");
                    return;
                }
                state.RappelReleaseAuthorized = true;
                state.RappelReleaseAt = now;
                PhysicsExperimentLog.Info(
                    "aerial_safe_rappel_released",
                    AerialSupportFields(state, now,
                        new Dictionary<string, object>
                        {
                            { "squad", state.RappelInsertionSquadId },
                            { "rooftop",
                                state.RappelInsertionRooftop },
                            { "crew_released", released },
                            { "horizontal_distance",
                                horizontalDistance },
                            { "height_above_insertion",
                                heightAboveInsertion },
                            { "helicopter_speed",
                                state.Helicopter.Speed },
                        }));
                return;
            }

            int crewStillAboard = 0;
            foreach (Ped member in state.RappelInsertionCrew.Values)
                if (member != null && member.Exists() && !member.IsDead &&
                    Function.Call<bool>(Hash.IS_PED_IN_VEHICLE,
                        member.Handle, state.Helicopter.Handle, false))
                    crewStillAboard++;
            if (crewStillAboard == 0)
            {
                CompleteSafeRappelInsertion(state, now);
                return;
            }
            if (unchecked(now - state.RappelReleaseAt) >=
                RappelInsertionCompletionTimeoutMs)
                AbortSafeRappelInsertion(state, now,
                    "crew_exit_timeout");
        }

        private void SyncPendingRappelCrew(AerialSupportState state)
        {
            foreach (RappelCrewLockState lockState in
                _rappelLockedCrew.Values)
                if (lockState.RappelRequested &&
                    lockState.Helicopter != null &&
                    lockState.Helicopter.Exists() &&
                    lockState.Helicopter.Handle ==
                        state.Helicopter.Handle &&
                    lockState.Crew != null && lockState.Crew.Exists())
                    state.RappelInsertionCrew[lockState.Crew.Handle] =
                        lockState.Crew;
        }

        private static void CommandSafeRappelApproach(
            AerialSupportState state, int now)
        {
            Vector3 target = state.RappelInsertionPoint +
                new Vector3(0f, 0f, RappelInsertionHoverHeight);
            Function.Call(Hash.TASK_HELI_MISSION,
                state.Pilot.Handle, state.Helicopter.Handle,
                0, 0, target.X, target.Y, target.Z,
                4, 26f, 12f, -1f, 18, 25, -1f, 0);
            state.LastMissionCommandAt = now;
            state.LastMissionTarget = target;
            state.LastMissionAnchor = state.RappelInsertionPoint;
            state.HasMissionTarget = true;
            state.LastMissionWasUnsafeEgress = false;
        }

        private void CompleteSafeRappelInsertion(
            AerialSupportState state, int now)
        {
            _safeRappelInsertionsCompleted++;
            PhysicsExperimentLog.Info(
                "aerial_safe_rappel_completed",
                AerialSupportFields(state, now,
                    new Dictionary<string, object>
                    {
                        { "squad", state.RappelInsertionSquadId },
                        { "rooftop", state.RappelInsertionRooftop },
                        { "crew", state.RappelInsertionCrew.Count },
                        { "casevac_eligible", true },
                    }));
            ResetSafeRappelInsertion(state);
        }

        private void AbortSafeRappelInsertion(
            AerialSupportState state, int now, string reason)
        {
            _safeRappelInsertionsAborted++;
            PhysicsExperimentLog.Warn(
                "aerial_safe_rappel_aborted",
                AerialSupportFields(state, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "squad", state.RappelInsertionSquadId },
                        { "rooftop", state.RappelInsertionRooftop },
                        { "crew", state.RappelInsertionCrew.Count },
                    }));
            ResetSafeRappelInsertion(state);
        }

        private static void ResetSafeRappelInsertion(
            AerialSupportState state)
        {
            state.RappelInsertionActive = false;
            state.RappelReleaseAuthorized = false;
            state.RappelInsertionRooftop = false;
            state.RappelInsertionSquadId = 0;
            state.RappelInsertionStartedAt = 0;
            state.RappelInsertionStableAt = 0;
            state.RappelReleaseAt = 0;
            state.RappelInsertionPoint = Vector3.Zero;
            state.RappelInsertionCrew.Clear();
            state.HasMissionTarget = false;
            state.LastMissionWasUnsafeEgress = false;
            state.LastMissionCommandAt = int.MinValue / 2;
        }

        private void ChangeAerialSupportRole(
            AerialSupportState state, AerialSupportRole role,
            int now, string reason)
        {
            AerialSupportRole previous = state.Role;
            state.Role = role;
            state.LastMissionCommandAt = int.MinValue / 2;
            state.HasMissionTarget = false;
            state.LastMissionWasUnsafeEgress = false;
            state.BestMissionDistance = float.MaxValue;
            state.LastMissionProgressAt = now;
            state.ReconControlRelinquished = false;
            _aerialRoleSwitches++;
            PhysicsExperimentLog.Info("aerial_role_switched",
                AerialSupportFields(state, now,
                    new Dictionary<string, object>
                    {
                        { "previous_role", previous.ToString() },
                        { "new_role", role.ToString() },
                        { "reason", reason },
                    }));
        }

        private void TryAssignCasevacRequest(Ped player, int now)
        {
            if (_cohesionResponses.Count == 0) return;
            foreach (CohesionResponse response in
                _cohesionResponses.Values)
            {
                if (response.Phase != CohesionPhase.AwaitCasevac ||
                    response.CasevacHelicopterHandle != 0 ||
                    response.Casualty == null ||
                    !response.Casualty.Exists()) continue;
                if (response.CasevacLandingPoint.DistanceTo(
                        player.Position) < 28f)
                {
                    LogCasevacDeferral(response, now,
                        "landing_too_close_to_threat", 0);
                    continue;
                }

                bool active = HasAerialRole(AerialSupportRole.Casevac);
                int cooldownRemaining = Math.Max(0, unchecked(
                    _nextDedicatedCasevacSpawnAt - now));
                if (!NpcPhysicsExperimentPolicy.ShouldSpawnDedicatedCasevac(
                        _enhancedPoliceAi, Game.IsMissionActive,
                        Game.IsCutsceneActive, Game.Player.WantedLevel,
                        true, active, cooldownRemaining))
                {
                    string reason = active
                        ? "dedicated_casevac_active"
                        : cooldownRemaining > 0
                        ? "dedicated_casevac_cooldown"
                        : "dedicated_casevac_disabled";
                    LogCasevacDeferral(response, now, reason,
                        active ? 1 : 0);
                    continue;
                }
                if (IsCasevacLandingBlocked(
                        response.CasevacLandingPoint, 0))
                {
                    LogCasevacDeferral(response, now,
                        "landing_blocked", 0);
                    continue;
                }
                TrySpawnDedicatedCasevac(response, player, now);
                return;
            }
        }

        private static bool IsCasevacLandingBlocked(
            Vector3 landingPoint, int ignoredVehicleHandle)
        {
            foreach (Vehicle nearby in World.GetNearbyVehicles(
                landingPoint, 7f, new Model[0]))
                if (nearby != null && nearby.Exists() &&
                    nearby.Handle != ignoredVehicleHandle)
                    return true;
            return false;
        }

        private void LogCasevacDeferral(
            CohesionResponse response, int now, string reason,
            int dedicatedAircraft)
        {
            bool sameReason = string.Equals(
                response.LastCasevacDeferralReason, reason,
                StringComparison.Ordinal);
            if (sameReason && unchecked(now -
                    response.LastCasevacDeferralAt) <
                AerialDeferralLogIntervalMs) return;
            response.LastCasevacDeferralAt = now;
            response.LastCasevacDeferralReason = reason;
            _casevacDeferrals++;
            PhysicsExperimentLog.Info("aerial_casevac_deferred",
                CohesionFields(response, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "dedicated_casevac_aircraft",
                            dedicatedAircraft },
                        { "landing_x", response.CasevacLandingPoint.X },
                        { "landing_y", response.CasevacLandingPoint.Y },
                        { "landing_z", response.CasevacLandingPoint.Z },
                    }));
        }

        private void UpdateAerialCasevac(
            AerialSupportState state, Ped player, int now)
        {
            if (state.DedicatedCasevac &&
                state.CasevacDepartureStartedAt != 0)
            {
                float distanceFromScene = HorizontalDistance2D(
                    state.Helicopter.Position, player.Position);
                int departureElapsed = unchecked(
                    now - state.CasevacDepartureStartedAt);
                if (NpcPhysicsExperimentPolicy.
                        ShouldDespawnDedicatedCasevac(
                            true, true, distanceFromScene,
                            departureElapsed))
                {
                    ReleaseAerialSupport(state.Helicopter.Handle,
                        "dedicated_casevac_flyout_complete");
                    return;
                }
                if (unchecked(now - state.LastMissionCommandAt) >=
                    CasevacMissionRefreshMs)
                {
                    Vector3 target = state.CasevacDepartureTarget;
                    Function.Call(Hash.TASK_HELI_MISSION,
                        state.Pilot.Handle, state.Helicopter.Handle,
                        0, 0, target.X, target.Y, target.Z,
                        4, 40f, 30f, -1f, 70, 40, 75f, 5120);
                    state.LastMissionCommandAt = now;
                    PhysicsExperimentLog.Info(
                        "dedicated_casevac_flyout_commanded",
                        AerialSupportFields(state, now,
                            new Dictionary<string, object>
                            {
                                { "distance_from_scene",
                                    distanceFromScene },
                                { "departure_elapsed_ms",
                                    departureElapsed },
                            }));
                }
                return;
            }
            if (unchecked(state.CasevacDepartingUntilAt - now) > 0)
            {
                if (unchecked(now - state.LastMissionCommandAt) >=
                    CasevacMissionRefreshMs)
                {
                    Vector3 target = state.CasevacDepartureTarget;
                    Function.Call(Hash.TASK_HELI_MISSION,
                        state.Pilot.Handle, state.Helicopter.Handle,
                        0, 0, target.X, target.Y, target.Z,
                        4, 32f, 20f, -1f, 70, 35, 20f, 4096);
                    state.LastMissionCommandAt = now;
                }
                return;
            }
            if (state.CasevacDepartingUntilAt != 0)
            {
                state.CasevacDepartingUntilAt = 0;
                state.CasevacDepartureTarget = Vector3.Zero;
            }

            if (!_cohesionResponses.TryGetValue(
                    state.CasevacCasualtyHandle,
                    out CohesionResponse response) ||
                response.Casualty == null ||
                !response.Casualty.Exists())
            {
                state.CasevacCasualtyHandle = 0;
                return;
            }

            if (response.Phase == CohesionPhase.BoardingCasevac)
            {
                bool boarded = response.Casualty.IsInVehicle() &&
                    Function.Call<int>(Hash.GET_VEHICLE_PED_IS_IN,
                        response.Casualty.Handle, false) ==
                        state.Helicopter.Handle;
                if (boarded)
                {
                    int casualtyHandle = response.Casualty.Handle;
                    Vector3 completedLanding =
                        response.CasevacLandingPoint;
                    Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                        response.Casualty.Handle, true);
                    Function.Call(Hash.SET_PED_KEEP_TASK,
                        response.Casualty.Handle, true);
                    Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                        response.Casualty.Handle, 3, false);
                    CompleteCasevacResponse(response, now);
                    state.CasevacCasualtyHandle = 0;
                    _casevacBoardings++;
                    _casevacCompletions++;
                    if (state.DedicatedCasevac)
                        _dedicatedCasevacPassengersLoaded++;
                    if (state.DedicatedCasevac &&
                        TryAssignNextCasevacPassenger(
                            state, completedLanding, now))
                    {
                        PhysicsExperimentLog.Info(
                            "dedicated_casevac_passenger_loaded",
                            AerialSupportFields(state, now,
                                new Dictionary<string, object>
                                {
                                    { "casualty", casualtyHandle },
                                    { "additional_pickup_assigned", true },
                                }));
                        return;
                    }
                    BeginCasevacDeparture(state, completedLanding,
                        player, now, "casualties_loaded");
                }
                return;
            }

            if (response.Phase != CohesionPhase.AwaitCasevac) return;
            Vector3 landing = response.CasevacLandingPoint;
            float horizontalDistance = HorizontalDistance2D(
                state.Helicopter.Position, landing);
            float height = Function.Call<float>(
                Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND,
                state.Helicopter.Handle);
            if (horizontalDistance <= 11f && height <= 4.5f &&
                state.Helicopter.Speed <= 6f)
            {
                int seat = FindFreeCasevacSeat(state.Helicopter);
                if (seat < 0)
                {
                    AbortCasevac(response, now, "no_free_seat");
                    return;
                }
                response.Phase = CohesionPhase.BoardingCasevac;
                response.PhaseStartedAt = now;
                response.CasevacBoardingStartedAt = now;
                Function.Call(Hash.TASK_ENTER_VEHICLE,
                    response.Casualty.Handle,
                    state.Helicopter.Handle,
                    CasevacBoardingTimeoutMs, seat, 1.5f, 1, 0);
                PhysicsExperimentLog.Info("aerial_casevac_boarding",
                    CohesionFields(response, now,
                        new Dictionary<string, object>
                        {
                            { "seat", seat },
                            { "helicopter_height", height },
                            { "landing_distance", horizontalDistance },
                        }));
                return;
            }

            if (unchecked(now - state.LastMissionCommandAt) <
                CasevacMissionRefreshMs) return;
            Function.Call(Hash.TASK_HELI_MISSION,
                state.Pilot.Handle, state.Helicopter.Handle,
                0, 0, landing.X, landing.Y, landing.Z,
                20, 24f, 6f, -1f, 28, 5, 14f, 4128);
            state.LastMissionCommandAt = now;
            PhysicsExperimentLog.Info("aerial_casevac_landing_commanded",
                CohesionFields(response, now,
                    new Dictionary<string, object>
                    {
                        { "helicopter_height", height },
                        { "landing_distance", horizontalDistance },
                    }));
        }

        private bool TryAssignNextCasevacPassenger(
            AerialSupportState state, Vector3 completedLanding, int now)
        {
            int freeSeat = FindFreeCasevacSeat(state.Helicopter);
            foreach (CohesionResponse candidate in
                _cohesionResponses.Values)
            {
                bool awaiting = candidate != null &&
                    candidate.Phase == CohesionPhase.AwaitCasevac;
                bool assigned = candidate != null &&
                    candidate.CasevacHelicopterHandle != 0;
                float landingDistance = candidate == null
                    ? float.MaxValue : HorizontalDistance2D(
                        candidate.CasevacLandingPoint, completedLanding);
                if (!NpcPhysicsExperimentPolicy.CanBatchCasevacCasualty(
                        awaiting, assigned, freeSeat >= 0,
                        landingDistance) ||
                    candidate.Casualty == null ||
                    !candidate.Casualty.Exists() ||
                    candidate.Casualty.IsDead)
                    continue;
                state.CasevacCasualtyHandle =
                    candidate.Casualty.Handle;
                state.LastMissionCommandAt = int.MinValue / 2;
                candidate.CasevacHelicopterHandle =
                    state.Helicopter.Handle;
                candidate.LastCasevacDeferralAt = 0;
                candidate.LastCasevacDeferralReason = null;
                _casevacAssignments++;
                _dedicatedCasevacBatchAssignments++;
                PhysicsExperimentLog.Info(
                    "dedicated_casevac_batch_assigned",
                    CohesionFields(candidate, now,
                        new Dictionary<string, object>
                        {
                            { "seat", freeSeat },
                            { "landing_point_distance",
                                landingDistance },
                        }));
                return true;
            }
            return false;
        }

        private void BeginCasevacDeparture(
            AerialSupportState state, Vector3 landingPoint,
            Ped player, int now, string reason)
        {
            Vector3 away = NormalizeHorizontalVector(
                landingPoint - player.Position,
                state.Helicopter.ForwardVector);
            state.CasevacDepartureTarget = landingPoint + away * 190f +
                new Vector3(0f, 0f, 65f);
            state.CasevacDepartureStartedAt = now;
            state.CasevacDepartingUntilAt = unchecked(now + 15000);
            state.LastMissionCommandAt = int.MinValue / 2;
            PhysicsExperimentLog.Info(
                state.DedicatedCasevac
                    ? "dedicated_casevac_departing"
                    : "aerial_casevac_departing",
                AerialSupportFields(state, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "departure_x", state.CasevacDepartureTarget.X },
                        { "departure_y", state.CasevacDepartureTarget.Y },
                        { "departure_z", state.CasevacDepartureTarget.Z },
                    }));
        }

        private void AbortCasevac(
            CohesionResponse response, int now, string reason)
        {
            AerialSupportState failedState = null;
            if (response.CasevacHelicopterHandle != 0 &&
                _aerialSupportStates.TryGetValue(
                    response.CasevacHelicopterHandle,
                    out AerialSupportState state))
            {
                failedState = state;
                state.CasevacCasualtyHandle = 0;
                state.LastMissionCommandAt = int.MinValue / 2;
            }
            response.CasevacHelicopterHandle = 0;
            response.CasevacBoardingStartedAt = 0;
            response.Phase = CohesionPhase.AwaitCasevac;
            response.PhaseStartedAt = now;
            response.Casualty.Task.StandStill(20000);
            _casevacFailures++;
            PhysicsExperimentLog.Warn("aerial_casevac_aborted",
                CohesionFields(response, now,
                    new Dictionary<string, object> { { "reason", reason } }));
            if (failedState != null && failedState.DedicatedCasevac &&
                failedState.Helicopter != null &&
                failedState.Helicopter.Exists())
                BeginCasevacDeparture(failedState,
                    response.CasevacLandingPoint,
                    Game.Player.Character, now,
                    "pickup_aborted_" + reason);
        }

        private void CompleteCasevacResponse(
            CohesionResponse response, int now)
        {
            int casualtyHandle = response.Casualty.Handle;
            if (response.Rescuer != null && response.Rescuer.Exists())
            {
                if (response.Threat != null && response.Threat.Exists() &&
                    !response.Threat.IsDead)
                    Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                        response.Rescuer.Handle,
                        response.Threat.Handle, 5000, false);
                else
                    response.Rescuer.Task.WanderAround();
            }
            RestoreCohesionCoverer(response);
            _cohesionResponses.Remove(casualtyHandle);
            _cohesionRescuesCompleted++;
            PhysicsExperimentLog.Info("cohesion_rescue_completed",
                CohesionFields(response, now,
                    new Dictionary<string, object>
                    {
                        { "completion_reason", "casevac_boarded" },
                    }));
        }

        private static int FindFreeCasevacSeat(Vehicle helicopter)
        {
            if (helicopter == null || !helicopter.Exists()) return -1;
            int maximumPassengers = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS,
                helicopter.Handle);
            for (int seat = 0; seat < maximumPassengers; seat++)
                if (Function.Call<bool>(Hash.IS_VEHICLE_SEAT_FREE,
                        helicopter.Handle, seat, false))
                    return seat;
            return -1;
        }

        private static Vector3 NormalizeHorizontalVector(
            Vector3 value, Vector3 fallback)
        {
            value.Z = 0f;
            float length = (float)Math.Sqrt(
                value.X * value.X + value.Y * value.Y);
            if (length >= 0.001f)
                return new Vector3(value.X / length,
                    value.Y / length, 0f);
            fallback.Z = 0f;
            float fallbackLength = (float)Math.Sqrt(
                fallback.X * fallback.X + fallback.Y * fallback.Y);
            return fallbackLength < 0.001f
                ? new Vector3(0f, 1f, 0f)
                : new Vector3(fallback.X / fallbackLength,
                    fallback.Y / fallbackLength, 0f);
        }

        private static float HorizontalDistance2D(
            Vector3 left, Vector3 right)
        {
            float x = left.X - right.X;
            float y = left.Y - right.Y;
            return (float)Math.Sqrt(x * x + y * y);
        }

        private static void ReduceAerialCrewFire(
            AerialSupportState state)
        {
            Ped[] occupants = state.Helicopter.Occupants;
            var currentCrew = new HashSet<int>();
            foreach (Ped occupant in occupants)
            {
                if (occupant == null || !occupant.Exists() ||
                    occupant.IsDead || occupant.Handle == state.Pilot.Handle)
                    continue;
                currentCrew.Add(occupant.Handle);
                Function.Call(Hash.SET_PED_SHOOT_RATE,
                    occupant.Handle, 5);
                state.ReducedFireCrew[occupant.Handle] = occupant;
            }

            var departed = new List<int>();
            foreach (KeyValuePair<int, Ped> pair in state.ReducedFireCrew)
            {
                if (currentCrew.Contains(pair.Key)) continue;
                RestoreAerialCrewMemberFire(pair.Value);
                departed.Add(pair.Key);
            }
            foreach (int handle in departed)
                state.ReducedFireCrew.Remove(handle);
        }

        private void ReleaseAllAerialSupport(string reason)
        {
            if (_aerialSupportStates.Count == 0) return;
            var assigned = new List<int>(_aerialSupportStates.Keys);
            foreach (int handle in assigned)
                ReleaseAerialSupport(handle, reason);
        }

        private void ReleaseAerialSupport(int helicopterHandle,
            string reason)
        {
            if (!_aerialSupportStates.TryGetValue(helicopterHandle,
                    out AerialSupportState state)) return;
            if (state.CasevacCasualtyHandle != 0 &&
                _cohesionResponses.TryGetValue(
                    state.CasevacCasualtyHandle,
                    out CohesionResponse response))
            {
                response.CasevacHelicopterHandle = 0;
                response.CasevacBoardingStartedAt = 0;
                response.Phase = CohesionPhase.AwaitCasevac;
                response.PhaseStartedAt = Game.GameTime;
                _casevacFailures++;
                PhysicsExperimentLog.Warn(
                    "aerial_casevac_aircraft_released",
                    CohesionFields(response, Game.GameTime,
                        new Dictionary<string, object>
                        {
                            { "reason", reason },
                        }));
            }
            var ownedCrew = new List<Ped>();
            if (state.DedicatedCasevac && state.Helicopter != null &&
                state.Helicopter.Exists())
                foreach (Ped crew in state.Helicopter.Occupants)
                    if (crew != null && crew.Exists())
                        ownedCrew.Add(crew);
            foreach (Ped crew in state.ReducedFireCrew.Values)
                RestoreAerialCrewMemberFire(crew);
            state.ReducedFireCrew.Clear();
            if (state.Helicopter != null && state.Helicopter.Exists())
                foreach (Ped crew in state.Helicopter.Occupants)
                    if (crew != null)
                        RestoreRappelDepartureLock(crew.Handle);
            _aerialSupportStates.Remove(helicopterHandle);
            if (state.Role == AerialSupportRole.Recon)
                _aerialReconReleases++;
            PhysicsExperimentLog.Info(state.DedicatedCasevac
                    ? "dedicated_casevac_despawned"
                    : "aerial_recon_released",
                AerialSupportFields(state, Game.GameTime,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "owned_occupants", ownedCrew.Count },
                        { "evacuated_passengers",
                            Math.Max(0, ownedCrew.Count - 1) },
                    }));
            if (state.DedicatedCasevac)
            {
                _dedicatedCasevacDespawns++;
                DeleteDedicatedCasevacEntities(
                    state.Helicopter, ownedCrew);
            }
        }

        private static void RestoreAerialCrewMemberFire(Ped crew)
        {
            if (crew == null || !crew.Exists() || crew.IsDead) return;
            // Rockstar commonly configures helicopter/security crew around 40.
            // We only modify shoot cadence, so no combat task or weapon state
            // needs to be guessed or reconstructed when recon duty ends.
            Function.Call(Hash.SET_PED_SHOOT_RATE, crew.Handle, 40);
        }

        private static Dictionary<string, object> AerialSupportFields(
            AerialSupportState state, int now,
            Dictionary<string, object> fields)
        {
            fields = fields ?? new Dictionary<string, object>();
            fields["helicopter"] = state?.Helicopter?.Handle ?? 0;
            fields["pilot"] = state?.Pilot?.Handle ?? 0;
            fields["role"] = state?.Role.ToString() ?? "None";
            fields["dedicated_casevac"] = state != null &&
                state.DedicatedCasevac;
            fields["reduced_fire_crew"] =
                state?.ReducedFireCrew.Count ?? 0;
            fields["assigned_elapsed_ms"] = state == null
                ? 0 : unchecked(now - state.AssignedAt);
            fields["visual_contact_age_ms"] = state == null
                ? 0 : unchecked(now - state.LastVisualContactAt);
            fields["casevac_casualty"] =
                state?.CasevacCasualtyHandle ?? 0;
            fields["casevac_passengers_aboard"] = state == null ||
                state.Helicopter == null || !state.Helicopter.Exists()
                ? 0 : Math.Max(0,
                    state.Helicopter.Occupants.Length - 1);
            fields["casevac_departing"] = state != null &&
                (unchecked(state.CasevacDepartingUntilAt - now) > 0 ||
                 state.CasevacDepartureStartedAt != 0);
            fields["casevac_departure_elapsed_ms"] = state == null ||
                state.CasevacDepartureStartedAt == 0 ? 0 : unchecked(
                    now - state.CasevacDepartureStartedAt);
            fields["recon_control_relinquished"] = state != null &&
                state.ReconControlRelinquished;
            fields["has_mission_target"] = state != null &&
                state.HasMissionTarget;
            fields["mission_target_distance"] = state == null ||
                !state.HasMissionTarget || state.Helicopter == null ||
                !state.Helicopter.Exists() ? -1f :
                state.Helicopter.Position.DistanceTo(
                    state.LastMissionTarget);
            return fields;
        }

        private bool HasAerialRole(AerialSupportRole role)
        {
            foreach (AerialSupportState state in
                _aerialSupportStates.Values)
                if (state.Role == role) return true;
            return false;
        }

        private int CountAerialRole(AerialSupportRole role)
        {
            int count = 0;
            foreach (AerialSupportState state in
                _aerialSupportStates.Values)
                if (state.Role == role) count++;
            return count;
        }

        private void DiscoverCohesionResponses(
            Ped[] nearby, int budget, Ped player, int now)
        {
            if (_cohesionResponses.Count >= MaximumCohesionResponses) return;
            for (int i = 0; i < budget &&
                _cohesionResponses.Count < MaximumCohesionResponses; i++)
            {
                Ped casualty = nearby[i];
                if (casualty == null || !casualty.Exists() ||
                    !_states.TryGetValue(casualty.Handle,
                        out PedState state) ||
                    _cohesionResponses.ContainsKey(casualty.Handle))
                    continue;

                bool alive = !casualty.IsDead && casualty.Health > 0;
                bool inVehicle = casualty.IsInVehicle();
                bool openWorldLaw = IsOpenWorldLawCohesionPed(
                    casualty, player);
                bool safeAmbient = IsSafeAmbientCohesionPed(
                    casualty, player);
                bool physicallyDown = IsPedPhysicallyDown(casualty);
                bool activeReaction = HasActiveReaction(state, now) ||
                    openWorldLaw;
                int elapsed = unchecked(now - state.LastCohesionRequestAt);
                _cohesionCandidatesEvaluated++;
                if (!safeAmbient)
                    _cohesionRejectedEntityFlags++;
                else if (!physicallyDown)
                    _cohesionRejectedNotDown++;
                else if (!activeReaction)
                    _cohesionRejectedInactiveReaction++;
                else if (casualty.MaxHealth > 0 && casualty.Health >
                    Math.Max(1, (int)Math.Floor(casualty.MaxHealth *
                        NpcPhysicsExperimentPolicy.InjuredAidHealthRatio)))
                    _cohesionRejectedHealth++;
                if (openWorldLaw && (casualty.IsPersistent ||
                    Function.Call<bool>(Hash.IS_ENTITY_A_MISSION_ENTITY,
                        casualty.Handle)))
                    _cohesionLawFlagOverrides++;
                bool cohesionEnabled = _enabled ||
                    (_enhancedPoliceAi && openWorldLaw);
                if (!NpcPhysicsExperimentPolicy.ShouldRequestCohesionAid(
                        cohesionEnabled, safeAmbient, alive, inVehicle,
                        activeReaction, physicallyDown,
                        casualty.Health, casualty.MaxHealth, elapsed,
                        _cohesionResponses.Count,
                        MaximumCohesionResponses))
                    continue;

                if (TryStartCohesionResponse(casualty, player, now))
                {
                    state.LastCohesionRequestAt = now;
                    _cohesionRequests++;
                }
            }
        }

        private bool TryStartCohesionResponse(
            Ped casualty, Ped player, int now)
        {
            Ped[] local = World.GetNearbyPeds(
                casualty, CohesionResponseRadius);
            Array.Sort(local, (left, right) =>
            {
                if (left == null || !left.Exists()) return 1;
                if (right == null || !right.Exists()) return -1;
                return left.Position.DistanceTo(casualty.Position).CompareTo(
                    right.Position.DistanceTo(casualty.Position));
            });

            int casualtyGroup = Function.Call<int>(
                Hash.GET_PED_RELATIONSHIP_GROUP_HASH, casualty.Handle);
            Ped rescuer = null;
            Ped coverer = null;
            Ped tacticalFallbackRescuer = null;
            foreach (Ped candidate in local)
            {
                if (candidate == null || !candidate.Exists() ||
                    candidate.Handle == casualty.Handle ||
                    candidate.Handle == player.Handle)
                    continue;
                float distance = candidate.Position.DistanceTo(
                    casualty.Position);
                int candidateGroup = Function.Call<int>(
                    Hash.GET_PED_RELATIONSHIP_GROUP_HASH, candidate.Handle);
                int relationship = Function.Call<int>(
                    Hash.GET_RELATIONSHIP_BETWEEN_PEDS,
                    candidate.Handle, casualty.Handle);
                bool allied = NpcPhysicsExperimentPolicy.IsCohesionAlly(
                    casualtyGroup != 0 && candidateGroup == casualtyGroup,
                    relationship);
                bool available =
                    NpcPhysicsExperimentPolicy.CanProvideCohesionAid(
                        IsSafeAmbientCohesionPed(candidate, player),
                        !candidate.IsDead && candidate.Health > 0,
                        candidate.IsInVehicle(),
                        IsPedPhysicallyDown(candidate),
                        IsCohesionResponderAssigned(candidate.Handle), allied,
                        candidate.Health, candidate.MaxHealth, distance);
                if (!available) continue;
                bool assignedToTacticalLine =
                    PoliceTacticsCoordinator.IsPedAssignedForTactics(
                        candidate.Handle);
                if (assignedToTacticalLine)
                {
                    if (tacticalFallbackRescuer == null)
                        tacticalFallbackRescuer = candidate;
                    continue;
                }
                if (rescuer == null)
                {
                    rescuer = candidate;
                    continue;
                }
                if (Function.Call<bool>(Hash.IS_PED_ARMED,
                        candidate.Handle, 4))
                {
                    coverer = candidate;
                    break;
                }
            }
            if (rescuer == null)
                rescuer = tacticalFallbackRescuer;
            if (rescuer == null)
            {
                _cohesionRejectedNoResponder++;
                return false;
            }

            Ped threat = FindCohesionThreat(casualty, player);
            bool hasCollectionPoint =
                PoliceTacticsCoordinator.TryGetCasualtyCollectionPoint(
                    casualty.Position, out Vector3 collectionPoint,
                    out Vector3 landingPoint, out int collectionSquadId);
            var response = new CohesionResponse
            {
                Casualty = casualty,
                Rescuer = rescuer,
                Coverer = threat != null && threat.Exists() ? coverer : null,
                Threat = threat,
                Phase = CohesionPhase.Approach,
                StartedAt = now,
                PhaseStartedAt = now,
                LastApproachCommandAt = now,
                HasCollectionPoint = hasCollectionPoint,
                CollectionPoint = collectionPoint,
                CasevacLandingPoint = landingPoint,
                CollectionSquadId = collectionSquadId,
            };
            _cohesionResponses.Add(casualty.Handle, response);
            CommandCoverSupport(response);
            Ped smokeThrower = response.Coverer ??
                (response.HasCollectionPoint ? response.Rescuer : null);
            if (smokeThrower != null && response.Threat != null)
                response.SmokeDeployed =
                    PoliceTacticsCoordinator.TryDeployProtectiveSmoke(
                        smokeThrower, response.Casualty.Position,
                        response.Threat, "casualty_extraction", now);
            bool rescuerDeployingSmoke = response.SmokeDeployed &&
                smokeThrower != null &&
                smokeThrower.Handle == response.Rescuer.Handle;
            if (rescuerDeployingSmoke)
                response.ApproachDeferredUntilAt = unchecked(
                    now + CohesionSmokeCoverDelayMs);
            else
                CommandRescuerApproach(response);
            PhysicsExperimentLog.Info("cohesion_rescue_requested",
                CohesionFields(response, now,
                    new Dictionary<string, object>
                    {
                        { "casualty_health", casualty.Health },
                        { "casualty_max_health", casualty.MaxHealth },
                        { "collection_point_available",
                            hasCollectionPoint },
                        { "collection_squad", collectionSquadId },
                    }));
            return true;
        }

        private bool IsCohesionResponderAssigned(int handle)
        {
            foreach (CohesionResponse response in _cohesionResponses.Values)
                if ((response.Rescuer != null &&
                        response.Rescuer.Handle == handle) ||
                    (response.Coverer != null &&
                        response.Coverer.Handle == handle))
                    return true;
            return false;
        }

        private bool IsSafeAmbientCohesionPed(Ped ped, Ped player)
        {
            if (ped == null || !ped.Exists()) return false;
            bool missionEntity = Function.Call<bool>(
                Hash.IS_ENTITY_A_MISSION_ENTITY, ped.Handle);
            return NpcPhysicsExperimentPolicy.CanUseCohesionEntity(
                ped.IsHuman,
                player != null && player.Exists() &&
                    ped.Handle == player.Handle,
                ped.IsDead, ped.IsPersistent, missionEntity,
                IsOpenWorldLawCohesionPed(ped, player));
        }

        private bool IsOpenWorldLawCohesionPed(Ped ped, Ped player)
        {
            if (!_enhancedPoliceAi || Game.IsMissionActive ||
                Game.IsCutsceneActive || Game.Player.WantedLevel < 2 ||
                ped == null || !ped.Exists() || player == null ||
                !player.Exists()) return false;
            int group = Function.Call<int>(
                Hash.GET_PED_RELATIONSHIP_GROUP_HASH, ped.Handle);
            if (group != CopRelationshipGroupHash &&
                group != ArmyRelationshipGroupHash) return false;
            int relationship = Function.Call<int>(
                Hash.GET_RELATIONSHIP_BETWEEN_PEDS,
                ped.Handle, player.Handle);
            return relationship == 4 || relationship == 5 ||
                ped.IsInCombatAgainst(player);
        }

        private static bool IsPedPhysicallyDown(Ped ped)
        {
            if (ped == null || !ped.Exists()) return false;
            if (ped.IsRagdoll || Function.Call<bool>(
                    Hash.IS_PED_RUNNING_RAGDOLL_TASK, ped.Handle))
                return true;
            float height = Function.Call<float>(
                Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND, ped.Handle);
            float upright = Function.Call<float>(
                Hash.GET_ENTITY_UPRIGHT_VALUE, ped.Handle);
            return NpcPhysicsExperimentPolicy.IsPhysicallyGrounded(
                height, ped.Velocity.Z, upright);
        }

        private static Ped FindCohesionThreat(Ped casualty, Ped player)
        {
            if (IsCohesionThreat(casualty, player)) return player;
            Ped[] possible = World.GetNearbyPeds(
                casualty, CohesionThreatRadius);
            Ped best = null;
            float bestDistance = float.MaxValue;
            foreach (Ped candidate in possible)
            {
                if (!IsCohesionThreat(casualty, candidate)) continue;
                float distance = casualty.Position.DistanceTo(
                    candidate.Position);
                if (distance >= bestDistance) continue;
                best = candidate;
                bestDistance = distance;
            }
            return best;
        }

        private static bool IsCohesionThreat(Ped ally, Ped candidate)
        {
            if (ally == null || !ally.Exists() || candidate == null ||
                !candidate.Exists() || candidate.IsDead ||
                candidate.Handle == ally.Handle)
                return false;
            int relationship = Function.Call<int>(
                Hash.GET_RELATIONSHIP_BETWEEN_PEDS,
                ally.Handle, candidate.Handle);
            return relationship == 4 || relationship == 5 ||
                ally.IsInCombatAgainst(candidate) ||
                candidate.IsInCombatAgainst(ally);
        }

        private static void CommandRescuerApproach(
            CohesionResponse response)
        {
            if (response.Rescuer == null || !response.Rescuer.Exists() ||
                response.Casualty == null || !response.Casualty.Exists())
                return;
            Function.Call(Hash.TASK_GO_TO_ENTITY,
                response.Rescuer.Handle, response.Casualty.Handle,
                CohesionApproachTimeoutMs, 1.35f, 2.0f, 2.0f, 0);
        }

        private void CommandCoverSupport(CohesionResponse response)
        {
            Ped coverer = response.Coverer;
            Ped casualty = response.Casualty;
            Ped threat = response.Threat;
            if (coverer == null || !coverer.Exists() ||
                casualty == null || !casualty.Exists() ||
                threat == null || !threat.Exists())
                return;
            response.PreviousCoverMovement = Function.Call<int>(
                Hash.GET_PED_COMBAT_MOVEMENT, coverer.Handle);
            Vector3 center = casualty.Position;
            Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                coverer.Handle, center.X, center.Y, center.Z,
                6f, false, false);
            Function.Call(Hash.SET_PED_COMBAT_MOVEMENT,
                coverer.Handle, 1);
            Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                coverer.Handle, threat.Handle,
                CohesionCoverSeekDurationMs, false);
            _cohesionCoverAssignments++;
            PhysicsExperimentLog.Info("cohesion_cover_assigned",
                CohesionFields(response, Game.GameTime, null));
        }

        private void UpdateCohesionResponses(int now)
        {
            if (_cohesionResponses.Count == 0) return;
            var casualties = new List<int>(_cohesionResponses.Keys);
            foreach (int casualtyHandle in casualties)
            {
                if (!_cohesionResponses.TryGetValue(casualtyHandle,
                        out CohesionResponse response))
                    continue;
                if (!CohesionEntitiesRemainValid(
                        response, out string invalidReason))
                {
                    CancelCohesionResponse(
                        casualtyHandle, invalidReason);
                    continue;
                }
                if (response.Phase == CohesionPhase.AwaitCasevac ||
                    response.Phase == CohesionPhase.BoardingCasevac)
                    MaintainStabilizedCasualty(response, now);
                int responseTimeout = response.HasCollectionPoint
                    ? CollectionResponseTimeoutMs
                    : CohesionResponseTimeoutMs;
                if (unchecked(now - response.StartedAt) >= responseTimeout)
                {
                    CancelCohesionResponse(casualtyHandle, "timeout");
                    continue;
                }

                if (response.Coverer != null &&
                    (!response.Coverer.Exists() ||
                     response.Coverer.IsDead ||
                     !IsSafeAmbientCohesionPed(
                        response.Coverer, Game.Player.Character)))
                {
                    RestoreCohesionCoverer(response);
                    response.Coverer = null;
                }

                if (!response.CoverEngaged &&
                    unchecked(now - response.StartedAt) >=
                        (response.SmokeDeployed
                            ? CohesionSmokeCoverDelayMs
                            : CohesionCoverSeekDurationMs))
                {
                    response.CoverEngaged = true;
                    if (response.Coverer != null &&
                        response.Coverer.Exists() &&
                        response.Threat != null && response.Threat.Exists())
                    {
                        Function.Call(Hash.TASK_COMBAT_PED,
                            response.Coverer.Handle,
                            response.Threat.Handle, 0, 16);
                        PhysicsExperimentLog.Info(
                            "cohesion_cover_engaged",
                            CohesionFields(response, now, null));
                    }
                }

                float distance = response.Rescuer.Position.DistanceTo(
                    response.Casualty.Position);
                if (response.Phase == CohesionPhase.Approach)
                {
                    if (unchecked(response.ApproachDeferredUntilAt - now) > 0)
                        continue;
                    if (distance <= 1.8f)
                    {
                        response.Phase = CohesionPhase.Turn;
                        response.PhaseStartedAt = now;
                        response.Rescuer.Task.TurnTo(
                            response.Casualty, CohesionTurnDurationMs);
                    }
                    else if (unchecked(now -
                            response.LastApproachCommandAt) >= 1500)
                    {
                        CommandRescuerApproach(response);
                        response.LastApproachCommandAt = now;
                    }
                }
                else if (response.Phase == CohesionPhase.Turn &&
                    unchecked(now - response.PhaseStartedAt) >=
                        CohesionTurnDurationMs)
                {
                    response.Phase = CohesionPhase.Treat;
                    response.PhaseStartedAt = now;
                    Function.Call(Hash.TASK_START_SCENARIO_IN_PLACE,
                        response.Rescuer.Handle,
                        "CODE_HUMAN_MEDIC_KNEEL", -1, true);
                    PhysicsExperimentLog.Info("cohesion_treatment_started",
                        CohesionFields(response, now, null));
                }
                else if (response.Phase == CohesionPhase.Treat)
                {
                    if (distance > 2.65f ||
                        response.Rescuer.IsRagdoll ||
                        response.Rescuer.IsFalling ||
                        Function.Call<bool>(Hash.IS_PED_RUNNING_RAGDOLL_TASK,
                            response.Rescuer.Handle))
                    {
                        CancelCohesionResponse(
                            casualtyHandle, "treatment_interrupted");
                        continue;
                    }
                    if (unchecked(now - response.PhaseStartedAt) >=
                        CohesionTreatmentDurationMs)
                        CompleteCohesionResponse(casualtyHandle, now);
                }
                else if (response.Phase ==
                    CohesionPhase.EvacuateToCollection)
                {
                    float collectionDistance = response.Casualty.Position
                        .DistanceTo(response.CollectionPoint);
                    if (collectionDistance <= 3.25f)
                    {
                        response.Phase = CohesionPhase.AwaitCasevac;
                        response.PhaseStartedAt = now;
                        response.StabilizedHoldingHealth =
                            response.Casualty.Health;
                        response.StabilizationDirectDamageAt = 0;
                        Function.Call(Hash.CLEAR_ENTITY_LAST_DAMAGE_ENTITY,
                            response.Casualty.Handle);
                        Function.Call(Hash.CLEAR_ENTITY_LAST_WEAPON_DAMAGE,
                            response.Casualty.Handle);
                        response.Casualty.Task.StandStill(30000);
                        response.Rescuer.Task.StandStill(30000);
                        _collectionArrivals++;
                        PhysicsExperimentLog.Info(
                            "casualty_arrived_at_collection_point",
                            CohesionFields(response, now,
                                new Dictionary<string, object>
                                {
                                    { "collection_distance",
                                        collectionDistance },
                                    { "stabilized_holding_health",
                                        response.StabilizedHoldingHealth },
                                }));
                    }
                    else if (unchecked(now - response.PhaseStartedAt) >=
                        CollectionRouteTimeoutMs)
                    {
                        FinishStabilizedCohesionResponse(
                            casualtyHandle, now,
                            "collection_route_timeout");
                    }
                    else if (unchecked(now -
                            response.LastCollectionCommandAt) >=
                        CollectionRouteRefreshMs)
                    {
                        CommandCollectionRoute(response, now);
                    }
                }
                else if (response.Phase == CohesionPhase.BoardingCasevac &&
                    unchecked(now - response.CasevacBoardingStartedAt) >=
                        CasevacBoardingTimeoutMs)
                {
                    AbortCasevac(response, now, "boarding_timeout");
                }
            }
        }

        private void RecordStabilizationDamageEvidence(
            Ped casualty, bool weaponDamage, bool onFire,
            bool nearExplosion, int now)
        {
            if (casualty == null || !casualty.Exists() ||
                !_cohesionResponses.TryGetValue(casualty.Handle,
                    out CohesionResponse response) ||
                (response.Phase != CohesionPhase.AwaitCasevac &&
                 response.Phase != CohesionPhase.BoardingCasevac))
                return;
            if (weaponDamage || onFire || nearExplosion ||
                HasDirectStabilizationDamageEvidence(casualty))
                response.StabilizationDirectDamageAt = now;
        }

        private void MaintainStabilizedCasualty(
            CohesionResponse response, int now)
        {
            Ped casualty = response?.Casualty;
            if (casualty == null || !casualty.Exists() ||
                casualty.IsDead || casualty.Health <= 0) return;
            int observedHealth = casualty.Health;
            if (response.StabilizedHoldingHealth <= 0)
                response.StabilizedHoldingHealth = observedHealth;
            int previousHoldingHealth =
                response.StabilizedHoldingHealth;
            bool healthDropped = observedHealth < previousHoldingHealth;
            bool directDamage = healthDropped &&
                (response.StabilizationDirectDamageAt == now ||
                 HasDirectStabilizationDamageEvidence(casualty));
            int resolvedHealth = NpcPhysicsExperimentPolicy.
                ResolveStabilizedHoldingHealth(
                    previousHoldingHealth, observedHealth,
                    directDamage);
            string result = null;
            if (directDamage && observedHealth < previousHoldingHealth)
            {
                response.StabilizedHoldingHealth = observedHealth;
                _stabilizedDamageAccepted++;
                result = "direct_damage_accepted";
                Function.Call(Hash.CLEAR_ENTITY_LAST_DAMAGE_ENTITY,
                    casualty.Handle);
                Function.Call(Hash.CLEAR_ENTITY_LAST_WEAPON_DAMAGE,
                    casualty.Handle);
            }
            else if (observedHealth < previousHoldingHealth)
            {
                casualty.Health = resolvedHealth;
                _stabilizedPassiveLossPrevented++;
                result = "passive_loss_prevented";
            }
            else if (observedHealth > previousHoldingHealth)
            {
                casualty.Health = resolvedHealth;
                _stabilizedHealingPrevented++;
                result = "healing_prevented";
            }
            if (result == null) return;
            bool logDue = response.LastStabilizationCorrectionLogAt == 0 ||
                unchecked(now - response.LastStabilizationCorrectionLogAt) >=
                    StabilizationCorrectionLogIntervalMs;
            if (!logDue) return;
            response.LastStabilizationCorrectionLogAt = now;
            PhysicsExperimentLog.Info(
                "casualty_stabilized_health_held",
                CohesionFields(response, now,
                    new Dictionary<string, object>
                    {
                        { "result", result },
                        { "observed_health", observedHealth },
                        { "previous_holding_health",
                            previousHoldingHealth },
                        { "resolved_health", resolvedHealth },
                        { "direct_damage", directDamage },
                    }));
        }

        private static bool HasDirectStabilizationDamageEvidence(
            Ped casualty)
        {
            return casualty.HasBeenDamagedByAnyWeapon() ||
                casualty.HasBeenDamagedByAnyMeleeWeapon() ||
                Function.Call<bool>(
                    Hash.HAS_ENTITY_BEEN_DAMAGED_BY_ANY_PED,
                    casualty.Handle) ||
                Function.Call<bool>(
                    Hash.HAS_ENTITY_BEEN_DAMAGED_BY_ANY_VEHICLE,
                    casualty.Handle) ||
                Function.Call<bool>(
                    Hash.HAS_ENTITY_BEEN_DAMAGED_BY_ANY_OBJECT,
                    casualty.Handle) ||
                Function.Call<bool>(Hash.IS_ENTITY_ON_FIRE,
                    casualty.Handle);
        }

        private bool CohesionEntitiesRemainValid(
            CohesionResponse response, out string reason)
        {
            reason = "entity_unavailable";
            if (response == null) return false;
            if (response.Casualty == null ||
                !response.Casualty.Exists())
            {
                reason = "casualty_missing";
                return false;
            }
            if (response.Casualty.IsDead || response.Casualty.Health <= 0)
            {
                reason = "casualty_died";
                return false;
            }
            if (!IsSafeAmbientCohesionPed(
                    response.Casualty, Game.Player.Character))
            {
                reason = "casualty_no_longer_eligible";
                return false;
            }
            if (response.Rescuer == null || !response.Rescuer.Exists())
            {
                reason = "rescuer_missing";
                return false;
            }
            if (response.Rescuer.IsDead || response.Rescuer.Health <= 0)
            {
                reason = "rescuer_died";
                return false;
            }
            if (response.Rescuer.IsInVehicle())
            {
                reason = "rescuer_entered_vehicle";
                return false;
            }
            if (!IsSafeAmbientCohesionPed(
                    response.Rescuer, Game.Player.Character))
            {
                reason = "rescuer_no_longer_eligible";
                return false;
            }
            return true;
        }

        private void CompleteCohesionResponse(
            int casualtyHandle, int now)
        {
            if (!_cohesionResponses.TryGetValue(casualtyHandle,
                    out CohesionResponse response))
                return;
            Ped casualty = response.Casualty;
            int previousHealth = casualty.Health;
            int stabilizedHealth =
                NpcPhysicsExperimentPolicy.StabilizedHealth(
                    previousHealth, casualty.MaxHealth);
            casualty.Health = stabilizedHealth;
            if (response.HasCollectionPoint)
            {
                response.Phase = CohesionPhase.EvacuateToCollection;
                response.PhaseStartedAt = now;
                response.LastCollectionCommandAt = int.MinValue / 2;
                CommandCollectionRoute(response, now);
                _collectionRoutesStarted++;
                PhysicsExperimentLog.Info(
                    "casualty_collection_route_started",
                    CohesionFields(response, now,
                        new Dictionary<string, object>
                        {
                            { "previous_health", previousHealth },
                            { "stabilized_health", stabilizedHealth },
                            { "collection_x", response.CollectionPoint.X },
                            { "collection_y", response.CollectionPoint.Y },
                            { "collection_z", response.CollectionPoint.Z },
                        }));
                return;
            }
            FinishStabilizedCohesionResponse(casualtyHandle, now,
                "treated_in_place", previousHealth, stabilizedHealth);
        }

        private static void CommandCollectionRoute(
            CohesionResponse response, int now)
        {
            Vector3 point = response.CollectionPoint;
            Function.Call(Hash.TASK_FOLLOW_NAV_MESH_TO_COORD,
                response.Casualty.Handle,
                point.X, point.Y, point.Z,
                1.35f, CollectionRouteTimeoutMs, 1.5f, true, 0f);
            Vector3 rescuerPoint = point + new Vector3(1.25f, 0f, 0f);
            Function.Call(Hash.TASK_FOLLOW_NAV_MESH_TO_COORD,
                response.Rescuer.Handle,
                rescuerPoint.X, rescuerPoint.Y, rescuerPoint.Z,
                1.5f, CollectionRouteTimeoutMs, 1.5f, true, 0f);
            response.LastCollectionCommandAt = now;
        }

        private void FinishStabilizedCohesionResponse(
            int casualtyHandle, int now, string reason,
            int previousHealth = -1, int stabilizedHealth = -1)
        {
            if (!_cohesionResponses.TryGetValue(casualtyHandle,
                    out CohesionResponse response)) return;
            Ped casualty = response.Casualty;
            if (previousHealth < 0) previousHealth = casualty.Health;
            if (stabilizedHealth < 0) stabilizedHealth = casualty.Health;
            response.Rescuer.Task.ClearAll();
            if (response.Threat != null && response.Threat.Exists() &&
                !response.Threat.IsDead)
            {
                Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                    casualty.Handle, response.Threat.Handle, 5000, false);
                Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                    response.Rescuer.Handle, response.Threat.Handle,
                    7000, false);
                if (response.Coverer != null && response.Coverer.Exists())
                    Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                        response.Coverer.Handle, response.Threat.Handle,
                        7000, false);
            }
            else
            {
                response.Rescuer.Task.WanderAround();
            }
            RestoreCohesionCoverer(response);
            _cohesionResponses.Remove(casualtyHandle);
            _cohesionRescuesCompleted++;
            PhysicsExperimentLog.Info("cohesion_rescue_completed",
                CohesionFields(response, now,
                    new Dictionary<string, object>
                    {
                        { "previous_health", previousHealth },
                        { "stabilized_health", stabilizedHealth },
                        { "completion_reason", reason },
                    }));
        }

        private void CancelCohesionResponse(
            int casualtyHandle, string reason)
        {
            if (!_cohesionResponses.TryGetValue(casualtyHandle,
                    out CohesionResponse response))
                return;
            if (response.Rescuer != null && response.Rescuer.Exists())
            {
                response.Rescuer.Task.ClearAll();
                if (response.Threat != null && response.Threat.Exists() &&
                    !response.Threat.IsDead)
                    Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                        response.Rescuer.Handle, response.Threat.Handle,
                        6000, false);
            }
            if (response.CasevacHelicopterHandle != 0 &&
                _aerialSupportStates.TryGetValue(
                    response.CasevacHelicopterHandle,
                    out AerialSupportState casevacState))
            {
                casevacState.CasevacCasualtyHandle = 0;
                casevacState.LastMissionCommandAt = int.MinValue / 2;
                if (casevacState.DedicatedCasevac &&
                    casevacState.Helicopter != null &&
                    casevacState.Helicopter.Exists())
                    BeginCasevacDeparture(casevacState,
                        response.CasevacLandingPoint,
                        Game.Player.Character, Game.GameTime,
                        "casualty_unavailable_" + reason);
            }
            RestoreCohesionCoverer(response);
            _cohesionResponses.Remove(casualtyHandle);
            _cohesionRescuesCancelled++;
            PhysicsExperimentLog.Info("cohesion_rescue_cancelled",
                CohesionFields(response, Game.GameTime,
                    new Dictionary<string, object> { { "reason", reason } }));
        }

        private static void RestoreCohesionCoverer(
            CohesionResponse response)
        {
            if (response.Coverer == null || !response.Coverer.Exists()) return;
            Function.Call(Hash.REMOVE_PED_DEFENSIVE_AREA,
                response.Coverer.Handle, false);
            Function.Call(Hash.SET_PED_COMBAT_MOVEMENT,
                response.Coverer.Handle, response.PreviousCoverMovement);
        }

        private static Dictionary<string, object> CohesionFields(
            CohesionResponse response, int now,
            Dictionary<string, object> fields)
        {
            fields = fields ?? new Dictionary<string, object>();
            fields["casualty"] = response?.Casualty?.Handle ?? 0;
            fields["rescuer"] = response?.Rescuer?.Handle ?? 0;
            fields["coverer"] = response?.Coverer?.Handle ?? 0;
            fields["threat"] = response?.Threat?.Handle ?? 0;
            fields["phase"] = response?.Phase.ToString() ?? "None";
            fields["collection_point"] =
                response != null && response.HasCollectionPoint;
            fields["collection_squad"] =
                response?.CollectionSquadId ?? 0;
            fields["casevac_helicopter"] =
                response?.CasevacHelicopterHandle ?? 0;
            fields["smoke_deployed"] =
                response != null && response.SmokeDeployed;
            fields["stabilized_holding_health"] =
                response?.StabilizedHoldingHealth ?? 0;
            fields["stabilization_direct_damage_at"] =
                response?.StabilizationDirectDamageAt ?? 0;
            fields["approach_deferred_remaining_ms"] = response == null
                ? 0 : Math.Max(0, unchecked(
                    response.ApproachDeferredUntilAt - now));
            fields["elapsed_ms"] = response == null
                ? 0 : unchecked(now - response.StartedAt);
            return fields;
        }

        private static bool WasDamagedBy(Ped ped, int weaponHash)
        {
            return Function.Call<bool>(Hash.HAS_ENTITY_BEEN_DAMAGED_BY_WEAPON,
                ped.Handle, weaponHash, 0);
        }

        private static int GetLastDamageBone(Ped ped)
        {
            var bone = new OutputArgument();
            return Function.Call<bool>(Hash.GET_PED_LAST_DAMAGE_BONE,
                ped.Handle, bone) ? bone.GetResult<int>() : 0;
        }

        private void ScheduleWeaponRecovery(Ped ped, PedState state,
            int weaponHash, int damageBone, int now)
        {
            state.DroppedWeaponHash = weaponHash;
            state.WeaponRecoveryEligibleAt = unchecked(now +
                NpcPhysicsExperimentPolicy.WeaponRecoveryDelayMs);
            state.WeaponRecoveryExpiresAt = unchecked(now +
                NpcPhysicsExperimentPolicy.WeaponRecoveryTimeoutMs);
            state.NextWeaponRecoveryScanAt =
                state.WeaponRecoveryEligibleAt;
            state.WeaponRecoveryCommandedAt = 0;
            state.WeaponRecoveryPickup = null;
            state.WeaponRecoveryPickupHash = 0;
            _handDisarms++;
            PhysicsExperimentLog.Info("weapon_dropped_from_hand",
                new Dictionary<string, object>
                {
                    { "ped", ped.Handle },
                    { "weapon", weaponHash },
                    { "damage_bone", damageBone },
                    { "recovery_eligible_in_ms",
                        NpcPhysicsExperimentPolicy.WeaponRecoveryDelayMs },
                });
        }

        private void UpdateWeaponRecovery(Ped ped, PedState state,
            Ped player, int now, bool safeAmbient, bool alive,
            bool inVehicle)
        {
            if (!_enhancedPoliceAi || !safeAmbient || player == null ||
                !player.Exists() || !IsLawWeaponRecoveryCandidate(ped, player))
                return;

            bool armed = Function.Call<bool>(Hash.IS_PED_ARMED,
                ped.Handle, 4);
            if (state.WeaponRecoveryExpiresAt == 0 || unchecked(
                    now - state.WeaponRecoveryExpiresAt) >= 0)
            {
                state.WeaponRecoveryEligibleAt = now;
                state.WeaponRecoveryExpiresAt = unchecked(now +
                    NpcPhysicsExperimentPolicy.WeaponRecoveryTimeoutMs);
                state.NextWeaponRecoveryScanAt = now;
            }

            bool inCover = Function.Call<bool>(Hash.IS_PED_IN_COVER,
                ped.Handle, false);
            bool lineOfSight = Function.Call<bool>(
                Hash.HAS_ENTITY_CLEAR_LOS_TO_ENTITY,
                player.Handle, ped.Handle, 17);
            float threatDistance = ped.Position.DistanceTo(player.Position);
            bool exposed = !inCover && lineOfSight && threatDistance < 45f;
            bool assigned = PoliceTacticsCoordinator.IsPedAssignedForTactics(
                ped.Handle);
            bool physicallyDown = IsPedPhysicallyDown(ped);
            if (!NpcPhysicsExperimentPolicy.ShouldAttemptWeaponRecovery(
                    _enhancedPoliceAi, safeAmbient, alive, inVehicle,
                    physicallyDown, assigned, exposed, now,
                    state.WeaponRecoveryEligibleAt,
                    state.WeaponRecoveryExpiresAt))
            {
                if (state.WeaponRecoveryPickup != null &&
                    (exposed || assigned || physicallyDown || inVehicle))
                {
                    state.WeaponRecoveryPickup = null;
                    state.WeaponRecoveryPickupHash = 0;
                    state.WeaponRecoveryCommandedAt = 0;
                    state.NextWeaponRecoveryScanAt = unchecked(now +
                        WeaponRecoveryScanIntervalMs);
                    _weaponRecoveryFailures++;
                    PhysicsExperimentLog.Info(
                        "weapon_recovery_aborted_for_safety",
                        new Dictionary<string, object>
                        {
                            { "ped", ped.Handle }, { "exposed", exposed },
                            { "assigned_to_tactics", assigned },
                            { "physically_down", physicallyDown },
                        });
                }
                return;
            }

            int bestWeapon = Function.Call<int>(
                Hash.GET_BEST_PED_WEAPON, ped.Handle, false);
            int currentPriority = GetSafeWeaponPriority(bestWeapon);
            // Never replace a deliberately equipped heavy/special weapon.  The
            // scavenger only handles disarmed peds or upgrades within its
            // explicitly non-explosive firearm allowlist.
            if (armed && currentPriority == 0) return;

            Prop target = state.WeaponRecoveryPickup;
            if (target != null)
            {
                bool targetValid = target.Exists() && Function.Call<bool>(
                    Hash.IS_PICKUP_WEAPON_OBJECT_VALID, target.Handle);
                float distance = targetValid
                    ? target.Position.DistanceTo(ped.Position)
                    : float.MaxValue;
                int candidatePriority = GetSafeWeaponPriority(
                    state.WeaponRecoveryPickupHash);
                if (!NpcPhysicsExperimentPolicy.ShouldTakeSafeWeapon(
                        currentPriority, candidatePriority,
                        targetValid, distance))
                {
                    state.WeaponRecoveryPickup = null;
                    state.WeaponRecoveryPickupHash = 0;
                    state.WeaponRecoveryCommandedAt = 0;
                    state.NextWeaponRecoveryScanAt = unchecked(now +
                        WeaponRecoveryScanIntervalMs);
                    _weaponRecoveryFailures++;
                    return;
                }

                if (distance <= 1.55f)
                {
                    int pickupHandle = target.Handle;
                    int weaponHash = state.WeaponRecoveryPickupHash;
                    Function.Call(Hash.GIVE_WEAPON_OBJECT_TO_PED,
                        pickupHandle, ped.Handle);
                    Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                        ped.Handle, weaponHash, true);
                    state.WeaponRecoveryPickup = null;
                    state.WeaponRecoveryPickupHash = 0;
                    state.WeaponRecoveryCommandedAt = 0;
                    state.DroppedWeaponHash = 0;
                    state.NextWeaponRecoveryScanAt = unchecked(now + 5000);
                    _weaponRecoveries++;
                    PhysicsExperimentLog.Info("weapon_recovery_completed",
                        new Dictionary<string, object>
                        {
                            { "ped", ped.Handle },
                            { "weapon", weaponHash },
                            { "pickup", pickupHandle },
                            { "upgraded", currentPriority > 0 },
                        });
                    return;
                }

                if (unchecked(now - state.WeaponRecoveryCommandedAt) >=
                    WeaponRecoveryApproachTimeoutMs)
                {
                    state.WeaponRecoveryPickup = null;
                    state.WeaponRecoveryPickupHash = 0;
                    state.WeaponRecoveryCommandedAt = 0;
                    state.NextWeaponRecoveryScanAt = unchecked(now +
                        WeaponRecoveryScanIntervalMs);
                    _weaponRecoveryFailures++;
                }
                return;
            }

            if (unchecked(now - state.NextWeaponRecoveryScanAt) < 0) return;
            state.NextWeaponRecoveryScanAt = unchecked(now +
                WeaponRecoveryScanIntervalMs);
            _weaponRecoverySearches++;
            Prop bestPickup = null;
            int bestPickupWeapon = 0;
            float bestScore = float.MinValue;
            foreach (Prop pickup in World.GetNearbyPickupObjects(
                ped.Position, WeaponRecoveryRadius))
            {
                if (pickup == null || !pickup.Exists() ||
                    !Function.Call<bool>(Hash.IS_PICKUP_WEAPON_OBJECT_VALID,
                        pickup.Handle)) continue;
                int candidateWeapon = GetSafeWeaponForModel(
                    pickup.Model.Hash);
                int candidatePriority = GetSafeWeaponPriority(
                    candidateWeapon);
                float distance = pickup.Position.DistanceTo(ped.Position);
                if (!NpcPhysicsExperimentPolicy.ShouldTakeSafeWeapon(
                        currentPriority, candidatePriority, true, distance))
                    continue;
                float score = candidatePriority * 100f - distance * 5f;
                if (candidateWeapon == state.DroppedWeaponHash)
                    score += 35f;
                if (score <= bestScore) continue;
                bestScore = score;
                bestPickup = pickup;
                bestPickupWeapon = candidateWeapon;
            }
            if (bestPickup == null) return;

            state.WeaponRecoveryPickup = bestPickup;
            state.WeaponRecoveryPickupHash = bestPickupWeapon;
            state.WeaponRecoveryCommandedAt = now;
            Function.Call(Hash.TASK_GO_TO_ENTITY,
                ped.Handle, bestPickup.Handle,
                WeaponRecoveryApproachTimeoutMs, 1.25f, 2.0f, 2.0f, 0);
            _weaponRecoveryCommands++;
            PhysicsExperimentLog.Info("weapon_recovery_commanded",
                new Dictionary<string, object>
                {
                    { "ped", ped.Handle },
                    { "weapon", bestPickupWeapon },
                    { "pickup", bestPickup.Handle },
                    { "distance",
                        bestPickup.Position.DistanceTo(ped.Position) },
                    { "current_priority", currentPriority },
                    { "candidate_priority",
                        GetSafeWeaponPriority(bestPickupWeapon) },
                });
        }

        private static bool IsLawWeaponRecoveryCandidate(Ped ped, Ped player)
        {
            if (ped == null || !ped.Exists() || player == null ||
                !player.Exists()) return false;
            int group = Function.Call<int>(
                Hash.GET_PED_RELATIONSHIP_GROUP_HASH, ped.Handle);
            if (group != CopRelationshipGroupHash &&
                group != ArmyRelationshipGroupHash) return false;
            int relationship = Function.Call<int>(
                Hash.GET_RELATIONSHIP_BETWEEN_PEDS,
                ped.Handle, player.Handle);
            return relationship == 4 || relationship == 5 ||
                ped.IsInCombatAgainst(player);
        }

        private static int GetSafeWeaponForModel(int modelHash)
        {
            if (modelHash == 0) return 0;
            foreach (WeaponRecoveryOption option in SafeRecoveryWeapons)
                if (option.ModelHash == modelHash)
                    return option.WeaponHash;
            return 0;
        }

        private static int GetSafeWeaponPriority(int weaponHash)
        {
            if (weaponHash == 0) return 0;
            foreach (WeaponRecoveryOption option in SafeRecoveryWeapons)
                if (option.WeaponHash == weaponHash)
                    return option.Priority;
            return 0;
        }

        private static bool WasNearExplosion(Vector3 position)
        {
            // Called only after an unexplained fresh health loss, so the native
            // query cost is paid on an exceptional path rather than each scan.
            foreach (ExplosionType explosionType in
                Enum.GetValues(typeof(ExplosionType)))
            {
                int type = (int)explosionType;
                if (type < 0) continue;
                if (Function.Call<bool>(Hash.IS_EXPLOSION_IN_SPHERE, type,
                        position.X, position.Y, position.Z, 6f))
                    return true;
            }
            return false;
        }

        private bool TryApplyVehicleBump(
            Ped ped, PedState state, int now)
        {
            bool collided = Function.Call<bool>(
                Hash.HAS_ENTITY_COLLIDED_WITH_ANYTHING, ped.Handle);
            if (!collided) return false;
            Vehicle vehicle = World.GetClosestVehicle(ped.Position, 3.25f);
            bool exists = vehicle != null && vehicle.Exists();
            bool touching = exists && Function.Call<bool>(
                Hash.IS_ENTITY_TOUCHING_ENTITY, ped.Handle, vehicle.Handle);
            float speed = exists ? vehicle.Speed : 0f;
            float distance = exists
                ? vehicle.Position.DistanceTo(ped.Position) : float.MaxValue;
            int elapsed = unchecked(now - state.LastVehicleBumpAt);
            bool shouldReact = NpcPhysicsExperimentPolicy.ShouldReactToVehicleBump(
                true, true, true, false, collided && touching, exists,
                speed, distance, elapsed);
            if (!shouldReact) return false;
            PhysicsExperimentLog.Info("vehicle_collision_accepted",
                new Dictionary<string, object>
                {
                    { "ped", ped.Handle }, { "vehicle", vehicle.Handle },
                    { "touching", touching },
                    { "speed", speed }, { "distance", distance },
                    { "cooldown_elapsed_ms", elapsed },
                });
            _vehicleReactions++;
            state.ReactionSequence++;
            ReactionSnapshot baseline = CaptureReactionSnapshot(ped);
            bool naturalMotionDispatched = ApplyVehicleBumpReaction(
                ped, vehicle, speed, state.ReactionSequence);
            Dictionary<string, object> outcome = BuildOutcomeFields(
                ped, ped.Handle, state.ReactionSequence);
            outcome["natural_motion_dispatched"] = naturalMotionDispatched;
            PhysicsExperimentLog.Info(naturalMotionDispatched
                    ? "vehicle_reaction_dispatched"
                    : "vehicle_native_reaction_observed",
                outcome);
            state.LastVehicleBumpAt = now;
            ScheduleReactionObservation(state, now, "vehicle",
                VehicleBumpDurationMs, baseline);
            return true;
        }

        private bool TryApplyPedPush(
            Ped ped, PedState state, int now, Ped player)
        {
            if (player == null || !player.Exists()) return false;
            bool collided = Function.Call<bool>(
                Hash.HAS_ENTITY_COLLIDED_WITH_ANYTHING, ped.Handle);
            if (!collided) return false;
            bool touching = Function.Call<bool>(Hash.IS_ENTITY_TOUCHING_ENTITY,
                ped.Handle, player.Handle);
            float distance = player.Position.DistanceTo(ped.Position);
            float speed = player.Velocity.Length();
            int elapsed = unchecked(now - state.LastPedPushAt);
            if (!NpcPhysicsExperimentPolicy.ShouldReactToPedPush(
                    true, true, true, false, collided && touching, speed,
                    distance, elapsed)) return false;

            _pedPushReactions++;
            state.ReactionSequence++;
            int handle = ped.Handle;
            ReactionSnapshot baseline = CaptureReactionSnapshot(ped);
            PhysicsExperimentLog.Info("ped_push_accepted",
                new Dictionary<string, object>
                {
                    { "ped", handle }, { "player_speed", speed },
                    { "touching", touching },
                    { "distance", distance },
                    { "cooldown_elapsed_ms", elapsed },
                });
            EnsureScriptControlRagdoll(ped, "ped_push",
                state.ReactionSequence, PedPushDurationMs,
                "push_script_control_ragdoll");
            SendNaturalMotionStage(ped, "ped_push", state.ReactionSequence,
                "push_low_stiffness", () =>
                ApplyLowStiffnessAndFriction(ped, PedPushDurationMs, 1.08f));
            SendNaturalMotionStage(ped, "ped_push", state.ReactionSequence,
                "push_balance", () =>
                ConfigureLongBalance(ped, PedPushDurationMs));
            state.LastPedPushAt = now;
            ScheduleReactionObservation(state, now, "ped_push",
                PedPushDurationMs, baseline);
            return true;
        }

        private static void ApplyDamageReaction(
            Ped ped, NpcPhysicsBodyRegion region, bool melee, bool taser,
            bool onFire, bool grounded, bool lethal, bool armed, int sequence,
            bool blast, string reactionKind, bool handHit)
        {
            int handle = ped.Handle;
            EnsureScriptControlRagdoll(ped, reactionKind, sequence,
                ReactionDurationMs, "script_control_ragdoll");
            SendNaturalMotionStage(ped, reactionKind, sequence,
                "low_stiffness_friction", () =>
                ApplyLowStiffnessAndFriction(ped, ReactionDurationMs, 1.12f,
                    lethal ? LethalBodyRelaxation : LiveBodyRelaxation,
                    lethal ? 3f : 8f));
            SendNaturalMotionStage(ped, reactionKind, sequence,
                "long_balance", () =>
                ConfigureLongBalance(ped, ReactionDurationMs));
            SendNaturalMotionStage(ped, reactionKind, sequence,
                "wound_reach", () =>
                ConfigureWoundReach(ped, melee, armed, sequence, handHit));
            SendNaturalMotionStage(ped, reactionKind, sequence,
                "body_region_" + region, () =>
                ConfigureBodyRegion(ped, region, lethal, armed, sequence,
                    handHit));
            if (blast) SendNaturalMotionStage(ped, reactionKind, sequence,
                "blast_protection", () => ApplyBlastProtection(ped));
            if (taser) SendNaturalMotionStage(ped, reactionKind, sequence,
                "electrocution", () => ApplyElectrocution(ped));
            if (onFire) SendNaturalMotionStage(ped, reactionKind, sequence,
                "fire_balance", () => ApplyFireBalance(ped));
            if (grounded) SendNaturalMotionStage(ped, reactionKind, sequence,
                "ground_injury", () => ApplyGroundInjury(ped, region, sequence));
            if (lethal && NpcPhysicsExperimentPolicy.DeterministicChance(
                    ped.Handle, sequence, 34))
                SendNaturalMotionStage(ped, reactionKind, sequence,
                    "knee_drop", () => ApplyKneeDrop(ped));
        }

        private static void ApplyLowStiffnessAndFriction(
            Ped ped, int duration, float friction,
            float relaxation = LiveBodyRelaxation,
            float bodyStiffness = 8f)
        {
            SetStiffnessHelper stiffness = ped.Euphoria.SetStiffness;
            stiffness.BodyStiffness = bodyStiffness;
            stiffness.Damping = 0.68f;
            stiffness.Start(duration);
            BodyRelaxHelper relax = ped.Euphoria.BodyRelax;
            relax.Relaxation = relaxation;
            relax.Damping = 0.65f;
            relax.HoldPose = false;
            relax.Start(duration);
            SetFrictionScaleHelper scale = ped.Euphoria.SetFrictionScale;
            scale.Scale = friction;
            scale.GlobalMin = 0f;
            scale.GlobalMax = 999999f;
            scale.Start(duration);
        }

        private static void ConfigureLongBalance(Ped ped, int duration)
        {
            ConfigureBalanceHelper balance = ped.Euphoria.ConfigureBalance;
            balance.LegStiffness = 12f;
            balance.LeftLegSwingDamping = 1.12f;
            balance.RightLegSwingDamping = 1.12f;
            balance.BalanceAbortThreshold = 0.94f;
            balance.GiveUpHeight = 0.12f;
            balance.PredictionTime = 0.3f;
            balance.MaxSteps = 32;
            balance.MaxBalanceTime = 6.2f;
            balance.ExtraSteps = 8;
            balance.ExtraTime = 2.0f;
            balance.FootFriction = 1.18f;
            balance.FootFrictionStagger = 1.02f;
            balance.GiveUpHeightEnd = 0.28f;
            balance.BalanceAbortThresholdEnd = 0.78f;
            balance.GiveUpRampDuration = 3.6f;
            balance.Start();
            BodyBalanceHelper body = ped.Euphoria.BodyBalance;
            body.ArmStiffness = 8f;
            body.SpineStiffness = 8f;
            body.ArmDamping = 0.78f;
            body.SpineDamping = 0.78f;
            body.UseHeadLook = true;
            body.ArmsOutOnPush = true;
            body.ArmsOutOnPushMultiplier = 0.65f;
            body.ArmsOutOnPushTimeout = 0.7f;
            body.ReturningToBalanceArmsOut = 0.65f;
            body.UseBodyTurn = true;
            body.Start(duration);
            CatchFallHelper catchFall = ped.Euphoria.CatchFall;
            catchFall.TorsoStiffness = 8f;
            catchFall.LegsStiffness = 10f;
            catchFall.ArmsStiffness = 8f;
            catchFall.UseHeadLook = true;
            catchFall.Start(duration);
        }

        private static void ConfigureWoundReach(
            Ped ped, bool melee, bool armed, int sequence, bool handHit)
        {
            ShotHelper shot = ped.Euphoria.Shot;
            shot.BodyStiffness = 6f;
            shot.ArmStiffness = handHit ? 3.5f : 6f;
            shot.ReachForWound = true;
            shot.GrabHoldTime = handHit ? 4.2f : 3.2f;
            shot.TimeBeforeReachForWound = 0.08f;
            shot.AllowInjuredArm = true;
            shot.AllowInjuredLeg = true;
            shot.AllowInjuredLowerLegReach = true;
            shot.AllowInjuredThighReach = true;
            shot.UseExtendedCatchFall = true;
            shot.Melee = melee;
            shot.ExagDuration = 0.15f;
            shot.ExagMag = 0.2f;
            shot.ExagTwistMag = 0.15f;
            shot.Start(ReactionDurationMs);
            ShotConfigureArmsHelper arms = ped.Euphoria.ShotConfigureArms;
            arms.Brace = !handHit;
            arms.ReachFalling = 2;
            arms.ReachFallingWithOneHand = 3;
            arms.ReachOnFloor = 2;
            arms.AlwaysReachTime = 2.6f;
            arms.ReachWithOneHand = handHit ? 1 : 0;
            arms.ReleaseWound = 0;
            arms.AllowLeftPistolRFW = true;
            arms.AllowRightPistolRFW = true;
            arms.RfwWithPistol = !handHit;
            arms.PointGun = !handHit && armed &&
                NpcPhysicsExperimentPolicy.DeterministicChance(
                    ped.Handle, sequence, 22);
            arms.Start();
        }

        private static void ConfigureBodyRegion(
            Ped ped, NpcPhysicsBodyRegion region, bool lethal,
            bool armed, int sequence, bool handHit)
        {
            if (region == NpcPhysicsBodyRegion.Leg)
            {
                ConfigureShotInjuredLegHelper leg =
                    ped.Euphoria.ConfigureShotInjuredLeg;
                leg.TimeBeforeCollapseWoundLeg = lethal ? 0.1f : 1.15f;
                leg.LegInjuryTime = 1.2f;
                leg.LegForceStep = true;
                leg.LegLimpBend = 0.38f;
                leg.LegLiftTime = 0.45f;
                leg.LegInjury = 0.75f;
                leg.LegInjurySpineBend = 0.28f;
                leg.Start();
                return;
            }
            if (region == NpcPhysicsBodyRegion.Arm)
            {
                ConfigureShotInjuredArmHelper arm =
                    ped.Euphoria.ConfigureShotInjuredArm;
                arm.InjuredArmTime = handHit ? 3.2f : 1.2f;
                arm.ForceStep = true;
                arm.ForceStepExtraHeight = 0.08f;
                arm.StepTurn = true;
                arm.HipRoll = 0.25f;
                arm.Start();
                if (armed && (handHit ||
                    NpcPhysicsExperimentPolicy.DeterministicChance(
                        ped.Handle, sequence, 20)))
                    Function.Call(Hash.SET_PED_DROPS_WEAPON, ped.Handle);
                return;
            }
            if (region == NpcPhysicsBodyRegion.Gut ||
                region == NpcPhysicsBodyRegion.Torso)
            {
                ShotInGutsHelper gut = ped.Euphoria.ShotInGuts;
                gut.ShotInGuts = true;
                gut.SigSpineAmount = region == NpcPhysicsBodyRegion.Gut
                    ? 3.4f : 1.8f;
                gut.SigNeckAmount = 0.35f;
                gut.SigHipAmount = 1.1f;
                gut.SigKneeAmount = 0.55f;
                gut.SigPeriod = 1.4f;
                gut.SigForceBalancePeriod = 1.15f;
                gut.SigKneesOnset = 0.35f;
                gut.Start();
            }
        }

        private static void ApplyGroundInjury(
            Ped ped, NpcPhysicsBodyRegion region, int sequence)
        {
            if ((region == NpcPhysicsBodyRegion.Head ||
                 region == NpcPhysicsBodyRegion.Neck) &&
                (sequence > 1 ||
                 NpcPhysicsExperimentPolicy.DeterministicChance(
                    ped.Handle, sequence, 30)))
            {
                PedalLegsHelper pedal = ped.Euphoria.PedalLegs;
                pedal.PedalLeftLeg = true;
                pedal.PedalRightLeg = true;
                pedal.Radius = 0.12f;
                pedal.AngularSpeed = 3.8f;
                pedal.LegStiffness = 6f;
                pedal.SpeedAsymmetry = 1.15f;
                pedal.RadiusVariance = 0.05f;
                pedal.Start(900);
            }
            BodyWritheHelper writhe = ped.Euphoria.BodyWrithe;
            writhe.ArmStiffness = 6f;
            writhe.BackStiffness = 6f;
            writhe.LegStiffness = 6f;
            writhe.ArmAmplitude = 0.18f;
            writhe.BackAmplitude = 0.12f;
            writhe.LegAmplitude = 0.12f;
            writhe.ApplyStiffness = false;
            writhe.Start(1200);
        }

        private static void ApplyKneeDrop(Ped ped)
        {
            ShotFallToKneesHelper knees = ped.Euphoria.ShotFallToKnees;
            knees.FallToKnees = true;
            knees.FtkAlwaysChangeFall = true;
            knees.FtkBalanceTime = 0.75f;
            knees.FtkHelperForce = 0.65f;
            knees.FtkHelperForceOnSpine = true;
            knees.FtkLeanHelp = 0.25f;
            knees.FtkSpineBend = 0.12f;
            knees.FtkImpactLooseness = 0.8f;
            knees.FtkImpactLoosenessTime = 0.35f;
            knees.FtkFricMult = 1.2f;
            knees.FtkReachForWound = true;
            knees.FtkReleaseReachForWound = -1f;
            knees.FtkReleasePointGun = false;
            knees.Start();
        }

        private static void ApplyElectrocution(Ped ped)
        {
            ElectrocuteHelper shock = ped.Euphoria.Electrocute;
            shock.StunMag = 0.42f;
            shock.InitialMult = 0.65f;
            shock.LargeMult = 0.85f;
            shock.LargeMinTime = 0.12f;
            shock.LargeMaxTime = 0.35f;
            shock.BalancingMult = 0.45f;
            shock.StunInterval = 0.14f;
            shock.DirectionRandomness = 0.55f;
            shock.ApplyStiffness = false;
            shock.UseTorques = true;
            shock.Start(2200);
        }

        private static void ApplyFireBalance(Ped ped)
        {
            OnFireHelper fire = ped.Euphoria.OnFire;
            fire.StaggerTime = 4.2f;
            fire.StaggerLeanRate = 0.4f;
            fire.StumbleMaxLeanBack = 0.45f;
            fire.StumbleMaxLeanForward = 0.65f;
            fire.ArmsWindmillWritheBlend = 0.25f;
            fire.RollOverFlag = false;
            fire.Start(ReactionDurationMs);
        }

        private static void ApplyBlastProtection(Ped ped)
        {
            UpperBodyFlinchHelper flinch = ped.Euphoria.UpperBodyFlinch;
            flinch.BodyStiffness = 6f;
            flinch.BodyDamping = 0.65f;
            flinch.BackBendAmount = 0.35f;
            flinch.UseRightArm = true;
            flinch.UseLeftArm = true;
            flinch.NewHit = true;
            flinch.ProtectHeadToggle = true;
            flinch.DontBraceHead = false;
            flinch.ApplyStiffness = false;
            flinch.UseHeadLook = true;
            flinch.Start(1600);
        }

        private static bool ApplyVehicleBumpReaction(
            Ped ped, Vehicle vehicle, float speed, int sequence)
        {
            bool highSpeedImpact =
                NpcPhysicsExperimentPolicy.ShouldForceVehicleImpactRagdoll(speed);
            if (highSpeedImpact)
            {
                EnsureScriptControlRagdoll(ped, "vehicle", sequence,
                    VehicleBumpDurationMs, "vehicle_script_control_ragdoll");
            }
            else
            {
                // Even a ConfigureBalance or BraceForImpact message can start a
                // NaturalMotion task on a standing ped. Preserve GTA's native
                // stumble for slow pushes and observe it without dispatching
                // any Euphoria helper of our own.
                ReactionSnapshot before = CaptureReactionSnapshot(ped);
                Dictionary<string, object> fields = BuildSnapshotFields(
                    before, "before_");
                fields["ped"] = ped.Handle;
                fields["vehicle"] = vehicle.Handle;
                fields["speed"] = speed;
                fields["sequence"] = sequence;
                fields["ragdoll_forced"] = false;
                fields["natural_motion_dispatched"] = false;
                PhysicsExperimentLog.Info("vehicle_push_vanilla_preserved",
                    fields);
                return false;
            }
            SendNaturalMotionStage(ped, "vehicle", sequence,
                "vehicle_low_stiffness_friction", () =>
                ApplyLowStiffnessAndFriction(ped, VehicleBumpDurationMs,
                    1.28f, 55f, 5f));
            SendNaturalMotionStage(ped, "vehicle", sequence,
                "vehicle_long_balance", () =>
                ConfigureLongBalance(ped, VehicleBumpDurationMs));
            SendNaturalMotionStage(ped, "vehicle", sequence,
                "brace_for_vehicle_impact", () =>
            {
            BraceForImpactHelper brace = ped.Euphoria.BraceForImpact;
            brace.BraceDistance = 0.55f;
            brace.TargetPredictionTime = 0.18f;
            brace.ReachAbsorbtionTime = 0.25f;
            brace.BodyStiffness = 6f;
            brace.LegStiffness = 6f;
            brace.GrabDontLetGo = false;
            brace.GrabStrength = 10f;
            brace.GrabDistance = 0.6f;
            brace.GrabHoldTimer = 0.3f;
            brace.MaxGrabCarVelocity = 12f;
            brace.Pos = vehicle.Position;
            brace.InstanceIndex = vehicle.Handle;
            brace.Look = vehicle.Position;
            brace.NewBrace = true;
            brace.BraceOnImpact = true;
            brace.MoveAway = true;
            brace.MoveAwayAmount = 0.35f;
            brace.SnapImpacts = false;
            brace.SnapBonnet = 0f;
            brace.DampSpin = 0.55f;
            brace.Start(VehicleBumpDurationMs);
            });
            if (highSpeedImpact)
            {
                SendNaturalMotionStage(ped, "vehicle", sequence,
                    "high_speed_smart_fall", () =>
                {
                SmartFallHelper fall = ped.Euphoria.SmartFall;
                fall.BodyStiffness = 6f;
                fall.Bodydamping = 0.65f;
                fall.FowardRoll = false;
                fall.Balance = false;
                fall.RdsUseStartingFriction = true;
                fall.RdsStartingFriction = 1.25f;
                fall.StopRollingTime = 0.75f;
                fall.ReboundScale = 0.08f;
                fall.ForceHeadAvoid = true;
                fall.Start(VehicleBumpDurationMs);
                });
            }
            return true;
        }

        private static void EnsureScriptControlRagdoll(
            Ped ped, string reaction, int sequence, int duration, string stage)
        {
            ReactionSnapshot before = CaptureReactionSnapshot(ped);
            if (before.IsRagdoll || before.RunningRagdollTask)
            {
                Dictionary<string, object> fields = BuildSnapshotFields(
                    before, "before_");
                fields["ped"] = ped.Handle;
                fields["stage"] = stage;
                fields["reaction"] = reaction;
                fields["sequence"] = sequence;
                fields["reason"] = "existing_natural_motion_reaction";
                // Restarting ScriptControl here replaces GTA's active shot or
                // collision task and can erase the behavior we want to tune.
                PhysicsExperimentLog.Info("natural_motion_stage_skipped", fields);
                return;
            }

            SendNaturalMotionStage(ped, reaction, sequence, stage, () =>
            {
                ped.CanRagdoll = true;
                ped.Ragdoll(duration, RagdollType.ScriptControl);
            });
        }

        private static void SendNaturalMotionStage(
            Ped ped, string reaction, int sequence, string stage, Action action)
        {
            ReactionSnapshot before = CaptureReactionSnapshot(ped);
            Dictionary<string, object> context = BuildSnapshotFields(
                before, "before_");
            context["reaction"] = reaction;
            context["sequence"] = sequence;
            PhysicsExperimentLog.Step(ped.Handle, stage, action, context, () =>
                BuildSnapshotFields(CaptureReactionSnapshot(ped), "after_"));
        }

        private static ReactionSnapshot CaptureReactionSnapshot(Ped ped)
        {
            var snapshot = new ReactionSnapshot
            {
                Exists = ped != null && ped.Exists(),
            };
            if (!snapshot.Exists) return snapshot;

            int handle = ped.Handle;
            Vector3 velocity = ped.Velocity;
            snapshot.IsRagdoll = ped.IsRagdoll;
            snapshot.RunningRagdollTask = Function.Call<bool>(
                Hash.IS_PED_RUNNING_RAGDOLL_TASK, handle);
            snapshot.CanRagdoll = ped.CanRagdoll;
            snapshot.Dead = ped.IsDead;
            snapshot.Health = ped.Health;
            snapshot.HeightAboveGround = Function.Call<float>(
                Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND, handle);
            snapshot.UprightValue = Function.Call<float>(
                Hash.GET_ENTITY_UPRIGHT_VALUE, handle);
            snapshot.Speed = velocity.Length();
            snapshot.VerticalSpeed = velocity.Z;
            snapshot.Position = ped.Position;
            return snapshot;
        }

        private static Dictionary<string, object> BuildSnapshotFields(
            ReactionSnapshot snapshot, string prefix)
        {
            prefix = prefix ?? "";
            return new Dictionary<string, object>
            {
                { prefix + "exists", snapshot != null && snapshot.Exists },
                { prefix + "health", snapshot?.Health ?? 0 },
                { prefix + "dead", snapshot != null && snapshot.Dead },
                { prefix + "ragdoll", snapshot != null && snapshot.IsRagdoll },
                { prefix + "running_ragdoll_task",
                    snapshot != null && snapshot.RunningRagdollTask },
                { prefix + "can_ragdoll",
                    snapshot != null && snapshot.CanRagdoll },
                { prefix + "height_above_ground",
                    snapshot?.HeightAboveGround ?? 0f },
                { prefix + "upright_value",
                    snapshot?.UprightValue ?? 0f },
                { prefix + "speed", snapshot?.Speed ?? 0f },
                { prefix + "vertical_speed",
                    snapshot?.VerticalSpeed ?? 0f },
            };
        }

        private static bool HasActiveReaction(PedState state, int now)
        {
            return state != null && !string.IsNullOrEmpty(
                state.ActiveReactionKind) &&
                unchecked(state.ActiveReactionUntilAt - now) > 0;
        }

        private static void ScheduleLiveBalanceReinforcement(
            PedState state, int now, int sequence, int duration)
        {
            state.BalanceReinforcementAt = unchecked(
                now + LiveBalanceReinforcementDelayMs);
            state.BalanceReinforcementSequence = sequence;
            state.BalanceReinforcementDuration = duration;
        }

        private static void ApplyDueLiveBalanceReinforcement(
            Ped ped, PedState state, int now, bool safeAmbient,
            bool alive, bool inVehicle)
        {
            if (state.BalanceReinforcementAt == 0 ||
                unchecked(now - state.BalanceReinforcementAt) < 0) return;

            int sequence = state.BalanceReinforcementSequence;
            int duration = Math.Max(1000, state.BalanceReinforcementDuration -
                unchecked(now - state.LastReactionAt));
            state.BalanceReinforcementAt = 0;
            state.BalanceReinforcementSequence = 0;
            state.BalanceReinforcementDuration = 0;
            if (!safeAmbient || !alive || inVehicle ||
                sequence != state.ReactionSequence)
            {
                PhysicsExperimentLog.Info("balance_reinforcement_skipped",
                    new Dictionary<string, object>
                    {
                        { "ped", ped.Handle }, { "sequence", sequence },
                        { "safe_ambient", safeAmbient }, { "alive", alive },
                        { "in_vehicle", inVehicle },
                        { "current_sequence", state.ReactionSequence },
                    });
                return;
            }

            SendNaturalMotionStage(ped, "weapon", sequence,
                "delayed_live_stiffness", () =>
                ApplyLowStiffnessAndFriction(ped, duration, 1.12f,
                    LiveBodyRelaxation, 8f));
            SendNaturalMotionStage(ped, "weapon", sequence,
                "delayed_live_balance", () =>
                ConfigureLongBalance(ped, duration));
            PhysicsExperimentLog.Info("balance_reinforcement_dispatched",
                new Dictionary<string, object>
                {
                    { "ped", ped.Handle }, { "sequence", sequence },
                    { "duration_ms", duration },
                    { "delay_ms", LiveBalanceReinforcementDelayMs },
                });
        }

        private void CountUnreactedDisposition(string disposition)
        {
            switch (disposition)
            {
                case "non_human": _excludedNonHuman++; break;
                case "player": _excludedPlayer++; break;
                case "mission_entity": _excludedMission++; break;
                case "persistent_entity": _excludedPersistent++; break;
                case "vehicle_occupant": _excludedVehicle++; break;
                case "dead_without_fresh_weapon_evidence": _excludedDead++; break;
                case "reaction_cooldown": _cooldowns++; break;
                case "follow_on_active_reaction": _followOnDamage++; break;
                case "missing_damage_provenance":
                    _noDamageEvidence++;
                    _ambiguousDamageLosses++;
                    break;
                default: _ambiguousDamageLosses++; break;
            }
        }

        private void PruneOldStates(int now)
        {
            if (_states.Count <= MaxCandidatesPerScan * 2) return;
            var stale = new List<int>();
            foreach (KeyValuePair<int, PedState> pair in _states)
                if (unchecked(now - pair.Value.LastSeenAt) > StateRetentionMs)
                    stale.Add(pair.Key);
            foreach (int handle in stale) _states.Remove(handle);
            _prunedStates += stale.Count;
        }

        private static void ScheduleReactionObservation(
            PedState state, int now, string kind, int duration,
            ReactionSnapshot baseline)
        {
            state.ObservationStartedAt = now;
            state.ObservationIndex = 0;
            state.ObservationKind = kind ?? "unknown";
            state.ObservationBaseline = baseline;
            state.ActiveReactionKind = state.ObservationKind;
            state.ActiveReactionUntilAt = unchecked(now + duration);
        }

        private void WriteDueReactionObservation(
            Ped ped, PedState state, int now)
        {
            if (state.ObservationIndex < 0 ||
                state.ObservationIndex >= ObservationDelaysMs.Length) return;
            int elapsed = unchecked(now - state.ObservationStartedAt);
            int due = ObservationDelaysMs[state.ObservationIndex];
            if (elapsed < due) return;

            ReactionSnapshot current = CaptureReactionSnapshot(ped);
            ReactionSnapshot baseline = state.ObservationBaseline;
            Dictionary<string, object> fields = BuildOutcomeFields(
                ped, ped.Handle, state.ReactionSequence);
            fields["reaction"] = state.ObservationKind;
            fields["sample_delay_ms"] = due;
            fields["actual_elapsed_ms"] = elapsed;
            if (baseline != null)
            {
                fields["baseline_ragdoll"] = baseline.IsRagdoll;
                fields["baseline_running_ragdoll_task"] =
                    baseline.RunningRagdollTask;
                fields["baseline_height_above_ground"] =
                    baseline.HeightAboveGround;
                fields["baseline_speed"] = baseline.Speed;
                fields["baseline_vertical_speed"] = baseline.VerticalSpeed;
                fields["ragdoll_transitioned"] =
                    !baseline.IsRagdoll && current.IsRagdoll;
                fields["height_delta"] = current.HeightAboveGround -
                    baseline.HeightAboveGround;
                fields["speed_delta"] = current.Speed - baseline.Speed;
                fields["displacement"] = current.Position.DistanceTo(
                    baseline.Position);
                fields["physical_response_observed"] =
                    baseline.IsRagdoll != current.IsRagdoll ||
                    baseline.RunningRagdollTask != current.RunningRagdollTask ||
                    Math.Abs(current.HeightAboveGround -
                        baseline.HeightAboveGround) >= 0.05f ||
                    current.Position.DistanceTo(baseline.Position) >= 0.05f;
            }
            fields["active_reaction_remaining_ms"] = HasActiveReaction(
                state, now) ? unchecked(state.ActiveReactionUntilAt - now) : 0;
            PhysicsExperimentLog.Info("reaction_observation", fields);
            _reactionObservations++;
            state.ObservationIndex++;
            if (state.ObservationIndex >= ObservationDelaysMs.Length)
                state.ObservationIndex = -1;
        }

        private static Dictionary<string, object> BuildOutcomeFields(
            Ped ped, int handle, int sequence)
        {
            ReactionSnapshot snapshot = CaptureReactionSnapshot(ped);
            Dictionary<string, object> fields = BuildSnapshotFields(snapshot, "");
            fields["ped"] = handle;
            fields["sequence"] = sequence;
            // Preserve the original field names for existing log-analysis tools.
            fields["is_ragdoll_immediate"] = snapshot.IsRagdoll;
            fields["velocity"] = snapshot.Speed;
            return fields;
        }

        private void WriteHeartbeat(int now, int nearby, int processed)
        {
            PhysicsExperimentLog.Info("heartbeat",
                new Dictionary<string, object>
                {
                    { "game_time_ms", now }, { "nearby", nearby },
                    { "processed", processed }, { "tracked_states", _states.Count },
                    { "scans", _scans }, { "candidates", _candidates },
                    { "new_states", _newStates },
                    { "health_losses", _healthLosses },
                    { "damage_reactions", _damageReactions },
                    { "blast_reactions", _blastReactions },
                    { "fire_reactions", _fireReactions },
                    { "vehicle_reactions", _vehicleReactions },
                    { "ped_push_reactions", _pedPushReactions },
                    { "reaction_observations", _reactionObservations },
                    { "cohesion_active_responses",
                        _cohesionResponses.Count },
                    { "cohesion_requests", _cohesionRequests },
                    { "cohesion_cover_assignments",
                        _cohesionCoverAssignments },
                    { "cohesion_rescues_completed",
                        _cohesionRescuesCompleted },
                    { "cohesion_rescues_cancelled",
                        _cohesionRescuesCancelled },
                    { "cohesion_candidates_evaluated",
                        _cohesionCandidatesEvaluated },
                    { "cohesion_law_flag_overrides",
                        _cohesionLawFlagOverrides },
                    { "cohesion_rejected_entity_flags",
                        _cohesionRejectedEntityFlags },
                    { "cohesion_rejected_not_down",
                        _cohesionRejectedNotDown },
                    { "cohesion_rejected_inactive_reaction",
                        _cohesionRejectedInactiveReaction },
                    { "cohesion_rejected_health",
                        _cohesionRejectedHealth },
                    { "cohesion_rejected_no_responder",
                        _cohesionRejectedNoResponder },
                    { "fast_rope_tracks", _fastRopeTracks },
                    { "fast_rope_uncontrolled_falls",
                        _fastRopeUncontrolledFalls },
                    { "fast_rope_recoveries", _fastRopeRecoveries },
                    { "fast_rope_recovery_reassertions",
                        _fastRopeRecoveryReassertions },
                    { "unsafe_rappel_tasks_cancelled",
                        _unsafeRappelTasksCancelled },
                    { "unsafe_rappel_crew_locks",
                        _unsafeRappelCrewLocks },
                    { "unsafe_rappel_crew_reseats",
                        _unsafeRappelCrewReseats },
                    { "unsafe_rappel_exits_intercepted",
                        _unsafeRappelExitsIntercepted },
                    { "rappel_requests_inferred_from_exit",
                        _rappelRequestsInferredFromExit },
                    { "unsafe_rappel_crew_locked_active",
                        _rappelLockedCrew.Count },
                    { "safe_rappel_insertions_planned",
                        _safeRappelInsertionsPlanned },
                    { "safe_rappel_insertions_completed",
                        _safeRappelInsertionsCompleted },
                    { "safe_rappel_insertions_aborted",
                        _safeRappelInsertionsAborted },
                    { "safe_rappel_plan_deferrals",
                        _safeRappelPlanDeferrals },
                    { "aerial_recon_active",
                        CountAerialRole(AerialSupportRole.Recon) },
                    { "dedicated_casevac_active",
                        CountAerialRole(AerialSupportRole.Casevac) },
                    { "aerial_recon_assignments",
                        _aerialReconAssignments },
                    { "aerial_intel_relays", _aerialIntelRelays },
                    { "aerial_orbit_commands", _aerialOrbitCommands },
                    { "aerial_recon_legs_completed",
                        _aerialReconLegsCompleted },
                    { "aerial_recon_leg_stalls",
                        _aerialReconLegStalls },
                    { "aerial_recon_control_relinquished",
                        _aerialReconControlRelinquished },
                    { "aerial_recon_releases", _aerialReconReleases },
                    { "aerial_role_switches", _aerialRoleSwitches },
                    { "dedicated_casevac_spawn_attempts",
                        _dedicatedCasevacSpawnAttempts },
                    { "dedicated_casevac_spawns",
                        _dedicatedCasevacSpawns },
                    { "dedicated_casevac_spawn_failures",
                        _dedicatedCasevacSpawnFailures },
                    { "dedicated_casevac_batch_assignments",
                        _dedicatedCasevacBatchAssignments },
                    { "dedicated_casevac_passengers_loaded",
                        _dedicatedCasevacPassengersLoaded },
                    { "dedicated_casevac_despawns",
                        _dedicatedCasevacDespawns },
                    { "dedicated_casevac_spawn_cooldown_ms", Math.Max(0,
                        unchecked(_nextDedicatedCasevacSpawnAt - now)) },
                    { "hand_disarms", _handDisarms },
                    { "weapon_recovery_searches",
                        _weaponRecoverySearches },
                    { "weapon_recovery_commands",
                        _weaponRecoveryCommands },
                    { "weapon_recoveries", _weaponRecoveries },
                    { "weapon_recovery_failures",
                        _weaponRecoveryFailures },
                    { "collection_routes_started",
                        _collectionRoutesStarted },
                    { "collection_arrivals", _collectionArrivals },
                    { "casevac_assignments", _casevacAssignments },
                    { "casevac_boardings", _casevacBoardings },
                    { "casevac_completions", _casevacCompletions },
                    { "casevac_failures", _casevacFailures },
                    { "casevac_deferrals", _casevacDeferrals },
                    { "stabilized_passive_loss_prevented",
                        _stabilizedPassiveLossPrevented },
                    { "stabilized_healing_prevented",
                        _stabilizedHealingPrevented },
                    { "stabilized_damage_accepted",
                        _stabilizedDamageAccepted },
                    { "excluded_player", _excludedPlayer },
                    { "excluded_non_human", _excludedNonHuman },
                    { "excluded_mission", _excludedMission },
                    { "excluded_persistent", _excludedPersistent },
                    { "excluded_in_vehicle", _excludedVehicle },
                    { "excluded_dead", _excludedDead },
                    { "cooldowns", _cooldowns },
                    { "no_damage_evidence", _noDamageEvidence },
                    { "follow_on_reaction_damage", _followOnDamage },
                    { "ambiguous_damage_losses", _ambiguousDamageLosses },
                    { "candidate_budget_skips", _candidateTruncations },
                    { "pruned_states", _prunedStates },
                    { "exceptions", _exceptions },
                });
        }
    }
}
