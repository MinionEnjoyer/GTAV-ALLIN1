// GarageManager.Rural.cs -- Grapeseed six-car garage.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal static partial class GarageManager
    {
        private const int RURAL_SLOT_COUNT = 6;
        private static readonly GarageDefinition RURAL_GARAGE =
            GarageDefinitions.Rural;

        internal static readonly Vector3 RURAL_VEHICLE_ENTRANCE_POS =
            new Vector3(2551.4610f, 4674.3250f, 33.9819f);
        private const float RURAL_VEHICLE_ENTRANCE_HEADING = 0f;
        internal static readonly Vector3 RURAL_PED_ENTRANCE_POS =
            new Vector3(2553.4590f, 4650.6360f, 34.0768f);
        private const float RURAL_PED_ENTRANCE_HEADING = 90f;

        // Native pedestrian exit at the six-car garage's internal door.
        private static readonly Vector3 RURAL_INTERIOR_PED =
            new Vector3(206.3603f, -999.0687f, -99.0000f);
        private const float RURAL_INTERIOR_PED_HEADING = 90f;
        private const float RURAL_FLOOR_Z = -100.0000f;
        private static readonly Vector3 RURAL_INTERIOR_CENTER =
            new Vector3(199.9716f, -999.6678f, -99.0000f);
        private const int RURAL_INTERIOR_LOAD_TIMEOUT_MS = 6000;
        private const int RURAL_INTERIOR_FALLBACK_SETTLE_MS = 1000;

        private static readonly string[] RURAL_IPLS =
        {
            // v_garagem is the interior type/name, not a requestable IPL.
            // Enhanced's six-car shell is this explicit High Life MILO.
            "hw1_blimp_interior_v_garagem_milo_",
        };

        // Native v_garagem six-car layout. The shared garage placement helper
        // applies measured per-model ground offsets after each spawn.
        internal static readonly ParkingSlot[] RuralSlots =
        {
            new ParkingSlot(193.60f, -1004.60f, -99.56f, 90f, RURAL_FLOOR_Z),
            new ParkingSlot(193.60f, -1000.40f, -99.56f, 90f, RURAL_FLOOR_Z),
            new ParkingSlot(193.60f, -996.20f, -99.56f, 90f, RURAL_FLOOR_Z),
            new ParkingSlot(202.70f, -1004.60f, -99.56f, 270f, RURAL_FLOOR_Z),
            new ParkingSlot(202.70f, -1000.40f, -99.56f, 270f, RURAL_FLOOR_Z),
            new ParkingSlot(202.70f, -996.20f, -99.56f, 270f, RURAL_FLOOR_Z),
        };

        private static readonly string RURAL_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_rural_garage.json");
        private static readonly Dictionary<string, List<StoredVehicle>> _ruralStored =
            new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL, new List<StoredVehicle>() },
                { KEY_FRANKLIN, new List<StoredVehicle>() },
                { KEY_TREVOR, new List<StoredVehicle>() },
            };
        private static readonly Vehicle[] _ruralHandles =
            new Vehicle[RURAL_SLOT_COUNT];
        private static bool _isPlayerInRuralGarage;
        private static bool _ruralInitialized;
        private static int _ruralExitCooldownFrames;
        private static Blip _ruralVehicleBlip;
        private static Blip _ruralPedBlip;

        internal static bool IsPlayerInRuralGarage => _isPlayerInRuralGarage;
        internal static bool IsRuralGarageInitialized => _ruralInitialized;

        internal static void InitializeRuralGarage()
        {
            if (_ruralInitialized) return;
            try
            {
                RuralLoad();
                _ruralVehicleBlip = World.CreateBlip(RURAL_VEHICLE_ENTRANCE_POS);
                _ruralVehicleBlip.Sprite = BlipSprite.Garage;
                _ruralVehicleBlip.Color = CharacterBlipColor();
                _ruralVehicleBlip.Name = "ALLIN1 Grapeseed Garage (Vehicle)";
                _ruralVehicleBlip.IsShortRange = true;

                _ruralPedBlip = World.CreateBlip(RURAL_PED_ENTRANCE_POS);
                _ruralPedBlip.Sprite = BlipSprite.Garage;
                _ruralPedBlip.Color = CharacterBlipColor();
                _ruralPedBlip.Name = "ALLIN1 Grapeseed Garage (Pedestrian)";
                _ruralPedBlip.IsShortRange = true;

                int count = 0;
                foreach (List<StoredVehicle> list in _ruralStored.Values)
                    count += list.Count;
                Log($"Grapeseed Garage initialized ({count} stored vehicles)");
            }
            catch (Exception ex)
            {
                LogException("InitializeRuralGarage", ex);
            }
            _ruralInitialized = true;
        }

        internal static int GetRuralGarageUsedSlots()
        {
            return _ruralStored.TryGetValue(CharacterKey(), out var list)
                ? list.Count : 0;
        }

        internal static int GetRuralGarageCapacity() => RURAL_SLOT_COUNT;

        internal static List<StoredVehicle> GetRuralGarageStoredVehicles()
        {
            return _ruralStored.TryGetValue(CharacterKey(), out var list)
                ? list : new List<StoredVehicle>();
        }

        internal static bool DeliverToRuralGarage(
            string model, int color1, int color2)
        {
            if (GetGarageSizeTier(model) >= 2) return false;
            if (!_ruralStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (list.Count >= RURAL_SLOT_COUNT) return false;
            int slotIndex = FindEmptyRuralSlot(list);
            if (slotIndex < 0) return false;

            var stored = new StoredVehicle
            {
                Model = model,
                ModelHash = Game.GenerateHash(model),
                Slot = slotIndex,
                Color1 = color1,
                Color2 = color2,
            };
            list.Add(stored);
            if (_isPlayerInRuralGarage) SpawnRuralVehicle(stored);
            if (!RuralSave())
            {
                list.Remove(stored);
                DeleteRuralHandle(slotIndex);
                return false;
            }
            Log($"DeliverToRuralGarage: {model} -> slot {slotIndex}");
            return true;
        }

        internal static bool RemoveRuralGarageVehicle(int listIndex)
        {
            if (!_ruralStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (listIndex < 0 || listIndex >= list.Count) return false;
            StoredVehicle stored = list[listIndex];
            DeleteRuralHandle(stored.Slot);
            list.RemoveAt(listIndex);
            if (!RuralSave())
            {
                list.Insert(listIndex, stored);
                return false;
            }
            Log($"RemoveRuralGarageVehicle: {stored.Model} from slot {stored.Slot}");
            return true;
        }

        internal static void OnRuralGarageTick()
        {
            if (!_ruralInitialized || _transitionInProgress) return;
            if (_isPlayerInGarage || _isPlayerInFloorGarage || _isPlayerInDavisGarage ||
                _isPlayerInGarmentGarage || _isPlayerInPaletoGarage)
                return;
            if (_ruralExitCooldownFrames > 0)
            {
                _ruralExitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;
            if (!_isPlayerInRuralGarage && !GbayShop.TryGetCurrentCharacter(out _))
                return;
            Color markerColor = CharacterMarkerColor();

            if (!_isPlayerInRuralGarage)
            {
                if (EvaluateGarageEntry(RURAL_GARAGE) ==
                    GarageEntryDenial.MissionActive) return;
                if (player.IsInVehicle())
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        RURAL_VEHICLE_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(2.5f, 2.5f, 1.5f),
                        markerColor);
                    if (player.Position.DistanceTo(RURAL_VEHICLE_ENTRANCE_POS) <
                        ENTER_RADIUS + 0.5f)
                    {
                        Vehicle vehicle = player.CurrentVehicle;
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            RURAL_GARAGE, vehicle);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(RURAL_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Grapeseed Garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterRuralGarage();
                        }
                    }
                }
                else
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        RURAL_PED_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(1.5f, 1.5f, 1.2f),
                        markerColor);
                    if (player.Position.DistanceTo(RURAL_PED_ENTRANCE_POS) < ENTER_RADIUS)
                    {
                        GarageEntryDenial denial = EvaluateGarageEntry(RURAL_GARAGE);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(RURAL_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Grapeseed Garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterRuralGarage();
                        }
                    }
                }
                return;
            }

            EnforceRuralVehicleState();
            if (player.IsInVehicle())
            {
                GTA.UI.Screen.ShowHelpTextThisFrame(
                    "Press ~INPUT_CONTEXT~ to leave the Grapeseed Garage with your vehicle.");
                if (Game.IsControlJustPressed(GTA.Control.Context))
                    LeaveRuralGarage();
            }
            else
            {
                World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                    RURAL_INTERIOR_PED - new Vector3(0f, 0f, 1f),
                    Vector3.Zero, Vector3.Zero, new Vector3(1.5f, 1.5f, 1.2f),
                    markerColor);
                if (player.Position.DistanceTo(RURAL_INTERIOR_PED) < EXIT_RADIUS)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to leave the Grapeseed Garage.");
                    if (Game.IsControlJustPressed(GTA.Control.Context))
                        LeaveRuralGarage();
                }
            }
        }

        private static void EnterRuralGarage()
        {
            if (RejectGarageEntry(RURAL_GARAGE)) return;
            if (!BeginTransition("EnterRuralGarage")) return;
            try { EnterRuralGarageCore(); }
            catch (Exception ex)
            {
                LogException("EnterRuralGarage", ex);
                UnloadRuralInterior();
                RecoverTransition("EnterRuralGarage",
                    RURAL_PED_ENTRANCE_POS, RURAL_PED_ENTRANCE_HEADING);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Grapeseed Garage entry failed safely. See ALLIN1_gbay.log.", 4000);
            }
            finally { EndTransition("EnterRuralGarage"); }
        }

        private static void EnterRuralGarageCore()
        {
            Ped player = Game.Player.Character;
            Vehicle rideInToDelete = null;
            string confirmation = null;
            bool interiorLoaded = false;
            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
                    string modelName = ResolveGarageVehicleName(rideIn);
                    if (RejectGarageEntry(
                        RURAL_GARAGE, rideIn, modelName, rideIn.Model.Hash)) return;
                    List<StoredVehicle> list = GetRuralGarageStoredVehicles();
                    if (list.Count >= RURAL_SLOT_COUNT)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~The Grapeseed Garage is full.~w~ ({list.Count}/{RURAL_SLOT_COUNT})",
                            3000);
                        return;
                    }
                    int slotIndex = FindEmptyRuralSlot(list);
                    if (slotIndex < 0) return;
                    StoredVehicle stored = CaptureVehicleState(
                        rideIn, modelName, slotIndex);
                    if (!LoadRuralInterior())
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The Grapeseed Garage interior could not be loaded.", 4000);
                        return;
                    }
                    interiorLoaded = true;
                    list.Add(stored);
                    if (!RuralSave())
                    {
                        list.Remove(stored);
                        UnloadRuralInterior();
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The vehicle could not be saved.", 3000);
                        return;
                    }
                    string display = RuntimeVehicleCatalog.GetDisplayName(modelName);
                    confirmation = $"~g~{display}~w~ stored in the Grapeseed Garage.";
                    rideIn.IsPersistent = true;
                    rideInToDelete = rideIn;
                }
            }

            if (!interiorLoaded && !LoadRuralInterior())
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The Grapeseed Garage interior could not be loaded.", 4000);
                return;
            }
            ClearRuralHandles();
            _isPlayerInRuralGarage = true;
            BeginGarageBlackTransition("EnterRuralGarage");
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                RURAL_INTERIOR_PED.X, RURAL_INTERIOR_PED.Y,
                RURAL_INTERIOR_PED.Z, false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player,
                RURAL_INTERIOR_PED_HEADING);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            if (rideInToDelete != null && rideInToDelete.Exists())
                rideInToDelete.Delete();
            SpawnRuralGarageVehicles();
            player.IsPositionFrozen = false;
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            CompleteGarageBlackTransition(
                "EnterRuralGarage", player, null,
                () => IsPlayerInReadyInterior(player), _ruralHandles);
            if (!string.IsNullOrEmpty(confirmation))
                GTA.UI.Screen.ShowSubtitle(confirmation, 4000);
        }

        private static void LeaveRuralGarage()
        {
            if (!BeginTransition("LeaveRuralGarage")) return;
            try { LeaveRuralGarageCore(); }
            catch (Exception ex)
            {
                LogException("LeaveRuralGarage", ex);
                RecoverTransition("LeaveRuralGarage",
                    RURAL_PED_ENTRANCE_POS, RURAL_PED_ENTRANCE_HEADING);
            }
            finally { EndTransition("LeaveRuralGarage"); }
        }

        private static void LeaveRuralGarageCore()
        {
            RuralUpdateStoredFromLive();
            Ped player = Game.Player.Character;
            Vehicle playerVehicle = null;
            int playerSlot = -1;
            if (player.IsInVehicle())
            {
                Vehicle current = player.CurrentVehicle;
                for (int i = 0; i < _ruralHandles.Length; i++)
                {
                    if (_ruralHandles[i] != null && _ruralHandles[i] == current)
                    {
                        playerVehicle = current;
                        playerSlot = i;
                        _ruralHandles[i] = null;
                        break;
                    }
                }
            }

            ClearRuralHandles();
            BeginGarageBlackTransition("LeaveRuralGarage");
            if (playerVehicle != null)
            {
                List<StoredVehicle> list = GetRuralGarageStoredVehicles();
                for (int i = list.Count - 1; i >= 0; i--)
                    if (list[i].Slot == playerSlot) { list.RemoveAt(i); break; }
                playerVehicle.IsPersistent = true;
                ReleaseGarageVehicleForDriving(playerVehicle,
                    RURAL_VEHICLE_ENTRANCE_POS,
                    RURAL_VEHICLE_ENTRANCE_HEADING, "Grapeseed");
            }
            else
            {
                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    RURAL_PED_ENTRANCE_POS.X, RURAL_PED_ENTRANCE_POS.Y,
                    RURAL_PED_ENTRANCE_POS.Z, false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player,
                    RURAL_PED_ENTRANCE_HEADING);
                player.IsPositionFrozen = false;
            }
            RuralSave();
            _isPlayerInRuralGarage = false;
            _ruralExitCooldownFrames = 60;
            UnloadRuralInterior();
            Script.Wait(500);
            CompleteGarageBlackTransition(
                "LeaveRuralGarage", player, playerVehicle,
                () => Function.Call<int>(
                    Hash.GET_INTERIOR_FROM_ENTITY, player) == 0);
        }

        private static bool LoadRuralInterior()
        {
            bool focusSet = false;
            try
            {
                // The six-car garage can be loaded directly through its High
                // Life MILO without switching the session-wide MP map. Do not
                // accept a merely resolved interior ID unless the actual MILO
                // IPL is active; the old behavior admitted the player into an
                // unloaded void below the map.
                StandaloneMapPack.TryActivate(RURAL_IPLS);
                foreach (string ipl in RURAL_IPLS)
                    Function.Call(Hash.REQUEST_IPL, ipl);

                Function.Call(Hash.SET_FOCUS_POS_AND_VEL,
                    RURAL_INTERIOR_CENTER.X, RURAL_INTERIOR_CENTER.Y,
                    RURAL_INTERIOR_CENTER.Z, 0f, 0f, 0f);
                focusSet = true;

                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    RURAL_INTERIOR_CENTER.X, RURAL_INTERIOR_CENTER.Y,
                    RURAL_INTERIOR_CENTER.Z);

                int startedAt = Game.GameTime;
                int interior = 0;
                bool interiorReady = false;
                bool iplActive = false;
                int firstResolvedAt = -1;
                while (Game.GameTime - startedAt < RURAL_INTERIOR_LOAD_TIMEOUT_MS)
                {
                    foreach (string ipl in RURAL_IPLS)
                        Function.Call(Hash.REQUEST_IPL, ipl);
                    Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                        RURAL_INTERIOR_CENTER.X, RURAL_INTERIOR_CENTER.Y,
                        RURAL_INTERIOR_CENTER.Z);
                    interior = Function.Call<int>(Hash.GET_INTERIOR_AT_COORDS,
                        RURAL_INTERIOR_CENTER.X, RURAL_INTERIOR_CENTER.Y,
                        RURAL_INTERIOR_CENTER.Z);
                    if (interior != 0)
                    {
                        Function.Call(Hash.DISABLE_INTERIOR, interior, false);
                        Function.Call(Hash.PIN_INTERIOR_IN_MEMORY, interior);
                        Function.Call(Hash.REFRESH_INTERIOR, interior);
                        interiorReady = Function.Call<bool>(
                            Hash.IS_INTERIOR_READY, interior);
                        if (firstResolvedAt < 0)
                            firstResolvedAt = Game.GameTime;
                    }
                    else firstResolvedAt = -1;
                    iplActive = true;
                    foreach (string ipl in RURAL_IPLS)
                        iplActive &= Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl);
                    int resolvedForMs = firstResolvedAt < 0 ? 0
                        : Game.GameTime - firstResolvedAt;
                    if (GarageInteriorReadinessPolicy.IsUsable(
                        interior, true, iplActive, interiorReady,
                        resolvedForMs, RURAL_INTERIOR_FALLBACK_SETTLE_MS))
                    {
                        Log($"LoadRuralInterior: interior={interior} ready " +
                            $"readySignal={interiorReady} iplActive={iplActive} " +
                            $"fallback={!interiorReady} " +
                            $"elapsed={Game.GameTime - startedAt}ms");
                        return true;
                    }
                    Script.Wait(100);
                }

                Log($"LoadRuralInterior: FAILED interior={interior} " +
                    $"interiorReady={interiorReady} iplActive={iplActive}");
            }
            catch (Exception ex)
            {
                LogException("LoadRuralInterior", ex);
            }
            finally
            {
                if (focusSet)
                    Function.Call(Hash.CLEAR_FOCUS);
            }
            return false;
        }

        private static void UnloadRuralInterior()
        {
            foreach (string ipl in RURAL_IPLS)
                Function.Call(Hash.REMOVE_IPL, ipl);
        }

        private static ParkingSlot ResolveRuralSlot(StoredVehicle stored)
        {
            return RuralSlots[stored.Slot];
        }

        private static void SpawnRuralGarageVehicles()
        {
            ClearRuralHandles();
            foreach (StoredVehicle stored in GetRuralGarageStoredVehicles())
                SpawnRuralVehicle(stored);
        }

        private static void SpawnRuralVehicle(StoredVehicle stored)
        {
            if (stored.Slot < 0 || stored.Slot >= RURAL_SLOT_COUNT) return;
            try
            {
                ParkingSlot slot = ResolveRuralSlot(stored);
                Model model = GetStoredModel(stored);
                model.Request(10000);
                if (!model.IsLoaded)
                {
                    Log($"SpawnRuralVehicle: model unavailable {stored.Model}");
                    return;
                }
                Vehicle vehicle = World.CreateVehicle(model, slot.Position, slot.Heading);
                model.MarkAsNoLongerNeeded();
                if (vehicle == null) return;
                ApplyVehicleState(vehicle, stored);
                vehicle.IsPersistent = true;
                vehicle.IsEngineRunning = false;
                PlaceVehicleInParkingSpace(
                    vehicle, slot, stored.Model, "Grapeseed");
                vehicle.IsPositionFrozen = true;
                _ruralHandles[stored.Slot] = vehicle;
            }
            catch (Exception ex)
            {
                LogException($"SpawnRuralVehicle({stored.Model})", ex);
            }
        }

        private static void EnforceRuralVehicleState()
        {
            foreach (Vehicle vehicle in _ruralHandles)
            {
                if (vehicle == null || !vehicle.Exists()) continue;
                vehicle.IsPositionFrozen = true;
                vehicle.IsEngineRunning = false;
            }
        }

        private static void ClearRuralHandles()
        {
            for (int i = 0; i < _ruralHandles.Length; i++)
                DeleteRuralHandle(i);
        }

        private static void DeleteRuralHandle(int slot)
        {
            if (slot < 0 || slot >= _ruralHandles.Length) return;
            Vehicle vehicle = _ruralHandles[slot];
            if (vehicle != null && vehicle.Exists())
            {
                vehicle.IsPersistent = true;
                vehicle.Delete();
            }
            _ruralHandles[slot] = null;
        }

        private static int FindEmptyRuralSlot(List<StoredVehicle> list)
        {
            var occupied = new HashSet<int>();
            foreach (StoredVehicle stored in list) occupied.Add(stored.Slot);
            for (int i = 0; i < RURAL_SLOT_COUNT; i++)
                if (!occupied.Contains(i)) return i;
            return -1;
        }

        private static void RuralUpdateStoredFromLive()
        {
            if (!_isPlayerInRuralGarage) return;
            List<StoredVehicle> list = GetRuralGarageStoredVehicles();
            for (int i = 0; i < list.Count; i++)
            {
                StoredVehicle stored = list[i];
                if (stored.Slot < 0 || stored.Slot >= RURAL_SLOT_COUNT) continue;
                Vehicle vehicle = _ruralHandles[stored.Slot];
                if (vehicle == null || !vehicle.Exists()) continue;
                list[i] = CaptureVehicleState(vehicle, stored.Model, stored.Slot);
            }
            RuralSave();
        }

        private static void RuralLoad()
        {
            string loadPath = File.Exists(RURAL_SAVE_PATH)
                ? RURAL_SAVE_PATH : RURAL_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath)) return;
            try
            {
                RuralParseJson(File.ReadAllText(loadPath));
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                    RuralSave();
            }
            catch (Exception ex)
            {
                LogException("RuralLoad", ex);
                string backup = RURAL_SAVE_PATH + ".bak";
                if (loadPath == RURAL_SAVE_PATH && File.Exists(backup))
                {
                    try { RuralParseJson(File.ReadAllText(backup)); }
                    catch (Exception backupEx)
                    {
                        LogException("RuralLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool RuralSave()
        {
            return StageOrWriteVehicleSave(
                RURAL_SAVE_PATH, RuralBuildJson, "RuralSave");
        }

        private static string RuralBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");
            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");
                if (_ruralStored.TryGetValue(key, out var list) && list.Count > 0)
                {
                    sb.AppendLine();
                    for (int i = 0; i < list.Count; i++)
                    {
                        AppendDavisVehicleJson(sb, list[i]);
                        sb.AppendLine(i < list.Count - 1 ? "," : "");
                    }
                    sb.Append("  ]");
                }
                else sb.Append("]");
                sb.AppendLine(k < keys.Length - 1 ? "," : "");
            }
            sb.AppendLine("}");
            return sb.ToString();
        }

        private static void RuralParseJson(string json)
        {
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR },
                RURAL_SLOT_COUNT);
            foreach (var entry in parsed)
                _ruralStored[entry.Key] = entry.Value;
        }
    }
}
