using System;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal static partial class GarageManager
    {
        /// <summary>
        /// Returns the currently occupied garage, falling back to the normal
        /// personal garage when the player is outside. This is presentation
        /// state only and grants no entry or streaming authority.
        /// </summary>
        internal static string ActiveGarageLocationId =>
            _isPlayerInFloorGarage ? "harmony" :
            _isPlayerInDavisGarage ? "davis" :
            _isPlayerInGarmentGarage ? "garment" :
            _isPlayerInRuralGarage ? "grapeseed" :
            _isPlayerInPaletoGarage ? "paleto" :
            "eclipse";

        internal static bool TrySetGarageWaypoint(
            string locationId, out string label)
        {
            label = "";
            if (!TryResolveGarageWaypoint(
                    locationId, out Vector3 position, out label))
                return false;

            try
            {
                Function.Call(Hash.SET_NEW_WAYPOINT, position.X, position.Y);
                Log("GarageWaypoint: " + locationId + " -> " +
                    position.X.ToString("0.00") + "," +
                    position.Y.ToString("0.00"));
                return true;
            }
            catch (Exception ex)
            {
                LogException("GarageWaypoint(" + locationId + ")", ex);
                return false;
            }
        }

        internal static bool TryResolveGarageWaypoint(
            string locationId, out Vector3 position, out string label)
        {
            label = "";
            switch ((locationId ?? "").Trim().ToLowerInvariant())
            {
                case "eclipse":
                    position = ENTRANCE_POS;
                    label = "Eclipse Garage";
                    return true;
                case "harmony":
                    position = FLOOR_GARAGE_ENTRANCE_POS;
                    label = "Harmony Garage";
                    return true;
                case "davis":
                    position = DAVIS_VEHICLE_ENTRANCE_POS;
                    label = "Davis Auto Shop";
                    return true;
                case "garment":
                    position = GARMENT_VEHICLE_ENTRANCE_POS;
                    label = "Garment Factory";
                    return true;
                case "grapeseed":
                    position = RURAL_VEHICLE_ENTRANCE_POS;
                    label = "Grapeseed Garage";
                    return true;
                case "paleto":
                    position = PALETO_VEHICLE_ENTRANCE_POS;
                    label = "Paleto Bay Garage";
                    return true;
                case "vespucci-helipad":
                    position = HelipadAccessPosition;
                    label = "Vespucci Helipad";
                    return true;
                case "yacht-helipad":
                    position = YachtHelipadPosition;
                    label = "Yacht Helipad";
                    return true;
                case "harbour":
                    position = HarbourAccessPosition;
                    label = "Los Santos Harbour";
                    return true;
                default:
                    position = new Vector3();
                    return false;
            }
        }
    }
}
