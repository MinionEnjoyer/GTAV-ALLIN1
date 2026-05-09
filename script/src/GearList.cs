// GearList.cs — Static gear item data for the GBAY Gear shop.
//
// Hand-written (no generator) since the list is small and stable.
// Covers body armor, parachute, and utility gadgets.

using System.Collections.Generic;

namespace ALLIN1
{
    internal static class GearList
    {
        // Special ID for armor (not a weapon hash — handled separately)
        internal const string ARMOR_ID = "ARMOR";

        // ------------------------------------------------------------------ //
        //  Category Arrays                                                    //
        // ------------------------------------------------------------------ //

        internal static readonly string[] All =
        {
            "ARMOR",
            "GADGET_PARACHUTE",
            "WEAPON_SMOKEGRENADE",
            "WEAPON_FIREEXTINGUISHER",
            "WEAPON_PETROLCAN",
            "WEAPON_HAZARDCAN",
            "WEAPON_NIGHTVISION",
        };

        internal static readonly string[] Protection =
        {
            "ARMOR",
        };

        internal static readonly string[] Equipment =
        {
            "GADGET_PARACHUTE",
            "WEAPON_SMOKEGRENADE",
            "WEAPON_FIREEXTINGUISHER",
            "WEAPON_PETROLCAN",
            "WEAPON_HAZARDCAN",
            "WEAPON_NIGHTVISION",
        };

        // ------------------------------------------------------------------ //
        //  Display Names                                                      //
        // ------------------------------------------------------------------ //

        internal static readonly Dictionary<string, string> DisplayNames =
            new Dictionary<string, string>
        {
            { "ARMOR",                     "Body Armor" },
            { "GADGET_PARACHUTE",          "Parachute" },
            { "WEAPON_SMOKEGRENADE",       "Tear Gas" },
            { "WEAPON_FIREEXTINGUISHER",   "Fire Extinguisher" },
            { "WEAPON_PETROLCAN",          "Jerry Can" },
            { "WEAPON_HAZARDCAN",          "Hazardous Jerry Can" },
            { "WEAPON_NIGHTVISION",        "Night Vision" },
        };

        // ------------------------------------------------------------------ //
        //  Prices                                                             //
        // ------------------------------------------------------------------ //

        internal static readonly Dictionary<string, int> Prices =
            new Dictionary<string, int>
        {
            { "ARMOR",                     500 },
            { "GADGET_PARACHUTE",          300 },
            { "WEAPON_SMOKEGRENADE",       150 },
            { "WEAPON_FIREEXTINGUISHER",   100 },
            { "WEAPON_PETROLCAN",          100 },
            { "WEAPON_HAZARDCAN",          250 },
            { "WEAPON_NIGHTVISION",        5000 },
        };

        // ------------------------------------------------------------------ //
        //  Category Names                                                     //
        // ------------------------------------------------------------------ //

        internal static readonly Dictionary<string, string> CategoryNames =
            new Dictionary<string, string>
        {
            { "ARMOR",                     "Protection" },
            { "GADGET_PARACHUTE",          "Equipment" },
            { "WEAPON_SMOKEGRENADE",       "Equipment" },
            { "WEAPON_FIREEXTINGUISHER",   "Equipment" },
            { "WEAPON_PETROLCAN",          "Equipment" },
            { "WEAPON_HAZARDCAN",          "Equipment" },
            { "WEAPON_NIGHTVISION",        "Equipment" },
        };
    }
}
