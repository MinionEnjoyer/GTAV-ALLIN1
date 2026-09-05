using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using Newtonsoft.Json;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class OfficialInteriorStockBridgeTests
    {
        [Theory]
        [InlineData(true)]
        [InlineData(false)]
        public void Exact_receipt_is_required_and_source_drift_is_rejected(bool harmony)
        {
            var policy = harmony ? OfficialInteriorStockBridgePolicy.Harmony : OfficialInteriorStockBridgePolicy.Paleto;
            string root = Path.Combine(Path.GetTempPath(), "allin1-interior-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                string pack = Path.Combine(root, "mods/update/x64/dlcpacks", policy.PackName);
                Directory.CreateDirectory(pack);
                string sourceRelative = "update/x64/dlcpacks/" + policy.SourcePack + "/dlc.rpf";
                string sourcePath = Path.Combine(root, sourceRelative);
                Directory.CreateDirectory(Path.GetDirectoryName(sourcePath));
                File.WriteAllText(sourcePath, "synthetic stock fixture");
                File.WriteAllText(Path.Combine(pack, "dlc.rpf"), "synthetic bridge fixture");
                var archive = new FileInfo(Path.Combine(pack, "dlc.rpf"));
                var source = new FileInfo(sourcePath);
                string hash = Sha(archive.FullName);
                var receipt = new Dictionary<string, object>
                {
                    ["schema"] = 1, ["status"] = "verified", ["package_id"] = "allin1.online-content",
                    ["pack_name"] = policy.PackName, ["device_name"] = policy.DeviceName,
                    ["edition"] = "enhanced", ["layout"] = "stock-reference-v1-metadata-only",
                    ["runtime_contract"] = policy.RuntimeContract, ["archive_bytes"] = archive.Length,
                    ["archive_sha256"] = hash, ["property_scope"] = policy.Key,
                    ["activation"] = "explicit-" + policy.Key + "-entry-black-transition",
                    ["black_transition_required"] = true, ["keep_resident"] = true, ["release_on_exit"] = false,
                    ["declared_groups"] = new[] { "GROUP_STARTUP", policy.DormantGroup },
                    ["stock_changeset"] = policy.StockChangeset, ["ipls"] = policy.Ipls,
                    ["source_attestation"] = new Dictionary<string, object>
                    {
                        ["pack"] = policy.SourcePack, ["archive"] = "dlc.rpf", ["source"] = "stock",
                        ["device_name"] = policy.SourceDevice, ["changeset_name"] = policy.StockChangeset,
                        ["requires_loading_screen"] = policy.RequiresLoading,
                        ["changeset_sha256"] = new string('A', 64), ["archive_sha256"] = Sha(sourcePath),
                        ["path"] = sourceRelative, ["size"] = source.Length,
                        ["mtime_ns"] = (source.LastWriteTimeUtc.Ticks - 621355968000000000L) * 100L,
                    },
                };
                var marker = new Dictionary<string, string>
                {
                    ["schema"] = "1", ["status"] = "verified", ["property_scope"] = policy.Key,
                    ["activation"] = "explicit-" + policy.Key + "-entry-black-transition",
                    ["black_transition_required"] = "true", ["keep_resident"] = "true", ["release_on_exit"] = "false",
                    ["declared_groups"] = "GROUP_STARTUP," + policy.DormantGroup,
                    ["stock_changeset"] = policy.StockChangeset, ["ipls"] = string.Join(",", policy.Ipls),
                    ["receipt"] = policy.ReceiptName, ["archive_bytes"] = archive.Length.ToString(), ["archive_sha256"] = hash,
                };
                var lines = new List<string>();
                foreach (var pair in marker) lines.Add(pair.Key + "=" + pair.Value);
                File.WriteAllLines(Path.Combine(pack, policy.MarkerName), lines);
                string rp = Path.Combine(pack, policy.ReceiptName);
                File.WriteAllText(rp, JsonConvert.SerializeObject(receipt));
                Assert.True(policy.VerifyFiles(root, "enhanced", out var identity));
                Assert.Equal(source.FullName, identity.Path);
                Assert.False(policy.VerifyFiles(root, "legacy", out _));
                receipt["ipls"] = new[] { "invented_map" };
                File.WriteAllText(rp, JsonConvert.SerializeObject(receipt));
                Assert.False(policy.VerifyFiles(root, "enhanced", out _));
                receipt["ipls"] = policy.Ipls;
                File.WriteAllText(rp, JsonConvert.SerializeObject(receipt));
                File.AppendAllText(sourcePath, "changed");
                Assert.False(policy.VerifyFiles(root, "enhanced", out _));
            }
            finally { Directory.Delete(root, true); }
        }

        [Theory]
        [InlineData("attestation")]
        [InlineData("mount")]
        [InlineData("fade")]
        [InlineData("permit")]
        [InlineData("ipl")]
        public void Missing_authority_performs_zero_map_mutations(string failure)
        {
            var bridge = new FakeBridge { Mounted = failure != "mount", Black = failure != "fade" };
            var manager = new DeferredMapContentLeaseManager(bridge, new NullLogger());
            using var transition = Transition();
            if (failure != "permit")
            {
                transition.HoldFade(() => { });
                transition.Advance(OfficialGarageTransitionPhase.LeaseRequested);
            }
            var result = DeferredMapContentRuntime.AcquireInteriorUnderBlackTransition(manager, bridge,
                DeferredMapProperty.Harmony, transition,
                failure == "ipl" ? new[] { "wrong" } : OfficialInteriorStockBridgePolicy.Harmony.Ipls,
                failure != "attestation", 100);
            Assert.False(result.Success);
            Assert.Equal(0, bridge.Mutations);
        }

        [Theory]
        [InlineData(true)]
        [InlineData(false)]
        public void Successful_entry_and_repeat_visit_reuse_resident_group(bool harmony)
        {
            var property = harmony ? DeferredMapProperty.Harmony : DeferredMapProperty.Paleto;
            var policy = OfficialInteriorStockBridgePolicy.For(property);
            var bridge = new FakeBridge();
            var manager = new DeferredMapContentLeaseManager(bridge, new NullLogger());
            using var transition = Transition();
            transition.HoldFade(() => { });
            transition.Advance(OfficialGarageTransitionPhase.LeaseRequested);
            var first = DeferredMapContentRuntime.AcquireInteriorUnderBlackTransition(
                manager, bridge, property, transition, policy.Ipls, true, 1000);
            Assert.True(first.Success);
            Assert.Equal(1, bridge.Executions);
            var descriptor = new DeferredMapContentDescriptor(property, policy.DormantGroup, policy.Ipls, true);
            Assert.Equal(DeferredMapContentOutcome.KeptResident, manager.Release(descriptor).Outcome);
            Assert.True(DeferredMapContentRuntime.AcquireInteriorUnderBlackTransition(
                manager, bridge, property, transition, policy.Ipls, true, 1000).Success);
            Assert.Equal(1, bridge.Executions);
            Assert.Equal(0, bridge.Reverts);
        }

        private static OfficialGarageTransitionCoordinator Transition() => new OfficialGarageTransitionCoordinator(
            "test", "entry", () => 0, null, () => { }, () => { });
        private static string Sha(string path)
        {
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(path))).Replace("-", "");
        }
        private sealed class NullLogger : IDeferredMapContentLogger
        {
            public void Info(string message, IDictionary<string, object> fields) { }
            public void Warn(string message, IDictionary<string, object> fields) { }
            public void Error(string message, Exception exception, IDictionary<string, object> fields) { }
        }
        private sealed class FakeBridge : IDeferredMapContentBridge
        {
            public bool Mounted = true, Black = true;
            public int Mutations, Executions, Reverts;
            private readonly HashSet<string> active = new HashSet<string>();
            public string Edition => "enhanced";
            public int MonotonicMilliseconds { get; private set; }
            public bool IsRuntimeSafe(out string reason) { reason = ""; return true; }
            public bool IsScreenFadedOut() => Black;
            public bool IsDlcPresent(string name) => Mounted;
            public uint GenerateHash(string value) => 1;
            public void ExecuteGroup(uint hash) { Mutations++; Executions++; }
            public void RevertGroup(uint hash) { Mutations++; Reverts++; }
            public void RequestIpl(string ipl) { Mutations++; active.Add(ipl); }
            public void RemoveIpl(string ipl) { Mutations++; active.Remove(ipl); }
            public bool IsIplActive(string ipl) => active.Contains(ipl);
            public void Yield(int milliseconds) { MonotonicMilliseconds += milliseconds; }
            public bool TryActivateFallback(string[] ipls, int timeout) => throw new Exception("Fallback forbidden");
        }
    }
}
