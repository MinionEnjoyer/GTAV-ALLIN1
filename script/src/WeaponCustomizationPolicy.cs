using System;
using System.Collections.Generic;

namespace ALLIN1
{
    internal static class WeaponCustomizationPolicy
    {
        // Ammunition is sold on the main weapon screen. A mandatory/default
        // magazine alone is not a customization choice.
        internal static bool HasChoices(IEnumerable<WeaponComponentDefaults.Entry> components, int tintCount)
        {
            if (tintCount > 1) return true;
            var slots = new Dictionary<int, HashSet<int>>();
            foreach (var component in components)
            {
                if (component.Hash == 0 || component.Hash == -1 ||
                    component.Point == unchecked((int)GTA.WeaponAttachmentPoint.Invalid)) continue;
                if (!component.Default && CanUnequipComponent(component.Point)) return true;
                if (!slots.TryGetValue(component.Point, out var hashes))
                    slots[component.Point] = hashes = new HashSet<int>();
                hashes.Add(component.Hash);
                if (hashes.Count > 1) return true;
            }
            return false;
        }

        // Removing a magazine, barrel, receiver or unknown slot may leave a
        // weapon incomplete. Only known optional accessory slots support None.
        internal static bool CanUnequipComponent(int point) =>
            point == (int)GTA.WeaponAttachmentPoint.Scope ||
            point == (int)GTA.WeaponAttachmentPoint.Scope2 ||
            point == (int)GTA.WeaponAttachmentPoint.Supp ||
            point == unchecked((int)GTA.WeaponAttachmentPoint.Supp2) ||
            point == unchecked((int)GTA.WeaponAttachmentPoint.FlashLaser) ||
            point == unchecked((int)GTA.WeaponAttachmentPoint.FlashLaser2) ||
            point == unchecked((int)GTA.WeaponAttachmentPoint.Grip) ||
            point == unchecked((int)GTA.WeaponAttachmentPoint.Grip2);

        internal static int ComponentPrice(string attachmentPoint, string name)
        {
            string point = attachmentPoint ?? "";
            string label = name ?? "";
            if (Contains(point, "Clip") || Contains(label, "Clip") || Contains(label, "Magazine") || Contains(label, "Rounds")) return 2500;
            if (Contains(point, "Scope") || Contains(label, "Scope") || Contains(label, "Sight")) return 3500;
            if (Contains(point, "Muzzle") || Contains(label, "Suppressor") || Contains(label, "Muzzle")) return 5000;
            if (Contains(point, "Barrel") || Contains(label, "Barrel")) return 6000;
            if (Contains(point, "Flash") || Contains(label, "Flashlight")) return 2000;
            if (Contains(point, "Grip") || Contains(label, "Grip")) return 2500;
            if (Contains(point, "GunRoot") || Contains(label, "Livery") || Contains(label, "Camo")) return 7500;
            return 3000;
        }

        internal static int TintPrice(int tintIndex) => tintIndex <= 0
            ? 0 : 1250 + tintIndex * 250;

        internal static int ComponentTintPrice(int tintIndex) => tintIndex <= 0
            ? 0 : 750 + tintIndex * 125;

        internal static bool IsDefaultComponentLabel(string label) =>
            Contains(label ?? "", "Default") ||
            Contains(label ?? "", "Standard");

        internal static bool IsComponentEquipped(
            int componentHash, int savedActiveHash, bool liveActive,
            bool anyLiveInFamily, bool isDefaultComponent)
        {
            if (liveActive) return true;
            if (anyLiveInFamily) return false;
            if (savedActiveHash != 0)
                return savedActiveHash == componentHash;
            return isDefaultComponent;
        }

        internal static bool IsOpaqueComponentLabel(string label) =>
            string.IsNullOrWhiteSpace(label) ||
            (label.StartsWith("Component 0x",
                StringComparison.OrdinalIgnoreCase) && label.Length >= 20);

        internal static string FallbackComponentLabel(string detail)
        {
            string family = string.IsNullOrWhiteSpace(detail)
                ? "Weapon" : detail.Trim();
            return family.EndsWith("upgrade",
                StringComparison.OrdinalIgnoreCase)
                ? family : family + " upgrade";
        }

        private static bool Contains(string value, string search) =>
            value.IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0;
    }
}
