// RealisticSuppressorController.cs -- suppressors provide a believable
// stealth benefit, accumulate heat and wear, glow when incandescent, and can
// fail permanently when the optional breakage simulation is enabled.

using System;
using System.Collections.Generic;
using System.Drawing;
using ALLIN1;
using GTA;
using GTA.Math;
using GTA.Native;

namespace RealisticSuppressors
{
    internal enum SuppressorWeaponClass
    {
        Sidearm,
        SubmachineGun,
        Rifle,
        Shotgun,
        Sniper,
        Other,
    }

    internal enum SuppressorWitnessReason
    {
        None,
        AlreadyAlerted,
        BulletCrackOrImpact,
        AudibleMuzzle,
        VisualIdentification,
    }

    internal readonly struct SuppressorPoint
    {
        internal SuppressorPoint(float x, float y, float z)
        {
            X = x;
            Y = y;
            Z = z;
        }

        internal float X { get; }
        internal float Y { get; }
        internal float Z { get; }
    }

    internal static class RealisticSuppressorPolicy
    {
        internal const int BurstResetMs = 1500;
        internal const float CloseAudibleRadius = 7.5f;
        internal const float BulletCrackRadius = 8f;
        internal const float ImpactCueRadius = 14f;
        internal const float VisualIdentificationRadius = 65f;
        internal const float MaximumAudibleRadius = 55f;

        internal static float BaseAudibleRadius(
            SuppressorWeaponClass weaponClass)
        {
            switch (weaponClass)
            {
                case SuppressorWeaponClass.Sidearm:
                    return 18f;
                case SuppressorWeaponClass.SubmachineGun:
                    return 23f;
                case SuppressorWeaponClass.Rifle:
                    return 29f;
                case SuppressorWeaponClass.Shotgun:
                    return 34f;
                case SuppressorWeaponClass.Sniper:
                    return 38f;
                default:
                    return 26f;
            }
        }

        internal static float AudibleRadius(
            SuppressorWeaponClass weaponClass, int burstRounds,
            bool indoors)
        {
            int rounds = Math.Max(1, Math.Min(12, burstRounds));
            float radius = BaseAudibleRadius(weaponClass) +
                (rounds - 1) * 2.25f;
            if (indoors) radius *= 1.30f;
            return Math.Min(MaximumAudibleRadius, radius);
        }

        internal static int UpdateBurstCount(
            int now, int lastShotAt, int previousRounds,
            int roundsFired)
        {
            if (roundsFired <= 0) return Math.Max(0, previousRounds);
            int elapsed = unchecked(now - lastShotAt);
            bool sameBurst = elapsed >= 0 && elapsed <= BurstResetMs;
            int prior = sameBurst ? Math.Max(0, previousRounds) : 0;
            return Math.Min(12, prior + roundsFired);
        }

        internal static SuppressorWitnessReason CredibleWitnessReason(
            float shooterDistance, float projectileDistance,
            float impactDistance, float audibleRadius,
            bool alreadyAlerted, bool canHearPlayer,
            bool hasClearLineOfSight, bool isFacingShooter)
        {
            if (alreadyAlerted)
                return SuppressorWitnessReason.AlreadyAlerted;
            if (projectileDistance <= BulletCrackRadius ||
                impactDistance <= ImpactCueRadius)
                return SuppressorWitnessReason.BulletCrackOrImpact;
            if (shooterDistance <= CloseAudibleRadius ||
                (shooterDistance <= audibleRadius && canHearPlayer))
                return SuppressorWitnessReason.AudibleMuzzle;
            if (shooterDistance <= VisualIdentificationRadius &&
                hasClearLineOfSight && isFacingShooter)
                return SuppressorWitnessReason.VisualIdentification;
            return SuppressorWitnessReason.None;
        }

        internal static bool ShouldPreArmCrime(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool weaponIsSilenced,
            bool hasPotentialWitness)
        {
            return enabled && !missionActive && !cutsceneActive &&
                wantedLevel == 0 && weaponIsSilenced &&
                !hasPotentialWitness;
        }

        internal static bool ShouldSuppressCrime(
            bool enabled, bool missionActive, bool cutsceneActive,
            int wantedLevel, bool isShooting, bool weaponIsSilenced,
            bool hasCredibleWitness)
        {
            return enabled && !missionActive && !cutsceneActive &&
                wantedLevel == 0 && isShooting && weaponIsSilenced &&
                !hasCredibleWitness;
        }

        internal static float DistanceToSegment(
            SuppressorPoint point, SuppressorPoint start,
            SuppressorPoint end)
        {
            float segmentX = end.X - start.X;
            float segmentY = end.Y - start.Y;
            float segmentZ = end.Z - start.Z;
            float lengthSquared = segmentX * segmentX +
                segmentY * segmentY + segmentZ * segmentZ;
            if (lengthSquared <= 0.000001f)
                return Distance(point, start);
            float projection = ((point.X - start.X) * segmentX +
                (point.Y - start.Y) * segmentY +
                (point.Z - start.Z) * segmentZ) / lengthSquared;
            projection = Math.Max(0f, Math.Min(1f, projection));
            return Distance(point, new SuppressorPoint(
                start.X + segmentX * projection,
                start.Y + segmentY * projection,
                start.Z + segmentZ * projection));
        }

        internal static bool IsKnownSuppressorHash(uint componentHash)
        {
            switch (componentHash)
            {
                case 0x837445AA: // COMPONENT_AT_AR_SUPP
                case 0xA73D4664: // COMPONENT_AT_AR_SUPP_02
                case 0xC304849A: // COMPONENT_AT_PI_SUPP
                case 0x65EA7EBB: // COMPONENT_AT_PI_SUPP_02
                case 0xE608B35E: // COMPONENT_AT_SR_SUPP
                case 0xAC42DF71: // COMPONENT_AT_SR_SUPP_03
                case 0x9307D6FA: // COMPONENT_CERAMICPISTOL_SUPP
                case 0x1E02B7E0: // COMPONENT_WM29_PISTOL_SUPP
                    return true;
                default:
                    return false;
            }
        }

        private static float Distance(
            SuppressorPoint left, SuppressorPoint right)
        {
            float x = left.X - right.X;
            float y = left.Y - right.Y;
            float z = left.Z - right.Z;
            return (float)Math.Sqrt(x * x + y * y + z * z);
        }
    }

