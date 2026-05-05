// TrafficSpawner.cs - Spawns GTA Online DLC vehicles into Story Mode traffic.
// Built via ScriptHookVDotNet Enhanced — works on both Legacy and Enhanced editions.
//
// Uses ScriptHookVDotNet to spawn vehicles from a hardcoded list of 444
// model names (generated from vehicles.toml). Vehicles appear as both
// driven traffic and parked cars at road nodes near the player.
//
// Requires: ScriptHookV + ScriptHookVDotNet Enhanced

using System;
using System.Collections.Generic;
using System.Drawing;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class TrafficSpawner : Script
    {
        // --- Configuration ---
        private const int MAX_DRIVEN = 20;
        private const int MAX_PARKED = 10;
        private const float SPAWN_DIST_MIN = 80f;
        private const float SPAWN_DIST_MAX = 200f;
        private const float PARKED_DIST_MIN = 40f;
        private const float PARKED_DIST_MAX = 130f;
        private const float CLEANUP_DIST = 350f;
        private const int DRIVEN_COOLDOWN_MS = 5000;
        private const int PARKED_COOLDOWN_MS = 3000;
        private const int MODEL_LOAD_TIMEOUT = 5000;

        // --- State ---
        private readonly List<SpawnedVehicle> _spawned = new List<SpawnedVehicle>();
        private readonly List<string> _validModels = new List<string>();
        private readonly Random _rng = new Random();
        private int _lastDrivenTime;
        private int _lastParkedTime;
        private bool _initialized;
        private int _totalSpawned;

        private struct SpawnedVehicle
        {
            public Vehicle Vehicle;
            public Ped Driver;
            public bool Parked;
        }

        public TrafficSpawner()
        {
            Tick += OnTick;
            Interval = 0;

            // Register the MPBitset decorator for despawn prevention
            Function.Call(Hash.DECOR_REGISTER, "MPBitset", 3);
        }

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

            if (now - _lastDrivenTime >= DRIVEN_COOLDOWN_MS && CountDriven() < MAX_DRIVEN)
            {
                if (SpawnDriven())
                    _lastDrivenTime = now;
            }

            if (now - _lastParkedTime >= PARKED_COOLDOWN_MS && CountParked() < MAX_PARKED)
            {
                if (SpawnParked())
                    _lastParkedTime = now;
            }
        }

        private void Initialize()
        {
            // Validate all model names against the game's cdimage.
            // Some models may not exist on Enhanced vs Legacy.
            _validModels.Clear();

            foreach (string name in VehicleList.All)
            {
                var model = new Model(name);
                if (model.IsInCdImage && model.IsVehicle)
                    _validModels.Add(name);
            }

            int now = Game.GameTime;
            _lastDrivenTime = now;
            _lastParkedTime = now;
            _initialized = true;

            GTA.UI.Notification.Show($"~g~ALLIN1~w~: {_validModels.Count}/{VehicleList.All.Length} vehicles available");
        }

        // --- Spawning ---

        private bool SpawnDriven()
        {
            Vector3 playerPos = Game.Player.Character.Position;

            if (!FindRoadNode(playerPos, SPAWN_DIST_MIN, SPAWN_DIST_MAX,
                              out Vector3 nodePos, out float heading))
                return false;

            string modelName = _validModels[_rng.Next(_validModels.Count)];
            Vehicle veh = CreateVehicle(modelName, nodePos, heading);
            if (veh == null)
                return false;

            veh.IsEngineRunning = true;

            // Create a random driver
            Ped driver = World.CreateRandomPed(nodePos);
            if (driver != null && driver.Exists())
            {
                driver.Task.WarpIntoVehicle(veh, VehicleSeat.Driver);
                driver.Task.CruiseWithVehicle(veh, 20f, DrivingStyle.Normal);
                driver.MarkAsNoLongerNeeded();
            }

            veh.MarkAsNoLongerNeeded();

            _spawned.Add(new SpawnedVehicle
            {
                Vehicle = veh,
                Driver = driver,
                Parked = false
            });
            _totalSpawned++;
            return true;
        }

        private bool SpawnParked()
        {
            Vector3 playerPos = Game.Player.Character.Position;

            if (!FindRoadNode(playerPos, PARKED_DIST_MIN, PARKED_DIST_MAX,
                              out Vector3 nodePos, out float heading))
                return false;

            // Offset to the side of the road
            float rad = heading * (float)Math.PI / 180f;
            float perpRad = rad + (float)Math.PI / 2f;
            nodePos.X += 3.5f * (float)Math.Cos(perpRad);
            nodePos.Y += 3.5f * (float)Math.Sin(perpRad);

            string modelName = _validModels[_rng.Next(_validModels.Count)];
            Vehicle veh = CreateVehicle(modelName, nodePos, heading);
            if (veh == null)
                return false;

            veh.IsEngineRunning = false;
            veh.MarkAsNoLongerNeeded();

            _spawned.Add(new SpawnedVehicle
            {
                Vehicle = veh,
                Driver = null,
                Parked = true
            });
            _totalSpawned++;
            return true;
        }

        // --- Vehicle creation helpers ---

        private Vehicle CreateVehicle(string modelName, Vector3 pos, float heading)
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

        // --- Road node finding ---

        private bool FindRoadNode(Vector3 playerPos, float minDist, float maxDist,
                                   out Vector3 nodePos, out float heading)
        {
            nodePos = Vector3.Zero;
            heading = 0f;

            for (int attempt = 0; attempt < 10; attempt++)
            {
                float angle = (float)(_rng.NextDouble() * 2.0 * Math.PI);
                float dist = minDist + (float)(_rng.NextDouble() * (maxDist - minDist));

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
                    float actualDist = pos.DistanceTo(playerPos);

                    if (actualDist >= minDist)
                    {
                        nodePos = pos;
                        heading = h;
                        return true;
                    }
                }
            }

            return false;
        }

        // --- Cleanup ---

        private void Cleanup()
        {
            Vector3 playerPos = Game.Player.Character.Position;

            for (int i = _spawned.Count - 1; i >= 0; i--)
            {
                var s = _spawned[i];
                bool remove = false;

                if (s.Vehicle == null || !s.Vehicle.Exists())
                {
                    remove = true;
                }
                else
                {
                    float dist = s.Vehicle.Position.DistanceTo(playerPos);
                    if (dist > CLEANUP_DIST)
                        remove = true;
                }

                if (remove)
                    _spawned.RemoveAt(i);
            }
        }

        // --- Counting ---

        private int CountDriven()
        {
            int n = 0;
            foreach (var s in _spawned)
                if (!s.Parked) n++;
            return n;
        }

        private int CountParked()
        {
            int n = 0;
            foreach (var s in _spawned)
                if (s.Parked) n++;
            return n;
        }
    }
}
