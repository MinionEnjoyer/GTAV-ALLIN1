// GbayShop.cs -- GBAY vehicle shop script entrypoint.
//
// Thin Script shell that handles config loading, key binding, and delegates
// all UI rendering to GbayBrowser. Delivery/purchase execution stays here
// so GbayBrowser only handles presentation.

using System;
using System.IO;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class GbayShop : Script
    {
        // --- Config ---
        private static readonly string SCRIPTS_DIR =
            AppDomain.CurrentDomain.BaseDirectory;
        private static readonly string CONFIG_PATH = Path.Combine(SCRIPTS_DIR, "ALLIN1.toml");
        private static readonly string GEAR_PRICES_PATH = Path.Combine(SCRIPTS_DIR, "prices_gear.toml");
        private static readonly string LOG_PATH = Path.Combine(SCRIPTS_DIR, "ALLIN1_gbay.log");

        private Keys _openKey = Keys.F9;
        private Keys _nightVisionKey = Keys.N;
        private bool _freeMode;
        private bool _garageDebug;
        private bool _enableLogging = true;
        private bool _initialized;

        // Night vision state
        internal static bool NightVisionOwned;
        private static bool _nightVisionActive;

        // Juggernaut armor state
        internal static bool JuggernautActive;
        private static int _savedMaxHealth;
        private static int[] _savedComponents; // 12 components: drawable per slot
        private static int[] _savedTextures;   // 12 components: texture per slot
        private static PedHash _lastCharacter; // track character switches

        // --- Browser UI ---
        private GbayBrowser _browser;

        // --- Public accessors for GbayBrowser ---
        internal bool FreeMode => _freeMode;

        public GbayShop()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        // ------------------------------------------------------------------ //
        //  Logging                                                            //
        // ------------------------------------------------------------------ //

        internal void Log(string msg)
        {
            if (!_enableLogging)
                return;
            try
            {
                File.AppendAllText(LOG_PATH,
                    $"[{DateTime.Now:HH:mm:ss}] {msg}{Environment.NewLine}");
            }
            catch { }
        }

        internal void LogException(string context, Exception ex)
        {
            try
            {
                File.AppendAllText(LOG_PATH,
                    $"[{DateTime.Now:HH:mm:ss}] EXCEPTION in {context}: {ex.Message}{Environment.NewLine}" +
                    $"  {ex.StackTrace}{Environment.NewLine}");
            }
            catch { }
        }

        // ------------------------------------------------------------------ //
        //  Config                                                             //
        // ------------------------------------------------------------------ //

        private void LoadConfig()
        {
            _openKey = Keys.F9;
            _freeMode = false;
            _garageDebug = false;
            _enableLogging = true;

            if (!File.Exists(CONFIG_PATH))
                return;

            try
            {
                string currentSection = "";
                foreach (string rawLine in File.ReadAllLines(CONFIG_PATH))
                {
                    string line = rawLine.Trim();
                    if (line.Length == 0 || line.StartsWith("#"))
                        continue;

                    if (line.StartsWith("[") && line.EndsWith("]"))
                    {
                        currentSection = line.Substring(1, line.Length - 2)
                            .Trim().ToLowerInvariant();
                        continue;
                    }

                    if (currentSection != "script")
                        continue;

                    int eq = line.IndexOf('=');
                    if (eq < 0)
                        continue;

                    string key = line.Substring(0, eq).Trim().ToLowerInvariant();
                    string val = line.Substring(eq + 1).Trim();
                    string valLower = val.ToLowerInvariant();

                    if (key == "gbay_key")
                    {
                        string cleaned = val.Trim('"', '\'');
                        if (Enum.TryParse(cleaned, true, out Keys parsed))
                            _openKey = parsed;
                    }
                    else if (key == "gbay_free_mode")
                    {
                        _freeMode = valLower == "true";
                    }
                    else if (key == "garage_debug")
                    {
                        _garageDebug = valLower == "true";
                    }
                    else if (key == "enable_logging")
                    {
                        _enableLogging = valLower == "true";
                    }
                    else if (key == "spawner_debug")
                    {
                        TrafficSpawner.ShowSpawnMessages = valLower == "true";
                    }
                }
            }
            catch (Exception ex)
            {
                LogException("LoadConfig", ex);
            }
        }

        private void LoadGearPrices()
        {
            if (!File.Exists(GEAR_PRICES_PATH))
                return;

            try
            {
                int count = 0;
                foreach (string rawLine in File.ReadAllLines(GEAR_PRICES_PATH))
                {
                    string line = rawLine.Trim();
                    if (line.Length == 0 || line.StartsWith("#") ||
                        (line.StartsWith("[") && line.EndsWith("]")))
                        continue;

                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;

                    string key = line.Substring(0, eq).Trim();
                    string val = line.Substring(eq + 1).Trim();

                    if (int.TryParse(val, out int price))
                    {
                        GearList.Prices[key] = price;
                        count++;
                    }
                }

                Log($"LoadGearPrices: loaded {count} prices from {GEAR_PRICES_PATH}");
            }
            catch (Exception ex)
            {
                LogException("LoadGearPrices", ex);
            }
        }

        // ------------------------------------------------------------------ //
        //  Initialization                                                     //
        // ------------------------------------------------------------------ //

        private void Initialize()
        {
            LoadConfig();
            LoadGearPrices();
            Log($"=== GBAY Initialized: key={_openKey} freeMode={_freeMode} garageDebug={_garageDebug} ===");

            try
            {
                GarageManager.Configure(_garageDebug, _enableLogging);
                GarageManager.Initialize();
                Log("GarageManager initialized");
            }
            catch (Exception ex)
            {
                LogException("GarageManager.Initialize", ex);
            }

            _browser = new GbayBrowser(this);
            _initialized = true;
        }

        // ------------------------------------------------------------------ //
        //  Delivery Execution (called by GbayBrowser)                         //
        // ------------------------------------------------------------------ //

        internal void ExecuteDeliverHere(string model, int price)
        {
            Ped player = Game.Player.Character;
            Vector3 pos = player.Position + player.ForwardVector * 5f;
            float heading = player.Heading + 90f;

            try
            {
                Vehicle veh = VehicleHelper.CreateVehicle(model, pos, heading);
                if (veh == null)
                {
                    Log($"DeliverHere: CreateVehicle returned null for {model}");
                    GTA.UI.Screen.ShowSubtitle("~r~Failed to create vehicle.", 3000);
                    return;
                }

                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;

                veh.IsPersistent = true;

                string name = VehicleList.DisplayNames.ContainsKey(model)
                    ? VehicleList.DisplayNames[model] : model;
                string msg = _freeMode || price <= 0
                    ? $"~g~{name}~w~ delivered!"
                    : $"~g~{name}~w~ purchased for ~g~${price:N0}";
                GTA.UI.Screen.ShowSubtitle(msg, 3000);

                Log($"DeliverHere: {model} spawned at player, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverHere", ex);
                GTA.UI.Screen.ShowSubtitle("~r~Failed to create vehicle.", 3000);
            }
        }

        internal void ExecuteDeliverToGarage(string model, int price)
        {
            int used = GarageManager.GetUsedSlots();
            int cap = GarageManager.GetCapacity();

            if (used >= cap)
            {
                Log($"DeliverToGarage: full ({used}/{cap})");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Garage full.~w~ ({used}/{cap} slots used)", 3000);
                return;
            }

            var rng = new Random();
            int c1 = rng.Next(0, 160);
            int c2 = rng.Next(0, 160);

            try
            {
                bool success = GarageManager.DeliverVehicle(model, c1, c2);
                if (!success)
                {
                    Log($"DeliverToGarage: failed for {model}");
                    GTA.UI.Screen.ShowSubtitle("~r~Delivery to garage failed.", 3000);
                    return;
                }

                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;

                string name = VehicleList.DisplayNames.ContainsKey(model)
                    ? VehicleList.DisplayNames[model] : model;
                string msg = _freeMode || price <= 0
                    ? $"~g~{name}~w~ delivered to garage!"
                    : $"~g~{name}~w~ delivered to garage for ~g~${price:N0}";
                GTA.UI.Screen.ShowSubtitle(msg, 3000);

                Log($"DeliverToGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToGarage", ex);
                GTA.UI.Screen.ShowSubtitle("~r~Delivery to garage failed.", 3000);
            }
        }

        // ------------------------------------------------------------------ //
        //  Weapon Purchase (called by GbayBrowser)                            //
        // ------------------------------------------------------------------ //

        internal void ExecuteGiveWeapon(string weaponName, int price)
        {
            Ped player = Game.Player.Character;
            Hash weaponHash = (Hash)Game.GenerateHash(weaponName);

            // Check funds
            if (!_freeMode && price > 0 && Game.Player.Money < price)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds.", 3000);
                return;
            }

            // Give weapon with ammo
            player.Weapons.Give((WeaponHash)(uint)weaponHash, 9999, false, true);

            if (!_freeMode && price > 0)
                Game.Player.Money -= price;

            string displayName = WeaponList.DisplayNames.ContainsKey(weaponName)
                ? WeaponList.DisplayNames[weaponName] : weaponName;
            string msg = _freeMode || price <= 0
                ? $"~g~{displayName}~w~ added!"
                : $"~g~{displayName}~w~ purchased for ~g~${price:N0}";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"GiveWeapon: {weaponName}, price=${price}");
        }

        /// <summary>
        /// Refill ammo for an owned weapon. Returns the cost charged,
        /// or -1 if already fully stocked, or -2 if insufficient funds.
        /// </summary>
        internal int ExecuteRefillAmmo(string weaponName)
        {
            Ped player = Game.Player.Character;
            Hash weaponHash = (Hash)Game.GenerateHash(weaponName);

            // Get current and max ammo
            int currentAmmo = Function.Call<int>(
                Hash.GET_AMMO_IN_PED_WEAPON, player, weaponHash);

            OutputArgument maxAmmoOut = new OutputArgument();
            Function.Call<bool>(
                Hash.GET_MAX_AMMO, player, weaponHash, maxAmmoOut);
            int maxAmmo = maxAmmoOut.GetResult<int>();

            if (maxAmmo <= 0)
            {
                GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                return -1;
            }

            int needed = maxAmmo - currentAmmo;
            if (needed <= 0)
            {
                GTA.UI.Screen.ShowSubtitle("~g~Already fully stocked!", 3000);
                return -1;
            }

            int costPerRound = WeaponList.AmmoCostPerRound.ContainsKey(weaponName)
                ? WeaponList.AmmoCostPerRound[weaponName] : 2;
            int totalCost = needed * costPerRound;

            if (_freeMode)
                totalCost = 0;

            if (!_freeMode && totalCost > 0 && Game.Player.Money < totalCost)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds for ammo.", 3000);
                return -2;
            }

            Function.Call(Hash.SET_PED_AMMO, player, weaponHash, maxAmmo);

            if (!_freeMode && totalCost > 0)
                Game.Player.Money -= totalCost;

            string displayName = WeaponList.DisplayNames.ContainsKey(weaponName)
                ? WeaponList.DisplayNames[weaponName] : weaponName;
            string msg = totalCost > 0
                ? $"~g~{displayName}~w~ ammo refilled ({needed} rounds) for ~g~${totalCost:N0}"
                : $"~g~{displayName}~w~ ammo refilled ({needed} rounds)!";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"RefillAmmo: {weaponName}, {needed} rounds, cost=${totalCost}");
            return totalCost;
        }

        // ------------------------------------------------------------------ //
        //  Gear Purchase (called by GbayBrowser)                              //
        // ------------------------------------------------------------------ //

        internal void ExecuteGiveGear(string gearId, int price)
        {
            Ped player = Game.Player.Character;

            // Check funds
            if (!_freeMode && price > 0 && Game.Player.Money < price)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds.", 3000);
                return;
            }

            if (gearId == GearList.ARMOR_JUGGERNAUT)
            {
                ApplyJuggernaut(player);
                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? "~g~Juggernaut Armor~w~ equipped! Heavy movement active."
                        : $"~g~Juggernaut Armor~w~ purchased for ~g~${price:N0}~w~. Heavy movement active.",
                    4000);
                Log($"GiveGear: {gearId}, price=${price}");
                return;
            }
            else if (GearList.IsArmor(gearId))
            {
                // Remove juggernaut if equipping a lower armor tier
                if (JuggernautActive)
                    RemoveJuggernaut(player);
                player.Armor = GearList.ArmorValues[gearId];
            }
            else if (gearId == "WEAPON_NIGHTVISION")
            {
                NightVisionOwned = true;
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? "~g~Night Vision~w~ acquired! Press ~y~N~w~ to toggle."
                        : $"~g~Night Vision~w~ purchased for ~g~${price:N0}~w~. Press ~y~N~w~ to toggle.",
                    4000);
                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;
                Log($"GiveGear: {gearId}, price=${price}");
                return;
            }
            else
            {
                WeaponHash itemHash = (WeaponHash)Game.GenerateHash(gearId);
                player.Weapons.Give(itemHash, 1, false, true);
            }

            if (!_freeMode && price > 0)
                Game.Player.Money -= price;

            string displayName = GearList.DisplayNames.ContainsKey(gearId)
                ? GearList.DisplayNames[gearId] : gearId;
            string msg = _freeMode || price <= 0
                ? $"~g~{displayName}~w~ acquired!"
                : $"~g~{displayName}~w~ purchased for ~g~${price:N0}";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"GiveGear: {gearId}, price=${price}");
        }

        // ------------------------------------------------------------------ //
        //  Vehicle Sell (called by GbayBrowser garage tab)                     //
        // ------------------------------------------------------------------ //

        /// <summary>Get the sell price for a vehicle (60% of purchase price).</summary>
        internal int GetSellPrice(string model)
        {
            if (_freeMode) return 0;
            int buyPrice = VehicleList.Prices.ContainsKey(model)
                ? VehicleList.Prices[model] : 0;
            return (int)(buyPrice * 0.6);
        }

        internal void ExecuteSellVehicle(string model, int listIndex)
        {
            int sellPrice = GetSellPrice(model);

            GarageManager.RemoveVehicle(listIndex);

            if (!_freeMode && sellPrice > 0)
                Game.Player.Money += sellPrice;

            string displayName = VehicleList.DisplayNames.ContainsKey(model)
                ? VehicleList.DisplayNames[model] : model;
            string msg = _freeMode || sellPrice <= 0
                ? $"~y~{displayName}~w~ removed from garage."
                : $"~g~{displayName}~w~ sold for ~g~${sellPrice:N0}";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"SellVehicle: {model}, sellPrice=${sellPrice}");
        }

        /// <summary>
        /// Get the ammo refill cost for an owned weapon. Returns -1 if not
        /// applicable (melee/misc), 0 if fully stocked, otherwise the cost.
        /// Also outputs the round count needed.
        /// </summary>
        internal int GetAmmoRefillInfo(string weaponName, out int roundsNeeded)
        {
            roundsNeeded = 0;
            Ped player = Game.Player.Character;
            Hash weaponHash = (Hash)Game.GenerateHash(weaponName);

            int currentAmmo = Function.Call<int>(
                Hash.GET_AMMO_IN_PED_WEAPON, player, weaponHash);

            OutputArgument maxAmmoOut = new OutputArgument();
            Function.Call<bool>(
                Hash.GET_MAX_AMMO, player, weaponHash, maxAmmoOut);
            int maxAmmo = maxAmmoOut.GetResult<int>();

            if (maxAmmo <= 0)
                return -1;  // melee/no-ammo

            roundsNeeded = maxAmmo - currentAmmo;
            if (roundsNeeded <= 0)
                return 0;  // fully stocked

            int costPerRound = WeaponList.AmmoCostPerRound.ContainsKey(weaponName)
                ? WeaponList.AmmoCostPerRound[weaponName] : 2;

            return _freeMode ? 0 : roundsNeeded * costPerRound;
        }

        // ------------------------------------------------------------------ //
        //  Armor Removal (called by GbayBrowser gear tab)                     //
        // ------------------------------------------------------------------ //

        internal void ExecuteRemoveArmor(string gearId)
        {
            Ped player = Game.Player.Character;

            if (gearId == GearList.ARMOR_JUGGERNAUT)
            {
                RemoveJuggernaut(player);
                GTA.UI.Screen.ShowSubtitle("~y~Juggernaut Armor~w~ removed.", 3000);
                Log("RemoveArmor: juggernaut removed");
            }
            else
            {
                player.Armor = 0;
                string displayName = GearList.DisplayNames.ContainsKey(gearId)
                    ? GearList.DisplayNames[gearId] : gearId;
                GTA.UI.Screen.ShowSubtitle($"~y~{displayName}~w~ removed.", 3000);
                Log($"RemoveArmor: {gearId} removed (armor set to 0)");
            }
        }

        internal void ExecuteRemoveNightVision()
        {
            NightVisionOwned = false;
            if (_nightVisionActive)
            {
                _nightVisionActive = false;
                Function.Call(Hash.SET_NIGHTVISION, false);
            }
            GTA.UI.Screen.ShowSubtitle("~y~Night Vision~w~ removed.", 3000);
            Log("RemoveNightVision: removed");
        }

        // ------------------------------------------------------------------ //
        //  Juggernaut Armor                                                   //
        // ------------------------------------------------------------------ //

        private const string BALLISTIC_CLIPSET = "ANIM_GROUP_MOVE_BALLISTIC";
        private const int JUGGERNAUT_MAX_HEALTH = 1000;
        private static int _lastKnownHealth;
        private static int _savedPropDrawable;
        private static int _savedPropTexture;
        private static int _savedEarPropDrawable;
        private static int _savedEarPropTexture;

        private void ApplyJuggernaut(Ped player)
        {
            // Save current outfit so we can restore later
            _savedComponents = new int[12];
            _savedTextures = new int[12];
            for (int i = 0; i < 12; i++)
            {
                _savedComponents[i] = Function.Call<int>(
                    Hash.GET_PED_DRAWABLE_VARIATION, player, i);
                _savedTextures[i] = Function.Call<int>(
                    Hash.GET_PED_TEXTURE_VARIATION, player, i);
            }

            // Save helmet/hat prop and ear prop
            _savedPropDrawable = Function.Call<int>(
                Hash.GET_PED_PROP_INDEX, player, 0);
            _savedPropTexture = Function.Call<int>(
                Hash.GET_PED_PROP_TEXTURE_INDEX, player, 0);
            _savedEarPropDrawable = Function.Call<int>(
                Hash.GET_PED_PROP_INDEX, player, 2);
            _savedEarPropTexture = Function.Call<int>(
                Hash.GET_PED_PROP_TEXTURE_INDEX, player, 2);

            // Apply Paleto Score ballistic outfit
            PedHash ch = GetCurrentCharacter();
            ApplyBallisticOutfit(player, ch);

            // Health boost to 1000 (matches Paleto Score mission values)
            _savedMaxHealth = player.MaxHealth;
            player.MaxHealth = JUGGERNAUT_MAX_HEALTH;
            player.Health = JUGGERNAUT_MAX_HEALTH;
            player.Armor = 0; // armor value isn't what makes it tanky
            _lastKnownHealth = JUGGERNAUT_MAX_HEALTH;

            // Disable headshot bonus damage
            player.CanSufferCriticalHits = false;

            // Heavy movement clipset
            Function.Call(Hash.REQUEST_ANIM_SET, BALLISTIC_CLIPSET);
            int timeout = 1000;
            while (!Function.Call<bool>(Hash.HAS_ANIM_SET_LOADED, BALLISTIC_CLIPSET)
                   && timeout > 0)
            {
                Script.Wait(0);
                timeout -= 16;
            }
            Function.Call(Hash.SET_PED_MOVEMENT_CLIPSET, player,
                BALLISTIC_CLIPSET, 0.25f);

            JuggernautActive = true;
            Log("Juggernaut armor applied");
        }

        internal static void RemoveJuggernaut(Ped player)
        {
            if (!JuggernautActive) return;

            // Restore outfit
            if (_savedComponents != null && _savedTextures != null)
            {
                for (int i = 0; i < 12; i++)
                {
                    Function.Call(Hash.SET_PED_COMPONENT_VARIATION,
                        player, i, _savedComponents[i], _savedTextures[i], 0);
                }
            }

            // Restore helmet/hat prop
            if (_savedPropDrawable >= 0)
                Function.Call(Hash.SET_PED_PROP_INDEX, player, 0,
                    _savedPropDrawable, _savedPropTexture, true);
            else
                Function.Call(Hash.CLEAR_PED_PROP, player, 0);

            // Restore ear prop
            if (_savedEarPropDrawable >= 0)
                Function.Call(Hash.SET_PED_PROP_INDEX, player, 2,
                    _savedEarPropDrawable, _savedEarPropTexture, true);
            else
                Function.Call(Hash.CLEAR_PED_PROP, player, 2);

            // Restore health
            player.MaxHealth = _savedMaxHealth > 0 ? _savedMaxHealth : 200;
            if (player.Health > player.MaxHealth)
                player.Health = player.MaxHealth;

            // Re-enable critical hits
            player.CanSufferCriticalHits = true;

            // Reset movement clipset
            Function.Call(Hash.RESET_PED_MOVEMENT_CLIPSET, player, 0.25f);

            JuggernautActive = false;
        }

        private static void ApplyBallisticOutfit(Ped player, PedHash ch)
        {
            // Paleto Score juggernaut suit — confirmed in-game on Enhanced Edition
            // via F10 debug overlay during the heist mission.
            //
            // The suit is built from multiple component slots + helmet prop.
            // Each character has different drawable IDs.
            // Uses SafeSetComponent to validate drawable/texture are in range
            // before applying (mission context may have different ranges than free-roam).

            if (ch == PedHash.Michael)
            {
                // Michael — captured during Paleto Score (Enhanced)
                SafeSetComponent(player, 3,  5, 1); // torso
                SafeSetComponent(player, 4,  5, 1); // legs
                SafeSetComponent(player, 5,  1, 1); // hands
                SafeSetComponent(player, 6,  1, 1); // shoes
                SafeSetComponent(player, 8,  5, 2); // shirt/accessory
                SafeSetComponent(player, 9,  1, 2); // body armor
                SafeSetComponent(player, 11, 0, 1); // aux/torso2
                SafeSetProp(player, 0, 26, 1);      // helmet
                SafeSetProp(player, 2,  0, 1);      // ears
            }
            else if (ch == PedHash.Trevor)
            {
                // Trevor — captured during Paleto Score (Enhanced)
                SafeSetComponent(player, 3,  2, 1); // torso
                SafeSetComponent(player, 4,  2, 1); // legs
                SafeSetComponent(player, 5,  1, 1); // hands
                SafeSetComponent(player, 6,  1, 1); // shoes
                SafeSetComponent(player, 8,  2, 1); // shirt/accessory
                SafeSetComponent(player, 9,  1, 4); // body armor
                SafeSetComponent(player, 11, 0, 0); // aux/torso2
                SafeSetProp(player, 0, 24, 1);      // helmet
            }
            else
            {
                // Franklin — partially captured via outfit editor.
                // Body armor confirmed, other slots use Michael's pattern with validation.
                SafeSetComponent(player, 3,  5, 1); // torso (placeholder)
                SafeSetComponent(player, 4,  4, 0); // legs — confirmed D4/T0
                SafeSetComponent(player, 5,  4, 0); // hands — confirmed D4/T0
                SafeSetComponent(player, 6,  1, 1); // shoes (placeholder)
                SafeSetComponent(player, 8,  5, 2); // shirt/accessory (placeholder)
                SafeSetComponent(player, 9,  3, 0); // body armor — confirmed D3/T0
                SafeSetComponent(player, 11, 0, 1); // aux/torso2 (placeholder)
                SafeSetProp(player, 0, 26, 1);      // helmet (placeholder)
            }
        }

        /// <summary>
        /// Set a component variation only if the drawable and texture are valid.
        /// Falls back to texture 0 if the requested texture is out of range.
        /// Skips entirely if the drawable is out of range.
        /// </summary>
        private static void SafeSetComponent(Ped player, int slot, int drawable, int texture)
        {
            int maxDrawable = Function.Call<int>(
                Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, player, slot);
            if (drawable >= maxDrawable)
                return; // drawable doesn't exist for this ped in free-roam

            int maxTexture = Function.Call<int>(
                Hash.GET_NUMBER_OF_PED_TEXTURE_VARIATIONS, player, slot, drawable);
            if (texture >= maxTexture)
                texture = 0; // fall back to texture 0

            Function.Call(Hash.SET_PED_COMPONENT_VARIATION, player, slot, drawable, texture, 0);
        }

        /// <summary>
        /// Set a prop only if the drawable and texture are valid.
        /// </summary>
        private static void SafeSetProp(Ped player, int slot, int drawable, int texture)
        {
            int maxDrawable = Function.Call<int>(
                Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS, player, slot);
            if (drawable >= maxDrawable)
                return;

            int maxTexture = Function.Call<int>(
                Hash.GET_NUMBER_OF_PED_PROP_TEXTURE_VARIATIONS, player, slot, drawable);
            if (texture >= maxTexture)
                texture = 0;

            Function.Call(Hash.SET_PED_PROP_INDEX, player, slot, drawable, texture, true);
        }

        /// <summary>
        /// Called every tick to apply damage reduction, check death, and
        /// detect character switches (which invalidate the juggernaut state).
        /// </summary>
        private void JuggernautTick()
        {
            Ped player = Game.Player.Character;
            if (player == null)
                return;

            // Detect character switch — reset juggernaut state
            PedHash currentChar = GetCurrentCharacter();
            if (currentChar != _lastCharacter)
            {
                if (JuggernautActive)
                {
                    // Character changed while juggernaut was active — just clear the flag.
                    // The old character's outfit is already gone, and the new character
                    // shouldn't inherit the juggernaut state.
                    JuggernautActive = false;
                    _savedComponents = null;
                    _savedTextures = null;
                    player.CanSufferCriticalHits = true;
                    Function.Call(Hash.RESET_PED_MOVEMENT_CLIPSET, player, 0.25f);
                    Log("Juggernaut cleared: character switch detected");
                }
                _lastCharacter = currentChar;
            }

            if (!JuggernautActive) return;

            if (player.IsDead)
            {
                JuggernautActive = false;
                _savedComponents = null;
                _savedTextures = null;
                return;
            }

            // Damage reduction: heal back 80% of damage taken each tick
            int currentHealth = player.Health;
            if (currentHealth < _lastKnownHealth && currentHealth > 0)
            {
                int damageTaken = _lastKnownHealth - currentHealth;
                int healBack = (int)(damageTaken * 0.80f);
                if (healBack > 0)
                {
                    int newHealth = Math.Min(currentHealth + healBack, player.MaxHealth);
                    player.Health = newHealth;
                    currentHealth = newHealth;
                }
            }
            _lastKnownHealth = currentHealth;
        }

        // ------------------------------------------------------------------ //
        //  Helpers                                                            //
        // ------------------------------------------------------------------ //

        internal static PedHash GetCurrentCharacter()
        {
            Model playerModel = Game.Player.Character.Model;

            if (playerModel == new Model(PedHash.Michael))
                return PedHash.Michael;
            if (playerModel == new Model(PedHash.Franklin))
                return PedHash.Franklin;
            if (playerModel == new Model(PedHash.Trevor))
                return PedHash.Trevor;

            return PedHash.Michael;
        }

        // ------------------------------------------------------------------ //
        //  Events                                                             //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            try
            {
                // Auto-initialize on first tick so garage blips/markers
                // appear immediately without needing to press F9 first.
                if (!_initialized && !Game.IsLoading)
                    Initialize();

                if (_initialized)
                    GarageManager.OnTick();

                if (_browser != null)
                    _browser.Draw();

                if (_garageDebug && _initialized)
                    GarageManager.DrawDebugMarkers();

                JuggernautTick();
            }
            catch (Exception ex)
            {
                LogException("OnTick", ex);
            }
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (Game.IsLoading)
                return;

            if (e.KeyCode == _openKey)
            {
                try
                {
                    if (!_initialized)
                        Initialize();

                    _browser.Toggle();
                }
                catch (Exception ex)
                {
                    LogException("OnKeyDown", ex);
                }
            }
            else if (e.KeyCode == _nightVisionKey && NightVisionOwned)
            {
                _nightVisionActive = !_nightVisionActive;
                Function.Call(Hash.SET_NIGHTVISION, _nightVisionActive);
            }
        }
    }
}
