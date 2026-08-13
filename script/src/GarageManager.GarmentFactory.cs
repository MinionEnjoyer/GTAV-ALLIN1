// GarageManager.GarmentFactory.cs -- Darnell Bros Garment Factory garage.

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
        private const int GARMENT_SLOT_COUNT = 10;
        private static readonly GarageDefinition GARMENT_GARAGE =
            GarageDefinitions.GarmentFactory;

        internal static readonly Vector3 GARMENT_VEHICLE_ENTRANCE_POS =
            new Vector3(762.1525f, -899.2333f, 25.1761f);
        private const float GARMENT_VEHICLE_ENTRANCE_HEADING = 270f;
        internal static readonly Vector3 GARMENT_PED_ENTRANCE_POS =
            new Vector3(760.7663f, -909.4583f, 25.2538f);
        private const float GARMENT_PED_ENTRANCE_HEADING = 270f;

        // Surveyed player-facing centre of the marked pedestrian exit door.
        // This is intentionally separate from Rockstar's deeper fast-travel
        // trigger so the world marker and interaction sit directly at the door.
        private static readonly Vector3 GARMENT_INTERIOR_PED =
            new Vector3(751.0350f, -975.4493f, -67.5536f);
        private const float GARMENT_INTERIOR_PED_HEADING = 180f;
        private const float GARMENT_FLOOR_Z = -67.75383f;

        private static readonly string[] GARMENT_IPLS =
        {
            "m24_2_int_placement",
            "m24_2_int_placement_interior_int_hacker_garage_milo_",
        };

        // Rockstar's ten roots from am_mp_hacker_den. Standard cars are
        // shifted 0.8 m into their bays; large models retain these roots.
        internal static readonly ParkingSlot[] GarmentFactorySlots =
        {
            new ParkingSlot(735.8997f, -977.9629f, -67.0919f, 176.4f, GARMENT_FLOOR_Z),
            new ParkingSlot(740.9352f, -977.9629f, -67.0903f, -175.32f, GARMENT_FLOOR_Z),
            new ParkingSlot(745.9560f, -977.9629f, -67.0887f, 175.22f, GARMENT_FLOOR_Z),
            new ParkingSlot(755.9915f, -977.9629f, -67.0856f, 179.9f, GARMENT_FLOOR_Z),
            new ParkingSlot(760.9529f, -977.9629f, -67.0840f, -177.48f, GARMENT_FLOOR_Z),
            new ParkingSlot(760.9529f, -995.7402f, -67.0849f, -3.412f, GARMENT_FLOOR_Z),
            new ParkingSlot(755.9875f, -995.7402f, -67.0833f, 2.017f, GARMENT_FLOOR_Z),
            new ParkingSlot(745.9362f, -995.7402f, -67.0802f, 4.832f, GARMENT_FLOOR_Z),
            new ParkingSlot(740.9589f, -995.7402f, -67.0786f, -3.231f, GARMENT_FLOOR_Z),
            new ParkingSlot(736.1323f, -995.7402f, -67.0770f, -5.313f, GARMENT_FLOOR_Z),
        };

        private static readonly string GARMENT_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_garment_factory_garage.json");
        private static readonly Dictionary<string, List<StoredVehicle>> _garmentStored =
            new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL, new List<StoredVehicle>() },
                { KEY_FRANKLIN, new List<StoredVehicle>() },
                { KEY_TREVOR, new List<StoredVehicle>() },
            };
        private static readonly Vehicle[] _garmentHandles =
            new Vehicle[GARMENT_SLOT_COUNT];
        private static bool _isPlayerInGarmentGarage;
        private static bool _garmentInitialized;
        private static int _garmentExitCooldownFrames;
        private static Blip _garmentVehicleBlip;
        private static Blip _garmentPedBlip;

        internal static bool IsPlayerInGarmentGarage => _isPlayerInGarmentGarage;
        internal static bool IsGarmentGarageInitialized => _garmentInitialized;

        internal static void InitializeGarmentGarage()
        {
            if (_garmentInitialized) return;
            try
            {
                GarmentLoad();
                _garmentVehicleBlip = World.CreateBlip(GARMENT_VEHICLE_ENTRANCE_POS);
                _garmentVehicleBlip.Sprite = BlipSprite.Garage;
                _garmentVehicleBlip.Color = CharacterBlipColor();
                _garmentVehicleBlip.Name = "ALLIN1 Garment Factory (Vehicle)";
                _garmentVehicleBlip.IsShortRange = true;

                _garmentPedBlip = World.CreateBlip(GARMENT_PED_ENTRANCE_POS);
                _garmentPedBlip.Sprite = BlipSprite.Garage;
                _garmentPedBlip.Color = CharacterBlipColor();
                _garmentPedBlip.Name = "ALLIN1 Garment Factory (Pedestrian)";
                _garmentPedBlip.IsShortRange = true;

                int count = 0;
                foreach (List<StoredVehicle> list in _garmentStored.Values)
                    count += list.Count;
                Log($"Garment Factory garage initialized ({count} stored vehicles)");
            }
            catch (Exception ex)
            {
                LogException("InitializeGarmentGarage", ex);
            }
            _garmentInitialized = true;
        }

        internal static int GetGarmentGarageUsedSlots()
        {
            return _garmentStored.TryGetValue(CharacterKey(), out var list)
                ? list.Count : 0;
        }

        internal static int GetGarmentGarageCapacity() => GARMENT_SLOT_COUNT;

        internal static List<StoredVehicle> GetGarmentGarageStoredVehicles()
        {
            return _garmentStored.TryGetValue(CharacterKey(), out var list)
                ? list : new List<StoredVehicle>();
        }

        internal static bool DeliverToGarmentGarage(
            string model, int color1, int color2)
        {
            if (VehicleList.GetSizeTier(model) == 2) return false;
            if (!_garmentStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (list.Count >= GARMENT_SLOT_COUNT) return false;
            int slotIndex = FindEmptyGarmentSlot(list);
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
            if (_isPlayerInGarmentGarage) SpawnGarmentVehicle(stored);
            if (!GarmentSave())
            {
                list.Remove(stored);
                DeleteGarmentHandle(slotIndex);
                return false;
            }
            Log($"DeliverToGarmentGarage: {model} -> slot {slotIndex}");
            return true;
        }

        internal static bool RemoveGarmentGarageVehicle(int listIndex)
        {
            if (!_garmentStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (listIndex < 0 || listIndex >= list.Count) return false;
            StoredVehicle stored = list[listIndex];
            DeleteGarmentHandle(stored.Slot);
            list.RemoveAt(listIndex);
            if (!GarmentSave())
            {
                list.Insert(listIndex, stored);
                return false;
            }
            Log($"RemoveGarmentGarageVehicle: {stored.Model} from slot {stored.Slot}");
            return true;
        }

        internal static void OnGarmentGarageTick()
        {
            if (!_garmentInitialized || _transitionInProgress) return;
            if (_isPlayerInGarage || _isPlayerInFloorGarage || _isPlayerInDavisGarage)
                return;
            if (_garmentExitCooldownFrames > 0)
            {
                _garmentExitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;
            if (!_isPlayerInGarmentGarage && !GbayShop.TryGetCurrentCharacter(out _))
                return;
            Color markerColor = CharacterMarkerColor();

            if (!_isPlayerInGarmentGarage)
            {
                if (EvaluateGarageEntry(GARMENT_GARAGE) ==
                    GarageEntryDenial.MissionActive) return;
                if (player.IsInVehicle())
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        GARMENT_VEHICLE_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(2.5f, 2.5f, 1.5f),
                        markerColor);
                    if (player.Position.DistanceTo(GARMENT_VEHICLE_ENTRANCE_POS) <
                        ENTER_RADIUS + 0.5f)
                    {
                        Vehicle vehicle = player.CurrentVehicle;
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            GARMENT_GARAGE, vehicle);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(GARMENT_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Garment Factory garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterGarmentGarage();
                        }
                    }
                }
                else
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        GARMENT_PED_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(1.5f, 1.5f, 1.2f),
                        markerColor);
                    if (player.Position.DistanceTo(GARMENT_PED_ENTRANCE_POS) < ENTER_RADIUS)
                    {
                        GarageEntryDenial denial = EvaluateGarageEntry(GARMENT_GARAGE);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(GARMENT_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Garment Factory garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterGarmentGarage();
                        }
                    }
                }
                return;
            }

            EnforceGarmentVehicleState();
            if (player.IsInVehicle())
            {
                GTA.UI.Screen.ShowHelpTextThisFrame(
                    "Press ~INPUT_CONTEXT~ to leave the Garment Factory with your vehicle.");
                if (Game.IsControlJustPressed(GTA.Control.Context))
                    LeaveGarmentGarage();
            }
            else
            {
                World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                    GARMENT_INTERIOR_PED - new Vector3(0f, 0f, 1f),
                    Vector3.Zero, Vector3.Zero, new Vector3(1.5f, 1.5f, 1.2f),
                    markerColor);
                if (player.Position.DistanceTo(GARMENT_INTERIOR_PED) < EXIT_RADIUS)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to leave the Garment Factory.");
                    if (Game.IsControlJustPressed(GTA.Control.Context))
                        LeaveGarmentGarage();
                }
            }
        }

        private static void EnterGarmentGarage()
        {
            if (RejectGarageEntry(GARMENT_GARAGE)) return;
            if (!BeginTransition("EnterGarmentGarage")) return;
            try { EnterGarmentGarageCore(); }
            catch (Exception ex)
            {
                LogException("EnterGarmentGarage", ex);
                UnloadGarmentInterior();
                RecoverTransition("EnterGarmentGarage",
                    GARMENT_PED_ENTRANCE_POS, GARMENT_PED_ENTRANCE_HEADING);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Garment Factory entry failed safely. See ALLIN1_gbay.log.", 4000);
            }
            finally { EndTransition("EnterGarmentGarage"); }
        }

        private static void EnterGarmentGarageCore()
        {
            Ped player = Game.Player.Character;
            Vehicle rideInToDelete = null;
            string confirmation = null;
            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
                    string modelName = ResolveGarageVehicleName(rideIn);
                    if (RejectGarageEntry(
                        GARMENT_GARAGE, rideIn, modelName, rideIn.Model.Hash)) return;
                    List<StoredVehicle> list = GetGarmentGarageStoredVehicles();
                    if (list.Count >= GARMENT_SLOT_COUNT)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~The Garment Factory garage is full.~w~ ({list.Count}/{GARMENT_SLOT_COUNT})",
                            3000);
                        return;
                    }
                    int slotIndex = FindEmptyGarmentSlot(list);
                    if (slotIndex < 0) return;
                    StoredVehicle stored = CaptureVehicleState(
                        rideIn, modelName, slotIndex);
                    list.Add(stored);
                    if (!GarmentSave())
                    {
                        list.Remove(stored);
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The vehicle could not be saved.", 3000);
                        return;
                    }
                    string display = VehicleList.DisplayNames.TryGetValue(
                        modelName, out string displayName) ? displayName : modelName;
                    confirmation = $"~g~{display}~w~ stored in the Garment Factory.";
                    rideIn.IsPersistent = true;
                    rideInToDelete = rideIn;
                }
            }

            LoadGarmentInterior();
            ClearGarmentHandles();
            _isPlayerInGarmentGarage = true;
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            Script.Wait(600);
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                GARMENT_INTERIOR_PED.X, GARMENT_INTERIOR_PED.Y,
                GARMENT_INTERIOR_PED.Z, false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player,
                GARMENT_INTERIOR_PED_HEADING);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            if (rideInToDelete != null && rideInToDelete.Exists())
                rideInToDelete.Delete();
            SpawnGarmentGarageVehicles();
            player.IsPositionFrozen = false;
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
            if (!string.IsNullOrEmpty(confirmation))
                GTA.UI.Screen.ShowSubtitle(confirmation, 4000);
        }

        private static void LeaveGarmentGarage()
        {
            if (!BeginTransition("LeaveGarmentGarage")) return;
            try { LeaveGarmentGarageCore(); }
            catch (Exception ex)
            {
                LogException("LeaveGarmentGarage", ex);
                RecoverTransition("LeaveGarmentGarage",
                    GARMENT_PED_ENTRANCE_POS, GARMENT_PED_ENTRANCE_HEADING);
            }
            finally { EndTransition("LeaveGarmentGarage"); }
        }

        private static void LeaveGarmentGarageCore()
        {
            GarmentUpdateStoredFromLive();
            Ped player = Game.Player.Character;
            Vehicle playerVehicle = null;
            int playerSlot = -1;
            if (player.IsInVehicle())
            {
                Vehicle current = player.CurrentVehicle;
                for (int i = 0; i < _garmentHandles.Length; i++)
                {
                    if (_garmentHandles[i] != null && _garmentHandles[i] == current)
                    {
                        playerVehicle = current;
                        playerSlot = i;
                        _garmentHandles[i] = null;
                        break;
                    }
                }
            }

            ClearGarmentHandles();
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            Script.Wait(600);
            if (playerVehicle != null)
            {
                List<StoredVehicle> list = GetGarmentGarageStoredVehicles();
                for (int i = list.Count - 1; i >= 0; i--)
                    if (list[i].Slot == playerSlot) { list.RemoveAt(i); break; }
                playerVehicle.IsPositionFrozen = false;
                playerVehicle.IsPersistent = true;
                Function.Call(Hash.SET_ENTITY_COORDS, playerVehicle,
                    GARMENT_VEHICLE_ENTRANCE_POS.X,
                    GARMENT_VEHICLE_ENTRANCE_POS.Y,
                    GARMENT_VEHICLE_ENTRANCE_POS.Z,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, playerVehicle,
                    GARMENT_VEHICLE_ENTRANCE_HEADING);
                Function.Call(Hash.SET_VEHICLE_ON_GROUND_PROPERLY, playerVehicle);
                playerVehicle.IsEngineRunning = true;
            }
            else
            {
                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    GARMENT_PED_ENTRANCE_POS.X, GARMENT_PED_ENTRANCE_POS.Y,
                    GARMENT_PED_ENTRANCE_POS.Z, false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player,
                    GARMENT_PED_ENTRANCE_HEADING);
                player.IsPositionFrozen = false;
            }
            GarmentSave();
            _isPlayerInGarmentGarage = false;
            _garmentExitCooldownFrames = 60;
            UnloadGarmentInterior();
            Script.Wait(500);
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
        }

        private static void LoadGarmentInterior()
        {
            DlcMapState.Acquire(GARMENT_GARAGE);
            Script.Wait(500);
            foreach (string ipl in GARMENT_IPLS)
                Function.Call(Hash.REQUEST_IPL, ipl);
            Script.Wait(1000);
            int interior = Function.Call<int>(Hash.GET_INTERIOR_AT_COORDS,
                750.9006f, -990.0551f, -67.75383f);
            if (interior != 0)
            {
                Function.Call(Hash.REFRESH_INTERIOR, interior);
                Function.Call(Hash.PIN_INTERIOR_IN_MEMORY, interior);
            }
            else Log("LoadGarmentInterior: WARNING - interior not found");
        }

        private static void UnloadGarmentInterior()
        {
            if (!DlcMapState.IsAcquired(GARMENT_GARAGE)) return;
            foreach (string ipl in GARMENT_IPLS)
                Function.Call(Hash.REMOVE_IPL, ipl);
            DlcMapState.Release(GARMENT_GARAGE);
        }

        private static ParkingSlot ResolveGarmentSlot(StoredVehicle stored)
        {
            ParkingSlot slot = GarmentFactorySlots[stored.Slot];
            if (GetGarageSizeTier(stored.Model, stored.ModelHash) > 0) return slot;
            slot.Position.Y += stored.Slot <= 4 ? 0.8f : -0.8f;
            return slot;
        }

        private static void SpawnGarmentGarageVehicles()
        {
            ClearGarmentHandles();
            foreach (StoredVehicle stored in GetGarmentGarageStoredVehicles())
                SpawnGarmentVehicle(stored);
        }

        private static void SpawnGarmentVehicle(StoredVehicle stored)
        {
            if (stored.Slot < 0 || stored.Slot >= GARMENT_SLOT_COUNT) return;
            try
            {
                ParkingSlot slot = ResolveGarmentSlot(stored);
                Model model = GetStoredModel(stored);
                model.Request(10000);
                if (!model.IsLoaded)
                {
                    Log($"SpawnGarmentVehicle: model unavailable {stored.Model}");
                    return;
                }
                Vehicle vehicle = World.CreateVehicle(model, slot.Position, slot.Heading);
                model.MarkAsNoLongerNeeded();
                if (vehicle == null) return;
                ApplyVehicleState(vehicle, stored);
                vehicle.IsPersistent = true;
                vehicle.IsEngineRunning = false;
                PlaceVehicleInParkingSpace(
                    vehicle, slot, stored.Model, "GarmentFactory");
                vehicle.IsPositionFrozen = true;
                _garmentHandles[stored.Slot] = vehicle;
            }
            catch (Exception ex)
            {
                LogException($"SpawnGarmentVehicle({stored.Model})", ex);
            }
        }

        private static void EnforceGarmentVehicleState()
        {
            foreach (Vehicle vehicle in _garmentHandles)
            {
                if (vehicle == null || !vehicle.Exists()) continue;
                vehicle.IsPositionFrozen = true;
                vehicle.IsEngineRunning = false;
            }
        }

        private static void ClearGarmentHandles()
        {
            for (int i = 0; i < _garmentHandles.Length; i++)
                DeleteGarmentHandle(i);
        }

        private static void DeleteGarmentHandle(int slot)
        {
            if (slot < 0 || slot >= _garmentHandles.Length) return;
            Vehicle vehicle = _garmentHandles[slot];
            if (vehicle != null && vehicle.Exists())
            {
                vehicle.IsPersistent = true;
                vehicle.Delete();
            }
            _garmentHandles[slot] = null;
        }

        private static int FindEmptyGarmentSlot(List<StoredVehicle> list)
        {
            var occupied = new HashSet<int>();
            foreach (StoredVehicle stored in list) occupied.Add(stored.Slot);
            for (int i = 0; i < GARMENT_SLOT_COUNT; i++)
                if (!occupied.Contains(i)) return i;
            return -1;
        }

        private static string ResolveGarageVehicleName(Vehicle vehicle)
        {
            int hash = vehicle.Model.Hash;
            if (_hashToSpawnName != null &&
                _hashToSpawnName.TryGetValue(hash, out string spawnName))
                return spawnName;
            string display = Function.Call<string>(
                Hash.GET_DISPLAY_NAME_FROM_VEHICLE_MODEL, (uint)hash);
            return string.IsNullOrEmpty(display)
                ? hash.ToString() : display.ToLowerInvariant();
        }

        private static void GarmentUpdateStoredFromLive()
        {
            if (!_isPlayerInGarmentGarage) return;
            List<StoredVehicle> list = GetGarmentGarageStoredVehicles();
            for (int i = 0; i < list.Count; i++)
            {
                StoredVehicle stored = list[i];
                if (stored.Slot < 0 || stored.Slot >= GARMENT_SLOT_COUNT) continue;
                Vehicle vehicle = _garmentHandles[stored.Slot];
                if (vehicle == null || !vehicle.Exists()) continue;
                list[i] = CaptureVehicleState(vehicle, stored.Model, stored.Slot);
            }
            GarmentSave();
        }

        private static void GarmentLoad()
        {
            string loadPath = File.Exists(GARMENT_SAVE_PATH)
                ? GARMENT_SAVE_PATH : GARMENT_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath)) return;
            try
            {
                GarmentParseJson(File.ReadAllText(loadPath));
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                    GarmentSave();
            }
            catch (Exception ex)
            {
                LogException("GarmentLoad", ex);
                string backup = GARMENT_SAVE_PATH + ".bak";
                if (loadPath == GARMENT_SAVE_PATH && File.Exists(backup))
                {
                    try { GarmentParseJson(File.ReadAllText(backup)); }
                    catch (Exception backupEx)
                    {
                        LogException("GarmentLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool GarmentSave()
        {
            try
            {
                AtomicWriteText(GARMENT_SAVE_PATH, GarmentBuildJson());
                return true;
            }
            catch (Exception ex)
            {
                LogException("GarmentSave", ex);
                return false;
            }
        }

        private static string GarmentBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");
            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");
                if (_garmentStored.TryGetValue(key, out var list) && list.Count > 0)
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

        private static void GarmentParseJson(string json)
        {
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR },
                GARMENT_SLOT_COUNT);
            foreach (var entry in parsed)
                _garmentStored[entry.Key] = entry.Value;
        }
    }
}
