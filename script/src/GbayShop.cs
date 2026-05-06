// GbayShop.cs -- In-game vehicle purchase menu (GBAY).
//
// Press the configured key (default F9) to open the GBAY shop.
// Browse vehicles by class, see prices, and purchase with story mode money.
// Uses LemonUI for native Rockstar-style menus.

using System;
using System.Collections.Generic;
using System.IO;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;
using LemonUI;
using LemonUI.Menus;

namespace ALLIN1
{
    public class GbayShop : Script
    {
        // Category definitions: TOML class name -> display label + VehicleList array
        private static readonly (string key, string label, string[] models)[] CATEGORIES =
        {
            ("compacts",       "Compacts",        VehicleList.Compacts),
            ("coupes",         "Coupes",          VehicleList.Coupes),
            ("sedans",         "Sedans",          VehicleList.Sedans),
            ("suvs",           "SUVs",            VehicleList.Suvs),
            ("muscle",         "Muscle",          VehicleList.Muscle),
            ("sportsclassics", "Sports Classics", VehicleList.Sportsclassics),
            ("super",          "Super",           VehicleList.Super),
            ("offroad",        "Off-Road",        VehicleList.Offroad),
            ("motorcycles",    "Motorcycles",     VehicleList.Motorcycles),
            ("vans",           "Vans",            VehicleList.Vans),
            ("boats",          "Boats",           VehicleList.Boats),
            ("helicopters",    "Helicopters",     VehicleList.Helicopters),
            ("planes",         "Planes",          VehicleList.Planes),
            ("military",       "Military",        VehicleList.Military),
            ("industrial",     "Industrial",      VehicleList.Industrial),
            ("openwheel",      "Open Wheel",      VehicleList.Openwheel),
            ("emergency",      "Emergency",       VehicleList.Emergency),
            ("cycles",         "Cycles",          VehicleList.Cycles),
            ("service",        "Service",         VehicleList.Service),
            ("special",        "Special",         VehicleList.Special),
        };

        // --- Config ---
        private static readonly string SCRIPTS_DIR = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "scripts");
        private static readonly string CONFIG_PATH = Path.Combine(SCRIPTS_DIR, "ALLIN1.toml");

        private Keys _openKey = Keys.F9;
        private bool _freeMode;

        // --- LemonUI ---
        private ObjectPool _pool;
        private NativeMenu _mainMenu;
        private bool _built;

        public GbayShop()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        // ------------------------------------------------------------------ //
        //  Config                                                             //
        // ------------------------------------------------------------------ //

        private void LoadConfig()
        {
            _openKey = Keys.F9;
            _freeMode = false;

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
                        // Strip quotes if present
                        string cleaned = val.Trim('"', '\'');
                        if (Enum.TryParse(cleaned, true, out Keys parsed))
                            _openKey = parsed;
                    }
                    else if (key == "gbay_free_mode")
                    {
                        _freeMode = valLower == "true";
                    }
                }
            }
            catch { }
        }

        // ------------------------------------------------------------------ //
        //  Menu building                                                      //
        // ------------------------------------------------------------------ //

        private void BuildMenus()
        {
            LoadConfig();

            _pool = new ObjectPool();
            _mainMenu = new NativeMenu("GBAY", "Vehicle Shop");
            _pool.Add(_mainMenu);

            foreach (var cat in CATEGORIES)
            {
                if (cat.models.Length == 0)
                    continue;

                var subMenu = new NativeMenu(cat.label, "Select a vehicle");
                _pool.Add(subMenu);

                foreach (string model in cat.models)
                {
                    string displayName = VehicleList.DisplayNames.ContainsKey(model)
                        ? VehicleList.DisplayNames[model]
                        : model;

                    int price = 0;
                    if (!_freeMode && VehicleList.Prices.ContainsKey(model))
                        price = VehicleList.Prices[model];

                    string priceText = _freeMode || price == 0
                        ? "FREE"
                        : $"${price:N0}";

                    var item = new NativeItem(displayName, $"Purchase this vehicle for {priceText}")
                    {
                        AltTitle = priceText,
                    };

                    string capturedModel = model;
                    int capturedPrice = price;
                    item.Activated += (sender, e) =>
                        PurchaseVehicle(capturedModel, capturedPrice, subMenu);

                    subMenu.Add(item);
                }

                var submenuItem = new NativeSubmenuItem(_mainMenu, subMenu,
                    $"{cat.label} ({cat.models.Length})");
                submenuItem.AltTitle = $"{cat.models.Length}";
            }

            _built = true;
        }

        // ------------------------------------------------------------------ //
        //  Purchase logic                                                     //
        // ------------------------------------------------------------------ //

        private void PurchaseVehicle(string modelName, int price, NativeMenu menu)
        {
            Ped player = Game.Player.Character;
            int money = Game.Player.Money;

            // Check funds
            if (!_freeMode && price > 0 && money < price)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Insufficient funds.~w~ You need ~g~${price:N0}~w~ (have ${money:N0})",
                    3000);
                return;
            }

            // Find a spawn position in front of the player
            Vector3 pos = player.Position + player.ForwardVector * 5f;
            float heading = player.Heading + 90f;

            Vehicle veh = VehicleHelper.CreateVehicle(modelName, pos, heading);
            if (veh == null)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Failed to create vehicle.", 3000);
                return;
            }

            // Deduct money
            if (!_freeMode && price > 0)
                Game.Player.Money -= price;

            // Set as player's last vehicle so it persists
            veh.IsPersistent = true;

            string name = VehicleList.DisplayNames.ContainsKey(modelName)
                ? VehicleList.DisplayNames[modelName]
                : modelName;

            string msg = _freeMode || price == 0
                ? $"~g~{name}~w~ delivered!"
                : $"~g~{name}~w~ purchased for ~g~${price:N0}";

            GTA.UI.Screen.ShowSubtitle(msg, 3000);
        }

        // ------------------------------------------------------------------ //
        //  Events                                                             //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            if (_pool != null)
                _pool.Process();
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (Game.IsLoading)
                return;

            if (e.KeyCode == _openKey)
            {
                if (!_built)
                    BuildMenus();

                _mainMenu.Visible = !_mainMenu.Visible;
            }
        }
    }
}
