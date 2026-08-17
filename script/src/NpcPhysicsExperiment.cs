// NpcPhysicsExperiment.cs -- opt-in GTA IV-style ambient ped reactions.
//
// This experiment deliberately stays in ScriptHookVDotNet. It does not replace
// physicstasks.ymt or NaturalMotion behavior assets, so disabling the option
// restores vanilla behavior without repairing game archives.

using System;
using System.Collections.Generic;
using System.IO;
using GTA;
using GTA.NaturalMotion;
using GTA.Native;

namespace ALLIN1
{
    internal static class NpcPhysicsExperimentPolicy
    {
        internal const int ReactionCooldownMs = 900;

        internal static bool ShouldReact(
            bool enabled,
            bool exists,
            bool isHuman,
            bool isAlive,
            bool isPlayer,
            bool isMissionEntity,
            bool isPersistent,
            bool isInVehicle,
            bool hasWeaponDamage,
            int previousHealth,
            int currentHealth,
            int elapsedSinceReactionMs)
        {
            return enabled && exists && isHuman && isAlive && !isPlayer &&
                !isMissionEntity && !isPersistent && !isInVehicle &&
                hasWeaponDamage && currentHealth < previousHealth &&
                elapsedSinceReactionMs >= ReactionCooldownMs;
        }
    }

    /// <summary>
    /// Applies an intentionally conservative, runtime-only Euphoria preset to
    /// nearby ambient human peds after weapon damage. Mission and persistent
    /// peds are excluded so authored scenes retain their own animation tasks.
    /// </summary>
    public sealed class NpcPhysicsExperiment : Script
    {
        private const float ScanRadius = 70f;
        private const int ScanIntervalMs = 100;
        private const int ReactionDurationMs = 4500;
        private const int StateRetentionMs = 10000;
        private const int MaxCandidatesPerScan = 32;

        private static readonly string ConfigPath = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.toml");

        private readonly Dictionary<int, PedState> _states =
            new Dictionary<int, PedState>();
        private bool _enabled;

        private sealed class PedState
        {
            internal int LastHealth;
            internal int LastReactionAt = int.MinValue / 2;
            internal int LastSeenAt;
        }

        public NpcPhysicsExperiment()
        {
            _enabled = ReadEnabledSetting();
            Interval = _enabled ? ScanIntervalMs : 1000;
            Tick += OnTick;
            ClientLog.Info("NPC-PHYSICS", _enabled
                ? "GTA IV-style runtime experiment enabled"
                : "Runtime experiment disabled");
        }

