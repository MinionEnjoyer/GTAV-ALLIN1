// GbayShop.cs -- In-game vehicle purchase menu (GBAY).
//
// Press the configured key (default F9) to open the GBAY shop.
// Browse vehicles by class, see prices, and purchase with story mode money.
// Vehicles can be delivered to the player's location or to a safehouse garage.
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
        private struct Category
        {
            internal string Key;
            internal string Label;
            internal string[] Models;

            internal Category(string key, string label, string[] models)
            {
                Key = key;
                Label = label;
                Models = models;
            }
        }

        // Category definitions: TOML class name -> display label + VehicleList array
        private static readonly Category[] CATEGORIES =
        {
            new Category("compacts",       "Compacts",        VehicleList.Compacts),
            new Category("coupes",         "Coupes",          VehicleList.Coupes),
            new Category("sedans",         "Sedans",          VehicleList.Sedans),
            new Category("suvs",           "SUVs",            VehicleList.Suvs),
            new Category("muscle",         "Muscle",          VehicleList.Muscle),
            new Category("sportsclassics", "Sports Classics", VehicleList.Sportsclassics),
            new Category("super",          "Super",           VehicleList.Super),
            new Category("offroad",        "Off-Road",        VehicleList.Offroad),
            new Category("motorcycles",    "Motorcycles",     VehicleList.Motorcycles),
            new Category("vans",           "Vans",            VehicleList.Vans),
            new Category("boats",          "Boats",           VehicleList.Boats),
            new Category("helicopters",    "Helicopters",     VehicleList.Helicopters),
            new Category("planes",         "Planes",          VehicleList.Planes),
            new Category("military",       "Military",        VehicleList.Military),
            new Category("industrial",     "Industrial",      VehicleList.Industrial),
            new Category("openwheel",      "Open Wheel",      VehicleList.Openwheel),
            new Category("emergency",      "Emergency",       VehicleList.Emergency),
            new Category("cycles",         "Cycles",          VehicleList.Cycles),
            new Category("service",        "Service",         VehicleList.Service),
            new Category("special",        "Special",         VehicleList.Special),
        };

        // --- Config ---
        private static readonly string SCRIPTS_DIR = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "scripts");
        private static readonly string CONFIG_PATH = Path.Combine(SCRIPTS_DIR, "ALLIN1.toml");
        private static readonly string LOG_PATH = Path.Combine(SCRIPTS_DIR, "ALLIN1_gbay.log");

        private Keys _openKey = Keys.F9;
        private bool _freeMode;
        private int _garageCapacity = 4;
        private bool _garageDebug;
        private bool _enableLogging;

        // --- LemonUI ---
        private ObjectPool _pool;
        private NativeMenu _mainMenu;
        private NativeMenu _deliveryMenu;
        private NativeMenu _garagesMenu;
        private bool _built;
        private bool _garageInitialized;

        // --- Pending purchase (set when vehicle item activated, consumed by delivery menu) ---
        private string _pendingModel;
        private int _pendingPrice;

        public GbayShop()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        // ------------------------------------------------------------------ //
        //  Logging                                                            //
        // ------------------------------------------------------------------ //

        private void Log(string msg)
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

        private void LogException(string context, Exception ex)
        {
            if (!_enableLogging)
                return;
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
            _garageCapacity = 4;
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
                    else if (key == "garage_capacity")
                    {
                        if (int.TryParse(val.Trim('"', '\''), out int cap))
                            _garageCapacity = cap;
                    }
                    else if (key == "garage_debug")
                    {
                        _garageDebug = valLower == "true";
                    }
                    else if (key == "enable_logging")
                    {
                        _enableLogging = valLower == "true";
                    }
                }
            }
            catch (Exception ex)
            {
                LogException("LoadConfig", ex);
            }
        }

        // ------------------------------------------------------------------ //
        //  Menu building                                                      //
        // ------------------------------------------------------------------ //

        private void BuildMenus()
        {
            LoadConfig();
            Log($"=== GBAY Initialized: key={_openKey} freeMode={_freeMode} garageCapacity={_garageCapacity} garageDebug={_garageDebug} ===");

            try
            {
                GarageManager.Configure(_garageCapacity, _garageDebug, _enableLogging);
                GarageManager.Initialize();
                _garageInitialized = true;
                Log("GarageManager initialized");
            }
            catch (Exception ex)
            {
                LogException("GarageManager.Initialize", ex);
            }

            _pool = new ObjectPool();
            _mainMenu = new NativeMenu("GBAY", "Vehicle Shop");
            _pool.Add(_mainMenu);

            // --- Delivery submenu (reused for every vehicle purchase) ---
            _deliveryMenu = new NativeMenu("Delivery", "Choose delivery method");
            _pool.Add(_deliveryMenu);

            // --- Vehicle category submenus ---
            foreach (var cat in CATEGORIES)
            {
                if (cat.Models.Length == 0)
                    continue;

                var subMenu = new NativeMenu(cat.Label, "Select a vehicle");
                _pool.Add(subMenu);

                foreach (string model in cat.Models)
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
                        OnVehicleSelected(capturedModel, capturedPrice);

                    subMenu.Add(item);
                }

                var submenuItem = new NativeSubmenuItem(subMenu, _mainMenu,
                    $"{cat.Label} ({cat.Models.Length})");
                submenuItem.AltTitle = $"{cat.Models.Length}";
            }

            // --- My Garages submenu ---
            _garagesMenu = new NativeMenu("My Garages", "Manage stored vehicles");
            _pool.Add(_garagesMenu);
            _garagesMenu.Opening += (sender, e) => RebuildGaragesMenu();

            var garagesItem = new NativeSubmenuItem(_garagesMenu, _mainMenu, "My Garages");
            garagesItem.AltTitle = ">";

            _built = true;
            Log($"Menus built: {CATEGORIES.Length} categories");
        }

        // ------------------------------------------------------------------ //
        //  Vehicle selection -> delivery submenu                              //
        // ------------------------------------------------------------------ //

        private void OnVehicleSelected(string modelName, int price)
        {
            // Check funds before showing delivery options
            if (!_freeMode && price > 0 && Game.Player.Money < price)
            {
                Log($"Purchase rejected: {modelName} costs ${price}, player has ${Game.Player.Money}");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Insufficient funds.~w~ You need ~g~${price:N0}~w~ (have ${Game.Player.Money:N0})",
                    3000);
                return;
            }

            _pendingModel = modelName;
            _pendingPrice = price;

            try
            {
                RebuildDeliveryMenu();
                _deliveryMenu.Visible = true;
            }
            catch (Exception ex)
            {
                LogException("OnVehicleSelected.RebuildDeliveryMenu", ex);
            }
        }

        private void RebuildDeliveryMenu()
        {
            _deliveryMenu.Clear();

            string displayName = VehicleList.DisplayNames.ContainsKey(_pendingModel)
                ? VehicleList.DisplayNames[_pendingModel]
                : _pendingModel;

            _deliveryMenu.Description = displayName;

            // "Deliver Here" option
            var hereItem = new NativeItem("Deliver Here", "Spawn vehicle at your location")
            {
                AltTitle = "Instant",
            };
            hereItem.Activated += (sender, e) => DeliverHere();
            _deliveryMenu.Add(hereItem);

            // Character-specific safehouse options
            PedHash character = GetCurrentCharacter();
            var safehouses = GarageManager.GetSafehouses(character);

            foreach (var sh in safehouses)
            {
                int used = GarageManager.GetUsedSlots(sh.Id);
                int cap = GarageManager.GetCapacity();
                bool full = used >= cap;

                var shItem = new NativeItem(
                    sh.Name,
                    full ? "No room available" : "Deliver to this safehouse")
                {
                    AltTitle = $"{used}/{cap}",
                };

                if (full)
                    shItem.Colors.TitleNormal = System.Drawing.Color.Gray;

                string capturedId = sh.Id;
                string capturedName = sh.Name;
                shItem.Activated += (sender, e) =>
                    DeliverToSafehouse(capturedId, capturedName);

                _deliveryMenu.Add(shItem);
            }
        }

        // ------------------------------------------------------------------ //
        //  Delivery actions                                                   //
        // ------------------------------------------------------------------ //

        private void DeliverHere()
        {
            _deliveryMenu.Visible = false;

            Ped player = Game.Player.Character;
            Vector3 pos = player.Position + player.ForwardVector * 5f;
            float heading = player.Heading + 90f;

            try
            {
                Vehicle veh = VehicleHelper.CreateVehicle(_pendingModel, pos, heading);
                if (veh == null)
                {
                    Log($"DeliverHere: CreateVehicle returned null for {_pendingModel}");
                    GTA.UI.Screen.ShowSubtitle("~r~Failed to create vehicle.", 3000);
                    return;
                }

                DeductMoney();
                veh.IsPersistent = true;
                Log($"DeliverHere: {_pendingModel} spawned at player, price=${_pendingPrice}");
                ShowPurchaseMessage("delivered");
            }
            catch (Exception ex)
            {
                LogException("DeliverHere", ex);
                GTA.UI.Screen.ShowSubtitle("~r~Failed to create vehicle.", 3000);
            }
        }

        private void DeliverToSafehouse(string safehouseId, string safehouseName)
        {
            _deliveryMenu.Visible = false;

            int used = GarageManager.GetUsedSlots(safehouseId);
            int cap = GarageManager.GetCapacity();

            if (used >= cap)
            {
                Log($"DeliverToSafehouse: {safehouseName} full ({used}/{cap})");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~No room at {safehouseName}.~w~ ({used}/{cap} slots used)",
                    3000);
                return;
            }

            // Generate colors for the vehicle
            var rng = new Random();
            int c1 = rng.Next(0, 160);
            int c2 = rng.Next(0, 160);

            try
            {
                bool success = GarageManager.DeliverVehicle(
                    safehouseId, _pendingModel, c1, c2);

                if (!success)
                {
                    Log($"DeliverToSafehouse: GarageManager.DeliverVehicle failed for {_pendingModel} -> {safehouseId}");
                    GTA.UI.Screen.ShowSubtitle(
                        $"~r~Delivery to {safehouseName} failed.", 3000);
                    return;
                }

                DeductMoney();

                string name = VehicleList.DisplayNames.ContainsKey(_pendingModel)
                    ? VehicleList.DisplayNames[_pendingModel]
                    : _pendingModel;

                Log($"DeliverToSafehouse: {_pendingModel} -> {safehouseId}, price=${_pendingPrice}");

                string msg = _freeMode || _pendingPrice == 0
                    ? $"~g~{name}~w~ delivered to ~b~{safehouseName}"
                    : $"~g~{name}~w~ delivered to ~b~{safehouseName}~w~ for ~g~${_pendingPrice:N0}";

                GTA.UI.Screen.ShowSubtitle(msg, 3000);
            }
            catch (Exception ex)
            {
                LogException("DeliverToSafehouse", ex);
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Delivery to {safehouseName} failed.", 3000);
            }
        }

        private void DeductMoney()
        {
            if (!_freeMode && _pendingPrice > 0)
                Game.Player.Money -= _pendingPrice;
        }

        private void ShowPurchaseMessage(string action)
        {
            string name = VehicleList.DisplayNames.ContainsKey(_pendingModel)
                ? VehicleList.DisplayNames[_pendingModel]
                : _pendingModel;

            string msg = _freeMode || _pendingPrice == 0
                ? $"~g~{name}~w~ {action}!"
                : $"~g~{name}~w~ purchased for ~g~${_pendingPrice:N0}";

            GTA.UI.Screen.ShowSubtitle(msg, 3000);
        }

        // ------------------------------------------------------------------ //
        //  My Garages menu                                                    //
        // ------------------------------------------------------------------ //

        private void RebuildGaragesMenu()
        {
            try
            {
                _garagesMenu.Clear();

                PedHash character = GetCurrentCharacter();
                var safehouses = GarageManager.GetSafehouses(character);

                if (safehouses.Length == 0)
                {
                    _garagesMenu.Add(new NativeItem("No safehouses available"));
                    return;
                }

                foreach (var sh in safehouses)
                {
                    int used = GarageManager.GetUsedSlots(sh.Id);
                    int cap = GarageManager.GetCapacity();

                    var shMenu = new NativeMenu(sh.Name, "Stored vehicles");
                    _pool.Add(shMenu);

                    var vehicles = GarageManager.GetStoredVehicles(sh.Id);
                    if (vehicles.Count == 0)
                    {
                        shMenu.Add(new NativeItem("Empty"));
                    }
                    else
                    {
                        for (int i = 0; i < vehicles.Count; i++)
                        {
                            var sv = vehicles[i];
                            string displayName = VehicleList.DisplayNames.ContainsKey(sv.Model)
                                ? VehicleList.DisplayNames[sv.Model]
                                : sv.Model;

                            var removeItem = new NativeItem(displayName, "Remove this vehicle")
                            {
                                AltTitle = "Remove",
                            };
                            removeItem.Colors.TitleNormal = System.Drawing.Color.IndianRed;

                            string capturedId = sh.Id;
                            int capturedIndex = i;
                            removeItem.Activated += (sender, e) =>
                            {
                                GarageManager.RemoveVehicle(capturedId, capturedIndex);
                                Log($"RemoveVehicle: {sv.Model} removed from {sh.Id} slot {sv.Slot}");
                                GTA.UI.Screen.ShowSubtitle(
                                    $"~y~{displayName}~w~ removed from ~b~{sh.Name}", 3000);
                                // Close the menu since indices shifted
                                shMenu.Visible = false;
                            };

                            shMenu.Add(removeItem);
                        }
                    }

                    var shItem = new NativeSubmenuItem(shMenu, _garagesMenu,
                        $"{sh.Name} ({used}/{cap})");
                    shItem.AltTitle = $"{used}/{cap}";
                }
            }
            catch (Exception ex)
            {
                LogException("RebuildGaragesMenu", ex);
            }
        }

        // ------------------------------------------------------------------ //
        //  Helpers                                                            //
        // ------------------------------------------------------------------ //

        private static PedHash GetCurrentCharacter()
        {
            Model playerModel = Game.Player.Character.Model;

            if (playerModel == new Model(PedHash.Michael))
                return PedHash.Michael;
            if (playerModel == new Model(PedHash.Franklin))
                return PedHash.Franklin;
            if (playerModel == new Model(PedHash.Trevor))
                return PedHash.Trevor;

            // Fallback: show all safehouses
            return PedHash.Michael;
        }

        // ------------------------------------------------------------------ //
        //  Events                                                             //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            try
            {
                if (_pool != null)
                    _pool.Process();

                if (_garageDebug && _garageInitialized)
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
                    if (!_built)
                        BuildMenus();

                    _mainMenu.Visible = !_mainMenu.Visible;
                }
                catch (Exception ex)
                {
                    LogException("OnKeyDown.BuildMenus", ex);
                }
            }
        }
    }
}
