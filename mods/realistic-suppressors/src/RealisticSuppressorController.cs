// RealisticSuppressorController.cs -- suppressors provide a believable
// stealth benefit, accumulate heat and wear, glow when incandescent, and can
// fail permanently when the optional breakage simulation is enabled.

using System;
using System.Collections.Generic;
using System.Globalization;
#if ALLIN1_HOST
using ALLIN1;
#endif
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

    public sealed class RealisticSuppressorController : Script
#if ALLIN1_HOST
        ,
        IStorySaveParticipant, IWeaponComponentLifecycleParticipant
#endif
    {
        private const string PackageId = "realistic-suppressors";
        private const float ShooterScanRadius = 75f;
        private const int WitnessRefreshMs = 125;
        private const int LineOfSightTraceFlags = 17;
        private const int PostShotCrimeLeaseMs = 180;
        private const int PersistenceIntervalMs = 2000;
        private const int WitnessWorldCacheMs = 100;
        private const int ActivationRetryMs = 5000;
        private const string BreakParticleAsset = "core";
        private const string BreakParticleEffect =
            "bul_carmetal";
        private const string BreakSoundName = "Drill_Pin_Break";
        private const string BreakSoundSet =
            "DLC_HEIST_FLEECA_SOUNDSET";
        private const float BreakParticleScale = 0.30f;
        private const string SmokeParticleAsset = "core";
        private const string SmokeParticleEffect =
            "muz_smoking_barrel";
        private const int SmokeStartRetryMs = 750;
        private const int SmokeVisualUpdateMs = 125;

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
            internal bool Dirty { get; set; }
            internal bool Broken { get; set; }
            internal bool BreakEventLogged { get; set; }
            internal bool ConditionRecorded { get; set; }
            internal bool ObservedAbsentAfterBreak { get; set; }
            internal bool GlowStartedLogged { get; set; }
            internal int LastBreakRemovalAttemptAt { get; set; } =
                int.MinValue / 2;
        }

        private bool _runtimeEnabled;
        private bool _stealthEnabled;
        private bool _breakageEnabled;
        private bool _temperatureDebugEnabled;
        private bool _heatSmokeEnabled;
        private float _durabilityScale = 1f;
        private float _heatSmokeIntensityScale = 1f;
        private readonly SuppressorStateStore _stateStore;
#if ALLIN1_HOST
        private IDisposable _saveRegistration;
        private IDisposable _componentRegistration;
#endif
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
        private int _lastActivationAttemptAt = int.MinValue / 2;
#if ALLIN1_HOST
        private bool _activationFailureLogged;