        private bool ReadEnabledSetting()
        {
            if (!File.Exists(ConfigPath))
                return false;

            try
            {
                string section = "";
                foreach (string rawLine in File.ReadAllLines(ConfigPath))
                {
                    string line = rawLine.Trim();
                    if (line.Length == 0 || line.StartsWith("#"))
                        continue;

                    if (line.StartsWith("[") && line.EndsWith("]"))
                    {
                        section = line.Substring(1, line.Length - 2)
                            .Trim().ToLowerInvariant();
                        continue;
                    }

                    if (section != "script")
                        continue;

                    int equals = line.IndexOf('=');
                    if (equals < 0)
                        continue;

                    string key = line.Substring(0, equals).Trim()
                        .ToLowerInvariant();
                    if (key != "gta_iv_npc_physics")
                        continue;

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
            if (!_enabled || Game.IsLoading)
                return;

            try
            {
                Ped player = Game.Player.Character;
                if (player == null || !player.Exists() || player.IsDead)
                    return;

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
            if (ped == null || !ped.Exists())
                return;

            int handle = ped.Handle;
            int health = ped.Health;
            if (!_states.TryGetValue(handle, out PedState state))
            {
                _states[handle] = new PedState
                {
                    LastHealth = health,
                    LastSeenAt = now,
                };
                return;
            }

            state.LastSeenAt = now;

            try
            {
                bool missionEntity = Function.Call<bool>(
                    Hash.IS_ENTITY_A_MISSION_ENTITY, handle);
                bool weaponDamage = health < state.LastHealth &&
                    (ped.HasBeenDamagedByAnyWeapon() ||
                     ped.HasBeenDamagedByAnyMeleeWeapon());
                int elapsed = unchecked(now - state.LastReactionAt);

                if (NpcPhysicsExperimentPolicy.ShouldReact(
                    _enabled,
                    exists: true,
                    isHuman: ped.IsHuman,
                    isAlive: !ped.IsDead,
                    isPlayer: handle == playerHandle,
                    isMissionEntity: missionEntity,
                    isPersistent: ped.IsPersistent,
                    isInVehicle: ped.IsInVehicle(),
                    hasWeaponDamage: weaponDamage,
                    previousHealth: state.LastHealth,
                    currentHealth: health,
                    elapsedSinceReactionMs: elapsed))
                {
                    ApplyGtaIvStyleReaction(ped);
                    state.LastReactionAt = now;
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("NPC-PHYSICS",
                    $"InspectPed handle={handle}", ex);
            }
            finally
            {
                state.LastHealth = health;
            }
        }

        private static void ApplyGtaIvStyleReaction(Ped ped)
        {
            ped.CanRagdoll = true;
            ped.Ragdoll(ReactionDurationMs, RagdollType.ScriptControl);

            ConfigureBalanceHelper balance = ped.Euphoria.ConfigureBalance;
            balance.LegStiffness = 9.5f;
            balance.LeftLegSwingDamping = 1.3f;
            balance.RightLegSwingDamping = 1.3f;
            balance.BalanceAbortThreshold = 0.72f;
            balance.GiveUpHeight = 0.35f;
            balance.PredictionTime = 0.32f;
            balance.MaxSteps = 12;
            balance.MaxBalanceTime = 4.25f;
            balance.ExtraSteps = 3;
            balance.ExtraTime = 1.25f;
            balance.FootFriction = 1.15f;
            balance.FootFrictionStagger = 0.85f;
            balance.GiveUpHeightEnd = 0.55f;
            balance.BalanceAbortThresholdEnd = 0.5f;
            balance.GiveUpRampDuration = 3.25f;
            balance.Start();

            StaggerFallHelper stagger = ped.Euphoria.StaggerFall;
            stagger.ArmStiffnessStart = 3.5f;
            stagger.SpineStiffnessStart = 4f;
            stagger.ArmStiffness = 8f;
            stagger.SpineStiffness = 7.5f;
            stagger.TimeAtStartValues = 0.18f;
            stagger.RampTimeFromStartValues = 0.55f;
            stagger.StaggerStepProb = 0.55f;
            stagger.StepsTillStartEnd = 5;
            stagger.TimeStartEnd = 2.8f;
            stagger.RampTimeToEndValues = 1.2f;
            stagger.LowerBodyStiffness = 11f;
            stagger.LowerBodyStiffnessEnd = 5.5f;
            stagger.PredictionTime = 0.28f;
            stagger.PerStepReduction1 = 0.55f;
            stagger.UpperBodyReaction = true;
            stagger.UseHeadLook = true;
            stagger.Start(ReactionDurationMs);

            CatchFallHelper catchFall = ped.Euphoria.CatchFall;
            catchFall.TorsoStiffness = 8f;
            catchFall.LegsStiffness = 7f;
            catchFall.ArmsStiffness = 9f;
            catchFall.UseHeadLook = true;
            catchFall.Start(ReactionDurationMs);
        }

        private void PruneOldStates(int now)
        {
            if (_states.Count <= MaxCandidatesPerScan * 2)
                return;

            var stale = new List<int>();
            foreach (KeyValuePair<int, PedState> pair in _states)
            {
                if (unchecked(now - pair.Value.LastSeenAt) > StateRetentionMs)
                    stale.Add(pair.Key);
            }

            foreach (int handle in stale)
                _states.Remove(handle);
        }
    }
}
