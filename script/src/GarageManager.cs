// GarageManager.cs -- Safehouse garage storage and vehicle delivery.
//
// Simulates garages at player safehouses. GTA V has no native garage API,
// so we track stored vehicles in a JSON file and spawn them at fixed
// parking slots near each safehouse.

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

        internal class Safehouse
        {
            internal string Id;
            internal string Name;
            internal PedHash Character;
            internal ParkingSlot[] Slots;
        }

        internal class StoredVehicle
        {
            internal string Model;
            internal int Slot;
            internal int Color1;
            internal int Color2;
        }

        // ------------------------------------------------------------------ //
        //  Safehouse definitions                                              //
        // ------------------------------------------------------------------ //

        // Coordinates are approximate -- use garage_debug = true to tune.
        internal static readonly Safehouse[] Safehouses =
        {
            new Safehouse
            {
                Id = "michael_mansion",
                Name = "De Santa Mansion",
                Character = PedHash.Michael,
                Slots = new[]
                {
                    new ParkingSlot(-813.5f, 183.1f, 72.2f, 120f),
                    new ParkingSlot(-816.8f, 186.5f, 72.2f, 120f),
                    new ParkingSlot(-820.1f, 189.9f, 72.2f, 120f),
                    new ParkingSlot(-823.4f, 193.3f, 72.2f, 120f),
                },
            },
            new Safehouse
            {
                Id = "franklin_old",
                Name = "Forum Drive",
                Character = PedHash.Franklin,
                Slots = new[]
                {
                    new ParkingSlot(-14.5f, -1438.5f, 31.1f, 0f),
                    new ParkingSlot(-18.0f, -1438.5f, 31.1f, 0f),
                    new ParkingSlot(-14.5f, -1444.0f, 31.1f, 180f),
                    new ParkingSlot(-18.0f, -1444.0f, 31.1f, 180f),
                },
            },
            new Safehouse
            {
                Id = "franklin_new",
                Name = "Whispymound Drive",
                Character = PedHash.Franklin,
                Slots = new[]
                {
                    new ParkingSlot(7.8f, 543.8f, 176.0f, 250f),
                    new ParkingSlot(4.2f, 542.0f, 176.0f, 250f),
                    new ParkingSlot(0.6f, 540.2f, 176.0f, 250f),
                    new ParkingSlot(-3.0f, 538.4f, 176.0f, 250f),
                },
            },
            new Safehouse
            {
                Id = "trevor_trailer",
                Name = "Sandy Shores",
                Character = PedHash.Trevor,
                Slots = new[]
                {
                    new ParkingSlot(1972.0f, 3818.0f, 33.4f, 30f),
                    new ParkingSlot(1976.0f, 3818.0f, 33.4f, 30f),
                    new ParkingSlot(1972.0f, 3822.0f, 33.4f, 30f),
                    new ParkingSlot(1976.0f, 3822.0f, 33.4f, 30f),
                },
            },
        };

        // ------------------------------------------------------------------ //
        //  State                                                              //
        // ------------------------------------------------------------------ //

        private static readonly string SCRIPTS_DIR = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "scripts");
        private static readonly string SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_garages.json");
        private static readonly string LOG_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_gbay.log");

        // safehouse id -> list of stored vehicles
        private static readonly Dictionary<string, List<StoredVehicle>> _stored =
            new Dictionary<string, List<StoredVehicle>>();

        // safehouse id -> vehicle handles per slot (null = empty)
        private static readonly Dictionary<string, Vehicle[]> _handles =
            new Dictionary<string, Vehicle[]>();

        private static int _capacity = 4;
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

        internal static void Configure(int capacity, bool debug, bool enableLogging)
        {
            _capacity = Math.Max(1, Math.Min(capacity, Safehouses[0].Slots.Length));
            _debug = debug;
            _enableLogging = enableLogging;
        }

        internal static void Initialize()
        {
            if (_initialized)
                return;

            foreach (var sh in Safehouses)
            {
                if (!_stored.ContainsKey(sh.Id))
                    _stored[sh.Id] = new List<StoredVehicle>();
                if (!_handles.ContainsKey(sh.Id))
                    _handles[sh.Id] = new Vehicle[sh.Slots.Length];
            }

            try
            {
                Load();
                int totalStored = 0;
                foreach (var list in _stored.Values)
                    totalStored += list.Count;
                Log($"Loaded {totalStored} stored vehicles from {SAVE_PATH}");

                RespawnAll();
                Log("RespawnAll complete");
            }
            catch (Exception ex)
            {
                LogException("Initialize", ex);
            }

            _initialized = true;
        }

        internal static Safehouse[] GetSafehouses(PedHash character)
        {
            var result = new List<Safehouse>();
            foreach (var sh in Safehouses)
            {
                if (sh.Character == character)
                    result.Add(sh);
            }
            return result.ToArray();
        }

        internal static int GetUsedSlots(string safehouseId)
        {
            if (_stored.TryGetValue(safehouseId, out var list))
                return list.Count;
            return 0;
        }

        internal static int GetCapacity()
        {
            return _capacity;
        }

        internal static List<StoredVehicle> GetStoredVehicles(string safehouseId)
        {
            if (_stored.TryGetValue(safehouseId, out var list))
                return list;
            return new List<StoredVehicle>();
        }

        /// <summary>
        /// Deliver a vehicle to a safehouse. Returns true if successful,
        /// false if no room.
        /// </summary>
        internal static bool DeliverVehicle(string safehouseId, string model,
                                            int color1, int color2)
        {
            Safehouse sh = FindSafehouse(safehouseId);
            if (sh == null)
            {
                Log($"DeliverVehicle: unknown safehouse '{safehouseId}'");
                return false;
            }

            if (!_stored.TryGetValue(safehouseId, out var list))
                return false;

            if (list.Count >= _capacity)
            {
                Log($"DeliverVehicle: {safehouseId} full ({list.Count}/{_capacity})");
                return false;
            }

            // Find first empty slot
            int slotIndex = FindEmptySlot(safehouseId, sh);
            if (slotIndex < 0)
            {
                Log($"DeliverVehicle: no empty slot at {safehouseId}");
                return false;
            }

            // Spawn the vehicle
            ParkingSlot slot = sh.Slots[slotIndex];
            Vehicle veh = null;
            try
            {
                veh = VehicleHelper.CreateVehicle(
                    model, slot.Position, slot.Heading, color1, color2);
            }
            catch (Exception ex)
            {
                LogException("DeliverVehicle.CreateVehicle", ex);
                return false;
            }

            if (veh == null)
            {
                Log($"DeliverVehicle: CreateVehicle returned null for {model}");
                return false;
            }

            veh.IsPersistent = true;
            veh.IsEngineRunning = false;

            // Track it
            var stored = new StoredVehicle
            {
                Model = model,
                Slot = slotIndex,
                Color1 = color1,
                Color2 = color2,
            };
            list.Add(stored);
            _handles[safehouseId][slotIndex] = veh;

            Log($"DeliverVehicle: {model} -> {safehouseId} slot {slotIndex}");
            Save();
            return true;
        }

        /// <summary>
        /// Remove a stored vehicle by its index in the stored list.
        /// Deletes the entity and frees the slot.
        /// </summary>
        internal static void RemoveVehicle(string safehouseId, int listIndex)
        {
            if (!_stored.TryGetValue(safehouseId, out var list))
                return;
            if (listIndex < 0 || listIndex >= list.Count)
                return;

            StoredVehicle sv = list[listIndex];
            int slotIndex = sv.Slot;

            // Delete the entity if it exists
            if (_handles.TryGetValue(safehouseId, out var handles)
                && slotIndex >= 0 && slotIndex < handles.Length)
            {
                Vehicle veh = handles[slotIndex];
                if (veh != null && veh.Exists())
                {
                    veh.IsPersistent = true;
                    veh.Delete();
                }
                handles[slotIndex] = null;
            }

            Log($"RemoveVehicle: {sv.Model} from {safehouseId} slot {slotIndex}");
            list.RemoveAt(listIndex);
            Save();
        }

        internal static bool IsDebug()
        {
            return _debug;
        }

        /// <summary>
        /// Draw debug markers at all parking slots. Call from OnTick when
        /// garage_debug is enabled.
        /// </summary>
        internal static void DrawDebugMarkers()
        {
            foreach (var sh in Safehouses)
            {
                for (int i = 0; i < _capacity && i < sh.Slots.Length; i++)
                {
                    Vector3 pos = sh.Slots[i].Position;
                    World.DrawMarker(
                        GTA.MarkerType.UpsideDownCone,
                        pos + new Vector3(0f, 0f, 2f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(0.5f, 0.5f, 0.5f),
                        System.Drawing.Color.FromArgb(128, 0, 255, 0));
                }
            }
        }

        // ------------------------------------------------------------------ //
        //  Internals                                                          //
        // ------------------------------------------------------------------ //

        private static Safehouse FindSafehouse(string id)
        {
            foreach (var sh in Safehouses)
            {
                if (sh.Id == id)
                    return sh;
            }
            return null;
        }

        private static int FindEmptySlot(string safehouseId, Safehouse sh)
        {
            if (!_stored.TryGetValue(safehouseId, out var list))
                return -1;

            var occupied = new HashSet<int>();
            foreach (var sv in list)
                occupied.Add(sv.Slot);

            for (int i = 0; i < _capacity && i < sh.Slots.Length; i++)
            {
                if (!occupied.Contains(i))
                    return i;
            }
            return -1;
        }

        private static void RespawnAll()
        {
            foreach (var sh in Safehouses)
            {
                if (!_stored.TryGetValue(sh.Id, out var list))
                    continue;

                if (!_handles.TryGetValue(sh.Id, out var handles))
                    continue;

                foreach (var sv in list)
                {
                    if (sv.Slot < 0 || sv.Slot >= sh.Slots.Length)
                        continue;

                    // Skip if already spawned (script reload)
                    if (handles[sv.Slot] != null && handles[sv.Slot].Exists())
                    {
                        Log($"RespawnAll: {sv.Model} at {sh.Id} slot {sv.Slot} already exists, skipping");
                        continue;
                    }

                    // Skip if another vehicle is already parked there
                    ParkingSlot slot = sh.Slots[sv.Slot];
                    try
                    {
                        Vehicle[] nearby = World.GetNearbyVehicles(slot.Position, 3f);
                        if (nearby != null && nearby.Length > 0)
                        {
                            // Claim the existing vehicle as ours
                            handles[sv.Slot] = nearby[0];
                            Log($"RespawnAll: claimed existing vehicle at {sh.Id} slot {sv.Slot}");
                            continue;
                        }
                    }
                    catch (Exception ex)
                    {
                        LogException("RespawnAll.GetNearbyVehicles", ex);
                    }

                    try
                    {
                        Vehicle veh = VehicleHelper.CreateVehicle(
                            sv.Model, slot.Position, slot.Heading,
                            sv.Color1, sv.Color2);

                        if (veh != null)
                        {
                            veh.IsPersistent = true;
                            veh.IsEngineRunning = false;
                            handles[sv.Slot] = veh;
                            Log($"RespawnAll: spawned {sv.Model} at {sh.Id} slot {sv.Slot}");
                        }
                        else
                        {
                            Log($"RespawnAll: failed to spawn {sv.Model} at {sh.Id} slot {sv.Slot}");
                        }
                    }
                    catch (Exception ex)
                    {
                        LogException($"RespawnAll.CreateVehicle({sv.Model})", ex);
                    }
                }
            }
        }

        // ------------------------------------------------------------------ //
        //  JSON persistence (hand-rolled -- tiny data, no library needed)     //
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

            bool firstSafehouse = true;
            foreach (var sh in Safehouses)
            {
                if (!firstSafehouse)
                    sb.AppendLine(",");
                firstSafehouse = false;

                sb.Append($"  \"{sh.Id}\": [");

                if (_stored.TryGetValue(sh.Id, out var list) && list.Count > 0)
                {
                    sb.AppendLine();
                    for (int i = 0; i < list.Count; i++)
                    {
                        var sv = list[i];
                        sb.Append($"    {{ \"model\": \"{sv.Model}\", \"slot\": {sv.Slot}, \"color1\": {sv.Color1}, \"color2\": {sv.Color2} }}");
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
            }

            sb.AppendLine();
            sb.AppendLine("}");
            return sb.ToString();
        }

        private static void ParseJson(string json)
        {
            // Minimal parser for our known flat structure.
            // Expects: { "safehouse_id": [ { "model": "x", "slot": N, "color1": N, "color2": N }, ... ], ... }
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

                    // Determine context: is this a top-level key or a value key?
                    if (currentKey == null)
                    {
                        // Check if next non-whitespace is ':'
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
                    // Parse array of objects for this safehouse
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
            string model = null;
            int slot = -1;
            int color1 = 0;
            int color2 = 0;

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

                    // Skip to ':'
                    i = SkipWhitespace(json, i);
                    if (i < json.Length && json[i] == ':')
                        i++;
                    i = SkipWhitespace(json, i);

                    if (key == "model")
                    {
                        // Read string value
                        if (i < json.Length && json[i] == '"')
                        {
                            int vEnd = json.IndexOf('"', i + 1);
                            if (vEnd >= 0)
                            {
                                model = json.Substring(i + 1, vEnd - i - 1);
                                i = vEnd + 1;
                            }
                        }
                    }
                    else
                    {
                        // Read integer value
                        int numStart = i;
                        while (i < json.Length && (char.IsDigit(json[i]) || json[i] == '-'))
                            i++;
                        string numStr = json.Substring(numStart, i - numStart);
                        if (int.TryParse(numStr, out int val))
                        {
                            if (key == "slot") slot = val;
                            else if (key == "color1") color1 = val;
                            else if (key == "color2") color2 = val;
                        }
                    }
                    continue;
                }

                i++;
            }

            if (model != null && slot >= 0)
            {
                return new StoredVehicle
                {
                    Model = model,
                    Slot = slot,
                    Color1 = color1,
                    Color2 = color2,
                };
            }
            return null;
        }

        private static int SkipWhitespace(string s, int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i]))
                i++;
            return i;
        }
    }
}
