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
        private static readonly string LOG_PATH = Path.Combine(SCRIPTS_DIR, "ALLIN1_gbay.log");

        private Keys _openKey = Keys.F9;
        private bool _freeMode;
        private bool _garageDebug;
        private bool _enableLogging = true;
        private bool _initialized;

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

        // ------------------------------------------------------------------ //
        //  Initialization                                                     //
        // ------------------------------------------------------------------ //

        private void Initialize()
        {
            LoadConfig();
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
            Function.Call((Hash)0xBF0FD6E56C964FCB,
                player, weaponHash, 9999, false, true);  // GIVE_WEAPON_TO_PED

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
                (Hash)0x015A522136D7F951, player, weaponHash);  // GET_AMMO_IN_PED_WEAPON

            OutputArgument maxAmmoOut = new OutputArgument();
            Function.Call<bool>(
                (Hash)0xDC16122C7A20C933, player, weaponHash, maxAmmoOut);  // GET_MAX_AMMO
            int maxAmmo = maxAmmoOut.GetResult<int>();

            if (maxAmmo <= 0)
            {
                // Melee or no-ammo weapon
                GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                return -1;
            }

            int needed = maxAmmo - currentAmmo;
            if (needed <= 0)
            {
                GTA.UI.Screen.ShowSubtitle("~g~Already fully stocked!", 3000);
                return -1;
            }

            // Calculate cost
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

            // Refill
            Function.Call((Hash)0x14E56BC5B5DB6A19,
                player, weaponHash, maxAmmo, false);  // SET_PED_AMMO

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

            if (gearId == GearList.ARMOR_ID)
            {
                // Set armor to 100
                Function.Call((Hash)0xCEA04D83135264CC, player, 100);  // SET_PED_ARMOUR
            }
            else
            {
                // Give as weapon/gadget
                Hash itemHash = (Hash)Game.GenerateHash(gearId);
                Function.Call((Hash)0xBF0FD6E56C964FCB,
                    player, itemHash, 1, false, true);  // GIVE_WEAPON_TO_PED
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
                (Hash)0x015A522136D7F951, player, weaponHash);  // GET_AMMO_IN_PED_WEAPON

            OutputArgument maxAmmoOut = new OutputArgument();
            Function.Call<bool>(
                (Hash)0xDC16122C7A20C933, player, weaponHash, maxAmmoOut);  // GET_MAX_AMMO
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
                if (_initialized)
                    GarageManager.OnTick();

                if (_browser != null)
                    _browser.Draw();

                if (_garageDebug && _initialized)
                    GarageManager.DrawDebugMarkers();
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
        }
    }
}
