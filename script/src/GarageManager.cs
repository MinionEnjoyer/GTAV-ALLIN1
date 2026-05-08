// GarageManager.cs -- Safehouse garage storage and vehicle delivery.
//
// Tracks stored vehicles in a JSON file and spawns them at parking slots
// at each character's real safehouse garages. Garage positions are from
// GTA V's internal garage zone data (DurtyFree/gta-v-data-dumps).

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
            internal string GarageName; // native name for IS_VEHICLE_IN_GARAGE_AREA
            internal uint GarageHash;   // hash for IS_PLAYER_ENTIRELY_INSIDE_GARAGE
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

        // Real GTA V safehouse garage zones. Coordinates from game data
        // (garages.json). Parking slot offsets are estimates -- use
        // garage_debug = true to tune in-game.
        internal static readonly Safehouse[] Safehouses =
        {
            // --- Franklin ---------------------------------------------------
            new Safehouse
            {
                Id = "franklin_aunt",
                Name = "Forum Drive Garage",
                Character = PedHash.Franklin,
                GarageName = "Franklin - Aunt",
                GarageHash = 4019785634,
                Slots = new[]
                {
                    // Enclosed garage at Aunt's house on Forum Drive
                    new ParkingSlot(-22.0f, -1432.0f, 28.83f, 180f),
                    new ParkingSlot(-25.5f, -1432.0f, 28.83f, 180f),
                },
            },
            new Safehouse
            {
                Id = "franklin_hills",
                Name = "Vinewood Hills Garage",
                Character = PedHash.Franklin,
                GarageName = "Franklin - Hills",
                GarageHash = 2393745202,
                Slots = new[]
                {
                    // Open driveway at 3671 Whispymound Drive
                    new ParkingSlot(18.0f, 545.0f, 175.5f, 340f),
                    new ParkingSlot(21.0f, 544.0f, 175.5f, 340f),
                    new ParkingSlot(24.0f, 543.0f, 175.5f, 340f),
                    new ParkingSlot(27.0f, 542.0f, 175.5f, 340f),
                },
            },

            // --- Michael ----------------------------------------------------
            new Safehouse
            {
                Id = "michael_beverly",
                Name = "Rockford Hills Garage",
                Character = PedHash.Michael,
                GarageName = "Michael - Beverly Hills",
                GarageHash = 360562957,
                Slots = new[]
                {
                    // Enclosed two-car garage at De Santa residence
                    new ParkingSlot(-811.0f, 187.0f, 72.5f, 0f),
                    new ParkingSlot(-814.5f, 187.0f, 72.5f, 0f),
                },
            },

            // --- Trevor -----------------------------------------------------
            new Safehouse
            {
                Id = "trevor_countryside",
                Name = "Sandy Shores Garage",
                Character = PedHash.Trevor,
                GarageName = "Trevor - Countryside",
                GarageHash = 2175093583,
                Slots = new[]
                {
                    // Open area beside Trevor's trailer
                    new ParkingSlot(1968.0f, 3818.0f, 32.3f, 30f),
                    new ParkingSlot(1971.5f, 3816.0f, 32.3f, 30f),
                    new ParkingSlot(1975.0f, 3814.0f, 32.3f, 30f),
                    new ParkingSlot(1978.5f, 3812.0f, 32.3f, 30f),
                },
            },
            new Safehouse
            {
                Id = "trevor_city",
                Name = "Vespucci Garage",
                Character = PedHash.Trevor,
                GarageName = "Trevor - City",
                GarageHash = 3774828611,
                Slots = new[]
                {
                    // Open parking at Floyd's apartment, Vespucci
                    new ParkingSlot(-1146.0f, -1539.0f, 4.4f, 35f),
                    new ParkingSlot(-1143.0f, -1541.0f, 4.4f, 35f),
                },
            },
            new Safehouse
            {
                Id = "trevor_stripclub",
                Name = "Stripclub Garage",
                Character = PedHash.Trevor,
                GarageName = "Trevor - Stripclub",
                GarageHash = 1066626361,
                Slots = new[]
                {
                    // Open parking at Vanilla Unicorn
                    new ParkingSlot(139.0f, -1292.0f, 29.3f, 120f),
                    new ParkingSlot(139.0f, -1288.5f, 29.3f, 120f),
                },
            },
        };

        // Migration map: old safehouse IDs -> new IDs (for save file compat)
        private static readonly Dictionary<string, string> MIGRATION_MAP =
            new Dictionary<string, string>
            {
                { "grove_street", "franklin_aunt" },
                { "vinewood_garage", "michael_beverly" },
                { "pillbox_hill", "trevor_countryside" },
            };

        // ------------------------------------------------------------------ //
        //  State                                                              //
        // ------------------------------------------------------------------ //

        private static readonly string SCRIPTS_DIR =
            AppDomain.CurrentDomain.BaseDirectory;
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

        // model hash -> model name (reverse lookup, built at init)
        private static readonly Dictionary<int, string> _modelByHash =
            new Dictionary<int, string>();

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

            foreach (var sh in Safehouses)
            {
                if (!_stored.ContainsKey(sh.Id))
                    _stored[sh.Id] = new List<StoredVehicle>();
                if (!_handles.ContainsKey(sh.Id))
                    _handles[sh.Id] = new Vehicle[sh.Slots.Length];
            }

            try
            {
                BuildModelLookup();

                Load();
                int totalStored = 0;
                foreach (var list in _stored.Values)
                    totalStored += list.Count;
                Log($"Loaded {totalStored} stored vehicles from {SAVE_PATH}");

                RespawnAll();
                ScanForExistingVehicles();
                Log("RespawnAll + scan complete");
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

        internal static int GetCapacity(string safehouseId)
        {
            Safehouse sh = FindSafehouse(safehouseId);
            if (sh == null) return 0;
            return sh.Slots.Length;
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

            if (list.Count >= sh.Slots.Length)
            {
                Log($"DeliverVehicle: {safehouseId} full ({list.Count}/{sh.Slots.Length})");
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
            Function.Call((Hash)0x428BACCDF5E26EAD, veh, true); // SET_VEHICLE_CAN_SAVE_IN_GARAGE

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
                for (int i = 0; i < sh.Slots.Length; i++)
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

        /// <summary>
        /// Build a hash -> model name lookup from VehicleList.All so we can
        /// identify vehicles found parked at garage slots.
        /// </summary>
        private static void BuildModelLookup()
        {
            _modelByHash.Clear();
            foreach (string name in VehicleList.All)
            {
                int hash = new Model(name).Hash;
                if (!_modelByHash.ContainsKey(hash))
                    _modelByHash[hash] = name;
            }
            Log($"BuildModelLookup: {_modelByHash.Count} models indexed");
        }

        /// <summary>
        /// Scan each empty parking slot for vehicles that are already there
        /// (e.g. vanilla game vehicles or leftovers from a previous session)
        /// and register them so they show up in the garage UI.
        /// </summary>
        private static void ScanForExistingVehicles()
        {
            bool changed = false;

            foreach (var sh in Safehouses)
            {
                if (!_stored.TryGetValue(sh.Id, out var list))
                    continue;
                if (!_handles.TryGetValue(sh.Id, out var handles))
                    continue;

                // Build set of already-occupied slots
                var occupied = new HashSet<int>();
                foreach (var sv in list)
                    occupied.Add(sv.Slot);

                for (int i = 0; i < sh.Slots.Length; i++)
                {
                    if (occupied.Contains(i))
                        continue;

                    ParkingSlot slot = sh.Slots[i];
                    Vehicle[] nearby = null;
                    try
                    {
                        nearby = World.GetNearbyVehicles(slot.Position, 5f);
                    }
                    catch (Exception ex)
                    {
                        LogException("ScanForExisting.GetNearby", ex);
                        continue;
                    }

                    if (nearby == null || nearby.Length == 0)
                        continue;

                    // Pick the closest vehicle
                    Vehicle best = null;
                    float bestDist = float.MaxValue;
                    foreach (var v in nearby)
                    {
                        if (v == null || !v.Exists())
                            continue;
                        float d = v.Position.DistanceTo(slot.Position);
                        if (d < bestDist)
                        {
                            bestDist = d;
                            best = v;
                        }
                    }

                    if (best == null)
                        continue;

                    // Look up model name from hash
                    int hash = best.Model.Hash;
                    string modelName;
                    if (!_modelByHash.TryGetValue(hash, out modelName))
                    {
                        // Unknown model -- use the GXT label as fallback
                        modelName = Function.Call<string>(
                            (Hash)0xB215AAC32D25D019, hash); // GET_DISPLAY_NAME_FROM_VEHICLE_MODEL
                        if (string.IsNullOrEmpty(modelName))
                            modelName = $"0x{hash:X8}";
                    }

                    // Get current colours
                    int c1 = 0, c2 = 0;
                    try
                    {
                        OutputArgument oc1 = new OutputArgument();
                        OutputArgument oc2 = new OutputArgument();
                        Function.Call((Hash)0xA19435F193E081AC, best, oc1, oc2); // GET_VEHICLE_COLOURS
                        c1 = oc1.GetResult<int>();
                        c2 = oc2.GetResult<int>();
                    }
                    catch { }

                    var stored = new StoredVehicle
                    {
                        Model = modelName,
                        Slot = i,
                        Color1 = c1,
                        Color2 = c2,
                    };
                    list.Add(stored);
                    handles[i] = best;
                    best.IsPersistent = true;
                    Function.Call((Hash)0x428BACCDF5E26EAD, best, true); // SET_VEHICLE_CAN_SAVE_IN_GARAGE
                    occupied.Add(i);
                    changed = true;

                    Log($"ScanForExisting: found {modelName} at {sh.Id} slot {i} (dist={bestDist:F1}m)");
                }
            }

            if (changed)
            {
                Save();
                int totalStored = 0;
                foreach (var list in _stored.Values)
                    totalStored += list.Count;
                Log($"ScanForExisting: saved, total={totalStored}");
            }
        }

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

            for (int i = 0; i < sh.Slots.Length; i++)
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
                            Function.Call((Hash)0x428BACCDF5E26EAD, veh, true); // SET_VEHICLE_CAN_SAVE_IN_GARAGE
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
                ValidateSlots();
            }
            catch (Exception ex)
            {
                LogException("Load", ex);
            }
        }

        /// <summary>
        /// After loading (and possibly migrating), ensure stored vehicles
        /// have valid slot indices for their garage. Old garages may have
        /// had more slots than the new definition.
        /// </summary>
        private static void ValidateSlots()
        {
            bool needsSave = false;

            foreach (var sh in Safehouses)
            {
                if (!_stored.TryGetValue(sh.Id, out var list))
                    continue;

                int capacity = sh.Slots.Length;
                var kept = new List<StoredVehicle>();
                var usedSlots = new HashSet<int>();

                foreach (var sv in list)
                {
                    if (sv.Slot >= 0 && sv.Slot < capacity && !usedSlots.Contains(sv.Slot))
                    {
                        kept.Add(sv);
                        usedSlots.Add(sv.Slot);
                    }
                    else
                    {
                        // Try to reassign to an available slot
                        int newSlot = -1;
                        for (int s = 0; s < capacity; s++)
                        {
                            if (!usedSlots.Contains(s))
                            {
                                newSlot = s;
                                break;
                            }
                        }

                        if (newSlot >= 0)
                        {
                            sv.Slot = newSlot;
                            kept.Add(sv);
                            usedSlots.Add(newSlot);
                            Log($"ValidateSlots: reassigned {sv.Model} to slot {newSlot} at {sh.Id}");
                            needsSave = true;
                        }
                        else
                        {
                            Log($"ValidateSlots: dropped {sv.Model} from {sh.Id} (no room, capacity={capacity})");
                            needsSave = true;
                        }
                    }
                }

                if (kept.Count != list.Count)
                {
                    _stored[sh.Id] = kept;
                    needsSave = true;
                }
            }

            if (needsSave)
            {
                Log("ValidateSlots: re-saving after migration/fixup");
                Save();
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

                    // Migrate old safehouse IDs to new ones
                    string resolvedKey = currentKey;
                    if (MIGRATION_MAP.TryGetValue(currentKey, out string newKey))
                    {
                        Log($"Load: migrating '{currentKey}' -> '{newKey}'");
                        resolvedKey = newKey;
                    }

                    if (_stored.ContainsKey(resolvedKey))
                        _stored[resolvedKey] = vehicles;

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
