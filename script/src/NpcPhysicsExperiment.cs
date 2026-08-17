// NpcPhysicsExperiment.cs -- opt-in GTA IV/RDR-style ambient ped reactions.
//
// This experiment deliberately stays in ScriptHookVDotNet. It sends runtime
// NaturalMotion messages and does not replace physicstasks.ymt, behaviours.xml,
// pedbounds.xml, or materials.dat.

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

    internal static class NpcPhysicsExperimentPolicy
    {
        internal const int ReactionCooldownMs = 900;
        internal const int VehicleBumpCooldownMs = 700;

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
                collided && vehicleExists && vehicleSpeed >= 1.2f &&
                distance <= 3.25f && elapsedMs >= VehicleBumpCooldownMs;
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
        private const float ScanRadius = 70f;
        private const int ScanIntervalMs = 100;
        private const int ReactionDurationMs = 4500;
        private const int VehicleBumpDurationMs = 3200;
        private const int StateRetentionMs = 10000;
        private const int MaxCandidatesPerScan = 32;

        private static readonly int StunGunHash =
            Game.GenerateHash("WEAPON_STUNGUN");
        private static readonly int StunGunMpHash =
            Game.GenerateHash("WEAPON_STUNGUN_MP");
        private static readonly string ConfigPath = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.toml");

        private readonly Dictionary<int, PedState> _states =
            new Dictionary<int, PedState>();
        private bool _enabled;

        private sealed class PedState
        {
            internal int LastHealth;
            internal bool WasAlive;
            internal int LastReactionAt = int.MinValue / 2;
            internal int LastVehicleBumpAt = int.MinValue / 2;
            internal int LastSeenAt;
            internal int ReactionSequence;
        }

        public NpcPhysicsExperiment()
        {
            _enabled = ReadEnabledSetting();
            Interval = _enabled ? ScanIntervalMs : 1000;
            Tick += OnTick;
            ClientLog.Info("NPC-PHYSICS", _enabled
                ? "Expanded Euphoria runtime experiment enabled"
                : "Runtime experiment disabled");
        }

        private bool ReadEnabledSetting()
        {
            if (!File.Exists(ConfigPath)) return false;
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
                    if (key != "gta_iv_npc_physics") continue;
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
                ClientLog.Error("NPC-PHYSICS", "ReadEnabledSetting", ex);
            }
            return false;
        }

        private void OnTick(object sender, EventArgs args)
        {
            if (!_enabled || Game.IsLoading) return;
            try
            {
                Ped player = Game.Player.Character;
                if (player == null || !player.Exists() || player.IsDead) return;
                int now = Game.GameTime;
                Ped[] nearby = World.GetNearbyPeds(player, ScanRadius);
                int budget = Math.Min(nearby.Length, MaxCandidatesPerScan);
                for (int i = 0; i < budget; i++)
                    InspectPed(nearby[i], player.Handle, now);
                PruneOldStates(now);
            }
            catch (Exception ex)
            {
                ClientLog.Error("NPC-PHYSICS", "OnTick", ex);
            }
        }

        private void InspectPed(Ped ped, int playerHandle, int now)
        {
            if (ped == null || !ped.Exists()) return;
            int handle = ped.Handle;
            int health = ped.Health;
            bool alive = !ped.IsDead && health > 0;
            if (!_states.TryGetValue(handle, out PedState state))
            {
                _states[handle] = new PedState
                {
                    LastHealth = health,
                    WasAlive = alive,
                    LastSeenAt = now,
                };
                return;
            }
            state.LastSeenAt = now;
            bool clearDamageFlags = false;

            try
            {
                bool missionEntity = Function.Call<bool>(
                    Hash.IS_ENTITY_A_MISSION_ENTITY, handle);
                bool safeAmbient = ped.IsHuman && handle != playerHandle &&
                    !missionEntity && !ped.IsPersistent;
                clearDamageFlags = safeAmbient && health < state.LastHealth;
                bool inVehicle = ped.IsInVehicle();
                bool meleeDamage = health < state.LastHealth &&
                    ped.HasBeenDamagedByAnyMeleeWeapon();
                bool weaponDamage = health < state.LastHealth &&
                    (ped.HasBeenDamagedByAnyWeapon() || meleeDamage);
                int elapsed = unchecked(now - state.LastReactionAt);
                bool blastReaction = !weaponDamage &&
                    NpcPhysicsExperimentPolicy.ShouldReactToBlast(
                        _enabled, safeAmbient, alive, inVehicle,
                        health < state.LastHealth,
                        health < state.LastHealth &&
                            WasNearExplosion(ped.Position), elapsed);
                bool liveReaction = NpcPhysicsExperimentPolicy.ShouldReact(
                    _enabled, true, ped.IsHuman, alive,
                    handle == playerHandle, missionEntity, ped.IsPersistent,
                    inVehicle, weaponDamage, state.LastHealth, health, elapsed);
                bool lethalReaction =
                    NpcPhysicsExperimentPolicy.ShouldReactToLethalDamage(
                        _enabled, ped.IsHuman, handle == playerHandle,
                        missionEntity, ped.IsPersistent, inVehicle, state.WasAlive,
                        state.LastHealth, health, weaponDamage, elapsed);

                if (liveReaction || lethalReaction || blastReaction)
                {
                    state.ReactionSequence++;
                    NpcPhysicsBodyRegion region =
                        NpcPhysicsExperimentPolicy.ClassifyBone(
                            GetLastDamageBone(ped));
                    bool grounded = ped.IsRagdoll ||
                        Function.Call<float>(Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND,
                            handle) < 0.8f;
                    bool taser = WasDamagedBy(ped, StunGunHash) ||
                        WasDamagedBy(ped, StunGunMpHash);
                    bool onFire = Function.Call<bool>(Hash.IS_ENTITY_ON_FIRE,
                        handle);
                    bool armed = Function.Call<bool>(Hash.IS_PED_ARMED,
                        handle, 4);
                    ApplyDamageReaction(ped, region, meleeDamage, taser,
                        onFire, grounded, lethalReaction, armed,
                        state.ReactionSequence, blastReaction);
                    state.LastReactionAt = now;
                }
                else if (alive && safeAmbient && !inVehicle)
                {
                    TryApplyVehicleBump(ped, state, now);
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("NPC-PHYSICS",
                    $"InspectPed handle={handle}", ex);
            }
            finally
            {
                if (clearDamageFlags && ped.Exists())
                    Function.Call(Hash.CLEAR_ENTITY_LAST_WEAPON_DAMAGE,
                        handle);
                state.LastHealth = health;
                state.WasAlive = alive;
            }
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

        private static bool WasNearExplosion(Vector3 position)
        {
            // Called only after an unexplained fresh health loss, so the native
            // query cost is paid on an exceptional path rather than each scan.
            for (int type = 0; type <= 38; type++)
                if (Function.Call<bool>(Hash.IS_EXPLOSION_IN_SPHERE, type,
                        position.X, position.Y, position.Z, 6f))
                    return true;
            return false;
        }

        private static void TryApplyVehicleBump(
            Ped ped, PedState state, int now)
        {
            bool collided = Function.Call<bool>(
                Hash.HAS_ENTITY_COLLIDED_WITH_ANYTHING, ped.Handle);
            if (!collided) return;
            Vehicle vehicle = World.GetClosestVehicle(ped.Position, 3.25f);
            bool exists = vehicle != null && vehicle.Exists();
            float speed = exists ? vehicle.Speed : 0f;
            float distance = exists
                ? vehicle.Position.DistanceTo(ped.Position) : float.MaxValue;
            int elapsed = unchecked(now - state.LastVehicleBumpAt);
            if (!NpcPhysicsExperimentPolicy.ShouldReactToVehicleBump(
                    true, true, true, false, collided, exists,
                    speed, distance, elapsed)) return;
            ApplyVehicleBumpReaction(ped, vehicle, speed);
            state.LastVehicleBumpAt = now;
        }

        private static void ApplyDamageReaction(
            Ped ped, NpcPhysicsBodyRegion region, bool melee, bool taser,
            bool onFire, bool grounded, bool lethal, bool armed, int sequence,
            bool blast)
        {
            ped.CanRagdoll = true;
            ped.Ragdoll(ReactionDurationMs, RagdollType.ScriptControl);
            ApplyLowStiffnessAndFriction(ped, ReactionDurationMs, 1.12f);
            ConfigureLongBalance(ped, ReactionDurationMs);
            ConfigureWoundReach(ped, melee, armed, sequence);
            ConfigureBodyRegion(ped, region, lethal);
            if (blast) ApplyBlastProtection(ped);
            if (taser) ApplyElectrocution(ped);
            if (onFire) ApplyFireBalance(ped);
            if (grounded) ApplyGroundInjury(ped, region, sequence);
            if (lethal && NpcPhysicsExperimentPolicy.DeterministicChance(
                    ped.Handle, sequence, 34))
                ApplyKneeDrop(ped);
        }

        private static void ApplyLowStiffnessAndFriction(
            Ped ped, int duration, float friction)
        {
            SetStiffnessHelper stiffness = ped.Euphoria.SetStiffness;
            stiffness.BodyStiffness = 2f;
            stiffness.Damping = 0.55f;
            stiffness.Start(duration);
            BodyRelaxHelper relax = ped.Euphoria.BodyRelax;
            relax.Relaxation = 82f;
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
            balance.LegStiffness = 6f;
            balance.LeftLegSwingDamping = 1.05f;
            balance.RightLegSwingDamping = 1.05f;
            balance.BalanceAbortThreshold = 0.78f;
            balance.GiveUpHeight = 0.28f;
            balance.PredictionTime = 0.3f;
            balance.MaxSteps = 16;
            balance.MaxBalanceTime = 4.4f;
            balance.ExtraSteps = 4;
            balance.ExtraTime = 1.35f;
            balance.FootFriction = 1.18f;
            balance.FootFrictionStagger = 1.02f;
            balance.GiveUpHeightEnd = 0.48f;
            balance.BalanceAbortThresholdEnd = 0.54f;
            balance.GiveUpRampDuration = 3.6f;
            balance.Start();
            BodyBalanceHelper body = ped.Euphoria.BodyBalance;
            body.ArmStiffness = 6f;
            body.SpineStiffness = 6f;
            body.ArmDamping = 0.7f;
            body.SpineDamping = 0.7f;
            body.UseHeadLook = true;
            body.ArmsOutOnPush = true;
            body.ArmsOutOnPushMultiplier = 0.65f;
            body.ArmsOutOnPushTimeout = 0.7f;
            body.ReturningToBalanceArmsOut = 0.65f;
            body.UseBodyTurn = true;
            body.Start(duration);
            CatchFallHelper catchFall = ped.Euphoria.CatchFall;
            catchFall.TorsoStiffness = 6f;
            catchFall.LegsStiffness = 6f;
            catchFall.ArmsStiffness = 6f;
            catchFall.UseHeadLook = true;
            catchFall.Start(duration);
        }

        private static void ConfigureWoundReach(
            Ped ped, bool melee, bool armed, int sequence)
        {
            ShotHelper shot = ped.Euphoria.Shot;
            shot.BodyStiffness = 6f;
            shot.ArmStiffness = 6f;
            shot.ReachForWound = true;
            shot.GrabHoldTime = 3.2f;
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
            arms.Brace = true;
            arms.ReachFalling = 2;
            arms.ReachFallingWithOneHand = 3;
            arms.ReachOnFloor = 2;
            arms.AlwaysReachTime = 2.6f;
            arms.ReachWithOneHand = 0;
            arms.ReleaseWound = 0;
            arms.AllowLeftPistolRFW = true;
            arms.AllowRightPistolRFW = true;
            arms.RfwWithPistol = true;
            arms.PointGun = armed &&
                NpcPhysicsExperimentPolicy.DeterministicChance(
                    ped.Handle, sequence, 22);
            arms.Start();
        }

        private static void ConfigureBodyRegion(
            Ped ped, NpcPhysicsBodyRegion region, bool lethal)
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
                arm.InjuredArmTime = 1.2f;
                arm.ForceStep = true;
                arm.ForceStepExtraHeight = 0.08f;
                arm.StepTurn = true;
                arm.HipRoll = 0.25f;
                arm.Start();
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

        private static void ApplyVehicleBumpReaction(
            Ped ped, Vehicle vehicle, float speed)
        {
            ped.CanRagdoll = true;
            ped.Ragdoll(VehicleBumpDurationMs, RagdollType.ScriptControl);
            ApplyLowStiffnessAndFriction(ped, VehicleBumpDurationMs,
                speed >= 7f ? 1.28f : 1.16f);
            ConfigureLongBalance(ped, VehicleBumpDurationMs);
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
            if (speed >= 7f)
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
        }
    }
}
