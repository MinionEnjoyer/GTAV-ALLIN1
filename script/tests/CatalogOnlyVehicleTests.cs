using System;
using System.Linq;
using System.IO;
using System.Reflection;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class CatalogOnlyVehicleTests
    {
        [Fact]
        public void ReactorDisplaysCatalogOnlyRatherThanAFreePurchase()
        {
            var plugin = Assembly.LoadFrom(Path.Combine(AppContext.BaseDirectory,
                "reactor-package", "scripts", "ReactorV", "ALLIN1.ReactorBridge.plugin"));
            var bridge = plugin.GetType("ALLIN1.ReactorBridge.Allin1ReactorBridge", true);
            var method = bridge.GetMethod("ListingDescription", BindingFlags.Static | BindingFlags.NonPublic);
            var description = (string)method.Invoke(null, new object[] {
                new Allin1VehicleListing { Model = "zentorno", Storage = "catalog_only", Price = 0,
                    Category = "super", Available = false, Manufacturer = "Pegassi" }
            });
            Assert.Contains("Price: CATALOG ONLY", description);
            Assert.Contains("Not offered yet", description);
            Assert.DoesNotContain("FREE", description);
        }

        [Fact]
        public void ReviewedSupplementHasPricesAndStorageButNeverEnablesTraffic()
        {
            RuntimeVehicleCatalog.MergeForTests(Array.Empty<RuntimeVehicleCatalogDocument>(), _ => true);
            Assert.Equal(218, CatalogOnlyVehicles.Records.Count);
            foreach (var record in CatalogOnlyVehicles.Records.Values)
            {
                Assert.True(RuntimeVehicleCatalog.IsListed(record.Model));
                bool blocked = record.Storage == "catalog_only";
                Assert.Equal(blocked, RuntimeVehicleCatalog.IsCatalogOnly(record.Model));
                if (blocked) Assert.False(RuntimeVehicleCatalog.IsModelAvailable(record.Model));
                Assert.Equal(record.Storage, RuntimeVehicleCatalog.GetStorage(record.Model));
                Assert.Equal(record.Storage == "garage", GarageVehicleTypePolicy.IsRegularGarageEligible(record.Model));
                Assert.Equal(record.Price, RuntimeVehicleCatalog.GetPrice(record.Model));
                Assert.True(blocked ? record.Price == 0 : record.Price > 0);
                Assert.False(record.TrafficEnabled);
                Assert.DoesNotContain(record.Model, VehicleList.All);
                Assert.Contains(record.Model, RuntimeVehicleCatalog.GetCategoryModels(record.Category));
                Assert.Contains(record.Model, RuntimeVehicleCatalog.GetCategoryModels("all"));
                Assert.True(RuntimeVehicleCatalog.TryGetByHash(
                    GetawayVehicleCompatibility.ModelHash(record.Model), out var byHash));
                Assert.Same(record, byHash);
            }
            Assert.Empty(RuntimeVehicleCatalog.TrafficEntries);
            Assert.Equal(149, CatalogOnlyVehicles.Records.Values.Count(row => row.Price > 0));
        }

        [Theory]
        [InlineData("tractor", "Epsilon")]
        [InlineData("tractor", "cult")]
        [InlineData("tractor", "cult tractor")]
        [InlineData("tractor", "Epsilon tractor")]
        [InlineData("dune2", "UFO")]
        [InlineData("dune2", "Space Docker")]
        [InlineData("jb700", "Devin")]
        [InlineData("jb700", "Devin Weston")]
        [InlineData("jb700", "Devon Weston")]
        [InlineData("ztype", "Weston")]
        [InlineData("entityxf", "Weston")]
        [InlineData("cheetah", "Weston")]
        [InlineData("monroe", "Weston")]
        public void StorySpecialsAreSearchableByTheirFamiliarNames(string model, string query)
        {
            Assert.Contains(query, RuntimeVehicleCatalog.SearchAliases(model));
        }
    }
}
