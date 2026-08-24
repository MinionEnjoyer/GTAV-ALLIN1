using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

namespace RealisticSuppressors
{
    internal sealed class StandaloneSuppressorSettings
    {
        internal const string FileName = "RealisticSuppressors.ini";
        internal const string DefaultDocument =
            "; Suppressors Enhanced standalone settings\r\n" +
            "; Restart Story Mode or reload SHVDN scripts after editing.\r\n" +
            "[RealisticSuppressors]\r\n" +
            "realistic_suppressor_stealth = true\r\n" +
            "suppressor_wear_and_breakage = true\r\n" +
            "suppressor_durability_multiplier = 1.0\r\n" +
            "suppressor_heat_smoke = true\r\n" +
            "heat_smoke_intensity = 1.0\r\n" +
            "temperature_debug = false\r\n";

        internal bool StealthEnabled { get; private set; } = true;
        internal bool BreakageEnabled { get; private set; } = true;
        internal bool HeatSmokeEnabled { get; private set; } = true;
        internal bool TemperatureDebugEnabled { get; private set; }
        internal float DurabilityScale { get; private set; } = 1f;
        internal float HeatSmokeIntensity { get; private set; } = 1f;
        internal IReadOnlyList<string> Warnings => _warnings;

        private readonly List<string> _warnings = new List<string>();

        internal static string EnsureDefaultFile(string path)
        {
            if (string.IsNullOrWhiteSpace(path) || File.Exists(path))
                return "";
            try
            {
                string directory = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(directory))
                    Directory.CreateDirectory(directory);
                using (var stream = new FileStream(path, FileMode.CreateNew,
                    FileAccess.Write, FileShare.Read))
                using (var writer = new StreamWriter(stream))
                    writer.Write(DefaultDocument);
                return "";
            }
            catch (IOException)
            {
                if (File.Exists(path)) return "";
                return "config_create_failed:IOException";
            }
            catch (Exception ex)
            {
                return "config_create_failed:" + ex.GetType().Name;
            }
        }

        internal static StandaloneSuppressorSettings Load(string path)
        {
            var settings = new StandaloneSuppressorSettings();
            if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
                return settings;

            string section = "";
            string[] lines;
            try
            {
                lines = File.ReadAllLines(path);
            }
            catch (Exception ex)
            {
                settings._warnings.Add("config_read_failed:" +
                    ex.GetType().Name);
                return settings;
            }

            for (int index = 0; index < lines.Length; index++)
            {
                string line = (lines[index] ?? "").Trim();
                if (line.Length == 0 || line.StartsWith(";",
                        StringComparison.Ordinal) || line.StartsWith("#",
                        StringComparison.Ordinal))
                    continue;
                if (line.StartsWith("[", StringComparison.Ordinal) &&
                    line.EndsWith("]", StringComparison.Ordinal))
                {
                    section = line.Substring(1, line.Length - 2).Trim();
                    continue;
                }
                if (section.Length > 0 && !string.Equals(section,
                        "RealisticSuppressors",
                        StringComparison.OrdinalIgnoreCase))
                    continue;

                int separator = line.IndexOf('=');
                if (separator <= 0)
                {
                    settings._warnings.Add("line_" + (index + 1) +
                        ":missing_equals");
                    continue;
                }
                string key = line.Substring(0, separator).Trim();
                string value = line.Substring(separator + 1).Trim();
                settings.Apply(key, value, index + 1);
            }
            return settings;
        }

        private void Apply(string key, string value, int lineNumber)
        {
            switch ((key ?? "").Trim().ToLowerInvariant())
            {
                case "realistic_suppressor_stealth":
                    StealthEnabled = Boolean(value, StealthEnabled,
                        key, lineNumber);
                    break;
                case "suppressor_wear_and_breakage":
                    BreakageEnabled = Boolean(value, BreakageEnabled,
                        key, lineNumber);
                    break;
                case "suppressor_heat_smoke":
                    HeatSmokeEnabled = Boolean(value, HeatSmokeEnabled,
                        key, lineNumber);
                    break;
                case "temperature_debug":
                    TemperatureDebugEnabled = Boolean(value,
                        TemperatureDebugEnabled, key, lineNumber);
                    break;
                case "suppressor_durability_multiplier":
                    DurabilityScale = Number(value, DurabilityScale,
                        0.5f, 3f, key, lineNumber);
                    break;
                case "heat_smoke_intensity":
                    HeatSmokeIntensity = Number(value,
                        HeatSmokeIntensity, 0.5f, 2f, key, lineNumber);
                    break;
            }
        }

        private bool Boolean(
            string value, bool fallback, string key, int lineNumber)
        {
            switch ((value ?? "").Trim().ToLowerInvariant())
            {
                case "true":
                case "yes":
                case "on":
                case "1":
                    return true;
                case "false":
                case "no":
                case "off":
                case "0":
                    return false;
                default:
                    _warnings.Add("line_" + lineNumber + ":" + key +
                        ":invalid_boolean");
                    return fallback;
            }
        }

        private float Number(
            string value, float fallback, float minimum, float maximum,
            string key, int lineNumber)
        {
            if (!float.TryParse(value, NumberStyles.Float,
                    CultureInfo.InvariantCulture, out float parsed) ||
                float.IsNaN(parsed) || float.IsInfinity(parsed))
            {
                _warnings.Add("line_" + lineNumber + ":" + key +
                    ":invalid_number");
                return fallback;
            }
            if (parsed < minimum)
            {
                _warnings.Add("line_" + lineNumber + ":" + key +
                    ":clamped_minimum");
                return minimum;
            }
            if (parsed > maximum)
            {
                _warnings.Add("line_" + lineNumber + ":" + key +
                    ":clamped_maximum");
                return maximum;
            }
            return parsed;
        }
    }
}
