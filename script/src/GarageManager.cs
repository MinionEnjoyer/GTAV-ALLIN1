// GarageManager.cs -- Independent garage at the 10-car underground interior.
//
// Each character (Michael, Franklin, Trevor) has 10 personal vehicle slots
// in a shared garage interior that exists permanently underground. Vehicles
// are spawned when the player enters the garage and despawned on exit.
// Entry/exit is via the Eclipse Garage marker on Eclipse Boulevard.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal static partial class GarageManager
    {
        // ------------------------------------------------------------------ //
        //  Types                                                              //
        // ------------------------------------------------------------------ //

        internal struct ParkingSlot
        {
            internal Vector3 Position;
            internal float Heading;
            internal float FloorZ;

            internal ParkingSlot(float x, float y, float z, float h)
                : this(x, y, z, h, float.NaN)
            {
            }

            internal ParkingSlot(float x, float y, float z, float h, float floorZ)
            {
                Position = new Vector3(x, y, z);
                Heading = h;
                FloorZ = floorZ;
            }
        }

        internal class StoredVehicle
        {
            internal string Model;
            // Preserve the native identity for base-game/add-on vehicles whose
            // GXT display label is not their spawn name (for example Furore GT:
            // `furore` vs `furoregt`). Zero means a legacy save entry.
            internal int ModelHash;
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
        private static readonly GarageDefinition ECLIPSE_GARAGE =
            GarageDefinitions.Eclipse;

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

        // Ten surveyed parking bays in the apartment garage shell. FloorZ is
        // the physical plane; Position.Z remains the audited root fallback.
        internal static readonly ParkingSlot[] Slots =
        {
            // Left row (facing heading -105)
            new ParkingSlot(224.57f, -1002.75f, -99.56f, -105f, -100.0f),
            new ParkingSlot(224.36f, -998.87f,  -99.56f, -105f, -100.0f),
            new ParkingSlot(223.61f, -993.94f,  -99.56f, -105f, -100.0f),
            new ParkingSlot(223.65f, -989.04f,  -99.56f, -105f, -100.0f),
            new ParkingSlot(224.18f, -983.51f,  -99.56f, -105f, -100.0f),
            // Right row (facing heading 134) -- shifted -0.5 X for wall clearance
            new ParkingSlot(233.94f, -1000.90f, -99.56f, 134f, -100.0f),
            new ParkingSlot(233.18f, -995.90f,  -99.56f, 134f, -100.0f),
            new ParkingSlot(232.50f, -991.15f,  -99.56f, 134f, -100.0f),
            new ParkingSlot(232.44f, -985.76f,  -99.56f, 134f, -100.0f),
            new ParkingSlot(231.89f, -981.39f,  -99.56f, 134f, -100.0f),
        };

        // Character keys for save file
        private const string KEY_MICHAEL  = "michael";
        private const string KEY_FRANKLIN = "franklin";
        private const string KEY_TREVOR   = "trevor";
        private const string KEY_UNSUPPORTED = "__unsupported__";

        // Story vehicles are owned and restored by Rockstar's scripts. Their
        // model/plate pairs provide a fallback when mission transitions remove
        // the normal decorator or personal-vehicle blip. Matching both avoids
        // blocking an ordinary civilian vehicle of the same model.
        private static readonly Dictionary<int, string> PROTECTED_STORY_VEHICLES =
            new Dictionary<int, string>
            {
                { Game.GenerateHash("buffalo2"),  "FC1988" },   // Franklin
                { Game.GenerateHash("bagger"),    "FC88" },     // Franklin
                { Game.GenerateHash("bodhi2"),    "BETTY32" },  // Trevor
                { Game.GenerateHash("tailgater"), "5MDS003" },  // Michael
                { Game.GenerateHash("premier"),   "880HS955" }, // Michael (temporary)
                { Game.GenerateHash("sentinel2"), "KRYST4L" },  // Amanda
                { Game.GenerateHash("issi2"),     "P3RSEUS" },  // Tracey
                { Game.GenerateHash("bjxl"),      "57EIG117" }, // Jimmy
            };

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
        private static bool _transitionInProgress;

        private static Blip _entranceBlip;
        private static Blip _pedEntranceBlip;
        private static BlipColor _lastBlipColor;
        private static bool _hasBlipColor;

        // Cooldown to avoid re-entering immediately after exiting
        private static int _exitCooldownFrames;

        // Reverse lookup: model hash -> spawn name (built from VehicleList.All)
        private static Dictionary<int, string> _hashToSpawnName;
        private static readonly Dictionary<string, string> LegacyModelAliases =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                { "furore", "furoregt" },
            };
        private static readonly Dictionary<string, string> LegacyModelDisplayNames =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                { "furoregt", "Furore GT" },
            };

        private static bool _enableLogging = true;
        private static bool _garagesAlwaysAccessible;
        private static bool _initialized;
        private static PedHash _lastGarageCharacter;
        private static bool _vehicleSavesDirty;
        private static bool _garageCustomizationSavesDirty;
        private static bool _vehicleSaveCommitInProgress;
        private static bool _storySaveWasInProgress;
        private static bool _discardStagedGarageStateAfterLoad;
        private static DateTime _lastStorySaveWriteUtc;
        private static DateTime _nextStorySavePollUtc;

        // ------------------------------------------------------------------ //
        //  Logging                                                            //
        // ------------------------------------------------------------------ //

        private static void Log(string msg)
        {
            if (!_enableLogging)
                return;
            ClientLog.Info("Garage", msg);
        }

        private static void LogException(string context, Exception ex)
        {
            ClientLog.Error("Garage", context, ex);
        }

        // ------------------------------------------------------------------ //
        //  Public API                                                         //
        // ------------------------------------------------------------------ //

        internal static void Configure(
            bool enableLogging, bool garagesAlwaysAccessible = false)
        {
            _enableLogging = enableLogging;
            _garagesAlwaysAccessible = garagesAlwaysAccessible;
        }

        internal static bool IsInGarage => _isPlayerInGarage;
        internal static bool TransitionInProgress => _transitionInProgress;

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
                _lastStorySaveWriteUtc =
                    CharacterInventory.LatestStorySaveWriteUtc();

                int total = 0;
                foreach (var list in _stored.Values)
                    total += list.Count;
                Log($"Loaded {total} stored vehicles from {SAVE_PATH}");

                // Create entrance blip
                _entranceBlip = World.CreateBlip(ENTRANCE_POS);
                _entranceBlip.Sprite = BlipSprite.Garage;
                _entranceBlip.Color = CharacterBlipColor();
                _entranceBlip.Name = "ALLIN1 Eclipse Garage (Vehicle)";
                _entranceBlip.IsShortRange = true;

                _pedEntranceBlip = World.CreateBlip(PED_EXIT_DEST);
                _pedEntranceBlip.Sprite = BlipSprite.Garage;
                _pedEntranceBlip.Color = CharacterBlipColor();
                _pedEntranceBlip.Name = "ALLIN1 Eclipse Garage (Pedestrian)";
                _pedEntranceBlip.IsShortRange = true;

                Log("GarageManager initialized (Eclipse Garage 10-car interior)");
            }
            catch (Exception ex)
            {
                LogException("Initialize", ex);
            }

            _initialized = true;
        }

        internal static bool IsPlayerInGarage => _isPlayerInGarage;
        internal static bool IsTransitionInProgress => _transitionInProgress;

        /// <summary>Emergency escape for a stuck interior or transition.</summary>
        internal static void EmergencyRecover()
        {
            try
            {
                Vector3 recoveryPosition = _isPlayerInPaletoGarage
                    ? PALETO_PED_ENTRANCE_POS
                    : _isPlayerInRuralGarage ? RURAL_PED_ENTRANCE_POS
                    : _isPlayerInGarmentGarage ? GARMENT_PED_ENTRANCE_POS
                    : _isPlayerInDavisGarage
                    ? DAVIS_PED_ENTRANCE_POS
                    : _isPlayerInFloorGarage ? FLOOR_GARAGE_PED_EXIT_DEST : PED_EXIT_DEST;
                float recoveryHeading = _isPlayerInPaletoGarage
                    ? PALETO_PED_ENTRANCE_HEADING
                    : _isPlayerInRuralGarage ? RURAL_PED_ENTRANCE_HEADING
                    : _isPlayerInGarmentGarage ? GARMENT_PED_ENTRANCE_HEADING
                    : _isPlayerInDavisGarage
                    ? DAVIS_PED_ENTRANCE_HEADING
                    : _isPlayerInFloorGarage
                        ? FLOOR_GARAGE_PED_EXIT_DEST_HEADING : PED_EXIT_DEST_HEADING;
                UpdateStoredFromLive();
                FloorGarageUpdateStoredFromLive();
                DavisUpdateStoredFromLive();
                GarmentUpdateStoredFromLive();
                RuralUpdateStoredFromLive();
                PaletoUpdateStoredFromLive();
                for (int i = 0; i < _handles.Length; i++)
                {
                    if (_handles[i] != null && _handles[i].Exists()) _handles[i].Delete();
                    _handles[i] = null;
                }
                for (int i = 0; i < _floorGarageHandles.Length; i++)
                {
                    if (_floorGarageHandles[i] != null && _floorGarageHandles[i].Exists())
                        _floorGarageHandles[i].Delete();
                    _floorGarageHandles[i] = null;
                }
                for (int i = 0; i < _davisHandles.Length; i++)
                {
                    if (_davisHandles[i] != null && _davisHandles[i].Exists())
                        _davisHandles[i].Delete();
                    _davisHandles[i] = null;
                }
                for (int i = 0; i < _garmentHandles.Length; i++)
                {
                    if (_garmentHandles[i] != null && _garmentHandles[i].Exists())
                        _garmentHandles[i].Delete();
                    _garmentHandles[i] = null;
                }
                for (int i = 0; i < _ruralHandles.Length; i++)
                {
                    if (_ruralHandles[i] != null && _ruralHandles[i].Exists())
                        _ruralHandles[i].Delete();
                    _ruralHandles[i] = null;
                }
                for (int i = 0; i < _paletoHandles.Length; i++)
                {
                    if (_paletoHandles[i] != null && _paletoHandles[i].Exists())
                        _paletoHandles[i].Delete();
                    _paletoHandles[i] = null;
                }
                RecoverTransition("EmergencyRecover", recoveryPosition, recoveryHeading);
                Log("EmergencyRecover: player returned outside and garage state reset");
                ClientLog.Warn("Garage", "emergency_recovery_completed");
            }
            catch (Exception ex)
            {
                LogException("EmergencyRecover", ex);
                RecoverTransition("EmergencyRecover.Fallback", PED_EXIT_DEST, PED_EXIT_DEST_HEADING);
            }
            finally { _transitionInProgress = false; }
        }

        /// <summary>
        /// Called every frame from GbayShop.OnTick. Handles entrance/exit
        /// marker drawing and proximity detection.
        /// </summary>
        internal static void OnTick()
        {
            if (!_initialized)
                return;

            PollStorySaveAndPersistVehicles();

            // Every ALLIN1 location follows the active protagonist. Keep this
            // before the garage/transition guards so switching characters in
            // an interior cannot leave another location with a stale color.
            UpdateLocationBlipColors();

            if (_transitionInProgress)
                return;

            // Don't show garage markers while in another garage.
            if (_isPlayerInFloorGarage || _isPlayerInDavisGarage)
                return;
            if (_isPlayerInGarmentGarage || _isPlayerInRuralGarage ||
                _isPlayerInPaletoGarage)
                return;

            if (_exitCooldownFrames > 0)
            {
                _exitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead)
                return;
            if (!_isPlayerInGarage && !GbayShop.TryGetCurrentCharacter(out _))
                return;

            if (!_isPlayerInGarage)
            {
                // Never detach the player, passengers, or a mission vehicle
                // from Rockstar's active mission script. Exits stay available
                // if a mission flag appears while already inside a garage.
                if (EvaluateGarageEntry(ECLIPSE_GARAGE) ==
                    GarageEntryDenial.MissionActive) return;

                bool inVehicle = player.IsInVehicle();

                // ---- Vehicle entrance — only when in a vehicle ----
                if (inVehicle)
                {
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(2f, 2f, 1.5f),
                        CharacterMarkerColor());

                    float vehDist = player.Position.DistanceTo(ENTRANCE_POS);
                    if (vehDist < ENTER_RADIUS)
                    {
                        Vehicle veh = player.CurrentVehicle;
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            ECLIPSE_GARAGE, veh);
                        if (denial != GarageEntryDenial.None)
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(ECLIPSE_GARAGE, denial));
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
                        CharacterMarkerColor());

                    float pedDist = player.Position.DistanceTo(PED_EXIT_DEST);
                    if (pedDist < ENTER_RADIUS)
                    {
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            ECLIPSE_GARAGE);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(ECLIPSE_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter your garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterGarage();
                        }
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
                        CharacterMarkerColor());

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

        internal static bool IsVehicleOwned(string model)
        {
            foreach (StoredVehicle vehicle in GetStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetFloorGarageStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetDavisGarageStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetGarmentGarageStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetRuralGarageStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetPaletoGarageStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetHelipadStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetHarbourStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            foreach (StoredVehicle vehicle in GetYachtHelipadStoredVehicles())
                if (string.Equals(vehicle.Model, model, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
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

            int modelHash = Game.GenerateHash(model);
            int slotIndex = FindEmptySlot(list, model, modelHash);
            if (slotIndex < 0)
            {
                Log($"DeliverVehicle: no empty slot for {model} (sizeTier={VehicleList.GetSizeTier(model)})");
                return false;
            }

            var stored = new StoredVehicle
            {
                Model = model,
                ModelHash = modelHash,
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
                        PlaceVehicleInParkingSpace(
                            veh, slot, model, "Eclipse");
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
        internal static bool RemoveVehicle(int listIndex)
        {
            string key = CharacterKey();
            if (!_stored.TryGetValue(key, out var list))
                return false;
            if (listIndex < 0 || listIndex >= list.Count)
                return false;

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
            if (!Save())
            {
                list.Insert(listIndex, sv);
                Log($"RemoveVehicle: persistence failed; restored {sv.Model}");
                return false;
            }
            return true;
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
            foreach (Vehicle[] handles in new[]
            {
                _floorGarageHandles, _davisHandles, _garmentHandles, _ruralHandles,
                _paletoHandles,
            })
            {
                foreach (Vehicle veh in handles)
                {
                    if (veh == null || !veh.Exists()) continue;
                    Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, veh, 0f);
                    Function.Call(Hash.SET_VEHICLE_FIXED, veh);
                    cleaned++;
                }
            }
            Log($"DetailVehicles: cleaned {cleaned} vehicles");
        }

        // ------------------------------------------------------------------ //
        //  Garage Enter / Leave                                               //
        // ------------------------------------------------------------------ //

        private static bool BeginTransition(string name)
        {
            if (_transitionInProgress)
            {
                Log($"{name}: ignored because another garage transition is active");
                return false;
            }
            _transitionInProgress = true;
            Log($"{name}: transition lock acquired");
            return true;
        }

        private static void RecoverTransition(string name, Vector3 fallback, float heading)
        {
            try
            {
                Ped player = Game.Player.Character;
                if (player != null && player.Exists())
                {
                    Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
                    Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
                    player.IsPositionFrozen = false;
                    Function.Call(Hash.SET_ENTITY_COORDS, player,
                        fallback.X, fallback.Y, fallback.Z,
                        false, false, false, true);
                    Function.Call(Hash.SET_ENTITY_HEADING, player, heading);
                }
            }
            catch (Exception recoveryEx)
            {
                LogException($"{name}.Recovery", recoveryEx);
            }
            finally
            {
                UnloadFloorGarageInterior();
                UnloadDavisAutoShopInterior();
                UnloadGarmentInterior();
                UnloadRuralInterior();
                UnloadPaletoInterior();
                _isPlayerInGarage = false;
                _isPlayerInFloorGarage = false;
                _isPlayerInDavisGarage = false;
                _isPlayerInGarmentGarage = false;
                _isPlayerInRuralGarage = false;
                _isPlayerInPaletoGarage = false;
                _elevatorMenuActive = false;
                _exitCooldownFrames = 120;
                _floorGarageExitCooldownFrames = 120;
                _davisExitCooldownFrames = 120;
                _garmentExitCooldownFrames = 120;
                _ruralExitCooldownFrames = 120;
                _paletoExitCooldownFrames = 120;
                try
                {
                    Function.Call(Hash.DO_SCREEN_FADE_IN, 0);
                }
                catch (Exception fadeEx)
                {
                    LogException($"{name}.RecoveryFade", fadeEx);
                }
            }
        }

        private static void EndTransition(string name)
        {
            try
            {
                Ped player = Game.Player.Character;
                if (player != null && player.Exists())
                {
                    Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
                    player.IsPositionFrozen = false;
                }
            }
            catch (Exception ex)
            {
                LogException($"{name}.End", ex);
            }
            _transitionInProgress = false;
            Log($"{name}: transition lock released");
        }

        private const int GARAGE_FADE_TIMEOUT_MS = 1500;
        private const int GARAGE_DESTINATION_TIMEOUT_MS = 8000;
        private const int GARAGE_DESTINATION_STABLE_MS = 250;

        private static void BeginGarageBlackTransition(string name)
        {
            if (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                Function.Call(Hash.DO_SCREEN_FADE_OUT, 350);

            int startedAt = Game.GameTime;
            while (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT) &&
                Game.GameTime - startedAt < GARAGE_FADE_TIMEOUT_MS)
                Script.Wait(0);

            if (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
            {
                Function.Call(Hash.DO_SCREEN_FADE_OUT, 0);
                Script.Wait(0);
            }
            Log($"{name}: black transition acquired in " +
                $"{Game.GameTime - startedAt}ms");
        }

        private static bool IsPlayerInReadyInterior(Ped player)
        {
            if (player == null || !player.Exists()) return false;
            int interior = Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY, player);
            return interior != 0 &&
                Function.Call<bool>(Hash.IS_INTERIOR_READY, interior);
        }

        private static bool AreGarageVehiclesReady(Vehicle[] handles)
        {
            if (handles == null) return true;
            foreach (Vehicle vehicle in handles)
            {
                if (vehicle == null || !vehicle.Exists()) continue;
                if (!Function.Call<bool>(
                    Hash.HAS_COLLISION_LOADED_AROUND_ENTITY, vehicle.Handle))
                    return false;
            }
            return true;
        }

        private static void CompleteGarageBlackTransition(
            string name,
            Ped player,
            Vehicle focusVehicle,
            Func<bool> destinationReady,
            Vehicle[] garageVehicles = null)
        {
            if (player == null || !player.Exists())
                throw new InvalidOperationException(
                    $"{name} lost the player during transition");

            int startedAt = Game.GameTime;
            int stableAt = -1;
            bool locationReady = false;
            bool collisionReady = false;
            bool vehiclesReady = false;
            while (Game.GameTime - startedAt < GARAGE_DESTINATION_TIMEOUT_MS)
            {
                Entity focus = focusVehicle != null && focusVehicle.Exists()
                    ? (Entity)focusVehicle : player;
                Vector3 position = focus.Position;
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    position.X, position.Y, position.Z);
                collisionReady = Function.Call<bool>(
                    Hash.HAS_COLLISION_LOADED_AROUND_ENTITY, focus.Handle);
                locationReady = destinationReady == null || destinationReady();
                vehiclesReady = AreGarageVehiclesReady(garageVehicles);

                if (locationReady && collisionReady && vehiclesReady)
                {
                    if (stableAt < 0) stableAt = Game.GameTime;
                    if (Game.GameTime - stableAt >= GARAGE_DESTINATION_STABLE_MS)
                    {
                        Log($"{name}: destination ready after " +
                            $"{Game.GameTime - startedAt}ms");
                        Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
                        return;
                    }
                }
                else stableAt = -1;
                Script.Wait(50);
            }

            throw new InvalidOperationException(
                $"{name} destination timed out while black " +
                $"(locationReady={locationReady}, " +
                $"collisionReady={collisionReady}, vehiclesReady={vehiclesReady})");
        }

        private static void EnterGarage()
        {
            if (RejectGarageEntry(ECLIPSE_GARAGE)) return;
            if (!BeginTransition("EnterGarage")) return;
            try
            {
                using (ClientLog.Time("Garage", "enter_garage")) EnterGarageCore();
            }
            catch (Exception ex)
            {
                LogException("EnterGarage", ex);
                RecoverTransition("EnterGarage", PED_EXIT_DEST, PED_EXIT_DEST_HEADING);
                GTA.UI.Screen.ShowSubtitle("~r~Garage entry failed safely. See ALLIN1_gbay.log.", 4000);
            }
            finally
            {
                EndTransition("EnterGarage");
            }
        }

        private static void EnterGarageCore()
        {
            Log("EnterGarage: START");
            Ped player = Game.Player.Character;
            Vehicle rideInToDelete = null;
            string storedConfirmation = null;

            // If player is in a vehicle, store it in the garage (if space),
            // then pull them out and delete the outside instance.
            // Personal vehicles are blocked — they can't be stored.
            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
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

                    if (RejectGarageEntry(
                        ECLIPSE_GARAGE, rideIn, modelName, modelHash)) return;

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
                            $"~r~The garage is full.~w~ ({storedList.Count}/{SLOT_COUNT} spaces used)", 3000);
                        return;
                    }

                    int slotIndex = FindEmptySlot(storedList, modelName, modelHash);
                    if (slotIndex < 0)
                    {
                        GTA.UI.Screen.ShowSubtitle("~r~The garage is full; no spaces are available.", 3000);
                        return;
                    }

                    // Capture full vehicle state (colors, mods, etc.)
                    StoredVehicle sv = CaptureVehicleState(rideIn, modelName, slotIndex);
                    storedList.Add(sv);
                    if (!Save())
                    {
                        storedList.Remove(sv);
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The vehicle could not be saved; it was left outside.", 3000);
                        return;
                    }

                    string displayName = VehicleList.DisplayNames.ContainsKey(modelName)
                        ? VehicleList.DisplayNames[modelName] : modelName;
                    storedConfirmation =
                        $"~g~{displayName}~w~ stored in the Eclipse Garage " +
                        $"(slot {slotIndex + 1}).";
                    Log($"EnterGarage: stored drive-in vehicle {modelName} -> slot {slotIndex}");

                    // Delete the outside vehicle (teleporting the player
                    // out via SET_ENTITY_COORDS below handles extraction)
                    rideIn.IsPersistent = true;
                    rideInToDelete = rideIn;
                }
            }

            // Clear any leftover handles from a previous session
            for (int i = 0; i < SLOT_COUNT; i++)
            {
                if (_handles[i] != null && _handles[i].Exists())
                    _handles[i].Delete();
                _handles[i] = null;
            }

            _isPlayerInGarage = true; // set early to block re-entry during fade
            Log("EnterGarage: flag set, starting fade out");

            // Hold black until the destination room, collision, and stored
            // vehicles have all remained ready for a stable interval.
            BeginGarageBlackTransition("EnterGarage");
            Log("EnterGarage: fade out done, teleporting");

            // Freeze player and teleport to safe interior position
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                PED_EXIT.X, PED_EXIT.Y, PED_EXIT.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player, PED_EXIT_HEADING);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, true);
            if (rideInToDelete != null && rideInToDelete.Exists())
            {
                rideInToDelete.Delete();
                Log("EnterGarage: deleted drive-in vehicle after player extraction");
            }
            Log("EnterGarage: teleported, spawning vehicles");

            // Pre-load all vehicle models before spawning
            string key = CharacterKey();
            var models = new List<Model>();
            if (_stored.TryGetValue(key, out var list))
            {
                Log($"EnterGarage: pre-loading {list.Count} vehicle models");
                foreach (var sv in list)
                {
                    var m = GetStoredModel(sv);
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
                        var model = GetStoredModel(sv);
                        Vehicle veh = World.CreateVehicle(model, slot.Position, slot.Heading);
                        model.MarkAsNoLongerNeeded();

                        if (veh != null)
                        {
                            ApplyVehicleState(veh, sv);
                            veh.IsPersistent = true;
                            veh.IsEngineRunning = false;
                            PlaceVehicleInParkingSpace(
                                veh, slot, sv.Model, "Eclipse");
                            veh.IsPositionFrozen = true;
                            _handles[sv.Slot] = veh;
                            Log($"EnterGarage: spawned {sv.Model} at slot {sv.Slot}");
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

            Log("EnterGarage: waiting for destination readiness");
            CompleteGarageBlackTransition(
                "EnterGarage", player, null,
                () => IsPlayerInReadyInterior(player), _handles);

            if (!string.IsNullOrEmpty(storedConfirmation))
                GTA.UI.Screen.ShowSubtitle(storedConfirmation, 4000);

            Log($"EnterGarage: COMPLETE, character={key}");
        }

        private static void LeaveGarage()
        {
            if (!BeginTransition("LeaveGarage")) return;
            try
            {
                using (ClientLog.Time("Garage", "leave_garage")) LeaveGarageCore();
            }
            catch (Exception ex)
            {
                LogException("LeaveGarage", ex);
                RecoverTransition("LeaveGarage", PED_EXIT_DEST, PED_EXIT_DEST_HEADING);
                GTA.UI.Screen.ShowSubtitle("~r~Garage exit recovered safely. See ALLIN1_gbay.log.", 4000);
            }
            finally
            {
                EndTransition("LeaveGarage");
            }
        }

        private static void LeaveGarageCore()
        {
            Log("LeaveGarage: START");
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

            Log("LeaveGarage: vehicles cleaned, starting fade out");
            BeginGarageBlackTransition("LeaveGarage");
            Log("LeaveGarage: fade done, teleporting");

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

                playerVehicle.IsPersistent = true;
                ReleaseGarageVehicleForDriving(
                    playerVehicle, ENTRANCE_POS, 180f, "Eclipse");

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

            Log("LeaveGarage: waiting for exterior readiness");
            CompleteGarageBlackTransition(
                "LeaveGarage", player, playerVehicle,
                () => Function.Call<int>(
                    Hash.GET_INTERIOR_FROM_ENTITY, player) == 0);
            Log("LeaveGarage: COMPLETE");
        }

        // ------------------------------------------------------------------ //
        //  Helpers                                                            //
        // ------------------------------------------------------------------ //

        private static bool IsMissionActive()
        {
            try { return Function.Call<bool>(Hash.GET_MISSION_FLAG); }
            catch (Exception ex)
            {
                // Fail closed. Entering a scripted interior without knowing
                // mission state is riskier than temporarily hiding a marker.
                LogException("IsMissionActive", ex);
                return true;
            }
        }

        private static void PollStorySaveAndPersistVehicles()
        {
            if (Game.IsLoading)
            {
                _storySaveWasInProgress = false;
                _discardStagedGarageStateAfterLoad = true;
                return;
            }

            try
            {
                if (_discardStagedGarageStateAfterLoad)
                {
                    _discardStagedGarageStateAfterLoad = false;
                    ReloadCommittedGarageState();
                }

                bool saveInProgress =
                    Function.Call<bool>(Hash.IS_AUTO_SAVE_IN_PROGRESS);
                DateTime latestWrite = _lastStorySaveWriteUtc;
                DateTime now = DateTime.UtcNow;
                if (now >= _nextStorySavePollUtc)
                {
                    _nextStorySavePollUtc = now.AddMilliseconds(500);
                    latestWrite = CharacterInventory.LatestStorySaveWriteUtc();
                }

                bool saveFileAdvanced = latestWrite > _lastStorySaveWriteUtc;
                bool hasSaveEvent = GarageStorySavePolicy.HasSaveEvent(
                    saveInProgress, _storySaveWasInProgress,
                    latestWrite, _lastStorySaveWriteUtc);
                _storySaveWasInProgress = saveInProgress;
                if (saveFileAdvanced)
                    _lastStorySaveWriteUtc = latestWrite;
                if (hasSaveEvent)
                    PersistVehiclesForStorySave(saveFileAdvanced
                        ? "story_save_written" : "story_save_started");
            }
            catch (Exception ex)
            {
                LogException("PollStorySaveAndPersistVehicles", ex);
            }
        }

        internal static void OnScriptAborted()
        {
            if (!_initialized) return;
            try
            {
                DateTime latestWrite =
                    CharacterInventory.LatestStorySaveWriteUtc();
                if (latestWrite <= _lastStorySaveWriteUtc) return;
                _lastStorySaveWriteUtc = latestWrite;
                PersistVehiclesForStorySave("story_save_written_on_shutdown");
            }
            catch (Exception ex)
            {
                LogException("OnScriptAborted", ex);
            }
        }

        private static void PersistVehiclesForStorySave(string reason)
        {
            // Capture live customization only at a genuine Story save. These
            // helpers return immediately for garages that are not occupied.
            UpdateStoredFromLive();
            FloorGarageUpdateStoredFromLive();
            DavisUpdateStoredFromLive();
            GarmentUpdateStoredFromLive();
            RuralUpdateStoredFromLive();
            PaletoUpdateStoredFromLive();
            YachtHelipadUpdateStoredFromLive();
            if (!_vehicleSavesDirty && !_garageCustomizationSavesDirty) return;

            bool eclipseSaved;
            bool harmonySaved;
            bool davisSaved;
            bool garmentSaved;
            bool ruralSaved;
            bool paletoSaved;
            bool helipadSaved;
            bool harbourSaved;
            bool yachtHelipadSaved;
            bool harmonyThemesSaved;
            bool davisCustomizationSaved;
            _vehicleSaveCommitInProgress = true;
            try
            {
                eclipseSaved = Save();
                harmonySaved = !_floorGarageInitialized || FloorGarageSave();
                davisSaved = !_davisInitialized || DavisSave();
                garmentSaved = !_garmentInitialized || GarmentSave();
                ruralSaved = !_ruralInitialized || RuralSave();
                paletoSaved = !_paletoInitialized || PaletoSave();
                helipadSaved = !_helipadInitialized || HelipadSave();
                harbourSaved = !_harbourInitialized || HarbourSave();
                yachtHelipadSaved = !_yachtHelipadInitialized ||
                    YachtHelipadSave();
                harmonyThemesSaved = !_garageCustomizationSavesDirty ||
                    FloorGarageThemesWrite();
                davisCustomizationSaved = !_garageCustomizationSavesDirty ||
                    DavisCustomizationWrite();
            }
            finally
            {
                _vehicleSaveCommitInProgress = false;
            }

            bool success = eclipseSaved && harmonySaved && davisSaved
                && garmentSaved && ruralSaved && paletoSaved &&
                helipadSaved && harbourSaved && yachtHelipadSaved &&
                harmonyThemesSaved && davisCustomizationSaved;
            if (success)
            {
                _vehicleSavesDirty = false;
                _garageCustomizationSavesDirty = false;
                ClientLog.Info("Garage", "vehicle_state_backed_up",
                    new Dictionary<string, object> { { "reason", reason } });
            }
            else
            {
                ClientLog.Warn("Garage", "vehicle_state_backup_failed",
                    new Dictionary<string, object> { { "reason", reason } });
            }
        }

        private static GarageEntryDenial EvaluateGarageEntry(
            GarageDefinition garage, Vehicle vehicle = null,
            string modelName = null, int modelHash = 0)
        {
            GarageEntryRules rules = garage.EntryRules;
            bool vehiclePresent = vehicle != null && vehicle.Exists();
            bool storyOwned = vehiclePresent && rules.BlockStoryOwnedVehicles &&
                IsPersonalVehicle(vehicle);
            bool unsupportedVehicleType = vehiclePresent &&
                RequiresSpecializedStorage(vehicle);
            bool sizeKnown = vehiclePresent && modelName != null;
            int sizeTier = sizeKnown ? GetGarageSizeTier(modelName, modelHash) : 0;
            return GarageEntryPolicy.Evaluate(
                rules,
                IsMissionActive(),
                IsUnsafeGarageTransitionActive(),
                Game.Player.WantedLevel,
                _garagesAlwaysAccessible,
                vehiclePresent,
                storyOwned,
                sizeKnown,
                sizeTier,
                unsupportedVehicleType);
        }

        private static string GarageEntryMessage(
            GarageDefinition garage, GarageEntryDenial denial,
            string vehicleName = null)
        {
            if (denial == GarageEntryDenial.MissionActive)
                return "~y~ALLIN1 garages are unavailable during missions.";
            if (denial == GarageEntryDenial.GameTransitionActive)
                return "~y~Wait for the current cutscene or game transition to finish.";
            if (denial == GarageEntryDenial.WantedLevel)
                return "~r~Lose your wanted level before entering an ALLIN1 garage.";
            if (denial == GarageEntryDenial.StoryOwnedVehicle)
                return $"~r~Story-owned personal vehicles cannot enter the {garage.DisplayName}.";
            if (denial == GarageEntryDenial.UnsupportedVehicleType)
                return "~r~Helicopters, planes, and boats require specialized ALLIN1 storage.";
            if (denial == GarageEntryDenial.VehicleTooLarge)
                return $"~r~{vehicleName ?? "That vehicle"}~w~ is too large for the " +
                    $"{garage.DisplayName}.{garage.EntryRules.OversizedVehicleHint}";
            return "";
        }

        private static bool RequiresSpecializedStorage(Vehicle vehicle)
        {
            if (vehicle == null || !vehicle.Exists()) return false;
            try
            {
                uint hash = (uint)vehicle.Model.Hash;
                return Function.Call<bool>(Hash.IS_THIS_MODEL_A_HELI, hash) ||
                    Function.Call<bool>(Hash.IS_THIS_MODEL_A_PLANE, hash) ||
                    Function.Call<bool>(Hash.IS_THIS_MODEL_A_BOAT, hash);
            }
            catch (Exception ex)
            {
                LogException("RequiresSpecializedStorage", ex);
                return true;
            }
        }

        private static void ReloadCommittedGarageState()
        {
            foreach (List<StoredVehicle> list in _stored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _floorGarageStored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _davisStored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _garmentStored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _ruralStored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _paletoStored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _helipadStored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _harbourStored.Values) list.Clear();
            foreach (List<StoredVehicle> list in _yachtHelipadStored.Values) list.Clear();

            ResetGarageCustomizationDefaults();
            Load();
            FloorGarageLoad();
            DavisLoad();
            GarmentLoad();
            RuralLoad();
            PaletoLoad();
            HelipadLoad();
            HarbourLoad();
            YachtHelipadLoad();
            FloorGarageThemesLoad();
            DavisCustomizationLoad();
            _vehicleSavesDirty = false;
            _garageCustomizationSavesDirty = false;
            ClientLog.Info("Garage", "unsaved_gbay_state_discarded");
        }

        private static void ResetGarageCustomizationDefaults()
        {
            _floorThemes[KEY_MICHAEL_FG] = DefaultThemes();
            _floorThemes[KEY_FRANKLIN_FG] = DefaultThemes();
            _floorThemes[KEY_TREVOR_FG] = DefaultThemes();
            _davisCustomization[KEY_MICHAEL] =
                (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone();
            _davisCustomization[KEY_FRANKLIN] =
                (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone();
            _davisCustomization[KEY_TREVOR] =
                (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone();
        }

        private static bool RejectGarageEntry(
            GarageDefinition garage, Vehicle vehicle = null,
            string modelName = null, int modelHash = 0)
        {
            GarageEntryDenial denial = EvaluateGarageEntry(
                garage, vehicle, modelName, modelHash);
            if (denial == GarageEntryDenial.None) return false;

            string displayName = modelName != null &&
                VehicleList.DisplayNames.TryGetValue(modelName, out string knownName)
                ? knownName : modelName;
            GTA.UI.Screen.ShowSubtitle(
                GarageEntryMessage(garage, denial, displayName), 3000);
            ClientLog.Warn("Garage", "entry_blocked",
                new Dictionary<string, object> {
                    { "garage", garage.Id }, { "reason", denial.ToString() },
                    { "model", modelName ?? "" }
                });
            return true;
        }

        private static bool IsUnsafeGarageTransitionActive()
        {
            try
            {
                return Function.Call<bool>(Hash.IS_CUTSCENE_ACTIVE)
                    || Function.Call<bool>(Hash.IS_PLAYER_SWITCH_IN_PROGRESS)
                    || Function.Call<bool>(Hash.IS_SCREEN_FADING_IN)
                    || Function.Call<bool>(Hash.IS_SCREEN_FADING_OUT);
            }
            catch (Exception ex)
            {
                // Map switching during an unknown transition can assert inside
                // GTA itself, so fail closed if transition state cannot be read.
                LogException("IsUnsafeGarageTransitionActive", ex);
                return true;
            }
        }

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

            // Method 3: Match Rockstar's model/plate identity. Unlike a model-
            // only blacklist, this still permits an ordinary civilian model.
            try
            {
                string plate = Function.Call<string>(
                    Hash.GET_VEHICLE_NUMBER_PLATE_TEXT, veh);
                if (IsProtectedStoryVehicle(veh.Model.Hash, plate))
                    return true;
            }
            catch { }

            return false;
        }

        private static string NormalizePlate(string plateText)
        {
            return string.IsNullOrWhiteSpace(plateText)
                ? ""
                : plateText.Replace(" ", "").Trim().ToUpperInvariant();
        }

        private static bool IsProtectedStoryVehicle(int modelHash, string plateText)
        {
            return PROTECTED_STORY_VEHICLES.TryGetValue(modelHash,
                out string expectedPlate) &&
                string.Equals(NormalizePlate(plateText), expectedPlate,
                    StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>Protect story-owned entries already present in older saves.</summary>
        internal static bool IsProtectedStoryVehicle(
            string model, string plateText, int modelHash = 0)
        {
            int resolvedHash = modelHash != 0 ? modelHash
                : !string.IsNullOrWhiteSpace(model) ? Game.GenerateHash(model) : 0;
            return resolvedHash != 0 &&
                IsProtectedStoryVehicle(resolvedHash, plateText);
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
            PedHash ch = GarageCharacter();
            if (ch == PedHash.Franklin) return BlipColor.Green;
            if (ch == PedHash.Trevor)   return BlipColor.Orange;
            if (ch == PedHash.Michael)  return BlipColor.Blue;
            return (BlipColor)0;
        }

        private static void SetBlipColor(Blip blip, BlipColor color)
        {
            if (blip != null && blip.Exists()) blip.Color = color;
        }

        /// <summary>
        /// Apply the active protagonist's color to every ALLIN1 map location.
        /// A single cache prevents the three garage implementations from
        /// drifting apart or doing redundant native calls every frame.
        /// </summary>
        private static void UpdateLocationBlipColors()
        {
            BlipColor charColor = CharacterBlipColor();
            if (_hasBlipColor && charColor == _lastBlipColor) return;

            SetBlipColor(_entranceBlip, charColor);
            SetBlipColor(_pedEntranceBlip, charColor);
            SetBlipColor(_floorGarageEntranceBlip, charColor);
            SetBlipColor(_floorGaragePedBlip, charColor);
            SetBlipColor(_davisVehicleBlip, charColor);
            SetBlipColor(_davisPedBlip, charColor);
            SetBlipColor(_garmentVehicleBlip, charColor);
            SetBlipColor(_garmentPedBlip, charColor);
            SetBlipColor(_ruralVehicleBlip, charColor);
            SetBlipColor(_ruralPedBlip, charColor);
            SetBlipColor(_paletoVehicleBlip, charColor);
            SetBlipColor(_paletoPedBlip, charColor);
            SetBlipColor(_helipadAccessBlip, charColor);
            SetBlipColor(_helipadVehicleBlip, charColor);
            SetBlipColor(_harbourAccessBlip, charColor);
            SetBlipColor(_harbourVehicleBlip, charColor);
            SetBlipColor(_marinaAccessBlip, charColor);
            SetBlipColor(_marinaVehicleBlip, charColor);

            _lastBlipColor = charColor;
            _hasBlipColor = true;
        }

        private static System.Drawing.Color CharacterMarkerColor()
        {
            PedHash ch = GarageCharacter();
            if (ch == PedHash.Franklin) return System.Drawing.Color.FromArgb(128, 100, 255, 100);
            if (ch == PedHash.Trevor)   return System.Drawing.Color.FromArgb(128, 255, 170, 50);
            if (ch == PedHash.Michael)  return System.Drawing.Color.FromArgb(128, 100, 100, 255);
            return System.Drawing.Color.FromArgb(128, 180, 180, 180);
        }

        private static PedHash GarageCharacter()
        {
            if (GbayShop.TryGetCurrentCharacter(out PedHash character))
            {
                _lastGarageCharacter = character;
                return character;
            }
            if ((_isPlayerInGarage || _isPlayerInFloorGarage ||
                _isPlayerInDavisGarage || _isPlayerInGarmentGarage ||
                _isPlayerInRuralGarage || _isPlayerInPaletoGarage) &&
                _lastGarageCharacter != (PedHash)0)
                return _lastGarageCharacter;
            return (PedHash)0;
        }

        private static string CharacterKey()
        {
            PedHash ch = GarageCharacter();
            if (ch == PedHash.Franklin) return KEY_FRANKLIN;
            if (ch == PedHash.Trevor) return KEY_TREVOR;
            if (ch == PedHash.Michael) return KEY_MICHAEL;
            return KEY_UNSUPPORTED;
        }

        private static int FindEmptySlot(
            List<StoredVehicle> list, string model = null, int modelHash = 0)
        {
            var occupied = new HashSet<int>();
            foreach (var sv in list)
                occupied.Add(sv.Slot);

            int sizeTier = model != null ? GetGarageSizeTier(model, modelHash) : 0;

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

        private static int GetGarageSizeTier(string model, int modelHash = 0)
        {
            int configuredTier = VehicleList.GetSizeTier(model);
            if (configuredTier >= 2 || string.IsNullOrWhiteSpace(model))
                return configuredTier;

            // Base-game and add-on vehicles may not be present in the GBAY
            // catalog. Use their actual bounds so a long/wide vehicle is not
            // assigned to Eclipse's tighter right row by accident.
            try
            {
                int hash = modelHash != 0 ? modelHash : Game.GenerateHash(model);
                var minArg = new OutputArgument();
                var maxArg = new OutputArgument();
                Function.Call(Hash.GET_MODEL_DIMENSIONS, hash, minArg, maxArg);
                Vector3 min = minArg.GetResult<Vector3>();
                Vector3 max = maxArg.GetResult<Vector3>();
                float width = Math.Abs(max.X - min.X);
                float length = Math.Abs(max.Y - min.Y);
                if (float.IsNaN(width) || float.IsNaN(length) ||
                    float.IsInfinity(width) || float.IsInfinity(length))
                    return configuredTier;
                if (width > 3.4f || length > 8.5f) return 2;
                if (width > 2.5f || length > 6.0f)
                    return Math.Max(1, configuredTier);
            }
            catch (Exception ex)
            {
                LogException($"GetGarageSizeTier({model})", ex);
            }
            return configuredTier;
        }

        private static void PlaceVehicleInParkingSpace(
            Vehicle vehicle, ParkingSlot slot,
            string modelName, string garageName, float maxCorrection = 1.25f)
        {
            if (vehicle == null || !vehicle.Exists()) return;
            try
            {
                Function.Call(Hash.SET_ENTITY_HEADING, vehicle, slot.Heading);
                Function.Call(Hash.SET_ENTITY_COORDS, vehicle,
                    slot.Position.X, slot.Position.Y, slot.Position.Z,
                    false, false, false, true);

                var minArg = new OutputArgument();
                var maxArg = new OutputArgument();
                Function.Call(Hash.GET_MODEL_DIMENSIONS,
                    vehicle.Model.Hash, minArg, maxArg);
                Vector3 min = minArg.GetResult<Vector3>();
                Vector3 max = maxArg.GetResult<Vector3>();
                bool usableBounds = VehiclePlacementMath.HasUsableBounds(
                    min.Z, max.Z);
                Vector3 localCenter = new Vector3(
                    (min.X + max.X) * 0.5f,
                    (min.Y + max.Y) * 0.5f,
                    0f);
                Vector3 worldCenter = vehicle.GetOffsetPosition(localCenter);
                Vector3 root = vehicle.Position;
                float correctionX = slot.Position.X - worldCenter.X;
                float correctionY = slot.Position.Y - worldCenter.Y;
                float correctionLength = (float)Math.Sqrt(
                    correctionX * correctionX + correctionY * correctionY);

                if (float.IsNaN(correctionLength) ||
                    float.IsInfinity(correctionLength)) return;
                if (correctionLength > maxCorrection && correctionLength > 0f)
                {
                    float scale = maxCorrection / correctionLength;
                    correctionX *= scale;
                    correctionY *= scale;
                }

                float floorZ = slot.FloorZ;
                string floorSource = "configured";
                if (TryProbeParkingFloor(vehicle, slot, out float probedFloorZ))
                {
                    floorZ = probedFloorZ;
                    floorSource = "raycast";
                }
                else if (!VehiclePlacementMath.IsFinite(floorZ))
                {
                    // Layouts without a measured floor keep Rockstar's native
                    // spawn root until their anchor can be audited in game.
                    floorSource = "native-root";
                }

                float rootZ = slot.Position.Z;
                string heightSource = "native-root";
                if (VehiclePlacementMath.IsFinite(floorZ)
                    && VehicleGroundingCatalog.TryGetStableRootOffset(
                        modelName, vehicle.Model.Hash, out float measuredOffset))
                {
                    rootZ = VehiclePlacementMath.CalculateMeasuredRootZ(
                        floorZ, measuredOffset, slot.Position.Z);
                    heightSource = "measured";
                }
                else if (usableBounds && VehiclePlacementMath.IsFinite(floorZ))
                {
                    rootZ = VehiclePlacementMath.CalculateRootZ(
                        floorZ, min.Z, slot.Position.Z);
                    heightSource = "bounds";
                }

                // Stored vehicle state can retain a road pitch from before it
                // entered the garage. Always level the body, then give its
                // suspension one short physics settle. Do not call the native
                // ground-placement helper in an underground interior:
                // GTA can resolve against the wrong collision layer and lift a
                // correctly measured car well above the garage floor.
                vehicle.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_ROTATION,
                    vehicle.Handle, 0f, 0f, slot.Heading, 2, true);
                Function.Call(Hash.SET_ENTITY_COORDS, vehicle,
                    root.X + correctionX, root.Y + correctionY,
                    rootZ,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, vehicle, slot.Heading);
                vehicle.IsCollisionEnabled = true;
                vehicle.IsPositionFrozen = false;
                Function.Call(Hash.SET_ENTITY_DYNAMIC, vehicle.Handle, true);
                Function.Call(Hash.ACTIVATE_PHYSICS, vehicle.Handle);
                Function.Call(Hash.SET_VEHICLE_HANDBRAKE,
                    vehicle.Handle, true);
                Script.Wait(180);
                float physicsSettledZ = vehicle.Position.Z;
                bool corrected = VehiclePlacementMath.NeedsSettledRootCorrection(
                    rootZ, physicsSettledZ);
                if (corrected)
                {
                    vehicle.IsPositionFrozen = true;
                    Function.Call(Hash.SET_ENTITY_ROTATION,
                        vehicle.Handle, 0f, 0f, slot.Heading, 2, true);
                    // SET_ENTITY_COORDS may reapply the vehicle's collision
                    // placement offset, which leaves some models roughly half
                    // a wheel above an interior floor even while frozen.  The
                    // measured catalog stores an exact entity-root offset, so
                    // the final correction must use the no-offset native.
                    Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET, vehicle,
                        root.X + correctionX, root.Y + correctionY,
                        rootZ,
                        false, false, true);
                    Function.Call(Hash.SET_ENTITY_HEADING,
                        vehicle, slot.Heading);
                    vehicle.IsCollisionEnabled = true;
                }
                vehicle.IsPositionFrozen = true;
                Log($"PlaceVehicleInParkingSpace: {garageName}/{modelName} " +
                    $"center=({correctionX:F3},{correctionY:F3}) " +
                    $"rootZ={rootZ:F3} floorZ={floorZ:F3} minZ={min.Z:F3} " +
                    $"floorSource={floorSource} heightSource={heightSource} " +
                    $"physicsZ={physicsSettledZ:F3} corrected={corrected} " +
                    $"settledZ={vehicle.Position.Z:F3} " +
                    $"pitch={vehicle.Rotation.X:F2} roll={vehicle.Rotation.Y:F2}");
            }
            catch (Exception ex)
            {
                LogException($"PlaceVehicleInParkingSpace({garageName}/{modelName})", ex);
            }
        }

        /// <summary>
        /// Transfer a parked garage vehicle back to normal gameplay. Parking
        /// applies both an entity freeze and the vehicle handbrake; clearing
        /// only one leaves the car apparently running but unable to move.
        /// Every garage exit must use this shared release path.
        /// </summary>
        private static void ReleaseGarageVehicleForDriving(
            Vehicle vehicle, Vector3 destination, float heading,
            string garageName)
        {
            if (vehicle == null || !vehicle.Exists()) return;

            vehicle.IsPositionFrozen = true;
            Function.Call(Hash.SET_FOCUS_POS_AND_VEL,
                destination.X, destination.Y, destination.Z,
                0f, 0f, 0f);
            Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                destination.X, destination.Y, destination.Z);
            Function.Call(Hash.SET_ENTITY_COORDS, vehicle,
                destination.X, destination.Y, destination.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, vehicle, heading);
            vehicle.IsCollisionEnabled = true;

            int collisionStartedAt = Game.GameTime;
            bool collisionLoaded = Function.Call<bool>(
                Hash.HAS_COLLISION_LOADED_AROUND_ENTITY, vehicle.Handle);
            while (!collisionLoaded &&
                   Game.GameTime - collisionStartedAt < 2500)
            {
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    destination.X, destination.Y, destination.Z);
                Script.Wait(50);
                collisionLoaded = Function.Call<bool>(
                    Hash.HAS_COLLISION_LOADED_AROUND_ENTITY,
                    vehicle.Handle);
            }

            Function.Call(Hash.SET_VEHICLE_HANDBRAKE, vehicle.Handle, false);
            Function.Call(Hash.SET_VEHICLE_UNDRIVEABLE, vehicle.Handle, false);
            Function.Call(Hash.SET_ENTITY_DYNAMIC, vehicle.Handle, true);
            Function.Call(Hash.SET_VEHICLE_ON_GROUND_PROPERLY, vehicle.Handle);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, vehicle.Handle, false);
            vehicle.IsPositionFrozen = false;
            Function.Call(Hash.ACTIVATE_PHYSICS, vehicle.Handle);
            Function.Call(Hash.SET_VEHICLE_ENGINE_ON,
                vehicle.Handle, true, true, false);
            vehicle.IsEngineRunning = true;
            Function.Call(Hash.CLEAR_FOCUS);

            Log($"ReleaseGarageVehicleForDriving: {garageName} " +
                $"handle={vehicle.Handle} frozen={vehicle.IsPositionFrozen} " +
                $"collisionLoaded={collisionLoaded} " +
                $"collisionWaitMs={Game.GameTime - collisionStartedAt} " +
                $"position=({vehicle.Position.X:F3},{vehicle.Position.Y:F3}," +
                $"{vehicle.Position.Z:F3})");
        }

        private static bool TryProbeParkingFloor(
            Vehicle vehicle, ParkingSlot slot, out float floorZ)
        {
            floorZ = 0f;
            try
            {
                Vector3 start = new Vector3(
                    slot.Position.X, slot.Position.Y, slot.Position.Z + 1.75f);
                Vector3 end = new Vector3(
                    slot.Position.X, slot.Position.Y, slot.Position.Z - 2.5f);
                RaycastResult result = World.Raycast(
                    start, end, IntersectFlags.Map | IntersectFlags.Objects,
                    vehicle);
                if (!result.DidHit || result.SurfaceNormal.Z < 0.55f)
                    return false;
                if (Math.Abs(result.HitPosition.Z - slot.Position.Z) > 2.25f)
                    return false;
                floorZ = result.HitPosition.Z;
                return VehiclePlacementMath.IsFinite(floorZ);
            }
            catch (Exception ex)
            {
                LogException("TryProbeParkingFloor", ex);
                return false;
            }
        }

        private static bool TryProbeInteriorFloor(
            Vector3 position, out float floorZ)
        {
            floorZ = 0f;
            try
            {
                Vector3 start = new Vector3(
                    position.X, position.Y, position.Z + 2.5f);
                Vector3 end = new Vector3(
                    position.X, position.Y, position.Z - 4.0f);
                RaycastResult result = World.Raycast(
                    start, end, IntersectFlags.Map | IntersectFlags.Objects,
                    null);
                if (!result.DidHit || result.SurfaceNormal.Z < 0.55f)
                    return false;
                floorZ = result.HitPosition.Z;
                return VehiclePlacementMath.IsFinite(floorZ);
            }
            catch (Exception ex)
            {
                LogException("TryProbeInteriorFloor", ex);
                return false;
            }
        }

        // ------------------------------------------------------------------ //
        //  JSON persistence                                                   //
        // ------------------------------------------------------------------ //

        private static void Load()
        {
            string loadPath = File.Exists(SAVE_PATH) ? SAVE_PATH : SAVE_PATH + ".bak";
            if (!File.Exists(loadPath))
                return;

            try
            {
                string json = File.ReadAllText(loadPath);
                ParseJson(json);
                MigrateModelNames();
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                {
                    Log("Load: recovered garage state from backup");
                    Save();
                }
            }
            catch (Exception ex)
            {
                LogException("Load", ex);
                string backup = SAVE_PATH + ".bak";
                if (loadPath == SAVE_PATH && File.Exists(backup))
                {
                    try
                    {
                        string json = File.ReadAllText(backup);
                        ParseJson(json);
                        Log("Load: primary save failed; recovered from backup");
                    }
                    catch (Exception backupEx)
                    {
                        LogException("Load.Backup", backupEx);
                    }
                }
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
                    if (LegacyModelAliases.TryGetValue(sv.Model, out string alias))
                    {
                        Log($"Migrate: {sv.Model} -> {alias} (known GXT alias)");
                        sv.Model = alias;
                        sv.ModelHash = Game.GenerateHash(alias);
                        changed = true;
                        continue;
                    }

                    if (validNames.Contains(sv.Model))
                    {
                        if (sv.ModelHash == 0)
                        {
                            sv.ModelHash = Game.GenerateHash(sv.Model);
                            changed = true;
                        }
                        continue; // already a valid spawn name
                    }

                    // Try to resolve: compute hash of stored name and see if
                    // it maps to a known vehicle (it won't if the GXT label
                    // differs from the spawn name)
                    int hash = Game.GenerateHash(sv.Model);
                    if (_hashToSpawnName.TryGetValue(hash, out string correctName))
                    {
                        Log($"Migrate: {sv.Model} -> {correctName} (hash match)");
                        sv.Model = correctName;
                        sv.ModelHash = Game.GenerateHash(correctName);
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

        private static int GetStoredModelHash(StoredVehicle stored)
        {
            if (stored == null) return 0;
            return stored.ModelHash != 0
                ? stored.ModelHash : Game.GenerateHash(stored.Model);
        }

        private static Model GetStoredModel(StoredVehicle stored)
        {
            return new Model(GetStoredModelHash(stored));
        }

        internal static string GetVehicleDisplayName(
            string model, int modelHash = 0)
        {
            if (!string.IsNullOrWhiteSpace(model) &&
                VehicleList.DisplayNames.TryGetValue(model, out string catalogName))
                return catalogName;
            if (!string.IsNullOrWhiteSpace(model) &&
                LegacyModelDisplayNames.TryGetValue(model, out string legacyName))
                return legacyName;
            return string.IsNullOrWhiteSpace(model) ? "Unknown vehicle" : model;
        }

        private static bool Save()
        {
            return StageOrWriteVehicleSave(SAVE_PATH, BuildJson, "Save");
        }

        private static bool StageOrWriteVehicleSave(
            string path, Func<string> buildJson, string context)
        {
            _vehicleSavesDirty = true;
            if (!_vehicleSaveCommitInProgress)
                return true;

            try
            {
                AtomicWriteText(path, buildJson());
                return true;
            }
            catch (Exception ex)
            {
                LogException(context, ex);
                return false;
            }
        }

        private static void AtomicWriteText(string path, string content)
        {
            string tmp = path + ".tmp";
            string backup = path + ".bak";
            File.WriteAllText(tmp, content);

            if (File.Exists(path))
            {
                try
                {
                    File.Replace(tmp, path, backup, true);
                    return;
                }
                catch (PlatformNotSupportedException)
                {
                    // Fall through to the portable rename sequence.
                }
                catch (IOException)
                {
                    // Some filesystems do not support replacement semantics.
                    // Fall through to the portable backup/rename sequence.
                }
            }

            if (File.Exists(path))
            {
                File.Copy(path, backup, true);
                File.Delete(path);
            }
            File.Move(tmp, path);
        }

        private static string BuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");

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
                        sb.Append($"\"model\": \"{EscapeJson(sv.Model)}\", ");
                        sb.Append($"\"modelHash\": {GetStoredModelHash(sv)}, ");
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
            var escaped = new StringBuilder(s.Length + 8);
            foreach (char value in s)
            {
                switch (value)
                {
                    case '\\': escaped.Append("\\\\"); break;
                    case '"': escaped.Append("\\\""); break;
                    case '\b': escaped.Append("\\b"); break;
                    case '\f': escaped.Append("\\f"); break;
                    case '\n': escaped.Append("\\n"); break;
                    case '\r': escaped.Append("\\r"); break;
                    case '\t': escaped.Append("\\t"); break;
                    default:
                        if (value < 0x20)
                            escaped.Append("\\u").Append(((int)value).ToString("x4"));
                        else
                            escaped.Append(value);
                        break;
                }
            }
            return escaped.ToString();
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
            var parsed = GarageSaveCodec.Parse(
                json, new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR }, SLOT_COUNT);
            foreach (var entry in parsed)
                _stored[entry.Key] = entry.Value;
        }

        // Kept temporarily for backward-comparison during the 0.4.0 parser
        // migration. Runtime loading exclusively uses GarageSaveCodec above.
        private static void LegacyParseJson(string json)
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
                                case "modelHash": sv.ModelHash = val; break;
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
            var sv = new StoredVehicle
            {
                Model = model,
                ModelHash = veh != null && veh.Exists()
                    ? veh.Model.Hash : Game.GenerateHash(model),
                Slot = slotIndex,
            };

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
                sv.ModelHash = updated.ModelHash;
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
        //  HARMONY GARAGE — five-floor oversized vehicle storage             //
        //                                                                    //
        // ================================================================== //

        private const int FLOOR_GARAGE_FLOOR_COUNT = 5;
        private const int FLOOR_GARAGE_SLOTS_PER_FLOOR = 5;
        private const int FLOOR_GARAGE_SLOT_COUNT =
            FLOOR_GARAGE_FLOOR_COUNT * FLOOR_GARAGE_SLOTS_PER_FLOOR;
        private const int FLOOR_GARAGE_ELEVATOR_OPTION_COUNT =
            FLOOR_GARAGE_FLOOR_COUNT + 1;
        private static readonly GarageDefinition THREE_FLOOR_GARAGE =
            GarageDefinitions.ThreeFloor;

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
        };
        private static readonly string[] FLOOR_GARAGE_REQUIRED_IPLS =
        {
            "ba_int_placement_ba_interior_1_dlc_int_02_ba_milo_",
        };
        private static readonly Vector3 FLOOR_GARAGE_INTERIOR_CENTER =
            new Vector3(-1505.782f, -3012.587f, -80.0f);
        private const string FLOOR_GARAGE_INTERIOR_TYPE = "ba_dlc_int_02_ba";
        private const int FLOOR_GARAGE_INTERIOR_LOAD_TIMEOUT_MS = 8000;
        private const int FLOOR_GARAGE_ENTITY_SET_CLEAR_MS = 150;
        private const int FLOOR_GARAGE_ENTITY_SET_SETTLE_MS = 350;

        // Interior ped spawn — at elevator 1 position
        // Interior-side floor anchor. The elevator interaction marker is a
        // room-volume boundary and is not safe after physics resumes.
        private static readonly Vector3 FLOOR_GARAGE_INTERIOR_PED =
            new Vector3(-1507.721f, -3011.700f, -80.2419f);
        private const float FLOOR_GARAGE_INTERIOR_PED_HEADING = 0f;

        // Elevator positions inside the garage (for floor switching + exit)
        private static readonly Vector3 FLOOR_GARAGE_ELEVATOR_1 =
            new Vector3(-1507.55f, -3014.50f, -79.24f);
        // Elevator 2 — TBD, will be set after in-game scouting
        private static readonly Vector3 FLOOR_GARAGE_ELEVATOR_2 =
            new Vector3(0f, 0f, 0f); // placeholder

        private const float ELEVATOR_INTERACT_RADIUS = 1.8f;

        // Virtual floor system — all 5 floors share the same 5 physical positions
        // within the nightclub garage interior. Only the current floor's vehicles
        // are spawned at a time; switching floors despawns/respawns.
        private static int _currentFloor; // 0 through 4
        private static int _floorGarageInteriorId;
        private static bool _elevatorMenuActive;
        private static int _elevatorMenuSelection; // floors 0-4, exit=5

        // Garage customization — 5 categories, each with 3 options
        // Players pick one option per category per floor via GBay menu
        internal static readonly string[] CUSTOM_CATEGORY_NAMES =
            { "Garage Level", "Security", "Equipment", "Workstations", "Storage Detail" };

        internal static readonly string[][] CUSTOM_OPTION_LABELS =
        {
            new[] { "Level 1", "Level 2", "Level 3", "Level 4", "Level 5" },
            new[] { "Standard", "Security Upgrade" },
            new[] { "Standard", "Equipment Upgrade" },
            new[] { "None", "Level 1 Desks", "Level 2-5 Desks" },
            new[] { "Clean", "Stocked" },
        };

        // Entity set name per [category][option]
        private static readonly string[][] CUSTOM_ENTITY_SETS =
        {
            // Keep the exact lowercase names stored in Rockstar's
            // ba_int_02_ba.ytyp rather than relying on name normalization that
            // is not consistent across the Legacy and Enhanced native paths.
            new[] { "int02_ba_floor01", "int02_ba_floor02", "int02_ba_floor03",
                "int02_ba_floor04", "int02_ba_floor05" },
            new[] { "", "int02_ba_sec_upgrade_grg" },
            new[] { "", "int02_ba_equipment_upgrade" },
            new[] { "", "int02_ba_sec_desks_l1", "int02_ba_sec_desks_l2345" },
            new[] { "", "int02_ba_clutterstuff" },
        };

        // Harmony is presented as a finished garage rather than an Online
        // business upgrade screen. These native detail packages are therefore
        // always enabled on every virtual floor.
        private static readonly string[] FLOOR_GARAGE_FIXED_ENTITY_SETS =
        {
            "int02_ba_sec_upgrade_grg",
            "int02_ba_equipment_upgrade",
            "int02_ba_truckmod",
            "int02_ba_deskpc",
            "int02_ba_sec_upgrade_strg",
            "int02_ba_sec_upgrade_desk",
            "int02_ba_sec_upgrade_desk02",
            "int02_ba_clutterstuff",
        };

        internal const int CUSTOM_CATEGORY_COUNT = 5;

        internal static int GetFloorCustomizationOptionCount(int category)
        {
            return category >= 0 && category < CUSTOM_OPTION_LABELS.Length
                ? CUSTOM_OPTION_LABELS[category].Length : 0;
        }

        // Per-floor theme choices: _floorThemes[charKey][floor] = int[5] (one choice per category)
        // Legacy theme values remain readable for save compatibility. Harmony
        // now uses a fixed, fully detailed interior on every floor.
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
                new[] { 0, 1, 1, 1, 1 }, // virtual floor 1
                new[] { 1, 1, 1, 2, 1 }, // virtual floor 2
                new[] { 2, 1, 1, 2, 1 }, // virtual floor 3
                new[] { 3, 1, 1, 2, 1 }, // virtual floor 4
                new[] { 4, 1, 1, 2, 1 }, // virtual floor 5
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
            {
                int optionCount = GetFloorCustomizationOptionCount(c);
                int choice = Math.Max(0, Math.Min(optionCount - 1, choices[c]));
                sets[c] = CUSTOM_ENTITY_SETS[c][choice];
            }
            return sets;
        }

        // Five surveyed positions in the Nightclub warehouse shell, reused by
        // each virtual floor. Vehicles face east into the aisle and remain six
        // metres apart so oversized bodies do not overlap adjacent vehicles.
        private static readonly ParkingSlot[] _floorGaragePhysicalSlots =
        {
            new ParkingSlot(-1517.0f, -3022.0f, -79.69f, 90f, -80.2422f),
            new ParkingSlot(-1517.0f, -3016.0f, -79.69f, 90f, -80.2422f),
            new ParkingSlot(-1517.0f, -3010.0f, -79.69f, 90f, -80.2422f),
            new ParkingSlot(-1517.0f, -3004.0f, -79.69f, 90f, -80.2422f),
            new ParkingSlot(-1517.0f, -2998.0f, -79.69f, 90f, -80.2422f),
        };

        // 25 logical slots across 5 virtual floors (5 per floor).
        // All floors share the same physical positions — only current floor is spawned
        internal static readonly ParkingSlot[] FloorGarageSlots =
            BuildFloorGarageSlots();

        private static ParkingSlot[] BuildFloorGarageSlots()
        {
            var slots = new ParkingSlot[FLOOR_GARAGE_SLOT_COUNT];
            for (int i = 0; i < slots.Length; i++)
                slots[i] = _floorGaragePhysicalSlots[
                    i % FLOOR_GARAGE_SLOTS_PER_FLOOR];
            return slots;
        }

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
        internal static bool IsFloorGarageInitialized => _floorGarageInitialized;
        internal static int CurrentFloor => _currentFloor;

        /// <summary>Get the theme choice for a specific floor and category.</summary>
        internal static int GetFloorThemeChoice(int floor, int category)
        {
            if (floor < 0 || floor >= FLOOR_GARAGE_FLOOR_COUNT ||
                category < 0 || category >= CUSTOM_CATEGORY_COUNT) return 0;
            string key = FloorGarageCharacterKey();
            if (!_floorThemes.TryGetValue(key, out var themes))
                return DefaultThemes()[floor][category];
            return themes[floor][category];
        }

        /// <summary>Set the theme choice for a specific floor and category. Applies live if in garage.</summary>
        internal static void SetFloorThemeChoice(int floor, int category, int option)
        {
            if (floor < 0 || floor >= FLOOR_GARAGE_FLOOR_COUNT) return;
            if (category < 0 || category >= CUSTOM_CATEGORY_COUNT) return;
            if (option < 0 || option >= GetFloorCustomizationOptionCount(category)) return;

            string key = FloorGarageCharacterKey();
            if (key == KEY_UNSUPPORTED) return;
            if (!_floorThemes.TryGetValue(key, out var themes))
            {
                themes = DefaultThemes();
                _floorThemes[key] = themes;
            }

            int oldOption = themes[floor][category];
            if (oldOption < 0 ||
                oldOption >= GetFloorCustomizationOptionCount(category))
                oldOption = 0;
            if (oldOption == option) return;

            themes[floor][category] = option;

            // If the player is currently viewing this floor, swap the entity sets live
            if (_isPlayerInFloorGarage && floor == _currentFloor)
            {
                int interior = Function.Call<int>(
                    Hash.GET_INTERIOR_AT_COORDS, -1505.782f, -3012.587f, -80.0f);
                if (interior != 0)
                {
                    ApplyFloorEntitySets(interior, floor);
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
                _floorGarageEntranceBlip.Name = "ALLIN1 Harmony Garage (Vehicle)";
                _floorGarageEntranceBlip.IsShortRange = true;

                _floorGaragePedBlip = World.CreateBlip(FLOOR_GARAGE_PED_EXIT_DEST);
                _floorGaragePedBlip.Sprite = BlipSprite.Garage;
                _floorGaragePedBlip.Color = CharacterBlipColor();
                _floorGaragePedBlip.Name = "ALLIN1 Harmony Garage (Pedestrian)";
                _floorGaragePedBlip.IsShortRange = true;

                Log("Floor Garage initialized (5-floor oversized vehicle storage)");
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
                ModelHash = Game.GenerateHash(model),
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
                            PlaceVehicleInParkingSpace(
                                veh, slot, model, "ThreeFloor", 2.0f);
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

        internal static bool RemoveFloorGarageVehicle(int listIndex)
        {
            string key = FloorGarageCharacterKey();
            if (!_floorGarageStored.TryGetValue(key, out var list))
                return false;
            if (listIndex < 0 || listIndex >= list.Count)
                return false;

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
            if (!FloorGarageSave())
            {
                list.Insert(listIndex, sv);
                Log($"RemoveFloorGarageVehicle: persistence failed; restored {sv.Model}");
                return false;
            }
            Log($"RemoveFloorGarageVehicle: {sv.Model} from slot {slotIndex}");
            return true;
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
            if (_transitionInProgress) return;

            if (_floorGarageExitCooldownFrames > 0)
            {
                _floorGarageExitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;
            if (!_isPlayerInFloorGarage && !GbayShop.TryGetCurrentCharacter(out _)) return;

            // Don't show floor garage markers while in garage (and vice versa)
            if (_isPlayerInGarage || _isPlayerInDavisGarage ||
                _isPlayerInGarmentGarage || _isPlayerInRuralGarage ||
                _isPlayerInPaletoGarage) return;

            if (!_isPlayerInFloorGarage)
            {
                if (EvaluateGarageEntry(THREE_FLOOR_GARAGE) ==
                    GarageEntryDenial.MissionActive) return;

                bool inVehicle = player.IsInVehicle();

                if (inVehicle)
                {
                    var markerColor = CharacterMarkerColor();
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        FLOOR_GARAGE_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(3f, 3f, 1.5f),
                        markerColor);

                    float dist = player.Position.DistanceTo(FLOOR_GARAGE_ENTRANCE_POS);
                    if (dist < ENTER_RADIUS + 1f)
                    {
                        Vehicle vehicle = player.CurrentVehicle;
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            THREE_FLOOR_GARAGE, vehicle);
                        if (denial != GarageEntryDenial.None)
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(THREE_FLOOR_GARAGE, denial));
                        }
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Harmony Garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterFloorGarage();
                        }
                    }
                }

                if (!inVehicle)
                {
                    var markerColor = CharacterMarkerColor();
                    World.DrawMarker(
                        GTA.MarkerType.VerticalCylinder,
                        FLOOR_GARAGE_PED_EXIT_DEST - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(2f, 2f, 1.2f),
                        markerColor);

                    float dist = player.Position.DistanceTo(FLOOR_GARAGE_PED_EXIT_DEST);
                    if (dist < ENTER_RADIUS)
                    {
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            THREE_FLOOR_GARAGE);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(THREE_FLOOR_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Harmony Garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterFloorGarage();
                        }
                    }
                }
            }
            else
            {
                bool inVehicle = player.IsInVehicle();
                EnforceFloorGarageVehicleState(player);

                // Floor indicator (always show)
                GTA.UI.Screen.ShowSubtitle(
                    $"~b~Floor {_currentFloor + 1}/{FLOOR_GARAGE_FLOOR_COUNT}", 1);

                if (inVehicle)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to leave the Harmony Garage with your vehicle.");
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
                            _elevatorMenuSelection = (_elevatorMenuSelection +
                                FLOOR_GARAGE_ELEVATOR_OPTION_COUNT - 1) %
                                FLOOR_GARAGE_ELEVATOR_OPTION_COUNT;
                        else if (Game.IsControlJustPressed(GTA.Control.FrontendDown))
                            _elevatorMenuSelection = (_elevatorMenuSelection + 1) %
                                FLOOR_GARAGE_ELEVATOR_OPTION_COUNT;
                        else if (Game.IsControlJustPressed(GTA.Control.FrontendAccept)
                              || Game.IsControlJustPressed(GTA.Control.Context))
                        {
                            _elevatorMenuActive = false;
                            if (_elevatorMenuSelection == FLOOR_GARAGE_FLOOR_COUNT)
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
            { "Floor 1", "Floor 2", "Floor 3", "Floor 4", "Floor 5", "Exit Garage" };

        /// <summary>
        /// Draws a simple centered elevator menu for five floors and the exit.
        /// The currently selected option is highlighted.
        /// </summary>
        private static void DrawElevatorMenu()
        {
            const float menuW = 0.16f;
            const float rowH = 0.035f;
            const float titleH = 0.04f;
            const float pad = 0.005f;
            const float menuX = 0.5f; // centered
            float totalH = titleH + rowH * FLOOR_GARAGE_ELEVATOR_OPTION_COUNT + pad * 2;
            float menuTop = 0.5f - totalH / 2f;

            // Background
            GbayRenderer.DrawRect(menuX, 0.5f, menuW, totalH,
                System.Drawing.Color.FromArgb(220, 15, 15, 15));

            // Title
            GbayRenderer.DrawText("ELEVATOR", menuX, menuTop + pad,
                0.38f, System.Drawing.Color.FromArgb(255, 100, 180, 255),
                font: 0, centered: true, shadow: true);

            // Options
            for (int i = 0; i < FLOOR_GARAGE_ELEVATOR_OPTION_COUNT; i++)
            {
                float rowY = menuTop + titleH + rowH * i;
                float rowCY = rowY + rowH / 2f;

                bool selected = (i == _elevatorMenuSelection);
                bool isCurrent = (i < FLOOR_GARAGE_FLOOR_COUNT && i == _currentFloor);

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
            GbayRenderer.DrawText("Up/Down: Select   Enter: Confirm   Esc: Close",
                menuX, menuTop + totalH + 0.005f,
                0.22f, System.Drawing.Color.FromArgb(180, 160, 160, 160),
                font: 0, centered: true);
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage Enter / Leave                                               //
        // ------------------------------------------------------------------ //

        private static void EnterFloorGarage()
        {
            if (RejectGarageEntry(THREE_FLOOR_GARAGE)) return;
            if (!BeginTransition("EnterFloorGarage")) return;
            try
            {
                using (ClientLog.Time("Garage", "enter_floor_garage")) EnterFloorGarageCore();
            }
            catch (Exception ex)
            {
                LogException("EnterFloorGarage", ex);
                RecoverTransition("EnterFloorGarage", FLOOR_GARAGE_PED_EXIT_DEST,
                    FLOOR_GARAGE_PED_EXIT_DEST_HEADING);
                GTA.UI.Screen.ShowSubtitle("~r~Floor garage entry failed safely. See ALLIN1_gbay.log.", 4000);
            }
            finally
            {
                EndTransition("EnterFloorGarage");
            }
        }

        private static void EnterFloorGarageCore()
        {
            Log("EnterFloorGarage: START");
            Ped player = Game.Player.Character;
            Vehicle rideInToDelete = null;
            string storedConfirmation = null;
            StoredVehicle storedDuringEntry = null;
            List<StoredVehicle> storedListDuringEntry = null;

            // This garage always opens on floor one. Set the virtual floor
            // before loading its entity sets so a prior visit cannot apply the
            // previous floor's customization during interior initialization.
            _currentFloor = 0;

            // Drive-in: store the vehicle
            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
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

                    if (RejectGarageEntry(
                        THREE_FLOOR_GARAGE, rideIn, modelName, modelHash)) return;

                    string hKey = FloorGarageCharacterKey();
                    if (!_floorGarageStored.TryGetValue(hKey, out var storedList))
                    {
                        storedList = new List<StoredVehicle>();
                        _floorGarageStored[hKey] = storedList;
                    }

                    if (storedList.Count >= FLOOR_GARAGE_SLOT_COUNT)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~The Harmony Garage is full.~w~ " +
                            $"({storedList.Count}/{FLOOR_GARAGE_SLOT_COUNT} spaces used)", 3000);
                        return;
                    }

                    int slotIndex = FindEmptyFloorGarageSlot(storedList);
                    if (slotIndex < 0)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The Harmony Garage is full; no spaces are available.", 3000);
                        return;
                    }

                    StoredVehicle sv = CaptureVehicleState(rideIn, modelName, slotIndex);
                    storedList.Add(sv);
                    if (!FloorGarageSave())
                    {
                        storedList.Remove(sv);
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The vehicle could not be saved; it was left outside.", 3000);
                        return;
                    }
                    storedDuringEntry = sv;
                    storedListDuringEntry = storedList;

                    string displayName = VehicleList.DisplayNames.ContainsKey(modelName)
                        ? VehicleList.DisplayNames[modelName] : modelName;
                    int floor = slotIndex / FLOOR_GARAGE_SLOTS_PER_FLOOR + 1;
                    int spotOnFloor = slotIndex % FLOOR_GARAGE_SLOTS_PER_FLOOR + 1;
                    storedConfirmation =
                        $"~g~{displayName}~w~ stored in the Harmony Garage " +
                        $"(floor {floor}, space {spotOnFloor}).";
                    Log($"EnterFloorGarage: stored drive-in vehicle {modelName} -> slot {slotIndex} (floor {floor})");

                    rideIn.IsPersistent = true;
                    rideInToDelete = rideIn;
                }
            }

            Log("EnterFloorGarage: loading IPL");
            // Load the nightclub garage IPL
            if (!LoadFloorGarageInterior())
            {
                if (storedDuringEntry != null && storedListDuringEntry != null)
                {
                    storedListDuringEntry.Remove(storedDuringEntry);
                    if (!FloorGarageSave())
                        Log("EnterFloorGarage: WARNING - entry rollback save failed");
                    Log("EnterFloorGarage: rolled back drive-in storage after interior load failure");
                }
                GTA.UI.Screen.ShowSubtitle(
                    "~y~The Harmony Garage is unavailable during the current game transition.",
                    3500);
                return;
            }
            Log("EnterFloorGarage: IPL loaded");

            // Clear existing handles
            for (int i = 0; i < FLOOR_GARAGE_SLOT_COUNT; i++)
            {
                if (_floorGarageHandles[i] != null && _floorGarageHandles[i].Exists())
                    _floorGarageHandles[i].Delete();
                _floorGarageHandles[i] = null;
            }

            _isPlayerInFloorGarage = true; // set early to block re-entry during fade
            Log("EnterFloorGarage: flag set, starting fade out");

            BeginGarageBlackTransition("EnterFloorGarage");
            Log("EnterFloorGarage: fade done, teleporting");

            // Freeze and teleport player
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                FLOOR_GARAGE_INTERIOR_PED.X, FLOOR_GARAGE_INTERIOR_PED.Y, FLOOR_GARAGE_INTERIOR_PED.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player, FLOOR_GARAGE_INTERIOR_PED_HEADING);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, true);
            if (rideInToDelete != null && rideInToDelete.Exists())
            {
                rideInToDelete.Delete();
                Log("EnterFloorGarage: deleted drive-in vehicle after player extraction");
            }

            // The standalone MLO can resolve before the player is attached to
            // one of its rooms. Reapply only after attachment so Enhanced
            // instantiates the selected floor and detail drawables rather
            // than merely remembering their active flags on a bare shell.
            int attachedInterior = WaitForFloorGaragePlayerInterior(
                player, _floorGarageInteriorId, 3500);
            if (attachedInterior == 0)
                throw new InvalidOperationException(
                    "Player did not attach to the loaded Harmony interior room");

            bool setsReady = ApplyFloorEntitySets(
                attachedInterior, _currentFloor);
            Log($"EnterFloorGarage: post-teleport interior={attachedInterior} " +
                $"setsReady={setsReady}");
            if (!setsReady)
                throw new InvalidOperationException(
                    "Harmony interior entity sets did not finish loading");

            Log("EnterFloorGarage: teleported, spawning vehicles");

            // Spawn vehicles for the current floor only
            SpawnFloorGarageVehicles();
            Log("EnterFloorGarage: vehicles spawned, unfreezing");

            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            player.IsPositionFrozen = false;

            Log("EnterFloorGarage: waiting for destination readiness");
            CompleteGarageBlackTransition(
                "EnterFloorGarage", player, null,
                () => Function.Call<bool>(Hash.IS_INTERIOR_READY,
                        _floorGarageInteriorId) &&
                    IsFloorGaragePlayerAttached(
                        player, _floorGarageInteriorId, out _),
                _floorGarageHandles);

            if (!string.IsNullOrEmpty(storedConfirmation))
                GTA.UI.Screen.ShowSubtitle(storedConfirmation, 4000);

            Log($"EnterFloorGarage: COMPLETE, character={FloorGarageCharacterKey()}");
        }

        private static void LeaveFloorGarage()
        {
            if (!BeginTransition("LeaveFloorGarage")) return;
            try
            {
                using (ClientLog.Time("Garage", "leave_floor_garage")) LeaveFloorGarageCore();
            }
            catch (Exception ex)
            {
                LogException("LeaveFloorGarage", ex);
                RecoverTransition("LeaveFloorGarage", FLOOR_GARAGE_PED_EXIT_DEST,
                    FLOOR_GARAGE_PED_EXIT_DEST_HEADING);
                GTA.UI.Screen.ShowSubtitle("~r~Floor garage exit recovered safely. See ALLIN1_gbay.log.", 4000);
            }
            finally
            {
                EndTransition("LeaveFloorGarage");
            }
        }

        private static void LeaveFloorGarageCore()
        {
            Log("LeaveFloorGarage: START");
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

            Log($"LeaveFloorGarage: player in vehicle={playerVehicle != null}, cleaning vehicles");
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

            Log("LeaveFloorGarage: vehicles cleaned, starting fade out");
            BeginGarageBlackTransition("LeaveFloorGarage");
            Log("LeaveFloorGarage: fade done, teleporting");

            player.IsPositionFrozen = true;
            if (playerVehicle != null)
                playerVehicle.IsPositionFrozen = true;
            UnloadFloorGarageInterior();
            Script.Wait(250);

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

                playerVehicle.IsPersistent = true;
                ReleaseGarageVehicleForDriving(playerVehicle,
                    FLOOR_GARAGE_ENTRANCE_POS, 270f, "Harmony");

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

            Log("LeaveFloorGarage: waiting for exterior readiness");
            CompleteGarageBlackTransition(
                "LeaveFloorGarage", player, playerVehicle,
                () => Function.Call<int>(
                    Hash.GET_INTERIOR_FROM_ENTITY, player) == 0);
            Log("LeaveFloorGarage: COMPLETE");
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage Helpers                                                     //
        // ------------------------------------------------------------------ //

        private static string FloorGarageCharacterKey()
        {
            PedHash ch = GarageCharacter();
            if (ch == PedHash.Franklin) return KEY_FRANKLIN_FG;
            if (ch == PedHash.Trevor) return KEY_TREVOR_FG;
            if (ch == PedHash.Michael) return KEY_MICHAEL_FG;
            return KEY_UNSUPPORTED;
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
        /// Activate one native garage level plus the complete finished detail
        /// package. The desk sets are mutually exclusive between level 1 and
        /// levels 2-5, so only the matching variant is enabled.
        /// </summary>
        private static bool ApplyFloorEntitySets(int interior, int floor)
        {
            if (interior == 0 || floor < 0 || floor >= FLOOR_GARAGE_FLOOR_COUNT)
                return false;

            string floorSet = CUSTOM_ENTITY_SETS[0][floor];
            string deskSet = floor == 0
                ? "int02_ba_sec_desks_l1"
                : "int02_ba_sec_desks_l2345";

            // A single refresh after both deactivation and activation can keep
            // the old MLO drawable instantiated on Enhanced. Rebuild in two
            // phases so the previous floor is physically removed before the
            // target floor is introduced.
            for (int option = 0; option < FLOOR_GARAGE_FLOOR_COUNT; option++)
                Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior,
                    CUSTOM_ENTITY_SETS[0][option]);
            Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior,
                "int02_ba_sec_desks_l1");
            Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior,
                "int02_ba_sec_desks_l2345");
            Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior,
                "int02_ba_garage_blocker");
            Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior,
                "int02_ba_storage_blocker");
            Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior,
                "int02_ba_fanblocker01");
            Function.Call(Hash.REFRESH_INTERIOR, interior);
            int clearStartedAt = Game.GameTime;
            while (Game.GameTime - clearStartedAt < FLOOR_GARAGE_ENTITY_SET_CLEAR_MS)
                Script.Wait(0);

            foreach (string set in FLOOR_GARAGE_FIXED_ENTITY_SETS)
                Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, set);
            Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, deskSet);
            Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, floorSet);
            Function.Call(Hash.REFRESH_INTERIOR, interior);
            int settleStartedAt = Game.GameTime;
            while (Game.GameTime - settleStartedAt < FLOOR_GARAGE_ENTITY_SET_SETTLE_MS)
                Script.Wait(0);

            bool valid = ValidateFloorEntitySets(interior, floor, out string detail);
            Log($"ApplyFloorEntitySets: interior={interior} floor={floor + 1} " +
                $"set={floorSet} valid={valid} {detail}");
            return valid;
        }

        private static bool ValidateFloorEntitySets(
            int interior, int floor, out string detail)
        {
            if (interior == 0 || floor < 0 || floor >= FLOOR_GARAGE_FLOOR_COUNT)
            {
                detail = "invalid interior or floor";
                return false;
            }

            var floorStates = new bool[FLOOR_GARAGE_FLOOR_COUNT];
            bool exclusive = true;
            for (int option = 0; option < FLOOR_GARAGE_FLOOR_COUNT; option++)
            {
                floorStates[option] = Function.Call<bool>(
                    (Hash)0x35F7DD45E8C0A16D,
                    interior, CUSTOM_ENTITY_SETS[0][option]);
                if (floorStates[option] != (option == floor))
                    exclusive = false;
            }

            var missingFixed = new List<string>();
            foreach (string set in FLOOR_GARAGE_FIXED_ENTITY_SETS)
                if (!Function.Call<bool>((Hash)0x35F7DD45E8C0A16D,
                    interior, set))
                    missingFixed.Add(set);

            bool desksL1 = Function.Call<bool>((Hash)0x35F7DD45E8C0A16D,
                interior, "int02_ba_sec_desks_l1");
            bool desksOther = Function.Call<bool>((Hash)0x35F7DD45E8C0A16D,
                interior, "int02_ba_sec_desks_l2345");
            bool deskValid = floor == 0
                ? desksL1 && !desksOther
                : !desksL1 && desksOther;

            detail = $"floors=[{string.Join(",", floorStates)}] " +
                $"exclusive={exclusive} fixedMissing=[{string.Join(",", missingFixed)}] " +
                $"desks=[{desksL1},{desksOther}]";
            return exclusive && missingFixed.Count == 0 && deskValid;
        }

        private static int ResolveFloorGarageInterior()
        {
            int interior = Function.Call<int>(
                Hash.GET_INTERIOR_AT_COORDS_WITH_TYPE,
                FLOOR_GARAGE_INTERIOR_CENTER.X,
                FLOOR_GARAGE_INTERIOR_CENTER.Y,
                FLOOR_GARAGE_INTERIOR_CENTER.Z,
                FLOOR_GARAGE_INTERIOR_TYPE);
            if (interior == 0 || !Function.Call<bool>(
                Hash.IS_VALID_INTERIOR, interior))
                return 0;
            return interior;
        }

        private static void PrimeFloorGarageInterior(int interior)
        {
            // Enhanced requires the complete lifecycle. Pinning an already
            // enabled interior can expose its shell while leaving the selected
            // floor and detail drawables uninstantiated.
            Function.Call(Hash.DISABLE_INTERIOR, interior, true);
            Function.Call(Hash.PIN_INTERIOR_IN_MEMORY, interior);
            Function.Call(Hash.DISABLE_INTERIOR, interior, false);
            Function.Call(Hash.SET_INTERIOR_ACTIVE, interior, true);
            if (Function.Call<bool>(Hash.IS_INTERIOR_CAPPED, interior))
                Function.Call(Hash.CAP_INTERIOR, interior, false);
            Function.Call(Hash.REFRESH_INTERIOR, interior);
        }

        private static void KeepFloorGarageInteriorActive(int interior)
        {
            Function.Call(Hash.PIN_INTERIOR_IN_MEMORY, interior);
            Function.Call(Hash.DISABLE_INTERIOR, interior, false);
            Function.Call(Hash.SET_INTERIOR_ACTIVE, interior, true);
            if (Function.Call<bool>(Hash.IS_INTERIOR_CAPPED, interior))
                Function.Call(Hash.CAP_INTERIOR, interior, false);
        }

        private static bool IsFloorGaragePlayerAttached(
            Ped player, int expectedInterior, out string detail)
        {
            int playerInterior = Function.Call<int>(
                Hash.GET_INTERIOR_FROM_ENTITY, player);
            int roomKey = Function.Call<int>(Hash.GET_ROOM_KEY_FROM_ENTITY, player);
            int viewportRoomKey = Function.Call<int>(
                Hash.GET_ROOM_KEY_FOR_GAME_VIEWPORT);
            Vector3 position = player.Position;
            bool collisionOutside = Function.Call<bool>(
                Hash.IS_COLLISION_MARKED_OUTSIDE,
                position.X, position.Y, position.Z);
            bool attached = GarageRoomAttachmentPolicy.IsAttached(
                expectedInterior, playerInterior, roomKey, viewportRoomKey);
            detail = $"expectedInterior={expectedInterior} " +
                $"playerInterior={playerInterior} roomKey={roomKey} " +
                $"viewportRoomKey={viewportRoomKey} " +
                $"collisionOutside={collisionOutside} pos={position}";
            return attached;
        }

        private static int WaitForFloorGaragePlayerInterior(
            Ped player, int expectedInterior, int timeoutMs)
        {
            int startedAt = Game.GameTime;
            while (Game.GameTime - startedAt < timeoutMs)
            {
                Vector3 position = player.Position;
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    position.X, position.Y, position.Z);
                if (IsFloorGaragePlayerAttached(
                    player, expectedInterior, out string detail))
                {
                    Log("WaitForFloorGaragePlayerInterior: attached " + detail);
                    return expectedInterior;
                }
                Script.Wait(50);
            }
            IsFloorGaragePlayerAttached(
                player, expectedInterior, out string finalDetail);
            Log("WaitForFloorGaragePlayerInterior: FAILED " + finalDetail);
            return 0;
        }

        /// <summary>
        /// Load the nightclub garage IPL and configure interior entity sets.
        /// </summary>
        private static bool LoadFloorGarageInterior()
        {
            // Recheck immediately before loading the local map asset. A
            // cutscene can begin after the proximity prompt was evaluated.
            if (IsUnsafeGarageTransitionActive())
            {
                Log("LoadFloorGarageInterior: blocked during active game transition");
                return false;
            }

            if (!StandaloneMapPack.TryActivate(FLOOR_GARAGE_REQUIRED_IPLS, 1500))
            {
                Log("LoadFloorGarageInterior: standalone map unavailable");
                return false;
            }

            bool focusSet = false;
            bool priorityModeSet = false;
            try
            {
                Function.Call(Hash.SET_INSTANCE_PRIORITY_MODE, true);
                priorityModeSet = true;
                Function.Call(Hash.SET_FOCUS_POS_AND_VEL,
                    FLOOR_GARAGE_INTERIOR_CENTER.X,
                    FLOOR_GARAGE_INTERIOR_CENTER.Y,
                    FLOOR_GARAGE_INTERIOR_CENTER.Z, 0f, 0f, 0f);
                focusSet = true;

                int startedAt = Game.GameTime;
                int interior = 0;
                bool interiorReady = false;
                bool primaryIplActive = false;
                bool floorCollisionReady = false;
                bool lifecyclePrimed = false;
                float floorZ = 0f;
                while (Game.GameTime - startedAt < FLOOR_GARAGE_INTERIOR_LOAD_TIMEOUT_MS)
                {
                    foreach (string ipl in FLOOR_GARAGE_IPLS)
                        Function.Call(Hash.REQUEST_IPL, ipl);
                    Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                        FLOOR_GARAGE_INTERIOR_CENTER.X,
                        FLOOR_GARAGE_INTERIOR_CENTER.Y,
                        FLOOR_GARAGE_INTERIOR_CENTER.Z);

                    int resolvedInterior = ResolveFloorGarageInterior();
                    if (resolvedInterior != interior)
                    {
                        interior = resolvedInterior;
                        lifecyclePrimed = false;
                    }
                    if (interior != 0)
                    {
                        if (!lifecyclePrimed)
                        {
                            PrimeFloorGarageInterior(interior);
                            lifecyclePrimed = true;
                            Log($"LoadFloorGarageInterior: primed typed interior={interior} " +
                                $"type={FLOOR_GARAGE_INTERIOR_TYPE}");
                        }
                        else
                            KeepFloorGarageInteriorActive(interior);
                        interiorReady = Function.Call<bool>(
                            Hash.IS_INTERIOR_READY, interior);
                    }
                    else interiorReady = false;

                    primaryIplActive = true;
                    foreach (string ipl in FLOOR_GARAGE_REQUIRED_IPLS)
                        primaryIplActive &= Function.Call<bool>(
                            Hash.IS_IPL_ACTIVE, ipl);
                    floorCollisionReady = TryProbeInteriorFloor(
                        FLOOR_GARAGE_INTERIOR_PED, out floorZ);
                    if (interior != 0 && primaryIplActive &&
                        interiorReady && floorCollisionReady)
                    {
                        Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET,
                            interior, "int02_ba_garage_blocker");
                        Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET,
                            interior, "int02_ba_storage_blocker");
                        Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET,
                            interior, "int02_ba_fanblocker01");
                        if (!ApplyFloorEntitySets(interior, _currentFloor))
                        {
                            Log("LoadFloorGarageInterior: entity-set validation failed; retrying");
                            Script.Wait(100);
                            continue;
                        }
                        _floorGarageInteriorId = interior;
                        Log($"LoadFloorGarageInterior: interior={interior} ready " +
                            $"readySignal={interiorReady} " +
                            $"primaryIplActive={primaryIplActive} " +
                            $"floorCollision=True floorZ={floorZ:F3} " +
                            $"elapsed={Game.GameTime - startedAt}ms");
                        return true;
                    }
                    Script.Wait(100);
                }

                Log($"LoadFloorGarageInterior: FAILED interior={interior} " +
                    $"interiorReady={interiorReady} " +
                    $"primaryIplActive={primaryIplActive} " +
                    $"floorCollision={floorCollisionReady}");
            }
            catch (Exception ex)
            {
                LogException("LoadFloorGarageInterior", ex);
            }
            finally
            {
                if (focusSet) Function.Call(Hash.CLEAR_FOCUS);
                if (priorityModeSet)
                    Function.Call(Hash.SET_INSTANCE_PRIORITY_MODE, false);
            }
            UnloadFloorGarageInterior();
            return false;
        }

        private static void UnloadFloorGarageInterior()
        {
            int interior = _floorGarageInteriorId;
            _floorGarageInteriorId = 0;
            if (interior != 0)
            {
                Function.Call(Hash.SET_INTERIOR_ACTIVE, interior, false);
                Function.Call(Hash.UNPIN_INTERIOR, interior);
            }
            foreach (string ipl in FLOOR_GARAGE_IPLS)
                Function.Call(Hash.REMOVE_IPL, ipl);
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
                var m = GetStoredModel(sv);
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
                    var model = GetStoredModel(sv);
                    Vehicle veh = World.CreateVehicle(model, slot.Position, slot.Heading);
                    model.MarkAsNoLongerNeeded();

                    if (veh != null)
                    {
                        ApplyVehicleState(veh, sv);
                        veh.IsPersistent = true;
                        veh.IsEngineRunning = false;
                        PlaceVehicleInParkingSpace(
                            veh, slot, sv.Model, "ThreeFloor", 2.0f);
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
            if (newFloor < 0 || newFloor >= FLOOR_GARAGE_FLOOR_COUNT) return;
            if (newFloor == _currentFloor) return;

            Ped player = Game.Player.Character;
            if (player.IsInVehicle())
            {
                GTA.UI.Screen.ShowSubtitle("~r~Exit your vehicle before switching floors.", 2000);
                return;
            }

            BeginGarageBlackTransition("SwitchFloorGarageFloor");
            player.IsPositionFrozen = true;
            int previousFloor = _currentFloor;
            int interior = 0;
            try
            {
                // Save state of vehicles on the current floor before changing
                // the virtual slot window.
                FloorGarageUpdateStoredFromLive();
                _currentFloor = newFloor;

                // Switch the native garage level while retaining all detail
                // sets. Apply waits for the MLO render proxy to rebuild before
                // vehicles are introduced on the target floor.
                interior = _floorGarageInteriorId != 0
                    ? _floorGarageInteriorId
                    : ResolveFloorGarageInterior();
                if (interior == 0 || !Function.Call<bool>(
                    Hash.IS_INTERIOR_READY, interior))
                    throw new InvalidOperationException(
                        $"Harmony interior unavailable for floor {newFloor + 1}");
                KeepFloorGarageInteriorActive(interior);
                if (!ApplyFloorEntitySets(interior, _currentFloor))
                    throw new InvalidOperationException(
                        $"Harmony entity sets failed for floor {newFloor + 1}");

                // Floor entity-set replacement can evict a ped standing on
                // the elevator boundary. Re-enter through the safe interior
                // anchor while the screen remains black.
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    FLOOR_GARAGE_INTERIOR_PED.X,
                    FLOOR_GARAGE_INTERIOR_PED.Y,
                    FLOOR_GARAGE_INTERIOR_PED.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING,
                    player, FLOOR_GARAGE_INTERIOR_PED_HEADING);
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    FLOOR_GARAGE_INTERIOR_CENTER.X,
                    FLOOR_GARAGE_INTERIOR_CENTER.Y,
                    FLOOR_GARAGE_INTERIOR_CENTER.Z);
                SpawnFloorGarageVehicles();
                player.IsPositionFrozen = false;
                Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
                CompleteGarageBlackTransition(
                    "SwitchFloorGarageFloor", player, null,
                    () => Function.Call<bool>(Hash.IS_INTERIOR_READY, interior) &&
                        IsFloorGaragePlayerAttached(
                            player, interior, out _),
                    _floorGarageHandles);

                GTA.UI.Screen.ShowSubtitle(
                    $"~b~Floor {_currentFloor + 1} of {FLOOR_GARAGE_FLOOR_COUNT}", 2000);
                Log($"SwitchFloorGarageFloor: switched to floor {_currentFloor + 1}");
            }
            catch (Exception ex)
            {
                LogException("SwitchFloorGarageFloor", ex);
                _currentFloor = previousFloor;
                if (interior != 0)
                    ApplyFloorEntitySets(interior, previousFloor);
                RecoverTransition("SwitchFloorGarageFloor",
                    FLOOR_GARAGE_PED_EXIT_DEST,
                    FLOOR_GARAGE_PED_EXIT_DEST_HEADING);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The elevator recovered safely outside the garage.", 3000);
            }
            finally
            {
                player.IsPositionFrozen = false;
                Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            }
        }

        // ------------------------------------------------------------------ //
        //  Floor Garage JSON Persistence                                            //
        // ------------------------------------------------------------------ //

        private static void FloorGarageLoad()
        {
            string loadPath = File.Exists(FLOOR_GARAGE_SAVE_PATH)
                ? FLOOR_GARAGE_SAVE_PATH : FLOOR_GARAGE_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath))
                return;
            try
            {
                string json = File.ReadAllText(loadPath);
                FloorGarageParseJson(json);
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                {
                    Log("FloorGarageLoad: recovered from backup");
                    FloorGarageSave();
                }
            }
            catch (Exception ex)
            {
                LogException("FloorGarageLoad", ex);
                string backup = FLOOR_GARAGE_SAVE_PATH + ".bak";
                if (loadPath == FLOOR_GARAGE_SAVE_PATH && File.Exists(backup))
                {
                    try
                    {
                        string json = File.ReadAllText(backup);
                        FloorGarageParseJson(json);
                        Log("FloorGarageLoad: primary save failed; recovered from backup");
                    }
                    catch (Exception backupEx)
                    {
                        LogException("FloorGarageLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool FloorGarageSave()
        {
            return StageOrWriteVehicleSave(
                FLOOR_GARAGE_SAVE_PATH, FloorGarageBuildJson,
                "FloorGarageSave");
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
                // Legacy customization data is still accepted for migration.
                string[] keys = { KEY_MICHAEL_FG, KEY_FRANKLIN_FG, KEY_TREVOR_FG };
                foreach (string key in keys)
                {
                    int keyIdx = json.IndexOf($"\"{key}\"");
                    if (keyIdx < 0) continue;
                    int arrStart = json.IndexOf('[', keyIdx);
                    if (arrStart < 0) continue;

                    int[][] themes = DefaultThemes();
                    int pos = arrStart + 1; // skip outer [
                    for (int f = 0; f < FLOOR_GARAGE_FLOOR_COUNT; f++)
                    {
                        int innerStart = json.IndexOf('[', pos);
                        if (innerStart < 0) break;
                        int innerEnd = json.IndexOf(']', innerStart);
                        if (innerEnd < 0) break;
                        string inner = json.Substring(innerStart + 1, innerEnd - innerStart - 1);
                        string[] parts = inner.Split(',');
                        for (int c = 0; c < Math.Min(parts.Length, CUSTOM_CATEGORY_COUNT); c++)
                        {
                            if (int.TryParse(parts[c].Trim(), out int val) && val >= 0 &&
                                val < GetFloorCustomizationOptionCount(c))
                                themes[f][c] = val;
                        }
                        pos = innerEnd + 1;
                    }
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
            _garageCustomizationSavesDirty = true;
        }

        private static bool FloorGarageThemesWrite()
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
                    for (int f = 0; f < FLOOR_GARAGE_FLOOR_COUNT; f++)
                    {
                        sb.Append($"[{string.Join(",", themes[f])}]");
                        if (f < FLOOR_GARAGE_FLOOR_COUNT - 1) sb.Append(", ");
                    }
                    sb.Append("]");
                    if (k < keys.Length - 1) sb.AppendLine(",");
                    else sb.AppendLine();
                }
                sb.AppendLine("}");

                AtomicWriteText(FLOOR_GARAGE_THEMES_PATH, sb.ToString());
                return true;
            }
            catch (Exception ex)
            {
                LogException("FloorGarageThemesSave", ex);
                return false;
            }
        }

        private static string FloorGarageBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");

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
                        sb.Append($"\"model\": \"{EscapeJson(sv.Model)}\", ");
                        sb.Append($"\"modelHash\": {GetStoredModelHash(sv)}, ");
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
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL_FG, KEY_FRANKLIN_FG, KEY_TREVOR_FG },
                FLOOR_GARAGE_SLOT_COUNT);
            foreach (var entry in parsed)
                _floorGarageStored[entry.Key] = entry.Value;
        }

        private static void LegacyFloorGarageParseJson(string json)
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
                sv.ModelHash = updated.ModelHash;
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
