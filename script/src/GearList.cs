// GearList.cs — Static gear item data for the GBAY Gear shop.
//
// Hand-written (no generator) since the list is small and stable.
// Covers 5 tiers of body armor, parachute, and utility gadgets.

using System.Collections.Generic;

namespace ALLIN1
{
    internal static class GearList
    {
        // Armor tier IDs — not weapon hashes, handled separately via player.Armor
        internal const string ARMOR_SUPER_LIGHT = "ARMOR_SUPER_LIGHT";
        internal const string ARMOR_LIGHT       = "ARMOR_LIGHT";
        internal const string ARMOR_STANDARD    = "ARMOR_STANDARD";
        internal const string ARMOR_HEAVY       = "ARMOR_HEAVY";
        internal const string ARMOR_SUPER_HEAVY = "ARMOR_SUPER_HEAVY";
        internal const string ARMOR_JUGGERNAUT  = "ARMOR_JUGGERNAUT";

        // ------------------------------------------------------------------ //
        //  Armor Helpers                                                      //
        // ------------------------------------------------------------------ //

        /// <summary>Armor value (0-100) each tier sets on the player.</summary>
        internal static readonly Dictionary<string, int> ArmorValues =
            new Dictionary<string, int>
        {
            { ARMOR_SUPER_LIGHT, 20 },
            { ARMOR_LIGHT,       40 },
            { ARMOR_STANDARD,    60 },
            { ARMOR_HEAVY,       80 },
            { ARMOR_SUPER_HEAVY, 100 },
            { ARMOR_JUGGERNAUT,  100 },
        };

        /// <summary>True if this gear ID is any armor tier.</summary>
        internal static bool IsArmor(string gearId) => ArmorValues.ContainsKey(gearId);

        // ------------------------------------------------------------------ //
        //  Category Arrays                                                    //
        // ------------------------------------------------------------------ //

        internal static readonly string[] All =
        {
            ARMOR_SUPER_LIGHT,
            ARMOR_LIGHT,
            ARMOR_STANDARD,
            ARMOR_HEAVY,
            ARMOR_SUPER_HEAVY,
            ARMOR_JUGGERNAUT,
            "GADGET_PARACHUTE",
            "WEAPON_SMOKEGRENADE",
            "WEAPON_FIREEXTINGUISHER",
            "WEAPON_PETROLCAN",
            "WEAPON_HAZARDCAN",
            "WEAPON_NIGHTVISION",
        };

        internal static readonly string[] Protection =
        {
            ARMOR_SUPER_LIGHT,
            ARMOR_LIGHT,
            ARMOR_STANDARD,
            ARMOR_HEAVY,
            ARMOR_SUPER_HEAVY,
            ARMOR_JUGGERNAUT,
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
            { ARMOR_SUPER_LIGHT,           "Super Light Armor" },
            { ARMOR_LIGHT,                 "Light Armor" },
            { ARMOR_STANDARD,              "Standard Armor" },
            { ARMOR_HEAVY,                 "Heavy Armor" },
            { ARMOR_SUPER_HEAVY,           "Super Heavy Armor" },
            { ARMOR_JUGGERNAUT,            "Juggernaut Armor" },
            { "GADGET_PARACHUTE",          "Parachute" },
            { "WEAPON_SMOKEGRENADE",       "Tear Gas" },
            { "WEAPON_FIREEXTINGUISHER",   "Fire Extinguisher" },
            { "WEAPON_PETROLCAN",          "Jerry Can" },
            { "WEAPON_HAZARDCAN",          "Hazardous Jerry Can" },
            { "WEAPON_NIGHTVISION",        "Night Vision" },
        };

        // ------------------------------------------------------------------ //
        //  Prices (match GTA V single-player Ammu-Nation)                     //
        // ------------------------------------------------------------------ //

        internal static readonly Dictionary<string, int> Prices =
            new Dictionary<string, int>
        {
            { ARMOR_SUPER_LIGHT,           500 },
            { ARMOR_LIGHT,                 1000 },
            { ARMOR_STANDARD,              1500 },
            { ARMOR_HEAVY,                 2000 },
            { ARMOR_SUPER_HEAVY,           2500 },
            { ARMOR_JUGGERNAUT,            50000 },
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
            { ARMOR_SUPER_LIGHT,           "Protection" },
            { ARMOR_LIGHT,                 "Protection" },
            { ARMOR_STANDARD,              "Protection" },
            { ARMOR_HEAVY,                 "Protection" },
            { ARMOR_SUPER_HEAVY,           "Protection" },
            { ARMOR_JUGGERNAUT,            "Protection" },
            { "GADGET_PARACHUTE",          "Equipment" },
            { "WEAPON_SMOKEGRENADE",       "Equipment" },
            { "WEAPON_FIREEXTINGUISHER",   "Equipment" },
            { "WEAPON_PETROLCAN",          "Equipment" },
            { "WEAPON_HAZARDCAN",          "Equipment" },
            { "WEAPON_NIGHTVISION",        "Equipment" },
        };
    }
}
