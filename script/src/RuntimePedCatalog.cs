// Receipt-authorized custom-ped catalog consumed only by PedPopulationSpawner.
// It intentionally does not register a GBAY listing or storefront route.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace ALLIN1
{
    internal sealed class RuntimePedRecord
    {
        internal RuntimePedRecord(string packageId, string catalogId,
            string model, string name, string sourcePack)
        {
            PackageId = packageId;
            CatalogId = catalogId;
            Model = model;
            Name = name;
            SourcePack = sourcePack;
        }

        internal string PackageId { get; private set; }
        internal string CatalogId { get; private set; }
        internal string Model { get; private set; }
        internal string Name { get; private set; }
        internal string SourcePack { get; private set; }
    }

    internal static class RuntimePedCatalog
    {
        private const int MaximumCatalogBytes = 4 * 1024 * 1024;
        private const int MaximumPedsPerCatalog = 2048;
        private static readonly Regex Identifier = new Regex(
            "^[a-z][a-z0-9._-]{1,95}$", RegexOptions.CultureInvariant);
        private static readonly Regex ModelName = new Regex(
            "^[a-z0-9_]{1,64}$", RegexOptions.CultureInvariant);
        private static readonly Regex Digest = new Regex(
            "^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
        private static readonly object Sync = new object();
        private static Dictionary<string, RuntimePedRecord> _records =
            new Dictionary<string, RuntimePedRecord>(StringComparer.OrdinalIgnoreCase);

        internal static IReadOnlyList<RuntimePedRecord> Records
        {
            get
            {
                lock (Sync)
                    return _records.Values.OrderBy(value => value.PackageId,
                        StringComparer.OrdinalIgnoreCase).ThenBy(value => value.Model,
                        StringComparer.OrdinalIgnoreCase).ToArray();
            }
        }

        internal static bool TryGet(string packageId, string model,
            out RuntimePedRecord record)
        {
            string key = Key(packageId, model);
            lock (Sync) return _records.TryGetValue(key, out record);
        }

        internal static void Refresh()
        {
            var accepted = new Dictionary<string, RuntimePedRecord>(
                StringComparer.OrdinalIgnoreCase);
            foreach (GbayCatalogDeclaration declaration in
                Allin1ExtensionApi.GetRuntimeCatalogs("ped"))
            {
                try
                {
                    foreach (RuntimePedRecord record in Load(declaration))
                    {
                        string key = Key(record.PackageId, record.Model);
                        if (accepted.ContainsKey(key))
                            throw new InvalidDataException(
                                "Duplicate ped model in one package: " + record.Model);
                        accepted.Add(key, record);
                    }
                }
                catch (Exception ex) when (ex is IOException ||
                    ex is UnauthorizedAccessException || ex is CryptographicException ||
                    ex is InvalidDataException || ex is FormatException)
                {
                    ClientLog.Warn("PedPopulation", "catalog_rejected",
                        new Dictionary<string, object>
                        {
                            { "package_id", declaration.PackageId },
                            { "catalog_id", declaration.Id ?? "" },
                            { "reason", ex.Message },
                        });
                }
            }
            lock (Sync) _records = accepted;
        }

        internal static IReadOnlyList<RuntimePedRecord> ParseForTests(
            string json, string packageId, string catalogId,
            IEnumerable<string> declaredDlcPacks)
        {
            return Parse(json, packageId, catalogId, new HashSet<string>(
                declaredDlcPacks ?? Array.Empty<string>(),
                StringComparer.OrdinalIgnoreCase));
        }

        private static IReadOnlyList<RuntimePedRecord> Load(
            GbayCatalogDeclaration declaration)
        {
            if (declaration == null || !declaration.Exists ||
                !Digest.IsMatch(declaration.ExpectedSha256 ?? ""))
                throw new InvalidDataException("Ped catalog lacks receipt authorization");
            byte[] bytes;
            using (var stream = new FileStream(declaration.SourcePath,
                FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                if (stream.Length < 2 || stream.Length > MaximumCatalogBytes)
                    throw new InvalidDataException("Ped catalog exceeds its 4 MiB limit");
                bytes = new byte[(int)stream.Length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    int read = stream.Read(bytes, offset, bytes.Length - offset);
                    if (read == 0) throw new EndOfStreamException("Ped catalog ended early");
                    offset += read;
                }
            }
            if (!string.Equals(
                    Sha256(bytes), declaration.ExpectedSha256,
                    StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Ped catalog failed its receipt hash");
            // Carry the receipt-authorized pack set obtained with this catalog
            // declaration. Do not reread the mutable registry after bytes were
            // selected and hashed.
            return Parse(Encoding.UTF8.GetString(bytes), declaration.PackageId,
                declaration.Id, new HashSet<string>(declaration.DeclaredDlcPacks,
                    StringComparer.OrdinalIgnoreCase));
        }

        private static IReadOnlyList<RuntimePedRecord> Parse(string json,
            string packageId, string catalogId, HashSet<string> declaredPacks)
        {
            string package = IdentifierValue(packageId, "ped package id");
            string catalog = IdentifierValue(catalogId, "ped catalog id");
            Dictionary<string, object> root = Object(PortableJsonParser.Parse(json),
                "ped catalog");
            ExactFields(root, "ped catalog", new[] {
                "schema_version", "id", "name", "peds"
            });
            if (Integer(root, "schema_version") != 1)
                throw new InvalidDataException("Unsupported ped catalog schema version");
            if (!string.Equals(IdentifierValue(Text(root, "id"), "ped catalog id"),
                    catalog, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Ped catalog id does not match declaration");
            BoundedText(root, "name", 1, 128);
            object[] rows = JsonArray(Value(root, "peds"), "ped catalog peds");
            if (rows.Length < 1 || rows.Length > MaximumPedsPerCatalog)
                throw new InvalidDataException("Ped catalog has an unsupported entry count");
            var result = new List<RuntimePedRecord>(rows.Length);
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (object value in rows)
            {
                Dictionary<string, object> row = Object(value, "ped catalog entry");
                ExactFields(row, "ped catalog entry", new[] {
                    "model", "name", "source_pack"
                });
                string model = ModelValue(Text(row, "model"));
                if (!seen.Add(model))
                    throw new InvalidDataException("Ped catalog contains duplicate model: " + model);
                string name = BoundedText(row, "name", 1, 128);
                string sourcePack = IdentifierValue(Text(row, "source_pack"),
                    "ped source_pack");
                if (declaredPacks == null || !declaredPacks.Contains(sourcePack))
                    throw new InvalidDataException(
                        "Ped source_pack is not declared by its package: " + sourcePack);
                result.Add(new RuntimePedRecord(package, catalog, model, name,
                    sourcePack));
            }
            return result;
        }

        private static string Key(string packageId, string model)
        {
            return (packageId ?? "").Trim().ToLowerInvariant() + "/" +
                (model ?? "").Trim().ToLowerInvariant();
        }

        private static string Sha256(byte[] data)
        {
            using (SHA256 hash = SHA256.Create())
                return string.Concat(hash.ComputeHash(data).Select(
                    value => value.ToString("x2")));
        }

        private static string IdentifierValue(string value, string label)
        {
            string result = (value ?? "").Trim().ToLowerInvariant();
            if (!Identifier.IsMatch(result))
                throw new InvalidDataException(label + " is invalid");
            return result;
        }

        private static string ModelValue(string value)
        {
            string result = (value ?? "").Trim().ToLowerInvariant();
            if (!ModelName.IsMatch(result))
                throw new InvalidDataException("Ped model is invalid");
            return result;
        }

        private static Dictionary<string, object> Object(object value, string label)
        {
            if (!(value is Dictionary<string, object> result))
                throw new InvalidDataException(label + " must be an object");
            return result;
        }

        private static object[] JsonArray(object value, string label)
        {
            if (!(value is object[] result))
                throw new InvalidDataException(label + " must be an array");
            return result;
        }

        private static object Value(Dictionary<string, object> value, string key)
        {
            if (!value.TryGetValue(key, out object result))
                throw new InvalidDataException("Missing required field: " + key);
            return result;
        }

        private static string Text(Dictionary<string, object> value, string key)
        {
            if (!(Value(value, key) is string result) || string.IsNullOrWhiteSpace(result))
                throw new InvalidDataException(key + " must be non-empty text");
            return result;
        }

        private static string BoundedText(Dictionary<string, object> value,
            string key, int minimum, int maximum)
        {
            string result = Text(value, key).Trim();
            if (result.Length < minimum || result.Length > maximum)
                throw new InvalidDataException(key + " length is outside supported range");
            return result;
        }

        private static int Integer(Dictionary<string, object> value, string key)
        {
            object raw = Value(value, key);
            if (raw is bool || !(raw is int result))
                throw new InvalidDataException(key + " must be an integer");
            return result;
        }

        private static void ExactFields(Dictionary<string, object> value,
            string label, IEnumerable<string> fields)
        {
            var allowed = new HashSet<string>(fields, StringComparer.Ordinal);
            if (value.Keys.Any(key => !allowed.Contains(key)) ||
                allowed.Any(key => !value.ContainsKey(key)))
                throw new InvalidDataException(label + " has unsupported or missing fields");
        }
    }
}
