using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Web.Script.Serialization;

namespace ALLIN1
{
    /// <summary>
    /// Closed runtime authority for Grapeseed's metadata-only mpheist bridge.
    ///
    /// Phase A proves only that GTA can register the dormant bridge at boot.
    /// Phase B authorizes one exact Rockstar changeset and one exact IPL, and
    /// only from the owned Grapeseed garage-entry transition while black is
    /// already held. Neither generic map descriptors nor proximity streaming
    /// can inherit this authority.
    /// </summary>
    internal static class GrapeseedStockReferenceBridgePolicy
    {
        internal const string PackName =
            "allin1_mpheist_grapeseed_bridge";
        internal const string MarkerName =
            "allin1_mpheist_grapeseed_bridge.active";
        internal const string ReceiptName =
            "allin1_mpheist_grapeseed_bridge.runtime.json";
        internal const string PackageId = "allin1.online-content";
        internal const string DeviceName =
            "dlc_allin1_mpheist_grapeseed_bridge";
        internal const string Layout = "stock-reference-v1-metadata-only";
        internal const string StartupChangeset =
            "ALLIN1_MPHEIST_GRAPESEED_BRIDGE_AUTOGEN";
        internal const string DormantGroup =
            "ALLIN1_STOCK_MPHEIST_GRAPESEED_V1";
        internal const string StockChangeset =
            "MPHEIST_GTA5_CITYE_HOLLYWOOD_01";
        internal const string GrapeseedIpl =
            "hei_hw1_blimp_interior_v_garagem_milo_";

        internal const string PhaseACanaryId =
            "grapeseed-enhanced-stock-reference-boot-v1";
        internal const string PhaseARuntimeContract =
            "allin1-stock-mpheist-grapeseed-boot-v1";
        internal const string PhaseAName = "phase-a-boot-only";
        internal const string PhaseAMarkerStatus =
            "installed_boot_only_pending";
        internal const string PhaseAReceiptStatus = "verified";
        internal const string PhaseAActivation =
            "disabled-phase-a-boot-only";
        internal const string PhaseAMarkerPreamble =
            "ALLIN1 stock mpheist Grapeseed Phase-A metadata bridge; " +
            "activation disabled.";

        internal const string PhaseBCanaryId =
            "grapeseed-enhanced-stock-reference-black-transition-v1";
        internal const string PhaseBRuntimeContract =
            "allin1-stock-mpheist-grapeseed-black-transition-v1";
        internal const string PhaseBName = "phase-b-black-transition";
        internal const string PhaseBMarkerStatus =
            "installed_black_transition_pending_test";
        internal const string PhaseBReceiptStatus = "verified";
        internal const string PhaseBActivation =
            "explicit-grapeseed-entry-black-transition";
        internal const string PhaseBActivationScope = "garage-entry-only";
        internal const string PhaseBMarkerPreamble =
            "ALLIN1 stock mpheist Grapeseed Phase-B black-transition " +
            "bridge; Grapeseed garage-entry activation only.";

        private const int VerificationCacheMilliseconds = 5000;
        private const int MaximumMarkerBytes = 32 * 1024;
        private const int MaximumReceiptBytes = 256 * 1024;
        private const int MaximumBridgeArchiveBytes = 4 * 1024 * 1024;
        private static readonly TimedBooleanVerificationCache
            PhaseAVerificationCache = new TimedBooleanVerificationCache();
        private static readonly TimedBooleanVerificationCache
            PhaseBVerificationCache = new TimedBooleanVerificationCache();
        private static readonly AsyncSourceArchiveAttestationCache
            NativeMutationAttestation =
                new AsyncSourceArchiveAttestationCache();
        private static int _startupPhaseAEvidenceEmitted;

        private static readonly string[] ExpectedStockStartupGroup =
        {
            "MPHEIST_COMMON_VEHICLE_INSURGENT",
            "MPHEIST_COMMON_VEHICLE_VALKYRIE",
            "MPHEIST_AUTOGEN",
            "MPHEIST_UNLOCKS_AUTOGEN",
        };

        private static readonly string[] ExpectedStockMapGroup =
        {
            "MPHEIST_PRE_MAP_CHANGES",
            "MPHEIST_GTA5_LODLIGHTS",
            "MPHEIST_BUSINESS2_MAP_UPDATE",
            "MPHEIST_GTA5_CITYE_DOWNTOWN_01",
            "MPHEIST_GTA5_CITYE_HOLLYWOOD_01",
            "MPHEIST_GTA5_CITYE_INDUST_01",
            "MPHEIST_GTA5_CITYE_INDUST_02",
            "MPHEIST_GTA5_CITYE_PORT_01",
            "MPHEIST_GTA5_CITYE_SCENTRAL_01",
            "MPHEIST_GTA5_CITYE_SUNSET",
            "MPHEIST_GTA5_CITYW_AIRPORT_01",
            "MPHEIST_GTA5_CITYW_BEVERLY_01",
            "MPHEIST_GTA5_CITYW_KOREATOWN_01",
            "MPHEIST_GTA5_CITYW_SANTAMON_01",
            "MPHEIST_GTA5_CITYW_VENICE_01",
            "MPHEIST_GTA5_HILLS_CITYHILLS_01",
            "MPHEIST_GTA5_HILLS_CITYHILLS_02",
            "MPHEIST_GTA5_HILLS_CITYHILLS_03",
            "MPHEIST_GTA5_HILLS_COUNTRY_01",
            "MPHEIST_GTA5_HILLS_COUNTRY_02",
            "MPHEIST_GTA5_HILLS_COUNTRY_03",
            "MPHEIST_GTA5_HILLS_COUNTRY_04",
            "MPHEIST_GTA5_HILLS_COUNTRY_06",
            "MPHEIST_POST_MAP_CHANGES",
        };

