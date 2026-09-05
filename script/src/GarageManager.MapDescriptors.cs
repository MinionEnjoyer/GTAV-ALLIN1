// GarageManager.MapDescriptors.cs -- official SDK map descriptors bridged to
// the mature Story garage backends.
//
// The descriptors are the spatial/streaming source of truth. GarageManager
// deliberately remains the behavior and persistence owner during this
// migration so existing save ids, vehicle capture, virtual floors,
// customization, rollback, and Story-save-only commits remain compatible.

using System;
using System.Collections.Generic;
using System.Linq;
using GTA.Math;

namespace ALLIN1
{
    /// <summary>
    /// Runtime-neutral ownership predicate shared by the map runtime and the
    /// garage compatibility bridge. Keeping this outside GarageManager avoids
    /// initializing GTA-native garage state merely to classify a descriptor.
    /// </summary>
    internal static class OfficialGarageMapProjects
    {
        internal const string PackageId = "allin1.online-content";
        private static readonly HashSet<string> ProjectIds =
            new HashSet<string>(new[]
            {
                "eclipse-garage",
                "harmony-garage",
                "davis-auto-shop",
                "garment-factory-garage",
                "grapeseed-garage",
                "paleto-garage",
            }, StringComparer.OrdinalIgnoreCase);

        internal static int Count => ProjectIds.Count;

        internal static bool IsOfficial(MapProjectDefinition project)
        {
            return project != null && string.Equals(
                project.PackageId, PackageId,
                StringComparison.OrdinalIgnoreCase) &&
                ProjectIds.Contains(project.Id ?? string.Empty);
        }

        internal static bool ContainsId(string projectId)
        {
            return ProjectIds.Contains(projectId ?? string.Empty);
        }

        /// <summary>
        /// Only Davis Phase A enters the non-mutating proximity observation
        /// table. Grapeseed is deliberately absent: its Phase B descriptor is
        /// entry-only and session-resident, and activation belongs exclusively
        /// to the owned black garage transition. Being an official descriptor
        /// is never authority to execute a content-change group.
        /// </summary>
        internal static bool TryGetIsolatedStreamingProperty(
            MapProjectDefinition project, out DeferredMapProperty property)
        {
            property = default;
            if (!IsOfficial(project) || !string.Equals(
                    project.Id, "davis-auto-shop",
                    StringComparison.OrdinalIgnoreCase))
                return false;
            // Phase A keeps Davis in this non-mutating state table so the boot
            // test can prove that proximity reaches the explicit guard. Once
            // Phase B is armed, Davis activation belongs exclusively to the
            // garage-entry black transition and must not be proximity driven.
            if (DavisStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized)
                return false;
            property = DeferredMapProperty.Davis;
            return true;
        }
    }

    internal static partial class GarageManager
    {
        private static int _descriptorBackedGarageCount;
        private static bool _descriptorBindingAttempted;

        internal static int DescriptorBackedGarageCount =>
            _descriptorBackedGarageCount;

        internal static bool IsOfficialGarageDescriptorProject(
            MapProjectDefinition project)
        {
            return OfficialGarageMapProjects.IsOfficial(project);
        }

        private static void EnsureOfficialGarageDescriptorsBound()
        {
            if (_descriptorBindingAttempted) return;
            _descriptorBindingAttempted = true;
            ApplyOfficialGarageDescriptors();
        }

        private static void ApplyOfficialGarageDescriptors()
        {
            try
            {
                Dictionary<string, MapProjectDefinition> projects =
                    LoadOfficialGarageProjects();
                int bound = 0;
                if (TryBindEclipse(projects)) bound++;
                if (TryBindHarmony(projects)) bound++;
                if (TryBindDavis(projects)) bound++;
                if (TryBindGarmentFactory(projects)) bound++;
                if (TryBindGrapeseed(projects)) bound++;
                if (TryBindPaleto(projects)) bound++;
                _descriptorBackedGarageCount = bound;
                ClientLog.Info("Garage", "official_map_descriptors_bound",
                    new Dictionary<string, object>
                    {
                        { "bound", bound },
                        { "expected", OfficialGarageMapProjects.Count },
                        { "fallbacks", OfficialGarageMapProjects.Count - bound },
                        { "save_identity_preserved", true },
                    });
            }
            catch (Exception ex)
            {
                _descriptorBackedGarageCount = 0;
                ClientLog.Error("Garage", "official_map_descriptor_bind_failed",
                    ex, new Dictionary<string, object>
                    {
                        { "fallback_layouts_active", true },
                    });
            }
        }