#endif
        private float _lastAudibleRadius;
        private string _lastWitnessReason = "none";
        private int _lastCandidateCount;
        private int _cachedWeaponEntity;
        private int _cachedSuppressorBoneIndex = -1;
        private string _cachedSuppressorBoneName = "none";
        private uint _cachedSuppressorComponentHash;
        private Prop _heatOverlay;
        private int _heatOverlayWeaponEntity;
        private int _heatOverlayBoneIndex = -1;
        private string _heatOverlayBaseModelName = "none";
        private string _heatOverlayModelName = "none";
        private int _heatOverlayMaterialLevel;
        private float _heatOverlaySmoothedOpacity;
        private int _heatOverlayLastFadeAt = int.MinValue / 2;
        private int _primaryHeatSmokeHandle;
        private int _secondaryHeatSmokeHandle;
        private int _heatSmokeWeaponEntity;
        private int _heatSmokeBoneIndex = -1;
        private uint _heatSmokeComponentHash;
        private int _lastHeatSmokeStartAttemptAt = int.MinValue / 2;
        private int _lastSecondarySmokeStartAttemptAt = int.MinValue / 2;
        private int _lastHeatSmokeVisualUpdateAt = int.MinValue / 2;
        private bool _heatSmokeRuntimeFailed;
        private bool _heatSmokeCleanupFailureLogged;
        private readonly HashSet<string> _unavailableHeatOverlayModelsLogged =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private bool _breakParticleAssetRequested;
        private bool _breakParticleAssetReady;
        private bool _breakParticleAssetFailureLogged;
        private Ped[] _cachedWorldPeds;
        private int _cachedWorldPedsAt = int.MinValue / 2;
        private long _roundsProcessed;
        private long _unwitnessedShots;
        private long _witnessedShots;
        private long _brokenSuppressors;
        private long _breakEffectsStarted;
        private long _heatSmokeEffectsStarted;
        private long _exceptions;

        public RealisticSuppressorController()
        {
            _stateStore = new SuppressorStateStore(
                SuppressorStateStore.DefaultPath);
            TryActivateRuntime(false);
            Interval = _runtimeEnabled ? 0 : 1000;
            Tick += OnTick;
            Aborted += OnAborted;
        }

        private bool TryActivateRuntime(bool recoveredAtRuntime)
        {
            _lastActivationAttemptAt = Game.GameTime;
#if ALLIN1_HOST
            bool enabled;
            try
            {
                enabled = Allin1ExtensionApi.IsPackageEnabled(PackageId);
            }
            catch (Exception ex)
            {
                enabled = false;
                if (!_activationFailureLogged)
                {
                    _activationFailureLogged = true;
                    ClientLog.Error("SUPPRESSORS",
                        "package_status_failed", ex);
                }
            }
            if (!enabled)
            {
                if (!_activationFailureLogged)
                {
                    _activationFailureLogged = true;
                    ClientLog.Warn("SUPPRESSORS", "runtime_inactive",
                        new Dictionary<string, object>
                        {
                            { "registry_available",
                                Allin1ExtensionApi.RegistryAvailable },
                            { "package_enabled", false },
                            { "retry_ms", ActivationRetryMs },
                            { "allin1_location",
                                typeof(Allin1ExtensionApi).Assembly.Location },
                            { "allin1_codebase",
                                typeof(Allin1ExtensionApi).Assembly.CodeBase },
                            { "app_base",
                                AppDomain.CurrentDomain.BaseDirectory },
                        });
                }
                return false;
            }

            IDisposable saveRegistration = null;
            IDisposable componentRegistration = null;
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
                if (!_activationFailureLogged)
                {
                    _activationFailureLogged = true;
                    ClientLog.Error("SUPPRESSORS",
                        "runtime_authorization_failed", ex,
                        new Dictionary<string, object>
                        {
                            { "registry_available",
                                Allin1ExtensionApi.RegistryAvailable },
                            { "package_enabled", true },
                        });
                }
                return false;
            }
            _saveRegistration = saveRegistration;
            _componentRegistration = componentRegistration;
            _runtimeEnabled = true;
            _activationFailureLogged = false;
            _stealthEnabled =
                Allin1ExtensionApi.GetBooleanSetting(
                    PackageId, "realistic_suppressors", true);
            _breakageEnabled = Allin1ExtensionApi.GetBooleanSetting(
                PackageId, "suppressor_breakage", true);
            _temperatureDebugEnabled =
                Allin1ExtensionApi.GetBooleanSetting(
                    PackageId, "suppressor_temperature_debug", false);
            _heatSmokeEnabled =
                Allin1ExtensionApi.GetBooleanSetting(
                    PackageId, "suppressor_heat_smoke", true);
            _durabilityScale = Clamp(
                (float)Allin1ExtensionApi.GetNumberSetting(
                    PackageId, "suppressor_durability_scale", 1d),
                0.5f, 3f);
            _heatSmokeIntensityScale = Clamp(
                (float)Allin1ExtensionApi.GetNumberSetting(
                    PackageId, "suppressor_smoke_intensity", 1d),
                0.5f, 2f);
            Interval = 0;
            ClientLog.Info("SUPPRESSORS", "configured",
                new Dictionary<string, object>
                {
                    { "runtime_mode", "allin1" },
                    { "stealth_enabled", _stealthEnabled },
                    { "breakage_enabled", _breakageEnabled },
                    { "temperature_debug_enabled",
                        _temperatureDebugEnabled },
                    { "heat_smoke_enabled", _heatSmokeEnabled },
                    { "heat_smoke_intensity",
                        _heatSmokeIntensityScale },
                    { "durability_scale", _durabilityScale },
                    { "profiled_weapons",
                        SuppressorThermalProfiles.All.Count },
                    { "recovered_at_runtime", recoveredAtRuntime },
                });
            return true;
#else
            string assemblyLocation =
                typeof(RealisticSuppressorController).Assembly.Location;
            string directory = System.IO.Path.GetDirectoryName(
                assemblyLocation) ?? AppDomain.CurrentDomain.BaseDirectory;
            string configPath = System.IO.Path.Combine(directory,
                StandaloneSuppressorSettings.FileName);
            string createWarning = StandaloneSuppressorSettings
                .EnsureDefaultFile(configPath);
            StandaloneSuppressorSettings settings =
                StandaloneSuppressorSettings.Load(configPath);

            _stealthEnabled = settings.StealthEnabled;
            _breakageEnabled = settings.BreakageEnabled;
            _temperatureDebugEnabled =
                settings.TemperatureDebugEnabled;
            _heatSmokeEnabled = settings.HeatSmokeEnabled;
            _durabilityScale = settings.DurabilityScale;
            _heatSmokeIntensityScale = settings.HeatSmokeIntensity;
            _runtimeEnabled = true;
            Interval = 0;

            ClientLog.Info("SUPPRESSORS", "configured",
                new Dictionary<string, object>
                {
                    { "runtime_mode", "standalone" },
                    { "config_path", configPath },
                    { "config_present", System.IO.File.Exists(configPath) },
                    { "config_warnings", settings.Warnings.Count },
                    { "stealth_enabled", _stealthEnabled },
                    { "breakage_enabled", _breakageEnabled },
                    { "temperature_debug_enabled",
                        _temperatureDebugEnabled },
                    { "heat_smoke_enabled", _heatSmokeEnabled },
                    { "heat_smoke_intensity",
                        _heatSmokeIntensityScale },
                    { "durability_scale", _durabilityScale },
                    { "profiled_weapons",
                        SuppressorThermalProfiles.All.Count },
                    { "recovered_at_runtime", recoveredAtRuntime },
                });
            foreach (string warning in settings.Warnings)
            {
                ClientLog.Warn("SUPPRESSORS", "standalone_config_warning",
                    new Dictionary<string, object>
                    {
                        { "warning", warning },
                        { "config_path", configPath },
                    });
            }
            if (createWarning.Length > 0)
            {
                ClientLog.Warn("SUPPRESSORS", "standalone_config_warning",
                    new Dictionary<string, object>
                    {
                        { "warning", createWarning },
                        { "config_path", configPath },
                    });
            }
            return true;
