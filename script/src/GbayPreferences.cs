using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;

namespace ALLIN1
{
    internal sealed class GbayPreferenceData
    {
        public List<string> FavoriteVehicles { get; set; } = new List<string>();
        public List<string> FavoriteWeapons { get; set; } = new List<string>();
        public List<string> RecentVehicles { get; set; } = new List<string>();
        public List<string> RecentWeapons { get; set; } = new List<string>();
    }

    internal static class GbayPreferences
    {
        private static readonly string PathName = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_gbay_preferences.json");
        private static GbayPreferenceData _data = Load();
        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();

        internal static bool IsVehicleFavorite(string model) => _data.FavoriteVehicles.Contains(model);
        internal static bool IsWeaponFavorite(string weapon) => _data.FavoriteWeapons.Contains(weapon);
        internal static void ToggleVehicle(string model) { Toggle(_data.FavoriteVehicles, model); Save(); }
        internal static void ToggleWeapon(string weapon) { Toggle(_data.FavoriteWeapons, weapon); Save(); }
        internal static void RecordVehicle(string model) { Record(_data.RecentVehicles, model); Save(); }
        internal static void RecordWeapon(string weapon) { Record(_data.RecentWeapons, weapon); Save(); }

        private static void Toggle(List<string> values, string value)
        { if (values.Contains(value)) values.Remove(value); else values.Add(value); }

        private static void Record(List<string> values, string value)
        {
            values.Remove(value); values.Insert(0, value);
            if (values.Count > 25) values.RemoveRange(25, values.Count - 25);
        }

        private static GbayPreferenceData Load()
        {
            try
            {
                if (!File.Exists(PathName)) return new GbayPreferenceData();
                return new JavaScriptSerializer().Deserialize<GbayPreferenceData>(
                    File.ReadAllText(PathName)) ?? new GbayPreferenceData();
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "preferences_load_failed", ex);
                return new GbayPreferenceData();
            }
        }

        private static void Save()
        {
            try
            {
                string temporary = PathName + ".tmp";
                File.WriteAllText(temporary, Serializer.Serialize(_data));
                if (File.Exists(PathName)) File.Copy(PathName, PathName + ".bak", true);
                if (File.Exists(PathName)) File.Delete(PathName);
                File.Move(temporary, PathName);
            }
            catch (Exception ex) { ClientLog.Error("GBAY", "preferences_save_failed", ex); }
        }
    }
}