        private static readonly string[] ExpectedFilesToInvalidate =
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

        private static readonly string[] ExpectedFilesToEnable =
        {
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/" +
                "dlc_apart_high_new.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/" +
                "dlc_apart_high2_new.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/" +
                "dlc_garage_high_new.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/interiors/" +
                "heist_ornate_bank.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_02.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_blimp.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_06.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_07.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_08.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_13.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_14.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_24.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hw1_rd.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hollywood.rpf",
            "dlcMPHeist:/%PLATFORM%/levels/gta5/_citye/hollywood_01/" +
                "hollywood_metadata.rpf",
        };

        internal static bool IsCurrentPhaseABootOnlyContract =>
            PhaseAVerificationCache.GetOrVerify(
                Environment.TickCount, VerificationCacheMilliseconds,
                VerifyInstalledPhaseAContract);

        internal static bool IsCurrentRuntimeActivationAuthorized =>
            PhaseBVerificationCache.GetOrVerify(
                Environment.TickCount, VerificationCacheMilliseconds,
                VerifyInstalledPhaseBContract);

        internal static bool IsCurrentNativeMutationAuthorized
        {
            get
            {
                if (!TryResolveInstalledPhaseBContract(
                        out SourceArchiveAttestationIdentity identity))
                    return false;
                NativeMutationAttestation.Begin(
                    identity, VerifySourceArchiveAttestation);
                return NativeMutationAttestation.IsCompletedVerified(identity);
            }
        }

        internal static bool IsCurrentNativeMutationAttestationPending
        {
            get
            {
                if (!TryResolveInstalledPhaseBContract(
                        out SourceArchiveAttestationIdentity identity))
                    return false;
                NativeMutationAttestation.Begin(
                    identity, VerifySourceArchiveAttestation);
                return !NativeMutationAttestation.IsCompleted(identity);
            }
        }

        /// <summary>
        /// Story startup observes exactly one state. A strict Phase-A install
        /// emits deterministic zero-native evidence for guarded promotion; a
        /// strict Phase-B install begins the expensive stock hash in the
        /// background. Missing or mixed state does neither.
        /// </summary>
        internal static void ObserveStartupAuthorizationState()
        {
            if (IsCurrentPhaseABootOnlyContract)
            {
                if (Interlocked.Exchange(
                        ref _startupPhaseAEvidenceEmitted, 1) == 0)
                    ReportPhaseARuntimeActivationBlocked("startup_guard");
                return;
            }
            if (IsCurrentRuntimeActivationAuthorized)
                WarmUpCurrentNativeMutationAuthorization();
        }

        internal static void ReportPhaseARuntimeActivationBlocked(
            string requestSource)
        {
            ClientLog.Warn("DeferredMap",
                "grapeseed_phase_a_runtime_activation_blocked",
                new Dictionary<string, object>
                {
                    { "property", "grapeseed" },
                    { "request_source", requestSource ?? "unknown" },
                    { "required_phase", "phase-b-black-transition" },
                    { "native_group_executed", false },
                    { "ipl_requested", false },
                });
        }

        internal static void WarmUpCurrentNativeMutationAuthorization()
        {
            if (!TryResolveInstalledPhaseBContract(
                    out SourceArchiveAttestationIdentity identity))
                return;
            bool started = NativeMutationAttestation.Begin(
                identity, VerifySourceArchiveAttestation);
            if (started)
            {
                ClientLog.Info("DeferredMap",
                    "grapeseed_native_attestation_warmup_started",
                    new Dictionary<string, object>
                    {
                        { "archive_bytes", identity.Size },
                        { "archive_mtime_ns", identity.MtimeNanoseconds },
                    });
            }
        }

        internal static bool IsRuntimeActivationAuthorized(
            DeferredMapProperty property) =>
            property != DeferredMapProperty.Grapeseed ||
            IsCurrentRuntimeActivationAuthorized;

