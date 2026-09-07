// TrafficSpawner.cs — Adds GTA Online and opted-in package vehicles to traffic.
//
// Two systems work together:
//   1. Driven spawner — creates eligible vehicles with AI drivers on road nodes.
//   2. Replacement scanner — swaps vanilla ambient vehicles (parked or driven)
//      with class-matched eligible equivalents while off-screen.
//
// Only road-appropriate classes are used (no planes, helis, boats, military,
// emergency, etc.).  Replacement rate is ~30 % for a natural vanilla/DLC mix.
//
// Requires: ScriptHookV + ScriptHookVDotNet Enhanced

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class TrafficSpawner : Script
    {
        // --- Driven spawner config ---
        private int _maxDriven = 20;
        private float _spawnDistMin = 80f;
        private float _spawnDistMax = 200f;
        private float _cleanupDist = 350f;
        private int _drivenCooldownMs = 5000;
        private const int MODEL_LOAD_TIMEOUT = 5000;

        // --- Replacement scanner config ---
        private int _scanCooldownMs = 3000;
        private float _scanRadius = 200f;
        private float _minReplaceDist = 50f;
        private float _replaceChance = 0.30f;
        private bool _adaptivePerformance = true;
        private int _minimumFps = 40;
        private float _smoothedFps = 60f;
        private bool _throttled;
        internal static int ManagedVehicleCount { get; private set; }
        internal static float SmoothedFps { get; private set; } = 60f;
        internal static bool IsThrottled { get; private set; }
        internal static string PauseReason { get; private set; } = "starting";

        // Road-appropriate vehicle classes used for driven spawns.
        private static readonly string[][] ROAD_CLASSES =
        {
            VehicleList.Compacts,
            VehicleList.Coupes,
            VehicleList.Sedans,
            VehicleList.Suvs,
            VehicleList.Muscle,
            VehicleList.Sports,
            VehicleList.Sportsclassics,
            VehicleList.Super,
            VehicleList.Offroad,
            VehicleList.Motorcycles,
            VehicleList.Vans,
        };

        // Map VehicleClass enum → VehicleList arrays for class-matched replacement.
        private static readonly Dictionary<VehicleClass, string[]> CLASS_MAP =
            new Dictionary<VehicleClass, string[]>
        {
            { VehicleClass.Compacts,       VehicleList.Compacts },
            { VehicleClass.Coupes,         VehicleList.Coupes },
            { VehicleClass.Sedans,         VehicleList.Sedans },
            { VehicleClass.SUVs,           VehicleList.Suvs },
            { VehicleClass.Muscle,         VehicleList.Muscle },
            { VehicleClass.SportsClassics, VehicleList.Sportsclassics },
            { VehicleClass.Sports,         VehicleList.Sports },
            { VehicleClass.Super,          VehicleList.Super },
            { VehicleClass.OffRoad,        VehicleList.Offroad },
            { VehicleClass.Motorcycles,    VehicleList.Motorcycles },
            { VehicleClass.Vans,           VehicleList.Vans },
        };

        // Explicit review of the expanded built-in catalog, not a blanket opt-in
        // by class: drift/race, armed, arena and specialist variants stay out.
        // Keep these outside VehicleList so GBAY prices/preview ordering and
        // third-party receipt/capability authorization remain unchanged.
        private static readonly string[] REVIEWED_CIVILIAN_SUPPLEMENT =
        {
            "alpha", "blade", "blista2", "brigham", "broadway", "btype", "btype3",
            "calico", "cheburek", "coquette2", "dubsta3", "dukes", "dynasty",
            "eudora", "fagaloa", "furoregt", "glendale", "greenwood", "huntley",
            "jester", "massacro", "panto", "peyote3", "pigalle", "ratloader2",
            "retinue2", "rhapsody", "slamvan", "slamvan3", "stalion", "tornado5",
            "turismor", "virgo", "voodoo", "warrener", "xls", "zentorno",
        };

        internal static int AddReviewedCivilianSupplement(
            IDictionary<VehicleClass, List<string>> pools)
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var pool in pools.Values)
                foreach (string model in pool) seen.Add(model);
            int added = 0;
            foreach (string model in REVIEWED_CIVILIAN_SUPPLEMENT)
            {
                if (!CatalogOnlyVehicles.Records.TryGetValue(model, out var record)
                    || record.Storage != "garage" || record.Price <= 0
                    || !TryMapPackageRoadCategory(record.Category, out var category)
                    || !seen.Add(model)) continue;
                if (!pools.TryGetValue(category, out var pool))
                    pools[category] = pool = new List<string>();
                pool.Add(model);
                added++;
            }
            return added;
        }

        // Package catalog categories are deliberately mapped through a strict
        // allow-list. Add-on aircraft, boats, emergency vehicles, and other
        // non-road content must never enter either traffic path by accident.
        private static readonly Dictionary<string, VehicleClass>
            PACKAGE_ROAD_CLASS_MAP =
                new Dictionary<string, VehicleClass>(
                    StringComparer.OrdinalIgnoreCase)
        {
            { "compacts",       VehicleClass.Compacts },
            { "coupes",         VehicleClass.Coupes },
            { "sedans",         VehicleClass.Sedans },
            { "suvs",           VehicleClass.SUVs },
            { "muscle",         VehicleClass.Muscle },
            { "sports",         VehicleClass.Sports },
            { "sportsclassics", VehicleClass.SportsClassics },
            { "super",          VehicleClass.Super },
            { "offroad",        VehicleClass.OffRoad },
            { "motorcycles",    VehicleClass.Motorcycles },
            { "vans",           VehicleClass.Vans },
        };

        internal enum PackageTrafficCandidateDecision
        {
            Eligible,
            TrafficDisabled,
            MissingModel,
            UnsupportedCategory,
            ModelUnavailable,
            NotVehicle,
            ClassMismatch,
            DuplicateModel,
        }

        internal enum ReplacementValidationOutcome
        {
            Ready,
            CloneFailed,
            CommitBlocked,
            SourceChanged,
        }

        // --- Logging ---
        private static readonly string LOG_PATH = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.log");

        // --- State ---
        private readonly List<ManagedTraffic> _spawned =
            new List<ManagedTraffic>();
        private readonly List<string> _validModels = new List<string>();
        private readonly Dictionary<VehicleClass, List<string>> _classPools =
            new Dictionary<VehicleClass, List<string>>();
        private readonly Dictionary<string, double> _trafficWeights =
            new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
        private readonly SelectedModelValidationCache _modelValidation =
            new SelectedModelValidationCache();
        private readonly HashSet<int> _seenVehicleHandles = new HashSet<int>();
        private readonly Queue<KeyValuePair<int, int>> _seenVehicleOrder =
            new Queue<KeyValuePair<int, int>>();
        private readonly Dictionary<int, int> _recentPlayerVehicleHandles =
            new Dictionary<int, int>();
        private readonly List<int> _expiredPlayerVehicleHandles =
            new List<int>();
        private readonly HashSet<int> _dlcModelHashes = new HashSet<int>();
        private readonly Random _rng = new Random();
        private int _lastDrivenTime;
        private int _lastScanTime;
        private int _lastCleanupTime;
        private int _lastPlayerProtectionPruneTime;
        private int _lastSourceChangeDiagnosticTime = int.MinValue;
        private int _sourceChangeSkipCount;
        private int _lastTrafficWorkTime;
        private int _lastActivityDiagnosticTime;
        private int _drivenAttemptsSinceDiagnostic;
        private int _drivenSuccessesSinceDiagnostic;
        private int _replacementScansSinceDiagnostic;
        private bool _preferReplacementWork;
        private bool _initialized;
        private bool _enabled = true;
        private string _lastSuppressionReason = "";
        private const int PLAYER_INTERACTION_PROTECTION_MS = 120000;
        private const int MAX_SCAN_CANDIDATES = 24;
        private const int THROTTLED_SCAN_CANDIDATES = 12;
        private const int MAX_REPLACEMENTS_PER_SCAN = 1;
        private const int SEEN_HANDLE_TTL_MS = 90000;
        private const int MAX_TRACKED_SEEN_HANDLES = 512;
        private const float MAX_PARKED_REPLACEMENT_SPEED = 0.75f;
        private const int SOURCE_CHANGE_DIAGNOSTIC_INTERVAL_MS = 30000;
        // Vehicle streaming, creation, ped setup, and replacement cloning are
        // the expensive operations in this service. The old independent
        // 5-second/3-second clocks could run both paths together and produced
        // hundreds of stream/create attempts in a short play session. One
        // staggered budget keeps traffic varied without periodic burst work.
        private const int TRAFFIC_WORK_INTERVAL_MS = 15000;
        private const int THROTTLED_TRAFFIC_WORK_INTERVAL_MS = 30000;
        private const int ACTIVITY_DIAGNOSTIC_INTERVAL_MS = 60000;

        internal enum TrafficWorkKind
        {
            None,
            DrivenSpawn,
            ReplacementScan,
        }

        private sealed class SafehouseGarageZone
        {
            internal readonly Vector3 Center;
            internal readonly float Radius;
            internal readonly float VerticalTolerance;

            internal SafehouseGarageZone(
                float x, float y, float z, float radius, float verticalTolerance)
            {
                Center = new Vector3(x, y, z);
                Radius = radius;
                VerticalTolerance = verticalTolerance;
            }
        }

        // Tight zones around Story Mode storage, not general neighborhoods.
        // Parked ambient traffic everywhere else remains eligible.
        private static readonly SafehouseGarageZone[] SAFEHOUSE_GARAGE_ZONES =
        {
            new SafehouseGarageZone(-807.7f, 187.0f, 72.5f, 14f, 8f),
            new SafehouseGarageZone(-25.3f, -1431.1f, 30.8f, 12f, 7f),
            new SafehouseGarageZone(13.5f, 549.2f, 175.7f, 14f, 8f),
            new SafehouseGarageZone(1977.0f, 3823.0f, 32.5f, 18f, 8f),
            new SafehouseGarageZone(-1151.8f, -1518.1f, 10.6f, 16f, 8f),
            new SafehouseGarageZone(98.0f, -1290.0f, 29.3f, 20f, 8f),
        };

        private sealed class ManagedTraffic
        {
            internal Vehicle Vehicle;
            internal Ped Driver;
            internal List<Ped> Occupants;
            internal bool RequiresDriver;
        }

        private sealed class AmbientOccupant
        {
            internal Ped SourcePed;
            internal Ped ClonePed;
            internal int SourceSeat;
            internal int TargetSeat;
        }

        internal enum ManagedTrafficAction
        {
            Keep,
            Release,
            Delete,
        }

        public TrafficSpawner()
        {
            bool packageEnabled = Allin1ExtensionApi.IsPackageEnabled(
                Allin1ExtensionApi.OnlineContentPackageId);
            if (!packageEnabled)
            {
                _enabled = false;
                PauseReason = "content package disabled";
                Interval = 1000;
                return;
            }
            LoadSettings();
            if (!ShouldAttachRuntimeHandlers(packageEnabled, _enabled))
            {
                PauseReason = "traffic disabled in settings";
                Interval = 1000;
                return;
            }
            Tick += OnTick;
            // Traffic work is proximity/cooldown based and does not need to run
            // at rendering frequency. This substantially reduces idle CPU use.
            Interval = 100;

            Function.Call(Hash.DECOR_REGISTER, "MPBitset", 3);
        }

        internal static bool ShouldAttachRuntimeHandlers(
            bool packageEnabled, bool trafficEnabled)
        {
            return packageEnabled && trafficEnabled;
        }

        private void LoadSettings()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.toml");
            if (!File.Exists(path)) return;
            try
            {
                string section = "";
                foreach (string raw in File.ReadAllLines(path))
                {
                    string line = raw.Trim();
                    if (line.StartsWith("[") && line.EndsWith("]"))
                    { section = line.Substring(1, line.Length - 2).ToLowerInvariant(); continue; }
                    if (section != "traffic" || line.StartsWith("#")) continue;
                    int eq = line.IndexOf('='); if (eq < 1) continue;
                    string key = line.Substring(0, eq).Trim().ToLowerInvariant();
                    string value = line.Substring(eq + 1).Trim();
                    if (key == "enabled") _enabled = value.Equals("true", StringComparison.OrdinalIgnoreCase);
                    else if (key == "max_driven" && int.TryParse(value, out int md)) _maxDriven = Math.Max(0, Math.Min(100, md));
                    else if (key == "spawn_distance_min" && float.TryParse(value, out float smin)) _spawnDistMin = smin;
                    else if (key == "spawn_distance_max" && float.TryParse(value, out float smax)) _spawnDistMax = smax;
                    else if (key == "cleanup_distance" && float.TryParse(value, out float clean)) _cleanupDist = clean;
                    else if (key == "driven_cooldown_ms" && int.TryParse(value, out int dc)) _drivenCooldownMs = dc;
                    else if (key == "scan_cooldown_ms" && int.TryParse(value, out int sc)) _scanCooldownMs = sc;
                    else if (key == "scan_radius" && float.TryParse(value, out float sr)) _scanRadius = sr;
                    else if (key == "minimum_replace_distance" && float.TryParse(value, out float mr)) _minReplaceDist = mr;
                    else if (key == "replacement_chance" && float.TryParse(value, out float rc)) _replaceChance = rc;
                    else if (key == "adaptive_performance") _adaptivePerformance = value.Equals("true", StringComparison.OrdinalIgnoreCase);
                    else if (key == "minimum_fps" && int.TryParse(value, out int fps)) _minimumFps = Math.Max(20, Math.Min(120, fps));
                }
                ClientLog.Info("Traffic", "settings_loaded", new Dictionary<string, object> {
                    { "max_driven", _maxDriven }, { "replacement_chance", _replaceChance }
                });
            }
            catch (Exception ex) { ClientLog.Error("Traffic", "settings_load_failed", ex); }
        }

        // ------------------------------------------------------------------ //
        //  Logging                                                            //
        // ------------------------------------------------------------------ //

        private void Log(string msg)
        {
            ClientLog.Info("Traffic", msg);
        }

        // ------------------------------------------------------------------ //
        //  Main loop                                                          //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            UpdatePerformanceSample();
            ManagedVehicleCount = _spawned.Count;

            if (!_enabled)
            {
                PauseReason = "disabled in settings";
                return;
            }
            if (ClientWatchdog.SafeMode)
            {
                PauseReason = ClientWatchdog.SafeModeReason;
                return;
            }
            if (Game.IsLoading)
            {
                PauseReason = "game loading";
                return;
            }

            string suppression = GetSuppressionReason();
            if (suppression.Length > 0)
            {
                PauseReason = suppression.Replace('_', ' ');
                if (suppression != _lastSuppressionReason)
                    ClientLog.Info("Traffic", "spawning_suppressed",
                        new Dictionary<string, object> { { "reason", suppression } });
                _lastSuppressionReason = suppression;

                // Do not request/reap traffic models while the garage owns
                // streaming. Leave a full work interval for world settling.
                if (suppression == "garage_transition")
                {
                    _lastTrafficWorkTime = Game.GameTime;
                    return;
                }

                // Suppression must stop existing ALLIN1 traffic as well as
                // new spawns. Previously this early return skipped cleanup,
                // allowing GTA to reap a released driver while its vehicle
                // survived into a mission as an empty moving car.
                Cleanup(ShouldPurgeManagedTraffic(suppression));
                return;
            }
            _lastSuppressionReason = "";
            PauseReason = "";

            if (!_initialized)
            {
                PauseReason = "initializing";
                Initialize();
                return;
            }

            if (_validModels.Count == 0)
            {
                PauseReason = "no valid vehicle models";
                return;
            }

            int now = Game.GameTime;
            RememberPlayerVehicles(Game.Player.Character, now);
            _throttled = _adaptivePerformance && _smoothedFps < _minimumFps;
            IsThrottled = _throttled;
            if (now - _lastCleanupTime >= 1000)
            {
                Cleanup(false);
                _lastCleanupTime = now;
            }

            // Driven spawner
            int effectiveMax = _throttled ? Math.Max(2, _maxDriven / 2) : _maxDriven;
            int effectiveDrivenCooldown = _throttled ? _drivenCooldownMs * 2 : _drivenCooldownMs;
            int effectiveScanCooldown = _throttled ? _scanCooldownMs * 2 : _scanCooldownMs;
            bool drivenDue = _maxDriven > 0 && _spawned.Count < effectiveMax
                && unchecked((uint)(now - _lastDrivenTime)) >=
                    (uint)Math.Max(0, effectiveDrivenCooldown);
            bool scanDue = _replaceChance > 0f
                && unchecked((uint)(now - _lastScanTime)) >=
                    (uint)Math.Max(0, effectiveScanCooldown);
            if (IsTrafficWorkDue(now, _lastTrafficWorkTime, _throttled))
            {
                TrafficWorkKind work = SelectTrafficWork(
                    drivenDue, scanDue, _preferReplacementWork);
                if (work != TrafficWorkKind.None)
                {
                    // Budget attempts rather than only successful mutations.
                    // A failed stream or road-node lookup must not retry every
                    // 100 ms and turn a transient condition into a hitch loop.
                    _lastTrafficWorkTime = now;
                    if (work == TrafficWorkKind.DrivenSpawn)
                    {
                        _lastDrivenTime = now;
                        _drivenAttemptsSinceDiagnostic++;
                        if (SpawnDriven()) _drivenSuccessesSinceDiagnostic++;
                        _preferReplacementWork = true;
                    }
                    else
                    {
                        _lastScanTime = now;
                        _replacementScansSinceDiagnostic++;
                        ScanAndReplace();
                        _preferReplacementWork = false;
                    }
                }
            }
            EmitActivityDiagnostic(now);
        }

        internal static bool IsTrafficWorkDue(
            int now, int lastWorkTime, bool throttled)
        {
            int interval = throttled
                ? THROTTLED_TRAFFIC_WORK_INTERVAL_MS
                : TRAFFIC_WORK_INTERVAL_MS;
            return unchecked((uint)(now - lastWorkTime)) >= (uint)interval;
        }

        internal static TrafficWorkKind SelectTrafficWork(
            bool drivenDue, bool replacementDue, bool preferReplacement)
        {
            if (drivenDue && replacementDue)
                return preferReplacement
                    ? TrafficWorkKind.ReplacementScan
                    : TrafficWorkKind.DrivenSpawn;
            if (drivenDue) return TrafficWorkKind.DrivenSpawn;
            if (replacementDue) return TrafficWorkKind.ReplacementScan;
            return TrafficWorkKind.None;
        }

        private void EmitActivityDiagnostic(int now)
        {
            if (unchecked((uint)(now - _lastActivityDiagnosticTime)) <
                    (uint)ACTIVITY_DIAGNOSTIC_INTERVAL_MS)
                return;
            _lastActivityDiagnosticTime = now;
            ClientLog.Info("Traffic", "activity_summary",
                new Dictionary<string, object>
                {
                    { "driven_attempts", _drivenAttemptsSinceDiagnostic },
                    { "driven_successes", _drivenSuccessesSinceDiagnostic },
                    { "replacement_scans", _replacementScansSinceDiagnostic },
                    { "managed", _spawned.Count },
                    { "smoothed_fps", Math.Round(_smoothedFps, 1) },
                    { "throttled", _throttled },
                });
            _drivenAttemptsSinceDiagnostic = 0;
            _drivenSuccessesSinceDiagnostic = 0;
            _replacementScansSinceDiagnostic = 0;
        }

        private void UpdatePerformanceSample()
        {
            float frameTime = Function.Call<float>(Hash.GET_FRAME_TIME);
            if (frameTime > 0.0001f)
                _smoothedFps = _smoothedFps * 0.92f + (1f / frameTime) * 0.08f;
            SmoothedFps = _smoothedFps;
        }

        private static string GetSuppressionReason()
        {
            if (GarageManager.TransitionInProgress) return "garage_transition";
            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead) return "player_unavailable";
            if (Game.Player.WantedLevel > 0) return "wanted_level";
            if (Function.Call<bool>(Hash.GET_MISSION_FLAG)) return "mission_active";
            if (Function.Call<bool>(Hash.IS_CUTSCENE_ACTIVE)) return "cutscene_active";
            if (Function.Call<bool>(Hash.IS_PLAYER_SWITCH_IN_PROGRESS)) return "player_switch";
            if (Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY, player.Handle) != 0) return "interior";
            return "";
        }

        internal static bool ShouldPurgeManagedTraffic(string suppression)
        {
            return suppression == "mission_active"
                || suppression == "cutscene_active"
                || suppression == "player_switch"
                || suppression == "interior"
                || suppression == "wanted_level";
        }

        internal static bool IsPackageTrafficEnabled(
            bool itemTrafficEnabled, bool packageTrafficEnabled)
        {
            return itemTrafficEnabled && packageTrafficEnabled;
        }

        internal static bool TryMapPackageRoadCategory(
            string category, out VehicleClass vehicleClass)
        {
            vehicleClass = default(VehicleClass);
            if (string.IsNullOrWhiteSpace(category)) return false;
            return PACKAGE_ROAD_CLASS_MAP.TryGetValue(
                category.Trim(), out vehicleClass);
        }

        internal static PackageTrafficCandidateDecision
            EvaluatePackageTrafficCandidate(
                bool effectiveTrafficEnabled,
                string modelName,
                string category,
                bool isInCdImage,
                bool isVehicle,
                VehicleClass actualClass,
                out VehicleClass declaredClass)
        {
            declaredClass = default(VehicleClass);
            if (!effectiveTrafficEnabled)
                return PackageTrafficCandidateDecision.TrafficDisabled;
            if (string.IsNullOrWhiteSpace(modelName))
                return PackageTrafficCandidateDecision.MissingModel;
            if (!TryMapPackageRoadCategory(category, out declaredClass))
                return PackageTrafficCandidateDecision.UnsupportedCategory;
            if (!isInCdImage)
                return PackageTrafficCandidateDecision.ModelUnavailable;
            if (!isVehicle)
                return PackageTrafficCandidateDecision.NotVehicle;
            if (actualClass != declaredClass)
                return PackageTrafficCandidateDecision.ClassMismatch;
            return PackageTrafficCandidateDecision.Eligible;
        }

        private static double GetPackageTrafficWeight(double configuredWeight)
        {
            // The package parser validates this range. Keep a defensive bound
            // here so a malformed runtime record cannot inflate hot-path pools.
            if (double.IsNaN(configuredWeight) ||
                double.IsInfinity(configuredWeight))
                return 1d;
            return Math.Max(0.1d, Math.Min(20d, configuredWeight));
        }

        private static void LogPackageTrafficRejection(
            GbayVehicleRecord entry,
            string modelName,
            PackageTrafficCandidateDecision decision,
            string actualClass = "")
        {
            ClientLog.Warn("Traffic", "package_model_rejected",
                new Dictionary<string, object>
                {
                    { "package_id", entry?.PackageId ?? "" },
                    { "catalog_id", entry?.CatalogId ?? "" },
                    { "model", modelName ?? "" },
                    { "category", entry?.Category ?? "" },
                    { "reason", PackageTrafficDecisionCode(decision) },
                    { "actual_class", actualClass ?? "" }
                });
        }

        private static string PackageTrafficDecisionCode(
            PackageTrafficCandidateDecision decision)
        {
            switch (decision)
            {
                case PackageTrafficCandidateDecision.TrafficDisabled:
                    return "traffic_disabled";
                case PackageTrafficCandidateDecision.MissingModel:
                    return "missing_model";
                case PackageTrafficCandidateDecision.UnsupportedCategory:
                    return "unsupported_category";
                case PackageTrafficCandidateDecision.ModelUnavailable:
                    return "model_unavailable";
                case PackageTrafficCandidateDecision.NotVehicle:
                    return "not_vehicle";
                case PackageTrafficCandidateDecision.ClassMismatch:
                    return "class_mismatch";
                case PackageTrafficCandidateDecision.DuplicateModel:
                    return "duplicate_model";
                default:
                    return "eligible";
            }
        }

        // ------------------------------------------------------------------ //
        //  Initialization                                                     //
        // ------------------------------------------------------------------ //

        private void Initialize()
        {
            var initialization = Stopwatch.StartNew();
            _validModels.Clear();
            _classPools.Clear();
            _trafficWeights.Clear();
            _modelValidation.Clear();
            _dlcModelHashes.Clear();

            // Build per-class pools of validated models.
            foreach (var entry in CLASS_MAP)
            {
                if (!_classPools.ContainsKey(entry.Key))
                    _classPools[entry.Key] = new List<string>();

                foreach (string name in entry.Value)
                {
                    // VehicleList is generated from reviewed data, but game
                    // editions do not necessarily expose every listed model.
                    // Defer the native-backed check until a model is selected,
                    // then cache or quarantine it for the rest of the session.
                    if (!string.IsNullOrWhiteSpace(name))
                        _classPools[entry.Key].Add(name);
                }
            }

            // Both driven spawns and class-matched replacements consume these
            // same reviewed pools. Native model availability is still checked
            // lazily on selection, with unavailable models quarantined.
            int supplementalAccepted = AddReviewedCivilianSupplement(_classPools);

            // Build the flat list for driven spawner (union of all class pools).
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var pool in _classPools.Values)
            {
                foreach (string name in pool)
                {
                    if (seen.Add(name))
                    {
                        _validModels.Add(name);
                        _trafficWeights[name] = 1d;
                    }
                }
            }

            int packageDeclared = 0;
            int packageAccepted = 0;
            try
            {
                // TrafficEntries is already receipt-authorized and runtime-
                // validated by RuntimeVehicleCatalog. Accessing it initializes
                // the catalog only when needed; do not force a second refresh.
                var packageEntries = new List<GbayVehicleRecord>(
                    RuntimeVehicleCatalog.TrafficEntries);
                packageEntries.Sort((left, right) =>
                {
                    int result = string.Compare(
                        left?.PackageId, right?.PackageId,
                        StringComparison.OrdinalIgnoreCase);
                    if (result != 0) return result;
                    result = string.Compare(
                        left?.CatalogId, right?.CatalogId,
                        StringComparison.OrdinalIgnoreCase);
                    if (result != 0) return result;
                    return string.Compare(
                        left?.Model, right?.Model,
                        StringComparison.OrdinalIgnoreCase);
                });
                packageDeclared = packageEntries.Count;

                foreach (GbayVehicleRecord entry in packageEntries)
                {
                    if (entry == null)
                    {
                        ClientLog.Warn("Traffic", "package_model_rejected",
                            new Dictionary<string, object>
                            {
                                { "reason", "missing_record" }
                            });
                        continue;
                    }

                    string modelName = (entry.Model ?? "").Trim()
                        .ToLowerInvariant();
                    if (!entry.TrafficEnabled)
                    {
                        LogPackageTrafficRejection(
                            entry, modelName,
                            PackageTrafficCandidateDecision.TrafficDisabled);
                        continue;
                    }
                    if (string.IsNullOrWhiteSpace(modelName))
                    {
                        LogPackageTrafficRejection(
                            entry, modelName,
                            PackageTrafficCandidateDecision.MissingModel);
                        continue;
                    }
                    if (!TryMapPackageRoadCategory(
                            entry.Category, out VehicleClass declaredClass))
                    {
                        LogPackageTrafficRejection(
                            entry, modelName,
                            PackageTrafficCandidateDecision.UnsupportedCategory);
                        continue;
                    }

                    bool runtimeValidated =
                        entry.HasValidatedRuntimeVehicleClass;
                    VehicleClass actualClass = runtimeValidated
                        ? entry.ValidatedRuntimeVehicleClass : declaredClass;
                    PackageTrafficCandidateDecision decision =
                        EvaluatePackageTrafficCandidate(
                            true,
                            modelName,
                            entry.Category,
                            runtimeValidated,
                            runtimeValidated,
                            actualClass,
                            out declaredClass);

                    if (decision != PackageTrafficCandidateDecision.Eligible)
                    {
                        LogPackageTrafficRejection(
                            entry, modelName, decision,
                            actualClass.ToString());
                        continue;
                    }

                    // Static ALLIN1 models and the first package owner win.
                    // This prevents duplicate weighting and ambiguous ownership
                    // when multiple packages declare the same spawn name.
                    if (!seen.Add(modelName))
                    {
                        LogPackageTrafficRejection(
                            entry, modelName,
                            PackageTrafficCandidateDecision.DuplicateModel,
                            actualClass.ToString());
                        continue;
                    }

                    double weight = GetPackageTrafficWeight(
                        entry.TrafficWeight);
                    List<string> classPool = _classPools[declaredClass];
                    classPool.Add(modelName);
                    _validModels.Add(modelName);
                    _trafficWeights[modelName] = weight;
                    _modelValidation.MarkValidated(modelName);
                    packageAccepted++;
                    ClientLog.Info("Traffic", "package_model_accepted",
                        new Dictionary<string, object>
                        {
                            { "package_id", entry.PackageId ?? "" },
                            { "catalog_id", entry.CatalogId ?? "" },
                            { "model", modelName },
                            { "category", entry.Category ?? "" },
                            { "weight", weight }
                        });
                }
            }
            catch (Exception ex)
            {
                // Package catalog failures must not disable built-in traffic.
                ClientLog.Error("Traffic", "package_catalog_load_failed", ex);
            }

            // Build hash set of all managed traffic model hashes so the scanner
            // never replaces a built-in or package vehicle it already injected.
            foreach (string name in seen)
                _dlcModelHashes.Add(
                    Function.Call<int>(Hash.GET_HASH_KEY, name));

            int now = Game.GameTime;
            _lastDrivenTime = now;
            _lastScanTime = now;
            _lastTrafficWorkTime = now;
            _lastActivityDiagnosticTime = now;
            _initialized = true;

            int total = 0;
            foreach (var arr in ROAD_CLASSES)
                total += arr.Length;
            total += supplementalAccepted;

            initialization.Stop();
            ClientLog.Info("Traffic", "catalog_initialized",
                new Dictionary<string, object>
                {
                    { "models", seen.Count },
                    { "declared_models", total + packageDeclared },
                    { "curated_models", total },
                    { "supplemental_civilian_models", supplementalAccepted },
                    { "package_models", packageAccepted },
                    { "package_declared", packageDeclared },
                    { "runtime_probes", 0 },
                    { "cached_package_validations", packageAccepted },
                    { "lazy_validation_pending", seen.Count - packageAccepted },
                    { "elapsed_ms", initialization.ElapsedMilliseconds },
                });

            GTA.UI.Notification.Show(
                $"~g~ALLIN1~w~: {seen.Count}/{total + packageDeclared} " +
                "traffic models available");
        }

        internal enum SelectedModelValidationAction
        {
            UseCachedValidation,
            ProbeOnce,
            RejectQuarantined,
        }

        internal static SelectedModelValidationAction DecideSelectedModelValidation(
            bool validated, bool quarantined)
        {
            if (quarantined)
                return SelectedModelValidationAction.RejectQuarantined;
            return validated
                ? SelectedModelValidationAction.UseCachedValidation
                : SelectedModelValidationAction.ProbeOnce;
        }

        internal sealed class SelectedModelValidationCache
        {
            private readonly HashSet<string> _validated =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            private readonly HashSet<string> _quarantined =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            internal SelectedModelValidationAction GetAction(string modelName)
            {
                return DecideSelectedModelValidation(
                    _validated.Contains(modelName ?? ""),
                    _quarantined.Contains(modelName ?? ""));
            }

            internal void MarkValidated(string modelName)
            {
                if (string.IsNullOrWhiteSpace(modelName)) return;
                _quarantined.Remove(modelName);
                _validated.Add(modelName);
            }

            internal bool Quarantine(string modelName)
            {
                if (string.IsNullOrWhiteSpace(modelName)) return false;
                _validated.Remove(modelName);
                return _quarantined.Add(modelName);
            }

            internal void Clear()
            {
                _validated.Clear();
                _quarantined.Clear();
            }
        }

        // ------------------------------------------------------------------ //
        //  Driven spawner (unchanged logic)                                   //
        // ------------------------------------------------------------------ //

        // Known ped models for fallback driver creation
        private static readonly string[] FALLBACK_PED_MODELS =
        {
            "a_m_y_business_01", "a_m_y_downtown_01", "a_m_y_stwhi_02",
            "a_f_y_business_01", "a_m_m_afriamer_01", "a_m_y_genstreet_01",
            "a_f_y_tourist_01", "a_m_y_latino_01",
        };

        private string SelectWeightedTrafficModel(IReadOnlyList<string> pool)
        {
            if (pool == null || pool.Count == 0) return null;
            double totalWeight = 0d;
            foreach (string modelName in pool)
            {
                if (!_trafficWeights.TryGetValue(
                        modelName, out double weight))
                    weight = 1d;
                if (weight > 0d && !double.IsNaN(weight) &&
                    !double.IsInfinity(weight))
                    totalWeight += weight;
            }
            if (totalWeight <= 0d || double.IsNaN(totalWeight) ||
                double.IsInfinity(totalWeight))
                return pool[_rng.Next(pool.Count)];

            double selection = _rng.NextDouble() * totalWeight;
            foreach (string modelName in pool)
            {
                if (!_trafficWeights.TryGetValue(
                        modelName, out double weight))
                    weight = 1d;
                if (weight <= 0d || double.IsNaN(weight) ||
                    double.IsInfinity(weight))
                    continue;
                selection -= weight;
                if (selection <= 0d) return modelName;
            }
            return pool[pool.Count - 1];
        }

        private bool SpawnDriven()
        {
            Vector3 playerPos = Game.Player.Character.Position;

            if (!FindRoadNode(playerPos, _spawnDistMin, _spawnDistMax,
                              out Vector3 nodePos, out float heading))
                return false;

            string modelName = SelectWeightedTrafficModel(_validModels);
            Vehicle veh = LoadAndCreateVehicle(modelName, nodePos, heading);
            if (veh == null)
                return false;

            // Give the game a frame to fully register the vehicle entity
            // before attempting ped creation — may fix intermittent failures.
            Script.Wait(0);

            ReleaseVehiclePhysics(veh, true);

            // Attempt 1: Let the game pick a random ped model
            Ped driver = null;
            string pedMethod = "random";
            try
            {
                driver = veh.CreateRandomPedOnSeat(VehicleSeat.Driver);
            }
            catch (Exception ex)
            {
                Log($"  attempt1 (random) exception: {ex.Message}");
            }

            bool driverExists = driver != null && driver.Exists();
            bool seatFree = driverExists ? veh.IsSeatFree(VehicleSeat.Driver) : true;

            // Attempt 2: If random ped failed, try explicit ped model
            if (!driverExists || seatFree)
            {
                // Clean up failed attempt
                if (driverExists)
                {
                    driver.IsPersistent = true;
                    driver.Delete();
                }

                pedMethod = "explicit";
                string pedModelName = FALLBACK_PED_MODELS[
                    _rng.Next(FALLBACK_PED_MODELS.Length)];

                var pedModel = new Model(pedModelName);
                pedModel.Request();
                var pedLoadWait = Stopwatch.StartNew();
                while (!pedModel.IsLoaded)
                {
                    if (HasModelLoadTimedOut(
                            pedLoadWait.ElapsedMilliseconds,
                            MODEL_LOAD_TIMEOUT))
                    {
                        Log($"  attempt2 (explicit): ped model {pedModelName} load TIMEOUT");
                        break;
                    }
                    Script.Wait(0);
                }

                if (pedModel.IsLoaded)
                {
                    try
                    {
                        driver = veh.CreatePedOnSeat(VehicleSeat.Driver, pedModel);
                    }
                    catch (Exception ex)
                    {
                        Log($"  attempt2 (explicit) exception: {ex.Message}");
                    }

                    pedModel.MarkAsNoLongerNeeded();
                }

                driverExists = driver != null && driver.Exists();
                seatFree = driverExists ? veh.IsSeatFree(VehicleSeat.Driver) : true;
            }

            // Attempt 3: Raw native as last resort
            if (!driverExists || seatFree)
            {
                if (driverExists)
                {
                    driver.IsPersistent = true;
                    driver.Delete();
                }

                pedMethod = "native";
                string nativePedName = FALLBACK_PED_MODELS[
                    _rng.Next(FALLBACK_PED_MODELS.Length)];
                int pedHash = Function.Call<int>(Hash.GET_HASH_KEY, nativePedName);
                Function.Call(Hash.REQUEST_MODEL, pedHash);

                DateTime deadline = DateTime.UtcNow.AddMilliseconds(MODEL_LOAD_TIMEOUT);
                while (!Function.Call<bool>(Hash.HAS_MODEL_LOADED, pedHash))
                {
                    if (DateTime.UtcNow > deadline)
                    {
                        Log($"  attempt3 (native): ped model {nativePedName} load TIMEOUT");
                        break;
                    }
                    Script.Wait(0);
                }

                if (Function.Call<bool>(Hash.HAS_MODEL_LOADED, pedHash))
                {
                    driver = Function.Call<Ped>(
                        Hash.CREATE_PED_INSIDE_VEHICLE,
                        veh.Handle, 26, pedHash, -1, true, true);
                    Function.Call(Hash.SET_MODEL_AS_NO_LONGER_NEEDED, pedHash);
                }

                driverExists = driver != null && driver.Exists();
                seatFree = driverExists ? veh.IsSeatFree(VehicleSeat.Driver) : true;
            }

            // If all attempts failed, delete the empty vehicle
            if (!driverExists || seatFree)
            {
                ClientLog.Warn("Traffic", "driven_spawn_failed",
                    new Dictionary<string, object>
                    {
                        { "model", modelName },
                        { "method", pedMethod },
                    });
                veh.IsPersistent = true;
                veh.Delete();
                if (driverExists)
                {
                    driver.IsPersistent = true;
                    driver.Delete();
                }
                return false;
            }

            // Prevent ambient events from making the ped exit
            Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                driver.Handle, true);

            ConfigureAmbientDriver(driver, veh, 20f, keepPersistent: true);

            // Keep the pair together while ALLIN1 owns it. Releasing the ped
            // independently allowed GTA cleanup to remove the driver while
            // MPBitset kept the vehicle alive.
            _spawned.Add(new ManagedTraffic
            {
                Vehicle = veh,
                Driver = driver,
                Occupants = new List<Ped> { driver },
                RequiresDriver = true,
            });
            return true;
        }

        // ------------------------------------------------------------------ //
        //  Replacement scanner                                                //
        // ------------------------------------------------------------------ //

        private void ScanAndReplace()
        {
            Ped player = Game.Player.Character;
            if (player == null || !player.Exists()) return;
            Vector3 playerPos = player.Position;
            int now = Game.GameTime;

            Vehicle[] nearby;
            try
            {
                nearby = World.GetNearbyVehicles(player, _scanRadius);
            }
            catch
            {
                return; // GetNearbyVehicles can throw on some SHVDN versions
            }

            if (nearby == null)
                return;

            ExpireSeenVehicleHandles(now);
            int candidatesInspected = 0;
            int replacementAttempts = 0;
            int candidateBudget = GetScanCandidateBudget(_throttled);

            foreach (Vehicle veh in nearby)
            {
                if (candidatesInspected >= candidateBudget
                    || replacementAttempts >= MAX_REPLACEMENTS_PER_SCAN)
                    break;
                if (veh == null || !veh.Exists())
                    continue;

                int handle = veh.Handle;
                if (_seenVehicleHandles.Contains(handle))
                    continue;
                TrackSeenVehicle(handle, now);
                candidatesInspected++;

                if (!IsEligibleForReplacement(veh, player, playerPos))
                    continue;

                // 30 % replacement chance
                if (_rng.NextDouble() > _replaceChance)
                    continue;

                // Class-matched model lookup
                VehicleClass cls = veh.ClassType;
                if (!_classPools.TryGetValue(cls, out List<string> pool)
                    || pool.Count == 0)
                    continue;

                string newModelName = SelectWeightedTrafficModel(pool);
                if (IsProtectedFromTrafficReplacement(veh, player))
                    continue;
                replacementAttempts++;
                ReplaceVehicle(veh, newModelName);
            }
        }

        internal static int GetScanCandidateBudget(bool throttled)
        {
            return throttled
                ? THROTTLED_SCAN_CANDIDATES : MAX_SCAN_CANDIDATES;
        }

        private void TrackSeenVehicle(int handle, int now)
        {
            if (handle == 0 || !_seenVehicleHandles.Add(handle)) return;
            _seenVehicleOrder.Enqueue(new KeyValuePair<int, int>(handle, now));
            ExpireSeenVehicleHandles(now);
        }

        private void ExpireSeenVehicleHandles(int now)
        {
            while (_seenVehicleOrder.Count > 0)
            {
                KeyValuePair<int, int> oldest = _seenVehicleOrder.Peek();
                uint age = unchecked((uint)(now - oldest.Value));
                bool expired = age > SEEN_HANDLE_TTL_MS;
                bool overCapacity = _seenVehicleOrder.Count
                    > MAX_TRACKED_SEEN_HANDLES;
                if (!expired && !overCapacity) break;
                _seenVehicleOrder.Dequeue();
                _seenVehicleHandles.Remove(oldest.Key);
            }
        }

        private bool IsEligibleForReplacement(Vehicle veh, Ped player,
                                               Vector3 playerPos)
        {
            if (veh == null || !veh.Exists())
                return false;

            // Player's own vehicle
            Vehicle currentVeh = player.CurrentVehicle;
            if (currentVeh != null && veh == currentVeh)
                return false;
            Vehicle lastVeh = player.LastVehicle;
            if (lastVeh != null && veh == lastVeh)
                return false;

            // Mission / persistent entities
            if (veh.IsPersistent)
                return false;

            float dist = veh.Position.DistanceTo(playerPos);
            if (dist < _minReplaceDist || veh.IsOnScreen)
                return false;

            // Population type: only ambient/random (1-5)
            int popType = Function.Call<int>(
                Hash.GET_ENTITY_POPULATION_TYPE, veh.Handle);
            if (popType < 1 || popType > 5)
                return false;

            // Skip non-replaceable classes
            VehicleClass cls = veh.ClassType;
            if (!_classPools.ContainsKey(cls))
                return false;

            // Already a DLC vehicle
            int modelHash = Function.Call<int>(
                Hash.GET_ENTITY_MODEL, veh.Handle);
            if (_dlcModelHashes.Contains(modelHash))
                return false;

            // Native decorator checks run only after cheaper filters pass.
            if (IsProtectedFromTrafficReplacement(veh, player))
                return false;

            return true;
        }

        private void RememberPlayerVehicles(Ped player, int now)
        {
            if (player == null || !player.Exists()) return;
            RememberPlayerVehicle(player.CurrentVehicle, now);
            RememberPlayerVehicle(player.LastVehicle, now);

            if (now - _lastPlayerProtectionPruneTime < 1000) return;
            _lastPlayerProtectionPruneTime = now;
            _expiredPlayerVehicleHandles.Clear();
            foreach (var entry in _recentPlayerVehicleHandles)
                if (now - entry.Value > PLAYER_INTERACTION_PROTECTION_MS)
                    _expiredPlayerVehicleHandles.Add(entry.Key);
            foreach (int handle in _expiredPlayerVehicleHandles)
                _recentPlayerVehicleHandles.Remove(handle);
        }

        private void RememberPlayerVehicle(Vehicle vehicle, int now)
        {
            if (vehicle != null && vehicle.Exists())
                _recentPlayerVehicleHandles[vehicle.Handle] = now;
        }

        private bool IsProtectedFromTrafficReplacement(Vehicle vehicle, Ped player)
        {
            if (vehicle == null || !vehicle.Exists()) return true;
            if (vehicle.IsPersistent) return true;
            if (player != null && player.Exists() &&
                (vehicle == player.CurrentVehicle || vehicle == player.LastVehicle))
                return true;
            if (_recentPlayerVehicleHandles.ContainsKey(vehicle.Handle)) return true;
            if (IsInsideSafehouseGarageZone(vehicle.Position)) return true;
            return HasDecorator(vehicle, "Player_Vehicle") ||
                HasDecorator(vehicle, "PV_Slot") ||
                HasDecorator(vehicle, "Veh_Modded_By_Player");
        }

        private static bool HasDecorator(Vehicle vehicle, string name)
        {
            try
            {
                return Function.Call<bool>(
                    (Hash)0x05661B80A8C9165F, vehicle.Handle, name);
            }
            catch { return false; }
        }

        internal static bool IsInsideSafehouseGarageZone(Vector3 position)
        {
            foreach (SafehouseGarageZone zone in SAFEHOUSE_GARAGE_ZONES)
            {
                if (Math.Abs(position.Z - zone.Center.Z) > zone.VerticalTolerance)
                    continue;
                float dx = position.X - zone.Center.X;
                float dy = position.Y - zone.Center.Y;
                if (dx * dx + dy * dy <= zone.Radius * zone.Radius)
                    return true;
            }
            return false;
        }

        private bool ReplaceVehicle(Vehicle old, string newModelName)
        {
            if (IsProtectedFromTrafficReplacement(old, Game.Player.Character))
                return false;

            Vector3 pos = old.Position;
            float heading = old.Heading;
            Vector3 stagingPos = pos + new Vector3(0f, 0f, 50f);
            Vehicle replacement = LoadAndCreateVehicle(
                newModelName, stagingPos, heading, placeOnGround: false);
            if (replacement == null)
            {
                ClientLog.Warn("Traffic", "replacement_stage_failed",
                    new Dictionary<string, object>
                    {
                        { "model", newModelName },
                        { "source_handle", old.Handle }
                });
                return false;
            }

            // Model streaming may yield for several seconds. Capture the
            // source occupants only after that work completes; otherwise GTA
            // can naturally update or reap the ambient source while the model
            // loads, making every later validation fail even for an empty
            // parked car. The source remains untouched during streaming.
            List<AmbientOccupant> occupants = null;
            Ped player = Game.Player.Character;
            if (old == null || !old.Exists()
                || player == null || !player.Exists()
                || IsProtectedFromTrafficReplacement(old, player))
            {
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }
            pos = old.Position;
            heading = old.Heading;
            float speed = old.Speed;
            try
            {
                occupants = CaptureAmbientOccupants(old);
            }
            catch (Exception ex)
            {
                ClientLog.Warn("Traffic", "occupant_capture_failed",
                    new Dictionary<string, object> { { "exception", ex.Message } });
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }

            AmbientOccupant sourceDriver = occupants.Find(
                occupant => occupant.SourceSeat == -1);
            bool hadDriver = sourceDriver != null;
            if (!CanStageSourceReplacement(
                    hadDriver, occupants.Count > 0, speed))
            {
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }
            foreach (AmbientOccupant occupant in occupants)
            {
                if (!occupant.SourcePed.IsPersistent) continue;
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }

            try
            {
                replacement.IsPersistent = true;
                replacement.IsPositionFrozen = true;
                replacement.IsCollisionEnabled = false;
                replacement.IsVisible = false;
                replacement.Position = pos;
                replacement.Heading = heading;
            }
            catch (Exception ex)
            {
                ClientLog.Error("Traffic", "replacement_stage_invalid", ex,
                    new Dictionary<string, object> { { "model", newModelName } });
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }

            bool cloneSettlementRequired = RequiresCloneSettlement(
                occupants.Count);
            bool seatsAssigned = !cloneSettlementRequired ||
                TryAssignReplacementSeats(occupants, replacement);
            bool occupantsCloned = seatsAssigned &&
                (!cloneSettlementRequired ||
                    TryCloneOccupants(occupants, replacement));
            AmbientOccupant clonedDriver = occupants.Find(
                occupant => occupant.SourceSeat == -1
                    && occupant.ClonePed != null
                    && IsPedInVehicleSeat(occupant.ClonePed, replacement, -1));
            bool driverReady = clonedDriver != null;
            bool commitAllowed = CanCommitReplacement(hadDriver, clonedDriver != null);
            bool sourceUnchanged = SourceOccupantsUnchanged(occupants, old);
            ReplacementValidationOutcome validationOutcome =
                EvaluateReplacementValidation(
                    occupantsCloned, commitAllowed, sourceUnchanged);
            if (validationOutcome != ReplacementValidationOutcome.Ready)
            {
                if (validationOutcome ==
                    ReplacementValidationOutcome.SourceChanged)
                {
                    RecordSourceChangedBeforeCommit(
                        newModelName, old.Handle, hadDriver,
                        occupants.Count);
                }
                else
                {
                    ClientLog.Warn("Traffic",
                        "replacement_clone_validation_failed",
                        new Dictionary<string, object>
                        {
                            { "model", newModelName },
                            { "source_handle", old.Handle },
                            { "had_driver", hadDriver },
                            { "occupants", occupants.Count },
                            { "clone_settlement_required",
                                cloneSettlementRequired },
                            { "seats_assigned", seatsAssigned },
                            { "occupants_cloned", occupantsCloned },
                            { "driver_ready", driverReady },
                            { "commit_allowed", commitAllowed },
                            { "source_unchanged", sourceUnchanged },
                            { "validation_outcome",
                                validationOutcome.ToString() }
                        });
                }
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }

            player = Game.Player.Character;
            if (player == null || !player.Exists()
                || old.IsOnScreen
                || old.Position.DistanceTo(player.Position) < _minReplaceDist
                || IsProtectedFromTrafficReplacement(old, player)
                || HasPersistentSourceOccupant(occupants))
            {
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }

            // Model loading and clone validation can take multiple frames.
            // Re-sample the moving source at the commit boundary so the new
            // vehicle continues from its current position rather than the
            // position where the scan began.
            pos = old.Position;
            heading = old.Heading;
            speed = old.Speed;
            try
            {
                replacement.Position = pos;
                replacement.Heading = heading;
            }
            catch
            {
                CleanupStagedReplacement(occupants, replacement);
                return false;
            }

            // Commit only after the replacement and all cloned occupants are
            // valid. Until this point the source car and its occupants have not
            // been moved, hidden, persisted, tasked, or otherwise modified.
            old.IsPersistent = true;
            old.Delete();
            if (old.Exists())
            {
                old.MarkAsNoLongerNeeded();
                CleanupStagedReplacement(occupants, replacement);
                ClientLog.Warn("Traffic", "source_delete_failed",
                    new Dictionary<string, object>
                    {
                        { "model", newModelName },
                        { "source_handle", old.Handle }
                    });
                return false;
            }

            if (!replacement.Exists())
            {
                DeleteSourceOccupants(occupants);
                CleanupStagedReplacement(occupants, replacement);
                ClientLog.Warn("Traffic", "replacement_lost_after_commit",
                    new Dictionary<string, object> { { "model", newModelName } });
                return false;
            }

            DeleteSourceOccupants(occupants);
            var managedOccupants = new List<Ped>();
            foreach (AmbientOccupant occupant in occupants)
            {
                Ped clone = occupant.ClonePed;
                if (clone == null || !clone.Exists()) continue;
                clone.IsVisible = true;
                Function.Call(Hash.RESET_ENTITY_ALPHA, clone.Handle);
                clone.IsPersistent = true;
                managedOccupants.Add(clone);
            }

            Ped driver = clonedDriver?.ClonePed;
            ReleaseVehiclePhysics(replacement, hadDriver);
            if (hadDriver)
                ConfigureAmbientDriver(
                    driver, replacement, speed, keepPersistent: true);

            replacement.IsPersistent = true;
            _spawned.Add(new ManagedTraffic
            {
                Vehicle = replacement,
                Driver = driver,
                Occupants = managedOccupants,
                RequiresDriver = hadDriver,
            });
            Log($"ScanReplace committed: {newModelName} "
                + $"driver={hadDriver} occupants={managedOccupants.Count}");
            return true;
        }

        internal static ReplacementValidationOutcome
            EvaluateReplacementValidation(
                bool occupantsCloned, bool commitAllowed,
                bool sourceUnchanged)
        {
            if (!occupantsCloned)
                return ReplacementValidationOutcome.CloneFailed;
            if (!commitAllowed)
                return ReplacementValidationOutcome.CommitBlocked;
            if (!sourceUnchanged)
                return ReplacementValidationOutcome.SourceChanged;
            return ReplacementValidationOutcome.Ready;
        }

        internal static bool ShouldEmitSourceChangeDiagnostic(
            int now, int lastDiagnosticTime)
        {
            if (lastDiagnosticTime == int.MinValue) return true;
            return unchecked((uint)(now - lastDiagnosticTime)) >=
                SOURCE_CHANGE_DIAGNOSTIC_INTERVAL_MS;
        }

        private void RecordSourceChangedBeforeCommit(
            string model, int sourceHandle, bool hadDriver,
            int occupantCount)
        {
            _sourceChangeSkipCount++;
            int now = Game.GameTime;
            if (!ShouldEmitSourceChangeDiagnostic(
                    now, _lastSourceChangeDiagnosticTime))
                return;

            ClientLog.Info("Traffic", "replacement_source_changed_before_commit",
                new Dictionary<string, object>
                {
                    { "model", model },
                    { "source_handle", sourceHandle },
                    { "had_driver", hadDriver },
                    { "occupants", occupantCount },
                    { "observed_since_last", _sourceChangeSkipCount }
                });
            _sourceChangeSkipCount = 0;
            _lastSourceChangeDiagnosticTime = now;
        }

        internal static bool CanStageSourceReplacement(
            bool hasDriver, bool hasAnyOccupant, float speed)
        {
            if (hasDriver) return true;
            if (hasAnyOccupant) return false;
            return !float.IsNaN(speed) && !float.IsInfinity(speed)
                && Math.Abs(speed) <= MAX_PARKED_REPLACEMENT_SPEED;
        }

        private static List<AmbientOccupant> CaptureAmbientOccupants(
            Vehicle vehicle)
        {
            var occupants = new List<AmbientOccupant>();
            int maxPassengers = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS, vehicle.Handle);
            for (int seat = -1; seat < maxPassengers; seat++)
            {
                Ped ped = vehicle.GetPedOnSeat((VehicleSeat)seat);
                if (ped == null || !ped.Exists()) continue;
                occupants.Add(new AmbientOccupant
                {
                    SourcePed = ped,
                    SourceSeat = seat,
                    TargetSeat = int.MinValue,
                });
            }
            return occupants;
        }

        private static bool TryAssignReplacementSeats(
            List<AmbientOccupant> occupants, Vehicle replacement)
        {
            int maxPassengers = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS,
                replacement.Handle);
            var used = new HashSet<int>();
            foreach (AmbientOccupant occupant in occupants)
            {
                if (occupant.SourceSeat == -1)
                {
                    occupant.TargetSeat = -1;
                    used.Add(-1);
                    continue;
                }

                int target = occupant.SourceSeat >= 0
                    && occupant.SourceSeat < maxPassengers
                    && !used.Contains(occupant.SourceSeat)
                    ? occupant.SourceSeat : -2;
                if (target == -2)
                {
                    for (int seat = 0; seat < maxPassengers; seat++)
                    {
                        if (used.Contains(seat)) continue;
                        target = seat;
                        break;
                    }
                }
                if (target == -2) return false;
                occupant.TargetSeat = target;
                used.Add(target);
            }
            return true;
        }

        private static bool TryCloneOccupants(
            List<AmbientOccupant> occupants, Vehicle replacement)
        {
            if (occupants == null) return false;
            if (!RequiresCloneSettlement(occupants.Count)) return true;
            foreach (AmbientOccupant occupant in occupants)
            {
                if (occupant.SourcePed == null || !occupant.SourcePed.Exists())
                    return false;
                try
                {
                    Ped clone = occupant.SourcePed.Clone(
                        occupant.SourcePed.Heading);
                    if (clone == null || !clone.Exists()) return false;
                    clone.IsPersistent = true;
                    clone.SetIntoVehicle(
                        replacement, (VehicleSeat)occupant.TargetSeat);
                    occupant.ClonePed = clone;
                }
                catch
                {
                    return false;
                }
            }

            Script.Wait(0);
            foreach (AmbientOccupant occupant in occupants)
                if (!IsPedInVehicleSeat(
                    occupant.ClonePed, replacement, occupant.TargetSeat))
                    return false;
            return true;
        }

        internal static bool RequiresCloneSettlement(int occupantCount)
        {
            return occupantCount > 0;
        }

        private static bool SourceOccupantsUnchanged(
            List<AmbientOccupant> captured, Vehicle source)
        {
            if (source == null || !source.Exists()) return false;
            List<AmbientOccupant> current;
            try { current = CaptureAmbientOccupants(source); }
            catch { return false; }
            if (current.Count != captured.Count) return false;
            foreach (AmbientOccupant original in captured)
            {
                AmbientOccupant match = current.Find(
                    occupant => occupant.SourceSeat == original.SourceSeat);
                if (match == null || match.SourcePed == null
                    || original.SourcePed == null
                    || match.SourcePed.Handle != original.SourcePed.Handle)
                    return false;
            }
            return true;
        }

        private static bool HasPersistentSourceOccupant(
            List<AmbientOccupant> occupants)
        {
            foreach (AmbientOccupant occupant in occupants)
                if (occupant.SourcePed == null
                    || !occupant.SourcePed.Exists()
                    || occupant.SourcePed.IsPersistent)
                    return true;
            return false;
        }

        private static void CleanupStagedReplacement(
            List<AmbientOccupant> occupants, Vehicle replacement)
        {
            if (occupants != null)
            {
                foreach (AmbientOccupant occupant in occupants)
                {
                    Ped clone = occupant.ClonePed;
                    if (clone == null || !clone.Exists()) continue;
                    clone.IsPersistent = true;
                    clone.Delete();
                    occupant.ClonePed = null;
                }
            }
            if (replacement != null && replacement.Exists())
            {
                replacement.IsPersistent = true;
                replacement.Delete();
            }
        }

        private static void DeleteSourceOccupants(
            List<AmbientOccupant> occupants)
        {
            foreach (AmbientOccupant occupant in occupants)
            {
                Ped source = occupant.SourcePed;
                if (source == null || !source.Exists()) continue;
                source.IsPersistent = true;
                source.Delete();
            }
        }

        private static bool IsPedInVehicleSeat(
            Ped ped, Vehicle vehicle, int seat)
        {
            if (ped == null || !ped.Exists()
                || vehicle == null || !vehicle.Exists())
                return false;
            Ped occupant = vehicle.GetPedOnSeat((VehicleSeat)seat);
            return occupant != null && occupant.Exists()
                && occupant.Handle == ped.Handle;
        }

        private static void ReleaseVehiclePhysics(
            Vehicle vehicle, bool engineOn)
        {
            if (vehicle == null || !vehicle.Exists()) return;
            vehicle.IsVisible = true;
            vehicle.IsCollisionEnabled = true;
            vehicle.IsPositionFrozen = false;
            Function.Call(Hash.SET_ENTITY_DYNAMIC, vehicle.Handle, true);
            Function.Call(Hash.ACTIVATE_PHYSICS, vehicle.Handle);
            Function.Call(Hash.SET_VEHICLE_HANDBRAKE, vehicle.Handle, false);
            Function.Call(Hash.SET_VEHICLE_ENGINE_ON,
                vehicle.Handle, engineOn, true, false);
        }

        private static void ConfigureAmbientDriver(
            Ped driver, Vehicle vehicle, float capturedSpeed,
            bool keepPersistent = false)
        {
            if (driver == null || !driver.Exists()
                || vehicle == null || !vehicle.Exists()) return;
            if (keepPersistent)
            {
                driver.IsPersistent = true;
                vehicle.IsPersistent = true;
            }
            ReleaseVehiclePhysics(vehicle, true);
            if (capturedSpeed > 1f)
                vehicle.Speed = capturedSpeed;
            Function.Call(Hash.TASK_VEHICLE_DRIVE_WANDER,
                driver.Handle, vehicle.Handle,
                GetTrafficCruiseSpeed(capturedSpeed), 786603);
            Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                driver.Handle, true);
            Function.Call(Hash.SET_PED_KEEP_TASK, driver.Handle, true);
            if (!keepPersistent)
                driver.MarkAsNoLongerNeeded();
        }

        internal static float GetTrafficCruiseSpeed(float capturedSpeed)
        {
            if (float.IsNaN(capturedSpeed) || float.IsInfinity(capturedSpeed)
                || capturedSpeed <= 1f)
                return 20f;
            return Math.Max(12f, Math.Min(30f, capturedSpeed));
        }

        internal static bool CanCommitReplacement(
            bool sourceHadDriver, bool driverTransferred)
        {
            return !sourceHadDriver || driverTransferred;
        }

        // ------------------------------------------------------------------ //
        //  Vehicle creation                                                   //
        // ------------------------------------------------------------------ //

        private Vehicle LoadAndCreateVehicle(string modelName, Vector3 pos,
                                              float heading,
                                              bool placeOnGround = true)
        {
            if (string.IsNullOrWhiteSpace(modelName)) return null;
            var model = new Model(modelName);
            SelectedModelValidationAction validationAction =
                _modelValidation.GetAction(modelName);
            if (validationAction ==
                SelectedModelValidationAction.RejectQuarantined)
                return null;
            if (validationAction == SelectedModelValidationAction.ProbeOnce)
            {
                bool available;
                try
                {
                    available = model.IsInCdImage && model.IsVehicle;
                }
                catch
                {
                    available = false;
                }
                if (!available)
                {
                    QuarantineModel(modelName, "edition_unavailable");
                    return null;
                }
                _modelValidation.MarkValidated(modelName);
            }

            // Parameterless Request queues the stream operation. Request(int)
            // may itself wait up to the supplied timeout on SHVDN; combining it
            // with another deadline loop could accidentally double the stall.
            try
            {
                model.Request();
            }
            catch
            {
                QuarantineModel(modelName, "stream_request_failed");
                return null;
            }
            var modelLoadWait = Stopwatch.StartNew();
            while (!model.IsLoaded)
            {
                if (HasModelLoadTimedOut(
                        modelLoadWait.ElapsedMilliseconds,
                        MODEL_LOAD_TIMEOUT))
                {
                    model.MarkAsNoLongerNeeded();
                    QuarantineModel(modelName, "stream_timeout");
                    return null;
                }
                Script.Wait(0);
            }

            Vehicle veh = World.CreateVehicle(model, pos, heading);
            model.MarkAsNoLongerNeeded();

            if (veh == null)
                return null;

            if (placeOnGround)
                veh.PlaceOnGround();

            // Random colors
            int c1 = _rng.Next(0, 160);
            int c2 = _rng.Next(0, 160);
            Function.Call(Hash.SET_VEHICLE_COLOURS, veh, c1, c2);

            // MPBitset decorator — prevents despawning in Story Mode
            Function.Call(Hash.DECOR_SET_INT, veh.Handle, "MPBitset", 0);

            return veh;
        }

        internal static bool HasModelLoadTimedOut(
            long elapsedMilliseconds, int timeoutMilliseconds)
        {
            return elapsedMilliseconds >= Math.Max(0, timeoutMilliseconds);
        }

        private void QuarantineModel(string modelName, string reason)
        {
            if (string.IsNullOrWhiteSpace(modelName) ||
                !_modelValidation.Quarantine(modelName)) return;
            _validModels.RemoveAll(value => string.Equals(
                value, modelName, StringComparison.OrdinalIgnoreCase));
            foreach (List<string> pool in _classPools.Values)
                pool.RemoveAll(value => string.Equals(
                    value, modelName, StringComparison.OrdinalIgnoreCase));
            _trafficWeights.Remove(modelName);
            ClientLog.Warn("Traffic", "model_quarantined",
                new Dictionary<string, object>
                {
                    { "model", modelName },
                    { "reason", reason ?? "unavailable" },
                });
        }

        // ------------------------------------------------------------------ //
        //  Road node finding (for driven spawner)                             //
        // ------------------------------------------------------------------ //

        private bool FindRoadNode(Vector3 playerPos, float minDist, float maxDist,
                                   out Vector3 nodePos, out float heading)
        {
            nodePos = Vector3.Zero;
            heading = 0f;

            for (int attempt = 0; attempt < 24; attempt++)
            {
                float angle = (float)(_rng.NextDouble() * 2.0 * Math.PI);
                float dist = minDist
                    + (float)(_rng.NextDouble() * (maxDist - minDist));

                float testX = playerPos.X + dist * (float)Math.Cos(angle);
                float testY = playerPos.Y + dist * (float)Math.Sin(angle);
                float testZ = playerPos.Z;

                using (var outPos = new OutputArgument())
                using (var outHead = new OutputArgument())
                {
                    bool found = Function.Call<bool>(
                        Hash.GET_CLOSEST_VEHICLE_NODE_WITH_HEADING,
                        testX, testY, testZ,
                        outPos, outHead,
                        1, 3.0f, 0);

                    if (!found)
                        continue;

                    Vector3 pos = outPos.GetResult<Vector3>();
                    float h = outHead.GetResult<float>();

                    float actualDistance = pos.DistanceTo(playerPos);
                    if (actualDistance < minDist || actualDistance > maxDist) continue;
                    if (!Function.Call<bool>(Hash.IS_POINT_ON_ROAD,
                        pos.X, pos.Y, pos.Z, Game.Player.Character.Handle)) continue;
                    if (Function.Call<bool>(Hash.IS_ANY_VEHICLE_NEAR_POINT,
                        pos.X, pos.Y, pos.Z, 8f)) continue;
                    // Never create a vehicle where the camera can see it pop in.
                    if (Function.Call<bool>(Hash.IS_SPHERE_VISIBLE,
                        pos.X, pos.Y, pos.Z, 5f)) continue;

                    nodePos = pos;
                    heading = h;
                    return true;
                }
            }

            return false;
        }

        // ------------------------------------------------------------------ //
        //  Cleanup                                                            //
        // ------------------------------------------------------------------ //

        internal static ManagedTrafficAction DecideManagedTrafficAction(
            bool vehicleExists, bool requiresDriver, bool driverExists,
            bool driverInSeat, bool claimedByPlayer, bool purge,
            bool vehicleOnScreen, bool tooFar)
        {
            if (!vehicleExists) return ManagedTrafficAction.Release;
            if (claimedByPlayer) return ManagedTrafficAction.Release;
            // A missing/ejected/dead driver is normal world gameplay: the
            // player may have shot the driver, be pulling the body out, or an
            // NPC may have fled after a crash. Relinquish the pair to GTA's
            // population manager; never despawn the vehicle in response.
            if (requiresDriver && (!driverExists || !driverInSeat))
                return ManagedTrafficAction.Release;
            if (purge)
                return vehicleOnScreen
                    ? ManagedTrafficAction.Keep
                    : ManagedTrafficAction.Delete;
            if (tooFar) return ManagedTrafficAction.Release;
            return ManagedTrafficAction.Keep;
        }

        private void Cleanup(bool purge)
        {
            Ped player = Game.Player.Character;
            bool playerAvailable = player != null && player.Exists();
            Vector3 playerPos = playerAvailable ? player.Position : Vector3.Zero;
            Vehicle currentVehicle = playerAvailable ? player.CurrentVehicle : null;
            Vehicle lastVehicle = playerAvailable ? player.LastVehicle : null;

            for (int i = _spawned.Count - 1; i >= 0; i--)
            {
                ManagedTraffic managed = _spawned[i];
                Vehicle vehicle = managed?.Vehicle;
                Ped driver = managed?.Driver;
                bool vehicleExists = vehicle != null && vehicle.Exists();
                bool driverExists = driver != null && driver.Exists();
                bool driverInSeat = vehicleExists && driverExists
                    && IsPedInVehicleSeat(driver, vehicle, -1);
                bool claimedByPlayer = vehicleExists
                    && ((currentVehicle != null
                            && currentVehicle.Handle == vehicle.Handle)
                        || (lastVehicle != null
                            && lastVehicle.Handle == vehicle.Handle));
                bool vehicleOnScreen = vehicleExists && vehicle.IsOnScreen;
                bool tooFar = playerAvailable && vehicleExists
                    && vehicle.Position.DistanceTo(playerPos) > _cleanupDist;
                ManagedTrafficAction action = DecideManagedTrafficAction(
                    vehicleExists, managed != null && managed.RequiresDriver,
                    driverExists, driverInSeat, claimedByPlayer, purge,
                    vehicleOnScreen, tooFar);

                if (action == ManagedTrafficAction.Keep)
                    continue;

                if (action == ManagedTrafficAction.Delete)
                {
                    ClientLog.Info("Traffic", "managed_traffic_purged",
                        new Dictionary<string, object>
                        {
                            { "vehicle_handle", vehicleExists ? vehicle.Handle : 0 }
                        });
                    DeleteManagedTraffic(managed);
                }
                else
                {
                    bool occupancyChanged = managed != null && managed.RequiresDriver
                        && (!driverExists || !driverInSeat);
                    if (occupancyChanged)
                        ClientLog.Info("Traffic", "managed_occupancy_released",
                            new Dictionary<string, object>
                            {
                                { "vehicle_handle", vehicleExists ? vehicle.Handle : 0 },
                                { "driver_exists", driverExists },
                                { "driver_in_seat", driverInSeat },
                            });
                    ReleaseManagedTraffic(managed);
                }
                _spawned.RemoveAt(i);
            }
            ManagedVehicleCount = _spawned.Count;
        }

        private static void ReleaseManagedTraffic(ManagedTraffic managed)
        {
            if (managed == null) return;
            Vehicle vehicle = managed.Vehicle;
            if (vehicle != null && vehicle.Exists())
            {
                Function.Call(Hash.DECOR_REMOVE, vehicle.Handle, "MPBitset");
                vehicle.MarkAsNoLongerNeeded();
            }
            ForEachManagedOccupant(managed, ped => ped.MarkAsNoLongerNeeded());
        }

        private static void DeleteManagedTraffic(ManagedTraffic managed)
        {
            if (managed == null) return;
            Vehicle vehicle = managed.Vehicle;
            ForEachManagedOccupant(managed, ped =>
            {
                ped.IsPersistent = true;
                ped.Delete();
            });
            if (vehicle != null && vehicle.Exists())
            {
                vehicle.IsPersistent = true;
                Function.Call(Hash.DECOR_REMOVE, vehicle.Handle, "MPBitset");
                vehicle.Delete();
            }
        }

        private static void ForEachManagedOccupant(
            ManagedTraffic managed, Action<Ped> action)
        {
            var visited = new HashSet<int>();
            if (managed.Occupants != null)
            {
                foreach (Ped ped in managed.Occupants)
                {
                    if (ped == null || !ped.Exists()
                        || !visited.Add(ped.Handle)) continue;
                    action(ped);
                }
            }
            Ped driver = managed.Driver;
            if (driver != null && driver.Exists()
                && visited.Add(driver.Handle))
                action(driver);
        }
    }
}
