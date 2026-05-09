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

        // Entrance marker on the street near Eclipse Towers
        private static readonly Vector3 ENTRANCE_POS =
            new Vector3(-796f, 303f, 85.2f);

        // Player spawn point inside the garage interior
        private static readonly Vector3 INTERIOR_SPAWN =
            new Vector3(240.65f, -1004.86f, -99.66f);
        private const float INTERIOR_SPAWN_HEADING = -165f;

        // Vehicle exit zone inside the garage
        private static readonly Vector3 VEHICLE_EXIT_INTERIOR =
            new Vector3(-227.9f, -1005.2f, -99f);
        private const float VEHICLE_EXIT_INTERIOR_HEADING = 357.4f;

        // Pedestrian-only exit inside the garage
        private static readonly Vector3 PED_EXIT =
            new Vector3(240.7f, -1004.8f, -99f);
        private const float PED_EXIT_HEADING = 82.8f;

        // Where the pedestrian exit teleports to on the main map
        private static readonly Vector3 PED_EXIT_DEST =
            new Vector3(-774f, 310.2f, 85.7f);
        private const float PED_EXIT_DEST_HEADING = 354.5f;

        // 10 vehicle parking positions (from SPGR data -- two rows of 5)
        internal static readonly ParkingSlot[] Slots =
        {
            // Left row (facing heading -105)
            new ParkingSlot(224.57f, -1002.75f, -99.0f, -105f),
            new ParkingSlot(224.36f, -998.87f,  -99.0f, -105f),
            new ParkingSlot(223.61f, -993.94f,  -99.0f, -105f),
            new ParkingSlot(223.65f, -989.04f,  -99.0f, -105f),
            new ParkingSlot(224.18f, -983.51f,  -99.0f, -105f),
            // Right row (facing heading 134)
            new ParkingSlot(234.44f, -1000.90f, -99.0f, 134f),
            new ParkingSlot(233.68f, -995.90f,  -99.0f, 134f),
            new ParkingSlot(233.00f, -991.15f,  -99.0f, 134f),
            new ParkingSlot(232.94f, -985.76f,  -99.0f, 134f),
            new ParkingSlot(232.39f, -981.39f,  -99.0f, 134f),
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
        private static Vector3 _returnPos;  // where to teleport back on exit
        private static float _returnHeading;
        private static Blip _entranceBlip;
        private static Blip _pedEntranceBlip;

        // Cooldown to avoid re-entering immediately after exiting
        private static int _exitCooldownFrames;

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
                Load();

                int total = 0;
                foreach (var list in _stored.Values)
                    total += list.Count;
                Log($"Loaded {total} stored vehicles from {SAVE_PATH}");

                // Create entrance blip
                _entranceBlip = World.CreateBlip(ENTRANCE_POS);
                _entranceBlip.Sprite = BlipSprite.Garage;
                _entranceBlip.Color = BlipColor.Green;
                _entranceBlip.Name = "ALLIN1 Garage (Vehicle)";
                _entranceBlip.IsShortRange = true;

                _pedEntranceBlip = World.CreateBlip(PED_EXIT_DEST);
                _pedEntranceBlip.Sprite = BlipSprite.Garage;
                _pedEntranceBlip.Color = BlipColor.Green;
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

            if (_exitCooldownFrames > 0)
            {
                _exitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead)
                return;

            if (!_isPlayerInGarage)
            {
                // Vehicle entrance marker (green)
                World.DrawMarker(
                    GTA.MarkerType.VerticalCylinder,
                    ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                    Vector3.Zero, Vector3.Zero,
                    new Vector3(2f, 2f, 1.5f),
                    System.Drawing.Color.FromArgb(128, 0, 200, 0));

                float vehDist = player.Position.DistanceTo(ENTRANCE_POS);
                if (vehDist < ENTER_RADIUS)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame("Press ~INPUT_CONTEXT~ to enter your garage.");

                    if (Game.IsControlJustPressed(GTA.Control.Context))
                    {
                        EnterGarage(pedEntrance: false);
                    }
                }

                // Pedestrian entrance marker (green)
                World.DrawMarker(
                    GTA.MarkerType.VerticalCylinder,
                    PED_EXIT_DEST - new Vector3(0f, 0f, 1f),
                    Vector3.Zero, Vector3.Zero,
                    new Vector3(1.5f, 1.5f, 1.2f),
                    System.Drawing.Color.FromArgb(128, 0, 200, 0));

                float pedDist = player.Position.DistanceTo(PED_EXIT_DEST);
                if (pedDist < ENTER_RADIUS)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame("Press ~INPUT_CONTEXT~ to enter your garage.");

                    if (Game.IsControlJustPressed(GTA.Control.Context))
                    {
                        EnterGarage(pedEntrance: true);
                    }
                }
            }
            else
            {
                bool inVehicle = player.IsInVehicle();

                // Vehicle exit marker (yellow) — only when in a vehicle
                if (inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        VEHICLE_EXIT_INTERIOR - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(2f, 2f, 1.5f),
                        System.Drawing.Color.FromArgb(128, 200, 200, 0));

                    float dist = player.Position.DistanceTo(VEHICLE_EXIT_INTERIOR);
                    if (dist < EXIT_RADIUS)
                    {
                        GTA.UI.Screen.ShowHelpTextThisFrame("Press ~INPUT_CONTEXT~ to drive out of the garage.");

                        if (Game.IsControlJustPressed(GTA.Control.Context))
                        {
                            LeaveGarage();
                        }
                    }
                }

                // Pedestrian exit marker (green) — only when on foot
                if (!inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        PED_EXIT - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(1.5f, 1.5f, 1.2f),
                        System.Drawing.Color.FromArgb(128, 0, 200, 0));

                    float pedDist = player.Position.DistanceTo(PED_EXIT);
                    if (pedDist < EXIT_RADIUS)
                    {
                        GTA.UI.Screen.ShowHelpTextThisFrame("Press ~INPUT_CONTEXT~ to leave the garage.");

                        if (Game.IsControlJustPressed(GTA.Control.Context))
                        {
                            LeaveGarage(usePedExit: true);
                        }
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

            int slotIndex = FindEmptySlot(list);
            if (slotIndex < 0)
            {
                Log($"DeliverVehicle: no empty slot");
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

        private static void EnterGarage(bool pedEntrance = false)
        {
            Ped player = Game.Player.Character;
            _returnPos = player.Position;
            _returnHeading = player.Heading;

            // Choose spawn point based on which entrance was used
            Vector3 spawnPos = pedEntrance ? PED_EXIT : INTERIOR_SPAWN;
            float spawnHeading = pedEntrance ? PED_EXIT_HEADING : INTERIOR_SPAWN_HEADING;

            // Freeze player, teleport into garage
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                spawnPos.X, spawnPos.Y, spawnPos.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player, spawnHeading);

            // Spawn the current character's vehicles
            string key = CharacterKey();
            if (_stored.TryGetValue(key, out var list))
            {
                foreach (var sv in list)
                {
                    if (sv.Slot < 0 || sv.Slot >= SLOT_COUNT)
                        continue;

                    ParkingSlot slot = Slots[sv.Slot];
                    try
                    {
                        Vehicle veh = VehicleHelper.CreateVehicle(
                            sv.Model, slot.Position, slot.Heading,
                            sv.Color1, sv.Color2);
                        if (veh != null)
                        {
                            ApplyVehicleState(veh, sv);
                            veh.IsPersistent = true;
                            veh.IsEngineRunning = false;
                            veh.IsPositionFrozen = true;
                            _handles[sv.Slot] = veh;
                        }
                        else
                        {
                            Log($"EnterGarage: failed to spawn {sv.Model} at slot {sv.Slot}");
                        }
                    }
                    catch (Exception ex)
                    {
                        LogException($"EnterGarage.Spawn({sv.Model})", ex);
                    }
                }
            }

            player.IsPositionFrozen = false;
            _isPlayerInGarage = true;

            Log($"EnterGarage: character={key}, vehicles spawned");
        }

        private static void LeaveGarage(bool usePedExit = false)
        {
            // Save all vehicle states before leaving
            UpdateStoredFromLive();

            Ped player = Game.Player.Character;
            Vehicle playerVehicle = null;

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

            if (playerVehicle != null)
            {
                // Teleport vehicle (with player inside) to entrance
                playerVehicle.IsPositionFrozen = false;
                playerVehicle.IsPersistent = true;
                Function.Call(Hash.SET_ENTITY_COORDS, playerVehicle,
                    ENTRANCE_POS.X, ENTRANCE_POS.Y, ENTRANCE_POS.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, playerVehicle, _returnHeading);
                playerVehicle.IsEngineRunning = true;

                Log("LeaveGarage: drove out in vehicle");
            }
            else
            {
                // Teleport player on foot
                Vector3 dest = usePedExit ? PED_EXIT_DEST : _returnPos;
                float heading = usePedExit ? PED_EXIT_DEST_HEADING : _returnHeading;

                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    dest.X, dest.Y, dest.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player, heading);
                player.IsPositionFrozen = false;

                Log($"LeaveGarage: returned on foot (pedExit={usePedExit})");
            }

            _isPlayerInGarage = false;
            _exitCooldownFrames = 60; // ~1 second cooldown
        }

        // ------------------------------------------------------------------ //
        //  Helpers                                                            //
        // ------------------------------------------------------------------ //

        private static string CharacterKey()
        {
            PedHash ch = GbayShop.GetCurrentCharacter();
            if (ch == PedHash.Franklin) return KEY_FRANKLIN;
            if (ch == PedHash.Trevor) return KEY_TREVOR;
            return KEY_MICHAEL;
        }

        private static int FindEmptySlot(List<StoredVehicle> list)
        {
            var occupied = new HashSet<int>();
            foreach (var sv in list)
                occupied.Add(sv.Slot);

            for (int i = 0; i < SLOT_COUNT; i++)
            {
                if (!occupied.Contains(i))
                    return i;
            }
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
            }
            catch (Exception ex)
            {
                LogException("Load", ex);
            }
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
    }
}
