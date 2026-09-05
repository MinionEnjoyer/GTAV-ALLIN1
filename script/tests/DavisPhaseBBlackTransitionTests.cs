using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using Newtonsoft.Json;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class DavisPhaseBBlackTransitionTests
    {
        private const long ArchiveBytes = 1536L;
        private static readonly string ArchiveSha256 = new string('a', 64);
        private static readonly string ObservationSha256 = new string('b', 64);

        [Fact]
        public void Exact_phase_b_marker_and_receipt_authorize_only_the_fixed_contract()
        {
            string marker = ValidMarker();
            string receipt = ValidReceipt();

            Assert.True(DavisStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, receipt, ArchiveBytes, ArchiveSha256));
            Assert.Equal(DavisStockReferenceBridgeMode.PhaseBBlackTransition,
                DavisStockReferenceBridgePolicy.Resolve(
                    exactPhaseABootOnlyContract: false,
                    futurePhaseBReceiptVerified: true));
            Assert.True(DavisStockReferenceBridgePolicy.AllowsRuntimeMutation(
                DavisStockReferenceBridgeMode.PhaseBBlackTransition));
        }

        [Fact]
        public void Phase_b_contract_fails_closed_on_authority_or_integrity_drift()
        {
            string marker = ValidMarker();
            string receipt = ValidReceipt();
            var mutations = new[]
            {
                new ContractMutation(
                    marker + "unexpected_authority=true\n", receipt,
                    ArchiveBytes, ArchiveSha256),
                new ContractMutation(
                    ReplaceRequired(marker,
                        "proximity_activation_enabled=false",
                        "proximity_activation_enabled=true"),
                    receipt, ArchiveBytes, ArchiveSha256),
                new ContractMutation(
                    ReplaceRequired(marker,
                        "black_transition_required=true",
                        "black_transition_required=false"),
                    receipt, ArchiveBytes, ArchiveSha256),
                new ContractMutation(
                    ReplaceRequired(marker, "keep_resident=true",
                        "keep_resident=false"),
                    receipt, ArchiveBytes, ArchiveSha256),
                new ContractMutation(
                    ReplaceRequired(marker, "release_on_exit=false",
                        "release_on_exit=true"),
                    receipt, ArchiveBytes, ArchiveSha256),
                new ContractMutation(
                    "{\"unexpected_authority\":true," +
                        receipt.Substring(1),
                    marker, ArchiveBytes, ArchiveSha256,
                    receiptComesFirst: true),
                new ContractMutation(
                    ReplaceRequired(receipt,
                        "\"proximity_activation_enabled\":false",
                        "\"proximity_activation_enabled\":true"),
                    marker, ArchiveBytes, ArchiveSha256,
                    receiptComesFirst: true),
                new ContractMutation(
                    ReplaceRequired(receipt,
                        "\"activation_sources\":[\"garage_entry\"]",
                        "\"activation_sources\":[\"proximity_zone\"]"),
                    marker, ArchiveBytes, ArchiveSha256,
                    receiptComesFirst: true),
                new ContractMutation(
                    ReplaceRequired(receipt,
                        "\"requires_black_screen\":true",
                        "\"requires_black_screen\":false"),
                    marker, ArchiveBytes, ArchiveSha256,
                    receiptComesFirst: true),
                new ContractMutation(
                    ReplaceRequired(receipt,
                        "\"ipls\":[\"" +
                            DavisStockReferenceBridgePolicy.DavisIpl + "\"]",
                        "\"ipls\":[\"unapproved_ipl\"]"),
                    marker, ArchiveBytes, ArchiveSha256,
                    receiptComesFirst: true),
                new ContractMutation(marker, receipt, ArchiveBytes + 1,
                    ArchiveSha256),
                new ContractMutation(marker, receipt, ArchiveBytes,
                    new string('f', 64)),
            };

            foreach (ContractMutation mutation in mutations)
            {
                Assert.False(DavisStockReferenceBridgePolicy
                    .IsExactPhaseBBlackTransitionContract(
                        mutation.Marker, mutation.Receipt,
                        mutation.ArchiveBytes, mutation.ArchiveSha256));
            }
        }

        [Fact]
        public void Davis_phase_b_entry_orders_black_fade_phase_and_exact_ipl_before_activation()
        {
            var phases = new List<OfficialGarageTransitionPhase>();
            long clock = 0;
            var transition = new OfficialGarageTransitionCoordinator(
                "davis", "entry", () => ++clock,
                observation => phases.Add(observation.Phase),
                rollback: () => { }, forceFadeIn: () => { });

            Assert.False(transition.FadeHeld);
            transition.HoldFade(() => { });
            transition.Advance(OfficialGarageTransitionPhase.LeaseRequested);

            Assert.True(transition.FadeHeld);
            Assert.Equal(OfficialGarageTransitionPhase.LeaseRequested,
                transition.Phase);
            Assert.Equal(new[]
            {
                OfficialGarageTransitionPhase.Idle,
                OfficialGarageTransitionPhase.FadeHeld,
                OfficialGarageTransitionPhase.LeaseRequested,
            }, phases);

            string runtime = ReadRepositoryFile(
                "script", "src", "DeferredMapContentRuntime.cs");
            string phaseBMethod = Slice(runtime,
                "internal static DeferredMapContentResult " +
                    "TryAcquireDavisPhaseB(",
                "private static DeferredMapContentResult " +
                    "TryAcquireOfficial(");
            AssertOrdered(phaseBMethod,
                "IsCurrentNativeMutationAuthorized",
                "transition == null || !transition.FadeHeld",
                "OfficialGarageTransitionPhase.LeaseRequested",
                "Bridge.IsScreenFadedOut()",
                "IsExactDavisIplSet(requested)",
                "Manager.Acquire(");
            Assert.Contains("blackTransitionVerified: true", phaseBMethod);
            Assert.Contains(
                "DavisStockReferenceBridgePolicy.DormantGroup",
                phaseBMethod);

            string davis = ReadRepositoryFile(
                "script", "src", "GarageManager.Davis.cs");
            string entry = Slice(davis,
                "private static void EnterDavisGarageCore(",
                "private static void LeaveDavisGarage(");
            AssertOrdered(entry,
                "transition.HoldFade",
                "OfficialGarageTransitionPhase.LeaseRequested",
                "LoadDavisAutoShopInterior(transition)",
                "OfficialGarageTransitionPhase.Occupied");
        }

        [Fact]
        public void Davis_proximity_path_is_blocked_before_any_native_route()
        {
            DeferredMapContentResult result =
                DeferredMapContentRuntime.TryAcquireProximity(
                    DeferredMapProperty.Davis,
                    new[] { DavisStockReferenceBridgePolicy.DavisIpl }, 50);

            Assert.Equal(DeferredMapContentOutcome.MapPackUnavailable,
                result.Outcome);

            // The runtime's process-bound receipt verifier and GTA bridge are
            // intentionally not replaceable in unit tests. Pin the remaining
            // zero-native guarantee at the source boundary: Davis returns
            // before descriptor resolution, Manager, Bridge, or Function.
            string runtime = ReadRepositoryFile(
                "script", "src", "DeferredMapContentRuntime.cs");
            string officialMethod = Slice(runtime,
                "private static DeferredMapContentResult TryAcquireOfficial(",
                "private static DeferredMapContentResult " +
                    "ObserveOfficialGarageAttempt(");
            string davisGuard = Slice(officialMethod,
                "if (property == DeferredMapProperty.Davis)",
                "string[] requestedIpls");
            Assert.Contains("native_group_executed\", false", davisGuard);
            Assert.Contains("ipl_requested\", false", davisGuard);
            Assert.Contains("return observeGarageEntryCooldown", davisGuard);
            Assert.DoesNotContain("Manager.", davisGuard);
            Assert.DoesNotContain("Bridge.", davisGuard);
            Assert.DoesNotContain("Function.Call", davisGuard);
        }

        [Fact]
        public void Black_transition_lease_stays_resident_until_forced_cleanup()
        {
            var blockedBridge = new PhaseBBridge
            {
                RuntimeSafe = false,
                UnsafeReason = "visible_world",
                ActivateOnRequest = true,
            };
            var blockedManager = new DeferredMapContentLeaseManager(
                blockedBridge, new NullLogger());
            DeferredMapContentDescriptor descriptor = PhaseBDescriptor();

            DeferredMapContentResult blocked = blockedManager.Acquire(
                descriptor, 100, allowFallback: false,
                executeDeferredGroup: true,
                blackTransitionVerified: false);

            Assert.Equal(DeferredMapContentOutcome.UnsafeRuntimeState,
                blocked.Outcome);
            Assert.Equal(0, blockedBridge.ExecuteCount);
            Assert.Equal(0, blockedBridge.RequestCount);
            Assert.Equal(0, blockedManager.ReferenceCount(
                DavisStockReferenceBridgePolicy.DormantGroup));

            var bridge = new PhaseBBridge
            {
                RuntimeSafe = false,
                UnsafeReason = "visible_world",
                ActivateOnRequest = true,
            };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new NullLogger());

            DeferredMapContentResult acquired = manager.Acquire(
                descriptor, 500, allowFallback: false,
                executeDeferredGroup: true,
                blackTransitionVerified: true);

            Assert.Equal(DeferredMapContentOutcome.Activated,
                acquired.Outcome);
            Assert.Equal(1, bridge.ExecuteCount);
            Assert.Equal(1, bridge.RequestCount);
            Assert.Equal(1, manager.ReferenceCount(
                DavisStockReferenceBridgePolicy.DormantGroup));

            DeferredMapContentResult retained = manager.Release(
                descriptor, force: false, timeoutMs: 100);

            Assert.Equal(DeferredMapContentOutcome.KeptResident,
                retained.Outcome);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Equal(0, bridge.RemoveCount);
            Assert.Equal(1, manager.ReferenceCount(
                DavisStockReferenceBridgePolicy.DormantGroup));

            DeferredMapContentResult released = manager.Release(
                descriptor, force: true, timeoutMs: 100);

            Assert.Equal(DeferredMapContentOutcome.Released,
                released.Outcome);
            Assert.Equal(1, bridge.RevertCount);
            Assert.Equal(1, bridge.RemoveCount);
            Assert.Equal(0, manager.ReferenceCount(
                DavisStockReferenceBridgePolicy.DormantGroup));
        }

        [Fact]
        public void Native_mutation_attestation_is_warmed_before_entry()
        {
            string policy = ReadRepositoryFile(
                "script", "src", "DavisStockReferenceBridgePolicy.cs");
            string runtime = ReadRepositoryFile(
                "script", "src", "DeferredMapContentRuntime.cs");
            string startup = ReadRepositoryFile(
                "script", "src", "GbayShop.cs");

            Assert.Contains("IsCurrentNativeMutationAuthorized", policy);
            Assert.Contains("AsyncSourceArchiveAttestationCache", policy);
            Assert.Contains("WarmUpCurrentNativeMutationAuthorization", policy);
            Assert.Contains("VerifySourceArchiveAttestation", policy);
            Assert.DoesNotContain(
                "NativeMutationVerificationCompleted", policy);
            Assert.Contains(
                "IsCurrentNativeMutationAuthorized", runtime);
            Assert.Contains(
                "davis_phase_b_native_attestation_unavailable", runtime);
            Assert.Contains(
                "WarmUpCurrentNativeMutationAuthorization", startup);
        }

        [Fact]
        public void Native_source_archive_identity_checks_full_hash_when_required()
        {
            string path = Path.GetTempFileName();
            try
            {
                File.WriteAllBytes(path, new byte[] { 1, 2, 3, 4, 5 });
                var file = new FileInfo(path);
                const long UnixEpochTicks = 621355968000000000L;
                long mtimeNanoseconds =
                    (file.LastWriteTimeUtc.Ticks - UnixEpochTicks) * 100L;
                string sha256;
                using (var algorithm = SHA256.Create())
                using (var stream = File.OpenRead(path))
                    sha256 = BitConverter.ToString(
                        algorithm.ComputeHash(stream)).Replace("-", "");

                Assert.True(DavisStockReferenceBridgePolicy
                    .IsExactSourceArchiveIdentity(
                        path, file.Length, mtimeNanoseconds, sha256, true));
                Assert.False(DavisStockReferenceBridgePolicy
                    .IsExactSourceArchiveIdentity(
                        path, file.Length, mtimeNanoseconds,
                        new string('f', 64), true));
                Assert.True(DavisStockReferenceBridgePolicy
                    .IsExactSourceArchiveIdentity(
                        path, file.Length, mtimeNanoseconds,
                        new string('f', 64), false));
                Assert.False(DavisStockReferenceBridgePolicy
                    .IsExactSourceArchiveIdentity(
                        path, file.Length + 1, mtimeNanoseconds,
                        sha256, true));
            }
            finally
            {
                File.Delete(path);
            }
        }

        private static DeferredMapContentDescriptor PhaseBDescriptor() =>
            new DeferredMapContentDescriptor(
                DeferredMapProperty.Davis,
                DavisStockReferenceBridgePolicy.DormantGroup,
                new[] { DavisStockReferenceBridgePolicy.DavisIpl },
                keepResident: true);

        private static string ValidMarker() =>
            DavisStockReferenceBridgePolicy.PhaseBMarkerPreamble + "\n" +
            "canary_id=" + DavisStockReferenceBridgePolicy.PhaseBCanaryId + "\n" +
            "schema=5\n" +
            "status=" + DavisStockReferenceBridgePolicy.PhaseBMarkerStatus + "\n" +
            "phase=" + DavisStockReferenceBridgePolicy.PhaseBName + "\n" +
            "layout=" + DavisStockReferenceBridgePolicy.PhaseALayout + "\n" +
            "runtime_contract=" +
                DavisStockReferenceBridgePolicy.PhaseBRuntimeContract + "\n" +
            "archive_registration=metadata-only\n" +
            "activation=" + DavisStockReferenceBridgePolicy.PhaseBActivation + "\n" +
            "activation_scope=" +
                DavisStockReferenceBridgePolicy.PhaseBActivationScope + "\n" +
            "property_scope=davis\n" +
            "asset_count=0\n" +
            "data_file_count=0\n" +
            "startup_changeset=" +
                DavisStockReferenceBridgePolicy.StartupChangeset + "\n" +
            "dormant_group_count=1\n" +
            "declared_groups=GROUP_STARTUP," +
                DavisStockReferenceBridgePolicy.DormantGroup + "\n" +
            "stock_changesets=" +
                DavisStockReferenceBridgePolicy.StockChangeset + "\n" +
            "ipls=" + DavisStockReferenceBridgePolicy.DavisIpl + "\n" +
            "native_group_execution_enabled=true\n" +
            "runtime_ipl_requests_enabled=true\n" +
            "proximity_activation_enabled=false\n" +
            "black_transition_required=true\n" +
            "keep_resident=true\n" +
            "release_on_exit=false\n" +
            "gameconfig_changed=false\n" +
            "native_host_installed=false\n" +
            "phase_a_canary_id=" +
                DavisStockReferenceBridgePolicy.PhaseACanaryId + "\n" +
            "phase_a_transaction_id=" + new string('1', 32) + "\n" +
            "phase_a_observation_sha256=" + ObservationSha256 + "\n" +
            "receipt=" + DavisStockReferenceBridgePolicy.ReceiptName + "\n" +
            "archive_bytes=" + ArchiveBytes + "\n" +
            "archive_sha256=" + ArchiveSha256 + "\n";

        private static string ValidReceipt()
        {
            var group = new Dictionary<string, object>
            {
                { "property", "davis" },
                { "group", DavisStockReferenceBridgePolicy.DormantGroup },
                { "changesets", new[]
                    { DavisStockReferenceBridgePolicy.StockChangeset } },
                { "ipls", new[]
                    { DavisStockReferenceBridgePolicy.DavisIpl } },
                { "activation_enabled", true },
                { "activation_sources", new[] { "garage_entry" } },
                { "requires_black_screen", true },
                { "keep_resident", true },
                { "release_on_exit", false },
            };
            var source = new Dictionary<string, object>
            {
                { "pack", "mptuner" },
                { "archive", "dlc.rpf" },
                { "source", "stock" },
                { "path", "update/x64/dlcpacks/mptuner/dlc.rpf" },
                { "size", 987654321L },
                { "mtime_ns", 1776402815896690400L },
                { "archive_sha256", new string('c', 64) },
                { "device_name", "dlc_mpTuner" },
                { "stock_startup_group", "GROUP_STARTUP" },
                { "stock_startup_changeset", "MPTUNER_AUTOGEN" },
                { "stock_map_group", "GROUP_MAP" },
                { "stock_map_group_changesets", new[]
                    {
                        "MPTUNER_MAP_UPDATE",
                        "MPTUNER_MAP_UPDATE_NAVMESH_ONLY",
                    }
                },
                { "changeset_name",
                    DavisStockReferenceBridgePolicy.StockChangeset },
            };
            var parent = new Dictionary<string, object>
            {
                { "canary_id", DavisStockReferenceBridgePolicy.PhaseACanaryId },
                { "transaction_id", new string('1', 32) },
                { "archive_sha256", ArchiveSha256 },
                { "marker_sha256", new string('d', 64) },
                { "runtime_receipt_sha256", new string('e', 64) },
            };
            var receipt = new Dictionary<string, object>
            {
                { "schema", 5 },
                { "canary_id", DavisStockReferenceBridgePolicy.PhaseBCanaryId },
                { "status", DavisStockReferenceBridgePolicy.PhaseBReceiptStatus },
                { "phase", DavisStockReferenceBridgePolicy.PhaseBName },
                { "package_id", DavisStockReferenceBridgePolicy.PackageId },
                { "pack_name", DavisStockReferenceBridgePolicy.PackName },
                { "device_name", DavisStockReferenceBridgePolicy.DeviceName },
                { "edition", "enhanced" },
                { "layout", DavisStockReferenceBridgePolicy.PhaseALayout },
                { "runtime_contract",
                    DavisStockReferenceBridgePolicy.PhaseBRuntimeContract },
                { "archive_registration", "metadata-only" },
                { "activation", DavisStockReferenceBridgePolicy.PhaseBActivation },
                { "activation_scope",
                    DavisStockReferenceBridgePolicy.PhaseBActivationScope },
                { "property_scope", "davis" },
                { "asset_count", 0 },
                { "data_file_count", 0 },
                { "startup_changeset",
                    DavisStockReferenceBridgePolicy.StartupChangeset },
                { "dormant_group_count", 1 },
                { "declared_groups", new[]
                    {
                        "GROUP_STARTUP",
                        DavisStockReferenceBridgePolicy.DormantGroup,
                    }
                },
                { "stock_changesets", new[]
                    { DavisStockReferenceBridgePolicy.StockChangeset } },
                { "ipls", new[]
                    { DavisStockReferenceBridgePolicy.DavisIpl } },
                { "groups", new object[] { group } },
                { "native_group_execution_enabled", true },
                { "runtime_ipl_requests_enabled", true },
                { "proximity_activation_enabled", false },
                { "black_transition_required", true },
                { "keep_resident", true },
                { "release_on_exit", false },
                { "gameconfig_changed", false },
                { "native_host_installed", false },
                { "archive_bytes", ArchiveBytes },
                { "archive_sha256", ArchiveSha256 },
                { "source_attestation", source },
                { "phase_a_parent", parent },
                { "phase_a_observation_sha256", ObservationSha256 },
            };
            return JsonConvert.SerializeObject(receipt);
        }

        private static string ReplaceRequired(
            string value, string oldValue, string newValue)
        {
            string changed = value.Replace(oldValue, newValue);
            Assert.NotEqual(value, changed);
            return changed;
        }

        private static string ReadRepositoryFile(params string[] segments)
        {
            string path = RepositoryRoot();
            foreach (string segment in segments)
                path = Path.Combine(path, segment);
            return File.ReadAllText(path);
        }

        private static string RepositoryRoot()
        {
            string current = AppContext.BaseDirectory;
            while (!string.IsNullOrEmpty(current))
            {
                if (File.Exists(Path.Combine(current,
                        "allin1.workspace.json")))
                    return current;
                current = Directory.GetParent(current)?.FullName;
            }
            throw new DirectoryNotFoundException(
                "Could not locate the ALLIN1 repository root.");
        }

        private static string Slice(string value, string start, string end)
        {
            int startAt = value.IndexOf(start, StringComparison.Ordinal);
            Assert.True(startAt >= 0, "Missing source anchor: " + start);
            int endAt = value.IndexOf(end, startAt + start.Length,
                StringComparison.Ordinal);
            Assert.True(endAt > startAt, "Missing source anchor: " + end);
            return value.Substring(startAt, endAt - startAt);
        }

        private static void AssertOrdered(string value, params string[] tokens)
        {
            int previous = -1;
            foreach (string token in tokens)
            {
                int current = value.IndexOf(token, previous + 1,
                    StringComparison.Ordinal);
                Assert.True(current > previous,
                    "Expected ordered source token: " + token);
                previous = current;
            }
        }

        private sealed class ContractMutation
        {
            internal ContractMutation(
                string marker, string receipt, long archiveBytes,
                string archiveSha256, bool receiptComesFirst = false)
            {
                Marker = receiptComesFirst ? receipt : marker;
                Receipt = receiptComesFirst ? marker : receipt;
                ArchiveBytes = archiveBytes;
                ArchiveSha256 = archiveSha256;
            }

            internal string Marker { get; }
            internal string Receipt { get; }
            internal long ArchiveBytes { get; }
            internal string ArchiveSha256 { get; }
        }

        private sealed class PhaseBBridge : IDeferredMapContentBridge
        {
            private readonly HashSet<string> _active =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            internal bool RuntimeSafe;
            internal string UnsafeReason = string.Empty;
            internal bool ActivateOnRequest;
            internal int ExecuteCount;
            internal int RevertCount;
            internal int RequestCount;
            internal int RemoveCount;

            public string Edition => "enhanced";
            public int MonotonicMilliseconds { get; private set; }
            public bool IsScreenFadedOut() => true;
            public bool IsDlcPresent(string packName) => true;

            public bool IsRuntimeSafe(out string reason)
            {
                reason = UnsafeReason;
                return RuntimeSafe;
            }

            public uint GenerateHash(string value) => 0xDA715u;
            public void ExecuteGroup(uint groupHash) => ExecuteCount++;
            public void RevertGroup(uint groupHash) => RevertCount++;

            public void RequestIpl(string ipl)
            {
                RequestCount++;
                if (ActivateOnRequest) _active.Add(ipl);
            }

            public void RemoveIpl(string ipl)
            {
                RemoveCount++;
                _active.Remove(ipl);
            }

            public bool IsIplActive(string ipl) => _active.Contains(ipl);

            public void Yield(int milliseconds) =>
                MonotonicMilliseconds += Math.Max(1, milliseconds);

            public bool TryActivateFallback(string[] ipls, int timeoutMs) =>
                false;
        }

        private sealed class NullLogger : IDeferredMapContentLogger
        {
            public void Info(string message,
                IDictionary<string, object> fields) { }
            public void Warn(string message,
                IDictionary<string, object> fields) { }
            public void Error(string message, Exception exception,
                IDictionary<string, object> fields) { }
        }
    }
}
