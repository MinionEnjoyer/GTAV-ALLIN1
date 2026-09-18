// Receipt-authorized add-on firearms shared by native GBAY and Reactor.
// The generated WeaponList remains the immutable stock baseline.
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace ALLIN1
{
    internal sealed class RuntimeWeaponEntry
    {
        internal string PackageId, Weapon, Name, Category, SourcePack;
        internal int Price, AmmoCostPerRound;
    }

    internal sealed class RuntimeWeaponDocument
    {
        internal string PackageId, Id;
        internal RuntimeWeaponEntry[] Weapons;
    }

    internal sealed class RuntimeWeaponSnapshot
    {
        internal readonly IReadOnlyDictionary<string, string> DisplayNames, CategoryNames;
        internal readonly IReadOnlyDictionary<string, int> Prices, PurchaseQuantities, AmmoCostPerRound;
        internal readonly string[] All;
        internal readonly IReadOnlyDictionary<string, RuntimeWeaponEntry> PopulationEntries;

        internal RuntimeWeaponSnapshot(IEnumerable<RuntimeWeaponEntry> entries)
        {
            RuntimeWeaponEntry[] populationEntries = entries.ToArray();
            var names = new Dictionary<string, string>(WeaponList.DisplayNames, StringComparer.OrdinalIgnoreCase);
            var categories = new Dictionary<string, string>(WeaponList.CategoryNames, StringComparer.OrdinalIgnoreCase);
            var prices = new Dictionary<string, int>(WeaponList.Prices, StringComparer.OrdinalIgnoreCase);
            var quantities = new Dictionary<string, int>(WeaponList.PurchaseQuantities, StringComparer.OrdinalIgnoreCase);
            var ammo = new Dictionary<string, int>(WeaponList.AmmoCostPerRound, StringComparer.OrdinalIgnoreCase);
            var all = WeaponList.All.ToList();
            foreach (RuntimeWeaponEntry entry in populationEntries)
            {
                names.Add(entry.Weapon, entry.Name);
                categories.Add(entry.Weapon, RuntimeWeaponCatalog.CategoryLabels[entry.Category]);
                prices.Add(entry.Weapon, entry.Price);
                quantities.Add(entry.Weapon, 1); // v1 is firearms, not throwable bundles.
                ammo.Add(entry.Weapon, entry.AmmoCostPerRound);
                all.Add(entry.Weapon);
            }
            DisplayNames = new ReadOnlyDictionary<string, string>(names);
            CategoryNames = new ReadOnlyDictionary<string, string>(categories);
            Prices = new ReadOnlyDictionary<string, int>(prices);
            PurchaseQuantities = new ReadOnlyDictionary<string, int>(quantities);
            AmmoCostPerRound = new ReadOnlyDictionary<string, int>(ammo);
            All = RuntimeWeaponCatalog.Sort(all, categories, names);
            PopulationEntries = new ReadOnlyDictionary<string, RuntimeWeaponEntry>(
                populationEntries.ToDictionary(item => RuntimeWeaponCatalog.PopulationKey(
                    item.PackageId, item.Weapon), item => item,
                    StringComparer.OrdinalIgnoreCase));
        }

        internal string[] Category(string label) =>
            All.Where(id => CategoryNames.TryGetValue(id, out string category) &&
                category == label).ToArray();
    }

    internal static class RuntimeWeaponCatalog
    {
        internal const int MaximumBytes = 4 * 1024 * 1024;
        internal const int MaximumEntries = 2048;
        internal static readonly IReadOnlyDictionary<string, string> CategoryLabels =
            new ReadOnlyDictionary<string, string>(new Dictionary<string, string>
            {
                { "pistols", "Pistols" }, { "smgs", "SMGs" },
                { "shotguns", "Shotguns" }, { "rifles", "Assault Rifles" },
                { "machineguns", "Machine Guns" }, { "snipers", "Sniper Rifles" },
                { "heavy", "Heavy Weapons" },
            });
        private static readonly Regex Identifier = new Regex(@"\A[a-z0-9][a-z0-9._-]{1,63}\z");
        private static readonly Regex WeaponId = new Regex(@"\AWEAPON_[A-Z0-9_]{1,56}\z");
        private static readonly Regex PackId = new Regex(@"\A[a-z0-9][a-z0-9_-]{0,63}\z");
        private static volatile RuntimeWeaponSnapshot _snapshot =
            new RuntimeWeaponSnapshot(Array.Empty<RuntimeWeaponEntry>());
        private static string _authorizationFingerprint = "";

        internal static string[] All => (string[])_snapshot.All.Clone();
        internal static string[] Pistols => _snapshot.Category("Pistols");
        internal static string[] Smgs => _snapshot.Category("SMGs");
        internal static string[] Shotguns => _snapshot.Category("Shotguns");
        internal static string[] Rifles => _snapshot.Category("Assault Rifles");
        internal static string[] MachineGuns => _snapshot.Category("Machine Guns");
        internal static string[] Snipers => _snapshot.Category("Sniper Rifles");
        internal static string[] Heavy => _snapshot.Category("Heavy Weapons");
        internal static string[] Melee => _snapshot.Category("Melee");
        internal static string[] Throwables => _snapshot.Category("Throwables");
        internal static string[] Misc => (string[])WeaponList.Misc.Clone();
        internal static IReadOnlyDictionary<string, string> DisplayNames => _snapshot.DisplayNames;
        internal static IReadOnlyDictionary<string, string> CategoryNames => _snapshot.CategoryNames;
        internal static IReadOnlyDictionary<string, int> Prices => _snapshot.Prices;
        internal static IReadOnlyDictionary<string, int> PurchaseQuantities => _snapshot.PurchaseQuantities;
        internal static IReadOnlyDictionary<string, int> AmmoCostPerRound => _snapshot.AmmoCostPerRound;
        // v1 add-ons use the existing no-artwork fallback; never borrow a stock gun's image.
        internal static IReadOnlyDictionary<string, string> PreviewDict => WeaponList.PreviewDict;

        // Population policy needs exact package ownership.  A catalog name
        // alone is not authorization: only the current receipt-hashed runtime
        // snapshot may supply a replacement firearm.
        internal static bool TryGetPopulationEntry(string packageId, string weapon,
            out RuntimeWeaponEntry entry) => _snapshot.PopulationEntries.TryGetValue(
                PopulationKey(packageId, weapon), out entry);

        internal static bool TryGetPrice(string weapon, out int price) =>
            _snapshot.Prices.TryGetValue(weapon ?? "", out price);

        // Catalog v1 authorizes firearms, not model/material cosmetic variants.
        // Native tint counts can be inherited from a donor whose palette the
        // replacement model never uses. Do not sell those unproven finishes.
        internal static int SupportedTintCount(string weapon, int nativeCount) =>
            weapon != null && WeaponList.DisplayNames.ContainsKey(weapon)
                ? Math.Max(0, Math.Min(32, nativeCount)) : 0;

        internal static string[] Sort(IEnumerable<string> weapons,
            IReadOnlyDictionary<string, string> categories = null,
            IReadOnlyDictionary<string, string> names = null)
        {
            categories = categories ?? _snapshot.CategoryNames;
            names = names ?? _snapshot.DisplayNames;
            string[] order = { "Pistols", "SMGs", "Shotguns", "Assault Rifles",
                "Machine Guns", "Sniper Rifles", "Heavy Weapons", "Melee",
                "Throwables", "Miscellaneous" };
            return weapons.Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(id => {
                    string category = SmokeGrenadeCatalog.IsProduct(id) ? "Throwables"
                        : categories.TryGetValue(id, out string label) ? label : "Miscellaneous";
                    int rank = Array.IndexOf(order, category);
                    return rank < 0 ? order.Length : rank;
                })
                .ThenBy(id => SmokeGrenadeCatalog.TryGetProduct(id, out SmokeGrenadeProduct product)
                    ? product.DisplayName : names.TryGetValue(id, out string name) ? name : id,
                    StringComparer.OrdinalIgnoreCase)
                .ThenBy(id => id, StringComparer.Ordinal).ToArray();
        }

        internal static void Refresh()
        {
            _authorizationFingerprint = "";
            RefreshIfChanged();
        }

        internal static bool RefreshIfChanged()
        {
            var documents = new List<RuntimeWeaponDocument>();
            var declarations = new List<GbayCatalogDeclaration>();
            try
            {
                declarations.AddRange(Allin1ExtensionApi.GetRuntimeCatalogs("weapon"));
            }
            catch (Exception ex)
            {
                ClientLog.Error("WeaponCatalog", "catalog_discovery_failed", ex);
            }
            string fingerprint = AuthorizationFingerprint(declarations);
            if (string.Equals(fingerprint, _authorizationFingerprint,
                    StringComparison.Ordinal)) return false;
            foreach (GbayCatalogDeclaration declaration in declarations)
            {
                try { documents.Add(Load(declaration)); }
                catch (Exception ex)
                {
                    ClientLog.Error("WeaponCatalog", "catalog_rejected", ex,
                        new Dictionary<string, object> {
                            { "package", declaration.PackageId },
                            { "catalog", declaration.Id },
                        });
                }
            }
            // Rebuild, don't append: disabled/tampered/missing catalogs lose purchase authority.
            _snapshot = Merge(documents);
            _authorizationFingerprint = fingerprint;
            return true;
        }

        private static string AuthorizationFingerprint(
            IEnumerable<GbayCatalogDeclaration> declarations)
        {
            var values = new List<string>();
            foreach (GbayCatalogDeclaration declaration in declarations
                .OrderBy(value => value.PackageId, StringComparer.Ordinal)
                .ThenBy(value => value.Id, StringComparer.Ordinal))
            {
                try
                {
                    var info = new FileInfo(declaration.SourcePath);
                    if (!info.Exists || info.Length < 2 ||
                        info.Length > MaximumBytes)
                    {
                        values.Add(declaration.PackageId + "/" + declaration.Id +
                            ":invalid");
                        continue;
                    }
                    values.Add(declaration.PackageId + "/" + declaration.Id + ":" +
                        declaration.ExpectedSha256 + ":" +
                        RuntimeExtensionRegistry.Sha256(declaration.SourcePath) + ":" +
                        declaration.SourcePath + ":" + string.Join(",",
                            declaration.DeclaredDlcPacks.OrderBy(value => value,
                                StringComparer.OrdinalIgnoreCase)));
                }
                catch (Exception ex) when (ex is IOException ||
                    ex is UnauthorizedAccessException ||
                    ex is CryptographicException)
                {
                    values.Add(declaration.PackageId + "/" + declaration.Id +
                        ":unreadable");
                }
            }
            return string.Join("|", values);
        }

        // A test seam for the identity fields which deliberately include
        // receipt-authorized pack scope and the resolved contained source.
        internal static string AuthorizationFingerprintForTests(
            IEnumerable<GbayCatalogDeclaration> declarations)
        {
            return AuthorizationFingerprint(declarations);
        }

        internal static RuntimeWeaponDocument Load(GbayCatalogDeclaration declaration)
        {
            if (!declaration.Exists || new FileInfo(declaration.SourcePath).Length > MaximumBytes)
                throw new InvalidDataException("Missing or oversized weapon catalog");
            byte[] bytes;
            using (var stream = new FileStream(declaration.SourcePath, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (stream.Length < 2 || stream.Length > MaximumBytes)
                    throw new InvalidDataException("Weapon catalog exceeds its byte limit");
                bytes = new byte[(int)stream.Length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    int count = stream.Read(bytes, offset, bytes.Length - offset);
                    if (count == 0) throw new EndOfStreamException();
                    offset += count;
                }
            }
            using (var hash = SHA256.Create())
            {
                string digest = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
                if (!string.Equals(digest, declaration.ExpectedSha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Weapon catalog bytes are not receipt-authorized");
            }
            return Parse(new UTF8Encoding(false, true).GetString(bytes),
                declaration.PackageId, declaration.Id, new HashSet<string>(
                    declaration.DeclaredDlcPacks,
                    StringComparer.OrdinalIgnoreCase));
        }

        internal static RuntimeWeaponDocument Parse(string json, string packageId, string catalogId)
        {
            return Parse(json, packageId, catalogId, null);
        }

        internal static RuntimeWeaponDocument ParseForTests(string json,
            string packageId, string catalogId,
            IEnumerable<string> declaredDlcPacks)
        {
            return Parse(json, packageId, catalogId, new HashSet<string>(
                declaredDlcPacks ?? Array.Empty<string>(),
                StringComparer.OrdinalIgnoreCase));
        }

        private static RuntimeWeaponDocument Parse(string json, string packageId,
            string catalogId, HashSet<string> declaredDlcPacks)
        {
            if (!Identifier.IsMatch(packageId ?? "") || !Identifier.IsMatch(catalogId ?? "") ||
                json == null || Encoding.UTF8.GetByteCount(json) > MaximumBytes)
                throw new InvalidDataException("Invalid catalog authorization or size");
            var root = Object(PortableJsonParser.Parse(json), "schema_version", "id", "name", "weapons");
            if (Integer(root["schema_version"], 1) != 1 || Text(root["id"]) != catalogId)
                throw new InvalidDataException("Unsupported schema or mismatched catalog id");
            Text(root["name"]);
            var entries = root["weapons"] as object[];
            if (entries == null || entries.Length < 1 || entries.Length > MaximumEntries)
                throw new InvalidDataException("Weapon catalog must contain 1 to 2048 entries");
            var hashes = new HashSet<uint>();
            var weapons = new List<RuntimeWeaponEntry>();
            foreach (object raw in entries)
            {
                var item = Object(raw, "weapon", "name", "category", "price", "ammo_cost_per_round", "source_pack");
                string weapon = Text(item["weapon"]);
                string category = Text(item["category"]);
                string pack = Text(item["source_pack"]);
                if (!WeaponId.IsMatch(weapon) || !PackId.IsMatch(pack) || pack == "base" ||
                    !CategoryLabels.ContainsKey(category) ||
                    (declaredDlcPacks != null && !declaredDlcPacks.Contains(pack)) ||
                    !hashes.Add(WeaponHash(weapon)))
                    throw new InvalidDataException("Invalid or duplicate add-on firearm identity/category");
                weapons.Add(new RuntimeWeaponEntry {
                    PackageId = packageId, Weapon = weapon, Name = Text(item["name"]), Category = category,
                    SourcePack = pack, Price = Integer(item["price"], 2000000000),
                    AmmoCostPerRound = Integer(item["ammo_cost_per_round"], 1000000),
                });
            }
            return new RuntimeWeaponDocument { PackageId = packageId, Id = catalogId, Weapons = weapons.ToArray() };
        }

        internal static RuntimeWeaponSnapshot Merge(IEnumerable<RuntimeWeaponDocument> documents)
        {
            var reserved = new HashSet<uint>(WeaponList.All
                .Concat(SmokeGrenadeCatalog.Products.Select(product => product.WeaponName))
                .Select(WeaponHash));
            var additions = new List<RuntimeWeaponEntry>();
            foreach (RuntimeWeaponDocument document in documents
                .OrderBy(item => item.PackageId, StringComparer.Ordinal)
                .ThenBy(item => item.Id, StringComparer.Ordinal))
            {
                // Whole-catalog rejection prevents partly installed conflicting catalogs.
                if (document.Weapons.Any(item => reserved.Contains(WeaponHash(item.Weapon))) ||
                    additions.Count + document.Weapons.Length > 8192)
                    continue;
                foreach (RuntimeWeaponEntry item in document.Weapons)
                {
                    reserved.Add(WeaponHash(item.Weapon));
                    additions.Add(item);
                }
            }
            return new RuntimeWeaponSnapshot(additions);
        }

        internal static uint WeaponHash(string value)
        {
            uint hash = 0;
            unchecked
            {
                foreach (char c in value.ToLowerInvariant())
                { hash += c; hash += hash << 10; hash ^= hash >> 6; }
                hash += hash << 3; hash ^= hash >> 11; hash += hash << 15;
            }
            return hash;
        }

        internal static string PopulationKey(string packageId, string weapon)
        {
            return (packageId ?? "").Trim().ToLowerInvariant() + "/" +
                (weapon ?? "").Trim().ToUpperInvariant();
        }

        private static Dictionary<string, object> Object(object value, params string[] fields)
        {
            var result = value as Dictionary<string, object>;
            if (result == null || result.Count != fields.Length || fields.Any(field => !result.ContainsKey(field)))
                throw new InvalidDataException("Unexpected or missing weapon catalog fields");
            return result;
        }

        private static string Text(object value)
        {
            string text = value as string;
            if (string.IsNullOrWhiteSpace(text) || text != text.Trim() || text.Length > 128 ||
                text.Any(c => c < 32 || c == '~'))
                throw new InvalidDataException("Invalid catalog text");
            return text;
        }

        private static int Integer(object value, int maximum)
        {
            if (!(value is int number) || number < 0 || number > maximum)
                throw new InvalidDataException("Invalid catalog integer");
            return number;
        }
    }
}