    public sealed class RealisticSuppressorController : Script,
        IStorySaveParticipant, IWeaponComponentLifecycleParticipant
    {
        private const string PackageId = "realistic-suppressors";
        private const float ShooterScanRadius = 75f;
        private const int WitnessRefreshMs = 125;
        private const int LineOfSightTraceFlags = 17;
        private const int PostShotCrimeLeaseMs = 180;
        private const int PersistenceIntervalMs = 2000;
        private const int WitnessWorldCacheMs = 100;

        // Values are CrimeType indices. SHVDN 3.6 exposes the native but not
        // the later named CrimeType enum.
        private static readonly int[] PreArmFirearmCrimes =
        {
            28, // FirearmDischarge
        };

        private static readonly int[] PostShotFirearmCrimes =
        {
            13, // ShootPed
            14, // ShootCop
            28, // FirearmDischarge
            31, // ShootNonLethalPed
            32, // ShootNonLethalCop
            33, // KillCop
            34, // ShootAtCop
            40, // KillPed
            46, // ShootPedSuppressed
        };

        private static readonly int MichaelHash =
            Game.GenerateHash("player_zero");
        private static readonly int FranklinHash =
            Game.GenerateHash("player_one");
        private static readonly int TrevorHash =
            Game.GenerateHash("player_two");

        private sealed class ThermalRuntimeState
        {
            internal ThermalRuntimeState(
                SuppressorThermalProfile profile, float durability,
                int now)
            {
                Profile = profile;
                TemperatureCelsius =
                    SuppressorThermalPolicy.AmbientCelsius;
                Durability = durability;
                LastPersistedDurability = durability;
                LastTemperatureAt = now;
                LastPersistedAt = now;
                Stage = SuppressorHeatStage.Normal;
                Broken = durability <= 0f;
                ConditionRecorded = Broken;
            }

            internal SuppressorThermalProfile Profile { get; }
            internal float TemperatureCelsius { get; set; }
            internal float Durability { get; set; }
            internal float LastPersistedDurability { get; set; }
            internal int LastTemperatureAt { get; set; }
            internal int LastPersistedAt { get; set; }
            internal SuppressorHeatStage Stage { get; set; }
            internal SuppressorHeatStage HighestNotifiedStage { get; set; }
            internal bool Dirty { get; set; }
            internal bool Broken { get; set; }
            internal bool BreakNotified { get; set; }
            internal bool ConditionRecorded { get; set; }
            internal bool ObservedAbsentAfterBreak { get; set; }
            internal int LastBreakRemovalAttemptAt { get; set; } =
                int.MinValue / 2;
        }

        private readonly bool _runtimeEnabled;
        private readonly bool _stealthEnabled;
        private readonly bool _breakageEnabled;
        private readonly float _durabilityScale;
        private readonly SuppressorStateStore _stateStore;
        private readonly IDisposable _saveRegistration;
        private readonly IDisposable _componentRegistration;
        private readonly Dictionary<uint, ThermalRuntimeState>
            _thermalStates =
                new Dictionary<uint, ThermalRuntimeState>();
        private readonly HashSet<uint> _unprofiledWeaponsLogged =
            new HashSet<uint>();
        private readonly HashSet<uint> _purchaseNotifications =
            new HashSet<uint>();

        private ThermalRuntimeState _activeThermalState;
        private int _characterModelHash;
        private int _stateStoreGeneration;
        private bool _breakageActiveForCurrentCharacter;
        private bool _unsupportedCharacterLogged;
        private bool _replacementBaselinesHydrated;
        private bool _wasShooting;
        private bool _lastShotHadWitness;
        private bool _lastPotentialWitness;
        private int _lastWeaponHash;
        private int _lastAmmoInClip = -1;
        private int _burstRounds;
        private int _lastShotAt = int.MinValue / 2;
        private int _lastWitnessSampleAt = int.MinValue / 2;
        private int _postShotLeaseStartedAt = int.MinValue / 2;
        private int _postShotLeaseWeaponHash;
        private int _lastPersistenceRetryAt = int.MinValue / 2;
        private float _lastAudibleRadius;
        private string _lastWitnessReason = "none";
        private int _lastCandidateCount;
        private int _cachedWeaponEntity;
        private int _cachedMuzzleBoneIndex = -1;
        private Ped[] _cachedWorldPeds;
        private int _cachedWorldPedsAt = int.MinValue / 2;
        private long _roundsProcessed;
        private long _unwitnessedShots;
        private long _witnessedShots;
        private long _brokenSuppressors;
        private long _exceptions;

        public RealisticSuppressorController()
        {
            _stateStore = new SuppressorStateStore(
                SuppressorStateStore.DefaultPath);
            bool enabled = Allin1ExtensionApi.IsPackageEnabled(PackageId);
            IDisposable saveRegistration = null;
            IDisposable componentRegistration = null;
            if (enabled)
            {
                try
                {
                    saveRegistration = Allin1ExtensionApi
                        .RegisterStorySaveParticipant(
                            PackageId, "suppressor-condition", this);
                    componentRegistration = Allin1ExtensionApi
                        .RegisterWeaponComponentLifecycleParticipant(
                            PackageId, "suppressor-components", this);
                }
                catch (Exception ex)
                {
                    saveRegistration?.Dispose();
                    componentRegistration?.Dispose();
                    enabled = false;
                    ClientLog.Error("SUPPRESSORS",
                        "runtime_authorization_failed", ex);
                }
            }
            _saveRegistration = saveRegistration;
            _componentRegistration = componentRegistration;
            _runtimeEnabled = enabled;
            _stealthEnabled = enabled &&
                Allin1ExtensionApi.GetBooleanSetting(
                    PackageId, "realistic_suppressors", true);
            _breakageEnabled = Allin1ExtensionApi.GetBooleanSetting(
                PackageId, "suppressor_breakage", true);
            _durabilityScale = Clamp(
                (float)Allin1ExtensionApi.GetNumberSetting(
                    PackageId, "suppressor_durability_scale", 1d),
                0.5f, 3f);
            Interval = _runtimeEnabled ? 0 : 1000;
            Tick += OnTick;
            Aborted += OnAborted;

            if (_runtimeEnabled)
            {
                ClientLog.Info("SUPPRESSORS", "configured",
                    new Dictionary<string, object>
                    {
                        { "stealth_enabled", _stealthEnabled },
                        { "breakage_enabled", _breakageEnabled },
                        { "durability_scale", _durabilityScale },
                        { "profiled_weapons",
                            SuppressorThermalProfiles.All.Count },
                    });
            }
        }

        private void OnTick(object sender, EventArgs args)
        {
            if (!_runtimeEnabled) return;
            int now = Game.GameTime;
            try
            {
                bool unsafeGameState = Game.IsLoading || Game.IsPaused ||
                    Game.IsCutsceneActive ||
                    Allin1ExtensionApi.IsGbayMenuActive ||
                    !Game.Player.CanControlCharacter;
                Ped player = Game.Player.Character;
                if (unsafeGameState || player == null || !player.Exists() ||
                    player.IsDead)
                {
                    if (player != null && player.Exists())
                        TryFlushActiveThermalState(now, true);
                    _activeThermalState = null;
                    CancelPostShotLease();
                    ResetShotObservation();
                    ResetMuzzleCache();
                    return;
                }

                DetectCharacterChange(player);
                DetectStateStoreReset();
                HydrateBrokenReplacementBaselines(player, now);

                Weapon weapon = player.Weapons.Current;
                int weaponHash = weapon == null ? 0 : (int)weapon.Hash;
                uint unsignedWeaponHash = unchecked((uint)weaponHash);
                int ammoInClip = ReadAmmoInClip(weapon);
                bool isShooting = player.IsShooting;
                bool weaponChanged = weaponHash != _lastWeaponHash;
                if (weaponChanged)
                    HandleWeaponChange(weaponHash, ammoInClip, now);

                int roundsFired = DetectRoundsFired(
                    ammoInClip, isShooting, weaponChanged);
                // Consume the ammo observation before any later native call
                // can throw, otherwise this delta could be applied twice.
                _lastAmmoInClip = ammoInClip;
                _wasShooting = isShooting;
                UpdateBurst(now, roundsFired);

                bool nativeSilenced = IsCurrentWeaponSilenced(player);
                _breakageActiveForCurrentCharacter =
                    _breakageEnabled &&
                    CurrentCharacter(player).Length > 0;
                if (_breakageEnabled &&
                    !_breakageActiveForCurrentCharacter &&
                    !_unsupportedCharacterLogged)
                {
                    _unsupportedCharacterLogged = true;
                    ClientLog.Warn("SUPPRESSORS",
                        "breakage_unavailable_for_player_model",
                        new Dictionary<string, object>
                        {
                            { "model_hash",
                                unchecked((uint)player.Model.Hash) },
                            { "effect",
                                "heat/glow enabled; destructive wear disabled" },
                        });
                }
                bool knownSuppressorAttached = UpdateThermalSimulation(
                    player, unsignedWeaponHash, roundsFired, now,
                    _breakageActiveForCurrentCharacter,
                    out ThermalRuntimeState thermalState);
                RetryPendingPersistence(player, now);
                bool weaponIsSilenced = knownSuppressorAttached
                    ? thermalState != null && !thermalState.Broken
                    : nativeSilenced;

                if (nativeSilenced && !knownSuppressorAttached &&
                    !SuppressorThermalProfiles.TryGet(
                        unsignedWeaponHash, out _) &&
                    _unprofiledWeaponsLogged.Add(unsignedWeaponHash))
                {
                    ClientLog.Warn("SUPPRESSORS", "unprofiled_weapon",
                        new Dictionary<string, object>
                        {
                            { "weapon_hash", unsignedWeaponHash },
                            { "effect",
                                "attachment heat/wear unavailable" },
                        });
                }

                if (thermalState != null && !thermalState.Broken)
                {
                    UpdateHeatStage(thermalState,
                        _breakageActiveForCurrentCharacter);
                    RenderSuppressorGlow(player, thermalState);
                    MaybePersistThermalState(
                        thermalState, now, false);
                }

                bool indoors = Function.Call<int>(
                    Hash.GET_INTERIOR_FROM_ENTITY, player.Handle) != 0;
                SuppressorWeaponClass weaponClass = thermalState?.Profile
                    .WeaponClass ?? ClassifyWeapon(weapon);
                float audibleRadius = RealisticSuppressorPolicy
                    .AudibleRadius(weaponClass,
                        Math.Max(1, _burstRounds), indoors);
                _lastAudibleRadius = audibleRadius;

                bool stealthEligible = _stealthEnabled &&
                    !Game.IsMissionActive && !Game.IsCutsceneActive &&
                    Game.Player.WantedLevel == 0;
                bool suppressedThisFrame = false;
                if (weaponIsSilenced && roundsFired > 0)
                    _roundsProcessed += roundsFired;

                if (stealthEligible && weaponIsSilenced &&
                    roundsFired > 0)
                {
                    bool cachedPotentialWitness =
                        _lastPotentialWitness &&
                        ElapsedMilliseconds(now,
                            _lastWitnessSampleAt) <=
                        WitnessRefreshMs * 2;
                    string cachedReason = _lastWitnessReason;
                    int cachedCandidates = _lastCandidateCount;
                    bool trajectoryWitness = HasCredibleWitness(
                        player, audibleRadius, true,
                        out _lastWitnessReason,
                        out _lastCandidateCount);
                    _lastShotHadWitness = trajectoryWitness ||
                        cachedPotentialWitness;
                    if (!trajectoryWitness && cachedPotentialWitness)
                    {
                        _lastWitnessReason = cachedReason;
                        _lastCandidateCount = cachedCandidates;
                    }
                    _lastWitnessSampleAt = now;
                    bool suppressCrime = RealisticSuppressorPolicy
                        .ShouldSuppressCrime(
                            _stealthEnabled, Game.IsMissionActive,
                            Game.IsCutsceneActive, Game.Player.WantedLevel,
                            isShooting, weaponIsSilenced,
                            _lastShotHadWitness);
                    if (suppressCrime)
                    {
                        SuppressFirearmCrimes(PostShotFirearmCrimes);
                        StartPostShotLease(now, weaponHash);
                        suppressedThisFrame = true;
                        _unwitnessedShots += roundsFired;
                    }
                    else
                    {
                        CancelPostShotLease();
                        _witnessedShots += roundsFired;
                    }
                    if (ShouldLogShotEvaluation(roundsFired))
                        LogShotEvaluation(
                            thermalState, weaponHash, roundsFired,
                            indoors, suppressCrime);
                }
                else if (!weaponIsSilenced)
                {
                    _lastShotHadWitness = false;
                    _lastPotentialWitness = false;
                    CancelPostShotLease();
                }
                else if (!stealthEligible)
                {
                    _lastShotHadWitness = false;
                    _lastPotentialWitness = false;
                    CancelPostShotLease();
                    if (roundsFired > 0)
                    {
                        _lastWitnessReason = _stealthEnabled
                            ? Game.IsMissionActive
                                ? "mission_active"
                                : Game.Player.WantedLevel != 0
                                    ? "wanted_response_active"
                                    : "cutscene_active"
                            : "stealth_disabled";
                        _lastCandidateCount = 0;
                        if (ShouldLogShotEvaluation(roundsFired))
                            LogShotEvaluation(
                                thermalState, weaponHash, roundsFired,
                                indoors, false);
                    }
                }

                if (stealthEligible && weaponIsSilenced &&
                    (roundsFired == 0 || IsPostShotLeaseActive(
                        now, weaponHash)))
                {
                    RefreshPotentialWitness(
                        player, audibleRadius, now, roundsFired > 0);
                }

                if (stealthEligible && weaponIsSilenced &&
                    roundsFired == 0 &&
                    RealisticSuppressorPolicy.ShouldPreArmCrime(
                        _stealthEnabled, Game.IsMissionActive,
                        Game.IsCutsceneActive, Game.Player.WantedLevel,
                        weaponIsSilenced, _lastPotentialWitness))
                {
                    SuppressFirearmCrimes(PreArmFirearmCrimes);
                }

                if (stealthEligible && !suppressedThisFrame &&
                    weaponIsSilenced &&
                    IsPostShotLeaseActive(now, weaponHash))
                {
                    if (_lastShotHadWitness || _lastPotentialWitness ||
                        Game.Player.WantedLevel != 0)
                    {
                        CancelPostShotLease();
                    }
                    else
                    {
                        SuppressFirearmCrimes(PostShotFirearmCrimes);
                    }
                }

            }
            catch (Exception ex)
            {
                _exceptions++;
                TryFlushActiveThermalState(now, true);
                CancelPostShotLease();
                ClientLog.Error("SUPPRESSORS", "tick_failed", ex);
            }
        }

        private void OnAborted(object sender, EventArgs args)
        {
            if (!_runtimeEnabled) return;
            try
            {
                int now = Game.GameTime;
                foreach (ThermalRuntimeState state in
                    _thermalStates.Values)
                {
                    if (state.Broken)
                        PersistBrokenCondition(state);
                    else
                        MaybePersistThermalState(state, now, true);
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error(
                    "SUPPRESSORS", "abort_persistence_failed", ex);
            }
            finally
            {
                _componentRegistration?.Dispose();
                _saveRegistration?.Dispose();
            }

            ClientLog.Info("SUPPRESSORS", "session_summary",
                new Dictionary<string, object>
                {
                    { "rounds_processed", _roundsProcessed },
                    { "unwitnessed_rounds", _unwitnessedShots },
                    { "witnessed_rounds", _witnessedShots },
                    { "broken_suppressors", _brokenSuppressors },
                    { "breakage_enabled", _breakageEnabled },
                    { "exceptions", _exceptions },
                });
        }

        public void Commit(StorySaveContext context)
        {
            _stateStore.Commit();
            ClientLog.Info("SUPPRESSORS", "condition_committed",
                new Dictionary<string, object>
                {
                    { "reason", context?.Reason ?? "story_save" },
                });
        }

        public void Discard(StorySessionEndContext context)
        {
            _stateStore.Discard();
            ClientLog.Info("SUPPRESSORS", "condition_discarded",
                new Dictionary<string, object>
                {
                    { "reason", context?.Reason ?? "session_end" },
                });
        }

        public bool IsComponentConsumed(
            string weaponName, int componentHash)
        {
            if (!_runtimeEnabled || !_breakageEnabled ||
                !TryGetLifecycleProfile(
                    weaponName, componentHash,
                    out SuppressorThermalProfile profile))
                return false;
            Ped player = Game.Player.Character;
            string character = CurrentCharacter(player);
            return character.Length > 0 &&
                _stateStore.GetDurability(
                    character, profile.WeaponName,
                    profile.ComponentHash) <= 0f;
        }

        public void OnComponentPurchased(
            string weaponName, int componentHash, int attachmentPoint)
        {
            if (!_runtimeEnabled || !_breakageEnabled ||
                !TryGetLifecycleProfile(
                    weaponName, componentHash,
                    out SuppressorThermalProfile profile))
                return;
            Ped player = Game.Player.Character;
            string character = CurrentCharacter(player);
            if (character.Length == 0) return;
            float current = _stateStore.GetDurability(
                character, profile.WeaponName,
                profile.ComponentHash);
            // Re-equipping a worn, usable suppressor must not repair it.
            if (current > 0f) return;
            _stateStore.SetDurability(
                character, profile.WeaponName,
                profile.ComponentHash,
                SuppressorStatePolicy.NewCondition);
            if (_thermalStates.TryGetValue(
                    profile.WeaponHash,
                    out ThermalRuntimeState runtimeState) &&
                runtimeState.Broken)
                _purchaseNotifications.Add(profile.WeaponHash);
            ClientLog.Info("SUPPRESSORS", "storefront_purchase_observed",
                new Dictionary<string, object>
                {
                    { "weapon", profile.WeaponName },
                    { "component_hash", profile.ComponentHash },
                    { "attachment_point", attachmentPoint },
                });
        }


        private void DetectCharacterChange(Ped player)
        {
            int modelHash = player.Model.Hash;
            if (_characterModelHash == 0)
            {
                _characterModelHash = modelHash;
                return;
            }
            if (_characterModelHash == modelHash) return;

            _thermalStates.Clear();
            _purchaseNotifications.Clear();
            _activeThermalState = null;
            _characterModelHash = modelHash;
            _replacementBaselinesHydrated = false;
            _unsupportedCharacterLogged = false;
            ResetShotObservation();
            ResetMuzzleCache();
            CancelPostShotLease();
        }

        private void DetectStateStoreReset()
        {
            int generation = _stateStore.Generation;
            if (generation == _stateStoreGeneration) return;
            _stateStoreGeneration = generation;
            _replacementBaselinesHydrated = false;
            _thermalStates.Clear();
            _purchaseNotifications.Clear();
            _activeThermalState = null;
            ResetShotObservation();
            ResetMuzzleCache();
            CancelPostShotLease();
        }

        private void HydrateBrokenReplacementBaselines(
            Ped player, int now)
        {
            string character = CurrentCharacter(player);
            if (_replacementBaselinesHydrated || !_breakageEnabled ||
                character.Length == 0)
                return;

            int brokenRecords = 0;
            int absentRecords = 0;
            foreach (SuppressorThermalProfile profile in
                SuppressorThermalProfiles.All)
            {
                float persisted = _stateStore.GetDurability(
                    character, profile.WeaponName, profile.ComponentHash);
                if (persisted > 0f) continue;
                brokenRecords++;
                if (!_thermalStates.TryGetValue(
                        profile.WeaponHash,
                        out ThermalRuntimeState state))
                {
                    state = new ThermalRuntimeState(
                        profile, persisted, now);
                    _thermalStates[profile.WeaponHash] = state;
                }
                bool ownsWeapon = Function.Call<bool>(
                    Hash.HAS_PED_GOT_WEAPON, player.Handle,
                    unchecked((int)profile.WeaponHash), false);
                if (!ownsWeapon) continue;
                bool attached = Function.Call<bool>(
                    Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                    player.Handle,
                    unchecked((int)profile.WeaponHash),
                    unchecked((int)profile.ComponentHash));
                if (attached) continue;
                state.ObservedAbsentAfterBreak = true;
                absentRecords++;
            }
            _replacementBaselinesHydrated = true;
            if (brokenRecords > 0)
            {
                ClientLog.Info("SUPPRESSORS",
                    "replacement_baseline_sampled",
                    new Dictionary<string, object>
                    {
                        { "broken_records", brokenRecords },
                        { "verified_absent", absentRecords },
                    });
            }
        }


        private void HandleWeaponChange(
            int weaponHash, int ammoInClip, int now)
        {
            FlushActiveThermalState(now, true);
            _activeThermalState = null;
            _lastWeaponHash = weaponHash;
            _lastAmmoInClip = ammoInClip;
            _burstRounds = 0;
            _lastShotHadWitness = false;
            _lastPotentialWitness = false;
            _lastWitnessReason = "none";
            _lastWitnessSampleAt = int.MinValue / 2;
            _wasShooting = false;
            ResetMuzzleCache();
            CancelPostShotLease();
        }

        private int DetectRoundsFired(
            int ammoInClip, bool isShooting, bool weaponChanged)
        {
            if (!isShooting) return 0;
            if (!weaponChanged && _lastAmmoInClip >= 0 &&
                ammoInClip >= 0 && ammoInClip < _lastAmmoInClip)
                return Math.Min(100, _lastAmmoInClip - ammoInClip);
            return !_wasShooting ? 1 : 0;
        }

        private void UpdateBurst(int now, int roundsFired)
        {
            if (roundsFired > 0)
            {
                _burstRounds = RealisticSuppressorPolicy.UpdateBurstCount(
                    now, _lastShotAt, _burstRounds, roundsFired);
                _lastShotAt = now;
            }
            else if (ElapsedMilliseconds(now, _lastShotAt) >
                RealisticSuppressorPolicy.BurstResetMs)
            {
                _burstRounds = 0;
            }
        }

        private bool UpdateThermalSimulation(
            Ped player, uint weaponHash, int roundsFired, int now,
            bool breakageActive,
            out ThermalRuntimeState state)
        {
            state = null;
            if (!SuppressorThermalProfiles.TryGet(
                    weaponHash, out SuppressorThermalProfile profile))
            {
                FlushActiveThermalState(now, true);
                _activeThermalState = null;
                return false;
            }

            bool attached = Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON_COMPONENT, player.Handle,
                unchecked((int)profile.WeaponHash),
                unchecked((int)profile.ComponentHash));
            if (!_thermalStates.TryGetValue(weaponHash, out state))
            {
                float persisted = _breakageEnabled
                    ? _stateStore.GetDurability(
                        CurrentCharacter(player), profile.WeaponName,
                        profile.ComponentHash)
                    : SuppressorStatePolicy.NewCondition;
                state = new ThermalRuntimeState(
                    profile, persisted, now);
                _thermalStates[weaponHash] = state;
            }
            if (!attached)
            {
                FlushActiveThermalState(now, true);
                if (state.Broken || state.Durability <= 0f)
                {
                    // A verified absent sample arms the source-agnostic
                    // replacement transition. A broken tombstone by itself
                    // is not purchase evidence because GTA may restore a
                    // stale native component after a reload.
                    state.ObservedAbsentAfterBreak = true;
                }
                _activeThermalState = null;
                return false;
            }
            bool replacementObserved = state.Broken &&
                ReconcileReplacement(player, state, now);

            _activeThermalState = state;
            int elapsed = ElapsedMilliseconds(
                now, state.LastTemperatureAt);
            state.TemperatureCelsius = SuppressorThermalPolicy
                .CoolTemperature(state.TemperatureCelsius, elapsed,
                    profile.CoolingHalfLifeSeconds);
            state.LastTemperatureAt = now;

            if (state.Broken || state.Durability <= 0f)
            {
                state.Broken = true;
                if (!replacementObserved && ElapsedMilliseconds(now,
                        state.LastBreakRemovalAttemptAt) >=
                    PersistenceIntervalMs)
                    EnsureBrokenSuppressorRemoved(
                        player, state, false, now);
                return true;
            }

            if (roundsFired > 0)
            {
                SuppressorThermalStep result = SuppressorThermalPolicy
                    .ApplyShots(profile, state.TemperatureCelsius,
                        state.Durability, roundsFired,
                        breakageActive, _durabilityScale);
                state.TemperatureCelsius = result.TemperatureCelsius;
                state.Durability = result.Durability;
                state.Dirty |= result.DurabilityLost > 0f;
                if (result.Broke)
                {
                    state.Broken = true;
                    EnsureBrokenSuppressorRemoved(
                        player, state, true, now);
                }
            }

            return true;
        }

        private bool ReconcileReplacement(
            Ped player, ThermalRuntimeState state, int now)
        {
            string character = CurrentCharacter(player);
            if (character.Length == 0) return false;
            float persisted = _stateStore.GetDurability(
                character, state.Profile.WeaponName,
                state.Profile.ComponentHash);
            bool purchaseObserved = _purchaseNotifications.Remove(
                state.Profile.WeaponHash);
            bool replacement = SuppressorStatePolicy
                .IsReplacementAttachment(
                    state.Broken, persisted, purchaseObserved,
                    state.ObservedAbsentAfterBreak);
            if (!replacement) return false;

            string source = purchaseObserved
                ? "gbay_purchase" : "live_component_attachment";
            if (persisted <= 0f)
            {
                _stateStore.SetDurability(
                    character, state.Profile.WeaponName,
                    state.Profile.ComponentHash,
                    SuppressorStatePolicy.NewCondition);
                persisted = _stateStore.GetDurability(
                    character, state.Profile.WeaponName,
                    state.Profile.ComponentHash);
                if (persisted <= 0f) return true;
            }

            state.Broken = false;
            state.BreakNotified = false;
            state.ConditionRecorded = false;
            state.ObservedAbsentAfterBreak = false;
            state.LastBreakRemovalAttemptAt = int.MinValue / 2;
            state.Durability = persisted;
            state.LastPersistedDurability = persisted;
            state.TemperatureCelsius =
                SuppressorThermalPolicy.AmbientCelsius;
            state.LastTemperatureAt = now;
            state.LastPersistedAt = now;
            state.Stage = SuppressorHeatStage.Normal;
            state.HighestNotifiedStage = SuppressorHeatStage.Normal;
            state.Dirty = false;
            ClientLog.Info("SUPPRESSORS", "replacement_registered",
                new Dictionary<string, object>
                {
                    { "weapon", state.Profile.WeaponName },
                    { "component_hash", state.Profile.ComponentHash },
                    { "source", source },
                    { "durability", persisted },
                });
            return true;
        }


        private bool PersistBrokenCondition(
            ThermalRuntimeState state)
        {
            if (state.ConditionRecorded) return true;
            Ped player = Game.Player.Character;
            string character = CurrentCharacter(player);
            if (character.Length == 0) return false;
            SuppressorThermalProfile profile = state.Profile;
            _stateStore.SetDurability(
                character, profile.WeaponName,
                profile.ComponentHash, 0f);
            bool confirmed = _stateStore.GetDurability(
                character, profile.WeaponName,
                profile.ComponentHash) <= 0f;
            state.ConditionRecorded = confirmed;
            return confirmed;
        }

        private void RetryPendingPersistence(Ped player, int now)
        {
            if (ElapsedMilliseconds(now,
                    _lastPersistenceRetryAt) <
                PersistenceIntervalMs)
                return;
            _lastPersistenceRetryAt = now;
            foreach (ThermalRuntimeState state in _thermalStates.Values)
            {
                if (state.Broken && !state.ConditionRecorded)
                    PersistBrokenCondition(state);
                else if (state.Dirty)
                    MaybePersistThermalState(state, now, false);
            }
        }


        private void EnsureBrokenSuppressorRemoved(
            Ped player, ThermalRuntimeState state, bool notify, int now)
        {
            state.LastBreakRemovalAttemptAt = now;
            SuppressorThermalProfile profile = state.Profile;
            bool conditionRecorded = PersistBrokenCondition(state);
            Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED,
                player.Handle, unchecked((int)profile.WeaponHash),
                unchecked((int)profile.ComponentHash));

            bool removed = !Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON_COMPONENT, player.Handle,
                unchecked((int)profile.WeaponHash),
                unchecked((int)profile.ComponentHash));
            if (!removed)
                DeactivateCurrentSuppressorComponent(
                    player, profile.ComponentHash);
            removed = !Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON_COMPONENT, player.Handle,
                unchecked((int)profile.WeaponHash),
                unchecked((int)profile.ComponentHash));

            state.Durability = 0f;
            state.LastPersistedDurability = 0f;
            state.Dirty = false;
            state.Broken = true;
            state.ObservedAbsentAfterBreak |= removed;
            state.TemperatureCelsius = Math.Min(
                state.TemperatureCelsius,
                SuppressorThermalPolicy.MaximumTrackedCelsius);

            if (notify && !state.BreakNotified)
            {
                state.BreakNotified = true;
                _brokenSuppressors++;
                GTA.UI.Notification.Show(
                    "~r~Suppressor failed~w~ on " +
                    DisplayWeaponName(profile.WeaponName) +
                    ". Replace it at Ammu-Nation or a compatible weapon shop.");
                ClientLog.Warn("SUPPRESSORS", "component_broken",
                    new Dictionary<string, object>
                    {
                        { "weapon", profile.WeaponName },
                        { "weapon_hash", profile.WeaponHash },
                        { "component_hash", profile.ComponentHash },
                        { "temperature_c",
                            state.TemperatureCelsius },
                        { "condition_recorded", conditionRecorded },
                        { "native_removed", removed },
                    });
            }
        }

        private static void DeactivateCurrentSuppressorComponent(
            Ped player, uint componentHash)
        {
            Weapon weapon = player.Weapons.Current;
            if (weapon == null) return;
            WeaponComponentCollection components = weapon.Components;
            int count = components.SuppressorAndMuzzleBrakeVariationsCount;
            for (int index = 0; index < count; index++)
            {
                WeaponComponent component = components
                    .GetSuppressorOrMuzzleBrakeComponent(index);
                if (component == null ||
                    unchecked((uint)component.ComponentHash) !=
                        componentHash)
                    continue;
                component.Active = false;
                return;
            }
        }


        private void MaybePersistThermalState(
            ThermalRuntimeState state, int now, bool force)
        {
            if (!_breakageEnabled || state == null || state.Broken ||
                !state.Dirty)
                return;
            if (!force && ElapsedMilliseconds(
                    now, state.LastPersistedAt) <
                PersistenceIntervalMs)
                return;

            Ped player = Game.Player.Character;
            string character = CurrentCharacter(player);
            bool persisted = character.Length > 0;
            if (persisted)
            {
                _stateStore.SetDurability(
                    character, state.Profile.WeaponName,
                    state.Profile.ComponentHash, state.Durability);
                persisted = Math.Abs(_stateStore.GetDurability(
                    character, state.Profile.WeaponName,
                    state.Profile.ComponentHash) - state.Durability) <=
                    0.000001f;
            }
            state.LastPersistedAt = now;
            if (persisted)
            {
                state.LastPersistedDurability = state.Durability;
                state.Dirty = false;
            }
        }

        private void FlushActiveThermalState(int now, bool force)
        {
            if (_activeThermalState == null) return;
            MaybePersistThermalState(_activeThermalState, now, force);
        }

        private void TryFlushActiveThermalState(int now, bool force)
        {
            try
            {
                FlushActiveThermalState(now, force);
            }
            catch (Exception ex)
            {
                ClientLog.Error(
                    "SUPPRESSORS", "durability_flush_failed", ex);
            }
        }

        private void UpdateHeatStage(
            ThermalRuntimeState state, bool breakageActive)
        {
            SuppressorHeatStage next = SuppressorThermalPolicy.HeatStage(
                state.Profile, state.TemperatureCelsius);
            state.Stage = next;
            if ((int)next <= (int)state.HighestNotifiedStage)
                return;
            state.HighestNotifiedStage = next;

            string message = null;
            if (next == SuppressorHeatStage.Damaging)
                message = "~o~Suppressor hot~w~ — pause fire to cool it.";
            else if (next == SuppressorHeatStage.Glowing)
                message = breakageActive
                    ? "~o~Suppressor glowing~w~ — sustained fire is accelerating wear."
                    : _breakageEnabled
                        ? "~o~Suppressor glowing~w~ — wear is unavailable for this player model."
                        : "~o~Suppressor glowing~w~ — breakage is disabled.";
            else if (next == SuppressorHeatStage.Critical)
                message = breakageActive
                    ? "~r~Suppressor critical~w~ — wear is extreme."
                    : _breakageEnabled
                        ? "~r~Suppressor critical~w~ — wear is unavailable for this player model."
                        : "~r~Suppressor critical~w~ — breakage is disabled.";
            if (message == null) return;
            GTA.UI.Notification.Show(message);
        }

        private void RenderSuppressorGlow(
            Ped player, ThermalRuntimeState state)
        {
            if (state.TemperatureCelsius <
                SuppressorThermalPolicy.GlowOnsetCelsius)
                return;
            if (!TryGetMuzzlePosition(player, out Vector3 position))
                return;

            float intensity = Math.Max(0.08f,
                SuppressorThermalPolicy.GlowIntensity(
                    state.Profile, state.TemperatureCelsius));
            int alpha = (int)(75f + 150f * intensity);
            int green = (int)(135f - 75f * intensity);
            Color color = Color.FromArgb(alpha, 255, green, 12);
            float size = 0.020f + 0.035f * intensity;
            float range = 0.30f + 0.55f * intensity;
            World.DrawMarker(MarkerType.DebugSphere, position,
                Vector3.Zero, Vector3.Zero,
                new Vector3(size, size, size), color);
            World.DrawLightWithRange(
                position, color, range, 0.20f + 0.80f * intensity);
        }

        private bool TryGetMuzzlePosition(
            Ped player, out Vector3 position)
        {
            position = Vector3.Zero;
            int weaponEntity = Function.Call<int>(
                Hash.GET_CURRENT_PED_WEAPON_ENTITY_INDEX,
                player.Handle, 0);
            if (weaponEntity != _cachedWeaponEntity)
            {
                _cachedWeaponEntity = weaponEntity;
                _cachedMuzzleBoneIndex = -1;
                if (weaponEntity != 0 && Function.Call<bool>(
                        Hash.DOES_ENTITY_EXIST, weaponEntity))
                    _cachedMuzzleBoneIndex = Function.Call<int>(
                        Hash.GET_ENTITY_BONE_INDEX_BY_NAME,
                        weaponEntity, "gun_muzzle");
            }

            if (_cachedWeaponEntity != 0 &&
                _cachedMuzzleBoneIndex >= 0 && Function.Call<bool>(
                    Hash.DOES_ENTITY_EXIST, _cachedWeaponEntity))
            {
                position = Function.Call<Vector3>(
                    Hash.GET_WORLD_POSITION_OF_ENTITY_BONE,
                    _cachedWeaponEntity, _cachedMuzzleBoneIndex);
            }

            if (!HasPosition(position))
            {
                position = Function.Call<Vector3>(
                    Hash.GET_PED_BONE_COORDS, player.Handle,
                    57005, 0f, 0f, 0f) +
                    player.ForwardVector * 0.48f;
            }
            return HasPosition(position);
        }

        private void RefreshPotentialWitness(
            Ped player, float audibleRadius, int now, bool force)
        {
            if (!force && ElapsedMilliseconds(
                    now, _lastWitnessSampleAt) < WitnessRefreshMs)
                return;
            _lastPotentialWitness = HasCredibleWitness(
                player, audibleRadius, false,
                out string reason, out int candidates);
            _lastWitnessSampleAt = now;
            if (_lastPotentialWitness)
            {
                _lastWitnessReason = reason;
                _lastCandidateCount = candidates;
            }
        }

        private bool HasCredibleWitness(
            Ped player, float audibleRadius, bool includeTrajectory,
            out string reason, out int candidateCount)
        {
            Vector3 origin = player.Position +
                new Vector3(0f, 0f, 0.7f);
            Vector3 impact = includeTrajectory
                ? player.LastWeaponImpactPosition
                : Vector3.Zero;
            bool hasImpact = IsCredibleImpact(origin, impact);
            Ped[] candidates = includeTrajectory
                ? GetCachedWorldPeds()
                : World.GetNearbyPeds(player, ShooterScanRadius);
            candidateCount = 0;
            if (candidates == null)
            {
                reason = "none";
                return false;
            }

            foreach (Ped candidate in candidates)
            {
                if (!IsEligibleWitness(candidate, player)) continue;
                Vector3 candidatePosition = candidate.Position;
                float shooterDistance =
                    candidatePosition.DistanceTo(origin);
                float projectileDistance = hasImpact
                    ? RealisticSuppressorPolicy.DistanceToSegment(
                        ToPoint(candidatePosition), ToPoint(origin),
                        ToPoint(impact))
                    : float.PositiveInfinity;
                float impactDistance = hasImpact
                    ? candidatePosition.DistanceTo(impact)
                    : float.PositiveInfinity;
                bool relevant = shooterDistance <= ShooterScanRadius ||
                    projectileDistance <=
                        RealisticSuppressorPolicy.BulletCrackRadius ||
                    impactDistance <=
                        RealisticSuppressorPolicy.ImpactCueRadius;
                if (!relevant) continue;
                candidateCount++;

                int alertThreshold = includeTrajectory ? 1 : 2;
                bool alreadyAlerted =
                    candidate.IsInCombatAgainst(player) ||
                    Function.Call<bool>(Hash.IS_PED_FLEEING,
                        candidate.Handle) ||
                    Function.Call<int>(Hash.GET_PED_ALERTNESS,
                        candidate.Handle) >= alertThreshold;
                bool canHearPlayer = false;
                if (shooterDistance <= audibleRadius &&
                    shooterDistance >
                        RealisticSuppressorPolicy.CloseAudibleRadius)
                {
                    // Before a shot exists, conservatively treat everyone in
                    // the modeled report radius as a potential hearer. After
                    // the shot, GTA's live hearing result can narrow it.
                    canHearPlayer = !includeTrajectory ||
                        Function.Call<bool>(Hash.CAN_PED_HEAR_PLAYER,
                            Game.Player.Handle, candidate.Handle);
                }

                bool clearLineOfSight = false;
                bool facingShooter = false;
                if (shooterDistance <= RealisticSuppressorPolicy
                        .VisualIdentificationRadius)
                {
                    clearLineOfSight = Function.Call<bool>(
                        Hash.HAS_ENTITY_CLEAR_LOS_TO_ENTITY,
                        candidate.Handle, player.Handle,
                        LineOfSightTraceFlags);
                    if (clearLineOfSight)
                        facingShooter = IsFacingShooter(
                            candidate, player.Position);
                }

                SuppressorWitnessReason witness =
                    RealisticSuppressorPolicy.CredibleWitnessReason(
                        shooterDistance, projectileDistance,
                        impactDistance, audibleRadius, alreadyAlerted,
                        canHearPlayer, clearLineOfSight, facingShooter);
                if (witness == SuppressorWitnessReason.None) continue;
                reason = WitnessReasonName(witness);
                return true;
            }

            reason = "none";
            return false;
        }

        private Ped[] GetCachedWorldPeds()
        {
            int now = Game.GameTime;
            if (_cachedWorldPeds == null || ElapsedMilliseconds(
                    now, _cachedWorldPedsAt) >= WitnessWorldCacheMs)
            {
                _cachedWorldPeds = World.GetAllPeds();
                _cachedWorldPedsAt = now;
            }
            return _cachedWorldPeds;
        }

        private static bool IsEligibleWitness(Ped candidate, Ped player)
        {
            return candidate != null && candidate.Exists() &&
                candidate.Handle != player.Handle && !candidate.IsPlayer &&
                candidate.IsHuman && !candidate.IsDead;
        }

        private static bool IsFacingShooter(
            Ped candidate, Vector3 shooterPosition)
        {
            Vector3 towardShooter = shooterPosition - candidate.Position;
            float lengthSquared = towardShooter.X * towardShooter.X +
                towardShooter.Y * towardShooter.Y +
                towardShooter.Z * towardShooter.Z;
            if (lengthSquared <= 0.000001f) return true;
            Vector3 forward = candidate.ForwardVector;
            float dot = forward.X * towardShooter.X +
                forward.Y * towardShooter.Y +
                forward.Z * towardShooter.Z;
            return dot / (float)Math.Sqrt(lengthSquared) >= 0f;
        }

        private static bool IsCurrentWeaponSilenced(Ped player)
        {
            if (Function.Call<bool>(
                    Hash.IS_PED_CURRENT_WEAPON_SILENCED,
                    player.Handle))
                return true;

            Weapon weapon = player.Weapons.Current;
            if (weapon == null) return false;
            WeaponComponentCollection components = weapon.Components;
            int count = components.SuppressorAndMuzzleBrakeVariationsCount;
            for (int index = 0; index < count; index++)
            {
                WeaponComponent component = components
                    .GetSuppressorOrMuzzleBrakeComponent(index);
                if (component != null && component.Active &&
                    RealisticSuppressorPolicy.IsKnownSuppressorHash(
                        unchecked((uint)component.ComponentHash)))
                    return true;
            }
            return false;
        }

        private static string CurrentCharacter(Ped player)
        {
            try
            {
                if (player == null || !player.Exists()) return "";
                int modelHash = player.Model.Hash;
                if (modelHash == MichaelHash) return "michael";
                if (modelHash == FranklinHash) return "franklin";
                if (modelHash == TrevorHash) return "trevor";
            }
            catch (Exception)
            {
                // Transient player/model access is expected during reloads.
            }
            return "";
        }

        private static bool TryGetLifecycleProfile(
            string weaponName, int componentHash,
            out SuppressorThermalProfile profile)
        {
            profile = null;
            if (string.IsNullOrWhiteSpace(weaponName) ||
                componentHash == 0)
                return false;
            uint unsignedComponentHash = unchecked((uint)componentHash);
            foreach (SuppressorThermalProfile candidate in
                SuppressorThermalProfiles.All)
            {
                if (candidate.ComponentHash == unsignedComponentHash &&
                    string.Equals(candidate.WeaponName,
                        weaponName.Trim(),
                        StringComparison.OrdinalIgnoreCase))
                {
                    profile = candidate;
                    return true;
                }
            }
            return false;
        }

        private static SuppressorWeaponClass ClassifyWeapon(Weapon weapon)
        {
            if (weapon == null) return SuppressorWeaponClass.Other;
            switch (weapon.Group)
            {
                case WeaponGroup.Pistol:
                    return SuppressorWeaponClass.Sidearm;
                case WeaponGroup.SMG:
                    return SuppressorWeaponClass.SubmachineGun;
                case WeaponGroup.AssaultRifle:
                case WeaponGroup.MG:
                    return SuppressorWeaponClass.Rifle;
                case WeaponGroup.Shotgun:
                    return SuppressorWeaponClass.Shotgun;
                case WeaponGroup.Sniper:
                    return SuppressorWeaponClass.Sniper;
                default:
                    return SuppressorWeaponClass.Other;
            }
        }

        private static void SuppressFirearmCrimes(int[] crimeTypes)
        {
            foreach (int crimeType in crimeTypes)
                Function.Call(Hash.SUPPRESS_CRIME_THIS_FRAME,
                    Game.Player.Handle, crimeType);
        }

        private void StartPostShotLease(int now, int weaponHash)
        {
            _postShotLeaseStartedAt = now;
            _postShotLeaseWeaponHash = weaponHash;
        }

        private bool IsPostShotLeaseActive(int now, int weaponHash)
        {
            return _postShotLeaseWeaponHash == weaponHash &&
                ElapsedMilliseconds(now, _postShotLeaseStartedAt) <=
                    PostShotCrimeLeaseMs;
        }

        private void CancelPostShotLease()
        {
            _postShotLeaseStartedAt = int.MinValue / 2;
            _postShotLeaseWeaponHash = 0;
        }

        private void ResetShotObservation()
        {
            _wasShooting = false;
            _lastWeaponHash = 0;
            _lastAmmoInClip = -1;
            _burstRounds = 0;
            _lastShotHadWitness = false;
            _lastPotentialWitness = false;
            _lastWitnessReason = "none";
            _lastWitnessSampleAt = int.MinValue / 2;
            _cachedWorldPeds = null;
            _cachedWorldPedsAt = int.MinValue / 2;
        }

        private void ResetMuzzleCache()
        {
            _cachedWeaponEntity = 0;
            _cachedMuzzleBoneIndex = -1;
        }

        private void LogShotEvaluation(
            ThermalRuntimeState thermalState, int weaponHash,
            int roundsFired, bool indoors, bool crimeSuppressed)
        {
            var data = new Dictionary<string, object>
            {
                { "weapon_hash", unchecked((uint)weaponHash) },
                { "rounds_fired", roundsFired },
                { "burst_rounds", _burstRounds },
                { "indoors", indoors },
                { "audible_radius_m", _lastAudibleRadius },
                { "candidate_count", _lastCandidateCount },
                { "witness_reason", _lastWitnessReason },
                { "crime_suppressed", crimeSuppressed },
                { "breakage_enabled", _breakageEnabled },
                { "breakage_active",
                    _breakageActiveForCurrentCharacter },
            };
            if (thermalState != null)
            {
                data["temperature_c"] =
                    thermalState.TemperatureCelsius;
                data["durability"] = thermalState.Durability;
                data["heat_stage"] = thermalState.Stage.ToString();
                data["profile"] = thermalState.Profile.ProfileCode;
            }
            ClientLog.Info("SUPPRESSORS", "shot_evaluated", data);
        }

        private bool ShouldLogShotEvaluation(int roundsFired)
        {
            return roundsFired > 0 &&
                (_burstRounds == Math.Min(12, roundsFired) ||
                    _burstRounds == 10);
        }

        private static int ReadAmmoInClip(Weapon weapon)
        {
            if (weapon == null) return -1;
            try
            {
                return weapon.AmmoInClip;
            }
            catch (Exception)
            {
                return -1;
            }
        }

        private static bool IsCredibleImpact(
            Vector3 origin, Vector3 impact)
        {
            if (!HasPosition(impact)) return false;
            float distance = origin.DistanceTo(impact);
            return distance >= 0.10f && distance <= 2500f;
        }

        private static bool HasPosition(Vector3 position)
        {
            return Math.Abs(position.X) > 0.001f ||
                Math.Abs(position.Y) > 0.001f ||
                Math.Abs(position.Z) > 0.001f;
        }

        private static SuppressorPoint ToPoint(Vector3 position)
        {
            return new SuppressorPoint(
                position.X, position.Y, position.Z);
        }

        private static int ElapsedMilliseconds(int now, int then)
        {
            int elapsed = unchecked(now - then);
            return elapsed < 0 ? int.MaxValue : elapsed;
        }

        private static float Clamp(float value, float minimum, float maximum)
        {
            if (float.IsNaN(value) || float.IsInfinity(value))
                return 1f;
            return Math.Max(minimum, Math.Min(maximum, value));
        }

        private static string DisplayWeaponName(string weaponName)
        {
            if (string.IsNullOrWhiteSpace(weaponName)) return "weapon";
            string value = weaponName.StartsWith("WEAPON_",
                StringComparison.OrdinalIgnoreCase)
                ? weaponName.Substring(7) : weaponName;
            return value.Replace('_', ' ').ToLowerInvariant();
        }

        private static string WitnessReasonName(
            SuppressorWitnessReason reason)
        {
            switch (reason)
            {
                case SuppressorWitnessReason.AlreadyAlerted:
                    return "already_alerted";
                case SuppressorWitnessReason.BulletCrackOrImpact:
                    return "bullet_crack_or_impact";
                case SuppressorWitnessReason.AudibleMuzzle:
                    return "audible_muzzle";
                case SuppressorWitnessReason.VisualIdentification:
                    return "visual_identification";
                default:
                    return "none";
            }
        }
    }
}