        internal static bool IsExactPhaseABootOnlyContract(
            string marker, string receiptJson, long archiveBytes,
            string archiveSha256)
        {
            if (!TryParseStrictMarker(marker, PhaseAMarkerPreamble,
                    out Dictionary<string, string> markerFields) ||
                archiveBytes <= 0 || !IsSha256(archiveSha256))
                return false;
            string[] exactMarkerKeys =
            {
                "canary_id", "schema", "status", "phase", "layout",
                "runtime_contract", "archive_registration", "activation",
                "property_scope", "asset_count", "data_file_count",
                "startup_changeset",
                "dormant_group_count", "declared_groups",
                "stock_changesets", "ipls",
                "native_group_execution_enabled",
                "runtime_ipl_requests_enabled", "gameconfig_changed",
                "native_host_installed", "receipt", "archive_bytes",
                "archive_sha256",
            };
            if (!HasExactKeys(markerFields, exactMarkerKeys) ||
                !MarkerEquals(markerFields, "canary_id", PhaseACanaryId) ||
                !MarkerEquals(markerFields, "schema", "4") ||
                !MarkerEquals(markerFields, "status", PhaseAMarkerStatus) ||
                !MarkerEquals(markerFields, "phase", PhaseAName) ||
                !MarkerEquals(markerFields, "layout", Layout) ||
                !MarkerEquals(markerFields, "runtime_contract",
                    PhaseARuntimeContract) ||
                !MarkerEquals(markerFields, "archive_registration",
                    "metadata-only") ||
                !MarkerEquals(markerFields, "activation", PhaseAActivation) ||
                !MarkerEquals(markerFields, "property_scope", "grapeseed") ||
                !MarkerEquals(markerFields, "asset_count", "0") ||
                !MarkerEquals(markerFields, "data_file_count", "0") ||
                !MarkerEquals(markerFields, "startup_changeset",
                    StartupChangeset) ||
                !MarkerEquals(markerFields, "dormant_group_count", "1") ||
                !MarkerEquals(markerFields, "declared_groups",
                    "GROUP_STARTUP," + DormantGroup) ||
                !MarkerEquals(markerFields, "stock_changesets",
                    StockChangeset) ||
                !MarkerEquals(markerFields, "ipls", GrapeseedIpl) ||
                !MarkerEquals(markerFields,
                    "native_group_execution_enabled", "false") ||
                !MarkerEquals(markerFields,
                    "runtime_ipl_requests_enabled", "false") ||
                !MarkerEquals(markerFields, "gameconfig_changed", "false") ||
                !MarkerEquals(markerFields, "native_host_installed", "false") ||
                !MarkerEquals(markerFields, "receipt", ReceiptName) ||
                !long.TryParse(markerFields["archive_bytes"],
                    out long markerBytes) || markerBytes != archiveBytes ||
                !FixedTimeEquals(markerFields["archive_sha256"],
                    archiveSha256))
                return false;

            try
            {
                Dictionary<string, object> receipt = Deserialize(receiptJson);
                string[] exactReceiptKeys =
                {
                    "schema", "canary_id", "status", "phase", "package_id",
                    "pack_name", "device_name", "edition", "layout",
                    "runtime_contract", "archive_registration", "activation",
                    "property_scope", "asset_count", "data_file_count",
                    "startup_changeset",
                    "dormant_group_count", "declared_groups",
                    "stock_changesets", "ipls", "groups",
                    "native_group_execution_enabled",
                    "runtime_ipl_requests_enabled", "gameconfig_changed",
                    "native_host_installed", "archive_bytes", "archive_sha256",
                    "source_attestation",
                };
                return receipt != null &&
                    HasExactKeys(receipt, exactReceiptKeys) &&
                    ReceiptLongEquals(receipt, "schema", 4) &&
                    ReceiptEquals(receipt, "canary_id", PhaseACanaryId) &&
                    ReceiptEquals(receipt, "status", PhaseAReceiptStatus) &&
                    ReceiptEquals(receipt, "phase", PhaseAName) &&
                    ReceiptEquals(receipt, "package_id", PackageId) &&
                    ReceiptEquals(receipt, "pack_name", PackName) &&
                    ReceiptEquals(receipt, "device_name", DeviceName) &&
                    ReceiptEquals(receipt, "edition", "enhanced") &&
                    ReceiptEquals(receipt, "layout", Layout) &&
                    ReceiptEquals(receipt, "runtime_contract",
                        PhaseARuntimeContract) &&
                    ReceiptEquals(receipt, "archive_registration",
                        "metadata-only") &&
                    ReceiptEquals(receipt, "activation", PhaseAActivation) &&
                    ReceiptEquals(receipt, "property_scope", "grapeseed") &&
                    ReceiptLongEquals(receipt, "asset_count", 0) &&
                    ReceiptLongEquals(receipt, "data_file_count", 0) &&
                    ReceiptEquals(receipt, "startup_changeset",
                        StartupChangeset) &&
                    ReceiptLongEquals(receipt, "dormant_group_count", 1) &&
                    ReceiptStringListEquals(receipt, "declared_groups",
                        "GROUP_STARTUP", DormantGroup) &&
                    ReceiptStringListEquals(receipt, "stock_changesets",
                        StockChangeset) &&
                    ReceiptStringListEquals(receipt, "ipls", GrapeseedIpl) &&
                    HasExactPhaseAGroup(receipt) &&
                    ReceiptBooleanEquals(receipt,
                        "native_group_execution_enabled", false) &&
                    ReceiptBooleanEquals(receipt,
                        "runtime_ipl_requests_enabled", false) &&
                    ReceiptBooleanEquals(receipt, "gameconfig_changed", false) &&
                    ReceiptBooleanEquals(receipt,
                        "native_host_installed", false) &&
                    ReceiptLongEquals(receipt, "archive_bytes", archiveBytes) &&
                    FixedTimeEquals(
                        ReceiptValue(receipt, "archive_sha256"), archiveSha256) &&
                    HasExactSourceAttestation(receipt);
            }
            catch
            {
                return false;
            }
        }

