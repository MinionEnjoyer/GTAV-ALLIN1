// VehicleHelper.cs -- Shared vehicle creation utilities.

using System;
using GTA;
using GTA.Native;
using GTA.Math;

namespace ALLIN1
{
    internal static class VehicleHelper
    {
        private const int DEFAULT_TIMEOUT = 5000;
        private static readonly Random Rng = new Random();

        /// <summary>
        /// Load a vehicle model and create it at the given position.
        /// Returns null if the model fails to load or the vehicle cannot
        /// be created.  Applies random colours and the MPBitset decorator
        /// so the vehicle persists in Story Mode.
        /// </summary>
        internal static Vehicle CreateVehicle(string modelName, Vector3 pos,
                                              float heading,
                                              int timeout = DEFAULT_TIMEOUT)
        {
            int c1 = Rng.Next(0, 160);
            int c2 = Rng.Next(0, 160);
            return CreateVehicle(modelName, pos, heading, c1, c2, timeout);
        }

        /// <summary>
        /// Create a vehicle with explicit colours (used when respawning
        /// stored garage vehicles with their saved colours).
        /// </summary>
        internal static Vehicle CreateVehicle(string modelName, Vector3 pos,
                                              float heading, int color1,
                                              int color2,
                                              int timeout = DEFAULT_TIMEOUT)
        {
            var model = new Model(modelName);
            model.Request(timeout);

            DateTime deadline = DateTime.UtcNow.AddMilliseconds(timeout);
            while (!model.IsLoaded)
            {
                if (DateTime.UtcNow > deadline)
                {
                    model.MarkAsNoLongerNeeded();
                    return null;
                }
                Script.Wait(0);
            }

            Vehicle veh = World.CreateVehicle(model, pos, heading);
            model.MarkAsNoLongerNeeded();

            if (veh == null)
                return null;

            veh.PlaceOnGround();

            Function.Call(Hash.SET_VEHICLE_COLOURS, veh, color1, color2);

            // MPBitset decorator -- prevents despawning in Story Mode
            Function.Call(Hash.DECOR_SET_INT, veh.Handle, "MPBitset", 0);

            return veh;
        }
    }
}
