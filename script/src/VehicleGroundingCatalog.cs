using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;

namespace ALLIN1
{
    public sealed class VehicleGroundingEntry
    {
        public string Model { get; set; }
        public int ModelHash { get; set; }
        public string Status { get; set; }
        public bool Stable { get; set; }
        public float RootOffset { get; set; }
    }

    public sealed class VehicleGroundingCatalogDocument
    {
        public int SchemaVersion { get; set; } = 1;
        public Dictionary<string, VehicleGroundingEntry> Entries { get; set; } =
            new Dictionary<string, VehicleGroundingEntry>(
                StringComparer.OrdinalIgnoreCase);
    }

    internal static class VehicleGroundingCatalog
    {
        internal const string FileName = "ALLIN1_vehicle_grounding.json";
        private static readonly object Sync = new object();
        private static VehicleGroundingCatalogDocument _loaded;

        private static string CatalogPath => Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, FileName);

        internal static bool TryGetStableRootOffset(
            string model, int modelHash, out float rootOffset)
        {
            rootOffset = 0f;
            lock (Sync)
            {
                if (_loaded == null) _loaded = LoadFromDisk();
                VehicleGroundingEntry entry = null;
                string key = NormalizeModel(model);
                if (key.Length > 0)
                    _loaded.Entries.TryGetValue(key, out entry);
                if (entry == null && modelHash != 0)
                    entry = _loaded.Entries.Values.FirstOrDefault(
                        item => item != null && item.ModelHash == modelHash);
                if (entry == null || !entry.Stable
                    || !string.Equals(entry.Status, "measured",
                        StringComparison.OrdinalIgnoreCase)
                    || !VehiclePlacementMath.IsUsableMeasuredRootOffset(
                        entry.RootOffset))
                    return false;
                rootOffset = entry.RootOffset;
                return true;
            }
        }

        private static string NormalizeModel(string model)
        {
            return (model ?? "").Trim().ToLowerInvariant();
        }

        private static VehicleGroundingCatalogDocument LoadFromDisk()
        {
            try
            {
                if (!File.Exists(CatalogPath))
                    return NewDocument();
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = int.MaxValue,
                    RecursionLimit = 100,
                };
                var document = serializer.Deserialize<VehicleGroundingCatalogDocument>(
                    File.ReadAllText(CatalogPath));
                if (document == null || document.SchemaVersion != 1)
                    return NewDocument();
                NormalizeEntries(document);
                return document;
            }
            catch (Exception ex)
            {
                ClientLog.Error("GroundingCatalog", "load_failed", ex);
                return NewDocument();
            }
        }

        private static VehicleGroundingCatalogDocument NewDocument()
        {
            return new VehicleGroundingCatalogDocument();
        }

        private static void NormalizeEntries(VehicleGroundingCatalogDocument document)
        {
            var normalized = new Dictionary<string, VehicleGroundingEntry>(
                StringComparer.OrdinalIgnoreCase);
            if (document.Entries != null)
            {
                foreach (var pair in document.Entries)
                {
                    VehicleGroundingEntry entry = pair.Value;
                    if (entry == null) continue;
                    string key = NormalizeModel(entry.Model);
                    if (key.Length == 0) key = NormalizeModel(pair.Key);
                    if (key.Length == 0) continue;
                    entry.Model = key;
                    normalized[key] = entry;
                }
            }
            document.Entries = normalized;
        }
    }
}