        private static Dictionary<string, MapProjectDefinition>
            LoadOfficialGarageProjects()
        {
            var projects = new Dictionary<string, MapProjectDefinition>(
                StringComparer.OrdinalIgnoreCase);
            string runtimeEdition =
                GarageMapDetectionCacheRuntime.DetectRuntimeEdition();
            bool detectionAvailable =
                GarageMapDetectionCacheRuntime.TryLoadCurrent(
                    runtimeEdition, out GarageMapDetectionCache detection,
                    out string detectionSource, out string detectionReason);
            int detectionApplied = 0;
            int detectionRejected = 0;
            if (detectionAvailable)
            {
                ClientLog.Info("Garage", "map_detection_cache_ready",
                    new Dictionary<string, object>
                    {
                        { "edition", runtimeEdition },
                        { "source", detectionSource },
                        { "projects", detection.ProjectCount },
                        { "source_identity",
                            detection.SourceIdentityFingerprint },
                    });
            }
            else if (!string.Equals(
                detectionReason, "missing", StringComparison.Ordinal))
            {
                ClientLog.Warn("Garage", "map_detection_cache_rejected",
                    new Dictionary<string, object>
                    {
                        { "edition", runtimeEdition },
                        { "source", detectionSource },
                        { "reason", detectionReason },
                        { "bundled_descriptors_retained", true },
                    });
            }
            foreach (MapDescriptorDeclaration declaration in
                Allin1ExtensionApi.GetMapDescriptors(
                    OfficialGarageMapProjects.PackageId))
            {
                try
                {
                    string descriptorJson;
                    if (!EarlyStartupSnapshot.TryGetTextByPath(
                            declaration.Source, out descriptorJson))
                        descriptorJson = System.IO.File.ReadAllText(
                            declaration.SourcePath);
                    if (!MapProjectParser.TryParse(
                            descriptorJson,
                            out MapProjectDefinition project,
                            out IReadOnlyList<string> errors) ||
                        project == null ||
                        !string.Equals(project.PackageId,
                            OfficialGarageMapProjects.PackageId,
                            StringComparison.OrdinalIgnoreCase) ||
                        !OfficialGarageMapProjects.ContainsId(project.Id) ||
                        projects.ContainsKey(project.Id))
                    {
                        ClientLog.Warn("Garage", "official_map_descriptor_rejected",
                            new Dictionary<string, object>
                            {
                                { "source", declaration.Source },
                                { "detail", string.Join("; ",
                                    (errors ?? Array.Empty<string>()).Take(4)) },
                            });
                    }
                    else
                    {
                        if (detectionAvailable && detection.ContainsProject(
                                project.Id))
                        {
                            bool applied = detection.TryApplyVerifiedMappings(
                                descriptorJson, project,
                                out GarageMapDetectionApplyResult result);
                            if (applied)
                            {
                                detectionApplied++;
                                ClientLog.Info("Garage",
                                    "map_detection_project_applied",
                                    new Dictionary<string, object>
                                    {
                                        { "project_id", project.Id },
                                        { "mapping_count", result.MappingCount },
                                        { "changed_occurrences",
                                            result.ChangedOccurrences },
                                    });
                            }
                            else if (string.Equals(result.Status, "verified",
                                StringComparison.Ordinal))
                            {
                                detectionRejected++;
                                ClientLog.Warn("Garage",
                                    "map_detection_project_rejected",
                                    new Dictionary<string, object>
                                    {
                                        { "project_id", project.Id },
                                        { "reason", result.Reason },
                                        { "bundled_descriptor_retained", true },
                                    });
                            }
                        }
                        projects.Add(project.Id, project);
                    }
                }
                catch (Exception ex)
                {
                    ClientLog.Error("Garage", "official_map_descriptor_read_failed",
                        ex, new Dictionary<string, object>
                        {
                            { "source", declaration.Source },
                        });
                }
            }
            if (detectionAvailable)
            {
                ClientLog.Info("Garage", "map_detection_cache_consumed",
                    new Dictionary<string, object>
                    {
                        { "applied_projects", detectionApplied },
                        { "rejected_verified_projects", detectionRejected },
                        { "loaded_descriptors", projects.Count },
                    });
            }
            return projects;
        }

