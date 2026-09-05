// MapPackageRuntime.cs -- receipt-authorized custom map portals for Story Mode.
//
// Package authors place receipt-authorized descriptors beneath:
//   scripts/ALLIN1/Maps/<package>/maps.json
// Official content may use multiple sibling *.maps.json descriptors so each
// property can be streamed and diagnosed independently.
//
// This runtime deliberately uses REQUEST_IPL/REMOVE_IPL through the existing
// lease manager.  It never executes an arbitrary content-change group: that
// public native route is unsafe on Enhanced. Third-party records own map
// streaming and portal transitions. Official ALLIN1 garage records are
// bridged into GarageManager, which retains the mature storage/save behavior
// while the SDK descriptors own coordinates, headings, slots, and IPL lists.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal sealed class MapPoint
    {
        internal float X { get; set; }
        internal float Y { get; set; }
        internal float Z { get; set; }
        internal float Heading { get; set; }
        internal Vector3 Position => new Vector3(X, Y, Z);
    }

    internal sealed class MapStreamingDefinition
    {
        internal string Mode { get; set; } = "ipl";
        internal string PackName { get; set; }
        internal string ContentGroup { get; set; }
        internal string[] Ipls { get; set; } = Array.Empty<string>();
        internal float ActivationRadius { get; set; }
        internal float ReleaseRadius { get; set; }
        internal bool KeepResident { get; set; }

        internal bool RequiresLease => !string.Equals(
            Mode, "none", StringComparison.OrdinalIgnoreCase);
    }

    internal sealed class MapLevelDefinition
    {
        internal string Id { get; set; }
        internal string Name { get; set; }
        internal MapPoint Center { get; set; }
        internal string[] Ipls { get; set; } = Array.Empty<string>();
    }

    internal enum MapPortalMode
    {
        Ped,
        Vehicle,
        Both,
    }

    internal sealed class MapPortalEndpoint
    {
        internal string Level { get; set; }
        internal MapPoint Point { get; set; }
    }

    internal sealed class MapPortalDefinition
    {
        internal string Id { get; set; }
        internal string Name { get; set; }
        internal MapPortalMode Mode { get; set; }
        internal MapPortalEndpoint From { get; set; }
        internal MapPortalEndpoint To { get; set; }
        internal float Radius { get; set; }
        internal bool OneWay { get; set; }
    }

    internal sealed class MapGarageRules
    {
        internal bool AllowStore { get; set; }
        internal bool AllowRetrieve { get; set; }
        internal string SavePolicy { get; set; }
    }

    internal sealed class MapGarageSlotDefinition
    {
        internal string Id { get; set; }
        internal MapPoint Point { get; set; }
        internal string[] VehicleTypes { get; set; } = Array.Empty<string>();
    }

    internal sealed class MapGarageDefinition
    {
        internal string Id { get; set; }
        internal string Name { get; set; }
        internal string LevelId { get; set; }
        internal string EntrancePortalId { get; set; }
        internal int Capacity { get; set; }
        internal string[] VehicleTypes { get; set; } = Array.Empty<string>();
        internal MapGarageSlotDefinition[] Slots { get; set; } =
            Array.Empty<MapGarageSlotDefinition>();
        internal MapGarageRules Rules { get; set; }
    }

    internal sealed class MapProjectDefinition
    {
        internal int SchemaVersion { get; set; }
        internal string Id { get; set; }
        internal string PackageId { get; set; }
        internal string Name { get; set; }
        internal string Version { get; set; }
        internal string[] Editions { get; set; } = Array.Empty<string>();
        internal MapStreamingDefinition Streaming { get; set; }
        internal MapLevelDefinition[] Levels { get; set; } =
            Array.Empty<MapLevelDefinition>();
        internal MapPortalDefinition[] Portals { get; set; } =
            Array.Empty<MapPortalDefinition>();
        internal MapGarageDefinition[] Garages { get; set; } =
            Array.Empty<MapGarageDefinition>();

        internal string LeaseKey => PackageId + ":" + Id;

        internal string LeaseGroup => LeaseKey + ":" +
            (Streaming?.ContentGroup ?? string.Empty);

        internal string[] RequiredIpls =>
            (Streaming?.Ipls ?? Array.Empty<string>())
                .Concat(Levels.SelectMany(level =>
                    level.Ipls ?? Array.Empty<string>()))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
    }

    internal sealed class MapProjectLoadResult
    {
        internal IReadOnlyList<MapProjectDefinition> Projects { get; }
        internal IReadOnlyList<string> Diagnostics { get; }
        internal string Fingerprint { get; }

        internal MapProjectLoadResult(
            IEnumerable<MapProjectDefinition> projects,
            IEnumerable<string> diagnostics, string fingerprint)
        {
            Projects = (projects ?? Enumerable.Empty<MapProjectDefinition>())
                .ToArray();
            Diagnostics = (diagnostics ?? Enumerable.Empty<string>()).ToArray();
            Fingerprint = fingerprint ?? string.Empty;
        }
    }

    internal static class MapProjectParser
    {
        private const int MaximumJsonLength = 1024 * 1024;
        private static readonly Regex SafeId = new Regex(
            "^[a-z0-9][a-z0-9._-]{1,63}$", RegexOptions.CultureInvariant);
        private static readonly Regex SafePackName = new Regex(
            "^[a-z0-9][a-z0-9_-]{0,63}$", RegexOptions.CultureInvariant);
        private static readonly Regex SafeNativeName = new Regex(
            "^[A-Za-z0-9_:.@-]{1,96}$",
            RegexOptions.CultureInvariant);
        private static readonly Regex SafeVersion = new Regex(
            "^[0-9A-Za-z][0-9A-Za-z._+-]{0,31}$",
            RegexOptions.CultureInvariant);
        private static readonly HashSet<string> VehicleTypes =
            new HashSet<string>(new[]
            {
                "land", "boat", "helicopter", "plane",
            }, StringComparer.OrdinalIgnoreCase);

        internal static bool TryParse(
            string json, out MapProjectDefinition project,
            out IReadOnlyList<string> errors)
        {
            project = null;
            var failures = new List<string>();
            errors = failures;
            if (string.IsNullOrWhiteSpace(json))
            {
                failures.Add("root: JSON is empty");
                return false;
            }
            if (Encoding.UTF8.GetByteCount(json) > MaximumJsonLength)
            {
                failures.Add("root: maps.json exceeds the 1 MiB limit");
                return false;
            }

            IDictionary<string, object> root;
            try
            {
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = MaximumJsonLength,
                    RecursionLimit = 32,
                };
                root = serializer.DeserializeObject(json)
                    as IDictionary<string, object>;
            }
            catch (Exception ex)
            {
                failures.Add("root: invalid JSON (" +
                    ex.GetType().Name + ")");
                return false;
            }
            if (root == null)
            {
                failures.Add("root: expected an object");
                return false;
            }

            CheckKeys(root, "root", failures,
                "schema_version", "id", "package_id", "name", "version",
                "editions", "streaming", "levels", "portals", "garages");

            int schema = RequiredInteger(root, "schema_version", "root",
                failures, 1, 1);
            string id = RequiredId(root, "id", "root", failures);
            string packageId = RequiredId(root, "package_id", "root", failures);
            string name = RequiredText(root, "name", "root", failures, 128);
            string version = RequiredText(
                root, "version", "root", failures, 32);
            if (!string.IsNullOrEmpty(version) && !SafeVersion.IsMatch(version))
                failures.Add("root.version: unsupported version characters");
            string[] editions = RequiredChoiceArray(root, "editions", "root",
                failures, new[] { "legacy", "enhanced" }, 2);
            MapStreamingDefinition streaming = ParseStreaming(
                RequiredObject(root, "streaming", "root", failures), failures);
            MapLevelDefinition[] levels = ParseLevels(
                RequiredArray(root, "levels", "root", failures), failures);
            MapPortalDefinition[] portals = ParsePortals(
                RequiredArray(root, "portals", "root", failures), failures);
            MapGarageDefinition[] garages = ParseGarages(
                OptionalArray(root, "garages", "root", failures), failures);

            if ((streaming?.RequiresLease ?? true) &&
                (streaming?.Ipls ?? Array.Empty<string>()).Length == 0 &&
                !levels.Any(level =>
                    (level?.Ipls ?? Array.Empty<string>()).Length > 0))
                failures.Add("root.streaming: the safe Story runtime requires " +
                    "at least one project or level IPL");
            if (!(streaming?.RequiresLease ?? true) && levels.Any(level =>
                    (level?.Ipls ?? Array.Empty<string>()).Length > 0))
                failures.Add("root.levels: mode none cannot declare IPLs");

            ValidateReferences(levels, portals, garages, failures);
            if (failures.Count > 0) return false;

            project = new MapProjectDefinition
            {
                SchemaVersion = schema,
                Id = id,
                PackageId = packageId,
                Name = name,
                Version = version,
                Editions = editions,
                Streaming = streaming,
                Levels = levels,
                Portals = portals,
                Garages = garages,
            };
            return true;
        }

        private static MapStreamingDefinition ParseStreaming(
            IDictionary<string, object> value, List<string> errors)
        {
            if (value == null) return null;
            const string path = "root.streaming";
            CheckKeys(value, path, errors,
                "mode", "pack_name", "content_group", "ipls", "activation_radius",
                "release_radius", "keep_resident");
            string mode = value.ContainsKey("mode")
                ? RequiredString(value, "mode", path, errors)
                : "ipl";
            if (!string.IsNullOrEmpty(mode)) mode = mode.ToLowerInvariant();
            if (mode != "ipl" && mode != "none")
                errors.Add(path + ".mode: expected ipl or none");
            string pack = RequiredString(value, "pack_name", path, errors);
            if (!string.IsNullOrEmpty(pack))
                pack = pack.ToLowerInvariant();
            if (!string.IsNullOrEmpty(pack) && !SafePackName.IsMatch(pack))
                errors.Add(path + ".pack_name: invalid DLC pack name");
            string group = OptionalNullableNativeName(
                value, "content_group", path, errors);
            if (!string.IsNullOrEmpty(group) && !SafeNativeName.IsMatch(group))
                errors.Add(path + ".content_group: invalid lease/content name");
            string[] ipls = OptionalNativeNameArray(
                value, "ipls", path, errors, 128);
            if (mode == "ipl" && string.IsNullOrEmpty(group) && ipls.Length == 0)
                errors.Add(path +
                    ": content_group or at least one IPL is required");
            if (mode == "none" &&
                (!string.IsNullOrEmpty(group) || ipls.Length != 0))
                errors.Add(path +
                    ": mode none cannot declare content_group or IPLs");
            float activation = OptionalNumber(value, "activation_radius", path,
                errors, 10f, 10000f, 300f);
            float release = OptionalNumber(value, "release_radius", path,
                errors, 10f, 20000f, 500f);
            if (release <= activation)
                errors.Add(path +
                    ".release_radius: must be greater than activation_radius");
            bool resident = OptionalBoolean(
                value, "keep_resident", path, errors, false);
            return new MapStreamingDefinition
            {
                Mode = mode,
                PackName = pack,
                ContentGroup = group,
                Ipls = ipls,
                ActivationRadius = activation,
                ReleaseRadius = release,
                KeepResident = resident,
            };
        }

        private static MapLevelDefinition[] ParseLevels(
            object[] values, List<string> errors)
        {
            if (values == null) return Array.Empty<MapLevelDefinition>();
            if (values.Length < 1 || values.Length > 64)
                errors.Add("root.levels: expected 1 to 64 levels");
            var result = new List<MapLevelDefinition>();
            var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < values.Length; index++)
            {
                string path = "root.levels[" + index + "]";
                IDictionary<string, object> item = AsObject(
                    values[index], path, errors);
                if (item == null) continue;
                CheckKeys(item, path, errors, "id", "name", "center", "ipls");
                string id = RequiredId(item, "id", path, errors);
                if (!string.IsNullOrEmpty(id) &&
                    id.Equals("world", StringComparison.OrdinalIgnoreCase))
                    errors.Add(path + ".id: world is reserved");
                if (!string.IsNullOrEmpty(id) && !ids.Add(id))
                    errors.Add(path + ".id: duplicate level id");
                string name = RequiredText(item, "name", path, errors, 128);
                MapPoint center = ParsePoint(
                    RequiredObject(item, "center", path, errors),
                    path + ".center", errors, headingRequired: false);
                string[] ipls = OptionalNativeNameArray(
                    item, "ipls", path, errors, 128);
                result.Add(new MapLevelDefinition
                {
                    Id = id,
                    Name = name,
                    Center = center,
                    Ipls = ipls,
                });
            }
            return result.ToArray();
        }

        private static MapPortalDefinition[] ParsePortals(
            object[] values, List<string> errors)
        {
            if (values == null) return Array.Empty<MapPortalDefinition>();
            if (values.Length < 1 || values.Length > 128)
                errors.Add("root.portals: expected 1 to 128 portals");
            var result = new List<MapPortalDefinition>();
            var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < values.Length; index++)
            {
                string path = "root.portals[" + index + "]";
                IDictionary<string, object> item = AsObject(
                    values[index], path, errors);
                if (item == null) continue;
                CheckKeys(item, path, errors,
                    "id", "name", "mode", "from", "to", "radius", "one_way");
                string id = RequiredId(item, "id", path, errors);
                if (!string.IsNullOrEmpty(id) && !ids.Add(id))
                    errors.Add(path + ".id: duplicate portal id");
                string name = OptionalText(item, "name", path, errors, 128) ?? id;
                string modeText = RequiredString(item, "mode", path, errors);
                if (!string.IsNullOrEmpty(modeText))
                    modeText = modeText.ToLowerInvariant();
                MapPortalMode mode = MapPortalMode.Both;
                if (modeText == "ped") mode = MapPortalMode.Ped;
                else if (modeText == "vehicle") mode = MapPortalMode.Vehicle;
                else if (modeText == "both") mode = MapPortalMode.Both;
                else if (!string.IsNullOrEmpty(modeText))
                    errors.Add(path + ".mode: expected ped, vehicle, or both");
                MapPortalEndpoint from = ParseEndpoint(
                    RequiredObject(item, "from", path, errors),
                    path + ".from", errors);
                MapPortalEndpoint to = ParseEndpoint(
                    RequiredObject(item, "to", path, errors),
                    path + ".to", errors);
                float radius = OptionalNumber(
                    item, "radius", path, errors, 0.5f, 50f, 3f);
                bool oneWay = OptionalBoolean(
                    item, "one_way", path, errors, false);
                result.Add(new MapPortalDefinition
                {
                    Id = id,
                    Name = name,
                    Mode = mode,
                    From = from,
                    To = to,
                    Radius = radius,
                    OneWay = oneWay,
                });
            }
            return result.ToArray();
        }

        private static MapPortalEndpoint ParseEndpoint(
            IDictionary<string, object> value, string path, List<string> errors)
        {
            if (value == null) return null;
            CheckKeys(value, path, errors, "level", "position");
            return new MapPortalEndpoint
            {
                Level = RequiredLevelReference(
                    value, "level", path, errors),
                Point = ParsePoint(
                    RequiredObject(value, "position", path, errors),
                    path + ".position", errors, headingRequired: false),
            };
        }

        private static MapGarageDefinition[] ParseGarages(
            object[] values, List<string> errors)
        {
            if (values == null) return Array.Empty<MapGarageDefinition>();
            if (values.Length > 64)
                errors.Add("root.garages: at most 64 garages are allowed");
            var result = new List<MapGarageDefinition>();
            var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < values.Length; index++)
            {
                string path = "root.garages[" + index + "]";
                IDictionary<string, object> item = AsObject(
                    values[index], path, errors);
                if (item == null) continue;
                CheckKeys(item, path, errors,
                    "id", "name", "level_id", "entrance_portal_id", "capacity",
                    "vehicle_types", "slots", "rules");
                string id = RequiredId(item, "id", path, errors);
                if (!string.IsNullOrEmpty(id) && !ids.Add(id))
                    errors.Add(path + ".id: duplicate garage id");
                string name = RequiredText(item, "name", path, errors, 128);
                string levelId = RequiredLevelReference(
                    item, "level_id", path, errors);
                string portalId = RequiredId(
                    item, "entrance_portal_id", path, errors);
                int capacity = RequiredInteger(
                    item, "capacity", path, errors, 1, 100);
                string[] vehicleTypes = RequiredVehicleTypes(
                    item, "vehicle_types", path, errors);
                MapGarageSlotDefinition[] slots = ParseSlots(
                    RequiredArray(item, "slots", path, errors), path,
                    vehicleTypes, errors);
                if (slots.Length == 0)
                    errors.Add(path +
                        ".slots: at least one spawn/store slot is required");
                if (slots.Length > capacity)
                    errors.Add(path + ".slots: count exceeds capacity");
                MapGarageRules rules = ParseRules(
                    OptionalObject(item, "rules", path, errors),
                    path + ".rules", errors);
                result.Add(new MapGarageDefinition
                {
                    Id = id,
                    Name = name,
                    LevelId = levelId,
                    EntrancePortalId = portalId,
                    Capacity = capacity,
                    VehicleTypes = vehicleTypes,
                    Slots = slots,
                    Rules = rules,
                });
            }
            return result.ToArray();
        }

        private static MapGarageSlotDefinition[] ParseSlots(
            object[] values, string parentPath, string[] inheritedVehicleTypes,
            List<string> errors)
        {
            if (values == null) return Array.Empty<MapGarageSlotDefinition>();
            if (values.Length > 100)
                errors.Add(parentPath + ".slots: at most 100 slots are allowed");
            var result = new List<MapGarageSlotDefinition>();
            var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < values.Length; index++)
            {
                string path = parentPath + ".slots[" + index + "]";
                IDictionary<string, object> item = AsObject(
                    values[index], path, errors);
                if (item == null) continue;
                CheckKeys(item, path, errors, "id", "position", "vehicle_types");
                string id = RequiredId(item, "id", path, errors);
                if (!string.IsNullOrEmpty(id) && !ids.Add(id))
                    errors.Add(path + ".id: duplicate slot id");
                MapPoint point = ParsePoint(
                    RequiredObject(item, "position", path, errors),
                    path + ".position", errors, headingRequired: false);
                string[] vehicleTypes = item.ContainsKey("vehicle_types")
                    ? RequiredVehicleTypes(item, "vehicle_types", path, errors)
                    : inheritedVehicleTypes.ToArray();
                if (vehicleTypes.Except(inheritedVehicleTypes,
                    StringComparer.OrdinalIgnoreCase).Any())
                    errors.Add(path +
                        ".vehicle_types: must be a subset of garage vehicle_types");
                result.Add(new MapGarageSlotDefinition
                {
                    Id = id,
                    Point = point,
                    VehicleTypes = vehicleTypes,
                });
            }
            return result.ToArray();
        }

        private static MapGarageRules ParseRules(
            IDictionary<string, object> value, string path, List<string> errors)
        {
            if (value == null) return null;
            CheckKeys(value, path, errors,
                "allow_store", "allow_retrieve", "save_policy");
            bool store = OptionalBoolean(
                value, "allow_store", path, errors, true);
            bool retrieve = OptionalBoolean(
                value, "allow_retrieve", path, errors, true);
            if (!store && !retrieve)
                errors.Add(path +
                    ": at least one of allow_store or allow_retrieve must be true");
            string policy = value.ContainsKey("save_policy")
                ? RequiredString(value, "save_policy", path, errors)
                : "story_save_only";
            if (!string.IsNullOrEmpty(policy))
                policy = policy.ToLowerInvariant();
            if (!string.IsNullOrEmpty(policy) && policy != "story_save_only")
                errors.Add(path +
                    ".save_policy: only story_save_only is supported");
            return new MapGarageRules
            {
                AllowStore = store,
                AllowRetrieve = retrieve,
                SavePolicy = policy,
            };
        }

        private static void ValidateReferences(
            MapLevelDefinition[] levels, MapPortalDefinition[] portals,
            MapGarageDefinition[] garages, List<string> errors)
        {
            var levelIds = new HashSet<string>(
                levels.Where(value => value != null)
                    .Select(value => value.Id)
                    .Where(value => !string.IsNullOrEmpty(value)),
                StringComparer.OrdinalIgnoreCase);
            var portalIds = new Dictionary<string, MapPortalDefinition>(
                StringComparer.OrdinalIgnoreCase);
            foreach (MapPortalDefinition portal in portals)
                if (portal != null && !string.IsNullOrEmpty(portal.Id) &&
                    !portalIds.ContainsKey(portal.Id))
                    portalIds.Add(portal.Id, portal);

            for (int index = 0; index < portals.Length; index++)
            {
                MapPortalDefinition portal = portals[index];
                if (portal == null) continue;
                ValidateLevelReference(portal.From?.Level,
                    "root.portals[" + index + "].from.level", levelIds, errors);
                ValidateLevelReference(portal.To?.Level,
                    "root.portals[" + index + "].to.level", levelIds, errors);
                if (portal.From != null && portal.To != null &&
                    string.Equals(portal.From.Level, portal.To.Level,
                        StringComparison.OrdinalIgnoreCase))
                    errors.Add("root.portals[" + index +
                        "]: endpoints must connect different levels");
            }

            for (int index = 0; index < garages.Length; index++)
            {
                MapGarageDefinition garage = garages[index];
                if (garage == null) continue;
                string path = "root.garages[" + index + "]";
                if (!string.Equals(garage.LevelId, "world",
                        StringComparison.OrdinalIgnoreCase) &&
                    !levelIds.Contains(garage.LevelId ?? string.Empty))
                    errors.Add(path + ".level_id: unknown level");
                if (!portalIds.TryGetValue(
                    garage.EntrancePortalId ?? string.Empty,
                    out MapPortalDefinition portal))
                    errors.Add(path + ".entrance_portal_id: unknown portal");
                else if (!string.Equals(portal.From.Level, garage.LevelId,
                             StringComparison.OrdinalIgnoreCase) &&
                         !string.Equals(portal.To.Level, garage.LevelId,
                             StringComparison.OrdinalIgnoreCase))
                    errors.Add(path +
                        ".entrance_portal_id: portal does not reach garage level");
            }
        }

        private static void ValidateLevelReference(
            string value, string path, ISet<string> levelIds,
            List<string> errors)
        {
            if (string.IsNullOrEmpty(value)) return;
            if (!value.Equals("world", StringComparison.OrdinalIgnoreCase) &&
                !levelIds.Contains(value))
                errors.Add(path + ": unknown level");
        }

        private static MapPoint ParsePoint(
            IDictionary<string, object> value, string path,
            List<string> errors, bool headingRequired)
        {
            if (value == null) return null;
            CheckKeys(value, path, errors, "x", "y", "z", "heading");
            float x = RequiredFiniteNumber(value, "x", path, errors);
            float y = RequiredFiniteNumber(value, "y", path, errors);
            float z = RequiredFiniteNumber(value, "z", path, errors);
            float heading = headingRequired
                ? RequiredFiniteNumber(value, "heading", path, errors)
                : OptionalFiniteNumber(value, "heading", path, errors, 0f);
            heading %= 360f;
            if (heading < 0f) heading += 360f;
            return new MapPoint { X = x, Y = y, Z = z, Heading = heading };
        }

        private static string[] RequiredVehicleTypes(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            object[] values = RequiredArray(map, key, path, errors);
            if (values == null) return Array.Empty<string>();
            if (values.Length < 1 || values.Length > 4)
                errors.Add(path + "." + key + ": expected 1 to 4 entries");
            var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < values.Length; index++)
            {
                string value = values[index] as string;
                if (string.IsNullOrWhiteSpace(value) ||
                    !VehicleTypes.Contains(value.Trim()))
                    errors.Add(path + "." + key + "[" + index +
                        "]: unsupported vehicle type");
                else if (!result.Add(value.Trim().ToLowerInvariant()))
                    errors.Add(path + "." + key + "[" + index +
                        "]: duplicate vehicle type");
            }
            return result.ToArray();
        }

        private static string[] RequiredChoiceArray(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, string[] choices, int maximum)
        {
            object[] values = RequiredArray(map, key, path, errors);
            if (values == null) return Array.Empty<string>();
            if (values.Length < 1 || values.Length > maximum)
                errors.Add(path + "." + key + ": invalid item count");
            var allowed = new HashSet<string>(choices,
                StringComparer.OrdinalIgnoreCase);
            var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < values.Length; index++)
            {
                string value = values[index] as string;
                if (string.IsNullOrWhiteSpace(value) ||
                    !allowed.Contains(value.Trim()))
                    errors.Add(path + "." + key + "[" + index +
                        "]: unsupported value");
                else if (!result.Add(value.Trim().ToLowerInvariant()))
                    errors.Add(path + "." + key + "[" + index +
                        "]: duplicate value");
            }
            return result.ToArray();
        }

        private static string[] RequiredNativeNameArray(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, int maximum, bool requireOne)
        {
            object[] values = RequiredArray(map, key, path, errors);
            return ParseNativeNameArray(
                values, path + "." + key, errors, maximum, requireOne);
        }

        private static string[] OptionalNativeNameArray(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, int maximum)
        {
            if (!map.TryGetValue(key, out object raw)) return Array.Empty<string>();
            object[] values = raw as object[];
            if (values == null)
            {
                errors.Add(path + "." + key + ": expected an array");
                return Array.Empty<string>();
            }
            return ParseNativeNameArray(
                values, path + "." + key, errors, maximum, false);
        }

        private static string[] ParseNativeNameArray(
            object[] values, string path, List<string> errors,
            int maximum, bool requireOne)
        {
            if (values == null) return Array.Empty<string>();
            if ((requireOne && values.Length < 1) || values.Length > maximum)
                errors.Add(path + ": invalid item count");
            var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int index = 0; index < values.Length; index++)
            {
                string value = values[index] as string;
                if (string.IsNullOrWhiteSpace(value) ||
                    !SafeNativeName.IsMatch(value.Trim()))
                    errors.Add(path + "[" + index + "]: invalid native name");
                else if (!result.Add(value.Trim()))
                    errors.Add(path + "[" + index +
                        "]: duplicate native name");
            }
            return result.ToArray();
        }

        private static string RequiredId(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            string value = RequiredString(map, key, path, errors);
            if (!string.IsNullOrEmpty(value))
                value = value.ToLowerInvariant();
            if (!string.IsNullOrEmpty(value) &&
                (!SafeId.IsMatch(value) || value == "world"))
                errors.Add(path + "." + key + ": invalid identifier");
            return value;
        }

        private static string RequiredLevelReference(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            string value = RequiredString(map, key, path, errors);
            if (string.IsNullOrEmpty(value)) return value;
            value = value.ToLowerInvariant();
            if (value != "world" && !SafeId.IsMatch(value))
                errors.Add(path + "." + key + ": invalid level reference");
            return value;
        }

        private static string OptionalNullableNativeName(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!map.TryGetValue(key, out object raw) || raw == null)
                return null;
            string value = raw as string;
            if (string.IsNullOrWhiteSpace(value))
            {
                errors.Add(path + "." + key +
                    ": expected a native name or null");
                return null;
            }
            value = value.Trim();
            if (!SafeNativeName.IsMatch(value))
                errors.Add(path + "." + key + ": invalid native name");
            return value;
        }

        private static string RequiredText(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, int maximum)
        {
            string value = RequiredString(map, key, path, errors);
            ValidateText(value, path + "." + key, maximum, errors);
            return value;
        }

        private static string OptionalText(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, int maximum)
        {
            if (!map.TryGetValue(key, out object raw)) return null;
            string value = raw as string;
            if (value == null)
            {
                errors.Add(path + "." + key + ": expected a string");
                return null;
            }
            value = value.Trim();
            ValidateText(value, path + "." + key, maximum, errors);
            return value;
        }

        private static void ValidateText(
            string value, string path, int maximum, List<string> errors)
        {
            if (string.IsNullOrWhiteSpace(value) || value.Length > maximum ||
                value.Any(char.IsControl))
                errors.Add(path + ": invalid display text");
        }

        private static string RequiredString(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!map.TryGetValue(key, out object raw))
            {
                errors.Add(path + "." + key + ": required");
                return null;
            }
            string value = raw as string;
            if (string.IsNullOrWhiteSpace(value))
            {
                errors.Add(path + "." + key + ": expected a non-empty string");
                return null;
            }
            return value.Trim();
        }

        private static IDictionary<string, object> RequiredObject(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!map.TryGetValue(key, out object raw))
            {
                errors.Add(path + "." + key + ": required");
                return null;
            }
            return AsObject(raw, path + "." + key, errors);
        }

        private static IDictionary<string, object> OptionalObject(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!map.TryGetValue(key, out object raw))
                return new Dictionary<string, object>();
            return AsObject(raw, path + "." + key, errors);
        }

        private static IDictionary<string, object> AsObject(
            object raw, string path, List<string> errors)
        {
            var value = raw as IDictionary<string, object>;
            if (value == null) errors.Add(path + ": expected an object");
            return value;
        }

        private static object[] RequiredArray(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!map.TryGetValue(key, out object raw))
            {
                errors.Add(path + "." + key + ": required");
                return null;
            }
            object[] value = raw as object[];
            if (value == null)
                errors.Add(path + "." + key + ": expected an array");
            return value;
        }

        private static object[] OptionalArray(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!map.TryGetValue(key, out object raw)) return Array.Empty<object>();
            object[] value = raw as object[];
            if (value == null)
                errors.Add(path + "." + key + ": expected an array");
            return value;
        }

        private static bool RequiredBoolean(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!map.TryGetValue(key, out object raw) || !(raw is bool value))
            {
                errors.Add(path + "." + key + ": expected a boolean");
                return false;
            }
            return value;
        }

        private static bool OptionalBoolean(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, bool fallback)
        {
            if (!map.TryGetValue(key, out object raw)) return fallback;
            if (!(raw is bool value))
            {
                errors.Add(path + "." + key + ": expected a boolean");
                return fallback;
            }
            return value;
        }

        private static int RequiredInteger(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, int minimum, int maximum)
        {
            if (!map.TryGetValue(key, out object raw) || raw == null ||
                raw is bool || !(raw is int || raw is long || raw is short ||
                    raw is byte) ||
                !long.TryParse(Convert.ToString(raw, CultureInfo.InvariantCulture),
                    NumberStyles.Integer, CultureInfo.InvariantCulture,
                    out long number) ||
                number < minimum || number > maximum)
            {
                errors.Add(path + "." + key + ": expected an integer from " +
                    minimum + " to " + maximum);
                return minimum;
            }
            return (int)number;
        }

        private static float RequiredNumber(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, float minimum, float maximum)
        {
            if (!TryNumber(map, key, out double number) ||
                double.IsNaN(number) || double.IsInfinity(number) ||
                number < minimum || number > maximum)
            {
                errors.Add(path + "." + key + ": expected a finite number from " +
                    minimum.ToString(CultureInfo.InvariantCulture) + " to " +
                    maximum.ToString(CultureInfo.InvariantCulture));
                return minimum;
            }
            return (float)number;
        }

        private static float RequiredFiniteNumber(
            IDictionary<string, object> map, string key, string path,
            List<string> errors)
        {
            if (!TryNumber(map, key, out double number) ||
                double.IsNaN(number) || double.IsInfinity(number) ||
                number < -float.MaxValue || number > float.MaxValue)
            {
                errors.Add(path + "." + key +
                    ": expected a finite number");
                return 0f;
            }
            return (float)number;
        }

        private static float OptionalNumber(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, float minimum, float maximum, float fallback)
        {
            if (!map.ContainsKey(key)) return fallback;
            return RequiredNumber(map, key, path, errors, minimum, maximum);
        }

        private static float OptionalFiniteNumber(
            IDictionary<string, object> map, string key, string path,
            List<string> errors, float fallback)
        {
            if (!map.ContainsKey(key)) return fallback;
            return RequiredFiniteNumber(map, key, path, errors);
        }

        private static bool TryNumber(
            IDictionary<string, object> map, string key, out double number)
        {
            number = 0;
            if (!map.TryGetValue(key, out object raw) || raw == null ||
                raw is bool || raw is string) return false;
            try
            {
                number = Convert.ToDouble(raw, CultureInfo.InvariantCulture);
                return true;
            }
            catch { return false; }
        }

        private static void CheckKeys(
            IDictionary<string, object> map, string path, List<string> errors,
            params string[] permitted)
        {
            var allowed = new HashSet<string>(permitted,
                StringComparer.Ordinal);
            foreach (string key in map.Keys)
                if (!allowed.Contains(key))
                    errors.Add(path + "." + key + ": unknown field");
        }
    }

    internal static class MapProjectDirectoryLoader
    {
        private const int MaximumProjects = 64;

        internal static MapProjectLoadResult LoadAuthorized(
            IEnumerable<MapDescriptorDeclaration> declarations,
            string runtimeEdition)
        {
            MapDescriptorDeclaration[] descriptors =
                (declarations ?? Enumerable.Empty<MapDescriptorDeclaration>())
                .Where(value => value != null && value.Exists)
                .OrderBy(value => value.PackageId,
                    StringComparer.OrdinalIgnoreCase)
                .ThenBy(value => value.Source,
                    StringComparer.OrdinalIgnoreCase)
                .Take(MaximumProjects + 1)
                .ToArray();
            var projects = new List<MapProjectDefinition>();
            var diagnostics = new List<string>();
            var identities = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            string fingerprint = string.Join("|", descriptors.Select(value =>
                value.PackageId + ":" + FileFingerprint(value.SourcePath)));
            foreach (MapDescriptorDeclaration descriptor in
                descriptors.Take(MaximumProjects))
            {
                string file = descriptor.SourcePath;
                try
                {
                    var info = new FileInfo(file);
                    if (!info.Exists || info.Length > 1024 * 1024)
                    {
                        diagnostics.Add(file + ": exceeds the 1 MiB limit");
                        continue;
                    }
                    string descriptorJson;
                    if (!EarlyStartupSnapshot.TryGetTextByPath(
                            descriptor.Source, out descriptorJson))
                        descriptorJson = File.ReadAllText(file);
                    if (!MapProjectParser.TryParse(
                        descriptorJson,
                        out MapProjectDefinition project,
                        out IReadOnlyList<string> errors))
                    {
                        diagnostics.AddRange(errors.Select(error =>
                            file + ": " + error));
                        continue;
                    }
                    if (!string.Equals(project.PackageId,
                        descriptor.PackageId,
                        StringComparison.OrdinalIgnoreCase))
                    {
                        diagnostics.Add(file +
                            ": package_id does not match its receipt");
                        continue;
                    }
                    if ((project.Streaming?.RequiresLease ?? true) &&
                        project.RequiredIpls.Length == 0)
                    {
                        diagnostics.Add(file +
                            ": content-group-only activation is unavailable on " +
                            "the safe cross-edition runtime; declare at least one IPL");
                        continue;
                    }
                    if (!project.Editions.Contains(
                        runtimeEdition ?? string.Empty,
                        StringComparer.OrdinalIgnoreCase))
                    {
                        diagnostics.Add(file + ": project does not target " +
                            (runtimeEdition ?? "unknown"));
                        continue;
                    }
                    string identity = project.PackageId + ":" + project.Id;
                    if (!identities.Add(identity))
                    {
                        diagnostics.Add(file + ": duplicate project identity " +
                            identity);
                        continue;
                    }
                    projects.Add(project);
                }
                catch (Exception ex)
                {
                    diagnostics.Add(file + ": load failed (" +
                        ex.GetType().Name + ")");
                }
            }
            if (descriptors.Length > MaximumProjects)
                diagnostics.Add("map receipts: project count exceeds " +
                    MaximumProjects);
            return new MapProjectLoadResult(projects, diagnostics, fingerprint);
        }

        private static string FileFingerprint(string path)
        {
            try
            {
                var info = new FileInfo(path);
                return path.ToLowerInvariant() + ":" + info.Length + ":" +
                    info.LastWriteTimeUtc.Ticks;
            }
            catch { return path.ToLowerInvariant() + ":unreadable"; }
        }
    }

    internal static class MapPackageRuntimeRegistry
    {
        private static readonly object Sync = new object();
        private static MapProjectDefinition[] _projects =
            Array.Empty<MapProjectDefinition>();

        internal static IReadOnlyList<MapProjectDefinition> Projects
        {
            get { lock (Sync) return _projects.ToArray(); }
        }

        internal static IReadOnlyList<MapGarageDefinition> Garages
        {
            get
            {
                lock (Sync)
                    return _projects.SelectMany(project => project.Garages)
                        .ToArray();
            }
        }

        internal static void Replace(IEnumerable<MapProjectDefinition> projects)
        {
            lock (Sync)
                _projects = (projects ?? Enumerable.Empty<MapProjectDefinition>())
                    .ToArray();
        }
    }

    internal enum MapStreamingZoneAction
    {
        None,
        Acquire,
        Release,
    }

    /// <summary>
    /// Pure hysteresis policy shared by interactive packages and official
    /// streaming-only zones. The gap between activation and release radii
    /// prevents boundary jitter from repeatedly executing content groups.
    /// Unsafe Story states retain the current lease rather than mutating map
    /// content during missions, cutscenes, or another garage transition.
    /// </summary>
    internal static class MapStreamingZonePolicy
    {
        internal static MapStreamingZoneAction Decide(
            bool safe, bool leaseHeld, bool canRelease, bool keepResident,
            float distance, float activationRadius, float releaseRadius)
        {
            if (!safe || float.IsNaN(distance) ||
                float.IsInfinity(distance)) return MapStreamingZoneAction.None;
            if (!leaseHeld && distance <= activationRadius)
                return MapStreamingZoneAction.Acquire;
            if (leaseHeld && canRelease && !keepResident &&
                distance >= releaseRadius)
                return MapStreamingZoneAction.Release;
            return MapStreamingZoneAction.None;
        }
    }

    public sealed class MapPackageRuntime : Script
    {
        private const int ReloadIntervalMs = 15000;
        private const int IdleIntervalMs = 250;
        private const int TransitionCooldownMs = 1200;
        private const int ActivationTimeoutMs = 8000;
        private const int ActivationRetryMs = 10000;
        private const int CollisionTimeoutMs = 2500;

        private sealed class RuntimeState
        {
            internal MapProjectDefinition Project;
            internal bool LeaseHeld;
            internal bool StreamingOnly;
            internal DeferredMapProperty OfficialProperty;
            internal string CurrentLevel = "world";
            internal int CooldownUntil;
            internal int ActivationRetryAt;
        }

        private readonly string _edition;
        private readonly Dictionary<string, RuntimeState> _states =
            new Dictionary<string, RuntimeState>(StringComparer.OrdinalIgnoreCase);
        private string _fingerprint = string.Empty;
        private int _nextReload;
        private bool _transitioning;

        public MapPackageRuntime()
        {
            // Official ALLIN1 garages use their established handlers and do
            // not populate _states. Do not schedule this generic package
            // portal host at rendering frequency when it has no work.
            Interval = IdleIntervalMs;
            _edition = DetectEdition();
            Tick += OnTick;
            Aborted += OnAborted;
            ReloadProjects(force: true);
        }

        private void OnTick(object sender, EventArgs args)
        {
            try
            {
                if (Game.GameTime >= _nextReload)
                    ReloadProjects(force: false);
                // Official ALLIN1 garages use their established transition
                // backends and are deliberately excluded from this generic
                // state table. Avoid paying for the generic interaction-safety
                // native probes every rendered frame when there is no custom
                // map project to service.
                if (_states.Count == 0) return;
                if (Game.IsLoading || _transitioning) return;
                Ped player = Game.Player.Character;
                if (player == null || !player.Exists() || player.IsDead) return;

                bool safe = IsInteractionSafe();
                foreach (RuntimeState state in _states.Values.ToArray())
                {
                    ObserveStreaming(state, player, safe);
                    if (safe && !state.StreamingOnly)
                        DrawAndHandlePortals(state, player);
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("MapRuntime", "tick_failed", ex);
            }
        }

        private void ReloadProjects(bool force)
        {
            _nextReload = Game.GameTime + ReloadIntervalMs;
            IReadOnlyList<MapDescriptorDeclaration> descriptors =
                Allin1ExtensionApi.GetEnabledPackageIds()
                    .SelectMany(Allin1ExtensionApi.GetMapDescriptors)
                    .ToArray();
            MapProjectLoadResult loaded =
                MapProjectDirectoryLoader.LoadAuthorized(
                    descriptors, _edition);
            if (!force && loaded.Fingerprint == _fingerprint) return;
            if (!force && _states.Values.Any(state =>
                !string.Equals(state.CurrentLevel, "world",
                    StringComparison.OrdinalIgnoreCase)))
            {
                // Never tear down an active interior because a registry file
                // changed in the background. Retain the already validated
                // in-memory project until the player exits to the world.
                return;
            }

            foreach (RuntimeState existing in _states.Values)
                if (existing.LeaseHeld) Release(existing, force: true);
            _states.Clear();
            _fingerprint = loaded.Fingerprint;
            foreach (MapProjectDefinition project in loaded.Projects)
            {
                // Official garages keep their established persistence and
                // transition backends. Their SDK descriptors supply layout
                // and IPL data, while this generic portal loop stays out of
                // the way so it cannot duplicate prompts or bypass storage.
                if (OfficialGarageMapProjects.IsOfficial(project))
                {
                    if (OfficialGarageMapProjects
                        .TryGetIsolatedStreamingProperty(
                            project, out DeferredMapProperty property))
                    {
                        _states[project.LeaseKey] = new RuntimeState
                        {
                            Project = project,
                            StreamingOnly = true,
                            OfficialProperty = property,
                            LeaseHeld = false,
                        };
                    }
                    continue;
                }
                _states[project.LeaseKey] = new RuntimeState
                {
                    Project = project,
                    LeaseHeld = !(project.Streaming?.RequiresLease ?? true),
                };
            }
            Interval = TickIntervalForStateCounts(
                _states.Count,
                _states.Values.Count(state => !state.StreamingOnly));
            MapPackageRuntimeRegistry.Replace(loaded.Projects);

            foreach (string diagnostic in loaded.Diagnostics.Take(32))
                ClientLog.Warn("MapRuntime", "project_rejected",
                    new Dictionary<string, object>
                    {
                        { "detail", diagnostic },
                    });
            foreach (MapProjectDefinition project in loaded.Projects)
            {
                bool officialGarageAdapter =
                    OfficialGarageMapProjects.IsOfficial(project);
                ClientLog.Info("MapRuntime", "project_registered",
                    new Dictionary<string, object>
                    {
                        { "package_id", project.PackageId },
                        { "project_id", project.Id },
                        { "portal_count", project.Portals.Length },
                        { "garage_count", project.Garages.Length },
                        { "garage_storage_runtime", officialGarageAdapter },
                        { "portal_runtime", !officialGarageAdapter },
                        { "proximity_streaming_runtime",
                            officialGarageAdapter &&
                            OfficialGarageMapProjects
                                .TryGetIsolatedStreamingProperty(
                                    project, out _) },
                    });
                foreach (MapGarageDefinition garage in project.Garages)
                    ClientLog.Info("MapRuntime", "garage_hook_registered",
                        new Dictionary<string, object>
                        {
                            { "package_id", project.PackageId },
                            { "project_id", project.Id },
                            { "garage_id", garage.Id },
                            { "portal_id", garage.EntrancePortalId },
                            { "slot_count", garage.Slots.Length },
                            { "capacity", garage.Capacity },
                            { "persistence_available", officialGarageAdapter },
                            { "story_save_only", officialGarageAdapter &&
                                string.Equals(garage.Rules?.SavePolicy,
                                    "story_save_only",
                                    StringComparison.OrdinalIgnoreCase) },
                        });
            }
        }

        internal static int TickIntervalForProjectCount(int projectCount)
        {
            return projectCount > 0 ? 0 : IdleIntervalMs;
        }

        internal static int TickIntervalForStateCounts(
            int stateCount, int interactivePortalCount)
        {
            if (stateCount <= 0 || interactivePortalCount <= 0)
                return IdleIntervalMs;
            return 0;
        }

        private static bool IsInteractionSafe()
        {
            try
            {
                return !Game.IsMissionActive && !Game.IsCutsceneActive &&
                    Game.Player.WantedLevel == 0 &&
                    !GarageManager.IsUnsafeGarageTransitionActive();
            }
            catch { return false; }
        }

        private void ObserveStreaming(
            RuntimeState state, Ped player, bool safe)
        {
            float nearestWorld = NearestWorldEndpointDistance(
                state.Project, player.Position);
            MapStreamingZoneAction action = MapStreamingZonePolicy.Decide(
                safe, state.LeaseHeld,
                state.StreamingOnly || string.Equals(
                    state.CurrentLevel, "world",
                    StringComparison.OrdinalIgnoreCase),
                state.Project.Streaming.KeepResident,
                nearestWorld, state.Project.Streaming.ActivationRadius,
                state.Project.Streaming.ReleaseRadius);
            if (action == MapStreamingZoneAction.Acquire) Acquire(state);
            else if (action == MapStreamingZoneAction.Release)
                Release(state, force: false);
        }

        private void DrawAndHandlePortals(RuntimeState state, Ped player)
        {
            bool inVehicle = player.IsInVehicle();
            foreach (MapPortalDefinition portal in state.Project.Portals)
            {
                if (!ModeAllows(portal.Mode, inVehicle)) continue;
                bool garagePortal = state.Project.Garages.Any(garage =>
                    string.Equals(garage.EntrancePortalId, portal.Id,
                        StringComparison.OrdinalIgnoreCase));
                DrawEndpointIfAvailable(state, portal.From, garagePortal);
                if (!portal.OneWay)
                    DrawEndpointIfAvailable(state, portal.To, garagePortal);

                MapPortalEndpoint source = null;
                MapPortalEndpoint destination = null;
                float fromDistance = AvailableEndpoint(state, portal.From)
                    ? player.Position.DistanceTo(portal.From.Point.Position)
                    : float.MaxValue;
                float toDistance = !portal.OneWay &&
                    AvailableEndpoint(state, portal.To)
                    ? player.Position.DistanceTo(portal.To.Point.Position)
                    : float.MaxValue;
                if (fromDistance <= portal.Radius && fromDistance <= toDistance)
                {
                    source = portal.From;
                    destination = portal.To;
                }
                else if (toDistance <= portal.Radius)
                {
                    source = portal.To;
                    destination = portal.From;
                }
                if (source == null || Game.GameTime < state.CooldownUntil)
                    continue;

                GTA.UI.Screen.ShowHelpTextThisFrame(
                    "Press ~INPUT_CONTEXT~ to use " + portal.Name + ".");
                if (!Game.IsControlJustPressed(Control.Context)) continue;
                Transition(state, portal, source, destination, player);
                break;
            }
        }

        private static void DrawEndpointIfAvailable(
            RuntimeState state, MapPortalEndpoint endpoint, bool garagePortal)
        {
            if (!AvailableEndpoint(state, endpoint)) return;
            Vector3 point = endpoint.Point.Position;
            World.DrawMarker(MarkerType.VerticalCylinder,
                point - new Vector3(0f, 0f, 0.85f),
                Vector3.Zero, Vector3.Zero,
                new Vector3(1.2f, 1.2f, 0.75f),
                garagePortal
                    ? Color.FromArgb(145, 65, 165, 225)
                    : Color.FromArgb(135, 56, 190, 115));
        }

        private static bool AvailableEndpoint(
            RuntimeState state, MapPortalEndpoint endpoint) =>
            endpoint != null && endpoint.Point != null &&
            string.Equals(endpoint.Level, state.CurrentLevel,
                StringComparison.OrdinalIgnoreCase) &&
            (string.Equals(endpoint.Level, "world",
                 StringComparison.OrdinalIgnoreCase) || state.LeaseHeld);

        private void Transition(
            RuntimeState state, MapPortalDefinition portal,
            MapPortalEndpoint source, MapPortalEndpoint destination, Ped player)
        {
            if (!state.LeaseHeld && !Acquire(state))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~y~This map could not be loaded safely.", 3500);
                return;
            }

            Entity entity = player.IsInVehicle() &&
                portal.Mode != MapPortalMode.Ped
                    ? (Entity)player.CurrentVehicle : player;
            if (entity == null || !entity.Exists()) return;
            _transitioning = true;
            bool focusSet = false;
            try
            {
                Function.Call(Hash.DO_SCREEN_FADE_OUT, 250);
                int fadeStart = Game.GameTime;
                while (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT) &&
                       Game.GameTime - fadeStart < 1000)
                    Wait(0);
                MapPoint target = destination.Point;
                Function.Call(Hash.SET_FOCUS_POS_AND_VEL,
                    target.X, target.Y, target.Z, 0f, 0f, 0f);
                focusSet = true;
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    target.X, target.Y, target.Z);
                entity.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_VELOCITY,
                    entity.Handle, 0f, 0f, 0f);
                Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET,
                    entity.Handle, target.X, target.Y, target.Z,
                    false, false, false);
                Function.Call(Hash.SET_ENTITY_HEADING,
                    entity.Handle, target.Heading);
                int collisionStartedAt = Game.GameTime;
                while (!Function.Call<bool>(
                           Hash.HAS_COLLISION_LOADED_AROUND_ENTITY,
                           entity.Handle) &&
                       Game.GameTime - collisionStartedAt < CollisionTimeoutMs)
                {
                    Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                        target.X, target.Y, target.Z);
                    Wait(0);
                }
                entity.IsPositionFrozen = false;
                state.CurrentLevel = destination.Level;
                state.CooldownUntil = Game.GameTime + TransitionCooldownMs;
                Function.Call(Hash.DO_SCREEN_FADE_IN, 300);
                ClientLog.Info("MapRuntime", "portal_transition_completed",
                    new Dictionary<string, object>
                    {
                        { "package_id", state.Project.PackageId },
                        { "project_id", state.Project.Id },
                        { "portal_id", portal.Id },
                        { "from_level", source.Level },
                        { "to_level", destination.Level },
                        { "vehicle", entity is Vehicle },
                    });
            }
            catch (Exception ex)
            {
                try { entity.IsPositionFrozen = false; } catch { }
                try { Function.Call(Hash.DO_SCREEN_FADE_IN, 0); } catch { }
                ClientLog.Error("MapRuntime", "portal_transition_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "package_id", state.Project.PackageId },
                        { "project_id", state.Project.Id },
                        { "portal_id", portal.Id },
                    });
            }
            finally
            {
                if (focusSet)
                {
                    try { Function.Call(Hash.CLEAR_FOCUS); } catch { }
                }
                _transitioning = false;
            }

            if (string.Equals(destination.Level, "world",
                StringComparison.OrdinalIgnoreCase) &&
                !state.Project.Streaming.KeepResident)
                Release(state, force: false);
        }

        private bool Acquire(RuntimeState state)
        {
            if (state.LeaseHeld) return true;
            if (!(state.Project.Streaming?.RequiresLease ?? true))
            {
                state.LeaseHeld = true;
                return true;
            }
            if (Game.GameTime < state.ActivationRetryAt) return false;
            MapProjectDefinition project = state.Project;
            DeferredMapContentResult result = state.StreamingOnly
                ? DeferredMapContentRuntime.TryAcquireProximity(
                    state.OfficialProperty, project.RequiredIpls,
                    ActivationTimeoutMs)
                : DeferredMapContentRuntime.TryAcquireRegistered(
                    project.LeaseKey, project.LeaseGroup,
                    project.RequiredIpls,
                    project.Streaming.KeepResident,
                    ActivationTimeoutMs);
            state.LeaseHeld = result.Success;
            state.ActivationRetryAt = result.Success
                ? 0 : Game.GameTime + ActivationRetryMs;
            ClientLog.Info("MapRuntime", "project_activation_result",
                new Dictionary<string, object>
                {
                    { "package_id", project.PackageId },
                    { "project_id", project.Id },
                    { "outcome", result.Outcome.ToString().ToLowerInvariant() },
                    { "elapsed_ms", result.ElapsedMilliseconds },
                });
            return state.LeaseHeld;
        }

        private static void Release(RuntimeState state, bool force)
        {
            if (!state.LeaseHeld) return;
            MapProjectDefinition project = state.Project;
            if (!(project.Streaming?.RequiresLease ?? true)) return;
            DeferredMapContentResult result = state.StreamingOnly
                ? DeferredMapContentRuntime.Release(
                    state.OfficialProperty, project.RequiredIpls, force)
                : DeferredMapContentRuntime.ReleaseRegistered(
                    project.LeaseKey, project.LeaseGroup,
                    project.RequiredIpls,
                    project.Streaming.KeepResident, force);
            if (result.ReleaseComplete ||
                result.Outcome == DeferredMapContentOutcome.KeptResident)
                state.LeaseHeld = result.Outcome ==
                    DeferredMapContentOutcome.KeptResident;
        }

        private static float NearestWorldEndpointDistance(
            MapProjectDefinition project, Vector3 position)
        {
            float nearest = float.MaxValue;
            foreach (MapPortalDefinition portal in project.Portals)
            {
                if (string.Equals(portal.From.Level, "world",
                    StringComparison.OrdinalIgnoreCase))
                    nearest = Math.Min(nearest,
                        position.DistanceTo(portal.From.Point.Position));
                if (string.Equals(portal.To.Level, "world",
                    StringComparison.OrdinalIgnoreCase))
                    nearest = Math.Min(nearest,
                        position.DistanceTo(portal.To.Point.Position));
            }
            return nearest;
        }

        private static bool ModeAllows(MapPortalMode mode, bool inVehicle) =>
            mode == MapPortalMode.Both ||
            (mode == MapPortalMode.Vehicle && inVehicle) ||
            (mode == MapPortalMode.Ped && !inVehicle);

        private static string DetectEdition()
        {
            try
            {
                string executable = System.Diagnostics.Process.GetCurrentProcess()
                    .MainModule?.FileName ?? string.Empty;
                return Path.GetFileName(executable).IndexOf(
                    "Enhanced", StringComparison.OrdinalIgnoreCase) >= 0
                    ? "enhanced" : "legacy";
            }
            catch { return "legacy"; }
        }

        private void OnAborted(object sender, EventArgs args)
        {
            foreach (RuntimeState state in _states.Values)
                if (state.LeaseHeld) Release(state, force: true);
            MapPackageRuntimeRegistry.Replace(
                Enumerable.Empty<MapProjectDefinition>());
        }
    }
}
