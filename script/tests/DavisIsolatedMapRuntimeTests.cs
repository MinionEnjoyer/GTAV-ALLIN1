using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class DavisIsolatedMapRuntimeTests
    {
        private const long ArchiveBytes = 4096;
        private static readonly string ArchiveHash = new string('a', 64);
        private const string DavisPlacementIpl =
            "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_";
        private const string DavisInteriorReference =
            "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/" +
            "dlc_int_01_tr.rpf";
        private const string DavisPlacementReference =
            "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/" +
            "int_placement_tr.rpf";
        private const string DavisProxyReference =
            "dlc_allin1_maps:/common/data/allin1/" +
            "mptuner_davis_interiorProxies.meta";

        [Fact]
        public void Exact_schema_three_startup_ipl_contract_is_quarantined()
        {
            Assert.False(StandaloneMapPack
                .IsVerifiedIsolatedDavisStartupIplReceipt(
                ValidMarker(), ValidReceipt(), ArchiveBytes,
                ArchiveHash, "enhanced"));
        }

        [Fact]
        public void Receipt_rejects_wrong_property_extra_group_or_reference()
        {
            AssertRejected(ValidReceipt(properties: "\"harmony\""));
            AssertRejected(ValidReceipt(groups:
                StartupGroup() + "," + StartupGroup()));
            AssertRejected(ValidReceipt(references:
                DavisReferences() + ",\"dlc_allin1_maps:/extra.rpf\""));
        }

        [Fact]
        public void Receipt_rejects_extra_assets_groups_and_wrong_startup_counts()
        {
            AssertRejected(ValidReceipt(assetCount: 4));
            AssertRejected(ValidReceipt(startupRpfEnableCount: 1));
            AssertRejected(ValidReceipt(startupFileEnableCount: 2));
            AssertRejected(ValidReceipt(
                declaredGroups: "\"GROUP_STARTUP\",\"ALLIN1_MAP_DAVIS\""));
            AssertRejected(ValidReceipt(
                customGroups: "\"ALLIN1_MAP_DAVIS\""));
            AssertRejected(ValidReceipt(groupMapBinding: true));
            AssertRejected(ValidReceipt(sources:
                DavisSources() + "," + DavisSource(
                    "extra.rpf", "extra.rpf")));
        }

        [Fact]
        public void Receipt_rejects_bad_archive_identity_layout_or_contract()
        {
            Assert.False(StandaloneMapPack.IsVerifiedIsolatedDavisReceipt(
                ValidMarker(), ValidReceipt(), ArchiveBytes,
                new string('b', 64), "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedIsolatedDavisReceipt(
                ValidMarker(), ValidReceipt(), ArchiveBytes - 1,
                ArchiveHash, "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedIsolatedDavisReceipt(
                ValidMarker(), ValidReceipt(), ArchiveBytes,
                ArchiveHash, "legacy"));
            Assert.False(StandaloneMapPack.IsVerifiedIsolatedDavisReceipt(
                ValidMarker().Replace(
                    "pruned-local-v3-startup-registered-ipl",
                    "pruned-local-v3-deferred"),
                ValidReceipt(), ArchiveBytes, ArchiveHash, "enhanced"));
            AssertRejected(ValidReceipt(layout:
                "pruned-local-v3-deferred"));
            Assert.False(StandaloneMapPack.IsVerifiedIsolatedDavisReceipt(
                ValidMarker().Replace("allin1-isolated-startup-ipl-v1",
                    "allin1-isolated-property-v1"),
                ValidReceipt(), ArchiveBytes, ArchiveHash, "enhanced"));
            AssertRejected(ValidReceipt(contract:
                "allin1-isolated-property-v1"));
            AssertRejected(ValidReceipt(hash: new string('b', 64)));
            AssertRejected(ValidReceipt(ipls: "\"Tuner_DLC_Int_01\""));
            AssertRejected(ValidReceipt(sources: DavisSources(
                firstHash: "not-a-sha256")));
        }

        [Fact]
        public void Crashed_schema_two_deferred_contract_is_rejected()
        {
            string oldMarker =
                "layout=pruned-local-v3-deferred\n" +
                "archive_registration=property-groups\n" +
                "activation=property-group-native-host-required\n" +
                "receipt=allin1_maps.runtime.json\n" +
                "runtime_contract=allin1-isolated-property-v1\n" +
                "asset_count=2\n" +
                "archive_bytes=" + ArchiveBytes + "\n" +
                "archive_sha256=" + ArchiveHash + "\n";
            string oldReceipt =
                "{\"schema\":2,\"status\":\"verified\"," +
                "\"package_id\":\"allin1.online-content\"," +
                "\"pack_name\":\"allin1_maps\"," +
                "\"edition\":\"enhanced\"," +
                "\"layout\":\"pruned-local-v3-deferred\"," +
                "\"runtime_contract\":\"allin1-isolated-property-v1\"," +
                "\"archive_bytes\":" + ArchiveBytes + "," +
                "\"archive_sha256\":\"" + ArchiveHash + "\"," +
                "\"asset_count\":2,\"startup_rpf_enable_count\":0," +
                "\"properties\":[\"davis\"]}";

            Assert.False(StandaloneMapPack
                .IsVerifiedIsolatedDavisStartupIplReceipt(
                    oldMarker, oldReceipt, ArchiveBytes,
                    ArchiveHash, "enhanced"));
        }

        [Fact]
        public void Official_isolated_streaming_allowlist_contains_only_davis()
        {
            string directory = Path.Combine(RepositoryRoot(), "data", "maps",
                "allin1-online-content");
            MapProjectDefinition[] projects = Directory
                .EnumerateFiles(directory, "*.maps.json")
                .Select(ParseProject)
                .ToArray();

            Assert.Equal(6, projects.Length);
            foreach (MapProjectDefinition project in projects)
            {
                bool mapped = OfficialGarageMapProjects
                    .TryGetIsolatedStreamingProperty(project,
                        out DeferredMapProperty property);
                if (string.Equals(project.Id, "davis-auto-shop",
                        StringComparison.OrdinalIgnoreCase))
                {
                    Assert.True(mapped);
                    Assert.Equal(DeferredMapProperty.Davis, property);
                }
                else
                {
                    Assert.False(mapped);
                }
            }

            MapProjectDefinition davis = projects.Single(project =>
                project.Id == "davis-auto-shop");
            davis.PackageId = "third.party";
            Assert.False(OfficialGarageMapProjects
                .TryGetIsolatedStreamingProperty(davis, out _));
        }

        [Fact]
        public void Davis_descriptor_resolves_phase_b_resident_contract()
        {
            MapProjectDefinition project = ParseProject(Path.Combine(
                RepositoryRoot(), "data", "maps", "allin1-online-content",
                "davis.maps.json"));

            Assert.Equal("mptuner", project.Streaming.PackName);
            Assert.Null(project.Streaming.ContentGroup);
            Assert.Equal(220f, project.Streaming.ActivationRadius);
            Assert.Equal(420f, project.Streaming.ReleaseRadius);
            Assert.True(project.Streaming.KeepResident);
            Assert.Equal(new[] { DavisPlacementIpl }, project.RequiredIpls);
        }

        [Theory]
        [InlineData(0, 0, 250)]
        [InlineData(1, 0, 250)]
        [InlineData(6, 0, 250)]
        [InlineData(1, 1, 0)]
        [InlineData(6, 1, 0)]
        public void Streaming_only_states_sleep_but_any_portal_is_interactive(
            int stateCount, int interactivePortalCount, int expectedInterval)
        {
            Assert.Equal(expectedInterval,
                MapPackageRuntime.TickIntervalForStateCounts(
                    stateCount, interactivePortalCount));
        }

        [Fact]
        public void Zone_policy_acquires_at_activation_boundary()
        {
            Assert.Equal(MapStreamingZoneAction.Acquire,
                MapStreamingZonePolicy.Decide(
                    true, false, true, false, 220f, 220f, 420f));
        }

        [Fact]
        public void Zone_policy_holds_through_hysteresis_band()
        {
            Assert.Equal(MapStreamingZoneAction.None,
                MapStreamingZonePolicy.Decide(
                    true, false, true, false, 221f, 220f, 420f));
            Assert.Equal(MapStreamingZoneAction.None,
                MapStreamingZonePolicy.Decide(
                    true, true, true, false, 419f, 220f, 420f));
        }

        [Fact]
        public void Zone_policy_releases_at_release_boundary()
        {
            Assert.Equal(MapStreamingZoneAction.Release,
                MapStreamingZonePolicy.Decide(
                    true, true, true, false, 420f, 220f, 420f));
        }

        [Fact]
        public void Zone_policy_retains_lease_during_unsafe_or_occupied_state()
        {
            Assert.Equal(MapStreamingZoneAction.None,
                MapStreamingZonePolicy.Decide(
                    false, true, true, false, 500f, 220f, 420f));
            Assert.Equal(MapStreamingZoneAction.None,
                MapStreamingZonePolicy.Decide(
                    true, true, false, false, 500f, 220f, 420f));
        }

        [Fact]
        public void Zone_policy_respects_keep_resident_and_nonfinite_distance()
        {
            Assert.Equal(MapStreamingZoneAction.None,
                MapStreamingZonePolicy.Decide(
                    true, true, true, true, 500f, 220f, 420f));
            Assert.Equal(MapStreamingZoneAction.None,
                MapStreamingZonePolicy.Decide(
                    true, false, true, false, float.NaN, 220f, 420f));
            Assert.Equal(MapStreamingZoneAction.None,
                MapStreamingZonePolicy.Decide(
                    true, true, true, false,
                    float.PositiveInfinity, 220f, 420f));
        }

        [Fact]
        public void Retired_startup_ipl_route_cannot_request_or_lease_davis()
        {
            var bridge = new LeaseBridge();
            var manager = new DeferredMapContentLeaseManager(
                bridge, new NullLeaseLogger());
            var descriptor = new DeferredMapContentDescriptor(
                DeferredMapProperty.Davis, new[] { DavisPlacementIpl });
            OfficialMapActivationRoute route =
                OfficialMapActivationPolicy.Resolve(
                    isolatedStartupIplVerified: true,
                    referenceBridgeVerified: false);

            Assert.Equal(OfficialMapActivationRoute.Unavailable, route);
            Assert.Equal(DeferredMapContentOutcome.MapPackUnavailable,
                OfficialMapActivationPolicy.Acquire(
                    manager, descriptor, route, 500).Outcome);
            Assert.Equal(DeferredMapContentOutcome.MapPackUnavailable,
                OfficialMapActivationPolicy.Acquire(
                    manager, descriptor,
                    OfficialMapActivationRoute.IsolatedStartupIpl,
                    500).Outcome);
            Assert.Equal(0, manager.ReferenceCount(descriptor.GroupName));
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
            Assert.DoesNotContain(DavisPlacementIpl, bridge.ActiveIpls);
        }

        [Fact]
        public void Reference_bridge_route_keeps_group_native_behavior()
        {
            OfficialMapActivationRoute route =
                OfficialMapActivationPolicy.Resolve(
                    isolatedStartupIplVerified: false,
                    referenceBridgeVerified: true);

            Assert.True(OfficialMapActivationPolicy
                .ExecutesDeferredGroup(route));
            Assert.True(OfficialMapActivationPolicy
                .AllowsMutation(route, referenceClosureSafe: true));
            Assert.False(OfficialMapActivationPolicy
                .AllowsMutation(route, referenceClosureSafe: false));
        }

        [Fact]
        public void Startup_ipl_recognizer_does_not_authorize_a_route()
        {
            Assert.True(StandaloneMapPack.IsExactIsolatedStartupIplRequest(
                DeferredMapProperty.Davis,
                new[] { DavisPlacementIpl }));
            Assert.False(StandaloneMapPack.IsExactIsolatedStartupIplRequest(
                DeferredMapProperty.Davis,
                new[] { DavisPlacementIpl, "extra_ipl" }));
            Assert.False(StandaloneMapPack.IsExactIsolatedStartupIplRequest(
                DeferredMapProperty.Harmony,
                new[] { DavisPlacementIpl }));
            Assert.Equal(OfficialMapActivationRoute.Unavailable,
                OfficialMapActivationPolicy.Resolve(
                    isolatedStartupIplVerified: true,
                    referenceBridgeVerified: false));
            Assert.False(OfficialMapActivationPolicy.AllowsMutation(
                OfficialMapActivationRoute.IsolatedStartupIpl,
                referenceClosureSafe: true));
        }

        private static void AssertRejected(string receipt)
        {
            Assert.False(StandaloneMapPack.IsVerifiedIsolatedDavisReceipt(
                ValidMarker(), receipt, ArchiveBytes,
                ArchiveHash, "enhanced"));
        }

        private static string ValidMarker() =>
            "layout=pruned-local-v3-startup-registered-ipl\n" +
            "archive_registration=startup\n" +
            "group_map_binding=false\n" +
            "activation=startup-file-registration-plus-request-ipl\n" +
            "receipt=allin1_maps.runtime.json\n" +
            "runtime_contract=allin1-isolated-startup-ipl-v1\n" +
            "property_scope=davis\n" +
            "asset_count=3\n" +
            "startup_rpf_enable_count=2\n" +
            "startup_file_enable_count=3\n" +
            "reference_count=3\n" +
            "custom_property_groups=0\n" +
            "archive_bytes=" + ArchiveBytes + "\n" +
            "archive_sha256=" + ArchiveHash + "\n";

        private static string ValidReceipt(
            string properties = "\"davis\"", string groups = null,
            string references = null,
            int startupRpfEnableCount = 2,
            int startupFileEnableCount = 3, int assetCount = 3,
            string declaredGroups = "\"GROUP_STARTUP\"",
            string customGroups = "", bool groupMapBinding = false,
            string ipls = null,
            string layout = "pruned-local-v3-startup-registered-ipl",
            string contract = "allin1-isolated-startup-ipl-v1",
            string hash = null, string sources = null)
        {
            hash = hash ?? ArchiveHash;
            groups = groups ?? StartupGroup(references);
            ipls = ipls ?? "\"" + DavisPlacementIpl + "\"";
            sources = sources ?? DavisSources();
            return "{\"schema\":3,\"status\":\"verified\"," +
                "\"canary_id\":\"davis-enhanced-isolated-startup-ipl-v3\"," +
                "\"package_id\":\"allin1.online-content\"," +
                "\"pack_name\":\"allin1_maps\"," +
                "\"layout\":\"" + layout + "\"," +
                "\"edition\":\"enhanced\"," +
                "\"runtime_contract\":\"" + contract + "\"," +
                "\"archive_registration\":\"startup\"," +
                "\"activation\":\"startup-file-registration-plus-request-ipl\"," +
                "\"property_scope\":\"davis\"," +
                "\"asset_count\":" + assetCount + "," +
                "\"startup_rpf_enable_count\":" +
                    startupRpfEnableCount + "," +
                "\"startup_file_enable_count\":" +
                    startupFileEnableCount + "," +
                "\"archive_bytes\":" + ArchiveBytes + "," +
                "\"archive_sha256\":\"" + hash + "\"," +
                "\"properties\":[" + properties + "]," +
                "\"ipls\":[" + ipls + "]," +
                "\"declared_changesets\":[\"ALLIN1_MAPS_AUTOGEN\"]," +
                "\"declared_groups\":[" + declaredGroups + "]," +
                "\"custom_property_groups\":[" + customGroups + "]," +
                "\"group_map_binding\":" +
                    (groupMapBinding ? "true" : "false") + "," +
                "\"groups\":[" + groups + "]," +
                "\"source_archives\":[" + DavisSourceArchive() + "]," +
                "\"sources\":[" + sources + "]," +
                "\"proxy_filters\":[" + DavisProxyFilter() + "]}";
        }

        private static string StartupGroup(string references = null)
        {
            references = references ?? DavisReferences();
            return "{\"group\":\"GROUP_STARTUP\"," +
                "\"changesets\":[\"ALLIN1_MAPS_AUTOGEN\"]," +
                "\"references\":[" + references + "]}";
        }

        private static string DavisReferences() =>
            "\"" + DavisInteriorReference + "\",\"" +
            DavisPlacementReference + "\",\"" +
            DavisProxyReference + "\"";

        private static string DavisSourceArchive() =>
            "{\"pack\":\"mptuner\",\"archive\":\"dlc.rpf\"," +
            "\"source\":\"stock\"," +
            "\"path\":\"update/x64/dlcpacks/mptuner/dlc.rpf\"," +
            "\"size\":8192,\"mtime_ns\":123456789," +
            "\"sha256\":\"" + new string('b', 64) + "\"}";

        private static string DavisSources(string firstHash = null) =>
            DavisSource(
                "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
                "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
                firstHash) + "," +
            DavisSource(
                "x64/levels/gta5/interiors/int_placement_tr.rpf",
                "x64/levels/gta5/interiors/int_placement_tr.rpf") + "," +
            DavisSource(
                "common/data/interiorProxies.meta",
                "common/data/allin1/mptuner_davis_interiorProxies.meta");

        private static string DavisSource(
            string sourcePath, string destinationPath, string hash = null)
        {
            string proxy = sourcePath == "common/data/interiorProxies.meta"
                ? ",\"proxy_names\":[\"" + DavisPlacementIpl + "\"]," +
                  "\"proxy_start_from\":1117"
                : string.Empty;
            return "{\"source_pack\":\"mptuner\"," +
                "\"source_archive\":\"dlc.rpf\"," +
                "\"source_path\":\"" + sourcePath + "\"," +
                "\"destination_path\":\"" + destinationPath + "\"," +
                "\"source_asset_bytes\":1024," +
                "\"source_asset_sha256\":\"" +
                    (hash ?? new string('c', 64)) + "\"" + proxy + "}";
        }

        private static string DavisProxyFilter() =>
            "{\"destination_path\":" +
            "\"common/data/allin1/mptuner_davis_interiorProxies.meta\"," +
            "\"proxy_names\":[\"" + DavisPlacementIpl + "\"]," +
            "\"start_from\":1117,\"entry_count\":1}";

        private static MapProjectDefinition ParseProject(string path)
        {
            Assert.True(MapProjectParser.TryParse(
                File.ReadAllText(path), out MapProjectDefinition project,
                out IReadOnlyList<string> errors),
                string.Join(Environment.NewLine, errors));
            return project;
        }

        private static string RepositoryRoot()
        {
            string current = AppContext.BaseDirectory;
            while (!string.IsNullOrEmpty(current))
            {
                if (File.Exists(Path.Combine(current, "allin1.workspace.json")))
                    return current;
                current = Directory.GetParent(current)?.FullName;
            }
            throw new DirectoryNotFoundException(
                "Could not locate the ALLIN1 repository root.");
        }

        private sealed class LeaseBridge : IDeferredMapContentBridge
        {
            internal readonly HashSet<string> ActiveIpls =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            internal int ExecuteCount;
            internal int RevertCount;

            public string Edition => "enhanced";
            public int MonotonicMilliseconds { get; private set; }
            public bool IsScreenFadedOut() => true;
            public bool IsDlcPresent(string packName) => true;
            public bool IsRuntimeSafe(out string reason)
            {
                reason = string.Empty;
                return true;
            }
            public uint GenerateHash(string value) => 0xDA715u;
            public void ExecuteGroup(uint groupHash)
            {
                ExecuteCount++;
            }
            public void RevertGroup(uint groupHash)
            {
                RevertCount++;
            }
            public void RequestIpl(string ipl) => ActiveIpls.Add(ipl);
            public void RemoveIpl(string ipl) => ActiveIpls.Remove(ipl);
            public bool IsIplActive(string ipl) => ActiveIpls.Contains(ipl);
            public void Yield(int milliseconds) =>
                MonotonicMilliseconds += Math.Max(1, milliseconds);
            public bool TryActivateFallback(string[] ipls, int timeoutMs) =>
                false;
        }

        private sealed class NullLeaseLogger : IDeferredMapContentLogger
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
