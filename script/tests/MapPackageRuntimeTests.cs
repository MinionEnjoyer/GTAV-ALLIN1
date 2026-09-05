using System;
using System.IO;
using System.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class MapPackageRuntimeTests
    {
        [Theory]
        [InlineData(0, 250)]
        [InlineData(1, 0)]
        [InlineData(25, 0)]
        public void Generic_map_runtime_sleeps_without_custom_projects(
            int projectCount, int expectedInterval)
        {
            Assert.Equal(expectedInterval,
                MapPackageRuntime.TickIntervalForProjectCount(projectCount));
        }

        [Fact]
        public void Valid_project_preserves_portals_levels_and_garage_hooks()
        {
            Assert.True(MapProjectParser.TryParse(
                ValidJson(), out MapProjectDefinition project,
                out var errors), string.Join(Environment.NewLine, errors));

            Assert.Equal(1, project.SchemaVersion);
            Assert.Equal("acme.garage", project.PackageId);
            Assert.Equal("acme.garage:warehouse", project.LeaseKey);
            Assert.Equal(2, project.Levels.Length);
            Assert.Equal(2, project.Portals.Length);
            Assert.Single(project.Garages);
            Assert.Equal("story_save_only", project.Garages[0].Rules.SavePolicy);
            Assert.Equal(2, project.Garages[0].Slots.Length);
            Assert.Equal(new[] { "acme_collision", "acme_shell" },
                project.RequiredIpls.OrderBy(value => value).ToArray());
            Assert.Equal(315f, project.Portals[0].To.Point.Heading);
        }

        [Fact]
        public void Parser_rejects_unknown_fields_and_broken_references()
        {
            string json = ValidJson()
                .Replace("\"version\":\"1.0.0\"",
                    "\"version\":\"1.0.0\",\"typo\":true")
                .Replace("\"entrance_portal_id\":\"main\"",
                    "\"entrance_portal_id\":\"missing\"");

            Assert.False(MapProjectParser.TryParse(
                json, out _, out var errors));
            Assert.Contains(errors, value => value.Contains("unknown field"));
            Assert.Contains(errors, value => value.Contains("unknown portal"));
        }

        [Fact]
        public void Parser_normalizes_contract_identifiers_and_optional_headings()
        {
            string json = ValidJson()
                .Replace("\"package_id\":\"acme.garage\"",
                    "\"package_id\":\"Acme.Garage\"")
                .Replace("\"pack_name\":\"acme_maps\"",
                    "\"pack_name\":\"ACME_MAPS\"")
                .Replace("\"mode\":\"both\"", "\"mode\":\"BOTH\"")
                .Replace("\"save_policy\":\"story_save_only\"",
                    "\"save_policy\":\"STORY_SAVE_ONLY\"")
                .Replace("\"z\":10.0,\"heading\":45.0", "\"z\":10.0");

            Assert.True(MapProjectParser.TryParse(
                json, out MapProjectDefinition project,
                out var errors), string.Join(Environment.NewLine, errors));
            Assert.Equal("acme.garage", project.PackageId);
            Assert.Equal("acme_maps", project.Streaming.PackName);
            Assert.Equal(MapPortalMode.Both, project.Portals[0].Mode);
            Assert.Equal(0f, project.Portals[0].From.Point.Heading);
            Assert.Equal("story_save_only", project.Garages[0].Rules.SavePolicy);
        }

        [Fact]
        public void Parser_rejects_float_capacity_even_when_near_an_integer()
        {
            string json = ValidJson()
                .Replace("\"capacity\":4", "\"capacity\":4.0000001");

            Assert.False(MapProjectParser.TryParse(
                json, out _, out var errors));
            Assert.Contains(errors, value =>
                value.Contains("capacity: expected an integer"));
        }

        [Fact]
        public void Parser_rejects_unsafe_policy_and_out_of_range_radius()
        {
            string json = ValidJson()
                .Replace("\"story_save_only\"", "\"immediate\"")
                .Replace("\"radius\":2.5", "\"radius\":51.0");

            Assert.False(MapProjectParser.TryParse(
                json, out _, out var errors));
            Assert.Contains(errors, value =>
                value.Contains("only story_save_only"));
            Assert.Contains(errors, value =>
                value.Contains("expected a finite number from 0.5 to 50"));
        }

        [Fact]
        public void Parser_requires_streaming_hysteresis_between_load_and_clear()
        {
            string json = ValidJson()
                .Replace("\"release_radius\":300.0",
                    "\"release_radius\":150.0");

            Assert.False(MapProjectParser.TryParse(
                json, out _, out var errors));
            Assert.Contains(errors, value => value.Contains(
                "release_radius: must be greater than activation_radius"));
        }

        [Fact]
        public void Authorized_loader_rejects_descriptor_package_mismatch()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-map-project-" + Guid.NewGuid().ToString("N"));
            string file = Path.Combine(root, "maps.json");
            try
            {
                Directory.CreateDirectory(root);
                File.WriteAllText(file, ValidJson());
                var declaration = new MapDescriptorDeclaration(
                    "another.package",
                    "scripts/ALLIN1/Maps/another.package/maps.json", file);

                MapProjectLoadResult result =
                    MapProjectDirectoryLoader.LoadAuthorized(
                        new[] { declaration }, "enhanced");

                Assert.Empty(result.Projects);
                Assert.Contains(result.Diagnostics, value =>
                    value.Contains("does not match its receipt"));
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        [Fact]
        public void Authorized_loader_accepts_matching_current_descriptor()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-map-project-" + Guid.NewGuid().ToString("N"));
            string file = Path.Combine(root, "maps.json");
            try
            {
                Directory.CreateDirectory(root);
                File.WriteAllText(file, ValidJson());
                var declaration = new MapDescriptorDeclaration(
                    "acme.garage",
                    "scripts/ALLIN1/Maps/acme.garage/maps.json", file);

                MapProjectLoadResult result =
                    MapProjectDirectoryLoader.LoadAuthorized(
                        new[] { declaration }, "enhanced");

                Assert.Single(result.Projects);
                Assert.Empty(result.Diagnostics);
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        [Fact]
        public void Parser_rejects_content_group_only_projects_for_safe_runtime()
        {
            string json = ValidJson()
                .Replace("\"ipls\":[\"acme_shell\"]", "\"ipls\":[]")
                .Replace("\"ipls\":[\"acme_collision\"]", "\"ipls\":[]");
            Assert.False(MapProjectParser.TryParse(
                json, out _, out var errors));
            Assert.Contains(errors, value =>
                value.Contains("safe Story runtime requires"));
        }

        [Fact]
        public void Parser_accepts_a_non_streaming_project_without_ipls()
        {
            string json = ValidJson()
                .Replace("\"streaming\":{", "\"streaming\":{\"mode\":\"none\",")
                .Replace("\"content_group\":\"ACME_MAP_WAREHOUSE\"",
                    "\"content_group\":null")
                .Replace("\"ipls\":[\"acme_shell\"]", "\"ipls\":[]")
                .Replace("\"ipls\":[\"acme_collision\"]", "\"ipls\":[]");

            Assert.True(MapProjectParser.TryParse(
                json, out MapProjectDefinition project,
                out var errors), string.Join(Environment.NewLine, errors));
            Assert.Equal("none", project.Streaming.Mode);
            Assert.False(project.Streaming.RequiresLease);
            Assert.Empty(project.RequiredIpls);
        }

        [Fact]
        public void Parser_rejects_ipls_or_a_content_group_in_none_mode()
        {
            string json = ValidJson().Replace(
                "\"streaming\":{", "\"streaming\":{\"mode\":\"none\",");

            Assert.False(MapProjectParser.TryParse(
                json, out _, out var errors));
            Assert.Contains(errors, value => value.Contains(
                "mode none cannot declare content_group or IPLs"));
        }

        [Theory]
        [InlineData("davis.maps.json", "davis-auto-shop", "davis", 10)]
        [InlineData("eclipse.maps.json", "eclipse-garage", "eclipse", 10)]
        [InlineData("garment-factory.maps.json", "garment-factory-garage",
            "garment_factory", 10)]
        [InlineData("grapeseed.maps.json", "grapeseed-garage", "rural", 6)]
        [InlineData("harmony.maps.json", "harmony-garage", "three_floor", 25)]
        [InlineData("paleto.maps.json", "paleto-garage", "paleto", 10)]
        public void Official_garage_descriptors_parse_and_match_storage_contracts(
            string fileName, string projectId, string garageId, int capacity)
        {
            string descriptor = Path.Combine(RepositoryRoot(), "data", "maps",
                "allin1-online-content", fileName);
            Assert.True(File.Exists(descriptor), descriptor);

            Assert.True(MapProjectParser.TryParse(
                File.ReadAllText(descriptor), out MapProjectDefinition project,
                out var errors), string.Join(Environment.NewLine, errors));

            Assert.Equal("allin1.online-content", project.PackageId);
            Assert.Equal(projectId, project.Id);
            MapGarageDefinition garage = Assert.Single(project.Garages);
            Assert.Equal(garageId, garage.Id);
            Assert.Equal(capacity, garage.Capacity);
            Assert.Equal(capacity, garage.Slots.Length);
            Assert.Equal("story_save_only", garage.Rules.SavePolicy);
            Assert.True(OfficialGarageMapProjects.IsOfficial(project));
            if (projectId == "grapeseed-garage")
            {
                Assert.Equal(new[] { "enhanced" }, project.Editions);
                Assert.True(project.Streaming.KeepResident);
                Assert.False(OfficialGarageMapProjects
                    .TryGetIsolatedStreamingProperty(project, out _));
            }
        }

        [Fact]
        public void Official_project_classification_requires_both_package_and_id()
        {
            Assert.True(MapProjectParser.TryParse(
                File.ReadAllText(Path.Combine(RepositoryRoot(), "data", "maps",
                    "allin1-online-content", "davis.maps.json")),
                out MapProjectDefinition project, out var errors),
                string.Join(Environment.NewLine, errors));

            Assert.True(OfficialGarageMapProjects.IsOfficial(project));
            project.PackageId = "third.party";
            Assert.False(OfficialGarageMapProjects.IsOfficial(project));
            project.PackageId = OfficialGarageMapProjects.PackageId;
            project.Id = "not-an-official-garage";
            Assert.False(OfficialGarageMapProjects.IsOfficial(project));
            Assert.False(OfficialGarageMapProjects.IsOfficial(null));
        }

        private static string RepositoryRoot()
        {
            string current = AppContext.BaseDirectory;
            while (!string.IsNullOrEmpty(current))
            {
                string marker = Path.Combine(current, "data", "maps",
                    "allin1-online-content");
                if (Directory.Exists(marker)) return current;
                DirectoryInfo parent = Directory.GetParent(current);
                current = parent?.FullName;
            }
            throw new DirectoryNotFoundException(
                "Could not locate the ALLIN1 repository root.");
        }

        private static string ValidJson() => @"{
          ""schema_version"":1,
          ""id"":""warehouse"",
          ""package_id"":""acme.garage"",
          ""name"":""Acme Warehouse"",
          ""version"":""1.0.0"",
          ""editions"":[""legacy"",""enhanced""],
          ""streaming"":{
            ""pack_name"":""acme_maps"",
            ""content_group"":""ACME_MAP_WAREHOUSE"",
            ""ipls"":[""acme_shell""],
            ""activation_radius"":150.0,
            ""release_radius"":300.0,
            ""keep_resident"":false
          },
          ""levels"":[{
            ""id"":""garage"",""name"":""Garage"",
            ""center"":{""x"":100.0,""y"":200.0,""z"":20.0},
            ""ipls"":[""acme_collision""]
          },{
            ""id"":""office"",""name"":""Office"",
            ""center"":{""x"":110.0,""y"":205.0,""z"":25.0},
            ""ipls"":[]
          }],
          ""portals"":[{
            ""id"":""main"",""name"":""Warehouse entrance"",
            ""mode"":""both"",
            ""from"":{""level"":""world"",""position"":{
              ""x"":-100.0,""y"":-200.0,""z"":10.0,""heading"":45.0}},
            ""to"":{""level"":""garage"",""position"":{
              ""x"":100.0,""y"":200.0,""z"":20.0,""heading"":-45.0}},
            ""radius"":2.5,""one_way"":false
          },{
            ""id"":""stairs"",""mode"":""ped"",
            ""from"":{""level"":""garage"",""position"":{
              ""x"":105.0,""y"":200.0,""z"":20.0,""heading"":0.0}},
            ""to"":{""level"":""office"",""position"":{
              ""x"":110.0,""y"":205.0,""z"":25.0,""heading"":180.0}},
            ""radius"":1.5
          }],
          ""garages"":[{
            ""id"":""storage"",""name"":""Vehicle storage"",
            ""level_id"":""garage"",""entrance_portal_id"":""main"",
            ""capacity"":4,""vehicle_types"":[""land""],
            ""slots"":[{
              ""id"":""one"",""position"":{
                ""x"":101.0,""y"":201.0,""z"":20.0,""heading"":90.0}
            },{
              ""id"":""two"",""position"":{
                ""x"":104.0,""y"":201.0,""z"":20.0,""heading"":90.0},
              ""vehicle_types"":[""land""]
            }],
            ""rules"":{""allow_store"":true,""allow_retrieve"":true,
              ""save_policy"":""story_save_only""}
          }]
        }";
    }
}
