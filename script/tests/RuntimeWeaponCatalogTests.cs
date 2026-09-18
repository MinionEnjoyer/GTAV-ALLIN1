using System;
using System.IO;
using System.Linq;
using System.Text;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class RuntimeWeaponCatalogTests
    {
        private const string Weapon = "WEAPON_A1_KRISS_VECTOR";
        private const string Json = "{\"schema_version\":1,\"id\":\"test-weapons\",\"name\":\"Weapons\",\"weapons\":[{" +
            "\"weapon\":\"WEAPON_A1_KRISS_VECTOR\",\"name\":\"KRISS Vector\",\"category\":\"smgs\"," +
            "\"price\":7500,\"ammo_cost_per_round\":2,\"source_pack\":\"a1_krissvector\"}]}";
        private static RuntimeWeaponDocument Parse(string json = Json, string package = "test.weapon") =>
            RuntimeWeaponCatalog.Parse(json, package, "test-weapons");

        [Fact]
        public void AddonSmgsAreGroupedAndAlphabetizedInsteadOfAppended()
        {
            var snapshot = RuntimeWeaponCatalog.Merge(new[] { Parse() });
            string[] smgs = snapshot.Category("SMGs");
            Assert.Equal(smgs.OrderBy(id => snapshot.DisplayNames[id], StringComparer.OrdinalIgnoreCase), smgs);
            int first = Array.IndexOf(snapshot.All, smgs[0]);
            Assert.Equal(smgs, snapshot.All.Skip(first).Take(smgs.Length));
            Assert.True(Array.IndexOf(snapshot.All, Weapon) < Array.IndexOf(snapshot.All, "WEAPON_PUMPSHOTGUN"));
            Assert.Equal(snapshot.All, RuntimeWeaponCatalog.Sort(snapshot.All.Reverse(), snapshot.CategoryNames, snapshot.DisplayNames));
        }

        [Fact]
        public void SmokeProductsSortIntoThrowablesInBothStorefronts()
        {
            var sorted = RuntimeWeaponCatalog.Sort(WeaponList.All.Concat(SmokeGrenadeCatalog.ProductIds));
            int start = Array.FindIndex(sorted, id => SmokeGrenadeCatalog.IsProduct(id) || WeaponList.Throwables.Contains(id));
            var group = sorted.Skip(start).Take(WeaponList.Throwables.Length + SmokeGrenadeCatalog.ProductIds.Length);
            Assert.All(group, id => Assert.True(SmokeGrenadeCatalog.IsProduct(id) || WeaponList.Throwables.Contains(id)));
        }

        [Theory]
        [InlineData("WEAPON_A1_KRISS_VECTOR", 8, 0)]
        [InlineData("WEAPON_UNDECLARED_ADDON", 32, 0)]
        [InlineData("WEAPON_SMG", 8, 8)]
        [InlineData("WEAPON_SMG", -1, 0)]
        [InlineData("WEAPON_SMG", 999999, 32)]
        [InlineData(null, 8, 0)]
        public void UndeclaredAddonMaterialsNeverAuthorizeInheritedTintSales(string weapon, int reported, int allowed)
        {
            Assert.Equal(allowed, RuntimeWeaponCatalog.SupportedTintCount(weapon, reported));
        }

        [Fact]
        public void BothRenderersReceiveTheSeparateSmgAndSharedPrices()
        {
            var snapshot = RuntimeWeaponCatalog.Merge(new[] { Parse() });
            Assert.Equal(0xCDA264A5u, RuntimeWeaponCatalog.WeaponHash(Weapon));
            Assert.Equal(WeaponList.All.Length + 1, snapshot.All.Length);
            Assert.Contains(Weapon, snapshot.Category("SMGs"));
            Assert.Equal("KRISS Vector", snapshot.DisplayNames[Weapon]);
            Assert.Equal(7500, snapshot.Prices[Weapon]);
            Assert.Equal(2, snapshot.AmmoCostPerRound[Weapon]);
            Assert.Equal(1, snapshot.PurchaseQuantities[Weapon]);
            Assert.DoesNotContain(Weapon, WeaponList.All);
        }

        [Fact]
        public void Population_authorization_is_bound_to_the_catalog_package()
        {
            var snapshot = RuntimeWeaponCatalog.Merge(new[] { Parse() });
            Assert.True(snapshot.PopulationEntries.ContainsKey(
                RuntimeWeaponCatalog.PopulationKey("test.weapon", Weapon)));
            Assert.False(snapshot.PopulationEntries.ContainsKey(
                RuntimeWeaponCatalog.PopulationKey("other.package", Weapon)));
        }

        [Fact]
        public void Population_catalog_requires_its_declaration_dlc_snapshot()
        {
            Assert.Single(RuntimeWeaponCatalog.ParseForTests(Json,
                "test.weapon", "test-weapons", new[] { "a1_krissvector" }).Weapons);
            Assert.Throws<InvalidDataException>(() =>
                RuntimeWeaponCatalog.ParseForTests(Json, "test.weapon",
                    "test-weapons", Array.Empty<string>()));
        }

        [Theory]
        [InlineData("7500", "true")]
        [InlineData("7500", "-1")]
        [InlineData("7500", "1.5")]
        [InlineData("7500", "2000000001")]
        [InlineData("\"schema_version\":1", "\"schema_version\":1.0")]
        [InlineData("\"schema_version\":1", "\"schema_version\":true")]
        [InlineData("\"schema_version\":1", "\"schema_version\":2")]
        [InlineData("\"ammo_cost_per_round\":2", "\"ammo_cost_per_round\":1000001")]
        [InlineData("smgs", "throwables")]
        [InlineData("a1_krissvector", "../escape")]
        [InlineData("a1_krissvector", "base")]
        [InlineData("KRISS Vector", "~r~KRISS Vector")]
        [InlineData("WEAPON_A1_KRISS_VECTOR", "weapon_a1_kriss_vector")]
        [InlineData("test-weapons", "wrong-id")]
        [InlineData("\"price\":7500", "\"price\":7500,\"extra\":true")]
        [InlineData("\"price\":7500", "\"price\":7500,\"price\":0")]
        public void InvalidCatalogsFailClosed(string oldValue, string newValue)
        {
            Assert.Throws<InvalidDataException>(() => Parse(Json.Replace(oldValue, newValue)));
        }

        [Fact]
        public void DuplicateEntriesAndLimitsFailClosed()
        {
            int start = Json.IndexOf("[", StringComparison.Ordinal);
            string entry = Json.Substring(start + 1, Json.Length - start - 3);
            Assert.Throws<InvalidDataException>(() => Parse(
                Json.Substring(0, start + 1) + entry + "," + entry + "]}"));
            Assert.Throws<InvalidDataException>(() => Parse(
                Json.Substring(0, start + 1) + string.Join(",", Enumerable.Repeat(entry, 2049)) + "]}"));
            Assert.Throws<InvalidDataException>(() => Parse(new string(' ', RuntimeWeaponCatalog.MaximumBytes + 1)));
        }

        [Theory]
        [InlineData("WEAPON_SMG")]
        [InlineData("WEAPON_ALLIN1_SMOKE_RED")]
        public void AddonsCannotReplaceStockOrOfficialSmokeWeapons(string reserved)
        {
            var snapshot = RuntimeWeaponCatalog.Merge(new[] { Parse(Json.Replace(Weapon, reserved)) });
            Assert.Equal(RuntimeWeaponCatalog.Sort(WeaponList.All), snapshot.All);
            Assert.Equal(WeaponList.Prices["WEAPON_SMG"], snapshot.Prices["WEAPON_SMG"]);
        }

        [Fact]
        public void PackagePrecedenceIsStableAndRefreshRemovalDoesNotMutateBaseline()
        {
            var first = Parse(Json.Replace("KRISS Vector", "First"), "a.package");
            var second = Parse(Json.Replace("KRISS Vector", "Second"), "z.package");
            var result = RuntimeWeaponCatalog.Merge(new[] { second, first });
            Assert.Equal("First", result.DisplayNames[Weapon]);
            var removed = RuntimeWeaponCatalog.Merge(Array.Empty<RuntimeWeaponDocument>());
            Assert.DoesNotContain(Weapon, removed.All);
            Assert.False(removed.Prices.ContainsKey(Weapon));
            Assert.Contains(Weapon, result.All); // Older snapshot is never mutated.
            Assert.Equal(RuntimeWeaponCatalog.Sort(WeaponList.All), removed.All);
        }

        [Fact]
        public void ExactReadBytesMustMatchTheReceiptEvenAfterDiscovery()
        {
            string root = Path.Combine(Path.GetTempPath(), "allin1-weapon-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            string path = Path.Combine(root, "weapons.json");
            try
            {
                File.WriteAllText(path, Json, new UTF8Encoding(false));
                string digest = RuntimeExtensionRegistry.Sha256(path);
                var declaration = new GbayCatalogDeclaration("test.weapon", "test-weapons",
                    "weapon", "scripts/Test/weapons.json", path, digest,
                    new[] { "a1_krissvector" });
                Assert.Equal(Weapon, Assert.Single(RuntimeWeaponCatalog.Load(declaration).Weapons).Weapon);
                Assert.Throws<InvalidDataException>(() => RuntimeWeaponCatalog.Load(
                    new GbayCatalogDeclaration("test.weapon", "test-weapons", "weapon",
                        "scripts/Test/weapons.json", path, digest,
                        Array.Empty<string>())));
                File.WriteAllText(path, Json.Replace("7500", "0"), new UTF8Encoding(false));
                Assert.Throws<InvalidDataException>(() => RuntimeWeaponCatalog.Load(declaration));
                Assert.Throws<InvalidDataException>(() => RuntimeWeaponCatalog.Load(
                    new GbayCatalogDeclaration("test.weapon", "test-weapons", "weapon", "scripts/Test/weapons.json", path)));
                File.Delete(path);
                Assert.Throws<InvalidDataException>(() => RuntimeWeaponCatalog.Load(declaration));
            }
            finally { Directory.Delete(root, true); }
        }

        [Fact]
        public void Authorization_fingerprint_includes_contained_source_and_declared_packs()
        {
            string root = Path.Combine(Path.GetTempPath(), "allin1-weapon-fingerprint-" +
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            string firstPath = Path.Combine(root, "one.json");
            string secondPath = Path.Combine(root, "two.json");
            try
            {
                File.WriteAllText(firstPath, Json, new UTF8Encoding(false));
                File.WriteAllText(secondPath, Json, new UTF8Encoding(false));
                string digest = RuntimeExtensionRegistry.Sha256(firstPath);
                var first = new GbayCatalogDeclaration("test.weapon", "test-weapons",
                    "weapon", "scripts/Test/one.json", firstPath, digest,
                    new[] { "a1_krissvector" });
                var revokedPack = new GbayCatalogDeclaration("test.weapon", "test-weapons",
                    "weapon", "scripts/Test/one.json", firstPath, digest,
                    Array.Empty<string>());
                var relocated = new GbayCatalogDeclaration("test.weapon", "test-weapons",
                    "weapon", "scripts/Test/two.json", secondPath, digest,
                    new[] { "a1_krissvector" });
                string baseline = RuntimeWeaponCatalog.AuthorizationFingerprintForTests(
                    new[] { first });
                Assert.NotEqual(baseline,
                    RuntimeWeaponCatalog.AuthorizationFingerprintForTests(new[] { revokedPack }));
                Assert.NotEqual(baseline,
                    RuntimeWeaponCatalog.AuthorizationFingerprintForTests(new[] { relocated }));
            }
            finally { Directory.Delete(root, true); }
        }
    }
}
