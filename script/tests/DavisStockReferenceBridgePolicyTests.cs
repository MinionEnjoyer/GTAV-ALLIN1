using System;
using System.Collections.Generic;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class DavisStockReferenceBridgePolicyTests
    {
        private const string Marker =
            "canary_id=davis-enhanced-stock-reference-boot-v4\n" +
            "layout=stock-reference-v1-metadata-only\n" +
            "runtime_contract=allin1-stock-mptuner-davis-boot-v1\n" +
            "phase=phase-a-boot-only\n" +
            "status=installed_boot_only_pending\n" +
            "archive_registration=metadata-only\n" +
            "activation=disabled-phase-a-boot-only\n" +
            "receipt=allin1_mptuner_bridge.runtime.json\n" +
            "asset_count=0\n" +
            "data_file_count=0\n" +
            "startup_changeset=ALLIN1_MPTUNER_BRIDGE_AUTOGEN\n" +
            "dormant_group_count=1\n" +
            "declared_groups=GROUP_STARTUP," +
                "ALLIN1_STOCK_MPTUNER_DAVIS_V1\n" +
            "stock_changesets=MPTUNER_MAP_UPDATE\n" +
            "native_group_execution_enabled=false\n" +
            "runtime_ipl_requests_enabled=false\n" +
            "gameconfig_changed=false\n" +
            "native_host_installed=false\n";

        private const string Receipt =
            "{\"schema\":4," +
            "\"canary_id\":\"davis-enhanced-stock-reference-boot-v4\"," +
            "\"package_id\":\"allin1.online-content\"," +
            "\"pack_name\":\"allin1_mptuner_bridge\"," +
            "\"device_name\":\"dlc_allin1_mptuner_bridge\"," +
            "\"edition\":\"enhanced\"," +
            "\"layout\":\"stock-reference-v1-metadata-only\"," +
            "\"runtime_contract\":" +
                "\"allin1-stock-mptuner-davis-boot-v1\"," +
            "\"phase\":\"phase-a-boot-only\"," +
            "\"status\":\"verified\"," +
            "\"archive_registration\":\"metadata-only\"," +
            "\"activation\":\"disabled-phase-a-boot-only\"," +
            "\"asset_count\":0,\"data_file_count\":0," +
            "\"startup_changeset\":\"ALLIN1_MPTUNER_BRIDGE_AUTOGEN\"," +
            "\"dormant_group_count\":1," +
            "\"declared_groups\":[\"GROUP_STARTUP\"," +
                "\"ALLIN1_STOCK_MPTUNER_DAVIS_V1\"]," +
            "\"stock_changesets\":[\"MPTUNER_MAP_UPDATE\"]," +
            "\"native_group_execution_enabled\":false," +
            "\"runtime_ipl_requests_enabled\":false," +
            "\"gameconfig_changed\":false," +
            "\"native_host_installed\":false," +
            "\"groups\":[{\"property\":\"davis\"," +
                "\"group\":\"ALLIN1_STOCK_MPTUNER_DAVIS_V1\"," +
                "\"changesets\":[\"MPTUNER_MAP_UPDATE\"]," +
                "\"activation_enabled\":false}]}";

        [Fact]
        public void Exact_phase_a_contract_is_recognized_as_boot_only()
        {
            Assert.True(DavisStockReferenceBridgePolicy
                .IsExactPhaseABootOnlyContract(Marker, Receipt));
            Assert.Equal(DavisStockReferenceBridgeMode.PhaseABootOnly,
                DavisStockReferenceBridgePolicy.Resolve(
                    exactPhaseABootOnlyContract: true,
                    futurePhaseBReceiptVerified: false));
        }

        [Theory]
        [InlineData("native_group_execution_enabled=false",
            "native_group_execution_enabled=true")]
        [InlineData("runtime_ipl_requests_enabled=false",
            "runtime_ipl_requests_enabled=true")]
        [InlineData("activation=disabled-phase-a-boot-only",
            "activation=property-group-runtime")]
        public void Marker_cannot_enable_any_phase_a_runtime_mutation(
            string current, string replacement)
        {
            Assert.False(DavisStockReferenceBridgePolicy
                .IsExactPhaseABootOnlyContract(
                    Marker.Replace(current, replacement), Receipt));
        }

        [Theory]
        [InlineData("\"activation_enabled\":false",
            "\"activation_enabled\":true")]
        [InlineData("\"native_group_execution_enabled\":false",
            "\"native_group_execution_enabled\":true")]
        [InlineData("\"runtime_ipl_requests_enabled\":false",
            "\"runtime_ipl_requests_enabled\":true")]
        public void Receipt_cannot_enable_any_phase_a_runtime_mutation(
            string current, string replacement)
        {
            Assert.False(DavisStockReferenceBridgePolicy
                .IsExactPhaseABootOnlyContract(
                    Marker, Receipt.Replace(current, replacement)));
        }

        [Fact]
        public void Phase_a_wins_over_a_conflicting_phase_b_claim()
        {
            DavisStockReferenceBridgeMode mode =
                DavisStockReferenceBridgePolicy.Resolve(
                    exactPhaseABootOnlyContract: true,
                    futurePhaseBReceiptVerified: true);

            Assert.Equal(DavisStockReferenceBridgeMode.PhaseABootOnly, mode);
            Assert.False(DavisStockReferenceBridgePolicy
                .AllowsRuntimeMutation(mode));
        }

        [Fact]
        public void Only_a_future_verified_phase_b_mode_can_mutate()
        {
            Assert.False(DavisStockReferenceBridgePolicy
                .AllowsRuntimeMutation(
                    DavisStockReferenceBridgeMode.Unavailable));
            Assert.False(DavisStockReferenceBridgePolicy
                .AllowsRuntimeMutation(
                    DavisStockReferenceBridgeMode.PhaseABootOnly));
            Assert.True(DavisStockReferenceBridgePolicy
                .AllowsRuntimeMutation(
                    DavisStockReferenceBridgeMode.PhaseBBlackTransition));
            Assert.False(DavisStockReferenceBridgePolicy
                .IsRuntimeActivationAuthorized(
                    DeferredMapProperty.Davis));
            Assert.True(DavisStockReferenceBridgePolicy
                .IsRuntimeActivationAuthorized(
                    DeferredMapProperty.Harmony));
        }

        [Fact]
        public void Phase_a_blocks_davis_before_black_transition_or_lease()
        {
            Assert.False(DeferredMapContentRuntime
                .CanBeginOfficialGarageEntry(
                    DeferredMapProperty.Davis, out int retryAfter));
            Assert.Equal(0, retryAfter);

            DeferredMapContentResult acquired =
                DeferredMapContentRuntime.TryAcquireProximity(
                    DeferredMapProperty.Davis,
                    new[]
                    {
                        "tr_int_placement_tr_interior_0_" +
                        "tuner_mod_garage_milo_",
                    }, 500);
            Assert.Equal(DeferredMapContentOutcome.MapPackUnavailable,
                acquired.Outcome);

            DeferredMapContentResult released =
                DeferredMapContentRuntime.Release(
                    DeferredMapProperty.Davis,
                    new[]
                    {
                        "tr_int_placement_tr_interior_0_" +
                        "tuner_mod_garage_milo_",
                    });
            Assert.Equal(DeferredMapContentOutcome.NotAcquired,
                released.Outcome);
        }

        [Fact]
        public void Phase_a_route_returns_before_any_map_native()
        {
            var bridge = new CountingBridge();
            var manager = new DeferredMapContentLeaseManager(
                bridge, new NullLogger());
            var descriptor = new DeferredMapContentDescriptor(
                DeferredMapProperty.Davis,
                new[]
                {
                    "tr_int_placement_tr_interior_0_" +
                    "tuner_mod_garage_milo_",
                });

            OfficialMapActivationRoute route =
                OfficialMapActivationPolicy.Resolve(
                    isolatedStartupIplVerified: false,
                    referenceBridgeVerified: false);
            DeferredMapContentResult result =
                OfficialMapActivationPolicy.Acquire(
                    manager, descriptor, route, 500);

            Assert.Equal(DeferredMapContentOutcome.MapPackUnavailable,
                result.Outcome);
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Equal(0, bridge.RequestCount);
            Assert.Equal(0, bridge.RemoveCount);
        }

        private sealed class CountingBridge : IDeferredMapContentBridge
        {
            internal int ExecuteCount;
            internal int RevertCount;
            internal int RequestCount;
            internal int RemoveCount;

            public string Edition => "enhanced";
            public int MonotonicMilliseconds => 0;
            public bool IsScreenFadedOut() => true;
            public bool IsDlcPresent(string packName) => true;
            public bool IsRuntimeSafe(out string reason)
            {
                reason = string.Empty;
                return true;
            }
            public uint GenerateHash(string value) => 1;
            public void ExecuteGroup(uint groupHash) => ExecuteCount++;
            public void RevertGroup(uint groupHash) => RevertCount++;
            public void RequestIpl(string ipl) => RequestCount++;
            public void RemoveIpl(string ipl) => RemoveCount++;
            public bool IsIplActive(string ipl) => false;
            public void Yield(int milliseconds) { }
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
