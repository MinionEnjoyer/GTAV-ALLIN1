using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using Newtonsoft.Json;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GrapeseedStockReferenceBridgePolicyTests
    {
        private const long ArchiveBytes = 4096;
        private static readonly string ArchiveHash = new string('a', 64);
        private static readonly string ObservationHash = new string('c', 64);

        [Fact]
        public void Exact_phase_b_contract_is_property_scoped_and_strict()
        {
            string marker = PhaseBMarker();
            string receipt = JsonConvert.SerializeObject(PhaseBReceipt());

            Assert.True(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, receipt, ArchiveBytes, ArchiveHash));
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker.Replace("property_scope=grapeseed",
                        "property_scope=davis"),
                    receipt, ArchiveBytes, ArchiveHash));
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker + "unexpected=true\n",
                    receipt, ArchiveBytes, ArchiveHash));

            Dictionary<string, object> expanded = PhaseBReceipt();
            expanded["unexpected"] = true;
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, JsonConvert.SerializeObject(expanded),
                    ArchiveBytes, ArchiveHash));
        }

        [Fact]
        public void Exact_phase_a_contract_remains_boot_only()
        {
            string marker = PhaseAMarker();
            string receipt = JsonConvert.SerializeObject(PhaseAReceipt());

            Assert.True(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseABootOnlyContract(
                    marker, receipt, ArchiveBytes, ArchiveHash));
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, receipt, ArchiveBytes, ArchiveHash));
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseABootOnlyContract(
                    marker.Replace(
                        "native_group_execution_enabled=false",
                        "native_group_execution_enabled=true"),
                    receipt, ArchiveBytes, ArchiveHash));
        }

        [Fact]
        public void Route_semantics_and_effective_source_are_pinned()
        {
            string marker = PhaseBMarker();
            Dictionary<string, object> receipt = PhaseBReceipt();
            var source = (Dictionary<string, object>)
                receipt["source_attestation"];
            source["path"] =
                "update/x64/dlcpacks/mptuner/dlc.rpf";
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, JsonConvert.SerializeObject(receipt),
                    ArchiveBytes, ArchiveHash));

            receipt = PhaseBReceipt();
            source = (Dictionary<string, object>)receipt["source_attestation"];
            source["stock_startup_changesets"] = new object[]
            {
                "MPHEIST_AUTOGEN",
            };
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, JsonConvert.SerializeObject(receipt),
                    ArchiveBytes, ArchiveHash));

            receipt = PhaseBReceipt();
            source = (Dictionary<string, object>)receipt["source_attestation"];
            var semantics = (Dictionary<string, object>)
                source["official_semantics"];
            semantics["requires_loading_screen"] = false;
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, JsonConvert.SerializeObject(receipt),
                    ArchiveBytes, ArchiveHash));

            receipt = PhaseBReceipt();
            source = (Dictionary<string, object>)receipt["source_attestation"];
            source["setup_order"] = 11;
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker, JsonConvert.SerializeObject(receipt),
                    ArchiveBytes, ArchiveHash));

            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactPhaseBBlackTransitionContract(
                    marker.Replace(new string('b', 32), new string('9', 32)),
                    JsonConvert.SerializeObject(PhaseBReceipt()),
                    ArchiveBytes, ArchiveHash));
        }

        [Fact]
        public void Bridge_pack_layout_rejects_reparse_nonregular_and_extra_entries()
        {
            var exact = new Dictionary<string, bool>(
                StringComparer.OrdinalIgnoreCase)
            {
                { "dlc.rpf", true },
                { GrapeseedStockReferenceBridgePolicy.MarkerName, true },
                { GrapeseedStockReferenceBridgePolicy.ReceiptName, true },
            };
            Assert.True(GrapeseedStockReferenceBridgePolicy
                .IsExactOwnedPackLayoutObservation(false, exact));
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactOwnedPackLayoutObservation(true, exact));

            exact[GrapeseedStockReferenceBridgePolicy.ReceiptName] = false;
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactOwnedPackLayoutObservation(false, exact));
            exact[GrapeseedStockReferenceBridgePolicy.ReceiptName] = true;
            exact["unowned.bin"] = true;
            Assert.False(GrapeseedStockReferenceBridgePolicy
                .IsExactOwnedPackLayoutObservation(false, exact));
        }

        [Fact]
        public void Filesystem_isolation_rejects_retired_pack_and_native_maphost()
        {
            string root = CreateIsolatedGameRoot();
            try
            {
                Assert.True(GrapeseedStockReferenceBridgePolicy
                    .HasRequiredFilesystemIsolation(root));

                string retired = Path.Combine(root, "mods", "update", "x64",
                    "dlcpacks", "allin1_maps");
                Directory.CreateDirectory(retired);
                Assert.False(GrapeseedStockReferenceBridgePolicy
                    .HasRequiredFilesystemIsolation(root));
                Directory.Delete(retired);

                File.WriteAllBytes(Path.Combine(root,
                    "CommunityMapHost.Experimental.asi"), new byte[] { 1 });
                Assert.False(GrapeseedStockReferenceBridgePolicy
                    .HasRequiredFilesystemIsolation(root));
                File.Delete(Path.Combine(root,
                    "CommunityMapHost.Experimental.asi"));

                string scripts = Path.Combine(root, "scripts");
                Directory.CreateDirectory(scripts);
                File.WriteAllBytes(Path.Combine(scripts,
                    "ALLIN1MapHost-Enhanced.asi"), new byte[] { 1 });
                Assert.False(GrapeseedStockReferenceBridgePolicy
                    .HasRequiredFilesystemIsolation(root));
            }
            finally
            {
                Directory.Delete(root, recursive: true);
            }
        }

        [Fact]
        public void Effective_source_resolution_tracks_mods_override_insertion_and_removal()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-grapeseed-source-" + Guid.NewGuid().ToString("N"));
            string stock = Path.Combine(root, "update", "x64", "dlcpacks",
                "mpheist", "dlc.rpf");
            string mods = Path.Combine(root, "mods", "update", "x64",
                "dlcpacks", "mpheist", "dlc.rpf");
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(stock));
                File.WriteAllBytes(stock, new byte[] { 1 });
                Assert.True(GrapeseedStockReferenceBridgePolicy
                    .TryResolveEffectiveSourceArchive(root, out string path,
                        out string provenance, out string relative));
                Assert.Equal("stock", provenance);
                Assert.Equal(Path.GetFullPath(stock), path);
                Assert.Equal(Path.Combine("update", "x64", "dlcpacks",
                    "mpheist", "dlc.rpf"), relative);

                Directory.CreateDirectory(Path.GetDirectoryName(mods));
                File.WriteAllBytes(mods, new byte[] { 2 });
                Assert.True(GrapeseedStockReferenceBridgePolicy
                    .TryResolveEffectiveSourceArchive(root, out path,
                        out provenance, out relative));
                Assert.Equal("mods", provenance);
                Assert.Equal(Path.GetFullPath(mods), path);

                File.Delete(mods);
                Assert.True(GrapeseedStockReferenceBridgePolicy
                    .TryResolveEffectiveSourceArchive(root, out path,
                        out provenance, out relative));
                Assert.Equal("stock", provenance);
                Assert.Equal(Path.GetFullPath(stock), path);
            }
            finally
            {
                Directory.Delete(root, recursive: true);
            }
        }

        [Fact]
        public void Mounted_pack_proof_fails_closed_on_absence_or_probe_error()
        {
            var bridge = new MountedProofBridge();
            Assert.False(DeferredMapContentRuntime.HasMountedPackProof(
                bridge, GrapeseedStockReferenceBridgePolicy.PackName));

            bridge.Present = true;
            Assert.True(DeferredMapContentRuntime.HasMountedPackProof(
                bridge, GrapeseedStockReferenceBridgePolicy.PackName));
            Assert.Equal(GrapeseedStockReferenceBridgePolicy.PackName,
                bridge.LastPackName);

            bridge.Throw = true;
            Assert.False(DeferredMapContentRuntime.HasMountedPackProof(
                bridge, GrapeseedStockReferenceBridgePolicy.PackName));
            Assert.False(DeferredMapContentRuntime.HasMountedPackProof(
                bridge, string.Empty));
        }

        [Fact]
        public void Full_archive_attestations_are_serialized_process_wide()
        {
            var first = new AsyncSourceArchiveAttestationCache();
            var second = new AsyncSourceArchiveAttestationCache();
            var firstEntered = new ManualResetEventSlim(false);
            var releaseFirst = new ManualResetEventSlim(false);
            var secondEntered = new ManualResetEventSlim(false);
            var firstIdentity = Identity("first.rpf", '1');
            var secondIdentity = Identity("second.rpf", '2');
            int active = 0;
            int maximumActive = 0;

            Assert.True(first.Begin(firstIdentity, _ =>
            {
                int current = Interlocked.Increment(ref active);
                UpdateMaximum(ref maximumActive, current);
                firstEntered.Set();
                releaseFirst.Wait(TimeSpan.FromSeconds(5));
                Interlocked.Decrement(ref active);
                return true;
            }));
            Assert.True(firstEntered.Wait(TimeSpan.FromSeconds(5)));

            Assert.True(second.Begin(secondIdentity, _ =>
            {
                int current = Interlocked.Increment(ref active);
                UpdateMaximum(ref maximumActive, current);
                secondEntered.Set();
                Interlocked.Decrement(ref active);
                return true;
            }));
            Assert.False(secondEntered.Wait(TimeSpan.FromMilliseconds(100)));

            releaseFirst.Set();
            Assert.True(secondEntered.Wait(TimeSpan.FromSeconds(5)));
            Assert.True(WaitUntil(() =>
                first.IsCompletedVerified(firstIdentity) &&
                second.IsCompletedVerified(secondIdentity)));
            Assert.Equal(1, maximumActive);
        }

        [Fact]
        public void Queued_stale_attestation_generation_never_executes_or_authorizes()
        {
            var blocker = new AsyncSourceArchiveAttestationCache();
            var cache = new AsyncSourceArchiveAttestationCache();
            var blockerEntered = new ManualResetEventSlim(false);
            var releaseBlocker = new ManualResetEventSlim(false);
            var currentEntered = new ManualResetEventSlim(false);
            var blockerIdentity = Identity("blocker.rpf", '3');
            var staleIdentity = Identity("stale.rpf", '4');
            var currentIdentity = Identity("current.rpf", '5');
            int staleExecutions = 0;

            blocker.Begin(blockerIdentity, _ =>
            {
                blockerEntered.Set();
                releaseBlocker.Wait(TimeSpan.FromSeconds(5));
                return true;
            });
            Assert.True(blockerEntered.Wait(TimeSpan.FromSeconds(5)));
            Assert.True(cache.Begin(staleIdentity, _ =>
            {
                Interlocked.Increment(ref staleExecutions);
                return true;
            }));
            Assert.True(cache.Begin(currentIdentity, _ =>
            {
                currentEntered.Set();
                return true;
            }));

            releaseBlocker.Set();
            Assert.True(currentEntered.Wait(TimeSpan.FromSeconds(5)));
            Assert.True(WaitUntil(() =>
                cache.IsCompletedVerified(currentIdentity)));
            Assert.Equal(0, staleExecutions);
            Assert.False(cache.IsCompletedVerified(staleIdentity));
        }

        private static string PhaseAMarker()
        {
            return Marker(
                GrapeseedStockReferenceBridgePolicy.PhaseAMarkerPreamble,
                new Dictionary<string, string>
                {
                    { "canary_id", GrapeseedStockReferenceBridgePolicy.PhaseACanaryId },
                    { "schema", "4" },
                    { "status", GrapeseedStockReferenceBridgePolicy.PhaseAMarkerStatus },
                    { "phase", GrapeseedStockReferenceBridgePolicy.PhaseAName },
                    { "layout", GrapeseedStockReferenceBridgePolicy.Layout },
                    { "runtime_contract", GrapeseedStockReferenceBridgePolicy.PhaseARuntimeContract },
                    { "archive_registration", "metadata-only" },
                    { "activation", GrapeseedStockReferenceBridgePolicy.PhaseAActivation },
                    { "property_scope", "grapeseed" },
                    { "asset_count", "0" },
                    { "data_file_count", "0" },
                    { "startup_changeset", GrapeseedStockReferenceBridgePolicy.StartupChangeset },
                    { "dormant_group_count", "1" },
                    { "declared_groups", "GROUP_STARTUP," + GrapeseedStockReferenceBridgePolicy.DormantGroup },
                    { "stock_changesets", GrapeseedStockReferenceBridgePolicy.StockChangeset },
                    { "ipls", GrapeseedStockReferenceBridgePolicy.GrapeseedIpl },
                    { "native_group_execution_enabled", "false" },
                    { "runtime_ipl_requests_enabled", "false" },
                    { "gameconfig_changed", "false" },
                    { "native_host_installed", "false" },
                    { "receipt", GrapeseedStockReferenceBridgePolicy.ReceiptName },
                    { "archive_bytes", ArchiveBytes.ToString() },
                    { "archive_sha256", ArchiveHash },
                });
        }

        private static Dictionary<string, object> PhaseAReceipt()
        {
            return new Dictionary<string, object>
            {
                { "schema", 4 },
                { "canary_id", GrapeseedStockReferenceBridgePolicy.PhaseACanaryId },
                { "status", GrapeseedStockReferenceBridgePolicy.PhaseAReceiptStatus },
                { "phase", GrapeseedStockReferenceBridgePolicy.PhaseAName },
                { "package_id", GrapeseedStockReferenceBridgePolicy.PackageId },
                { "pack_name", GrapeseedStockReferenceBridgePolicy.PackName },
                { "device_name", GrapeseedStockReferenceBridgePolicy.DeviceName },
                { "edition", "enhanced" },
                { "layout", GrapeseedStockReferenceBridgePolicy.Layout },
                { "runtime_contract", GrapeseedStockReferenceBridgePolicy.PhaseARuntimeContract },
                { "archive_registration", "metadata-only" },
                { "activation", GrapeseedStockReferenceBridgePolicy.PhaseAActivation },
                { "property_scope", "grapeseed" },
                { "asset_count", 0 },
                { "data_file_count", 0 },
                { "startup_changeset", GrapeseedStockReferenceBridgePolicy.StartupChangeset },
                { "dormant_group_count", 1 },
                { "declared_groups", new object[] { "GROUP_STARTUP", GrapeseedStockReferenceBridgePolicy.DormantGroup } },
                { "stock_changesets", new object[] { GrapeseedStockReferenceBridgePolicy.StockChangeset } },
                { "ipls", new object[] { GrapeseedStockReferenceBridgePolicy.GrapeseedIpl } },
                { "groups", new object[] { new Dictionary<string, object>
                    {
                        { "property", "grapeseed" },
                        { "group", GrapeseedStockReferenceBridgePolicy.DormantGroup },
                        { "changesets", new object[] { GrapeseedStockReferenceBridgePolicy.StockChangeset } },
                        { "ipls", new object[] { GrapeseedStockReferenceBridgePolicy.GrapeseedIpl } },
                        { "activation_enabled", false },
                    } } },
                { "native_group_execution_enabled", false },
                { "runtime_ipl_requests_enabled", false },
                { "gameconfig_changed", false },
                { "native_host_installed", false },
                { "archive_bytes", ArchiveBytes },
                { "archive_sha256", ArchiveHash },
                { "source_attestation", SourceAttestation() },
            };
        }

        private static string PhaseBMarker()
        {
            return Marker(
                GrapeseedStockReferenceBridgePolicy.PhaseBMarkerPreamble,
                new Dictionary<string, string>
                {
                    { "canary_id", GrapeseedStockReferenceBridgePolicy.PhaseBCanaryId },
                    { "schema", "5" },
                    { "status", GrapeseedStockReferenceBridgePolicy.PhaseBMarkerStatus },
                    { "phase", GrapeseedStockReferenceBridgePolicy.PhaseBName },
                    { "layout", GrapeseedStockReferenceBridgePolicy.Layout },
                    { "runtime_contract", GrapeseedStockReferenceBridgePolicy.PhaseBRuntimeContract },
                    { "archive_registration", "metadata-only" },
                    { "activation", GrapeseedStockReferenceBridgePolicy.PhaseBActivation },
                    { "activation_scope", GrapeseedStockReferenceBridgePolicy.PhaseBActivationScope },
                    { "property_scope", "grapeseed" },
                    { "asset_count", "0" },
                    { "data_file_count", "0" },
                    { "startup_changeset", GrapeseedStockReferenceBridgePolicy.StartupChangeset },
                    { "dormant_group_count", "1" },
                    { "declared_groups", "GROUP_STARTUP," + GrapeseedStockReferenceBridgePolicy.DormantGroup },
                    { "stock_changesets", GrapeseedStockReferenceBridgePolicy.StockChangeset },
                    { "ipls", GrapeseedStockReferenceBridgePolicy.GrapeseedIpl },
                    { "native_group_execution_enabled", "true" },
                    { "runtime_ipl_requests_enabled", "true" },
                    { "proximity_activation_enabled", "false" },
                    { "black_transition_required", "true" },
                    { "keep_resident", "true" },
                    { "release_on_exit", "false" },
                    { "gameconfig_changed", "false" },
                    { "native_host_installed", "false" },
                    { "phase_a_canary_id", GrapeseedStockReferenceBridgePolicy.PhaseACanaryId },
                    { "phase_a_transaction_id", new string('b', 32) },
                    { "phase_a_observation_sha256", ObservationHash },
                    { "receipt", GrapeseedStockReferenceBridgePolicy.ReceiptName },
                    { "archive_bytes", ArchiveBytes.ToString() },
                    { "archive_sha256", ArchiveHash },
                });
        }

        private static Dictionary<string, object> PhaseBReceipt()
        {
            return new Dictionary<string, object>
            {
                { "schema", 5 },
                { "canary_id", GrapeseedStockReferenceBridgePolicy.PhaseBCanaryId },
                { "status", GrapeseedStockReferenceBridgePolicy.PhaseBReceiptStatus },
                { "phase", GrapeseedStockReferenceBridgePolicy.PhaseBName },
                { "package_id", GrapeseedStockReferenceBridgePolicy.PackageId },
                { "pack_name", GrapeseedStockReferenceBridgePolicy.PackName },
                { "device_name", GrapeseedStockReferenceBridgePolicy.DeviceName },
                { "edition", "enhanced" },
                { "layout", GrapeseedStockReferenceBridgePolicy.Layout },
                { "runtime_contract", GrapeseedStockReferenceBridgePolicy.PhaseBRuntimeContract },
                { "archive_registration", "metadata-only" },
                { "activation", GrapeseedStockReferenceBridgePolicy.PhaseBActivation },
                { "activation_scope", GrapeseedStockReferenceBridgePolicy.PhaseBActivationScope },
                { "property_scope", "grapeseed" },
                { "asset_count", 0 },
                { "data_file_count", 0 },
                { "startup_changeset", GrapeseedStockReferenceBridgePolicy.StartupChangeset },
                { "dormant_group_count", 1 },
                { "declared_groups", new object[] { "GROUP_STARTUP", GrapeseedStockReferenceBridgePolicy.DormantGroup } },
                { "stock_changesets", new object[] { GrapeseedStockReferenceBridgePolicy.StockChangeset } },
                { "ipls", new object[] { GrapeseedStockReferenceBridgePolicy.GrapeseedIpl } },
                { "groups", new object[] { new Dictionary<string, object>
                    {
                        { "property", "grapeseed" },
                        { "group", GrapeseedStockReferenceBridgePolicy.DormantGroup },
                        { "changesets", new object[] { GrapeseedStockReferenceBridgePolicy.StockChangeset } },
                        { "ipls", new object[] { GrapeseedStockReferenceBridgePolicy.GrapeseedIpl } },
                        { "activation_enabled", true },
                        { "activation_sources", new object[] { "garage_entry" } },
                        { "requires_black_screen", true },
                        { "keep_resident", true },
                        { "release_on_exit", false },
                    } } },
                { "native_group_execution_enabled", true },
                { "runtime_ipl_requests_enabled", true },
                { "proximity_activation_enabled", false },
                { "black_transition_required", true },
                { "keep_resident", true },
                { "release_on_exit", false },
                { "gameconfig_changed", false },
                { "native_host_installed", false },
                { "archive_bytes", ArchiveBytes },
                { "archive_sha256", ArchiveHash },
                { "source_attestation", SourceAttestation() },
                { "phase_a_parent", new Dictionary<string, object>
                    {
                        { "canary_id", GrapeseedStockReferenceBridgePolicy.PhaseACanaryId },
                        { "transaction_id", new string('b', 32) },
                        { "archive_sha256", ArchiveHash },
                        { "marker_sha256", new string('d', 64) },
                        { "runtime_receipt_sha256", new string('e', 64) },
                    } },
                { "phase_a_observation_sha256", ObservationHash },
            };
        }

        private static Dictionary<string, object> SourceAttestation()
        {
            return new Dictionary<string, object>
            {
                { "pack", "mpheist" },
                { "archive", "dlc.rpf" },
                { "source", "stock" },
                { "path", "update/x64/dlcpacks/mpheist/dlc.rpf" },
                { "size", 2438424576L },
                { "mtime_ns", 1776402815892310800L },
                { "archive_sha256", new string('f', 64) },
                { "content_xml_bytes", 116991 },
                { "content_xml_sha256", new string('1', 64) },
                { "setup2_xml_bytes", 2273 },
                { "setup2_xml_sha256", new string('2', 64) },
                { "device_name", "dlcMPHeist" },
                { "device_name_sha256", new string('3', 64) },
                { "setup_order", 10 },
                { "stock_startup_group", "GROUP_STARTUP" },
                { "stock_startup_changesets", new object[]
                    {
                        "MPHEIST_COMMON_VEHICLE_INSURGENT",
                        "MPHEIST_COMMON_VEHICLE_VALKYRIE",
                        "MPHEIST_AUTOGEN",
                        "MPHEIST_UNLOCKS_AUTOGEN",
                    } },
                { "stock_startup_changeset", "MPHEIST_AUTOGEN" },
                { "stock_startup_changeset_sha256", new string('4', 64) },
                { "stock_proxy", "dlcMPHeist:/common/data/interiorProxies.meta" },
                { "stock_map_group", "GROUP_MAP" },
                { "stock_map_group_changesets", StockMapGroup() },
                { "changeset_name", GrapeseedStockReferenceBridgePolicy.StockChangeset },
                { "changeset_sha256", new string('5', 64) },
                { "official_semantics", new Dictionary<string, object>
                    {
                        { "associated_maps", new object[] { "MO_JIM_L11" } },
                        { "files_to_invalidate", FilesToInvalidate() },
                        { "files_to_disable", Array.Empty<object>() },
                        { "files_to_enable", FilesToEnable() },
                        { "requires_loading_screen", true },
                        { "loading_screen_context", "LOADINGSCREEN_CONTEXT_LAST_FRAME" },
                        { "use_cache_loader", true },
                    } },
            };
        }

        private static object[] StockMapGroup() => new object[]
        {
            "MPHEIST_PRE_MAP_CHANGES", "MPHEIST_GTA5_LODLIGHTS",
            "MPHEIST_BUSINESS2_MAP_UPDATE", "MPHEIST_GTA5_CITYE_DOWNTOWN_01",
            "MPHEIST_GTA5_CITYE_HOLLYWOOD_01", "MPHEIST_GTA5_CITYE_INDUST_01",
            "MPHEIST_GTA5_CITYE_INDUST_02", "MPHEIST_GTA5_CITYE_PORT_01",
            "MPHEIST_GTA5_CITYE_SCENTRAL_01", "MPHEIST_GTA5_CITYE_SUNSET",
            "MPHEIST_GTA5_CITYW_AIRPORT_01", "MPHEIST_GTA5_CITYW_BEVERLY_01",
            "MPHEIST_GTA5_CITYW_KOREATOWN_01", "MPHEIST_GTA5_CITYW_SANTAMON_01",
            "MPHEIST_GTA5_CITYW_VENICE_01", "MPHEIST_GTA5_HILLS_CITYHILLS_01",
            "MPHEIST_GTA5_HILLS_CITYHILLS_02", "MPHEIST_GTA5_HILLS_CITYHILLS_03",
            "MPHEIST_GTA5_HILLS_COUNTRY_01", "MPHEIST_GTA5_HILLS_COUNTRY_02",
            "MPHEIST_GTA5_HILLS_COUNTRY_03", "MPHEIST_GTA5_HILLS_COUNTRY_04",
            "MPHEIST_GTA5_HILLS_COUNTRY_06", "MPHEIST_POST_MAP_CHANGES",
        };

        private static object[] FilesToInvalidate() => new object[]
        {
            "hw1_blimp_interior_v_garagel_milo_.interior",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_02.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_06.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_07.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_08.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_13.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_14.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_24.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hw1_rd.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hollywood.rpf",
            "platform:/levels/gta5/_citye/hollywood_01/hollywood_metadata.rpf",
        };

        private static object[] FilesToEnable() => new object[]
        {
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/dlc_apart_high_new.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/dlc_apart_high2_new.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/dlc_garage_high_new.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/heist_ornate_bank.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_02.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_blimp.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_06.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_07.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_08.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_13.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_14.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_24.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_rd.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hollywood.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hollywood_metadata.rpf",
        };

        private static string Marker(
            string preamble, IDictionary<string, string> fields)
        {
            var builder = new StringBuilder(preamble).Append('\n');
            foreach (KeyValuePair<string, string> field in fields)
                builder.Append(field.Key).Append('=').Append(field.Value)
                    .Append('\n');
            return builder.ToString();
        }

        private static SourceArchiveAttestationIdentity Identity(
            string fileName, char digestCharacter) =>
            new SourceArchiveAttestationIdentity(
                System.IO.Path.Combine(
                    System.IO.Path.GetTempPath(), fileName),
                1, 1, new string(digestCharacter, 64));

        private static string CreateIsolatedGameRoot()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-grapeseed-isolation-" + Guid.NewGuid().ToString("N"));
            string pack = Path.Combine(root, "mods", "update", "x64",
                "dlcpacks", GrapeseedStockReferenceBridgePolicy.PackName);
            Directory.CreateDirectory(pack);
            File.WriteAllBytes(Path.Combine(pack, "dlc.rpf"),
                new byte[] { 1 });
            File.WriteAllText(Path.Combine(pack,
                GrapeseedStockReferenceBridgePolicy.MarkerName), "marker");
            File.WriteAllText(Path.Combine(pack,
                GrapeseedStockReferenceBridgePolicy.ReceiptName), "{}");
            return root;
        }

        private sealed class MountedProofBridge : IDeferredMapContentBridge
        {
            internal bool Present;
            internal bool Throw;
            internal string LastPackName;

            public string Edition => "enhanced";
            public int MonotonicMilliseconds => 0;
            public bool IsRuntimeSafe(out string reason)
            {
                reason = string.Empty;
                return true;
            }
            public bool IsScreenFadedOut() => true;
            public bool IsDlcPresent(string packName)
            {
                LastPackName = packName;
                if (Throw) throw new InvalidOperationException("probe failed");
                return Present;
            }
            public uint GenerateHash(string value) => 0;
            public void ExecuteGroup(uint groupHash) { }
            public void RevertGroup(uint groupHash) { }
            public void RequestIpl(string ipl) { }
            public void RemoveIpl(string ipl) { }
            public bool IsIplActive(string ipl) => false;
            public void Yield(int milliseconds) { }
            public bool TryActivateFallback(string[] ipls, int timeoutMs) =>
                false;
        }

        private static bool WaitUntil(Func<bool> predicate)
        {
            DateTime deadline = DateTime.UtcNow.AddSeconds(5);
            while (DateTime.UtcNow < deadline)
            {
                if (predicate()) return true;
                Thread.Sleep(10);
            }
            return predicate();
        }

        private static void UpdateMaximum(ref int maximum, int candidate)
        {
            int observed;
            do
            {
                observed = maximum;
                if (candidate <= observed) return;
            }
            while (Interlocked.CompareExchange(
                ref maximum, candidate, observed) != observed);
        }
    }
}
