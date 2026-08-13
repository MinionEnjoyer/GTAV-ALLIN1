// Owns ALLIN1's temporary switch to GTA Online map data. ON_ENTER_MP is a
// global session state, so every acquisition must be paired with ON_ENTER_SP
// or Story Mode interior variants (including beds and furniture) can disappear.

using System;
using System.Collections.Generic;
using GTA.Native;

namespace ALLIN1
{
    internal sealed class DlcMapLeaseRegistry
    {
        private readonly HashSet<string> _owners =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        internal bool IsAcquired(GarageDefinition garage) =>
            garage != null && _owners.Contains(garage.Id);

        internal bool Acquire(GarageDefinition garage)
        {
            if (garage == null || !garage.RequiresMultiplayerMap ||
                !_owners.Add(garage.Id)) return false;
            return _owners.Count == 1;
        }

        internal bool Release(GarageDefinition garage)
        {
            if (garage == null || !garage.RequiresMultiplayerMap ||
                !_owners.Remove(garage.Id)) return false;
            return _owners.Count == 0;
        }

        internal bool ReleaseAll()
        {
            if (_owners.Count == 0) return false;
            _owners.Clear();
            return true;
        }
    }

    internal static class DlcMapState
    {
        private static readonly DlcMapLeaseRegistry Registry =
            new DlcMapLeaseRegistry();

        internal static bool IsAcquired(GarageDefinition garage) =>
            Registry.IsAcquired(garage);

        internal static void Acquire(GarageDefinition garage)
        {
            if (Registry.Acquire(garage))
            {
                Function.Call((Hash)0x0888C3502DBBEEF5); // ON_ENTER_MP
                ClientLog.Info("Garage", "multiplayer_map_acquired",
                    new Dictionary<string, object> { { "garage", garage.Id } });
            }
        }

        internal static void Release(GarageDefinition garage)
        {
            if (Registry.Release(garage))
            {
                Function.Call((Hash)0xD7C10C4A637992C9); // ON_ENTER_SP
                ClientLog.Info("Garage", "story_map_restored",
                    new Dictionary<string, object> { { "garage", garage.Id } });
            }
        }

        internal static void ReleaseAll(string reason)
        {
            if (!Registry.ReleaseAll()) return;
            Function.Call((Hash)0xD7C10C4A637992C9); // ON_ENTER_SP
            ClientLog.Info("Garage", "story_map_restored",
                new Dictionary<string, object> { { "reason", reason } });
        }
    }
}
