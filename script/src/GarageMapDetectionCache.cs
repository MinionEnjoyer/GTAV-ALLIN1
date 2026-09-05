// GarageMapDetectionCache.cs -- fail-closed consumer for the launcher's
// verified official-map discovery cache.
//
// The launcher performs the expensive RPF inspection before GTA starts and
// writes one small receipt-bearing cache. The game-side runtime never scans an
// RPF. It verifies the exact payload, edition, descriptor text, project
// identity, and complete one-to-one IPL mapping before changing an in-memory
// descriptor. Any missing, stale, partial, or malformed cache leaves the
// bundled descriptor untouched.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace ALLIN1
{
    internal sealed class GarageMapDetectionApplyResult
    {
        internal bool Considered { get; set; }
        internal bool Applied { get; set; }
        internal string Status { get; set; } = string.Empty;
        internal string Reason { get; set; } = string.Empty;
        internal int MappingCount { get; set; }
        internal int ChangedOccurrences { get; set; }
    }

    internal sealed class GarageMapDetectionCache
    {
        internal const int SchemaVersion = 1;
        internal const string Producer = "allin1-launcher";
        internal const int MaximumEnvelopeBytes = 1024 * 1024;
        private const int MaximumProjects = 32;
        private const int MaximumMappingsPerProject = 256;
        private const int MaximumMappingsTotal = 1024;
        private const long MaximumSourceBytes = 64L * 1024L * 1024L * 1024L;
        private const long UnixEpochTicks = 621355968000000000L;

        private static readonly UTF8Encoding StrictUtf8 =
            new UTF8Encoding(false, true);
        private static readonly Regex SafeId = new Regex(
            "^[a-z0-9][a-z0-9._-]{1,63}$", RegexOptions.CultureInvariant);
        private static readonly Regex SafePackName = new Regex(
            "^[a-z0-9][a-z0-9_-]{0,63}$", RegexOptions.CultureInvariant);
        private static readonly Regex SafeNativeName = new Regex(
            "^[A-Za-z0-9_:.@-]{1,96}$", RegexOptions.CultureInvariant);
        private static readonly Regex SafeRelativePathCharacters = new Regex(
            "^[A-Za-z0-9_@+./ -]{1,512}$", RegexOptions.CultureInvariant);
        private static readonly Regex LowerSha256 = new Regex(
            "^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
        private static readonly Regex PackArchiveName = new Regex(
            "^dlc(?:[1-9][0-9]*)?\\.rpf$",
            RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

        private readonly Dictionary<string, DetectedProject> _projects;

        private GarageMapDetectionCache(
            string edition, string sourceIdentityFingerprint,
            Dictionary<string, DetectedProject> projects)
        {
            Edition = edition;
            SourceIdentityFingerprint = sourceIdentityFingerprint;
            _projects = projects;
        }

        internal string Edition { get; }
        internal string SourceIdentityFingerprint { get; }
        internal int ProjectCount => _projects.Count;

        internal bool ContainsProject(string projectId)
        {
            return _projects.ContainsKey(projectId ?? string.Empty);
        }

        internal bool SourcesAreCurrent(string gameRoot, out string reason)
        {
            reason = "source_current";
            try
            {
                if (string.IsNullOrWhiteSpace(gameRoot) ||
                    !Directory.Exists(gameRoot))
                {
                    reason = "source_game_root";
                    return false;
                }
                foreach (DetectedProject project in _projects.Values)
                {
                    if (!TryMeasurePackSource(
                            gameRoot, project.PackName,
                            out long size, out long mtimeNs, out reason))
                        return false;
                    if (size != project.SourceSize)
                    {
                        reason = "source_size_mismatch";
                        return false;
                    }
                    if (mtimeNs != project.SourceMtimeNs)
                    {
                        reason = "source_mtime_mismatch";
                        return false;
                    }
                }
                return true;
            }
            catch (Exception ex) when (
                ex is IOException || ex is UnauthorizedAccessException ||
                ex is ArgumentException || ex is NotSupportedException ||
                ex is SecurityException || ex is OverflowException)
            {
                reason = "source_io";
                return false;
            }
        }

        internal static bool TryParse(
            string envelopeJson, string runtimeEdition,
            out GarageMapDetectionCache cache, out string reason)
        {
            cache = null;
            reason = "invalid";
            try
            {
                if (!IsEdition(runtimeEdition))
                    throw new InvalidDataException("runtime_edition");
                if (string.IsNullOrEmpty(envelopeJson) ||
                    StrictUtf8.GetByteCount(envelopeJson) > MaximumEnvelopeBytes)
                    throw new InvalidDataException("envelope_size");

                Dictionary<string, object> envelope = Object(
                    PortableJsonParser.Parse(
                        envelopeJson, MaximumEnvelopeBytes), "envelope");
                ExactFields(envelope, "envelope", new[]
                {
                    "schema_version", "producer", "payload_sha256",
                    "payload_json",
                });
                if (Integer(envelope, "schema_version") != SchemaVersion)
                    throw new InvalidDataException("envelope_schema");
                if (!string.Equals(Text(envelope, "producer"), Producer,
                        StringComparison.Ordinal))
                    throw new InvalidDataException("envelope_producer");
                string claimedDigest = Text(envelope, "payload_sha256");
                if (!LowerSha256.IsMatch(claimedDigest))
                    throw new InvalidDataException("payload_digest_format");
                string payloadJson = Text(envelope, "payload_json");
                if (StrictUtf8.GetByteCount(payloadJson) > MaximumEnvelopeBytes ||
                    !string.Equals(HashUtf8(payloadJson), claimedDigest,
                        StringComparison.Ordinal))
                    throw new InvalidDataException("payload_digest");

                Dictionary<string, object> payload = Object(
                    PortableJsonParser.Parse(
                        payloadJson, MaximumEnvelopeBytes), "payload");
                ExactFields(payload, "payload", new[]
                {
                    "schema_version", "edition",
                    "source_identity_fingerprint", "projects",
                });
                if (Integer(payload, "schema_version") != SchemaVersion)
                    throw new InvalidDataException("payload_schema");
                string edition = Text(payload, "edition");
                if (!IsEdition(edition) || !string.Equals(
                        edition, runtimeEdition,
                        StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("payload_edition");
                edition = edition.ToLowerInvariant();
                string fingerprint = Text(
                    payload, "source_identity_fingerprint");
                if (!LowerSha256.IsMatch(fingerprint))
                    throw new InvalidDataException("source_identity_fingerprint");

                object[] projectValues = Array(payload, "projects");
                if (projectValues.Length > MaximumProjects)
                    throw new InvalidDataException("project_count");
                var projects = new Dictionary<string, DetectedProject>(
                    StringComparer.OrdinalIgnoreCase);
                int totalMappings = 0;
                foreach (object projectValue in projectValues)
                {
                    DetectedProject project = ParseProject(projectValue);
                    totalMappings += project.Mappings.Length;
                    if (totalMappings > MaximumMappingsTotal)
                        throw new InvalidDataException("mapping_count_total");
                    if (projects.ContainsKey(project.Id))
                        throw new InvalidDataException("duplicate_project");
                    projects.Add(project.Id, project);
                }

                cache = new GarageMapDetectionCache(
                    edition, fingerprint, projects);
                reason = "valid";
                return true;
            }
            catch (Exception ex) when (
                ex is InvalidDataException || ex is ArgumentException ||
                ex is EncoderFallbackException || ex is CryptographicException)
            {
                reason = ex is InvalidDataException &&
                    !string.IsNullOrWhiteSpace(ex.Message)
                    ? ex.Message : "invalid";
                cache = null;
                return false;
            }
        }

        internal bool TryApplyVerifiedMappings(
            string descriptorJson, MapProjectDefinition project,
            out GarageMapDetectionApplyResult result)
        {
            result = new GarageMapDetectionApplyResult();
            if (project == null || string.IsNullOrWhiteSpace(project.Id))
            {
                result.Reason = "project_missing";
                return false;
            }
            if (!_projects.TryGetValue(project.Id, out DetectedProject detected))
            {
                result.Reason = "cache_project_missing";
                return false;
            }
            result.Considered = true;
            result.Status = detected.Status;
            result.MappingCount = detected.Mappings.Length;
            if (!string.Equals(detected.Status, "verified",
                    StringComparison.Ordinal))
            {
                result.Reason = "project_" + detected.Status;
                return false;
            }
            if (!string.Equals(detected.PackName,
                    project.Streaming?.PackName ?? string.Empty,
                    StringComparison.OrdinalIgnoreCase))
            {
                result.Reason = "pack_name_mismatch";
                return false;
            }
            if (!(project.Editions ?? System.Array.Empty<string>()).Contains(
                    Edition, StringComparer.OrdinalIgnoreCase))
            {
                result.Reason = "project_edition_mismatch";
                return false;
            }

            string descriptorDigest;
            try { descriptorDigest = HashUtf8(descriptorJson ?? string.Empty); }
            catch (Exception)
            {
                result.Reason = "descriptor_encoding";
                return false;
            }
            if (!string.Equals(descriptorDigest, detected.DescriptorSha256,
                    StringComparison.Ordinal))
            {
                result.Reason = "descriptor_digest_mismatch";
                return false;
            }

            string[] required = project.RequiredIpls;
            if (required.Length == 0)
            {
                result.Reason = "verified_project_has_no_ipls";
                return false;
            }
            if (required.Length > MaximumMappingsPerProject ||
                detected.Mappings.Length != required.Length)
            {
                result.Reason = "mapping_coverage";
                return false;
            }

            var requiredSet = new HashSet<string>(
                required, StringComparer.OrdinalIgnoreCase);
            var replacements = new Dictionary<string, string>(
                StringComparer.OrdinalIgnoreCase);
            var resolvedNames = new HashSet<string>(
                StringComparer.OrdinalIgnoreCase);
            foreach (DetectedMapping mapping in detected.Mappings)
            {
                if (!requiredSet.Contains(mapping.Requested) ||
                    replacements.ContainsKey(mapping.Requested))
                {
                    result.Reason = "mapping_requested_mismatch";
                    return false;
                }
                if (string.Equals(mapping.Match, "exact",
                        StringComparison.Ordinal) &&
                    !string.Equals(mapping.Requested, mapping.Resolved,
                        StringComparison.OrdinalIgnoreCase))
                {
                    result.Reason = "exact_mapping_changed_name";
                    return false;
                }
                if (!resolvedNames.Add(mapping.Resolved))
                {
                    result.Reason = "mapping_resolved_duplicate";
                    return false;
                }
                replacements.Add(mapping.Requested, mapping.Resolved);
            }
            if (replacements.Count != requiredSet.Count ||
                requiredSet.Any(value => !replacements.ContainsKey(value)))
            {
                result.Reason = "mapping_coverage";
                return false;
            }

            int changed = Replace(
                project.Streaming?.Ipls, replacements);
            foreach (MapLevelDefinition level in
                project.Levels ?? System.Array.Empty<MapLevelDefinition>())
                changed += Replace(level?.Ipls, replacements);
            result.Applied = true;
            result.Reason = "applied";
            result.ChangedOccurrences = changed;
            return true;
        }

        internal static string HashUtf8(string value)
        {
            byte[] bytes = StrictUtf8.GetBytes(value ?? string.Empty);
            using (SHA256 sha = SHA256.Create())
                return string.Concat(sha.ComputeHash(bytes).Select(
                    item => item.ToString("x2", CultureInfo.InvariantCulture)));
        }

        private static DetectedProject ParseProject(object value)
        {
            Dictionary<string, object> project = Object(value, "project");
            ExactFields(project, "project", new[]
            {
                "id", "descriptor_sha256", "pack_name", "status", "source",
                "ipl_mappings",
            });
            string id = Text(project, "id");
            if (!SafeId.IsMatch(id))
                throw new InvalidDataException("project_id");
            string descriptorDigest = Text(project, "descriptor_sha256");
            if (!LowerSha256.IsMatch(descriptorDigest))
                throw new InvalidDataException("descriptor_digest_format");
            string packName = Text(project, "pack_name");
            if (!SafePackName.IsMatch(packName))
                throw new InvalidDataException("pack_name");
            string status = Text(project, "status");
            if (status != "verified" && status != "unresolved" &&
                status != "not_applicable")
                throw new InvalidDataException("project_status");

            Dictionary<string, object> source = Object(
                Required(project, "source"), "project.source");
            ExactFields(source, "project.source", new[]
            {
                "archive_path", "size", "mtime_ns",
            });
            string sourceArchivePath = Text(source, "archive_path");
            string expectedSourcePath = "update/x64/dlcpacks/" +
                packName + "/dlc.rpf";
            if (!IsSafeRelativePath(sourceArchivePath) || !string.Equals(
                    sourceArchivePath, expectedSourcePath,
                    StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("source_archive_path");
            long sourceSize = LongInteger(source, "size");
            long sourceMtime = LongInteger(source, "mtime_ns");
            if (sourceSize < 0 || sourceSize > MaximumSourceBytes ||
                sourceMtime < 0)
                throw new InvalidDataException("source_metadata");

            object[] values = Array(project, "ipl_mappings");
            if (values.Length > MaximumMappingsPerProject)
                throw new InvalidDataException("mapping_count");
            var mappings = new List<DetectedMapping>();
            var requestedNames = new HashSet<string>(
                StringComparer.OrdinalIgnoreCase);
            var resolvedNames = new HashSet<string>(
                StringComparer.OrdinalIgnoreCase);
            foreach (object mappingValue in values)
            {
                Dictionary<string, object> mapping = Object(
                    mappingValue, "mapping");
                ExactFields(mapping, "mapping",
                    mapping.ContainsKey("source_rpf")
                        ? new[]
                        {
                            "requested", "resolved", "match",
                            "archive_path", "entry_path", "source_rpf",
                        }
                        : new[]
                        {
                            "requested", "resolved", "match",
                            "archive_path", "entry_path",
                        });
                string requested = Text(mapping, "requested");
                string resolved = Text(mapping, "resolved");
                string match = Text(mapping, "match");
                if (!SafeNativeName.IsMatch(requested) ||
                    !SafeNativeName.IsMatch(resolved))
                    throw new InvalidDataException("mapping_native_name");
                if (match != "exact" && match != "semantic_unique")
                    throw new InvalidDataException("mapping_match");
                string archivePath = Text(mapping, "archive_path");
                string entryPath = Text(mapping, "entry_path");
                if (!IsSafeVirtualArchivePath(archivePath) ||
                    !IsSafeRelativePath(entryPath))
                    throw new InvalidDataException("mapping_path");
                if (mapping.ContainsKey("source_rpf") &&
                    !IsSafeRelativePath(Text(mapping, "source_rpf")))
                    throw new InvalidDataException("mapping_source_rpf");
                if (!requestedNames.Add(requested))
                    throw new InvalidDataException(
                        "mapping_requested_duplicate");
                if (!resolvedNames.Add(resolved))
                    throw new InvalidDataException(
                        "mapping_resolved_duplicate");
                mappings.Add(new DetectedMapping
                {
                    Requested = requested,
                    Resolved = resolved,
                    Match = match,
                });
            }
            return new DetectedProject
            {
                Id = id,
                DescriptorSha256 = descriptorDigest,
                PackName = packName,
                Status = status,
                SourceSize = sourceSize,
                SourceMtimeNs = sourceMtime,
                Mappings = mappings.ToArray(),
            };
        }

        private static bool TryMeasurePackSource(
            string gameRoot, string packName, out long size,
            out long mtimeNs, out string reason)
        {
            size = 0;
            mtimeNs = 0;
            reason = "source_current";
            if (!SafePackName.IsMatch(packName ?? string.Empty))
            {
                reason = "source_pack_name";
                return false;
            }
            string packRoot = Path.Combine(
                Path.GetFullPath(gameRoot), "update", "x64", "dlcpacks",
                packName);
            var directory = new DirectoryInfo(packRoot);
            FileInfo[] archives = directory.Exists
                ? directory.EnumerateFiles("*", SearchOption.TopDirectoryOnly)
                    .Where(file => PackArchiveName.IsMatch(file.Name))
                    .OrderBy(file => string.Equals(
                        file.Name, "dlc.rpf",
                        StringComparison.OrdinalIgnoreCase) ? 0 : 1)
                    .ThenBy(file => file.Name, StringComparer.OrdinalIgnoreCase)
                    .Take(8)
                    .ToArray()
                : System.Array.Empty<FileInfo>();
            foreach (FileInfo archive in archives)
            {
                archive.Refresh();
                size = checked(size + archive.Length);
                long ticksSinceEpoch = checked(
                    archive.LastWriteTimeUtc.Ticks - UnixEpochTicks);
                if (ticksSinceEpoch < 0)
                {
                    reason = "source_mtime";
                    return false;
                }
                long archiveMtimeNs = checked(ticksSinceEpoch * 100L);
                if (archiveMtimeNs > mtimeNs) mtimeNs = archiveMtimeNs;
            }
            return true;
        }

        private static int Replace(
            string[] values, IDictionary<string, string> replacements)
        {
            if (values == null) return 0;
            int changed = 0;
            for (int index = 0; index < values.Length; index++)
            {
                string current = values[index];
                if (!replacements.TryGetValue(
                        current ?? string.Empty, out string replacement))
                    continue;
                if (!string.Equals(current, replacement,
                        StringComparison.Ordinal))
                    changed++;
                values[index] = replacement;
            }
            return changed;
        }

        private static bool IsEdition(string value)
        {
            return string.Equals(value, "legacy", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(value, "enhanced", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsSafeRelativePath(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || value != value.Trim() ||
                value.IndexOf('\\') >= 0 || value.StartsWith("/",
                    StringComparison.Ordinal) || Path.IsPathRooted(value) ||
                !SafeRelativePathCharacters.IsMatch(value))
                return false;
            string[] parts = value.Split('/');
            return parts.Length > 0 && parts.All(part =>
                !string.IsNullOrWhiteSpace(part) && part == part.Trim() &&
                part != "." && part != "..");
        }

        private static bool IsSafeVirtualArchivePath(string value)
        {
            if (string.IsNullOrEmpty(value) || value.Length > 512)
                return false;
            string[] archives = value.Split('!');
            return archives.Length > 0 && archives.All(
                IsSafeRelativePath);
        }

        private static Dictionary<string, object> Object(
            object value, string path)
        {
            if (value is Dictionary<string, object> map) return map;
            throw new InvalidDataException(path + "_object");
        }

        private static object[] Array(
            IDictionary<string, object> map, string key)
        {
            object value = Required(map, key);
            if (value is object[] values) return values;
            throw new InvalidDataException(key + "_array");
        }

        private static object Required(
            IDictionary<string, object> map, string key)
        {
            if (!map.TryGetValue(key, out object value) || value == null)
                throw new InvalidDataException(key + "_required");
            return value;
        }

        private static string Text(
            IDictionary<string, object> map, string key)
        {
            if (!(Required(map, key) is string value) ||
                string.IsNullOrWhiteSpace(value) || value != value.Trim())
                throw new InvalidDataException(key + "_text");
            return value;
        }

        private static int Integer(
            IDictionary<string, object> map, string key)
        {
            object value = Required(map, key);
            if (value is int integer) return integer;
            throw new InvalidDataException(key + "_integer");
        }

        private static long LongInteger(
            IDictionary<string, object> map, string key)
        {
            object value = Required(map, key);
            if (value is int integer) return integer;
            if (value is long longInteger) return longInteger;
            throw new InvalidDataException(key + "_integer");
        }

        private static void ExactFields(
            IDictionary<string, object> map, string path,
            IEnumerable<string> fields)
        {
            var expected = new HashSet<string>(fields, StringComparer.Ordinal);
            if (map.Count != expected.Count ||
                expected.Any(field => !map.ContainsKey(field)))
                throw new InvalidDataException(path + "_fields");
        }

        private sealed class DetectedProject
        {
            internal string Id;
            internal string DescriptorSha256;
            internal string PackName;
            internal string Status;
            internal long SourceSize;
            internal long SourceMtimeNs;
            internal DetectedMapping[] Mappings;
        }

        private sealed class DetectedMapping
        {
            internal string Requested;
            internal string Resolved;
            internal string Match;
        }
    }

    internal static class GarageMapDetectionCacheRuntime
    {
        private const string SnapshotEntryId = "garage-map-runtime";
        private const string RelativeDiskPath =
            "ALLIN1/Maps/runtime-detected.json";
        private static readonly UTF8Encoding StrictUtf8 =
            new UTF8Encoding(false, true);

        internal static bool TryLoadCurrent(
            string runtimeEdition, out GarageMapDetectionCache cache,
            out string source, out string reason)
        {
            cache = null;
            source = "none";
            reason = "missing";
            string json;
            if (EarlyStartupSnapshot.TryGetText(SnapshotEntryId, out json))
            {
                source = "reactor_snapshot";
            }
            else
            {
                string scripts = ResolveScriptsDirectory();
                string path = Path.Combine(
                    scripts, RelativeDiskPath.Replace(
                        '/', Path.DirectorySeparatorChar));
                if (!TryReadBoundedFile(path, out json, out reason))
                    return false;
                source = "disk";
            }
            if (!GarageMapDetectionCache.TryParse(
                    json, runtimeEdition, out cache, out reason))
                return false;
            string scriptsRoot = ResolveScriptsDirectory();
            string gameRoot = Directory.GetParent(
                Path.GetFullPath(scriptsRoot))?.FullName ?? string.Empty;
            if (!cache.SourcesAreCurrent(gameRoot, out reason))
            {
                cache = null;
                return false;
            }
            return true;
        }

        internal static bool TryReadBoundedFile(
            string path, out string json, out string reason)
        {
            json = null;
            reason = "missing";
            try
            {
                var info = new FileInfo(path ?? string.Empty);
                if (!info.Exists) return false;
                if (info.Length < 2 ||
                    info.Length > GarageMapDetectionCache.MaximumEnvelopeBytes)
                {
                    reason = "disk_size";
                    return false;
                }
                byte[] bytes = File.ReadAllBytes(info.FullName);
                if (bytes.LongLength != info.Length ||
                    bytes.LongLength > GarageMapDetectionCache.MaximumEnvelopeBytes)
                {
                    reason = "disk_changed";
                    return false;
                }
                json = StrictUtf8.GetString(bytes);
                reason = "read";
                return true;
            }
            catch (DecoderFallbackException)
            {
                reason = "disk_encoding";
                return false;
            }
            catch (IOException)
            {
                reason = "disk_io";
                return false;
            }
            catch (UnauthorizedAccessException)
            {
                reason = "disk_access";
                return false;
            }
            catch (ArgumentException)
            {
                reason = "disk_path";
                return false;
            }
            catch (NotSupportedException)
            {
                reason = "disk_path";
                return false;
            }
        }

        internal static string DetectRuntimeEdition()
        {
            try
            {
                string executable = Process.GetCurrentProcess()
                    .MainModule?.FileName ?? string.Empty;
                string name = Path.GetFileName(executable);
                if (name.IndexOf("Enhanced",
                        StringComparison.OrdinalIgnoreCase) >= 0)
                    return "enhanced";
                if (string.Equals(name, "GTA5.exe",
                        StringComparison.OrdinalIgnoreCase))
                    return "legacy";
            }
            catch (Exception) { }

            try
            {
                string scripts = ResolveScriptsDirectory();
                DirectoryInfo parent = Directory.GetParent(scripts);
                string root = parent?.FullName ?? string.Empty;
                if (File.Exists(Path.Combine(root, "GTA5_Enhanced.exe")))
                    return "enhanced";
                if (File.Exists(Path.Combine(root, "GTA5.exe")))
                    return "legacy";
            }
            catch (Exception) { }
            return "legacy";
        }

        private static string ResolveScriptsDirectory()
        {
            string source = Allin1ExtensionApi.ResolveAssemblySourcePath(
                typeof(GarageMapDetectionCacheRuntime).Assembly);
            return Allin1ExtensionApi.ResolveScriptsDirectory(
                source, AppDomain.CurrentDomain.BaseDirectory);
        }
    }
}
