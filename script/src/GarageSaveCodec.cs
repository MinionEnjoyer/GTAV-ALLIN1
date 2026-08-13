using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Web.Script.Serialization;

namespace ALLIN1
{
    /// <summary>
    /// Strict, side-effect-free decoder for every garage vehicle save.
    /// Parsing completes into a new dictionary before callers replace live
    /// state, so malformed or partially written JSON cannot empty a garage.
    /// </summary>
    internal static class GarageSaveCodec
    {
        private const int MaxJsonBytes = 2 * 1024 * 1024;
        private const int MaxModelLength = 64;
        private const int MaxPlateLength = 32;
        private const int MaxModSlots = 64;
        private const int MaxExtras = 32;

        internal static Dictionary<string, List<GarageManager.StoredVehicle>> Parse(
            string json, IReadOnlyList<string> characterKeys, int slotCount)
        {
            if (string.IsNullOrWhiteSpace(json))
                throw new InvalidDataException("Garage save is empty.");
            if (json.Length > MaxJsonBytes)
                throw new InvalidDataException("Garage save exceeds the supported size.");
            if (characterKeys == null || characterKeys.Count == 0)
                throw new ArgumentException("At least one garage character key is required.", nameof(characterKeys));
            if (slotCount <= 0)
                throw new ArgumentOutOfRangeException(nameof(slotCount));

            object decoded;
            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = MaxJsonBytes,
                    RecursionLimit = 32,
                };
                decoded = serializer.DeserializeObject(json);
            }
            catch (Exception ex) when (ex is ArgumentException || ex is InvalidOperationException)
            {
                throw new InvalidDataException("Garage save is not valid JSON.", ex);
            }

            if (!(decoded is Dictionary<string, object> root))
                throw new InvalidDataException("Garage save root must be a JSON object.");

            var parsed = new Dictionary<string, List<GarageManager.StoredVehicle>>(
                StringComparer.OrdinalIgnoreCase);
            foreach (string key in characterKeys)
            {
                if (!root.TryGetValue(key, out object rawVehicles))
                    throw new InvalidDataException($"Garage save is missing required collection '{key}'.");

                List<object> entries = RequireArray(rawVehicles, key, slotCount);
                var vehicles = new List<GarageManager.StoredVehicle>(entries.Count);
                var occupiedSlots = new HashSet<int>();
                for (int index = 0; index < entries.Count; index++)
                {
                    if (!(entries[index] is Dictionary<string, object> record))
                        throw new InvalidDataException($"{key}[{index}] must be a JSON object.");

                    GarageManager.StoredVehicle vehicle = ParseVehicle(record, $"{key}[{index}]");
                    if (vehicle.Slot < 0 || vehicle.Slot >= slotCount)
                        throw new InvalidDataException(
                            $"{key}[{index}].slot {vehicle.Slot} is outside 0-{slotCount - 1}.");
                    if (!occupiedSlots.Add(vehicle.Slot))
                        throw new InvalidDataException($"{key} contains duplicate slot {vehicle.Slot}.");
                    vehicles.Add(vehicle);
                }
                parsed.Add(key, vehicles);
            }

