using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Web.Script.Serialization;

namespace RealisticSuppressors
{
    internal static class SuppressorStatePolicy
    {
        internal const float NewCondition = 1f;

        internal static float ClampDurability(float value)
        {
            if (float.IsNaN(value)) return NewCondition;
            if (value <= 0f) return 0f;
            if (value >= NewCondition) return NewCondition;
            return value;
        }

        internal static string ComponentKey(
            string weaponName, uint componentHash)
        {
            return (weaponName ?? "").Trim().ToUpperInvariant() + ":" +
                componentHash.ToString("X8", CultureInfo.InvariantCulture);
        }

        internal static bool IsReplacementAttachment(
            bool broken, float persistedDurability,
            bool purchaseNotificationObserved,
            bool observedAbsentAfterBreak)
        {
            if (!broken) return false;
            if (ClampDurability(persistedDurability) > 0f)
                return purchaseNotificationObserved ||
                    observedAbsentAfterBreak;
            return purchaseNotificationObserved ||
                observedAbsentAfterBreak;
        }
    }

    internal sealed class SuppressorStateStore
    {
        private sealed class StateDocument
        {
            public int schema_version { get; set; } = 1;
            public Dictionary<string, Dictionary<string, float>> characters
                { get; set; } =
                    new Dictionary<string, Dictionary<string, float>>(
                        StringComparer.OrdinalIgnoreCase);
        }

        private static readonly JavaScriptSerializer Json =
            new JavaScriptSerializer();
        private readonly string _path;
        private StateDocument _committed;
        private StateDocument _working;
        private bool _dirty;

        internal SuppressorStateStore(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new ArgumentException(
                    "A suppressor-state path is required.", nameof(path));
            _path = Path.GetFullPath(path);
            _committed = Load(_path);
            _working = Clone(_committed);
        }

        internal static string DefaultPath
        {
            get
            {
                string root = Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData);
                return Path.Combine(root, "RealisticSuppressors",
                    "condition.json");
            }
        }

        internal int Generation { get; private set; }
        internal bool Dirty => _dirty;

        internal float GetDurability(
            string character, string weaponName, uint componentHash)
        {
            string characterKey = NormalizeCharacter(character);
            if (characterKey.Length == 0)
                return SuppressorStatePolicy.NewCondition;
            if (!_working.characters.TryGetValue(
                    characterKey,
                    out Dictionary<string, float> components) ||
                !components.TryGetValue(
                    SuppressorStatePolicy.ComponentKey(
                        weaponName, componentHash),
                    out float durability))
                return SuppressorStatePolicy.NewCondition;
            return SuppressorStatePolicy.ClampDurability(durability);
        }

        internal bool SetDurability(
            string character, string weaponName, uint componentHash,
            float durability)
        {
            string characterKey = NormalizeCharacter(character);
            if (characterKey.Length == 0 ||
                string.IsNullOrWhiteSpace(weaponName))
                return false;
            if (!_working.characters.TryGetValue(
                    characterKey,
                    out Dictionary<string, float> components))
            {
                components = new Dictionary<string, float>(
                    StringComparer.OrdinalIgnoreCase);
                _working.characters[characterKey] = components;
            }
            string componentKey = SuppressorStatePolicy.ComponentKey(
                weaponName, componentHash);
            float normalized = SuppressorStatePolicy.ClampDurability(
                durability);
            if (components.TryGetValue(componentKey, out float current) &&
                SuppressorStatePolicy.ClampDurability(current) == normalized &&
                current == normalized)
                return false;
            components[componentKey] = normalized;
            _dirty = true;
            return true;
        }

        internal void Commit()
        {
            if (_dirty)
            {
                Save(_path, _working);
                _committed = Clone(_working);
                _dirty = false;
            }
        }

        internal void Discard()
        {
            _working = Clone(_committed);
            _dirty = false;
            unchecked { Generation++; }
        }

        private static StateDocument Load(string path)
        {
            if (!File.Exists(path)) return Empty();
            try
            {
                StateDocument loaded = Json.Deserialize<StateDocument>(
                    File.ReadAllText(path));
                return Normalize(loaded);
            }
            catch (Exception ex)
            {
                ClientLog.Error("STATE", "state_load_failed", ex);
                return Empty();
            }
        }

        private static void Save(string path, StateDocument state)
        {
            string directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(directory))
                Directory.CreateDirectory(directory);
            string temporary = path + ".tmp";
            File.WriteAllText(temporary, Json.Serialize(Normalize(state)));
            if (File.Exists(path))
                File.Replace(temporary, path, path + ".bak", true);
            else
                File.Move(temporary, path);
        }

        private static StateDocument Clone(StateDocument state)
        {
            return Normalize(Json.Deserialize<StateDocument>(
                Json.Serialize(Normalize(state))));
        }

        private static StateDocument Normalize(StateDocument state)
        {
            var result = Empty();
            if (state?.characters == null) return result;
            foreach (KeyValuePair<string, Dictionary<string, float>>
                character in state.characters)
            {
                string characterKey = NormalizeCharacter(character.Key);
                if (characterKey.Length == 0 || character.Value == null)
                    continue;
                var components = new Dictionary<string, float>(
                    StringComparer.OrdinalIgnoreCase);
                foreach (KeyValuePair<string, float> component in
                    character.Value)
                {
                    if (string.IsNullOrWhiteSpace(component.Key)) continue;
                    components[component.Key.Trim().ToUpperInvariant()] =
                        SuppressorStatePolicy.ClampDurability(
                            component.Value);
                }
                result.characters[characterKey] = components;
            }
            return result;
        }

        private static StateDocument Empty() => new StateDocument();

        private static string NormalizeCharacter(string value)
        {
            string normalized = (value ?? "").Trim().ToLowerInvariant();
            switch (normalized)
            {
                case "michael":
                case "franklin":
                case "trevor":
                    return normalized;
                default:
                    return "";
            }
        }
    }
}
