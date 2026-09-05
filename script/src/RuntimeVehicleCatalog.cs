// Receipt-authorized vehicle catalogs consumed by GBAY and ambient traffic.
//
// Catalog files are data only. The launcher owns their paths and hashes in the
// extension registry; this reader applies a second bounded, strict validation
// pass before any model is exposed to the game client.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal sealed class GbayVehicleRecord
    {
        internal GbayVehicleRecord(
            string packageId, string catalogId, string model, string name,
            string manufacturer, string category, int price, string storage,
            string sourcePack, int sizeTier, string previewDictionary,
            string previewTexture, bool trafficEnabled, double trafficWeight)
        {
            PackageId = packageId;
            CatalogId = catalogId;
            Model = model;
            Name = name;
            Manufacturer = manufacturer;
            Category = category;
            Price = price;
            Storage = storage;
            SourcePack = sourcePack;
            SizeTier = sizeTier;
            PreviewDictionary = previewDictionary;
            PreviewTexture = previewTexture;
            TrafficEnabled = trafficEnabled;
            TrafficWeight = trafficWeight;
        }

        internal string PackageId { get; }
        internal string CatalogId { get; }
        internal string Model { get; }
        internal string Name { get; }
        internal string Manufacturer { get; }
        internal string Category { get; }
        internal int Price { get; }
        internal string Storage { get; }
        internal string SourcePack { get; }
        internal int SizeTier { get; }
        internal string PreviewDictionary { get; }
        internal string PreviewTexture { get; }
        internal bool TrafficEnabled { get; }
        internal double TrafficWeight { get; }
        internal bool HasValidatedRuntimeVehicleClass { get; private set; }
        internal VehicleClass ValidatedRuntimeVehicleClass { get; private set; }

        internal void SetValidatedRuntimeVehicleClass(VehicleClass vehicleClass)
        {
            ValidatedRuntimeVehicleClass = vehicleClass;
            HasValidatedRuntimeVehicleClass = true;
        }

        internal bool IsOfficialStoryVehicle =>
            string.Equals(PackageId,
                Allin1ExtensionApi.OnlineContentPackageId,
                StringComparison.OrdinalIgnoreCase) &&
            string.Equals(SourcePack, "base",
                StringComparison.OrdinalIgnoreCase);
    }

    internal sealed class RuntimeVehicleCatalogDocument
    {
        internal RuntimeVehicleCatalogDocument(
            string packageId, string catalogId, string name,
            IReadOnlyList<GbayVehicleRecord> vehicles)
        {
            PackageId = packageId;
            CatalogId = catalogId;
            Name = name;
            Vehicles = vehicles;
        }

        internal string PackageId { get; }
        internal string CatalogId { get; }
        internal string Name { get; }
        internal IReadOnlyList<GbayVehicleRecord> Vehicles { get; }
    }

    internal static class RuntimeVehicleCatalog
    {
        private const int MaximumCatalogBytes = 4 * 1024 * 1024;
        private const int MaximumVehiclesPerCatalog = 2048;
        // The per-catalog contract is 2,048. Keep a separate bounded merged
        // ceiling so the 256-entry official Story catalog plus at least one
        // maximum-size third-party catalog can coexist without silent loss.
        private const int MaximumDynamicVehicles = 8192;
        private const int MaximumPrice = 2000000000;
        private const double MinimumTrafficWeight = 0.1;
        private const double MaximumTrafficWeight = 20.0;
        private const ulong GetMakeNameFromVehicleModelNative =
            0xF7AF4F159FF99F97UL;

        private static readonly object Sync = new object();
        private static readonly Regex Identifier = new Regex(
            "^[a-z0-9][a-z0-9._-]{1,95}$",
            RegexOptions.CultureInvariant);
        private static readonly Regex ModelIdentifier = new Regex(
            "^[a-z0-9][a-z0-9_-]{0,63}$",
            RegexOptions.CultureInvariant);
        private static readonly Regex AssetIdentifier = new Regex(
            "^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$",
            RegexOptions.CultureInvariant);
        private static readonly Regex PackIdentifier = new Regex(
            "^(base|[a-z0-9][a-z0-9_-]{0,63})$",
            RegexOptions.CultureInvariant);

        private static readonly HashSet<string> Categories =
            new HashSet<string>(new[]
            {
                "compacts", "coupes", "sedans", "suvs", "muscle",
                "sports", "sportsclassics", "super", "offroad",
                "motorcycles", "vans", "boats", "helicopters", "planes",
                "military", "industrial", "openwheel", "emergency",
                "cycles", "service", "special",
            }, StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> RoadTrafficCategories =
            new HashSet<string>(new[]
            {
                "compacts", "coupes", "sedans", "suvs", "muscle",
                "sports", "sportsclassics", "super", "offroad",
                "motorcycles", "vans",
            }, StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> StorageKinds =
            new HashSet<string>(new[]
            {
                "garage", "helipad", "harbour", "hangar",
            },
                StringComparer.OrdinalIgnoreCase);
        private static Dictionary<string, GbayVehicleRecord> _records =
            new Dictionary<string, GbayVehicleRecord>(
                StringComparer.OrdinalIgnoreCase);
        private static Dictionary<int, GbayVehicleRecord> _recordsByHash =
            new Dictionary<int, GbayVehicleRecord>();
        private static IReadOnlyList<string> _allDynamicModels =
            Array.Empty<string>();
        private static IReadOnlyList<GbayVehicleRecord> _trafficEntries =
            Array.Empty<GbayVehicleRecord>();
        private static readonly Dictionary<string, string> LocalizedNames =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, string> LocalizedManufacturers =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static bool _initialized;

        internal static IReadOnlyList<string> AllDynamicModels
        {
            get
            {
                EnsureInitialized();
                lock (Sync) return _allDynamicModels.ToArray();
            }
        }

        /// <summary>
        /// Dynamic, receipt-authorized traffic records whose catalog item and
        /// package traffic setting are both enabled. Static VehicleList pools
        /// remain owned by TrafficSpawner.
        /// </summary>
        internal static IReadOnlyList<GbayVehicleRecord> TrafficEntries
        {
            get
            {
                EnsureInitialized();
                lock (Sync) return _trafficEntries.ToArray();
            }
        }

        internal static void Refresh()
        {
            var documents = new List<RuntimeVehicleCatalogDocument>();
            try
            {
                foreach (string packageId in
                    Allin1ExtensionApi.GetEnabledPackageIds()
                        .OrderBy(value => value,
                            StringComparer.OrdinalIgnoreCase))
                {
                    bool trafficSetting = Allin1ExtensionApi.GetBooleanSetting(
                        packageId, "traffic_enabled", false);
                    bool trafficCapability = Allin1ExtensionApi.HasCapability(
                        packageId, "traffic.catalog");
                    foreach (GbayCatalogDeclaration declaration in
                        Allin1ExtensionApi.GetGbayCatalogs(packageId)
                            .Where(value => string.Equals(
                                value.Kind, "vehicle",
                                StringComparison.OrdinalIgnoreCase))
                            .OrderBy(value => value.Id,
                                StringComparer.OrdinalIgnoreCase))
                    {
                        try
                        {
                            documents.Add(Load(
                                declaration, trafficSetting,
                                trafficCapability));
                        }
                        catch (Exception ex)
                        {
                            ClientLog.Error("VehicleCatalog",
                                "catalog_rejected", ex,
                                new Dictionary<string, object>
                                {
                                    { "package", packageId },
                                    { "catalog", declaration.Id },
                                    { "source", declaration.Source },
                                });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("VehicleCatalog", "catalog_discovery_failed", ex);
            }

            ApplyDocuments(documents, RuntimeModelMatchesRecord);
        }

        private static void EnsureInitialized()
        {
            lock (Sync)
            {
                if (_initialized) return;
            }
            Refresh();
        }

        private static RuntimeVehicleCatalogDocument Load(
            GbayCatalogDeclaration declaration, bool trafficSetting,
            bool trafficCapability)
        {
            if (declaration == null || !declaration.Exists)
                throw new InvalidDataException("Vehicle catalog file is missing");
            var info = new FileInfo(declaration.SourcePath);
            if (info.Length < 2 || info.Length > MaximumCatalogBytes)
                throw new InvalidDataException(
                    "Vehicle catalog is empty or exceeds its 4 MiB limit");
            string json;
            if (!EarlyStartupSnapshot.TryGetTextByPath(
                    declaration.Source, out json))
                json = File.ReadAllText(declaration.SourcePath);
            return Parse(json, declaration.PackageId, declaration.Id,
                trafficSetting, trafficCapability);
        }

        internal static RuntimeVehicleCatalogDocument ParseForTests(
            string json, string packageId, string catalogId,
            bool trafficSetting = false, bool trafficCapability = false)
        {
            return Parse(json, packageId, catalogId,
                trafficSetting, trafficCapability);
        }

        private static RuntimeVehicleCatalogDocument Parse(
            string json, string packageId, string catalogId,
            bool trafficSetting, bool trafficCapability)
        {
            if (json == null || json.Length > MaximumCatalogBytes)
                throw new InvalidDataException(
                    "Vehicle catalog exceeds its 4 MiB limit");
            if (!IsIdentifier(packageId) || !IsIdentifier(catalogId))
                throw new InvalidDataException(
                    "Vehicle catalog authorization identity is invalid");

            Dictionary<string, object> root = Object(
                PortableJsonParser.Parse(json), "vehicle catalog");
            ExactFields(root, "vehicle catalog",
                new[] { "schema_version", "id", "name", "vehicles" });
            if (Integer(root, "schema_version") != 1)
                throw new InvalidDataException(
                    "Unsupported vehicle catalog schema version");
            string declaredId = LowerIdentifier(Text(root, "id"),
                "vehicle catalog id");
            if (!string.Equals(declaredId, catalogId,
                    StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(
                    "Vehicle catalog id does not match its authorized declaration");
            string catalogName = BoundedText(root, "name", 1, 128);
            object[] entries = JsonArray(Value(root, "vehicles"),
                "vehicle catalog vehicles");
            if (entries.Length == 0)
                throw new InvalidDataException(
                    "Vehicle catalog must contain at least one vehicle");
            if (entries.Length > MaximumVehiclesPerCatalog)
                throw new InvalidDataException(
                    "Vehicle catalog exceeds its 2048-item limit");

            var models = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var hashes = new HashSet<int>();
            var records = new List<GbayVehicleRecord>();
            foreach (object entryValue in entries)
            {
                Dictionary<string, object> entry = Object(
                    entryValue, "vehicle catalog entry");
                ExactFields(entry, "vehicle catalog entry", new[]
                {
                    "model", "name", "category", "price", "storage",
                    "source_pack",
                }, optional: new[]
                {
                    "manufacturer", "size_tier", "traffic",
                    "preview_dictionary", "preview_texture",
                });

                string model = Text(entry, "model").Trim().ToLowerInvariant();
                if (!ModelIdentifier.IsMatch(model) || !models.Add(model))
                    throw new InvalidDataException(
                        "Vehicle catalog contains an invalid or duplicate model: " +
                        model);
                int modelHash = ModelHash(model);
                if (!hashes.Add(modelHash))
                    throw new InvalidDataException(
                        "Vehicle catalog contains colliding model hashes");
                string name = BoundedText(entry, "name", 1, 128);
                string manufacturer = OptionalText(
                    entry, "manufacturer", "").Trim();
                if (manufacturer.Length > 96)
                    throw new InvalidDataException(
                        "manufacturer length is outside its supported range");
                string category = Text(entry, "category").Trim()
                    .ToLowerInvariant();
                if (!Categories.Contains(category))
                    throw new InvalidDataException(
                        "Vehicle catalog category is unsupported: " + category);
                int price = Integer(entry, "price");
                if (price < 0 || price > MaximumPrice)
                    throw new InvalidDataException(
                        "Vehicle catalog price must be between 0 and " +
                        MaximumPrice.ToString(CultureInfo.InvariantCulture));
                string storage = Text(entry, "storage").Trim()
                    .ToLowerInvariant();
                if (!StorageKinds.Contains(storage))
                    throw new InvalidDataException(
                        "Vehicle catalog storage is unsupported: " + storage);
                string expectedStorage = category == "boats" ? "harbour"
                    : category == "helicopters" ? "helipad"
                    : category == "planes" ? "hangar" : "garage";
                if (!string.Equals(storage, expectedStorage,
                        StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException(
                        "Vehicle catalog storage does not match category " +
                        category);
                string sourcePack = Text(entry, "source_pack").Trim()
                    .ToLowerInvariant();
                if (!PackIdentifier.IsMatch(sourcePack))
                    throw new InvalidDataException(
                        "vehicle source_pack is invalid");
                if (string.Equals(sourcePack, "base",
                        StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(packageId,
                        Allin1ExtensionApi.OnlineContentPackageId,
                        StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException(
                        "Only official Online Content may declare source_pack=base");
                int sizeTier = OptionalInteger(entry, "size_tier", 0);
                if (sizeTier < 0 || sizeTier > 2)
                    throw new InvalidDataException(
                        "Vehicle catalog size_tier must be 0, 1, or 2");
                string previewDictionary = OptionalText(
                    entry, "preview_dictionary", "").Trim();
                if (previewDictionary.Length > 0 &&
                    !AssetIdentifier.IsMatch(previewDictionary))
                    throw new InvalidDataException(
                        "Vehicle preview dictionary is invalid");
                string previewTexture = OptionalText(
                    entry, "preview_texture", "").Trim();
                if (previewTexture.Length > 0 &&
                    !AssetIdentifier.IsMatch(previewTexture))
                    throw new InvalidDataException(
                        "Vehicle preview texture is invalid");
                if (previewTexture.Length > 0 &&
                    previewDictionary.Length == 0)
                    throw new InvalidDataException(
                        "preview_texture requires preview_dictionary");

                Dictionary<string, object> traffic = entry.TryGetValue(
                        "traffic", out object rawTraffic)
                    ? Object(rawTraffic, "vehicle traffic policy")
                    : new Dictionary<string, object>();
                ExactFields(traffic, "vehicle traffic policy",
                    Array.Empty<string>(), optional: new[]
                    {
                        "enabled", "weight",
                    });
                bool itemTrafficEnabled = OptionalBoolean(
                    traffic, "enabled", false);
                double trafficWeight = OptionalNumber(
                    traffic, "weight", 1.0);
                if (trafficWeight < MinimumTrafficWeight ||
                    trafficWeight > MaximumTrafficWeight)
                    throw new InvalidDataException(
                        "Vehicle traffic weight must be between 0.1 and 20");
                if (itemTrafficEnabled && !trafficCapability)
                    throw new InvalidDataException(
                        "Traffic-enabled vehicle catalogs require traffic.catalog");
                if (itemTrafficEnabled &&
                    (!RoadTrafficCategories.Contains(category) ||
                     !string.Equals(storage, "garage",
                         StringComparison.OrdinalIgnoreCase)))
                    throw new InvalidDataException(
                        "Only road vehicles may opt into ambient traffic");

                records.Add(new GbayVehicleRecord(
                    packageId.ToLowerInvariant(), catalogId.ToLowerInvariant(),
                    model, name, manufacturer, category, price, storage,
                    sourcePack, sizeTier, previewDictionary, previewTexture,
                    itemTrafficEnabled && trafficSetting && trafficCapability,
                    trafficWeight));
            }
            return new RuntimeVehicleCatalogDocument(
                packageId.ToLowerInvariant(), catalogId.ToLowerInvariant(),
                catalogName, records.ToArray());
        }

        private static void ApplyDocuments(
            IEnumerable<RuntimeVehicleCatalogDocument> documents,
            Func<GbayVehicleRecord, bool> available)
        {
            var staticModels = new HashSet<string>(
                VehicleList.All, StringComparer.OrdinalIgnoreCase);
            var staticHashes = new HashSet<int>(
                VehicleList.All.Select(ModelHash));
            var records = new Dictionary<string, GbayVehicleRecord>(
                StringComparer.OrdinalIgnoreCase);
            var hashes = new HashSet<int>(staticHashes);

            IEnumerable<GbayVehicleRecord> ordered = documents
                .SelectMany(document => document.Vehicles)
                .OrderBy(record => record.IsOfficialStoryVehicle ? 0 : 1)
                .ThenBy(record => record.PackageId,
                    StringComparer.OrdinalIgnoreCase)
                .ThenBy(record => record.CatalogId,
                    StringComparer.OrdinalIgnoreCase)
                .ThenBy(record => record.Model,
                    StringComparer.OrdinalIgnoreCase);
            foreach (GbayVehicleRecord record in ordered)
            {
                int hash = ModelHash(record.Model);
                if (staticModels.Contains(record.Model) ||
                    records.ContainsKey(record.Model) || hashes.Contains(hash))
                {
                    // The official Story catalog deliberately describes base
                    // vehicles so GBAY can expose their metadata. A small
                    // subset is already present in the compiled compatibility
                    // list; that trusted mirror is expected, not a package
                    // authoring collision. Third-party and dynamic collisions
                    // remain visible and fail closed below.
                    if (ShouldReportModelCollision(
                            record, staticModels.Contains(record.Model)))
                    {
                        ClientLog.Warn("VehicleCatalog", "model_collision",
                            new Dictionary<string, object>
                            {
                                { "package", record.PackageId },
                                { "catalog", record.CatalogId },
                                { "model", record.Model },
                            });
                    }
                    continue;
                }
                if (records.Count >= MaximumDynamicVehicles)
                {
                    ClientLog.Warn("VehicleCatalog", "merged_limit_reached",
                        new Dictionary<string, object>
                        {
                            { "limit", MaximumDynamicVehicles },
                        });
                    break;
                }
                if (available != null && !available(record))
                {
                    ClientLog.Warn("VehicleCatalog", "model_unavailable",
                        new Dictionary<string, object>
                        {
                            { "package", record.PackageId },
                            { "catalog", record.CatalogId },
                            { "model", record.Model },
                        });
                    continue;
                }
                records.Add(record.Model, record);
                hashes.Add(hash);
            }

            GbayVehicleRecord[] values = records.Values
                .OrderBy(value => value.Model, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            lock (Sync)
            {
                _records = records;
                _recordsByHash = values.ToDictionary(
                    value => ModelHash(value.Model), value => value);
                _allDynamicModels = values.Select(value => value.Model).ToArray();
                _trafficEntries = values.Where(value => value.TrafficEnabled)
                    .ToArray();
                LocalizedNames.Clear();
                LocalizedManufacturers.Clear();
                _initialized = true;
            }
            ClientLog.Info("VehicleCatalog", "catalog_refreshed",
                new Dictionary<string, object>
                {
                    { "dynamic_models", values.Length },
                    { "traffic_models", _trafficEntries.Count },
                });
        }

        internal static bool ShouldReportModelCollision(
            GbayVehicleRecord record, bool conflictsWithStaticModel)
        {
            return record == null || !conflictsWithStaticModel ||
                !record.IsOfficialStoryVehicle;
        }

        internal static IReadOnlyList<GbayVehicleRecord> MergeForTests(
            IEnumerable<RuntimeVehicleCatalogDocument> documents,
            Func<GbayVehicleRecord, bool> available = null)
        {
            ApplyDocuments(documents ??
                Array.Empty<RuntimeVehicleCatalogDocument>(),
                available ?? (_ => true));
            lock (Sync) return _records.Values
                .OrderBy(value => value.Model, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }

        internal static bool TryGet(string model, out GbayVehicleRecord record)
        {
            EnsureInitialized();
            lock (Sync) return _records.TryGetValue(model ?? "", out record);
        }

        internal static bool TryGetByHash(
            int modelHash, out GbayVehicleRecord record)
        {
            EnsureInitialized();
            lock (Sync) return _recordsByHash.TryGetValue(modelHash, out record);
        }

        internal static bool IsListed(string model)
        {
            if (string.IsNullOrWhiteSpace(model)) return false;
            if (VehicleList.Prices.ContainsKey(model)) return true;
            return TryGet(model, out _);
        }

        internal static IReadOnlyList<string> GetCategoryModels(string category)
        {
            EnsureInitialized();
            category = (category ?? "all").Trim().ToLowerInvariant();
            IEnumerable<string> staticValues = StaticCategoryModels(category);
            GbayVehicleRecord[] dynamicValues;
            lock (Sync) dynamicValues = _records.Values
                .Where(value => category == "all" ||
                    string.Equals(value.Category, category,
                        StringComparison.OrdinalIgnoreCase))
                .OrderBy(value => value.Model, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            return staticValues.Concat(dynamicValues.Select(value => value.Model))
                .Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        }

        internal static string GetName(string model)
        {
            if (TryGet(model, out GbayVehicleRecord record))
            {
                if (record.IsOfficialStoryVehicle)
                {
                    lock (Sync)
                        if (LocalizedNames.TryGetValue(
                                model, out string cached)) return cached;
                    string resolved = TryGetLocalizedVehicleName(
                        model, out string localized) ? localized : record.Name;
                    lock (Sync) LocalizedNames[model] = resolved;
                    return resolved;
                }
                return record.Name;
            }
            if (!VehicleList.DisplayNames.TryGetValue(model ?? "",
                    out string display)) return model ?? "";
            int separator = display.IndexOf(' ');
            return separator > 0 && separator + 1 < display.Length
                ? display.Substring(separator + 1) : display;
        }

        internal static string GetManufacturer(string model)
        {
            if (TryGet(model, out GbayVehicleRecord record))
            {
                if (record.IsOfficialStoryVehicle)
                {
                    lock (Sync)
                        if (LocalizedManufacturers.TryGetValue(
                                model, out string cached)) return cached;
                    string resolved = TryGetLocalizedManufacturer(
                        model, out string localized)
                        ? localized : record.Manufacturer;
                    lock (Sync) LocalizedManufacturers[model] = resolved;
                    return resolved;
                }
                return record.Manufacturer;
            }
            if (!VehicleList.DisplayNames.TryGetValue(model ?? "",
                    out string display)) return "";
            int separator = display.IndexOf(' ');
            return separator > 0 ? display.Substring(0, separator) : "";
        }

        internal static string GetDisplayName(string model)
        {
            string name = GetName(model);
            string manufacturer = GetManufacturer(model);
            if (string.IsNullOrWhiteSpace(manufacturer) ||
                name.StartsWith(manufacturer + " ",
                    StringComparison.OrdinalIgnoreCase)) return name;
            return manufacturer + " " + name;
        }

        internal static string GetCategory(string model)
        {
            if (TryGet(model, out GbayVehicleRecord record))
                return record.Category;
            if (VehicleList.ClassNames.TryGetValue(model ?? "",
                    out string category))
                return NormalizeStaticCategory(category);
            return "special";
        }

        internal static int GetPrice(string model)
        {
            if (TryGet(model, out GbayVehicleRecord record)) return record.Price;
            return VehicleList.Prices.TryGetValue(model ?? "", out int price)
                ? price : 0;
        }

        internal static int GetSizeTier(string model)
        {
            if (TryGet(model, out GbayVehicleRecord record))
                return record.SizeTier;
            return VehicleList.GetSizeTier(model);
        }

        internal static string GetStorage(string model)
        {
            if (TryGet(model, out GbayVehicleRecord record))
                return record.Storage;
            if (Contains(VehicleList.Helicopters, model) ||
                string.Equals(model, "conada2",
                    StringComparison.OrdinalIgnoreCase)) return "helipad";
            if (Contains(VehicleList.Boats, model)) return "harbour";
            if (Contains(VehicleList.Planes, model) ||
                string.Equals(model, "raiju",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(model, "streamer216",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(model, "thruster",
                    StringComparison.OrdinalIgnoreCase)) return "hangar";
            return "garage";
        }

        internal static bool TryGetPreviewDictionary(
            string model, out string dictionary)
        {
            if (TryGet(model, out GbayVehicleRecord record) &&
                !string.IsNullOrWhiteSpace(record.PreviewDictionary))
            {
                dictionary = record.PreviewDictionary;
                return true;
            }
            return VehicleList.PreviewDict.TryGetValue(model ?? "", out dictionary);
        }

        internal static bool TryGetPreview(
            string model, out string dictionary, out string texture)
        {
            if (TryGet(model, out GbayVehicleRecord record) &&
                !string.IsNullOrWhiteSpace(record.PreviewDictionary))
            {
                dictionary = record.PreviewDictionary;
                texture = string.IsNullOrWhiteSpace(record.PreviewTexture)
                    ? record.Model : record.PreviewTexture;
                return true;
            }
            if (VehicleList.PreviewDict.TryGetValue(
                    model ?? "", out dictionary))
            {
                texture = model ?? "";
                return true;
            }
            texture = "";
            return false;
        }

        internal static bool IsModelAvailable(string model)
        {
            if (!IsListed(model)) return false;
            try
            {
                var runtimeModel = new Model(model);
                return runtimeModel.IsInCdImage && runtimeModel.IsVehicle;
            }
            catch (Exception ex)
            {
                ClientLog.Error("VehicleCatalog", "model_probe_failed", ex,
                    new Dictionary<string, object> { { "model", model ?? "" } });
                return false;
            }
        }

        private static bool RuntimeModelMatchesRecord(GbayVehicleRecord record)
        {
            try
            {
                var model = new Model(record.Model);
                if (!model.IsInCdImage || !model.IsVehicle) return false;
                int hash = model.Hash;
                bool boat = Function.Call<bool>(Hash.IS_THIS_MODEL_A_BOAT, hash);
                bool heli = Function.Call<bool>(Hash.IS_THIS_MODEL_A_HELI, hash);
                bool plane = Function.Call<bool>(Hash.IS_THIS_MODEL_A_PLANE, hash);
                bool train = Function.Call<bool>(Hash.IS_THIS_MODEL_A_TRAIN, hash);
                if (train) return false;
                if (record.Storage == "harbour" && !boat) return false;
                if (record.Storage == "helipad" && !heli) return false;
                if (record.Storage == "hangar" && !plane) return false;
                if (record.Storage == "garage" && (boat || heli || plane))
                    return false;
                if (record.TrafficEnabled)
                {
                    record.SetValidatedRuntimeVehicleClass(
                        (VehicleClass)Function.Call<int>(
                            Hash.GET_VEHICLE_CLASS_FROM_NAME, hash));
                }
                // Category is a storefront grouping, not proof of the native
                // class. TrafficSpawner performs its stricter road-class check
                // against this cached result rather than repeating native model
                // discovery for the same admitted record.
                return true;
            }
            catch (Exception ex)
            {
                ClientLog.Error("VehicleCatalog", "model_validation_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "package", record.PackageId },
                        { "catalog", record.CatalogId },
                        { "model", record.Model },
                    });
                return false;
            }
        }

        private static bool TryGetLocalizedVehicleName(
            string model, out string localized)
        {
            localized = "";
            try
            {
                int hash = Game.GenerateHash(model);
                string label = Function.Call<string>(
                    Hash.GET_DISPLAY_NAME_FROM_VEHICLE_MODEL, (uint)hash);
                return TryLocalizeLabel(label, out localized);
            }
            catch (Exception ex)
            {
                ClientLog.Error("VehicleCatalog", "name_localization_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "model", model ?? "" },
                    });
                return false;
            }
        }

        private static bool TryGetLocalizedManufacturer(
            string model, out string localized)
        {
            localized = "";
            try
            {
                int hash = Game.GenerateHash(model);
                string label = Function.Call<string>(
                    (Hash)GetMakeNameFromVehicleModelNative, (uint)hash);
                return TryLocalizeLabel(label, out localized);
            }
            catch (Exception ex)
            {
                ClientLog.Error("VehicleCatalog", "make_localization_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "model", model ?? "" },
                    });
                return false;
            }
        }

        private static bool TryLocalizeLabel(
            string label, out string localized)
        {
            localized = "";
            if (string.IsNullOrWhiteSpace(label) ||
                string.Equals(label, "NULL", StringComparison.OrdinalIgnoreCase))
                return false;
            string value = Game.GetLocalizedString(label);
            if (string.IsNullOrWhiteSpace(value) ||
                string.Equals(value, "NULL", StringComparison.OrdinalIgnoreCase))
                return false;
            localized = value.Trim();
            return true;
        }

        private static IEnumerable<string> StaticCategoryModels(string category)
        {
            switch (category)
            {
                case "all": return VehicleList.All;
                case "compacts": return VehicleList.Compacts;
                case "coupes": return VehicleList.Coupes;
                case "sedans": return VehicleList.Sedans;
                case "suvs": return VehicleList.Suvs;
                case "muscle": return VehicleList.Muscle;
                case "sports": return VehicleList.Sports;
                case "sportsclassics": return VehicleList.Sportsclassics;
                case "super": return VehicleList.Super;
                case "offroad": return VehicleList.Offroad;
                case "motorcycles": return VehicleList.Motorcycles;
                case "vans": return VehicleList.Vans;
                case "boats": return VehicleList.Boats;
                case "helicopters": return VehicleList.Helicopters;
                case "planes": return VehicleList.Planes;
                case "military": return VehicleList.Military;
                case "industrial": return VehicleList.Industrial;
                case "openwheel": return VehicleList.Openwheel;
                case "emergency": return VehicleList.Emergency;
                case "cycles": return VehicleList.Cycles;
                case "service": return VehicleList.Service;
                case "special": return VehicleList.Special;
                default: return Array.Empty<string>();
            }
        }

        private static string NormalizeStaticCategory(string value)
        {
            return (value ?? "special").Trim().ToLowerInvariant();
        }

        private static int ModelHash(string value)
        {
            uint hash = 0;
            foreach (char raw in value ?? "")
            {
                hash += char.ToLowerInvariant(raw);
                hash += hash << 10;
                hash ^= hash >> 6;
            }
            hash += hash << 3;
            hash ^= hash >> 11;
            hash += hash << 15;
            return unchecked((int)hash);
        }

        private static bool Contains(string[] values, string candidate)
        {
            return values != null && values.Any(value => string.Equals(
                value, candidate, StringComparison.OrdinalIgnoreCase));
        }

        private static bool IsIdentifier(string value)
        {
            return value != null && Identifier.IsMatch(
                value.Trim().ToLowerInvariant());
        }

        private static string LowerIdentifier(string value, string label)
        {
            string result = (value ?? "").Trim().ToLowerInvariant();
            if (!Identifier.IsMatch(result))
                throw new InvalidDataException(label + " is invalid");
            return result;
        }

        private static Dictionary<string, object> Object(
            object value, string label)
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

        private static object Value(
            Dictionary<string, object> value, string key)
        {
            if (!value.TryGetValue(key, out object result))
                throw new InvalidDataException("Missing required field: " + key);
            return result;
        }

        private static string Text(
            Dictionary<string, object> value, string key)
        {
            if (!(Value(value, key) is string result) ||
                string.IsNullOrWhiteSpace(result))
                throw new InvalidDataException(key + " must be non-empty text");
            return result;
        }

        private static string OptionalText(
            Dictionary<string, object> value, string key, string fallback)
        {
            if (!value.TryGetValue(key, out object raw)) return fallback;
            if (!(raw is string result))
                throw new InvalidDataException(key + " must be text");
            return result;
        }

        private static string BoundedText(
            Dictionary<string, object> value, string key,
            int minimum, int maximum)
        {
            string result = Text(value, key).Trim();
            if (result.Length < minimum || result.Length > maximum)
                throw new InvalidDataException(
                    key + " length is outside its supported range");
            return result;
        }

        private static int Integer(
            Dictionary<string, object> value, string key)
        {
            object raw = Value(value, key);
            if (raw is bool || !(raw is int result))
                throw new InvalidDataException(key + " must be an integer");
            return result;
        }

        private static int OptionalInteger(
            Dictionary<string, object> value, string key, int fallback)
        {
            if (!value.ContainsKey(key)) return fallback;
            return Integer(value, key);
        }

        private static double OptionalNumber(
            Dictionary<string, object> value, string key, double fallback)
        {
            if (!value.TryGetValue(key, out object raw)) return fallback;
            if (raw is bool)
                throw new InvalidDataException(key + " must be a number");
            double result;
            if (raw is int integer) result = integer;
            else if (raw is long longInteger) result = longInteger;
            else if (raw is decimal decimalNumber)
                result = (double)decimalNumber;
            else if (raw is double doubleNumber) result = doubleNumber;
            else throw new InvalidDataException(key + " must be a number");
            if (double.IsNaN(result) || double.IsInfinity(result))
                throw new InvalidDataException(key + " must be finite");
            return result;
        }

        private static bool Boolean(
            Dictionary<string, object> value, string key)
        {
            if (!(Value(value, key) is bool result))
                throw new InvalidDataException(key + " must be true or false");
            return result;
        }

        private static bool OptionalBoolean(
            Dictionary<string, object> value, string key, bool fallback)
        {
            if (!value.ContainsKey(key)) return fallback;
            return Boolean(value, key);
        }

        private static void ExactFields(
            Dictionary<string, object> value, string label,
            IEnumerable<string> fields, IEnumerable<string> optional = null)
        {
            var required = new HashSet<string>(fields,
                StringComparer.Ordinal);
            var allowed = new HashSet<string>(required,
                StringComparer.Ordinal);
            if (optional != null) allowed.UnionWith(optional);
            foreach (string key in value.Keys)
                if (!allowed.Contains(key))
                    throw new InvalidDataException(
                        label + " contains unknown field: " + key);
            foreach (string key in required)
                if (!value.ContainsKey(key) &&
                    (optional == null || !optional.Contains(key)))
                    throw new InvalidDataException(
                        label + " is missing field: " + key);
        }
    }
}