            return parsed;
        }

        private static GarageManager.StoredVehicle ParseVehicle(
            Dictionary<string, object> record, string path)
        {
            string model = RequireString(record, "model", path, MaxModelLength);
            int slot = RequireInt(record, "slot", path);
            var vehicle = new GarageManager.StoredVehicle
            {
                Model = model,
                Slot = slot,
                ModelHash = OptionalInt(record, "modelHash", path),
                Color1 = OptionalInt(record, "color1", path),
                Color2 = OptionalInt(record, "color2", path),
                WheelType = OptionalInt(record, "wheelType", path),
                WindowTint = OptionalInt(record, "windowTint", path),
                Livery = OptionalInt(record, "livery", path),
                PlateStyle = OptionalInt(record, "plateStyle", path),
                PearlescentColor = OptionalInt(record, "pearlescent", path),
                RimColor = OptionalInt(record, "rimColor", path),
            };

            if (record.TryGetValue("plate", out object plate))
                vehicle.PlateText = RequireStringValue(plate, path + ".plate", MaxPlateLength, true);
            vehicle.Mods = OptionalIntArray(record, "mods", path, MaxModSlots);
            int[] toggleValues = OptionalIntArray(record, "modToggles", path, MaxModSlots);
            if (toggleValues != null)
            {
                vehicle.ModToggles = new bool[toggleValues.Length];
                for (int i = 0; i < toggleValues.Length; i++)
                {
                    if (toggleValues[i] != 0 && toggleValues[i] != 1)
                        throw new InvalidDataException($"{path}.modToggles[{i}] must be 0 or 1.");
                    vehicle.ModToggles[i] = toggleValues[i] == 1;
                }
            }

            vehicle.NeonEnabled = OptionalIntArray(record, "neonEnabled", path, 4);
            vehicle.NeonColor = OptionalRgb(record, "neonColor", path);
            vehicle.TyreSmokeColor = OptionalRgb(record, "tyreSmokeColor", path);
            vehicle.Extras = OptionalIntArray(record, "extras", path, MaxExtras);
            vehicle.CustomPrimary = OptionalRgb(record, "customPrimary", path);
            vehicle.CustomPrimaryColor = vehicle.CustomPrimary != null;
            vehicle.CustomSecondary = OptionalRgb(record, "customSecondary", path);
            vehicle.CustomSecondaryColor = vehicle.CustomSecondary != null;
            return vehicle;
        }

        private static List<object> RequireArray(object value, string path, int maxLength)
        {
            if (value is string || !(value is IEnumerable enumerable))
                throw new InvalidDataException($"{path} must be a JSON array.");
            var result = new List<object>();
            foreach (object item in enumerable)
            {
                if (result.Count >= maxLength)
                    throw new InvalidDataException($"{path} contains more than {maxLength} entries.");
                result.Add(item);
            }
            return result;
        }

        private static string RequireString(
            Dictionary<string, object> record, string key, string path, int maxLength)
        {
            if (!record.TryGetValue(key, out object value))
                throw new InvalidDataException($"{path}.{key} is required.");
            return RequireStringValue(value, path + "." + key, maxLength, false);
        }

        private static string RequireStringValue(object value, string path, int maxLength, bool allowEmpty)
        {
            if (!(value is string text) || (!allowEmpty && string.IsNullOrWhiteSpace(text)))
                throw new InvalidDataException($"{path} must be a non-empty string.");
            if (text.Length > maxLength)
                throw new InvalidDataException($"{path} exceeds {maxLength} characters.");
            return text;
        }

        private static int RequireInt(Dictionary<string, object> record, string key, string path)
        {
            if (!record.TryGetValue(key, out object value))
                throw new InvalidDataException($"{path}.{key} is required.");
            return RequireIntValue(value, path + "." + key);
        }

        private static int OptionalInt(Dictionary<string, object> record, string key, string path)
        {
            return record.TryGetValue(key, out object value)
                ? RequireIntValue(value, path + "." + key)
                : 0;
        }

        private static int RequireIntValue(object value, string path)
        {
            try
            {
                switch (value)
                {
                    case int integer:
                        return integer;
                    case long longValue when longValue >= int.MinValue && longValue <= int.MaxValue:
                        return (int)longValue;
                    case decimal decimalValue when decimal.Truncate(decimalValue) == decimalValue &&
                                                   decimalValue >= int.MinValue && decimalValue <= int.MaxValue:
                        return decimal.ToInt32(decimalValue);
                    default:
                        throw new InvalidDataException($"{path} must be a 32-bit integer.");
                }
            }
            catch (OverflowException ex)
            {
                throw new InvalidDataException($"{path} is outside the supported integer range.", ex);
            }
        }

        private static int[] OptionalIntArray(
            Dictionary<string, object> record, string key, string path, int maxLength)
        {
            if (!record.TryGetValue(key, out object value)) return null;
            List<object> values = RequireArray(value, path + "." + key, maxLength);
            var result = new int[values.Count];
            for (int i = 0; i < values.Count; i++)
                result[i] = RequireIntValue(values[i], $"{path}.{key}[{i}]");
            return result;
        }

        private static int[] OptionalRgb(
            Dictionary<string, object> record, string key, string path)
        {
            int[] values = OptionalIntArray(record, key, path, 3);
            if (values == null) return null;
            if (values.Length != 3)
                throw new InvalidDataException($"{path}.{key} must contain exactly three values.");
            for (int i = 0; i < values.Length; i++)
                if (values[i] < 0 || values[i] > 255)
                    throw new InvalidDataException($"{path}.{key}[{i}] must be between 0 and 255.");
            return values;
        }
    }
}
