// Validated handoff from ReactorV's process-scoped early data preloader.
//
// This cache is only an I/O optimization. It never signals that GTA natives
// are ready and never replaces the launcher's receipt or runtime validation.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace ALLIN1
{
    internal static class EarlyStartupSnapshot
    {
        private const int SchemaVersion = 1;
        private const int MaximumEntries = 64;
        private const int MaximumEntryBytes = 4 * 1024 * 1024;
        private const int MaximumAggregateBytes = 16 * 1024 * 1024;
        private const int MaximumSnapshotBytes = 24 * 1024 * 1024;
        private const int ReadyWaitMilliseconds = 100;
        private static readonly TimeSpan MaximumAge = TimeSpan.FromMinutes(15);
        private static readonly TimeSpan MaximumFutureSkew = TimeSpan.FromMinutes(2);
        private static readonly object Sync = new object();
        private static Snapshot _snapshot;
        private static bool _attempted;
        private static readonly HashSet<string> ReportedHits =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        // Test-only overrides are reset by ResetForTests. They avoid depending
        // on the current test runner PID or %LOCALAPPDATA% layout.
        private static string _snapshotPathOverride;
        private static string _scriptsDirectoryOverride;
        private static int? _processIdOverride;
        private static DateTimeOffset? _nowOverride;

        internal static bool TryGetText(string id, out string content)
        {
            content = null;
            Snapshot snapshot = Current();
            if (snapshot == null || string.IsNullOrWhiteSpace(id)) return false;
            Entry entry;
            if (!snapshot.ById.TryGetValue(id, out entry) || !entry.IsCurrent())
                return false;
            content = entry.Content;
            ReportHit(entry);
            return true;
        }

        internal static bool TryGetTextByPath(
            string relativePath, out string content)
        {
            content = null;
            string normalized;
            if (!TryNormalizeRelativePath(relativePath, out normalized))
                return false;
            Snapshot snapshot = Current();
            if (snapshot == null) return false;
            Entry entry;
            if (!snapshot.ByPath.TryGetValue(normalized, out entry) ||
                !entry.IsCurrent())
                return false;
            content = entry.Content;
            ReportHit(entry);
            return true;
        }

        internal static bool TryGetJson(string id, out object value)
        {
            value = null;
            string content;
            if (!TryGetText(id, out content)) return false;
            try
            {
                value = PortableJsonParser.Parse(content, MaximumEntryBytes);
                return true;
            }
            catch (Exception ex)
            {
                ClientLog.Error("EarlyStartup", "snapshot_json_invalid", ex,
                    new Dictionary<string, object> { { "entry_id", id } });
                value = null;
                return false;
            }
        }

        private static Snapshot Current()
        {
            lock (Sync)
            {
                if (_attempted) return _snapshot;
                _attempted = true;
                var watch = Stopwatch.StartNew();
                string reason = "unknown";
                try
                {
                    string snapshotPath = ResolveSnapshotPath();
                    string scriptsDirectory = ResolveScriptsDirectory();
                    int processId = _processIdOverride ??
                        Process.GetCurrentProcess().Id;
                    DateTimeOffset now = _nowOverride ?? DateTimeOffset.UtcNow;
                    _snapshot = Load(
                        snapshotPath, scriptsDirectory, processId, now,
                        out reason);
                    // Reactor normally publishes long before SHVDN starts. If
                    // startup ordering is unusually fast, wait only when the
                    // process-scoped producer event already exists, then make
                    // one final atomic-file retry. Missing Reactor installs
                    // therefore pay no delay and a failed producer adds at
                    // most 100 ms before the normal disk fallback.
                    if (_snapshot == null &&
                        string.Equals(reason, "missing", StringComparison.Ordinal) &&
                        WaitForProducerAttempt(processId))
                    {
                        _snapshot = Load(
                            snapshotPath, scriptsDirectory, processId, now,
                            out reason);
                    }
                }
                catch (Exception ex)
                {
                    reason = "unexpected_error";
                    ClientLog.Error("EarlyStartup", "snapshot_load_failed", ex);
                    _snapshot = null;
                }
                finally
                {
                    watch.Stop();
                    ClientLog.Info("EarlyStartup",
                        _snapshot == null ? "snapshot_unavailable" : "snapshot_ready",
                        new Dictionary<string, object>
                        {
                            { "reason", reason },
                            { "elapsed_ms", watch.ElapsedMilliseconds },
                            { "entries", _snapshot?.ById.Count ?? 0 },
                            { "fallback", _snapshot == null },
                        });
                }
                return _snapshot;
            }
        }

        private static Snapshot Load(
            string snapshotPath, string scriptsDirectory, int processId,
            DateTimeOffset now, out string reason)
        {
            reason = "missing";
            if (string.IsNullOrWhiteSpace(snapshotPath) ||
                string.IsNullOrWhiteSpace(scriptsDirectory) ||
                !File.Exists(snapshotPath))
                return null;
            var snapshotInfo = new FileInfo(snapshotPath);
            if (snapshotInfo.Length < 2 ||
                snapshotInfo.Length > MaximumSnapshotBytes)
            {
                reason = "snapshot_size";
                return null;
            }

            string json;
            try
            {
                byte[] bytes = File.ReadAllBytes(snapshotPath);
                json = new UTF8Encoding(false, true).GetString(bytes);
            }
            catch (Exception)
            {
                reason = "snapshot_read";
                return null;
            }

            Dictionary<string, object> root;
            try
            {
                root = Object(
                    PortableJsonParser.Parse(json, MaximumSnapshotBytes),
                    "snapshot");
                ExactFields(root, "snapshot", new[]
                {
                    "schema_version", "producer", "gta_process_id",
                    "manifest_id", "created_utc", "complete", "errors",
                    "entries",
                });
                if (Integer(root, "schema_version") != SchemaVersion ||
                    !string.Equals(Text(root, "producer"),
                        "reactorv-preloader", StringComparison.Ordinal) ||
                    Integer(root, "gta_process_id") != processId ||
                    !string.Equals(Text(root, "manifest_id"), "allin1",
                        StringComparison.Ordinal) ||
                    !Boolean(root, "complete"))
                {
                    reason = "snapshot_identity";
                    return null;
                }
                object[] errors = Array(root, "errors");
                if (errors.Length > MaximumEntries)
                {
                    reason = "snapshot_errors";
                    return null;
                }
            }
            catch (Exception)
            {
                reason = "snapshot_schema";
                return null;
            }

            DateTimeOffset created;
            if (!DateTimeOffset.TryParse(
                    Text(root, "created_utc"), CultureInfo.InvariantCulture,
                    DateTimeStyles.RoundtripKind, out created) ||
                created.Offset != TimeSpan.Zero)
            {
                reason = "snapshot_timestamp";
                return null;
            }
            TimeSpan age = now - created;
            if (age > MaximumAge || age < -MaximumFutureSkew)
            {
                reason = "snapshot_stale";
                return null;
            }

            string scripts = Path.GetFullPath(scriptsDirectory)
                .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            DirectoryInfo scriptsInfo = Directory.GetParent(scripts);
            if (scriptsInfo == null)
            {
                reason = "scripts_root";
                return null;
            }
            string gameRoot = scriptsInfo.FullName.TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            object[] values = Array(root, "entries");
            if (values.Length > MaximumEntries)
            {
                reason = "entry_count";
                return null;
            }

            var byId = new Dictionary<string, Entry>(
                StringComparer.OrdinalIgnoreCase);
            var byPath = new Dictionary<string, Entry>(
                StringComparer.OrdinalIgnoreCase);
            long aggregate = 0;
            try
            {
                foreach (object value in values)
                {
                    Dictionary<string, object> item = Object(value, "entry");
                    ExactFields(item, "entry", new[]
                    {
                        "id", "path", "kind", "content", "sha256",
                        "length", "last_write_utc_ticks",
                    });
                    string id = Text(item, "id");
                    if (!IsSafeId(id) || byId.ContainsKey(id))
                        throw new InvalidDataException("Invalid snapshot entry id");
                    string relative;
                    if (!TryNormalizeRelativePath(
                            Text(item, "path"), out relative) ||
                        byPath.ContainsKey(relative))
                        throw new InvalidDataException("Invalid snapshot entry path");
                    string kind = Text(item, "kind").ToLowerInvariant();
                    if (kind != "text" && kind != "json")
                        throw new InvalidDataException("Invalid snapshot entry kind");
                    string content = Text(item, "content");
                    string digest = Text(item, "sha256").ToLowerInvariant();
                    long length = LongInteger(item, "length");
                    long writeTicks = LongInteger(item, "last_write_utc_ticks");
                    if (length < 0 || length > MaximumEntryBytes ||
                        writeTicks < DateTime.MinValue.Ticks ||
                        writeTicks > DateTime.MaxValue.Ticks ||
                        !IsSha256(digest))
                        throw new InvalidDataException("Invalid snapshot entry metadata");
                    aggregate += length;
                    if (aggregate > MaximumAggregateBytes)
                        throw new InvalidDataException("Snapshot aggregate is too large");

                    byte[] contentBytes = new UTF8Encoding(false, true)
                        .GetBytes(content);
                    if (contentBytes.LongLength != length ||
                        !string.Equals(Sha256(contentBytes), digest,
                            StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Snapshot entry digest mismatch");
                    if (kind == "json")
                        PortableJsonParser.Parse(content, MaximumEntryBytes);

                    string source = ResolveContainedPath(gameRoot, relative);
                    if (ContainsReparsePoint(gameRoot, source))
                        throw new InvalidDataException(
                            "Snapshot entry source contains a reparse point");
                    var info = new FileInfo(source);
                    if (!info.Exists || info.Length != length ||
                        info.LastWriteTimeUtc.Ticks != writeTicks)
                        throw new InvalidDataException(
                            "Snapshot entry source metadata changed");
                    var entry = new Entry(
                        id, relative, kind, content, source, gameRoot, digest,
                        length, writeTicks);
                    byId.Add(id, entry);
                    byPath.Add(relative, entry);
                }
            }
            catch (Exception)
            {
                reason = "entry_validation";
                return null;
            }

            reason = "valid";
            return new Snapshot(byId, byPath);
        }

        private static void ReportHit(Entry entry)
        {
            lock (Sync)
            {
                if (!ReportedHits.Add(entry.Id)) return;
            }
            ClientLog.Info("EarlyStartup", "snapshot_entry_used",
                new Dictionary<string, object>
                {
                    { "entry_id", entry.Id },
                    { "path", entry.RelativePath },
                    { "length", entry.Length },
                });
        }

        private static string ResolveSnapshotPath()
        {
            if (!string.IsNullOrWhiteSpace(_snapshotPathOverride))
                return _snapshotPathOverride;
            string local = Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData);
            int pid = _processIdOverride ?? Process.GetCurrentProcess().Id;
            return Path.Combine(local, "ReactorV", "Preload",
                pid.ToString(CultureInfo.InvariantCulture),
                "allin1.snapshot.json");
        }

        private static string ResolveScriptsDirectory()
        {
            if (!string.IsNullOrWhiteSpace(_scriptsDirectoryOverride))
                return _scriptsDirectoryOverride;
            string source = Allin1ExtensionApi.ResolveAssemblySourcePath(
                typeof(EarlyStartupSnapshot).Assembly);
            return Allin1ExtensionApi.ResolveScriptsDirectory(
                source, AppDomain.CurrentDomain.BaseDirectory);
        }

        private static string ResolveContainedPath(
            string gameRoot, string relativePath)
        {
            string candidate = Path.GetFullPath(Path.Combine(
                gameRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
            string prefix = gameRoot + Path.DirectorySeparatorChar;
            if (!candidate.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Snapshot entry escapes GTA root");
            return candidate;
        }

        private static bool WaitForProducerAttempt(int processId)
        {
            string eventName = @"Local\ReactorV.PreloadDataReady." +
                processId.ToString(CultureInfo.InvariantCulture);
            try
            {
                using (EventWaitHandle ready =
                    EventWaitHandle.OpenExisting(eventName))
                {
                    ready.WaitOne(ReadyWaitMilliseconds);
                    return true;
                }
            }
            catch (WaitHandleCannotBeOpenedException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
            catch (IOException) { return false; }
        }

        private static bool ContainsReparsePoint(
            string root, string candidate)
        {
            string resolvedRoot = Path.GetFullPath(root).TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string resolvedCandidate = Path.GetFullPath(candidate);
            string prefix = resolvedRoot + Path.DirectorySeparatorChar;
            if (!resolvedCandidate.StartsWith(
                    prefix, StringComparison.OrdinalIgnoreCase))
                return true;
            string relative = resolvedCandidate.Substring(prefix.Length);
            string current = resolvedRoot;
            foreach (string segment in relative.Split(new[]
            {
                Path.DirectorySeparatorChar,
                Path.AltDirectorySeparatorChar,
            }, StringSplitOptions.RemoveEmptyEntries))
            {
                current = Path.Combine(current, segment);
                if (!Directory.Exists(current) && !File.Exists(current))
                    continue;
                try
                {
                    if ((File.GetAttributes(current) &
                            FileAttributes.ReparsePoint) != 0)
                        return true;
                }
                catch (IOException) { return true; }
                catch (UnauthorizedAccessException) { return true; }
                catch (NotSupportedException) { return true; }
            }
            return false;
        }

        private static bool TryNormalizeRelativePath(
            string value, out string normalized)
        {
            normalized = null;
            if (string.IsNullOrWhiteSpace(value) || value != value.Trim() ||
                value.Contains("\\") || value.StartsWith("/", StringComparison.Ordinal) ||
                Path.IsPathRooted(value))
                return false;
            string[] parts = value.Split('/');
            if (parts.Length < 2 ||
                !string.Equals(parts[0], "scripts",
                    StringComparison.OrdinalIgnoreCase) ||
                parts.Any(part => string.IsNullOrEmpty(part) ||
                    part == "." || part == ".." || part.EndsWith(".") ||
                    part.EndsWith(" ") || part.IndexOfAny(
                        Path.GetInvalidFileNameChars()) >= 0))
                return false;
            normalized = string.Join("/", parts);
            return true;
        }

        private static bool IsSafeId(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || value.Length > 64)
                return false;
            foreach (char character in value)
                if (!(character >= 'a' && character <= 'z') &&
                    !(character >= '0' && character <= '9') &&
                    character != '.' && character != '_' && character != '-')
                    return false;
            return true;
        }

        private static bool IsSha256(string value)
        {
            if (value == null || value.Length != 64) return false;
            foreach (char character in value)
                if (!(character >= '0' && character <= '9') &&
                    !(character >= 'a' && character <= 'f'))
                    return false;
            return true;
        }

        private static string Sha256(byte[] value)
        {
            using (SHA256 digest = SHA256.Create())
                return string.Concat(digest.ComputeHash(value)
                    .Select(item => item.ToString("x2", CultureInfo.InvariantCulture)));
        }

        private static Dictionary<string, object> Object(
            object value, string label)
        {
            var result = value as Dictionary<string, object>;
            if (result == null)
                throw new InvalidDataException(label + " must be an object");
            return result;
        }

        private static object[] Array(
            Dictionary<string, object> source, string key)
        {
            object value;
            object[] result;
            if (!source.TryGetValue(key, out value) ||
                (result = value as object[]) == null)
                throw new InvalidDataException(key + " must be an array");
            return result;
        }

        private static string Text(
            Dictionary<string, object> source, string key)
        {
            object value;
            string result;
            if (!source.TryGetValue(key, out value) ||
                (result = value as string) == null)
                throw new InvalidDataException(key + " must be text");
            return result;
        }

        private static bool Boolean(
            Dictionary<string, object> source, string key)
        {
            object value;
            if (!source.TryGetValue(key, out value) || !(value is bool))
                throw new InvalidDataException(key + " must be boolean");
            return (bool)value;
        }

        private static int Integer(
            Dictionary<string, object> source, string key)
        {
            long result = LongInteger(source, key);
            if (result < int.MinValue || result > int.MaxValue)
                throw new InvalidDataException(key + " is out of range");
            return (int)result;
        }

        private static long LongInteger(
            Dictionary<string, object> source, string key)
        {
            object value;
            if (!source.TryGetValue(key, out value))
                throw new InvalidDataException("Missing field: " + key);
            if (value is int) return (int)value;
            if (value is long) return (long)value;
            if (value is decimal)
            {
                decimal number = (decimal)value;
                if (decimal.Truncate(number) == number &&
                    number >= long.MinValue && number <= long.MaxValue)
                    return (long)number;
            }
            if (value is double)
            {
                double number = (double)value;
                if (!double.IsNaN(number) && !double.IsInfinity(number) &&
                    Math.Truncate(number) == number &&
                    number >= long.MinValue && number <= long.MaxValue)
                    return (long)number;
            }
            throw new InvalidDataException(key + " must be an integer");
        }

        private static void ExactFields(
            Dictionary<string, object> source, string label,
            IEnumerable<string> expected)
        {
            var fields = new HashSet<string>(expected, StringComparer.Ordinal);
            if (source.Count != fields.Count || source.Keys.Any(
                    key => !fields.Contains(key)))
                throw new InvalidDataException(label + " contains unsupported fields");
        }

        internal static void ConfigureForTests(
            string snapshotPath, string scriptsDirectory, int processId,
            DateTimeOffset now)
        {
            lock (Sync)
            {
                _snapshotPathOverride = snapshotPath;
                _scriptsDirectoryOverride = scriptsDirectory;
                _processIdOverride = processId;
                _nowOverride = now;
                _snapshot = null;
                _attempted = false;
                ReportedHits.Clear();
            }
        }

        internal static void ResetForTests()
        {
            lock (Sync)
            {
                _snapshotPathOverride = null;
                _scriptsDirectoryOverride = null;
                _processIdOverride = null;
                _nowOverride = null;
                _snapshot = null;
                _attempted = false;
                ReportedHits.Clear();
            }
        }

        private sealed class Snapshot
        {
            internal Snapshot(
                Dictionary<string, Entry> byId,
                Dictionary<string, Entry> byPath)
            {
                ById = byId;
                ByPath = byPath;
            }

            internal Dictionary<string, Entry> ById { get; }
            internal Dictionary<string, Entry> ByPath { get; }
        }

        private sealed class Entry
        {
            internal Entry(
                string id, string relativePath, string kind, string content,
                string sourcePath, string containmentRoot, string sha256,
                long length, long writeTicks)
            {
                Id = id;
                RelativePath = relativePath;
                Kind = kind;
                Content = content;
                SourcePath = sourcePath;
                ContainmentRoot = containmentRoot;
                Sha256 = sha256;
                Length = length;
                WriteTicks = writeTicks;
            }

            internal string Id { get; }
            internal string RelativePath { get; }
            internal string Kind { get; }
            internal string Content { get; }
            internal string SourcePath { get; }
            internal string ContainmentRoot { get; }
            internal string Sha256 { get; }
            internal long Length { get; }
            internal long WriteTicks { get; }

            internal bool IsCurrent()
            {
                try
                {
                    if (ContainsReparsePoint(ContainmentRoot, SourcePath))
                        return false;
                    var info = new FileInfo(SourcePath);
                    if (!info.Exists || info.Length != Length ||
                        info.LastWriteTimeUtc.Ticks != WriteTicks)
                        return false;
                    string currentDigest;
                    using (var stream = new FileStream(
                        SourcePath, FileMode.Open, FileAccess.Read,
                        FileShare.Read, 4096, FileOptions.SequentialScan))
                    using (SHA256 digest = SHA256.Create())
                    {
                        if (stream.Length != Length) return false;
                        currentDigest = string.Concat(
                            digest.ComputeHash(stream).Select(item =>
                                item.ToString("x2", CultureInfo.InvariantCulture)));
                    }
                    var after = new FileInfo(SourcePath);
                    return !ContainsReparsePoint(
                            ContainmentRoot, SourcePath) &&
                        after.Exists && after.Length == Length &&
                        after.LastWriteTimeUtc.Ticks == WriteTicks &&
                        string.Equals(currentDigest, Sha256,
                            StringComparison.OrdinalIgnoreCase);
                }
                catch (IOException) { return false; }
                catch (UnauthorizedAccessException) { return false; }
                catch (NotSupportedException) { return false; }
                catch (CryptographicException) { return false; }
            }
        }
    }
}
