using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal enum StandaloneMapPackLayout
    {
        Missing = 0,
        LegacyMonolithic = 1,
        Deferred = 2,
        Unknown = 3,
        StartupRegisteredIpl = 4,
        Unregistered = 5,
        OfficialReferenceBridge = 6,
    }

    /// <summary>
    /// Small monotonic cache used for filesystem-backed readiness checks that
    /// can be reached repeatedly while GBAY builds its view model. Both ready
    /// and blocked results are cached so a missing or damaged bridge cannot
    /// turn a frame callback into repeated disk work.
    /// </summary>
    internal sealed class TimedBooleanVerificationCache
    {
        private readonly object _gate = new object();
        private bool _hasValue;
        private bool _value;
        private int _checkedAt;

        internal bool GetOrVerify(
            int now, int lifetimeMs, Func<bool> verifier)
        {
            if (verifier == null)
                throw new ArgumentNullException(nameof(verifier));

            lock (_gate)
            {
                // Unsigned subtraction remains correct when TickCount wraps.
                uint elapsed = unchecked((uint)(now - _checkedAt));
                if (_hasValue && lifetimeMs > 0 &&
                    elapsed < unchecked((uint)lifetimeMs))
                    return _value;

                _value = verifier();
                _checkedAt = now;
                _hasValue = true;
                return _value;
            }
        }
    }

    /// <summary>
    /// Detects and probes the locally generated allin1_maps compatibility DLC.
    /// The pack exposes only the Rockstar interior archives used by ALLIN1 to
    /// Story Mode without changing global map state. A failed probe is terminal
    /// for that interaction; callers must never switch the whole session to the
    /// Online map as a fallback.
    /// </summary>
    internal static class StandaloneMapPack
    {
        internal const string RepairableDeliveryUnavailableStatus =
            "Map content unavailable; run Install / Repair";
        internal const string QuarantinedDeliveryUnavailableStatus =
            "Map content temporarily disabled for startup stability";

        internal static string DeliveryUnavailableStatus =>
            DeliveryUnavailableStatusForLayout(
                Layout, IsStartupRegistrationVerified);

        private const string PackName = "allin1_maps";
        private const string ActiveMarker = "allin1_maps.active";
        private const string RuntimeReceipt = "allin1_maps.runtime.json";
        private const string StartupLayout =
            "pruned-local-v3-startup-registered-ipl";
        private const string ReferenceLayout =
            "official-reference-v2-deferred";
        private const string ReferenceContract =
            "allin1-official-map-groups-v2";
        private const string IsolatedStartupIplContract =
            "allin1-isolated-startup-ipl-v1";
        private const string IsolatedStartupIplCanaryId =
            "davis-enhanced-isolated-startup-ipl-v3";
        private const string IsolatedStartupIplActivation =
            "startup-file-registration-plus-request-ipl";
        private const string DavisStartupIpl =
            "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_";
        private static readonly bool StartupRegisteredIplRuntimeRetired = true;
        private const int ReferenceVerificationCacheMs = 5000;
        private static readonly TimedBooleanVerificationCache
            ReferenceVerificationCache =
                new TimedBooleanVerificationCache();

        internal static StandaloneMapPackLayout Layout
        {
            get
            {
                try
                {
                    if (!TryGetPackRoot(out string packRoot))
                        return StandaloneMapPackLayout.Missing;
                    var archive = new FileInfo(Path.Combine(packRoot, "dlc.rpf"));
                    string markerPath = Path.Combine(packRoot, ActiveMarker);
                    if (!archive.Exists || archive.Length <= 0 ||
                        !File.Exists(markerPath))
                        return StandaloneMapPackLayout.Missing;
                    return ClassifyMarker(File.ReadAllText(markerPath));
                }
                catch
                {
                    return StandaloneMapPackLayout.Unknown;
                }
            }
        }

        internal static bool CanUseMonolithicFallback =>
            Layout == StandaloneMapPackLayout.LegacyMonolithic;

        internal static bool IsRuntimeUsable(StandaloneMapPackLayout layout) =>
            layout == StandaloneMapPackLayout.LegacyMonolithic ||
            layout == StandaloneMapPackLayout.OfficialReferenceBridge;

        internal static bool IsReferenceBridgeVerified
        {
            get => ReferenceVerificationCache.GetOrVerify(
                Environment.TickCount, ReferenceVerificationCacheMs,
                VerifyReferenceBridgeNow);
        }

        /// <summary>
        /// Compatibility boundary for the retired locally generated property
        /// pack. It remains callable by older code but never grants authority;
        /// the broad metadata-reference bridge is verified independently.
        /// </summary>
        internal static bool IsIsolatedStartupPropertyVerified(
            DeferredMapProperty property)
        {
            // The v3 Davis startup-IPL canary reached GTA's native metadata
            // loader before SHVDN and crashed at a repeatable native offset.
            // Keep the API and marker classification for diagnostics, but do
            // not let any startup-registered receipt authorize runtime use.
            return false;
        }

        // Retained as a source-compatible alias for callers compiled while
        // the isolated route was still a deferred content-change-set group.
        // The verifier now rejects every retired startup-IPL contract.
        internal static bool IsIsolatedPropertyVerified(
            DeferredMapProperty property) =>
            IsIsolatedStartupPropertyVerified(property);

        internal static bool IsPropertyRuntimeAvailable(
            DeferredMapProperty property)
        {
            var interiorBridge = OfficialInteriorStockBridgePolicy.For(property);
            if (interiorBridge != null)
                return interiorBridge.IsCurrentRuntimeActivationAuthorized;
            // Davis and Grapeseed Phase B are independently attested,
            // property-scoped stock-reference bridges. Neither may inherit
            // authority from the retired broad allin1_maps layout.
            if (property == DeferredMapProperty.Davis)
                return DavisStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized;
            if (property == DeferredMapProperty.Grapeseed)
                return GrapeseedStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized;
            if (property == DeferredMapProperty.GarmentFactory)
                return GarmentStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized;
            return IsIsolatedStartupPropertyVerified(property) ||
                (IsReferenceBridgeVerified &&
                 IsOfficialClosureSafeForVisibleRuntime(property, out _));
        }

        internal static bool IsExactIsolatedStartupIplRequest(
            DeferredMapProperty property, IEnumerable<string> ipls)
        {
            if (property != DeferredMapProperty.Davis || ipls == null)
                return false;
            string[] requested = ipls
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
            return requested.Length == 1 && string.Equals(
                requested[0], DavisStartupIpl,
                StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>
        /// A Rockstar content changeset that declares a loading-screen
        /// transition is not safe to execute while Story Mode is visible.
        /// The metadata bridge intentionally preserves Rockstar's complete
        /// changeset contract, including broad world-archive invalidations;
        /// treating such a route like an ordinary IPL request can therefore
        /// flash the screen or temporarily remove world geometry.
        /// </summary>
        internal static bool IsOfficialClosureSafeForVisibleRuntime(
            DeferredMapProperty property, out string reason)
        {
            reason = "official_closure_receipt_unavailable";
            try
            {
                if (!TryGetPackRoot(out string packRoot)) return false;
                string receiptPath = Path.Combine(packRoot, RuntimeReceipt);
                if (!File.Exists(receiptPath)) return false;
                return IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    File.ReadAllText(receiptPath),
                    DeferredMapContentGroups.Resolve(property), out reason);
            }
            catch
            {
                return false;
            }
        }

        internal static bool IsOfficialClosureSafeForVisibleRuntimeReceipt(
            string receiptJson, string groupName, out string reason)
        {
            reason = "official_closure_receipt_invalid";
            if (string.IsNullOrWhiteSpace(receiptJson) ||
                string.IsNullOrWhiteSpace(groupName)) return false;

            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt =
                    serializer.Deserialize<Dictionary<string, object>>(
                        receiptJson);
                if (receipt == null ||
                    !receipt.TryGetValue("groups", out object rawGroups) ||
                    !(rawGroups is IList groups)) return false;

                foreach (object rawGroup in groups)
                {
                    if (!(rawGroup is IDictionary<string, object> group) ||
                        !ReceiptEquals(group, "group", groupName)) continue;
                    if (!TryReceiptStringSet(group, "references",
                            out HashSet<string> references) ||
                        references.Count == 0)
                    {
                        reason = "official_closure_reference_contract_missing";
                        return false;
                    }
                    if (!group.TryGetValue("routes", out object rawRoutes) ||
                        !(rawRoutes is IList routes) || routes.Count == 0)
                    {
                        reason = "official_closure_routes_missing";
                        return false;
                    }

                    var enabled = new HashSet<string>(
                        StringComparer.OrdinalIgnoreCase);
                    foreach (object rawRoute in routes)
                    {
                        if (!(rawRoute is IDictionary<string, object> route) ||
                            !route.TryGetValue("requires_loading_screen",
                                out object rawRequirement) ||
                            !(rawRequirement is bool requiresLoadingScreen) ||
                            !route.TryGetValue("use_cache_loader",
                                out object rawCacheLoader) ||
                            !(rawCacheLoader is bool useCacheLoader) ||
                            !route.TryGetValue("loading_screen_context",
                                out object rawLoadingContext) ||
                            !(rawLoadingContext is string loadingContext) ||
                            !TryReceiptStringSet(route,
                                "files_to_invalidate", out HashSet<string>
                                    invalidated) ||
                            !TryReceiptStringSet(route,
                                "files_to_disable", out HashSet<string>
                                    disabled) ||
                            !TryReceiptStringSet(route,
                                "files_to_enable", out HashSet<string>
                                    routeEnabled))
                        {
                            reason = "official_closure_loading_contract_missing";
                            return false;
                        }
                        string changeset = ReceiptValue(route, "changeset") ??
                            "unknown";
                        if (requiresLoadingScreen)
                        {
                            reason = "official_closure_requires_loading_screen:" +
                                changeset;
                            return false;
                        }
                        if (!string.IsNullOrWhiteSpace(loadingContext))
                        {
                            reason = "official_closure_loading_context:" +
                                changeset;
                            return false;
                        }
                        if (useCacheLoader)
                        {
                            reason = "official_closure_uses_cache_loader:" +
                                changeset;
                            return false;
                        }
                        if (invalidated.Count > 0)
                        {
                            reason = "official_closure_invalidates_files:" +
                                changeset;
                            return false;
                        }
                        if (disabled.Count > 0)
                        {
                            reason = "official_closure_disables_files:" +
                                changeset;
                            return false;
                        }
                        enabled.UnionWith(routeEnabled);
                    }

                    foreach (string unexpected in enabled.Except(references))
                    {
                        reason =
                            "official_closure_enables_unexpected_reference:" +
                            unexpected;
                        return false;
                    }
                    foreach (string missing in references.Except(enabled))
                    {
                        reason = "official_closure_omits_reference:" + missing;
                        return false;
                    }

                    reason = string.Empty;
                    return true;
                }

                reason = "official_closure_group_missing:" + groupName;
                return false;
            }
            catch
            {
                return false;
            }
        }

        private static bool VerifyReferenceBridgeNow()
        {
            try
            {
                if (!TryGetPackRoot(out string packRoot)) return false;
                string markerPath = Path.Combine(packRoot, ActiveMarker);
                string receiptPath = Path.Combine(packRoot, RuntimeReceipt);
                var archive = new FileInfo(Path.Combine(packRoot, "dlc.rpf"));
                if (!archive.Exists || archive.Length <= 0 ||
                    !File.Exists(markerPath) || !File.Exists(receiptPath))
                    return false;
                string scripts = AppDomain.CurrentDomain.BaseDirectory
                    .TrimEnd(Path.DirectorySeparatorChar,
                        Path.AltDirectorySeparatorChar);
                string gameRoot = Directory.GetParent(scripts)?.FullName;
                string edition = !string.IsNullOrEmpty(gameRoot) &&
                    File.Exists(Path.Combine(gameRoot, "GTA5_Enhanced.exe"))
                    ? "enhanced" : "legacy";
                string archiveHash;
                using (var stream = archive.OpenRead())
                using (var sha = SHA256.Create())
                    archiveHash = BitConverter.ToString(
                        sha.ComputeHash(stream)).Replace("-", string.Empty);
                string receiptJson = File.ReadAllText(receiptPath);
                return IsVerifiedReferenceBridgeReceipt(
                        File.ReadAllText(markerPath), receiptJson,
                        archive.Length, archiveHash, edition) &&
                    AreReferenceSourcesCurrent(receiptJson, gameRoot);
            }
            catch
            {
                return false;
            }
        }

        internal static bool IsStartupRegistrationVerified
        {
            get => false;
        }

        // "Installed" here means usable by the current runtime, not merely
        // present on disk. Retired startup registrations never qualify.
        internal static bool IsInstalled
        {
            get
            {
                StandaloneMapPackLayout layout = Layout;
                return layout == StandaloneMapPackLayout.LegacyMonolithic ||
                    (layout == StandaloneMapPackLayout.OfficialReferenceBridge &&
                     IsReferenceBridgeVerified);
            }
        }

        /// <summary>
        /// The generated map pack owns the five custom land garages and the
        /// yacht world placement. Eclipse, Vespucci Helipad, and Los Santos
        /// Harbour are base-world destinations and remain usable while the
        /// pack is missing, unregistered, or quarantined.
        /// </summary>
        internal static bool IsMapBackedDeliveryDestination(int index) =>
            (index >= 1 && index <= 5) || index == 7;

        internal static bool IsDeliveryDestinationAvailable(
            int index, bool mapPackInstalled) =>
            !IsMapBackedDeliveryDestination(index) ||
            (mapPackInstalled &&
             (index != 2 || DavisStockReferenceBridgePolicy
                 .IsCurrentRuntimeActivationAuthorized) &&
             (index != 4 || GrapeseedStockReferenceBridgePolicy
                 .IsCurrentRuntimeActivationAuthorized));

        internal static bool IsDeliveryDestinationAvailable(int index) =>
            !IsMapBackedDeliveryDestination(index) ||
            (index == 1
                ? IsPropertyRuntimeAvailable(DeferredMapProperty.Harmony)
                : index == 5
                    ? IsPropertyRuntimeAvailable(DeferredMapProperty.Paleto)
                : index == 2
                ? IsPropertyRuntimeAvailable(DeferredMapProperty.Davis)
                : index == 4
                    ? IsPropertyRuntimeAvailable(DeferredMapProperty.Grapeseed)
                    : index == 3
                        ? IsPropertyRuntimeAvailable(
                            DeferredMapProperty.GarmentFactory)
                    : IsInstalled);

        internal static bool IsWorldPropertyPurchaseAvailable(
            bool alreadyOwned, bool mapPackInstalled) =>
            !alreadyOwned && mapPackInstalled;

        internal static bool IsWorldPropertyPurchaseAvailable(
            bool alreadyOwned) =>
            IsWorldPropertyPurchaseAvailable(alreadyOwned, IsInstalled);

        internal static string DeliveryUnavailableStatusForLayout(
            StandaloneMapPackLayout layout,
            bool startupRegistrationVerified = false)
        {
            // Install / Repair deliberately writes the unregistered layout.
            // Telling the player to repair that healthy quarantine creates an
            // endless loop and falsely implies the installer can enable these
            // destinations. Reserve repair guidance for genuinely absent or
            // malformed payloads.
            if (layout == StandaloneMapPackLayout.Unregistered ||
                layout == StandaloneMapPackLayout.Deferred ||
                layout == StandaloneMapPackLayout.StartupRegisteredIpl)
                return QuarantinedDeliveryUnavailableStatus;
            return RepairableDeliveryUnavailableStatus;
        }

        // Compatibility alias retained for older call sites. Deferred layouts
        // must never use this path: their custom group activation either
        // succeeds or the transition fails closed.
        internal static bool TryActivate(string[] ipls, int timeoutMs = 750)
        {
            return TryActivateLegacyFallback(ipls, timeoutMs);
        }

        internal static bool TryActivateLegacyFallback(
            string[] ipls, int timeoutMs = 750)
        {
            StandaloneMapPackLayout layout = Layout;
            if (layout != StandaloneMapPackLayout.LegacyMonolithic ||
                ipls == null || ipls.Length == 0)
            {
                ClientLog.Warn("World", "standalone_map_fallback_rejected",
                    new System.Collections.Generic.Dictionary<string, object>
                    {
                        { "layout", layout.ToString().ToLowerInvariant() },
                        { "ipl_count", ipls?.Length ?? 0 },
                    });
                return false;
            }

            int startedAt = Game.GameTime;
            do
            {
                bool active = true;
                foreach (string ipl in ipls)
                {
                    if (string.IsNullOrWhiteSpace(ipl)) continue;
                    if (!Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl))
                    {
                        Function.Call(Hash.REQUEST_IPL, ipl);
                        active = false;
                    }
                }
                if (active)
                {
                    ClientLog.Info("World", "standalone_map_fallback_ready",
                        new System.Collections.Generic.Dictionary<string, object>
                        {
                            { "layout", "legacy_monolithic" },
                            { "elapsed_ms", Game.GameTime - startedAt },
                            { "ipl_count", ipls.Length },
                        });
                    return true;
                }
                if (timeoutMs <= 0) break;
                Script.Wait(50);
            }
            while (Game.GameTime - startedAt < timeoutMs);

            ClientLog.Warn("World", "standalone_map_fallback_probe_failed",
                new System.Collections.Generic.Dictionary<string, object>
                {
                    { "layout", "legacy_monolithic" },
                    { "elapsed_ms", Game.GameTime - startedAt },
                    { "ipl_count", ipls.Length },
                });
            return false;
        }

        internal static StandaloneMapPackLayout ClassifyMarker(string marker)
        {
            if (string.IsNullOrWhiteSpace(marker))
                return StandaloneMapPackLayout.Unknown;

            string layout = null;
            string archiveRegistration = null;
            foreach (string rawLine in marker.Replace("\r", string.Empty)
                .Split('\n'))
            {
                string line = rawLine.Trim();
                if (line.StartsWith("layout=",
                    StringComparison.OrdinalIgnoreCase))
                    layout = line.Substring("layout=".Length).Trim();
                else if (line.StartsWith("archive_registration=",
                    StringComparison.OrdinalIgnoreCase))
                    archiveRegistration = line.Substring(
                        "archive_registration=".Length).Trim();
            }

            if (string.Equals(archiveRegistration, "disabled",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(archiveRegistration, "unregistered",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(archiveRegistration, "none",
                    StringComparison.OrdinalIgnoreCase))
                return StandaloneMapPackLayout.Unregistered;

            // The marker predates explicit layout fields, so a marker without
            // one belongs to the old GROUP_MAP/GROUP_MAP_SP pack.
            if (string.IsNullOrWhiteSpace(layout))
                return StandaloneMapPackLayout.LegacyMonolithic;
            if (layout.Equals("pruned-local-v3-deferred",
                StringComparison.OrdinalIgnoreCase))
                return StandaloneMapPackLayout.Deferred;
            if (layout.Equals("pruned-local-v3-startup-registered-ipl",
                StringComparison.OrdinalIgnoreCase))
                return StandaloneMapPackLayout.StartupRegisteredIpl;
            if (layout.Equals("pruned-local-v4-unregistered",
                StringComparison.OrdinalIgnoreCase))
                return StandaloneMapPackLayout.Unregistered;
            if (layout.Equals(ReferenceLayout,
                StringComparison.OrdinalIgnoreCase))
                return StandaloneMapPackLayout.OfficialReferenceBridge;
            if (layout.Equals("pruned-local-v2",
                    StringComparison.OrdinalIgnoreCase) ||
                layout.Equals("pruned-local-v2-legacy-monolithic",
                    StringComparison.OrdinalIgnoreCase))
                return StandaloneMapPackLayout.LegacyMonolithic;
            return StandaloneMapPackLayout.Unknown;
        }

        internal static bool IsVerifiedReferenceBridgeReceipt(
            string marker, string receiptJson, long archiveBytes,
            string actualArchiveHash, string expectedEdition)
        {
            if (archiveBytes <= 0 ||
                ClassifyMarker(marker) !=
                    StandaloneMapPackLayout.OfficialReferenceBridge ||
                !IsSha256(actualArchiveHash) ||
                string.IsNullOrWhiteSpace(receiptJson))
                return false;

            Dictionary<string, string> markerFields = ParseMarker(marker);
            if (!MarkerEquals(markerFields, "archive_registration",
                    "metadata-bridge") ||
                !MarkerEquals(markerFields, "activation",
                    "property-group-runtime") ||
                !MarkerEquals(markerFields, "receipt", RuntimeReceipt) ||
                !MarkerEquals(markerFields, "group_contract",
                    ReferenceContract) ||
                !MarkerEquals(markerFields, "asset_count", "0") ||
                !MarkerEquals(markerFields, "reference_count", "17") ||
                !TryPositiveLong(markerFields, "archive_bytes",
                    out long markerBytes) || markerBytes != archiveBytes ||
                !string.Equals(MarkerValue(markerFields, "archive_sha256"),
                    actualArchiveHash, StringComparison.OrdinalIgnoreCase))
                return false;

            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt =
                    serializer.Deserialize<Dictionary<string, object>>(
                        receiptJson);
                if (receipt == null ||
                    !ReceiptEquals(receipt, "status", "verified") ||
                    !ReceiptEquals(receipt, "package_id",
                        "allin1.online-content") ||
                    !ReceiptEquals(receipt, "pack_name", PackName) ||
                    !ReceiptEquals(receipt, "layout", ReferenceLayout) ||
                    !ReceiptEquals(receipt, "edition", expectedEdition) ||
                    !ReceiptEquals(receipt, "group_contract",
                        ReferenceContract) ||
                    !TryReceiptLong(receipt, "schema", out long schema) ||
                    schema != 1 ||
                    !TryReceiptLong(receipt, "asset_count", out long assets) ||
                    assets != 0 ||
                    !TryReceiptLong(receipt, "reference_count",
                        out long references) || references != 17 ||
                    !TryReceiptLong(receipt, "archive_bytes",
                        out long receiptBytes) || receiptBytes != archiveBytes ||
                    !string.Equals(ReceiptValue(receipt, "archive_sha256"),
                        actualArchiveHash, StringComparison.OrdinalIgnoreCase) ||
                    !ReferenceGroupsMatch(receipt))
                    return false;
                return true;
            }
            catch
            {
                return false;
            }
        }

        internal static bool IsVerifiedIsolatedDavisStartupIplReceipt(
            string marker, string receiptJson, long archiveBytes,
            string actualArchiveHash, string expectedEdition)
        {
            // Schema 3 describes the retired live-crashing canary. Preserve
            // the parser for forensic compatibility, but never turn its
            // attestation into runtime authority.
            if (StartupRegisteredIplRuntimeRetired) return false;
            if (archiveBytes <= 0 ||
                !string.Equals(expectedEdition, "enhanced",
                    StringComparison.OrdinalIgnoreCase) ||
                ClassifyMarker(marker) !=
                    StandaloneMapPackLayout.StartupRegisteredIpl ||
                !IsSha256(actualArchiveHash) ||
                string.IsNullOrWhiteSpace(receiptJson))
                return false;

            Dictionary<string, string> markerFields = ParseMarker(marker);
            if (!MarkerEquals(markerFields, "archive_registration",
                    "startup") ||
                !MarkerEquals(markerFields, "activation",
                    IsolatedStartupIplActivation) ||
                !MarkerEquals(markerFields, "receipt", RuntimeReceipt) ||
                !MarkerEquals(markerFields, "runtime_contract",
                    IsolatedStartupIplContract) ||
                !MarkerEquals(markerFields, "property_scope", "davis") ||
                !MarkerEquals(markerFields, "asset_count", "3") ||
                !MarkerEquals(markerFields, "startup_rpf_enable_count", "2") ||
                !MarkerEquals(markerFields, "startup_file_enable_count", "3") ||
                !MarkerEquals(markerFields, "custom_property_groups", "0") ||
                !MarkerEquals(markerFields, "group_map_binding", "false") ||
                !MarkerEquals(markerFields, "reference_count", "3") ||
                !TryPositiveLong(markerFields, "archive_bytes",
                    out long markerBytes) || markerBytes != archiveBytes ||
                !string.Equals(MarkerValue(markerFields, "archive_sha256"),
                    actualArchiveHash, StringComparison.OrdinalIgnoreCase))
                return false;

            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt =
                    serializer.Deserialize<Dictionary<string, object>>(
                        receiptJson);
                if (receipt == null || receipt.Count != 26 ||
                    !ReceiptEquals(receipt, "status", "verified") ||
                    !ReceiptEquals(receipt, "canary_id",
                        IsolatedStartupIplCanaryId) ||
                    !ReceiptEquals(receipt, "package_id",
                        "allin1.online-content") ||
                    !ReceiptEquals(receipt, "pack_name", PackName) ||
                    !ReceiptEquals(receipt, "layout", StartupLayout) ||
                    !ReceiptEquals(receipt, "edition", "enhanced") ||
                    !ReceiptEquals(receipt, "runtime_contract",
                        IsolatedStartupIplContract) ||
                    !ReceiptEquals(receipt, "archive_registration",
                        "startup") ||
                    !ReceiptEquals(receipt, "activation",
                        IsolatedStartupIplActivation) ||
                    !ReceiptEquals(receipt, "property_scope", "davis") ||
                    !TryReceiptLong(receipt, "schema", out long schema) ||
                    schema != 3 ||
                    !TryReceiptLong(receipt, "asset_count", out long assets) ||
                    assets != 3 ||
                    !TryReceiptLong(receipt, "startup_rpf_enable_count",
                        out long startupEnables) || startupEnables != 2 ||
                    !TryReceiptLong(receipt, "startup_file_enable_count",
                        out long startupFiles) || startupFiles != 3 ||
                    !TryReceiptLong(receipt, "archive_bytes",
                        out long receiptBytes) || receiptBytes != archiveBytes ||
                    !string.Equals(ReceiptValue(receipt, "archive_sha256"),
                        actualArchiveHash, StringComparison.OrdinalIgnoreCase) ||
                    !ReceiptStringListEquals(receipt, "properties",
                        "davis") ||
                    !ReceiptStringListEquals(receipt, "ipls",
                        DavisStartupIpl) ||
                    !ReceiptStringListEquals(receipt, "declared_changesets",
                        "ALLIN1_MAPS_AUTOGEN") ||
                    !ReceiptStringListEquals(receipt, "declared_groups",
                        "GROUP_STARTUP") ||
                    !ReceiptStringListEquals(receipt,
                        "custom_property_groups") ||
                    !ReceiptBooleanEquals(receipt, "group_map_binding", false) ||
                    !IsolatedDavisStartupGroupMatches(receipt) ||
                    !IsolatedDavisSourceArchiveMatches(receipt) ||
                    !IsolatedDavisSourceAssetsMatch(receipt) ||
                    !IsolatedDavisProxyFilterMatches(receipt))
                    return false;
                return true;
            }
            catch
            {
                return false;
            }
        }

        // Compatibility entry point used by focused tests and older callers.
        // It deliberately delegates to the v3-only verifier, so a formerly
        // valid v2 deferred receipt is now rejected.
        internal static bool IsVerifiedIsolatedDavisReceipt(
            string marker, string receiptJson, long archiveBytes,
            string actualArchiveHash, string expectedEdition) =>
            IsVerifiedIsolatedDavisStartupIplReceipt(
                marker, receiptJson, archiveBytes, actualArchiveHash,
                expectedEdition);

        private static bool IsolatedDavisStartupGroupMatches(
            IDictionary<string, object> receipt)
        {
            if (receipt == null ||
                !receipt.TryGetValue("groups", out object rawGroups) ||
                !(rawGroups is IList groups) || groups.Count != 1 ||
                !(groups[0] is IDictionary<string, object> group) ||
                group.Count != 3 ||
                !ReceiptEquals(group, "group", "GROUP_STARTUP") ||
                !ReceiptStringListEquals(group, "changesets",
                    "ALLIN1_MAPS_AUTOGEN") ||
                !ReceiptStringListEquals(group, "references",
                    IsolatedDavisReferences))
                return false;
            return true;
        }

        private static bool IsolatedDavisSourceArchiveMatches(
            IDictionary<string, object> receipt)
        {
            if (receipt == null ||
                !receipt.TryGetValue("source_archives", out object raw) ||
                !(raw is IList sources) || sources.Count != 1 ||
                !(sources[0] is IDictionary<string, object> source) ||
                source.Count != 7 ||
                !ReceiptEquals(source, "pack", "mptuner") ||
                !ReceiptEquals(source, "archive", "dlc.rpf") ||
                !ReceiptEquals(source, "source", "stock") ||
                !ReceiptEquals(source, "path",
                    "update/x64/dlcpacks/mptuner/dlc.rpf") ||
                !TryReceiptLong(source, "size", out long bytes) || bytes <= 0 ||
                !TryReceiptLong(source, "mtime_ns", out long mtimeNs) ||
                mtimeNs <= 0 ||
                !IsSha256(ReceiptValue(source, "sha256")))
                return false;

            return true;
        }

        private static bool IsolatedDavisSourceAssetsMatch(
            IDictionary<string, object> receipt)
        {
            if (receipt == null ||
                !receipt.TryGetValue("sources", out object rawSources) ||
                !(rawSources is IList sources) || sources.Count != 3)
                return false;

            string[] sourcePaths =
            {
                "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
                "x64/levels/gta5/interiors/int_placement_tr.rpf",
                "common/data/interiorProxies.meta",
            };
            string[] destinationPaths =
            {
                "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
                "x64/levels/gta5/interiors/int_placement_tr.rpf",
                "common/data/allin1/mptuner_davis_interiorProxies.meta",
            };
            for (int index = 0; index < sourcePaths.Length; index++)
            {
                if (!(sources[index] is IDictionary<string, object> source) ||
                    source.Count != (index == 2 ? 8 : 6) ||
                    !ReceiptEquals(source, "source_pack", "mptuner") ||
                    !ReceiptEquals(source, "source_archive", "dlc.rpf") ||
                    !ReceiptEquals(source, "source_path", sourcePaths[index]) ||
                    !ReceiptEquals(source, "destination_path",
                        destinationPaths[index]) ||
                    !TryReceiptLong(source, "source_asset_bytes",
                        out long bytes) || bytes <= 0 ||
                    !IsSha256(ReceiptValue(source,
                        "source_asset_sha256")))
                    return false;
            }
            return sources[2] is IDictionary<string, object> proxySource &&
                ReceiptStringListEquals(proxySource, "proxy_names",
                    DavisStartupIpl) &&
                TryReceiptLong(proxySource, "proxy_start_from",
                    out long startFrom) && startFrom == 1117;
        }

        private static bool IsolatedDavisProxyFilterMatches(
            IDictionary<string, object> receipt)
        {
            if (receipt == null ||
                !receipt.TryGetValue("proxy_filters", out object raw) ||
                !(raw is IList filters) || filters.Count != 1 ||
                !(filters[0] is IDictionary<string, object> filter) ||
                filter.Count != 4 ||
                !ReceiptEquals(filter, "destination_path",
                    "common/data/allin1/mptuner_davis_interiorProxies.meta") ||
                !ReceiptStringListEquals(filter, "proxy_names",
                    DavisStartupIpl) ||
                !TryReceiptLong(filter, "start_from", out long startFrom) ||
                startFrom != 1117 ||
                !TryReceiptLong(filter, "entry_count", out long entries) ||
                entries != 1)
                return false;
            return true;
        }

        private static readonly string[] IsolatedDavisReferences =
        {
            "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/" +
                "dlc_int_01_tr.rpf",
            "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/" +
                "int_placement_tr.rpf",
            "dlc_allin1_maps:/common/data/allin1/" +
                "mptuner_davis_interiorProxies.meta",
        };

        internal static bool AreIsolatedDavisSourcesCurrent(
            string receiptJson, string gameRoot)
        {
            if (string.IsNullOrWhiteSpace(receiptJson) ||
                string.IsNullOrWhiteSpace(gameRoot)) return false;
            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt =
                    serializer.Deserialize<Dictionary<string, object>>(
                        receiptJson);
                if (receipt == null ||
                    !receipt.TryGetValue("source_archives", out object raw) ||
                    !(raw is IList sources) || sources.Count != 1 ||
                    !(sources[0] is IDictionary<string, object> source) ||
                    !ReceiptEquals(source, "pack", "mptuner") ||
                    !ReceiptEquals(source, "archive", "dlc.rpf") ||
                    !IsSha256(ReceiptValue(source, "sha256")))
                    return false;

                string relative = ReceiptValue(source, "path")
                    ?.Replace('/', Path.DirectorySeparatorChar);
                string provenance = ReceiptValue(source, "source");
                string expectedRelative = string.Equals(
                    provenance, "mods", StringComparison.OrdinalIgnoreCase)
                    ? Path.Combine("mods", "update", "x64", "dlcpacks",
                        "mptuner", "dlc.rpf")
                    : Path.Combine("update", "x64", "dlcpacks", "mptuner",
                        "dlc.rpf");
                if (!string.Equals(relative, expectedRelative,
                        StringComparison.OrdinalIgnoreCase) ||
                    !(string.Equals(provenance, "mods",
                          StringComparison.OrdinalIgnoreCase) ||
                      string.Equals(provenance, "stock",
                          StringComparison.OrdinalIgnoreCase)))
                    return false;

                string root = Path.GetFullPath(gameRoot)
                    .TrimEnd(Path.DirectorySeparatorChar) +
                    Path.DirectorySeparatorChar;
                string sourcePath = Path.GetFullPath(Path.Combine(
                    gameRoot, expectedRelative));
                if (!sourcePath.StartsWith(root,
                        StringComparison.OrdinalIgnoreCase) ||
                    !File.Exists(sourcePath) ||
                    !TryReceiptLong(source, "size", out long size) ||
                    size != new FileInfo(sourcePath).Length ||
                    !TryReceiptLong(source, "mtime_ns", out long mtimeNs) ||
                    mtimeNs != FileMtimeNanoseconds(sourcePath))
                    return false;
                return true;
            }
            catch
            {
                return false;
            }
        }

        private static bool ReferenceGroupsMatch(
            IDictionary<string, object> receipt)
        {
            if (receipt == null || !receipt.TryGetValue("groups", out object raw) ||
                !(raw is IList groups) || groups.Count != 6)
                return false;
            string[] properties =
            {
                "grapeseed", "yacht", "davis", "harmony", "paleto",
                "garment_factory",
            };
            string[] groupNames =
            {
                "ALLIN1_MAP_GRAPESEED", "ALLIN1_MAP_YACHT",
                "ALLIN1_MAP_DAVIS", "ALLIN1_MAP_HARMONY",
                "ALLIN1_MAP_PALETO", "ALLIN1_MAP_GARMENT_FACTORY",
            };
            string[][] routes =
            {
                new[] { "mpheist|MPHEIST_GTA5_CITYE_HOLLYWOOD_01" },
                new[]
                {
                    "mpheist|MPHEIST_PRE_MAP_CHANGES",
                    "mpheist|MPHEIST_GTA5_LODLIGHTS",
                    "mpheist|MPHEIST_GTA5_HILLS_CITYHILLS_01",
                },
                new[] { "mptuner|MPTUNER_MAP_UPDATE" },
                new[] { "mpbattle|MPBATTLE_INTERIOR_ADDITIONS" },
                new[] { "mpvinewood|mpVinewood_INTERIOR_ADDITIONS" },
                new[] { "mp2024_02|MP2024_02_MAP_UPDATE" },
            };
            int referenceCount = 0;
            for (int index = 0; index < groups.Count; index++)
            {
                if (!(groups[index] is IDictionary<string, object> item) ||
                    !ReceiptEquals(item, "property", properties[index]) ||
                    !ReceiptEquals(item, "group", groupNames[index]) ||
                    !item.TryGetValue("references", out object refs) ||
                    !(refs is IList referenceItems) ||
                    referenceItems.Count <= 0 ||
                    !ReferenceRoutesMatch(item, routes[index]))
                    return false;
                foreach (object reference in referenceItems)
                {
                    string value = Convert.ToString(reference)?.Trim();
                    if (string.IsNullOrEmpty(value) ||
                        !value.Contains(":/%PLATFORM%/") ||
                        value.StartsWith("dlc_allin1_maps:",
                            StringComparison.OrdinalIgnoreCase))
                        return false;
                    referenceCount++;
                }
            }
            return referenceCount == 17;
        }

        private static bool ReferenceRoutesMatch(
            IDictionary<string, object> item, string[] expected)
        {
            if (item == null || expected == null ||
                !item.TryGetValue("routes", out object raw) ||
                !(raw is IList routes) || routes.Count != expected.Length)
                return false;
            for (int index = 0; index < expected.Length; index++)
            {
                if (!(routes[index] is IDictionary<string, object> route))
                    return false;
                string actual = ReceiptValue(route, "pack") + "|" +
                    ReceiptValue(route, "changeset");
                if (!string.Equals(actual, expected[index],
                        StringComparison.OrdinalIgnoreCase))
                    return false;
            }
            return true;
        }

        internal static bool AreReferenceSourcesCurrent(
            string receiptJson, string gameRoot)
        {
            if (string.IsNullOrWhiteSpace(receiptJson) ||
                string.IsNullOrWhiteSpace(gameRoot)) return false;
            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt =
                    serializer.Deserialize<Dictionary<string, object>>(
                        receiptJson);
                if (receipt == null ||
                    !receipt.TryGetValue("source_archives", out object raw) ||
                    !(raw is IList sources) || sources.Count != 6)
                    return false;

                var expected = new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase)
                {
                    "mpheist|dlc.rpf",
                    "mptuner|dlc.rpf",
                    "mpbattle|dlc.rpf",
                    "mpbattle|dlc1.rpf",
                    "mpvinewood|dlc.rpf",
                    "mp2024_02|dlc.rpf",
                };
                foreach (object rawSource in sources)
                {
                    if (!(rawSource is IDictionary<string, object> source))
                        return false;
                    string pack = ReceiptValue(source, "pack");
                    string archive = ReceiptValue(source, "archive");
                    string key = pack + "|" + archive;
                    if (!expected.Remove(key)) return false;
                    string relative = Path.Combine(
                        "update", "x64", "dlcpacks", pack, archive);
                    string modsPath = Path.Combine(gameRoot, "mods", relative);
                    string stockPath = Path.Combine(gameRoot, relative);
                    bool usesMods = File.Exists(modsPath);
                    string effectivePath = usesMods ? modsPath : stockPath;
                    if (!File.Exists(effectivePath) ||
                        !ReceiptEquals(source, "source",
                            usesMods ? "mods" : "stock") ||
                        !ReceiptEquals(source, "path",
                            (usesMods ? "mods/" : string.Empty) +
                            relative.Replace('\\', '/')) ||
                        !TryReceiptLong(source, "size", out long size) ||
                        size != new FileInfo(effectivePath).Length ||
                        !TryReceiptLong(source, "mtime_ns", out long mtimeNs) ||
                        mtimeNs != FileMtimeNanoseconds(effectivePath))
                        return false;
                }
                return expected.Count == 0;
            }
            catch
            {
                return false;
            }
        }

        private static long FileMtimeNanoseconds(string path)
        {
            var epoch = new DateTime(
                1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);
            return checked((File.GetLastWriteTimeUtc(path) - epoch).Ticks * 100L);
        }

        /// <summary>
        /// Validate the small installer receipt without hashing the 163 MiB
        /// map archive on the game thread. The installer verifies the archive
        /// and the full gameconfig before writing this receipt last; runtime
        /// activation requires the independent marker and receipt to agree.
        /// </summary>
        internal static bool IsVerifiedStartupReceipt(
            string marker, string receiptJson, long archiveBytes,
            string expectedEdition)
        {
            // Startup-registered map archives are quarantined after the live
            // Davis canary crash. A formerly valid receipt is diagnostic
            // evidence only and cannot make the layout runtime-usable.
            if (StartupRegisteredIplRuntimeRetired) return false;
            if (archiveBytes <= 0 ||
                ClassifyMarker(marker) !=
                    StandaloneMapPackLayout.StartupRegisteredIpl ||
                string.IsNullOrWhiteSpace(receiptJson))
                return false;

            Dictionary<string, string> markerFields = ParseMarker(marker);
            if (!MarkerEquals(markerFields, "archive_registration", "startup") ||
                !MarkerEquals(markerFields, "activation",
                    "verified-startup-registration") ||
                !MarkerEquals(markerFields, "receipt", RuntimeReceipt) ||
                !TryPositiveLong(markerFields, "archive_bytes",
                    out long markerBytes) || markerBytes != archiveBytes ||
                !TryPositiveLong(markerFields, "asset_count", out long assetCount))
                return false;

            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt =
                    serializer.Deserialize<Dictionary<string, object>>(
                        receiptJson);
                if (receipt == null ||
                    !ReceiptEquals(receipt, "status", "verified") ||
                    !ReceiptEquals(receipt, "layout", StartupLayout) ||
                    !ReceiptEquals(receipt, "edition", expectedEdition) ||
                    !ReceiptEquals(receipt, "gameconfig_entry",
                        "common/data/gameconfig.xml") ||
                    !TryReceiptLong(receipt, "schema", out long schema) ||
                    schema != 1 ||
                    !TryReceiptLong(receipt, "archive_bytes",
                        out long receiptBytes) || receiptBytes != archiveBytes ||
                    !TryReceiptLong(receipt, "asset_count",
                        out long receiptAssets) || receiptAssets != assetCount)
                    return false;

                string markerArchiveHash = MarkerValue(
                    markerFields, "archive_sha256");
                string markerConfigHash = MarkerValue(
                    markerFields, "gameconfig_sha256");
                string receiptArchiveHash = ReceiptValue(
                    receipt, "archive_sha256");
                string receiptConfigHash = ReceiptValue(
                    receipt, "gameconfig_sha256");
                return IsSha256(markerArchiveHash) &&
                    IsSha256(markerConfigHash) &&
                    string.Equals(markerArchiveHash, receiptArchiveHash,
                        StringComparison.OrdinalIgnoreCase) &&
                    string.Equals(markerConfigHash, receiptConfigHash,
                        StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return false;
            }
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

        private static string MarkerValue(
            IDictionary<string, string> fields, string key) =>
            fields != null && fields.TryGetValue(key, out string value)
                ? value?.Trim() : null;

        private static bool MarkerEquals(
            IDictionary<string, string> fields, string key, string expected) =>
            string.Equals(MarkerValue(fields, key), expected,
                StringComparison.OrdinalIgnoreCase);

        private static bool TryPositiveLong(
            IDictionary<string, string> fields, string key, out long value) =>
            long.TryParse(MarkerValue(fields, key), out value) && value > 0;

        private static string ReceiptValue(
            IDictionary<string, object> receipt, string key)
        {
            if (receipt == null || !receipt.TryGetValue(key, out object value) ||
                value == null) return null;
            return Convert.ToString(value)?.Trim();
        }

        private static bool ReceiptEquals(
            IDictionary<string, object> receipt, string key,
            string expected) => string.Equals(ReceiptValue(receipt, key),
                expected, StringComparison.OrdinalIgnoreCase);

        private static bool TryReceiptStringSet(
            IDictionary<string, object> receipt, string key,
            out HashSet<string> values)
        {
            values = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (receipt == null || !receipt.TryGetValue(key, out object raw) ||
                !(raw is IList items)) return false;
            foreach (object item in items)
            {
                string value = Convert.ToString(item)?.Trim();
                if (string.IsNullOrEmpty(value)) return false;
                values.Add(value);
            }
            return true;
        }

        private static bool ReceiptStringListEquals(
            IDictionary<string, object> receipt, string key,
            params string[] expected)
        {
            if (receipt == null || expected == null ||
                !receipt.TryGetValue(key, out object raw) ||
                !(raw is IList items) || items.Count != expected.Length)
                return false;
            for (int index = 0; index < expected.Length; index++)
            {
                string actual = Convert.ToString(items[index])?.Trim();
                if (!string.Equals(actual, expected[index],
                        StringComparison.OrdinalIgnoreCase))
                    return false;
            }
            return true;
        }

        private static bool ReceiptBooleanEquals(
            IDictionary<string, object> receipt, string key, bool expected) =>
            receipt != null && receipt.TryGetValue(key, out object raw) &&
            raw is bool actual && actual == expected;

        private static bool TryReceiptLong(
            IDictionary<string, object> receipt, string key, out long value) =>
            long.TryParse(ReceiptValue(receipt, key), out value);

        private static bool IsSha256(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || value.Length != 64)
                return false;
            foreach (char character in value)
            {
                bool digit = character >= '0' && character <= '9';
                bool lower = character >= 'a' && character <= 'f';
                bool upper = character >= 'A' && character <= 'F';
                if (!digit && !lower && !upper) return false;
            }
            return true;
        }

        private static bool TryGetPackRoot(out string packRoot)
        {
            packRoot = null;
            try
            {
                string scripts = AppDomain.CurrentDomain.BaseDirectory
                    .TrimEnd(Path.DirectorySeparatorChar,
                        Path.AltDirectorySeparatorChar);
                string gameRoot = Directory.GetParent(scripts)?.FullName;
                if (string.IsNullOrEmpty(gameRoot)) return false;
                packRoot = Path.Combine(
                    gameRoot, "mods", "update", "x64", "dlcpacks",
                    PackName);
                return true;
            }
            catch
            {
                return false;
            }
        }
    }
}
