using System;
using System.Collections.Generic;

namespace ALLIN1
{
    /// <summary>
    /// GBAY listings that are persistent world properties rather than vehicle
    /// models. Keeping these separate prevents property purchases from being
    /// sent through vehicle spawning, garage delivery, or traffic systems.
    /// </summary>
    internal static class WorldAssetList
    {
        internal const string SuperYacht = "allin1_super_yacht";
        internal const int SuperYachtPrice = 8000000;

        internal static readonly string[] All = { SuperYacht };

        internal static readonly Dictionary<string, string> PreviewDict =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                { SuperYacht, "allin1_asset_01" },
            };

        internal static bool IsWorldAsset(string id) =>
            string.Equals(id, SuperYacht, StringComparison.OrdinalIgnoreCase);

        internal static string DisplayName(string id) =>
            string.Equals(id, SuperYacht, StringComparison.OrdinalIgnoreCase)
                ? "Galaxy Super Yacht" : id;

        internal static string Manufacturer(string id) =>
            string.Equals(id, SuperYacht, StringComparison.OrdinalIgnoreCase)
                ? "DockTease" : "Property";

        internal static string ClassName(string id) =>
            IsWorldAsset(id) ? "Special Property" : "Property";

        internal static int Price(string id) =>
            string.Equals(id, SuperYacht, StringComparison.OrdinalIgnoreCase)
                ? SuperYachtPrice : 0;
    }
}
