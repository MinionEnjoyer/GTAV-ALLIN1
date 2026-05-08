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

        internal void ExecuteDeliverToSafehouse(string model, int price,
                                                 string safehouseId, string safehouseName)
        {
            int used = GarageManager.GetUsedSlots(safehouseId);
            int cap = GarageManager.GetCapacity(safehouseId);

            if (used >= cap)
            {
                Log($"DeliverToSafehouse: {safehouseName} full ({used}/{cap})");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~No room at {safehouseName}.~w~ ({used}/{cap} slots used)", 3000);
                return;
            }

            var rng = new Random();
            int c1 = rng.Next(0, 160);
            int c2 = rng.Next(0, 160);

            try
            {
                bool success = GarageManager.DeliverVehicle(safehouseId, model, c1, c2);
                if (!success)
                {
                    Log($"DeliverToSafehouse: failed for {model} -> {safehouseId}");
                    GTA.UI.Screen.ShowSubtitle(
                        $"~r~Delivery to {safehouseName} failed.", 3000);
                    return;
                }

                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;

                string name = VehicleList.DisplayNames.ContainsKey(model)
                    ? VehicleList.DisplayNames[model] : model;
                string msg = _freeMode || price <= 0
                    ? $"~g~{name}~w~ delivered to ~b~{safehouseName}"
                    : $"~g~{name}~w~ delivered to ~b~{safehouseName}~w~ for ~g~${price:N0}";
                GTA.UI.Screen.ShowSubtitle(msg, 3000);

                Log($"DeliverToSafehouse: {model} -> {safehouseId}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToSafehouse", ex);
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Delivery to {safehouseName} failed.", 3000);
            }
        }

        // ------------------------------------------------------------------ //
        //  Weapon Purchase (called by GbayBrowser)                            //
        // ------------------------------------------------------------------ //

        internal void ExecuteGiveWeapon(string weaponName, int price)
        {
            Ped player = Game.Player.Character;
            Hash weaponHash = (Hash)Game.GenerateHash(weaponName);

            // Check if already owned
            bool hasWeapon = Function.Call<bool>(
                (Hash)0x8DECB02F88F428BC, player, weaponHash, false);  // HAS_PED_GOT_WEAPON

            if (hasWeapon)
            {
                // Give max ammo instead
                Function.Call((Hash)0x14E56BC5B5DB6A19,
                    player, weaponHash, 9999, false);  // SET_PED_AMMO
                string name = WeaponList.DisplayNames.ContainsKey(weaponName)
                    ? WeaponList.DisplayNames[weaponName] : weaponName;
                GTA.UI.Screen.ShowSubtitle($"~g~{name}~w~ ammo refilled!", 3000);
                Log($"GiveWeapon: {weaponName} already owned, refilled ammo");
                return;
            }

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
