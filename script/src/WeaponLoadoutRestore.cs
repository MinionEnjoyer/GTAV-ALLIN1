using System;
using System.Collections.Generic;

namespace ALLIN1
{
    // Pure restore policy: a missing DLC/catalog must never erase a purchase.
    internal sealed class WeaponRestoreResult
    {
        internal readonly List<string> Restored = new List<string>();
        internal readonly Dictionary<string, string> Deferred =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    }

    internal static class WeaponLoadoutRestore
    {
        internal static WeaponRestoreResult Restore(
            CharacterInventory.Inventory inventory, IEnumerable<string> candidates,
            IEnumerable<string> authorizedWeapons, Func<string, bool> isValid,
            Func<string, int, bool> grant, Action<string> customize)
        {
            var result = new WeaponRestoreResult();
            var owned = new HashSet<string>(inventory.weapons, StringComparer.OrdinalIgnoreCase);
            var authorized = new HashSet<string>(authorizedWeapons, StringComparer.OrdinalIgnoreCase);
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string weapon in candidates)
            {
                if (string.IsNullOrWhiteSpace(weapon) || !owned.Contains(weapon) || !seen.Add(weapon))
                    continue;
                if (!authorized.Contains(weapon))
                {
                    result.Deferred[weapon] = "catalog_unavailable";
                    continue;
                }
                try
                {
                    if (!isValid(weapon))
                    {
                        result.Deferred[weapon] = "weapon_not_ready";
                        continue;
                    }
                    int ammo = inventory.weapon_ammo.TryGetValue(weapon, out int saved)
                        ? Math.Max(0, saved) : 9999;
                    if (!grant(weapon, ammo))
                    {
                        result.Deferred[weapon] = "grant_not_confirmed";
                        continue;
                    }
                    customize(weapon);
                    result.Restored.Add(weapon);
                }
                catch (Exception ex)
                {
                    result.Deferred[weapon] = "restore_failed:" + ex.GetType().Name;
                }
            }
            return result;
        }
    }
}