        internal static bool IsExactPhaseBBlackTransitionContract(
            string marker, string receiptJson, long archiveBytes,
            string archiveSha256)
        {
            if (!TryParseStrictMarker(marker, PhaseBMarkerPreamble,
                    out Dictionary<string, string> markerFields) ||
                archiveBytes <= 0 || !IsSha256(archiveSha256))
                return false;
            string[] exactMarkerKeys =
            {
                "canary_id", "schema", "status", "phase", "layout",
                "runtime_contract", "archive_registration", "activation",
                "activation_scope", "property_scope", "asset_count",
                "data_file_count", "startup_changeset",
                "dormant_group_count", "declared_groups",
                "stock_changesets", "ipls",
                "native_group_execution_enabled",
                "runtime_ipl_requests_enabled",
                "proximity_activation_enabled", "black_transition_required",
                "keep_resident", "release_on_exit", "gameconfig_changed",
                "native_host_installed", "phase_a_canary_id",
                "phase_a_transaction_id", "phase_a_observation_sha256",
                "receipt", "archive_bytes", "archive_sha256",
            };
            if (!HasExactKeys(markerFields, exactMarkerKeys) ||
                !MarkerEquals(markerFields, "canary_id", PhaseBCanaryId) ||
                !MarkerEquals(markerFields, "schema", "5") ||
                !MarkerEquals(markerFields, "status", PhaseBMarkerStatus) ||
                !MarkerEquals(markerFields, "phase", PhaseBName) ||
                !MarkerEquals(markerFields, "layout", Layout) ||
                !MarkerEquals(markerFields, "runtime_contract",
                    PhaseBRuntimeContract) ||
                !MarkerEquals(markerFields, "archive_registration",
                    "metadata-only") ||
                !MarkerEquals(markerFields, "activation", PhaseBActivation) ||
                !MarkerEquals(markerFields, "activation_scope",
                    PhaseBActivationScope) ||
                !MarkerEquals(markerFields, "property_scope", "grapeseed") ||
                !MarkerEquals(markerFields, "asset_count", "0") ||
                !MarkerEquals(markerFields, "data_file_count", "0") ||
                !MarkerEquals(markerFields, "startup_changeset",
                    StartupChangeset) ||
                !MarkerEquals(markerFields, "dormant_group_count", "1") ||
                !MarkerEquals(markerFields, "declared_groups",
                    "GROUP_STARTUP," + DormantGroup) ||
                !MarkerEquals(markerFields, "stock_changesets",
                    StockChangeset) ||
                !MarkerEquals(markerFields, "ipls", GrapeseedIpl) ||
                !MarkerEquals(markerFields,
                    "native_group_execution_enabled", "true") ||
                !MarkerEquals(markerFields,
                    "runtime_ipl_requests_enabled", "true") ||
                !MarkerEquals(markerFields,
                    "proximity_activation_enabled", "false") ||
                !MarkerEquals(markerFields,
                    "black_transition_required", "true") ||
                !MarkerEquals(markerFields, "keep_resident", "true") ||
                !MarkerEquals(markerFields, "release_on_exit", "false") ||
                !MarkerEquals(markerFields, "gameconfig_changed", "false") ||
                !MarkerEquals(markerFields, "native_host_installed", "false") ||
                !MarkerEquals(markerFields, "phase_a_canary_id",
                    PhaseACanaryId) ||
                !MarkerEquals(markerFields, "receipt", ReceiptName) ||
                !IsTransactionId(markerFields["phase_a_transaction_id"]) ||
                !IsSha256(markerFields["phase_a_observation_sha256"]) ||
                !long.TryParse(markerFields["archive_bytes"],
                    out long markerBytes) || markerBytes != archiveBytes ||
                !FixedTimeEquals(markerFields["archive_sha256"],
                    archiveSha256))
                return false;

            try
            {
                Dictionary<string, object> receipt = Deserialize(receiptJson);
                string[] exactReceiptKeys =
                {
                    "schema", "canary_id", "status", "phase", "package_id",
                    "pack_name", "device_name", "edition", "layout",
                    "runtime_contract", "archive_registration", "activation",
                    "activation_scope", "property_scope", "asset_count",
                    "data_file_count", "startup_changeset",
                    "dormant_group_count", "declared_groups",
                    "stock_changesets", "ipls", "groups",
                    "native_group_execution_enabled",
                    "runtime_ipl_requests_enabled",
                    "proximity_activation_enabled", "black_transition_required",
                    "keep_resident", "release_on_exit", "gameconfig_changed",
                    "native_host_installed", "archive_bytes", "archive_sha256",
                    "source_attestation", "phase_a_parent",
                    "phase_a_observation_sha256",
                };
                return receipt != null &&
                    HasExactKeys(receipt, exactReceiptKeys) &&
                    ReceiptLongEquals(receipt, "schema", 5) &&
                    ReceiptEquals(receipt, "canary_id", PhaseBCanaryId) &&
                    ReceiptEquals(receipt, "status", PhaseBReceiptStatus) &&
                    ReceiptEquals(receipt, "phase", PhaseBName) &&
                    ReceiptEquals(receipt, "package_id", PackageId) &&
                    ReceiptEquals(receipt, "pack_name", PackName) &&
                    ReceiptEquals(receipt, "device_name", DeviceName) &&
                    ReceiptEquals(receipt, "edition", "enhanced") &&
                    ReceiptEquals(receipt, "layout", Layout) &&
                    ReceiptEquals(receipt, "runtime_contract",
                        PhaseBRuntimeContract) &&
                    ReceiptEquals(receipt, "archive_registration",
                        "metadata-only") &&
                    ReceiptEquals(receipt, "activation", PhaseBActivation) &&
                    ReceiptEquals(receipt, "activation_scope",
                        PhaseBActivationScope) &&
                    ReceiptEquals(receipt, "property_scope", "grapeseed") &&
                    ReceiptLongEquals(receipt, "asset_count", 0) &&
                    ReceiptLongEquals(receipt, "data_file_count", 0) &&
                    ReceiptEquals(receipt, "startup_changeset",
                        StartupChangeset) &&
                    ReceiptLongEquals(receipt, "dormant_group_count", 1) &&
                    ReceiptStringListEquals(receipt, "declared_groups",
                        "GROUP_STARTUP", DormantGroup) &&
                    ReceiptStringListEquals(receipt, "stock_changesets",
                        StockChangeset) &&
                    ReceiptStringListEquals(receipt, "ipls", GrapeseedIpl) &&
                    HasExactPhaseBGroup(receipt) &&
                    ReceiptBooleanEquals(receipt,
                        "native_group_execution_enabled", true) &&
                    ReceiptBooleanEquals(receipt,
                        "runtime_ipl_requests_enabled", true) &&
                    ReceiptBooleanEquals(receipt,
                        "proximity_activation_enabled", false) &&
                    ReceiptBooleanEquals(receipt,
                        "black_transition_required", true) &&
                    ReceiptBooleanEquals(receipt, "keep_resident", true) &&
                    ReceiptBooleanEquals(receipt, "release_on_exit", false) &&
                    ReceiptBooleanEquals(receipt, "gameconfig_changed", false) &&
                    ReceiptBooleanEquals(receipt,
                        "native_host_installed", false) &&
                    ReceiptLongEquals(receipt, "archive_bytes", archiveBytes) &&
                    FixedTimeEquals(
                        ReceiptValue(receipt, "archive_sha256"), archiveSha256) &&
                    HasExactSourceAttestation(receipt) &&
                    HasExactPhaseAParent(receipt, archiveSha256,
                        markerFields["phase_a_transaction_id"]) &&
                    IsSha256(ReceiptValue(
                        receipt, "phase_a_observation_sha256")) &&
                    FixedTimeEquals(
                        ReceiptValue(receipt, "phase_a_observation_sha256"),
                        markerFields["phase_a_observation_sha256"]);
            }
            catch
            {
                return false;
            }
        }

