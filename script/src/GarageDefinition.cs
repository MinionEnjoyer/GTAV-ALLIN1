// Shared garage identity and entry-policy definitions. New garage
// implementations should define one profile here and route every entrance
// through GarageManager's common policy evaluator.

using System;

namespace ALLIN1
{
    internal enum GarageEntryDenial
    {
        None,
        MissionActive,
        GameTransitionActive,
        WantedLevel,
        StoryOwnedVehicle,
        UnsupportedVehicleType,
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

        internal GarageDefinition(
            string id, string displayName, GarageEntryRules entryRules)
        {
            Id = id;
            DisplayName = displayName;
            EntryRules = entryRules;
        }
    }

    internal static class GarageEntryPolicy
    {
        internal static GarageEntryDenial Evaluate(
            GarageEntryRules rules,
            bool missionActive,
            bool gameTransitionActive,
            int wantedLevel,
            bool garagesAlwaysAccessible,
            bool vehiclePresent,
            bool storyOwnedVehicle,
            bool vehicleSizeKnown,
            int vehicleSizeTier,
            bool unsupportedVehicleType = false)
        {
            if (rules == null)
                return GarageEntryDenial.MissionActive;
            if (rules.DisableDuringMissions && missionActive)
                return GarageEntryDenial.MissionActive;
            if (gameTransitionActive)
                return GarageEntryDenial.GameTransitionActive;
            if (rules.BlockWantedLevel && wantedLevel > 0
                && !garagesAlwaysAccessible)
                return GarageEntryDenial.WantedLevel;
            if (vehiclePresent && rules.BlockStoryOwnedVehicles && storyOwnedVehicle)
                return GarageEntryDenial.StoryOwnedVehicle;
            if (vehiclePresent && unsupportedVehicleType)
                return GarageEntryDenial.UnsupportedVehicleType;
            if (vehiclePresent && vehicleSizeKnown &&
                vehicleSizeTier > rules.MaximumVehicleSizeTier)
                return GarageEntryDenial.VehicleTooLarge;
            return GarageEntryDenial.None;
        }
    }

    internal static class GarageVehicleTypePolicy
    {
        internal static bool RequiresSpecializedStorage(string model)
        {
            if (string.IsNullOrWhiteSpace(model)) return false;
            return !string.Equals(RuntimeVehicleCatalog.GetStorage(model),
                "garage", StringComparison.OrdinalIgnoreCase);
        }

        internal static bool IsRegularGarageEligible(string model) =>
            !RequiresSpecializedStorage(model);

    }

    internal static class GarageStorySavePolicy
    {
        internal static bool HasSaveEvent(
            bool saveInProgress,
            bool saveWasInProgress,
            DateTime latestStorySaveWriteUtc,
            DateTime lastObservedStorySaveWriteUtc)
        {
            return (saveInProgress && !saveWasInProgress)
                || latestStorySaveWriteUtc > lastObservedStorySaveWriteUtc;
        }
    }

    internal static class GarageInteriorReadinessPolicy
    {
        /// <summary>
        /// Enhanced can keep IS_INTERIOR_READY false for valid Online and
        /// apartment garage shells. Prefer the native ready signal, but accept
        /// a stable, resolved interior after a bounded settle interval.
        /// </summary>
        internal static bool IsUsable(
            int interior,
            bool requireIplActive,
            bool iplActive,
            bool interiorReady,
            int resolvedForMs,
            int fallbackSettleMs)
        {
            if (interior == 0) return false;
            if (requireIplActive && !iplActive) return false;
            return interiorReady || resolvedForMs >= fallbackSettleMs;
        }
    }

    internal static class GarageRoomAttachmentPolicy
    {
        /// <summary>
        /// Standalone MLO collision can be marked outside even while GTA has
        /// attached both the player and viewport to the correct interior room.
        /// Interior identity and matching nonzero room keys are the reliable
        /// attachment signals; collision classification remains diagnostic.
        /// </summary>
        internal static bool IsAttached(
            int expectedInterior,
            int playerInterior,
            int playerRoomKey,
            int viewportRoomKey)
        {
            return expectedInterior != 0 &&
                playerInterior == expectedInterior &&
                playerRoomKey != 0 &&
                viewportRoomKey != 0 &&
                playerRoomKey == viewportRoomKey;
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
                maximumVehicleSizeTier: 2));

        internal static readonly GarageDefinition Davis = new GarageDefinition(
            "davis", "Davis Auto Shop",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1));

        internal static readonly GarageDefinition GarmentFactory = new GarageDefinition(
            "garment_factory", "Garment Factory garage",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1));

        internal static readonly GarageDefinition Rural = new GarageDefinition(
            "rural", "Grapeseed Garage",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1));

        internal static readonly GarageDefinition Paleto = new GarageDefinition(
            "paleto", "Paleto Bay Garage",
            new GarageEntryRules(
                disableDuringMissions: true,
                blockWantedLevel: true,
                blockStoryOwnedVehicles: true,
                maximumVehicleSizeTier: 1));
    }
}
