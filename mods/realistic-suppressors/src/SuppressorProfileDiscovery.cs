using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace RealisticSuppressors
{
    // Immutable per-controller snapshot. Never mutate the stock table or do IO
    // on a shot/tick. Custom profiles are rediscovered after a script restart.
    internal sealed class SuppressorProfileCatalog
    {
        private readonly Dictionary<uint, SuppressorThermalProfile> _byWeapon;
        internal IReadOnlyList<SuppressorThermalProfile> All { get; }
        internal IReadOnlyList<string> Diagnostics { get; }
        internal IReadOnlyDictionary<uint, string> Sources { get; }
        internal int CustomCount => Sources.Count;

        internal SuppressorProfileCatalog(
            IEnumerable<SuppressorThermalProfile> custom = null,
            IDictionary<uint, string> sources = null,
            IEnumerable<string> diagnostics = null)
        {
            var profiles = SuppressorThermalProfiles.All
                .Concat(custom ?? Array.Empty<SuppressorThermalProfile>()).ToArray();
            All = Array.AsReadOnly(profiles);
            _byWeapon = profiles.ToDictionary(p => p.WeaponHash);
            Sources = new System.Collections.ObjectModel.ReadOnlyDictionary<uint, string>(
                new Dictionary<uint, string>(sources ?? new Dictionary<uint, string>()));
            Diagnostics = Array.AsReadOnly((diagnostics ?? Array.Empty<string>()).ToArray());
        }

        internal bool TryGet(uint weapon, out SuppressorThermalProfile profile) =>
            _byWeapon.TryGetValue(weapon, out profile);

        internal bool TryGetLifecycle(string weapon, int component,
            out SuppressorThermalProfile profile)
        {
            profile = null;
            if (string.IsNullOrWhiteSpace(weapon) || component == 0) return false;
            if (!TryGet(SuppressorProfileDiscovery.Hash(weapon.Trim()), out var candidate) ||
                candidate.ComponentHash != unchecked((uint)component) ||
                !string.Equals(candidate.WeaponName, weapon.Trim(), StringComparison.OrdinalIgnoreCase))
                return false;
            profile = candidate;
            return true;
        }
    }

    internal static class SuppressorProfileDiscovery
    {
        internal const int MaxFileBytes = 64 * 1024;
        internal const int MaxFiles = 128;
        internal const int MaxProfiles = 256;
        internal const int MaxReceipts = 256;
        private const int MaxReceiptBytes = 1024 * 1024;
        private const int MaxReadBytes = 8 * 1024 * 1024;
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        private static readonly Regex WeaponName = new Regex(
            @"^WEAPON_[A-Z0-9_]{1,90}$", RegexOptions.CultureInvariant);
        private static readonly Regex ComponentName = new Regex(
            @"^COMPONENT_[A-Z0-9_]{1,90}$", RegexOptions.CultureInvariant);
        private static readonly Regex PackageId = new Regex(
            @"^[a-z0-9][a-z0-9._-]{0,95}$", RegexOptions.CultureInvariant);
        private static readonly Regex Digest = new Regex(
            @"^[a-fA-F0-9]{64}$", RegexOptions.CultureInvariant);
        private static readonly HashSet<string> Fields = new HashSet<string>(
            new[] { "weapon", "component", "preset", "weapon_class", "profile_code",
                "thermal_basis", "heat_per_shot_c", "cooling_half_life_s",
                "damage_onset_c", "critical_c", "rated_life_rounds" });

        // Values are gameplay presets, not measurements of a creator's hardware.
        private static readonly Dictionary<string, uint> Presets =
            new Dictionary<string, uint>(StringComparer.Ordinal)
            {
                { "pistol_9mm", 0x1B06D571 }, { "smg_9mm", 0x2BE6766B },
                { "smg_45", 0xD205520E }, { "rifle_556", 0x83BF0278 },
                { "rifle_762", 0xC78D71B4 }, { "shotgun_12g", 0x1D073A89 },
                { "sniper_magnum", 0x05FC3C11 }
            };

        internal static uint Hash(string name)
        {
            unchecked
            {
                uint hash = 0;
                foreach (char value in name.ToLowerInvariant())
                {
                    hash += value; hash += hash << 10; hash ^= hash >> 6;
                }
                hash += hash << 3; hash ^= hash >> 11; hash += hash << 15;
                return hash;
            }
        }

        internal static IReadOnlyList<SuppressorThermalProfile> Parse(string json)
        {
            var root = PortableJson.ParseObject(json);
            if (root.Keys.Any(k => k != "schema_version" && k != "profiles"))
                throw new InvalidDataException("Unknown profile document field.");
            if (!root.TryGetValue("schema_version", out var version) ||
                !(version is int schema) || schema != 1)
                throw new InvalidDataException("schema_version must be integer 1.");
            if (!root.TryGetValue("profiles", out var raw) || !(raw is object[] profiles)
                || profiles.Length == 0 || profiles.Length > 64)
                throw new InvalidDataException("profiles must contain 1 through 64 entries.");
            return Array.AsReadOnly(profiles.Select(ParseProfile).ToArray());
        }

        private static SuppressorThermalProfile ParseProfile(object value)
        {
            if (!(value is Dictionary<string, object> row) || row.Keys.Any(k => !Fields.Contains(k)))
                throw new InvalidDataException("Profile must be an object with known fields.");
            string weapon = Text(row, "weapon", 97).ToUpperInvariant();
            string component = Text(row, "component", 100).ToUpperInvariant();
            if (!WeaponName.IsMatch(weapon) || !ComponentName.IsMatch(component))
                throw new InvalidDataException("Invalid weapon/component identifier.");
            uint weaponHash = Hash(weapon), componentHash = Hash(component);
            if (weaponHash == 0 || !RealisticSuppressorPolicy.IsKnownSuppressorHash(componentHash))
                throw new InvalidDataException("Version 1 requires a supported stock suppressor component.");
            SuppressorThermalProfile preset = null;
            string presetName = null;
            if (row.ContainsKey("preset"))
            {
                presetName = Text(row, "preset", 32);
                if (!Presets.TryGetValue(presetName, out var donor) ||
                    !SuppressorThermalProfiles.TryGet(donor, out preset))
                    throw new InvalidDataException("Unknown preset.");
            }
            var weaponClass = presetName == "smg_45" ? SuppressorWeaponClass.SubmachineGun
                : preset?.WeaponClass ?? SuppressorWeaponClass.Other;
            if (row.ContainsKey("weapon_class"))
            {
                switch (Text(row, "weapon_class", 16))
                {
                    case "sidearm": weaponClass = SuppressorWeaponClass.Sidearm; break;
                    case "smg": weaponClass = SuppressorWeaponClass.SubmachineGun; break;
                    case "rifle": weaponClass = SuppressorWeaponClass.Rifle; break;
                    case "shotgun": weaponClass = SuppressorWeaponClass.Shotgun; break;
                    case "sniper": weaponClass = SuppressorWeaponClass.Sniper; break;
                    case "other": weaponClass = SuppressorWeaponClass.Other; break;
                    default: throw new InvalidDataException("Unknown weapon_class.");
                }
            }
            else if (preset == null)
                throw new InvalidDataException("weapon_class is required without a preset.");
            float heat = Number(row, "heat_per_shot_c", preset?.HeatPerShotCelsius, .01f, 100);
            float cooling = Number(row, "cooling_half_life_s", preset?.CoolingHalfLifeSeconds, 1, 3600);
            float onset = Number(row, "damage_onset_c", preset?.DamageOnsetCelsius, 21, 1500);
            float critical = Number(row, "critical_c", preset?.CriticalCelsius, 526, 1600);
            float life = Number(row, "rated_life_rounds", preset?.RatedLifeRounds, 1, 1000000);
            if (critical <= onset || life != Math.Truncate(life))
                throw new InvalidDataException("critical_c must exceed damage_onset_c; rated_life_rounds must be an integer.");
            string code = row.ContainsKey("profile_code") ? Text(row, "profile_code", 16) : "J" + weaponHash.ToString("X8");
            if (!Regex.IsMatch(code, @"^[A-Z0-9_-]{1,16}$", RegexOptions.CultureInvariant))
                throw new InvalidDataException("profile_code must use uppercase letters, digits, _ or -.");
            string basis = row.ContainsKey("thermal_basis") ? Text(row, "thermal_basis", 160)
                : "Creator JSON gameplay approximation" + (presetName == null ? "." : " (" + presetName + ").");
            return new SuppressorThermalProfile(weapon, weaponHash, componentHash, weaponClass,
                code, basis, heat, cooling, onset, critical, (int)life);
        }

        private static string Text(Dictionary<string, object> row, string key, int max)
        {
            if (!row.TryGetValue(key, out var raw) || !(raw is string text) ||
                text.Length == 0 || text.Length > max || text != text.Trim() || text.Any(char.IsControl))
                throw new InvalidDataException("Invalid " + key + ".");
            return text;
        }

        private static float Number(Dictionary<string, object> row, string key, float? fallback, float min, float max)
        {
            if (!row.TryGetValue(key, out var raw))
            {
                if (fallback.HasValue) return fallback.Value;
                throw new InvalidDataException(key + " is required without a preset.");
            }
            if (!(raw is int) && !(raw is long) && !(raw is double) && !(raw is decimal))
                throw new InvalidDataException(key + " must be a number.");
            double value = Convert.ToDouble(raw, CultureInfo.InvariantCulture);
            if (double.IsNaN(value) || double.IsInfinity(value) || value < min || value > max ||
                (key == "rated_life_rounds" && value != Math.Truncate(value)))
                throw new InvalidDataException(key + " is outside its supported range.");
            return (float)value;
        }

        private sealed class Candidate
        {
            internal string Path, Source, Checksum;
            internal Candidate(string path, string source, string checksum = null)
            { Path = path; Source = source; Checksum = checksum; }
        }

        // Hosted mode: receipt ownership AND the host's enabled registry are required.
        // Standalone mode: only the explicitly designated local profile directory.
        internal static SuppressorProfileCatalog Load(string gameRoot, string standaloneDirectory,
            Func<string, bool> enabledPackage = null)
        {
            var warnings = new List<string>();
            var candidates = new List<Candidate>();
            int remaining = MaxReadBytes;
            try
            {
                if (enabledPackage != null)
                {
                    string root = SafeRoot(gameRoot);
                    string receiptDirectory = Contained(root, "scripts/.allin1/mods");
                    foreach (string path in Files(receiptDirectory, "*.json", MaxReceipts))
                    {
                        string id = System.IO.Path.GetFileNameWithoutExtension(path);
                        try
                        {
                            if (!PackageId.IsMatch(id) || !enabledPackage(id)) continue;
                            var receipt = PortableJson.ParseObject(Read(path, MaxReceiptBytes, ref remaining));
                            if (Text(receipt, "id", 96) != id)
                                throw new InvalidDataException("Receipt identifier mismatch.");
                            if (!receipt.TryGetValue("enabled", out var enabled) || !(enabled is bool))
                                throw new InvalidDataException("Receipt enabled flag is invalid.");
                            if (!(bool)enabled) continue;
                            if (!receipt.TryGetValue("files", out var rows) || !(rows is object[] files) || files.Length > 4096)
                                throw new InvalidDataException("Invalid receipt file list.");
                            var packageCandidates = new List<Candidate>();
                            var destinations = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                            foreach (var item in files)
                            {
                                if (!(item is Dictionary<string, object> file))
                                    throw new InvalidDataException("Invalid receipt file record.");
                                string relative = Text(file, "destination", 512);
                                if (!destinations.Add(relative.Replace('\\', '/')))
                                    throw new InvalidDataException("Duplicate receipt destination.");
                                if (!relative.Replace('\\', '/').EndsWith("/suppressor-profile.json", StringComparison.OrdinalIgnoreCase))
                                    continue;
                                if (!relative.StartsWith("scripts/", StringComparison.OrdinalIgnoreCase))
                                    throw new InvalidDataException("Profile must be a loose file under scripts/.");
                                string checksum = Text(file, "sha256", 64);
                                if (!Digest.IsMatch(checksum)) throw new InvalidDataException("Invalid receipt checksum.");
                                packageCandidates.Add(new Candidate(Contained(root, relative),
                                    "package:" + id + "/" + relative, checksum));
                            }
                            candidates.AddRange(packageCandidates);
                        }
                        catch (Exception ex) when (Recoverable(ex))
                        { warnings.Add("receipt:" + id + ": " + ex.Message); }
                    }
                }
                else
                {
                    foreach (string path in Files(SafeRoot(standaloneDirectory), "*.json", MaxFiles))
                        candidates.Add(new Candidate(path, "standalone:" + System.IO.Path.GetFileName(path)));
                }
                if (candidates.Count > MaxFiles)
                    throw new InvalidDataException("Profile file count exceeds " + MaxFiles + ".");
                var parsed = new List<KeyValuePair<SuppressorThermalProfile, string>>();
                foreach (var candidate in candidates.OrderBy(c => c.Source, StringComparer.Ordinal))
                {
                    try
                    {
                        string json = Read(candidate.Path, MaxFileBytes, ref remaining, candidate.Checksum);
                        foreach (var profile in Parse(json))
                            parsed.Add(new KeyValuePair<SuppressorThermalProfile, string>(profile, candidate.Source));
                    }
                    catch (Exception ex) when (Recoverable(ex))
                    { warnings.Add(candidate.Source + ": " + ex.Message); }
                }
                if (remaining < 0 || parsed.Count > MaxProfiles)
                    throw new InvalidDataException("Aggregate profile discovery limit exceeded.");
                var accepted = new List<SuppressorThermalProfile>();
                var sources = new Dictionary<uint, string>();
                foreach (var group in parsed.GroupBy(pair => pair.Key.WeaponHash).OrderBy(g => g.Key))
                {
                    if (SuppressorThermalProfiles.TryGet(group.Key, out var stock))
                    { warnings.Add("Built-in profile protected: " + stock.WeaponName + "."); continue; }
                    if (group.Count() != 1)
                    {
                        warnings.Add("Conflicting custom weapon profile " + group.First().Key.WeaponName
                            + "; rejected all definitions: " + string.Join(", ", group.Select(p => p.Value)));
                        continue;
                    }
                    accepted.Add(group.First().Key);
                    sources.Add(group.Key, group.First().Value);
                }
                return new SuppressorProfileCatalog(accepted, sources, warnings);
            }
            catch (Exception ex) when (Recoverable(ex))
            {
                warnings.Add("Profile discovery failed closed: " + ex.Message);
                return new SuppressorProfileCatalog(diagnostics: warnings);
            }
        }

        private static bool Recoverable(Exception ex) => ex is InvalidDataException || ex is IOException || ex is UnauthorizedAccessException
            || ex is ArgumentException || ex is InvalidOperationException || ex is System.Security.SecurityException;

        private static IEnumerable<string> Files(string directory, string pattern, int max)
        {
            RejectRedirects(directory);
            if (!Directory.Exists(directory)) return Array.Empty<string>();
            var files = Directory.EnumerateFiles(directory, pattern, SearchOption.TopDirectoryOnly).Take(max + 1).ToArray();
            if (files.Length > max) throw new InvalidDataException("Discovery directory exceeds its file count limit.");
            return files.OrderBy(p => p, StringComparer.Ordinal);
        }

        private static string Read(string path, int max, ref int remaining, string expected = null)
        {
            RejectRedirects(path);
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                long length = stream.Length;
                if (length > max) throw new InvalidDataException("File exceeds the byte limit.");
                remaining -= checked((int)length);
                if (remaining < 0) throw new InvalidDataException("Aggregate read budget exceeded.");
                var bytes = new byte[(int)length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    int read = stream.Read(bytes, offset, bytes.Length - offset);
                    if (read == 0) throw new EndOfStreamException();
                    offset += read;
                }
                if (stream.ReadByte() != -1) throw new InvalidDataException("File changed while reading.");
                if (expected != null)
                {
                    using (var hash = SHA256.Create())
                        if (!string.Equals(BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", ""),
                                expected, StringComparison.OrdinalIgnoreCase))
                            throw new InvalidDataException("Receipt SHA-256 mismatch; rebuild/reinstall the owning package.");
                }
                int start = bytes.Length >= 3 && bytes[0] == 239 && bytes[1] == 187 && bytes[2] == 191 ? 3 : 0;
                return Utf8.GetString(bytes, start, bytes.Length - start);
            }
        }

        internal static string SafeRoot(string directory)
        {
            if (string.IsNullOrWhiteSpace(directory) || !System.IO.Path.IsPathRooted(directory))
                throw new InvalidDataException("An absolute discovery directory is required.");
            string full = System.IO.Path.GetFullPath(directory);
            RejectRedirects(full);
            // Keep the separator on a volume root: C:\\ is absolute, C: is not.
            return full;
        }

        internal static string Contained(string root, string relative)
        {
            if (string.IsNullOrWhiteSpace(relative) || relative.Length > 512 || relative.Contains("\\") ||
                relative.Contains(":") || System.IO.Path.IsPathRooted(relative) ||
                relative.Split('/').Any(p => p == "" || p == "." || p == ".." || p != p.Trim() || p.EndsWith(".")))
                throw new InvalidDataException("Unsafe profile destination.");
            string full = System.IO.Path.GetFullPath(System.IO.Path.Combine(root, relative));
            if (!full.StartsWith(root.TrimEnd('\\', '/') + System.IO.Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Profile destination escaped the game directory.");
            RejectRedirects(full);
            return full;
        }

        private static void RejectRedirects(string path)
        {
            for (string current = System.IO.Path.GetFullPath(path); !string.IsNullOrEmpty(current);
                current = System.IO.Path.GetDirectoryName(current))
            {
                if ((File.Exists(current) || Directory.Exists(current)) &&
                    (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("Redirected profile paths are not allowed.");
            }
        }

        internal static string ResolveGameRoot(string assemblyPath, string applicationBase)
        {
            foreach (string start in new[] { applicationBase, System.IO.Path.GetDirectoryName(assemblyPath) })
            {
                string current = start;
                for (int depth = 0; depth < 4 && !string.IsNullOrWhiteSpace(current); depth++)
                {
                    if (File.Exists(System.IO.Path.Combine(current, "GTA5.exe")) ||
                        File.Exists(System.IO.Path.Combine(current, "GTA5_Enhanced.exe")))
                        return SafeRoot(current);
                    current = System.IO.Path.GetDirectoryName(current);
                }
            }
            throw new InvalidDataException("Could not resolve the game root for profile discovery.");
        }
    }
}