        private static bool TryBindEclipse(
            IDictionary<string, MapProjectDefinition> projects)
        {
            if (!TryLayout(projects, "eclipse-garage", "eclipse", 10,
                    out MapProjectDefinition project,
                    out MapGarageDefinition garage,
                    out ParkingSlot[] slots)) return false;
            if (!TryPortal(project, "eclipse-vehicle-entry",
                    out MapPortalDefinition vehicleEntry) ||
                !TryPortal(project, "eclipse-vehicle-exit",
                    out MapPortalDefinition vehicleExit) ||
                !TryPortal(project, "eclipse-ped",
                    out MapPortalDefinition ped)) return false;

            ENTRANCE_POS = WorldPoint(vehicleEntry).Position;
            ENTRANCE_HEADING = WorldPoint(vehicleEntry).Heading;
            INTERIOR_SPAWN = LevelPoint(vehicleEntry, garage.LevelId).Position;
            INTERIOR_SPAWN_HEADING =
                LevelPoint(vehicleEntry, garage.LevelId).Heading;
            VEHICLE_EXIT_INTERIOR =
                LevelPoint(vehicleExit, garage.LevelId).Position;
            VEHICLE_EXIT_INTERIOR_HEADING =
                LevelPoint(vehicleExit, garage.LevelId).Heading;
            PED_EXIT_DEST = WorldPoint(ped).Position;
            PED_EXIT_DEST_HEADING = WorldPoint(ped).Heading;
            PED_EXIT = LevelPoint(ped, garage.LevelId).Position;
            PED_EXIT_HEADING = LevelPoint(ped, garage.LevelId).Heading;
            Slots = PreserveFloorPlanes(slots, Slots);
            return true;
        }

        private static bool TryBindHarmony(
            IDictionary<string, MapProjectDefinition> projects)
        {
            if (!TryLayout(projects, "harmony-garage", "three_floor", 25,
                    out MapProjectDefinition project,
                    out MapGarageDefinition garage,
                    out ParkingSlot[] slots) ||
                !TryPortal(project, "harmony-vehicle",
                    out MapPortalDefinition vehicle) ||
                !TryPortal(project, "harmony-ped",
                    out MapPortalDefinition ped) ||
                !TryLevel(project, garage.LevelId,
                    out MapLevelDefinition level)) return false;

            FLOOR_GARAGE_ENTRANCE_POS = WorldPoint(vehicle).Position;
            FLOOR_GARAGE_ENTRANCE_HEADING = WorldPoint(vehicle).Heading;
            FLOOR_GARAGE_PED_EXIT_DEST = WorldPoint(ped).Position;
            FLOOR_GARAGE_PED_EXIT_DEST_HEADING = WorldPoint(ped).Heading;
            FLOOR_GARAGE_INTERIOR_PED =
                LevelPoint(ped, garage.LevelId).Position;
            FLOOR_GARAGE_INTERIOR_PED_HEADING =
                LevelPoint(ped, garage.LevelId).Heading;
            FLOOR_GARAGE_INTERIOR_CENTER = level.Center.Position;
            FLOOR_GARAGE_IPLS = project.RequiredIpls;
            FLOOR_GARAGE_REQUIRED_IPLS = project.RequiredIpls;
            FloorGarageSlots = PreserveFloorPlanes(slots, FloorGarageSlots);
            _floorGaragePhysicalSlots = FloorGarageSlots.Take(
                FLOOR_GARAGE_SLOTS_PER_FLOOR).ToArray();
            return true;
        }

