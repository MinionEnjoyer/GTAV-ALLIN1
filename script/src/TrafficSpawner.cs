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

            GTA.UI.Notification.Show(
                $"~g~ALLIN1~w~: {_validModels.Count}/{total} DLC vehicles available");
        }

        // ------------------------------------------------------------------ //
        //  Driven spawner (unchanged logic)                                   //
        // ------------------------------------------------------------------ //

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

            veh.IsEngineRunning = true;

            // Use the native that spawns a random ped directly into the
            // driver seat — more reliable than CreateRandomPed + warp.
            Ped driver = Function.Call<Ped>(
                Hash.CREATE_RANDOM_PED_AS_DRIVER, veh.Handle, true);

            if (driver == null || !driver.Exists())
            {
                // No driver — delete the vehicle so we don't leave
                // driverless cars on the road.
                veh.IsPersistent = true;
                veh.Delete();
                return false;
            }

            driver.Task.CruiseWithVehicle(veh, 20f, DrivingStyle.Normal);
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

            // Remove old vehicle
            old.IsPersistent = true;
            old.Delete();

            // Create replacement
            Vehicle replacement = LoadAndCreateVehicle(newModelName, pos, heading);
            if (replacement == null)
                return;

            if (hadDriver && driver.Exists())
            {
                // Transfer driver
                driver.Task.WarpIntoVehicle(replacement, VehicleSeat.Driver);

                if (speed > 1f)
                {
                    replacement.Speed = speed;
                    // TASK_VEHICLE_DRIVE_WANDER with normal civilian style
                    Function.Call(Hash.TASK_VEHICLE_DRIVE_WANDER,
                        driver.Handle, replacement.Handle,
                        speed, 786603);
                }
                else
                {
                    replacement.IsEngineRunning = false;
                }

                driver.MarkAsNoLongerNeeded();

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
