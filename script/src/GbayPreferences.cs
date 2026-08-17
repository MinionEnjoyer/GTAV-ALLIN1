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
        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();
        private static GbayPreferenceData _committedData = Normalize(Load());
        private static GbayPreferenceData _data = Clone(_committedData);
        private static bool _dirty;

        internal static bool IsVehicleFavorite(string model) => _data.FavoriteVehicles.Contains(model);
        internal static bool IsWeaponFavorite(string weapon) => _data.FavoriteWeapons.Contains(weapon);
        internal static void ToggleVehicle(string model) { Toggle(_data.FavoriteVehicles, model); Stage(); }
        internal static void ToggleWeapon(string weapon) { Toggle(_data.FavoriteWeapons, weapon); Stage(); }
        internal static void RecordVehicle(string model) { Record(_data.RecentVehicles, model); Stage(); }
        internal static void RecordWeapon(string weapon) { Record(_data.RecentWeapons, weapon); Stage(); }

        internal static void CommitForStorySave(string reason)
        {
            if (!_dirty) return;
            if (!Save()) return;
            _committedData = Clone(_data);
            _dirty = false;
            ClientLog.Info("GBAY", "preferences_backed_up",
                new Dictionary<string, object> { { "reason", reason } });
        }

        internal static void DiscardStaged()
        {
            if (!_dirty) return;
            _data = Clone(_committedData);
            _dirty = false;
            ClientLog.Info("GBAY", "unsaved_preferences_discarded");
        }

        private static void Toggle(List<string> values, string value)
        { if (values.Contains(value)) values.Remove(value); else values.Add(value); }

        private static void Record(List<string> values, string value)
        {
            values.Remove(value); values.Insert(0, value);
            if (values.Count > 25) values.RemoveRange(25, values.Count - 25);
        }

        private static void Stage()
        {
            _dirty = true;
        }

        private static GbayPreferenceData Normalize(GbayPreferenceData data)
        {
            if (data == null) data = new GbayPreferenceData();
            if (data.FavoriteVehicles == null) data.FavoriteVehicles = new List<string>();
            if (data.FavoriteWeapons == null) data.FavoriteWeapons = new List<string>();
            if (data.RecentVehicles == null) data.RecentVehicles = new List<string>();
            if (data.RecentWeapons == null) data.RecentWeapons = new List<string>();
            return data;
        }

        private static GbayPreferenceData Clone(GbayPreferenceData source)
        {
            source = Normalize(source);
            return new GbayPreferenceData
            {
                FavoriteVehicles = new List<string>(source.FavoriteVehicles),
                FavoriteWeapons = new List<string>(source.FavoriteWeapons),
                RecentVehicles = new List<string>(source.RecentVehicles),
                RecentWeapons = new List<string>(source.RecentWeapons),
            };
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

        private static bool Save()
        {
            try
            {
                string temporary = PathName + ".tmp";
                File.WriteAllText(temporary, Serializer.Serialize(_data));
                if (File.Exists(PathName)) File.Copy(PathName, PathName + ".bak", true);
                if (File.Exists(PathName)) File.Delete(PathName);
                File.Move(temporary, PathName);
                return true;
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "preferences_save_failed", ex);
                return false;
            }
        }
    }
}
