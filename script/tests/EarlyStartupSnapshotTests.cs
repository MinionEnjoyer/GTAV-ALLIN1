using System;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class EarlyStartupSnapshotTests : IDisposable
    {
        private readonly string _root;
        private readonly string _scripts;
        private readonly string _source;
        private readonly string _snapshot;
        private readonly DateTimeOffset _now = new DateTimeOffset(
            2026, 8, 28, 20, 0, 0, TimeSpan.Zero);
        private const int ProcessId = 4242;

        public EarlyStartupSnapshotTests()
        {
            _root = Path.Combine(Path.GetTempPath(),
                "allin1-preload-" + Guid.NewGuid().ToString("N"));
            _scripts = Path.Combine(_root, "scripts");
            _source = Path.Combine(_scripts, "ALLIN1.toml");
            _snapshot = Path.Combine(_root, "allin1.snapshot.json");
            Directory.CreateDirectory(_scripts);
            File.WriteAllText(_source, "[script]\ngbay_menu_enabled = false\n",
                new UTF8Encoding(false));
        }

        [Fact]
        public void ValidSnapshotServesTextByIdAndPortablePath()
        {
            WriteSnapshot();
            Configure();

            Assert.True(EarlyStartupSnapshot.TryGetText(
                "config", out string byId));
            Assert.True(EarlyStartupSnapshot.TryGetTextByPath(
                "scripts/ALLIN1.toml", out string byPath));
            Assert.Equal(File.ReadAllText(_source), byId);
            Assert.Equal(byId, byPath);
        }

        [Fact]
        public void MissingOptionalEntryDoesNotInvalidateCompleteSnapshot()
        {
            // Optional inputs are omitted by Reactor, not represented as null.
            WriteSnapshot();
            Configure();

            Assert.True(EarlyStartupSnapshot.TryGetText(
                "config", out _));
            Assert.False(EarlyStartupSnapshot.TryGetText(
                "characters", out _));
        }

        [Fact]
        public void StaleSnapshotFallsBackToDisk()
        {
            WriteSnapshot(created: _now.AddMinutes(-16));
            Configure();

            Assert.False(EarlyStartupSnapshot.TryGetText(
                "config", out _));
            Assert.Contains("gbay_menu_enabled", File.ReadAllText(_source));
        }

        [Fact]
        public void WrongProcessSnapshotIsRejected()
        {
            WriteSnapshot(processId: ProcessId + 1);
            Configure();

            Assert.False(EarlyStartupSnapshot.TryGetText(
                "config", out _));
        }

        [Fact]
        public void TamperedCachedContentIsRejected()
        {
            WriteSnapshot(digestContent: "different content with a wrong digest");
            Configure();

            Assert.False(EarlyStartupSnapshot.TryGetText(
                "config", out _));
        }

        [Fact]
        public void SelfConsistentForgedCacheIsRejectedAgainstSourceHash()
        {
            int sourceLength = new UTF8Encoding(false).GetByteCount(
                File.ReadAllText(_source));
            string forged = new string('x', sourceLength);
            WriteSnapshot(content: forged);
            Configure();

            Assert.False(EarlyStartupSnapshot.TryGetText(
                "config", out _));
        }

        [Fact]
        public void MissingSnapshotRetriesOnceWhenProducerEventExists()
        {
            Configure();
            string eventName = @"Local\ReactorV.PreloadDataReady." +
                ProcessId.ToString(CultureInfo.InvariantCulture);
            var producer = new Thread(() =>
            {
                Thread.Sleep(10);
                WriteSnapshot();
                using (var signal = EventWaitHandle.OpenExisting(eventName))
                    signal.Set();
            });
            using (var ready = new EventWaitHandle(
                false, EventResetMode.ManualReset, eventName))
            {
                producer.Start();
                Assert.True(EarlyStartupSnapshot.TryGetText(
                    "config", out string content));
                Assert.Contains("gbay_menu_enabled", content);
                producer.Join();
            }
        }

        [Fact]
        public void MalformedSnapshotIsRejected()
        {
            File.WriteAllText(_snapshot, "{not-json", new UTF8Encoding(false));
            Configure();

            Assert.False(EarlyStartupSnapshot.TryGetText(
                "config", out _));
        }

        [Fact]
        public void TraversalPathIsRejected()
        {
            WriteSnapshot(relativePath: "scripts/../outside.json");
            Configure();

            Assert.False(EarlyStartupSnapshot.TryGetText(
                "config", out _));
        }

        [Fact]
        public void SourceChangeAfterLoadInvalidatesCachedEntry()
        {
            WriteSnapshot();
            Configure();
            Assert.True(EarlyStartupSnapshot.TryGetText(
                "config", out _));

            File.WriteAllText(_source, "[script]\ngbay_menu_enabled = true\n",
                new UTF8Encoding(false));
            File.SetLastWriteTimeUtc(_source, _now.AddMinutes(1).UtcDateTime);

            Assert.False(EarlyStartupSnapshot.TryGetText(
                "config", out _));
        }

        private void Configure()
        {
            EarlyStartupSnapshot.ConfigureForTests(
                _snapshot, _scripts, ProcessId, _now);
        }

        private void WriteSnapshot(
            DateTimeOffset? created = null, int processId = ProcessId,
            string content = null, string digestContent = null,
            string relativePath = "scripts/ALLIN1.toml")
        {
            string sourceContent = content ?? File.ReadAllText(_source);
            string hashedContent = digestContent ?? sourceContent;
            byte[] sourceBytes = new UTF8Encoding(false).GetBytes(sourceContent);
            string digest = Sha256(new UTF8Encoding(false).GetBytes(hashedContent));
            long ticks = File.GetLastWriteTimeUtc(_source).Ticks;
            string json = "{" +
                "\"schema_version\":1," +
                "\"producer\":\"reactorv-preloader\"," +
                "\"gta_process_id\":" + processId.ToString(CultureInfo.InvariantCulture) + "," +
                "\"manifest_id\":\"allin1\"," +
                "\"created_utc\":" + Quote((created ?? _now).ToString("o")) + "," +
                "\"complete\":true," +
                "\"errors\":[]," +
                "\"entries\":[{" +
                    "\"id\":\"config\"," +
                    "\"path\":" + Quote(relativePath) + "," +
                    "\"kind\":\"text\"," +
                    "\"content\":" + Quote(sourceContent) + "," +
                    "\"sha256\":\"" + digest + "\"," +
                    "\"length\":" + sourceBytes.Length.ToString(CultureInfo.InvariantCulture) + "," +
                    "\"last_write_utc_ticks\":" + ticks.ToString(CultureInfo.InvariantCulture) +
                "}]}";
            File.WriteAllText(_snapshot, json, new UTF8Encoding(false));
        }

        private static string Sha256(byte[] value)
        {
            using (SHA256 digest = SHA256.Create())
            {
                var result = new StringBuilder(64);
                foreach (byte item in digest.ComputeHash(value))
                    result.Append(item.ToString("x2", CultureInfo.InvariantCulture));
                return result.ToString();
            }
        }

        private static string Quote(string value)
        {
            var result = new StringBuilder("\"");
            foreach (char character in value ?? "")
            {
                switch (character)
                {
                    case '\\': result.Append("\\\\"); break;
                    case '"': result.Append("\\\""); break;
                    case '\r': result.Append("\\r"); break;
                    case '\n': result.Append("\\n"); break;
                    case '\t': result.Append("\\t"); break;
                    default: result.Append(character); break;
                }
            }
            return result.Append('"').ToString();
        }

        public void Dispose()
        {
            EarlyStartupSnapshot.ResetForTests();
            try { Directory.Delete(_root, true); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}