        private static bool HasExactPhaseAGroup(
            IDictionary<string, object> receipt)
        {
            if (!receipt.TryGetValue("groups", out object rawGroups) ||
                !(rawGroups is IList groups) || groups.Count != 1 ||
                !(groups[0] is IDictionary<string, object> group))
                return false;
            string[] keys =
            {
                "property", "group", "changesets", "ipls",
                "activation_enabled",
            };
            return HasExactKeys(group, keys) &&
                ReceiptEquals(group, "property", "grapeseed") &&
                ReceiptEquals(group, "group", DormantGroup) &&
                ReceiptStringListEquals(group, "changesets", StockChangeset) &&
                ReceiptStringListEquals(group, "ipls", GrapeseedIpl) &&
                ReceiptBooleanEquals(group, "activation_enabled", false);
        }

        private static bool HasExactPhaseBGroup(
            IDictionary<string, object> receipt)
        {
            if (!receipt.TryGetValue("groups", out object rawGroups) ||
                !(rawGroups is IList groups) || groups.Count != 1 ||
                !(groups[0] is IDictionary<string, object> group))
                return false;
            string[] keys =
            {
                "property", "group", "changesets", "ipls",
                "activation_enabled", "activation_sources",
                "requires_black_screen", "keep_resident", "release_on_exit",
            };
            return HasExactKeys(group, keys) &&
                ReceiptEquals(group, "property", "grapeseed") &&
                ReceiptEquals(group, "group", DormantGroup) &&
                ReceiptStringListEquals(group, "changesets", StockChangeset) &&
                ReceiptStringListEquals(group, "ipls", GrapeseedIpl) &&
                ReceiptBooleanEquals(group, "activation_enabled", true) &&
                ReceiptStringListEquals(group, "activation_sources",
                    "garage_entry") &&
                ReceiptBooleanEquals(group, "requires_black_screen", true) &&
                ReceiptBooleanEquals(group, "keep_resident", true) &&
                ReceiptBooleanEquals(group, "release_on_exit", false);
        }

        private static bool HasExactPhaseAParent(
            IDictionary<string, object> receipt, string archiveSha256,
            string markerTransactionId)
        {
            if (!receipt.TryGetValue("phase_a_parent", out object rawParent) ||
                !(rawParent is IDictionary<string, object> parent))
                return false;
            string[] keys =
            {
                "canary_id", "transaction_id", "archive_sha256",
                "marker_sha256", "runtime_receipt_sha256",
            };
            return HasExactKeys(parent, keys) &&
                ReceiptEquals(parent, "canary_id", PhaseACanaryId) &&
                IsTransactionId(ReceiptValue(parent, "transaction_id")) &&
                string.Equals(ReceiptValue(parent, "transaction_id"),
                    markerTransactionId, StringComparison.Ordinal) &&
                FixedTimeEquals(
                    ReceiptValue(parent, "archive_sha256"), archiveSha256) &&
                IsSha256(ReceiptValue(parent, "marker_sha256")) &&
                IsSha256(ReceiptValue(parent, "runtime_receipt_sha256"));
        }

        private static bool HasExactSourceAttestation(
            IDictionary<string, object> receipt)
        {
            if (!receipt.TryGetValue("source_attestation", out object raw) ||
                !(raw is IDictionary<string, object> source))
                return false;
            string[] sourceKeys =
            {
                "pack", "archive", "source", "path", "size", "mtime_ns",
                "archive_sha256", "content_xml_bytes", "content_xml_sha256",
                "setup2_xml_bytes", "setup2_xml_sha256", "device_name",
                "device_name_sha256", "setup_order", "stock_startup_group",
                "stock_startup_changesets", "stock_startup_changeset",
                "stock_startup_changeset_sha256", "stock_proxy",
                "stock_map_group", "stock_map_group_changesets",
                "changeset_name", "changeset_sha256", "official_semantics",
            };
            if (!HasExactKeys(source, sourceKeys) ||
                !ReceiptEquals(source, "pack", "mpheist") ||
                !ReceiptEquals(source, "archive", "dlc.rpf") ||
                !(ReceiptEquals(source, "source", "stock") ||
                  ReceiptEquals(source, "source", "mods")) ||
                !ReceiptLongPositive(source, "size") ||
                !ReceiptLongPositive(source, "mtime_ns") ||
                !IsSha256(ReceiptValue(source, "archive_sha256")) ||
                !ReceiptLongPositive(source, "content_xml_bytes") ||
                !IsSha256(ReceiptValue(source, "content_xml_sha256")) ||
                !ReceiptLongPositive(source, "setup2_xml_bytes") ||
                !IsSha256(ReceiptValue(source, "setup2_xml_sha256")) ||
                !ReceiptEquals(source, "device_name", "dlcMPHeist") ||
                !IsSha256(ReceiptValue(source, "device_name_sha256")) ||
                !ReceiptLongEquals(source, "setup_order", 10) ||
                !ReceiptEquals(source, "stock_startup_group", "GROUP_STARTUP") ||
                !ReceiptStringListEquals(source, "stock_startup_changesets",
                    ExpectedStockStartupGroup) ||
                !ReceiptEquals(source, "stock_startup_changeset",
                    "MPHEIST_AUTOGEN") ||
                !IsSha256(ReceiptValue(
                    source, "stock_startup_changeset_sha256")) ||
                !ReceiptEquals(source, "stock_proxy",
                    "dlcMPHeist:/common/data/interiorProxies.meta") ||
                !ReceiptEquals(source, "stock_map_group", "GROUP_MAP") ||
                !ReceiptStringListEquals(source,
                    "stock_map_group_changesets", ExpectedStockMapGroup) ||
                !ReceiptEquals(source, "changeset_name", StockChangeset) ||
                !IsSha256(ReceiptValue(source, "changeset_sha256")) ||
                !HasExactOfficialSemantics(source))
                return false;

            string expectedPath = ReceiptEquals(source, "source", "mods")
                ? "mods/update/x64/dlcpacks/mpheist/dlc.rpf"
                : "update/x64/dlcpacks/mpheist/dlc.rpf";
            return ReceiptEquals(source, "path", expectedPath);
        }

