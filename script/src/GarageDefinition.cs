// Shared garage identity and entry-policy definitions. New garage
// implementations should define one profile here and route every entrance
// through GarageManager's common policy evaluator.

namespace ALLIN1
{
    internal enum GarageEntryDenial
    {
        None,
        MissionActive,
        WantedLevel,
        StoryOwnedVehicle,
        VehicleTooLarge,
    }

    internal sealed class GarageEntryRules
    {
        internal bool DisableDuringMissions { get; }
        internal bool BlockWantedLevel { get; }
        internal bool BlockStoryOwnedVehicles { get; }
        internal int MaximumVehicleSizeTier { get; }
        internal string OversizedVehicleHint { get; }

        internal GarageEntryRules(
            bool disableDuringMissions,
            bool blockWantedLevel,
            bool blockStoryOwnedVehicles,
            int maximumVehicleSizeTier,
            string oversizedVehicleHint = "")
        {
            DisableDuringMissions = disableDuringMissions;
            BlockWantedLevel = blockWantedLevel;
            BlockStoryOwnedVehicles = blockStoryOwnedVehicles;
            MaximumVehicleSizeTier = maximumVehicleSizeTier;
            OversizedVehicleHint = oversizedVehicleHint ?? "";
        }
    }

    internal sealed class GarageDefinition
    {
        internal string Id { get; }
        internal string DisplayName { get; }
        internal GarageEntryRules EntryRules { get; }
        internal bool RequiresMultiplayerMap { get; }

        internal GarageDefinition(
            string id, string displayName, GarageEntryRules entryRules,
            bool requiresMultiplayerMap = false)
        {
            Id = id;
            DisplayName = displayName;
            EntryRules = entryRules;
            RequiresMultiplayerMap = requiresMultiplayerMap;
        }
    }

    internal static class GarageEntryPolicy
    {
        internal static GarageEntryDenial Evaluate(
            GarageEntryRules rules,
            bool missionActive,
            int wantedLevel,
            bool garagesAlwaysAccessible,
            bool vehiclePresent,
            bool storyOwnedVehicle,
            bool vehicleSizeKnown,
            int vehicleSizeTier)
        {
            if (rules == null)
                return GarageEntryDenial.MissionActive;
            if (rules.DisableDuringMissions && missionActive)
                return GarageEntryDenial.MissionActive;
            if (rules.BlockWantedLevel && wantedLevel > 0
                && !garagesAlwaysAccessible)
                return GarageEntryDenial.WantedLevel;
            if (vehiclePresent && rules.BlockStoryOwnedVehicles && storyOwnedVehicle)
                return GarageEntryDenial.StoryOwnedVehicle;
            if (vehiclePresent && vehicleSizeKnown &&
                vehicleSizeTier > rules.MaximumVehicleSizeTier)
                return GarageEntryDenial.VehicleTooLarge;
            return GarageEntryDenial.None;
        }
    }

    internal static class GarageDefinitions
    {
        internal static readonly GarageDefinition Eclipse = new GarageDefinition(
            "eclipse", "Eclipse Garage",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1,
                oversizedVehicleHint: " Use the Harmony Garage."));

        internal static readonly GarageDefinition ThreeFloor = new GarageDefinition(
            "three_floor", "Harmony Garage",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 2),
            requiresMultiplayerMap: true);

        internal static readonly GarageDefinition Davis = new GarageDefinition(
            "davis", "Davis Auto Shop",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1),
            requiresMultiplayerMap: true);

        internal static readonly GarageDefinition GarmentFactory = new GarageDefinition(
            "garment_factory", "Garment Factory garage",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1),
            requiresMultiplayerMap: true);

        internal static readonly GarageDefinition Rural = new GarageDefinition(
            "rural", "Grapeseed Garage",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1),
            requiresMultiplayerMap: false);
    }
}