        private static bool TryBindDavis(
            IDictionary<string, MapProjectDefinition> projects)
        {
            if (!TryLayout(projects, "davis-auto-shop", "davis", 10,
                    out MapProjectDefinition project,
                    out MapGarageDefinition garage,
                    out ParkingSlot[] slots) ||
                !TryPortal(project, "davis-vehicle",
                    out MapPortalDefinition vehicle) ||
                !TryPortal(project, "davis-ped",
                    out MapPortalDefinition ped) ||
                !TryLevel(project, garage.LevelId,
                    out MapLevelDefinition level)) return false;

            DAVIS_VEHICLE_ENTRANCE_POS = WorldPoint(vehicle).Position;
            DAVIS_VEHICLE_ENTRANCE_HEADING = WorldPoint(vehicle).Heading;
            DAVIS_PED_ENTRANCE_POS = WorldPoint(ped).Position;
            DAVIS_PED_ENTRANCE_HEADING = WorldPoint(ped).Heading;
            DAVIS_INTERIOR_PED = LevelPoint(ped, garage.LevelId).Position;
            DAVIS_INTERIOR_PED_HEADING =
                LevelPoint(ped, garage.LevelId).Heading;
            DAVIS_INTERIOR_CENTER = level.Center.Position;
            DAVIS_AUTO_SHOP_IPLS = project.RequiredIpls;
            DavisGarageSlots = PreserveFloorPlanes(slots, DavisGarageSlots);
            return true;
        }

        private static bool TryBindGarmentFactory(
            IDictionary<string, MapProjectDefinition> projects)
        {
            if (!TryLayout(projects, "garment-factory-garage",
                    "garment_factory", 10, out MapProjectDefinition project,
                    out MapGarageDefinition garage,
                    out ParkingSlot[] slots) ||
                !TryPortal(project, "garment-factory-vehicle",
                    out MapPortalDefinition vehicle) ||
                !TryPortal(project, "garment-factory-ped",
                    out MapPortalDefinition ped)) return false;

            GARMENT_VEHICLE_ENTRANCE_POS = WorldPoint(vehicle).Position;
            GARMENT_VEHICLE_ENTRANCE_HEADING = WorldPoint(vehicle).Heading;
            GARMENT_PED_ENTRANCE_POS = WorldPoint(ped).Position;
            GARMENT_PED_ENTRANCE_HEADING = WorldPoint(ped).Heading;
            GARMENT_INTERIOR_PED = LevelPoint(ped, garage.LevelId).Position;
            GARMENT_INTERIOR_PED_HEADING =
                LevelPoint(ped, garage.LevelId).Heading;
            GARMENT_IPLS = project.RequiredIpls;
            GarmentFactorySlots = PreserveFloorPlanes(
                slots, GarmentFactorySlots);
            return true;
        }

        private static bool TryBindGrapeseed(
            IDictionary<string, MapProjectDefinition> projects)
        {
            if (!TryLayout(projects, "grapeseed-garage", "rural", 6,
                    out MapProjectDefinition project,
                    out MapGarageDefinition garage,
                    out ParkingSlot[] slots) ||
                !TryPortal(project, "rural-vehicle",
                    out MapPortalDefinition vehicle) ||
                !TryPortal(project, "rural-ped",
                    out MapPortalDefinition ped) ||
                !TryLevel(project, garage.LevelId,
                    out MapLevelDefinition level)) return false;

            RURAL_VEHICLE_ENTRANCE_POS = WorldPoint(vehicle).Position;
            RURAL_VEHICLE_ENTRANCE_HEADING = WorldPoint(vehicle).Heading;
            RURAL_PED_ENTRANCE_POS = WorldPoint(ped).Position;
            RURAL_PED_ENTRANCE_HEADING = WorldPoint(ped).Heading;
            RURAL_INTERIOR_PED = LevelPoint(ped, garage.LevelId).Position;
            RURAL_INTERIOR_PED_HEADING =
                LevelPoint(ped, garage.LevelId).Heading;
            RURAL_INTERIOR_CENTER = level.Center.Position;
            RURAL_IPLS = project.RequiredIpls;
            RuralSlots = PreserveFloorPlanes(slots, RuralSlots);
            return true;
        }