#endif
        }

        private void OnTick(object sender, EventArgs args)
        {
            int now = Game.GameTime;
            if (!_runtimeEnabled)
            {
                if (ElapsedMilliseconds(now,
                        _lastActivationAttemptAt) >= ActivationRetryMs)
                    TryActivateRuntime(true);
                if (!_runtimeEnabled) return;
            }
            try
            {
                bool unsafeGameState = Game.IsLoading || Game.IsPaused ||
                    Game.IsCutsceneActive ||
#if ALLIN1_HOST
                    Allin1ExtensionApi.IsGbayMenuActive ||
#endif
                    !Game.Player.CanControlCharacter;
                Ped player = Game.Player.Character;
                if (unsafeGameState || player == null || !player.Exists() ||
                    player.IsDead)
                {
                    if (player != null && player.Exists())
                        TryFlushActiveThermalState(now, true);
                    DestroyHeatOverlay();
                    DestroySuppressorSmoke();
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
                if (_breakageActiveForCurrentCharacter)
                    PrepareBreakEffectAsset();
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

                if (knownSuppressorAttached && thermalState != null &&
                    !thermalState.Broken)
                {
                    UpdateHeatStage(thermalState);
                    RenderSuppressorGlow(player, thermalState);
                    TryRenderSuppressorSmoke(player, thermalState, now);
                    RenderTemperatureDebug(
                        knownSuppressorAttached, thermalState);
                    MaybePersistThermalState(
                        thermalState, now, false);
                }
                else
                {
                    DestroyHeatOverlay();
                    DestroySuppressorSmoke();
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
                DestroySuppressorSmoke();
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
#if STANDALONE_RUNTIME
                TryCommitStandaloneState("script_abort");
#endif
            }
            catch (Exception ex)
            {
                ClientLog.Error(
                    "SUPPRESSORS", "abort_persistence_failed", ex);
            }
            finally
            {
                DestroySuppressorSmoke();
                DestroyHeatOverlay();
                ReleaseBreakEffectAsset();
#if ALLIN1_HOST
                _componentRegistration?.Dispose();
                _saveRegistration?.Dispose();
#endif
            }

            ClientLog.Info("SUPPRESSORS", "session_summary",
                new Dictionary<string, object>
                {
                    { "rounds_processed", _roundsProcessed },
                    { "unwitnessed_rounds", _unwitnessedShots },
                    { "witnessed_rounds", _witnessedShots },
                    { "broken_suppressors", _brokenSuppressors },
                    { "break_effects_started", _breakEffectsStarted },
                    { "heat_smoke_effects_started",
                        _heatSmokeEffectsStarted },
                    { "breakage_enabled", _breakageEnabled },
                    { "exceptions", _exceptions },
                });
        }

#if ALLIN1_HOST
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
#endif

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
#if STANDALONE_RUNTIME
            TryCommitStandaloneState("native_component_purchase");
#endif
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
            DestroyHeatOverlay();
            DestroySuppressorSmoke();
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
            DestroyHeatOverlay();
            DestroySuppressorSmoke();
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
            DestroyHeatOverlay();
            DestroySuppressorSmoke();
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
            return CountRoundsFired(_lastAmmoInClip, ammoInClip,
                isShooting, _wasShooting, weaponChanged);
        }

        internal static int CountRoundsFired(
            int previousAmmoInClip, int ammoInClip,
            bool isShooting, bool wasShooting, bool weaponChanged)
        {
            // The ammo delta is the durable observation. IsShooting may have
            // returned to false before this script's frame after a quick
            // semi-automatic shot, so applying that guard first loses heat.
            if (!weaponChanged && previousAmmoInClip >= 0 &&
                ammoInClip >= 0 && ammoInClip < previousAmmoInClip)
                return Math.Min(100,
                    previousAmmoInClip - ammoInClip);
            if (!isShooting) return 0;
            return !wasShooting ? 1 : 0;
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
                // The cached per-weapon state remains in _thermalStates so a
                // reattached can can resume cooling and durability, but it is
                // not the active suppressor for this frame. Clearing the out
                // value prevents stale heat/HUD state on an unsuppressed gun.
                state = null;
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
#if STANDALONE_RUNTIME
                TryCommitStandaloneState("native_component_replacement");
#endif
                persisted = _stateStore.GetDurability(
                    character, state.Profile.WeaponName,
                    state.Profile.ComponentHash);
                if (persisted <= 0f) return true;
            }

            state.Broken = false;
            state.BreakEventLogged = false;
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
#if STANDALONE_RUNTIME
            if (confirmed)
                confirmed = TryCommitStandaloneState(
                    "suppressor_failure");
#endif
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
            bool firstBreak = SuppressorThermalPolicy
                .ShouldBeginBreakEvent(notify, state.BreakEventLogged);
            if (firstBreak)
            {
                // Latch before any native call so an exception cannot replay
                // the one-shot audiovisual failure on a later removal retry.
                state.BreakEventLogged = true;
                TryEmitSuppressorBreakEffect(player, profile);
            }
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
            DestroyHeatOverlay();
            state.ObservedAbsentAfterBreak |= removed;
            state.TemperatureCelsius = Math.Min(
                state.TemperatureCelsius,
                SuppressorThermalPolicy.MaximumTrackedCelsius);

            if (firstBreak)
            {
                _brokenSuppressors++;
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

        private void PrepareBreakEffectAsset()
        {
            if (_breakParticleAssetReady) return;
            try
            {
                Function.Call(Hash.REQUEST_NAMED_PTFX_ASSET,
                    BreakParticleAsset);
                _breakParticleAssetRequested = true;
                _breakParticleAssetReady = Function.Call<bool>(
                    Hash.HAS_NAMED_PTFX_ASSET_LOADED,
                    BreakParticleAsset);
            }
            catch (Exception ex)
            {
                if (_breakParticleAssetFailureLogged) return;
                _breakParticleAssetFailureLogged = true;
                ClientLog.Error("SUPPRESSORS",
                    "break_effect_asset_request_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "particle_asset", BreakParticleAsset },
                        { "effect",
                            "breakage remains active without sparks" },
                    });
            }
        }

        private void ReleaseBreakEffectAsset()
        {
            if (!_breakParticleAssetRequested) return;
            try
            {
                Function.Call(Hash.REMOVE_NAMED_PTFX_ASSET,
                    BreakParticleAsset);
            }
            catch (Exception ex)
            {
                ClientLog.Error("SUPPRESSORS",
                    "break_effect_asset_release_failed", ex);
            }
            finally
            {
                _breakParticleAssetRequested = false;
                _breakParticleAssetReady = false;
            }
        }

        private void TryEmitSuppressorBreakEffect(
            Ped player, SuppressorThermalProfile profile)
        {
            try
            {
                if (!TryGetSuppressorAttachment(
                        player, profile, out Entity _,
                        out EntityBone attachmentBone,
                        out string poseSource))
                {
                    ClientLog.Warn("SUPPRESSORS",
                        "break_effect_attachment_unavailable",
                        new Dictionary<string, object>
                        {
                            { "weapon", profile.WeaponName },
                            { "component_hash", profile.ComponentHash },
                        });
                    return;
                }

                float axialOffset = SuppressorThermalPolicy
                    .BreakEffectAxialOffset(profile.ComponentHash);
                if (axialOffset <= 0f) return;
                Vector3 effectPosition;
                try
                {
                    // The attached overlay has the same +X authoring axis as
                    // the suppressor and remains available until removal.
                    // Resolve the front cap to world space now so the
                    // non-looped burst survives deletion of the component.
                    effectPosition = _heatOverlay != null &&
                        _heatOverlay.Exists()
                        ? _heatOverlay.GetOffsetPosition(
                            new Vector3(axialOffset, 0f, 0f))
                        : attachmentBone.Position;
                }
                catch (Exception)
                {
                    effectPosition = attachmentBone.Position;
                }

                PrepareBreakEffectAsset();
                bool particleStarted = false;
                if (_breakParticleAssetReady)
                {
                    try
                    {
                        Function.Call(Hash.USE_PARTICLE_FX_ASSET,
                            BreakParticleAsset);
                        particleStarted = Function.Call<bool>(
                            Hash.START_PARTICLE_FX_NON_LOOPED_AT_COORD,
                            BreakParticleEffect,
                            effectPosition.X, effectPosition.Y,
                            effectPosition.Z,
                            0f, 0f, 0f,
                            BreakParticleScale,
                            false, false, false);
                    }
                    catch (Exception ex)
                    {
                        ClientLog.Error("SUPPRESSORS",
                            "break_effect_particle_failed", ex,
                            new Dictionary<string, object>
                            {
                                { "weapon", profile.WeaponName },
                                { "particle_asset", BreakParticleAsset },
                                { "particle_effect", BreakParticleEffect },
                            });
                    }
                }

                bool soundRequested = false;
                try
                {
                    Function.Call(Hash.PLAY_SOUND_FROM_COORD,
                        -1, BreakSoundName,
                        effectPosition.X, effectPosition.Y,
                        effectPosition.Z, BreakSoundSet,
                        false, 0, false);
                    soundRequested = true;
                }
                catch (Exception ex)
                {
                    ClientLog.Error("SUPPRESSORS",
                        "break_effect_sound_failed", ex,
                        new Dictionary<string, object>
                        {
                            { "weapon", profile.WeaponName },
                            { "sound", BreakSoundName },
                            { "sound_set", BreakSoundSet },
                        });
                }

                if (particleStarted || soundRequested)
                    _breakEffectsStarted++;
                ClientLog.Info("SUPPRESSORS", "break_effect_emitted",
                    new Dictionary<string, object>
                    {
                        { "weapon", profile.WeaponName },
                        { "component_hash", profile.ComponentHash },
                        { "pose_source", poseSource },
                        { "axial_offset_m", axialOffset },
                        { "particle_asset", BreakParticleAsset },
                        { "particle_effect", BreakParticleEffect },
                        { "particle_scale", BreakParticleScale },
                        { "particle_started", particleStarted },
                        { "sound", BreakSoundName },
                        { "sound_requested", soundRequested },
                        { "gameplay_damage", false },
                    });
            }
            catch (Exception ex)
            {
                // Visual/audio failure must never prevent the durability
                // tombstone or native suppressor removal from completing.
                ClientLog.Error(
                    "SUPPRESSORS", "break_effect_failed", ex);
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
#if STANDALONE_RUNTIME
                if (persisted)
                    persisted = TryCommitStandaloneState(
                        "wear_checkpoint");
#endif
            }
            state.LastPersistedAt = now;
            if (persisted)
            {
                state.LastPersistedDurability = state.Durability;
                state.Dirty = false;
            }
        }

#if STANDALONE_RUNTIME
        private bool TryCommitStandaloneState(string reason)
        {
            try
            {
                _stateStore.Commit();
                return true;
            }
            catch (Exception ex)
            {
                ClientLog.Error("SUPPRESSORS",
                    "standalone_condition_commit_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "reason", reason ?? "checkpoint" },
                    });
                return false;
            }
        }
