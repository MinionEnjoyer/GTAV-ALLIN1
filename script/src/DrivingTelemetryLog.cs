using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace ALLIN1
{
    // No GTA objects/native calls cross onto this thread. Bounded queue, one disk writer.
    internal sealed class DrivingTelemetryLog : IDisposable
    {
        private readonly BlockingCollection<Dictionary<string, object>> _queue = new BlockingCollection<Dictionary<string, object>>(512);
        private readonly Thread _writer;
        private readonly string _path;
        private readonly long _limit;
        private readonly string _session = Guid.NewGuid().ToString("N");
        private int _dropped, _failed, _closed;
        internal int Dropped => Volatile.Read(ref _dropped);
        internal bool Failed => Volatile.Read(ref _failed) != 0;
        internal DrivingTelemetryLog(string path, long limit = 8 * 1024 * 1024)
        {
            _path = path; _limit = limit;
            _writer = new Thread(WriteLoop) { IsBackground = true, Name = "ALLIN1 driving telemetry" };
            _writer.Start();
        }
        internal void Record(string kind, Dictionary<string, object> data = null)
        {
            if (Failed || Volatile.Read(ref _closed) != 0) return;
            // Copy to prevent callers mutating queued samples.
            var row = data == null ? new Dictionary<string, object>() : new Dictionary<string, object>(data);
            row["schema"] = 1; row["session"] = _session; row["kind"] = kind;
            row["utc"] = DateTime.UtcNow.ToString("o"); row["dropped_samples"] = Dropped;
            try { if (!_queue.TryAdd(row)) Interlocked.Increment(ref _dropped); }
            catch (InvalidOperationException) { /* Shutdown raced a final event. */ }
        }
        private void WriteLoop()
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(_path)));
                var json = new JavaScriptSerializer();
                while (!_queue.IsCompleted)
                {
                    if (!_queue.TryTake(out var row, 1000)) continue;
                    var batch = new StringBuilder(); batch.AppendLine(json.Serialize(row));
                    while (batch.Length < 65536 && _queue.TryTake(out row)) batch.AppendLine(json.Serialize(row));
                    if (File.Exists(_path) && new FileInfo(_path).Length + Encoding.UTF8.GetByteCount(batch.ToString()) > _limit)
                    {
                        // Exact log paths only; 3 archives, never an unbounded history.
                        if (File.Exists(_path + ".3")) File.Delete(_path + ".3");
                        for (int n = 2; n >= 1; n--) if (File.Exists(_path + "." + n)) File.Move(_path + "." + n, _path + "." + (n + 1));
                        File.Move(_path, _path + ".1");
                    }
                    File.AppendAllText(_path, batch.ToString(), new UTF8Encoding(false));
                }
            }
            catch { Interlocked.Exchange(ref _failed, 1); } // Fail closed, never retry every tick on a full disk.
        }
        public void Dispose()
        {
            if (Interlocked.Exchange(ref _closed, 1) != 0) return;
            _queue.CompleteAdding(); _writer.Join(500);
            // Do not dispose queue under a slow writer. It finishes draining as a background thread.
        }
    }
}
