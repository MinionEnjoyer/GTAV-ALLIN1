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
        private static DateTime _lastWrite;
        private static bool _stateDirty;
        private static int _lastSmokeWeaponAvailability = -1;
        private static int _lastSmokeWeaponRegistration = -1;
        private static readonly Dictionary<int, string> SmokeSyncStates =
            new Dictionary<int, string>();
        private string _lastCharacter = "";
        private int _lastPedHandle;
        private bool _restorePending;
        private bool _saveWasInProgress;
        private bool _discardStagedAfterLoad;
        private DateTime _lastStorySaveWriteUtc;
        private DateTime _nextStorySavePollUtc;

        public sealed class Inventory
        {
            public int schema_version { get; set; } = 10;
            public List<string> weapons { get; set; } = new List<string>();
            public Dictionary<string, int> weapon_ammo { get; set; } =
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            public Dictionary<string, WeaponCustomization> weapon_customizations { get; set; } =
                new Dictionary<string, WeaponCustomization>(StringComparer.OrdinalIgnoreCase);
            public List<string> gear { get; set; } = new List<string>();
            public List<string> equipped_gear { get; set; } = new List<string>();
            public List<string> properties { get; set; } = new List<string>();
            public Dictionary<string, int> smoke_grenades { get; set; } =
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            public string active_smoke_color { get; set; } = "white";
            public bool managed { get; set; }
            public Outfit outfit { get; set; } = new Outfit();
            public Progress progress { get; set; } = new Progress();
        }

        public sealed class WeaponCustomization
        {
            public List<int> owned_components { get; set; } = new List<int>();
            public Dictionary<string, int> active_components { get; set; } =
                new Dictionary<string, int>();
            public List<int> owned_tints { get; set; } = new List<int> { 0 };
            public int active_tint { get; set; }
            public Dictionary<string, List<int>> owned_component_tints { get; set; } =
                new Dictionary<string, List<int>>();
            public Dictionary<string, int> active_component_tints { get; set; } =
                new Dictionary<string, int>();
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

        internal static bool IsPropertyOwned(string propertyId)
        {
            if (string.IsNullOrWhiteSpace(propertyId)) return false;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    return false;
                NormalizeInventory(inventory);
                return ContainsIgnoreCase(inventory.properties, propertyId);
            }
        }

        private static void Reload()
        {
            lock (Sync)
            {
                try
                {
                    _state = EmptyState();
                    _stateDirty = false;
                    if (!File.Exists(PathName))
                    {
                        _lastWrite = DateTime.MinValue;
                        return;
                    }
                    var loaded = Json.Deserialize<Dictionary<string, Inventory>>(
                        File.ReadAllText(PathName));
                    if (loaded != null)
                    {
                        _state = loaded;
                        EnsureCharacterKeys(_state);
                        bool migrated = false;
                        foreach (Inventory inventory in _state.Values)
                            migrated |= NormalizeInventory(inventory);
                        if (migrated) SaveStateLocked();
                    }
                    _lastWrite = File.GetLastWriteTimeUtc(PathName);
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
                _discardStagedAfterLoad = true;
                _saveWasInProgress = false;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead)
            {
                _restorePending = true;
                return;
            }

            if (_discardStagedAfterLoad)
            {
                _discardStagedAfterLoad = false;
                GbayShop.DiscardStagedRuntimeGear(Game.Player.Character);
                Reload();
                GbayPreferences.DiscardStaged();
                _lastCharacter = "";
                _lastPedHandle = 0;
                ClientLog.Info("Character", "unsaved_gbay_state_discarded");
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
            bool hasSavedCustomizations =
                inventory.weapon_customizations.Count > 0;
            bool hasSavedSmoke = SmokeTotalInMemory(inventory) > 0;
            if (!inventory.managed && !(inventory.outfit?.managed ?? false) &&
                !(inventory.progress?.managed ?? false) &&
                inventory.equipped_gear.Count == 0 && !hasSavedWeapons &&
                !hasSavedCustomizations && !hasSavedSmoke) return;
            Ped ped = Game.Player.Character;
            CleanupInvalidSavedWeapons(character, ped, inventory);
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
                    ApplyWeaponCustomization(ped, entry.Key, hash, inventory);
                }
                else if (inventory.managed)
                    Function.Call(Hash.REMOVE_WEAPON_FROM_PED, ped.Handle, hash);
            }
            ApplySmokeInventory(ped, inventory);
            // Story/base-game weapons may be customized through GBAY without
            // having been purchased through GBAY. Reapply those saved upgrades
            // when the character loads without granting the weapon itself.
            foreach (KeyValuePair<string, WeaponCustomization> entry in
                inventory.weapon_customizations)
            {
                if (owned.Contains(entry.Key)) continue;
                int weaponHash = GetWeaponHash(entry.Key);
                if (Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                        ped.Handle, weaponHash, false))
                    ApplyWeaponCustomization(ped, entry.Key,
                        (Hash)weaponHash, inventory);
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
                NormalizeInventory(inventory);
                if (gear)
                {
                    // Normalize before adding ownership. Schema 7 intentionally
                    // discards unequipped gear, so adding first would make the
                    // normalizer erase a new purchase before it could be marked
                    // equipped. That made every subsequent click look like a
                    // first purchase and allowed repeated deductions.
                    RecordOwnedGearInMemory(inventory, item);
                }
                else
                {
                    if (!ContainsIgnoreCase(inventory.weapons, item))
                        inventory.weapons.Add(item);
                    int ammo = Function.Call<int>(Hash.GET_AMMO_IN_PED_WEAPON,
                        Game.Player.Character.Handle, GetWeaponHash(item));
                    inventory.weapon_ammo[item] = Math.Max(0, ammo);
                }
                StageStateLocked(character, gear
                    ? "gear_purchase" : "weapon_purchase", item);
            }
        }

        internal static bool RecordOwnedGearInMemory(
            Inventory inventory, string item)
        {
            if (inventory == null || string.IsNullOrWhiteSpace(item))
                return false;
            NormalizeInventory(inventory);
            bool added = !ContainsIgnoreCase(inventory.gear, item);
            if (added) inventory.gear.Add(item);
            SetEquippedInMemory(inventory, item, true);
            return added;
        }

        internal static bool RecordPropertyOwned(string propertyId)
        {
            if (string.IsNullOrWhiteSpace(propertyId)) return false;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    _state[character] = inventory = new Inventory();
                NormalizeInventory(inventory);
                if (ContainsIgnoreCase(inventory.properties, propertyId))
                    return true;

                inventory.properties.Add(propertyId);
                StageStateLocked(character, "property_purchase", propertyId);
                return true;
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
                StageStateLocked(character,
                    equipped ? "gear_equipped" : "gear_unequipped", item);
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
                StageStateLocked(character, "gear_removed", item);
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
                StageStateLocked(character, "weapon_ammo_purchase", item);
            }
        }

        internal static int GetSmokeQuantity(string color)
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return 0;
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return 0;
                NormalizeInventory(inventory);
                string normalized = SmokeGrenadeCatalog.NormalizeColor(color);
                return inventory.smoke_grenades.TryGetValue(
                    normalized, out int quantity) ? quantity : 0;
            }
        }

        internal static int GetSmokeTotal()
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return 0;
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return 0;
                NormalizeInventory(inventory);
                return SmokeTotalInMemory(inventory);
            }
        }

        internal static string GetActiveSmokeColor()
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return "white";
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return "white";
                NormalizeInventory(inventory);
                return ResolveActiveSmokeColorInMemory(inventory);
            }
        }

        internal static int RecordSmokePurchase(
            string color, int quantity)
        {
            string character = CurrentCharacter();
            if (character.Length == 0 || quantity <= 0) return 0;
            int added;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    _state[character] = inventory = new Inventory();
                NormalizeInventory(inventory);
                added = AddSmokeInMemory(inventory, color, quantity);
                if (added <= 0) return 0;
                inventory.active_smoke_color =
                    SmokeGrenadeCatalog.NormalizeColor(color);
                StageStateLocked(character, "smoke_purchase",
                    inventory.active_smoke_color);
                ApplySmokeInventory(Game.Player.Character, inventory);
                if (SmokeGrenadeCatalog.TryGetByColor(
                        inventory.active_smoke_color,
                        out SmokeGrenadeProduct product))
                {
                    Ped ped = Game.Player.Character;
                    int weaponHash = Game.GenerateHash(product.WeaponName);
                    bool owned = ped != null && ped.Exists() &&
                        Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                            ped.Handle, weaponHash, false);
                    int actualAmmo = owned ? Function.Call<int>(
                        Hash.GET_AMMO_IN_PED_WEAPON,
                        ped.Handle, weaponHash) : 0;
                    if (!owned || actualAmmo <= 0)
                    {
                        RemoveSmokeInMemory(inventory,
                            product.ColorName, added);
                        ApplySmokeInventory(ped, inventory);
                        ClientLog.Warn("Character",
                            "colored_smoke_purchase_grant_failed",
                            new Dictionary<string, object>
                            {
                                { "color", product.ColorName },
                                { "weapon", product.WeaponName },
                                { "weapon_hash", weaponHash },
                                { "owned_after_grant", owned },
                                { "ammo_after_grant", actualAmmo },
                                { "inventory_rolled_back", true },
                            });
                        return 0;
                    }
                }
            }
            return added;
        }

        internal static bool TryEquipSmokeColor(
            string color, out int selectedWeaponHash)
        {
            selectedWeaponHash = 0;
            if (!SmokeGrenadeCatalog.TryGetByColor(color,
                    out SmokeGrenadeProduct product)) return false;
            string character = CurrentCharacter();
            Ped ped = Game.Player.Character;
            if (character.Length == 0 || ped == null || !ped.Exists())
                return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return false;
                NormalizeInventory(inventory);
                ApplySmokeInventory(ped, inventory);
                int weaponHash = Game.GenerateHash(product.WeaponName);
                bool owned = Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    ped.Handle, weaponHash, false);
                int ammo = owned ? Function.Call<int>(
                    Hash.GET_AMMO_IN_PED_WEAPON,
                    ped.Handle, weaponHash) : 0;
                if (owned && ammo > 0)
                    Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                        ped.Handle, weaponHash, true);
                selectedWeaponHash = Function.Call<int>(
                    Hash.GET_SELECTED_PED_WEAPON, ped.Handle);
                bool equipped = owned && ammo > 0 &&
                    selectedWeaponHash == weaponHash;
                ClientLog.Info("Character",
                    "colored_smoke_equip_attempt",
                    new Dictionary<string, object>
                    {
                        { "color", product.ColorName },
                        { "weapon", product.WeaponName },
                        { "weapon_hash", weaponHash },
                        { "owned", owned },
                        { "ammo", ammo },
                        { "selected_weapon_hash", selectedWeaponHash },
                        { "equipped", equipped },
                    });
                return equipped;
            }
        }

        internal static bool TryConsumeActiveSmoke(
            out string color, out int remaining)
        {
            color = "white";
            remaining = 0;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return false;
                NormalizeInventory(inventory);
                if (!TryConsumeSmokeInMemory(inventory, out color))
                    return false;
                remaining = SmokeTotalInMemory(inventory);
                StageStateLocked(character, "smoke_consumed", color);
                return true;
            }
        }

        internal static bool TryConsumeSmokeColor(
            string requestedColor, out int remaining)
        {
            remaining = 0;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return false;
                NormalizeInventory(inventory);
                if (!TryConsumeSmokeColorInMemory(
                        inventory, requestedColor, out string color,
                        out remaining))
                    return false;
                StageStateLocked(character, "smoke_consumed", color);
                return true;
            }
        }

        internal static bool TryConsumeSmokeColorInMemory(
            Inventory inventory, string requestedColor,
            out string color, out int remaining)
        {
            color = SmokeGrenadeCatalog.NormalizeColor(requestedColor);
            remaining = 0;
            if (inventory == null) return false;
            NormalizeSmokeInventoryInMemory(inventory);
            if (!inventory.smoke_grenades.TryGetValue(
                    color, out int quantity) || quantity <= 0)
                return false;
            remaining = quantity - 1;
            if (remaining == 0) inventory.smoke_grenades.Remove(color);
            else inventory.smoke_grenades[color] = remaining;
            return true;
        }

        internal static string CycleActiveSmokeColor()
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return "white";
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return "white";
                NormalizeInventory(inventory);
                string previous = ResolveActiveSmokeColorInMemory(inventory);
                string selected = CycleSmokeColorInMemory(inventory);
                if (!string.Equals(previous, selected,
                        StringComparison.OrdinalIgnoreCase))
                    StageStateLocked(character, "smoke_color_selected",
                        selected);
                return selected;
            }
        }

        internal static void SyncSmokeWeaponNow(Ped ped)
        {
            string character = CurrentCharacter();
            if (character.Length == 0 || ped == null || !ped.Exists()) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character,
                        out Inventory inventory)) return;
                NormalizeInventory(inventory);
                ApplySmokeInventory(ped, inventory);
            }
        }

        internal static int AddSmokeInMemory(
            Inventory inventory, string color, int quantity)
        {
            if (inventory == null || quantity <= 0) return 0;
            NormalizeSmokeInventoryInMemory(inventory);
            string normalized = SmokeGrenadeCatalog.NormalizeColor(color);
            int current = inventory.smoke_grenades.TryGetValue(
                normalized, out int stored) ? Math.Max(0, stored) : 0;
            int added = Math.Min(quantity,
                SmokeGrenadeCatalog.MaximumPerColor - Math.Min(
                    SmokeGrenadeCatalog.MaximumPerColor, current));
            if (added <= 0) return 0;
            inventory.smoke_grenades[normalized] = current + added;
            inventory.active_smoke_color = normalized;
            return added;
        }

        internal static int RemoveSmokeInMemory(
            Inventory inventory, string color, int quantity)
        {
            if (inventory == null || quantity <= 0) return 0;
            NormalizeSmokeInventoryInMemory(inventory);
            string normalized = SmokeGrenadeCatalog.NormalizeColor(color);
            if (!inventory.smoke_grenades.TryGetValue(
                    normalized, out int stored) || stored <= 0) return 0;
            int removed = Math.Min(quantity, stored);
            int remaining = stored - removed;
            if (remaining <= 0) inventory.smoke_grenades.Remove(normalized);
            else inventory.smoke_grenades[normalized] = remaining;
            ResolveActiveSmokeColorInMemory(inventory);
            return removed;
        }

        internal static bool TryConsumeSmokeInMemory(
            Inventory inventory, out string color)
        {
            color = "white";
            if (inventory == null) return false;
            NormalizeSmokeInventoryInMemory(inventory);
            string selected = ResolveActiveSmokeColorInMemory(inventory);
            if (!inventory.smoke_grenades.TryGetValue(
                    selected, out int quantity) || quantity <= 0)
                return false;
            color = selected;
            if (quantity == 1) inventory.smoke_grenades.Remove(selected);
            else inventory.smoke_grenades[selected] = quantity - 1;
            ResolveActiveSmokeColorInMemory(inventory);
            return true;
        }

        internal static string CycleSmokeColorInMemory(Inventory inventory)
        {
            if (inventory == null) return "white";
            NormalizeSmokeInventoryInMemory(inventory);
            string current = ResolveActiveSmokeColorInMemory(inventory);
            int start = -1;
            for (int index = 0;
                index < SmokeGrenadeCatalog.Products.Length; index++)
                if (string.Equals(
                        SmokeGrenadeCatalog.Products[index].ColorName,
                        current, StringComparison.OrdinalIgnoreCase))
                    start = index;
            for (int step = 1;
                step <= SmokeGrenadeCatalog.Products.Length; step++)
            {
                int index = (start + step) %
                    SmokeGrenadeCatalog.Products.Length;
                string candidate =
                    SmokeGrenadeCatalog.Products[index].ColorName;
                if (!inventory.smoke_grenades.TryGetValue(
                        candidate, out int quantity) || quantity <= 0)
                    continue;
                inventory.active_smoke_color = candidate;
                return candidate;
            }
            inventory.active_smoke_color = "white";
            return "white";
        }

        internal static int SmokeTotalInMemory(Inventory inventory)
        {
            if (inventory?.smoke_grenades == null) return 0;
            long total = 0;
            foreach (int quantity in inventory.smoke_grenades.Values)
                total += Math.Max(0, quantity);
            return total >= int.MaxValue ? int.MaxValue : (int)total;
        }

        internal static bool IsWeaponComponentOwned(string weapon, int componentHash)
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return false;
                NormalizeInventory(inventory);
                return inventory.weapon_customizations.TryGetValue(
                    weapon, out WeaponCustomization customization) &&
                    customization.owned_components.Contains(componentHash);
            }
        }

        internal static int GetActiveWeaponComponent(string weapon, int attachmentPoint)
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return 0;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return 0;
                NormalizeInventory(inventory);
                if (!inventory.weapon_customizations.TryGetValue(
                        weapon, out WeaponCustomization customization)) return 0;
                return customization.active_components.TryGetValue(
                    attachmentPoint.ToString(), out int hash) ? hash : 0;
            }
        }

        internal static void RecordWeaponComponent(
            string weapon, int componentHash, int attachmentPoint)
        {
            string character = CurrentCharacter();
            if (character.Length == 0 || string.IsNullOrWhiteSpace(weapon)) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return;
                NormalizeInventory(inventory);
                WeaponCustomization customization = GetOrCreateCustomization(
                    inventory, weapon);
                if (!customization.owned_components.Contains(componentHash))
                    customization.owned_components.Add(componentHash);
                customization.active_components[attachmentPoint.ToString()] = componentHash;
                StageStateLocked(character, "weapon_component", weapon);
            }
        }

        internal static bool IsWeaponTintOwned(string weapon, int tint)
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return tint == 0;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return tint == 0;
                NormalizeInventory(inventory);
                return inventory.weapon_customizations.TryGetValue(
                    weapon, out WeaponCustomization customization)
                    ? customization.owned_tints.Contains(tint) : tint == 0;
            }
        }

        internal static int GetActiveWeaponTint(string weapon)
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return 0;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return 0;
                NormalizeInventory(inventory);
                return inventory.weapon_customizations.TryGetValue(
                    weapon, out WeaponCustomization customization)
                    ? customization.active_tint : 0;
            }
        }

        internal static void RecordWeaponTint(string weapon, int tint)
        {
            string character = CurrentCharacter();
            if (character.Length == 0 || string.IsNullOrWhiteSpace(weapon)) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return;
                NormalizeInventory(inventory);
                WeaponCustomization customization = GetOrCreateCustomization(
                    inventory, weapon);
                if (!customization.owned_tints.Contains(tint))
                    customization.owned_tints.Add(tint);
                customization.active_tint = tint;
                StageStateLocked(character, "weapon_tint", weapon);
            }
        }

        internal static bool IsWeaponComponentTintOwned(
            string weapon, int componentHash, int tint)
        {
            if (tint == 0) return true;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    return false;
                NormalizeInventory(inventory);
                if (!inventory.weapon_customizations.TryGetValue(
                        weapon, out WeaponCustomization customization))
                    return false;
                return customization.owned_component_tints.TryGetValue(
                    componentHash.ToString(), out List<int> tints) &&
                    tints.Contains(tint);
            }
        }

        internal static int GetActiveWeaponComponentTint(
            string weapon, int componentHash)
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return 0;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    return 0;
                NormalizeInventory(inventory);
                if (!inventory.weapon_customizations.TryGetValue(
                        weapon, out WeaponCustomization customization))
                    return 0;
                return customization.active_component_tints.TryGetValue(
                    componentHash.ToString(), out int tint) ? tint : 0;
            }
        }

        internal static void RecordWeaponComponentTint(
            string weapon, int componentHash, int tint)
        {
            string character = CurrentCharacter();
            if (character.Length == 0 || string.IsNullOrWhiteSpace(weapon)) return;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return;
                NormalizeInventory(inventory);
                WeaponCustomization customization = GetOrCreateCustomization(
                    inventory, weapon);
                string key = componentHash.ToString();
                if (!customization.owned_component_tints.TryGetValue(
                        key, out List<int> owned))
                {
                    owned = new List<int> { 0 };
                    customization.owned_component_tints[key] = owned;
                }
                if (!owned.Contains(tint)) owned.Add(tint);
                customization.active_component_tints[key] = tint;
                StageStateLocked(character, "weapon_component_tint", weapon);
            }
        }

        private static WeaponCustomization GetOrCreateCustomization(
            Inventory inventory, string weapon)
        {
            if (!inventory.weapon_customizations.TryGetValue(
                    weapon, out WeaponCustomization customization))
            {
                customization = new WeaponCustomization();
                inventory.weapon_customizations[weapon] = customization;
            }
            return customization;
        }

        private static void ApplyWeaponCustomization(
            Ped ped, string weapon, Hash weaponHash, Inventory inventory)
        {
            if (!inventory.weapon_customizations.TryGetValue(
                    weapon, out WeaponCustomization customization)) return;
            foreach (int component in customization.active_components.Values)
            {
                if (Function.Call<bool>(Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT,
                        weaponHash, component))
                    Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED,
                        ped.Handle, weaponHash, component);
            }
            foreach (KeyValuePair<string, int> entry in
                customization.active_component_tints)
            {
                if (!int.TryParse(entry.Key, out int component) ||
                    !customization.active_components.ContainsValue(component))
                    continue;
                Function.Call(Hash.SET_PED_WEAPON_COMPONENT_TINT_INDEX,
                    ped.Handle, weaponHash, component, entry.Value);
            }
            int tintCount = Function.Call<int>(Hash.GET_WEAPON_TINT_COUNT, weaponHash);
            if (customization.active_tint >= 0 && customization.active_tint < tintCount)
                Function.Call(Hash.SET_PED_WEAPON_TINT_INDEX,
                    ped.Handle, weaponHash, customization.active_tint);
        }

        internal static bool ApplyWeaponCustomizationNow(
            Ped ped, string weapon)
        {
            if (ped == null || !ped.Exists() ||
                string.IsNullOrWhiteSpace(weapon)) return false;
            string character = CurrentCharacter();
            if (character.Length == 0) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    return false;
                NormalizeInventory(inventory);
                if (!inventory.weapon_customizations.TryGetValue(
                        weapon, out WeaponCustomization customization))
                    return true;
                int weaponHash = GetWeaponHash(weapon);
                if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                        ped.Handle, weaponHash, false)) return false;
                // Giving an already-active Mk II magazine component can reset
                // its special-ammo pool (SMG Mk II commonly falls back to one
                // round). Preserve the live amount and clamp it to the capacity
                // of the component set that was just applied.
                int ammoBeforeComponents = Function.Call<int>(
                    Hash.GET_AMMO_IN_PED_WEAPON, ped.Handle, weaponHash);
                ApplyWeaponCustomization(ped, weapon, (Hash)weaponHash, inventory);
                var maxAmmoOut = new OutputArgument();
                bool capacityResolved = Function.Call<bool>(
                    Hash.GET_MAX_AMMO, ped.Handle, weaponHash, maxAmmoOut);
                int maxAmmoAfterComponents = maxAmmoOut.GetResult<int>();
                int preservedAmmo = AmmoRefillPolicy.ClampPreservedAmmo(
                    ammoBeforeComponents, capacityResolved,
                    maxAmmoAfterComponents);
                Function.Call(Hash.SET_PED_AMMO,
                    ped.Handle, weaponHash, preservedAmmo);
                foreach (int component in customization.active_components.Values)
                    if (Function.Call<bool>(
                            Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT,
                            weaponHash, component) &&
                        !Function.Call<bool>(
                            Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                            ped.Handle, weaponHash, component))
                        return false;
                foreach (KeyValuePair<string, int> entry in
                    customization.active_component_tints)
                {
                    if (!int.TryParse(entry.Key, out int component) ||
                        !customization.active_components.ContainsValue(component))
                        continue;
                    if (Function.Call<int>(
                            Hash.GET_PED_WEAPON_COMPONENT_TINT_INDEX,
                            ped.Handle, weaponHash, component) != entry.Value)
                        return false;
                }
                int tintCount = Function.Call<int>(
                    Hash.GET_WEAPON_TINT_COUNT, weaponHash);
                if (customization.active_tint >= 0 &&
                    customization.active_tint < tintCount &&
                    Function.Call<int>(Hash.GET_PED_WEAPON_TINT_INDEX,
                        ped.Handle, weaponHash) != customization.active_tint)
                    return false;
                return true;
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

        internal static DateTime LatestStorySaveWriteUtc()
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
                if (inventory.progress?.managed ?? false)
                    inventory.progress.money = Math.Max(0, Game.Player.Money);
                try
                {
                    bool hadStagedChanges = _stateDirty;
                    SaveStateLocked();
                    ClientLog.Info("Character", "gbay_state_backed_up",
                        new Dictionary<string, object> {
                            { "character", character }, { "weapons", captured },
                            { "reason", reason },
                            { "had_staged_changes", hadStagedChanges }
                        });
                }
                catch (Exception ex) { ClientLog.Error("Character", "inventory_save_failed", ex); }
            }
            GbayPreferences.CommitForStorySave(reason);
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

        internal static List<string> RemoveInvalidWeaponsInMemory(
            Inventory inventory, Func<string, bool> isValid)
        {
            var removed = new List<string>();
            if (inventory == null || inventory.weapons == null ||
                isValid == null) return removed;
            foreach (string weapon in new List<string>(inventory.weapons))
            {
                bool valid = !string.IsNullOrWhiteSpace(weapon) &&
                    isValid(weapon);
                if (valid) continue;
                inventory.weapons.RemoveAll(value => string.Equals(
                    value, weapon, StringComparison.OrdinalIgnoreCase));
                if (!string.IsNullOrEmpty(weapon))
                {
                    inventory.weapon_ammo?.Remove(weapon);
                    inventory.weapon_customizations?.Remove(weapon);
                }
                string removedName = weapon ?? "";
                if (!ContainsIgnoreCase(removed, removedName))
                    removed.Add(removedName);
            }
            return removed;
        }

        private static void CleanupInvalidSavedWeapons(
            string character, Ped ped, Inventory inventory)
        {
            List<string> removed = RemoveInvalidWeaponsInMemory(
                inventory, weapon => Function.Call<bool>(
                    Hash.IS_WEAPON_VALID, GetWeaponHash(weapon)));
            if (removed.Count == 0) return;
            foreach (string weapon in removed)
            {
                if (string.IsNullOrWhiteSpace(weapon)) continue;
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                    ped.Handle, GetWeaponHash(weapon));
            }
            StageStateLocked(character, "invalid_weapons_cleaned",
                string.Join(",", removed));
            ClientLog.Warn("Character", "invalid_managed_weapons_cleaned",
                new Dictionary<string, object>
                {
                    { "character", character },
                    { "count", removed.Count },
                    { "weapons", string.Join(",", removed) },
                    { "removed_from_runtime", true },
                    { "persistence", "next_story_save" },
                });
            GTA.UI.Screen.ShowSubtitle(
                $"~y~ALLIN1 removed {removed.Count} invalid weapon" +
                (removed.Count == 1 ? "." : "s."), 3500);
        }

        private static void ApplySmokeInventory(Ped ped, Inventory inventory)
        {
            if (ped == null || !ped.Exists() || inventory == null) return;
            int availableWeapons =
                SmokeGrenadeCatalog.AvailableCustomWeaponCount();
            int registeredWeapons =
                SmokeGrenadeCatalog.RegisteredCustomWeaponCount(
                    out int totalDlcWeapons,
                    out string catalogFailure);
            bool smokeWeaponsUsable =
                availableWeapons == SmokeGrenadeCatalog.Products.Length;
            if (!smokeWeaponsUsable)
            {
                int removedRuntimeWeapons = 0;
                foreach (SmokeGrenadeProduct product in
                    SmokeGrenadeCatalog.Products)
                {
                    int weaponHash = Game.GenerateHash(product.WeaponName);
                    if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                            ped.Handle, weaponHash, false))
                        continue;
                    Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                        ped.Handle, weaponHash);
                    removedRuntimeWeapons++;
                }
                if (_lastSmokeWeaponAvailability != availableWeapons ||
                    _lastSmokeWeaponRegistration != registeredWeapons)
                {
                    ClientLog.Warn("Character",
                        "colored_smoke_weapon_pack_unavailable",
                        new Dictionary<string, object>
                        {
                            { "valid_weapon_definitions", availableWeapons },
                            { "required_weapon_definitions",
                                SmokeGrenadeCatalog.Products.Length },
                            { "registered_weapon_definitions",
                                registeredWeapons },
                            { "registration_required", false },
                            { "total_dlc_weapons", totalDlcWeapons },
                            { "dlc_catalog_failure", catalogFailure },
                            { "removed_runtime_weapons",
                                removedRuntimeWeapons },
                            { "staged_smoke_stock_preserved", true },
                            { "native_smoke_preserved", true },
                            { "inventory_mutated", false },
                        });
                    _lastSmokeWeaponAvailability = availableWeapons;
                    _lastSmokeWeaponRegistration = registeredWeapons;
                }
                return;
            }
            if (_lastSmokeWeaponAvailability != availableWeapons ||
                _lastSmokeWeaponRegistration != registeredWeapons)
            {
                ClientLog.Info("Character",
                    "colored_smoke_weapon_pack_available",
                    new Dictionary<string, object>
                    {
                        { "valid_weapon_definitions", availableWeapons },
                        { "registered_weapon_definitions",
                            registeredWeapons },
                        { "registration_mode", registeredWeapons ==
                            SmokeGrenadeCatalog.Products.Length
                                ? "dlc_catalog" : "base_weapon_info" },
                        { "registration_required", false },
                        { "total_dlc_weapons", totalDlcWeapons },
                        { "dlc_catalog_failure", catalogFailure },
                        { "inventory_sync_enabled", true },
                    });
                _lastSmokeWeaponAvailability = availableWeapons;
                _lastSmokeWeaponRegistration = registeredWeapons;
            }
            foreach (SmokeGrenadeProduct product in
                SmokeGrenadeCatalog.Products)
            {
                int desiredAmmo = inventory.smoke_grenades.TryGetValue(
                    product.ColorName, out int stored)
                    ? Math.Max(0, stored) : 0;
                int weaponHash = Game.GenerateHash(product.WeaponName);
                bool owned = Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    ped.Handle, weaponHash, false);
                bool grantAttempted = false;
                if (desiredAmmo <= 0)
                {
                    if (owned)
                        Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                            ped.Handle, weaponHash);
                    bool ownedAfterRemoval = Function.Call<bool>(
                        Hash.HAS_PED_GOT_WEAPON,
                        ped.Handle, weaponHash, false);
                    int ammoAfterRemoval = ownedAfterRemoval
                        ? Function.Call<int>(Hash.GET_AMMO_IN_PED_WEAPON,
                            ped.Handle, weaponHash) : 0;
                    LogSmokeSyncState(ped, product, desiredAmmo,
                        owned, ownedAfterRemoval, ammoAfterRemoval, false);
                    continue;
                }
                var output = new OutputArgument();
                if (Function.Call<bool>(Hash.GET_MAX_AMMO,
                        ped.Handle, weaponHash, output))
                {
                    int maximum = output.GetResult<int>();
                    if (maximum > 0)
                        desiredAmmo = Math.Min(desiredAmmo, maximum);
                }
                if (!owned)
                {
                    grantAttempted = true;
                    // Add-on throwables are most reliable when GTA receives a
                    // real loaded round with the initial grant. Reconcile the
                    // full per-color stock immediately afterward without
                    // forcing every restored color into the player's hand.
                    ped.Weapons.Give((WeaponHash)(uint)weaponHash,
                        1, false, true);
                }
                int currentAmmo = Function.Call<int>(
                    Hash.GET_AMMO_IN_PED_WEAPON,
                    ped.Handle, weaponHash);
                if (currentAmmo != desiredAmmo)
                    Function.Call(Hash.SET_PED_AMMO,
                        ped.Handle, weaponHash, desiredAmmo);
                bool ownedAfter = Function.Call<bool>(
                    Hash.HAS_PED_GOT_WEAPON,
                    ped.Handle, weaponHash, false);
                int ammoAfter = Function.Call<int>(
                    Hash.GET_AMMO_IN_PED_WEAPON,
                    ped.Handle, weaponHash);
                LogSmokeSyncState(ped, product, desiredAmmo,
                    owned, ownedAfter, ammoAfter, grantAttempted);
            }

            int legacyHash = Game.GenerateHash(
                SmokeGrenadeCatalog.NativeWeaponName);
            if (Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    ped.Handle, legacyHash, false))
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                    ped.Handle, legacyHash);
        }

        private static void LogSmokeSyncState(
            Ped ped, SmokeGrenadeProduct product, int desiredAmmo,
            bool ownedBefore, bool ownedAfter, int ammoAfter,
            bool grantAttempted)
        {
            int weaponHash = Game.GenerateHash(product.WeaponName);
            int selectedHash = Function.Call<int>(
                Hash.GET_SELECTED_PED_WEAPON, ped.Handle);
            string fingerprint = desiredAmmo + ":" + ownedAfter + ":" +
                ammoAfter + ":" + selectedHash;
            if (SmokeSyncStates.TryGetValue(weaponHash,
                    out string previous) && previous == fingerprint) return;
            SmokeSyncStates[weaponHash] = fingerprint;
            var fields = new Dictionary<string, object>
            {
                { "color", product.ColorName },
                { "weapon", product.WeaponName },
                { "weapon_hash", weaponHash },
                { "desired_ammo", desiredAmmo },
                { "owned_before", ownedBefore },
                { "grant_attempted", grantAttempted },
                { "grant_loaded_round", grantAttempted },
                { "owned_after", ownedAfter },
                { "ammo_after", ammoAfter },
                { "selected_weapon_hash", selectedHash },
                { "sync_succeeded", desiredAmmo <= 0 ||
                    (ownedAfter && ammoAfter == desiredAmmo) },
            };
            if (desiredAmmo > 0 && (!ownedAfter || ammoAfter <= 0))
                ClientLog.Warn("Character",
                    "colored_smoke_weapon_sync_failed", fields);
            else
                ClientLog.Info("Character",
                    "colored_smoke_weapon_sync", fields);
        }

        private static string ResolveActiveSmokeColorInMemory(
            Inventory inventory)
        {
            string selected = SmokeGrenadeCatalog.NormalizeColor(
                inventory.active_smoke_color);
            if (inventory.smoke_grenades.TryGetValue(
                    selected, out int quantity) && quantity > 0)
            {
                inventory.active_smoke_color = selected;
                return selected;
            }
            foreach (SmokeGrenadeProduct product in
                SmokeGrenadeCatalog.Products)
            {
                if (!inventory.smoke_grenades.TryGetValue(
                        product.ColorName, out quantity) || quantity <= 0)
                    continue;
                inventory.active_smoke_color = product.ColorName;
                return product.ColorName;
            }
            inventory.active_smoke_color = "white";
            return "white";
        }

        private static bool NormalizeSmokeInventoryInMemory(
            Inventory inventory)
        {
            bool changed = false;
            if (inventory.smoke_grenades == null)
            {
                inventory.smoke_grenades =
                    new Dictionary<string, int>(
                        StringComparer.OrdinalIgnoreCase);
                changed = true;
            }
            var normalized = new Dictionary<string, int>(
                StringComparer.OrdinalIgnoreCase);
            foreach (KeyValuePair<string, int> entry in
                inventory.smoke_grenades)
            {
                if (!SmokeGrenadeCatalog.IsSupportedColor(entry.Key) ||
                    entry.Value <= 0)
                {
                    changed = true;
                    continue;
                }
                string color = SmokeGrenadeCatalog.NormalizeColor(entry.Key);
                int quantity = Math.Min(
                    SmokeGrenadeCatalog.MaximumPerColor, entry.Value);
                if (quantity != entry.Value ||
                    !string.Equals(color, entry.Key,
                        StringComparison.Ordinal)) changed = true;
                normalized[color] = normalized.TryGetValue(
                    color, out int existing)
                    ? Math.Min(SmokeGrenadeCatalog.MaximumPerColor,
                        existing + quantity) : quantity;
            }
            if (normalized.Count != inventory.smoke_grenades.Count)
                changed = true;
            inventory.smoke_grenades = normalized;
            string before = inventory.active_smoke_color;
            string resolved = ResolveActiveSmokeColorInMemory(inventory);
            if (!string.Equals(before, resolved,
                    StringComparison.Ordinal)) changed = true;
            return changed;
        }

        private static bool NormalizeInventory(Inventory inventory)
        {
            bool changed = false;
            if (inventory.weapons == null) { inventory.weapons = new List<string>(); changed = true; }
            if (inventory.gear == null) { inventory.gear = new List<string>(); changed = true; }
            if (inventory.properties == null)
            {
                inventory.properties = new List<string>();
                changed = true;
            }

            // Schema 10 uses the game's dedicated smoke-grenade weapon as the
            // runtime carrier. Native WEAPON_BZGAS remains ordinary Tear Gas.
            // Preserve older smoke-grenade ammo as white stock.
            if (inventory.schema_version < 10 &&
                ContainsIgnoreCase(inventory.weapons,
                    SmokeGrenadeCatalog.NativeWeaponName))
            {
                int legacyAmmo = 0;
                if (inventory.weapon_ammo != null)
                    inventory.weapon_ammo.TryGetValue(
                        SmokeGrenadeCatalog.NativeWeaponName,
                        out legacyAmmo);
                inventory.weapons.RemoveAll(value => string.Equals(
                    value, SmokeGrenadeCatalog.NativeWeaponName,
                    StringComparison.OrdinalIgnoreCase));
                inventory.weapon_ammo?.Remove(
                    SmokeGrenadeCatalog.NativeWeaponName);
                if (legacyAmmo > 0)
                    AddSmokeInMemory(inventory, "white", legacyAmmo);
                changed = true;
            }
            changed |= NormalizeSmokeInventoryInMemory(inventory);

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
            var normalizedCustomizations = new Dictionary<string, WeaponCustomization>(
                StringComparer.OrdinalIgnoreCase);
            if (inventory.weapon_customizations == null)
            {
                inventory.weapon_customizations = normalizedCustomizations;
                changed = true;
            }
            else
            {
                foreach (var entry in inventory.weapon_customizations)
                {
                    if (!ContainsIgnoreCase(inventory.weapons, entry.Key) || entry.Value == null)
                    {
                        changed = true;
                        continue;
                    }
                    WeaponCustomization value = entry.Value;
                    if (value.owned_components == null)
                    {
                        value.owned_components = new List<int>(); changed = true;
                    }
                    if (value.active_components == null)
                    {
                        value.active_components = new Dictionary<string, int>(); changed = true;
                    }
                    if (value.owned_tints == null)
                    {
                        value.owned_tints = new List<int>(); changed = true;
                    }
                    if (!value.owned_tints.Contains(0))
                    {
                        value.owned_tints.Add(0); changed = true;
                    }
                    if (!value.owned_tints.Contains(value.active_tint))
                    {
                        value.owned_tints.Add(value.active_tint); changed = true;
                    }
                    if (value.owned_component_tints == null)
                    {
                        value.owned_component_tints =
                            new Dictionary<string, List<int>>(); changed = true;
                    }
                    if (value.active_component_tints == null)
                    {
                        value.active_component_tints =
                            new Dictionary<string, int>(); changed = true;
                    }
                    foreach (KeyValuePair<string, int> tintEntry in
                        new Dictionary<string, int>(value.active_component_tints))
                    {
                        if (!int.TryParse(tintEntry.Key, out int component) ||
                            !value.owned_components.Contains(component))
                        {
                            value.active_component_tints.Remove(tintEntry.Key);
                            value.owned_component_tints.Remove(tintEntry.Key);
                            changed = true;
                            continue;
                        }
                        if (!value.owned_component_tints.TryGetValue(
                                tintEntry.Key, out List<int> componentTints) ||
                            componentTints == null)
                        {
                            componentTints = new List<int> { 0 };
                            value.owned_component_tints[tintEntry.Key] =
                                componentTints;
                            changed = true;
                        }
                        if (!componentTints.Contains(0))
                        {
                            componentTints.Add(0); changed = true;
                        }
                        if (!componentTints.Contains(tintEntry.Value))
                        {
                            componentTints.Add(tintEntry.Value); changed = true;
                        }
                    }
                    normalizedCustomizations[entry.Key] = value;
                }
                inventory.weapon_customizations = normalizedCustomizations;
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
            if (inventory.schema_version != 10)
            {
                inventory.schema_version = 10;
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

        private static void EnsureCharacterKeys(
            Dictionary<string, Inventory> state)
        {
            foreach (string character in new[] { "michael", "franklin", "trevor" })
                if (!state.ContainsKey(character))
                    state[character] = new Inventory();
        }

        private static void StageStateLocked(
            string character, string action, string item)
        {
            _stateDirty = true;
            ClientLog.Info("Character", "gbay_state_staged",
                new Dictionary<string, object> {
                    { "character", character }, { "action", action },
                    { "item", item }
                });
        }

        private static void SaveStateLocked()
        {
            string temporary = PathName + ".tmp";
            File.WriteAllText(temporary, Json.Serialize(_state));
            if (File.Exists(PathName)) File.Copy(PathName, PathName + ".bak", true);
            if (File.Exists(PathName)) File.Replace(temporary, PathName, null);
            else File.Move(temporary, PathName);
            _lastWrite = File.GetLastWriteTimeUtc(PathName);
            _stateDirty = false;
        }
    }
}