        private static bool HasExactOfficialSemantics(
            IDictionary<string, object> source)
        {
            if (!source.TryGetValue("official_semantics", out object raw) ||
                !(raw is IDictionary<string, object> semantics))
                return false;
            string[] keys =
            {
                "associated_maps", "files_to_invalidate",
                "files_to_disable", "files_to_enable",
                "requires_loading_screen", "loading_screen_context",
                "use_cache_loader",
            };
            return HasExactKeys(semantics, keys) &&
                ReceiptStringListEquals(
                    semantics, "associated_maps", "MO_JIM_L11") &&
                ReceiptStringListEquals(
                    semantics, "files_to_invalidate",
                    ExpectedFilesToInvalidate) &&
                ReceiptStringListEquals(
                    semantics, "files_to_disable") &&
                ReceiptStringListEquals(
                    semantics, "files_to_enable", ExpectedFilesToEnable) &&
                ReceiptBooleanEquals(
                    semantics, "requires_loading_screen", true) &&
                ReceiptEquals(semantics, "loading_screen_context",
                    "LOADINGSCREEN_CONTEXT_LAST_FRAME") &&
                ReceiptBooleanEquals(semantics, "use_cache_loader", true);
        }

        private static bool VerifyInstalledPhaseAContract() =>
            TryResolveInstalledContract(
                phaseB: false, out SourceArchiveAttestationIdentity _);

        private static bool VerifyInstalledPhaseBContract() =>
            TryResolveInstalledPhaseBContract(
                out SourceArchiveAttestationIdentity _);

        private static bool TryResolveInstalledPhaseBContract(
            out SourceArchiveAttestationIdentity identity) =>
            TryResolveInstalledContract(phaseB: true, out identity);

