// Launcher-managed, per-character weapon and gear inventory shared with GBAY.
using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    public class CharacterInventory : Script
    {
        private static readonly string PathName = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_characters.json");
        private static readonly object Sync = new object();
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        private static Dictionary<string, Inventory> _state = EmptyState();
        private static readonly int MichaelHash = Game.GenerateHash("player_zero");
        private static readonly int FranklinHash = Game.GenerateHash("player_one");
        private static readonly int TrevorHash = Game.GenerateHash("player_two");
        private static readonly Dictionary<string, int> WeaponHashes = BuildWeaponHashes();
        private DateTime _lastWrite;
        private string _lastCharacter = "";

        public sealed class Inventory
        {
            public int schema_version { get; set; } = 3;
            public List<string> weapons { get; set; } = new List<string>();
            public List<string> gear { get; set; } = new List<string>();
            public bool managed { get; set; }
            public Outfit outfit { get; set; } = new Outfit();
            public Progress progress { get; set; } = new Progress();
        }

        public sealed class Variation
        {
            public int drawable { get; set; }
            public int texture { get; set; }
        }

        public sealed class Outfit
        {
            public bool managed { get; set; }
            public bool unlock_all { get; set; }
            public List<Variation> components { get; set; } = new List<Variation>();
            public List<Variation> props { get; set; } = new List<Variation>();
            public Dictionary<string, object> presets { get; set; } = new Dictionary<string, object>();
        }

        public sealed class Progress
        {
            public bool managed { get; set; }
            public int money { get; set; }
            public Dictionary<string, int> skills { get; set; } = new Dictionary<string, int>();
        }

        public CharacterInventory()
        {
            Interval = 1000;
            Tick += OnTick;
            Reload();
        }

        private static Dictionary<string, Inventory> EmptyState() =>
            new Dictionary<string, Inventory>(StringComparer.OrdinalIgnoreCase) {
                { "michael", new Inventory() }, { "franklin", new Inventory() },
                { "trevor", new Inventory() }
            };

        private static string CurrentCharacter()
        {
            int model = Function.Call<int>(Hash.GET_ENTITY_MODEL, Game.Player.Character.Handle);
            if (model == MichaelHash) return "michael";
            if (model == FranklinHash) return "franklin";
            if (model == TrevorHash) return "trevor";
            return "";
        }

        private static Dictionary<string, int> BuildWeaponHashes()
        {
            var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            foreach (string weapon in WeaponList.All) result[weapon] = Game.GenerateHash(weapon);
            return result;
        }

        internal static int GetWeaponHash(string weapon) => WeaponHashes.TryGetValue(
            weapon, out int hash) ? hash : Game.GenerateHash(weapon);

        private static void Reload()
        {
            lock (Sync)
            {
                try
                {
                    if (!File.Exists(PathName)) return;
                    var loaded = Json.Deserialize<Dictionary<string, Inventory>>(File.ReadAllText(PathName));
                    if (loaded != null) _state = loaded;
                    ClientLog.Info("Character", "loadouts_loaded");
                }
                catch (Exception ex) { ClientLog.Error("Character", "loadouts_load_failed", ex); }
            }
        }

        private void OnTick(object sender, EventArgs args)
        {
            DateTime write = File.Exists(PathName) ? File.GetLastWriteTimeUtc(PathName) : DateTime.MinValue;
            string character = CurrentCharacter();
            if (write != _lastWrite) { Reload(); _lastWrite = write; _lastCharacter = ""; }
            if (character.Length == 0 || character == _lastCharacter) return;
            _lastCharacter = character;
            Apply(character);
        }

        private static void Apply(string character)
        {
            if (!_state.TryGetValue(character, out Inventory inventory)) return;
            if (!inventory.managed && !(inventory.outfit?.managed ?? false) &&
                !(inventory.progress?.managed ?? false)) return;
            Ped ped = Game.Player.Character;
            var owned = new HashSet<string>(inventory.weapons ?? new List<string>(), StringComparer.OrdinalIgnoreCase);
            if (inventory.managed)
            {
                foreach (var entry in WeaponHashes)
                {
                    Hash hash = (Hash)entry.Value;
                    if (owned.Contains(entry.Key)) ped.Weapons.Give((WeaponHash)(uint)hash, 9999, false, false);
                    else Function.Call(Hash.REMOVE_WEAPON_FROM_PED, ped.Handle, hash);
                }
                foreach (string gear in inventory.gear ?? new List<string>())
                {
                    if (GearList.IsArmor(gear)) ped.Armor = GearList.ArmorValues[gear];
                    else if (gear == "WEAPON_NIGHTVISION") GbayShop.NightVisionOwned = true;
                    else ped.Weapons.Give((WeaponHash)Game.GenerateHash(gear), 1, false, false);
                }
            }
            if (inventory.outfit?.managed ?? false) ApplyOutfit(ped, inventory.outfit);
            if (inventory.progress?.managed ?? false) ApplyProgress(character, inventory.progress);
            ClientLog.Info("Character", "loadout_applied", new Dictionary<string, object> {
                { "character", character }, { "weapons", owned.Count }, { "gear", inventory.gear?.Count ?? 0 }
            });
        }

        private static void ApplyProgress(string character, Progress progress)
        {
            int prefix = character == "michael" ? 0 : character == "franklin" ? 1 : 2;
            var statSuffixes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase) {
                { "stamina", "STAMINA" }, { "strength", "STRENGTH" },
                { "lung_capacity", "LUNG_CAPACITY" }, { "driving", "WHEELIE_ABILITY" },
                { "flying", "FLYING_ABILITY" }, { "shooting", "SHOOTING_ABILITY" },
                { "stealth", "STEALTH_ABILITY" }
            };
            Game.Player.Money = Math.Max(0, progress.money);
            foreach (var entry in statSuffixes)
            {
                if (progress.skills == null || !progress.skills.TryGetValue(entry.Key, out int value)) continue;
                value = Math.Max(0, Math.Min(100, value));
                int statHash = Game.GenerateHash($"SP{prefix}_{entry.Value}");
                Function.Call(Hash.STAT_SET_INT, statHash, value, true);
            }
            ClientLog.Info("Character", "progress_applied", new Dictionary<string, object> {
                { "character", character }, { "money", progress.money },
                { "skills", progress.skills?.Count ?? 0 }
            });
            GTA.UI.Screen.ShowSubtitle($"~g~ALLIN1~w~ applied {character}'s saved stats and money.", 3000);
        }

        private static void ApplyOutfit(Ped ped, Outfit outfit)
        {
            var components = outfit.components ?? new List<Variation>();
            for (int slot = 0; slot < components.Count && slot < 12; slot++)
            {
                Variation value = components[slot];
                int drawables = Function.Call<int>(Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, ped, slot);
                if (value.drawable < 0 || value.drawable >= drawables) continue;
                int textures = Function.Call<int>(Hash.GET_NUMBER_OF_PED_TEXTURE_VARIATIONS,
                    ped, slot, value.drawable);
                if (value.texture < 0 || value.texture >= Math.Max(1, textures)) continue;
                Function.Call(Hash.SET_PED_COMPONENT_VARIATION, ped, slot,
                    value.drawable, value.texture, 0);
            }
            var props = outfit.props ?? new List<Variation>();
            for (int slot = 0; slot < props.Count && slot < 8; slot++)
            {
                Variation value = props[slot];
                if (value.drawable < 0) { Function.Call(Hash.CLEAR_PED_PROP, ped, slot); continue; }
                int drawables = Function.Call<int>(Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS, ped, slot);
                if (value.drawable >= drawables) continue;
                int textures = Function.Call<int>(Hash.GET_NUMBER_OF_PED_PROP_TEXTURE_VARIATIONS,
                    ped, slot, value.drawable);
                if (value.texture < 0 || value.texture >= Math.Max(1, textures)) continue;
                Function.Call(Hash.SET_PED_PROP_INDEX, ped, slot, value.drawable, value.texture, true);
            }
            ClientLog.Info("Character", "outfit_applied", new Dictionary<string, object> {
                { "unlock_all", outfit.unlock_all }, { "components", components.Count }, { "props", props.Count }
            });
        }

        internal static void RecordOwned(string item, bool gear)
        {
            if (!File.Exists(PathName)) return;
            string character = CurrentCharacter();
            if (character.Length == 0) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    _state[character] = inventory = new Inventory();
                List<string> list = gear ? inventory.gear : inventory.weapons;
                if (!list.Contains(item)) list.Add(item);
                try
                {
                    string temporary = PathName + ".tmp";
                    File.WriteAllText(temporary, Json.Serialize(_state));
                    if (File.Exists(PathName)) File.Copy(PathName, PathName + ".bak", true);
                    if (File.Exists(PathName)) File.Replace(temporary, PathName, null);
                    else File.Move(temporary, PathName);
                    ClientLog.Info("Character", "gbay_inventory_synced", new Dictionary<string, object> {
                        { "character", character }, { "item", item }, { "gear", gear }
                    });
                }
                catch (Exception ex) { ClientLog.Error("Character", "inventory_save_failed", ex); }
            }
        }
    }
}
