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
    /// One-slot, per-character aircraft storage on the Galaxy Super Yacht.
    /// GTA Online's yacht packages provide two helipad aircraft: the Swift
    /// Deluxe (Pisces) and SuperVolito Carbon (Aquarius). The helipad does not
    /// accept the player's general personal-aircraft catalog.
    /// </summary>
    internal static partial class GarageManager
    {
        private const int YACHT_HELIPAD_SLOT_COUNT = 1;
        private const float YACHT_HELIPAD_HEADING = 255.76f;
        private const float YACHT_HELIPAD_DECK_Z = 11.9807f;
        private const float YACHT_HELIPAD_SPAWN_DISTANCE = 500f;
        private const int YACHT_HELIPAD_RESPAWN_DELAY_MS = 15000;

        internal static readonly Vector3 YachtHelipadPosition =
            new Vector3(-2043.9200f, -1031.4230f, YACHT_HELIPAD_DECK_Z);

        private static readonly string YACHT_HELIPAD_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_yacht_helipad.json");

        private static readonly Dictionary<string, List<StoredVehicle>>
            _yachtHelipadStored =
                new Dictionary<string, List<StoredVehicle>>
                {
                    { KEY_MICHAEL, new List<StoredVehicle>() },
                    { KEY_FRANKLIN, new List<StoredVehicle>() },
                    { KEY_TREVOR, new List<StoredVehicle>() },
                };

        private static Vehicle _yachtHelipadHandle;
        private static string _yachtHelipadHandleCharacter = "";
        private static bool _yachtHelipadInitialized;
        private static int _yachtHelipadNextRespawn;

        internal static void InitializeYachtHelipad()
        {
            if (_yachtHelipadInitialized) return;
            try
            {
                YachtHelipadLoad();
                int count = 0;
                foreach (List<StoredVehicle> list in _yachtHelipadStored.Values)
                    count += list.Count;
                Log($"Yacht Helipad initialized ({count} stored aircraft)");
            }
            catch (Exception ex)
            {
                LogException("InitializeYachtHelipad", ex);
            }
            _yachtHelipadInitialized = true;
        }

        internal static bool IsYachtHelipadVehicleEligible(string model) =>
            YachtHelipadPolicy.IsEligible(model);

        internal static int GetYachtHelipadUsedSlots()
        {
            return _yachtHelipadStored.TryGetValue(CharacterKey(), out var list)
                ? list.Count : 0;
        }

        internal static int GetYachtHelipadCapacity() =>
            YACHT_HELIPAD_SLOT_COUNT;

        internal static List<StoredVehicle> GetYachtHelipadStoredVehicles()
        {
            return _yachtHelipadStored.TryGetValue(CharacterKey(), out var list)
                ? list : new List<StoredVehicle>();
        }

        internal static bool DeliverToYachtHelipad(
            string model, int color1, int color2)
        {
            if (!YachtManager.FeaturesUnlocked ||
                !YachtHelipadPolicy.IsEligible(model)) return false;
            string key = CharacterKey();
            if (!_yachtHelipadStored.TryGetValue(key, out var list) ||
                list.Count >= YACHT_HELIPAD_SLOT_COUNT) return false;

            var stored = new StoredVehicle
            {
                Model = model,
                ModelHash = Game.GenerateHash(model),
                Slot = 0,
                Color1 = color1,
                Color2 = color2,
            };
            list.Add(stored);
            if (!YachtHelipadSave())
            {
                list.Remove(stored);
                return false;
            }

            if (YachtManager.IsWorldStreamed)
                SpawnYachtHelipadVehicle(stored, key);
            Log($"DeliverToYachtHelipad: {model} -> slot 0");
            return true;
        }

        internal static bool RemoveYachtHelipadVehicle(int listIndex)
        {
            string key = CharacterKey();
            if (!_yachtHelipadStored.TryGetValue(key, out var list) ||
                listIndex < 0 || listIndex >= list.Count) return false;
            StoredVehicle stored = list[listIndex];
            if (string.Equals(_yachtHelipadHandleCharacter, key,
                    StringComparison.OrdinalIgnoreCase))
                DeleteYachtHelipadHandle();
            list.RemoveAt(listIndex);
            if (!YachtHelipadSave())
            {
                list.Insert(listIndex, stored);
                return false;
            }
            Log($"RemoveYachtHelipadVehicle: {stored.Model}");
            return true;
        }

        internal static void OnYachtHelipadTick()
        {
            if (!_yachtHelipadInitialized) return;

            if (_yachtHelipadHandle != null && !_yachtHelipadHandle.Exists())
            {
                _yachtHelipadHandle = null;
                _yachtHelipadHandleCharacter = "";
                _yachtHelipadNextRespawn = Game.GameTime +
                    YACHT_HELIPAD_RESPAWN_DELAY_MS;
            }

            string key = CharacterKey();
            if (_yachtHelipadHandle != null && _yachtHelipadHandle.Exists())
            {
                if (!string.Equals(_yachtHelipadHandleCharacter, key,
                        StringComparison.OrdinalIgnoreCase) &&
                    Game.Player.Character.CurrentVehicle != _yachtHelipadHandle)
                    DeleteYachtHelipadHandle();
                else
                {
                    bool occupied = Game.Player.Character.CurrentVehicle ==
                        _yachtHelipadHandle;
                    _yachtHelipadHandle.IsPositionFrozen = !occupied &&
                        _yachtHelipadHandle.Position.DistanceTo(
                            YachtHelipadPosition) < 8f;
                }
            }

            if (!YachtManager.FeaturesUnlocked ||
                !YachtManager.IsWorldStreamed) return;

            List<StoredVehicle> list = GetYachtHelipadStoredVehicles();
            if (list.Count == 0)
            {
                DrawYachtHelipadMarker();
                return;
            }
            if (_yachtHelipadHandle != null && _yachtHelipadHandle.Exists())
                return;
            if (Game.GameTime < _yachtHelipadNextRespawn ||
                Game.Player.Character.Position.DistanceTo(YachtHelipadPosition) >
                    YACHT_HELIPAD_SPAWN_DISTANCE) return;

            SpawnYachtHelipadVehicle(list[0], key);
        }

        internal static void OnYachtWorldUnloaded()
        {
            if (_yachtHelipadHandle == null || !_yachtHelipadHandle.Exists())
                return;
            Ped player = Game.Player.Character;
            bool playerUsing = player != null && player.Exists() &&
                player.CurrentVehicle == _yachtHelipadHandle;
            bool flownAway = _yachtHelipadHandle.Position.DistanceTo(
                YachtHelipadPosition) > 100f;
            if (!playerUsing && !flownAway)
                DeleteYachtHelipadHandle();
        }

        private static void DrawYachtHelipadMarker()
        {
            World.DrawMarker(MarkerType.VerticalCylinder,
                YachtHelipadPosition - new Vector3(0f, 0f, 0.8f),
                Vector3.Zero, Vector3.Zero, new Vector3(3f, 3f, 0.35f),
                CharacterMarkerColor());
            if (Game.Player.Character.Position.DistanceTo(YachtHelipadPosition) < 4f)
                GTA.UI.Screen.ShowHelpTextThisFrame(
                    "Purchase a Swift Deluxe or SuperVolito Carbon from GBAY and select Yacht Helipad.");
        }

        private static void SpawnYachtHelipadVehicle(
            StoredVehicle stored, string characterKey)
        {
            if (_yachtHelipadHandle != null && _yachtHelipadHandle.Exists())
                return;
            try
            {
                Model model = GetStoredModel(stored);
                model.Request(10000);
                if (!model.IsLoaded)
                {
                    Log($"SpawnYachtHelipadVehicle: model unavailable {stored.Model}");
                    return;
                }
                Vehicle vehicle = World.CreateVehicle(model,
                    YachtHelipadPosition + new Vector3(0f, 0f, 1.5f),
                    YACHT_HELIPAD_HEADING);
                model.MarkAsNoLongerNeeded();
                if (vehicle == null) return;
                ApplyVehicleState(vehicle, stored);
                vehicle.IsPersistent = true;
                vehicle.IsEngineRunning = false;
                var pad = new ParkingSlot(
                    YachtHelipadPosition.X, YachtHelipadPosition.Y,
                    YachtHelipadPosition.Z + 1.5f, YACHT_HELIPAD_HEADING,
                    YACHT_HELIPAD_DECK_Z);
                PlaceVehicleInParkingSpace(vehicle, pad, stored.Model, "YachtHelipad");
                vehicle.IsPositionFrozen = true;
                _yachtHelipadHandle = vehicle;
                _yachtHelipadHandleCharacter = characterKey;
                Log($"SpawnYachtHelipadVehicle: {stored.Model}");
            }
            catch (Exception ex)
            {
                LogException($"SpawnYachtHelipadVehicle({stored.Model})", ex);
            }
        }

        private static void DeleteYachtHelipadHandle()
        {
            if (_yachtHelipadHandle != null && _yachtHelipadHandle.Exists())
            {
                _yachtHelipadHandle.IsPersistent = true;
                _yachtHelipadHandle.Delete();
            }
            _yachtHelipadHandle = null;
            _yachtHelipadHandleCharacter = "";
        }

        private static void YachtHelipadUpdateStoredFromLive()
        {
            if (_yachtHelipadHandle == null || !_yachtHelipadHandle.Exists() ||
                string.IsNullOrEmpty(_yachtHelipadHandleCharacter)) return;
            if (!_yachtHelipadStored.TryGetValue(_yachtHelipadHandleCharacter,
                    out var list) || list.Count == 0) return;
            list[0] = CaptureVehicleState(
                _yachtHelipadHandle, list[0].Model, 0);
            YachtHelipadSave();
        }

        private static void YachtHelipadLoad()
        {
            string loadPath = File.Exists(YACHT_HELIPAD_SAVE_PATH)
                ? YACHT_HELIPAD_SAVE_PATH : YACHT_HELIPAD_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath)) return;
            try
            {
                YachtHelipadParseJson(File.ReadAllText(loadPath));
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                    YachtHelipadSave();
            }
            catch (Exception ex)
            {
                LogException("YachtHelipadLoad", ex);
                string backup = YACHT_HELIPAD_SAVE_PATH + ".bak";
                if (loadPath == YACHT_HELIPAD_SAVE_PATH && File.Exists(backup))
                {
                    try { YachtHelipadParseJson(File.ReadAllText(backup)); }
                    catch (Exception backupEx)
                    {
                        LogException("YachtHelipadLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool YachtHelipadSave()
        {
            return StageOrWriteVehicleSave(
                YACHT_HELIPAD_SAVE_PATH, YachtHelipadBuildJson,
                "YachtHelipadSave");
        }

        private static string YachtHelipadBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");
            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");
                if (_yachtHelipadStored.TryGetValue(key, out var list) &&
                    list.Count > 0)
                {
                    sb.AppendLine();
                    AppendDavisVehicleJson(sb, list[0]);
                    sb.Append("  ]");
                }
                else sb.Append("]");
                sb.AppendLine(k < keys.Length - 1 ? "," : "");
            }
            sb.AppendLine("}");
            return sb.ToString();
        }

        private static void YachtHelipadParseJson(string json)
        {
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR },
                YACHT_HELIPAD_SLOT_COUNT);
            foreach (var entry in parsed)
                _yachtHelipadStored[entry.Key] = entry.Value;
        }
    }

    internal static class YachtHelipadPolicy
    {
        internal static bool IsEligible(string model)
        {
            return string.Equals(model, "swift2",
                       StringComparison.OrdinalIgnoreCase) ||
                   string.Equals(model, "supervolito2",
                       StringComparison.OrdinalIgnoreCase);
        }
    }
}
