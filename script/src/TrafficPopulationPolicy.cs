// Launcher-owned custom-package traffic selection policy.  Built-in curated
// traffic remains in TrafficSpawner and is intentionally not configurable here.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;

namespace ALLIN1
{
    internal sealed class TrafficPopulationSelection
    {
        internal TrafficPopulationSelection(string packageId, string model,
            bool enabled, double weight)
        {
            PackageId = packageId;
            Model = model;
            Enabled = enabled;
            Weight = weight;
        }

        internal string PackageId { get; }
        internal string Model { get; }
        internal bool Enabled { get; }
        internal double Weight { get; }
    }

    internal sealed class TrafficPopulationConfiguration
    {
        private readonly Dictionary<string, TrafficPopulationSelection> _entries;

        internal TrafficPopulationConfiguration(bool enabled,
            double replacementChance,
            IEnumerable<TrafficPopulationSelection> entries)
        {
            Enabled = enabled;
            ReplacementChance = replacementChance;
            _entries = new Dictionary<string, TrafficPopulationSelection>(
                StringComparer.OrdinalIgnoreCase);
            foreach (TrafficPopulationSelection entry in entries)
                _entries.Add(Key(entry.PackageId, entry.Model), entry);
        }

        internal bool Enabled { get; }
        internal double ReplacementChance { get; }
        internal IReadOnlyCollection<TrafficPopulationSelection> Entries =>
            _entries.Values;

        internal bool TryGetEnabledWeight(string packageId, string model,
            out double weight)
        {
            weight = 0d;
            TrafficPopulationSelection entry;
            if (!_entries.TryGetValue(Key(packageId, model), out entry) ||
                !entry.Enabled)
                return false;
            weight = entry.Weight;
            return true;
        }

        internal static string Key(string packageId, string model) =>
            packageId + "\u001f" + model;
    }

    internal static class TrafficPopulationPolicy
    {
        internal const int MaximumDocumentBytes = 1024 * 1024;
        internal const int MaximumEntries = 512;
        internal const double MinimumWeight = 0.1d;
        internal const double MaximumWeight = 20d;
        private static readonly Regex Identifier = new Regex(
            "^[a-z][a-z0-9._-]{1,95}$", RegexOptions.CultureInvariant);
        private static readonly Regex Model = new Regex(
            "^[a-z0-9][a-z0-9_-]{0,63}$", RegexOptions.CultureInvariant);

        // `present` distinguishes no document (legacy behavior) from an
        // invalid document (fail closed).  Callers never get a partial policy.
        internal static bool TryLoad(string path,
            out TrafficPopulationConfiguration configuration,
            out bool present, out string error)
        {
            configuration = null;
            present = File.Exists(path);
            error = "";
            if (!present) return true;
            try
            {
                var info = new FileInfo(path);
                if (info.Length > MaximumDocumentBytes)
                    throw new InvalidDataException(
                        "traffic population document exceeds 1 MiB");
                string text = File.ReadAllText(path);
                if (text.Length > MaximumDocumentBytes)
                    throw new InvalidDataException(
                        "traffic population document exceeds 1 MiB");
                configuration = Parse(text);
                return true;
            }
            catch (Exception ex) when (ex is IOException ||
                ex is UnauthorizedAccessException || ex is InvalidDataException ||
                ex is FormatException || ex is ArgumentException)
            {
                error = ex.Message;
                return false;
            }
        }

