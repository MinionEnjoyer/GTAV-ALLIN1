// Bounded configuration reader shared by shipped runtime features.
using System;
using System.IO;
using System.Text;

namespace ALLIN1
{
    internal static class RuntimeScriptSettings
    {
        internal const int MaximumConfigurationBytes = 256 * 1024;
        private static readonly string ConfigPath = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.toml");

        internal static bool ReadBoolean(string requestedKey, bool defaultValue)
        {
            return ReadBooleanFile(ConfigPath, requestedKey, defaultValue);
        }

        internal static bool ReadBooleanFile(string path, string requestedKey,
            bool defaultValue)
        {
            if (string.IsNullOrWhiteSpace(path) ||
                string.IsNullOrWhiteSpace(requestedKey) || !File.Exists(path))
                return defaultValue;
            try
            {
                byte[] buffer = new byte[MaximumConfigurationBytes + 1];
                int total = 0;
                using (var stream = new FileStream(path, FileMode.Open,
                    FileAccess.Read, FileShare.ReadWrite))
                {
                    while (total < buffer.Length)
                    {
                        int read = stream.Read(buffer, total, buffer.Length - total);
                        if (read == 0) break;
                        total += read;
                    }
                }
                if (total > MaximumConfigurationBytes)
                    throw new InvalidDataException("configuration exceeds limit");
                return ParseBoolean(Encoding.UTF8.GetString(buffer, 0, total),
                    requestedKey, defaultValue);
            }
            catch (Exception error)
            {
                ClientLog.Error("RuntimeSettings", "read_boolean_failed", error);
            }
            return defaultValue;
        }

        internal static bool ParseBoolean(string document, string requestedKey,
            bool defaultValue)
        {
            if (string.IsNullOrWhiteSpace(document) ||
                string.IsNullOrWhiteSpace(requestedKey)) return defaultValue;
            // File.ReadAllLines previously consumed a UTF-8 BOM before yielding
            // the first section header.  Keep that compatibility at the input
            // boundary only; a BOM elsewhere is ordinary invalid configuration.
            if (document[0] == '\ufeff') document = document.Substring(1);
            string requested = requestedKey.Trim().ToLowerInvariant();
            string section = "";
            foreach (string rawLine in document.Replace("\r", "").Split('\n'))
            {
                string line = rawLine.Trim();
                if (line.Length == 0 || line.StartsWith("#")) continue;
                if (line.StartsWith("[") && line.EndsWith("]"))
                {
                    section = line.Substring(1, line.Length - 2)
                        .Trim().ToLowerInvariant();
                    continue;
                }
                if (section != "script") continue;
                int equals = line.IndexOf('=');
                if (equals < 0) continue;
                string key = line.Substring(0, equals).Trim().ToLowerInvariant();
                if (key != requested) continue;
                string value = line.Substring(equals + 1).Trim();
                int comment = value.IndexOf('#');
                if (comment >= 0) value = value.Substring(0, comment).Trim();
                return string.Equals(value, "true",
                    StringComparison.OrdinalIgnoreCase);
            }
            return defaultValue;
        }
    }
}