        private static bool TryResolveInstalledContract(
            bool phaseB, out SourceArchiveAttestationIdentity identity)
        {
            identity = null;
            try
            {
                string executable = Process.GetCurrentProcess()
                    .MainModule?.FileName ?? string.Empty;
                if (Path.GetFileName(executable).IndexOf(
                        "Enhanced", StringComparison.OrdinalIgnoreCase) < 0)
                    return false;
                string gameRoot = Path.GetDirectoryName(executable);
                if (string.IsNullOrWhiteSpace(gameRoot)) return false;
                string packRoot = Path.Combine(gameRoot, "mods", "update",
                    "x64", "dlcpacks", PackName);
                string archivePath = Path.Combine(packRoot, "dlc.rpf");
                string markerPath = Path.Combine(packRoot, MarkerName);
                string receiptPath = Path.Combine(packRoot, ReceiptName);
                if (!HasRequiredFilesystemIsolation(gameRoot) ||
                    !File.Exists(archivePath) || !File.Exists(markerPath) ||
                    !File.Exists(receiptPath) ||
                    new FileInfo(archivePath).Length <= 0 ||
                    new FileInfo(archivePath).Length >
                        MaximumBridgeArchiveBytes ||
                    new FileInfo(markerPath).Length > MaximumMarkerBytes ||
                    new FileInfo(receiptPath).Length > MaximumReceiptBytes)
                    return false;

                var archive = new FileInfo(archivePath);
                string archiveSha256 = Sha256File(archivePath);
                string marker = File.ReadAllText(markerPath);
                string receiptJson = File.ReadAllText(receiptPath);
                bool exact = phaseB
                    ? IsExactPhaseBBlackTransitionContract(
                        marker, receiptJson, archive.Length, archiveSha256)
                    : IsExactPhaseABootOnlyContract(
                        marker, receiptJson, archive.Length, archiveSha256);
                if (!exact) return false;

                Dictionary<string, object> receipt = Deserialize(receiptJson);
                if (!(receipt?["source_attestation"] is
                        IDictionary<string, object> source)) return false;
                string receiptProvenance = ReceiptValue(source, "source");
                string receiptRelative = ReceiptValue(source, "path")
                    ?.Replace('/', Path.DirectorySeparatorChar);
                if (!TryResolveEffectiveSourceArchive(gameRoot,
                        out string sourcePath, out string provenance,
                        out string relative) ||
                    !string.Equals(receiptProvenance, provenance,
                        StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(receiptRelative, relative,
                        StringComparison.OrdinalIgnoreCase) ||
                    !long.TryParse(ReceiptValue(source, "size"),
                        out long expectedSize) ||
                    !long.TryParse(ReceiptValue(source, "mtime_ns"),
                        out long expectedMtime))
                    return false;
                string expectedSha256 =
                    ReceiptValue(source, "archive_sha256");
                if (!DavisStockReferenceBridgePolicy
                        .IsExactSourceArchiveIdentity(
                            sourcePath, expectedSize, expectedMtime,
                            expectedSha256, requireSha256: false))
                    return false;
                identity = new SourceArchiveAttestationIdentity(
                    sourcePath, expectedSize, expectedMtime, expectedSha256);
                return true;
            }
            catch
            {
                identity = null;
                return false;
            }
        }

        /// <summary>
        /// OpenIV-style mods content shadows the stock archive. Resolve that
        /// effective source first, then require the receipt provenance and
        /// identity to describe the same file GTA will consume. A later
        /// override insertion/removal therefore invalidates authorization.
        /// </summary>
        internal static bool TryResolveEffectiveSourceArchive(
            string gameRoot, out string sourcePath, out string provenance,
            out string relativePath)
        {
            sourcePath = null;
            provenance = null;
            relativePath = null;
            if (string.IsNullOrWhiteSpace(gameRoot)) return false;
            try
            {
                string root = Path.GetFullPath(gameRoot);
                string modsRelative = Path.Combine("mods", "update", "x64",
                    "dlcpacks", "mpheist", "dlc.rpf");
                string stockRelative = Path.Combine("update", "x64",
                    "dlcpacks", "mpheist", "dlc.rpf");
                string modsPath = Path.GetFullPath(
                    Path.Combine(root, modsRelative));
                string stockPath = Path.GetFullPath(
                    Path.Combine(root, stockRelative));
                if (File.Exists(modsPath))
                {
                    sourcePath = modsPath;
                    provenance = "mods";
                    relativePath = modsRelative;
                }
                else if (File.Exists(stockPath))
                {
                    sourcePath = stockPath;
                    provenance = "stock";
                    relativePath = stockRelative;
                }
                else
                {
                    return false;
                }

                string rooted = root.TrimEnd(Path.DirectorySeparatorChar,
                    Path.AltDirectorySeparatorChar) +
                    Path.DirectorySeparatorChar;
                return sourcePath.StartsWith(rooted,
                    StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                sourcePath = null;
                provenance = null;
                relativePath = null;
                return false;
            }
        }

        /// <summary>
        /// The promoted bridge owns exactly three regular, non-reparse files.
        /// Retired broad map packs and native MapHost implementations would
        /// create competing authority, so either one invalidates this narrow
        /// metadata-only contract before any archive hash or native call.
        /// </summary>
        internal static bool HasRequiredFilesystemIsolation(string gameRoot)
        {
            if (string.IsNullOrWhiteSpace(gameRoot)) return false;
            try
            {
                string root = Path.GetFullPath(gameRoot);
                string packRoot = Path.Combine(root, "mods", "update", "x64",
                    "dlcpacks", PackName);
                if (!HasExactOwnedPackLayout(packRoot)) return false;

                string retiredMods = Path.Combine(root, "mods", "update",
                    "x64", "dlcpacks", "allin1_maps");
                string retiredStock = Path.Combine(root, "update", "x64",
                    "dlcpacks", "allin1_maps");
                if (File.Exists(retiredMods) || Directory.Exists(retiredMods) ||
                    File.Exists(retiredStock) || Directory.Exists(retiredStock))
                    return false;

                return !ContainsNativeMapHost(root) &&
                    !ContainsNativeMapHost(Path.Combine(root, "scripts"));
            }
            catch
            {
                return false;
            }
        }

        private static bool HasExactOwnedPackLayout(string packRoot)
        {
            if (!Directory.Exists(packRoot)) return false;
            bool rootIsReparsePoint = IsReparsePoint(packRoot);
            string[] entries = Directory.GetFileSystemEntries(packRoot);
            var observations = new Dictionary<string, bool>(
                StringComparer.OrdinalIgnoreCase);
            foreach (string entry in entries)
            {
                FileAttributes attributes = File.GetAttributes(entry);
                observations[Path.GetFileName(entry)] =
                    (attributes & (FileAttributes.Directory |
                        FileAttributes.ReparsePoint)) == 0 &&
                    File.Exists(entry);
            }
            return IsExactOwnedPackLayoutObservation(
                rootIsReparsePoint, observations);
        }

        internal static bool IsExactOwnedPackLayoutObservation(
            bool packRootIsReparsePoint,
            IDictionary<string, bool> regularNonReparseFiles)
        {
            if (packRootIsReparsePoint || regularNonReparseFiles == null ||
                regularNonReparseFiles.Count != 3 ||
                regularNonReparseFiles.Values.Any(value => !value))
                return false;
            var expected = new HashSet<string>(new[]
            {
                "dlc.rpf", MarkerName, ReceiptName,
            }, StringComparer.OrdinalIgnoreCase);
            return expected.SetEquals(regularNonReparseFiles.Keys);
        }

        private static bool ContainsNativeMapHost(string directory)
        {
            if (!Directory.Exists(directory)) return false;
            foreach (string path in Directory.GetFiles(
                directory, "*.asi", SearchOption.TopDirectoryOnly))
            {
                string name = Path.GetFileNameWithoutExtension(path);
                if (name.IndexOf("maphost",
                        StringComparison.OrdinalIgnoreCase) >= 0)
                    return true;
            }
            return false;
        }

        private static bool IsReparsePoint(string path) =>
            (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;

        private static bool VerifySourceArchiveAttestation(
            SourceArchiveAttestationIdentity identity)
        {
            if (identity == null) return false;
            bool verified = DavisStockReferenceBridgePolicy
                .IsExactSourceArchiveIdentity(
                    identity.Path, identity.Size, identity.MtimeNanoseconds,
                    identity.ExpectedSha256, requireSha256: true);
            ClientLog.Info("DeferredMap",
                verified
                    ? "grapeseed_native_attestation_warmup_verified"
                    : "grapeseed_native_attestation_warmup_rejected",
                new Dictionary<string, object>
                {
                    { "archive_bytes", identity.Size },
                    { "archive_mtime_ns", identity.MtimeNanoseconds },
                    { "verified", verified },
                });
            return verified;
        }

        private static Dictionary<string, object> Deserialize(string json)
        {
            if (string.IsNullOrWhiteSpace(json) ||
                json.Length > MaximumReceiptBytes) return null;
            return new JavaScriptSerializer
            {
                MaxJsonLength = MaximumReceiptBytes,
            }.Deserialize<Dictionary<string, object>>(json);
        }

        private static bool TryParseStrictMarker(
            string marker, string preamble,
            out Dictionary<string, string> fields)
        {
            fields = new Dictionary<string, string>(
                StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrWhiteSpace(marker) ||
                marker.Length > MaximumMarkerBytes) return false;
            string[] lines = marker.Replace("\r", string.Empty).Split('\n');
            if (lines.Length == 0 || !string.Equals(
                    lines[0], preamble, StringComparison.Ordinal))
                return false;
            for (int index = 1; index < lines.Length; index++)
            {
                string line = lines[index];
                if (string.IsNullOrEmpty(line)) continue;
                int separator = line.IndexOf('=');
                if (separator <= 0) return false;
                string key = line.Substring(0, separator).Trim();
                string value = line.Substring(separator + 1).Trim();
                if (string.IsNullOrEmpty(key) || fields.ContainsKey(key))
                    return false;
                fields.Add(key, value);
            }
            return true;
        }

        private static string Sha256File(string path)
        {
            using (var algorithm = SHA256.Create())
            using (var stream = new FileStream(path, FileMode.Open,
                FileAccess.Read, FileShare.Read))
                return BitConverter.ToString(algorithm.ComputeHash(stream))
                    .Replace("-", string.Empty);
        }

        private static bool HasExactKeys<T>(
            IDictionary<string, T> values, IEnumerable<string> expected)
        {
            if (values == null || expected == null) return false;
            return new HashSet<string>(values.Keys,
                StringComparer.OrdinalIgnoreCase).SetEquals(expected);
        }

        private static bool MarkerEquals(
            IDictionary<string, string> fields, string key,
            string expected) =>
            fields != null && fields.TryGetValue(key, out string value) &&
            string.Equals(value?.Trim(), expected,
                StringComparison.OrdinalIgnoreCase);

        private static string ReceiptValue(
            IDictionary<string, object> receipt, string key)
        {
            if (receipt == null || !receipt.TryGetValue(key, out object value) ||
                value == null) return null;
            return Convert.ToString(value)?.Trim();
        }

        private static bool ReceiptEquals(
            IDictionary<string, object> receipt, string key,
            string expected) =>
            string.Equals(ReceiptValue(receipt, key), expected,
                StringComparison.OrdinalIgnoreCase);

        private static bool ReceiptLongEquals(
            IDictionary<string, object> receipt, string key,
            long expected) =>
            long.TryParse(ReceiptValue(receipt, key), out long value) &&
            value == expected;

        private static bool ReceiptLongPositive(
            IDictionary<string, object> receipt, string key) =>
            long.TryParse(ReceiptValue(receipt, key), out long value) &&
            value > 0;

        private static bool ReceiptLongNonNegative(
            IDictionary<string, object> receipt, string key) =>
            long.TryParse(ReceiptValue(receipt, key), out long value) &&
            value >= 0;

        private static bool ReceiptBooleanEquals(
            IDictionary<string, object> receipt, string key,
            bool expected) =>
            receipt != null && receipt.TryGetValue(key, out object value) &&
            value is bool actual && actual == expected;

        private static bool ReceiptStringListEquals(
            IDictionary<string, object> receipt, string key,
            params string[] expected)
        {
            if (receipt == null || expected == null ||
                !receipt.TryGetValue(key, out object raw) ||
                !(raw is IList values) || values.Count != expected.Length)
                return false;
            for (int index = 0; index < expected.Length; index++)
            {
                if (!string.Equals(
                        Convert.ToString(values[index])?.Trim(),
                        expected[index], StringComparison.OrdinalIgnoreCase))
                    return false;
            }
            return true;
        }

        private static bool IsSha256(string value) =>
            !string.IsNullOrWhiteSpace(value) && value.Length == 64 &&
            value.All(character =>
                (character >= '0' && character <= '9') ||
                (character >= 'a' && character <= 'f') ||
                (character >= 'A' && character <= 'F'));

        private static bool IsTransactionId(string value) =>
            !string.IsNullOrWhiteSpace(value) && value.Length == 32 &&
            value.All(character =>
                (character >= '0' && character <= '9') ||
                (character >= 'a' && character <= 'f'));

        private static bool FixedTimeEquals(string left, string right)
        {
            if (!IsSha256(left) || !IsSha256(right)) return false;
            byte[] leftBytes = System.Text.Encoding.ASCII.GetBytes(
                left.ToUpperInvariant());
            byte[] rightBytes = System.Text.Encoding.ASCII.GetBytes(
                right.ToUpperInvariant());
            int difference = leftBytes.Length ^ rightBytes.Length;
            int length = Math.Min(leftBytes.Length, rightBytes.Length);
            for (int index = 0; index < length; index++)
                difference |= leftBytes[index] ^ rightBytes[index];
            return difference == 0;
        }
    }
}
