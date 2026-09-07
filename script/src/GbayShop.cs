// GbayShop.cs -- GBAY vehicle shop script entrypoint.
//
// Thin Script shell that handles config loading, key binding, and delegates
// UI presentation to Reactor V. Delivery/purchase execution stays here;
// the native workbench supplies the in-world camera/character preview only.

using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class GbayShop : Script
    {
        private const long ShutdownSlowThresholdMilliseconds = 50;
        private static GbayShop _current;

        internal static bool IsMenuActive =>
            _current != null &&
            ((_current._browser != null && _current._browser.IsOpen) ||
             (_current._menuBridge != null &&
              _current._menuBridge.IsMenuActive));

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
        private readonly bool _onlineContentEnabled;

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
        private GbayVehicleStorefront _vehicleStorefront;
        private IAllin1MenuBridge _menuBridge;
        private readonly GbayToggleInputGate _toggleInput =
            new GbayToggleInputGate();
        private readonly ReactorF9HandoffGate _f9Handoff =
            new ReactorF9HandoffGate();
        private readonly GbayStoryCharacterRefreshGate
            _storyCharacterRefresh = new GbayStoryCharacterRefreshGate();
        private readonly GbayGameStateSynchronizationGate
            _gameStateSynchronization =
                new GbayGameStateSynchronizationGate();
        private bool _handoffBlockedLogged;
        private long _lastHandoffSuppressionLoggedGeneration;
        private bool _gameStateSyncFailureLogged;

        // --- Public accessors for GbayBrowser ---
        internal bool FreeMode => _freeMode;
        internal bool OnlineContentEnabled => _onlineContentEnabled;
        internal const int AmmoNotApplicable = -1;
        internal const int AmmoCapacityUnavailable = -3;

        public GbayShop()
        {
            _current = this;
            _onlineContentEnabled = Allin1ExtensionApi.IsPackageEnabled(
                Allin1ExtensionApi.OnlineContentPackageId);
            Tick += OnTick;
            KeyDown += OnKeyDown;
            KeyUp += OnKeyUp;
            Aborted += OnAborted;
            Interval = 0;
        }

        private void OnAborted(object sender, EventArgs args)
        {
            TrailerHitchRuntime.Shutdown();
            DrivingRuntime.Shutdown();
            using (ClientLog.Time("GBAY", "shutdown_on_aborted",
                new Dictionary<string, object>
                {
                    { "browser_present", _browser != null },
                    { "reactor_bridge_present", _menuBridge != null },
                    { "online_content_enabled", _onlineContentEnabled },
                }, ShutdownSlowThresholdMilliseconds))
            {
                using (ClientLog.Time("GBAY", "shutdown_browser_close",
                    new Dictionary<string, object>
                    {
                        { "browser_present", _browser != null },
                    }, ShutdownSlowThresholdMilliseconds))
                {
                    _browser?.Close();
                }

                using (ClientLog.Time("GBAY",
                    "shutdown_reactor_bridge_dispose",
                    new Dictionary<string, object>
                    {
                        { "reactor_bridge_present", _menuBridge != null },
                    }, ShutdownSlowThresholdMilliseconds))
                {
                    try { _menuBridge?.Dispose(); }
                    catch (Exception ex)
                    {
                        LogException("ReactorBridge.Dispose", ex);
                    }
                    _menuBridge = null;
                }

                using (ClientLog.Time("GBAY",
                    "shutdown_f9_handoff_dispose", null,
                    ShutdownSlowThresholdMilliseconds))
                {
                    _f9Handoff.Dispose();
                }

                using (ClientLog.Time("GBAY", "shutdown_current_release",
                    null, ShutdownSlowThresholdMilliseconds))
                {
                    if (ReferenceEquals(_current, this)) _current = null;
                }

                if (_onlineContentEnabled)
                {
                    using (ClientLog.Time("GBAY",
                        "shutdown_garage_manager_abort", null,
                        ShutdownSlowThresholdMilliseconds))
                    {
                        GarageManager.OnScriptAborted();
                    }

                    using (ClientLog.Time("GBAY",
                        "shutdown_yacht_manager", null,
                        ShutdownSlowThresholdMilliseconds))
                    {
                        YachtManager.Shutdown();
                    }
                }
            }
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
                string configText;
                string[] configLines = EarlyStartupSnapshot.TryGetText(
                        "config", out configText)
                    ? SplitLines(configText)
                    : File.ReadAllLines(CONFIG_PATH);
                string currentSection = "";
                foreach (string rawLine in configLines)
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
                string pricesText;
                string[] priceLines = EarlyStartupSnapshot.TryGetText(
                        "gear-prices", out pricesText)
                    ? SplitLines(pricesText)
                    : File.ReadAllLines(GEAR_PRICES_PATH);
                int count = 0;
                foreach (string rawLine in priceLines)
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

        private static string[] SplitLines(string value)
        {
            return (value ?? "").Replace("\r\n", "\n")
                .Replace('\r', '\n').Split('\n');
        }

        // ------------------------------------------------------------------ //
        //  Initialization                                                     //
        // ------------------------------------------------------------------ //

        private void Initialize()
        {
            LoadConfig();
            ControllerBindings.Load(CONFIG_PATH);
            ClientLog.Configure(_enableLogging);
            ClientWatchdog.Configure(_safeMode);
            DrivingRuntime.Initialize(CONFIG_PATH, _safeMode);
            if (_onlineContentEnabled)
            {
                // Hash the stock Tuners archive away from the Davis entry/black
                // transition. Entry remains unavailable until this exact keyed
                // background attestation has completed successfully.
                DavisStockReferenceBridgePolicy
                    .WarmUpCurrentNativeMutationAuthorization();
                // A strict Grapeseed Phase-A install emits one deterministic
                // zero-native startup guard for promotion evidence. A strict
                // Phase-B install instead warms its multi-gigabyte mpheist
                // archive attestation away from the garage-entry transition.
                GrapeseedStockReferenceBridgePolicy
                    .ObserveStartupAuthorizationState();
                // Garment Factory uses its own scoped mp2024_02 bridge. Hash
                // the stock archive in the shared background queue so entry
                // never performs multi-gigabyte I/O on the game thread.
                GarmentStockReferenceBridgePolicy
                    .WarmUpCurrentNativeMutationAuthorization();
                OfficialInteriorStockBridgePolicy.Harmony
                    .WarmUpCurrentNativeMutationAuthorization();
                OfficialInteriorStockBridgePolicy.Paleto
                    .WarmUpCurrentNativeMutationAuthorization();
            }
            RuntimeVehicleCatalog.Refresh();
            RuntimeWeaponCatalog.Refresh();
            if (_onlineContentEnabled)
                LoadGearPrices();
            Log($"=== GBAY services initialized: backend=Reactor " +
                $"key={_openKey} " +
                $"freeMode={_freeMode} ===");

            if (_onlineContentEnabled)
            {
                YachtManager.Initialize();
                try
                {
                    GarageManager.Configure(
                        _enableLogging, _garagesAlwaysAccessible);
                    GarageManager.Initialize();
                    GarageManager.InitializeDavisGarage();
                    GarageManager.InitializeGarmentGarage();
                    GarageManager.InitializeRuralGarage();
                    GarageManager.InitializePaletoGarage();
                    GarageManager.InitializeHelipad();
                    GarageManager.InitializeHarbour();
                    GarageManager.InitializeYachtHelipad();
                    // Recovery mode may defer Harmony's interior/storage work,
                    // but its map locations should remain visible with every
                    // other ALLIN1 garage.
                    GarageManager.EnsureFloorGarageBlips();
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
            }

            TryInitializeReactorBridge(logUnavailable: false);
            _initialized = true;
        }

        private bool TryInitializeReactorBridge(bool logUnavailable)
        {
            if (_menuBridge != null)
                return true;
            if (_vehicleStorefront == null)
                _vehicleStorefront = new GbayVehicleStorefront(this);
            _menuBridge = GbayReactorBridgeLoader.TryLoad(
                _vehicleStorefront, out string status);
            if (_menuBridge != null)
            {
                Ped activePlayer = Game.Player.Character;
                if (_menuBridge is IAllin1StoryCharacterBridge &&
                    !Game.IsLoading &&
                    activePlayer != null && activePlayer.Exists() &&
                    !activePlayer.IsDead &&
                    TryResolveProtagonist(
                        activePlayer.Model.Hash, out PedHash character) &&
                    !GarageManager.IsTransitionInProgress)
                    _storyCharacterRefresh.Seed(
                        StoryCharacterId(character));
                ClientLog.Info("GBAY", "reactor_bridge_ready",
                    new Dictionary<string, object>
                    {
                        { "status", status ?? "ready" },
                    });
                return true;
            }
            if (logUnavailable)
                ClientLog.Warn("GBAY", "reactor_bridge_unavailable",
                    new Dictionary<string, object>
                    {
                        { "status", status ?? "unavailable" },
                    });
            return false;
        }

        private GbayBrowser EnsureBrowser()
        {
            if (_browser != null)
                return _browser;

            // Shared camera/dummy preview helpers are allocated only on demand.
            // This is not a fallback storefront: Reactor owns all menu entry.
            GbayBrowser.ReducedMotion = _reducedMotion;
            GbayRenderer.ColorblindMode = _colorblindMode;
            GbayRenderer.UiScale = _uiScale;
            _browser = new GbayBrowser(this);
            return _browser;
        }

        internal bool TryGetCachedWeaponCustomizationCatalog(
            string weapon,
            out IReadOnlyList<GbayBrowser.DetachedWorkbenchRow> rows)
        {
            if (_vehicleStorefront == null)
            {
                rows = Array.Empty<GbayBrowser.DetachedWorkbenchRow>();
                return false;
            }
            return _vehicleStorefront.TryGetCachedWeaponCustomizationCatalog(
                weapon, out rows);
        }

        internal bool TryOpenReactorWeaponWorkbench(
            string weaponName, string displayName)
        {
            // Retain the bridge method contract, but never open a native menu.
            return TryOpenReactorWeaponPreview(weaponName, displayName);
        }

        internal bool TryOpenReactorWeaponPreview(
            string weaponName, string displayName)
        {
            GbayBrowser browser = EnsureBrowser();
            if (browser.IsOpen || !browser.TryOpenReactorWeaponPreview(
                    weaponName, displayName))
                return false;
            ClientLog.Info("GBAY", "reactor_weapon_preview_opened",
                new Dictionary<string, object>
                {
                    { "weapon", weaponName ?? "" },
                    { "menu_owner", "reactor" },
                });
            return true;
        }

        internal bool TryPreviewReactorWeaponOption(
            string weaponName, string kind, int componentHash,
            int attachmentPoint, int tint)
        {
            return _browser != null &&
                _browser.TryPreviewReactorWeaponOption(
                    weaponName, kind, componentHash, attachmentPoint, tint);
        }

        internal void CloseReactorWeaponPreview()
        {
            if (_browser == null || !_browser.IsReactorWeaponPreviewOpen)
                return;
            _browser.CloseReactorWeaponPreview();
            ClientLog.Info("GBAY", "reactor_weapon_preview_closed");
        }

        private void OpenGarageWorldEntry(
            Allin1GarageWorldEntryLocation location)
        {
            if (TryInitializeReactorBridge(logUnavailable: true))
            {
                try
                {
                    if (_menuBridge.TryPresentGarage(
                            new Allin1GaragePresentationRequest
                            {
                                Location = location,
                            }))
                    {
                        ClientLog.Info("GBAY",
                            "reactor_world_entry_presented",
                            new Dictionary<string, object>
                            {
                                { "location", location.ToString() },
                            });
                        return;
                    }
                    ClientLog.Warn("GBAY",
                        "reactor_world_entry_not_ready",
                        new Dictionary<string, object>
                        {
                            { "location", location.ToString() },
                            { "status", _menuBridge.Status ?? "not ready" },
                        });
                }
                catch (Exception ex)
                {
                    LogException("ReactorBridge.WorldEntry", ex);
                }
            }

            ShowReactorUnavailable();
        }

        private static void ShowReactorUnavailable()
        {
            GTA.UI.Screen.ShowSubtitle(
                "~y~GBAY requires Reactor V. If loading does not finish, use ALLIN1 Launcher > Install / Repair.",
                5000);
        }

        // ------------------------------------------------------------------ //
        //  Delivery Execution (called by GbayBrowser)                         //
        // ------------------------------------------------------------------ //

        private bool RejectSpecializedVehicleFromGarage(
            string model, string garageName)
        {
            if (GarageVehicleTypePolicy.IsRegularGarageEligible(model))
                return false;
            GTA.UI.Screen.ShowSubtitle(
                "~r~Helicopters, planes, and boats require specialized ALLIN1 storage.",
                3500);
            Log($"Delivery rejected: {model} cannot use {garageName}");
            return true;
        }

        private bool RejectUnavailableMapDestination(
            int location, string destinationName)
        {
            if (OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                    location))
                return false;
            GTA.UI.Screen.ShowSubtitle(
                "~r~That destination is not recognized by this build.",
                4000);
            Log($"Delivery rejected: unknown destination {destinationName}");
            return true;
        }

        /// <summary>
        /// Re-authorize the listing and native model immediately before GBAY
        /// stores a vehicle or changes Story Mode money. This closes the stale
        /// menu window when a package is disabled or its asset stops streaming.
        /// </summary>
        internal bool ValidateVehiclePurchase(string model, int quotedPrice)
        {
            if (RuntimeVehicleCatalog.IsCatalogOnly(model))
            {
                GTA.UI.Screen.ShowSubtitle("~y~Catalog only — purchasing and delivery are not enabled yet.", 3500);
                return false;
            }
            RuntimeVehicleCatalog.Refresh();
            if (!RuntimeVehicleCatalog.IsListed(model) ||
                !RuntimeVehicleCatalog.IsModelAvailable(model))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~That vehicle is no longer available in this installation.",
                    3500);
                Log($"Vehicle purchase rejected: unavailable model {model}");
                return false;
            }

            int currentPrice = RuntimeVehicleCatalog.GetPrice(model);
            if (!_freeMode && quotedPrice != currentPrice)
            {
                _browser?.SynchronizeVehicleListing(model, currentPrice);
                GTA.UI.Screen.ShowSubtitle(
                    "~y~That listing changed. GBAY will update it automatically.",
                    3500);
                Log($"Vehicle purchase rejected: stale quote {model}, " +
                    $"quoted=${quotedPrice}, current=${currentPrice}");
                return false;
            }
            if (!_freeMode && currentPrice > Game.Player.Money)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~You no longer have enough money for that vehicle.",
                    3500);
                return false;
            }
            return true;
        }

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

                string name = RuntimeVehicleCatalog.GetDisplayName(model);
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
            if (RejectSpecializedVehicleFromGarage(model, "Eclipse Garage"))
                return;
            // The buyer explicitly selected Eclipse in the destination modal.
            // Never silently reroute the purchase to a different garage.
            if (GarageManager.GetGarageSizeTier(model) >= 2)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~That vehicle is too large for the Eclipse Garage.", 3000);
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

                string name = RuntimeVehicleCatalog.GetDisplayName(model);
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
            if (RejectUnavailableMapDestination(1, "Harmony Garage")) return;
            if (RejectSpecializedVehicleFromGarage(model, "Harmony Garage"))
                return;
            int used = GarageManager.GetFloorGarageUsedSlots();
            int cap = GarageManager.GetFloorGarageCapacity();

            if (used >= cap)
            {
                Log($"DeliverToFloorGarage: full ({used}/{cap})");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The Harmony Garage is full.~w~ ({used}/{cap} spaces used)", 3000);
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
                    GTA.UI.Screen.ShowSubtitle("~r~Delivery to the Harmony Garage failed.", 3000);
                    return;
                }

                if (!_freeMode && price > 0)
                    Game.Player.Money -= price;

                string name = RuntimeVehicleCatalog.GetDisplayName(model);
                string msg = _freeMode || price <= 0
                    ? $"~g~{name}~w~ delivered to the Harmony Garage."
                    : $"~g~{name}~w~ delivered to the Harmony Garage for ~g~${price:N0}~w~.";
                GTA.UI.Screen.ShowSubtitle(msg, 3000);

                Log($"DeliverToFloorGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToFloorGarage", ex);
                GTA.UI.Screen.ShowSubtitle("~r~Delivery to the Harmony Garage failed.", 3000);
            }
        }

        internal void ExecuteDeliverToDavisGarage(string model, int price)
        {
            if (RejectUnavailableMapDestination(2, "Davis Auto Shop")) return;
            if (RejectSpecializedVehicleFromGarage(model, "Davis Auto Shop"))
                return;
            if (GarageManager.GetGarageSizeTier(model) >= 2)
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
                string name = RuntimeVehicleCatalog.GetDisplayName(model);
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
            if (SmokeGrenadeCatalog.TryGetProduct(
                    weaponName, out SmokeGrenadeProduct smoke))
                return WeaponPurchasePolicy.Quote(
                    smoke.UnitPrice, "Throwables",
                    smoke.BundleQuantity, _freeMode);
            string category = RuntimeWeaponCatalog.CategoryNames.ContainsKey(weaponName)
                ? RuntimeWeaponCatalog.CategoryNames[weaponName] : "";
            int configuredQuantity = RuntimeWeaponCatalog.PurchaseQuantities.ContainsKey(
                    weaponName)
                ? RuntimeWeaponCatalog.PurchaseQuantities[weaponName] : 1;
            return WeaponPurchasePolicy.Quote(
                unitPrice, category, configuredQuantity, _freeMode);
        }

        internal void ExecuteGiveWeapon(string weaponName, int unitPrice)
        {
            if (SmokeGrenadeCatalog.IsProduct(weaponName))
            {
                ExecuteGiveSmokeGrenades(weaponName);
                return;
            }
            RuntimeWeaponCatalog.Refresh();
            if (!RuntimeWeaponCatalog.TryGetPrice(weaponName, out int currentPrice))
            {
                GTA.UI.Screen.ShowSubtitle("~r~This weapon is no longer listed in GBAY.", 3500);
                return;
            }
            // Require another confirmation if the authorized price has changed.
            if (unitPrice != currentPrice)
            {
                GTA.UI.Screen.ShowSubtitle("~y~The weapon price changed. Choose the listing again.", 3500);
                return;
            }
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

            string displayName = RuntimeWeaponCatalog.DisplayNames.ContainsKey(weaponName)
                ? RuntimeWeaponCatalog.DisplayNames[weaponName] : weaponName;
            string quantityText = quote.QuantityPriced
                ? $" ({chargedQuantity} x ${quote.UnitPrice:N0})" : "";
            string msg = _freeMode || totalPrice <= 0
                ? $"~g~{displayName}~w~ added."
                : $"~g~{displayName}~w~ purchased{quantityText} for "
                    + $"~g~${totalPrice:N0}~w~.";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"GiveWeapon: {weaponName}, unit=${quote.UnitPrice}, "
                + $"quantity={chargedQuantity}, total=${totalPrice}");
            ClientLog.Info("GBAY", "weapon_purchase_completed",
                new Dictionary<string, object> {
                    { "event_schema", 1 }, { "weapon", weaponName },
                    { "unit_price", quote.UnitPrice }, { "quantity", chargedQuantity },
                    { "total_price", totalPrice }
                });
            CharacterInventory.RecordOwned(weaponName, false);
            GbayPreferences.RecordWeapon(weaponName);
        }

        internal void ExecuteGiveSmokeGrenades(string productId)
        {
            if (!SmokeGrenadeCatalog.TryGetProduct(
                    productId, out SmokeGrenadeProduct product))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~This smoke colour is unavailable.", 3000);
                return;
            }
            int availableWeapons =
                SmokeGrenadeCatalog.AvailableCustomWeaponCount();
            int registeredWeapons =
                SmokeGrenadeCatalog.RegisteredCustomWeaponCount(
                    out int totalDlcWeapons,
                    out string catalogFailure);
            if (availableWeapons != SmokeGrenadeCatalog.Products.Length)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Colored smoke weapons are temporarily unavailable. " +
                    "Your inventory was not charged.", 4500);
                ClientLog.Warn("GBAY", "smoke_purchase_pack_unavailable",
                    new Dictionary<string, object>
                    {
                        { "product", productId },
                        { "valid_weapon_definitions", availableWeapons },
                        { "required_weapon_definitions",
                            SmokeGrenadeCatalog.Products.Length },
                        { "registered_weapon_definitions",
                            registeredWeapons },
                        { "registration_required", false },
                        { "total_dlc_weapons", totalDlcWeapons },
                        { "dlc_catalog_failure", catalogFailure },
                        { "charged", false },
                    });
                return;
            }
            WeaponPurchaseQuote quote = GetWeaponPurchaseQuote(
                productId, product.UnitPrice);
            if (quote.Status != WeaponPurchaseStatus.Available ||
                quote.Quantity <= 0)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Smoke quantity is unavailable.", 3000);
                return;
            }
            if (!_freeMode && quote.TotalPrice > 0 &&
                Game.Player.Money < quote.TotalPrice)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Insufficient funds.", 3000);
                return;
            }

            int added = CharacterInventory.RecordSmokePurchase(
                product.ColorName, quote.Quantity);
            if (added <= 0)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Smoke purchase could not be added.", 3000);
                return;
            }
            int charged = WeaponPurchasePolicy.PriceActualQuantity(
                quote, added, _freeMode);
            if (!_freeMode && charged > 0)
                Game.Player.Money -= charged;
            int stock = CharacterInventory.GetSmokeQuantity(
                product.ColorName);
            bool equipped = CharacterInventory.TryEquipSmokeColor(
                product.ColorName, out int selectedWeaponHash);
            GTA.UI.Screen.ShowSubtitle(
                charged > 0
                    ? $"~g~{product.DisplayName}~w~ purchased " +
                        $"({added} x ${quote.UnitPrice:N0}) for " +
                        $"~g~${charged:N0}~w~. " +
                        (equipped ? "Equipped." :
                            "Added to the weapon wheel.")
                    : $"~g~{product.DisplayName}~w~ added to the weapon wheel" +
                        (equipped ? " and equipped." : "."),
                3000);
            GbayPreferences.RecordWeapon(productId);
            ClientLog.Info("GBAY", "smoke_grenade_purchase_staged",
                new Dictionary<string, object>
                {
                    { "product", productId },
                    { "color", product.ColorName },
                    { "quantity", added },
                    { "stock", stock },
                    { "unit_price", quote.UnitPrice },
                    { "total_price", charged },
                    { "equip_requested", true },
                    { "equipped", equipped },
                    { "selected_weapon_hash", selectedWeaponHash },
                    { "persistence", "next_story_save" },
                });
        }

        /// <summary>
        /// Refill ammo for an owned weapon. Returns the cost charged,
        /// or -1 if already fully stocked, or -2 if insufficient funds.
        /// </summary>
        internal int ExecuteRefillAmmo(string weaponName)
        {
            RuntimeWeaponCatalog.Refresh();
            if (!RuntimeWeaponCatalog.TryGetPrice(weaponName, out _) ||
                !Function.Call<bool>(Hash.IS_WEAPON_VALID, Game.GenerateHash(weaponName)) ||
                !Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    Game.Player.Character.Handle, Game.GenerateHash(weaponName), false))
            {
                GTA.UI.Screen.ShowSubtitle("~r~This weapon is unavailable or not equipped in your inventory.", 3500);
                return 0;
            }
            Ped player = Game.Player.Character;
            Hash weaponHash = (Hash)Game.GenerateHash(weaponName);

            // Get current and max ammo
            int currentAmmo = Function.Call<int>(
                Hash.GET_AMMO_IN_PED_WEAPON, player, weaponHash);

            OutputArgument maxAmmoOut = new OutputArgument();
            bool capacityResolved = Function.Call<bool>(
                Hash.GET_MAX_AMMO, player, weaponHash, maxAmmoOut);
            int nativeMaxAmmo = maxAmmoOut.GetResult<int>();
            int maxClipAmmo = capacityResolved ? Function.Call<int>(
                Hash.GET_MAX_AMMO_IN_CLIP,
                player.Handle, weaponHash, true) : 0;
            int refillTarget = AmmoRefillPolicy.ResolveRefillTarget(
                capacityResolved, nativeMaxAmmo, maxClipAmmo);
            AmmoCapacityResult capacity = AmmoRefillPolicy.Evaluate(
                capacityResolved, currentAmmo, refillTarget);

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
            int totalCost = AmmoRefillPolicy.Price(needed, costPerRound, _freeMode);

            if (!_freeMode && totalCost > 0 && Game.Player.Money < totalCost)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds for ammo.", 3000);
                return -2;
            }

            Function.Call(Hash.SET_PED_AMMO, player, weaponHash, refillTarget);
            CharacterInventory.RecordWeaponAmmo(weaponName, refillTarget);

            if (!_freeMode && totalCost > 0)
                Game.Player.Money -= totalCost;

            string displayName = RuntimeWeaponCatalog.DisplayNames.ContainsKey(weaponName)
                ? RuntimeWeaponCatalog.DisplayNames[weaponName] : weaponName;
            string msg = totalCost > 0
                ? $"~g~{displayName}~w~ ammo refilled ({needed} rounds) for ~g~${totalCost:N0}~w~."
                : $"~g~{displayName}~w~ ammo refilled ({needed} rounds).";
            GTA.UI.Screen.ShowSubtitle(msg, 3000);

            Log($"RefillAmmo: {weaponName}, {needed} rounds, cost=${totalCost}, "
                + $"target={refillTarget}, native_max={nativeMaxAmmo}, "
                + $"clip_max={maxClipAmmo}");
            return totalCost;
        }

        internal bool ExecuteWeaponComponentPurchase(
            string weaponName, int componentHash, int attachmentPoint, int price)
        {
            Ped player = Game.Player.Character;
            int weaponHash = CharacterInventory.GetWeaponHash(weaponName);
            if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    player.Handle, weaponHash, false) ||
                !Function.Call<bool>(Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT,
                    weaponHash, componentHash))
            {
                GTA.UI.Screen.ShowSubtitle("~r~That upgrade is unavailable for this weapon.", 2500);
                return false;
            }

            bool inventoryOwned = CharacterInventory.IsWeaponComponentOwned(
                weaponName, componentHash);
            bool liveOwned = Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                player.Handle, weaponHash, componentHash);
            bool consumed = Allin1ExtensionApi.IsWeaponComponentConsumed(
                weaponName, componentHash);
            bool owned = !consumed && (inventoryOwned || liveOwned);
            bool defaultPart = WeaponComponentDefaults.IsDefault(weaponHash, componentHash);
            int charge = _freeMode || owned || defaultPart ? 0 : Math.Max(0, price);
            if (charge > 0 && Game.Player.Money < charge)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds.", 2500);
                return false;
            }

            int active = CharacterInventory.GetActiveWeaponComponent(
                weaponName, attachmentPoint);
            if (active != 0 && active != componentHash)
                Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED,
                    player.Handle, weaponHash, active);
            Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED,
                player.Handle, weaponHash, componentHash);
            if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                    player.Handle, weaponHash, componentHash))
            {
                GTA.UI.Screen.ShowSubtitle("~r~The upgrade could not be applied.", 2500);
                return false;
            }
            if (charge > 0) Game.Player.Money -= charge;
            CharacterInventory.RecordWeaponComponent(
                weaponName, componentHash, attachmentPoint);
            if (!defaultPart)
                Allin1ExtensionApi.NotifyWeaponComponentPurchased(
                    weaponName, componentHash, attachmentPoint);
            GTA.UI.Screen.ShowSubtitle(charge > 0
                ? $"~g~Weapon upgrade~w~ purchased for ~g~${charge:N0}~w~."
                : "~g~Weapon upgrade equipped.~w~", 2500);
            ClientLog.Info("GBAY", "weapon_component_staged",
                new Dictionary<string, object> {
                    { "weapon", weaponName },
                    { "component_hash", componentHash },
                    { "attachment", attachmentPoint }, { "charged", charge }
                });
            return true;
        }

        internal bool ExecuteWeaponComponentRemoval(string weaponName, int componentHash, int attachmentPoint)
        {
            Ped player = Game.Player.Character;
            int weaponHash = CharacterInventory.GetWeaponHash(weaponName);
            if (player == null || !player.Exists() ||
                !WeaponCustomizationPolicy.CanUnequipComponent(attachmentPoint) ||
                WeaponComponentDefaults.IsDefault(weaponHash, componentHash) ||
                !Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON, player.Handle, weaponHash, false) ||
                !Function.Call<bool>(Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT, weaponHash, componentHash) ||
                !Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT, player.Handle, weaponHash, componentHash))
                return false;
            Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED, player.Handle, weaponHash, componentHash);
            if (Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT, player.Handle, weaponHash, componentHash))
                return false;
            if (!WeaponComponentDefaults.RestoreAfterRemoval(player.Handle, weaponHash, attachmentPoint, componentHash))
            {
                Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED, player.Handle, weaponHash, componentHash);
                return false;
            }
            if (!CharacterInventory.RecordWeaponComponentUnequipped(weaponName, componentHash, attachmentPoint))
            {
                Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED, player.Handle, weaponHash, componentHash);
                return false;
            }
            // Keep ownership; neither charge nor emit a purchase/wear-reset event.
            GTA.UI.Screen.ShowSubtitle("~g~Attachment unequipped. It remains owned.~w~", 2500);
            return true;
        }

        internal bool ExecuteWeaponTintPurchase(
            string weaponName, int tint, int price)
        {
            Ped player = Game.Player.Character;
            int weaponHash = CharacterInventory.GetWeaponHash(weaponName);
            int tintCount = Function.Call<int>(Hash.GET_WEAPON_TINT_COUNT, weaponHash);
            if (tint < 0 || tint >= RuntimeWeaponCatalog.SupportedTintCount(weaponName, tintCount)) return false;
            bool owned = CharacterInventory.IsWeaponTintOwned(weaponName, tint);
            int charge = _freeMode || owned ? 0 : Math.Max(0, price);
            if (charge > 0 && Game.Player.Money < charge)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds.", 2500);
                return false;
            }
            Function.Call(Hash.SET_PED_WEAPON_TINT_INDEX,
                player.Handle, weaponHash, tint);
            int applied = Function.Call<int>(Hash.GET_PED_WEAPON_TINT_INDEX,
                player.Handle, weaponHash);
            if (applied != tint)
            {
                GTA.UI.Screen.ShowSubtitle("~r~The tint could not be applied.", 2500);
                return false;
            }
            if (charge > 0) Game.Player.Money -= charge;
            CharacterInventory.RecordWeaponTint(weaponName, tint);
            GTA.UI.Screen.ShowSubtitle(charge > 0
                ? $"~g~Weapon finish~w~ purchased for ~g~${charge:N0}~w~."
                : "~g~Weapon finish equipped.~w~", 2500);
            ClientLog.Info("GBAY", "weapon_tint_staged",
                new Dictionary<string, object> {
                    { "weapon", weaponName }, { "tint", tint },
                    { "charged", charge }
                });
            return true;
        }

        internal bool ExecuteWeaponComponentTintPurchase(
            string weaponName, int componentHash, int attachmentPoint,
            int tint, int price)
        {
            Ped player = Game.Player.Character;
            int weaponHash = CharacterInventory.GetWeaponHash(weaponName);
            if (tint < 0 || tint >= 32 || !Function.Call<bool>(
                    Hash.HAS_PED_GOT_WEAPON_COMPONENT, player.Handle,
                    weaponHash, componentHash))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~y~Equip that livery before selecting its color.", 2500);
                return false;
            }
            bool owned = CharacterInventory.IsWeaponComponentTintOwned(
                weaponName, componentHash, tint);
            int charge = _freeMode || owned ? 0 : Math.Max(0, price);
            if (charge > 0 && Game.Player.Money < charge)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds.", 2500);
                return false;
            }

            Function.Call(Hash.SET_PED_WEAPON_COMPONENT_TINT_INDEX,
                player.Handle, weaponHash, componentHash, tint);
            int applied = Function.Call<int>(
                Hash.GET_PED_WEAPON_COMPONENT_TINT_INDEX,
                player.Handle, weaponHash, componentHash);
            if (applied != tint)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The livery color could not be applied.", 2500);
                return false;
            }
            if (charge > 0) Game.Player.Money -= charge;
            if (!CharacterInventory.IsWeaponComponentOwned(
                    weaponName, componentHash))
                CharacterInventory.RecordWeaponComponent(
                    weaponName, componentHash, attachmentPoint);
            CharacterInventory.RecordWeaponComponentTint(
                weaponName, componentHash, tint);
            GTA.UI.Screen.ShowSubtitle(charge > 0
                ? $"~g~Livery color~w~ purchased for ~g~${charge:N0}~w~."
                : "~g~Livery color equipped.~w~", 2500);
            ClientLog.Info("GBAY", "weapon_component_tint_staged",
                new Dictionary<string, object> {
                    { "weapon", weaponName },
                    { "component_hash", componentHash },
                    { "tint", tint }, { "charged", charge }
                });
            return true;
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

        internal bool IsWorldAssetOwned(string assetId)
        {
            return WorldAssetList.IsWorldAsset(assetId) &&
                CharacterInventory.IsPropertyOwned(assetId);
        }

        internal bool ExecutePurchaseWorldAsset(string assetId, int price)
        {
            if (!WorldAssetList.IsWorldAsset(assetId))
            {
                Log($"PurchaseWorldAsset: rejected unknown asset {assetId}");
                return false;
            }
            if (IsWorldAssetOwned(assetId))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~y~Already owned.~w~ Yacht features are unlocked.", 3000);
                return false;
            }
            if (!OfficialMapContentPolicy.IsWorldPropertyPurchaseAvailable(
                    alreadyOwned: false))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~That world property is not available.",
                    4000);
                Log("PurchaseWorldAsset: rejected unavailable map content for " +
                    assetId);
                return false;
            }
            if (!_freeMode && price > 0 && Game.Player.Money < price)
            {
                GTA.UI.Screen.ShowSubtitle("~r~Insufficient funds.", 3000);
                return false;
            }
            if (!CharacterInventory.RecordPropertyOwned(assetId))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The yacht purchase could not be saved.", 3000);
                return false;
            }

            if (!_freeMode && price > 0)
                Game.Player.Money -= price;
            string name = WorldAssetList.DisplayName(assetId);
            GTA.UI.Screen.ShowSubtitle(
                _freeMode
                    ? $"~g~{name} acquired.~w~ Yacht features are unlocked."
                    : $"~g~{name} purchased for ${price:N0}.~w~ Yacht features are unlocked.",
                4500);
            Log($"PurchaseWorldAsset: {assetId}, price=${price}");
            return true;
        }

        internal void ExecuteDeliverToGarmentGarage(string model, int price)
        {
            if (RejectUnavailableMapDestination(3, "Garment Factory")) return;
            if (RejectSpecializedVehicleFromGarage(
                    model, "Garment Factory garage")) return;
            if (GarageManager.GetGarageSizeTier(model) >= 2)
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
                string name = RuntimeVehicleCatalog.GetDisplayName(model);
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

        internal void ExecuteDeliverToRuralGarage(string model, int price)
        {
            if (RejectUnavailableMapDestination(4, "Grapeseed Garage")) return;
            if (RejectSpecializedVehicleFromGarage(model, "Grapeseed Garage"))
                return;
            if (GarageManager.GetGarageSizeTier(model) >= 2)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~That vehicle is too large for the Grapeseed Garage.", 3000);
                return;
            }
            int used = GarageManager.GetRuralGarageUsedSlots();
            int cap = GarageManager.GetRuralGarageCapacity();
            if (used >= cap)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The Grapeseed Garage is full.~w~ ({used}/{cap} spaces used)",
                    3000);
                return;
            }
            var rng = new Random();
            try
            {
                bool success = GarageManager.DeliverToRuralGarage(
                    model, rng.Next(0, 160), rng.Next(0, 160));
                if (!success)
                {
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~Delivery to the Grapeseed Garage failed.", 3000);
                    return;
                }
                if (!_freeMode && price > 0) Game.Player.Money -= price;
                string name = RuntimeVehicleCatalog.GetDisplayName(model);
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? $"~g~{name}~w~ delivered to the Grapeseed Garage."
                        : $"~g~{name}~w~ delivered to the Grapeseed Garage for ~g~${price:N0}~w~.",
                    3000);
                Log($"DeliverToRuralGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToRuralGarage", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Delivery to the Grapeseed Garage failed.", 3000);
            }
        }

        internal void ExecuteDeliverToPaletoGarage(string model, int price)
        {
            if (RejectUnavailableMapDestination(5, "Paleto Bay Garage")) return;
            if (RejectSpecializedVehicleFromGarage(model, "Paleto Bay Garage"))
                return;
            if (GarageManager.GetGarageSizeTier(model) >= 2)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~That vehicle is too large for the Paleto Bay Garage.", 3000);
                return;
            }
            int used = GarageManager.GetPaletoGarageUsedSlots();
            int cap = GarageManager.GetPaletoGarageCapacity();
            if (used >= cap)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The Paleto Bay Garage is full.~w~ ({used}/{cap} spaces used)",
                    3000);
                return;
            }
            var rng = new Random();
            try
            {
                bool success = GarageManager.DeliverToPaletoGarage(
                    model, rng.Next(0, 160), rng.Next(0, 160));
                if (!success)
                {
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~Delivery to the Paleto Bay Garage failed.", 3000);
                    return;
                }
                if (!_freeMode && price > 0) Game.Player.Money -= price;
                string name = RuntimeVehicleCatalog.GetDisplayName(model);
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? $"~g~{name}~w~ delivered to the Paleto Bay Garage."
                        : $"~g~{name}~w~ delivered to the Paleto Bay Garage for ~g~${price:N0}~w~.",
                    3000);
                Log($"DeliverToPaletoGarage: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToPaletoGarage", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Delivery to the Paleto Bay Garage failed.", 3000);
            }
        }

        internal void ExecuteDeliverToHarbour(string model, int price)
        {
            if (!GarageManager.IsHarbourVehicleEligible(model))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Los Santos Harbour accepts boats only.", 3500);
                return;
            }
            int used = GarageManager.GetHarbourUsedSlots();
            int cap = GarageManager.GetHarbourCapacity();
            if (used >= cap)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The harbour is full.~w~ ({used}/{cap} spaces used)",
                    3500);
                return;
            }

            var rng = new Random();
            try
            {
                bool success = GarageManager.DeliverToHarbour(
                    model, rng.Next(0, 160), rng.Next(0, 160));
                if (!success)
                {
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~Delivery to Los Santos Harbour failed.", 3000);
                    return;
                }
                if (!_freeMode && price > 0) Game.Player.Money -= price;
                string name = RuntimeVehicleCatalog.GetDisplayName(model);
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? $"~g~{name}~w~ delivered to Los Santos Harbour."
                        : $"~g~{name}~w~ delivered to Los Santos Harbour for ~g~${price:N0}~w~.",
                    3500);
                Log($"DeliverToHarbour: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToHarbour", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Delivery to Los Santos Harbour failed.", 3000);
            }
        }

        internal bool ExecuteRetrieveFromHarbour(int listIndex)
        {
            try
            {
                bool success = GarageManager.RetrieveHarbourVehicle(listIndex);
                if (!success)
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~The boat could not be retrieved.", 3000);
                return success;
            }
            catch (Exception ex)
            {
                LogException("RetrieveFromHarbour", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The boat could not be retrieved.", 3000);
                return false;
            }
        }

        internal void ExecuteDeliverToHelipad(string model, int price)
        {
            if (!GarageManager.IsHelipadVehicleEligible(model))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The Vespucci Helipad accepts helicopters only.", 3500);
                return;
            }
            int used = GarageManager.GetHelipadUsedSlots();
            int cap = GarageManager.GetHelipadCapacity();
            if (used >= cap)
            {
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~The Vespucci Helipad is full.~w~ ({used}/{cap} spaces used)",
                    3500);
                return;
            }

            var rng = new Random();
            try
            {
                bool success = GarageManager.DeliverToHelipad(
                    model, rng.Next(0, 160), rng.Next(0, 160));
                if (!success)
                {
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~Delivery to the Vespucci Helipad failed.", 3000);
                    return;
                }
                if (!_freeMode && price > 0) Game.Player.Money -= price;
                string name = RuntimeVehicleCatalog.GetDisplayName(model);
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? $"~g~{name}~w~ delivered to the Vespucci Helipad."
                        : $"~g~{name}~w~ delivered to the Vespucci Helipad for ~g~${price:N0}~w~.",
                    3500);
                Log($"DeliverToHelipad: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToHelipad", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Delivery to the Vespucci Helipad failed.", 3000);
            }
        }

        internal bool ExecuteRetrieveFromHelipad(int listIndex)
        {
            try
            {
                bool success = GarageManager.RetrieveHelipadVehicle(listIndex);
                if (!success)
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~The helicopter could not be retrieved.", 3000);
                return success;
            }
            catch (Exception ex)
            {
                LogException("RetrieveFromHelipad", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The helicopter could not be retrieved.", 3000);
                return false;
            }
        }

        internal void ExecuteDeliverToYachtHelipad(string model, int price)
        {
            if (RejectUnavailableMapDestination(7, "Yacht Helipad")) return;
            if (!YachtManager.FeaturesUnlocked)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Purchase the Galaxy Super Yacht before using its helipad.",
                    3500);
                return;
            }
            if (!GarageManager.IsYachtHelipadVehicleEligible(model))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The yacht helipad accepts only the Swift Deluxe and SuperVolito Carbon.",
                    4000);
                return;
            }
            int used = GarageManager.GetYachtHelipadUsedSlots();
            int cap = GarageManager.GetYachtHelipadCapacity();
            if (used >= cap)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The Yacht Helipad is occupied.~w~ Sell or remove its aircraft first.",
                    3500);
                return;
            }
            var rng = new Random();
            try
            {
                bool success = GarageManager.DeliverToYachtHelipad(
                    model, rng.Next(0, 160), rng.Next(0, 160));
                if (!success)
                {
                    GTA.UI.Screen.ShowSubtitle(
                        "~r~Delivery to the Yacht Helipad failed.", 3000);
                    return;
                }
                if (!_freeMode && price > 0) Game.Player.Money -= price;
                string name = RuntimeVehicleCatalog.GetDisplayName(model);
                GTA.UI.Screen.ShowSubtitle(
                    _freeMode || price <= 0
                        ? $"~g~{name}~w~ assigned to the Yacht Helipad."
                        : $"~g~{name}~w~ assigned to the Yacht Helipad for ~g~${price:N0}~w~.",
                    3500);
                Log($"DeliverToYachtHelipad: {model}, price=${price}");
            }
            catch (Exception ex)
            {
                LogException("DeliverToYachtHelipad", ex);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Delivery to the Yacht Helipad failed.", 3000);
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
            if (RuntimeVehicleCatalog.IsListed(model) && !RuntimeVehicleCatalog.IsCatalogOnly(model))
            {
                buyPrice = RuntimeVehicleCatalog.GetPrice(model);
            }
            else
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
                    : garageLocation == 4
                        ? GarageManager.RemoveRuralGarageVehicle(listIndex)
                    : garageLocation == 5
                        ? GarageManager.RemovePaletoGarageVehicle(listIndex)
                    : garageLocation == 6
                        ? GarageManager.RemoveHelipadVehicle(listIndex)
                    : garageLocation == 7
                        ? GarageManager.RemoveYachtHelipadVehicle(listIndex)
                    : garageLocation == 8
                        ? GarageManager.RemoveHarbourVehicle(listIndex)
                    : GarageManager.RemoveVehicle(listIndex);
            string garageName = garageLocation == 1 ? "three_floor"
                : garageLocation == 2 ? "davis"
                : garageLocation == 3 ? "garment_factory"
                : garageLocation == 4 ? "rural"
                : garageLocation == 5 ? "paleto"
                : garageLocation == 6 ? "vespucci_helipad"
                : garageLocation == 7 ? "yacht_helipad"
                : garageLocation == 8 ? "los_santos_harbour" : "eclipse";
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

            string displayName = RuntimeVehicleCatalog.GetDisplayName(model);
            bool helipadLocation = garageLocation == 6 || garageLocation == 7;
            bool harbourLocation = garageLocation == 8;
            string msg = _freeMode || sellPrice <= 0
                ? $"~y~{displayName}~w~ removed from the " +
                    (helipadLocation ? "helipad."
                        : harbourLocation ? "harbour." : "garage.")
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
            int nativeMaxAmmo = maxAmmoOut.GetResult<int>();
            int maxClipAmmo = capacityResolved ? Function.Call<int>(
                Hash.GET_MAX_AMMO_IN_CLIP,
                player.Handle, weaponHash, true) : 0;
            int refillTarget = AmmoRefillPolicy.ResolveRefillTarget(
                capacityResolved, nativeMaxAmmo, maxClipAmmo);
            AmmoCapacityResult capacity = AmmoRefillPolicy.Evaluate(
                capacityResolved, currentAmmo, refillTarget);
            if (capacity.Status == AmmoCapacityStatus.Unavailable)
                return AmmoCapacityUnavailable;
            if (capacity.Status == AmmoCapacityStatus.NotApplicable)
                return AmmoNotApplicable;
            if (capacity.Status == AmmoCapacityStatus.FullyStocked)
                return 0;
            roundsNeeded = capacity.RoundsNeeded;

            int costPerRound = GetAmmoUnitPrice(weaponName);

            return AmmoRefillPolicy.Price(roundsNeeded, costPerRound, _freeMode);
        }

        private static int GetAmmoUnitPrice(string weaponName)
        {
            int fallback = RuntimeWeaponCatalog.AmmoCostPerRound.ContainsKey(weaponName)
                ? RuntimeWeaponCatalog.AmmoCostPerRound[weaponName] : 2;
            int catalogPrice = RuntimeWeaponCatalog.Prices.ContainsKey(weaponName)
                ? RuntimeWeaponCatalog.Prices[weaponName] : fallback;
            string category = RuntimeWeaponCatalog.CategoryNames.ContainsKey(weaponName)
                ? RuntimeWeaponCatalog.CategoryNames[weaponName] : "";
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

        internal static void DiscardStagedRuntimeGear(Ped player)
        {
            if (player != null && player.Exists() && JuggernautActive)
                RemoveJuggernaut(player);
            else
                JuggernautActive = false;

            NightVisionOwned = false;
            if (_nightVisionActive)
                Function.Call(Hash.SET_NIGHTVISION, false);
            _nightVisionActive = false;
        }

        internal static bool ClearRuntimeGearAfterDeath()
        {
            // The dying ped is no longer a safe target for outfit restoration.
            // Clear transient effects now; CharacterInventory removes the
            // consumed items from the replacement ped after hospital respawn.
            bool juggernautWasActive = JuggernautActive;
            JuggernautActive = false;
            NightVisionOwned = false;
            if (_nightVisionActive)
                Function.Call(Hash.SET_NIGHTVISION, false);
            _nightVisionActive = false;
            return juggernautWasActive;
        }

        internal static void CompleteRuntimeGearCleanupAfterDeath(
            Ped player, bool juggernautWasLost)
        {
            ClearRuntimeGearAfterDeath();
            if (juggernautWasLost && player != null && player.Exists())
            {
                // RemoveJuggernaut normally refuses after the death tick has
                // cleared its active flag. Temporarily restore that flag so
                // the replacement ped receives the saved health, outfit, and
                // movement settings instead of inheriting ballistic effects.
                JuggernautActive = true;
                RemoveJuggernaut(player);
            }
            _savedComponents = null;
            _savedTextures = null;
            _savedMaxHealth = 0;
            _lastKnownHealth = 0;
        }

        internal static void ApplyBallisticOutfit(Ped player, PedHash ch)
        {
            // Paleto Score juggernaut suit — confirmed in-game on Enhanced Edition
            // during the heist mission.
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

        private static string StoryCharacterId(PedHash character)
        {
            if (character == PedHash.Michael) return "michael";
            if (character == PedHash.Franklin) return "franklin";
            if (character == PedHash.Trevor) return "trevor";
            return "";
        }

        /// <summary>
        /// Refresh Reactor's detached, character-scoped data once per
        /// protagonist edge. The per-frame player-model check already exists
        /// for Story safety; this adds no provider polling or timer.
        /// </summary>
        private void ObserveStoryCharacterSnapshot(PedHash character)
        {
            var bridge = _menuBridge as IAllin1StoryCharacterBridge;
            if (bridge == null || !_storyCharacterRefresh.TryBegin(
                    StoryCharacterId(character), Game.GameTime,
                    out string characterId))
                return;

            bool refreshed = false;
            try
            {
                refreshed = bridge.TryRefreshStoryCharacter(characterId);
                if (refreshed)
                {
                    ClientLog.Info("GBAY",
                        "story_character_snapshot_refreshed",
                        new Dictionary<string, object>
                        {
                            { "character", characterId },
                        });
                }
                else
                {
                    ClientLog.Warn("GBAY",
                        "story_character_snapshot_refresh_failed",
                        new Dictionary<string, object>
                        {
                            { "character", characterId },
                            { "status", _menuBridge.Status ?? "not ready" },
                        });
                }
            }
            catch (Exception ex)
            {
                LogException("ReactorBridge.CharacterRefresh", ex);
            }
            finally
            {
                // Commit the identity only after Reactor publishes a complete
                // character-bound snapshot. A transient failure gets up to
                // three throttled retries; a success suppresses every later
                // per-frame observation for that protagonist.
                _storyCharacterRefresh.Complete(characterId, refreshed);
            }
        }

        /// <summary>
        /// While Reactor owns the visible GBAY surface, keep every detached
        /// menu projection aligned with live Story state at a bounded rate.
        /// Hidden menus perform no polling, and reopening always checks state
        /// immediately. Older bridges simply do not expose this capability.
        /// </summary>
        private void ObserveReactorGameState(PedHash character)
        {
            var bridge = _menuBridge as IAllin1GameStateBridge;
            bool active = bridge != null && _menuBridge.IsMenuActive;
            if (!_gameStateSynchronization.TryBegin(
                    Game.GameTime, active))
                return;

            bool synchronized = false;
            try
            {
                synchronized = bridge.TrySynchronizeGameState(
                    StoryCharacterId(character));
                if (!synchronized && !_gameStateSyncFailureLogged)
                {
                    _gameStateSyncFailureLogged = true;
                    ClientLog.Warn("GBAY",
                        "game_state_synchronization_failed",
                        new Dictionary<string, object>
                        {
                            { "status", _menuBridge.Status ?? "not ready" },
                        });
                }
                else if (synchronized)
                    _gameStateSyncFailureLogged = false;
            }
            catch (Exception ex)
            {
                if (!_gameStateSyncFailureLogged)
                {
                    _gameStateSyncFailureLogged = true;
                    LogException(
                        "ReactorBridge.GameStateSynchronization", ex);
                }
            }
            finally
            {
                _gameStateSynchronization.Complete(
                    Game.GameTime, synchronized);
            }
        }

        // ------------------------------------------------------------------ //
        //  Events                                                             //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            try
            {
                ObserveStartupHandoffPresentation(Game.GameTime);

                bool physicalDown;
                bool physicalStateAvailable = TryReadPhysicalKeyState(
                    _openKey,
                    out physicalDown);
                bool physicalToggleEdge = _toggleInput.ObservePhysicalState(
                    Game.GameTime,
                    physicalStateAvailable,
                    physicalDown);
                if (!physicalToggleEdge)
                    LogStartupHandoffSuppressionIfPending("physical_poll");
                if (physicalToggleEdge)
                {
                    if (Game.IsLoading)
                    {
                        ClientLog.Info("GBAY", "toggle_input_ignored",
                            new Dictionary<string, object>
                            {
                                { "source", "physical_poll" },
                                { "key", _openKey.ToString() },
                                { "reason", "game_loading" },
                            });
                    }
                    else
                    {
                        ClientLog.Info("GBAY", "toggle_input_edge",
                            new Dictionary<string, object>
                            {
                                { "source", "physical_poll" },
                                { "key", _openKey.ToString() },
                                { "fallback", true },
                            });
                        TryToggleBrowser(isPhysicalF9: _openKey == Keys.F9);
                    }
                }

                // Auto-initialize on first tick so garage blips/markers
                // appear immediately without needing to press F9 first.
                if (!_initialized && !Game.IsLoading)
                    Initialize();

                DrivingRuntime.Tick(_menuBridge?.IsMenuActive == true);

                Ped activePlayer = Game.Player.Character;
                bool playerExists = activePlayer != null &&
                    activePlayer.Exists();
                PedHash activeCharacter = (PedHash)0;
                bool supportedCharacter = playerExists &&
                    TryResolveProtagonist(
                        activePlayer.Model.Hash,
                        out activeCharacter);
                bool characterSnapshotReady = !Game.IsLoading &&
                    supportedCharacter &&
                    !activePlayer.IsDead &&
                    !GarageManager.IsTransitionInProgress;
                if (characterSnapshotReady)
                {
                    ObserveStoryCharacterSnapshot(activeCharacter);
                    ObserveReactorGameState(activeCharacter);
                }
                else
                    _gameStateSynchronization.TryBegin(
                        Game.GameTime, menuActive: false);
                bool reactorMenuUnsafe = !characterSnapshotReady;
                if (reactorMenuUnsafe && _menuBridge != null &&
                    _menuBridge.IsMenuActive)
                {
                    _menuBridge.TryDismissVehicles();
                    ClientLog.Warn("GBAY",
                        "reactor_menu_closed_for_unavailable_story_state");
                }
                  else if (!reactorMenuUnsafe && _initialized &&
                      (_menuBridge == null || !_menuBridge.IsMenuActive) &&
                      _f9Handoff.TryBeginStartupIntentCheck())
                  {
                    // Native Reactor owns a physical F9 pressed before the
                    // managed provider is ready. Once Story Mode and this
                    // extension are both safe, convert that typed, process-
                    // scoped intent into exactly one normal GBAY presentation.
                    // This never replays the original key or another action.
                      bool presented = false;
                      long handoffGeneration = 0;
                      try
                      {
                          presented = _menuBridge != null &&
                              _menuBridge.TryPresentPendingStartupMenu();
                      }
                      finally
                      {
                          // A miss remains retryable for only five seconds,
                          // throttled to four bridge checks per second. This
                          // covers native release racing the preloader's UI
                          // event without reopening a named event every tick.
                          handoffGeneration =
                              _f9Handoff.CompleteStartupIntentCheck(presented);
                          if (handoffGeneration > 0)
                          {
                              _toggleInput.ClaimStartupHandoff(
                                  Game.GameTime, handoffGeneration);
                              ClientLog.Info("GBAY",
                                  "startup_menu_intent_presented",
                                  new Dictionary<string, object>
                                  {
                                      { "handoff_generation", handoffGeneration },
                                      { "opening_f9_consumed", true },
                                      { "settle_ms", GbayToggleInputGate.DefaultHandoffSettleMilliseconds },
                                      { "visibility_timeout_ms", GbayToggleInputGate.DefaultHandoffVisibilityTimeoutMilliseconds },
                                  });
                          }
                      }
                  }
                if (reactorMenuUnsafe && _browser != null &&
                    (_browser.IsWeaponCustomizationOpen ||
                     _browser.IsReactorWeaponPreviewOpen))
                {
                    // The native camera/dummy workbench owns temporary player
                    // visibility and camera state. Never carry that state into
                    // death, loading, or a garage transition.
                    _browser.Close();
                    ClientLog.Warn("GBAY",
                        "weapon_workbench_closed_for_unavailable_story_state");
                }
                if (!supportedCharacter && _browser != null && _browser.IsOpen)
                {
                    _browser.Close();
                    ClientLog.Warn("GBAY", "browser_closed_for_unsupported_player_model");
                }

                if (_initialized && _onlineContentEnabled)
                {
                    YachtManager.OnTick();
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
                        GarageManager.IsPlayerInGarmentGarage ||
                        GarageManager.IsPlayerInRuralGarage ||
                        GarageManager.IsPlayerInPaletoGarage)
                    {
                        GarageManager.OnTick();
                        GarageManager.OnFloorGarageTick();
                        GarageManager.OnDavisGarageTick();
                        GarageManager.OnGarmentGarageTick();
                        GarageManager.OnRuralGarageTick();
                        GarageManager.OnPaletoGarageTick();
                        GarageManager.OnHelipadTick();
                        GarageManager.OnHarbourTick();
                        GarageManager.OnYachtHelipadTick();
                    }

                    if (supportedCharacter &&
                        GarageManager.ConsumeHelipadListRequest())
                        OpenGarageWorldEntry(
                            Allin1GarageWorldEntryLocation.VespucciHelipad);
                    if (supportedCharacter &&
                        GarageManager.ConsumeHarbourListRequest())
                        OpenGarageWorldEntry(
                            Allin1GarageWorldEntryLocation.Harbour);
                }

                if (supportedCharacter && _browser != null)
                {
                    _browser.TickReactorWeaponPreview();
                }

                if (supportedCharacter &&
                    ControllerBindings.ChordJustPressed(
                        ControllerBindings.OpenGbayModifier,
                        ControllerBindings.OpenGbay))
                {
                    TryToggleBrowser(isPhysicalF9: false);
                }

                if (_onlineContentEnabled && NightVisionOwned &&
                    ControllerBindings.ChordJustPressed(
                        ControllerBindings.NightVisionModifier,
                        ControllerBindings.NightVision))
                    ToggleNightVision();

                if (_onlineContentEnabled)
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
                if (!_toggleInput.TryPress(Game.GameTime))
                {
                    LogStartupHandoffSuppressionIfPending("shvdn_keydown");
                    return;
                }
                ClientLog.Info("GBAY", "toggle_input_edge",
                    new Dictionary<string, object>
                    {
                        { "source", "shvdn_keydown" },
                        { "key", e.KeyCode.ToString() },
                        { "fallback", false },
                    });
                try
                {
                    TryToggleBrowser(isPhysicalF9: e.KeyCode == Keys.F9);
                }
                catch (Exception ex)
                {
                    LogException("OnKeyDown", ex);
                }
            }
            else if (_onlineContentEnabled && e.KeyCode == _nightVisionKey &&
                NightVisionOwned)
                ToggleNightVision();
        }

        private void OnKeyUp(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == _openKey)
                _toggleInput.ObserveManagedRelease(Game.GameTime);
        }

        private void ObserveStartupHandoffPresentation(long nowMilliseconds)
        {
            bool menuActive = _menuBridge != null &&
                _menuBridge.IsMenuActive;
            bool menuReady = menuActive && IsReactorMenuReady();
            _toggleInput.ObserveMenuLifecycle(menuActive);

            if (!_toggleInput.StartupHandoffActive)
                return;

            var transition = _toggleInput.ObserveStartupPresentation(
                nowMilliseconds,
                menuReady);
            if (transition == GbayToggleHandoffTransition.PresentationObserved)
            {
                ClientLog.Info("GBAY", "startup_f9_presentation_observed",
                    new Dictionary<string, object>
                    {
                        { "handoff_generation", _toggleInput.StartupHandoffGeneration },
                        { "settle_ms", GbayToggleInputGate.DefaultHandoffSettleMilliseconds },
                    });
            }
            else if (transition == GbayToggleHandoffTransition.Settled)
            {
                ClientLog.Info("GBAY", "startup_f9_handoff_settled",
                    new Dictionary<string, object>
                    {
                        { "handoff_generation", _toggleInput.StartupHandoffGeneration },
                        { "result", "visible_and_released" },
                    });
            }
            else if (transition == GbayToggleHandoffTransition.TimedOut)
            {
                ClientLog.Warn("GBAY", "startup_f9_handoff_settled",
                    new Dictionary<string, object>
                    {
                        { "handoff_generation", _toggleInput.StartupHandoffGeneration },
                        { "result", "visibility_timeout_after_release" },
                    });
            }
        }

        private bool IsReactorMenuReady()
        {
            if (_menuBridge == null)
                return false;
            var lifecycle = _menuBridge as IAllin1MenuLifecycleBridge;
            return lifecycle == null
                ? _menuBridge.IsMenuActive
                : lifecycle.IsMenuReady;
        }

        private void LogStartupHandoffSuppressionIfPending(string source)
        {
            if (!_toggleInput.ConsumeHandoffSuppression())
                return;
            long generation = _toggleInput.StartupHandoffGeneration;
            if (generation == _lastHandoffSuppressionLoggedGeneration)
                return;
            _lastHandoffSuppressionLoggedGeneration = generation;
            ClientLog.Info("GBAY", "toggle_input_ignored",
                new Dictionary<string, object>
                {
                    { "source", source ?? "unknown" },
                    { "key", _openKey.ToString() },
                    { "reason", "startup_handoff_generation_consumed" },
                    { "handoff_generation", generation },
                });
        }

        private void TryToggleBrowser(bool isPhysicalF9)
        {
            if (!_f9Handoff.CanDispatch(isPhysicalF9))
            {
                if (_initialized && !_handoffBlockedLogged)
                {
                    _handoffBlockedLogged = true;
                    ClientLog.Info("GBAY", "f9_waiting_for_reactor_handoff");
                    if (_menuBridge == null)
                        ShowReactorUnavailable();
                }
                return;
            }
            _handoffBlockedLogged = false;

            if (!_initialized)
                Initialize();
            // Logical presentation and browser readiness are separate. Once
            // Reactor accepts an open request, reject another F9 until that
            // exact generation has painted; once dismissal is accepted,
            // reject replacement requests until Reactor reports it hidden.
            // This makes one released press one transition while preserving
            // click-close followed by a later F9 reopen.
            if (_menuBridge != null && _menuBridge.IsMenuActive)
            {
                GbayMenuToggleDecision decision =
                    _toggleInput.BeginMenuToggle(
                        isMenuActive: true,
                        isMenuReady: IsReactorMenuReady());
                if (decision != GbayMenuToggleDecision.Close)
                {
                    ClientLog.Info("GBAY", "toggle_input_ignored",
                        new Dictionary<string, object>
                        {
                            { "source", "menu_lifecycle" },
                            { "key", _openKey.ToString() },
                            { "reason", decision ==
                                GbayMenuToggleDecision.OpeningNotReady
                                    ? "reactor_presentation_not_ready"
                                    : "reactor_dismissal_pending" },
                        });
                    return;
                }

                bool dismissed = _menuBridge.TryDismissVehicles();
                _toggleInput.CompleteMenuToggle(decision, dismissed);
                if (dismissed)
                    ClientLog.Info("GBAY", "reactor_menu_dismiss_requested");
                else
                    ClientLog.Warn("GBAY", "reactor_menu_dismiss_failed",
                        new Dictionary<string, object>
                        {
                            { "status", _menuBridge.Status ?? "not ready" },
                        });
                return;
            }
            // While Reactor's typed startup intent is active, this same F9
            // edge means cancel/close, never a second direct GBAY request.
            // The optional bridge performs an atomic process-scoped cancel
            // and removes any queued-but-undrained presentation.
            if (isPhysicalF9 && _menuBridge != null &&
                _menuBridge.TryCancelPendingStartupMenu())
            {
                ClientLog.Info("GBAY", "startup_menu_intent_cancelled_by_f9");
                return;
            }
            if (isPhysicalF9 && _f9Handoff.TryRequestStartupIntentClose())
            {
                ClientLog.Info("GBAY", "startup_initializer_close_requested_by_f9");
                return;
            }
            if (!TryGetCurrentCharacter(out _))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~y~GBAY is available to Michael, Franklin, and Trevor.", 2500);
                ClientLog.Warn("GBAY", "unsupported_player_model");
                return;
            }
            if (GarageManager.IsTransitionInProgress)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~y~A garage transition is already in progress.", 1500);
                return;
            }

            if (TryInitializeReactorBridge(logUnavailable: true))
            {
                try
                {
                    GbayMenuToggleDecision decision =
                        _toggleInput.BeginMenuToggle(
                            isMenuActive: _menuBridge.IsMenuActive,
                            isMenuReady: IsReactorMenuReady());
                    if (decision != GbayMenuToggleDecision.Open)
                    {
                        ClientLog.Info("GBAY", "toggle_input_ignored",
                            new Dictionary<string, object>
                            {
                                { "source", "menu_lifecycle" },
                                { "key", _openKey.ToString() },
                                { "reason", "reactor_transition_in_progress" },
                            });
                        return;
                    }

                    bool presented = _menuBridge.TryPresentVehicles(
                        new Allin1VehicleCatalogRequest());
                    _toggleInput.CompleteMenuToggle(decision, presented);
                    if (presented)
                    {
                        ClientLog.Info("GBAY", "reactor_menu_present_requested");
                        ClientLog.Info("GBAY", "reactor_menu_toggled");
                        return;
                    }
                    ClientLog.Warn("GBAY", "reactor_menu_not_ready",
                        new Dictionary<string, object>
                        {
                            { "status", _menuBridge.Status ?? "not ready" },
                        });
                }
                catch (Exception ex)
                {
                    LogException("ReactorBridge.Present", ex);
                }
            }

            ShowReactorUnavailable();
        }

        private static bool TryReadPhysicalKeyState(
            Keys key,
            out bool isDown)
        {
            try
            {
                isDown = (GetAsyncKeyState((int)key) & 0x8000) != 0;
                return true;
            }
            catch (DllNotFoundException)
            {
                isDown = false;
                return false;
            }
            catch (EntryPointNotFoundException)
            {
                isDown = false;
                return false;
            }
        }

        [DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int virtualKey);

        private static void ToggleNightVision()
        {
            _nightVisionActive = !_nightVisionActive;
            Function.Call(Hash.SET_NIGHTVISION, _nightVisionActive);
        }
    }
}
