using System;
using GTA.Native;

namespace ALLIN1
{
    internal static partial class GarageManager
    {
        private static OfficialGarageTransitionCoordinator CreateScopedInteriorEntryTransition(
            string garageId, Action rollback) => new OfficialGarageTransitionCoordinator(
                garageId, "entry", () => Environment.TickCount,
                ObserveOfficialGarageTransition, rollback,
                () => Function.Call(Hash.DO_SCREEN_FADE_IN, 0));
    }
}
