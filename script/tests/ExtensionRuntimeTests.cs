using System;
using System.IO;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class ExtensionRuntimeTests
    {
        [Fact]
        public void MissingRegistryKeepsOnlyOfficialLegacyPackagesEnabled()
        {
            RuntimeExtensionRegistry registry =
                RuntimeExtensionRegistry.Legacy(Path.GetTempPath());

            Assert.False(registry.Present);
            Assert.True(registry.IsEnabled(
                Allin1ExtensionApi.OnlineContentPackageId));
            Assert.True(registry.IsEnabled(
                Allin1ExtensionApi.ExperimentalGameplayPackageId));
            Assert.False(registry.IsEnabled("third.party"));
        }

        [Fact]
        public void RegistryParsesSettingsCapabilitiesAndGbayRoutes()
        {
            string scripts = Path.Combine(Path.GetTempPath(), "allin1-api", "scripts");
            string json = @"{
              ""schema_version"": 1,
              ""api_version"": 1,
              ""extensions"": [{
                ""schema_version"": 1,
                ""api_version"": 1,
                ""id"": ""example.content"",
                ""name"": ""Example Content"",
                ""version"": ""1.2.3"",
                ""source"": ""package"",
                ""enabled"": true,
                ""capabilities"": [""gbay.sections"", ""gbay.catalogs"",
                  ""story-save.transactions""],
                ""settings"": {""enabled"": true, ""density"": 3},
                ""gbay"": {""sections"": [{
                  ""id"": ""example-action"",
                  ""label"": ""Example Action"",
                  ""description"": ""Runs the example."",
                  ""route"": ""example:action"",
                  ""order"": 25
                }], ""catalogs"": [{
                  ""id"": ""example-services"",
                  ""kind"": ""service"",
                  ""source"": ""scripts/Example/services.json""
                }]},
                ""runtime_files"": [{
                  ""path"": ""scripts/Example.dll"",
                  ""sha256"": ""aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa""
                }],
                ""catalog_files"": [{
                  ""path"": ""scripts/Example/services.json"",
                  ""sha256"": ""bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb""
                }]
              }]
            }";

            RuntimeExtensionRegistry registry =
                RuntimeExtensionRegistry.Parse(json, scripts);

            Assert.True(registry.Present);
            Assert.True(registry.Valid);
            Assert.True(registry.IsEnabled("example.content"));
            RuntimeExtensionPackage package = registry.Packages["example.content"];
            Assert.Contains("gbay.sections", package.Capabilities);
            Assert.Equal(true, package.Settings["enabled"]);
            Assert.Equal(3, package.Settings["density"]);
            Assert.Single(package.Sections);
            Assert.Equal("example:action", package.Sections[0].Route);
            Assert.Equal(25, package.Sections[0].Order);
            Assert.Single(package.Catalogs);
            Assert.Equal("service", package.Catalogs[0].Kind);
            Assert.Equal("scripts/Example/services.json",
                package.Catalogs[0].Source);
            Assert.Single(package.RuntimeFiles);
        }

        [Fact]
        public void BlockedPackageCannotAuthorizeRuntimeBehavior()
        {
            string json = @"{
              ""schema_version"": 1,
              ""api_version"": 1,
              ""extensions"": [{
                ""schema_version"": 1,
                ""api_version"": 1,
                ""id"": ""blocked.package"",
                ""source"": ""package"",
                ""enabled"": true,
                ""blocked_reason"": ""receipt hash mismatch"",
                ""capabilities"": [],
                ""settings"": {},
                ""gbay"": {""sections"": []},
                ""runtime_files"": []
              }]
            }";

            RuntimeExtensionRegistry registry = RuntimeExtensionRegistry.Parse(
                json, Path.Combine(Path.GetTempPath(), "game", "scripts"));

            Assert.False(registry.IsEnabled("blocked.package"));
        }

        [Theory]
        [InlineData("mods/Evil.dll")]
        [InlineData("scripts/../Evil.dll")]
        [InlineData("scripts/C:/Evil.dll")]
        [InlineData("scripts")]
        public void RuntimeAuthorizationPathsStayBelowScripts(
            string relativePath)
        {
            string game = Path.Combine(Path.GetTempPath(), "allin1-contained-game");
            Assert.Null(RuntimeExtensionRegistry.ContainedRuntimePath(
                game, relativePath));
        }

        [Fact]
        public void DuplicatePackageIdsAreRejected()
        {
            string extension = @"{
              ""schema_version"": 1, ""api_version"": 1,
              ""id"": ""same.package"", ""source"": ""package"",
              ""enabled"": true,
              ""capabilities"": [], ""settings"": {},
              ""gbay"": {""sections"": []}, ""runtime_files"": []
            }";
            string json = "{\"schema_version\":1,\"api_version\":1," +
                "\"extensions\":[" + extension + "," + extension + "]}";

            Assert.Throws<InvalidDataException>(() =>
                RuntimeExtensionRegistry.Parse(
                    json, Path.Combine(Path.GetTempPath(), "game", "scripts")));
        }

        [Fact]
        public void RuntimeRegistryUsesTheAssemblyDirectoryForScriptsState()
        {
            string root = Path.Combine(Path.GetTempPath(), "allin1-path-test");
            string scripts = Path.Combine(root, "scripts");
            string assembly = Path.Combine(scripts, "ALLIN1.dll");

            Assert.Equal(
                Path.GetFullPath(scripts),
                Allin1ExtensionApi.ResolveScriptsDirectory(assembly, root));
        }

        [Fact]
        public void RuntimeRegistryFallsBackWhenAssemblyLocationIsUnavailable()
        {
            string fallback = Path.Combine(
                Path.GetTempPath(), "allin1-path-fallback");

            Assert.Equal(
                Path.GetFullPath(fallback),
                Allin1ExtensionApi.ResolveScriptsDirectory("", fallback));
        }

        [Fact]
        public void PackageCannotClaimAnOfficialBuiltInId()
        {
            string json = @"{
              ""schema_version"": 1, ""api_version"": 1,
              ""extensions"": [{
                ""schema_version"": 1, ""api_version"": 1,
                ""id"": ""allin1.online-content"",
                ""source"": ""package"", ""enabled"": true,
                ""capabilities"": [], ""settings"": {},
                ""gbay"": {""sections"": []}, ""runtime_files"": []
              }]
            }";

            RuntimeExtensionRegistry registry = RuntimeExtensionRegistry.Parse(
                json, Path.Combine(Path.GetTempPath(), "game", "scripts"));

            Assert.False(registry.IsEnabled(
                Allin1ExtensionApi.OnlineContentPackageId));
        }

        [Fact]
        public void MulticastGbayCallbacksAreRejectedBeforeAuthorization()
        {
            Action callback = NoOp;
            callback += NoOp;

            Assert.Throws<ArgumentException>(() =>
                Allin1ExtensionApi.RegisterGbayAction(
                    "example.content", "example:action", callback));
        }

        [Fact]
        public void PackageCatalogRequiresMatchingReceiptAuthorization()
        {
            string scripts = Path.Combine(
                Path.GetTempPath(), "allin1-catalog-receipt", "scripts");

            Assert.Throws<InvalidDataException>(() =>
                RuntimeExtensionRegistry.Parse(
                    CatalogRegistryJson("package", "[]"), scripts));
        }

        [Fact]
        public void PackageCatalogRejectsAReceiptForAnotherPath()
        {
            string scripts = Path.Combine(
                Path.GetTempPath(), "allin1-catalog-mismatch", "scripts");
            string files = @"[{
              ""path"": ""scripts/Example/other.json"",
              ""sha256"": ""aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa""
            }]";

            Assert.Throws<InvalidDataException>(() =>
                RuntimeExtensionRegistry.Parse(
                    CatalogRegistryJson("package", files), scripts));
        }

        [Fact]
        public void PackageCatalogIsFilteredAfterFileTamperingOrRemoval()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-catalog-integrity-" + Guid.NewGuid().ToString("N"));
            string scripts = Path.Combine(root, "scripts");
            string catalogPath = Path.Combine(
                scripts, "Example", "services.json");
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(catalogPath));
                File.WriteAllText(catalogPath, "{\"items\":[]}");
                string digest = RuntimeExtensionRegistry.Sha256(catalogPath);
                string files = "[{\"path\":\"scripts/Example/services.json\"," +
                    "\"sha256\":\"" + digest + "\"}]";
                RuntimeExtensionRegistry registry = RuntimeExtensionRegistry.Parse(
                    CatalogRegistryJson("package", files), scripts);
                RuntimeExtensionPackage package = registry.Packages["example.content"];

                Assert.Single(Allin1ExtensionApi.CurrentGbayCatalogs(package));

                File.AppendAllText(catalogPath, " ");
                Assert.Empty(Allin1ExtensionApi.CurrentGbayCatalogs(package));

                File.Delete(catalogPath);
                Assert.Empty(Allin1ExtensionApi.CurrentGbayCatalogs(package));
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        [Fact]
        public void BuiltInCatalogMayOmitAReceiptButMustExist()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-builtin-catalog-" + Guid.NewGuid().ToString("N"));
            string scripts = Path.Combine(root, "scripts");
            string catalogPath = Path.Combine(
                scripts, "Example", "services.json");
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(catalogPath));
                File.WriteAllText(catalogPath, "{\"items\":[]}");
                RuntimeExtensionRegistry registry = RuntimeExtensionRegistry.Parse(
                    CatalogRegistryJson("built-in", "[]"), scripts);
                RuntimeExtensionPackage package = registry.Packages["example.content"];

                Assert.Single(Allin1ExtensionApi.CurrentGbayCatalogs(package));

                File.Delete(catalogPath);
                Assert.Empty(Allin1ExtensionApi.CurrentGbayCatalogs(package));
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        [Fact]
        public void RegisteredGbayActionInvokesAndDisposalRemovesIt()
        {
            Allin1ExtensionApi.ResetCallbacksForTests();
            int invoked = 0;
            try
            {
                IDisposable registration =
                    Allin1ExtensionApi.RegisterGbayActionForTests(
                        "example.content", "example:action", () => invoked++);

                GbayAddonAction action = Assert.Single(
                    Allin1ExtensionApi.GetGbayActions());
                Allin1ExtensionApi.InvokeGbayAction(action);
                Allin1ExtensionApi.InvokeGbayAction(action);
                Assert.Equal(2, invoked);

                registration.Dispose();
                Assert.Empty(Allin1ExtensionApi.GetGbayActions());
                Allin1ExtensionApi.InvokeGbayAction(action);
                Assert.Equal(2, invoked);
            }
            finally
            {
                Allin1ExtensionApi.ResetCallbacksForTests();
            }
        }

        [Fact]
        public void StorySaveParticipantCommitsOnlyForNewSavesAndDiscardsOnExit()
        {
            Allin1ExtensionApi.ResetCallbacksForTests();
            var participant = new RecordingSaveParticipant();
            DateTime first = new DateTime(
                2026, 8, 22, 12, 0, 0, DateTimeKind.Utc);
            try
            {
                using (Allin1ExtensionApi.RegisterStorySaveParticipantForTests(
                    "example.content", "purchases", participant))
                {
                    Allin1ExtensionApi.NotifyStorySave(first, "first_save");
                    Allin1ExtensionApi.NotifyStorySave(first, "duplicate_save");
                    Allin1ExtensionApi.NotifyStorySave(
                        first.AddSeconds(-1), "older_save");
                    Allin1ExtensionApi.NotifyStorySave(
                        first.AddSeconds(1), "second_save");

                    Assert.Equal(2, participant.CommitCount);
                    Assert.Equal("second_save", participant.LastCommitReason);

                    Allin1ExtensionApi.NotifySessionEnd(
                        first.AddSeconds(1), "script_aborted");
                    Assert.Equal(1, participant.DiscardCount);
                    Assert.Equal("script_aborted", participant.LastDiscardReason);
                }

                Allin1ExtensionApi.NotifyStorySave(
                    first.AddSeconds(2), "after_dispose");
                Assert.Equal(2, participant.CommitCount);
            }
            finally
            {
                Allin1ExtensionApi.ResetCallbacksForTests();
            }
        }

        [Fact]
        public void RegistryReloadRevokesAndDiscardsTestParticipant()
        {
            Allin1ExtensionApi.ResetCallbacksForTests();
            var participant = new RecordingSaveParticipant();
            DateTime save = new DateTime(
                2026, 8, 22, 13, 0, 0, DateTimeKind.Utc);
            try
            {
                using (Allin1ExtensionApi.RegisterStorySaveParticipantForTests(
                    "example.content", "revoked", participant))
                {
                    Allin1ExtensionApi.ReloadRegistry();
                    Allin1ExtensionApi.NotifyStorySave(save, "save_after_reload");
                    Assert.Equal(0, participant.CommitCount);
                    Assert.Equal(1, participant.DiscardCount);
                    Assert.Equal(
                        "authorization_revoked", participant.LastDiscardReason);
                }
            }
            finally
            {
                Allin1ExtensionApi.ResetCallbacksForTests();
            }
        }

        [Fact]
        public void StorySaveScopePinsOneEditionAndOneProfile()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-save-scope-" + Guid.NewGuid().ToString("N"));
            string documents = Path.Combine(root, "Documents");
            string game = Path.Combine(root, "Grand Theft Auto V Enhanced");
            string scripts = Path.Combine(game, "scripts");
            string enhancedProfiles = Path.Combine(
                documents, "Rockstar Games", "GTAV Enhanced", "Profiles");
            string legacyProfile = Path.Combine(
                documents, "Rockstar Games", "GTA V", "Profiles", "legacy");
            string active = Path.Combine(enhancedProfiles, "active");
            string other = Path.Combine(enhancedProfiles, "other");
            try
            {
                Directory.CreateDirectory(scripts);
                File.WriteAllBytes(Path.Combine(game, "GTA5_Enhanced.exe"),
                    new byte[] { 1 });
                Directory.CreateDirectory(active);
                Directory.CreateDirectory(other);
                Directory.CreateDirectory(legacyProfile);
                string activeSave = Path.Combine(active, "SGTA50001");
                string otherSave = Path.Combine(other, "SGTA50002");
                string legacySave = Path.Combine(legacyProfile, "SGTA50003");
                File.WriteAllText(activeSave, "active");
                File.WriteAllText(otherSave, "other");
                File.WriteAllText(legacySave, "legacy");
                DateTime baseline = new DateTime(
                    2026, 8, 22, 10, 0, 0, DateTimeKind.Utc);
                File.SetLastWriteTimeUtc(activeSave, baseline);
                File.SetLastWriteTimeUtc(otherSave, baseline.AddMinutes(-1));
                File.SetLastWriteTimeUtc(legacySave, baseline.AddHours(1));

                StorySaveScope scope = StorySaveMonitor.CreateActiveScope(
                    documents, scripts);
                Assert.NotNull(scope);
                Assert.Equal(Path.GetFullPath(active), scope.ProfileDirectory);
                Assert.Equal(baseline, scope.LatestStorySaveWriteUtc());

                File.SetLastWriteTimeUtc(otherSave, baseline.AddHours(2));
                Assert.Equal(baseline, scope.LatestStorySaveWriteUtc());
                File.SetLastWriteTimeUtc(activeSave, baseline.AddMinutes(1));
                Assert.Equal(
                    baseline.AddMinutes(1), scope.LatestStorySaveWriteUtc());
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        private static string CatalogRegistryJson(
            string source, string catalogFiles)
        {
            return @"{
              ""schema_version"": 1,
              ""api_version"": 1,
              ""extensions"": [{
                ""schema_version"": 1,
                ""api_version"": 1,
                ""id"": ""example.content"",
                ""source"": ""__SOURCE__"",
                ""enabled"": true,
                ""capabilities"": [""gbay.catalogs""],
                ""settings"": {},
                ""gbay"": {
                  ""sections"": [],
                  ""catalogs"": [{
                    ""id"": ""example.services"",
                    ""kind"": ""service"",
                    ""source"": ""scripts/Example/services.json""
                  }]
                },
                ""runtime_files"": [],
                ""catalog_files"": __CATALOG_FILES__
              }]
            }".Replace("__SOURCE__", source)
                .Replace("__CATALOG_FILES__", catalogFiles);
        }

        private static void NoOp()
        {
        }

        private sealed class RecordingSaveParticipant : IStorySaveParticipant
        {
            internal int CommitCount { get; private set; }
            internal int DiscardCount { get; private set; }
            internal string LastCommitReason { get; private set; }
            internal string LastDiscardReason { get; private set; }

            public void Commit(StorySaveContext context)
            {
                CommitCount++;
                LastCommitReason = context.Reason;
            }

            public void Discard(StorySessionEndContext context)
            {
                DiscardCount++;
                LastDiscardReason = context.Reason;
            }
        }
    }
}
