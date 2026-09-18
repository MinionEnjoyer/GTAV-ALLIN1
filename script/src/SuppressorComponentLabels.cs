using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace ALLIN1
{
    // Reader for receipt-installed known-can profiles. It supplies labels and
    // exact component/model bindings; GBAY still owns the native probe gate.
    internal static class SuppressorComponentLabels
    {
        private const int MaxBytes = 64 * 1024;
        private static readonly Regex Weapon = new Regex("^WEAPON_[A-Z0-9_]{1,90}$", RegexOptions.CultureInvariant);
        private static readonly Regex Component = new Regex("^COMPONENT_RSKC_[A-Z0-9_]{1,90}$", RegexOptions.CultureInvariant);
        private static readonly Regex ComponentModel = new Regex("^[a-z0-9_]{1,96}$", RegexOptions.CultureInvariant);
        private static readonly object Sync = new object();
        private static Dictionary<string, string> _labels;
        private static Dictionary<string, KnownCanBinding> _bindings;

        internal sealed class KnownCanBinding
        {
            internal string Weapon, Component, DisplayName, ExpectedComponentModel;
            internal int WeaponHash, ComponentHash, ExpectedComponentModelHash;
        }

        internal static string Resolve(int weaponHash, int componentHash, string fallback)
        {
            EnsureLoaded();
            lock (Sync)
                return _labels.TryGetValue(Key(weaponHash, componentHash), out var label) ? label : fallback;
        }

        internal static IReadOnlyDictionary<string, string> ParseForTests(string json) => Parse(json);

        internal static IReadOnlyList<KnownCanBinding> ParseBindingsForTests(string json) =>
            ParseBindings(json).Values.ToArray();

        internal static IReadOnlyList<KnownCanBinding> GetBindingsForWeapon(
            int weaponHash)
        {
            EnsureLoaded();
            lock (Sync)
                return _bindings.Values.Where(binding =>
                    binding.WeaponHash == weaponHash).ToArray();
        }

        // This stays pure so the native result can be verified independently
        // from profile parsing and never turns a profile into an equip action.
        internal static bool AcceptsExpectedComponentModel(bool weaponTakesComponent,
            int expectedComponentModelHash, int nativeComponentModelHash) =>
            weaponTakesComponent && expectedComponentModelHash != 0 &&
            expectedComponentModelHash == nativeComponentModelHash;

        private static void EnsureLoaded()
        {
            lock (Sync)
            {
                if (_labels != null) return;
                var merged = new Dictionary<string, string>(StringComparer.Ordinal);
                var bindings = new Dictionary<string, KnownCanBinding>(StringComparer.Ordinal);
                try
                {
                    string scripts = Allin1ExtensionApi.ResolveScriptsDirectory(
                        Allin1ExtensionApi.ResolveAssemblySourcePath(
                            typeof(SuppressorComponentLabels).Assembly),
                        AppDomain.CurrentDomain.BaseDirectory);
                    string basePath = Path.Combine(scripts, "RealisticSuppressors", "known-cans", "suppressor-profile.json");
                    TryMerge(merged, bindings, basePath, false);
                    string userPath = Path.Combine(scripts, "RealisticSuppressors", "user-profiles", "known-cans.json");
                    TryMerge(merged, bindings, userPath, true);
                }
                catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is InvalidDataException || ex is FormatException || ex is DecoderFallbackException)
                { merged.Clear(); bindings.Clear(); ClientLog.Warn("GBAY", "suppressor_component_labels_rejected", new Dictionary<string, object> { { "reason", ex.Message } }); }
                _labels = merged;
                _bindings = bindings;
                if (merged.Count > 0) ClientLog.Info("GBAY", "suppressor_component_labels_loaded", new Dictionary<string, object> { { "labels", merged.Count }, { "candidate_bindings", bindings.Count }, { "source", "schema3_known_cans" } });
            }
        }

        private static void TryMerge(Dictionary<string, string> target,
            Dictionary<string, KnownCanBinding> targetBindings,
            string path, bool overwrite)
        {
            if (!File.Exists(path)) return;
            try
            {
                string json = Read(path);
                Merge(target, Parse(json), overwrite);
                MergeBindings(targetBindings, ParseBindings(json), overwrite);
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is InvalidDataException || ex is FormatException || ex is DecoderFallbackException)
            {
                ClientLog.Warn("GBAY", "suppressor_component_labels_source_rejected",
                    new Dictionary<string, object> { { "path", Path.GetFileName(path) }, { "reason", ex.Message } });
            }
        }

        private static string Read(string path)
        {
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (stream.Length < 2 || stream.Length > MaxBytes) throw new InvalidDataException("Known-can profile exceeds byte limit.");
                var bytes = new byte[(int)stream.Length]; int offset = 0;
                while (offset < bytes.Length) { int read = stream.Read(bytes, offset, bytes.Length - offset); if (read == 0) throw new EndOfStreamException(); offset += read; }
                if (stream.ReadByte() != -1) throw new InvalidDataException("Known-can profile changed while reading.");
                int bom = bytes.Length >= 3 && bytes[0] == 239 && bytes[1] == 187 && bytes[2] == 191 ? 3 : 0;
                return new UTF8Encoding(false, true).GetString(bytes, bom, bytes.Length - bom);
            }
        }

        private static Dictionary<string, string> Parse(string json)
        {
            if (!(PortableJsonParser.Parse(json, MaxBytes) is Dictionary<string, object> root) ||
                !root.TryGetValue("schema_version", out var version) || !(version is int) || (int)version != 3 ||
                !root.TryGetValue("profiles", out var raw) || !(raw is object[] profiles) || profiles.Length > 64)
                throw new InvalidDataException("Known-can labels require schema 3 profiles.");
            var cans = new Dictionary<string, Dictionary<string, object>>(StringComparer.Ordinal);
            if (root.TryGetValue("cans", out var rawCans))
            {
                if (!(rawCans is Dictionary<string, object> definitions) || definitions.Count > 32) throw new InvalidDataException("Invalid reusable cans.");
                foreach (var entry in definitions) if (entry.Value is Dictionary<string, object> value) cans.Add(entry.Key, value); else throw new InvalidDataException("Invalid reusable can.");
            }
            var result = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var rawProfile in profiles)
            {
                if (!(rawProfile is Dictionary<string, object> profile)) throw new InvalidDataException("Invalid profile.");
                var row = new Dictionary<string, object>(StringComparer.Ordinal);
                if (profile.TryGetValue("can", out var canRef)) { if (!(canRef is string id) || !cans.TryGetValue(id, out var defaults)) throw new InvalidDataException("Undefined reusable can."); foreach (var item in defaults) row[item.Key] = item.Value; }
                foreach (var item in profile) if (item.Key != "can") row[item.Key] = item.Value;
                if (!Text(row, "weapon", 97, out var weapon) || !Text(row, "component", 100, out var component) || !Text(row, "display_name", 80, out var name) || !Weapon.IsMatch(weapon) || !Component.IsMatch(component)) continue;
                string key = Key(unchecked((int)RuntimeWeaponCatalog.WeaponHash(weapon)),
                    unchecked((int)RuntimeWeaponCatalog.WeaponHash(component)));
                if (result.ContainsKey(key)) throw new InvalidDataException("Duplicate known-can binding.");
                result.Add(key, name);
            }
            return result;
        }

        private static Dictionary<string, KnownCanBinding> ParseBindings(string json)
        {
            if (!(PortableJsonParser.Parse(json, MaxBytes) is Dictionary<string, object> root) ||
                !root.TryGetValue("schema_version", out var version) || !(version is int) ||
                (int)version != 3 || !root.TryGetValue("profiles", out var raw) ||
                !(raw is object[] profiles) || profiles.Length > 64)
                throw new InvalidDataException("Known-can labels require schema 3 profiles.");
            var cans = ReusableCans(root);
            var result = new Dictionary<string, KnownCanBinding>(StringComparer.Ordinal);
            foreach (var rawProfile in profiles)
            {
                if (!(rawProfile is Dictionary<string, object> profile)) throw new InvalidDataException("Invalid profile.");
                Dictionary<string, object> row = Flatten(profile, cans);
                if (!Text(row, "weapon", 97, out var weapon) ||
                    !Text(row, "component", 100, out var component) ||
                    !Text(row, "display_name", 80, out var name) ||
                    !Text(row, "component_model", 96, out var model) ||
                    !Weapon.IsMatch(weapon) || !Component.IsMatch(component) ||
                    !ComponentModel.IsMatch(model)) continue;
                int weaponHash = unchecked((int)RuntimeWeaponCatalog.WeaponHash(weapon));
                int componentHash = unchecked((int)RuntimeWeaponCatalog.WeaponHash(component));
                string key = Key(weaponHash, componentHash);
                if (result.ContainsKey(key)) throw new InvalidDataException("Duplicate known-can binding.");
                result.Add(key, new KnownCanBinding {
                    Weapon = weapon, Component = component, DisplayName = name,
                    ExpectedComponentModel = model, WeaponHash = weaponHash,
                    ComponentHash = componentHash,
                    ExpectedComponentModelHash = unchecked((int)RuntimeWeaponCatalog.WeaponHash(model)),
                });
            }
            return result;
        }

        private static Dictionary<string, Dictionary<string, object>> ReusableCans(
            Dictionary<string, object> root)
        {
            var cans = new Dictionary<string, Dictionary<string, object>>(StringComparer.Ordinal);
            if (!root.TryGetValue("cans", out var rawCans)) return cans;
            if (!(rawCans is Dictionary<string, object> definitions) || definitions.Count > 32) throw new InvalidDataException("Invalid reusable cans.");
            foreach (var entry in definitions)
                if (entry.Value is Dictionary<string, object> value) cans.Add(entry.Key, value);
                else throw new InvalidDataException("Invalid reusable can.");
            return cans;
        }

        private static Dictionary<string, object> Flatten(
            Dictionary<string, object> profile,
            Dictionary<string, Dictionary<string, object>> cans)
        {
            var row = new Dictionary<string, object>(StringComparer.Ordinal);
            if (profile.TryGetValue("can", out var canRef))
            {
                if (!(canRef is string id) || !cans.TryGetValue(id, out var defaults))
                    throw new InvalidDataException("Undefined reusable can.");
                foreach (var item in defaults) row[item.Key] = item.Value;
            }
            foreach (var item in profile) if (item.Key != "can") row[item.Key] = item.Value;
            return row;
        }
        private static bool Text(Dictionary<string, object> row, string key, int max, out string text)
        { text = null; return row.TryGetValue(key, out var raw) && raw is string value && value.Length > 0 && value.Length <= max && value == value.Trim() && !value.Any(char.IsControl) && (text = value) != null; }
        private static void Merge(Dictionary<string,string> target, Dictionary<string,string> input, bool overwrite)
        { foreach (var item in input) { if (target.ContainsKey(item.Key) && !overwrite) throw new InvalidDataException("Duplicate known-can binding."); target[item.Key] = item.Value; } }
        private static void MergeBindings(Dictionary<string, KnownCanBinding> target,
            Dictionary<string, KnownCanBinding> input, bool overwrite)
        { foreach (var item in input) { if (target.ContainsKey(item.Key) && !overwrite) throw new InvalidDataException("Duplicate known-can binding."); target[item.Key] = item.Value; } }
        private static string Key(int weapon, int component) => unchecked((uint)weapon).ToString("X8") + ":" + unchecked((uint)component).ToString("X8");
    }
}
