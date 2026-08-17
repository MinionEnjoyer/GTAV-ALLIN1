using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    /// <summary>
    /// List-backed helicopter storage at the Vespucci helipad. Unlike a garage,
    /// no stored aircraft are kept alive in the world. Aircraft are removed when
    /// stored and recreated only when the player retrieves one from the list.
    /// </summary>
    internal static partial class GarageManager
    {
        private const int HELIPAD_SLOT_COUNT = 10;
        private const float HELIPAD_ACCESS_HEADING = 24f;
        private const float HELIPAD_SPAWN_HEADING = 317f;
        private const float HELIPAD_ACCESS_RADIUS = 2.5f;
        private const float HELIPAD_STORE_RADIUS = 9f;

        internal static readonly Vector3 HelipadAccessPosition =
            new Vector3(-743.7491f, -1504.9200f, 5.0005f);
        internal static readonly Vector3 HelipadPosition =
            new Vector3(-745.3192f, -1468.5640f, 5.0005f);

        private static readonly string HELIPAD_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_helipad.json");

        private static readonly Dictionary<string, List<StoredVehicle>>
            _helipadStored = new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL, new List<StoredVehicle>() },
                { KEY_FRANKLIN, new List<StoredVehicle>() },
                { KEY_TREVOR, new List<StoredVehicle>() },
            };

        private static bool _helipadInitialized;
        private static bool _helipadListRequested;
        private static Blip _helipadAccessBlip;
        private static Blip _helipadVehicleBlip;

        internal static void InitializeHelipad()
        {
            if (_helipadInitialized) return;
            try
            {
                HelipadLoad();
                int count = 0;
                foreach (List<StoredVehicle> list in _helipadStored.Values)
                    count += list.Count;

                _helipadAccessBlip = World.CreateBlip(HelipadAccessPosition);
                _helipadAccessBlip.Sprite = BlipSprite.Helicopter;
                _helipadAccessBlip.Color = CharacterBlipColor();
                _helipadAccessBlip.Name = "ALLIN1 Vespucci Helipad (Aircraft List)";
                _helipadAccessBlip.IsShortRange = true;

                _helipadVehicleBlip = World.CreateBlip(HelipadPosition);
                _helipadVehicleBlip.Sprite = BlipSprite.Helicopter;
                _helipadVehicleBlip.Color = CharacterBlipColor();
                _helipadVehicleBlip.Name = "ALLIN1 Vespucci Helipad (Store Aircraft)";
                _helipadVehicleBlip.IsShortRange = true;

                Log($"Vespucci Helipad initialized ({count} stored aircraft)");
            }
            catch (Exception ex)
            {
                LogException("InitializeHelipad", ex);
            }
            _helipadInitialized = true;
        }

        internal static bool IsHelipadVehicleEligible(string model) =>
            HelipadPolicy.IsEligible(model);

        internal static int GetHelipadUsedSlots()
        {
            return _helipadStored.TryGetValue(CharacterKey(), out var list)
                ? list.Count : 0;
        }

        internal static int GetHelipadCapacity() => HELIPAD_SLOT_COUNT;

        internal static List<StoredVehicle> GetHelipadStoredVehicles()
        {
            return _helipadStored.TryGetValue(CharacterKey(), out var list)
                ? list : new List<StoredVehicle>();
        }

        internal static bool DeliverToHelipad(
            string model, int color1, int color2)
        {
            if (!HelipadPolicy.IsEligible(model)) return false;
            string key = CharacterKey();
            if (!_helipadStored.TryGetValue(key, out var list) ||
                list.Count >= HELIPAD_SLOT_COUNT) return false;

            int slot = FindHelipadSlot(list);
            if (slot < 0) return false;
            var stored = new StoredVehicle
            {
                Model = model,
                ModelHash = Game.GenerateHash(model),
                Slot = slot,
                Color1 = color1,
                Color2 = color2,
            };
            list.Add(stored);
            if (!HelipadSave())
            {
                list.Remove(stored);
                return false;
            }
            Log($"DeliverToHelipad: {model} -> slot {slot}");
            return true;
        }

        internal static bool RemoveHelipadVehicle(int listIndex)
        {
            string key = CharacterKey();
            if (!_helipadStored.TryGetValue(key, out var list) ||
                listIndex < 0 || listIndex >= list.Count) return false;
            StoredVehicle stored = list[listIndex];
            list.RemoveAt(listIndex);
            if (!HelipadSave())
            {
                list.Insert(listIndex, stored);
                return false;
            }
            Log($"RemoveHelipadVehicle: {stored.Model}");
            return true;
        }

        internal static bool RetrieveHelipadVehicle(int listIndex)
        {
            string key = CharacterKey();
            if (!_helipadStored.TryGetValue(key, out var list) ||
                listIndex < 0 || listIndex >= list.Count) return false;
            if (!IsHelipadClear())
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The helipad is blocked.~w~ Move the aircraft from the pad first.",
                    3500);
                return false;
            }

            StoredVehicle stored = list[listIndex];
            Vehicle aircraft = null;
            bool removedFromStorage = false;
            try
            {
                Model model = GetStoredModel(stored);
                model.Request(10000);
                if (!model.IsLoaded) return false;

                aircraft = World.CreateVehicle(model,
                    HelipadPosition + new Vector3(0f, 0f, 1.5f),
                    HELIPAD_SPAWN_HEADING);
                model.MarkAsNoLongerNeeded();
                if (aircraft == null) return false;

                ApplyVehicleState(aircraft, stored);
                aircraft.IsPersistent = true;
                aircraft.IsEngineRunning = false;
                var pad = new ParkingSlot(
                    HelipadPosition.X, HelipadPosition.Y,
                    HelipadPosition.Z + 1.5f, HELIPAD_SPAWN_HEADING,
                    HelipadPosition.Z);
                PlaceVehicleInParkingSpace(
                    aircraft, pad, stored.Model, "VespucciHelipad");

                list.RemoveAt(listIndex);
                removedFromStorage = true;
                if (!HelipadSave())
                {
                    list.Insert(listIndex, stored);
                    removedFromStorage = false;
                    aircraft.Delete();
                    return false;
                }

                Ped player = Game.Player.Character;
                BeginGarageBlackTransition("RetrieveHelipadVehicle");
                player.SetIntoVehicle(aircraft, VehicleSeat.Driver);
                aircraft.IsPositionFrozen = false;
                CompleteGarageBlackTransition(
                    "RetrieveHelipadVehicle", player, aircraft, () => true);
                Log($"RetrieveHelipadVehicle: {stored.Model} from slot {stored.Slot}");
                return true;
            }
            catch (Exception ex)
            {
                if (aircraft != null && aircraft.Exists()) aircraft.Delete();
                if (removedFromStorage)
                {
                    list.Insert(Math.Min(listIndex, list.Count), stored);
                    HelipadSave();
                }
                LogException($"RetrieveHelipadVehicle({stored.Model})", ex);
                return false;
            }
        }

        internal static bool ConsumeHelipadListRequest()
        {
            bool requested = _helipadListRequested;
            _helipadListRequested = false;
            return requested;
        }

        internal static void OnHelipadTick()
        {
            if (!_helipadInitialized || _transitionInProgress || Game.IsLoading)
                return;

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead ||
                !GbayShop.TryGetCurrentCharacter(out _)) return;

            if (!player.IsInVehicle())
            {
                World.DrawMarker(MarkerType.VerticalCylinder,
                    HelipadAccessPosition - new Vector3(0f, 0f, 0.9f),
                    Vector3.Zero, Vector3.Zero,
                    new Vector3(1.5f, 1.5f, 1.2f),
                    CharacterMarkerColor());
                if (player.Position.DistanceTo(HelipadAccessPosition) <
                    HELIPAD_ACCESS_RADIUS)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to access your helicopter list.");
                    if (Game.IsControlJustPressed(Control.Context))
                        _helipadListRequested = true;
                }
                return;
            }

            Vehicle aircraft = player.CurrentVehicle;
            if (aircraft == null || !aircraft.Exists() ||
                !IsHelicopter(aircraft)) return;

            World.DrawMarker(MarkerType.VerticalCylinder,
                HelipadPosition - new Vector3(0f, 0f, 1f),
                Vector3.Zero, Vector3.Zero,
                new Vector3(8f, 8f, 1.2f), CharacterMarkerColor());
            if (aircraft.Position.DistanceTo(HelipadPosition) >=
                HELIPAD_STORE_RADIUS) return;

            int used = GetHelipadUsedSlots();
            if (used >= HELIPAD_SLOT_COUNT)
            {
                GTA.UI.Screen.ShowHelpTextThisFrame(
                    $"The Vespucci Helipad is full ({used}/{HELIPAD_SLOT_COUNT}).");
                return;
            }

            GTA.UI.Screen.ShowHelpTextThisFrame(
                "Press ~INPUT_CONTEXT~ to store this helicopter.");
            if (Game.IsControlJustPressed(Control.Context))
                StoreCurrentHelicopter(aircraft);
        }

        private static bool StoreCurrentHelicopter(Vehicle aircraft)
        {
            string key = CharacterKey();
            if (!_helipadStored.TryGetValue(key, out var list) ||
                list.Count >= HELIPAD_SLOT_COUNT) return false;

            int hash = aircraft.Model.Hash;
            string modelName = _hashToSpawnName != null &&
                _hashToSpawnName.TryGetValue(hash, out string knownName)
                ? knownName
                : Function.Call<string>(
                    Hash.GET_DISPLAY_NAME_FROM_VEHICLE_MODEL, (uint)hash)
                    ?.ToLowerInvariant();
            if (string.IsNullOrWhiteSpace(modelName)) modelName = hash.ToString();
            if (!IsHelicopter(aircraft)) return false;

            int slot = FindHelipadSlot(list);
            if (slot < 0) return false;
            StoredVehicle stored = CaptureVehicleState(aircraft, modelName, slot);
            list.Add(stored);
            if (!HelipadSave())
            {
                list.Remove(stored);
                return false;
            }

            try
            {
                Ped player = Game.Player.Character;
                BeginGarageBlackTransition("StoreHelipadVehicle");
                Function.Call(Hash.TASK_LEAVE_VEHICLE, player, aircraft, 16);
                Script.Wait(0);
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    HelipadAccessPosition.X, HelipadAccessPosition.Y,
                    HelipadAccessPosition.Z + 0.2f,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING,
                    player, HELIPAD_ACCESS_HEADING);
                aircraft.IsPersistent = true;
                aircraft.Delete();
                CompleteGarageBlackTransition(
                    "StoreHelipadVehicle", player, null, () => true);

                string display = GetVehicleDisplayName(modelName, hash);
                GTA.UI.Screen.ShowSubtitle(
                    $"~g~{display}~w~ stored at the Vespucci Helipad " +
                    $"({list.Count}/{HELIPAD_SLOT_COUNT}).", 4000);
                Log($"StoreHelipadVehicle: {modelName} -> slot {slot}");
                return true;
            }
            catch (Exception ex)
            {
                list.Remove(stored);
                HelipadSave();
                LogException($"StoreHelipadVehicle({modelName})", ex);
                Function.Call(Hash.DO_SCREEN_FADE_IN, 0);
                return false;
            }
        }

        private static bool IsHelicopter(Vehicle vehicle)
        {
            try
            {
                return vehicle != null && vehicle.Exists() &&
                    Function.Call<bool>(Hash.IS_THIS_MODEL_A_HELI,
                        (uint)vehicle.Model.Hash);
            }
            catch { return false; }
        }

        private static bool IsHelipadClear()
        {
            foreach (Vehicle vehicle in World.GetNearbyVehicles(
                HelipadPosition, HELIPAD_STORE_RADIUS))
                if (vehicle != null && vehicle.Exists()) return false;
            return true;
        }

        private static int FindHelipadSlot(List<StoredVehicle> list)
        {
            for (int slot = 0; slot < HELIPAD_SLOT_COUNT; slot++)
            {
                bool used = false;
                foreach (StoredVehicle stored in list)
                    if (stored.Slot == slot) { used = true; break; }
                if (!used) return slot;
            }
            return -1;
        }

        private static void HelipadLoad()
        {
            string loadPath = File.Exists(HELIPAD_SAVE_PATH)
                ? HELIPAD_SAVE_PATH : HELIPAD_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath)) return;
            try
            {
                HelipadParseJson(File.ReadAllText(loadPath));
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                    HelipadSave();
            }
            catch (Exception ex)
            {
                LogException("HelipadLoad", ex);
                string backup = HELIPAD_SAVE_PATH + ".bak";
                if (loadPath == HELIPAD_SAVE_PATH && File.Exists(backup))
                {
                    try { HelipadParseJson(File.ReadAllText(backup)); }
                    catch (Exception backupEx)
                    {
                        LogException("HelipadLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool HelipadSave()
        {
            return StageOrWriteVehicleSave(
                HELIPAD_SAVE_PATH, HelipadBuildJson, "HelipadSave");
        }

        private static string HelipadBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");
            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");
                if (_helipadStored.TryGetValue(key, out var list) &&
                    list.Count > 0)
                {
                    sb.AppendLine();
                    for (int i = 0; i < list.Count; i++)
                    {
                        AppendDavisVehicleJson(sb, list[i]);
                        if (i < list.Count - 1) sb.AppendLine(",");
                    }
                    sb.Append("  ]");
                }
                else sb.Append("]");
                sb.AppendLine(k < keys.Length - 1 ? "," : "");
            }
            sb.AppendLine("}");
            return sb.ToString();
        }

        private static void HelipadParseJson(string json)
        {
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR },
                HELIPAD_SLOT_COUNT);
            foreach (var entry in parsed)
                _helipadStored[entry.Key] = entry.Value;
        }
    }

    internal static class HelipadPolicy
    {
        internal static bool IsEligible(string model)
        {
            if (string.IsNullOrWhiteSpace(model)) return false;
            foreach (string helicopter in VehicleList.Helicopters)
                if (string.Equals(model, helicopter,
                    StringComparison.OrdinalIgnoreCase)) return true;

            // The weaponized Conada is catalogued under Military in GBAY but
            // is still a helicopter and belongs in the helipad list.
            return string.Equals(model, "conada2",
                StringComparison.OrdinalIgnoreCase);
        }
    }
}
