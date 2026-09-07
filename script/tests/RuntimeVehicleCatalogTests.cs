using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class RuntimeVehicleCatalogTests
    {
        [Fact]
        public void ValidCatalogParsesAndNormalizesEveryAuthorizedField()
        {
            RuntimeVehicleCatalogDocument document = Parse(
                "example.vehicles",
                "Example Vehicles",
                Vehicle(
                    "examplecar", "Example Car", "Example Motors",
                    "sportsclassics", 125000, "garage", "examplepack", 1,
                    trafficEnabled: true, trafficWeight: 2.5,
                    previewDictionary: "examplecar_previews",
                    previewTexture: "examplecar_card"),
                trafficSetting: true,
                trafficCapability: true);

            Assert.Equal("example.package", document.PackageId);
            Assert.Equal("example.vehicles", document.CatalogId);
            Assert.Equal("Example Vehicles", document.Name);

            GbayVehicleRecord record = Assert.Single(document.Vehicles);
            Assert.Equal("example.package", record.PackageId);
            Assert.Equal("example.vehicles", record.CatalogId);
            Assert.Equal("examplecar", record.Model);
            Assert.Equal("Example Car", record.Name);
            Assert.Equal("Example Motors", record.Manufacturer);
            Assert.Equal("sportsclassics", record.Category);
            Assert.Equal(125000, record.Price);
            Assert.Equal("garage", record.Storage);
            Assert.Equal("examplepack", record.SourcePack);
            Assert.Equal(1, record.SizeTier);
            Assert.Equal("examplecar_previews", record.PreviewDictionary);
            Assert.Equal("examplecar_card", record.PreviewTexture);
            Assert.True(record.TrafficEnabled);
            Assert.Equal(2.5, record.TrafficWeight);
            Assert.False(record.HasValidatedRuntimeVehicleClass);

            record.SetValidatedRuntimeVehicleClass(
                GTA.VehicleClass.SportsClassics);
            Assert.True(record.HasValidatedRuntimeVehicleClass);
            Assert.Equal(GTA.VehicleClass.SportsClassics,
                record.ValidatedRuntimeVehicleClass);
        }

        [Fact]
        public void OptionalCatalogFieldsUseSchemaDefaults()
        {
            RuntimeVehicleCatalogDocument document = Parse(
                "example.no-preview", "No Preview",
                Vehicle("no-preview-car", manufacturer: null,
                    previewDictionary: null, includeOptionals: false));

            GbayVehicleRecord record = Assert.Single(document.Vehicles);
            Assert.Equal("", record.Manufacturer);
            Assert.Equal("", record.PreviewDictionary);
            Assert.Equal("", record.PreviewTexture);
            Assert.Equal(0, record.SizeTier);
            Assert.False(record.TrafficEnabled);
            Assert.Equal(1.0, record.TrafficWeight);
            Assert.Null(record.Hitches);
        }

        [Fact]
        public void HitchProfilesReachRuntimeAndRejectMismatchedOwnership()
        {
            var vehicle = Newtonsoft.Json.Linq.JObject.Parse(Vehicle("examplecar"));
            vehicle["hitches"] = Newtonsoft.Json.Linq.JObject.Parse(@"{
                'schema_version':1,'vehicle_model':'examplecar','points':[{
                    'id':'rear','mode':'native','bone':'attach_female',
                    'position':[0,0,0],'rotation':[0,0,0],
                    'coupler_bone':'attach_male','coupler_offset':[0,0,0],
                    'compatible_models':['trailers'],'connect_distance':1,'break_force':10000
                }]}");
            var record = Assert.Single(Parse("example.hitches", "Hitches", vehicle.ToString()).Vehicles);
            Assert.Equal("rear", Assert.Single(record.Hitches.Points).Id);
            vehicle["hitches"]["vehicle_model"] = "othercar";
            Assert.Throws<InvalidDataException>(() => Parse("example.hitches", "Hitches", vehicle.ToString()));
            vehicle["hitches"]["vehicle_model"] = "examplecar";
            vehicle["hitches"]["points"] = new Newtonsoft.Json.Linq.JArray();
            Assert.Empty(Assert.Single(Parse("example.hitches", "Hitches", vehicle.ToString()).Vehicles).Hitches.Points);
        }

        [Fact]
        public void PreviewTextureRequiresPreviewDictionary()
        {
            Assert.Throws<InvalidDataException>(() => Parse(
                "example.preview", "Preview",
                Vehicle("previewcar", previewTexture: "preview_card")));
        }

        [Fact]
        public void HangarAndZeroPriceMatchLauncherContract()
        {
            GbayVehicleRecord record = Assert.Single(Parse(
                "example.aircraft", "Aircraft",
                Vehicle("exampleplane", category: "planes", price: 0,
                    storage: "hangar")).Vehicles);

            Assert.Equal("hangar", record.Storage);
            Assert.Equal(0, record.Price);
        }

        [Fact]
        public void SpecializedCategoryStorageMismatchIsRejected()
        {
            Assert.Throws<InvalidDataException>(() => Parse(
                "example.storage", "Storage",
                Vehicle("badboat", category: "boats", storage: "garage")));
        }

        [Theory]
        [MemberData(nameof(InvalidStrictCatalogs))]
        public void UnknownOrMissingFieldsAreRejected(string json)
        {
            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    json, "example.package", "example.vehicles"));
        }

        public static IEnumerable<object[]> InvalidStrictCatalogs()
        {
            string vehicle = Vehicle("strictcar");
            yield return new object[]
            {
                Root("example.vehicles", "Strict", vehicle,
                    ",\"unexpected\":true"),
            };
            yield return new object[]
            {
                "{\"schema_version\":1,\"id\":\"example.vehicles\"," +
                "\"vehicles\":[" + vehicle + "]}",
            };
            yield return new object[]
            {
                Root("example.vehicles", "Strict",
                    vehicle.Replace("\"model\":\"strictcar\",", "")),
            };
            yield return new object[]
            {
                Root("example.vehicles", "Strict",
                    vehicle.Replace("\"traffic\":{",
                        "\"unexpected\":true,\"traffic\":{")),
            };
        }

        [Fact]
        public void ThirdPartyPackageCannotClaimOfficialBaseContent()
        {
            string json = Root("example.vehicles", "Example Vehicles",
                Vehicle("forgedbasecar", sourcePack: "base"));

            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    json, "example.package", "example.vehicles"));
        }

        [Fact]
        public void TrafficEnabledItemRequiresTheDeclaredCapability()
        {
            string json = Root("example.vehicles", "Example Vehicles",
                Vehicle("trafficcar", trafficEnabled: true));

            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    json, "example.package", "example.vehicles",
                    trafficSetting: true, trafficCapability: false));
        }

        [Theory]
        [InlineData(false, true, false)]
        [InlineData(true, true, true)]
        [InlineData(true, false, false)]
        public void TrafficExposureRequiresItemSettingAndCapability(
            bool packageSetting, bool itemEnabled, bool expected)
        {
            RuntimeVehicleCatalogDocument document = Parse(
                "example.traffic", "Traffic",
                Vehicle("trafficgatecar", trafficEnabled: itemEnabled),
                trafficSetting: packageSetting,
                trafficCapability: true);

            GbayVehicleRecord record = Assert.Single(document.Vehicles);
            Assert.Equal(expected, record.TrafficEnabled);

            RuntimeVehicleCatalog.MergeForTests(new[] { document });
            Assert.Equal(expected,
                RuntimeVehicleCatalog.TrafficEntries.Any(value =>
                    value.Model == "trafficgatecar"));
        }

        [Fact]
        public void StaticVehicleListWinsAConflictingPackageRecord()
        {
            RuntimeVehicleCatalogDocument document = Parse(
                "example.static-collision", "Static Collision",
                Vehicle("brioso") + "," + Vehicle("uniqueaddoncar"));

            IReadOnlyList<GbayVehicleRecord> merged =
                RuntimeVehicleCatalog.MergeForTests(new[] { document });

            Assert.DoesNotContain(merged, value => value.Model == "brioso");
            Assert.Contains(merged, value => value.Model == "uniqueaddoncar");
        }

        [Fact]
        public void OnlyOfficialBaseMirrorsSuppressStaticCollisionNoise()
        {
            GbayVehicleRecord official = Assert.Single(Parse(
                "official.story", "Official Story",
                Vehicle("stretch", sourcePack: "base"),
                packageId: Allin1ExtensionApi.OnlineContentPackageId).Vehicles);
            GbayVehicleRecord thirdParty = Assert.Single(Parse(
                "third.vehicles", "Third Party",
                Vehicle("brioso"), packageId: "third.package").Vehicles);

            Assert.False(RuntimeVehicleCatalog.ShouldReportModelCollision(
                official, conflictsWithStaticModel: true));
            Assert.True(RuntimeVehicleCatalog.ShouldReportModelCollision(
                thirdParty, conflictsWithStaticModel: true));
            Assert.True(RuntimeVehicleCatalog.ShouldReportModelCollision(
                official, conflictsWithStaticModel: false));
        }

        [Fact]
        public void OfficialStoryRecordWinsRegardlessOfDocumentOrder()
        {
            const string model = "officialcollisioncar";
            RuntimeVehicleCatalogDocument package = Parse(
                "third.vehicles", "Third Party", Vehicle(model),
                packageId: "aaa.third-party");
            RuntimeVehicleCatalogDocument official = Parse(
                "official.vehicles", "Official",
                Vehicle(model, name: "Official Name", sourcePack: "base"),
                packageId: Allin1ExtensionApi.OnlineContentPackageId);

            GbayVehicleRecord winner = Assert.Single(
                RuntimeVehicleCatalog.MergeForTests(
                    new[] { package, official }));

            Assert.Equal(Allin1ExtensionApi.OnlineContentPackageId,
                winner.PackageId);
            Assert.Equal("Official Name", winner.Name);
            Assert.True(winner.IsOfficialStoryVehicle);
            Assert.False(GetawayVehicleCompatibility.IsAllIn1DlcModel(
                GetawayVehicleCompatibility.ModelHash(model)));
        }

        [Fact]
        public void PackageCollisionWinnerUsesStablePackageAndCatalogOrdering()
        {
            const string model = "deterministiccollisioncar";
            RuntimeVehicleCatalogDocument laterPackage = Parse(
                "aaa.catalog", "Later Package",
                Vehicle(model, name: "Later Package"),
                packageId: "zzz.package");
            RuntimeVehicleCatalogDocument laterCatalog = Parse(
                "zzz.catalog", "Later Catalog",
                Vehicle(model, name: "Later Catalog"),
                packageId: "aaa.package");
            RuntimeVehicleCatalogDocument winnerDocument = Parse(
                "aaa.catalog", "Winner",
                Vehicle(model, name: "Stable Winner"),
                packageId: "aaa.package");

            GbayVehicleRecord winner = Assert.Single(
                RuntimeVehicleCatalog.MergeForTests(new[]
                {
                    laterPackage, laterCatalog, winnerDocument,
                }));

            Assert.Equal("aaa.package", winner.PackageId);
            Assert.Equal("aaa.catalog", winner.CatalogId);
            Assert.Equal("Stable Winner", winner.Name);
        }

        [Fact]
        public void DuplicateModelsAreRejectedCaseInsensitively()
        {
            string json = Root("example.duplicates", "Duplicates",
                Vehicle("duplicatecar") + "," + Vehicle("DUPLICATECAR"));

            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    json, "example.package", "example.duplicates"));
        }

        [Fact]
        public void JenkinsHashCollisionsAreRejectedEvenWhenNamesDiffer()
        {
            string json = Root("example.hashes", "Hash Collisions",
                Vehicle("xqe8v7fz") + "," + Vehicle("xc7xaymx"));

            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    json, "example.package", "example.hashes"));
        }

        [Fact]
        public void MergedAddOnCanBeResolvedByNativeModelHash()
        {
            RuntimeVehicleCatalogDocument document = Parse(
                "example.hash-lookup", "Hash Lookup", Vehicle("hashlookupcar"));
            GbayVehicleRecord expected = Assert.Single(
                RuntimeVehicleCatalog.MergeForTests(new[] { document }));

            Assert.True(RuntimeVehicleCatalog.TryGetByHash(
                GetawayVehicleCompatibility.ModelHash("hashlookupcar"),
                out GbayVehicleRecord actual));
            Assert.Same(expected, actual);
            Assert.False(actual.IsOfficialStoryVehicle);
            Assert.True(GetawayVehicleCompatibility.IsAllIn1DlcModel(
                GetawayVehicleCompatibility.ModelHash("hashlookupcar")));
        }

        [Fact]
        public void CatalogRejectsMoreThanTwoThousandFortyEightVehicles()
        {
            var vehicles = new string[2049];
            for (int index = 0; index < vehicles.Length; index++)
                vehicles[index] = Vehicle("boundedcar" + index);

            string json = Root("example.bounded", "Bounded",
                string.Join(",", vehicles));

            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    json, "example.package", "example.bounded"));
        }

        [Fact]
        public void MergedLimitAccommodatesStoryPlusAMaximumSizePackage()
        {
            string[] storyVehicles = new string[256];
            for (int index = 0; index < storyVehicles.Length; index++)
                storyVehicles[index] = Vehicle(
                    "storybounded" + index, sourcePack: "base");
            string[] packageVehicles = new string[2048];
            for (int index = 0; index < packageVehicles.Length; index++)
                packageVehicles[index] = Vehicle("packagebounded" + index);

            RuntimeVehicleCatalogDocument story = Parse(
                "story.bounded", "Story",
                string.Join(",", storyVehicles),
                packageId: Allin1ExtensionApi.OnlineContentPackageId);
            RuntimeVehicleCatalogDocument package = Parse(
                "package.bounded", "Package",
                string.Join(",", packageVehicles));

            Assert.Equal(2304, RuntimeVehicleCatalog.MergeForTests(
                new[] { package, story }).Count);
        }

        [Fact]
        public void CatalogRejectsInputLargerThanFourMebibytes()
        {
            string oversized = new string(' ', 4 * 1024 * 1024 + 1);

            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    oversized, "example.package", "example.oversized"));
        }

        [Theory]
        [InlineData("\"price\":2000000001")]
        [InlineData("\"size_tier\":3")]
        [InlineData("\"weight\":20.1")]
        public void NumericBoundsAreEnforced(string invalidField)
        {
            string vehicle = Vehicle("numericboundcar");
            if (invalidField.StartsWith("\"price\"", StringComparison.Ordinal))
                vehicle = vehicle.Replace("\"price\":100000", invalidField);
            else if (invalidField.StartsWith("\"size_tier\"", StringComparison.Ordinal))
                vehicle = vehicle.Replace("\"size_tier\":1", invalidField);
            else
                vehicle = vehicle.Replace("\"weight\":1", invalidField);

            Assert.Throws<InvalidDataException>(() =>
                RuntimeVehicleCatalog.ParseForTests(
                    Root("example.bounds", "Bounds", vehicle),
                    "example.package", "example.bounds"));
        }

        [Fact]
        public void MergeFiltersUnavailableModelsBeforeExposure()
        {
            RuntimeVehicleCatalogDocument document = Parse(
                "example.availability", "Availability",
                Vehicle("availablecar") + "," + Vehicle("missingcar"));

            IReadOnlyList<GbayVehicleRecord> merged =
                RuntimeVehicleCatalog.MergeForTests(new[] { document },
                    record => record.Model == "availablecar");

            Assert.Single(merged);
            Assert.Equal("availablecar", merged[0].Model);
        }

        private static RuntimeVehicleCatalogDocument Parse(
            string catalogId, string catalogName, string vehicles,
            bool trafficSetting = false, bool trafficCapability = false,
            string packageId = "example.package")
        {
            return RuntimeVehicleCatalog.ParseForTests(
                Root(catalogId, catalogName, vehicles),
                packageId, catalogId, trafficSetting, trafficCapability);
        }

        private static string Root(
            string id, string name, string vehicles, string suffix = "")
        {
            return "{\"schema_version\":1,\"id\":\"" + id +
                "\",\"name\":\"" + name + "\",\"vehicles\":[" +
                vehicles + "]" + suffix + "}";
        }

        private static string Vehicle(
            string model,
            string name = "Example Car",
            string manufacturer = "Example Motors",
            string category = "sports",
            int price = 100000,
            string storage = "garage",
            string sourcePack = "examplepack",
            int sizeTier = 1,
            bool trafficEnabled = false,
            double trafficWeight = 1.0,
            string previewDictionary = null,
            string previewTexture = null,
            bool includeOptionals = true)
        {
            var json = new StringBuilder();
            json.Append("{\"model\":\"").Append(model)
                .Append("\",\"name\":\"").Append(name);
            if (manufacturer != null)
                json.Append("\",\"manufacturer\":\"").Append(manufacturer);
            json
                .Append("\",\"category\":\"").Append(category)
                .Append("\",\"price\":").Append(price)
                .Append(",\"storage\":\"").Append(storage)
                .Append("\",\"source_pack\":\"").Append(sourcePack);
            if (includeOptionals)
                json.Append("\",\"size_tier\":").Append(sizeTier);
            else
                json.Append('"');
            if (previewDictionary != null)
                json.Append(",\"preview_dictionary\":\"")
                    .Append(previewDictionary).Append('"');
            if (previewTexture != null)
                json.Append(",\"preview_texture\":\"")
                    .Append(previewTexture).Append('"');
            if (includeOptionals)
            {
                json.Append(",\"traffic\":{\"enabled\":")
                    .Append(trafficEnabled ? "true" : "false")
                    .Append(",\"weight\":")
                    .Append(trafficWeight.ToString(
                        System.Globalization.CultureInfo.InvariantCulture))
                    .Append("}");
            }
            json.Append('}');
            return json.ToString();
        }
    }
}
