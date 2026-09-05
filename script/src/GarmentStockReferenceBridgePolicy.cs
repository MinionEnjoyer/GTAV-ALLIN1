using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Web.Script.Serialization;

namespace ALLIN1
{
    /// <summary>
    /// Fail-closed authorization for the property-scoped mp2024_02 bridge.
    /// The bridge is metadata only. It may be executed only by the Garment
    /// entry coordinator while the screen is verified fully black.
    /// </summary>
    internal static class GarmentStockReferenceBridgePolicy
    {
        internal const string PackName =
            "allin1_mp2024_02_garment_bridge";
        internal const string DeviceName =
            "dlc_allin1_mp2024_02_garment_bridge";
        internal const string MarkerName =
            "allin1_mp2024_02_garment_bridge.active";
        internal const string ReceiptName =
            "allin1_mp2024_02_garment_bridge.runtime.json";
        internal const string DormantGroup =
            "ALLIN1_STOCK_MP2024_02_GARMENT_V1";
        internal const string StockChangeset = "MP2024_02_MAP_UPDATE";
        internal const string RuntimeContract =
            "allin1-stock-mp2024-02-garment-black-transition-v1";
        internal static readonly string[] Ipls =
        {
            "m24_2_int_placement",
            "m24_2_int_placement_interior_int_hacker_garage_milo_",
        };

        private const int VerificationCacheMilliseconds = 5000;
        private static readonly TimedBooleanVerificationCache
            ContractCache = new TimedBooleanVerificationCache();
        private static readonly AsyncSourceArchiveAttestationCache
            NativeMutationAttestation =
                new AsyncSourceArchiveAttestationCache();

        internal static bool IsCurrentRuntimeActivationAuthorized =>
            ContractCache.GetOrVerify(
                Environment.TickCount, VerificationCacheMilliseconds,
                VerifyInstalledContract);

        internal static bool IsCurrentNativeMutationAuthorized
        {
            get
            {
                if (!TryResolveInstalledContract(
                        out SourceArchiveAttestationIdentity identity))
                    return false;
                NativeMutationAttestation.Begin(identity, VerifySourceArchive);
                return NativeMutationAttestation.IsCompletedVerified(identity);
            }
        }

        internal static void WarmUpCurrentNativeMutationAuthorization()
        {
            if (!TryResolveInstalledContract(
                    out SourceArchiveAttestationIdentity identity))
                return;
            if (NativeMutationAttestation.Begin(identity, VerifySourceArchive))
            {
                ClientLog.Info("DeferredMap",
                    "garment_native_attestation_warmup_started",
                    new Dictionary<string, object>
                    {
                        { "archive_bytes", identity.Size },
                        { "archive_mtime_ns", identity.MtimeNanoseconds },
                    });
            }
        }

        private static bool VerifyInstalledContract() =>
            TryResolveInstalledContract(
                out SourceArchiveAttestationIdentity _);

