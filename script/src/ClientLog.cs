using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;

namespace ALLIN1
{
    internal static class ClientLog
    {
        private const long MaxBytes = 5L * 1024L * 1024L;
        private const int Archives = 3;
        private static readonly object Sync = new object();
        private static readonly string LogPath = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_client.log");
        private static readonly string Session = Guid.NewGuid().ToString("N").Substring(0, 12);
        private static bool _enabled = true;
        private static bool _started;

        internal static void Configure(bool enabled)
        {
            _enabled = enabled;
            if (enabled) EnsureStarted();
        }

        internal static void Info(string component, string message,
            IDictionary<string, object> fields = null) => Write("INFO", component, message, fields, null);
        internal static void Warn(string component, string message,
            IDictionary<string, object> fields = null) => Write("WARN", component, message, fields, null);
        internal static void Error(string component, string message, Exception ex,
            IDictionary<string, object> fields = null) => Write("ERROR", component, message, fields, ex);
        internal static IDisposable Time(string component, string operation,
            IDictionary<string, object> fields = null) => new TimedOperation(component, operation, fields);

        private static void EnsureStarted()
        {
            if (_started) return;
            _started = true;
            Write("INFO", "Client", "session_started", new Dictionary<string, object>
            {
                { "version", typeof(ClientLog).Assembly.GetName().Version?.ToString() ?? "unknown" },
                { "runtime", Environment.Version.ToString() },
                { "os", Environment.OSVersion.ToString() },
                { "process64", Environment.Is64BitProcess }
            }, null);
        }

        private static void Write(string level, string component, string message,
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
                    Add(line, "level", level); Add(line, "session", Session);
                    Add(line, "component", component); Add(line, "message", message);
                    if (fields != null)
                        foreach (var field in fields)
                            Add(line, StructuredLogKeyPolicy.Normalize(
                                field.Key), field.Value);
                    if (ex != null)
                    {
                        Add(line, "exception_type", ex.GetType().FullName);
                        Add(line, "exception", ex.Message); Add(line, "stack", ex.StackTrace ?? "");
                    }
                    if (line[line.Length - 1] == ',') line.Length--;
                    line.Append('}').AppendLine();
                    File.AppendAllText(LogPath, line.ToString(), Encoding.UTF8);
                }
            }
            catch { }
        }

        private static void Add(StringBuilder line, string key, object value)
        {
            line.Append('"').Append(Escape(key)).Append("\":");
            if (value == null) line.Append("null");
            else if (value is bool) line.Append((bool)value ? "true" : "false");
            else if (value is byte || value is short || value is int || value is long ||
                     value is float || value is double || value is decimal)
                line.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
            else line.Append('"').Append(Escape(Convert.ToString(value, CultureInfo.InvariantCulture))).Append('"');
            line.Append(',');
        }

        private static string Escape(string value) => (value ?? "").Replace("\\", "\\\\")
            .Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n");

        private static void RotateIfNeeded()
        {
            var file = new FileInfo(LogPath);
            if (!file.Exists || file.Length < MaxBytes) return;
            if (File.Exists(LogPath + "." + Archives)) File.Delete(LogPath + "." + Archives);
            for (int i = Archives - 1; i >= 1; i--)
                if (File.Exists(LogPath + "." + i))
                    File.Move(LogPath + "." + i, LogPath + "." + (i + 1));
            File.Move(LogPath, LogPath + ".1");
        }

        private sealed class TimedOperation : IDisposable
        {
            private readonly string _component, _operation;
            private readonly IDictionary<string, object> _fields;
            private readonly Stopwatch _watch = Stopwatch.StartNew();
            internal TimedOperation(string component, string operation, IDictionary<string, object> fields)
            { _component = component; _operation = operation; _fields = fields; Info(component, operation + "_started", fields); }
            public void Dispose()
            {
                _watch.Stop();
                var fields = _fields == null ? new Dictionary<string, object>() : new Dictionary<string, object>(_fields);
                fields["elapsed_ms"] = _watch.ElapsedMilliseconds;
                Info(_component, _operation + "_completed", fields);
            }
        }
    }
}
