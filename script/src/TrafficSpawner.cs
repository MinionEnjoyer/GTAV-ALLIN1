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
        private const int MAX_DRIVEN = 20;
        private const float SPAWN_DIST_MIN = 80f;
        private const float SPAWN_DIST_MAX = 200f;
        private const float CLEANUP_DIST = 350f;
        private const int DRIVEN_COOLDOWN_MS = 5000;
        private const int MODEL_LOAD_TIMEOUT = 5000;

        // --- Replacement scanner config ---
        private const int SCAN_COOLDOWN_MS = 3000;
        private const float SCAN_RADIUS = 200f;
        private const float MIN_REPLACE_DIST = 50f;
        private const float REPLACE_CHANCE = 0.30f;

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
        private readonly List<Vehicle> _spawned = new List<Vehicle>();
        private readonly List<string> _validModels = new List<string>();
        private readonly Dictionary<VehicleClass, List<string>> _classPools =
            new Dictionary<VehicleClass, List<string>>();
        private readonly HashSet<int> _replacedHandles = new HashSet<int>();
        private readonly HashSet<int> _dlcModelHashes = new HashSet<int>();
        private readonly Random _rng = new Random();
        private int _lastDrivenTime;
        private int _lastScanTime;
        private bool _initialized;

        public TrafficSpawner()
        {
            Tick += OnTick;
            Interval = 0;

            Function.Call(Hash.DECOR_REGISTER, "MPBitset", 3);
        }

        // ------------------------------------------------------------------ //
        //  Logging                                                            //
        // ------------------------------------------------------------------ //

        private void Log(string msg)
        {
            try
            {
                File.AppendAllText(LOG_PATH,
                    $"[{DateTime.Now:HH:mm:ss}] {msg}{Environment.NewLine}");
            }
            catch { }
        }

        // ------------------------------------------------------------------ //
        //  Main loop                                                          //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            if (Game.IsLoading)
                return;

            if (!_initialized)
            {
                Initialize();
                return;
            }

            if (_validModels.Count == 0)
                return;

            Cleanup();

            int now = Game.GameTime;

            // Driven spawner
            if (now - _lastDrivenTime >= DRIVEN_COOLDOWN_MS
                && _spawned.Count < MAX_DRIVEN)
            {
                if (SpawnDriven())
                    _lastDrivenTime = now;
            }

            // Replacement scanner
            if (now - _lastScanTime >= SCAN_COOLDOWN_MS)
            {
                ScanAndReplace();
                _lastScanTime = now;
            }
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

            if (!FindRoadNode(playerPos, SPAWN_DIST_MIN, SPAWN_DIST_MAX,
                              out Vector3 nodePos, out float heading))
                return false;

            string modelName = _validModels[_rng.Next(_validModels.Count)];
            Vehicle veh = LoadAndCreateVehicle(modelName, nodePos, heading);
            if (veh == null)
                return false;

            // Give the game a frame to fully register the vehicle entity
            // before attempting ped creation — may fix intermittent failures.
            Script.Wait(0);

            veh.IsEngineRunning = true;

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

            // Log + on-screen notification
            string result = (driverExists && !seatFree) ? "OK" : "FAIL";
            Log($"  RESULT: {modelName} | method={pedMethod} | {result}");
            string status = (driverExists && !seatFree) ? "~g~OK" : "~r~FAIL";
            GTA.UI.Notification.Show(
                $"~y~SPAWN~w~: {modelName} | {pedMethod} | {status}");

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

            // Assign driving task
            driver.Task.CruiseWithVehicle(veh, 20f, DrivingStyle.Normal);

            // Ensure the driving task survives MarkAsNoLongerNeeded
            Function.Call(Hash.SET_PED_KEEP_TASK, driver.Handle, true);

            // Release to ambient traffic AFTER everything is configured
            driver.MarkAsNoLongerNeeded();
            veh.MarkAsNoLongerNeeded();
            _spawned.Add(veh);
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
                nearby = World.GetNearbyVehicles(player, SCAN_RADIUS);
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
                if (_rng.NextDouble() > REPLACE_CHANCE)
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
            if (dist < MIN_REPLACE_DIST)
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

        private void ReplaceVehicle(Vehicle old, string newModelName)
        {
            // Capture state
            Vector3 pos = old.Position;
            float heading = old.Heading;
            float speed = old.Speed;

            Ped driver = old.Driver;
            bool hadDriver = driver != null && driver.Exists();

            Ped[] passengers = null;
            if (hadDriver)
            {
                try { passengers = old.Passengers; }
                catch { passengers = null; }
            }

            Log($"  ReplaceVehicle: hadDriver={hadDriver} speed={speed:F1} passengers={passengers?.Length ?? 0}");

            // Make driver persistent before deleting vehicle so they don't
            // despawn when their vehicle is removed.
            if (hadDriver)
                driver.IsPersistent = true;

            // Remove old vehicle
            old.IsPersistent = true;
            old.Delete();

            // Create replacement
            Vehicle replacement = LoadAndCreateVehicle(newModelName, pos, heading);
            if (replacement == null)
            {
                // Vehicle creation failed — clean up orphaned driver
                if (hadDriver && driver.Exists())
                {
                    Log($"  ReplaceVehicle: vehicle creation failed, deleting orphaned driver");
                    driver.Delete();
                }
                return;
            }

            if (hadDriver && driver.Exists())
            {
                // Transfer driver
                driver.Task.WarpIntoVehicle(replacement, VehicleSeat.Driver);

                // Verify the warp actually worked
                Script.Wait(0);
                bool driverInSeat = !replacement.IsSeatFree(VehicleSeat.Driver);
                Log($"  ReplaceVehicle: driver warp driverInSeat={driverInSeat}");

                if (!driverInSeat)
                {
                    // Warp failed — create a new driver instead
                    Log($"  ReplaceVehicle: warp failed, creating fallback driver");
                    driver.IsPersistent = true;
                    driver.Delete();

                    Ped newDriver = null;
                    try
                    {
                        newDriver = replacement.CreateRandomPedOnSeat(VehicleSeat.Driver);
                    }
                    catch { }

                    if (newDriver != null && newDriver.Exists())
                    {
                        driver = newDriver;
                        driverInSeat = true;
                        Log($"  ReplaceVehicle: fallback driver created OK");
                    }
                    else
                    {
                        Log($"  ReplaceVehicle: fallback driver FAILED — car will be empty");
                    }
                }

                if (driverInSeat)
                {
                    if (speed > 1f)
                    {
                        replacement.Speed = speed;
                        Function.Call(Hash.TASK_VEHICLE_DRIVE_WANDER,
                            driver.Handle, replacement.Handle,
                            speed, 786603);
                    }
                    else
                    {
                        replacement.IsEngineRunning = false;
                    }

                    Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                        driver.Handle, true);
                    Function.Call(Hash.SET_PED_KEEP_TASK, driver.Handle, true);
                    driver.MarkAsNoLongerNeeded();
                }
                else
                {
                    replacement.IsEngineRunning = false;
                }

                // Transfer passengers
                if (passengers != null)
                {
                    for (int i = 0; i < passengers.Length; i++)
                    {
                        if (passengers[i] != null && passengers[i].Exists())
                        {
                            passengers[i].Task.WarpIntoVehicle(
                                replacement, (VehicleSeat)(i + 1));
                            passengers[i].MarkAsNoLongerNeeded();
                        }
                    }
                }
            }
            else
            {
                // Parked — no driver
                Log($"  ReplaceVehicle: parked (no driver)");
                replacement.IsEngineRunning = false;
            }

            replacement.MarkAsNoLongerNeeded();
            _spawned.Add(replacement);
            _replacedHandles.Add(replacement.Handle);
        }

        // ------------------------------------------------------------------ //
        //  Vehicle creation                                                   //
        // ------------------------------------------------------------------ //

        private Vehicle LoadAndCreateVehicle(string modelName, Vector3 pos,
                                              float heading)
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

            for (int attempt = 0; attempt < 10; attempt++)
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

                    if (pos.DistanceTo(playerPos) >= minDist)
                    {
                        nodePos = pos;
                        heading = h;
                        return true;
                    }
                }
            }

            return false;
        }

        // ------------------------------------------------------------------ //
        //  Cleanup                                                            //
        // ------------------------------------------------------------------ //

        private void Cleanup()
        {
            Vector3 playerPos = Game.Player.Character.Position;

            for (int i = _spawned.Count - 1; i >= 0; i--)
            {
                Vehicle v = _spawned[i];

                if (v == null || !v.Exists()
                    || v.Position.DistanceTo(playerPos) > CLEANUP_DIST)
                {
                    _spawned.RemoveAt(i);
                }
            }
        }
    }
}