        private static bool TryResolveInstalledContract(
            out SourceArchiveAttestationIdentity identity)
        {
            identity = null;
            try
            {
                string executable = Process.GetCurrentProcess()
                    .MainModule?.FileName ?? string.Empty;
                string gameRoot = Path.GetDirectoryName(executable);
                if (string.IsNullOrWhiteSpace(gameRoot)) return false;
                string edition = Path.GetFileName(executable).IndexOf(
                        "Enhanced", StringComparison.OrdinalIgnoreCase) >= 0
                    ? "enhanced" : "legacy";
                string packRoot = Path.Combine(gameRoot, "mods", "update",
                    "x64", "dlcpacks", PackName);
                string archivePath = Path.Combine(packRoot, "dlc.rpf");
                string markerPath = Path.Combine(packRoot, MarkerName);
                string receiptPath = Path.Combine(packRoot, ReceiptName);
                if (!File.Exists(archivePath) || !File.Exists(markerPath) ||
                    !File.Exists(receiptPath)) return false;

                var archive = new FileInfo(archivePath);
                string archiveSha256 = Sha256File(archivePath);
                Dictionary<string, string> marker = ParseMarker(
                    File.ReadAllText(markerPath));
                if (!MarkerEquals(marker, "schema", "1") ||
                    !MarkerEquals(marker, "status", "verified") ||
                    !MarkerEquals(marker, "property_scope", "garment_factory") ||
                    !MarkerEquals(marker, "activation",
                        "explicit-garment-entry-black-transition") ||
                    !MarkerEquals(marker, "black_transition_required", "true") ||
                    !MarkerEquals(marker, "keep_resident", "true") ||
                    !MarkerEquals(marker, "release_on_exit", "false") ||
                    !MarkerEquals(marker, "declared_groups",
                        "GROUP_STARTUP," + DormantGroup) ||
                    !MarkerEquals(marker, "stock_changeset", StockChangeset) ||
                    !MarkerEquals(marker, "ipls", string.Join(",", Ipls)) ||
                    !MarkerEquals(marker, "receipt", ReceiptName) ||
                    !long.TryParse(Value(marker, "archive_bytes"),
                        out long markerBytes) || markerBytes != archive.Length ||
                    !FixedTimeEquals(Value(marker, "archive_sha256"),
                        archiveSha256)) return false;

                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 256 * 1024,
                };
                Dictionary<string, object> receipt = serializer.Deserialize<
                    Dictionary<string, object>>(File.ReadAllText(receiptPath));
                if (receipt == null ||
                    !ReceiptLongEquals(receipt, "schema", 1) ||
                    !ReceiptEquals(receipt, "status", "verified") ||
                    !ReceiptEquals(receipt, "package_id",
                        "allin1.online-content") ||
                    !ReceiptEquals(receipt, "pack_name", PackName) ||
                    !ReceiptEquals(receipt, "device_name", DeviceName) ||
                    !ReceiptEquals(receipt, "edition", edition) ||
                    !ReceiptEquals(receipt, "layout",
                        "stock-reference-v1-metadata-only") ||
                    !ReceiptEquals(receipt, "runtime_contract",
                        RuntimeContract) ||
                    !ReceiptLongEquals(receipt, "archive_bytes",
                        archive.Length) ||
                    !FixedTimeEquals(ReceiptValue(receipt, "archive_sha256"),
                        archiveSha256) ||
                    !ReceiptEquals(receipt, "property_scope",
                        "garment_factory") ||
                    !ReceiptEquals(receipt, "activation",
                        "explicit-garment-entry-black-transition") ||
                    !ReceiptBooleanEquals(receipt,
                        "black_transition_required", true) ||
                    !ReceiptBooleanEquals(receipt, "keep_resident", true) ||
                    !ReceiptBooleanEquals(receipt, "release_on_exit", false) ||
                    !ReceiptStringListEquals(receipt, "declared_groups",
                        "GROUP_STARTUP", DormantGroup) ||
                    !ReceiptEquals(receipt, "stock_changeset",
                        StockChangeset) ||
                    !ReceiptStringListEquals(receipt, "ipls", Ipls) ||
                    !(receipt["source_attestation"] is
                        IDictionary<string, object> source) ||
                    !ReceiptEquals(source, "pack", "mp2024_02") ||
                    !ReceiptEquals(source, "archive", "dlc.rpf") ||
                    !(ReceiptEquals(source, "source", "stock") ||
                      ReceiptEquals(source, "source", "mods")) ||
                    !ReceiptEquals(source, "device_name",
                        "dlc_mp2024_02") ||
                    !ReceiptEquals(source, "changeset_name",
                        StockChangeset) ||
                    !ReceiptBooleanEquals(source,
                        "requires_loading_screen", true) ||
                    !IsSha256(ReceiptValue(source, "changeset_sha256")) ||
                    !IsSha256(ReceiptValue(source, "archive_sha256")))
                    return false;

                string provenance = ReceiptValue(source, "source");
                string expectedRelative = string.Equals(provenance, "mods",
                        StringComparison.OrdinalIgnoreCase)
                    ? Path.Combine("mods", "update", "x64", "dlcpacks",
                        "mp2024_02", "dlc.rpf")
                    : Path.Combine("update", "x64", "dlcpacks",
                        "mp2024_02", "dlc.rpf");
                string receiptRelative = ReceiptValue(source, "path")
                    ?.Replace('/', Path.DirectorySeparatorChar);
                if (!string.Equals(receiptRelative, expectedRelative,
                        StringComparison.OrdinalIgnoreCase) ||
                    !long.TryParse(ReceiptValue(source, "size"),
                        out long expectedSize) || expectedSize <= 0 ||
                    !long.TryParse(ReceiptValue(source, "mtime_ns"),
                        out long expectedMtime) || expectedMtime <= 0)
                    return false;
                string sourcePath = Path.GetFullPath(Path.Combine(
                    gameRoot, expectedRelative));
                string safeRoot = Path.GetFullPath(gameRoot)
                    .TrimEnd(Path.DirectorySeparatorChar) +
                    Path.DirectorySeparatorChar;
                if (!sourcePath.StartsWith(safeRoot,
                        StringComparison.OrdinalIgnoreCase) ||
                    !MatchesFileIdentity(
                        sourcePath, expectedSize, expectedMtime))
                    return false;
                identity = new SourceArchiveAttestationIdentity(
                    sourcePath, expectedSize, expectedMtime,
                    ReceiptValue(source, "archive_sha256"));
                return true;
            }
            catch
            {
                identity = null;
                return false;
            }
        }