        internal static TrafficPopulationConfiguration Parse(string json)
        {
            Dictionary<string, object> root = Object(
                PortableJsonParser.Parse(json), "traffic population document");
            ExactFields(root, "traffic population document", new[] {
                "schema_version", "enabled", "replacement_chance", "entries",
            });
            if (Integer(root, "schema_version") != 1)
                throw new InvalidDataException(
                    "Unsupported traffic population schema version");
            bool enabled = Boolean(root, "enabled");
            double replacementChance = Number(root, "replacement_chance", 0d, 1d);
            object[] values = Array(Value(root, "entries"),
                "traffic population entries");
            if (values.Length > MaximumEntries)
                throw new InvalidDataException("traffic population has too many entries");
            var entries = new List<TrafficPopulationSelection>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (object value in values)
            {
                Dictionary<string, object> row = Object(value,
                    "traffic population entry");
                ExactFields(row, "traffic population entry", new[] {
                    "package_id", "model", "enabled", "weight",
                });
                string packageId = IdentifierValue(Text(row, "package_id"),
                    "package_id");
                string model = ModelValue(Text(row, "model"), "model");
                string key = TrafficPopulationConfiguration.Key(packageId, model);
                if (!seen.Add(key))
                    throw new InvalidDataException(
                        "traffic population repeats a package/model entry");
                entries.Add(new TrafficPopulationSelection(packageId, model,
                    Boolean(row, "enabled"), Number(row, "weight",
                        MinimumWeight, MaximumWeight)));
            }
            return new TrafficPopulationConfiguration(enabled,
                replacementChance, entries);
        }

        private static Dictionary<string, object> Object(object value, string label)
        {
            if (!(value is Dictionary<string, object> result))
                throw new InvalidDataException(label + " must be an object");
            return result;
        }

        private static object[] Array(object value, string label)
        {
            if (!(value is object[] result))
                throw new InvalidDataException(label + " must be an array");
            return result;
        }

        private static object Value(Dictionary<string, object> value, string key)
        {
            if (!value.TryGetValue(key, out object result))
                throw new InvalidDataException("Missing required field: " + key);
            return result;
        }

        private static string Text(Dictionary<string, object> value, string key)
        {
            if (!(Value(value, key) is string result) ||
                string.IsNullOrWhiteSpace(result))
                throw new InvalidDataException(key + " must be non-empty text");
            return result;
        }

        private static string IdentifierValue(string value, string label)
        {
            string normalized = value.Trim().ToLowerInvariant();
            if (!Identifier.IsMatch(normalized))
                throw new InvalidDataException("Invalid traffic " + label);
            return normalized;
        }

        private static string ModelValue(string value, string label)
        {
            string normalized = value.Trim().ToLowerInvariant();
            if (!Model.IsMatch(normalized))
                throw new InvalidDataException("Invalid traffic " + label);
            return normalized;
        }

        private static int Integer(Dictionary<string, object> value, string key)
        {
            object raw = Value(value, key);
            if (raw is bool || !(raw is int result))
                throw new InvalidDataException(key + " must be an integer");
            return result;
        }

        private static bool Boolean(Dictionary<string, object> value, string key)
        {
            if (!(Value(value, key) is bool result))
                throw new InvalidDataException(key + " must be true or false");
            return result;
        }

        private static double Number(Dictionary<string, object> value, string key,
            double minimum, double maximum)
        {
            object raw = Value(value, key);
            double result;
            if (raw is int integer) result = integer;
            else if (raw is long longInteger) result = longInteger;
            else if (raw is decimal decimalNumber) result = (double)decimalNumber;
            else if (raw is double doubleNumber) result = doubleNumber;
            else throw new InvalidDataException(key + " must be a number");
            if (double.IsNaN(result) || double.IsInfinity(result) ||
                result < minimum || result > maximum)
                throw new InvalidDataException(key + " is outside supported range");
            return result;
        }

        private static void ExactFields(Dictionary<string, object> value,
            string label, IEnumerable<string> fields)
        {
            var allowed = new HashSet<string>(fields, StringComparer.Ordinal);
            foreach (string key in value.Keys)
                if (!allowed.Contains(key))
                    throw new InvalidDataException(
                        label + " contains unknown field: " + key);
            foreach (string key in allowed)
                if (!value.ContainsKey(key))
                    throw new InvalidDataException(
                        label + " is missing field: " + key);
        }
    }
}
