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
        private int _lastPedHandle;
        private bool _restorePending;
        private bool _saveWasInProgress;
        private DateTime _lastStorySaveWriteUtc;
        private DateTime _nextStorySavePollUtc;

        public sealed class Inventory
        {
            public int schema_version { get; set; } = 6;
            public List<string> weapons { get; set; } = new List<string>();
            public Dictionary<string, int> weapon_ammo { get; set; } =
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            public List<string> gear { get; set; } = new List<string>();
            public List<string> equipped_gear { get; set; } = new List<string>();
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
            Interval = 250;
            Tick += OnTick;
            Aborted += OnAborted;
            Reload();
            _lastStorySaveWriteUtc = LatestStorySaveWriteUtc();
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

        internal static bool IsOwned(string item, bool gear)
        {
            if (string.IsNullOrWhiteSpace(item)) return false;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return false;
                List<string> list = gear ? inventory.gear : inventory.weapons;
                if (list == null) return false;
                foreach (string owned in list)
                    if (string.Equals(owned, item, StringComparison.OrdinalIgnoreCase))
                        return true;
                return false;
            }
        }

        internal static bool IsGearEquipped(string item)
        {
            if (string.IsNullOrWhiteSpace(item)) return false;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return false;
                NormalizeInventory(inventory);
                foreach (string equipped in inventory.equipped_gear)
                    if (string.Equals(equipped, item, StringComparison.OrdinalIgnoreCase))
                        return true;
                return false;
            }
        }

        private static void Reload()
        {
            lock (Sync)
            {
                try
                {
                    if (!File.Exists(PathName)) return;
                    var loaded = Json.Deserialize<Dictionary<string, Inventory>>(File.ReadAllText(PathName));
                    if (loaded != null)
                    {
                        _state = loaded;
                        bool migrated = false;
                        foreach (Inventory inventory in _state.Values)
                            migrated |= NormalizeInventory(inventory);
                        if (migrated) SaveStateLocked();
                    }
                    ClientLog.Info("Character", "loadouts_loaded");
                }
                catch (Exception ex) { ClientLog.Error("Character", "loadouts_load_failed", ex); }
            }
        }

        private void OnTick(object sender, EventArgs args)
        {
            if (Game.IsLoading)
            {
                _restorePending = true;
                _saveWasInProgress = false;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead)
            {
                _restorePending = true;
                return;
            }

            DateTime write = File.Exists(PathName) ? File.GetLastWriteTimeUtc(PathName) : DateTime.MinValue;
            string character = CurrentCharacter();
            if (write != _lastWrite)
            {
                Reload();
                _lastWrite = write;
                _lastCharacter = "";
                _lastPedHandle = 0;
            }
            if (_restorePending)
            {
                _restorePending = false;
                _lastCharacter = "";
                _lastPedHandle = 0;
            }
            if (character.Length == 0)
            {
                _restorePending = true;
                return;
            }

            BackupWhenStorySaveWritten(character, player);
            bool saveInProgress = Function.Call<bool>(Hash.IS_AUTO_SAVE_IN_PROGRESS);
            if (saveInProgress && !_saveWasInProgress)
                CaptureWeaponAmmo(character, player, "story_save_started");
            _saveWasInProgress = saveInProgress;

            if (character == _lastCharacter && player.Handle == _lastPedHandle)
                return;
            _lastCharacter = character;
            _lastPedHandle = player.Handle;
            Apply(character);
        }

        private static void Apply(string character)
        {
            if (!_state.TryGetValue(character, out Inventory inventory)) return;
            NormalizeInventory(inventory);
            bool hasSavedWeapons = inventory.weapons.Count > 0;
            if (!inventory.managed && !(inventory.outfit?.managed ?? false) &&
                !(inventory.progress?.managed ?? false) &&
                inventory.equipped_gear.Count == 0 && !hasSavedWeapons) return;
            Ped ped = Game.Player.Character;
            var owned = new HashSet<string>(inventory.weapons ?? new List<string>(), StringComparer.OrdinalIgnoreCase);
            foreach (var entry in WeaponHashes)
            {
                Hash hash = (Hash)entry.Value;
                if (owned.Contains(entry.Key))
                {
                    int ammo = 9999;
                    if (inventory.weapon_ammo.TryGetValue(entry.Key, out int savedAmmo))
                        ammo = Math.Max(0, savedAmmo);
                    ped.Weapons.Give((WeaponHash)(uint)hash, ammo, false, false);
                    // GIVE_WEAPON_TO_PED may add to an already-present weapon. Set
                    // the total explicitly so a save restore cannot duplicate ammo.
                    Function.Call(Hash.SET_PED_AMMO, ped.Handle, hash, ammo);
                }
                else if (inventory.managed)
                    Function.Call(Hash.REMOVE_WEAPON_FROM_PED, ped.Handle, hash);
            }
            foreach (string gear in inventory.equipped_gear)
            {
                if (gear == GearList.ARMOR_JUGGERNAUT)
                {
                    if (!GbayShop.JuggernautActive) GbayShop.ApplyJuggernaut(ped);
                }
                else if (GearList.IsArmor(gear))
                    ped.Armor = GearList.ArmorValues[gear];
                else if (gear == "WEAPON_NIGHTVISION")
                    GbayShop.NightVisionOwned = true;
                else
                    ped.Weapons.Give((WeaponHash)Game.GenerateHash(gear), 1, false, false);
            }
            if (inventory.outfit?.managed ?? false) ApplyOutfit(ped, inventory.outfit);
            if (inventory.progress?.managed ?? false) ApplyProgress(character, inventory.progress);
            ClientLog.Info("Character", "loadout_applied", new Dictionary<string, object> {
                { "character", character }, { "weapons", owned.Count },
                { "managed", inventory.managed }, { "gear", inventory.gear?.Count ?? 0 }
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
            if (string.IsNullOrWhiteSpace(item)) return;
            string character = CurrentCharacter();
            if (character.Length == 0) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    _state[character] = inventory = new Inventory();
                List<string> list = gear ? inventory.gear : inventory.weapons;
                if (list == null)
                {
                    list = new List<string>();
                    if (gear) inventory.gear = list;
                    else inventory.weapons = list;
                }
                bool alreadyOwned = false;
                foreach (string owned in list)
                    if (string.Equals(owned, item, StringComparison.OrdinalIgnoreCase))
                    {
                        alreadyOwned = true;
                        break;
                    }
                if (!alreadyOwned) list.Add(item);
                if (gear)
                {
                    NormalizeInventory(inventory);
                    SetEquippedInMemory(inventory, item, true);
                }
                else
                {
                    NormalizeInventory(inventory);
                    int ammo = Function.Call<int>(Hash.GET_AMMO_IN_PED_WEAPON,
                        Game.Player.Character.Handle, GetWeaponHash(item));
                    inventory.weapon_ammo[item] = Math.Max(0, ammo);
                }
                try
                {
                    SaveStateLocked();
                    ClientLog.Info("Character", "gbay_inventory_synced", new Dictionary<string, object> {
                        { "character", character }, { "item", item }, { "gear", gear }
                    });
                }
                catch (Exception ex) { ClientLog.Error("Character", "inventory_save_failed", ex); }
            }
        }

        internal static void SetGearEquipped(string item, bool equipped)
        {
            if (string.IsNullOrWhiteSpace(item)) return;
            string character = CurrentCharacter();
            if (character.Length == 0) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return;
                NormalizeInventory(inventory);
                if (equipped && !ContainsIgnoreCase(inventory.gear, item)) return;
                SetEquippedInMemory(inventory, item, equipped);
                try
                {
                    SaveStateLocked();
                    ClientLog.Info("Character", "gear_equipment_synced",
                        new Dictionary<string, object> {
                            { "character", character }, { "item", item },
                            { "equipped", equipped }
                        });
                }
                catch (Exception ex) { ClientLog.Error("Character", "inventory_save_failed", ex); }
            }
        }

        internal static void RemoveOwnedGear(string item)
        {
            if (string.IsNullOrWhiteSpace(item)) return;
            string character = CurrentCharacter();
            if (character.Length == 0) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return;
                NormalizeInventory(inventory);
                if (!RemoveOwnedGearInMemory(inventory, item)) return;
                try
                {
                    SaveStateLocked();
                    ClientLog.Info("Character", "gear_ownership_removed",
                        new Dictionary<string, object> {
                            { "character", character }, { "item", item }
                        });
                }
                catch (Exception ex) { ClientLog.Error("Character", "inventory_save_failed", ex); }
            }
        }

        internal static void RecordWeaponAmmo(string item, int ammo)
        {
            if (string.IsNullOrWhiteSpace(item)) return;
            string character = CurrentCharacter();
            if (character.Length == 0) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return;
                NormalizeInventory(inventory);
                if (!ContainsIgnoreCase(inventory.weapons, item)) return;
                inventory.weapon_ammo[item] = Math.Max(0, ammo);
                try { SaveStateLocked(); }
                catch (Exception ex) { ClientLog.Error("Character", "inventory_save_failed", ex); }
            }
        }

        private void BackupWhenStorySaveWritten(string character, Ped player)
        {
            DateTime now = DateTime.UtcNow;
            if (now < _nextStorySavePollUtc) return;
            _nextStorySavePollUtc = now.AddMilliseconds(500);

            DateTime latest = LatestStorySaveWriteUtc();
            if (latest <= _lastStorySaveWriteUtc) return;
            _lastStorySaveWriteUtc = latest;
            CaptureWeaponAmmo(character, player, "story_save_written");
        }

        private static DateTime LatestStorySaveWriteUtc()
        {
            DateTime latest = DateTime.MinValue;
            string documents = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            string rockstar = Path.Combine(documents, "Rockstar Games");
            foreach (string gameFolder in new[] { "GTA V", "GTAV Enhanced" })
            {
                string profiles = Path.Combine(rockstar, gameFolder, "Profiles");
                if (!Directory.Exists(profiles)) continue;
                try
                {
                    foreach (string path in Directory.EnumerateFiles(
                        profiles, "SGTA5*", SearchOption.AllDirectories))
                    {
                        // Real save slots have no extension. Ignore Rockstar's .bak
                        // recovery copies so one save operation produces one backup.
                        if (Path.GetExtension(path).Length != 0) continue;
                        DateTime write = File.GetLastWriteTimeUtc(path);
                        if (write > latest) latest = write;
                    }
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
            return latest;
        }

        private static void CaptureWeaponAmmo(string character, Ped ped, string reason)
        {
            if (ped == null || !ped.Exists()) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return;
                NormalizeInventory(inventory);
                int captured = 0;
                foreach (string weapon in inventory.weapons)
                {
                    int hash = GetWeaponHash(weapon);
                    if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                            ped.Handle, hash, false))
                        continue;
                    int ammo = Function.Call<int>(Hash.GET_AMMO_IN_PED_WEAPON,
                        ped.Handle, hash);
                    inventory.weapon_ammo[weapon] = Math.Max(0, ammo);
                    captured++;
                }
                try
                {
                    SaveStateLocked();
                    ClientLog.Info("Character", "weapon_state_backed_up",
                        new Dictionary<string, object> {
                            { "character", character }, { "weapons", captured },
                            { "reason", reason }
                        });
                }
                catch (Exception ex) { ClientLog.Error("Character", "inventory_save_failed", ex); }
            }
        }

        private void OnAborted(object sender, EventArgs args)
        {
            try
            {
                DateTime latest = LatestStorySaveWriteUtc();
                if (latest <= _lastStorySaveWriteUtc) return;
                Ped player = Game.Player.Character;
                string character = CurrentCharacter();
                if (character.Length > 0 && player != null && player.Exists())
                    CaptureWeaponAmmo(character, player, "story_save_written_on_shutdown");
            }
            catch (Exception ex) { ClientLog.Error("Character", "shutdown_backup_failed", ex); }
        }

        internal static void SetEquippedInMemory(
            Inventory inventory, string item, bool equipped)
        {
            inventory.equipped_gear.RemoveAll(value =>
                string.Equals(value, item, StringComparison.OrdinalIgnoreCase));
            if (!equipped) return;

            // Protection is a single equipment slot: equipping one armor tier
            // consumes the previous normal or Juggernaut armor.
            if (GearList.IsArmor(item))
            {
                var displaced = inventory.equipped_gear.FindAll(GearList.IsArmor);
                inventory.equipped_gear.RemoveAll(GearList.IsArmor);
                foreach (string oldArmor in displaced)
                    inventory.gear.RemoveAll(value => string.Equals(
                        value, oldArmor, StringComparison.OrdinalIgnoreCase));
            }
            inventory.equipped_gear.Add(item);
        }

        internal static bool RemoveOwnedGearInMemory(
            Inventory inventory, string item)
        {
            if (inventory == null || string.IsNullOrWhiteSpace(item))
                return false;
            bool changed = inventory.gear.RemoveAll(value => string.Equals(
                value, item, StringComparison.OrdinalIgnoreCase)) > 0;
            changed |= inventory.equipped_gear.RemoveAll(value => string.Equals(
                value, item, StringComparison.OrdinalIgnoreCase)) > 0;
            return changed;
        }

        private static bool NormalizeInventory(Inventory inventory)
        {
            bool changed = false;
            if (inventory.weapons == null) { inventory.weapons = new List<string>(); changed = true; }
            if (inventory.gear == null) { inventory.gear = new List<string>(); changed = true; }

            if (inventory.schema_version < 4 || inventory.equipped_gear == null)
            {
                inventory.equipped_gear = new List<string>(inventory.gear);
                changed = true;
            }

            if (inventory.schema_version < 5 || inventory.weapon_ammo == null)
            {
                inventory.weapon_ammo = new Dictionary<string, int>(
                    StringComparer.OrdinalIgnoreCase);
                foreach (string weapon in inventory.weapons)
                    inventory.weapon_ammo[weapon] = 9999;
                changed = true;
            }
            else
            {
                var normalizedAmmo = new Dictionary<string, int>(
                    StringComparer.OrdinalIgnoreCase);
                foreach (string weapon in inventory.weapons)
                {
                    int ammo = 9999;
                    if (inventory.weapon_ammo.TryGetValue(weapon, out int savedAmmo))
                    {
                        ammo = Math.Max(0, savedAmmo);
                        if (ammo != savedAmmo) changed = true;
                    }
                    else
                    {
                        changed = true;
                    }
                    normalizedAmmo[weapon] = ammo;
                }
                if (normalizedAmmo.Count != inventory.weapon_ammo.Count)
                    changed = true;
                inventory.weapon_ammo = normalizedAmmo;
            }
            var normalized = new List<string>();
            string activeArmor = null;
            foreach (string item in inventory.equipped_gear)
            {
                if (!ContainsIgnoreCase(inventory.gear, item)) { changed = true; continue; }
                if (GearList.IsArmor(item))
                {
                    activeArmor = item;
                    continue;
                }
                if (!ContainsIgnoreCase(normalized, item)) normalized.Add(item);
                else changed = true;
            }
            if (activeArmor != null) normalized.Add(activeArmor);
            if (!ListsEqualIgnoreCase(inventory.equipped_gear, normalized)) changed = true;
            inventory.equipped_gear = normalized;

            // Schema 6 makes gear consumable: ownership exists only while an
            // item is equipped. Migrating an older save discards gear that had
            // already been explicitly unequipped under the former locker rule.
            int ownedBefore = inventory.gear.Count;
            inventory.gear.RemoveAll(item =>
                !ContainsIgnoreCase(inventory.equipped_gear, item));
            if (inventory.gear.Count != ownedBefore) changed = true;
            if (inventory.schema_version != 6)
            {
                inventory.schema_version = 6;
                changed = true;
            }
            return changed;
        }

        private static bool ContainsIgnoreCase(List<string> values, string item)
        {
            if (values == null) return false;
            foreach (string value in values)
                if (string.Equals(value, item, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        private static bool ListsEqualIgnoreCase(List<string> left, List<string> right)
        {
            if (left == null || right == null || left.Count != right.Count) return false;
            for (int i = 0; i < left.Count; i++)
                if (!string.Equals(left[i], right[i], StringComparison.OrdinalIgnoreCase)) return false;
            return true;
        }

        private static void SaveStateLocked()
        {
            string temporary = PathName + ".tmp";
            File.WriteAllText(temporary, Json.Serialize(_state));
            if (File.Exists(PathName)) File.Copy(PathName, PathName + ".bak", true);
            if (File.Exists(PathName)) File.Replace(temporary, PathName, null);
            else File.Move(temporary, PathName);
        }
    }
}