        private static bool VerifySourceArchive(
            SourceArchiveAttestationIdentity identity)
        {
            bool verified = identity != null && MatchesFileIdentity(
                identity.Path, identity.Size, identity.MtimeNanoseconds) &&
                FixedTimeEquals(Sha256File(identity.Path),
                    identity.ExpectedSha256) &&
                MatchesFileIdentity(identity.Path, identity.Size,
                    identity.MtimeNanoseconds);
            ClientLog.Info("DeferredMap", verified
                    ? "garment_native_attestation_warmup_verified"
                    : "garment_native_attestation_warmup_rejected",
                new Dictionary<string, object>
                {
                    { "archive_bytes", identity?.Size ?? 0 },
                    { "verified", verified },
                });
            return verified;
        }

        private static bool MatchesFileIdentity(
            string path, long size, long mtimeNanoseconds)
        {
            if (!File.Exists(path)) return false;
            var file = new FileInfo(path);
            const long UnixEpochTicks = 621355968000000000L;
            long actualMtime =
                (file.LastWriteTimeUtc.Ticks - UnixEpochTicks) * 100L;
            return file.Length == size && actualMtime == mtimeNanoseconds;
        }

        private static string Sha256File(string path)
        {
            using (var algorithm = SHA256.Create())
            using (var stream = new FileStream(path, FileMode.Open,
                FileAccess.Read, FileShare.Read))
                return BitConverter.ToString(algorithm.ComputeHash(stream))
                    .Replace("-", string.Empty);
        }

        private static Dictionary<string, string> ParseMarker(string text)
        {
            var result = new Dictionary<string, string>(
                StringComparer.OrdinalIgnoreCase);
            foreach (string line in (text ?? string.Empty)
                .Replace("\r", string.Empty).Split('\n'))
            {
                int separator = line.IndexOf('=');
                if (separator <= 0) continue;
                result[line.Substring(0, separator).Trim()] =
                    line.Substring(separator + 1).Trim();
            }
            return result;
        }

        private static string Value(
            IDictionary<string, string> values, string key) =>
            values.TryGetValue(key, out string value) ? value : null;

        private static bool MarkerEquals(
            IDictionary<string, string> values, string key, string expected) =>
            string.Equals(Value(values, key), expected,
                StringComparison.OrdinalIgnoreCase);

        private static string ReceiptValue(
            IDictionary<string, object> values, string key) =>
            values != null && values.TryGetValue(key, out object value)
                ? Convert.ToString(value)?.Trim() : null;

        private static bool ReceiptEquals(
            IDictionary<string, object> values, string key, string expected) =>
            string.Equals(ReceiptValue(values, key), expected,
                StringComparison.OrdinalIgnoreCase);

        private static bool ReceiptLongEquals(
            IDictionary<string, object> values, string key, long expected) =>
            long.TryParse(ReceiptValue(values, key), out long actual) &&
            actual == expected;

        private static bool ReceiptBooleanEquals(
            IDictionary<string, object> values, string key, bool expected) =>
            values != null && values.TryGetValue(key, out object value) &&
            value is bool actual && actual == expected;

        private static bool ReceiptStringListEquals(
            IDictionary<string, object> values, string key,
            params string[] expected)
        {
            if (values == null || !values.TryGetValue(key, out object raw) ||
                !(raw is IList actual) || actual.Count != expected.Length)
                return false;
            for (int index = 0; index < expected.Length; index++)
                if (!string.Equals(Convert.ToString(actual[index])?.Trim(),
                        expected[index], StringComparison.OrdinalIgnoreCase))
                    return false;
            return true;
        }

        private static bool IsSha256(string value) =>
            !string.IsNullOrWhiteSpace(value) && value.Length == 64 &&
            value.All(character =>
                (character >= '0' && character <= '9') ||
                (character >= 'a' && character <= 'f') ||
                (character >= 'A' && character <= 'F'));

        private static bool FixedTimeEquals(string left, string right)
        {
            if (!IsSha256(left) || !IsSha256(right)) return false;
            byte[] a = System.Text.Encoding.ASCII.GetBytes(
                left.ToUpperInvariant());
            byte[] b = System.Text.Encoding.ASCII.GetBytes(
                right.ToUpperInvariant());
            int difference = a.Length ^ b.Length;
            for (int index = 0; index < Math.Min(a.Length, b.Length); index++)
                difference |= a[index] ^ b[index];
            return difference == 0;
        }
    }
}
