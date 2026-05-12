// GarageManager.cs -- Independent garage at the 10-car underground interior.
//
// Each character (Michael, Franklin, Trevor) has 10 personal vehicle slots
// in a shared garage interior that exists permanently underground. Vehicles
// are spawned when the player enters the garage and despawned on exit.
// Entry/exit is via a marker near Eclipse Towers on Eclipse Boulevard.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal static class GarageManager
    {
        // ------------------------------------------------------------------ //
        //  Types                                                              //
        // ------------------------------------------------------------------ //

        internal struct ParkingSlot
        {
            internal Vector3 Position;
            internal float Heading;

            internal ParkingSlot(float x, float y, float z, float h)
            {
                Position = new Vector3(x, y, z);
                Heading = h;
            }
        }

        internal class StoredVehicle
        {
            internal string Model;
            internal int Slot;
            internal int Color1;
            internal int Color2;
            internal int[] Mods;          // 50 mod slots (index -> variation)
            internal bool[] ModToggles;   // 50 toggleable mods
            internal int WheelType;
            internal int WindowTint;
            internal int Livery;
            internal string PlateText;
            internal int PlateStyle;
            internal int PearlescentColor;
            internal int RimColor;
            internal int[] NeonEnabled;   // 4 bools (left,right,front,back)
            internal int[] NeonColor;     // R,G,B
            internal int[] TyreSmokeColor;// R,G,B
            internal int[] Extras;        // which extras are enabled (up to 15)
            internal bool CustomPrimaryColor;
            internal int[] CustomPrimary;  // R,G,B (if custom)
            internal bool CustomSecondaryColor;
            internal int[] CustomSecondary;// R,G,B (if custom)
        }

        // ------------------------------------------------------------------ //
        //  Constants                                                          //
        // ------------------------------------------------------------------ //

        private const int SLOT_COUNT = 10;
        private const float ENTER_RADIUS = 2.5f;
        private const float EXIT_RADIUS = 4.0f;

        // Outside entrance/exit positions (shared by all characters)
        private static readonly Vector3 ENTRANCE_POS =
            new Vector3(-796f, 303f, 85.2f);

        private static readonly Vector3 PED_EXIT_DEST =
            new Vector3(-774f, 310.2f, 85.7f);
        private const float PED_EXIT_DEST_HEADING = 180f;

        // Interior positions (shared underground garage)
        private static readonly Vector3 INTERIOR_SPAWN =
            new Vector3(240.65f, -1004.86f, -99.66f);
        private const float INTERIOR_SPAWN_HEADING = -165f;

        private static readonly Vector3 VEHICLE_EXIT_INTERIOR =
            new Vector3(228.2f, -1004.3f, -99f);
        private const float VEHICLE_EXIT_INTERIOR_HEADING = 352.3f;

        private static readonly Vector3 PED_EXIT =
            new Vector3(240.7f, -1004.8f, -99f);
        private const float PED_EXIT_HEADING = 82.8f;

        // 10 vehicle parking positions (from SPGR data -- two rows of 5)
        internal static readonly ParkingSlot[] Slots =
        {
            // Left row (facing heading -105)
            new ParkingSlot(224.57f, -1002.75f, -99.0f, -105f),
            new ParkingSlot(224.36f, -998.87f,  -99.0f, -105f),
            new ParkingSlot(223.61f, -993.94f,  -99.0f, -105f),
            new ParkingSlot(223.65f, -989.04f,  -99.0f, -105f),
            new ParkingSlot(224.18f, -983.51f,  -99.0f, -105f),
            // Right row (facing heading 134) -- shifted -0.5 X for wall clearance
            new ParkingSlot(233.94f, -1000.90f, -99.0f, 134f),
            new ParkingSlot(233.18f, -995.90f,  -99.0f, 134f),
            new ParkingSlot(232.50f, -991.15f,  -99.0f, 134f),
            new ParkingSlot(232.44f, -985.76f,  -99.0f, 134f),
            new ParkingSlot(231.89f, -981.39f,  -99.0f, 134f),
        };

        // Character keys for save file
        private const string KEY_MICHAEL  = "michael";
        private const string KEY_FRANKLIN = "franklin";
        private const string KEY_TREVOR   = "trevor";

        // ------------------------------------------------------------------ //
        //  State                                                              //
        // ------------------------------------------------------------------ //

        private static readonly string SCRIPTS_DIR =
            AppDomain.CurrentDomain.BaseDirectory;
        private static readonly string SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_garage.json");
        private static readonly string LOG_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_gbay.log");

        // Per-character stored vehicle lists
        private static readonly Dictionary<string, List<StoredVehicle>> _stored =
            new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL,  new List<StoredVehicle>() },
                { KEY_FRANKLIN, new List<StoredVehicle>() },
                { KEY_TREVOR,   new List<StoredVehicle>() },
            };

        // Active vehicle handles (only populated while player is inside garage)
        private static readonly Vehicle[] _handles = new Vehicle[SLOT_COUNT];

        // Player state
        private static bool _isPlayerInGarage;

        private static Blip _entranceBlip;
        private static Blip _pedEntranceBlip;

        // Cooldown to avoid re-entering immediately after exiting
        private static int _exitCooldownFrames;

        // Reverse lookup: model hash -> spawn name (built from VehicleList.All)
        private static Dictionary<int, string> _hashToSpawnName;

        private static bool _debug;
        private static bool _enableLogging = true;
        private static bool _initialized;

        // ------------------------------------------------------------------ //
        //  Logging                                                            //
        // ------------------------------------------------------------------ //

        private static void Log(string msg)
        {
            if (!_enableLogging)
                return;
            try
            {
                File.AppendAllText(LOG_PATH,
                    $"[{DateTime.Now:HH:mm:ss}] [Garage] {msg}{Environment.NewLine}");
            }
            catch { }
        }

        private static void LogException(string context, Exception ex)
        {
            try
            {
                File.AppendAllText(LOG_PATH,
                    $"[{DateTime.Now:HH:mm:ss}] [Garage] EXCEPTION in {context}: {ex.Message}{Environment.NewLine}" +
                    $"  {ex.StackTrace}{Environment.NewLine}");
            }
            catch { }
        }

        // ------------------------------------------------------------------ //
        //  Public API                                                         //
        // ------------------------------------------------------------------ //

        internal static void Configure(bool debug, bool enableLogging)
        {
            _debug = debug;
            _enableLogging = enableLogging;
        }

        internal static void Initialize()
        {
            if (_initialized)
                return;

            try
            {
                // Build reverse hash -> spawn name lookup from VehicleList
                _hashToSpawnName = new Dictionary<int, string>();
                foreach (string name in VehicleList.All)
                {
                    int hash = Game.GenerateHash(name);
                    if (!_hashToSpawnName.ContainsKey(hash))
                        _hashToSpawnName[hash] = name;
                }
                Log($"Built hash->spawn lookup: {_hashToSpawnName.Count} entries");

                Load();

                int total = 0;
                foreach (var list in _stored.Values)
                    total += list.Count;
                Log($"Loaded {total} stored vehicles from {SAVE_PATH}");

                // Create entrance blip
                _entranceBlip = World.CreateBlip(ENTRANCE_POS);
                _entranceBlip.Sprite = BlipSprite.Garage;
                _entranceBlip.Color = CharacterBlipColor();
                _entranceBlip.Name = "ALLIN1 Garage (Vehicle)";
                _entranceBlip.IsShortRange = true;

                _pedEntranceBlip = World.CreateBlip(PED_EXIT_DEST);
                _pedEntranceBlip.Sprite = BlipSprite.Garage;
                _pedEntranceBlip.Color = CharacterBlipColor();
                _pedEntranceBlip.Name = "ALLIN1 Garage (Pedestrian)";
                _pedEntranceBlip.IsShortRange = true;

                Log("GarageManager initialized (Eclipse Towers 10-car interior)");
            }
            catch (Exception ex)
            {
                LogException("Initialize", ex);
            }

            _initialized = true;
        }

        internal static bool IsPlayerInGarage => _isPlayerInGarage;

        /// <summary>
        /// Called every frame from GbayShop.OnTick. Handles entrance/exit
        /// marker drawing and proximity detection.
        /// </summary>
        internal static void OnTick()
        {
            if (!_initialized)
                return;

            // Don't show garage markers while in floor garage
            if (_isPlayerInFloorGarage)
                return;

            if (_exitCooldownFrames > 0)
            {
                _exitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead)
                return;

            // Update blip colors to match current character
            BlipColor charColor = CharacterBlipColor();
            if (_entranceBlip != null && _entranceBlip.Exists())
                _entranceBlip.Color = charColor;
            if (_pedEntranceBlip != null && _pedEntranceBlip.Exists())
                _pedEntranceBlip.Color = charColor;

            if (!_isPlayerInGarage)
            {
                bool inVehicle = player.IsInVehicle();

                // ---- Vehicle entrance — only when in a vehicle ----
                if (inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(2f, 2f, 1.5f),
                        System.Drawing.Color.FromArgb(128, 0, 200, 0));

                    float vehDist = player.Position.DistanceTo(ENTRANCE_POS);
                    if (vehDist < ENTER_RADIUS)
                    {
                        Vehicle veh = player.CurrentVehicle;
                        if (veh != null && veh.Exists() && IsPersonalVehicle(veh))
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "You cannot store your personal vehicle in the garage.");
                        }
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter your garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterGarage();
                        }
                    }
                }

                // ---- Pedestrian entrance — only when on foot ----
                if (!inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        PED_EXIT_DEST - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(1.5f, 1.5f, 1.2f),
                        System.Drawing.Color.FromArgb(128, 0, 200, 0));

                    float pedDist = player.Position.DistanceTo(PED_EXIT_DEST);
                    if (pedDist < ENTER_RADIUS)
                    {
                        GTA.UI.Screen.ShowHelpTextThisFrame(
                            "Press ~INPUT_CONTEXT~ to enter your garage.");
                        if (Game.IsControlJustPressed(GTA.Control.Context))
                            EnterGarage();
                    }
                }
            }
            else
            {
                bool inVehicle = player.IsInVehicle();

                // Keep all parked vehicles frozen with engines off
                EnforceGarageVehicleState(player);

                // ---- Vehicle exit — press E anywhere while in a vehicle ----
                if (inVehicle)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to leave the garage with your vehicle.");
                    if (Game.IsControlJustPressed(GTA.Control.Context))
                        LeaveGarage();
                }

                // ---- Pedestrian exit (PED_EXIT) — only when on foot ----
                if (!inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        PED_EXIT - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(1.5f, 1.5f, 1.2f),
                        System.Drawing.Color.FromArgb(128, 0, 200, 0));

                    float pedExitDist = player.Position.DistanceTo(PED_EXIT);
                    if (pedExitDist < EXIT_RADIUS)
                    {
                        GTA.UI.Screen.ShowHelpTextThisFrame(
                            "Press ~INPUT_CONTEXT~ to leave the garage.");
                        if (Game.IsControlJustPressed(GTA.Control.Context))
                            LeaveGarage();
                    }
                }
            }
        }

        internal static int GetUsedSlots()
        {
            string key = CharacterKey();
            if (_stored.TryGetValue(key, out var list))
                return list.Count;
            return 0;
        }

        internal static int GetCapacity()
        {
            return SLOT_COUNT;
        }

        internal static List<StoredVehicle> GetStoredVehicles()
        {
            string key = CharacterKey();
            if (_stored.TryGetValue(key, out var list))
                return list;
            return new List<StoredVehicle>();
        }

        /// <summary>
        /// Deliver a vehicle to the current character's garage.
        /// </summary>
        internal static bool DeliverVehicle(string model, int color1, int color2)
        {
            string key = CharacterKey();
            if (!_stored.TryGetValue(key, out var list))
                return false;

            if (list.Count >= SLOT_COUNT)
            {
                Log($"DeliverVehicle: garage full ({list.Count}/{SLOT_COUNT})");
                return false;
            }

            int slotIndex = FindEmptySlot(list, model);
            if (slotIndex < 0)
            {
                Log($"DeliverVehicle: no empty slot for {model} (sizeTier={VehicleList.GetSizeTier(model)})");
                return false;
            }

            var stored = new StoredVehicle
            {
                Model = model,
                Slot = slotIndex,
                Color1 = color1,
                Color2 = color2,
            };
            list.Add(stored);

            // If player is currently inside the garage, spawn it immediately
            if (_isPlayerInGarage)
            {
                try
                {
                    ParkingSlot slot = Slots[slotIndex];
                    Vehicle veh = VehicleHelper.CreateVehicle(
                        model, slot.Position, slot.Heading, color1, color2);
                    if (veh != null)
                    {
                        veh.IsPersistent = true;
                        veh.IsEngineRunning = false;
                        float deltaZ = VehicleList.GetSpawnDeltaZ(model);
                        Function.Call(Hash.SET_ENTITY_COORDS, veh,
                            slot.Position.X, slot.Position.Y, slot.Position.Z + deltaZ,
                            false, false, false, true);
                        Function.Call(Hash.SET_ENTITY_HEADING, veh, slot.Heading);
                        veh.IsPositionFrozen = true;
                        _handles[slotIndex] = veh;
                    }
                }
                catch (Exception ex)
                {
                    LogException("DeliverVehicle.SpawnInGarage", ex);
                }
            }

            Log($"DeliverVehicle: {model} -> slot {slotIndex}");
            Save();
            return true;
        }

        /// <summary>
        /// Remove a stored vehicle by its index in the stored list.
        /// </summary>
        internal static void RemoveVehicle(int listIndex)
        {
            string key = CharacterKey();
            if (!_stored.TryGetValue(key, out var list))
                return;
            if (listIndex < 0 || listIndex >= list.Count)
                return;

            StoredVehicle sv = list[listIndex];
            int slotIndex = sv.Slot;

            // Delete the entity if it's spawned
            if (slotIndex >= 0 && slotIndex < SLOT_COUNT)
            {
                Vehicle veh = _handles[slotIndex];
                if (veh != null && veh.Exists())
                {
                    veh.IsPersistent = true;
                    veh.Delete();
                }
                _handles[slotIndex] = null;
            }

            Log($"RemoveVehicle: {sv.Model} from slot {slotIndex}");
            list.RemoveAt(listIndex);
            Save();
        }

        /// <summary>
        /// Clean (detail) all spawned vehicles in the garage.
        /// Sets dirt level to 0 and fixes any damage.
        /// </summary>
        internal static void DetailVehicles()
        {
            int cleaned = 0;
            for (int i = 0; i < SLOT_COUNT; i++)
            {
                Vehicle veh = _handles[i];
                if (veh == null || !veh.Exists())
                    continue;

                Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, veh, 0f);
                Function.Call(Hash.SET_VEHICLE_FIXED, veh);
                cleaned++;
            }
            Log($"DetailVehicles: cleaned {cleaned} vehicles");
        }

        /// <summary>
        /// Draw debug markers at all parking slots and entrance/exit points.
        /// </summary>
        internal static void DrawDebugMarkers()
        {
            // Entrance
            World.DrawMarker(
                GTA.MarkerType.UpsideDownCone,
                ENTRANCE_POS + new Vector3(0f, 0f, 2f),
                Vector3.Zero, Vector3.Zero,
                new Vector3(0.5f, 0.5f, 0.5f),
                System.Drawing.Color.FromArgb(128, 0, 255, 0));

            // Interior spawn + exit
            World.DrawMarker(
                GTA.MarkerType.UpsideDownCone,
                INTERIOR_SPAWN + new Vector3(0f, 0f, 2f),
                Vector3.Zero, Vector3.Zero,
                new Vector3(0.5f, 0.5f, 0.5f),
                System.Drawing.Color.FromArgb(128, 0, 0, 255));

            World.DrawMarker(
                GTA.MarkerType.UpsideDownCone,
                VEHICLE_EXIT_INTERIOR + new Vector3(0f, 0f, 2f),
                Vector3.Zero, Vector3.Zero,
                new Vector3(0.5f, 0.5f, 0.5f),
                System.Drawing.Color.FromArgb(128, 255, 255, 0));

            // Parking slots
            for (int i = 0; i < SLOT_COUNT; i++)
            {
                Vector3 pos = Slots[i].Position;
                World.DrawMarker(
                    GTA.MarkerType.UpsideDownCone,
                    pos + new Vector3(0f, 0f, 2f),
                    Vector3.Zero, Vector3.Zero,
                    new Vector3(0.5f, 0.5f, 0.5f),
                    System.Drawing.Color.FromArgb(128, 255, 128, 0));
            }
        }

        // ------------------------------------------------------------------ //
        //  Garage Enter / Leave                                               //
        // ------------------------------------------------------------------ //

        private static void EnterGarage()
        {
            Ped player = Game.Player.Character;

            // If player is in a vehicle, store it in the garage (if space),
            // then pull them out and delete the outside instance.
            // Personal vehicles are blocked — they can't be stored.
            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
                    if (IsPersonalVehicle(rideIn))
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~You cannot bring your personal vehicle into the garage.", 3000);
                        return;
                    }

                    // Resolve spawn name from model hash before slot assignment
                    int modelHash = rideIn.Model.Hash;
                    string modelName;
                    if (_hashToSpawnName != null && _hashToSpawnName.TryGetValue(modelHash, out string spawnName))
                    {
                        modelName = spawnName;
                    }
                    else
                    {
                        modelName = Function.Call<string>(
                            Hash.GET_DISPLAY_NAME_FROM_VEHICLE_MODEL,
                            (uint)modelHash);
                        if (!string.IsNullOrEmpty(modelName))
                            modelName = modelName.ToLowerInvariant();
                        else
                            modelName = modelHash.ToString();
                        Log($"EnterGarage: vehicle hash {modelHash} not in VehicleList, fallback name={modelName}");
                    }

                    // Reject oversized vehicles
                    if (VehicleList.GetSizeTier(modelName) == 2)
                    {
                        string ovName = VehicleList.DisplayNames.ContainsKey(modelName)
                            ? VehicleList.DisplayNames[modelName] : modelName;
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~{ovName}~w~ is too large for this garage. Use the 3-Floor Garage.", 3000);
                        return;
                    }

                    // Try to store the vehicle in the garage
                    string charKey = CharacterKey();
                    if (!_stored.TryGetValue(charKey, out var storedList))
                    {
                        storedList = new List<StoredVehicle>();
                        _stored[charKey] = storedList;
                    }

                    if (storedList.Count >= SLOT_COUNT)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~Garage full.~w~ ({storedList.Count}/{SLOT_COUNT} slots used)", 3000);
                        return;
                    }

                    int slotIndex = FindEmptySlot(storedList, modelName);
                    if (slotIndex < 0)
                    {
                        GTA.UI.Screen.ShowSubtitle("~r~Garage full. No empty slots.", 3000);
                        return;
                    }

                    // Capture full vehicle state (colors, mods, etc.)
                    StoredVehicle sv = CaptureVehicleState(rideIn, modelName, slotIndex);
                    storedList.Add(sv);
                    Save();

                    string displayName = VehicleList.DisplayNames.ContainsKey(modelName)
                        ? VehicleList.DisplayNames[modelName] : modelName;
                    GTA.UI.Screen.ShowSubtitle(
                        $"~g~{displayName}~w~ stored in garage. (Slot {slotIndex + 1})", 3000);
                    Log($"EnterGarage: stored drive-in vehicle {modelName} -> slot {slotIndex}");

                    // Delete the outside vehicle (teleporting the player
                    // out via SET_ENTITY_COORDS below handles extraction)
                    rideIn.IsPersistent = true;
                    rideIn.Delete();
                }
            }

            // Clear any leftover handles from a previous session
            for (int i = 0; i < SLOT_COUNT; i++)
            {
                if (_handles[i] != null && _handles[i].Exists())
                    _handles[i].Delete();
                _handles[i] = null;
            }

            // Fade to black before teleporting
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            while (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                Script.Wait(0);

            // Freeze player and teleport to safe interior position
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                PED_EXIT.X, PED_EXIT.Y, PED_EXIT.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player, PED_EXIT_HEADING);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, true);

            _isPlayerInGarage = true; // set early to block re-entry during spawning

            // Pre-load all vehicle models before spawning
            string key = CharacterKey();
            var models = new List<Model>();
            if (_stored.TryGetValue(key, out var list))
            {
                Log($"EnterGarage: pre-loading {list.Count} vehicle models");
                foreach (var sv in list)
                {
                    var m = new Model(sv.Model);
                    m.Request();
                    models.Add(m);
                }

                // Wait for all models to load (up to 10s total)
                DateTime deadline = DateTime.UtcNow.AddMilliseconds(10000);
                bool allLoaded = false;
                while (!allLoaded && DateTime.UtcNow < deadline)
                {
                    allLoaded = true;
                    foreach (var m in models)
                    {
                        if (!m.IsLoaded) { allLoaded = false; break; }
                    }
                    if (!allLoaded) Script.Wait(0);
                }

                // Now spawn all vehicles quickly
                foreach (var sv in list)
                {
                    if (sv.Slot < 0 || sv.Slot >= SLOT_COUNT)
                    {
                        Log($"EnterGarage: skipping {sv.Model}, invalid slot {sv.Slot}");
                        continue;
                    }

                    ParkingSlot slot = Slots[sv.Slot];
                    try
                    {
                        var model = new Model(sv.Model);
                        Vehicle veh = World.CreateVehicle(model, slot.Position, slot.Heading);
                        model.MarkAsNoLongerNeeded();

                        if (veh != null)
                        {
                            ApplyVehicleState(veh, sv);
                            veh.IsPersistent = true;
                            veh.IsEngineRunning = false;
                            float deltaZ = VehicleList.GetSpawnDeltaZ(sv.Model);
                            Function.Call(Hash.SET_ENTITY_COORDS, veh,
                                slot.Position.X, slot.Position.Y, slot.Position.Z + deltaZ,
                                false, false, false, true);
                            Function.Call(Hash.SET_ENTITY_HEADING, veh, slot.Heading);
                            veh.IsPositionFrozen = true;
                            _handles[sv.Slot] = veh;
                            Log($"EnterGarage: spawned {sv.Model} at slot {sv.Slot} (deltaZ={deltaZ:F3})");
                        }
                        else
                        {
                            Log($"EnterGarage: FAILED to spawn {sv.Model} at slot {sv.Slot}");
                        }
                    }
                    catch (Exception ex)
                    {
                        LogException($"EnterGarage.Spawn({sv.Model})", ex);
                    }
                }

                // Release models
                foreach (var m in models)
                    m.MarkAsNoLongerNeeded();
            }

            // Unfreeze player
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            player.IsPositionFrozen = false;

            // Fade back in
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);

            Log($"EnterGarage: character={key}, vehicles spawned");
        }

        private static void LeaveGarage()
        {
            // Save all vehicle states before leaving
            UpdateStoredFromLive();

            Ped player = Game.Player.Character;
            Vehicle playerVehicle = null;
            int playerSlotIndex = -1;

            // Check if player is in one of the garage vehicles
            if (player.IsInVehicle())
            {
                Vehicle current = player.CurrentVehicle;
                if (current != null && current.Exists())
                {
                    for (int i = 0; i < SLOT_COUNT; i++)
                    {
                        if (_handles[i] != null && _handles[i] == current)
                        {
                            playerVehicle = current;
                            playerSlotIndex = i;
                            _handles[i] = null; // detach from garage — don't delete
                            break;
                        }
                    }
                }
            }

            // Delete all OTHER spawned vehicles
            for (int i = 0; i < SLOT_COUNT; i++)
            {
                Vehicle veh = _handles[i];
                if (veh != null && veh.Exists())
                {
                    veh.IsPersistent = true;
                    veh.Delete();
                }
                _handles[i] = null;
            }

            // Fade to black before teleporting outside
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            while (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                Script.Wait(0);

            if (playerVehicle != null)
            {
                // IMPORTANT: Remove the driven-out vehicle from the stored list
                // so it doesn't get duped on next entry. The player is taking
                // it out of the garage.
                string key = CharacterKey();
                if (_stored.TryGetValue(key, out var list))
                {
                    for (int i = list.Count - 1; i >= 0; i--)
                    {
                        if (list[i].Slot == playerSlotIndex)
                        {
                            Log($"LeaveGarage: removing {list[i].Model} from slot {playerSlotIndex} (driven out)");
                            list.RemoveAt(i);
                            break;
                        }
                    }
                }

                // Teleport vehicle (with player inside) to vehicle entrance
                playerVehicle.IsPositionFrozen = false;
                playerVehicle.IsPersistent = true;
                Function.Call(Hash.SET_ENTITY_COORDS, playerVehicle,
                    ENTRANCE_POS.X, ENTRANCE_POS.Y, ENTRANCE_POS.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, playerVehicle, 180f);
                playerVehicle.IsEngineRunning = true;
                Function.Call(Hash.SET_VEHICLE_ON_GROUND_PROPERLY, playerVehicle);

                Save();
                Log("LeaveGarage: drove out in vehicle");
            }
            else
            {
                // Teleport player on foot to ped entrance
                Vector3 dest = PED_EXIT_DEST;
                float heading = PED_EXIT_DEST_HEADING;

                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    dest.X, dest.Y, dest.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player, heading);
                player.IsPositionFrozen = false;

                Save();
                Log($"LeaveGarage: returned on foot to {CharacterKey()} ped entrance");
            }

            _isPlayerInGarage = false;
            _exitCooldownFrames = 60; // ~1 second cooldown

            // Fade back in
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
        }

        // ------------------------------------------------------------------ //
        //  Helpers                                                            //
        // ------------------------------------------------------------------ //

        /// <summary>
        /// Check if a vehicle is the character's assigned personal vehicle
        /// (e.g., Michael's Tailgater, Franklin's Buffalo/Bagger, Trevor's Bodhi).
        /// Uses multiple detection methods since Enhanced may differ from legacy.
        /// </summary>
        private static bool IsPersonalVehicle(Vehicle veh)
        {
            // Method 1: Decorator check (how decompiled scripts detect it)
            try
            {
                bool hasDecorator = Function.Call<bool>(
                    (Hash)0x05661B80A8C9165F, // DECOR_EXIST_ON
                    veh, "Player_Vehicle");
                if (hasDecorator)
                    return true;
            }
            catch { }

            // Method 2: Check if vehicle has an attached blip with the
            // personal vehicle sprite (blip exists + is special car sprite).
            // The game assigns a unique blip to story-mode personal vehicles.
            Blip vehBlip = veh.AttachedBlip;
            if (vehBlip != null && vehBlip.Exists())
            {
                // Personal vehicles have a blip. Regular random cars don't.
                // Check that it's not one of OUR garage blips.
                BlipSprite sprite = vehBlip.Sprite;
                if (sprite == BlipSprite.PersonalVehicleCar ||
                    sprite == BlipSprite.PersonalVehicleBike)
                    return true;
            }

            return false;
        }

        /// <summary>
        /// Every tick while inside the garage, keep all parked vehicles
        /// frozen with engines off. The player's current vehicle is excluded
        /// so they can get in/out of cars but not drive them around.
        /// </summary>
        private static void EnforceGarageVehicleState(Ped player)
        {
            Vehicle playerVeh = player.IsInVehicle() ? player.CurrentVehicle : null;

            for (int i = 0; i < SLOT_COUNT; i++)
            {
                Vehicle veh = _handles[i];
                if (veh == null || !veh.Exists())
                    continue;

                if (playerVeh != null && veh == playerVeh)
                {
                    // Player is sitting in this vehicle — keep it frozen
                    // so they can't drive around. Engine stays off.
                    veh.IsPositionFrozen = true;
                    veh.IsEngineRunning = false;
                    continue;
                }

                // All other parked vehicles stay frozen and engines off
                veh.IsPositionFrozen = true;
                veh.IsEngineRunning = false;
            }
        }

        private static BlipColor CharacterBlipColor()
        {
            PedHash ch = GbayShop.GetCurrentCharacter();
            if (ch == PedHash.Franklin) return BlipColor.Green;
            if (ch == PedHash.Trevor)   return BlipColor.Orange;
            return BlipColor.Blue; // Michael
        }

        private static System.Drawing.Color CharacterMarkerColor()
        {
            PedHash ch = GbayShop.GetCurrentCharacter();
            if (ch == PedHash.Franklin) return System.Drawing.Color.FromArgb(128, 100, 255, 100);
            if (ch == PedHash.Trevor)   return System.Drawing.Color.FromArgb(128, 255, 170, 50);
            return System.Drawing.Color.FromArgb(128, 100, 100, 255); // Michael
        }

        private static string CharacterKey()
        {
            PedHash ch = GbayShop.GetCurrentCharacter();
            if (ch == PedHash.Franklin) return KEY_FRANKLIN;
            if (ch == PedHash.Trevor) return KEY_TREVOR;
            return KEY_MICHAEL;
        }

        private static int FindEmptySlot(List<StoredVehicle> list, string model = null)
        {
            var occupied = new HashSet<int>();
            foreach (var sv in list)
                occupied.Add(sv.Slot);

            int sizeTier = (model != null) ? VehicleList.GetSizeTier(model) : 0;

            if (sizeTier >= 1) // large vehicles: left row only (slots 0-4)
            {
                for (int i = 0; i < 5; i++)
                    if (!occupied.Contains(i)) return i;
                return -1;
            }

            // Normal vehicles: prefer right row first (slots 5-9) to leave
            // left row available for large vehicles. Fall back to left row.
            for (int i = 5; i < SLOT_COUNT; i++)
                if (!occupied.Contains(i)) return i;
            for (int i = 0; i < 5; i++)
                if (!occupied.Contains(i)) return i;

            return -1;
        }

        // ------------------------------------------------------------------ //
        //  JSON persistence                                                   //
        // ------------------------------------------------------------------ //

        private static void Load()
        {
            if (!File.Exists(SAVE_PATH))
                return;

            try
            {
                string json = File.ReadAllText(SAVE_PATH);
                ParseJson(json);
                MigrateModelNames();
            }
            catch (Exception ex)
            {
                LogException("Load", ex);
            }
        }

        /// <summary>
        /// Fix stored vehicles that were saved with GXT labels instead of
        /// spawn names (e.g. "insurgent" instead of "insurgent3"). Uses the
        /// hash lookup built during Initialize.
        /// </summary>
        private static void MigrateModelNames()
        {
            if (_hashToSpawnName == null || _hashToSpawnName.Count == 0)
                return;

            // Build a set of valid spawn names for quick lookup
            var validNames = new HashSet<string>();
            foreach (string name in VehicleList.All)
                validNames.Add(name);

            bool changed = false;
            foreach (var kvp in _stored)
            {
                foreach (var sv in kvp.Value)
                {
                    if (validNames.Contains(sv.Model))
                        continue; // already a valid spawn name

                    // Try to resolve: compute hash of stored name and see if
                    // it maps to a known vehicle (it won't if the GXT label
                    // differs from the spawn name)
                    int hash = Game.GenerateHash(sv.Model);
                    if (_hashToSpawnName.TryGetValue(hash, out string correctName))
                    {
                        Log($"Migrate: {sv.Model} -> {correctName} (hash match)");
                        sv.Model = correctName;
                        changed = true;
                    }
                    else
                    {
                        Log($"Migrate: {sv.Model} has no matching spawn name (hash {hash}), vehicle may not spawn");
                    }
                }
            }

            if (changed)
                Save();
        }

        private static void Save()
        {
            try
            {
                string json = BuildJson();
                string tmp = SAVE_PATH + ".tmp";
                File.WriteAllText(tmp, json);
                if (File.Exists(SAVE_PATH))
                    File.Delete(SAVE_PATH);
                File.Move(tmp, SAVE_PATH);
            }
            catch (Exception ex)
            {
                LogException("Save", ex);
            }
        }

        private static string BuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");

            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");

                if (_stored.TryGetValue(key, out var list) && list.Count > 0)
                {
                    sb.AppendLine();
                    for (int i = 0; i < list.Count; i++)
                    {
                        var sv = list[i];
                        sb.Append("    { ");
                        sb.Append($"\"model\": \"{sv.Model}\", ");
                        sb.Append($"\"slot\": {sv.Slot}, ");
                        sb.Append($"\"color1\": {sv.Color1}, ");
                        sb.Append($"\"color2\": {sv.Color2}");

                        if (sv.PlateText != null)
                            sb.Append($", \"plate\": \"{EscapeJson(sv.PlateText)}\"");
                        if (sv.PlateStyle != 0)
                            sb.Append($", \"plateStyle\": {sv.PlateStyle}");
                        if (sv.WheelType != 0)
                            sb.Append($", \"wheelType\": {sv.WheelType}");
                        if (sv.WindowTint != 0)
                            sb.Append($", \"windowTint\": {sv.WindowTint}");
                        if (sv.Livery > 0)
                            sb.Append($", \"livery\": {sv.Livery}");
                        if (sv.PearlescentColor != 0)
                            sb.Append($", \"pearlescent\": {sv.PearlescentColor}");
                        if (sv.RimColor != 0)
                            sb.Append($", \"rimColor\": {sv.RimColor}");

                        if (sv.Mods != null)
                            sb.Append($", \"mods\": [{string.Join(",", sv.Mods)}]");
                        if (sv.ModToggles != null)
                            sb.Append($", \"modToggles\": [{string.Join(",", BoolArrayToInts(sv.ModToggles))}]");
                        if (sv.NeonEnabled != null)
                            sb.Append($", \"neonEnabled\": [{string.Join(",", sv.NeonEnabled)}]");
                        if (sv.NeonColor != null)
                            sb.Append($", \"neonColor\": [{string.Join(",", sv.NeonColor)}]");
                        if (sv.TyreSmokeColor != null)
                            sb.Append($", \"tyreSmokeColor\": [{string.Join(",", sv.TyreSmokeColor)}]");
                        if (sv.Extras != null)
                            sb.Append($", \"extras\": [{string.Join(",", sv.Extras)}]");
                        if (sv.CustomPrimaryColor && sv.CustomPrimary != null)
                            sb.Append($", \"customPrimary\": [{string.Join(",", sv.CustomPrimary)}]");
                        if (sv.CustomSecondaryColor && sv.CustomSecondary != null)
                            sb.Append($", \"customSecondary\": [{string.Join(",", sv.CustomSecondary)}]");

                        sb.Append(" }");
                        if (i < list.Count - 1)
                            sb.AppendLine(",");
                        else
                            sb.AppendLine();
                    }
                    sb.Append("  ]");
                }
                else
                {
                    sb.Append("]");
                }

                if (k < keys.Length - 1)
                    sb.AppendLine(",");
                else
                    sb.AppendLine();
            }

            sb.AppendLine("}");
            return sb.ToString();
        }

        private static string EscapeJson(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        private static int[] BoolArrayToInts(bool[] arr)
        {
            if (arr == null) return new int[0];
            int[] result = new int[arr.Length];
            for (int i = 0; i < arr.Length; i++)
                result[i] = arr[i] ? 1 : 0;
            return result;
        }

        private static void ParseJson(string json)
        {
            string currentKey = null;

            int i = 0;
            while (i < json.Length)
            {
                char c = json[i];

                if (c == '"')
                {
                    int end = json.IndexOf('"', i + 1);
                    if (end < 0) break;
                    string str = json.Substring(i + 1, end - i - 1);
                    i = end + 1;

                    if (currentKey == null)
                    {
                        int peek = SkipWhitespace(json, i);
                        if (peek < json.Length && json[peek] == ':')
                        {
                            currentKey = str;
                            i = peek + 1;
                        }
                    }
                    continue;
                }

                if (c == '[' && currentKey != null)
                {
                    i++;
                    var vehicles = ParseVehicleArray(json, ref i);

                    if (_stored.ContainsKey(currentKey))
                        _stored[currentKey] = vehicles;

                    currentKey = null;
                    continue;
                }

                i++;
            }
        }

        private static List<StoredVehicle> ParseVehicleArray(string json, ref int i)
        {
            var result = new List<StoredVehicle>();

            while (i < json.Length)
            {
                char c = json[i];

                if (c == ']')
                {
                    i++;
                    break;
                }

                if (c == '{')
                {
                    i++;
                    var sv = ParseVehicleObject(json, ref i);
                    if (sv != null)
                        result.Add(sv);
                    continue;
                }

                i++;
            }

            return result;
        }

        private static StoredVehicle ParseVehicleObject(string json, ref int i)
        {
            var sv = new StoredVehicle();
            string model = null;
            int slot = -1;

            while (i < json.Length)
            {
                char c = json[i];

                if (c == '}')
                {
                    i++;
                    break;
                }

                if (c == '"')
                {
                    int end = json.IndexOf('"', i + 1);
                    if (end < 0) break;
                    string key = json.Substring(i + 1, end - i - 1);
                    i = end + 1;

                    i = SkipWhitespace(json, i);
                    if (i < json.Length && json[i] == ':')
                        i++;
                    i = SkipWhitespace(json, i);

                    if (key == "model" || key == "plate")
                    {
                        if (i < json.Length && json[i] == '"')
                        {
                            int vEnd = json.IndexOf('"', i + 1);
                            if (vEnd >= 0)
                            {
                                string val = json.Substring(i + 1, vEnd - i - 1);
                                if (key == "model") model = val;
                                else sv.PlateText = val;
                                i = vEnd + 1;
                            }
                        }
                    }
                    else if (json[i] == '[')
                    {
                        // Parse int array
                        int[] arr = ParseIntArray(json, ref i);
                        switch (key)
                        {
                            case "mods": sv.Mods = arr; break;
                            case "modToggles": sv.ModToggles = IntsToBoolArray(arr); break;
                            case "neonEnabled": sv.NeonEnabled = arr; break;
                            case "neonColor": sv.NeonColor = arr; break;
                            case "tyreSmokeColor": sv.TyreSmokeColor = arr; break;
                            case "extras": sv.Extras = arr; break;
                            case "customPrimary":
                                sv.CustomPrimaryColor = true;
                                sv.CustomPrimary = arr;
                                break;
                            case "customSecondary":
                                sv.CustomSecondaryColor = true;
                                sv.CustomSecondary = arr;
                                break;
                        }
                    }
                    else
                    {
                        int numStart = i;
                        while (i < json.Length && (char.IsDigit(json[i]) || json[i] == '-'))
                            i++;
                        string numStr = json.Substring(numStart, i - numStart);
                        if (int.TryParse(numStr, out int val))
                        {
                            switch (key)
                            {
                                case "slot": slot = val; break;
                                case "color1": sv.Color1 = val; break;
                                case "color2": sv.Color2 = val; break;
                                case "wheelType": sv.WheelType = val; break;
                                case "windowTint": sv.WindowTint = val; break;
                                case "livery": sv.Livery = val; break;
                                case "plateStyle": sv.PlateStyle = val; break;
                                case "pearlescent": sv.PearlescentColor = val; break;
                                case "rimColor": sv.RimColor = val; break;
                            }
                        }
                    }
                    continue;
                }

                i++;
            }

            if (model != null && slot >= 0)
            {
                sv.Model = model;
                sv.Slot = slot;
                return sv;
            }
            return null;
        }

        private static int[] ParseIntArray(string json, ref int i)
        {
            var result = new List<int>();
            i++; // skip '['

            while (i < json.Length)
            {
                char c = json[i];
                if (c == ']') { i++; break; }

                if (char.IsDigit(c) || c == '-')
                {
                    int numStart = i;
                    while (i < json.Length && (char.IsDigit(json[i]) || json[i] == '-'))
                        i++;
                    string numStr = json.Substring(numStart, i - numStart);
                    if (int.TryParse(numStr, out int val))
                        result.Add(val);
                    continue;
                }
                i++;
            }

            return result.ToArray();
        }

        private static bool[] IntsToBoolArray(int[] arr)
        {
            if (arr == null) return null;
            bool[] result = new bool[arr.Length];
            for (int j = 0; j < arr.Length; j++)
                result[j] = arr[j] != 0;
            return result;
        }

        private static int SkipWhitespace(string s, int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i]))
                i++;
            return i;
        }

        // ------------------------------------------------------------------ //
        //  Vehicle State Capture / Apply                                      //
        // ------------------------------------------------------------------ //

        private const int MOD_SLOT_COUNT = 50;
        private const int EXTRA_COUNT = 15;

        /// <summary>
        /// Capture full vehicle customization state for persistence.
        /// </summary>
        internal static StoredVehicle CaptureVehicleState(Vehicle veh, string model, int slotIndex)
        {
            var sv = new StoredVehicle { Model = model, Slot = slotIndex };

            try
            {
                // Colors
                {
                    OutputArgument outC1 = new OutputArgument();
                    OutputArgument outC2 = new OutputArgument();
                    Function.Call(Hash.GET_VEHICLE_COLOURS, veh, outC1, outC2);
                    sv.Color1 = outC1.GetResult<int>();
                    sv.Color2 = outC2.GetResult<int>();
                }

                // Pearlescent + rim color
                {
                    OutputArgument outP = new OutputArgument();
                    OutputArgument outR = new OutputArgument();
                    Function.Call(Hash.GET_VEHICLE_EXTRA_COLOURS, veh, outP, outR);
                    sv.PearlescentColor = outP.GetResult<int>();
                    sv.RimColor = outR.GetResult<int>();
                }

                // Custom primary/secondary colors
                if (Function.Call<bool>(Hash.GET_IS_VEHICLE_PRIMARY_COLOUR_CUSTOM, veh))
                {
                    sv.CustomPrimaryColor = true;
                    OutputArgument r = new OutputArgument(), g = new OutputArgument(), b = new OutputArgument();
                    Function.Call(Hash.GET_VEHICLE_CUSTOM_PRIMARY_COLOUR, veh, r, g, b);
                    sv.CustomPrimary = new int[] { r.GetResult<int>(), g.GetResult<int>(), b.GetResult<int>() };
                }

                if (Function.Call<bool>(Hash.GET_IS_VEHICLE_SECONDARY_COLOUR_CUSTOM, veh))
                {
                    sv.CustomSecondaryColor = true;
                    OutputArgument r = new OutputArgument(), g = new OutputArgument(), b = new OutputArgument();
                    Function.Call(Hash.GET_VEHICLE_CUSTOM_SECONDARY_COLOUR, veh, r, g, b);
                    sv.CustomSecondary = new int[] { r.GetResult<int>(), g.GetResult<int>(), b.GetResult<int>() };
                }

                // Plate
                sv.PlateText = Function.Call<string>(Hash.GET_VEHICLE_NUMBER_PLATE_TEXT, veh);
                sv.PlateStyle = Function.Call<int>(Hash.GET_VEHICLE_NUMBER_PLATE_TEXT_INDEX, veh);

                // Mods
                Function.Call(Hash.SET_VEHICLE_MOD_KIT, veh, 0);
                sv.WheelType = Function.Call<int>(Hash.GET_VEHICLE_WHEEL_TYPE, veh);
                sv.WindowTint = Function.Call<int>(Hash.GET_VEHICLE_WINDOW_TINT, veh);
                sv.Livery = Function.Call<int>(Hash.GET_VEHICLE_LIVERY, veh);

                sv.Mods = new int[MOD_SLOT_COUNT];
                sv.ModToggles = new bool[MOD_SLOT_COUNT];
                for (int m = 0; m < MOD_SLOT_COUNT; m++)
                {
                    sv.Mods[m] = Function.Call<int>(Hash.GET_VEHICLE_MOD, veh, m);
                    sv.ModToggles[m] = Function.Call<bool>(Hash.IS_TOGGLE_MOD_ON, veh, m);
                }

                // Neon lights
                sv.NeonEnabled = new int[4];
                for (int n = 0; n < 4; n++)
                    sv.NeonEnabled[n] = Function.Call<bool>(Hash.GET_VEHICLE_NEON_ENABLED, veh, n) ? 1 : 0;

                {
                    OutputArgument r = new OutputArgument(), g = new OutputArgument(), b = new OutputArgument();
                    Function.Call(Hash.GET_VEHICLE_NEON_COLOUR, veh, r, g, b);
                    sv.NeonColor = new int[] { r.GetResult<int>(), g.GetResult<int>(), b.GetResult<int>() };
                }

                // Tyre smoke
                {
                    OutputArgument r = new OutputArgument(), g = new OutputArgument(), b = new OutputArgument();
                    Function.Call(Hash.GET_VEHICLE_TYRE_SMOKE_COLOR, veh, r, g, b);
                    sv.TyreSmokeColor = new int[] { r.GetResult<int>(), g.GetResult<int>(), b.GetResult<int>() };
                }

                // Extras
                var extras = new List<int>();
                for (int e = 0; e < EXTRA_COUNT; e++)
                {
                    if (Function.Call<bool>(Hash.DOES_EXTRA_EXIST, veh, e))
                    {
                        if (Function.Call<bool>(Hash.IS_VEHICLE_EXTRA_TURNED_ON, veh, e))
                            extras.Add(e);
                    }
                }
                if (extras.Count > 0)
                    sv.Extras = extras.ToArray();
            }
            catch (Exception ex)
            {
                LogException("CaptureVehicleState", ex);
            }

            return sv;
        }

        /// <summary>
        /// Apply saved customization state to a spawned vehicle.
        /// </summary>
        private static void ApplyVehicleState(Vehicle veh, StoredVehicle sv)
        {
            try
            {
                // Colors
                Function.Call(Hash.SET_VEHICLE_COLOURS, veh, sv.Color1, sv.Color2);

                // Custom colors
                if (sv.CustomPrimaryColor && sv.CustomPrimary != null && sv.CustomPrimary.Length >= 3)
                    Function.Call(Hash.SET_VEHICLE_CUSTOM_PRIMARY_COLOUR, veh,
                        sv.CustomPrimary[0], sv.CustomPrimary[1], sv.CustomPrimary[2]);

                if (sv.CustomSecondaryColor && sv.CustomSecondary != null && sv.CustomSecondary.Length >= 3)
                    Function.Call(Hash.SET_VEHICLE_CUSTOM_SECONDARY_COLOUR, veh,
                        sv.CustomSecondary[0], sv.CustomSecondary[1], sv.CustomSecondary[2]);

                // Pearlescent + rim
                if (sv.PearlescentColor != 0 || sv.RimColor != 0)
                    Function.Call(Hash.SET_VEHICLE_EXTRA_COLOURS, veh, sv.PearlescentColor, sv.RimColor);

                // Plate
                if (sv.PlateText != null)
                    Function.Call(Hash.SET_VEHICLE_NUMBER_PLATE_TEXT, veh, sv.PlateText);
                if (sv.PlateStyle != 0)
                    Function.Call(Hash.SET_VEHICLE_NUMBER_PLATE_TEXT_INDEX, veh, sv.PlateStyle);

                // Mod kit must be set before applying mods
                Function.Call(Hash.SET_VEHICLE_MOD_KIT, veh, 0);

                // Wheel type
                if (sv.WheelType != 0)
                    Function.Call(Hash.SET_VEHICLE_WHEEL_TYPE, veh, sv.WheelType);

                // Mods
                if (sv.Mods != null)
                {
                    for (int m = 0; m < sv.Mods.Length && m < MOD_SLOT_COUNT; m++)
                    {
                        if (sv.Mods[m] >= 0)
                            Function.Call(Hash.SET_VEHICLE_MOD, veh, m, sv.Mods[m], false);
                    }
                }

                // Toggle mods
                if (sv.ModToggles != null)
                {
                    for (int m = 0; m < sv.ModToggles.Length && m < MOD_SLOT_COUNT; m++)
                    {
                        if (sv.ModToggles[m])
                            Function.Call(Hash.TOGGLE_VEHICLE_MOD, veh, m, true);
                    }
                }

                // Window tint
                if (sv.WindowTint != 0)
                    Function.Call(Hash.SET_VEHICLE_WINDOW_TINT, veh, sv.WindowTint);

                // Livery
                if (sv.Livery > 0)
                    Function.Call(Hash.SET_VEHICLE_LIVERY, veh, sv.Livery);

                // Neon lights
                if (sv.NeonEnabled != null)
                {
                    for (int n = 0; n < sv.NeonEnabled.Length && n < 4; n++)
                        Function.Call(Hash.SET_VEHICLE_NEON_ENABLED, veh, n, sv.NeonEnabled[n] != 0);
                }
                if (sv.NeonColor != null && sv.NeonColor.Length >= 3)
                    Function.Call(Hash.SET_VEHICLE_NEON_COLOUR, veh, sv.NeonColor[0], sv.NeonColor[1], sv.NeonColor[2]);

                // Tyre smoke
                if (sv.TyreSmokeColor != null && sv.TyreSmokeColor.Length >= 3)
                    Function.Call(Hash.SET_VEHICLE_TYRE_SMOKE_COLOR, veh,
                        sv.TyreSmokeColor[0], sv.TyreSmokeColor[1], sv.TyreSmokeColor[2]);

                // Extras
                if (sv.Extras != null)
                {
                    // Turn off all extras first, then enable saved ones
                    for (int e = 0; e < EXTRA_COUNT; e++)
                    {
                        if (Function.Call<bool>(Hash.DOES_EXTRA_EXIST, veh, e))
                            Function.Call(Hash.SET_VEHICLE_EXTRA, veh, e, true); // true = OFF in GTA
                    }
                    foreach (int e in sv.Extras)
                        Function.Call(Hash.SET_VEHICLE_EXTRA, veh, e, false); // false = ON in GTA
                }
            }
            catch (Exception ex)
            {
                LogException("ApplyVehicleState", ex);
            }
        }

        /// <summary>
        /// Update a stored vehicle's state from its live entity.
        /// Called when leaving the garage to persist any changes.
        /// </summary>
        internal static void UpdateStoredFromLive()
        {
            if (!_isPlayerInGarage) return;

            string key = CharacterKey();
            if (!_stored.TryGetValue(key, out var list)) return;

            foreach (var sv in list)
            {
                if (sv.Slot < 0 || sv.Slot >= SLOT_COUNT) continue;
                Vehicle veh = _handles[sv.Slot];
                if (veh == null || !veh.Exists()) continue;

                // Re-capture state from the live vehicle
                var updated = CaptureVehicleState(veh, sv.Model, sv.Slot);
                sv.Color1 = updated.Color1;
                sv.Color2 = updated.Color2;
                sv.Mods = updated.Mods;
                sv.ModToggles = updated.ModToggles;
                sv.WheelType = updated.WheelType;
                sv.WindowTint = updated.WindowTint;
                sv.Livery = updated.Livery;
                sv.PlateText = updated.PlateText;
                sv.PlateStyle = updated.PlateStyle;
                sv.PearlescentColor = updated.PearlescentColor;
                sv.RimColor = updated.RimColor;
                sv.NeonEnabled = updated.NeonEnabled;
                sv.NeonColor = updated.NeonColor;
                sv.TyreSmokeColor = updated.TyreSmokeColor;
                sv.Extras = updated.Extras;
                sv.CustomPrimaryColor = updated.CustomPrimaryColor;
                sv.CustomPrimary = updated.CustomPrimary;
                sv.CustomSecondaryColor = updated.CustomSecondaryColor;
                sv.CustomSecondary = updated.CustomSecondary;
            }

            Save();
        }

        // ================================================================== //
        //                                                                    //
        //  3-FLOOR GARAGE — Oversized vehicle storage (location TBD)         //
        //                                                                    //
        // ================================================================== //

        private const int FLOOR_GARAGE_SLOT_COUNT = 15; // 3 floors x 5 slots
        private const int FLOOR_GARAGE_SLOTS_PER_FLOOR = 5;

        // Outside entrance/exit — placeholder coordinates, will be set later
        private static readonly Vector3 FLOOR_GARAGE_ENTRANCE_POS =
            new Vector3(922.4f, 3564.8f, 33.8f);

        private static readonly Vector3 FLOOR_GARAGE_PED_EXIT_DEST =
            new Vector3(906f, 3554.3f, 33.8f);
        private const float FLOOR_GARAGE_PED_EXIT_DEST_HEADING = 180f;

        // Nightclub garage interior (DLC After Hours: BA_DLC_INT_02_BA)
        // Single physical room reused for all virtual floors
        // Must use full milo path names — short names don't load in SP
        private static readonly string[] FLOOR_GARAGE_IPLS =
        {
            "ba_int_placement_ba_interior_1_dlc_int_02_ba_milo_", // garage & storage
            "ba_int_placement_ba_interior_0_dlc_int_01_ba_milo_", // main nightclub
            "ba_int_placement_ba_interior_2_dlc_int_03_ba_milo_", // terrorbyte bay
        };

        // Interior ped spawn — at elevator 1 position
        private static readonly Vector3 FLOOR_GARAGE_INTERIOR_PED =
            new Vector3(-1507.55f, -3014.50f, -79.24f);
        private const float FLOOR_GARAGE_INTERIOR_PED_HEADING = 0f;

        // Elevator positions inside the garage (for floor switching + exit)
        private static readonly Vector3 FLOOR_GARAGE_ELEVATOR_1 =
            new Vector3(-1507.55f, -3014.50f, -79.24f);
        // Elevator 2 — TBD, will be set after in-game scouting
        private static readonly Vector3 FLOOR_GARAGE_ELEVATOR_2 =
            new Vector3(0f, 0f, 0f); // placeholder

        private const float ELEVATOR_INTERACT_RADIUS = 1.8f;

        // Virtual floor system — all 3 floors share the same 5 physical positions
        // within the nightclub garage interior. Only the current floor's vehicles
        // are spawned at a time; switching floors despawns/respawns.
        private static int _currentFloor; // 0, 1, or 2
        private static bool _elevatorMenuActive;
        private static int _elevatorMenuSelection; // 0=Floor1, 1=Floor2, 2=Floor3, 3=Exit

        // Garage customization — 5 categories, each with 3 options
        // Players pick one option per category per floor via GBay menu
        internal static readonly string[] CUSTOM_CATEGORY_NAMES =
            { "Floor", "Style", "Walls", "Decor", "Lighting" };

        internal static readonly string[][] CUSTOM_OPTION_LABELS =
        {
            new[] { "Option 1", "Option 2", "Option 3" },  // Floor
            new[] { "Option 1", "Option 2", "Option 3" },  // Style
            new[] { "Option 1", "Option 2", "Option 3" },  // Walls
            new[] { "Option 1", "Option 2", "Option 3" },  // Decor
            new[] { "Traditional", "Neon", "Glamorous" },   // Lighting
        };

        // Entity set name per [category][option]
        private static readonly string[][] CUSTOM_ENTITY_SETS =
        {
            new[] { "Int02_ba_floor01",     "Int02_ba_floor02",     "Int02_ba_floor03" },
            new[] { "Int02_ba_Style01",     "Int02_ba_Style02",     "Int02_ba_Style03" },
            new[] { "Int02_ba_walls_01",    "Int02_ba_walls_02",    "Int02_ba_walls_03" },
            new[] { "Int02_ba_decor_01",    "Int02_ba_decor_02",    "Int02_ba_decor_03" },
            new[] { "Int02_ba_trad_lights", "Int02_ba_neon",        "Int02_ba_lights" },
        };

        internal const int CUSTOM_CATEGORY_COUNT = 5;
        internal const int CUSTOM_OPTION_COUNT = 3;

        // Per-floor theme choices: _floorThemes[charKey][floor] = int[5] (one choice per category)
        // Default: floor 0 = all 0s, floor 1 = all 1s, floor 2 = all 2s
        private static readonly Dictionary<string, int[][]> _floorThemes =
            new Dictionary<string, int[][]>
            {
                { KEY_MICHAEL_FG,  DefaultThemes() },
                { KEY_FRANKLIN_FG, DefaultThemes() },
                { KEY_TREVOR_FG,   DefaultThemes() },
            };

        private static int[][] DefaultThemes()
        {
            return new[]
            {
                new[] { 0, 0, 0, 0, 0 }, // floor 0: all option 1
                new[] { 1, 1, 1, 1, 1 }, // floor 1: all option 2
                new[] { 2, 2, 2, 2, 2 }, // floor 2: all option 3
            };
        }

        /// <summary>
        /// Build the list of entity set names for a floor based on current theme choices.
        /// </summary>
        private static string[] GetFloorEntitySets(int floor)
        {
            string key = FloorGarageCharacterKey();
            int[][] themes = _floorThemes.ContainsKey(key) ? _floorThemes[key] : DefaultThemes();
            int[] choices = themes[floor];
            var sets = new string[CUSTOM_CATEGORY_COUNT];
            for (int c = 0; c < CUSTOM_CATEGORY_COUNT; c++)
                sets[c] = CUSTOM_ENTITY_SETS[c][choices[c]];
            return sets;
        }

        // 5 physical parking positions inside the nightclub garage interior
        // Laid out in a single row along the Y axis, all facing heading 0
        private static readonly ParkingSlot[] _floorGaragePhysicalSlots =
        {
            new ParkingSlot(-1517.0f, -3022.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3016.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3010.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3004.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -2998.0f, -80.0f, 0f),
        };

        // 15 logical slots across 3 virtual floors (5 per floor)
        // Floor 0 = slots 0-4, Floor 1 = slots 5-9, Floor 2 = slots 10-14
        // All floors share the same physical positions — only current floor is spawned
        internal static readonly ParkingSlot[] FloorGarageSlots =
        {
            // Floor 0 — 5 slots (physical positions 0-4)
            new ParkingSlot(-1517.0f, -3022.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3016.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3010.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3004.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -2998.0f, -80.0f, 0f),
            // Floor 1 — 5 slots (same physical positions)
            new ParkingSlot(-1517.0f, -3022.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3016.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3010.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3004.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -2998.0f, -80.0f, 0f),
            // Floor 2 — 5 slots (same physical positions)
            new ParkingSlot(-1517.0f, -3022.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3016.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3010.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -3004.0f, -80.0f, 0f),
            new ParkingSlot(-1517.0f, -2998.0f, -80.0f, 0f),
        };

        private static readonly string FLOOR_GARAGE_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_floor_garage.json");

        // Floor Garage character keys
        private const string KEY_MICHAEL_FG  = "michael_floor_garage";
        private const string KEY_FRANKLIN_FG = "franklin_floor_garage";
        private const string KEY_TREVOR_FG   = "trevor_floor_garage";

        private static readonly Dictionary<string, List<StoredVehicle>> _floorGarageStored =
            new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL_FG,  new List<StoredVehicle>() },
                { KEY_FRANKLIN_FG, new List<StoredVehicle>() },
                { KEY_TREVOR_FG,   new List<StoredVehicle>() },
            };

        private static readonly string FLOOR_GARAGE_THEMES_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_floor_themes.json");

        private static readonly Vehicle[] _floorGarageHandles = new Vehicle[FLOOR_GARAGE_SLOT_COUNT];
        private static bool _isPlayerInFloorGarage;
        private static int _floorGarageExitCooldownFrames;
        private static Blip _floorGarageEntranceBlip;
        private static Blip _floorGaragePedBlip;
        private static bool _floorGarageInitialized;

        // ------------------------------------------------------------------ //
        //  Floor Garage Public API                                                  //
        // ------------------------------------------------------------------ //

        internal static bool IsPlayerInFloorGarage => _isPlayerInFloorGarage;
        internal static int CurrentFloor => _currentFloor;

        /// <summary>Debug: force the floor garage state (used by InteriorScout).</summary>
        internal static void DebugSetInFloorGarage(bool value) => _isPlayerInFloorGarage = value;

        /// <summary>Get the theme choice for a specific floor and category.</summary>
        internal static int GetFloorThemeChoice(int floor, int category)
        {
            string key = FloorGarageCharacterKey();
            if (!_floorThemes.TryGetValue(key, out var themes)) return floor;
            if (floor < 0 || floor >= 3 || category < 0 || category >= CUSTOM_CATEGORY_COUNT) return 0;
            return themes[floor][category];
        }

        /// <summary>Set the theme choice for a specific floor and category. Applies live if in garage.</summary>
        internal static void SetFloorThemeChoice(int floor, int category, int option)
        {
            if (floor < 0 || floor >= 3) return;
            if (category < 0 || category >= CUSTOM_CATEGORY_COUNT) return;
            if (option < 0 || option >= CUSTOM_OPTION_COUNT) return;

            string key = FloorGarageCharacterKey();
            if (!_floorThemes.TryGetValue(key, out var themes))
            {
                themes = DefaultThemes();
                _floorThemes[key] = themes;
            }

            int oldOption = themes[floor][category];
            if (oldOption == option) return;

            themes[floor][category] = option;

            // If the player is currently viewing this floor, swap the entity sets live
            if (_isPlayerInFloorGarage && floor == _currentFloor)
            {
                int interior = Function.Call<int>(
                    Hash.GET_INTERIOR_AT_COORDS, -1505.782f, -3012.587f, -80.0f);
                if (interior != 0)
                {
                    // Deactivate the old entity set for this category
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior,
                        CUSTOM_ENTITY_SETS[category][oldOption]);
                    // Activate the new one
                    Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior,
                        CUSTOM_ENTITY_SETS[category][option]);
                    Function.Call(Hash.REFRESH_INTERIOR, interior);
                }
            }

            FloorGarageThemesSave();
            Log($"SetFloorThemeChoice: floor={floor} cat={CUSTOM_CATEGORY_NAMES[category]} option={option}");
        }

        internal static void InitializeFloorGarage()
        {
            if (_floorGarageInitialized) return;

            try
            {
                FloorGarageLoad();
                FloorGarageThemesLoad();
                int total = 0;
                foreach (var list in _floorGarageStored.Values)
                    total += list.Count;
                Log($"Floor Garage: loaded {total} stored vehicles");

                _floorGarageEntranceBlip = World.CreateBlip(FLOOR_GARAGE_ENTRANCE_POS);
                _floorGarageEntranceBlip.Sprite = BlipSprite.Garage;
                _floorGarageEntranceBlip.Color = CharacterBlipColor();
                _floorGarageEntranceBlip.Name = "ALLIN1 Floor Garage (Oversized)";
                _floorGarageEntranceBlip.IsShortRange = true;

                _floorGaragePedBlip = World.CreateBlip(FLOOR_GARAGE_PED_EXIT_DEST);
                _floorGaragePedBlip.Sprite = BlipSprite.Garage;
                _floorGaragePedBlip.Color = CharacterBlipColor();
                _floorGaragePedBlip.Name = "ALLIN1 Floor Garage (Pedestrian)";
                _floorGaragePedBlip.IsShortRange = true;

                Log("Floor Garage initialized (3-floor oversized vehicle storage)");
            }
            catch (Exception ex)
            {
                LogException("InitializeFloorGarage", ex);
            }

            _floorGarageInitialized = true;
        }

        internal static int GetFloorGarageUsedSlots()
        {
            string key = FloorGarageCharacterKey();
            if (_floorGarageStored.TryGetValue(key, out var list))
                return list.Count;
            return 0;
        }

        internal static int GetFloorGarageCapacity() => FLOOR_GARAGE_SLOT_COUNT;

        internal static List<StoredVehicle> GetFloorGarageStoredVehicles()
        {
            string key = FloorGarageCharacterKey();
            if (_floorGarageStored.TryGetValue(key, out var list))
                return list;
            return new List<StoredVehicle>();
        }

        internal static bool DeliverToFloorGarage(string model, int color1, int color2)
        {
            string key = FloorGarageCharacterKey();
            if (!_floorGarageStored.TryGetValue(key, out var list))
                return false;

            if (list.Count >= FLOOR_GARAGE_SLOT_COUNT)
            {
                Log($"DeliverToFloorGarage: full ({list.Count}/{FLOOR_GARAGE_SLOT_COUNT})");
                return false;
            }

            int slotIndex = FindEmptyFloorGarageSlot(list);
            if (slotIndex < 0)
            {
                Log($"DeliverToFloorGarage: no empty slot");
                return false;
            }

            var stored = new StoredVehicle
            {
                Model = model,
                Slot = slotIndex,
                Color1 = color1,
                Color2 = color2,
            };
            list.Add(stored);

            // Only spawn the vehicle live if the player is in the garage
            // AND the vehicle's slot is on the currently displayed floor
            if (_isPlayerInFloorGarage)
            {
                int slotFloor = slotIndex / FLOOR_GARAGE_SLOTS_PER_FLOOR;
                if (slotFloor == _currentFloor)
                {
                    try
                    {
                        int physicalIndex = slotIndex % FLOOR_GARAGE_SLOTS_PER_FLOOR;
                        ParkingSlot slot = _floorGaragePhysicalSlots[physicalIndex];
                        Vehicle veh = VehicleHelper.CreateVehicle(
                            model, slot.Position, slot.Heading, color1, color2);
                        if (veh != null)
                        {
                            veh.IsPersistent = true;
                            veh.IsEngineRunning = false;
                            float deltaZ = VehicleList.GetSpawnDeltaZ(model);
                            Function.Call(Hash.SET_ENTITY_COORDS, veh,
                                slot.Position.X, slot.Position.Y, slot.Position.Z + deltaZ,
                                false, false, false, true);
                            Function.Call(Hash.SET_ENTITY_HEADING, veh, slot.Heading);
                            veh.IsPositionFrozen = true;
                            _floorGarageHandles[slotIndex] = veh;
                        }
                    }
                    catch (Exception ex)
                    {
                        LogException("DeliverToFloorGarage.Spawn", ex);
                    }
                }
            }

            Log($"DeliverToFloorGarage: {model} -> slot {slotIndex}");
            FloorGarageSave();
            return true;
        }

        internal static void RemoveFloorGarageVehicle(int listIndex)
        {
            string key = FloorGarageCharacterKey();
            if (!_floorGarageStored.TryGetValue(key, out var list))
                return;
            if (listIndex < 0 || listIndex >= list.Count)
                return;

            StoredVehicle sv = list[listIndex];
            int slotIndex = sv.Slot;

            if (slotIndex >= 0 && slotIndex < FLOOR_GARAGE_SLOT_COUNT)
            {
                Vehicle veh = _floorGarageHandles[slotIndex];
                if (veh != null && veh.Exists())
                {
                    veh.IsPersistent = true;
                    veh.Delete();
                }
                _floorGarageHandles[slotIndex] = null;
            }

            list.RemoveAt(listIndex);
            FloorGarageSave();
            Log($"RemoveFloorGarageVehicle: {sv.Model} from slot {slotIndex}");
        }

        internal static void DetailFloorGarageVehicles()
        {
            int cleaned = 0;
            for (int i = 0; i < FLOOR_GARAGE_SLOT_COUNT; i++)
            {
                Vehicle veh = _floorGarageHandles[i];
                if (veh == null || !veh.Exists()) continue;
                veh.DirtLevel = 0f;
                Function.Call(Hash.SET_VEHICLE_FIXED, veh);
                cleaned++;
            }
            Log($"DetailFloorGarageVehicles: cleaned {cleaned} vehicles");
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage Tick                                                        //
        // ------------------------------------------------------------------ //

        internal static void OnFloorGarageTick()
        {
            if (!_floorGarageInitialized) return;

            if (_floorGarageExitCooldownFrames > 0)
            {
                _floorGarageExitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;

            // Don't show floor garage markers while in garage (and vice versa)
            if (_isPlayerInGarage) return;

            BlipColor charColor = CharacterBlipColor();
            if (_floorGarageEntranceBlip != null && _floorGarageEntranceBlip.Exists())
                _floorGarageEntranceBlip.Color = charColor;
            if (_floorGaragePedBlip != null && _floorGaragePedBlip.Exists())
                _floorGaragePedBlip.Color = charColor;

            if (!_isPlayerInFloorGarage)
            {
                bool inVehicle = player.IsInVehicle();

                if (inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        FLOOR_GARAGE_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(3f, 3f, 1.5f),
                        System.Drawing.Color.FromArgb(128, 200, 100, 0));

                    float dist = player.Position.DistanceTo(FLOOR_GARAGE_ENTRANCE_POS);
                    if (dist < ENTER_RADIUS + 1f)
                    {
                        GTA.UI.Screen.ShowHelpTextThisFrame(
                            "Press ~INPUT_CONTEXT~ to enter the floor garage.");
                        if (Game.IsControlJustPressed(GTA.Control.Context))
                            EnterFloorGarage();
                    }
                }

                if (!inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        FLOOR_GARAGE_PED_EXIT_DEST - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(2f, 2f, 1.2f),
                        System.Drawing.Color.FromArgb(128, 200, 100, 0));

                    float dist = player.Position.DistanceTo(FLOOR_GARAGE_PED_EXIT_DEST);
                    if (dist < ENTER_RADIUS)
                    {
                        GTA.UI.Screen.ShowHelpTextThisFrame(
                            "Press ~INPUT_CONTEXT~ to enter the floor garage.");
                        if (Game.IsControlJustPressed(GTA.Control.Context))
                            EnterFloorGarage();
                    }
                }
            }
            else
            {
                bool inVehicle = player.IsInVehicle();
                EnforceFloorGarageVehicleState(player);

                // Floor indicator (always show)
                GTA.UI.Screen.ShowSubtitle(
                    $"~b~Floor {_currentFloor + 1}/3", 1);

                if (inVehicle)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to leave the floor garage with your vehicle.");
                    if (Game.IsControlJustPressed(GTA.Control.Context))
                        LeaveFloorGarage();
                }

                if (!inVehicle)
                {
                    if (_elevatorMenuActive)
                    {
                        // Draw elevator menu
                        DrawElevatorMenu();

                        if (Game.IsControlJustPressed(GTA.Control.FrontendUp))
                            _elevatorMenuSelection = (_elevatorMenuSelection + 3) % 4; // wrap up
                        else if (Game.IsControlJustPressed(GTA.Control.FrontendDown))
                            _elevatorMenuSelection = (_elevatorMenuSelection + 1) % 4; // wrap down
                        else if (Game.IsControlJustPressed(GTA.Control.FrontendAccept)
                              || Game.IsControlJustPressed(GTA.Control.Context))
                        {
                            _elevatorMenuActive = false;
                            if (_elevatorMenuSelection == 3) // Exit
                                LeaveFloorGarage();
                            else
                                SwitchFloorGarageFloor(_elevatorMenuSelection);
                        }
                        else if (Game.IsControlJustPressed(GTA.Control.FrontendCancel))
                        {
                            _elevatorMenuActive = false;
                        }
                    }
                    else
                    {
                        // Draw elevator 1 marker
                        var markerColor = CharacterMarkerColor();
                        World.DrawMarker(
                            GTA.MarkerType.VerticalCylinder,
                            FLOOR_GARAGE_ELEVATOR_1 - new Vector3(0f, 0f, 1f),
                            Vector3.Zero, Vector3.Zero,
                            new Vector3(1.5f, 1.5f, 1.2f),
                            markerColor);

                        float dist1 = player.Position.DistanceTo(FLOOR_GARAGE_ELEVATOR_1);
                        if (dist1 < ELEVATOR_INTERACT_RADIUS)
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to use the elevator.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                            {
                                _elevatorMenuActive = true;
                                _elevatorMenuSelection = _currentFloor;
                            }
                        }

                        // Draw elevator 2 marker (if set)
                        if (FLOOR_GARAGE_ELEVATOR_2.X != 0f)
                        {
                            World.DrawMarker(
                                GTA.MarkerType.VerticalCylinder,
                                FLOOR_GARAGE_ELEVATOR_2 - new Vector3(0f, 0f, 1f),
                                Vector3.Zero, Vector3.Zero,
                                new Vector3(1.5f, 1.5f, 1.2f),
                                markerColor);

                            float dist2 = player.Position.DistanceTo(FLOOR_GARAGE_ELEVATOR_2);
                            if (dist2 < ELEVATOR_INTERACT_RADIUS)
                            {
                                GTA.UI.Screen.ShowHelpTextThisFrame(
                                    "Press ~INPUT_CONTEXT~ to use the elevator.");
                                if (Game.IsControlJustPressed(GTA.Control.Context))
                                {
                                    _elevatorMenuActive = true;
                                    _elevatorMenuSelection = _currentFloor;
                                }
                            }
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage Elevator Menu                                         //
        // ------------------------------------------------------------------ //

        private static readonly string[] _elevatorLabels =
            { "Floor 1", "Floor 2", "Floor 3", "Exit Garage" };

        /// <summary>
        /// Draws a simple centered elevator menu on screen with 4 options.
        /// The currently selected option is highlighted.
        /// </summary>
        private static void DrawElevatorMenu()
        {
            const float menuW = 0.16f;
            const float rowH = 0.035f;
            const float titleH = 0.04f;
            const float pad = 0.005f;
            const float menuX = 0.5f; // centered
            float totalH = titleH + rowH * 4 + pad * 2;
            float menuTop = 0.5f - totalH / 2f;

            // Background
            GbayRenderer.DrawRect(menuX, 0.5f, menuW, totalH,
                System.Drawing.Color.FromArgb(220, 15, 15, 15));

            // Title
            GbayRenderer.DrawText("ELEVATOR", menuX, menuTop + pad,
                0.38f, System.Drawing.Color.FromArgb(255, 100, 180, 255),
                font: 0, centered: true, shadow: true);

            // Options
            for (int i = 0; i < 4; i++)
            {
                float rowY = menuTop + titleH + rowH * i;
                float rowCY = rowY + rowH / 2f;

                bool selected = (i == _elevatorMenuSelection);
                bool isCurrent = (i < 3 && i == _currentFloor);

                if (selected)
                {
                    GbayRenderer.DrawRect(menuX, rowCY, menuW - 0.006f, rowH - 0.003f,
                        System.Drawing.Color.FromArgb(200, 60, 130, 220));
                }

                string label = _elevatorLabels[i];
                if (isCurrent)
                    label += "  (current)";

                var textColor = selected
                    ? System.Drawing.Color.White
                    : (isCurrent
                        ? System.Drawing.Color.FromArgb(255, 130, 190, 255)
                        : System.Drawing.Color.FromArgb(255, 200, 200, 200));

                GbayRenderer.DrawText(label, menuX, rowY + 0.006f,
                    0.33f, textColor, font: 0, centered: true, shadow: true);
            }

            // Hint at bottom
            GbayRenderer.DrawText("Up/Down to select  Enter to confirm  Esc to close",
                menuX, menuTop + totalH + 0.005f,
                0.22f, System.Drawing.Color.FromArgb(180, 160, 160, 160),
                font: 0, centered: true);
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage Enter / Leave                                               //
        // ------------------------------------------------------------------ //

        private static void EnterFloorGarage()
        {
            Ped player = Game.Player.Character;

            // Drive-in: store the vehicle
            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
                    if (IsPersonalVehicle(rideIn))
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~You cannot bring your personal vehicle into the floor garage.", 3000);
                        return;
                    }

                    int modelHash = rideIn.Model.Hash;
                    string modelName;
                    if (_hashToSpawnName != null && _hashToSpawnName.TryGetValue(modelHash, out string spawnName))
                        modelName = spawnName;
                    else
                    {
                        modelName = Function.Call<string>(
                            Hash.GET_DISPLAY_NAME_FROM_VEHICLE_MODEL, (uint)modelHash);
                        if (!string.IsNullOrEmpty(modelName))
                            modelName = modelName.ToLowerInvariant();
                        else
                            modelName = modelHash.ToString();
                    }

                    string hKey = FloorGarageCharacterKey();
                    if (!_floorGarageStored.TryGetValue(hKey, out var storedList))
                    {
                        storedList = new List<StoredVehicle>();
                        _floorGarageStored[hKey] = storedList;
                    }

                    if (storedList.Count >= FLOOR_GARAGE_SLOT_COUNT)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~Floor Garage full.~w~ ({storedList.Count}/{FLOOR_GARAGE_SLOT_COUNT} slots used)", 3000);
                        return;
                    }

                    int slotIndex = FindEmptyFloorGarageSlot(storedList);
                    if (slotIndex < 0)
                    {
                        GTA.UI.Screen.ShowSubtitle("~r~Floor Garage full. No empty slots.", 3000);
                        return;
                    }

                    StoredVehicle sv = CaptureVehicleState(rideIn, modelName, slotIndex);
                    storedList.Add(sv);
                    FloorGarageSave();

                    string displayName = VehicleList.DisplayNames.ContainsKey(modelName)
                        ? VehicleList.DisplayNames[modelName] : modelName;
                    int floor = slotIndex / FLOOR_GARAGE_SLOTS_PER_FLOOR + 1;
                    int spotOnFloor = slotIndex % FLOOR_GARAGE_SLOTS_PER_FLOOR + 1;
                    GTA.UI.Screen.ShowSubtitle(
                        $"~g~{displayName}~w~ stored in floor garage. (Floor {floor}, Spot {spotOnFloor})", 3000);
                    Log($"EnterFloorGarage: stored drive-in vehicle {modelName} -> slot {slotIndex} (floor {floor})");

                    rideIn.IsPersistent = true;
                    rideIn.Delete();
                }
            }

            // Load the nightclub garage IPL
            LoadFloorGarageInterior();

            // Clear existing handles
            for (int i = 0; i < FLOOR_GARAGE_SLOT_COUNT; i++)
            {
                if (_floorGarageHandles[i] != null && _floorGarageHandles[i].Exists())
                    _floorGarageHandles[i].Delete();
                _floorGarageHandles[i] = null;
            }

            // Fade to black before teleporting
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            while (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                Script.Wait(0);

            // Freeze and teleport player
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                FLOOR_GARAGE_INTERIOR_PED.X, FLOOR_GARAGE_INTERIOR_PED.Y, FLOOR_GARAGE_INTERIOR_PED.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player, FLOOR_GARAGE_INTERIOR_PED_HEADING);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, true);

            _isPlayerInFloorGarage = true;
            _currentFloor = 0; // Always start on floor 1

            // Spawn vehicles for the current floor only
            SpawnFloorGarageVehicles();

            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            player.IsPositionFrozen = false;

            // Fade back in
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);

            Log($"EnterFloorGarage: character={FloorGarageCharacterKey()}, floor=1");
        }

        private static void LeaveFloorGarage()
        {
            FloorGarageUpdateStoredFromLive();

            Ped player = Game.Player.Character;
            Vehicle playerVehicle = null;
            int playerSlotIndex = -1;

            if (player.IsInVehicle())
            {
                Vehicle current = player.CurrentVehicle;
                if (current != null && current.Exists())
                {
                    for (int i = 0; i < FLOOR_GARAGE_SLOT_COUNT; i++)
                    {
                        if (_floorGarageHandles[i] != null && _floorGarageHandles[i] == current)
                        {
                            playerVehicle = current;
                            playerSlotIndex = i;
                            _floorGarageHandles[i] = null;
                            break;
                        }
                    }
                }
            }

            for (int i = 0; i < FLOOR_GARAGE_SLOT_COUNT; i++)
            {
                Vehicle veh = _floorGarageHandles[i];
                if (veh != null && veh.Exists())
                {
                    veh.IsPersistent = true;
                    veh.Delete();
                }
                _floorGarageHandles[i] = null;
            }

            // Fade to black before teleporting outside
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            while (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                Script.Wait(0);

            if (playerVehicle != null)
            {
                string hKey = FloorGarageCharacterKey();
                if (_floorGarageStored.TryGetValue(hKey, out var hList))
                {
                    for (int i = hList.Count - 1; i >= 0; i--)
                    {
                        if (hList[i].Slot == playerSlotIndex)
                        {
                            Log($"LeaveFloorGarage: removing {hList[i].Model} from slot {playerSlotIndex} (driven out)");
                            hList.RemoveAt(i);
                            break;
                        }
                    }
                }

                playerVehicle.IsPositionFrozen = false;
                playerVehicle.IsPersistent = true;
                Function.Call(Hash.SET_ENTITY_COORDS, playerVehicle,
                    FLOOR_GARAGE_ENTRANCE_POS.X, FLOOR_GARAGE_ENTRANCE_POS.Y, FLOOR_GARAGE_ENTRANCE_POS.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, playerVehicle, 270f);
                playerVehicle.IsEngineRunning = true;
                Function.Call(Hash.SET_VEHICLE_ON_GROUND_PROPERLY, playerVehicle);

                FloorGarageSave();
                Log("LeaveFloorGarage: drove out in vehicle");
            }
            else
            {
                Vector3 dest = FLOOR_GARAGE_PED_EXIT_DEST;
                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    dest.X, dest.Y, dest.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player, FLOOR_GARAGE_PED_EXIT_DEST_HEADING);
                player.IsPositionFrozen = false;

                FloorGarageSave();
                Log("LeaveFloorGarage: returned on foot");
            }

            _isPlayerInFloorGarage = false;
            _floorGarageExitCooldownFrames = 60;

            // Fade back in
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage Helpers                                                     //
        // ------------------------------------------------------------------ //

        private static string FloorGarageCharacterKey()
        {
            PedHash ch = GbayShop.GetCurrentCharacter();
            if (ch == PedHash.Franklin) return KEY_FRANKLIN_FG;
            if (ch == PedHash.Trevor) return KEY_TREVOR_FG;
            return KEY_MICHAEL_FG;
        }

        private static int FindEmptyFloorGarageSlot(List<StoredVehicle> list)
        {
            var occupied = new HashSet<int>();
            foreach (var sv in list)
                occupied.Add(sv.Slot);
            for (int i = 0; i < FLOOR_GARAGE_SLOT_COUNT; i++)
                if (!occupied.Contains(i)) return i;
            return -1;
        }

        private static void EnforceFloorGarageVehicleState(Ped player)
        {
            // Only enforce vehicles on the current floor
            int startSlot = _currentFloor * FLOOR_GARAGE_SLOTS_PER_FLOOR;
            int endSlot = startSlot + FLOOR_GARAGE_SLOTS_PER_FLOOR;
            for (int i = startSlot; i < endSlot; i++)
            {
                Vehicle veh = _floorGarageHandles[i];
                if (veh == null || !veh.Exists()) continue;
                veh.IsPositionFrozen = true;
                veh.IsEngineRunning = false;
            }
        }

        /// <summary>
        /// Activate entity sets for the given floor and refresh the interior.
        /// Uses customized theme choices instead of hardcoded sets.
        /// </summary>
        private static void ApplyFloorEntitySets(int interior, int floor)
        {
            string[] sets = GetFloorEntitySets(floor);
            foreach (string set in sets)
                Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, set);
            Function.Call(Hash.REFRESH_INTERIOR, interior);
        }

        /// <summary>
        /// Load the nightclub garage IPL and configure interior entity sets.
        /// </summary>
        private static void LoadFloorGarageInterior()
        {
            // Load MP DLC maps — required for Online interiors in SP
            // Native: _LOAD_MP_DLC_MAPS (0x0888C3502DBBEEF5)
            Function.Call((Hash)0x0888C3502DBBEEF5, 1);
            Script.Wait(500);

            // Remove then re-request all IPLs (pattern from Enable All Interiors mod)
            foreach (string ipl in FLOOR_GARAGE_IPLS)
                Function.Call(Hash.REMOVE_IPL, ipl);
            foreach (string ipl in FLOOR_GARAGE_IPLS)
                Function.Call(Hash.REQUEST_IPL, ipl);

            // Wait for IPLs to load
            Script.Wait(1000);

            // Get the garage interior ID (Int02_ba at garage coords, NOT main nightclub)
            int interior = Function.Call<int>(
                Hash.GET_INTERIOR_AT_COORDS, -1505.782f, -3012.587f, -80.0f);

            if (interior != 0)
            {
                // Disable blockers so the full garage space is accessible
                Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_garage_blocker");
                Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_storage_blocker");
                Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_FanBlocker01");

                // Enable security upgrade (adds more light)
                Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_sec_upgrade_grg");

                // Activate current floor's entity set theme
                ApplyFloorEntitySets(interior, _currentFloor);

                Log($"LoadFloorGarageInterior: interior={interior}, IPL loaded, entity sets configured");
            }
            else
            {
                Log("LoadFloorGarageInterior: WARNING — could not get interior ID");
            }
        }

        /// <summary>
        /// Spawn vehicles for the current virtual floor only.
        /// Despawns any previously spawned vehicles first.
        /// </summary>
        private static void SpawnFloorGarageVehicles()
        {
            // Despawn all existing floor garage vehicle handles
            for (int i = 0; i < FLOOR_GARAGE_SLOT_COUNT; i++)
            {
                if (_floorGarageHandles[i] != null && _floorGarageHandles[i].Exists())
                    _floorGarageHandles[i].Delete();
                _floorGarageHandles[i] = null;
            }

            string key = FloorGarageCharacterKey();
            if (!_floorGarageStored.TryGetValue(key, out var list))
                return;

            int startSlot = _currentFloor * FLOOR_GARAGE_SLOTS_PER_FLOOR;
            int endSlot = startSlot + FLOOR_GARAGE_SLOTS_PER_FLOOR;

            // Collect models for this floor
            var modelsToLoad = new List<Model>();
            foreach (var sv in list)
            {
                if (sv.Slot < startSlot || sv.Slot >= endSlot) continue;
                var m = new Model(sv.Model);
                m.Request();
                modelsToLoad.Add(m);
            }

            // Wait for models to load
            DateTime deadline = DateTime.UtcNow.AddMilliseconds(10000);
            bool allLoaded = false;
            while (!allLoaded && DateTime.UtcNow < deadline)
            {
                allLoaded = true;
                foreach (var m in modelsToLoad)
                    if (!m.IsLoaded) { allLoaded = false; break; }
                if (!allLoaded) Script.Wait(0);
            }

            // Spawn vehicles at their physical positions
            foreach (var sv in list)
            {
                if (sv.Slot < startSlot || sv.Slot >= endSlot) continue;
                int physicalIndex = sv.Slot % FLOOR_GARAGE_SLOTS_PER_FLOOR;
                ParkingSlot slot = _floorGaragePhysicalSlots[physicalIndex];

                try
                {
                    var model = new Model(sv.Model);
                    Vehicle veh = World.CreateVehicle(model, slot.Position, slot.Heading);
                    model.MarkAsNoLongerNeeded();

                    if (veh != null)
                    {
                        ApplyVehicleState(veh, sv);
                        veh.IsPersistent = true;
                        veh.IsEngineRunning = false;
                        float deltaZ = VehicleList.GetSpawnDeltaZ(sv.Model);
                        Function.Call(Hash.SET_ENTITY_COORDS, veh,
                            slot.Position.X, slot.Position.Y, slot.Position.Z + deltaZ,
                            false, false, false, true);
                        Function.Call(Hash.SET_ENTITY_HEADING, veh, slot.Heading);
                        veh.IsPositionFrozen = true;
                        _floorGarageHandles[sv.Slot] = veh;
                        Log($"SpawnFloorGarageVehicles: spawned {sv.Model} at slot {sv.Slot} (physical {physicalIndex})");
                    }
                }
                catch (Exception ex)
                {
                    LogException($"SpawnFloorGarageVehicles({sv.Model})", ex);
                }
            }

            foreach (var m in modelsToLoad)
                m.MarkAsNoLongerNeeded();

            Log($"SpawnFloorGarageVehicles: floor {_currentFloor + 1}, spawned vehicles");
        }

        /// <summary>
        /// Switch to a different virtual floor. Saves current vehicle state,
        /// despawns all, then spawns the target floor's vehicles.
        /// </summary>
        private static void SwitchFloorGarageFloor(int newFloor)
        {
            if (newFloor < 0 || newFloor >= 3) return;
            if (newFloor == _currentFloor) return;

            Ped player = Game.Player.Character;
            if (player.IsInVehicle())
            {
                GTA.UI.Screen.ShowSubtitle("~r~Exit your vehicle before switching floors.", 2000);
                return;
            }

            // Save state of vehicles on the current floor
            FloorGarageUpdateStoredFromLive();

            int oldFloor = _currentFloor;
            _currentFloor = newFloor;

            // Freeze player while switching
            player.IsPositionFrozen = true;

            // Switch entity sets — different theme per floor
            int interior = Function.Call<int>(
                Hash.GET_INTERIOR_AT_COORDS, -1505.782f, -3012.587f, -80.0f);
            if (interior != 0)
            {
                // Deactivate old floor's sets
                foreach (string set in GetFloorEntitySets(oldFloor))
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, set);
                // Activate new floor's sets
                ApplyFloorEntitySets(interior, _currentFloor);
            }

            SpawnFloorGarageVehicles();

            player.IsPositionFrozen = false;
            GTA.UI.Screen.ShowSubtitle($"~b~Floor {_currentFloor + 1} of 3", 2000);
            Log($"SwitchFloorGarageFloor: switched to floor {_currentFloor + 1}");
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage JSON Persistence                                            //
        // ------------------------------------------------------------------ //

        private static void FloorGarageLoad()
        {
            if (!File.Exists(FLOOR_GARAGE_SAVE_PATH))
                return;
            try
            {
                string json = File.ReadAllText(FLOOR_GARAGE_SAVE_PATH);
                FloorGarageParseJson(json);
            }
            catch (Exception ex)
            {
                LogException("FloorGarageLoad", ex);
            }
        }

        private static void FloorGarageSave()
        {
            try
            {
                string json = FloorGarageBuildJson();
                string tmp = FLOOR_GARAGE_SAVE_PATH + ".tmp";
                File.WriteAllText(tmp, json);
                if (File.Exists(FLOOR_GARAGE_SAVE_PATH))
                    File.Delete(FLOOR_GARAGE_SAVE_PATH);
                File.Move(tmp, FLOOR_GARAGE_SAVE_PATH);
            }
            catch (Exception ex)
            {
                LogException("FloorGarageSave", ex);
            }
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage Theme Persistence                                     //
        // ------------------------------------------------------------------ //

        private static void FloorGarageThemesLoad()
        {
            if (!File.Exists(FLOOR_GARAGE_THEMES_PATH))
                return;
            try
            {
                string json = File.ReadAllText(FLOOR_GARAGE_THEMES_PATH);
                // Simple JSON: { "key": [[0,1,2,0,1],[...],[...]], ... }
                string[] keys = { KEY_MICHAEL_FG, KEY_FRANKLIN_FG, KEY_TREVOR_FG };
                foreach (string key in keys)
                {
                    int keyIdx = json.IndexOf($"\"{key}\"");
                    if (keyIdx < 0) continue;
                    int arrStart = json.IndexOf('[', keyIdx);
                    if (arrStart < 0) continue;

                    // Parse 3 inner arrays of 5 ints each: [[a,b,c,d,e],[...],[...]]
                    int[][] themes = new int[3][];
                    int pos = arrStart + 1; // skip outer [
                    for (int f = 0; f < 3; f++)
                    {
                        int innerStart = json.IndexOf('[', pos);
                        int innerEnd = json.IndexOf(']', innerStart);
                        if (innerStart < 0 || innerEnd < 0) break;
                        string inner = json.Substring(innerStart + 1, innerEnd - innerStart - 1);
                        string[] parts = inner.Split(',');
                        themes[f] = new int[CUSTOM_CATEGORY_COUNT];
                        for (int c = 0; c < Math.Min(parts.Length, CUSTOM_CATEGORY_COUNT); c++)
                        {
                            if (int.TryParse(parts[c].Trim(), out int val) && val >= 0 && val < CUSTOM_OPTION_COUNT)
                                themes[f][c] = val;
                        }
                        pos = innerEnd + 1;
                    }
                    if (themes[0] != null && themes[1] != null && themes[2] != null)
                        _floorThemes[key] = themes;
                }
                Log("FloorGarageThemesLoad: loaded custom themes");
            }
            catch (Exception ex)
            {
                LogException("FloorGarageThemesLoad", ex);
            }
        }

        private static void FloorGarageThemesSave()
        {
            try
            {
                var sb = new StringBuilder();
                sb.AppendLine("{");
                string[] keys = { KEY_MICHAEL_FG, KEY_FRANKLIN_FG, KEY_TREVOR_FG };
                for (int k = 0; k < keys.Length; k++)
                {
                    string key = keys[k];
                    int[][] themes = _floorThemes.ContainsKey(key) ? _floorThemes[key] : DefaultThemes();
                    sb.Append($"  \"{key}\": [");
                    for (int f = 0; f < 3; f++)
                    {
                        sb.Append($"[{string.Join(",", themes[f])}]");
                        if (f < 2) sb.Append(", ");
                    }
                    sb.Append("]");
                    if (k < keys.Length - 1) sb.AppendLine(",");
                    else sb.AppendLine();
                }
                sb.AppendLine("}");

                string tmp = FLOOR_GARAGE_THEMES_PATH + ".tmp";
                File.WriteAllText(tmp, sb.ToString());
                if (File.Exists(FLOOR_GARAGE_THEMES_PATH))
                    File.Delete(FLOOR_GARAGE_THEMES_PATH);
                File.Move(tmp, FLOOR_GARAGE_THEMES_PATH);
            }
            catch (Exception ex)
            {
                LogException("FloorGarageThemesSave", ex);
            }
        }

        private static string FloorGarageBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");

            string[] keys = { KEY_MICHAEL_FG, KEY_FRANKLIN_FG, KEY_TREVOR_FG };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");

                if (_floorGarageStored.TryGetValue(key, out var list) && list.Count > 0)
                {
                    sb.AppendLine();
                    for (int i = 0; i < list.Count; i++)
                    {
                        var sv = list[i];
                        sb.Append("    { ");
                        sb.Append($"\"model\": \"{sv.Model}\", ");
                        sb.Append($"\"slot\": {sv.Slot}, ");
                        sb.Append($"\"color1\": {sv.Color1}, ");
                        sb.Append($"\"color2\": {sv.Color2}");

                        if (sv.PlateText != null)
                            sb.Append($", \"plate\": \"{EscapeJson(sv.PlateText)}\"");
                        if (sv.PlateStyle != 0)
                            sb.Append($", \"plateStyle\": {sv.PlateStyle}");
                        if (sv.WheelType != 0)
                            sb.Append($", \"wheelType\": {sv.WheelType}");
                        if (sv.WindowTint != 0)
                            sb.Append($", \"windowTint\": {sv.WindowTint}");
                        if (sv.Livery > 0)
                            sb.Append($", \"livery\": {sv.Livery}");
                        if (sv.PearlescentColor != 0)
                            sb.Append($", \"pearlescent\": {sv.PearlescentColor}");
                        if (sv.RimColor != 0)
                            sb.Append($", \"rimColor\": {sv.RimColor}");
                        if (sv.Mods != null)
                            sb.Append($", \"mods\": [{string.Join(",", sv.Mods)}]");
                        if (sv.ModToggles != null)
                            sb.Append($", \"modToggles\": [{string.Join(",", BoolArrayToInts(sv.ModToggles))}]");
                        if (sv.NeonEnabled != null)
                            sb.Append($", \"neonEnabled\": [{string.Join(",", sv.NeonEnabled)}]");
                        if (sv.NeonColor != null)
                            sb.Append($", \"neonColor\": [{string.Join(",", sv.NeonColor)}]");
                        if (sv.TyreSmokeColor != null)
                            sb.Append($", \"tyreSmokeColor\": [{string.Join(",", sv.TyreSmokeColor)}]");
                        if (sv.Extras != null)
                            sb.Append($", \"extras\": [{string.Join(",", sv.Extras)}]");
                        if (sv.CustomPrimaryColor && sv.CustomPrimary != null)
                            sb.Append($", \"customPrimary\": [{string.Join(",", sv.CustomPrimary)}]");
                        if (sv.CustomSecondaryColor && sv.CustomSecondary != null)
                            sb.Append($", \"customSecondary\": [{string.Join(",", sv.CustomSecondary)}]");

                        sb.Append(" }");
                        if (i < list.Count - 1)
                            sb.AppendLine(",");
                        else
                            sb.AppendLine();
                    }
                    sb.Append("  ]");
                }
                else
                {
                    sb.Append("]");
                }

                if (k < keys.Length - 1)
                    sb.AppendLine(",");
                else
                    sb.AppendLine();
            }

            sb.AppendLine("}");
            return sb.ToString();
        }

        private static void FloorGarageParseJson(string json)
        {
            // Reuse the same JSON parsing approach as the garage
            string currentKey = null;
            int i = 0;
            while (i < json.Length)
            {
                char c = json[i];
                if (c == '"')
                {
                    int end = json.IndexOf('"', i + 1);
                    if (end < 0) break;
                    string str = json.Substring(i + 1, end - i - 1);
                    i = end + 1;

                    if (currentKey == null)
                    {
                        int peek = SkipWhitespace(json, i);
                        if (peek < json.Length && json[peek] == ':')
                        {
                            currentKey = str;
                            i = peek + 1;
                        }
                    }
                    continue;
                }

                if (c == '[' && currentKey != null)
                {
                    i++;
                    var vehicles = ParseVehicleArray(json, ref i);
                    if (_floorGarageStored.ContainsKey(currentKey))
                        _floorGarageStored[currentKey] = vehicles;
                    currentKey = null;
                    continue;
                }

                i++;
            }
        }

        private static void FloorGarageUpdateStoredFromLive()
        {
            if (!_isPlayerInFloorGarage) return;

            string key = FloorGarageCharacterKey();
            if (!_floorGarageStored.TryGetValue(key, out var list)) return;

            // Only update vehicles that are on the current floor (have live handles)
            int startSlot = _currentFloor * FLOOR_GARAGE_SLOTS_PER_FLOOR;
            int endSlot = startSlot + FLOOR_GARAGE_SLOTS_PER_FLOOR;

            foreach (var sv in list)
            {
                if (sv.Slot < startSlot || sv.Slot >= endSlot) continue;
                Vehicle veh = _floorGarageHandles[sv.Slot];
                if (veh == null || !veh.Exists()) continue;

                var updated = CaptureVehicleState(veh, sv.Model, sv.Slot);
                sv.Color1 = updated.Color1;
                sv.Color2 = updated.Color2;
                sv.Mods = updated.Mods;
                sv.ModToggles = updated.ModToggles;
                sv.WheelType = updated.WheelType;
                sv.WindowTint = updated.WindowTint;
                sv.Livery = updated.Livery;
                sv.PlateText = updated.PlateText;
                sv.PlateStyle = updated.PlateStyle;
                sv.PearlescentColor = updated.PearlescentColor;
                sv.RimColor = updated.RimColor;
                sv.NeonEnabled = updated.NeonEnabled;
                sv.NeonColor = updated.NeonColor;
                sv.TyreSmokeColor = updated.TyreSmokeColor;
                sv.Extras = updated.Extras;
                sv.CustomPrimaryColor = updated.CustomPrimaryColor;
                sv.CustomPrimary = updated.CustomPrimary;
                sv.CustomSecondaryColor = updated.CustomSecondaryColor;
                sv.CustomSecondary = updated.CustomSecondary;
            }

            FloorGarageSave();
        }
    }
}
