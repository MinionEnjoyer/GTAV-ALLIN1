using System;
using System.Collections.Generic;
using System.Globalization;
using System.Diagnostics;
using System.IO;
using System.Text;

namespace ALLIN1
{
    /// <summary>
    /// Dedicated diagnostics for the opt-in physics experiment. This logger is
    /// deliberately independent from ClientLog: GBAY may disable general client
    /// logging after the physics script has initialized.
    /// </summary>
    internal static class PhysicsExperimentLog
    {
        private const long MaxBytes = 8L * 1024L * 1024L;
        private const int Archives = 4;
        private static readonly object Sync = new object();
        private static readonly string ScriptDirectory =
            AppDomain.CurrentDomain.BaseDirectory;
        private static readonly string LogPath = Path.Combine(
            ScriptDirectory, "ALLIN1_npc_physics.log");
        private static readonly string Session =
            Guid.NewGuid().ToString("N").Substring(0, 12);
        private static bool _enabled;

        internal static string PathName => LogPath;

        internal static void Configure(bool enabled)
        {
            _enabled = enabled;
            if (!enabled) return;
            Info("session_started", new Dictionary<string, object>
            {
                { "version", typeof(PhysicsExperimentLog).Assembly.GetName().Version?.ToString() ?? "unknown" },
                { "runtime", Environment.Version.ToString() },
                { "process64", Environment.Is64BitProcess },
                { "log_path", LogPath },
            });
        }

        internal static void Info(string message,
            IDictionary<string, object> fields = null) =>
            Write("INFO", message, fields, null);

        internal static void Warn(string message,
            IDictionary<string, object> fields = null) =>
            Write("WARN", message, fields, null);

        internal static void Error(string message, Exception ex,
            IDictionary<string, object> fields = null) =>
            Write("ERROR", message, fields, ex);

        internal static bool Step(int pedHandle, string stage, Action action,
            IDictionary<string, object> context = null,
            Func<IDictionary<string, object>> observeAfter = null)
        {
            var stopwatch = Stopwatch.StartNew();
            try
            {
                action();
                stopwatch.Stop();
                Dictionary<string, object> fields = Merge(context,
                    observeAfter == null ? null : observeAfter());
                fields["ped"] = pedHandle;
                fields["stage"] = stage;
                fields["dispatch_elapsed_ms"] = stopwatch.Elapsed.TotalMilliseconds;
                // SHVDN exposes managed dispatch completion, not an engine-side
                // acknowledgement that a helper changed the final animation.
                fields["confirmation"] = "managed_dispatch_completed";
                Info("natural_motion_stage_sent", fields);
                return true;
            }
            catch (Exception ex)
            {
                stopwatch.Stop();
                Dictionary<string, object> fields = Merge(context, null);
                fields["ped"] = pedHandle;
                fields["stage"] = stage;
                fields["dispatch_elapsed_ms"] = stopwatch.Elapsed.TotalMilliseconds;
                Error("natural_motion_stage_failed", ex,
                    fields);
                return false;
            }
        }

        private static Dictionary<string, object> Merge(
            IDictionary<string, object> first,
            IDictionary<string, object> second)
        {
            var merged = new Dictionary<string, object>();
            if (first != null)
                foreach (KeyValuePair<string, object> field in first)
                    merged[field.Key] = field.Value;
            if (second != null)
                foreach (KeyValuePair<string, object> field in second)
                    merged[field.Key] = field.Value;
            return merged;
        }

        private static void Write(string level, string message,
            IDictionary<string, object> fields, Exception ex)
        {
            if (!_enabled) return;
            try
            {
                lock (Sync)
                {
                    RotateIfNeeded();
                    var line = new StringBuilder("{");
                    Add(line, "ts", DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture));
                    Add(line, "level", level);
                    Add(line, "session", Session);
                    Add(line, "component", "NPC-PHYSICS");
                    Add(line, "message", message);
                    if (fields != null)
                        foreach (KeyValuePair<string, object> field in fields)
                            Add(line, StructuredLogKeyPolicy.Normalize(
                                field.Key), field.Value);
                    if (ex != null)
                    {
                        Add(line, "exception_type", ex.GetType().FullName);
                        Add(line, "exception", ex.Message);
                        Add(line, "stack", ex.StackTrace ?? "");
                    }
                    if (line[line.Length - 1] == ',') line.Length--;
                    line.Append('}').AppendLine();
                    File.AppendAllText(LogPath, line.ToString(), Encoding.UTF8);
                }
            }
            catch
            {
                // Diagnostics must never destabilize gameplay.
            }
        }

        private static void Add(StringBuilder line, string key, object value)
        {
            line.Append('"').Append(Escape(key)).Append("\":");
            if (value == null) line.Append("null");
            else if (value is bool boolean) line.Append(boolean ? "true" : "false");
            else if (value is byte || value is short || value is int ||
                     value is long || value is float || value is double ||
                     value is decimal)
                line.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
            else line.Append('"').Append(Escape(Convert.ToString(
                value, CultureInfo.InvariantCulture))).Append('"');
            line.Append(',');
        }

        private static string Escape(string value) => (value ?? "")
            .Replace("\\", "\\\\").Replace("\"", "\\\"")
            .Replace("\r", "\\r").Replace("\n", "\\n");

        private static void RotateIfNeeded()
        {
            var file = new FileInfo(LogPath);
            if (!file.Exists || file.Length < MaxBytes) return;
            if (File.Exists(LogPath + "." + Archives))
                File.Delete(LogPath + "." + Archives);
            for (int index = Archives - 1; index >= 1; index--)
                if (File.Exists(LogPath + "." + index))
                    File.Move(LogPath + "." + index,
                        LogPath + "." + (index + 1));
            File.Move(LogPath, LogPath + ".1");
        }
    }
}
