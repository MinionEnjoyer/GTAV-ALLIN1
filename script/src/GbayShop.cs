// GbayShop.cs -- GBAY vehicle shop script entrypoint.
//
// Thin Script shell that handles config loading, key binding, and delegates
// all UI rendering to GbayBrowser. Delivery/purchase execution stays here
// so GbayBrowser only handles presentation.

using System;
using System.Collections.Generic;
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
        private bool _enableLogging = true;
        private bool _initialized;
        private bool _safeMode;
        private bool _garagesAlwaysAccessible;
        private bool _reducedMotion;
        private bool _colorblindMode;
        private float _uiScale = 1f;

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
        internal const int AmmoNotApplicable = -1;
        internal const int AmmoCapacityUnavailable = -3;

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
            ClientLog.Info("GBAY", msg);
        }

        internal void LogException(string context, Exception ex)
        {
            ClientLog.Error("GBAY", context, ex);
        }

        // ------------------------------------------------------------------ //
        //  Config                                                             //
        // ------------------------------------------------------------------ //

        private void LoadConfig()
        {
            _openKey = Keys.F9;
            _freeMode = false;
            _enableLogging = true;
            _safeMode = false;
            _garagesAlwaysAccessible = false;

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
                    else if (key == "night_vision_key")
                    {
                        string cleaned = val.Trim('"', '\'');
                        if (Enum.TryParse(cleaned, true, out Keys parsed))
                            _nightVisionKey = parsed;
                    }
                    else if (key == "gbay_free_mode")
                    {
                        _freeMode = valLower == "true";
                    }
                    else if (key == "enable_logging")
                    {
                        _enableLogging = valLower == "true";
                    }
                    else if (key == "safe_mode")
                    {
                        _safeMode = valLower == "true";
                    }
                    else if (key == "garages_always_accessible")
                    {
                        _garagesAlwaysAccessible = valLower == "true";
                    }
                    else if (key == "reduced_motion")
                    {
                        _reducedMotion = valLower == "true";
                    }
                    else if (key == "colorblind_mode")
                    {
                        _colorblindMode = valLower == "true";
                    }
                    else if (key == "ui_scale" && float.TryParse(val, out float scale))
                    {
                        _uiScale = Math.Max(0.75f, Math.Min(1.5f, scale));
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
            ClientLog.Configure(_enableLogging);
            ClientWatchdog.Configure(_safeMode);
            GbayBrowser.ReducedMotion = _reducedMotion;
            GbayRenderer.ColorblindMode = _colorblindMode;
            GbayRenderer.UiScale = _uiScale;
            LoadGearPrices();
            Log($"=== GBAY Initialized: key={_openKey} freeMode={_freeMode} ===");

            try
            {
                GarageManager.Configure(
                    _enableLogging, _garagesAlwaysAccessible);
                GarageManager.Initialize();
                GarageManager.InitializeDavisGarage();
                GarageManager.InitializeGarmentGarage();
                if (!ClientWatchdog.SafeMode)
                    GarageManager.InitializeFloorGarage();
                else
                    Log("Floor garage initialization deferred: " +
                        ClientWatchdog.SafeModeReason);
                Log("GarageManager base initialization completed");
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
                    ? $"~g~{name}~w~ delivered."
                    : $"~g~{name}~w~ purchased for ~g~${price:N0}~w~.";
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
            // Oversized vehicles route to floor garage instead
            if (VehicleList.GetSizeTier(model) == 2)
            {
                ExecuteDeliverToFloorGarage(model, price);
                return;
            }

            int used = GarageManager.GetUsedSlots();
            int cap = GarageManager.GetCapacity();

            if (used >= cap)
            {
                Log($"DeliverToGarage: full ({used}/{cap})");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The garage is full.~w~ ({used}/{cap} spaces used)", 3000);
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
                    ? $"~g~{name}~w~ delivered to the garage."
                    : $"~g~{name}~w~ delivered to the garage for ~g~${price:N0}~w~.";
                GTA.UI.Screen.ShowSubtitle(msg, 3000);

                Log($"DeliverToGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToGarage", ex);
                GTA.UI.Screen.ShowSubtitle("~r~Delivery to garage failed.", 3000);
            }
        }

        internal void ExecuteDeliverToFloorGarage(string model, int price)
        {
            int used = GarageManager.GetFloorGarageUsedSlots();
            int cap = GarageManager.GetFloorGarageCapacity();

            if (used >= cap)
            {
                Log($"DeliverToFloorGarage: full ({used}/{cap})");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The three-floor garage is full.~w~ ({used}/{cap} spaces used)", 3000);
                return;
            }

            var rng = new Random();
            int c1 = rng.Next(0, 160);
            int c2 = rng.Next(0, 160);

            try
            {
                bool success = GarageManager.DeliverToFloorGarage(model, c1, c2);
                if (!success)
                {
                    Log($"DeliverToFloorGarage: failed for {model}");
                    GTA.UI.Screen.ShowSubtitle("~r~Delivery to the three-floor garage failed.", 3000);
                    return;
                }

                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;

                string name = VehicleList.DisplayNames.ContainsKey(model)
                    ? VehicleList.DisplayNames[model] : model;
                string msg = _freeMode || price <= 0
                    ? $"~g~{name}~w~ delivered to the three-floor garage."
                    : $"~g~{name}~w~ delivered to the three-floor garage for ~g~${price:N0}~w~.";
                GTA.UI.Screen.ShowSubtitle(msg, 3000);

                Log($"DeliverToFloorGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToFloorGarage", ex);
                GTA.UI.Screen.ShowSubtitle("~r~Delivery to the three-floor garage failed.", 3000);
            }
        }

        internal void ExecuteDeliverToDavisGarage(string model, int price)
        {
            if (VehicleList.GetSizeTier(model) == 2)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~That vehicle is too large for the Davis Auto Shop.", 3000);
                return;
            }

            int used = GarageManager.GetDavisGarageUsedSlots();
            int cap = GarageManager.GetDavisGarageCapacity();
            if (used >= cap)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The Davis Auto Shop is full.~w~ ({used}/{cap} spaces used)",
                    3000);
                return;
            }

            var rng = new Random();
            try
            {
                bool success = GarageManager.DeliverToDavisGarage(
                    model, rng.Next(0, 160), rng.Next(0, 160));
                if (!success)
                {
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~Delivery to the Davis Auto Shop failed.", 3000);
                    return;
                }
                if (!_freeMode && price > 0) Game.Player.Money -= price;
                string name = VehicleList.DisplayNames.TryGetValue(
                    model, out string displayName) ? displayName : model;
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? $"~g~{name}~w~ delivered to the Davis Auto Shop."
                        : $"~g~{name}~w~ delivered to the Davis Auto Shop for ~g~${price:N0}~w~.",
                    3000);
                Log($"DeliverToDavisGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToDavisGarage", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Delivery to the Davis Auto Shop failed.", 3000);
            }
        }

        // ------------------------------------------------------------------ //
        //  Weapon Purchase (called by GbayBrowser)                            //
        // ------------------------------------------------------------------ //

        internal WeaponPurchaseQuote GetWeaponPurchaseQuote(
            string weaponName, int unitPrice)
        {
            Ped player = Game.Player.Character;
            Hash weaponHash = (Hash)Game.GenerateHash(weaponName);
            string category = WeaponList.CategoryNames.ContainsKey(weaponName)
                ? WeaponList.CategoryNames[weaponName] : "";
            int configuredQuantity = WeaponList.PurchaseQuantities.ContainsKey(
                    weaponName)
                ? WeaponList.PurchaseQuantities[weaponName] : 1;
            return WeaponPurchasePolicy.Quote(
                unitPrice, category, configuredQuantity, _freeMode);
        }

        internal void ExecuteGiveWeapon(string weaponName, int unitPrice)
        {
            Ped player = Game.Player.Character;
            Hash weaponHash = (Hash)Game.GenerateHash(weaponName);

            if (!Function.Call<bool>(Hash.IS_WEAPON_VALID, weaponHash))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~This weapon is unavailable in the installed GTA V build.", 3500);
                Log($"GiveWeapon: rejected unavailable weapon {weaponName}");
                return;
            }

            // The browser normally routes an owned weapon to ammo refill, but
            // recheck here so rapid input or another caller cannot charge for
            // the same weapon twice.
            if (Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    player.Handle, weaponHash, false) ||
                CharacterInventory.IsOwned(weaponName, false))
            {
                GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                Log($"GiveWeapon: duplicate purchase blocked for {weaponName}");
                return;
            }

            WeaponPurchaseQuote quote = GetWeaponPurchaseQuote(
                weaponName, unitPrice);
            if (quote.Status != WeaponPurchaseStatus.Available)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Purchase quantity is unavailable for this item.", 3000);
                ClientLog.Warn("GBAY", "weapon_purchase_quantity_unavailable",
                    new Dictionary<string, object> { { "weapon", weaponName } });
                return;
            }

            if (!_freeMode && quote.TotalPrice > 0
                && Game.Player.Money < quote.TotalPrice)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds.", 3000);
                return;
            }

            player.Weapons.Give((WeaponHash)(uint)weaponHash,
                quote.GrantAmmo, false, true);

            // Some Online-only weapons are edition/build gated. Never charge
            // the player unless the native confirms the weapon was granted.
            if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    player.Handle, weaponHash, false))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Weapon could not be granted by this GTA V build.", 3500);
                Log($"GiveWeapon: native grant failed for {weaponName}");
                return;
            }

            int actualAmmo = Function.Call<int>(
                Hash.GET_AMMO_IN_PED_WEAPON, player, weaponHash);
            if (quote.QuantityPriced && actualAmmo <= 0)
            {
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                    player.Handle, weaponHash);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The purchased item quantity could not be verified.", 3500);
                ClientLog.Warn("GBAY", "weapon_purchase_empty_grant",
                    new Dictionary<string, object> { { "weapon", weaponName } });
                return;
            }
            int chargedQuantity = quote.QuantityPriced
                ? Math.Min(quote.Quantity, actualAmmo) : 1;
            int totalPrice = WeaponPurchasePolicy.PriceActualQuantity(
                quote, chargedQuantity, _freeMode);

            if (!_freeMode && totalPrice > 0)
                Game.Player.Money -= totalPrice;

            string displayName = WeaponList.DisplayNames.ContainsKey(weaponName)
                ? WeaponList.DisplayNames[weaponName] : weaponName;
            string quantityText = quote.QuantityPriced
                ? $" ({chargedQuantity} x ${quote.UnitPrice:N0})" : "";
            string msg = _freeMode || totalPrice <= 0
                ? $"~g~{displayName}~w~ added."
                : $"~g~{displayName}~w~ purchased{quantityText} for "
                    + $"~g~${totalPrice:N0}~w~.";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"GiveWeapon: {weaponName}, unit=${quote.UnitPrice}, "
                + $"quantity={chargedQuantity}, total=${totalPrice}");
            CharacterInventory.RecordOwned(weaponName, false);
            GbayPreferences.RecordWeapon(weaponName);
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
            bool capacityResolved = Function.Call<bool>(
                Hash.GET_MAX_AMMO, player, weaponHash, maxAmmoOut);
            int maxAmmo = maxAmmoOut.GetResult<int>();
            AmmoCapacityResult capacity = AmmoRefillPolicy.Evaluate(
                capacityResolved, currentAmmo, maxAmmo);

            if (capacity.Status == AmmoCapacityStatus.Unavailable)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Ammo capacity is unavailable for this weapon.", 3000);
                ClientLog.Warn("GBAY", "ammo_capacity_unavailable",
                    new Dictionary<string, object> { { "weapon", weaponName } });
                return AmmoCapacityUnavailable;
            }
            if (capacity.Status == AmmoCapacityStatus.NotApplicable)
            {
                GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                return AmmoNotApplicable;
            }
            if (capacity.Status == AmmoCapacityStatus.FullyStocked)
            {
                GTA.UI.Screen.ShowSubtitle("~g~Already fully stocked.", 3000);
                return AmmoNotApplicable;
            }
            int needed = capacity.RoundsNeeded;

            int costPerRound = GetAmmoUnitPrice(weaponName);
            int totalCost = needed * costPerRound;

            if (_freeMode)
                totalCost = 0;

            if (!_freeMode && totalCost > 0 && Game.Player.Money < totalCost)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds for ammo.", 3000);
                return -2;
            }

            Function.Call(Hash.SET_PED_AMMO, player, weaponHash, maxAmmo);
            CharacterInventory.RecordWeaponAmmo(weaponName, maxAmmo);

            if (!_freeMode && totalCost > 0)
                Game.Player.Money -= totalCost;

            string displayName = WeaponList.DisplayNames.ContainsKey(weaponName)
                ? WeaponList.DisplayNames[weaponName] : weaponName;
            string msg = totalCost > 0
                ? $"~g~{displayName}~w~ ammo refilled ({needed} rounds) for ~g~${totalCost:N0}~w~."
                : $"~g~{displayName}~w~ ammo refilled ({needed} rounds).";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"RefillAmmo: {weaponName}, {needed} rounds, cost=${totalCost}");
            return totalCost;
        }

        // ------------------------------------------------------------------ //
        //  Gear Purchase (called by GbayBrowser)                              //
        // ------------------------------------------------------------------ //

        internal bool IsGearOwned(string gearId)
        {
            if (string.IsNullOrWhiteSpace(gearId)) return false;
            if (CharacterInventory.IsOwned(gearId, true)) return true;
            if (gearId == GearList.ARMOR_JUGGERNAUT) return JuggernautActive;
            if (gearId == "WEAPON_NIGHTVISION") return NightVisionOwned;
            if (GearList.IsArmor(gearId)) return false;

            Ped player = Game.Player.Character;
            Hash itemHash = (Hash)Game.GenerateHash(gearId);
            return Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                player.Handle, itemHash, false);
        }

        internal void ExecuteDeliverToGarmentGarage(string model, int price)
        {
            if (VehicleList.GetSizeTier(model) == 2)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~That vehicle is too large for the Garment Factory garage.", 3000);
                return;
            }
            int used = GarageManager.GetGarmentGarageUsedSlots();
            int cap = GarageManager.GetGarmentGarageCapacity();
            if (used >= cap)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The Garment Factory garage is full.~w~ ({used}/{cap} spaces used)",
                    3000);
                return;
            }
            var rng = new Random();
            try
            {
                bool success = GarageManager.DeliverToGarmentGarage(
                    model, rng.Next(0, 160), rng.Next(0, 160));
                if (!success)
                {
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~Delivery to the Garment Factory failed.", 3000);
                    return;
                }
                if (!_freeMode && price > 0) Game.Player.Money -= price;
                string name = VehicleList.DisplayNames.TryGetValue(
                    model, out string displayName) ? displayName : model;
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? $"~g~{name}~w~ delivered to the Garment Factory."
                        : $"~g~{name}~w~ delivered to the Garment Factory for ~g~${price:N0}~w~.",
                    3000);
                Log($"DeliverToGarmentGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToGarmentGarage", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Delivery to the Garment Factory failed.", 3000);
            }
        }

        internal bool IsGearEquipped(string gearId)
        {
            return !string.IsNullOrWhiteSpace(gearId) &&
                CharacterInventory.IsGearEquipped(gearId);
        }

        internal void ExecuteGiveGear(string gearId, int price)
        {
            Ped player = Game.Player.Character;

            // Ownership is enforced at execution time as well as in the UI so
            // a double click can never result in two deductions.
            if (IsGearOwned(gearId))
            {
                GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                Log($"GiveGear: duplicate purchase blocked for {gearId}");
                return;
            }

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
                        ? "~g~Juggernaut Armor~w~ equipped. Heavy movement is active."
                        : $"~g~Juggernaut Armor~w~ purchased for ~g~${price:N0}~w~. Heavy movement is active.",
                    4000);
                Log($"GiveGear: {gearId}, price=${price}");
                CharacterInventory.RecordOwned(gearId, true);
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
                        ? "~g~Night Vision~w~ acquired. Press ~y~N~w~ to toggle it."
                        : $"~g~Night Vision~w~ purchased for ~g~${price:N0}~w~. Press ~y~N~w~ to toggle it.",
                    4000);
                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;
                Log($"GiveGear: {gearId}, price=${price}");
                CharacterInventory.RecordOwned(gearId, true);
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
                ? $"~g~{displayName}~w~ acquired."
                : $"~g~{displayName}~w~ purchased for ~g~${price:N0}~w~.";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"GiveGear: {gearId}, price=${price}");
            CharacterInventory.RecordOwned(gearId, true);
        }

        internal void ExecuteEquipGear(string gearId)
        {
            if (!IsGearOwned(gearId))
            {
                GTA.UI.Screen.ShowSubtitle("~r~Purchase this item before equipping it.", 3000);
                return;
            }
            if (IsGearEquipped(gearId))
            {
                GTA.UI.Screen.ShowSubtitle("~g~Already equipped.", 2500);
                return;
            }

            Ped player = Game.Player.Character;
            if (gearId == GearList.ARMOR_JUGGERNAUT)
                ApplyJuggernaut(player);
            else if (GearList.IsArmor(gearId))
            {
                if (JuggernautActive) RemoveJuggernaut(player);
                player.Armor = GearList.ArmorValues[gearId];
            }
            else if (gearId == "WEAPON_NIGHTVISION")
                NightVisionOwned = true;
            else
                player.Weapons.Give(
                    (WeaponHash)Game.GenerateHash(gearId), 1, false, true);

            CharacterInventory.SetGearEquipped(gearId, true);
            string displayName = GearList.DisplayNames.TryGetValue(
                gearId, out string name) ? name : gearId;
            GTA.UI.Screen.ShowSubtitle($"~g~{displayName}~w~ equipped.", 3000);
            Log($"EquipGear: {gearId}");
        }

        internal void ExecuteUnequipGear(string gearId)
        {
            if (!CharacterInventory.IsGearEquipped(gearId))
            {
                GTA.UI.Screen.ShowSubtitle("~y~That item is not equipped.", 2500);
                return;
            }

            Ped player = Game.Player.Character;
            if (GearList.IsArmor(gearId))
                ExecuteRemoveArmor(gearId);
            else if (gearId == "WEAPON_NIGHTVISION")
                ExecuteRemoveNightVision();
            else
            {
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED,
                    player.Handle, Game.GenerateHash(gearId));
                Log($"UnequipGear: {gearId}");
            }
            CharacterInventory.RemoveOwnedGear(gearId);
            string removedName = GearList.DisplayNames.TryGetValue(
                gearId, out string removedDisplay) ? removedDisplay : gearId;
            GTA.UI.Screen.ShowSubtitle(
                $"~y~{removedName}~w~ removed. Repurchase it to equip it again.",
                3500);
            Log($"UnequipGear: ownership removed for {gearId}");
        }

        // ------------------------------------------------------------------ //
        //  Vehicle Sell (called by GbayBrowser garage tab)                     //
        // ------------------------------------------------------------------ //

        internal bool CanSellVehicle(
            string model, string plateText = null, int modelHash = 0)
        {
            if (string.IsNullOrWhiteSpace(model)) return false;
            if (GarageManager.IsProtectedStoryVehicle(
                    model, plateText, modelHash)) return false;
            int resolvedHash = modelHash != 0 ? modelHash : Game.GenerateHash(model);
            return Function.Call<bool>(Hash.IS_MODEL_A_VEHICLE, resolvedHash);
        }

        private static int GetFallbackVehicleValue(int vehicleClass)
        {
            // Conservative base values for valid vehicles whose model value is
            // unavailable in this GTA build. Indexes match GTA vehicle classes.
            int[] values = {
                20000, 25000, 35000, 30000, 30000, 40000, 60000, 100000,
                15000, 35000, 40000, 25000, 25000, 1000, 60000, 100000,
                150000, 25000, 40000, 120000, 60000, 25000
            };
            return vehicleClass >= 0 && vehicleClass < values.Length
                ? values[vehicleClass] : 25000;
        }

        /// <summary>
        /// Get the sell price for a vehicle (60% of catalog/native value).
        /// Stored base-game vehicles are sellable even when GBAY does not list them.
        /// </summary>
        internal int GetSellPrice(
            string model, string plateText = null, int modelHash = 0)
        {
            if (_freeMode) return 0;
            if (!CanSellVehicle(model, plateText, modelHash)) return 0;

            int buyPrice;
            if (!VehicleList.Prices.TryGetValue(model, out buyPrice))
            {
                int resolvedHash = modelHash != 0 ? modelHash : Game.GenerateHash(model);
                buyPrice = Function.Call<int>(Hash.GET_VEHICLE_MODEL_VALUE, resolvedHash);
                if (buyPrice <= 0)
                {
                    int vehicleClass = Function.Call<int>(
                        Hash.GET_VEHICLE_CLASS_FROM_NAME, resolvedHash);
                    buyPrice = GetFallbackVehicleValue(vehicleClass);
                }
            }
            return (int)(buyPrice * 0.6);
        }

        internal void ExecuteSellVehicle(string model, int listIndex,
            int garageLocation = 0, string plateText = null, int modelHash = 0)
        {
            if (GarageManager.IsProtectedStoryVehicle(
                    model, plateText, modelHash))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Story-owned personal vehicles cannot be sold.", 3500);
                ClientLog.Warn("GBAY", "vehicle_sale_rejected",
                    new Dictionary<string, object> {
                        { "model", model }, { "reason", "protected_story_vehicle" }
                    });
                return;
            }

            int sellPrice = GetSellPrice(model, plateText, modelHash);

            bool removed = garageLocation == 1
                ? GarageManager.RemoveFloorGarageVehicle(listIndex)
                : garageLocation == 2
                    ? GarageManager.RemoveDavisGarageVehicle(listIndex)
                    : garageLocation == 3
                        ? GarageManager.RemoveGarmentGarageVehicle(listIndex)
                    : GarageManager.RemoveVehicle(listIndex);
            string garageName = garageLocation == 1 ? "three_floor"
                : garageLocation == 2 ? "davis"
                : garageLocation == 3 ? "garment_factory" : "eclipse";
            if (!removed)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Sale failed; your garage and money were not changed.", 3500);
                ClientLog.Warn("GBAY", "vehicle_sale_failed", new Dictionary<string, object> {
                    { "model", model }, { "list_index", listIndex },
                    { "garage", garageName }
                });
                return;
            }

            if (!_freeMode && sellPrice > 0)
                Game.Player.Money += sellPrice;

            string displayName = VehicleList.DisplayNames.ContainsKey(model)
                ? VehicleList.DisplayNames[model] : model;
            string msg = _freeMode || sellPrice <= 0
                ? $"~y~{displayName}~w~ removed from the garage."
                : $"~g~{displayName}~w~ sold for ~g~${sellPrice:N0}";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"SellVehicle: {model}, sellPrice=${sellPrice}, garage={garageName}");
        }

        // ------------------------------------------------------------------ //
        //  Detail Cars (clean all garage vehicles)                            //
        // ------------------------------------------------------------------ //

        private const int DETAIL_COST = 500;

        internal int GetDetailCost()
        {
            if (_freeMode) return 0;
            return DETAIL_COST;
        }

        internal bool ExecuteDetailCars()
        {
            int cost = GetDetailCost();

            if (!_freeMode && cost > 0 && Game.Player.Money < cost)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Not enough money.~w~ Detailing costs ~g~${cost:N0}~w~.", 3000);
                return false;
            }

            GarageManager.DetailVehicles();

            if (!_freeMode && cost > 0)
                Game.Player.Money -= cost;

            string msg = _freeMode || cost <= 0
                ? "All vehicles have been ~b~detailed~w~."
                : $"All vehicles were ~b~detailed~w~ for ~g~${cost:N0}~w~.";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);
            Log($"DetailCars: cost=${cost}");
            return true;
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
            bool capacityResolved = Function.Call<bool>(
                Hash.GET_MAX_AMMO, player, weaponHash, maxAmmoOut);
            int maxAmmo = maxAmmoOut.GetResult<int>();
            AmmoCapacityResult capacity = AmmoRefillPolicy.Evaluate(
                capacityResolved, currentAmmo, maxAmmo);
            if (capacity.Status == AmmoCapacityStatus.Unavailable)
                return AmmoCapacityUnavailable;
            if (capacity.Status == AmmoCapacityStatus.NotApplicable)
                return AmmoNotApplicable;
            if (capacity.Status == AmmoCapacityStatus.FullyStocked)
                return 0;
            roundsNeeded = capacity.RoundsNeeded;

            int costPerRound = GetAmmoUnitPrice(weaponName);

            return _freeMode ? 0 : roundsNeeded * costPerRound;
        }

        private static int GetAmmoUnitPrice(string weaponName)
        {
            int fallback = WeaponList.AmmoCostPerRound.ContainsKey(weaponName)
                ? WeaponList.AmmoCostPerRound[weaponName] : 2;
            int catalogPrice = WeaponList.Prices.ContainsKey(weaponName)
                ? WeaponList.Prices[weaponName] : fallback;
            string category = WeaponList.CategoryNames.ContainsKey(weaponName)
                ? WeaponList.CategoryNames[weaponName] : "";
            return WeaponPurchasePolicy.RefillUnitPrice(
                category, catalogPrice, fallback);
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
                Log("RemoveArmor: juggernaut removed");
            }
            else
            {
                player.Armor = 0;
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

        internal static void ApplyJuggernaut(Ped player)
        {
            if (!TryGetCurrentCharacter(out PedHash ch))
            {
                ClientLog.Warn("GBAY", "juggernaut_rejected_for_unsupported_player_model");
                return;
            }

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
            ClientLog.Info("GBAY", "Juggernaut armor applied");
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

        internal static void ApplyBallisticOutfit(Ped player, PedHash ch)
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
            else if (ch == PedHash.Franklin)
            {
                // Franklin — no juggernaut torso or helmet in his model.
                // Slots 3 (torso) and prop 0 (helmet) left unchanged.
                SafeSetComponent(player, 4,  4, 0); // legs — confirmed D4/T0
                SafeSetComponent(player, 5,  4, 0); // hands — confirmed D4/T0
                SafeSetComponent(player, 9,  3, 0); // body armor — confirmed D3/T0
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
            Ped player = Game.Player.Character;
            if (player != null && TryResolveProtagonist(player.Model.Hash, out PedHash character))
                return character;
            return (PedHash)0;
        }

        internal static bool TryGetCurrentCharacter(out PedHash character)
        {
            Ped player = Game.Player.Character;
            if (player != null)
                return TryResolveProtagonist(player.Model.Hash, out character);
            character = (PedHash)0;
            return false;
        }

        internal static bool TryResolveProtagonist(int modelHash, out PedHash character)
        {
            if (modelHash == unchecked((int)PedHash.Michael))
                character = PedHash.Michael;
            else if (modelHash == unchecked((int)PedHash.Franklin))
                character = PedHash.Franklin;
            else if (modelHash == unchecked((int)PedHash.Trevor))
                character = PedHash.Trevor;
            else
            {
                character = (PedHash)0;
                return false;
            }
            return true;
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

                bool supportedCharacter = TryGetCurrentCharacter(out _);
                if (!supportedCharacter && _browser != null && _browser.IsOpen)
                {
                    _browser.Close();
                    ClientLog.Warn("GBAY", "browser_closed_for_unsupported_player_model");
                }

                if (_initialized)
                {
                    // A crash-recovery session suppresses the multi-floor
                    // garage for its first 30 seconds. Initialize it as soon
                    // as that temporary window closes; otherwise its map
                    // blips and world markers remain absent for the session.
                    if (!GarageManager.IsFloorGarageInitialized &&
                        !ClientWatchdog.SafeMode)
                    {
                        GarageManager.InitializeFloorGarage();
                        Log("Floor garage initialized after safe-mode recovery");
                    }
                    if (supportedCharacter || GarageManager.IsPlayerInGarage ||
                        GarageManager.IsPlayerInFloorGarage ||
                        GarageManager.IsPlayerInDavisGarage ||
                        GarageManager.IsPlayerInGarmentGarage)
                    {
                        GarageManager.OnTick();
                        GarageManager.OnFloorGarageTick();
                        GarageManager.OnDavisGarageTick();
                        GarageManager.OnGarmentGarageTick();
                    }
                }

                if (supportedCharacter && _browser != null)
                    _browser.Draw();

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
                    if (!TryGetCurrentCharacter(out _))
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            "~y~GBAY is available to Michael, Franklin, and Trevor.", 2500);
                        ClientLog.Warn("GBAY", "unsupported_player_model");
                        return;
                    }
                    if (GarageManager.IsTransitionInProgress)
                    {
                        GTA.UI.Screen.ShowSubtitle("~y~A garage transition is already in progress.", 1500);
                        return;
                    }

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
