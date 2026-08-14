// TrafficSpawner.cs — Adds GTA Online DLC vehicles to Story Mode traffic.
//
// Two systems work together:
//   1. Driven spawner — creates new DLC vehicles with AI drivers on road nodes.
//   2. Replacement scanner — swaps vanilla ambient vehicles (parked or driven)
//      with class-matched DLC equivalents while off-screen.
//
// Only road-appropriate classes are used (no planes, helis, boats, military,
// emergency, etc.).  Replacement rate is ~30 % for a natural vanilla/DLC mix.
//
// Requires: ScriptHookV + ScriptHookVDotNet Enhanced

using System;
using System.Collections.Generic;
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
            { VehicleClass.Sports,         VehicleList.Sportsclassics }, // shared
            { VehicleClass.Super,          VehicleList.Super },
            { VehicleClass.OffRoad,        VehicleList.Offroad },
            { VehicleClass.Motorcycles,    VehicleList.Motorcycles },
            { VehicleClass.Vans,           VehicleList.Vans },
        };

        // --- Logging ---
        private static readonly string LOG_PATH = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.log");

        // --- State ---
        private readonly List<ManagedTraffic> _spawned =
            new List<ManagedTraffic>();
        private readonly List<string> _validModels = new List<string>();
        private readonly Dictionary<VehicleClass, List<string>> _classPools =
            new Dictionary<VehicleClass, List<string>>();
        private readonly HashSet<int> _replacedHandles = new HashSet<int>();
        private readonly Dictionary<int, int> _recentPlayerVehicleHandles =
            new Dictionary<int, int>();
        private readonly HashSet<int> _dlcModelHashes = new HashSet<int>();
        private readonly Random _rng = new Random();
        private int _lastDrivenTime;
        private int _lastScanTime;
        private int _lastCleanupTime;
        private bool _initialized;
        private bool _enabled = true;
        private string _lastSuppressionReason = "";
        private const int PLAYER_INTERACTION_PROTECTION_MS = 120000;

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

        private sealed class AmbientOccupant
        {
            internal Ped Ped;
            internal int SourceSeat;
            internal int TargetSeat;
        }

        private sealed class ManagedTraffic
        {
            internal Vehicle Vehicle;
            internal Ped Driver;
            internal bool RequiresDriver;
        }

        internal enum ManagedTrafficAction
        {
            Keep,
            Release,
            Delete,
        }

        public TrafficSpawner()
        {
            LoadSettings();
            Tick += OnTick;
            // Traffic work is proximity/cooldown based and does not need to run
            // at rendering frequency. This substantially reduces idle CPU use.
            Interval = 100;

            Function.Call(Hash.DECOR_REGISTER, "MPBitset", 3);
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
            if (now - _lastDrivenTime >= effectiveDrivenCooldown
                && _spawned.Count < effectiveMax)
            {
                if (SpawnDriven())
                    _lastDrivenTime = now;
            }

            // Replacement scanner
            if (now - _lastScanTime >= effectiveScanCooldown)
            {
                ScanAndReplace();
                _lastScanTime = now;
            }
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

        // ------------------------------------------------------------------ //
        //  Initialization                                                     //
        // ------------------------------------------------------------------ //

        private void Initialize()
        {
            _validModels.Clear();
            _classPools.Clear();
            _dlcModelHashes.Clear();

            // Build per-class pools of validated models.
            foreach (var entry in CLASS_MAP)
            {
                if (!_classPools.ContainsKey(entry.Key))
                    _classPools[entry.Key] = new List<string>();

                foreach (string name in entry.Value)
                {
                    var m = new Model(name);
                    if (m.IsInCdImage && m.IsVehicle)
                        _classPools[entry.Key].Add(name);
                }
            }

            // Build the flat list for driven spawner (union of all class pools).
            var seen = new HashSet<string>();
            foreach (var pool in _classPools.Values)
            {
                foreach (string name in pool)
                {
                    if (seen.Add(name))
                        _validModels.Add(name);
                }
            }

            // Build hash set of DLC model hashes so the scanner can skip
            // vehicles that are already DLC.
            foreach (string name in _validModels)
                _dlcModelHashes.Add(
                    Function.Call<int>(Hash.GET_HASH_KEY, name));

            int now = Game.GameTime;
            _lastDrivenTime = now;
            _lastScanTime = now;
            _initialized = true;

            int total = 0;
            foreach (var arr in ROAD_CLASSES)
                total += arr.Length;

            Log($"=== ALLIN1 Initialized: {_validModels.Count}/{total} DLC vehicles available ===");
            foreach (var kv in _classPools)
                Log($"  {kv.Key}: {kv.Value.Count} models");

            GTA.UI.Notification.Show(
                $"~g~ALLIN1~w~: {_validModels.Count}/{total} DLC vehicles available");
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

        private bool SpawnDriven()
        {
            Vector3 playerPos = Game.Player.Character.Position;

            if (!FindRoadNode(playerPos, _spawnDistMin, _spawnDistMax,
                              out Vector3 nodePos, out float heading))
                return false;

            string modelName = _validModels[_rng.Next(_validModels.Count)];
            Vehicle veh = LoadAndCreateVehicle(modelName, nodePos, heading);
            if (veh == null)
                return false;

            // Give the game a frame to fully register the vehicle entity
            // before attempting ped creation — may fix intermittent failures.
            Script.Wait(0);

            ReleaseVehiclePhysics(veh, true);

            Log($"SpawnDriven: vehicle={modelName} handle={veh.Handle}");

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
            Log($"  attempt1 (random): exists={driverExists} seatFree={seatFree}");

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
                pedModel.Request(MODEL_LOAD_TIMEOUT);

                DateTime deadline = DateTime.UtcNow.AddMilliseconds(MODEL_LOAD_TIMEOUT);
                while (!pedModel.IsLoaded)
                {
                    if (DateTime.UtcNow > deadline)
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
                Log($"  attempt2 (explicit {pedModelName}): exists={driverExists} seatFree={seatFree}");
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
                Log($"  attempt3 (native {nativePedName}): exists={driverExists} seatFree={seatFree}");
            }

            // Keep the detailed result in the support log without interrupting gameplay.
            string result = (driverExists && !seatFree) ? "OK" : "FAIL";
            Log($"  RESULT: {modelName} | method={pedMethod} | {result}");

            // If all attempts failed, delete the empty vehicle
            if (!driverExists || seatFree)
            {
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
            Vector3 playerPos = player.Position;

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

            // Clean stale handles
            _replacedHandles.RemoveWhere(h =>
                !Function.Call<bool>(Hash.DOES_ENTITY_EXIST, h));

            foreach (Vehicle veh in nearby)
            {
                if (!IsEligibleForReplacement(veh, player, playerPos))
                    continue;

                // 30 % replacement chance
                if (_rng.NextDouble() > _replaceChance)
                {
                    // Mark as seen even when skipped so we don't re-roll
                    // the same vehicle every scan.
                    _replacedHandles.Add(veh.Handle);
                    continue;
                }

                // Class-matched model lookup
                VehicleClass cls = veh.ClassType;
                if (!_classPools.TryGetValue(cls, out List<string> pool)
                    || pool.Count == 0)
                    continue;

                string newModelName = pool[_rng.Next(pool.Count)];
                if (IsProtectedFromTrafficReplacement(veh, player))
                    continue;
                Log($"ScanReplace: {cls} → {newModelName} (handle={veh.Handle})");
                ReplaceVehicle(veh, newModelName);
            }
        }

        private bool IsEligibleForReplacement(Vehicle veh, Ped player,
                                               Vector3 playerPos)
        {
            if (veh == null || !veh.Exists())
                return false;

            // Already processed
            if (_replacedHandles.Contains(veh.Handle))
                return false;

            // Player's own vehicle
            Vehicle currentVeh = player.CurrentVehicle;
            if (currentVeh != null && veh == currentVeh)
                return false;
            Vehicle lastVeh = player.LastVehicle;
            if (lastVeh != null && veh == lastVeh)
                return false;

            if (IsProtectedFromTrafficReplacement(veh, player))
                return false;

            // Mission / persistent entities
            if (veh.IsPersistent)
                return false;

            // Population type: only ambient/random (1-5)
            int popType = Function.Call<int>(
                Hash.GET_ENTITY_POPULATION_TYPE, veh.Handle);
            if (popType > 5)
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

            // Too close — prevents pop-in even if off-screen check fails
            float dist = veh.Position.DistanceTo(playerPos);
            if (dist < _minReplaceDist)
                return false;

            // Must be off-screen to prevent visible pop-in
            if (veh.IsOnScreen)
                return false;

            // Skip if driver is a mission ped
            Ped driver = veh.Driver;
            if (driver != null && driver.Exists() && driver.IsPersistent)
                return false;

            return true;
        }

        private void RememberPlayerVehicles(Ped player, int now)
        {
            if (player == null || !player.Exists()) return;
            RememberPlayerVehicle(player.CurrentVehicle, now);
            RememberPlayerVehicle(player.LastVehicle, now);

            var expired = new List<int>();
            foreach (var entry in _recentPlayerVehicleHandles)
                if (now - entry.Value > PLAYER_INTERACTION_PROTECTION_MS)
                    expired.Add(entry.Key);
            foreach (int handle in expired)
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
            if (HasDecorator(vehicle, "Player_Vehicle") ||
                HasDecorator(vehicle, "PV_Slot") ||
                HasDecorator(vehicle, "Veh_Modded_By_Player")) return true;
            return IsInsideSafehouseGarageZone(vehicle.Position);
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

        private void ReplaceVehicle(Vehicle old, string newModelName)
        {
            if (IsProtectedFromTrafficReplacement(old, Game.Player.Character))
                return;

            // Capture state
            Vector3 pos = old.Position;
            float heading = old.Heading;
            float speed = old.Speed;

            List<AmbientOccupant> occupants;
            try { occupants = CaptureAmbientOccupants(old); }
            catch (Exception ex)
            {
                ClientLog.Warn("Traffic", "passenger_capture_failed",
                    new Dictionary<string, object> { { "exception", ex.Message } });
                return;
            }

            AmbientOccupant driverOccupant = occupants.Find(
                occupant => occupant.SourceSeat == -1);
            bool hadDriver = driverOccupant != null;
            int passengerCount = Math.Max(
                0, occupants.Count - (hadDriver ? 1 : 0));

            Log($"  ReplaceVehicle: hadDriver={hadDriver} speed={speed:F1} passengers={passengerCount}");

            // Stage and validate the replacement before touching the original.
            // Creating it above the source vehicle keeps both entities from
            // colliding while the transaction is prepared.
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
                return;
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
                    new Dictionary<string, object>
                    {
                        { "model", newModelName }
                    });
                if (replacement.Exists())
                    replacement.Delete();
                return;
            }

            // Move occupants to the staged replacement before deleting their
            // source vehicle. Deleting an ambient vehicle can destroy its peds
            // even after IsPersistent is set, which used to turn moving traffic
            // into empty, stationary replacement cars.
            bool occupantsTransferred =
                TryAssignReplacementSeats(occupants, replacement)
                && TryTransferOccupants(occupants, replacement);
            bool driverTransferred = !hadDriver || (occupantsTransferred
                && IsPedInVehicleSeat(driverOccupant.Ped, replacement, -1));
            if (!occupantsTransferred
                || !CanCommitReplacement(hadDriver, driverTransferred))
            {
                ClientLog.Warn("Traffic", "replacement_occupant_transfer_failed",
                    new Dictionary<string, object>
                    {
                        { "model", newModelName },
                        { "source_handle", old.Handle },
                        { "had_driver", hadDriver },
                        { "occupants", occupants.Count }
                    });
                RestoreOccupantsToSource(occupants, old);
                if (replacement.Exists()) replacement.Delete();
                RestoreSourceTraffic(old, driverOccupant?.Ped, speed);
                return;
            }

            // Remove the now-empty source vehicle.
            old.IsPersistent = true;
            old.Delete();

            if (old.Exists())
            {
                ClientLog.Warn("Traffic", "source_delete_failed",
                    new Dictionary<string, object>
                    {
                        { "model", newModelName },
                        { "source_handle", old.Handle }
                    });
                RestoreOccupantsToSource(occupants, old);
                if (replacement.Exists()) replacement.Delete();
                RestoreSourceTraffic(old, driverOccupant?.Ped, speed);
                return;
            }

            // Revalidate the staged entity before committing it to traffic.
            if (!replacement.Exists())
            {
                ClientLog.Warn("Traffic", "replacement_lost_after_commit",
                    new Dictionary<string, object> { { "model", newModelName } });
                // Vehicle creation failed — clean up orphaned driver
                foreach (AmbientOccupant occupant in occupants)
                    if (occupant.Ped != null && occupant.Ped.Exists())
                        occupant.Ped.MarkAsNoLongerNeeded();
                return;
            }

            ReleaseVehiclePhysics(replacement, hadDriver);

            if (hadDriver && driverOccupant.Ped.Exists())
            {
                // A source driver still represents moving traffic even when
                // captured at 0 mph at a light. Always restore a driving task.
                ConfigureAmbientDriver(
                    driverOccupant.Ped, replacement, speed,
                    keepPersistent: true);
                Log($"  ReplaceVehicle: driven speed={speed:F1} "
                    + $"cruise={GetTrafficCruiseSpeed(speed):F1}");
            }
            else
            {
                Log("  ReplaceVehicle: parked (source had no driver)");
            }

            foreach (AmbientOccupant occupant in occupants)
            {
                if (occupant.SourceSeat != -1
                    && occupant.Ped != null && occupant.Ped.Exists())
                    occupant.Ped.MarkAsNoLongerNeeded();
            }

            replacement.IsPersistent = true;
            _spawned.Add(new ManagedTraffic
            {
                Vehicle = replacement,
                Driver = hadDriver ? driverOccupant.Ped : null,
                RequiresDriver = hadDriver,
            });
            _replacedHandles.Add(replacement.Handle);
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
                if (ped != null && ped.Exists())
                {
                    occupants.Add(new AmbientOccupant
                    {
                        Ped = ped,
                        SourceSeat = seat,
                        TargetSeat = int.MinValue,
                    });
                }
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
                if (target == -2)
                    return false;
                occupant.TargetSeat = target;
                used.Add(target);
            }
            return true;
        }

        private static bool TryTransferOccupants(
            List<AmbientOccupant> occupants, Vehicle replacement)
        {
            foreach (AmbientOccupant occupant in occupants)
            {
                if (occupant.Ped == null || !occupant.Ped.Exists())
                    return false;
                occupant.Ped.IsPersistent = true;
                Function.Call(Hash.SET_PED_INTO_VEHICLE,
                    occupant.Ped.Handle, replacement.Handle,
                    occupant.TargetSeat);
            }
            Script.Wait(0);
            foreach (AmbientOccupant occupant in occupants)
            {
                if (!IsPedInVehicleSeat(
                    occupant.Ped, replacement, occupant.TargetSeat))
                    return false;
            }
            return true;
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

        private static void RestoreOccupantsToSource(
            List<AmbientOccupant> occupants, Vehicle source)
        {
            if (source == null || !source.Exists()) return;
            foreach (AmbientOccupant occupant in occupants)
            {
                if (occupant.Ped == null || !occupant.Ped.Exists()) continue;
                Function.Call(Hash.SET_PED_INTO_VEHICLE,
                    occupant.Ped.Handle, source.Handle, occupant.SourceSeat);
            }
            Script.Wait(0);
        }

        private static void RestoreSourceTraffic(
            Vehicle source, Ped driver, float capturedSpeed)
        {
            if (source == null || !source.Exists()) return;
            if (driver != null && driver.Exists()
                && IsPedInVehicleSeat(driver, source, -1))
                ConfigureAmbientDriver(driver, source, capturedSpeed);
            source.MarkAsNoLongerNeeded();
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
            var model = new Model(modelName);
            model.Request(MODEL_LOAD_TIMEOUT);

            DateTime deadline = DateTime.UtcNow.AddMilliseconds(MODEL_LOAD_TIMEOUT);
            while (!model.IsLoaded)
            {
                if (DateTime.UtcNow > deadline)
                {
                    model.MarkAsNoLongerNeeded();
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
            if (requiresDriver && (!driverExists || !driverInSeat))
                return ManagedTrafficAction.Delete;
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
                    ClientLog.Warn("Traffic", "managed_driver_lost",
                        new Dictionary<string, object>
                        {
                            { "vehicle_handle", vehicleExists ? vehicle.Handle : 0 },
                            { "driver_exists", driverExists },
                            { "driver_in_seat", driverInSeat },
                        });
                    DeleteManagedTraffic(managed);
                }
                else
                    ReleaseManagedTraffic(managed);
                _spawned.RemoveAt(i);
            }
            ManagedVehicleCount = _spawned.Count;
        }

        private static void ReleaseManagedTraffic(ManagedTraffic managed)
        {
            if (managed == null) return;
            Vehicle vehicle = managed.Vehicle;
            Ped driver = managed.Driver;
            if (vehicle != null && vehicle.Exists())
            {
                Function.Call(Hash.DECOR_REMOVE, vehicle.Handle, "MPBitset");
                vehicle.MarkAsNoLongerNeeded();
            }
            if (driver != null && driver.Exists())
                driver.MarkAsNoLongerNeeded();
        }

        private static void DeleteManagedTraffic(ManagedTraffic managed)
        {
            if (managed == null) return;
            Vehicle vehicle = managed.Vehicle;
            Ped driver = managed.Driver;
            if (driver != null && driver.Exists())
            {
                driver.IsPersistent = true;
                driver.Delete();
            }
            if (vehicle != null && vehicle.Exists())
            {
                vehicle.IsPersistent = true;
                Function.Call(Hash.DECOR_REMOVE, vehicle.Handle, "MPBitset");
                vehicle.Delete();
            }
        }
    }
}
