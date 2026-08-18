// PoliceTacticsCoordinator.cs -- bounded open-world squad coordination.

using System;
using System.Collections.Generic;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal enum PoliceTactic
    {
        StackAndRush,
        DefensiveLine,
    }

    internal enum PoliceCombatRole
    {
        PassiveHold,
        Containment,
        DefensiveLine,
        Support,
        Assault,
        Rescue,
    }

    internal static class PoliceTacticsPolicy
    {
        internal const int MinimumSquadSize = 3;
        internal const int RushSquadSize = 6;
        internal const int StackMinimumWaitMs = 3000;
        internal const int StackMaximumWaitMs = 8000;
        internal const int FiringLineMinimumWaitMs = 1400;
        internal const int FiringLineMaximumWaitMs = 9000;
        internal const int WithdrawalSupportMaximumMs = 4200;

        internal static int CombatMovementForRole(PoliceCombatRole role)
        {
            return role == PoliceCombatRole.Assault ? 2 : 1;
        }

        internal static int CombatRangeForRole(PoliceCombatRole role)
        {
            switch (role)
            {
                case PoliceCombatRole.Assault:
                    return 1; // CR_MEDIUM, 7-30m
                case PoliceCombatRole.Support:
                    return 2; // CR_FAR, 15-40m
                default:
                    return 3; // CR_VERY_FAR, 22-45m
            }
        }

        internal static bool MaintainsMinimumDistance(
            PoliceCombatRole role)
        {
            return role != PoliceCombatRole.Assault;
        }

        internal static bool AllowsNativeAdvance(PoliceCombatRole role)
        {
            return role == PoliceCombatRole.Assault;
        }

        internal static bool CanDismountDynamicContainment(
            float distanceToPlayer, float vehicleSpeed,
            bool approachTimedOut)
        {
            float minimumRange = approachTimedOut ? 38f : 42f;
            float maximumSpeed = approachTimedOut ? 10f : 6f;
            return distanceToPlayer >= minimumRange &&
                distanceToPlayer <= 68f && vehicleSpeed <= maximumSpeed;
        }

        internal static bool CanCoordinate(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool playerAlive, int availableOfficers)
        {
            return enabled && !missionActive && !cutsceneActive &&
                wantedLevel >= 2 && playerAlive &&
                availableOfficers >= MinimumSquadSize;
        }

        internal static bool CanStageVehicleContainment(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool vehicleDriveable, bool lawDriver,
            int availableOccupants, float distanceToPlayer)
        {
            return enabled && !missionActive && !cutsceneActive &&
                wantedLevel >= 2 && vehicleDriveable && lawDriver &&
                availableOccupants >= MinimumSquadSize &&
                distanceToPlayer >= 38f && distanceToPlayer <= 110f;
        }

        internal static bool CanDismountContainment(
            float distanceToTarget, float distanceToPlayer,
            bool approachTimedOut)
        {
            float targetTolerance = approachTimedOut ? 14f : 8f;
            float safeThreatRange = approachTimedOut ? 40f : 34f;
            return distanceToTarget <= targetTolerance &&
                distanceToPlayer >= safeThreatRange &&
                distanceToPlayer <= 72f;
        }

        internal static PoliceTactic SelectTactic(
            int officers, float averageHealthRatio,
            int nearbyCasualties, bool playerInVehicle)
        {
            bool advantage = officers >= RushSquadSize &&
                averageHealthRatio >= 0.80f &&
                nearbyCasualties == 0 &&
                !playerInVehicle;
            return advantage
                ? PoliceTactic.StackAndRush
                : PoliceTactic.DefensiveLine;
        }

        internal static int RequiredStackReady(int squadSize)
        {
            if (squadSize <= 0) return 0;
            // A rush is only cohesive if the complete assigned element has
            // actually reached the stack. Partial timeout launches were the
            // main source of officers crossing open ground one at a time.
            return squadSize;
        }

        internal static bool ShouldReleaseStack(
            int readyOfficers, int squadSize, int elapsedMs)
        {
            return readyOfficers >= RequiredStackReady(squadSize) &&
                elapsedMs >= StackMinimumWaitMs;
        }

        internal static bool ShouldFallbackToLine(
            int readyOfficers, int squadSize, int elapsedMs)
        {
            return elapsedMs >= StackMaximumWaitMs &&
                readyOfficers < RequiredStackReady(squadSize);
        }

        internal static int RequiredFiringLineReady(int squadSize)
        {
            if (squadSize <= 0) return 0;
            return Math.Min(squadSize, Math.Max(2,
                (int)Math.Ceiling(squadSize * 0.60f)));
        }

        internal static bool ShouldEstablishFiringLine(
            int readyOfficers, int squadSize, int elapsedMs)
        {
            return readyOfficers >= RequiredFiringLineReady(squadSize) &&
                elapsedMs >= FiringLineMinimumWaitMs;
        }

        internal static bool ShouldAbandonFiringLineFormation(
            int readyOfficers, int squadSize, int elapsedMs)
        {
            return elapsedMs >= FiringLineMaximumWaitMs &&
                readyOfficers < RequiredFiringLineReady(squadSize);
        }

        internal static bool IsFormationMemberReady(
            float distanceToSlot, bool inCover)
        {
            return distanceToSlot <= 5.5f ||
                (inCover && distanceToSlot <= 10f);
        }

        internal static bool CanPublishCasualtyCollectionPoint(
            int readyOfficers, int squadSize, float depthBehindLine,
            float distanceFromThreat)
        {
            return readyOfficers >= RequiredFiringLineReady(squadSize) &&
                depthBehindLine >= 6f && distanceFromThreat >= 28f;
        }

        internal static int RushSupportCount(int squadSize)
        {
            if (squadSize < RushSquadSize) return 0;
            return squadSize >= 6 ? 2 : 1;
        }

        internal static bool CanSustainRushAdvantage(
            int officers, float averageHealthRatio,
            bool playerInVehicle)
        {
            return officers >= RushSquadSize &&
                averageHealthRatio >= 0.78f && !playerInVehicle;
        }

        internal static bool ShouldWithdrawDamagedElement(
            int initialOfficers, int remainingOfficers,
            float averageHealthRatio)
        {
            if (initialOfficers < MinimumSquadSize ||
                remainingOfficers <= 0) return false;
            bool casualtyThreshold = remainingOfficers * 3 <=
                initialOfficers * 2;
            return casualtyThreshold || averageHealthRatio < 0.55f;
        }

        internal static bool CanDeployProtectiveSmoke(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool throwerReady, float threatDistance,
            int cooldownRemainingMs)
        {
            return enabled && !missionActive && !cutsceneActive &&
                wantedLevel >= 2 && throwerReady &&
                threatDistance >= 10f && threatDistance <= 70f &&
                cooldownRemainingMs <= 0;
        }

        internal static bool ShouldReleaseWithdrawalCoverer(
            int movingOfficers, int movingOfficersArrived,
            int elapsedMs)
        {
            return movingOfficers <= 0 ||
                movingOfficersArrived >= movingOfficers ||
                elapsedMs >= WithdrawalSupportMaximumMs;
        }

    }

    public sealed class PoliceTacticsCoordinator : Script
    {
        private static PoliceTacticsCoordinator _current;
        private const float CoordinationRadius = 72f;
        private const float MinimumAssignmentDistance = 9f;
        private const float ClusterRadius = 25f;
        private const float CasualtyInfluenceRadius = 22f;
        private const int MaximumSquadSize = 6;
        private const int MaximumActiveSquads = 2;
        private const int DiscoveryIntervalMs = 900;
        private const int CommandRefreshMs = 1800;
        private const int CoverRetryIntervalMs = 2400;
        private const int FiringLineLifetimeMs = 45000;
        private const int MaximumCoverAttempts = 3;
        private const int RushCloseDurationMs = 3500;
        private const int RushLifetimeMs = 9000;
        private const int ReassignmentCooldownMs = 5000;
        private const int HeartbeatIntervalMs = 5000;
        private const int PassiveHoldRefreshMs = 2600;
        private const float PassiveHoldRadius = 60f;
        private const float FormationReanchorDistance = 28f;
        private const int VehicleContainmentScanIntervalMs = 1000;
        private const int VehicleContainmentCommandRefreshMs = 2500;
        private const int VehicleContainmentApproachTimeoutMs = 10000;
        private const int VehicleContainmentDismountTimeoutMs = 6500;
        private const int MaximumContainmentVehicles = 2;
        private const int MaximumContainmentRetargets = 2;
        private const float ContainmentPerimeterRange = 48f;
        private const float MinimumContainmentDismountRange = 34f;
        private const float CollectionPointDepth = 9f;
        private const float CasevacLandingDepth = 22f;
        private const int WithdrawalDurationMs = 16000;
        private const int WithdrawalCommandRefreshMs = 2200;
        private const int WithdrawalReassignmentCooldownMs = 15000;
        private const int ReinforcementPauseAfterWithdrawalMs = 10000;
        private const int ProtectiveSmokeCooldownMs = 14000;
        private const int CasualtySmokeCooldownMs = 9000;
        private const int ProtectiveSmokeGlobalMinimumMs = 4500;
        private const int ProtectiveSmokeCleanupMs = 2400;
        private const float WithdrawalDepth = 16f;

        private static readonly int CopRelationshipGroupHash =
            Game.GenerateHash("COP");
        private static readonly int ArmyRelationshipGroupHash =
            Game.GenerateHash("ARMY");
        private static readonly int RappelFromHeliTaskHash =
            Game.GenerateHash("SCRIPT_TASK_RAPPEL_FROM_HELI");
        private static readonly int BurstFirePatternHash =
            Game.GenerateHash("FIRING_PATTERN_BURST_FIRE");
        private static readonly int ProtectiveWhiteSmokeWeaponHash =
            Game.GenerateHash("WEAPON_ALLIN1_SMOKE_WHITE");
        private static readonly int ProtectiveOrangeSmokeWeaponHash =
            Game.GenerateHash("WEAPON_ALLIN1_SMOKE_ORANGE");

        private readonly Dictionary<int, TacticalSquad> _squads =
            new Dictionary<int, TacticalSquad>();
        private readonly HashSet<int> _assignedPeds =
            new HashSet<int>();
        private readonly Dictionary<int, int> _reassignmentCooldowns =
            new Dictionary<int, int>();
        private readonly Dictionary<int, VehicleContainment>
            _containmentVehicles =
                new Dictionary<int, VehicleContainment>();
        private readonly Dictionary<int, Vehicle> _deployedRoadblocks =
            new Dictionary<int, Vehicle>();
        private readonly Dictionary<int, PassiveOfficerHold> _passiveHolds =
            new Dictionary<int, PassiveOfficerHold>();
        private readonly Dictionary<int, SmokeDeployment> _smokeDeployments =
            new Dictionary<int, SmokeDeployment>();
        private readonly bool _enabled;
        private int _nextSquadId = 1;
        private int _lastDiscoveryAt;
        private int _lastHeartbeatAt;
        private int _lastVehicleContainmentScanAt;
        private int _lastProtectiveSmokeAt = int.MinValue / 2;
        private int _lastWithdrawalSmokeAt = int.MinValue / 2;
        private int _lastCasualtySmokeAt = int.MinValue / 2;
        private int _reinforcementPauseUntilAt;
        private long _squadsFormed;
        private long _rushesLaunched;
        private long _linesFormed;
        private long _rushFallbacks;
        private long _squadsReleased;
        private long _membersLost;
        private long _formationAbandons;
        private long _coverRequests;
        private long _coverAcquisitions;
        private long _coverFailures;
        private long _collectionPointsPublished;
        private long _defensiveReforms;
        private long _containmentVehiclesStaged;
        private long _containmentVehicleLinesFormed;
        private long _containmentVehicleFailures;
        private long _passiveHoldCommands;
        private long _withdrawalsStarted;
        private long _withdrawalsCompleted;
        private long _withdrawalCoverBounds;
        private long _protectiveSmokesDeployed;
        private long _combatProfileTransitions;
        private long _vehicleBlockCommands;
        private long _exceptions;

        private enum SquadPhase
        {
            Forming,
            HoldingLine,
            Rushing,
            Withdrawing,
        }

        private enum VehicleContainmentPhase
        {
            Approaching,
            Dismounting,
        }

        private sealed class VehicleContainment
        {
            internal Vehicle Vehicle;
            internal Ped Driver;
            internal readonly List<Ped> Officers = new List<Ped>();
            internal Vector3 Target;
            internal VehicleContainmentPhase Phase;
            internal int StartedAt;
            internal int PhaseStartedAt;
            internal int LastCommandAt;
            internal int Retargets;
            internal bool DynamicBlock;
            internal readonly Dictionary<int, int> PreviousCombatRanges =
                new Dictionary<int, int>();
        }

        private sealed class TacticalMember
        {
            internal Ped Ped;
            internal Vector3 Slot;
            internal int PreviousCombatMovement = 2;
            internal int PreviousCombatRange = 1;
            internal int LastCommandAt;
            internal bool Support;
            internal PoliceCombatRole? CombatRole;
            internal int CoverRequestedAt;
            internal int CoverAttempts;
            internal bool CoverAcquired;
            internal bool CoverFailureLogged;
        }

        private sealed class PassiveOfficerHold
        {
            internal Ped Ped;
            internal int PreviousCombatMovement;
            internal int PreviousCombatRange;
            internal int LastCommandAt;
        }

        private sealed class SmokeDeployment
        {
            internal Ped Thrower;
            internal int PreviousWeaponHash;
            internal int PreviousSmokeAmmo;
            internal int SmokeWeaponHash;
            internal bool PreviouslyOwnedSmoke;
            internal int CleanupAt;
        }

        private sealed class TacticalSquad
        {
            internal int Id;
            internal PoliceTactic Tactic;
            internal SquadPhase Phase;
            internal readonly List<TacticalMember> Members =
                new List<TacticalMember>();
            internal Vector3 PlayerAnchor;
            internal Vector3 FormationCenter;
            internal Vector3 AwayFromPlayer;
            internal Vector3 FormationRight;
            internal int StartedAt;
            internal int PhaseStartedAt;
            internal bool CloseCombatEngaged;
            internal Vector3 CasualtyCollectionPoint;
            internal Vector3 CasevacLandingPoint;
            internal bool CollectionPointActive;
            internal int InitialMemberCount;
            internal Vector3 WithdrawalCenter;
            internal int WithdrawalCovererHandle;
            internal bool WithdrawalCovererReleased;
        }

        public PoliceTacticsCoordinator()
        {
            _current = this;
            _enabled = NpcPhysicsExperiment.ReadBooleanSetting(
                "enhanced_police_ai", true);
            Interval = _enabled ? 200 : 1000;
            Tick += OnTick;
            Aborted += OnAborted;
            PhysicsExperimentLog.Info("police_tactics_configuration_loaded",
                new Dictionary<string, object>
                {
                    { "enabled", _enabled },
                    { "coordination_radius", CoordinationRadius },
                    { "maximum_squads", MaximumActiveSquads },
                    { "maximum_squad_size", MaximumSquadSize },
                });
        }

        private void OnTick(object sender, EventArgs args)
        {
            if (!_enabled || Game.IsLoading) return;
            try
            {
                Ped player = Game.Player.Character;
                int now = Game.GameTime;
                UpdateSmokeDeployments(now);
                if (player == null || !player.Exists() || player.IsDead ||
                    Game.IsMissionActive || Game.IsCutsceneActive ||
                    Game.Player.WantedLevel < 2)
                {
                    string releaseReason = Game.IsMissionActive
                        ? "mission_active" : Game.IsCutsceneActive
                        ? "cutscene_active" : Game.Player.WantedLevel < 2
                        ? "wanted_level_low" : "player_unavailable";
                    ReleaseAllSquads(player,
                        releaseReason, now);
                    ReleaseAllVehicleContainment(
                        player, releaseReason, now);
                    ReleaseAllPassiveHolds(true);
                    ReleaseAllSmokeDeployments();
                    ReleaseDeployedRoadblocks();
                    return;
                }

                UpdateVehicleContainment(player, now);
                UpdateSquads(player, now);
                PrunePassiveHolds(player);
                if (unchecked(now - _lastDiscoveryAt) >=
                    DiscoveryIntervalMs)
                {
                    DiscoverSquads(player, now);
                    _lastDiscoveryAt = now;
                }
                PruneCooldowns(now);
                if (unchecked(now - _lastHeartbeatAt) >=
                    HeartbeatIntervalMs)
                {
                    WriteHeartbeat(now);
                    _lastHeartbeatAt = now;
                }
            }
            catch (Exception ex)
            {
                _exceptions++;
                PhysicsExperimentLog.Error("police_tactics_tick_failed", ex);
                ClientLog.Error("NPC-PHYSICS", "PoliceTacticsCoordinator", ex);
            }
        }

        private void OnAborted(object sender, EventArgs args)
        {
            ReleaseAllSquads(Game.Player.Character,
                "script_aborted", Game.GameTime);
            ReleaseAllVehicleContainment(
                Game.Player.Character, "script_aborted", Game.GameTime);
            ReleaseAllPassiveHolds(true);
            ReleaseAllSmokeDeployments();
            ReleaseDeployedRoadblocks();
            if (ReferenceEquals(_current, this)) _current = null;
        }

        private void DiscoverSquads(Ped player, int now)
        {
            if (_squads.Count >= MaximumActiveSquads) return;
            Ped[] nearby = World.GetNearbyPeds(player, CoordinationRadius);
            var candidates = new List<Ped>();
            var casualties = new List<Vector3>();
            foreach (Ped ped in nearby)
            {
                if (!IsLawOfficer(ped, player)) continue;
                if (ped.IsDead || ped.Health <= 0 || IsPhysicallyDown(ped))
                {
                    casualties.Add(ped.Position);
                    continue;
                }
                if (IsAvailableForTactics(ped, player, now))
                    candidates.Add(ped);
            }
            foreach (Ped candidate in candidates)
                StagePassiveOfficer(candidate, player, now);
            if (unchecked(_reinforcementPauseUntilAt - now) > 0)
                return;
            if (!PoliceTacticsPolicy.CanCoordinate(
                    _enabled, false, false, Game.Player.WantedLevel,
                    !player.IsDead, candidates.Count))
                return;

            candidates.Sort((left, right) => right.Position.DistanceTo(
                player.Position).CompareTo(left.Position.DistanceTo(
                    player.Position)));
            while (_squads.Count < MaximumActiveSquads &&
                candidates.Count >= PoliceTacticsPolicy.MinimumSquadSize)
            {
                Ped seed = candidates[0];
                var cluster = new List<Ped> { seed };
                candidates.RemoveAt(0);
                candidates.Sort((left, right) => left.Position.DistanceTo(
                    seed.Position).CompareTo(right.Position.DistanceTo(
                        seed.Position)));
                for (int i = 0; i < candidates.Count &&
                    cluster.Count < MaximumSquadSize;)
                {
                    Ped candidate = candidates[i];
                    if (candidate.Position.DistanceTo(seed.Position) <=
                        ClusterRadius)
                    {
                        cluster.Add(candidate);
                        candidates.RemoveAt(i);
                    }
                    else i++;
                }
                if (cluster.Count < PoliceTacticsPolicy.MinimumSquadSize)
                    continue;
                Vector3 centroid = Vector3.Zero;
                foreach (Ped officer in cluster)
                    centroid += officer.Position;
                centroid /= cluster.Count;
                int localCasualties = 0;
                foreach (Vector3 casualty in casualties)
                    if (HorizontalDistance(casualty, centroid) <=
                        CasualtyInfluenceRadius)
                        localCasualties++;
                CreateSquad(cluster, player, localCasualties, now);
            }
        }

        private void CreateSquad(List<Ped> officers,
            Ped player, int nearbyCasualties, int now,
            bool forceDefensive = false)
        {
            float averageHealthRatio = 0f;
            Vector3 centroid = Vector3.Zero;
            foreach (Ped officer in officers)
            {
                centroid += officer.Position;
                averageHealthRatio += HealthRatio(officer);
            }
            centroid /= officers.Count;
            averageHealthRatio /= officers.Count;
            PoliceTactic tactic = forceDefensive
                ? PoliceTactic.DefensiveLine
                : PoliceTacticsPolicy.SelectTactic(
                    officers.Count, averageHealthRatio,
                    nearbyCasualties, player.IsInVehicle());
            Vector3 away = NormalizeHorizontal(
                centroid - player.Position, -player.ForwardVector);
            Vector3 right = new Vector3(-away.Y, away.X, 0f);
            float currentRange = HorizontalDistance(
                centroid, player.Position);
            float formationRange = tactic == PoliceTactic.StackAndRush
                ? Clamp(currentRange, 24f, 40f)
                : Clamp(currentRange, 38f, 52f);
            Vector3 center = player.Position + away * formationRange;
            center = ResolveSafePosition(center);
            var squad = new TacticalSquad
            {
                Id = _nextSquadId++,
                Tactic = tactic,
                Phase = SquadPhase.Forming,
                PlayerAnchor = player.Position,
                FormationCenter = center,
                AwayFromPlayer = away,
                FormationRight = right,
                StartedAt = now,
                PhaseStartedAt = now,
                InitialMemberCount = officers.Count,
            };

            for (int i = 0; i < officers.Count; i++)
            {
                Ped officer = officers[i];
                ReleasePassiveHold(officer.Handle, false);
                Vector3 desired = tactic == PoliceTactic.StackAndRush
                    ? StackSlot(squad, i)
                    : FiringLineSlot(squad, i, officers.Count);
                var member = new TacticalMember
                {
                    Ped = officer,
                    Slot = ResolveSafePosition(desired),
                    PreviousCombatMovement = Function.Call<int>(
                        Hash.GET_PED_COMBAT_MOVEMENT, officer.Handle),
                    PreviousCombatRange = Function.Call<int>(
                        Hash.GET_PED_COMBAT_RANGE, officer.Handle),
                    LastCommandAt = int.MinValue / 2,
                };
                squad.Members.Add(member);
                _assignedPeds.Add(officer.Handle);
                CommandMemberToFormation(member, squad, player, now);
            }
            _squads.Add(squad.Id, squad);
            _squadsFormed++;
            PhysicsExperimentLog.Info("police_tactical_squad_formed",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "average_health_ratio", averageHealthRatio },
                        { "nearby_casualties", nearbyCasualties },
                        { "player_in_vehicle", player.IsInVehicle() },
                        { "vehicle_borne", forceDefensive },
                    }));
        }

        private void StagePassiveOfficer(Ped officer, Ped player, int now)
        {
            if (HorizontalDistance(officer.Position, player.Position) >
                    PassiveHoldRadius)
                return;
            if (!_passiveHolds.TryGetValue(officer.Handle,
                    out PassiveOfficerHold hold))
            {
                hold = new PassiveOfficerHold
                {
                    Ped = officer,
                    PreviousCombatMovement = Function.Call<int>(
                        Hash.GET_PED_COMBAT_MOVEMENT, officer.Handle),
                    PreviousCombatRange = Function.Call<int>(
                        Hash.GET_PED_COMBAT_RANGE, officer.Handle),
                    LastCommandAt = int.MinValue / 2,
                };
                _passiveHolds.Add(officer.Handle, hold);
                ApplyCombatProfile(officer, PoliceCombatRole.PassiveHold);
                _combatProfileTransitions++;
                PhysicsExperimentLog.Info(
                    "police_combat_profile_applied",
                    new Dictionary<string, object>
                    {
                        { "ped", officer.Handle },
                        { "profile", PoliceCombatRole.PassiveHold.ToString() },
                        { "combat_movement", 1 },
                        { "combat_range", 3 },
                        { "reason", "unassigned_perimeter_hold" },
                    });
            }
            if (unchecked(now - hold.LastCommandAt) <
                    PassiveHoldRefreshMs)
                return;
            Vector3 anchor = officer.Position;
            ApplyCombatProfile(officer, PoliceCombatRole.PassiveHold);
            Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                officer.Handle, anchor.X, anchor.Y, anchor.Z,
                6f, false, false);
            Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                officer.Handle, player.Handle, 6500, false);
            hold.LastCommandAt = now;
            _passiveHoldCommands++;
        }

        private void PrunePassiveHolds(Ped player)
        {
            var handles = new List<int>(_passiveHolds.Keys);
            foreach (int handle in handles)
            {
                PassiveOfficerHold hold = _passiveHolds[handle];
                Ped officer = hold.Ped;
                if (officer == null || !officer.Exists() ||
                    officer.IsDead || officer.IsInVehicle() ||
                    _assignedPeds.Contains(handle) ||
                    HorizontalDistance(officer.Position, player.Position) >
                        CoordinationRadius + 12f)
                    ReleasePassiveHold(handle, true);
            }
        }

        private void ReleasePassiveHold(int handle, bool restoreMovement)
        {
            if (!_passiveHolds.TryGetValue(handle,
                    out PassiveOfficerHold hold)) return;
            _passiveHolds.Remove(handle);
            Ped officer = hold.Ped;
            if (officer == null || !officer.Exists() || officer.IsDead) return;
            Function.Call(Hash.REMOVE_PED_DEFENSIVE_AREA,
                officer.Handle, false);
            if (restoreMovement)
                RestoreCombatProfile(officer,
                    hold.PreviousCombatMovement,
                    hold.PreviousCombatRange);
        }

        private void ReleaseAllPassiveHolds(bool restoreMovement)
        {
            var handles = new List<int>(_passiveHolds.Keys);
            foreach (int handle in handles)
                ReleasePassiveHold(handle, restoreMovement);
        }

        private void UpdateVehicleContainment(Ped player, int now)
        {
            if (unchecked(now - _lastVehicleContainmentScanAt) >=
                VehicleContainmentScanIntervalMs)
            {
                DiscoverVehicleContainment(player, now);
                _lastVehicleContainmentScanAt = now;
            }
            if (_containmentVehicles.Count == 0) return;
            var handles = new List<int>(_containmentVehicles.Keys);
            foreach (int handle in handles)
            {
                if (!_containmentVehicles.TryGetValue(handle,
                        out VehicleContainment state)) continue;
                Vehicle vehicle = state.Vehicle;
                if (vehicle == null || !vehicle.Exists() ||
                    !vehicle.IsDriveable || vehicle.EngineHealth <= 250f ||
                    state.Driver == null || !state.Driver.Exists() ||
                    state.Driver.IsDead)
                {
                    ReleaseVehicleContainment(handle, player,
                        "vehicle_unavailable", now, true);
                    continue;
                }

                if (state.Phase == VehicleContainmentPhase.Approaching)
                {
                    float distance = HorizontalDistance(
                        vehicle.Position, state.Target);
                    float threatDistance = HorizontalDistance(
                        vehicle.Position, player.Position);
                    int elapsed = unchecked(now - state.PhaseStartedAt);
                    bool timedOut = elapsed >=
                        VehicleContainmentApproachTimeoutMs;
                    bool canDismount = state.DynamicBlock
                        ? PoliceTacticsPolicy.CanDismountDynamicContainment(
                            threatDistance, vehicle.Speed, timedOut)
                        : PoliceTacticsPolicy.CanDismountContainment(
                            distance, threatDistance, timedOut);
                    if (canDismount)
                    {
                        BeginVehicleDismount(state, player, now,
                            timedOut ? "safe_timeout_hold" :
                            "perimeter_reached");
                        continue;
                    }
                    if ((threatDistance <
                            MinimumContainmentDismountRange &&
                            elapsed >= 1500) || timedOut)
                    {
                        RetargetContainmentVehicle(
                            state, player, now,
                            threatDistance <
                                MinimumContainmentDismountRange
                                ? "too_close_to_threat"
                                : "approach_timeout");
                        continue;
                    }
                    if (unchecked(now - state.LastCommandAt) >=
                        VehicleContainmentCommandRefreshMs)
                        CommandContainmentVehicle(state, player, now);
                    continue;
                }

                var dismounted = new List<Ped>();
                foreach (Ped officer in state.Officers)
                    if (officer != null && officer.Exists() &&
                        !officer.IsDead && officer.Health > 0 &&
                        !officer.IsInVehicle())
                        dismounted.Add(officer);
                int dismountElapsed = unchecked(now - state.PhaseStartedAt);
                if (dismounted.Count < PoliceTacticsPolicy.MinimumSquadSize &&
                    dismountElapsed < VehicleContainmentDismountTimeoutMs)
                    continue;

                _containmentVehicles.Remove(handle);
                foreach (Ped officer in state.Officers)
                {
                    if (officer != null) _assignedPeds.Remove(officer.Handle);
                    if (officer != null && officer.Exists() &&
                        state.PreviousCombatRanges.TryGetValue(
                            officer.Handle, out int previousRange))
                        Function.Call(Hash.SET_PED_COMBAT_RANGE,
                            officer.Handle, previousRange);
                }
                if (dismounted.Count >= PoliceTacticsPolicy.MinimumSquadSize &&
                    _squads.Count < MaximumActiveSquads)
                {
                    _deployedRoadblocks[handle] = vehicle;
                    CreateSquad(dismounted, player, 0, now, true);
                    _containmentVehicleLinesFormed++;
                    PhysicsExperimentLog.Info(
                        "police_vehicle_containment_line_forming",
                        new Dictionary<string, object>
                        {
                            { "vehicle", handle },
                            { "officers", dismounted.Count },
                            { "dismount_elapsed_ms", dismountElapsed },
                        });
                }
                else
                {
                    _containmentVehicleFailures++;
                    foreach (Ped officer in dismounted)
                        Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                            officer.Handle, player.Handle, 7000, false);
                    PhysicsExperimentLog.Warn(
                        "police_vehicle_containment_dismount_failed",
                        new Dictionary<string, object>
                        {
                            { "vehicle", handle },
                            { "officers", dismounted.Count },
                            { "active_squads", _squads.Count },
                        });
                }
            }
        }

        private void DiscoverVehicleContainment(Ped player, int now)
        {
            if (_containmentVehicles.Count >= MaximumContainmentVehicles ||
                _squads.Count >= MaximumActiveSquads) return;
            Vehicle[] vehicles = World.GetNearbyVehicles(
                player, 100f, new Model[0]);
            foreach (Vehicle vehicle in vehicles)
            {
                if (_containmentVehicles.Count >=
                    MaximumContainmentVehicles) break;
                if (vehicle == null || !vehicle.Exists() ||
                    _containmentVehicles.ContainsKey(vehicle.Handle) ||
                    vehicle.Model.IsHelicopter || vehicle.Model.IsPlane ||
                    vehicle.Model.IsBoat) continue;
                Ped driver = vehicle.Driver;
                if (driver == null || !driver.Exists()) continue;
                var officers = new List<Ped>();
                AddContainmentOfficer(officers, driver, player);
                foreach (Ped occupant in vehicle.Occupants)
                    AddContainmentOfficer(officers, occupant, player);
                float distance = HorizontalDistance(
                    vehicle.Position, player.Position);
                if (!PoliceTacticsPolicy.CanStageVehicleContainment(
                        _enabled, false, false, Game.Player.WantedLevel,
                        vehicle.IsDriveable && vehicle.EngineHealth > 400f,
                        IsLawOfficer(driver, player), officers.Count,
                        distance)) continue;

                Vector3 target = ResolveContainmentTarget(
                    vehicle, player, _containmentVehicles.Count);
                if (target == Vector3.Zero ||
                    HorizontalDistance(target, player.Position) <
                        MinimumContainmentDismountRange)
                    continue;
                var state = new VehicleContainment
                {
                    Vehicle = vehicle,
                    Driver = driver,
                    Target = target,
                    Phase = VehicleContainmentPhase.Approaching,
                    StartedAt = now,
                    PhaseStartedAt = now,
                    LastCommandAt = int.MinValue / 2,
                };
                foreach (Ped officer in officers)
                {
                    state.Officers.Add(officer);
                    state.PreviousCombatRanges[officer.Handle] =
                        Function.Call<int>(Hash.GET_PED_COMBAT_RANGE,
                            officer.Handle);
                    _assignedPeds.Add(officer.Handle);
                }
                _containmentVehicles.Add(vehicle.Handle, state);
                foreach (Ped officer in state.Officers)
                    ApplyCombatProfile(officer,
                        officer.Handle == driver.Handle
                        ? PoliceCombatRole.Containment
                        : PoliceCombatRole.Support);
                _combatProfileTransitions += state.Officers.Count;
                CommandContainmentVehicle(state, player, now);
                _containmentVehiclesStaged++;
                PhysicsExperimentLog.Info(
                    "police_vehicle_containment_staged",
                    new Dictionary<string, object>
                    {
                        { "vehicle", vehicle.Handle },
                        { "officers", officers.Count },
                        { "distance", distance },
                        { "target_x", target.X },
                        { "target_y", target.Y },
                        { "target_z", target.Z },
                    });
            }
        }

        private void AddContainmentOfficer(List<Ped> officers,
            Ped officer, Ped player)
        {
            if (officer == null || !officer.Exists() || officer.IsDead ||
                officer.Health <= 0 || !IsLawOfficer(officer, player) ||
                _assignedPeds.Contains(officer.Handle) ||
                NpcPhysicsExperiment.IsPedReservedForCohesion(
                    officer.Handle) ||
                NpcPhysicsExperiment.IsPedInFastRopeSequence(
                    officer.Handle)) return;
            foreach (Ped existing in officers)
                if (existing.Handle == officer.Handle) return;
            officers.Add(officer);
        }

        private void CommandContainmentVehicle(
            VehicleContainment state, Ped player, int now)
        {
            Vehicle targetVehicle = player != null && player.Exists()
                ? player.CurrentVehicle : null;
            state.DynamicBlock = targetVehicle != null &&
                targetVehicle.Exists();
            Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                state.Driver.Handle, 84, state.DynamicBlock);
            if (state.DynamicBlock)
            {
                Function.Call(Hash.TASK_VEHICLE_MISSION,
                    state.Driver.Handle, state.Vehicle.Handle,
                    targetVehicle.Handle, 3, 18f,
                    (int)VehicleDrivingFlags.DrivingModeAvoidVehicles,
                    48f, 24f, false);
                _vehicleBlockCommands++;
            }
            else
            {
                state.Driver.Task.StartVehicleMission(
                    state.Vehicle, state.Target, (VehicleMissionType)4,
                    18f, VehicleDrivingFlags.DrivingModeAvoidVehicles,
                    5f, 18f, false);
            }
            state.LastCommandAt = now;
        }

        private void RetargetContainmentVehicle(
            VehicleContainment state, Ped player, int now, string reason)
        {
            state.Retargets = Math.Min(
                MaximumContainmentRetargets, state.Retargets + 1);
            state.Target = ResolveContainmentTarget(
                state.Vehicle, player,
                state.Retargets + _containmentVehicles.Count);
            state.PhaseStartedAt = now;
            CommandContainmentVehicle(state, player, now);
            PhysicsExperimentLog.Info(
                "police_vehicle_containment_retargeted",
                new Dictionary<string, object>
                {
                    { "vehicle", state.Vehicle.Handle },
                    { "reason", reason },
                    { "retargets", state.Retargets },
                    { "target_x", state.Target.X },
                    { "target_y", state.Target.Y },
                    { "target_z", state.Target.Z },
                    { "distance_to_player", HorizontalDistance(
                        state.Vehicle.Position, player.Position) },
                });
        }

        private static Vector3 ResolveContainmentTarget(
            Vehicle vehicle, Ped player, int ordinal)
        {
            Vector3 outward = NormalizeHorizontal(
                vehicle.Position - player.Position,
                -player.ForwardVector);
            Vector3 right = new Vector3(-outward.Y, outward.X, 0f);
            float range = player.IsInVehicle()
                ? ContainmentPerimeterRange + 10f
                : ContainmentPerimeterRange;
            float lateral = ordinal % 2 == 0 ? -6f : 6f;
            Vector3 desired = player.Position + outward * range +
                right * lateral;
            Vector3 target = World.GetNextPositionOnStreet(desired, true);
            if (target != Vector3.Zero && HorizontalDistance(
                    target, player.Position) >=
                    MinimumContainmentDismountRange)
                return target;
            desired = player.Position + outward * (range + 12f);
            target = World.GetNextPositionOnStreet(desired, true);
            return target == Vector3.Zero
                ? ResolveSafePosition(desired) : target;
        }

        private static void BeginVehicleDismount(
            VehicleContainment state, Ped player, int now, string reason)
        {
            Vehicle vehicle = state.Vehicle;
            Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                state.Driver.Handle, 84, false);
            Function.Call(Hash.SET_VEHICLE_FORWARD_SPEED,
                vehicle.Handle, 0f);
            Function.Call(Hash.SET_VEHICLE_HANDBRAKE,
                vehicle.Handle, true);
            Vector3 towardThreat = NormalizeHorizontal(
                player.Position - vehicle.Position, vehicle.ForwardVector);
            float heading = (float)(Math.Atan2(
                -towardThreat.X, towardThreat.Y) * 180.0 / Math.PI) + 90f;
            Function.Call(Hash.SET_ENTITY_HEADING,
                vehicle.Handle, heading);
            foreach (Ped officer in state.Officers)
                if (officer != null && officer.Exists() &&
                    !officer.IsDead && officer.IsInVehicle())
                {
                    ApplyCombatProfile(officer,
                        PoliceCombatRole.DefensiveLine);
                    Function.Call(Hash.TASK_LEAVE_VEHICLE,
                        officer.Handle, vehicle.Handle, 0);
                }
            state.Phase = VehicleContainmentPhase.Dismounting;
            state.PhaseStartedAt = now;
            PhysicsExperimentLog.Info(
                "police_vehicle_containment_dismount_ordered",
                new Dictionary<string, object>
                {
                    { "vehicle", vehicle.Handle },
                    { "officers", state.Officers.Count },
                    { "reason", reason },
                });
        }

        private void ReleaseAllVehicleContainment(
            Ped player, string reason, int now)
        {
            var handles = new List<int>(_containmentVehicles.Keys);
            foreach (int handle in handles)
                ReleaseVehicleContainment(handle, player, reason, now, false);
        }

        private void ReleaseVehicleContainment(
            int handle, Ped player, string reason, int now,
            bool defensiveExit)
        {
            if (!_containmentVehicles.TryGetValue(handle,
                    out VehicleContainment state)) return;
            _containmentVehicles.Remove(handle);
            foreach (Ped officer in state.Officers)
            {
                if (officer == null) continue;
                _assignedPeds.Remove(officer.Handle);
                if (officer.Exists() && !officer.IsDead &&
                    state.PreviousCombatRanges.TryGetValue(
                        officer.Handle, out int previousRange))
                    Function.Call(Hash.SET_PED_COMBAT_RANGE,
                        officer.Handle, previousRange);
                if (defensiveExit && officer.Exists() && !officer.IsDead &&
                    !officer.IsInVehicle() && player != null &&
                    player.Exists())
                    Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                        officer.Handle, player.Handle, 7000, false);
            }
            if (state.Vehicle != null && state.Vehicle.Exists() &&
                !defensiveExit)
                Function.Call(Hash.SET_VEHICLE_HANDBRAKE,
                    state.Vehicle.Handle, false);
            if (state.Driver != null && state.Driver.Exists())
                Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                    state.Driver.Handle, 84, false);
            _containmentVehicleFailures++;
            PhysicsExperimentLog.Warn(
                "police_vehicle_containment_released",
                new Dictionary<string, object>
                {
                    { "vehicle", handle }, { "reason", reason },
                    { "elapsed_ms", unchecked(now - state.StartedAt) },
                });
        }

        private void ReleaseDeployedRoadblocks()
        {
            foreach (KeyValuePair<int, Vehicle> pair in
                _deployedRoadblocks)
            {
                Vehicle vehicle = pair.Value;
                if (vehicle != null && vehicle.Exists())
                    Function.Call(Hash.SET_VEHICLE_HANDBRAKE,
                        vehicle.Handle, false);
            }
            _deployedRoadblocks.Clear();
        }

        internal static bool TryDeployProtectiveSmoke(
            Ped thrower, Vector3 protectedPosition, Ped threat,
            string reason, int now)
        {
            PoliceTacticsCoordinator current = _current;
            return current != null && current.TryDeployProtectiveSmokeInternal(
                thrower, protectedPosition, threat, reason, now);
        }

        private bool TryDeployProtectiveSmokeInternal(
            Ped thrower, Vector3 protectedPosition, Ped threat,
            string reason, int now)
        {
            bool throwerReady = thrower != null && thrower.Exists() &&
                !thrower.IsDead && thrower.Health > 0 &&
                !thrower.IsInVehicle() && !IsPhysicallyDown(thrower);
            float threatDistance = threat == null || !threat.Exists()
                ? float.MaxValue : HorizontalDistance(
                    protectedPosition, threat.Position);
            bool casualtyExtraction = string.Equals(
                reason, "casualty_extraction",
                StringComparison.OrdinalIgnoreCase);
            int purposeCooldown = casualtyExtraction
                ? CasualtySmokeCooldownMs : ProtectiveSmokeCooldownMs;
            int purposeLastSmokeAt = casualtyExtraction
                ? _lastCasualtySmokeAt : _lastWithdrawalSmokeAt;
            int cooldownRemaining = Math.Max(
                Math.Max(0, unchecked(_lastProtectiveSmokeAt +
                    ProtectiveSmokeGlobalMinimumMs - now)),
                Math.Max(0, unchecked(purposeLastSmokeAt +
                    purposeCooldown - now)));
            if (!PoliceTacticsPolicy.CanDeployProtectiveSmoke(
                    _enabled, Game.IsMissionActive, Game.IsCutsceneActive,
                    Game.Player.WantedLevel, throwerReady,
                    threatDistance, cooldownRemaining) ||
                _smokeDeployments.ContainsKey(thrower.Handle))
                return false;

            int smokeWeaponHash = casualtyExtraction
                ? ProtectiveOrangeSmokeWeaponHash
                : ProtectiveWhiteSmokeWeaponHash;

            bool previouslyOwned = Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON, thrower.Handle,
                smokeWeaponHash, false);
            int previousSmokeAmmo = previouslyOwned
                ? Function.Call<int>(Hash.GET_AMMO_IN_PED_WEAPON,
                    thrower.Handle, smokeWeaponHash) : 0;
            int previousWeapon = Function.Call<int>(
                Hash.GET_SELECTED_PED_WEAPON, thrower.Handle);
            Vector3 direction = NormalizeHorizontal(
                threat.Position - protectedPosition,
                thrower.ForwardVector);
            float screenDepth = Clamp(threatDistance * 0.32f, 8f, 14f);
            Vector3 target = ResolveSafePosition(
                protectedPosition + direction * screenDepth);
            Function.Call(Hash.GIVE_WEAPON_TO_PED,
                thrower.Handle, smokeWeaponHash,
                1, false, true);
            EnhancedSmokeController.ExpectThrownSmoke(
                thrower.Handle, reason, now);
            Function.Call(Hash.TASK_THROW_PROJECTILE,
                thrower.Handle, target.X, target.Y, target.Z,
                -1, false);
            _smokeDeployments[thrower.Handle] = new SmokeDeployment
            {
                Thrower = thrower,
                PreviousWeaponHash = previousWeapon,
                PreviousSmokeAmmo = previousSmokeAmmo,
                SmokeWeaponHash = smokeWeaponHash,
                PreviouslyOwnedSmoke = previouslyOwned,
                CleanupAt = unchecked(now + ProtectiveSmokeCleanupMs),
            };
            _lastProtectiveSmokeAt = now;
            if (casualtyExtraction) _lastCasualtySmokeAt = now;
            else _lastWithdrawalSmokeAt = now;
            _protectiveSmokesDeployed++;
            PhysicsExperimentLog.Info("police_protective_smoke_deployed",
                new Dictionary<string, object>
                {
                    { "reason", reason ?? "unspecified" },
                    { "thrower", thrower.Handle },
                    { "threat", threat.Handle },
                    { "threat_distance", threatDistance },
                    { "target_x", target.X },
                    { "target_y", target.Y },
                    { "target_z", target.Z },
                    { "smoke_weapon_hash", smokeWeaponHash },
                    { "settlement_required", true },
                });
            return true;
        }

        private void UpdateSmokeDeployments(int now)
        {
            if (_smokeDeployments.Count == 0) return;
            var completed = new List<int>();
            foreach (KeyValuePair<int, SmokeDeployment> pair in
                _smokeDeployments)
                if (unchecked(now - pair.Value.CleanupAt) >= 0)
                    completed.Add(pair.Key);
            foreach (int handle in completed)
                RestoreSmokeDeployment(handle);
        }

        private void RestoreSmokeDeployment(int handle)
        {
            if (!_smokeDeployments.TryGetValue(handle,
                    out SmokeDeployment deployment)) return;
            _smokeDeployments.Remove(handle);
            Ped thrower = deployment.Thrower;
            if (thrower == null || !thrower.Exists() || thrower.IsDead) return;
            if (deployment.PreviouslyOwnedSmoke)
                Function.Call(Hash.SET_PED_AMMO, thrower.Handle,
                    deployment.SmokeWeaponHash,
                    deployment.PreviousSmokeAmmo);
            else
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                    thrower.Handle, deployment.SmokeWeaponHash);
            if (deployment.PreviousWeaponHash != 0)
                Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                    thrower.Handle, deployment.PreviousWeaponHash, true);
        }

        private void ReleaseAllSmokeDeployments()
        {
            var handles = new List<int>(_smokeDeployments.Keys);
            foreach (int handle in handles) RestoreSmokeDeployment(handle);
        }

        private void UpdateSquads(Ped player, int now)
        {
            if (_squads.Count == 0) return;
            var squadIds = new List<int>(_squads.Keys);
            foreach (int squadId in squadIds)
            {
                if (!_squads.TryGetValue(squadId,
                        out TacticalSquad squad)) continue;
                RemoveUnavailableMembers(squad, player, now);
                if (squad.Phase != SquadPhase.Withdrawing &&
                    PoliceTacticsPolicy.ShouldWithdrawDamagedElement(
                        squad.InitialMemberCount, squad.Members.Count,
                        AverageMemberHealthRatio(squad)))
                {
                    BeginWithdrawal(squad, player, now,
                        "casualty_threshold_reached");
                }
                if (squad.Phase == SquadPhase.Withdrawing)
                {
                    UpdateWithdrawal(squad, player, now);
                    continue;
                }
                if (squad.Members.Count < 2)
                {
                    ReleaseSquad(squadId, player,
                        "insufficient_members", now, true);
                    continue;
                }
                if (HorizontalDistance(player.Position,
                        squad.PlayerAnchor) > FormationReanchorDistance &&
                    squad.Phase != SquadPhase.Rushing)
                {
                    ReformDefensiveLine(squad, player, now,
                        "player_moved_beyond_anchor");
                    continue;
                }

                if (squad.Phase == SquadPhase.Forming)
                    UpdateFormingSquad(squad, player, now);
                else if (squad.Phase == SquadPhase.HoldingLine)
                    UpdateFiringLine(squad, player, now);
                else
                    UpdateRush(squad, player, now);
            }
        }

        private void BeginWithdrawal(
            TacticalSquad squad, Ped player, int now, string reason)
        {
            squad.Phase = SquadPhase.Withdrawing;
            squad.PhaseStartedAt = now;
            squad.CollectionPointActive = false;
            Vector3 centroid = Vector3.Zero;
            foreach (TacticalMember member in squad.Members)
                centroid += member.Ped.Position;
            centroid /= Math.Max(1, squad.Members.Count);
            Vector3 away = NormalizeHorizontal(
                centroid - player.Position, squad.AwayFromPlayer);
            squad.AwayFromPlayer = away;
            squad.FormationRight = new Vector3(-away.Y, away.X, 0f);
            squad.WithdrawalCenter = ResolveSafePosition(
                centroid + away * WithdrawalDepth);
            for (int i = 0; i < squad.Members.Count; i++)
            {
                TacticalMember member = squad.Members[i];
                member.Support = false;
                member.Slot = ResolveSafePosition(squad.WithdrawalCenter +
                    squad.FormationRight *
                    ((i - (squad.Members.Count - 1) * 0.5f) * 2.5f));
                member.LastCommandAt = int.MinValue / 2;
            }

            TacticalMember smokeMember = null;
            foreach (TacticalMember member in squad.Members)
            {
                if (member.Ped == null || !member.Ped.Exists() ||
                    member.Ped.IsDead || member.Ped.IsInVehicle() ||
                    IsPhysicallyDown(member.Ped)) continue;
                smokeMember = member;
                if (squad.Members.Count >= 2)
                {
                    smokeMember.Support = true;
                    squad.WithdrawalCovererHandle = member.Ped.Handle;
                }
                break;
            }
            bool smokeDeployed = false;
            if (smokeMember != null)
                smokeDeployed = TryDeployProtectiveSmokeInternal(
                    smokeMember.Ped, centroid, player,
                    "squad_withdrawal", now);
            foreach (TacticalMember member in squad.Members)
            {
                if (member.Support)
                {
                    if (!smokeDeployed)
                        CommandWithdrawalSupport(member, player, now);
                    continue;
                }
                if (smokeDeployed && smokeMember != null &&
                    member.Ped.Handle == smokeMember.Ped.Handle)
                    continue;
                CommandWithdrawalRun(member, now);
            }

            _withdrawalsStarted++;
            if (smokeMember != null && smokeMember.Support)
                _withdrawalCoverBounds++;
            _reinforcementPauseUntilAt = unchecked(now +
                ReinforcementPauseAfterWithdrawalMs);
            PhysicsExperimentLog.Warn("police_tactical_withdrawal_started",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "initial_members", squad.InitialMemberCount },
                        { "remaining_members", squad.Members.Count },
                        { "coverer", squad.WithdrawalCovererHandle },
                        { "smoke_deployed", smokeDeployed },
                        { "withdrawal_x", squad.WithdrawalCenter.X },
                        { "withdrawal_y", squad.WithdrawalCenter.Y },
                        { "withdrawal_z", squad.WithdrawalCenter.Z },
                    }));
        }

        private void UpdateWithdrawal(
            TacticalSquad squad, Ped player, int now)
        {
            if (squad.Members.Count == 0)
            {
                ReleaseSquad(squad.Id, player,
                    "withdrawal_element_lost", now, false);
                return;
            }
            int arrived = 0;
            int movers = 0;
            int moversArrived = 0;
            TacticalMember coverer = null;
            foreach (TacticalMember member in squad.Members)
            {
                bool memberArrived = member.Ped.Position.DistanceTo(
                    member.Slot) <= 5.5f;
                if (memberArrived)
                    arrived++;
                if (member.Support)
                {
                    coverer = member;
                    continue;
                }
                movers++;
                if (memberArrived) moversArrived++;
                if (_smokeDeployments.ContainsKey(member.Ped.Handle))
                    continue;
                if (unchecked(now - member.LastCommandAt) >=
                    WithdrawalCommandRefreshMs)
                    CommandWithdrawalRun(member, now);
            }
            int elapsed = unchecked(now - squad.PhaseStartedAt);
            if (coverer != null && !squad.WithdrawalCovererReleased)
            {
                bool releaseCoverer =
                    PoliceTacticsPolicy.ShouldReleaseWithdrawalCoverer(
                        movers, moversArrived, elapsed);
                if (releaseCoverer)
                {
                    squad.WithdrawalCovererReleased = true;
                    CommandWithdrawalRun(coverer, now);
                    PhysicsExperimentLog.Info(
                        "police_tactical_withdrawal_coverer_released",
                        SquadFields(squad, now,
                            new Dictionary<string, object>
                            {
                                { "coverer", coverer.Ped.Handle },
                                { "movers", movers },
                                { "movers_arrived", moversArrived },
                            }));
                }
                else if (!_smokeDeployments.ContainsKey(
                        coverer.Ped.Handle) && unchecked(
                        now - coverer.LastCommandAt) >=
                        WithdrawalCommandRefreshMs)
                {
                    CommandWithdrawalSupport(coverer, player, now);
                }
            }
            else if (coverer != null && unchecked(
                    now - coverer.LastCommandAt) >=
                    WithdrawalCommandRefreshMs)
            {
                CommandWithdrawalRun(coverer, now);
            }
            if (arrived < squad.Members.Count &&
                elapsed < WithdrawalDurationMs) return;

            var cooldownHandles = new List<int>();
            foreach (TacticalMember member in squad.Members)
                if (member.Ped != null) cooldownHandles.Add(member.Ped.Handle);
            ReleaseSquad(squad.Id, player,
                arrived == squad.Members.Count
                    ? "withdrawal_complete" : "withdrawal_timeout",
                now, false);
            foreach (int handle in cooldownHandles)
                _reassignmentCooldowns[handle] = unchecked(now +
                    WithdrawalReassignmentCooldownMs);
            _withdrawalsCompleted++;
        }

        private static void CommandWithdrawalRun(
            TacticalMember member, int now)
        {
            if (member.Ped == null || !member.Ped.Exists() ||
                member.Ped.IsDead) return;
            Vector3 slot = member.Slot;
            ApplyCombatProfile(member.Ped, PoliceCombatRole.DefensiveLine);
            Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                member.Ped.Handle, slot.X, slot.Y, slot.Z,
                6f, false, false);
            Function.Call(Hash.TASK_FOLLOW_NAV_MESH_TO_COORD,
                member.Ped.Handle, slot.X, slot.Y, slot.Z,
                2.8f, WithdrawalDurationMs, 1.5f, false, 0f);
            member.LastCommandAt = now;
        }

        private static void CommandWithdrawalSupport(
            TacticalMember member, Ped player, int now)
        {
            if (member.Ped == null || !member.Ped.Exists() ||
                member.Ped.IsDead) return;
            Vector3 anchor = member.Ped.Position;
            ApplyCombatProfile(member.Ped, PoliceCombatRole.Support);
            Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                member.Ped.Handle, anchor.X, anchor.Y, anchor.Z,
                4f, false, false);
            Function.Call(Hash.TASK_SHOOT_AT_ENTITY,
                member.Ped.Handle, player.Handle, 2400,
                BurstFirePatternHash);
            member.LastCommandAt = now;
        }

        private void UpdateFormingSquad(
            TacticalSquad squad, Ped player, int now)
        {
            if (squad.Tactic == PoliceTactic.StackAndRush &&
                !PoliceTacticsPolicy.CanSustainRushAdvantage(
                    squad.Members.Count,
                    AverageMemberHealthRatio(squad),
                    player.IsInVehicle()))
            {
                ConvertToFiringLine(squad, player, now,
                    "tactical_advantage_lost");
                return;
            }
            int ready = 0;
            foreach (TacticalMember member in squad.Members)
            {
                bool inCover = Function.Call<bool>(
                    Hash.IS_PED_IN_COVER, member.Ped.Handle, false);
                if (PoliceTacticsPolicy.IsFormationMemberReady(
                        member.Ped.Position.DistanceTo(member.Slot),
                        inCover))
                    ready++;
                if (unchecked(now - member.LastCommandAt) >=
                    CommandRefreshMs)
                    CommandMemberToFormation(member, squad, player, now);
            }
            int elapsed = unchecked(now - squad.PhaseStartedAt);
            if (squad.Tactic == PoliceTactic.StackAndRush)
            {
                if (PoliceTacticsPolicy.ShouldReleaseStack(
                        ready, squad.Members.Count, elapsed))
                    LaunchRush(squad, player, now, ready);
                else if (PoliceTacticsPolicy.ShouldFallbackToLine(
                        ready, squad.Members.Count, elapsed))
                    ConvertToFiringLine(squad, player, now,
                        "stack_failed_to_assemble");
            }
            else if (PoliceTacticsPolicy.ShouldEstablishFiringLine(
                    ready, squad.Members.Count, elapsed))
            {
                EnterFiringLine(squad, player, now, ready);
            }
            else if (PoliceTacticsPolicy.ShouldAbandonFiringLineFormation(
                    ready, squad.Members.Count, elapsed))
            {
                AbandonFormationToCover(squad, player, now, ready);
            }
        }

        private void CommandMemberToFormation(
            TacticalMember member, TacticalSquad squad,
            Ped player, int now)
        {
            PoliceCombatRole role =
                squad.Tactic == PoliceTactic.DefensiveLine
                ? PoliceCombatRole.DefensiveLine
                : PoliceCombatRole.Support;
            ApplyMemberCombatProfile(member, role, squad, now,
                "formation_assignment");
            Vector3 slot = member.Slot;
            Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                member.Ped.Handle, slot.X, slot.Y, slot.Z,
                squad.Tactic == PoliceTactic.DefensiveLine ? 4f : 2.4f,
                false, false);
            if (squad.Tactic == PoliceTactic.DefensiveLine)
            {
                Function.Call(Hash.TASK_SEEK_COVER_TO_COORDS,
                    member.Ped.Handle,
                    slot.X, slot.Y, slot.Z,
                    player.Position.X, player.Position.Y,
                    player.Position.Z, 10000, false);
                member.LastCommandAt = now;
                return;
            }
            Function.Call(Hash.TASK_GO_TO_COORD_WHILE_AIMING_AT_ENTITY,
                member.Ped.Handle, slot.X, slot.Y, slot.Z,
                player.Handle,
                squad.Tactic == PoliceTactic.DefensiveLine ? 1.6f : 1.35f,
                true, 0.65f, 3f, true, 0, false,
                BurstFirePatternHash, 7000);
            member.LastCommandAt = now;
        }

        private void LaunchRush(TacticalSquad squad,
            Ped player, int now, int ready)
        {
            squad.Phase = SquadPhase.Rushing;
            squad.PhaseStartedAt = now;
            squad.CloseCombatEngaged = false;
            int supportCount = PoliceTacticsPolicy.RushSupportCount(
                squad.Members.Count);
            int assaultCount = squad.Members.Count - supportCount;
            for (int i = 0; i < squad.Members.Count; i++)
            {
                TacticalMember member = squad.Members[i];
                member.Support = i >= assaultCount;
                if (member.Support)
                {
                    ApplyMemberCombatProfile(member,
                        PoliceCombatRole.Support, squad, now,
                        "rush_fire_support");
                    Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                        member.Ped.Handle, player.Handle, 5000, false);
                    continue;
                }
                float lateral = (i - (assaultCount - 1) * 0.5f) * 1.5f;
                Vector3 closePosition = player.Position +
                    squad.AwayFromPlayer * 8f +
                    squad.FormationRight * lateral;
                closePosition = ResolveSafePosition(closePosition);
                ApplyMemberCombatProfile(member,
                    PoliceCombatRole.Assault, squad, now,
                    "coordinated_rush");
                Function.Call(Hash.TASK_GO_TO_COORD_WHILE_AIMING_AT_ENTITY,
                    member.Ped.Handle,
                    closePosition.X, closePosition.Y, closePosition.Z,
                    player.Handle, 3f, true, 0.5f, 2f,
                    true, 0, false, BurstFirePatternHash,
                    RushCloseDurationMs + 1200);
            }
            _rushesLaunched++;
            PhysicsExperimentLog.Info("police_stack_rush_launched",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "ready", ready },
                        { "required",
                            PoliceTacticsPolicy.RequiredStackReady(
                                squad.Members.Count) },
                        { "assault_count", assaultCount },
                        { "support_count", supportCount },
                    }));
        }

        private void UpdateRush(TacticalSquad squad,
            Ped player, int now)
        {
            int elapsed = unchecked(now - squad.PhaseStartedAt);
            if (!squad.CloseCombatEngaged &&
                elapsed >= RushCloseDurationMs)
            {
                squad.CloseCombatEngaged = true;
                foreach (TacticalMember member in squad.Members)
                {
                    ApplyMemberCombatProfile(member,
                        member.Support ? PoliceCombatRole.Support :
                        PoliceCombatRole.Assault,
                        squad, now, "close_combat_transition");
                    if (member.Support)
                    {
                        Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                            member.Ped.Handle, player.Handle, 6500, false);
                        continue;
                    }
                    Function.Call(Hash.TASK_COMBAT_PED,
                        member.Ped.Handle, player.Handle, 0, 16);
                }
                PhysicsExperimentLog.Info("police_stack_rush_engaged",
                    SquadFields(squad, now, null));
            }
            if (elapsed >= RushLifetimeMs)
                ReformDefensiveLine(squad, player, now,
                    "rush_completed_recontain");
        }

        private void ConvertToFiringLine(TacticalSquad squad,
            Ped player, int now, string reason)
        {
            ConfigureDefensiveLineFormation(squad, player, now);
            _rushFallbacks++;
            PhysicsExperimentLog.Info("police_stack_fallback_to_line",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                    }));
        }

        private void ReformDefensiveLine(TacticalSquad squad,
            Ped player, int now, string reason)
        {
            ConfigureDefensiveLineFormation(squad, player, now);
            _defensiveReforms++;
            PhysicsExperimentLog.Info("police_firing_line_reforming",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                        { "anchor_threshold", FormationReanchorDistance },
                    }));
        }

        private void ConfigureDefensiveLineFormation(
            TacticalSquad squad, Ped player, int now)
        {
            Vector3 centroid = Vector3.Zero;
            foreach (TacticalMember member in squad.Members)
                centroid += member.Ped.Position;
            centroid /= Math.Max(1, squad.Members.Count);
            squad.Tactic = PoliceTactic.DefensiveLine;
            squad.Phase = SquadPhase.Forming;
            squad.PhaseStartedAt = now;
            squad.PlayerAnchor = player.Position;
            squad.AwayFromPlayer = NormalizeHorizontal(
                centroid - player.Position, -player.ForwardVector);
            squad.FormationRight = new Vector3(
                -squad.AwayFromPlayer.Y, squad.AwayFromPlayer.X, 0f);
            float range = Clamp(HorizontalDistance(
                centroid, player.Position), 38f, 52f);
            squad.FormationCenter = ResolveSafePosition(
                player.Position + squad.AwayFromPlayer * range);
            squad.CollectionPointActive = false;
            for (int i = 0; i < squad.Members.Count; i++)
            {
                TacticalMember member = squad.Members[i];
                member.Support = false;
                member.CoverRequestedAt = 0;
                member.CoverAttempts = 0;
                member.CoverAcquired = false;
                member.CoverFailureLogged = false;
                member.Slot = ResolveSafePosition(
                    FiringLineSlot(squad, i, squad.Members.Count));
                member.LastCommandAt = int.MinValue / 2;
                CommandMemberToFormation(member, squad, player, now);
            }
        }

        private void EnterFiringLine(TacticalSquad squad,
            Ped player, int now, int ready)
        {
            squad.Phase = SquadPhase.HoldingLine;
            squad.PhaseStartedAt = now;
            _linesFormed++;
            Vector3 collectionPoint = ResolveSafePosition(
                squad.FormationCenter +
                squad.AwayFromPlayer * CollectionPointDepth);
            Vector3 landingPoint = ResolveSafePosition(
                squad.FormationCenter +
                squad.AwayFromPlayer * CasevacLandingDepth);
            float collectionDepth = HorizontalDistance(
                collectionPoint, squad.FormationCenter);
            float threatDistance = HorizontalDistance(
                collectionPoint, player.Position);
            squad.CollectionPointActive =
                PoliceTacticsPolicy.CanPublishCasualtyCollectionPoint(
                    ready, squad.Members.Count, collectionDepth,
                    threatDistance);
            if (squad.CollectionPointActive)
            {
                squad.CasualtyCollectionPoint = collectionPoint;
                squad.CasevacLandingPoint = landingPoint;
                _collectionPointsPublished++;
                PhysicsExperimentLog.Info(
                    "police_casualty_collection_point_published",
                    SquadFields(squad, now,
                        new Dictionary<string, object>
                        {
                            { "collection_x", collectionPoint.X },
                            { "collection_y", collectionPoint.Y },
                            { "collection_z", collectionPoint.Z },
                            { "landing_x", landingPoint.X },
                            { "landing_y", landingPoint.Y },
                            { "landing_z", landingPoint.Z },
                            { "threat_distance", threatDistance },
                        }));
            }
            foreach (TacticalMember member in squad.Members)
            {
                Vector3 slot = member.Slot;
                ApplyMemberCombatProfile(member,
                    PoliceCombatRole.DefensiveLine, squad, now,
                    "firing_line_established");
                Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                    member.Ped.Handle,
                    slot.X, slot.Y, slot.Z, 4.5f, false, false);
                CommandMemberToSlotCover(member, player, now);
            }
            PhysicsExperimentLog.Info("police_firing_line_established",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "ready", ready },
                    }));
        }

        private void UpdateFiringLine(TacticalSquad squad,
            Ped player, int now)
        {
            int elapsed = unchecked(now - squad.PhaseStartedAt);
            foreach (TacticalMember member in squad.Members)
            {
                if (member.CoverFailureLogged)
                {
                    if (unchecked(now - member.LastCommandAt) >=
                        CommandRefreshMs)
                        CommandExposedMemberToRearwardHold(
                            member, squad, player, now);
                    continue;
                }
                bool inCover = Function.Call<bool>(Hash.IS_PED_IN_COVER,
                    member.Ped.Handle, false);
                bool seekingCover = Function.Call<bool>(
                    Hash.IS_PED_GOING_INTO_COVER, member.Ped.Handle);
                if (inCover)
                {
                    if (!member.CoverAcquired)
                    {
                        member.CoverAcquired = true;
                        _coverAcquisitions++;
                        PhysicsExperimentLog.Info(
                            "police_firing_line_cover_acquired",
                            MemberFields(squad, member, now, null));
                    }
                    continue;
                }
                if (seekingCover || unchecked(now - member.LastCommandAt) <
                    CoverRetryIntervalMs) continue;

                if (member.CoverAttempts < MaximumCoverAttempts)
                {
                    if (member.CoverAttempts > 0)
                    {
                        float side = member.CoverAttempts % 2 == 0
                            ? -1.5f : 1.5f;
                        member.Slot = ResolveSafePosition(member.Slot +
                            squad.AwayFromPlayer * 2.5f +
                            squad.FormationRight * side);
                    }
                    CommandMemberToSlotCover(member, player, now);
                    continue;
                }

                if (!member.CoverFailureLogged)
                {
                    member.CoverFailureLogged = true;
                    member.Slot = ResolveSafePosition(
                        member.Ped.Position +
                        squad.AwayFromPlayer * 8f);
                    _coverFailures++;
                    PhysicsExperimentLog.Warn(
                        "police_firing_line_cover_failed",
                        MemberFields(squad, member, now,
                            new Dictionary<string, object>
                            {
                                { "fallback", "rearward_defensive_hold" },
                            }));
                }
                CommandExposedMemberToRearwardHold(
                    member, squad, player, now);
            }
            if (elapsed >= FiringLineLifetimeMs)
                ReformDefensiveLine(squad, player, now,
                    "firing_line_cycle_completed");
        }

        private void CommandMemberToSlotCover(
            TacticalMember member, Ped player, int now)
        {
            // The slot is a nav-safe formation anchor, not necessarily a real
            // cover node. Let the cover system choose geometry around the
            // defensive area instead of asking it to find cover at bare road.
            Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                member.Ped.Handle, player.Handle, 6500, false);
            member.LastCommandAt = now;
            if (member.CoverRequestedAt == 0)
                member.CoverRequestedAt = now;
            member.CoverAttempts++;
            _coverRequests++;
        }

        private void CommandExposedMemberToRearwardHold(
            TacticalMember member, TacticalSquad squad,
            Ped player, int now)
        {
            Vector3 slot = member.Slot;
            ApplyMemberCombatProfile(member,
                PoliceCombatRole.DefensiveLine, squad, now,
                "exposed_rearward_hold");
            Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                member.Ped.Handle, slot.X, slot.Y, slot.Z,
                5f, false, false);
            if (member.Ped.Position.DistanceTo(slot) > 3.5f)
            {
                Function.Call(Hash.TASK_GO_TO_COORD_WHILE_AIMING_AT_ENTITY,
                    member.Ped.Handle, slot.X, slot.Y, slot.Z,
                    player.Handle, 1.35f, true, 0.8f, 4f,
                    true, 0, false, BurstFirePatternHash, 6500);
            }
            else
            {
                Function.Call(Hash.TASK_AIM_GUN_AT_ENTITY,
                    member.Ped.Handle, player.Handle, 4500, false);
            }
            member.LastCommandAt = now;
        }

        private void AbandonFormationToCover(
            TacticalSquad squad, Ped player, int now, int ready)
        {
            Vector3 centroid = Vector3.Zero;
            foreach (TacticalMember member in squad.Members)
            {
                if (member.Ped == null || !member.Ped.Exists() ||
                    member.Ped.IsDead) continue;
                member.Slot = ResolveSafePosition(member.Ped.Position);
                centroid += member.Slot;
                ApplyMemberCombatProfile(member,
                    PoliceCombatRole.DefensiveLine, squad, now,
                    "degraded_cover_hold");
                Function.Call(Hash.SET_PED_SPHERE_DEFENSIVE_AREA,
                    member.Ped.Handle, member.Slot.X, member.Slot.Y,
                    member.Slot.Z, 5f, false, false);
                Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                    member.Ped.Handle, player.Handle, 9000, false);
                member.LastCommandAt = now;
            }
            centroid /= Math.Max(1, squad.Members.Count);
            squad.FormationCenter = centroid;
            squad.PlayerAnchor = player.Position;
            squad.AwayFromPlayer = NormalizeHorizontal(
                centroid - player.Position, -player.ForwardVector);
            squad.FormationRight = new Vector3(
                -squad.AwayFromPlayer.Y, squad.AwayFromPlayer.X, 0f);
            squad.Phase = SquadPhase.HoldingLine;
            squad.PhaseStartedAt = now;
            squad.CollectionPointActive = false;
            _formationAbandons++;
            _linesFormed++;
            PhysicsExperimentLog.Warn(
                "police_firing_line_degraded_hold",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "ready", ready },
                        { "required",
                            PoliceTacticsPolicy.RequiredFiringLineReady(
                                squad.Members.Count) },
                    }));
        }

        private void RemoveUnavailableMembers(
            TacticalSquad squad, Ped player, int now)
        {
            for (int i = squad.Members.Count - 1; i >= 0; i--)
            {
                TacticalMember member = squad.Members[i];
                Ped ped = member.Ped;
                bool exists = ped != null && ped.Exists();
                bool dead = !exists || ped.IsDead || ped.Health <= 0;
                bool inVehicle = exists && ped.IsInVehicle();
                bool physicallyDown = exists && IsPhysicallyDown(ped);
                bool reservedForCohesion = exists &&
                    NpcPhysicsExperiment.IsPedReservedForCohesion(ped.Handle);
                bool fastRopeSequence = exists &&
                    NpcPhysicsExperiment.IsPedInFastRopeSequence(ped.Handle);
                bool lawOfficer = exists && IsLawOfficer(ped, player);
                bool unavailable = !exists || dead || inVehicle ||
                    physicallyDown || reservedForCohesion ||
                    fastRopeSequence || !lawOfficer;
                if (!unavailable) continue;
                PhysicsExperimentLog.Info(
                    "police_tactical_member_removed",
                    MemberFields(squad, member, now,
                        new Dictionary<string, object>
                        {
                            { "exists", exists },
                            { "dead", dead },
                            { "health", exists ? ped.Health : 0 },
                            { "in_vehicle", inVehicle },
                            { "physically_down", physicallyDown },
                            { "reserved_for_cohesion",
                                reservedForCohesion },
                            { "fast_rope_sequence",
                                fastRopeSequence },
                            { "law_officer", lawOfficer },
                        }));
                ReleaseMember(member, player, now, false);
                squad.Members.RemoveAt(i);
                _membersLost++;
            }
        }

        private bool IsAvailableForTactics(Ped ped, Ped player, int now)
        {
            if (_assignedPeds.Contains(ped.Handle) ||
                NpcPhysicsExperiment.IsPedReservedForCohesion(ped.Handle) ||
                NpcPhysicsExperiment.IsPedInFastRopeSequence(ped.Handle) ||
                ped.IsInVehicle() || IsPhysicallyDown(ped) ||
                HorizontalDistance(ped.Position, player.Position) <
                    MinimumAssignmentDistance ||
                !Function.Call<bool>(Hash.IS_PED_ARMED, ped.Handle, 4))
                return false;
            if (_reassignmentCooldowns.TryGetValue(ped.Handle,
                    out int until) && unchecked(until - now) > 0)
                return false;
            int rappelStatus = Function.Call<int>(
                Hash.GET_SCRIPT_TASK_STATUS,
                ped.Handle, RappelFromHeliTaskHash);
            return !NpcPhysicsExperimentPolicy.IsRappelTaskActive(
                rappelStatus);
        }

        private static bool IsLawOfficer(Ped ped, Ped player)
        {
            if (ped == null || !ped.Exists() || !ped.IsHuman ||
                player == null || !player.Exists() ||
                ped.Handle == player.Handle) return false;
            int group = Function.Call<int>(
                Hash.GET_PED_RELATIONSHIP_GROUP_HASH, ped.Handle);
            if (group != CopRelationshipGroupHash &&
                group != ArmyRelationshipGroupHash) return false;
            if (ped.IsDead || ped.Health <= 0) return true;
            int relationship = Function.Call<int>(
                Hash.GET_RELATIONSHIP_BETWEEN_PEDS,
                ped.Handle, player.Handle);
            return relationship == 4 || relationship == 5 ||
                ped.IsInCombatAgainst(player);
        }

        private static bool IsPhysicallyDown(Ped ped)
        {
            if (ped == null || !ped.Exists()) return true;
            if (ped.IsRagdoll || ped.IsFalling || Function.Call<bool>(
                    Hash.IS_PED_RUNNING_RAGDOLL_TASK, ped.Handle))
                return true;
            float height = Function.Call<float>(
                Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND, ped.Handle);
            float upright = Function.Call<float>(
                Hash.GET_ENTITY_UPRIGHT_VALUE, ped.Handle);
            return NpcPhysicsExperimentPolicy.IsPhysicallyGrounded(
                height, ped.Velocity.Z, upright);
        }

        private static void ApplyCombatProfile(
            Ped ped, PoliceCombatRole role)
        {
            if (ped == null || !ped.Exists() || ped.IsDead) return;
            bool advance = PoliceTacticsPolicy.AllowsNativeAdvance(role);
            bool maintainDistance =
                PoliceTacticsPolicy.MaintainsMinimumDistance(role);
            Function.Call(Hash.SET_PED_COMBAT_MOVEMENT, ped.Handle,
                PoliceTacticsPolicy.CombatMovementForRole(role));
            Function.Call(Hash.SET_PED_COMBAT_RANGE, ped.Handle,
                PoliceTacticsPolicy.CombatRangeForRole(role));
            SetCombatAttribute(ped, 0, true);   // use cover
            SetCombatAttribute(ped, 4, true);   // dynamic strafe decisions
            SetCombatAttribute(ped, 13, advance); // aggressive advance
            SetCombatAttribute(ped, 22,
                role == PoliceCombatRole.Rescue); // drag injured allies
            SetCombatAttribute(ped, 23, true);  // require LOS to shoot
            SetCombatAttribute(ped, 28, advance); // frustrated advance
            SetCombatAttribute(ped, 29, !advance); // stage before cover search
            SetCombatAttribute(ped, 31, maintainDistance);
            SetCombatAttribute(ped, 42, advance); // flank only on assault
            SetCombatAttribute(ped, 43, advance); // advance if cover fails
            SetCombatAttribute(ped, 44, true);  // defensive while in cover
            SetCombatAttribute(ped, 47, !advance); // defensive tactical points
            SetCombatAttribute(ped, 50, advance); // charge
            SetCombatAttribute(ped, 54, true);  // choose best safe weapon
            SetCombatAttribute(ped, 60, false); // smoke is squad-coordinated
            SetCombatAttribute(ped, 71, advance); // leave area only on push
            SetCombatAttribute(ped, 73, true);  // clear-LOS tactical points
        }

        private static void RestoreCombatProfile(
            Ped ped, int combatMovement, int combatRange)
        {
            if (ped == null || !ped.Exists() || ped.IsDead) return;
            Function.Call(Hash.SET_PED_COMBAT_MOVEMENT,
                ped.Handle, combatMovement);
            Function.Call(Hash.SET_PED_COMBAT_RANGE,
                ped.Handle, combatRange);
            // Restore the native open-world law profile after our bounded
            // assignment. Values that only exist for the experiment are
            // cleared; the normal advance options are handed back to GTA.
            SetCombatAttribute(ped, 0, true);
            SetCombatAttribute(ped, 4, true);
            SetCombatAttribute(ped, 13, true);
            SetCombatAttribute(ped, 22, false);
            SetCombatAttribute(ped, 23, false);
            SetCombatAttribute(ped, 28, true);
            SetCombatAttribute(ped, 29, false);
            SetCombatAttribute(ped, 31, false);
            SetCombatAttribute(ped, 42, true);
            SetCombatAttribute(ped, 43, true);
            SetCombatAttribute(ped, 44, true);
            SetCombatAttribute(ped, 47, false);
            SetCombatAttribute(ped, 50, true);
            SetCombatAttribute(ped, 54, true);
            SetCombatAttribute(ped, 60, false);
            SetCombatAttribute(ped, 71, true);
            SetCombatAttribute(ped, 73, false);
        }

        private static void SetCombatAttribute(
            Ped ped, int attribute, bool enabled)
        {
            Function.Call(Hash.SET_PED_COMBAT_ATTRIBUTES,
                ped.Handle, attribute, enabled);
        }

        private void ApplyMemberCombatProfile(
            TacticalMember member, PoliceCombatRole role,
            TacticalSquad squad, int now, string reason)
        {
            if (member == null || member.Ped == null ||
                !member.Ped.Exists() || member.Ped.IsDead) return;
            bool changed = !member.CombatRole.HasValue ||
                member.CombatRole.Value != role;
            ApplyCombatProfile(member.Ped, role);
            member.CombatRole = role;
            if (!changed) return;
            _combatProfileTransitions++;
            PhysicsExperimentLog.Info("police_combat_profile_applied",
                MemberFields(squad, member, now,
                    new Dictionary<string, object>
                    {
                        { "profile", role.ToString() },
                        { "combat_movement",
                            PoliceTacticsPolicy.CombatMovementForRole(role) },
                        { "combat_range",
                            PoliceTacticsPolicy.CombatRangeForRole(role) },
                        { "maintain_minimum_distance",
                            PoliceTacticsPolicy.MaintainsMinimumDistance(role) },
                        { "native_advance",
                            PoliceTacticsPolicy.AllowsNativeAdvance(role) },
                        { "reason", reason },
                    }));
        }

        private void ReleaseAllSquads(
            Ped player, string reason, int now)
        {
            if (_squads.Count == 0) return;
            var ids = new List<int>(_squads.Keys);
            foreach (int id in ids)
                ReleaseSquad(id, player, reason, now);
        }

        private void ReleaseSquad(
            int squadId, Ped player, string reason, int now,
            bool resumeCombat = true)
        {
            if (!_squads.TryGetValue(squadId,
                    out TacticalSquad squad)) return;
            squad.CollectionPointActive = false;
            foreach (TacticalMember member in squad.Members)
                ReleaseMember(member, player, now, resumeCombat);
            _squads.Remove(squadId);
            _squadsReleased++;
            PhysicsExperimentLog.Info("police_tactical_squad_released",
                SquadFields(squad, now,
                    new Dictionary<string, object>
                    {
                        { "reason", reason },
                    }));
        }

        private void ReleaseMember(TacticalMember member,
            Ped player, int now, bool resumeCombat)
        {
            Ped ped = member.Ped;
            int handle = ped?.Handle ?? 0;
            _assignedPeds.Remove(handle);
            if (handle != 0)
                _reassignmentCooldowns[handle] = unchecked(
                    now + ReassignmentCooldownMs);
            if (ped == null || !ped.Exists() || ped.IsDead) return;
            Function.Call(Hash.REMOVE_PED_DEFENSIVE_AREA,
                ped.Handle, false);
            RestoreCombatProfile(ped, member.PreviousCombatMovement,
                member.PreviousCombatRange);
            if (resumeCombat && player != null && player.Exists() &&
                !player.IsDead && Game.Player.WantedLevel >= 2 &&
                !IsPhysicallyDown(ped))
            {
                // Never hand a degraded formation straight to FightAgainst;
                // that native causes the visible one-at-a-time rush. Give the
                // officer a bounded defensive transition before vanilla AI
                // resumes naturally.
                ApplyCombatProfile(ped, PoliceCombatRole.PassiveHold);
                Function.Call(Hash.TASK_SEEK_COVER_FROM_PED,
                    ped.Handle, player.Handle, 7000, false);
            }
        }

        private void PruneCooldowns(int now)
        {
            var expired = new List<int>();
            foreach (KeyValuePair<int, int> pair in _reassignmentCooldowns)
                if (unchecked(now - pair.Value) >= 0)
                    expired.Add(pair.Key);
            foreach (int handle in expired)
                _reassignmentCooldowns.Remove(handle);
        }

        private static Vector3 StackSlot(TacticalSquad squad, int index)
        {
            int row = index / 2;
            float side = index == 0 ? 0f :
                (index % 2 == 0 ? -0.85f : 0.85f);
            return squad.FormationCenter +
                squad.AwayFromPlayer * (row * 1.25f) +
                squad.FormationRight * side;
        }

        private static Vector3 FiringLineSlot(
            TacticalSquad squad, int index, int count)
        {
            float lateral = (index - (count - 1) * 0.5f) * 3.0f;
            return squad.FormationCenter +
                squad.FormationRight * lateral;
        }

        private static Vector3 ResolveSafePosition(Vector3 desired)
        {
            Vector3 safe = World.GetSafeCoordForPed(desired, true, 0);
            if (safe != Vector3.Zero &&
                safe.DistanceTo(desired) <= 7f) return safe;
            float ground = World.GetGroundHeight(desired);
            if (ground != 0f) desired.Z = ground + 0.05f;
            return desired;
        }

        private static Vector3 NormalizeHorizontal(
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

        private static float HorizontalDistance(Vector3 left, Vector3 right)
        {
            float x = left.X - right.X;
            float y = left.Y - right.Y;
            return (float)Math.Sqrt(x * x + y * y);
        }

        private static float HealthRatio(Ped ped)
        {
            return ped.MaxHealth <= 0 ? 0f :
                Clamp((float)ped.Health / ped.MaxHealth, 0f, 1f);
        }

        private static float AverageMemberHealthRatio(TacticalSquad squad)
        {
            if (squad == null || squad.Members.Count == 0) return 0f;
            float total = 0f;
            foreach (TacticalMember member in squad.Members)
                total += HealthRatio(member.Ped);
            return total / squad.Members.Count;
        }

        private static float Clamp(float value, float minimum, float maximum)
        {
            return Math.Max(minimum, Math.Min(maximum, value));
        }

        private static Dictionary<string, object> SquadFields(
            TacticalSquad squad, int now,
            Dictionary<string, object> fields)
        {
            fields = fields ?? new Dictionary<string, object>();
            fields["squad"] = squad?.Id ?? 0;
            fields["tactic"] = squad?.Tactic.ToString() ?? "None";
            fields["phase"] = squad?.Phase.ToString() ?? "None";
            fields["members"] = squad?.Members.Count ?? 0;
            fields["initial_members"] = squad?.InitialMemberCount ?? 0;
            fields["elapsed_ms"] = squad == null
                ? 0 : unchecked(now - squad.StartedAt);
            fields["phase_elapsed_ms"] = squad == null
                ? 0 : unchecked(now - squad.PhaseStartedAt);
            fields["collection_point_active"] =
                squad != null && squad.CollectionPointActive;
            return fields;
        }

        private static Dictionary<string, object> MemberFields(
            TacticalSquad squad, TacticalMember member, int now,
            Dictionary<string, object> fields)
        {
            fields = SquadFields(squad, now, fields);
            fields["ped"] = member?.Ped?.Handle ?? 0;
            fields["cover_attempts"] = member?.CoverAttempts ?? 0;
            fields["cover_elapsed_ms"] = member == null ||
                member.CoverRequestedAt == 0 ? 0 :
                unchecked(now - member.CoverRequestedAt);
            fields["slot_x"] = member?.Slot.X ?? 0f;
            fields["slot_y"] = member?.Slot.Y ?? 0f;
            fields["slot_z"] = member?.Slot.Z ?? 0f;
            return fields;
        }

        internal static bool TryGetCasualtyCollectionPoint(
            Vector3 casualtyPosition, out Vector3 collectionPoint,
            out Vector3 landingPoint, out int squadId)
        {
            collectionPoint = Vector3.Zero;
            landingPoint = Vector3.Zero;
            squadId = 0;
            PoliceTacticsCoordinator current = _current;
            if (current == null || !current._enabled) return false;
            float bestDistance = float.MaxValue;
            foreach (TacticalSquad squad in current._squads.Values)
            {
                if (!squad.CollectionPointActive ||
                    squad.Phase != SquadPhase.HoldingLine) continue;
                float distance = HorizontalDistance(
                    casualtyPosition, squad.FormationCenter);
                if (distance > CoordinationRadius ||
                    distance >= bestDistance) continue;
                bestDistance = distance;
                collectionPoint = squad.CasualtyCollectionPoint;
                landingPoint = squad.CasevacLandingPoint;
                squadId = squad.Id;
            }
            return squadId != 0;
        }

        internal static bool TryGetAerialInsertionRearZone(
            Vector3 aircraftPosition, out Vector3 rearPoint,
            out Vector3 awayFromThreat, out Vector3 formationRight,
            out Vector3 threatPosition, out int squadId)
        {
            rearPoint = Vector3.Zero;
            awayFromThreat = Vector3.Zero;
            formationRight = Vector3.Zero;
            threatPosition = Vector3.Zero;
            squadId = 0;
            PoliceTacticsCoordinator current = _current;
            if (current == null || !current._enabled) return false;
            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead)
                return false;
            float bestDistance = float.MaxValue;
            foreach (TacticalSquad squad in current._squads.Values)
            {
                if (squad.Phase != SquadPhase.HoldingLine ||
                    !squad.CollectionPointActive) continue;
                Vector3 candidate = ResolveSafePosition(
                    squad.FormationCenter + squad.AwayFromPlayer * 14f +
                    squad.FormationRight *
                        ((squad.Id & 1) == 0 ? 15f : -15f));
                float depth = HorizontalDistance(
                    candidate, squad.FormationCenter);
                float threatDistance = HorizontalDistance(
                    candidate, player.Position);
                if (!PoliceTacticsPolicy.CanPublishCasualtyCollectionPoint(
                        squad.Members.Count, squad.Members.Count,
                        depth, threatDistance)) continue;
                float aircraftDistance = HorizontalDistance(
                    aircraftPosition, candidate);
                if (aircraftDistance >= bestDistance) continue;
                bestDistance = aircraftDistance;
                rearPoint = candidate;
                awayFromThreat = squad.AwayFromPlayer;
                formationRight = squad.FormationRight;
                threatPosition = player.Position;
                squadId = squad.Id;
            }
            return squadId != 0;
        }

        internal static bool IsPedAssignedForTactics(int handle)
        {
            PoliceTacticsCoordinator current = _current;
            return current != null && handle != 0 &&
                current._assignedPeds.Contains(handle);
        }

        private void WriteHeartbeat(int now)
        {
            PhysicsExperimentLog.Info("police_tactics_heartbeat",
                new Dictionary<string, object>
                {
                    { "game_time_ms", now },
                    { "active_squads", _squads.Count },
                    { "assigned_peds", _assignedPeds.Count },
                    { "squads_formed", _squadsFormed },
                    { "rushes_launched", _rushesLaunched },
                    { "firing_lines_formed", _linesFormed },
                    { "rush_fallbacks", _rushFallbacks },
                    { "squads_released", _squadsReleased },
                    { "members_lost", _membersLost },
                    { "formation_abandons", _formationAbandons },
                    { "cover_requests", _coverRequests },
                    { "cover_acquisitions", _coverAcquisitions },
                    { "cover_failures", _coverFailures },
                    { "collection_points_published",
                        _collectionPointsPublished },
                    { "defensive_reforms", _defensiveReforms },
                    { "containment_vehicles_active",
                        _containmentVehicles.Count },
                    { "containment_vehicles_staged",
                        _containmentVehiclesStaged },
                    { "containment_vehicle_lines_formed",
                        _containmentVehicleLinesFormed },
                    { "containment_vehicle_failures",
                        _containmentVehicleFailures },
                    { "combat_profile_transitions",
                        _combatProfileTransitions },
                    { "vehicle_block_commands",
                        _vehicleBlockCommands },
                    { "passive_holds_active", _passiveHolds.Count },
                    { "passive_hold_commands", _passiveHoldCommands },
                    { "withdrawals_started", _withdrawalsStarted },
                    { "withdrawals_completed", _withdrawalsCompleted },
                    { "withdrawal_cover_bounds",
                        _withdrawalCoverBounds },
                    { "protective_smokes_deployed",
                        _protectiveSmokesDeployed },
                    { "reinforcement_pause_remaining_ms", Math.Max(0,
                        unchecked(_reinforcementPauseUntilAt - now)) },
                    { "deployed_roadblocks",
                        _deployedRoadblocks.Count },
                    { "exceptions", _exceptions },
                });
        }
    }
}
