using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GarageMapDetectionCacheTests
    {
        [Fact]
        public void Verified_semantic_mapping_replaces_streaming_and_level_ipls()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string resolved = requested.Replace(
                "tuner_mod_garage", "tuner_mod_garage_updated");
            string envelope = Envelope(descriptor, project, "verified",
                new[] { Mapping(requested, resolved, "semantic_unique",
                    "update/x64/dlcpacks/mptuner/dlc1.rpf") });

            Assert.True(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out GarageMapDetectionCache cache,
                out string reason), reason);
            Assert.True(cache.TryApplyVerifiedMappings(
                descriptor, project,
                out GarageMapDetectionApplyResult result), result.Reason);

            Assert.Equal(2, result.ChangedOccurrences);
            Assert.Equal(resolved, Assert.Single(project.Streaming.Ipls));
            Assert.Equal(resolved, Assert.Single(project.Levels[0].Ipls));
            Assert.Equal(resolved, Assert.Single(project.RequiredIpls));
        }

        [Fact]
        public void Exact_mapping_must_not_disguise_a_renamed_ipl()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string envelope = Envelope(descriptor, project, "verified",
                new[] { Mapping(requested, requested + "changed", "exact") });
            Assert.True(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out GarageMapDetectionCache cache,
                out string reason), reason);

            Assert.False(cache.TryApplyVerifiedMappings(
                descriptor, project,
                out GarageMapDetectionApplyResult result));
            Assert.Equal("exact_mapping_changed_name", result.Reason);
            Assert.Equal(requested, Assert.Single(project.RequiredIpls));
        }

        [Fact]
        public void Tampered_payload_is_rejected_without_touching_descriptor()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string envelope = Envelope(descriptor, project, "verified",
                new[] { Mapping(requested, requested, "exact") });
            envelope = envelope.Replace(
                "\"payload_sha256\":\"", "\"payload_sha256\":\"0");

            Assert.False(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out _, out string reason));
            Assert.Equal("payload_digest_format", reason);
            Assert.Equal(requested, Assert.Single(project.RequiredIpls));
        }

        [Fact]
        public void Cache_for_the_other_edition_is_rejected()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string envelope = Envelope(descriptor, project, "verified",
                new[] { Mapping(requested, requested, "exact") }, "legacy");

            Assert.False(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out _, out string reason));
            Assert.Equal("payload_edition", reason);
        }

        [Fact]
        public void Descriptor_digest_mismatch_retains_bundled_ipls()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string envelope = Envelope(descriptor + " ", project, "verified",
                new[] { Mapping(requested, requested + "_new", "semantic_unique") });
            Assert.True(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out GarageMapDetectionCache cache,
                out string reason), reason);

            Assert.False(cache.TryApplyVerifiedMappings(
                descriptor, project,
                out GarageMapDetectionApplyResult result));
            Assert.Equal("descriptor_digest_mismatch", result.Reason);
            Assert.Equal(requested, Assert.Single(project.RequiredIpls));
        }

        [Fact]
        public void Verified_project_requires_complete_one_to_one_coverage()
        {
            string descriptor = Descriptor("garment-factory.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string[] requested = project.RequiredIpls;
            Assert.True(requested.Length > 1);
            string envelope = Envelope(descriptor, project, "verified",
                new[] { Mapping(requested[0], requested[0], "exact") });
            Assert.True(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out GarageMapDetectionCache cache,
                out string reason), reason);

            Assert.False(cache.TryApplyVerifiedMappings(
                descriptor, project,
                out GarageMapDetectionApplyResult result));
            Assert.Equal("mapping_coverage", result.Reason);
            Assert.Equal(requested, project.RequiredIpls);
        }

        [Fact]
        public void Duplicate_resolved_names_reject_the_cache_contract()
        {
            string descriptor = Descriptor("garment-factory.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string[] requested = project.RequiredIpls;
            Assert.True(requested.Length > 1);
            string envelope = Envelope(descriptor, project, "verified",
                new[]
                {
                    Mapping(requested[0], "shared_native_map", "semantic_unique"),
                    Mapping(requested[1], "shared_native_map", "semantic_unique"),
                });

            Assert.False(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out _, out string reason));
            Assert.Equal("mapping_resolved_duplicate", reason);
        }

        [Fact]
        public void Nested_virtual_archive_paths_are_accepted_safely()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string envelope = Envelope(descriptor, project, "verified",
                new[] { Mapping(requested, requested, "exact", null,
                    "x64/interiors.rpf!nested/maps.rpf") });

            Assert.True(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out _, out string reason), reason);
        }

        [Fact]
        public void More_than_1024_total_mappings_rejects_the_cache()
        {
            var projects = new List<object>();
            for (int projectIndex = 0; projectIndex < 5; projectIndex++)
            {
                int currentProject = projectIndex;
                projects.Add(new
                {
                    id = "project-" + currentProject,
                    descriptor_sha256 = new string('a', 64),
                    pack_name = "pack_" + currentProject,
                    status = "unresolved",
                    source = new
                    {
                        archive_path = "update/x64/dlcpacks/pack_" +
                            currentProject + "/dlc.rpf",
                        size = 1,
                        mtime_ns = 1,
                    },
                    ipl_mappings = Enumerable.Range(0, 256).Select(index => new
                    {
                        requested = "requested_" + currentProject + "_" + index,
                        resolved = "resolved_" + currentProject + "_" + index,
                        match = "semantic_unique",
                        archive_path = "x64/maps.rpf",
                        entry_path = "map_" + index + ".ymap",
                    }).ToArray(),
                });
            }
            string envelope = EnvelopePayload(new
            {
                schema_version = 1,
                edition = "enhanced",
                source_identity_fingerprint = new string('1', 64),
                projects = projects.ToArray(),
            });

            Assert.False(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out _, out string reason));
            Assert.Equal("mapping_count_total", reason);
        }

        [Fact]
        public void Source_archive_size_and_mtime_guard_direct_game_launches()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-map-source-" + Guid.NewGuid().ToString("N"));
            string pack = Path.Combine(root, "update", "x64", "dlcpacks",
                "mptuner");
            try
            {
                Directory.CreateDirectory(pack);
                string primary = Path.Combine(pack, "dlc.rpf");
                string split = Path.Combine(pack, "dlc1.rpf");
                File.WriteAllBytes(primary, new byte[3]);
                File.WriteAllBytes(split, new byte[4]);
                File.SetLastWriteTimeUtc(primary,
                    new DateTime(2026, 1, 2, 3, 4, 5, DateTimeKind.Utc));
                File.SetLastWriteTimeUtc(split,
                    new DateTime(2026, 1, 2, 3, 4, 6, DateTimeKind.Utc));
                long sourceSize = new FileInfo(primary).Length +
                    new FileInfo(split).Length;
                long sourceMtime = Math.Max(
                    UnixNanoseconds(primary), UnixNanoseconds(split));
                string envelope = Envelope(
                    descriptor, project, "verified",
                    new[] { Mapping(requested, requested, "exact") },
                    "enhanced", sourceSize, sourceMtime);
                Assert.True(GarageMapDetectionCache.TryParse(
                    envelope, "enhanced", out GarageMapDetectionCache cache,
                    out string parseReason), parseReason);

                Assert.True(cache.SourcesAreCurrent(root, out string reason),
                    reason);
                File.AppendAllText(split, "x");
                Assert.False(cache.SourcesAreCurrent(root, out reason));
                Assert.Equal("source_size_mismatch", reason);

                File.WriteAllBytes(split, new byte[4]);
                File.SetLastWriteTimeUtc(split,
                    new DateTime(2026, 1, 2, 3, 5, 6, DateTimeKind.Utc));
                Assert.False(cache.SourcesAreCurrent(root, out reason));
                Assert.Equal("source_mtime_mismatch", reason);
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        [Theory]
        [InlineData("unresolved")]
        [InlineData("not_applicable")]
        public void Nonverified_project_never_changes_the_descriptor(string status)
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string envelope = Envelope(descriptor, project, status,
                new[] { Mapping(requested, requested + "_new", "semantic_unique") });
            Assert.True(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out GarageMapDetectionCache cache,
                out string reason), reason);

            Assert.False(cache.TryApplyVerifiedMappings(
                descriptor, project,
                out GarageMapDetectionApplyResult result));
            Assert.Equal("project_" + status, result.Reason);
            Assert.Equal(requested, Assert.Single(project.RequiredIpls));
        }

        [Fact]
        public void Unsafe_detected_native_name_rejects_the_entire_cache()
        {
            string descriptor = Descriptor("davis.maps.json");
            MapProjectDefinition project = Parse(descriptor);
            string requested = Assert.Single(project.RequiredIpls);
            string envelope = Envelope(descriptor, project, "verified",
                new[] { Mapping(requested, "../../not_an_ipl", "semantic_unique") });

            Assert.False(GarageMapDetectionCache.TryParse(
                envelope, "enhanced", out _, out string reason));
            Assert.Equal("mapping_native_name", reason);
        }

        [Fact]
        public void Disk_fallback_enforces_the_one_megabyte_bound()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-map-cache-" + Guid.NewGuid().ToString("N"));
            string path = Path.Combine(root, "runtime-detected.json");
            try
            {
                Directory.CreateDirectory(root);
                File.WriteAllBytes(path, new byte[
                    GarageMapDetectionCache.MaximumEnvelopeBytes + 1]);

                Assert.False(GarageMapDetectionCacheRuntime.TryReadBoundedFile(
                    path, out _, out string reason));
                Assert.Equal("disk_size", reason);
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        private static MapProjectDefinition Parse(string descriptor)
        {
            Assert.True(MapProjectParser.TryParse(
                descriptor, out MapProjectDefinition project, out var errors),
                string.Join(Environment.NewLine, errors));
            return project;
        }

        private static string Descriptor(string fileName)
        {
            return File.ReadAllText(Path.Combine(
                RepositoryRoot(), "data", "maps", "allin1-online-content",
                fileName));
        }

        private static string Envelope(
            string descriptor, MapProjectDefinition project, string status,
            IEnumerable<MappingData> mappings, string edition = "enhanced",
            long sourceSize = 1024, long sourceMtime = 123456789L)
        {
            string payload = JsonConvert.SerializeObject(new
            {
                schema_version = 1,
                edition,
                source_identity_fingerprint = new string('1', 64),
                projects = new[]
                {
                    new
                    {
                        id = project.Id,
                        descriptor_sha256 =
                            GarageMapDetectionCache.HashUtf8(descriptor),
                        pack_name = project.Streaming.PackName,
                        status,
                        source = new
                        {
                            archive_path = "update/x64/dlcpacks/" +
                                project.Streaming.PackName + "/dlc.rpf",
                            size = sourceSize,
                            mtime_ns = sourceMtime,
                        },
                        ipl_mappings = mappings.ToArray(),
                    },
                },
            }, Formatting.None, new JsonSerializerSettings
            {
                NullValueHandling = NullValueHandling.Ignore,
            });
            return EnvelopePayload(JsonConvert.DeserializeObject(payload));
        }

        private static string EnvelopePayload(object payloadObject)
        {
            string payload = JsonConvert.SerializeObject(
                payloadObject, Formatting.None, new JsonSerializerSettings
                {
                    NullValueHandling = NullValueHandling.Ignore,
                });
            return JsonConvert.SerializeObject(new
            {
                schema_version = 1,
                producer = "allin1-launcher",
                payload_sha256 = GarageMapDetectionCache.HashUtf8(payload),
                payload_json = payload,
            }, Formatting.None);
        }

        private static MappingData Mapping(
            string requested, string resolved, string match,
            string sourceRpf = null, string archivePath = null)
        {
            return new MappingData
            {
                requested = requested,
                resolved = resolved,
                match = match,
                archive_path = archivePath ??
                    "x64/levels/gta5/interiors/int_placement_tr.rpf",
                entry_path = resolved + ".ymap",
                source_rpf = sourceRpf,
            };
        }

        private static long UnixNanoseconds(string path)
        {
            const long unixEpochTicks = 621355968000000000L;
            return checked((new FileInfo(path).LastWriteTimeUtc.Ticks -
                unixEpochTicks) * 100L);
        }

        private static string RepositoryRoot()
        {
            string current = AppContext.BaseDirectory;
            while (!string.IsNullOrEmpty(current))
            {
                if (Directory.Exists(Path.Combine(
                        current, "data", "maps", "allin1-online-content")))
                    return current;
                current = Directory.GetParent(current)?.FullName;
            }
            throw new DirectoryNotFoundException(
                "Could not locate the ALLIN1 repository root.");
        }

        private sealed class MappingData
        {
            public string requested { get; set; }
            public string resolved { get; set; }
            public string match { get; set; }
            public string archive_path { get; set; }
            public string entry_path { get; set; }
            public string source_rpf { get; set; }
        }
    }
}
