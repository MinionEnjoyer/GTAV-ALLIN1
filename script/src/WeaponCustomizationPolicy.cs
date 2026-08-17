using System;

namespace ALLIN1
{
    internal static class WeaponCustomizationPolicy
    {
        internal static int ComponentPrice(string attachmentPoint, string name)
        {
            string point = attachmentPoint ?? "";
            string label = name ?? "";
            if (Contains(point, "Clip") || Contains(label, "Magazine") || Contains(label, "Rounds")) return 2500;
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

        private static bool Contains(string value, string search) =>
            value.IndexOf(search, StringComparison.OrdinalIgnoreCase) >= 0;
    }
}