#endif

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

        private static void UpdateHeatStage(
            ThermalRuntimeState state)
        {
            SuppressorHeatStage next = SuppressorThermalPolicy.HeatStage(
                state.Profile, state.TemperatureCelsius);
            if (next < SuppressorHeatStage.Glowing)
                state.GlowStartedLogged = false;
            state.Stage = next;
        }

        private void RenderTemperatureDebug(
            bool suppressorAttached, ThermalRuntimeState state)
        {
            if (!ShouldRenderTemperatureDebug(
                    _temperatureDebugEnabled, suppressorAttached,
                    state != null, state != null && state.Broken))
                return;

            int red = 225;
            int green = 235;
            int blue = 245;
            if (state.Stage == SuppressorHeatStage.Damaging)
            {
                red = 255;
                green = 190;
                blue = 70;
            }
            else if (state.Stage == SuppressorHeatStage.Glowing)
            {
                red = 255;
                green = 105;
                blue = 45;
            }
            else if (state.Stage == SuppressorHeatStage.Critical)
            {
                red = 255;
                green = 45;
                blue = 35;
            }

            Function.Call(Hash.SET_TEXT_FONT, 0);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, 0.32f);
            Function.Call(Hash.SET_TEXT_COLOUR, red, green, blue, 235);
            Function.Call(Hash.SET_TEXT_CENTRE, false);
            Function.Call(Hash.SET_TEXT_RIGHT_JUSTIFY, true);
            Function.Call(Hash.SET_TEXT_WRAP, 0f, 0.985f);
            Function.Call(Hash.SET_TEXT_DROP_SHADOW);
            Function.Call(Hash.SET_TEXT_OUTLINE);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME,
                TemperatureDebugText(state.TemperatureCelsius));
            Function.Call(Hash.END_TEXT_COMMAND_DISPLAY_TEXT, 0.985f, 0.915f);
        }

        internal static bool ShouldRenderTemperatureDebug(
            bool debugEnabled, bool suppressorAttached,
            bool hasThermalState, bool suppressorBroken)
        {
            return debugEnabled && suppressorAttached && hasThermalState &&
                !suppressorBroken;
        }

        internal static string TemperatureDebugText(
            float temperatureCelsius)
        {
            float bounded = temperatureCelsius;
            if (float.IsNaN(bounded) || float.IsInfinity(bounded))
                bounded = SuppressorThermalPolicy.AmbientCelsius;
            bounded = Math.Max(SuppressorThermalPolicy.AmbientCelsius,
                Math.Min(SuppressorThermalPolicy.MaximumTrackedCelsius,
                    bounded));
            return "SUPPRESSOR " + Math.Round(bounded).ToString(
                "0", CultureInfo.InvariantCulture) + " °C";
        }

        private void RenderSuppressorGlow(
            Ped player, ThermalRuntimeState state)
        {
            int now = Game.GameTime;
            SuppressorGlowVisual visual = SuppressorThermalPolicy
                .GlowVisual(state.Profile, state.TemperatureCelsius);
            bool overlayExists = _heatOverlay != null &&
                _heatOverlay.Exists();
            if (!visual.Visible && !overlayExists)
            {
                DestroyHeatOverlay();
                return;
            }
            if (!TryGetSuppressorAttachment(
                    player, state.Profile, out Entity heldWeapon,
                    out EntityBone attachmentBone,
                    out string poseSource))
            {
                DestroyHeatOverlay();
                return;
            }
            string baseModelName = visual.OverlayModelName ??
                SuppressorThermalPolicy.HeatOverlayModelName(
                    state.Profile.ComponentHash);
            if (!EnsureHeatOverlay(
                    heldWeapon, attachmentBone, baseModelName,
                    visual.Visible ? visual.Opacity : 0f,
                    visual.Visible, now))
                return;

            if (!visual.Visible) return;

            if (!state.GlowStartedLogged)
            {
                state.GlowStartedLogged = true;
                ClientLog.Info("SUPPRESSORS", "glow_started",
                    new Dictionary<string, object>
                    {
                        { "weapon", state.Profile.WeaponName },
                        { "temperature_c", state.TemperatureCelsius },
                        { "physical_intensity", visual.Intensity },
                        { "pose_source", poseSource },
                        { "renderer",
                            "bone_attached_steady_material_overlay" },
                        { "overlay_model", _heatOverlayModelName },
                        { "target_opacity", visual.Opacity },
                        { "material_level", _heatOverlayMaterialLevel },
                    });
            }
        }

        private bool EnsureHeatOverlay(
            Entity heldWeapon, EntityBone attachmentBone,
            string baseModelName, float targetOpacity,
            bool forceVisible, int now)
        {
            if (string.IsNullOrWhiteSpace(baseModelName))
            {
                DestroyHeatOverlay();
                return false;
            }

            bool overlayExists = _heatOverlay != null &&
                _heatOverlay.Exists();
            bool fadeIdentityMatches =
                _heatOverlayWeaponEntity == heldWeapon.Handle &&
                _heatOverlayBoneIndex == attachmentBone.Index &&
                string.Equals(_heatOverlayBaseModelName,
                    baseModelName,
                    StringComparison.OrdinalIgnoreCase);
            if (!fadeIdentityMatches)
            {
                _heatOverlayWeaponEntity = heldWeapon.Handle;
                _heatOverlayBoneIndex = attachmentBone.Index;
                _heatOverlayBaseModelName = baseModelName;
                _heatOverlaySmoothedOpacity = 0f;
                _heatOverlayMaterialLevel = 0;
                _heatOverlayLastFadeAt = now;
            }

            int elapsedMilliseconds = _heatOverlayLastFadeAt > 0
                ? Math.Max(0, now - _heatOverlayLastFadeAt)
                : 0;
            _heatOverlayLastFadeAt = now;
            _heatOverlaySmoothedOpacity = SuppressorThermalPolicy
                .SmoothHeatOverlayOpacity(
                    _heatOverlaySmoothedOpacity, targetOpacity,
                    elapsedMilliseconds);
            int materialLevel = SuppressorThermalPolicy
                .HeatOverlayMaterialLevel(
                    _heatOverlaySmoothedOpacity,
                    _heatOverlayMaterialLevel);
            if (forceVisible && materialLevel == 0)
                materialLevel = 1;
            if (materialLevel == 0)
            {
                DestroyHeatOverlay();
                return true;
            }

            string desiredModelName = SuppressorThermalPolicy
                .HeatOverlayMaterialModelName(
                    baseModelName, materialLevel);
            bool identityMatches = overlayExists &&
                string.Equals(_heatOverlayModelName,
                    desiredModelName,
                    StringComparison.OrdinalIgnoreCase) &&
                _heatOverlay.IsAttachedTo(heldWeapon);
            if (!identityMatches)
            {
                Model model = new Model(desiredModelName);
                if (!model.IsValid || !model.IsInCdImage)
                {
                    if (_unavailableHeatOverlayModelsLogged.Add(
                            desiredModelName))
                    {
                        ClientLog.Warn("SUPPRESSORS",
                            "heat_overlay_model_unavailable",
                            new Dictionary<string, object>
                            {
                                { "model", desiredModelName },
                                { "model_hash",
                                    unchecked((uint)model.Hash) },
                                { "effect",
                                    "temperature simulation remains active" },
                            });
                    }
                    return false;
                }
                model.Request();
                if (!model.IsLoaded) return false;

                Prop overlay = World.CreatePropNoOffset(
                    model, attachmentBone.Position, false);
                model.MarkAsNoLongerNeeded();
                if (overlay == null || !overlay.Exists())
                    return false;

                Prop previousOverlay = _heatOverlay;
                _heatOverlay = overlay;
                _heatOverlayWeaponEntity = heldWeapon.Handle;
                _heatOverlayBoneIndex = attachmentBone.Index;
                _heatOverlayBaseModelName = baseModelName;
                _heatOverlayModelName = desiredModelName;
                _heatOverlayMaterialLevel = materialLevel;
                overlay.IsPersistent = true;
                overlay.IsInvincible = true;
                overlay.IsCollisionEnabled = false;
                Function.Call(Hash.SET_ENTITY_FLAG_SUPPRESS_SHADOW,
                    overlay.Handle, true);
                overlay.Opacity = 255;
                overlay.AttachTo(
                    attachmentBone, Vector3.Zero, Vector3.Zero);
                try
                {
                    if (previousOverlay != null &&
                        previousOverlay.Exists())
                        previousOverlay.Delete();
                }
                catch (Exception ex)
                {
                    ClientLog.Error("SUPPRESSORS",
                        "heat_overlay_replacement_cleanup_failed", ex);
                }
                return true;
            }

            _heatOverlayMaterialLevel = materialLevel;
            return true;
        }

        private void DestroyHeatOverlay()
        {
            Prop overlay = _heatOverlay;
            _heatOverlay = null;
            _heatOverlayWeaponEntity = 0;
            _heatOverlayBoneIndex = -1;
            _heatOverlayBaseModelName = "none";
            _heatOverlayModelName = "none";
            _heatOverlayMaterialLevel = 0;
            _heatOverlaySmoothedOpacity = 0f;
            _heatOverlayLastFadeAt = int.MinValue / 2;
            try
            {
                if (overlay != null && overlay.Exists())
                    overlay.Delete();
            }
            catch (Exception ex)
            {
                ClientLog.Error(
                    "SUPPRESSORS", "heat_overlay_cleanup_failed", ex);
            }
        }

        private void RenderSuppressorSmoke(
            Ped player, ThermalRuntimeState state, int now)
        {
            if (!_heatSmokeEnabled || state == null || state.Broken)
            {
                DestroySuppressorSmoke();
                return;
            }

            SuppressorSmokeVisual visual = SuppressorThermalPolicy
                .SmokeVisual(state.Profile, state.TemperatureCelsius,
                    _heatSmokeIntensityScale);
            if (!visual.Visible || !TryGetSuppressorAttachment(
                    player, state.Profile, out Entity heldWeapon,
                    out EntityBone attachmentBone,
                    out string poseSource))
            {
                DestroySuppressorSmoke();
                return;
            }

            bool primaryExists = SmokeEmitterExists(
                _primaryHeatSmokeHandle);
            bool identityMatches = primaryExists &&
                _heatSmokeWeaponEntity == heldWeapon.Handle &&
                _heatSmokeBoneIndex == attachmentBone.Index &&
                _heatSmokeComponentHash == state.Profile.ComponentHash;
            bool primaryStarted = false;
            if (!identityMatches)
            {
                DestroySuppressorSmoke();
                // If a native stop failed, DestroySuppressorSmoke retains
                // the positive handle for a later retry. Never overwrite it
                // with a new loop or the old emitter would become orphaned.
                if (_primaryHeatSmokeHandle > 0 ||
                    _secondaryHeatSmokeHandle > 0)
                    return;
                if (ElapsedMilliseconds(now,
                        _lastHeatSmokeStartAttemptAt) < SmokeStartRetryMs)
                    return;
                _lastHeatSmokeStartAttemptAt = now;
                PrepareBreakEffectAsset();
                if (!_breakParticleAssetReady) return;

                float frontCap = SuppressorThermalPolicy
                    .BreakEffectAxialOffset(state.Profile.ComponentHash);
                if (frontCap <= 0f) return;
                _primaryHeatSmokeHandle = StartSuppressorSmokeEmitter(
                    heldWeapon, attachmentBone,
                    frontCap * 0.82f, visual.PrimaryScale);
                if (_primaryHeatSmokeHandle <= 0) return;

                _heatSmokeWeaponEntity = heldWeapon.Handle;
                _heatSmokeBoneIndex = attachmentBone.Index;
                _heatSmokeComponentHash = state.Profile.ComponentHash;
                _heatSmokeEffectsStarted++;
                primaryStarted = true;
                ClientLog.Info("SUPPRESSORS", "heat_smoke_started",
                    new Dictionary<string, object>
                    {
                        { "weapon", state.Profile.WeaponName },
                        { "component_hash",
                            state.Profile.ComponentHash },
                        { "temperature_c", state.TemperatureCelsius },
                        { "physical_intensity", visual.Intensity },
                        { "particle_asset", SmokeParticleAsset },
                        { "particle_effect", SmokeParticleEffect },
                        { "pose_source", poseSource },
                        { "renderer",
                            "bone_attached_looped_particle" },
                    });
            }

            bool secondaryStarted = false;
            bool secondaryExists = SmokeEmitterExists(
                _secondaryHeatSmokeHandle);
            if (!secondaryExists)
                _secondaryHeatSmokeHandle = 0;
            bool useSecondary = SuppressorThermalPolicy
                .ShouldUseSecondarySmoke(
                    visual.Intensity, secondaryExists);
            if (useSecondary &&
                _secondaryHeatSmokeHandle <= 0 &&
                ElapsedMilliseconds(now,
                    _lastSecondarySmokeStartAttemptAt) >=
                        SmokeStartRetryMs)
            {
                _lastSecondarySmokeStartAttemptAt = now;
                float frontCap = SuppressorThermalPolicy
                    .BreakEffectAxialOffset(state.Profile.ComponentHash);
                _secondaryHeatSmokeHandle = StartSuppressorSmokeEmitter(
                    heldWeapon, attachmentBone,
                    frontCap * 0.42f, visual.SecondaryScale);
                if (_secondaryHeatSmokeHandle > 0)
                {
                    _heatSmokeEffectsStarted++;
                    secondaryStarted = true;
                }
            }
            else if (!useSecondary &&
                _secondaryHeatSmokeHandle > 0)
            {
                StopSuppressorSmokeEmitter(_secondaryHeatSmokeHandle);
                _secondaryHeatSmokeHandle = 0;
            }

            if (!primaryStarted && !secondaryStarted &&
                ElapsedMilliseconds(now,
                    _lastHeatSmokeVisualUpdateAt) <
                        SmokeVisualUpdateMs)
                return;
            _lastHeatSmokeVisualUpdateAt = now;
            ApplySuppressorSmokeVisual(visual);
        }

        private void TryRenderSuppressorSmoke(
            Ped player, ThermalRuntimeState state, int now)
        {
            if (_heatSmokeRuntimeFailed)
            {
                DestroySuppressorSmoke();
                return;
            }
            try
            {
                RenderSuppressorSmoke(player, state, now);
            }
            catch (Exception ex)
            {
                _heatSmokeRuntimeFailed = true;
                DestroySuppressorSmoke();
                ClientLog.Error("SUPPRESSORS",
                    "heat_smoke_renderer_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "effect",
                            "temperature simulation remains active" },
                    });
            }
        }

        private static int StartSuppressorSmokeEmitter(
            Entity heldWeapon, EntityBone attachmentBone,
            float axialOffset, float scale)
        {
            Function.Call(Hash.USE_PARTICLE_FX_ASSET,
                SmokeParticleAsset);
            int handle = Function.Call<int>(
                Hash.START_PARTICLE_FX_LOOPED_ON_ENTITY_BONE,
                SmokeParticleEffect, heldWeapon.Handle,
                axialOffset, 0f, 0f,
                0f, 0f, 0f,
                attachmentBone.Index, scale,
                false, false, false);
            if (handle <= 0) return 0;
            try
            {
                // Colour is cosmetic. Once the native returns a positive
                // loop handle, always return it to the owner so cleanup can
                // stop the emitter even if this optional adjustment fails.
                Function.Call(Hash.SET_PARTICLE_FX_LOOPED_COLOUR,
                    handle, 0.72f, 0.74f, 0.77f, false);
            }
            catch (Exception)
            {
                // Keep the stock particle colour rather than orphaning a
                // live loop whose handle the controller can no longer reach.
            }
            return handle;
        }

        private void ApplySuppressorSmokeVisual(
            SuppressorSmokeVisual visual)
        {
            if (SmokeEmitterExists(_primaryHeatSmokeHandle))
            {
                Function.Call(Hash.SET_PARTICLE_FX_LOOPED_SCALE,
                    _primaryHeatSmokeHandle, visual.PrimaryScale);
                Function.Call(Hash.SET_PARTICLE_FX_LOOPED_ALPHA,
                    _primaryHeatSmokeHandle, visual.Alpha);
            }
            if (SmokeEmitterExists(_secondaryHeatSmokeHandle))
            {
                Function.Call(Hash.SET_PARTICLE_FX_LOOPED_SCALE,
                    _secondaryHeatSmokeHandle, visual.SecondaryScale);
                Function.Call(Hash.SET_PARTICLE_FX_LOOPED_ALPHA,
                    _secondaryHeatSmokeHandle,
                    visual.Alpha * 0.82f);
            }
        }

        private static bool SmokeEmitterExists(int handle)
        {
            return handle > 0 && Function.Call<bool>(
                Hash.DOES_PARTICLE_FX_LOOPED_EXIST, handle);
        }

        private static void StopSuppressorSmokeEmitter(int handle)
        {
            if (handle <= 0) return;
            // A direct stop is safe for a stale handle and avoids a separate
            // existence native becoming a failure point before cleanup.
            Function.Call(Hash.STOP_PARTICLE_FX_LOOPED,
                handle, false);
        }

        private void DestroySuppressorSmoke()
        {
            _heatSmokeWeaponEntity = 0;
            _heatSmokeBoneIndex = -1;
            _heatSmokeComponentHash = 0;
            _lastHeatSmokeVisualUpdateAt = int.MinValue / 2;
            Exception cleanupFailure = null;
            try
            {
                StopSuppressorSmokeEmitter(_primaryHeatSmokeHandle);
                _primaryHeatSmokeHandle = 0;
            }
            catch (Exception ex)
            {
                // Retain the positive handle so a later tick can retry.
                cleanupFailure = ex;
            }
            try
            {
                StopSuppressorSmokeEmitter(_secondaryHeatSmokeHandle);
                _secondaryHeatSmokeHandle = 0;
            }
            catch (Exception ex)
            {
                // Stop the other emitter independently and preserve this
                // handle for the next cleanup attempt.
                cleanupFailure = cleanupFailure ?? ex;
            }
            if (cleanupFailure != null &&
                !_heatSmokeCleanupFailureLogged)
            {
                _heatSmokeCleanupFailureLogged = true;
                ClientLog.Error("SUPPRESSORS",
                    "heat_smoke_cleanup_failed", cleanupFailure);
            }
            else if (_primaryHeatSmokeHandle <= 0 &&
                _secondaryHeatSmokeHandle <= 0)
            {
                _heatSmokeCleanupFailureLogged = false;
            }
        }

        private bool TryGetSuppressorAttachment(
            Ped player, SuppressorThermalProfile profile,
            out Entity heldWeapon, out EntityBone attachmentBone,
            out string poseSource)
        {
            heldWeapon = null;
            attachmentBone = null;
            poseSource = "none";
            int weaponEntity = Function.Call<int>(
                Hash.GET_CURRENT_PED_WEAPON_ENTITY_INDEX,
                player.Handle, 0);
            if (weaponEntity != _cachedWeaponEntity ||
                profile.ComponentHash != _cachedSuppressorComponentHash)
            {
                _cachedWeaponEntity = weaponEntity;
                _cachedSuppressorBoneIndex = -1;
                _cachedSuppressorBoneName = "none";
                _cachedSuppressorComponentHash = profile.ComponentHash;
                if (weaponEntity != 0 && Function.Call<bool>(
                        Hash.DOES_ENTITY_EXIST, weaponEntity))
                {
                    string first = profile.WeaponName.EndsWith(
                        "_MK2", StringComparison.OrdinalIgnoreCase)
                        ? "WAPSupp_2" : "WAPSupp";
                    string second = first == "WAPSupp"
                        ? "WAPSupp_2" : "WAPSupp";
                    _cachedSuppressorBoneIndex = Function.Call<int>(
                        Hash.GET_ENTITY_BONE_INDEX_BY_NAME,
                        weaponEntity, first);
                    if (_cachedSuppressorBoneIndex >= 0)
                        _cachedSuppressorBoneName = first;
                    else
                    {
                        _cachedSuppressorBoneIndex = Function.Call<int>(
                            Hash.GET_ENTITY_BONE_INDEX_BY_NAME,
                            weaponEntity, second);
                        if (_cachedSuppressorBoneIndex >= 0)
                            _cachedSuppressorBoneName = second;
                    }
                }
            }

            bool validWeaponEntity = _cachedWeaponEntity != 0 &&
                Function.Call<bool>(
                    Hash.DOES_ENTITY_EXIST, _cachedWeaponEntity);
            if (!validWeaponEntity || _cachedSuppressorBoneIndex < 0)
                return false;

            try
            {
                heldWeapon = Entity.FromHandle(_cachedWeaponEntity);
                if (heldWeapon == null || !heldWeapon.Exists())
                    return false;
                attachmentBone = heldWeapon.Bones[
                    _cachedSuppressorBoneIndex];
                if (attachmentBone == null || !attachmentBone.IsValid)
                    return false;
                poseSource = _cachedSuppressorBoneName +
                    "+engine_attachment";
                return true;
            }
            catch (Exception)
            {
                heldWeapon = null;
                attachmentBone = null;
                return false;
            }
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
            _cachedSuppressorBoneIndex = -1;
            _cachedSuppressorBoneName = "none";
            _cachedSuppressorComponentHash = 0;
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
