using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace ALLIN1
{
    /// <summary>
    /// Immutable identity for the stock archive whose full hash authorizes the
    /// Davis Phase-B native mutation. The cache key intentionally includes all
    /// cheap on-disk identity fields plus the receipt-pinned digest.
    /// </summary>
    internal sealed class SourceArchiveAttestationIdentity :
        IEquatable<SourceArchiveAttestationIdentity>
    {
        internal SourceArchiveAttestationIdentity(
            string path, long size, long mtimeNanoseconds,
            string expectedSha256)
        {
            Path = System.IO.Path.GetFullPath(path ?? string.Empty);
            Size = size;
            MtimeNanoseconds = mtimeNanoseconds;
            ExpectedSha256 = (expectedSha256 ?? string.Empty)
                .ToUpperInvariant();
        }

        internal string Path { get; }
        internal long Size { get; }
        internal long MtimeNanoseconds { get; }
        internal string ExpectedSha256 { get; }

        public bool Equals(SourceArchiveAttestationIdentity other) =>
            other != null &&
            string.Equals(Path, other.Path,
                StringComparison.OrdinalIgnoreCase) &&
            Size == other.Size &&
            MtimeNanoseconds == other.MtimeNanoseconds &&
            string.Equals(ExpectedSha256, other.ExpectedSha256,
                StringComparison.OrdinalIgnoreCase);

        public override bool Equals(object value) =>
            Equals(value as SourceArchiveAttestationIdentity);

        public override int GetHashCode()
        {
            unchecked
            {
                int hash = StringComparer.OrdinalIgnoreCase.GetHashCode(Path);
                hash = (hash * 397) ^ Size.GetHashCode();
                hash = (hash * 397) ^ MtimeNanoseconds.GetHashCode();
                hash = (hash * 397) ^ StringComparer.OrdinalIgnoreCase
                    .GetHashCode(ExpectedSha256);
                return hash;
            }
        }
    }

    /// <summary>
    /// Single-flight, process-local cache for an expensive full-file
    /// attestation. Callers never wait for the worker: until the exact keyed
    /// identity has completed successfully, authorization fails closed.
    /// </summary>
    internal sealed class AsyncSourceArchiveAttestationCache
    {
        // Davis and Grapeseed use distinct cache instances, but their stock
        // archives share the same physical disk. Serialize full-file
        // attestations process-wide so startup never hashes multiple
        // multi-gigabyte RPFs concurrently. Begin remains nonblocking and each
        // cache continues to fail closed until its exact identity completes.
        private static readonly SemaphoreSlim GlobalVerifierGate =
            new SemaphoreSlim(1, 1);
        private readonly object _gate = new object();
        private SourceArchiveAttestationIdentity _identity;
        private bool _completed;
        private bool _verified;
        private int _generation;

        internal bool Begin(
            SourceArchiveAttestationIdentity identity,
            Func<SourceArchiveAttestationIdentity, bool> verifier)
        {
            if (identity == null)
                throw new ArgumentNullException(nameof(identity));
            if (verifier == null)
                throw new ArgumentNullException(nameof(verifier));

            int generation;
            lock (_gate)
            {
                if (_identity != null && _identity.Equals(identity))
                    return false;
                _identity = identity;
                _completed = false;
                _verified = false;
                generation = ++_generation;
            }

            Task.Run(() =>
            {
                bool verified;
                GlobalVerifierGate.Wait();
                try
                {
                    // An identity may be superseded while this worker waits
                    // behind another archive. Skip the stale verifier instead
                    // of wasting I/O; the newer generation owns its own queued
                    // worker and remains unauthorized until completion.
                    lock (_gate)
                    {
                        if (_generation != generation || _identity == null ||
                            !_identity.Equals(identity))
                            return;
                    }
                    verified = verifier(identity);
                }
                catch
                {
                    verified = false;
                }
                finally
                {
                    GlobalVerifierGate.Release();
                }

                lock (_gate)
                {
                    // A new identity supersedes an older worker. Never allow a
                    // stale completion to authorize the current file.
                    if (_generation != generation ||
                        !_identity.Equals(identity))
                        return;
                    _verified = verified;
                    _completed = true;
                }
            });
            return true;
        }

        internal bool IsCompletedVerified(
            SourceArchiveAttestationIdentity identity)
        {
            if (identity == null) return false;
            lock (_gate)
            {
                return _identity != null && _identity.Equals(identity) &&
                    _completed && _verified;
            }
        }

        internal bool IsCompleted(
            SourceArchiveAttestationIdentity identity)
        {
            if (identity == null) return false;
            lock (_gate)
            {
                return _identity != null && _identity.Equals(identity) &&
                    _completed;
            }
        }
    }

    internal enum DavisStockReferenceBridgeMode
    {
        Unavailable = 0,
        PhaseABootOnly = 1,
        PhaseBBlackTransition = 2,
    }

    /// <summary>
    /// Safety boundary for the metadata-only mptuner boot canary.
    ///
    /// Phase A proves only that GTA can register a dormant stock-reference
    /// bridge during boot. It grants no authority to execute or revert the
    /// dormant content group and no authority to request or remove an IPL.
    /// Phase B is a distinct, exact marker/receipt contract. It authorizes
    /// only the Davis garage-entry path while a full black transition is held.
    /// </summary>
    internal static class DavisStockReferenceBridgePolicy
    {
        internal const string PackName = "allin1_mptuner_bridge";
        internal const string MarkerName =
            "allin1_mptuner_bridge.active";
        internal const string ReceiptName =
            "allin1_mptuner_bridge.runtime.json";
        internal const string PhaseACanaryId =
            "davis-enhanced-stock-reference-boot-v4";
        internal const string PhaseALayout =
            "stock-reference-v1-metadata-only";
        internal const string PhaseARuntimeContract =
            "allin1-stock-mptuner-davis-boot-v1";
        internal const string PhaseAMarkerStatus =
            "installed_boot_only_pending";
        internal const string PhaseAReceiptStatus = "verified";
        internal const string PackageId = "allin1.online-content";
        internal const string DeviceName = "dlc_allin1_mptuner_bridge";
        internal const string PhaseAName = "phase-a-boot-only";
        internal const string StartupChangeset =
            "ALLIN1_MPTUNER_BRIDGE_AUTOGEN";
        internal const string DormantGroup =
            "ALLIN1_STOCK_MPTUNER_DAVIS_V1";
        internal const string StockChangeset = "MPTUNER_MAP_UPDATE";
        internal const string DavisIpl =
            "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_";
        internal const string PhaseBCanaryId =
            "davis-enhanced-stock-reference-black-transition-v1";
        internal const string PhaseBRuntimeContract =
            "allin1-stock-mptuner-davis-black-transition-v1";
        internal const string PhaseBName = "phase-b-black-transition";
        internal const string PhaseBMarkerStatus =
            "installed_black_transition_pending_test";
        internal const string PhaseBReceiptStatus = "verified";
        internal const string PhaseBActivation =
            "explicit-davis-entry-black-transition";
        internal const string PhaseBActivationScope = "garage-entry-only";
        internal const string PhaseBMarkerPreamble =
            "ALLIN1 stock mptuner Phase-B black-transition bridge; " +
            "Davis garage-entry activation only.";
        private const int VerificationCacheMilliseconds = 5000;
        private static readonly TimedBooleanVerificationCache
            PhaseBVerificationCache = new TimedBooleanVerificationCache();
        private static readonly AsyncSourceArchiveAttestationCache
            NativeMutationAttestation =
                new AsyncSourceArchiveAttestationCache();

        // Runtime authority comes only from the exact promoted marker/receipt
        // pair beside the already-tested metadata archive. The bounded cache
        // prevents per-frame filesystem work while still failing closed soon
        // after any on-disk drift.
        internal static bool IsCurrentRuntimeActivationAuthorized =>
            PhaseBVerificationCache.GetOrVerify(
                Environment.TickCount, VerificationCacheMilliseconds,
                VerifyInstalledPhaseBContract);

        // This property never performs the full stock-archive hash. Startup
        // begins that work on a background worker; entry only consumes a
        // completed result for the exact path/size/mtime/expected-hash key.
        internal static bool IsCurrentNativeMutationAuthorized
        {
            get
            {
                if (!TryResolveInstalledPhaseBContract(
                        out SourceArchiveAttestationIdentity identity))
                    return false;
                NativeMutationAttestation.Begin(
                    identity, VerifySourceArchiveAttestation);
                return NativeMutationAttestation
                    .IsCompletedVerified(identity);
            }
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
                    "davis_native_attestation_warmup_started",
                    new Dictionary<string, object>
                    {
                        { "archive_bytes", identity.Size },
                        { "archive_mtime_ns", identity.MtimeNanoseconds },
                    });
            }
        }

        internal static bool IsRuntimeActivationAuthorized(
            DeferredMapProperty property) =>
            property != DeferredMapProperty.Davis ||
            IsCurrentRuntimeActivationAuthorized;

        internal static DavisStockReferenceBridgeMode Resolve(
            bool exactPhaseABootOnlyContract,
            bool futurePhaseBReceiptVerified)
        {
            // An installed Phase-A contract always wins over a second claim.
            // Mixed Phase-A/Phase-B state is not a valid upgrade boundary.
            if (exactPhaseABootOnlyContract)
                return DavisStockReferenceBridgeMode.PhaseABootOnly;
            return futurePhaseBReceiptVerified
                ? DavisStockReferenceBridgeMode.PhaseBBlackTransition
                : DavisStockReferenceBridgeMode.Unavailable;
        }

        internal static bool AllowsRuntimeMutation(
            DavisStockReferenceBridgeMode mode) =>
            mode == DavisStockReferenceBridgeMode.PhaseBBlackTransition;

        internal static bool IsExactPhaseBBlackTransitionContract(
            string marker, string receiptJson, long archiveBytes,
            string archiveSha256)
        {
            if (string.IsNullOrWhiteSpace(marker) ||
                !marker.TrimStart().StartsWith(
                    PhaseBMarkerPreamble, StringComparison.Ordinal) ||
                archiveBytes <= 0 || !IsSha256(archiveSha256))
                return false;

            Dictionary<string, string> markerFields = ParseMarker(marker);
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
                !MarkerEquals(markerFields, "layout", PhaseALayout) ||
                !MarkerEquals(markerFields, "runtime_contract",
                    PhaseBRuntimeContract) ||
                !MarkerEquals(markerFields, "archive_registration",
                    "metadata-only") ||
                !MarkerEquals(markerFields, "activation", PhaseBActivation) ||
                !MarkerEquals(markerFields, "activation_scope",
                    PhaseBActivationScope) ||
                !MarkerEquals(markerFields, "property_scope", "davis") ||
                !MarkerEquals(markerFields, "asset_count", "0") ||
                !MarkerEquals(markerFields, "data_file_count", "0") ||
                !MarkerEquals(markerFields, "startup_changeset",
                    StartupChangeset) ||
                !MarkerEquals(markerFields, "dormant_group_count", "1") ||
                !MarkerEquals(markerFields, "declared_groups",
                    "GROUP_STARTUP," + DormantGroup) ||
                !MarkerEquals(markerFields, "stock_changesets",
                    StockChangeset) ||
                !MarkerEquals(markerFields, "ipls", DavisIpl) ||
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
                !long.TryParse(markerFields["archive_bytes"],
                    out long markerBytes) || markerBytes != archiveBytes ||
                !FixedTimeEquals(markerFields["archive_sha256"],
                    archiveSha256) ||
                !IsTransactionId(markerFields["phase_a_transaction_id"]) ||
                !IsSha256(markerFields["phase_a_observation_sha256"]))
                return false;

            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt = serializer.Deserialize<
                    Dictionary<string, object>>(receiptJson);
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
                    "proximity_activation_enabled",
                    "black_transition_required", "keep_resident",
                    "release_on_exit", "gameconfig_changed",
                    "native_host_installed", "archive_bytes", "archive_sha256",
                    "source_attestation", "phase_a_parent",
                    "phase_a_observation_sha256",
                };
                if (receipt == null ||
                    !HasExactKeys(receipt, exactReceiptKeys) ||
                    !ReceiptLongEquals(receipt, "schema", 5) ||
                    !ReceiptEquals(receipt, "canary_id", PhaseBCanaryId) ||
                    !ReceiptEquals(receipt, "status", PhaseBReceiptStatus) ||
                    !ReceiptEquals(receipt, "phase", PhaseBName) ||
                    !ReceiptEquals(receipt, "package_id", PackageId) ||
                    !ReceiptEquals(receipt, "pack_name", PackName) ||
                    !ReceiptEquals(receipt, "device_name", DeviceName) ||
                    !ReceiptEquals(receipt, "edition", "enhanced") ||
                    !ReceiptEquals(receipt, "layout", PhaseALayout) ||
                    !ReceiptEquals(receipt, "runtime_contract",
                        PhaseBRuntimeContract) ||
                    !ReceiptEquals(receipt, "archive_registration",
                        "metadata-only") ||
                    !ReceiptEquals(receipt, "activation", PhaseBActivation) ||
                    !ReceiptEquals(receipt, "activation_scope",
                        PhaseBActivationScope) ||
                    !ReceiptEquals(receipt, "property_scope", "davis") ||
                    !ReceiptLongEquals(receipt, "asset_count", 0) ||
                    !ReceiptLongEquals(receipt, "data_file_count", 0) ||
                    !ReceiptEquals(receipt, "startup_changeset",
                        StartupChangeset) ||
                    !ReceiptLongEquals(receipt, "dormant_group_count", 1) ||
                    !ReceiptStringListEquals(receipt, "declared_groups",
                        "GROUP_STARTUP", DormantGroup) ||
                    !ReceiptStringListEquals(receipt, "stock_changesets",
                        StockChangeset) ||
                    !ReceiptStringListEquals(receipt, "ipls", DavisIpl) ||
                    !ReceiptBooleanEquals(receipt,
                        "native_group_execution_enabled", true) ||
                    !ReceiptBooleanEquals(receipt,
                        "runtime_ipl_requests_enabled", true) ||
                    !ReceiptBooleanEquals(receipt,
                        "proximity_activation_enabled", false) ||
                    !ReceiptBooleanEquals(receipt,
                        "black_transition_required", true) ||
                    !ReceiptBooleanEquals(receipt, "keep_resident", true) ||
                    !ReceiptBooleanEquals(receipt, "release_on_exit", false) ||
                    !ReceiptBooleanEquals(receipt,
                        "gameconfig_changed", false) ||
                    !ReceiptBooleanEquals(receipt,
                        "native_host_installed", false) ||
                    !ReceiptLongEquals(receipt, "archive_bytes", archiveBytes) ||
                    !FixedTimeEquals(ReceiptValue(receipt, "archive_sha256"),
                        archiveSha256) ||
                    !IsSha256(ReceiptValue(receipt,
                        "phase_a_observation_sha256")) ||
                    !HasExactPhaseBGroup(receipt) ||
                    !HasExactPhaseAParent(receipt, archiveSha256) ||
                    !HasBoundedSourceAttestation(receipt))
                    return false;

                return FixedTimeEquals(
                    markerFields["phase_a_observation_sha256"],
                    ReceiptValue(receipt, "phase_a_observation_sha256"));
            }
            catch
            {
                return false;
            }
        }

        internal static bool IsExactPhaseABootOnlyContract(
            string marker, string receiptJson)
        {
            Dictionary<string, string> markerFields = ParseMarker(marker);
            if (!MarkerEquals(markerFields, "canary_id", PhaseACanaryId) ||
                !MarkerEquals(markerFields, "layout", PhaseALayout) ||
                !MarkerEquals(markerFields, "runtime_contract",
                    PhaseARuntimeContract) ||
                !MarkerEquals(markerFields, "phase", PhaseAName) ||
                !MarkerEquals(markerFields, "status", PhaseAMarkerStatus) ||
                !MarkerEquals(markerFields, "archive_registration",
                    "metadata-only") ||
                !MarkerEquals(markerFields, "activation",
                    "disabled-phase-a-boot-only") ||
                !MarkerEquals(markerFields, "receipt", ReceiptName) ||
                !MarkerEquals(markerFields, "asset_count", "0") ||
                !MarkerEquals(markerFields, "data_file_count", "0") ||
                !MarkerEquals(markerFields, "startup_changeset",
                    StartupChangeset) ||
                !MarkerEquals(markerFields, "dormant_group_count", "1") ||
                !MarkerEquals(markerFields, "declared_groups",
                    "GROUP_STARTUP," + DormantGroup) ||
                !MarkerEquals(markerFields, "stock_changesets",
                    StockChangeset) ||
                !MarkerEquals(markerFields,
                    "native_group_execution_enabled", "false") ||
                !MarkerEquals(markerFields,
                    "runtime_ipl_requests_enabled", "false") ||
                !MarkerEquals(markerFields, "gameconfig_changed", "false") ||
                !MarkerEquals(markerFields, "native_host_installed", "false"))
                return false;

            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 64 * 1024,
                };
                Dictionary<string, object> receipt = serializer.Deserialize<
                    Dictionary<string, object>>(receiptJson);
                if (receipt == null ||
                    !ReceiptLongEquals(receipt, "schema", 4) ||
                    !ReceiptEquals(receipt, "canary_id", PhaseACanaryId) ||
                    !ReceiptEquals(receipt, "package_id", PackageId) ||
                    !ReceiptEquals(receipt, "pack_name", PackName) ||
                    !ReceiptEquals(receipt, "device_name", DeviceName) ||
                    !ReceiptEquals(receipt, "edition", "enhanced") ||
                    !ReceiptEquals(receipt, "layout", PhaseALayout) ||
                    !ReceiptEquals(receipt, "runtime_contract",
                        PhaseARuntimeContract) ||
                    !ReceiptEquals(receipt, "phase", PhaseAName) ||
                    !ReceiptEquals(receipt, "status", PhaseAReceiptStatus) ||
                    !ReceiptEquals(receipt, "archive_registration",
                        "metadata-only") ||
                    !ReceiptEquals(receipt, "activation",
                        "disabled-phase-a-boot-only") ||
                    !ReceiptLongEquals(receipt, "asset_count", 0) ||
                    !ReceiptLongEquals(receipt, "data_file_count", 0) ||
                    !ReceiptEquals(receipt, "startup_changeset",
                        StartupChangeset) ||
                    !ReceiptLongEquals(receipt,
                        "dormant_group_count", 1) ||
                    !ReceiptStringListEquals(receipt, "declared_groups",
                        "GROUP_STARTUP", DormantGroup) ||
                    !ReceiptStringListEquals(receipt, "stock_changesets",
                        StockChangeset) ||
                    !ReceiptBooleanEquals(receipt,
                        "native_group_execution_enabled", false) ||
                    !ReceiptBooleanEquals(receipt,
                        "runtime_ipl_requests_enabled", false) ||
                    !ReceiptBooleanEquals(receipt,
                        "gameconfig_changed", false) ||
                    !ReceiptBooleanEquals(receipt,
                        "native_host_installed", false) ||
                    !HasExactDormantGroup(receipt))
                    return false;

                // Phase A must not contain an early Phase-B authorization
                // escape hatch, even if every other field is valid.
                return !receipt.ContainsKey(
                    "phase_b_activation_authorized");
            }
            catch
            {
                return false;
            }
        }

        private static bool HasExactDormantGroup(
            IDictionary<string, object> receipt)
        {
            if (!receipt.TryGetValue("groups", out object rawGroups) ||
                !(rawGroups is IList groups) || groups.Count != 1 ||
                !(groups[0] is IDictionary<string, object> group) ||
                !ReceiptEquals(group, "property", "davis") ||
                !ReceiptEquals(group, "group", DormantGroup) ||
                !ReceiptBooleanEquals(group, "activation_enabled", false) ||
                !group.TryGetValue("changesets", out object rawChangesets) ||
                !(rawChangesets is IList changesets) ||
                changesets.Count != 1)
                return false;
            return string.Equals(
                Convert.ToString(changesets[0])?.Trim(), StockChangeset,
                StringComparison.OrdinalIgnoreCase);
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
                ReceiptEquals(group, "property", "davis") &&
                ReceiptEquals(group, "group", DormantGroup) &&
                ReceiptStringListEquals(group, "changesets", StockChangeset) &&
                ReceiptStringListEquals(group, "ipls", DavisIpl) &&
                ReceiptBooleanEquals(group, "activation_enabled", true) &&
                ReceiptStringListEquals(group, "activation_sources",
                    "garage_entry") &&
                ReceiptBooleanEquals(group, "requires_black_screen", true) &&
                ReceiptBooleanEquals(group, "keep_resident", true) &&
                ReceiptBooleanEquals(group, "release_on_exit", false);
        }

        private static bool HasExactPhaseAParent(
            IDictionary<string, object> receipt, string archiveSha256)
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
                FixedTimeEquals(ReceiptValue(parent, "archive_sha256"),
                    archiveSha256) &&
                IsSha256(ReceiptValue(parent, "marker_sha256")) &&
                IsSha256(ReceiptValue(parent, "runtime_receipt_sha256"));
        }

        private static bool HasBoundedSourceAttestation(
            IDictionary<string, object> receipt)
        {
            if (!receipt.TryGetValue("source_attestation", out object raw) ||
                !(raw is IDictionary<string, object> source))
                return false;
            return ReceiptEquals(source, "pack", "mptuner") &&
                ReceiptEquals(source, "archive", "dlc.rpf") &&
                (ReceiptEquals(source, "source", "stock") ||
                 ReceiptEquals(source, "source", "mods")) &&
                ReceiptLongPositive(source, "size") &&
                ReceiptLongPositive(source, "mtime_ns") &&
                IsSha256(ReceiptValue(source, "archive_sha256")) &&
                ReceiptEquals(source, "device_name", "dlc_mpTuner") &&
                ReceiptEquals(source, "stock_startup_group", "GROUP_STARTUP") &&
                ReceiptEquals(source, "stock_startup_changeset",
                    "MPTUNER_AUTOGEN") &&
                ReceiptEquals(source, "stock_map_group", "GROUP_MAP") &&
                ReceiptStringListEquals(source, "stock_map_group_changesets",
                    "MPTUNER_MAP_UPDATE",
                    "MPTUNER_MAP_UPDATE_NAVMESH_ONLY") &&
                ReceiptEquals(source, "changeset_name", StockChangeset);
        }

        internal static bool IsExactSourceArchiveIdentity(
            string sourcePath, long expectedSize, long expectedMtimeNanoseconds,
            string expectedSha256, bool requireSha256)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(sourcePath) ||
                    expectedSize <= 0 || expectedMtimeNanoseconds <= 0 ||
                    !IsSha256(expectedSha256) || !File.Exists(sourcePath))
                    return false;
                var sourceFile = new FileInfo(sourcePath);
                if (sourceFile.Length != expectedSize ||
                    FileMtimeNanoseconds(sourceFile) !=
                        expectedMtimeNanoseconds)
                    return false;
                if (!requireSha256) return true;
                string actualSha256 = Sha256File(sourcePath);
                sourceFile.Refresh();
                // A file changed during hashing must not inherit the result
                // obtained for its previous cache key.
                return sourceFile.Exists &&
                    sourceFile.Length == expectedSize &&
                    FileMtimeNanoseconds(sourceFile) ==
                        expectedMtimeNanoseconds &&
                    FixedTimeEquals(actualSha256, expectedSha256);
            }
            catch
            {
                return false;
            }
        }

        private static bool VerifyInstalledPhaseBContract() =>
            TryResolveInstalledPhaseBContract(
                out SourceArchiveAttestationIdentity _);

        private static bool TryResolveInstalledPhaseBContract(
            out SourceArchiveAttestationIdentity identity)
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
                if (!File.Exists(archivePath) || !File.Exists(markerPath) ||
                    !File.Exists(receiptPath)) return false;

                var archive = new FileInfo(archivePath);
                string archiveSha256 = Sha256File(archivePath);
                string marker = File.ReadAllText(markerPath);
                string receiptJson = File.ReadAllText(receiptPath);
                if (!IsExactPhaseBBlackTransitionContract(
                        marker, receiptJson, archive.Length, archiveSha256))
                    return false;

                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt = serializer.Deserialize<
                    Dictionary<string, object>>(receiptJson);
                if (!(receipt?["source_attestation"] is
                        IDictionary<string, object> source)) return false;
                string provenance = ReceiptValue(source, "source");
                string relative = ReceiptValue(source, "path")
                    ?.Replace('/', Path.DirectorySeparatorChar);
                string expected = string.Equals(provenance, "mods",
                        StringComparison.OrdinalIgnoreCase)
                    ? Path.Combine("mods", "update", "x64", "dlcpacks",
                        "mptuner", "dlc.rpf")
                    : Path.Combine("update", "x64", "dlcpacks", "mptuner",
                        "dlc.rpf");
                if (!string.Equals(relative, expected,
                        StringComparison.OrdinalIgnoreCase)) return false;
                string sourcePath = Path.GetFullPath(
                    Path.Combine(gameRoot, expected));
                string root = Path.GetFullPath(gameRoot)
                    .TrimEnd(Path.DirectorySeparatorChar) +
                    Path.DirectorySeparatorChar;
                if (!sourcePath.StartsWith(root,
                        StringComparison.OrdinalIgnoreCase) ||
                    !File.Exists(sourcePath)) return false;
                if (!long.TryParse(ReceiptValue(source, "size"),
                        out long expectedSize) ||
                    !long.TryParse(ReceiptValue(source, "mtime_ns"),
                        out long expectedMtime))
                    return false;
                string expectedSha256 =
                    ReceiptValue(source, "archive_sha256");
                if (!IsExactSourceArchiveIdentity(
                        sourcePath, expectedSize, expectedMtime,
                        expectedSha256, requireSha256: false))
                    return false;
                identity = new SourceArchiveAttestationIdentity(
                    sourcePath, expectedSize, expectedMtime,
                    expectedSha256);
                return true;
            }
            catch
            {
                identity = null;
                return false;
            }
        }

        private static bool VerifySourceArchiveAttestation(
            SourceArchiveAttestationIdentity identity)
        {
            if (identity == null) return false;
            bool verified = IsExactSourceArchiveIdentity(
                identity.Path, identity.Size, identity.MtimeNanoseconds,
                identity.ExpectedSha256, requireSha256: true);
            ClientLog.Info("DeferredMap",
                verified
                    ? "davis_native_attestation_warmup_verified"
                    : "davis_native_attestation_warmup_rejected",
                new Dictionary<string, object>
                {
                    { "archive_bytes", identity.Size },
                    { "archive_mtime_ns", identity.MtimeNanoseconds },
                    { "verified", verified },
                });
            return verified;
        }

        private static long FileMtimeNanoseconds(FileInfo file)
        {
            // Python reports nanoseconds from the Unix epoch. DateTime ticks
            // are 100 ns from 0001-01-01, so keep this integer-only.
            const long UnixEpochTicks = 621355968000000000L;
            return (file.LastWriteTimeUtc.Ticks - UnixEpochTicks) * 100L;
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
            var keys = new HashSet<string>(values.Keys,
                StringComparer.OrdinalIgnoreCase);
            return keys.SetEquals(expected);
        }

        private static bool ReceiptLongPositive(
            IDictionary<string, object> receipt, string key) =>
            long.TryParse(ReceiptValue(receipt, key), out long value) &&
            value > 0;

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

        private static Dictionary<string, string> ParseMarker(string marker)
        {
            var result = new Dictionary<string, string>(
                StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrWhiteSpace(marker)) return result;
            foreach (string rawLine in marker.Replace("\r", string.Empty)
                .Split('\n'))
            {
                int separator = rawLine.IndexOf('=');
                if (separator <= 0) continue;
                string key = rawLine.Substring(0, separator).Trim();
                string value = rawLine.Substring(separator + 1).Trim();
                if (!string.IsNullOrEmpty(key)) result[key] = value;
            }
            return result;
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
    }
}