        private static bool TryBindPaleto(
            IDictionary<string, MapProjectDefinition> projects)
        {
            if (!TryLayout(projects, "paleto-garage", "paleto", 10,
                    out MapProjectDefinition project,
                    out MapGarageDefinition garage,
                    out ParkingSlot[] slots) ||
                !TryPortal(project, "paleto-vehicle",
                    out MapPortalDefinition vehicle) ||
                !TryPortal(project, "paleto-ped",
                    out MapPortalDefinition ped) ||
                !TryPortal(project, "paleto-ped-secondary",
                    out MapPortalDefinition secondary) ||
                !TryLevel(project, garage.LevelId,
                    out MapLevelDefinition level)) return false;

            PALETO_VEHICLE_ENTRANCE_POS = WorldPoint(vehicle).Position;
            PALETO_VEHICLE_ENTRANCE_HEADING = WorldPoint(vehicle).Heading;
            PALETO_PED_ENTRANCE_POS = WorldPoint(ped).Position;
            PALETO_PED_ENTRANCE_HEADING = WorldPoint(ped).Heading;
            MapPoint primaryExit = LevelPoint(ped, garage.LevelId);
            MapPoint secondaryExit = LevelPoint(secondary, garage.LevelId);
            PALETO_INTERIOR_PED_EXITS = new[]
            {
                primaryExit.Position,
                secondaryExit.Position,
            };
            PALETO_INTERIOR_PED_EXIT_HEADINGS = new[]
            {
                primaryExit.Heading,
                secondaryExit.Heading,
            };
            PALETO_INTERIOR_CENTER = level.Center.Position;
            PALETO_IPLS = project.RequiredIpls;
            PaletoSlots = PreserveFloorPlanes(slots, PaletoSlots);
            return true;
        }

        private static bool TryLayout(
            IDictionary<string, MapProjectDefinition> projects,
            string projectId, string garageId, int capacity,
            out MapProjectDefinition project,
            out MapGarageDefinition garage,
            out ParkingSlot[] slots)
        {
            garage = null;
            slots = null;
            if (!projects.TryGetValue(projectId, out project)) return false;
            garage = project.Garages.SingleOrDefault(value => string.Equals(
                value.Id, garageId, StringComparison.OrdinalIgnoreCase));
            if (garage == null || garage.Capacity != capacity ||
                garage.Slots.Length != capacity || garage.Rules == null ||
                !garage.Rules.AllowStore || !garage.Rules.AllowRetrieve ||
                !string.Equals(garage.Rules.SavePolicy, "story_save_only",
                    StringComparison.OrdinalIgnoreCase) ||
                garage.VehicleTypes.Length != 1 ||
                !string.Equals(garage.VehicleTypes[0], "land",
                    StringComparison.OrdinalIgnoreCase)) return false;
            slots = garage.Slots.Select(value => new ParkingSlot(
                value.Point.X, value.Point.Y, value.Point.Z,
                value.Point.Heading)).ToArray();
            return true;
        }

        private static ParkingSlot[] PreserveFloorPlanes(
            ParkingSlot[] descriptorSlots, ParkingSlot[] fallbackSlots)
        {
            if (descriptorSlots == null || fallbackSlots == null ||
                descriptorSlots.Length != fallbackSlots.Length)
                return fallbackSlots;
            var result = new ParkingSlot[descriptorSlots.Length];
            for (int index = 0; index < result.Length; index++)
            {
                ParkingSlot source = descriptorSlots[index];
                result[index] = new ParkingSlot(
                    source.Position.X, source.Position.Y, source.Position.Z,
                    source.Heading, fallbackSlots[index].FloorZ);
            }
            return result;
        }

        private static bool TryPortal(
            MapProjectDefinition project, string id,
            out MapPortalDefinition portal)
        {
            portal = project?.Portals.SingleOrDefault(value => string.Equals(
                value.Id, id, StringComparison.OrdinalIgnoreCase));
            return portal?.From?.Point != null && portal.To?.Point != null;
        }

        private static bool TryLevel(
            MapProjectDefinition project, string id,
            out MapLevelDefinition level)
        {
            level = project?.Levels.SingleOrDefault(value => string.Equals(
                value.Id, id, StringComparison.OrdinalIgnoreCase));
            return level?.Center != null;
        }

        private static MapPoint WorldPoint(MapPortalDefinition portal)
        {
            if (string.Equals(portal.From.Level, "world",
                    StringComparison.OrdinalIgnoreCase)) return portal.From.Point;
            if (string.Equals(portal.To.Level, "world",
                    StringComparison.OrdinalIgnoreCase)) return portal.To.Point;
            throw new InvalidOperationException(
                "Official garage portal does not reach the world");
        }

        private static MapPoint LevelPoint(
            MapPortalDefinition portal, string levelId)
        {
            if (string.Equals(portal.From.Level, levelId,
                    StringComparison.OrdinalIgnoreCase)) return portal.From.Point;
            if (string.Equals(portal.To.Level, levelId,
                    StringComparison.OrdinalIgnoreCase)) return portal.To.Point;
            throw new InvalidOperationException(
                "Official garage portal does not reach its garage level");
        }
    }
}
