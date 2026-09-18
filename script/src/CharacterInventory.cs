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
        private static readonly string DefaultPathName = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_characters.json");
        private static string _pathNameOverride;
        private static string PathName => _pathNameOverride ?? DefaultPathName;
        private static readonly object Sync = new object();
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        private static Dictionary<string, Inventory> _state = EmptyState();
        // Keep off-game persistence tests independent of ScriptHookV. Hashes
        // are first needed only when a live Ped is inspected.
        private static readonly Lazy<int> MichaelHash =
            new Lazy<int>(() => Game.GenerateHash("player_zero"));
        private static readonly Lazy<int> FranklinHash =
            new Lazy<int>(() => Game.GenerateHash("player_one"));
        private static readonly Lazy<int> TrevorHash =
            new Lazy<int>(() => Game.GenerateHash("player_two"));
        private static readonly Lazy<Dictionary<string, int>> WeaponHashes =
            new Lazy<Dictionary<string, int>>(BuildWeaponHashes);
        private static DateTime _lastWrite;
        private static bool _stateDirty;
        private static int _lastSmokeWeaponAvailability = -1;
        private static int _lastSmokeWeaponRegistration = -1;
        private static readonly Dictionary<int, string> SmokeSyncStates =
            new Dictionary<int, string>();
        private const int DeathRespawnLoadWindowMs = 300000;
        private string _lastCharacter = "";
        private int _lastPedHandle;
        private bool _restorePending;
        private bool _saveWasInProgress;
        private bool _discardStagedAfterLoad;
        private bool _deathObserved;
        private string _deathCharacter = "";
        private bool _juggernautActiveOnDeath;
        private readonly List<string> _gearLostOnDeath = new List<string>();
        private DateTime _lastStorySaveWriteUtc;
        private DateTime _nextStorySavePollUtc;
        private List<string> _deferredWeapons = new List<string>();
        private int _weaponRestoreRetries;
        private DateTime _nextWeaponRestoreUtc;

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
            public List<int> unequipped_components { get; set; } = new List<int>();
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
            if (!Allin1ExtensionApi.IsPackageEnabled(
                    Allin1ExtensionApi.OnlineContentPackageId))
            {
                Interval = 1000;
                return;
            }
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
            return CharacterForPed(Game.Player.Character);
        }

        // Small, character-bound snapshot used by a single GBAY gear
        // transaction. It intentionally covers only the two mutable gear
        // lists and uses the existing staged-save path on restore.
        internal sealed class GearInventorySnapshot
        {
            internal string Character { get; set; } = "";
            internal List<string> Gear { get; set; } = new List<string>();
            internal List<string> Equipped { get; set; } = new List<string>();
        }

        private static string CharacterForPed(Ped player)
        {
            if (player == null || !player.Exists()) return "";
            int model = Function.Call<int>(Hash.GET_ENTITY_MODEL, player.Handle);
            if (model == MichaelHash.Value) return "michael";
            if (model == FranklinHash.Value) return "franklin";
            if (model == TrevorHash.Value) return "trevor";
            return "";
        }

        private static Dictionary<string, int> BuildWeaponHashes()
        {
            var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            foreach (string weapon in WeaponList.All) result[weapon] = Game.GenerateHash(weapon);
            return result;
        }

        internal static int GetWeaponHash(string weapon) => WeaponHashes.Value.TryGetValue(
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

        private static void Reload(bool discardStaged = false)
        {
            lock (Sync)
            {
                // Decode into a candidate before replacing the live ledger. A
                // damaged file can otherwise turn an in-session purchase into
                // an empty inventory which a later Story save would persist.
                // The only exception is GTA's explicit Story-load path: it
                // deliberately discards in-session state before loading the
                // persisted ledger (or its recovery copy).
                if (discardStaged)
                {
                    _state = EmptyState();
                    _stateDirty = false;
                    _lastWrite = DateTime.MinValue;
                }
                bool candidateInstalled = false;
                try
                {
                    if (!File.Exists(PathName))
                    {
                        // A watcher reload may observe the primary between
                        // File.Replace/File.Move operations. Keep a purchase
                        // staged in memory unless this is the deliberate
                        // Story-load discard path below.
                        if (_stateDirty && !discardStaged)
                        {
                            ClientLog.Warn("Character",
                                "loadouts_missing_reload_retained_staged_state");
                            return;
                        }
                        // A clean process can still recover from the last
                        // known-good copy when a primary was removed or a
                        // replacement was interrupted. Do not initialize an
                        // empty ledger while that source exists.
                        if (File.Exists(PathName + ".bak"))
                        {
                            TryRecoverFromBackup();
                            return;
                        }
                        _state = EmptyState();
                        _stateDirty = false;
                        _lastWrite = DateTime.MinValue;
                        return;
                    }
                    string inventoryJson;
                    if (!EarlyStartupSnapshot.TryGetText(
                            "characters", out inventoryJson))
                        inventoryJson = File.ReadAllText(PathName);
                    Dictionary<string, Inventory> loaded = DecodeState(
                        inventoryJson, out bool migrated);
                    _state = loaded;
                    _stateDirty = false;
                    candidateInstalled = true;
                    if (migrated) SaveStateLocked();
                    _lastWrite = File.GetLastWriteTimeUtc(PathName);
                    ClientLog.Info("Character", "loadouts_loaded");
                }
                catch (Exception ex)
                {
                    ClientLog.Error("Character", candidateInstalled
                        ? "loadouts_post_load_failed" : "loadouts_load_failed", ex);
                    // Do not replace an already accepted ledger with an older
                    // backup merely because a migration write or timestamp
                    // read failed after it was installed.
                    if (!candidateInstalled)
                    {
                        // A file watcher reload can race a pending GBAY
                        // purchase. The in-memory staged ledger is newer than
                        // every persisted copy until Story Mode saves it, so a
                        // corrupt primary must not replace it from .bak.
                        if (_stateDirty)
                            ClientLog.Warn("Character",
                                "loadouts_invalid_reload_retained_staged_state");
                        else
                            TryRecoverFromBackup();
                    }
                }
            }
        }

        /// <summary>
        /// Deserialize and normalize a complete inventory document without
        /// touching the active ledger. Keeping this transactional is important
        /// because reloads also occur while the player has unsaved purchases.
        /// </summary>
        internal static Dictionary<string, Inventory> DecodeState(
            string inventoryJson, out bool migrated)
        {
            if (string.IsNullOrWhiteSpace(inventoryJson))
                throw new InvalidDataException("Character inventory is empty.");

            Dictionary<string, Inventory> decoded;
            try
            {
                // Keep decode usable in the off-game test harness too: the
                // shared serializer lives on CharacterInventory alongside
                // GTA-native static initialization.
                var serializer = new JavaScriptSerializer
                {
                    MaxJsonLength = 2 * 1024 * 1024,
                    RecursionLimit = 32,
                };
                decoded = serializer.Deserialize<Dictionary<string, Inventory>>(
                    inventoryJson);
            }
            catch (Exception ex) when (ex is ArgumentException ||
                ex is InvalidOperationException)
            {
                throw new InvalidDataException(
                    "Character inventory is not valid JSON.", ex);
            }
            if (decoded == null)
                throw new InvalidDataException(
                    "Character inventory root must be a JSON object.");

            var canonical = EmptyState();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (KeyValuePair<string, Inventory> entry in decoded)
            {
                if (!canonical.ContainsKey(entry.Key)) continue;
                if (!seen.Add(entry.Key))
                    throw new InvalidDataException(
                        "Character inventory contains a duplicate character key.");
                if (entry.Value == null)
                    throw new InvalidDataException(
                        "Character inventory contains a null character record.");
                canonical[entry.Key] = entry.Value;
            }

            if (seen.Count == 0)
                throw new InvalidDataException(
                    "Character inventory contains no recognized character records.");

            // Unknown root entries are not part of the per-protagonist
            // ledger. Mark them for rewrite even when their count happens to
            // equal the three canonical character records.
            migrated = decoded.Count != seen.Count ||
                seen.Count != canonical.Count;
            foreach (Inventory inventory in canonical.Values)
                migrated |= NormalizeInventory(inventory);
            return canonical;
        }

        private static void TryRecoverFromBackup()
        {
            string backup = PathName + ".bak";
            if (!File.Exists(backup)) return;
            try
            {
                Dictionary<string, Inventory> recovered = DecodeState(
                    File.ReadAllText(backup), out bool migrated);
                _state = recovered;
                _stateDirty = false;
                // Keep the known-good backup intact until the replacement has
                // succeeded. SaveStateLocked's normal path intentionally
                // refreshes .bak, which would overwrite our recovery source.
                SaveStateLocked(preserveBackup: true);
                if (migrated)
                    ClientLog.Info("Character", "loadouts_backup_migrated");
                ClientLog.Warn("Character", "loadouts_recovered_from_backup");
            }
            catch (Exception backupEx)
            {
                ClientLog.Error("Character", "loadouts_backup_load_failed",
                    backupEx);
            }
        }

        // Persistence-only hooks keep malformed-save regression coverage out
        // of GTA. They do not construct a Script or access a native hash.
        internal static IDisposable UsePersistenceForTests(
            string path, Dictionary<string, Inventory> state, bool dirty)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new ArgumentException("A persistence path is required.",
                    nameof(path));
            lock (Sync)
            {
                string previousPath = _pathNameOverride;
                Dictionary<string, Inventory> previousState = _state;
                bool previousDirty = _stateDirty;
                DateTime previousWrite = _lastWrite;
                _pathNameOverride = path;
                _state = state ?? EmptyState();
                _stateDirty = dirty;
                _lastWrite = DateTime.MinValue;
                return new PersistenceTestScope(() =>
                {
                    lock (Sync)
                    {
                        _pathNameOverride = previousPath;
                        _state = previousState;
                        _stateDirty = previousDirty;
                        _lastWrite = previousWrite;
                    }
                });
            }
        }

        internal static void ReloadForTests(bool discardStaged = false) =>
            Reload(discardStaged);

        internal static Dictionary<string, Inventory> StateForTests()
        {
            lock (Sync) return _state;
        }

        private sealed class PersistenceTestScope : IDisposable
        {
            private Action _dispose;

            internal PersistenceTestScope(Action dispose) { _dispose = dispose; }

            public void Dispose()
            {
                Action dispose = _dispose;
                _dispose = null;
                dispose?.Invoke();
            }
        }

        private void OnTick(object sender, EventArgs args)
        {
            // Observe death before the loading guard. Hospital respawn can
            // activate GTA's loading state, and treating that transition like
            // an explicit save reload would restore the just-consumed gear.
            Ped player = null;
            if (Game.Player.IsDead && !_deathObserved)
            {
                player = Game.Player.Character;
                HandlePlayerDeath(player);
            }

            if (Game.IsLoading)
            {
                _deferredWeapons.Clear();
                _restorePending = true;
                _discardStagedAfterLoad = true;
                _saveWasInProgress = false;
                return;
            }

            if (player == null)
                player = Game.Player.Character;
            if (player == null || !player.Exists())
            {
                _restorePending = true;
                return;
            }

            if (player.IsDead)
            {
                _restorePending = true;
                return;
            }

            if (_discardStagedAfterLoad)
            {
                _discardStagedAfterLoad = false;
                int timeSinceDeath = _deathObserved
                    ? Function.Call<int>(Hash.GET_TIME_SINCE_LAST_DEATH)
                    : -1;
                if (ShouldPreserveDeathAcrossLoading(
                        _deathObserved, timeSinceDeath))
                {
                    // A hospital transition is not an explicit save reload.
                    // Keep the staged death loss (and the rest of the current
                    // session) so the next Story save remains authoritative.
                    ClientLog.Info("Character",
                        "death_state_preserved_across_respawn_load",
                        new Dictionary<string, object> {
                            { "time_since_death_ms", timeSinceDeath }
                        });
                }
                else
                {
                    GbayShop.DiscardStagedRuntimeGear(
                        Game.Player.Character);
                    // Story loading intentionally discards staged changes;
                    // pass that intent through so a transiently missing
                    // primary cannot retain the discarded purchase.
                    Reload(discardStaged: true);
                    GbayPreferences.DiscardStaged();
                    ResetDeathTracking();
                    ClientLog.Info("Character",
                        "unsaved_gbay_state_discarded");
                }
                _lastCharacter = "";
                _lastPedHandle = 0;
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

            CompleteDeathCleanup(player, character);

            BackupWhenStorySaveWritten(character, player);
            bool saveInProgress = Function.Call<bool>(Hash.IS_AUTO_SAVE_IN_PROGRESS);
            if (saveInProgress && !_saveWasInProgress)
                CaptureWeaponAmmo(character, player, "story_save_started");
            _saveWasInProgress = saveInProgress;

            if (character == _lastCharacter && player.Handle == _lastPedHandle)
            {
                RetryDeferredWeapons(character);
                return;
            }
            _lastCharacter = character;
            _lastPedHandle = player.Handle;
            Apply(character);
        }

        private void HandlePlayerDeath(Ped player)
        {
            _deathObserved = true;
            _deathCharacter = CharacterForPed(player);
            if (_deathCharacter.Length == 0)
                _deathCharacter = _lastCharacter;
            _gearLostOnDeath.Clear();

            _juggernautActiveOnDeath =
                GbayShop.ClearRuntimeGearAfterDeath();
            if (_deathCharacter.Length == 0)
            {
                ClientLog.Warn("Character", "gear_reset_on_death_skipped",
                    new Dictionary<string, object> {
                        { "reason", "character_unresolved" }
                    });
                return;
            }

            lock (Sync)
            {
                if (!_state.TryGetValue(_deathCharacter,
                        out Inventory inventory))
                    return;
                NormalizeInventory(inventory);
                _gearLostOnDeath.AddRange(
                    ConsumeAllGearAfterDeathInMemory(inventory));
                if (_gearLostOnDeath.Count > 0)
                    StageStateLocked(_deathCharacter,
                        "gear_lost_on_death",
                        string.Join(",", _gearLostOnDeath));
            }

            RemoveDeathGearFromPed(player, _gearLostOnDeath);
            ClientLog.Info("Character", "gear_reset_on_death",
                new Dictionary<string, object> {
                    { "character", _deathCharacter },
                    { "gear_count", _gearLostOnDeath.Count },
                    { "gear", string.Join(",", _gearLostOnDeath) },
                    { "persistence", "staged_until_story_save" }
                });
        }

        private void CompleteDeathCleanup(Ped player, string character)
        {
            if (!_deathObserved) return;
            if (string.Equals(character, _deathCharacter,
                    StringComparison.OrdinalIgnoreCase))
            {
                GbayShop.CompleteRuntimeGearCleanupAfterDeath(
                    player, _juggernautActiveOnDeath);
                RemoveDeathGearFromPed(player, _gearLostOnDeath);
            }
            ResetDeathTracking();
        }

        private void ResetDeathTracking()
        {
            _deathObserved = false;
            _deathCharacter = "";
            _juggernautActiveOnDeath = false;
            _gearLostOnDeath.Clear();
        }

        internal static bool ShouldPreserveDeathAcrossLoading(
            bool deathObserved, int timeSinceDeathMs)
        {
            return deathObserved && timeSinceDeathMs >= 0 &&
                timeSinceDeathMs <= DeathRespawnLoadWindowMs;
        }

        private static void RemoveDeathGearFromPed(
            Ped player, IEnumerable<string> gear)
        {
            if (player == null || !player.Exists()) return;
            bool removeArmor = false;
            foreach (string item in gear ?? new string[0])
            {
                if (GearList.IsArmor(item))
                {
                    removeArmor = true;
                    continue;
                }
                if (string.Equals(item, "WEAPON_NIGHTVISION",
                        StringComparison.OrdinalIgnoreCase))
                    continue;
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                    player.Handle, Game.GenerateHash(item));
            }
            if (removeArmor)
                player.Armor = 0;
        }

        private void Apply(string character)
        {
            _deferredWeapons.Clear();
            _weaponRestoreRetries = 0;
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
            var owned = new HashSet<string>(inventory.weapons ?? new List<string>(), StringComparer.OrdinalIgnoreCase);
            RuntimeWeaponCatalog.Refresh();
            WeaponRestoreResult restored = RestoreWeapons(ped, inventory, inventory.weapons);
            _deferredWeapons = new List<string>(restored.Deferred.Keys);
            _nextWeaponRestoreUtc = DateTime.UtcNow.AddSeconds(2);
            // Preserve the existing managed-stock removal policy. Add-on grants
            // come from saved ownership and the current receipt-authorized catalog.
            foreach (var entry in WeaponHashes.Value)
            {
                Hash hash = (Hash)entry.Value;
                if (!owned.Contains(entry.Key) && inventory.managed)
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
            if (inventory.outfit?.managed ?? false) ApplyOutfit(ped, inventory.outfit);
            // Shop actions and saved loadouts share validation. Apply the saved
            // appearance first so staged ballistic armor captures that outfit.
            foreach (string gear in inventory.equipped_gear)
                GbayShop.RestoreGearValidated(ped, gear);
            if (inventory.progress?.managed ?? false) ApplyProgress(character, inventory.progress);
            ClientLog.Info("Character", "loadout_applied", new Dictionary<string, object> {
                { "character", character }, { "weapons", restored.Restored.Count },
                { "saved_weapons", owned.Count }, { "deferred_weapons", restored.Deferred },
                { "managed", inventory.managed }, { "gear", inventory.gear?.Count ?? 0 }
            });
        }

        private static WeaponRestoreResult RestoreWeapons(Ped ped, Inventory inventory,
            IEnumerable<string> candidates)
        {
            return WeaponLoadoutRestore.Restore(inventory, candidates, RuntimeWeaponCatalog.All,
                weapon => Function.Call<bool>(Hash.IS_WEAPON_VALID, GetWeaponHash(weapon)),
                (weapon, ammo) => {
                    int hash = GetWeaponHash(weapon);
                    Function.Call(Hash.GIVE_WEAPON_TO_PED, ped.Handle, hash, ammo, false, false);
                    if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON, ped.Handle, hash, false))
                        return false;
                    // Restore exactly, even when GTA already supplied the weapon.
                    Function.Call(Hash.SET_PED_AMMO, ped.Handle, hash, ammo);
                    return true;
                },
                weapon => ApplyWeaponCustomization(ped, weapon, (Hash)GetWeaponHash(weapon), inventory));
        }

        private void RetryDeferredWeapons(string character)
        {
            if (_deferredWeapons.Count == 0 || _weaponRestoreRetries >= 5 ||
                DateTime.UtcNow < _nextWeaponRestoreUtc) return;
            if (!_state.TryGetValue(character, out Inventory inventory)) return;
            _weaponRestoreRetries++;
            _nextWeaponRestoreUtc = DateTime.UtcNow.AddSeconds(2);
            RuntimeWeaponCatalog.Refresh();
            WeaponRestoreResult result = RestoreWeapons(Game.Player.Character, inventory, _deferredWeapons);
            _deferredWeapons = new List<string>(result.Deferred.Keys);
            ClientLog.Info("Character", "loadout_restore_retry", new Dictionary<string, object> {
                { "character", character }, { "attempt", _weaponRestoreRetries },
                { "restored_weapons", result.Restored }, { "deferred_weapons", result.Deferred },
                { "retry_exhausted", _weaponRestoreRetries >= 5 && _deferredWeapons.Count > 0 },
                { "ownership_preserved", true }
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

        internal static GearInventorySnapshot CaptureGearSnapshot()
        {
            string character = CurrentCharacter();
            if (character.Length == 0) return null;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory))
                    return null;
                NormalizeInventory(inventory);
                return new GearInventorySnapshot
                {
                    Character = character,
                    Gear = new List<string>(inventory.gear),
                    Equipped = new List<string>(inventory.equipped_gear),
                };
            }
        }

        internal static bool RestoreGearSnapshot(GearInventorySnapshot snapshot)
        {
            if (snapshot == null || string.IsNullOrWhiteSpace(snapshot.Character) ||
                !string.Equals(CurrentCharacter(), snapshot.Character,
                    StringComparison.OrdinalIgnoreCase)) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(snapshot.Character, out Inventory inventory))
                    return false;
                inventory.gear = new List<string>(snapshot.Gear ??
                    new List<string>());
                inventory.equipped_gear = new List<string>(snapshot.Equipped ??
                    new List<string>());
                NormalizeInventory(inventory);
                StageStateLocked(snapshot.Character, "gear_operation_rollback", "");
                return true;
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
                SetWeaponComponentEquippedInMemory(customization, componentHash, attachmentPoint, true);
                StageStateLocked(character, "weapon_component", weapon);
            }
        }

        internal static void SetWeaponComponentEquippedInMemory(
            WeaponCustomization customization, int component, int point, bool equipped)
        {
            if (component == 0) throw new ArgumentException("A component is required");
            if (customization.owned_components == null) customization.owned_components = new List<int>();
            if (customization.unequipped_components == null) customization.unequipped_components = new List<int>();
            if (customization.active_components == null) customization.active_components = new Dictionary<string, int>();
            if (!customization.owned_components.Contains(component))
                customization.owned_components.Add(component);
            if (equipped)
            {
                customization.unequipped_components.RemoveAll(value => value == component);
                customization.active_components[point.ToString()] = component;
            }
            else
            {
                // Preserve another accessory that replaced a stale selection.
                foreach (var pair in new Dictionary<string, int>(customization.active_components))
                    if (pair.Value == component) customization.active_components.Remove(pair.Key);
                if (!customization.unequipped_components.Contains(component))
                    customization.unequipped_components.Add(component);
            }
        }

        internal static bool RecordWeaponComponentUnequipped(string weapon, int component, int point)
        {
            string character = CurrentCharacter();
            if (character.Length == 0 || string.IsNullOrWhiteSpace(weapon)) return false;
            lock (Sync)
            {
                if (!_state.TryGetValue(character, out Inventory inventory)) return false;
                NormalizeInventory(inventory);
                SetWeaponComponentEquippedInMemory(GetOrCreateCustomization(inventory, weapon), component, point, false);
                StageStateLocked(character, "weapon_component_unequipped", weapon);
                return true;
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
                    weapon, out WeaponCustomization customization))
            {
                WeaponComponentDefaults.RestoreEmptySightSlots(ped.Handle, unchecked((int)weaponHash));
                return;
            }
            foreach (int component in customization.unequipped_components)
                if (!customization.active_components.ContainsValue(component))
                    Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED,
                        ped.Handle, weaponHash, component);
            foreach (int component in customization.active_components.Values)
            {
                if (Function.Call<bool>(Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT,
                        weaponHash, component))
                    Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED,
                        ped.Handle, weaponHash, component);
            }
            WeaponComponentDefaults.RestoreEmptySightSlots(ped.Handle, unchecked((int)weaponHash));
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
            if (customization.active_tint >= 0 && customization.active_tint <
                RuntimeWeaponCatalog.SupportedTintCount(weapon, tintCount))
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
                foreach (int component in customization.unequipped_components)
                    if (!customization.active_components.ContainsValue(component) &&
                        Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                            ped.Handle, weaponHash, component)) return false;
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
                    customization.active_tint < RuntimeWeaponCatalog.SupportedTintCount(weapon, tintCount) &&
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
            return StorySaveMonitor.LatestStorySaveWriteUtc();
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
                    if (value.unequipped_components == null)
                    {
                        value.unequipped_components = new List<int>(); changed = true;
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

        internal static List<string> ConsumeAllGearAfterDeathInMemory(
            Inventory inventory)
        {
            var removed = new List<string>();
            if (inventory == null) return removed;
            foreach (string item in inventory.gear ?? new List<string>())
                if (!string.IsNullOrWhiteSpace(item) &&
                    !ContainsIgnoreCase(removed, item))
                    removed.Add(item);
            foreach (string item in inventory.equipped_gear ??
                    new List<string>())
                if (!string.IsNullOrWhiteSpace(item) &&
                    !ContainsIgnoreCase(removed, item))
                    removed.Add(item);
            inventory.gear = new List<string>();
            inventory.equipped_gear = new List<string>();
            return removed;
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

        private static void SaveStateLocked(bool preserveBackup = false)
        {
            string temporary = PathName + ".tmp";
            File.WriteAllText(temporary, Json.Serialize(_state));
            if (File.Exists(PathName) && !preserveBackup)
                File.Copy(PathName, PathName + ".bak", true);
            if (File.Exists(PathName))
                File.Replace(temporary, PathName, null);
            else File.Move(temporary, PathName);
            _lastWrite = File.GetLastWriteTimeUtc(PathName);
            _stateDirty = false;
        }
    }
}
