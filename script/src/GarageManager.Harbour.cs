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
    /// List-backed boat storage at Los Santos Harbour. Stored boats have no
    /// physical world handle; they are removed on storage and recreated only
    /// when selected from the pedestrian-access list.
    /// </summary>
    internal static partial class GarageManager
    {
        private const int HARBOUR_SLOT_COUNT = 10;
        private const float HARBOUR_ACCESS_HEADING = 4f;
        private const float HARBOUR_SPAWN_HEADING = 52f;
        private const float MARINA_ACCESS_HEADING = 172f;
        private const float MARINA_SPAWN_HEADING = 135f;
        private const float HARBOUR_ACCESS_RADIUS = 2.5f;
        private const float HARBOUR_STORE_RADIUS = 14f;

        internal static readonly Vector3 HarbourAccessPosition =
            new Vector3(-278.1758f, -2396.8460f, 6.0006f);
        internal static readonly Vector3 HarbourPosition =
            new Vector3(-322.2098f, -2371.4510f, 0.3184f);
        internal static readonly Vector3 MarinaAccessPosition =
            new Vector3(-812.0333f, -1400.0630f, 5.0005f);
        internal static readonly Vector3 MarinaPosition =
            new Vector3(-815.5561f, -1449.9360f, -0.4744f);

        private static readonly string HARBOUR_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_harbour.json");

        private static readonly Dictionary<string, List<StoredVehicle>>
            _harbourStored = new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL, new List<StoredVehicle>() },
                { KEY_FRANKLIN, new List<StoredVehicle>() },
                { KEY_TREVOR, new List<StoredVehicle>() },
            };

        private static bool _harbourInitialized;
        private static bool _harbourListRequested;
        private static int _activeHarbourLocation;
        private static Blip _harbourAccessBlip;
        private static Blip _harbourVehicleBlip;
        private static Blip _marinaAccessBlip;
        private static Blip _marinaVehicleBlip;

        internal static void InitializeHarbour()
        {
            if (_harbourInitialized) return;
            try
            {
                HarbourLoad();
                int count = 0;
                foreach (List<StoredVehicle> list in _harbourStored.Values)
                    count += list.Count;

                _harbourAccessBlip = World.CreateBlip(HarbourAccessPosition);
                _harbourAccessBlip.Sprite = BlipSprite.Marina;
                _harbourAccessBlip.Color = CharacterBlipColor();
                _harbourAccessBlip.Name = "ALLIN1 Harbour (Boat List)";
                _harbourAccessBlip.IsShortRange = true;

                _harbourVehicleBlip = World.CreateBlip(HarbourPosition);
                _harbourVehicleBlip.Sprite = BlipSprite.Marina;
                _harbourVehicleBlip.Color = CharacterBlipColor();
                _harbourVehicleBlip.Name = "ALLIN1 Harbour (Store Boat)";
                _harbourVehicleBlip.IsShortRange = true;

                _marinaAccessBlip = World.CreateBlip(MarinaAccessPosition);
                _marinaAccessBlip.Sprite = BlipSprite.Marina;
                _marinaAccessBlip.Color = CharacterBlipColor();
                _marinaAccessBlip.Name = "ALLIN1 Puerto Del Sol Marina (Boat List)";
                _marinaAccessBlip.IsShortRange = true;

                _marinaVehicleBlip = World.CreateBlip(MarinaPosition);
                _marinaVehicleBlip.Sprite = BlipSprite.Marina;
                _marinaVehicleBlip.Color = CharacterBlipColor();
                _marinaVehicleBlip.Name = "ALLIN1 Puerto Del Sol Marina (Store Boat)";
                _marinaVehicleBlip.IsShortRange = true;

                Log($"Los Santos Harbour initialized ({count} stored boats)");
            }
            catch (Exception ex)
            {
                LogException("InitializeHarbour", ex);
            }
            _harbourInitialized = true;
        }

        internal static bool IsHarbourVehicleEligible(string model) =>
            HarbourPolicy.IsEligible(model);

        internal static int GetHarbourUsedSlots()
        {
            return _harbourStored.TryGetValue(CharacterKey(), out var list)
                ? list.Count : 0;
        }

        internal static int GetHarbourCapacity() => HARBOUR_SLOT_COUNT;

        internal static List<StoredVehicle> GetHarbourStoredVehicles()
        {
            return _harbourStored.TryGetValue(CharacterKey(), out var list)
                ? list : new List<StoredVehicle>();
        }

        internal static bool DeliverToHarbour(
            string model, int color1, int color2)
        {
            if (!HarbourPolicy.IsEligible(model)) return false;
            string key = CharacterKey();
            if (!_harbourStored.TryGetValue(key, out var list) ||
                list.Count >= HARBOUR_SLOT_COUNT) return false;

            int slot = FindHarbourSlot(list);
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
            if (!HarbourSave())
            {
                list.Remove(stored);
                return false;
            }
            Log($"DeliverToHarbour: {model} -> slot {slot}");
            return true;
        }

        internal static bool RemoveHarbourVehicle(int listIndex)
        {
            string key = CharacterKey();
            if (!_harbourStored.TryGetValue(key, out var list) ||
                listIndex < 0 || listIndex >= list.Count) return false;
            StoredVehicle stored = list[listIndex];
            list.RemoveAt(listIndex);
            if (!HarbourSave())
            {
                list.Insert(listIndex, stored);
                return false;
            }
            Log($"RemoveHarbourVehicle: {stored.Model}");
            return true;
        }

        internal static bool RetrieveHarbourVehicle(int listIndex)
        {
            string key = CharacterKey();
            if (!_harbourStored.TryGetValue(key, out var list) ||
                listIndex < 0 || listIndex >= list.Count) return false;
            Vector3 spawnPosition = HarbourSpawnPosition(_activeHarbourLocation);
            float spawnHeading = HarbourSpawnHeading(_activeHarbourLocation);
            if (!IsHarbourClear(spawnPosition))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The harbour launch is blocked.~w~ Move the boat first.",
                    3500);
                return false;
            }

            StoredVehicle stored = list[listIndex];
            Vehicle boat = null;
            bool removedFromStorage = false;
            try
            {
                Model model = GetStoredModel(stored);
                model.Request(10000);
                if (!model.IsLoaded) return false;

                boat = World.CreateVehicle(
                    model, spawnPosition, spawnHeading);
                model.MarkAsNoLongerNeeded();
                if (boat == null) return false;
                ApplyVehicleState(boat, stored);
                boat.IsPersistent = true;
                boat.IsEngineRunning = false;

                list.RemoveAt(listIndex);
                removedFromStorage = true;
                if (!HarbourSave())
                {
                    list.Insert(listIndex, stored);
                    removedFromStorage = false;
                    boat.Delete();
                    return false;
                }

                Ped player = Game.Player.Character;
                BeginGarageBlackTransition("RetrieveHarbourVehicle");
                player.SetIntoVehicle(boat, VehicleSeat.Driver);
                CompleteGarageBlackTransition(
                    "RetrieveHarbourVehicle", player, boat, () => true);
                Log($"RetrieveHarbourVehicle: {stored.Model} from slot {stored.Slot}");
                return true;
            }
            catch (Exception ex)
            {
                if (boat != null && boat.Exists()) boat.Delete();
                if (removedFromStorage)
                {
                    list.Insert(Math.Min(listIndex, list.Count), stored);
                    HarbourSave();
                }
                LogException($"RetrieveHarbourVehicle({stored.Model})", ex);
                return false;
            }
        }

        internal static bool ConsumeHarbourListRequest()
        {
            bool requested = _harbourListRequested;
            _harbourListRequested = false;
            return requested;
        }

        internal static void OnHarbourTick()
        {
            if (!_harbourInitialized || _transitionInProgress || Game.IsLoading)
                return;

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead ||
                !GbayShop.TryGetCurrentCharacter(out _)) return;

            if (!player.IsInVehicle())
            {
                for (int location = 0; location < 2; location++)
                {
                    Vector3 accessPosition = HarbourPedPosition(location);
                    World.DrawMarker(MarkerType.VerticalCylinder,
                        accessPosition - new Vector3(0f, 0f, 0.9f),
                        Vector3.Zero, Vector3.Zero,
                        new Vector3(1.5f, 1.5f, 1.2f),
                        CharacterMarkerColor());
                    if (player.Position.DistanceTo(accessPosition) <
                        HARBOUR_ACCESS_RADIUS)
                    {
                        GTA.UI.Screen.ShowHelpTextThisFrame(
                            "Press ~INPUT_CONTEXT~ to access your boat list.");
                        if (Game.IsControlJustPressed(Control.Context))
                        {
                            _activeHarbourLocation = location;
                            _harbourListRequested = true;
                        }
                    }
                }
                return;
            }

            Vehicle boat = player.CurrentVehicle;
            if (boat == null || !boat.Exists() || !IsBoat(boat)) return;

            int storeLocation = -1;
            for (int location = 0; location < 2; location++)
            {
                Vector3 spawnPosition = HarbourSpawnPosition(location);
                World.DrawMarker(MarkerType.VerticalCylinder,
                    spawnPosition - new Vector3(0f, 0f, 1f),
                    Vector3.Zero, Vector3.Zero,
                    new Vector3(12f, 12f, 1.5f), CharacterMarkerColor());
                if (boat.Position.DistanceTo(spawnPosition) <
                    HARBOUR_STORE_RADIUS) storeLocation = location;
            }
            if (storeLocation < 0) return;

            int used = GetHarbourUsedSlots();
            if (used >= HARBOUR_SLOT_COUNT)
            {
                GTA.UI.Screen.ShowHelpTextThisFrame(
                    $"The harbour is full ({used}/{HARBOUR_SLOT_COUNT}).");
                return;
            }

            GTA.UI.Screen.ShowHelpTextThisFrame(
                "Press ~INPUT_CONTEXT~ to store this boat.");
            if (Game.IsControlJustPressed(Control.Context))
                StoreCurrentBoat(boat, storeLocation);
        }

        private static bool StoreCurrentBoat(Vehicle boat, int location)
        {
            string key = CharacterKey();
            if (!_harbourStored.TryGetValue(key, out var list) ||
                list.Count >= HARBOUR_SLOT_COUNT) return false;

            int hash = boat.Model.Hash;
            string modelName = _hashToSpawnName != null &&
                _hashToSpawnName.TryGetValue(hash, out string knownName)
                ? knownName
                : Function.Call<string>(
                    Hash.GET_DISPLAY_NAME_FROM_VEHICLE_MODEL, (uint)hash)
                    ?.ToLowerInvariant();
            if (string.IsNullOrWhiteSpace(modelName)) modelName = hash.ToString();

            int slot = FindHarbourSlot(list);
            if (slot < 0) return false;
            StoredVehicle stored = CaptureVehicleState(boat, modelName, slot);
            list.Add(stored);
            if (!HarbourSave())
            {
                list.Remove(stored);
                return false;
            }

            try
            {
                Ped player = Game.Player.Character;
                Vector3 accessPosition = HarbourPedPosition(location);
                BeginGarageBlackTransition("StoreHarbourVehicle");
                Function.Call(Hash.TASK_LEAVE_VEHICLE, player, boat, 16);
                Script.Wait(0);
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    accessPosition.X, accessPosition.Y,
                    accessPosition.Z + 0.2f,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING,
                    player, HarbourPedHeading(location));
                boat.IsPersistent = true;
                boat.Delete();
                CompleteGarageBlackTransition(
                    "StoreHarbourVehicle", player, null, () => true);

                string display = GetVehicleDisplayName(modelName, hash);
                GTA.UI.Screen.ShowSubtitle(
                    $"~g~{display}~w~ stored at {HarbourLocationName(location)} " +
                    $"({list.Count}/{HARBOUR_SLOT_COUNT}).", 4000);
                Log($"StoreHarbourVehicle: {modelName} -> slot {slot}");
                return true;
            }
            catch (Exception ex)
            {
                list.Remove(stored);
                HarbourSave();
                LogException($"StoreHarbourVehicle({modelName})", ex);
                Function.Call(Hash.DO_SCREEN_FADE_IN, 0);
                return false;
            }
        }

        private static bool IsBoat(Vehicle vehicle)
        {
            try
            {
                return vehicle != null && vehicle.Exists() &&
                    Function.Call<bool>(Hash.IS_THIS_MODEL_A_BOAT,
                        (uint)vehicle.Model.Hash);
            }
            catch { return false; }
        }

        private static Vector3 HarbourPedPosition(int location) =>
            location == 1 ? MarinaAccessPosition : HarbourAccessPosition;

        private static Vector3 HarbourSpawnPosition(int location) =>
            location == 1 ? MarinaPosition : HarbourPosition;

        private static float HarbourPedHeading(int location) =>
            location == 1 ? MARINA_ACCESS_HEADING : HARBOUR_ACCESS_HEADING;

        private static float HarbourSpawnHeading(int location) =>
            location == 1 ? MARINA_SPAWN_HEADING : HARBOUR_SPAWN_HEADING;

        private static string HarbourLocationName(int location) =>
            location == 1 ? "Puerto Del Sol Marina" : "Los Santos Harbour";

        private static bool IsHarbourClear(Vector3 spawnPosition)
        {
            foreach (Vehicle vehicle in World.GetNearbyVehicles(
                spawnPosition, HARBOUR_STORE_RADIUS))
                if (vehicle != null && vehicle.Exists()) return false;
            return true;
        }

        private static int FindHarbourSlot(List<StoredVehicle> list)
        {
            for (int slot = 0; slot < HARBOUR_SLOT_COUNT; slot++)
            {
                bool used = false;
                foreach (StoredVehicle stored in list)
                    if (stored.Slot == slot) { used = true; break; }
                if (!used) return slot;
            }
            return -1;
        }

        private static void HarbourLoad()
        {
            string loadPath = File.Exists(HARBOUR_SAVE_PATH)
                ? HARBOUR_SAVE_PATH : HARBOUR_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath)) return;
            try
            {
                HarbourParseJson(File.ReadAllText(loadPath));
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                    HarbourSave();
            }
            catch (Exception ex)
            {
                LogException("HarbourLoad", ex);
                string backup = HARBOUR_SAVE_PATH + ".bak";
                if (loadPath == HARBOUR_SAVE_PATH && File.Exists(backup))
                {
                    try { HarbourParseJson(File.ReadAllText(backup)); }
                    catch (Exception backupEx)
                    {
                        LogException("HarbourLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool HarbourSave()
        {
            return StageOrWriteVehicleSave(
                HARBOUR_SAVE_PATH, HarbourBuildJson, "HarbourSave");
        }

        private static string HarbourBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");
            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");
                if (_harbourStored.TryGetValue(key, out var list) &&
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

        private static void HarbourParseJson(string json)
        {
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR },
                HARBOUR_SLOT_COUNT);
            foreach (var entry in parsed)
                _harbourStored[entry.Key] = entry.Value;
        }
    }

    internal static class HarbourPolicy
    {
        internal static bool IsEligible(string model)
        {
            if (string.IsNullOrWhiteSpace(model)) return false;
            foreach (string boat in VehicleList.Boats)
                if (string.Equals(model, boat,
                    StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }
    }
}
