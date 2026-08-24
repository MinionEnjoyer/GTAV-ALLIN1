using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Web.Script.Serialization;

namespace RealisticSuppressors
{
    internal static class ClientLog
    {
        private static readonly object Sync = new object();
        private static readonly JavaScriptSerializer Json =
            new JavaScriptSerializer();
        private static readonly string LogPath = Path.Combine(
            Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData),
            "RealisticSuppressors", "RealisticSuppressors.log");

        internal static void Info(
            string category, string eventName,
            IDictionary<string, object> data = null) =>
            Write("INFO", category, eventName, null, data);

        internal static void Warn(
            string category, string eventName,
            IDictionary<string, object> data = null) =>
            Write("WARN", category, eventName, null, data);

        internal static void Error(
            string category, string eventName, Exception exception,
            IDictionary<string, object> data = null) =>
            Write("ERROR", category, eventName, exception, data);

        private static void Write(
            string level, string category, string eventName,
            Exception exception, IDictionary<string, object> data)
        {
            try
            {
                var record = new Dictionary<string, object>
                {
                    { "timestamp", DateTime.UtcNow.ToString(
                        "o", CultureInfo.InvariantCulture) },
                    { "level", level },
                    { "category", category ?? "SUPPRESSORS" },
                    { "event", eventName ?? "event" },
                };
                if (data != null)
                {
                    foreach (KeyValuePair<string, object> entry in data)
                        record[entry.Key] = entry.Value;
                }
                if (exception != null)
                    record["exception"] = exception.ToString();
                lock (Sync)
                {
                    Directory.CreateDirectory(
                        Path.GetDirectoryName(LogPath));
                    File.AppendAllText(LogPath,
                        Json.Serialize(record) + Environment.NewLine);
                }
            }
            catch (Exception)
            {
                // Diagnostics must never interrupt the game script.
            }
        }
    }
}
