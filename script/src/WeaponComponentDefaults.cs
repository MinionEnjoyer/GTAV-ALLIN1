using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using GTA.Native;

namespace ALLIN1
{
    // Native DLC metadata, not English labels or a Vector-specific hash list.
    // GET_DLC_WEAPON_COMPONENT_DATA exposes bActiveByDefault at offset 0x08:
    // https://github.com/citizenfx/natives/blob/master/FILES/GetDlcWeaponComponentData.md
    internal static class WeaponComponentDefaults
    {
        internal readonly struct Entry
        {
            internal readonly int Hash, Point;
            internal readonly bool Default;
            internal Entry(int hash, int point, bool isDefault)
            { Hash = hash; Point = point; Default = isDefault; }
        }

        private sealed class Cached
        {
            internal DateTime Expires;
            internal List<Entry> Entries;
        }
        private static readonly Dictionary<int, Cached> Cache = new Dictionary<int, Cached>();

        internal static int SelectDefault(IEnumerable<Entry> entries, int point)
        {
            int result = 0;
            foreach (Entry entry in entries)
            {
                if (!entry.Default || entry.Point != point || entry.Hash == 0) continue;
                if (result != 0 && result != entry.Hash) return 0; // Ambiguous: do not guess.
                result = entry.Hash;
            }
            return result;
        }

        internal static bool IsDefault(int weaponHash, int componentHash)
        {
            foreach (Entry entry in Read(weaponHash))
                if (entry.Hash == componentHash && entry.Default) return true;
            return false;
        }

        internal static int SelectRestoration(IEnumerable<Entry> entries, int point,
            int removedHash, Func<int, bool> isEquipped)
        {
            if (!WeaponCustomizationPolicy.CanUnequipComponent(point)) return 0;
            int fallback = SelectDefault(entries, point);
            if (fallback == 0 || fallback == removedHash) return 0;
            foreach (Entry entry in entries)
                if (entry.Point == point && entry.Hash != removedHash && isEquipped(entry.Hash))
                    return 0;
            return fallback;
        }

        internal static bool RestoreAfterRemoval(int ped, int weaponHash, int point, int removedHash)
        {
            if (!WeaponCustomizationPolicy.CanUnequipComponent(point)) return true;
            List<Entry> entries = Read(weaponHash);
            int fallback = SelectRestoration(entries, point, removedHash, hash =>
                Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT, ped, weaponHash, hash));
            if (fallback == 0) return true; // Never replace an existing chosen accessory.
            if (!Function.Call<bool>(Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT, weaponHash, fallback)) return false;
            Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED, ped, weaponHash, fallback);
            return Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT, ped, weaponHash, fallback);
        }

        internal static void RestoreEmptySightSlots(int ped, int weaponHash)
        {
            RestoreAfterRemoval(ped, weaponHash, (int)GTA.WeaponAttachmentPoint.Scope, 0);
            RestoreAfterRemoval(ped, weaponHash, (int)GTA.WeaponAttachmentPoint.Scope2, 0);
        }

        private static List<Entry> Read(int weaponHash)
        {
            DateTime now = DateTime.UtcNow;
            if (Cache.TryGetValue(weaponHash, out Cached cached) && cached.Expires > now)
                return cached.Entries;
            var entries = new List<Entry>();
            foreach (bool story in new[] { false, true })
            {
                try
                {
                    var source = new List<Entry>();
                    ReadNative(weaponHash, story, source);
                    entries.AddRange(source); // A failed native pass contributes no partial data.
                }
                catch (Exception ex)
                {
                    ClientLog.Warn("GBAY", "default_component_metadata_unavailable",
                        new Dictionary<string, object> { { "weapon_hash", weaponHash }, { "story", story }, { "error", ex.Message } });
                }
            }
            if (Cache.Count >= 256) Cache.Clear();
            Cache[weaponHash] = new Cached { Expires = now.AddSeconds(30), Entries = entries };
            return entries;
        }

        private static unsafe void ReadNative(int weaponHash, bool story, List<Entry> entries)
        {
            Hash countNative = story ? Hash.GET_NUM_DLC_WEAPONS_SP : Hash.GET_NUM_DLC_WEAPONS;
            Hash weaponNative = story ? Hash.GET_DLC_WEAPON_DATA_SP : Hash.GET_DLC_WEAPON_DATA;
            Hash componentCountNative = story ? Hash.GET_NUM_DLC_WEAPON_COMPONENTS_SP : Hash.GET_NUM_DLC_WEAPON_COMPONENTS;
            Hash componentNative = story ? Hash.GET_DLC_WEAPON_COMPONENT_DATA_SP : Hash.GET_DLC_WEAPON_COMPONENT_DATA;
            int count = Function.Call<int>(countNative);
            if (count < 0 || count > 4096) throw new InvalidOperationException("Unbounded DLC weapon count");
            byte* weapon = stackalloc byte[0x138];
            byte* component = stackalloc byte[0x110];
            for (int wi = 0; wi < count; wi++)
            {
                for (int i = 0; i < 0x138; i++) weapon[i] = 0;
                if (!Function.Call<bool>(weaponNative, wi, (IntPtr)weapon) ||
                    Marshal.ReadInt32((IntPtr)weapon, 0x08) != weaponHash) continue;
                int componentCount = Function.Call<int>(componentCountNative, wi);
                if (componentCount < 0 || componentCount > 256) throw new InvalidOperationException("Unbounded DLC component count");
                for (int ci = 0; ci < componentCount; ci++)
                {
                    for (int i = 0; i < 0x110; i++) component[i] = 0;
                    if (!Function.Call<bool>(componentNative, wi, ci, (IntPtr)component)) continue;
                    int hash = Marshal.ReadInt32((IntPtr)component, 0x18);
                    int point = Marshal.ReadInt32((IntPtr)component, 0x00);
                    int isDefault = Marshal.ReadInt32((IntPtr)component, 0x08);
                    if (hash == 0 || (isDefault != 0 && isDefault != 1) ||
                        !Function.Call<bool>(Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT, weaponHash, hash)) continue;
                    entries.Add(new Entry(hash, point, isDefault == 1));
                }
            }
        }
    }
}
