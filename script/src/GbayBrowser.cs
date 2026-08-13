// GbayBrowser.cs -- Custom-drawn browser UI for the GBAY vehicle shop.
//
// Renders a grid-based vehicle catalog with category tabs, pagination,
// and keyboard + mouse navigation using GTA native drawing functions.

using System;
using System.Collections.Generic;
using System.Drawing;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal enum BrowserState
    {
        Closed,
        Loading,
        TopMenu,
        VehicleBrowser,
        VehiclePreview,
        DeliveryConfirm,
        GarageView,
        GarageSellConfirm,
        GarageCustomize,
        WeaponBrowser,
        GearBrowser,
        Diagnostics,
        About,
    }

    internal struct VehicleCard
    {
        internal string Model;
        internal string DisplayName;
        internal string Manufacturer;
        internal int Price;
    }

    internal struct WeaponCard
    {
        internal string WeaponName;
        internal string DisplayName;
        internal string Category;
        internal int UnitPrice;
        internal int Price;
        internal int PurchaseQuantity;
        internal bool QuantityPriced;
        internal bool PurchaseAvailable;
        internal bool Owned;
    }

    internal partial class GbayBrowser
    {
        // ------------------------------------------------------------------ //
        //  Layout Constants (normalized 0.0-1.0 screen space)                 //
        // ------------------------------------------------------------------ //

        private const float BROWSER_LEFT   = 0.08f;
        private const float BROWSER_RIGHT  = 0.92f;
        private const float BROWSER_TOP    = 0.03f;
        private const float BROWSER_BOTTOM = 0.93f;
        private const float BROWSER_W      = 0.84f;
        private const float BROWSER_CX     = 0.50f;  // center X

        // Header
        private const float HEADER_Y       = 0.03f;
        private const float HEADER_H       = 0.07f;
        private const float HEADER_CY      = 0.065f;  // center = 0.03 + 0.06/2

        // Category tab strip
        private const float TAB_Y          = 0.10f;
        private const float TAB_H          = 0.055f;
        private const float TAB_CY         = 0.1275f; // center = 0.09 + 0.045/2
        private const int   MAX_VISIBLE_TABS = 8;

        // Grid area
        private const float GRID_TOP       = 0.16f;
        private const float GRID_BOTTOM    = 0.88f;
        private const int   GRID_COLS      = 3;
        private const int   GRID_ROWS      = 3;
        private const int   PAGE_SIZE      = 9;

        // Footer
        private const float FOOTER_Y       = 0.88f;
        private const float FOOTER_H       = 0.05f;
        private const float FOOTER_CY      = 0.905f;

        // Shared navigation action. Every full browser page places Back at
        // the same horizontal position so mouse and controller navigation do
        // not require relearning the layout from screen to screen.
        private const float BACK_BTN_W      = 0.14f;
        private const float BACK_BTN_H      = 0.038f;

        // Card dimensions (computed per-frame for aspect ratio)
        private const float CARD_H         = 0.21f;
        private const float CARD_GAP_X     = 0.015f;
        private const float CARD_GAP_Y     = 0.014f;

        // Top menu button layout
        private const float TOP_BTN_W      = 0.35f;
        private const float TOP_BTN_H      = 0.065f;
        private const float TOP_BTN_GAP    = 0.015f;

        // Shared informational page action
        private const float INFO_BACK_W    = 0.28f;
        private const float INFO_BACK_H    = 0.055f;
        private const float INFO_BACK_CY   = 0.825f;

        // Delivery modal
        private const float MODAL_W        = 0.45f;
        private const float MODAL_ITEM_H   = 0.055f;

        private int _pendingSellIndex = -1;
        private string _pendingSellModel = "";
        private string _pendingSellPlate = "";
        private int _pendingSellModelHash;
        private int _pendingSellGarageLocation;
        private int _garageLocationIndex;
        private int _deliveryGarageIndex;

        // ------------------------------------------------------------------ //
        //  Category Definitions                                               //
        // ------------------------------------------------------------------ //

        private struct Category
        {
            internal string Label;
            internal string[] Models;
            internal bool FavoritesOnly;

            internal Category(string label, string[] models, bool favoritesOnly = false)
            {
                Label = label;
                Models = models;
                FavoritesOnly = favoritesOnly;
            }
        }

        private static readonly Category[] CATEGORIES =
        {
            new Category("All",             VehicleList.All),
            new Category("Favorites",       VehicleList.All, true),
            new Category("Compacts",        VehicleList.Compacts),
            new Category("Coupes",          VehicleList.Coupes),
            new Category("Sedans",          VehicleList.Sedans),
            new Category("SUVs",            VehicleList.Suvs),
            new Category("Muscle",          VehicleList.Muscle),
            new Category("Sports Classics", VehicleList.Sportsclassics),
            new Category("Super",           VehicleList.Super),
            new Category("Off-Road",        VehicleList.Offroad),
            new Category("Motorcycles",     VehicleList.Motorcycles),
            new Category("Vans",            VehicleList.Vans),
            new Category("Boats",           VehicleList.Boats),
            new Category("Helicopters",     VehicleList.Helicopters),
            new Category("Planes",          VehicleList.Planes),
            new Category("Military",        VehicleList.Military),
            new Category("Industrial",      VehicleList.Industrial),
            new Category("Open Wheel",      VehicleList.Openwheel),
            new Category("Emergency",       VehicleList.Emergency),
            new Category("Cycles",          VehicleList.Cycles),
            new Category("Service",         VehicleList.Service),
            new Category("Special",         VehicleList.Special),
        };

        private struct WeaponCategory
        {
            internal string Label;
            internal string[] Weapons;
            internal bool FavoritesOnly;

            internal WeaponCategory(
                string label, string[] weapons, bool favoritesOnly = false)
            {
                Label = label;
                Weapons = weapons;
                FavoritesOnly = favoritesOnly;
            }
        }

        private static readonly WeaponCategory[] WEAPON_CATEGORIES =
        {
            new WeaponCategory("All",             WeaponList.All),
            new WeaponCategory("Favorites",       WeaponList.All, true),
            new WeaponCategory("Pistols",         WeaponList.Pistols),
            new WeaponCategory("SMGs",            WeaponList.Smgs),
            new WeaponCategory("Shotguns",        WeaponList.Shotguns),
            new WeaponCategory("Assault Rifles",  WeaponList.Rifles),
            new WeaponCategory("Machine Guns",    WeaponList.MachineGuns),
            new WeaponCategory("Sniper Rifles",   WeaponList.Snipers),
            new WeaponCategory("Heavy Weapons",   WeaponList.Heavy),
            new WeaponCategory("Melee",           WeaponList.Melee),
            new WeaponCategory("Throwables",      WeaponList.Throwables),
            new WeaponCategory("Miscellaneous",   WeaponList.Misc),
        };

        // ------------------------------------------------------------------ //
        //  State                                                              //
        // ------------------------------------------------------------------ //

        private readonly GbayShop _shop;
        private BrowserState _state = BrowserState.Closed;
        private BrowserState _lastDrawState = BrowserState.Closed;
        private int _stateStartedAt;
        private const int LOADING_DURATION_MS = 850;
        private const int TRANSITION_DURATION_MS = 180;
        internal static bool ReducedMotion;

        // Top menu
        private int _topMenuIndex;
        private int _topMenuHover = -1;

        // Vehicle browser
        private int _activeCategoryIndex;
        private int _currentPage;
        private int _totalPages;
        private int _selectedCard;
        private int _hoverCard = -1;
        private int _tabScrollOffset;
        private int _hoverTab = -1;
        private readonly List<VehicleCard> _filtered = new List<VehicleCard>();
        private readonly HashSet<string> _activeDicts = new HashSet<string>();
        private int _vehicleOwnershipFilter;
        private string _vehicleSearch = "";
        private bool _vehicleKeyboardActive;

        // Delivery confirm
        private string _pendingModel;
        private int _pendingPrice;

        // Garage view
        private int _garageVehicleIdx;
        private int _garageHoverIdx = -1;

        // Weapon browser
        private int _weaponCategoryIndex;
        private int _weaponPage;
        private int _weaponTotalPages;
        private int _weaponSelectedCard;
        private int _weaponHoverCard = -1;
        private int _weaponTabScrollOffset;
        private int _weaponHoverTab = -1;
        private readonly List<WeaponCard> _weaponFiltered = new List<WeaponCard>();
        private int _weaponOwnershipFilter; // 0 all, 1 owned, 2 available
        private string _weaponSearch = "";
        private bool _weaponKeyboardActive;

        // Weapon ammo confirm
        private bool _ammoConfirmPending;
        private string _ammoConfirmWeapon;
        private int _ammoConfirmCost;
        private int _ammoConfirmRounds;
        private int _ammoConfirmCardIdx;

        // Vehicle preview (3D showroom)
        private Vehicle _previewVehicle;
        private Camera _previewCamera;
        private float _previewAngle;
        private float _previewRadius;
        private float _previewHeight;
        private float _previewZoom = 1.0f;
        private string _previewModel;
        private string _previewDisplayName;
        private string _previewManufacturer;
        private int _previewPrice;
        private static readonly Vector3 PREVIEW_POS = new Vector3(0f, 0f, 1000f);
        private const float AUTO_ORBIT_SPEED = 0.4f; // radians per second
        private const float MANUAL_ORBIT_SPEED = 2.5f;
        private const float ZOOM_SPEED = 0.1f;
        private const float ZOOM_MIN = 0.5f;
        private const float ZOOM_MAX = 2.0f;

        // ------------------------------------------------------------------ //
        //  Constructor                                                        //
        // ------------------------------------------------------------------ //

        internal GbayBrowser(GbayShop shop)
        {
            _shop = shop;
        }

        // ------------------------------------------------------------------ //
        //  Public API                                                         //
        // ------------------------------------------------------------------ //

        internal bool IsOpen => _state != BrowserState.Closed;

        internal void Toggle()
        {
            if (_state == BrowserState.Closed)
            {
                _state = BrowserState.Loading;
                _stateStartedAt = Game.GameTime;
                _topMenuIndex = 0;
                GbayRenderer.EnsureTextures();
                GbayRenderer.RequestDict("phat_logo");
            }
            else
            {
                ClosePreview();
                ReleaseAllDicts();
                _state = BrowserState.Closed;
            }
        }

        internal void Close()
        {
            ClosePreview();
            ReleaseAllDicts();
            _state = BrowserState.Closed;
        }

        // ------------------------------------------------------------------ //
        //  Main Draw (called every frame from GbayShop.OnTick)                //
        // ------------------------------------------------------------------ //

        internal void Draw()
        {
            if (_state == BrowserState.Closed)
                return;

            if (Game.Player.Character.IsDead || Game.IsLoading)
            {
                ClosePreview();
                ReleaseAllDicts();
                _state = BrowserState.Closed;
                return;
            }

            var input = GbayInput.Poll();
            GbayInput.DisableGameControls();

            if (_state != _lastDrawState)
            {
                _lastDrawState = _state;
                _stateStartedAt = Game.GameTime;
                ClientLog.Info("GBAY", "screen_transition", new Dictionary<string, object> {
                    { "screen", _state.ToString() }
                });
            }

            // Preview and delivery states handle their own background
            if (_state != BrowserState.VehiclePreview &&
                _state != BrowserState.DeliveryConfirm ||
                _state == BrowserState.DeliveryConfirm && _previewVehicle == null)
            {
                GbayRenderer.DrawScrim();
            }

            switch (_state)
            {
                case BrowserState.Loading:
                    DrawLoading();
                    break;
                case BrowserState.TopMenu:
                    DrawTopMenu(input);
                    break;
                case BrowserState.VehicleBrowser:
                    DrawBrowser(input);
                    break;
                case BrowserState.VehiclePreview:
                    DrawPreview(input);
                    break;
                case BrowserState.DeliveryConfirm:
                    if (_previewVehicle != null)
                        UpdatePreviewCamera(); // keep camera orbiting behind modal
                    else
                        DrawBrowser(new FrameInput());
                    DrawDeliveryModal(input);
                    break;
                case BrowserState.GarageView:
                    DrawGarageView(input);
                    break;
                case BrowserState.GarageSellConfirm:
                    DrawGarageSellConfirm(input);
                    break;
                case BrowserState.GarageCustomize:
                    DrawGarageCustomize(input);
                    break;
                case BrowserState.WeaponBrowser:
                    DrawWeaponBrowser(input);
                    break;
                case BrowserState.GearBrowser:
                    DrawGearBrowser(input);
                    break;
                case BrowserState.Diagnostics:
                    DrawDiagnostics(input);
                    break;
                case BrowserState.About:
                    DrawAbout(input);
                    break;
            }

            DrawTransition();
            if (_state != BrowserState.Loading) GbayRenderer.DrawCursor();
        }

        private void DrawLoading()
        {
            GbayRenderer.DrawRect(0.5f, 0.5f, 1f, 1f, Color.FromArgb(255, 15, 25, 20));
            float pulse = 0.17f + 0.012f * (float)Math.Sin(Game.GameTime / 110.0);
            GbayRenderer.DrawLogo(0.5f, 0.43f, pulse);
            GbayRenderer.DrawTitleBadge(
                "LOADING GBAY", 0.5f, 0.585f, 0.25f, 0.055f, 0.40f);
            float progress = Math.Min(1f, (Game.GameTime - _stateStartedAt) / (float)LOADING_DURATION_MS);
            GbayRenderer.DrawRect(0.5f, 0.63f, 0.30f, 0.008f, Color.FromArgb(100, 255, 255, 255));
            GbayRenderer.DrawRect(0.35f + 0.15f * progress, 0.63f, 0.30f * progress, 0.008f,
                GbayRenderer.BtnGreen);
            if (progress >= 1f) _state = BrowserState.TopMenu;
        }

        private void DrawTransition()
        {
            int elapsed = Game.GameTime - _stateStartedAt;
            if (ReducedMotion || _state == BrowserState.Loading || elapsed >= TRANSITION_DURATION_MS) return;
            int alpha = (int)(150f * (1f - elapsed / (float)TRANSITION_DURATION_MS));
            GbayRenderer.DrawRect(0.5f, 0.5f, 1f, 1f, Color.FromArgb(Math.Max(0, alpha), 8, 20, 13));
        }

        private static float FocusBorderWidth()
        {
            return 0.003f;
        }

        private static Color FocusBorderColor()
        {
            return GbayRenderer.CardBorderSel;
        }

        private static void DrawFocusedRect(float x, float y, float w, float h, Color fill)
        {
            GbayRenderer.DrawBorderedRect(x, y, w, h, fill,
                FocusBorderColor(), FocusBorderWidth());
        }

        private bool DrawCenteredBackButton(
            FrameInput input, float centerY = FOOTER_CY, float width = BACK_BTN_W,
            string label = "Back", bool focused = false)
        {
            bool hover = GbayRenderer.HitTest(
                input.MouseX, input.MouseY, BROWSER_CX, centerY, width, BACK_BTN_H);
            Color fill = hover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen;
            if (focused || hover)
                DrawFocusedRect(BROWSER_CX, centerY, width, BACK_BTN_H, fill);
            else
                GbayRenderer.DrawBorderedRect(BROWSER_CX, centerY, width, BACK_BTN_H,
                    fill, GbayRenderer.CardBorderSel, 0.002f);
            GbayRenderer.DrawText(label, BROWSER_CX, centerY - 0.014f, 0.30f,
                GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);
            return input.MouseClick && hover;
        }

        /// <summary>
        /// Draw the shared high-contrast control legend used by GBAY pages.
        /// The explicit green field prevents the hint from disappearing into
        /// the pale footer or the game world behind full-screen previews.
        /// </summary>
        private static void DrawControlHint(
            string text, float rightEdge = BROWSER_RIGHT - 0.01f,
            float centerY = FOOTER_CY, float width = 0.325f,
            float height = 0.038f)
        {
            float centerX = rightEdge - width / 2f;
            GbayRenderer.DrawBorderedRect(centerX, centerY, width, height,
                GbayRenderer.BtnGreen, Color.FromArgb(255, 18, 105, 51), 0.002f);
            GbayRenderer.DrawTextFit(text, centerX, centerY - height * 0.31f,
                0.31f, 0.235f, width - 0.018f, GbayRenderer.TextWhite,
                GbayRenderer.FONT_CONDENSED, true, true);
        }

        // ------------------------------------------------------------------ //
        //  Top Menu                                                           //
        // ------------------------------------------------------------------ //

        private void DrawTopMenu(FrameInput input)
        {
            // Background panel
            float panelW = 0.40f;
            float panelH = 0.72f;
            GbayRenderer.DrawRect(BROWSER_CX, 0.5f, panelW, panelH,
                GbayRenderer.ModalBg);

            // Clean GBAY panel. PHAT remains on the loading screen only.
            GbayRenderer.DrawGbayHeader(BROWSER_CX, 0.18f, 0.22f, 0.075f);

            // Buttons
            string[] labels = { "Vehicles", "Weapons", "Gear", "My Garage", "Diagnostics", "About" };
            bool[] enabled = { true, true, true, true, true, true };
            float startY = 0.245f;

            _topMenuHover = -1;

            for (int i = 0; i < labels.Length; i++)
            {
                float btnY = startY + i * (TOP_BTN_H + TOP_BTN_GAP);
                float btnCY = btnY + TOP_BTN_H / 2f;
                bool isSelected = i == _topMenuIndex;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    BROWSER_CX, btnCY, TOP_BTN_W, TOP_BTN_H);

                if (isHover && enabled[i])
                    _topMenuHover = i;

                Color bg;
                Color text;
                if (!enabled[i])
                {
                    bg = GbayRenderer.BtnGray;
                    text = GbayRenderer.TextDim;
                }
                else if (isSelected || isHover)
                {
                    bg = GbayRenderer.BtnGreenHover;
                    text = GbayRenderer.TextWhite;
                }
                else
                {
                    bg = GbayRenderer.BtnGreen;
                    text = GbayRenderer.TextWhite;
                }

                if (isSelected && enabled[i])
                    DrawFocusedRect(BROWSER_CX, btnCY, TOP_BTN_W, TOP_BTN_H, bg);
                else
                    GbayRenderer.DrawRect(BROWSER_CX, btnCY, TOP_BTN_W, TOP_BTN_H, bg);
                GbayRenderer.DrawText(labels[i], BROWSER_CX, btnY + 0.018f,
                    0.50f, text, GbayRenderer.FONT_CHALET, true);
            }

            bool closeClicked = DrawCenteredBackButton(
                input, 0.825f, 0.20f, "Close", false);

            // Input handling
            if (input.DirY != 0)
            {
                int next = _topMenuIndex + input.DirY;
                // Skip disabled items
                while (next >= 0 && next < labels.Length && !enabled[next])
                    next += input.DirY;
                if (next >= 0 && next < labels.Length)
                {
                    _topMenuIndex = next;
                    GbayRenderer.PlayNav();
                }
            }

            bool accepted = input.Accept ||
                            (input.MouseClick && _topMenuHover >= 0);
            int activateIdx = input.MouseClick && _topMenuHover >= 0
                ? _topMenuHover : _topMenuIndex;

            if (accepted && enabled[activateIdx])
            {
                GbayRenderer.PlaySelect();
                if (activateIdx == 0) // Vehicles
                {
                    _state = BrowserState.VehicleBrowser;
                    _activeCategoryIndex = 0;
                    _currentPage = 0;
                    _selectedCard = 0;
                    _tabScrollOffset = 0;
                    RebuildFilteredList();
                }
                else if (activateIdx == 1) // Weapons
                {
                    _state = BrowserState.WeaponBrowser;
                    _weaponCategoryIndex = 0;
                    _weaponPage = 0;
                    _weaponSelectedCard = 0;
                    _weaponTabScrollOffset = 0;
                    RebuildWeaponFilteredList();
                }
                else if (activateIdx == 2) // Gear
                {
                    OpenGearBrowser();
                }
                else if (activateIdx == 3) // My Garage
                {
                    _state = BrowserState.GarageView;
                    _garageVehicleIdx = 0;
                    _garageLocationIndex = GarageManager.IsPlayerInFloorGarage ? 1
                        : GarageManager.IsPlayerInDavisGarage ? 2
                        : GarageManager.IsPlayerInGarmentGarage ? 3 : 0;
                }
                else if (activateIdx == 4)
                {
                    _state = BrowserState.Diagnostics;
                }
                else if (activateIdx == 5)
                {
                    _state = BrowserState.About;
                }
            }

            if (input.Back || input.MouseRightClick || closeClicked)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.Closed;
            }
        }

        private void DrawInfoPanel(
            string title, string[] lines, FrameInput input, bool showLogo)
        {
            const float panelW = 0.68f;
            const float panelH = 0.80f;
            GbayRenderer.DrawRect(BROWSER_CX, 0.49f, panelW, panelH,
                GbayRenderer.ModalBg);
            if (showLogo)
                GbayRenderer.DrawBrandLogo(
                    BROWSER_CX, 0.165f, 0.24f, 0.115f);
            else
                GbayRenderer.DrawGbayWordmark(BROWSER_CX, 0.115f, 0.58f);

            float titleY = showLogo ? 0.255f : 0.205f;
            GbayRenderer.DrawTitleBadge(
                title, BROWSER_CX, titleY, 0.30f, 0.055f, 0.48f);

            float bodyTop = showLogo ? 0.315f : 0.265f;
            const float bodyBottom = 0.775f;
            const float rowGap = 0.006f;
            float available = bodyBottom - bodyTop - rowGap * Math.Max(0, lines.Length - 1);
            float rowH = lines.Length > 0
                ? Math.Min(showLogo ? 0.085f : 0.052f, available / lines.Length)
                : 0f;
            float y = bodyTop;
            for (int i = 0; i < lines.Length; i++)
            {
                float rowCY = y + rowH / 2f;
                Color rowBg = i % 2 == 0
                    ? Color.FromArgb(255, 241, 246, 243)
                    : Color.FromArgb(255, 232, 240, 235);
                GbayRenderer.DrawRect(BROWSER_CX, rowCY, 0.60f, rowH, rowBg);
                Color textColor = lines[i].StartsWith("buymeacoffee", StringComparison.OrdinalIgnoreCase)
                    ? GbayRenderer.TextMfg : GbayRenderer.TextDark;
                if (showLogo)
                {
                    GbayRenderer.DrawTextFit(lines[i], BROWSER_CX, rowCY - 0.014f,
                        0.36f, 0.25f, 0.55f, textColor,
                        GbayRenderer.FONT_CHALET, true);
                }
                else
                {
                    GbayRenderer.DrawTextFit(lines[i], BROWSER_LEFT + 0.16f,
                        rowCY - 0.013f, 0.32f, 0.22f, 0.56f, textColor,
                        GbayRenderer.FONT_CHALET);
                }
                y += rowH + rowGap;
            }
            bool backClicked = DrawCenteredBackButton(
                input, INFO_BACK_CY, INFO_BACK_W, "Back", false);
            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
            }
        }

        private void DrawDiagnostics(FrameInput input)
        {
            string version = typeof(GbayBrowser).Assembly.GetName().Version?.ToString(3) ?? "unknown";
            DrawInfoPanel("DIAGNOSTICS", new[] {
                "ALLIN1 client " + version,
                "Session duration: " + (Game.GameTime / 1000) + " seconds",
                "Garage location: " + (GarageManager.IsPlayerInFloorGarage
                    ? "three-floor garage"
                    : GarageManager.IsPlayerInDavisGarage ? "Davis Auto Shop"
                    : GarageManager.IsPlayerInGarmentGarage ? "Garment Factory"
                    : GarageManager.IsInGarage ? "Eclipse Towers" : "outside"),
                "Traffic: " + TrafficSpawner.ManagedVehicleCount + " managed, " +
                    Math.Round(TrafficSpawner.SmoothedFps) + " FPS" +
                    (TrafficSpawner.IsThrottled ? " (adaptive throttle)" : "") +
                    (string.IsNullOrEmpty(TrafficSpawner.PauseReason) ? "" :
                        " (paused: " + TrafficSpawner.PauseReason + ")"),
                "Safe mode: " + (ClientWatchdog.SafeMode ? "active" : "off"),
                "GBAY artwork: " + GbayRenderer.PreviewDiagnostics,
                "RPF support: " + GbayRenderer.OpenRpfStatus,
                "Detailed events are written to ALLIN1_client.log.",
                "Use the desktop manager to export a redacted support bundle."
            }, input, false);
        }

        private void DrawAbout(FrameInput input)
        {
            string version = typeof(GbayBrowser).Assembly.GetName().Version?.ToString(3) ?? "unknown";
            DrawInfoPanel("ABOUT ALLIN1", new[] {
                "Version " + version,
                "Bring GTA Online DLC content into Story Mode with one click.",
                "Created and maintained by MinionEnjoyer.",
                "buymeacoffee.com/minionenjoyer"
            }, input, true);
        }

        // ------------------------------------------------------------------ //
        //  Vehicle Browser                                                    //
        // ------------------------------------------------------------------ //

        private void DrawBrowser(FrameInput input)
        {
            UpdateVehicleSearchKeyboard();
            float aspect = GbayRenderer.GetAspectRatio();
            float cardW = CARD_H / aspect;

            // Browser background
            float bgCY = (BROWSER_TOP + BROWSER_BOTTOM) / 2f;
            float bgH = BROWSER_BOTTOM - BROWSER_TOP;
            GbayRenderer.DrawRect(BROWSER_CX, bgCY, BROWSER_W, bgH,
                GbayRenderer.BodyBg);

            // Header
            DrawHeader();

            // Category tabs
            DrawCategoryTabs(input, aspect);

            // Grid
            DrawGrid(input, cardW);

            // Footer
            bool previousPageClicked;
            bool nextPageClicked;
            bool backClicked = DrawFooter(
                input, out previousPageClicked, out nextPageClicked);

            // Handle input
            HandleBrowserInput(
                input, backClicked, previousPageClicked, nextPageClicked);
        }

        private void DrawHeader()
        {
            GbayRenderer.DrawRect(BROWSER_CX, HEADER_CY, BROWSER_W, HEADER_H,
                GbayRenderer.HeaderBg);

            GbayRenderer.DrawGbayWordmark(
                BROWSER_LEFT + 0.035f, HEADER_Y + 0.010f, 0.43f, true);

            // Section label
            GbayRenderer.DrawTitleBadge(
                "VEHICLES", BROWSER_LEFT + 0.18f, HEADER_CY,
                0.17f, 0.044f, 0.35f);

            // Player money (right)
            string money = $"${Game.Player.Money:N0}";
            GbayRenderer.DrawText(money, BROWSER_RIGHT - 0.01f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.HeaderText, GbayRenderer.FONT_CHALET,
                false, false, true);
        }

        private void DrawCategoryTabs(FrameInput input, float aspect)
        {
            GbayRenderer.DrawRect(BROWSER_CX, TAB_CY, BROWSER_W, TAB_H,
                GbayRenderer.TabBg);

            int visibleCount = Math.Min(MAX_VISIBLE_TABS, CATEGORIES.Length - _tabScrollOffset);
            const float arrowW = 0.032f;
            float tabAreaW = BROWSER_W - arrowW * 2f - 0.016f;
            float singleTabW = tabAreaW / MAX_VISIBLE_TABS;
            float tabStartX = BROWSER_LEFT + arrowW + 0.008f;

            _hoverTab = -1;

            for (int i = 0; i < visibleCount; i++)
            {
                int catIdx = _tabScrollOffset + i;
                float tabCX = tabStartX + singleTabW * i + singleTabW / 2f;
                bool isActive = catIdx == _activeCategoryIndex;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    tabCX, TAB_CY, singleTabW - 0.004f, TAB_H);

                if (isHover)
                    _hoverTab = catIdx;

                if (isActive)
                    DrawFocusedRect(tabCX, TAB_CY, singleTabW - 0.006f,
                        TAB_H - 0.006f, GbayRenderer.BtnGreenHover);
                else if (isHover)
                    GbayRenderer.DrawRect(tabCX, TAB_CY, singleTabW - 0.004f,
                        TAB_H, GbayRenderer.TabHover);

                // Active indicator (white bar at bottom of tab)
                if (isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_Y + TAB_H - 0.004f,
                        singleTabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);

                // Label
                Color textColor = isActive ? GbayRenderer.TabActive : GbayRenderer.TabInactive;
                string label = CATEGORIES[catIdx].Label;
                GbayRenderer.DrawTextFit(label, tabCX, TAB_Y + 0.01f,
                    0.32f, 0.22f, singleTabW - 0.012f, textColor,
                    GbayRenderer.FONT_CONDENSED, true);
            }

            // Mouse-accessible tab paging. The old arrows were decorative,
            // which made later categories unreachable without a controller.
            float leftArrowX = BROWSER_LEFT + arrowW / 2f;
            float rightArrowX = BROWSER_RIGHT - arrowW / 2f;
            bool canScrollLeft = _tabScrollOffset > 0;
            bool canScrollRight = _tabScrollOffset + MAX_VISIBLE_TABS < CATEGORIES.Length;
            bool leftHover = canScrollLeft && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, leftArrowX, TAB_CY, arrowW, TAB_H);
            bool rightHover = canScrollRight && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, rightArrowX, TAB_CY, arrowW, TAB_H);
            GbayRenderer.DrawRect(leftArrowX, TAB_CY, arrowW, TAB_H,
                leftHover ? GbayRenderer.BtnGreenHover : GbayRenderer.TabBg);
            GbayRenderer.DrawRect(rightArrowX, TAB_CY, arrowW, TAB_H,
                rightHover ? GbayRenderer.BtnGreenHover : GbayRenderer.TabBg);
            if (canScrollLeft)
            {
                GbayRenderer.DrawText("<", leftArrowX, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET, true);
            }
            if (canScrollRight)
            {
                GbayRenderer.DrawText(">", rightArrowX, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET, true);
            }
            if (input.MouseClick && leftHover)
            {
                _tabScrollOffset = Math.Max(0,
                    _tabScrollOffset - (MAX_VISIBLE_TABS - 1));
                GbayRenderer.PlayNav();
            }
            else if (input.MouseClick && rightHover)
            {
                _tabScrollOffset = Math.Min(
                    Math.Max(0, CATEGORIES.Length - MAX_VISIBLE_TABS),
                    _tabScrollOffset + (MAX_VISIBLE_TABS - 1));
                GbayRenderer.PlayNav();
            }
        }

        private void DrawGrid(FrameInput input, float cardW)
        {
            float gridW = GRID_COLS * cardW + (GRID_COLS - 1) * CARD_GAP_X;
            float gridStartX = BROWSER_CX - gridW / 2f;
            float gridStartY = GRID_TOP + 0.01f;

            int startIdx = _currentPage * PAGE_SIZE;
            int count = Math.Min(PAGE_SIZE, _filtered.Count - startIdx);

            _hoverCard = -1;

            for (int i = 0; i < count; i++)
            {
                int col = i % GRID_COLS;
                int row = i / GRID_COLS;
                float cardLeft = gridStartX + col * (cardW + CARD_GAP_X);
                float cardTop = gridStartY + row * (CARD_H + CARD_GAP_Y);
                float cardCX = cardLeft + cardW / 2f;
                float cardCY = cardTop + CARD_H / 2f;

                bool isSelected = i == _selectedCard;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    cardCX, cardCY, cardW, CARD_H);

                if (isHover)
                    _hoverCard = i;

                VehicleCard card = _filtered[startIdx + i];
                DrawCard(card, cardLeft, cardTop, cardW, isSelected, isHover, i);
            }

            // Empty state
            if (count == 0)
            {
                GbayRenderer.DrawText("No vehicles in this category",
                    BROWSER_CX, 0.45f, 0.4f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);
            }
        }

        private void DrawCard(VehicleCard card, float left, float top,
                               float cardW, bool selected, bool hovered,
                               int cardIndex)
        {
            float cx = left + cardW / 2f;
            float cy = top + CARD_H / 2f;

            // Card background
            Color bgColor = selected ? GbayRenderer.CardSelected
                          : hovered ? GbayRenderer.CardHover
                          : GbayRenderer.CardBg;
            Color borderColor = selected ? FocusBorderColor()
                              : GbayRenderer.CardBorder;

            GbayRenderer.DrawBorderedRect(cx, cy, cardW, CARD_H,
                bgColor, borderColor, selected ? FocusBorderWidth() : 0.002f);

            // Top area (preview image or category-colored placeholder -- 55% of card height)
            float topAreaH = CARD_H * 0.55f;
            float topAreaCY = top + topAreaH / 2f;

            // Try to draw preview texture; fall back to placeholder if not loaded
            bool previewDrawn = GbayRenderer.HasPreviewTexture(card.Model);
            if (previewDrawn)
            {
                // Draw dark background behind texture (in case of letterboxing)
                GbayRenderer.DrawRect(cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f,
                    Color.FromArgb(255, 20, 20, 20));
                GbayRenderer.DrawPreviewTexture(card.Model,
                    cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f);
            }
            else
            {
                // Fallback: colored placeholder with class name
                Color topColor = GetCategoryColor(card.Model, hovered || selected);
                GbayRenderer.DrawRect(cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f,
                    topColor);

                string className = VehicleList.ClassNames.ContainsKey(card.Model)
                    ? VehicleList.ClassNames[card.Model]
                    : "";
                if (className.Length > 0)
                {
                    GbayRenderer.DrawText(className, cx, top + topAreaH * 0.35f,
                        0.28f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true);
                }
            }

            // Text area below the placeholder
            float textTop = top + topAreaH + 0.005f;
            float textLeft = left + 0.008f;

            // Manufacturer
            GbayRenderer.DrawTextFit(card.Manufacturer, textLeft, textTop,
                0.26f, 0.20f, cardW - 0.016f, GbayRenderer.TextMfg,
                GbayRenderer.FONT_CONDENSED);

            // Vehicle name
            GbayRenderer.DrawTextFit(card.DisplayName, textLeft, textTop + 0.028f,
                0.33f, 0.22f, cardW - 0.016f, GbayRenderer.TextDark,
                GbayRenderer.FONT_CHALET);

            // Price
            string priceText = card.Price <= 0 ? "FREE" : $"${card.Price:N0}";
            Color priceColor = card.Price <= 0
                ? GbayRenderer.TextPriceFree : GbayRenderer.TextPrice;
            GbayRenderer.DrawText(priceText, textLeft, textTop + 0.058f,
                0.30f, priceColor, GbayRenderer.FONT_CHALET);
        }

        private void DrawPager(
            FrameInput input, int page, int totalPages, int itemCount,
            out bool previousClicked, out bool nextClicked)
        {
            int pageCount = Math.Max(1, totalPages);
            bool canGoBack = page > 0;
            bool canGoForward = page < pageCount - 1;
            const float buttonW = 0.034f;
            const float buttonH = 0.034f;
            float previousX = BROWSER_LEFT + 0.025f;
            float nextX = BROWSER_LEFT + 0.315f;
            float labelX = (previousX + nextX) / 2f;
            bool previousHover = canGoBack && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, previousX, FOOTER_CY, buttonW, buttonH);
            bool nextHover = canGoForward && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, nextX, FOOTER_CY, buttonW, buttonH);

            Color disabledFill = Color.FromArgb(255, 211, 220, 215);
            Color enabledFill = GbayRenderer.BtnGreen;
            GbayRenderer.DrawBorderedRect(previousX, FOOTER_CY, buttonW, buttonH,
                previousHover ? GbayRenderer.BtnGreenHover
                    : canGoBack ? enabledFill : disabledFill,
                canGoBack ? GbayRenderer.CardBorderSel : GbayRenderer.CardBorder, 0.002f);
            GbayRenderer.DrawBorderedRect(nextX, FOOTER_CY, buttonW, buttonH,
                nextHover ? GbayRenderer.BtnGreenHover
                    : canGoForward ? enabledFill : disabledFill,
                canGoForward ? GbayRenderer.CardBorderSel : GbayRenderer.CardBorder, 0.002f);

            Color previousText = canGoBack ? GbayRenderer.TextWhite : GbayRenderer.TextDim;
            Color nextText = canGoForward ? GbayRenderer.TextWhite : GbayRenderer.TextDim;
            GbayRenderer.DrawText("<", previousX, FOOTER_Y + 0.009f,
                0.30f, previousText, GbayRenderer.FONT_CHALET, true);
            GbayRenderer.DrawText(">", nextX, FOOTER_Y + 0.009f,
                0.30f, nextText, GbayRenderer.FONT_CHALET, true);

            string itemLabel = itemCount == 1 ? "item" : "items";
            string pageText = $"Page {page + 1} / {pageCount}  -  {itemCount} {itemLabel}";
            GbayRenderer.DrawTextFit(pageText, labelX, FOOTER_Y + 0.011f,
                0.28f, 0.20f, nextX - previousX - buttonW - 0.012f,
                GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);

            previousClicked = input.MouseClick && previousHover;
            nextClicked = input.MouseClick && nextHover;
        }

        private bool DrawFooter(
            FrameInput input, out bool previousPageClicked, out bool nextPageClicked)
        {
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);

            DrawPager(input, _currentPage, _totalPages, _filtered.Count,
                out previousPageClicked, out nextPageClicked);

            bool backClicked = DrawCenteredBackButton(input);

            // Control hints
            string filter = _vehicleOwnershipFilter == 1 ? "OWNED"
                : _vehicleOwnershipFilter == 2 ? "AVAILABLE" : "ALL";
            string search = _vehicleSearch.Length > 0 ? "SEARCH ON" : "SEARCH";
            string hints = $"Y {filter}   X {search}   R3 FAVORITE   LB/RB PAGES";
            DrawControlHint(hints);
            return backClicked;
        }

        private void HandleBrowserInput(
            FrameInput input, bool backClicked,
            bool previousPageClicked, bool nextPageClicked)
        {
            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
                return;
            }

            if (input.FilterNext)
            {
                _vehicleOwnershipFilter = (_vehicleOwnershipFilter + 1) % 3;
                _currentPage = 0; _selectedCard = 0;
                RebuildFilteredList(); GbayRenderer.PlayNav(); return;
            }
            if (input.Favorite && _filtered.Count > 0)
            {
                int favoriteIdx = _currentPage * PAGE_SIZE + _selectedCard;
                if (favoriteIdx < _filtered.Count)
                    GbayPreferences.ToggleVehicle(_filtered[favoriteIdx].Model);
                if (CATEGORIES[_activeCategoryIndex].FavoritesOnly)
                {
                    RebuildFilteredList();
                    _currentPage = Math.Min(_currentPage, _totalPages - 1);
                    _selectedCard = Math.Max(0,
                        Math.Min(_selectedCard, GetPageCount() - 1));
                    UpdateActiveDicts();
                }
                GbayRenderer.PlayNav(); return;
            }
            if (input.Search && !_vehicleKeyboardActive)
            {
                Function.Call(Hash.DISPLAY_ONSCREEN_KEYBOARD, 0, "FMMC_KEY_TIP8", "",
                    _vehicleSearch, "", "", "", 32);
                _vehicleKeyboardActive = true;
                return;
            }

            // Category tab click
            if (input.MouseClick && _hoverTab >= 0 && _hoverTab != _activeCategoryIndex)
            {
                _activeCategoryIndex = _hoverTab;
                _currentPage = 0;
                _selectedCard = 0;
                RebuildFilteredList();
                GbayRenderer.PlayNav();
                return;
            }

            // Category scroll (Z/X)
            if (input.CategoryPrev && _activeCategoryIndex > 0)
            {
                _activeCategoryIndex--;
                _currentPage = 0;
                _selectedCard = 0;
                EnsureTabVisible(_activeCategoryIndex);
                RebuildFilteredList();
                GbayRenderer.PlayNav();
            }
            else if (input.CategoryNext && _activeCategoryIndex < CATEGORIES.Length - 1)
            {
                _activeCategoryIndex++;
                _currentPage = 0;
                _selectedCard = 0;
                EnsureTabVisible(_activeCategoryIndex);
                RebuildFilteredList();
                GbayRenderer.PlayNav();
            }

            // Page navigation: shoulder keys, mouse wheel, or footer buttons.
            bool previousPage = input.PageLeft || previousPageClicked || input.ScrollDelta < 0;
            bool nextPage = input.PageRight || nextPageClicked || input.ScrollDelta > 0;
            if (previousPage && _currentPage > 0)
            {
                _currentPage--;
                _selectedCard = Math.Min(_selectedCard, GetPageCount() - 1);
                UpdateActiveDicts();
                GbayRenderer.PlayNav();
                return;
            }
            else if (nextPage && _currentPage < _totalPages - 1)
            {
                _currentPage++;
                _selectedCard = Math.Min(_selectedCard, GetPageCount() - 1);
                UpdateActiveDicts();
                GbayRenderer.PlayNav();
                return;
            }

            // Grid navigation (arrows)
            if ((input.DirX != 0 || input.DirY != 0) && _filtered.Count > 0)
            {
                int col = _selectedCard % GRID_COLS;
                int row = _selectedCard / GRID_COLS;
                int maxIdx = GetPageCount() - 1;

                // Crossing an outer grid edge advances to the adjacent page.
                // This lets controller/keyboard users traverse the full catalog
                // without having to move focus down to a separate pager.
                if (input.DirX < 0 && _selectedCard == 0 && _currentPage > 0)
                {
                    _currentPage--;
                    _selectedCard = Math.Max(0, GetPageCount() - 1);
                    UpdateActiveDicts();
                    GbayRenderer.PlayNav();
                    return;
                }
                if (input.DirX > 0 && _selectedCard == maxIdx &&
                    _currentPage < _totalPages - 1)
                {
                    _currentPage++;
                    _selectedCard = 0;
                    UpdateActiveDicts();
                    GbayRenderer.PlayNav();
                    return;
                }
                if (input.DirY < 0 && row == 0 && _currentPage > 0)
                {
                    _currentPage--;
                    _selectedCard = Math.Min(
                        (GRID_ROWS - 1) * GRID_COLS + col, GetPageCount() - 1);
                    UpdateActiveDicts();
                    GbayRenderer.PlayNav();
                    return;
                }
                if (input.DirY > 0 && _selectedCard + GRID_COLS > maxIdx &&
                    _currentPage < _totalPages - 1)
                {
                    _currentPage++;
                    _selectedCard = Math.Min(col, GetPageCount() - 1);
                    UpdateActiveDicts();
                    GbayRenderer.PlayNav();
                    return;
                }

                if (input.DirX != 0)
                    col = Math.Max(0, Math.Min(col + input.DirX, GRID_COLS - 1));
                if (input.DirY != 0)
                    row = Math.Max(0, Math.Min(row + input.DirY, GRID_ROWS - 1));

                int newIdx = Math.Min(row * GRID_COLS + col, maxIdx);
                if (newIdx != _selectedCard)
                {
                    _selectedCard = newIdx;
                    GbayRenderer.PlayNav();
                }
            }

            // Mouse hover updates selection
            if (_hoverCard >= 0 && _hoverCard != _selectedCard)
                _selectedCard = _hoverCard;

            // Select vehicle
            bool accepted = input.Accept || (input.MouseClick && _hoverCard >= 0);
            if (accepted && _filtered.Count > 0)
            {
                int idx = _currentPage * PAGE_SIZE + _selectedCard;
                if (idx < _filtered.Count)
                {
                    VehicleCard card = _filtered[idx];
                    OpenPreview(card);
                }
            }
        }

        // ------------------------------------------------------------------ //
        //  Delivery Confirm Modal                                             //
        // ------------------------------------------------------------------ //

        private void OpenDeliveryConfirm(string model, int price)
        {
            // Check funds
            if (!_shop.FreeMode && price > 0 && Game.Player.Money < price)
            {
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Insufficient funds.~w~ You need ~g~${price:N0}~w~; " +
                    $"your balance is ${Game.Player.Money:N0}.",
                    3000);
                return;
            }

            _pendingModel = model;
            _pendingPrice = price;
            _deliveryGarageIndex = GarageManager.IsPlayerInDavisGarage ? 1
                : GarageManager.IsPlayerInGarmentGarage ? 2 : 0;

            GbayRenderer.PlaySelect();
            _state = BrowserState.DeliveryConfirm;
        }

        private void DrawDeliveryModal(FrameInput input)
        {
            // Modal scrim
            GbayRenderer.DrawRect(0.5f, 0.5f, 1f, 1f, GbayRenderer.ModalScrim);

            // Modal panel
            float modalH = 0.26f;
            float modalTop = 0.5f - modalH / 2f;

            GbayRenderer.DrawBorderedRect(BROWSER_CX, 0.5f, MODAL_W, modalH,
                GbayRenderer.ModalBg, GbayRenderer.CardBorderSel, 0.003f);

            // Title
            string displayName = VehicleList.DisplayNames.ContainsKey(_pendingModel)
                ? VehicleList.DisplayNames[_pendingModel] : _pendingModel;
            GbayRenderer.DrawTitleBadge(displayName, BROWSER_CX,
                modalTop + 0.029f, 0.32f, 0.045f, 0.35f,
                GbayRenderer.FONT_CHALET);

            // Price
            string priceText = _shop.FreeMode || _pendingPrice <= 0
                ? "FREE" : $"${_pendingPrice:N0}";
            GbayRenderer.DrawText(priceText, BROWSER_CX, modalTop + 0.06f,
                0.30f, GbayRenderer.TextPrice, GbayRenderer.FONT_CHALET, true);

            bool oversized = VehicleList.GetSizeTier(_pendingModel) == 2;
            float garageArrowY = modalTop + 0.105f;
            float garageLeftX = BROWSER_CX - 0.19f;
            float garageRightX = BROWSER_CX + 0.19f;
            bool garageLeftHover = !oversized && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, garageLeftX, garageArrowY, 0.035f, 0.035f);
            bool garageRightHover = !oversized && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, garageRightX, garageArrowY, 0.035f, 0.035f);
            if (!oversized && (input.DirX != 0 || input.CategoryPrev ||
                input.CategoryNext || input.MouseClick &&
                (garageLeftHover || garageRightHover)))
            {
                int direction = input.DirX != 0 ? input.DirX
                    : input.CategoryNext || garageRightHover ? 1 : -1;
                _deliveryGarageIndex = (_deliveryGarageIndex + direction + 3) % 3;
                GbayRenderer.PlayNav();
            }

            // Standard vehicles can be delivered to either ten-car garage.
            // Oversized vehicles continue to route to the three-floor garage.
            int used = oversized ? GarageManager.GetFloorGarageUsedSlots()
                : _deliveryGarageIndex == 1
                    ? GarageManager.GetDavisGarageUsedSlots()
                    : _deliveryGarageIndex == 2
                        ? GarageManager.GetGarmentGarageUsedSlots()
                    : GarageManager.GetUsedSlots();
            int cap = oversized ? GarageManager.GetFloorGarageCapacity()
                : _deliveryGarageIndex == 1
                    ? GarageManager.GetDavisGarageCapacity()
                    : _deliveryGarageIndex == 2
                        ? GarageManager.GetGarmentGarageCapacity()
                    : GarageManager.GetCapacity();
            bool isFull = used >= cap;
            string garageName = oversized ? "Three-Floor Garage"
                : _deliveryGarageIndex == 1 ? "Davis Auto Shop"
                : _deliveryGarageIndex == 2 ? "Garment Factory" : "Eclipse Towers";
            string garageInfo = $"{garageName} ({used}/{cap})";
            Color garageColor = isFull ? GbayRenderer.TextDim : GbayRenderer.TextDark;
            GbayRenderer.DrawText(garageInfo, BROWSER_CX, modalTop + 0.09f,
                0.32f, garageColor, GbayRenderer.FONT_CHALET, true);

            if (!oversized)
            {
                GbayRenderer.DrawBorderedRect(garageLeftX, garageArrowY,
                    0.035f, 0.035f,
                    garageLeftHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen,
                    GbayRenderer.CardBorderSel, 0.002f);
                GbayRenderer.DrawBorderedRect(garageRightX, garageArrowY,
                    0.035f, 0.035f,
                    garageRightHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen,
                    GbayRenderer.CardBorderSel, 0.002f);
                GbayRenderer.DrawText("<", garageLeftX, garageArrowY - 0.013f,
                    0.28f, GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);
                GbayRenderer.DrawText(">", garageRightX, garageArrowY - 0.013f,
                    0.28f, GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);
                GbayRenderer.DrawText("Left/Right or Z/X: Choose garage",
                    BROWSER_CX, modalTop + 0.125f, 0.24f,
                    GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true);
            }

            if (isFull)
            {
                GbayRenderer.DrawText("The garage is full.", BROWSER_CX, modalTop + 0.155f,
                    0.28f, Color.FromArgb(255, 200, 80, 80), GbayRenderer.FONT_CONDENSED, true);
            }

            float actionY = modalTop + 0.215f;
            float actionW = 0.15f;
            float confirmX = BROWSER_CX - 0.09f;
            float backX = BROWSER_CX + 0.09f;
            bool confirmHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                confirmX, actionY, actionW, BACK_BTN_H);
            bool backHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                backX, actionY, actionW, BACK_BTN_H);
            Color confirmFill = isFull ? GbayRenderer.BtnGray
                : confirmHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen;
            GbayRenderer.DrawBorderedRect(confirmX, actionY, actionW, BACK_BTN_H,
                confirmFill, confirmHover ? FocusBorderColor() : GbayRenderer.CardBorderSel,
                confirmHover ? FocusBorderWidth() : 0.002f);
            GbayRenderer.DrawText("Confirm", confirmX, actionY - 0.014f, 0.28f,
                GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);
            GbayRenderer.DrawBorderedRect(backX, actionY, actionW, BACK_BTN_H,
                backHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen,
                backHover ? FocusBorderColor() : GbayRenderer.CardBorderSel,
                backHover ? FocusBorderWidth() : 0.002f);
            GbayRenderer.DrawText("Back", backX, actionY - 0.014f, 0.28f,
                GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);

            // Accept
            if ((input.Accept || (input.MouseClick && confirmHover)) && !isFull)
            {
                GbayRenderer.PlaySelect();
                if (!oversized && _deliveryGarageIndex == 1)
                    _shop.ExecuteDeliverToDavisGarage(_pendingModel, _pendingPrice);
                else if (!oversized && _deliveryGarageIndex == 2)
                    _shop.ExecuteDeliverToGarmentGarage(_pendingModel, _pendingPrice);
                else
                    _shop.ExecuteDeliverToGarage(_pendingModel, _pendingPrice);
                ClosePreview();
                _state = BrowserState.VehicleBrowser;
            }

            if (input.Back || input.MouseRightClick || (input.MouseClick && backHover))
            {
                GbayRenderer.PlayBack();
                _state = _previewVehicle != null
                    ? BrowserState.VehiclePreview
                    : BrowserState.VehicleBrowser;
            }
        }

        // ------------------------------------------------------------------ //
        //  Vehicle Preview (3D Showroom)                                      //
        // ------------------------------------------------------------------ //

        private void OpenPreview(VehicleCard card)
        {
            GbayRenderer.PlaySelect();
            GbayPreferences.RecordVehicle(card.Model);

            _previewModel = card.Model;
            _previewDisplayName = card.DisplayName;
            _previewManufacturer = card.Manufacturer;
            _previewPrice = card.Price;
            _previewAngle = 0f;
            _previewZoom = 1.0f;

            // Load model and get dimensions for camera framing
            var model = new Model(_previewModel);
            model.Request(5000);
            int hash = model.Hash;

            OutputArgument minArg = new OutputArgument();
            OutputArgument maxArg = new OutputArgument();
            Function.Call(Hash.GET_MODEL_DIMENSIONS, hash, minArg, maxArg);
            Vector3 vMin = minArg.GetResult<Vector3>();
            Vector3 vMax = maxArg.GetResult<Vector3>();

            float length = Math.Max(vMax.Y - vMin.Y, 3f);
            float width = Math.Max(vMax.X - vMin.X, 2f);
            float height = Math.Max(vMax.Z - vMin.Z, 1.5f);
            float extent = (float)Math.Sqrt(length * length + width * width);

            _previewRadius = extent * 1.2f;
            _previewHeight = height * 0.5f;

            // Spawn vehicle at preview position
            _previewVehicle = VehicleHelper.CreateVehicle(
                _previewModel, PREVIEW_POS, 0f);

            if (_previewVehicle == null)
            {
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle("~r~Failed to load vehicle model.", 3000);
                return;
            }

            _previewVehicle.IsPositionFrozen = true;
            _previewVehicle.IsCollisionEnabled = false;
            _previewVehicle.IsInvincible = true;
            Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, _previewVehicle, 0f);
            Function.Call(Hash.SET_VEHICLE_ON_GROUND_PROPERLY, _previewVehicle);

            // Create camera
            Vector3 camPos = GetOrbitPosition();
            _previewCamera = World.CreateCamera(camPos, Vector3.Zero, 50f);
            _previewCamera.PointAt(_previewVehicle);
            World.RenderingCamera = _previewCamera;

            _state = BrowserState.VehiclePreview;
        }

        private Vector3 GetOrbitPosition()
        {
            float r = _previewRadius * _previewZoom;
            float x = PREVIEW_POS.X + r * (float)Math.Cos(_previewAngle);
            float y = PREVIEW_POS.Y + r * (float)Math.Sin(_previewAngle);
            float z = PREVIEW_POS.Z + _previewHeight;
            return new Vector3(x, y, z);
        }

        private void UpdatePreviewCamera()
        {
            if (_previewCamera == null || _previewVehicle == null)
                return;

            // Auto-orbit
            _previewAngle += Game.LastFrameTime * AUTO_ORBIT_SPEED;

            _previewCamera.Position = GetOrbitPosition();
            _previewCamera.PointAt(_previewVehicle);
        }

        private void DrawPreview(FrameInput input)
        {
            if (_previewVehicle == null || _previewCamera == null)
            {
                _state = BrowserState.VehicleBrowser;
                return;
            }

            // Manual orbit (Left/Right arrows or mouse drag)
            if (input.DirX != 0)
                _previewAngle += input.DirX * MANUAL_ORBIT_SPEED * Game.LastFrameTime * 4f;

            // Zoom (Q/E or scroll)
            if (input.PageLeft)
                _previewZoom = Math.Max(ZOOM_MIN, _previewZoom - ZOOM_SPEED);
            if (input.PageRight)
                _previewZoom = Math.Min(ZOOM_MAX, _previewZoom + ZOOM_SPEED);

            // Auto orbit + update camera
            UpdatePreviewCamera();

            // --- HUD overlay on top of 3D view ---

            // Top bar with vehicle info
            float barH = 0.09f;
            GbayRenderer.DrawRect(0.5f, barH / 2f, 1f, barH,
                Color.FromArgb(180, 0, 0, 0));

            // Manufacturer (small, above name)
            GbayRenderer.DrawText(_previewManufacturer, 0.04f, 0.026f,
                0.30f, GbayRenderer.TextWhite, GbayRenderer.FONT_CONDENSED);

            // Vehicle name
            GbayRenderer.DrawTitleBadge(_previewDisplayName, 0.5f, 0.045f,
                0.40f, 0.064f, 0.48f, GbayRenderer.FONT_CHALET);

            // Price (right side)
            string priceText = _previewPrice <= 0 ? "FREE" : $"${_previewPrice:N0}";
            GbayRenderer.DrawText(priceText, 0.92f, 0.025f,
                0.42f, GbayRenderer.TextPrice, GbayRenderer.FONT_CHALET,
                false, false, true);

            // Bottom bar with controls and the same centered Back action used
            // throughout GBAY.
            float footerY = 0.93f;
            float footerH = 0.07f;
            GbayRenderer.DrawRect(0.5f, footerY + footerH / 2f, 1f, footerH,
                Color.FromArgb(180, 0, 0, 0));
            DrawControlHint("LEFT/RIGHT ROTATE   Q/E ZOOM",
                0.40f, footerY + footerH / 2f, 0.35f, 0.042f);
            DrawControlHint("ENTER PURCHASE",
                0.97f, footerY + footerH / 2f, 0.22f, 0.042f);
            bool backClicked = DrawCenteredBackButton(
                input, footerY + footerH / 2f, 0.14f, "Back", false);

            // Input: Buy
            if (input.Accept)
            {
                OpenDeliveryConfirm(_previewModel, _previewPrice);
            }

            // Input: Back
            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.PlayBack();
                ClosePreview();
                _state = BrowserState.VehicleBrowser;
            }
        }

        private void ClosePreview()
        {
            if (_previewCamera != null)
            {
                World.RenderingCamera = null;
                _previewCamera.Delete();
                _previewCamera = null;
            }

            if (_previewVehicle != null)
            {
                _previewVehicle.Delete();
                _previewVehicle = null;
            }
        }

        // ------------------------------------------------------------------ //
        //  Garage View                                                        //
        // ------------------------------------------------------------------ //

        private void DrawGarageView(FrameInput input)
        {
            // Background
            float bgCY = (BROWSER_TOP + BROWSER_BOTTOM) / 2f;
            float bgH = BROWSER_BOTTOM - BROWSER_TOP;
            GbayRenderer.DrawRect(BROWSER_CX, bgCY, BROWSER_W, bgH,
                GbayRenderer.BodyBg);

            // Header
            GbayRenderer.DrawRect(BROWSER_CX, HEADER_CY, BROWSER_W, HEADER_H,
                GbayRenderer.HeaderBg);
            GbayRenderer.DrawGbayWordmark(
                BROWSER_LEFT + 0.035f, HEADER_Y + 0.010f, 0.43f, true);
            GbayRenderer.DrawTitleBadge(
                "MY GARAGE", BROWSER_LEFT + 0.19f, HEADER_CY,
                0.19f, 0.044f, 0.35f);

            DrawGarageLocationTabs(input);

            bool floorGarage = _garageLocationIndex == 1;
            bool davisGarage = _garageLocationIndex == 2;
            bool garmentGarage = _garageLocationIndex == 3;

            // Capacity info (right side of header)
            int used = floorGarage ? GarageManager.GetFloorGarageUsedSlots()
                : davisGarage ? GarageManager.GetDavisGarageUsedSlots()
                : garmentGarage ? GarageManager.GetGarmentGarageUsedSlots()
                : GarageManager.GetUsedSlots();
            int cap = floorGarage ? GarageManager.GetFloorGarageCapacity()
                : davisGarage ? GarageManager.GetDavisGarageCapacity()
                : garmentGarage ? GarageManager.GetGarmentGarageCapacity()
                : GarageManager.GetCapacity();
            string capText = floorGarage ? $"Three-Floor Garage ({used}/{cap})"
                : davisGarage ? $"Davis Auto Shop ({used}/{cap})"
                : garmentGarage ? $"Garment Factory ({used}/{cap})"
                : $"Eclipse Towers ({used}/{cap})";
            GbayRenderer.DrawTextFit(capText, BROWSER_RIGHT - 0.01f, HEADER_Y + 0.018f,
                0.32f, 0.23f, 0.25f, GbayRenderer.HeaderText,
                GbayRenderer.FONT_CHALET, false, false, true);

            // Vehicle list
            var vehicles = floorGarage ? GarageManager.GetFloorGarageStoredVehicles()
                : davisGarage ? GarageManager.GetDavisGarageStoredVehicles()
                : garmentGarage ? GarageManager.GetGarmentGarageStoredVehicles()
                : GarageManager.GetStoredVehicles();

            float listTop = TAB_Y + TAB_H + 0.015f;
            float itemH = 0.055f;
            const int visibleGarageRows = 12;

            _garageHoverIdx = -1;

            // Keyboard and mouse-wheel navigation. The three-floor garage can
            // hold 15 vehicles, so keep the selected row inside a scrolling
            // 12-row viewport.
            int move = input.DirY != 0 ? input.DirY : input.ScrollDelta;
            if (move != 0 && vehicles.Count > 0)
            {
                int next = Math.Max(0, Math.Min(
                    vehicles.Count - 1, _garageVehicleIdx + move));
                if (next != _garageVehicleIdx)
                {
                    _garageVehicleIdx = next;
                    GbayRenderer.PlayNav();
                }
            }

            if (_garageVehicleIdx >= vehicles.Count)
                _garageVehicleIdx = Math.Max(0, vehicles.Count - 1);
            int firstVisible = Math.Max(0, _garageVehicleIdx - visibleGarageRows + 1);
            firstVisible = Math.Min(firstVisible,
                Math.Max(0, vehicles.Count - visibleGarageRows));
            int lastVisible = Math.Min(vehicles.Count, firstVisible + visibleGarageRows);

            if (vehicles.Count == 0)
            {
                GbayRenderer.DrawText("No vehicles stored.",
                    BROWSER_CX, listTop + 0.10f, 0.35f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);
                string emptyHint = floorGarage
                    ? "Drive a vehicle inside or deliver one to the three-floor garage."
                    : davisGarage
                        ? "Drive a vehicle inside or choose Davis during GBAY delivery."
                    : garmentGarage
                        ? "Drive a vehicle inside or choose Garment Factory during delivery."
                    : "Purchase a vehicle or drive one inside to store it here.";
                GbayRenderer.DrawTextFit(emptyHint,
                    BROWSER_CX, listTop + 0.15f, 0.26f, 0.20f, 0.62f,
                    GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true);
            }
            else
            {
                for (int i = firstVisible; i < lastVisible; i++)
                {
                    var sv = vehicles[i];
                    float itemY = listTop + (i - firstVisible) * itemH;
                    float itemCY = itemY + itemH / 2f;
                    bool isSel = i == _garageVehicleIdx;
                    bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                        BROWSER_CX, itemCY, BROWSER_W - 0.08f, itemH);

                    if (isHover)
                        _garageHoverIdx = i;

                    if (isSel)
                        DrawFocusedRect(BROWSER_CX, itemCY,
                            BROWSER_W - 0.08f, itemH - 0.006f,
                            GbayRenderer.CardSelected);
                    else if (isHover)
                        GbayRenderer.DrawRect(BROWSER_CX, itemCY,
                            BROWSER_W - 0.08f, itemH, GbayRenderer.CardHover);

                    string name = GarageManager.GetVehicleDisplayName(
                        sv.Model, sv.ModelHash);

                    // Slot number
                    string slotLabel = floorGarage
                        ? $"F{sv.Slot / 5 + 1}-{sv.Slot % 5 + 1}"
                        : $"#{sv.Slot + 1}";
                    GbayRenderer.DrawText(slotLabel, BROWSER_LEFT + 0.06f, itemY + 0.012f,
                        0.28f, GbayRenderer.TextMfg, GbayRenderer.FONT_CONDENSED);

                    // Vehicle name
                    GbayRenderer.DrawTextFit(name, BROWSER_LEFT + 0.10f, itemY + 0.012f,
                        0.32f, 0.22f, 0.58f, GbayRenderer.TextDark,
                        GbayRenderer.FONT_CHALET);

                    // Sell button
                    float removeBtnX = BROWSER_RIGHT - 0.08f;
                    bool removeHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                        removeBtnX, itemCY, 0.08f, itemH);

                    Color removeBg = removeHover
                        ? Color.FromArgb(255, 200, 60, 60)
                        : Color.FromArgb(255, 180, 80, 80);
                    GbayRenderer.DrawRect(removeBtnX, itemCY, 0.07f, itemH - 0.01f,
                        removeBg);
                    bool protectedStory = GarageManager.IsProtectedStoryVehicle(
                        sv.Model, sv.PlateText, sv.ModelHash);
                    int sellPrice = _shop.GetSellPrice(
                        sv.Model, sv.PlateText, sv.ModelHash);
                    string sellLabel = protectedStory ? "Protected"
                        : sellPrice > 0 ? $"Sell ${sellPrice:N0}" : "Remove";
                    GbayRenderer.DrawTextFit(sellLabel, removeBtnX, itemY + 0.012f,
                        0.25f, 0.18f, 0.062f, GbayRenderer.TextWhite,
                        GbayRenderer.FONT_CONDENSED, true);

                    if (removeHover && input.MouseClick)
                    {
                        BeginSell(sv.Model, sv.PlateText, sv.ModelHash,
                            i, _garageLocationIndex);
                        return;
                    }
                }
            }

            if (_garageHoverIdx >= 0)
                _garageVehicleIdx = _garageHoverIdx;

            // Keyboard remove
            if (input.Accept && vehicles.Count > 0 && _garageVehicleIdx < vehicles.Count)
            {
                var selected = vehicles[_garageVehicleIdx];
                BeginSell(selected.Model, selected.PlateText, selected.ModelHash,
                    _garageVehicleIdx, _garageLocationIndex);
                return;
            }

            // Eclipse Towers uses a fixed Story Mode interior. The DLC
            // three-floor garage and Davis Auto Shop expose real entity sets.
            bool customizationAvailable = floorGarage || davisGarage;
            if (input.PageLeft && customizationAvailable)
            {
                GbayRenderer.PlaySelect();
                _customFloor = GarageManager.IsPlayerInFloorGarage ? GarageManager.CurrentFloor : 0;
                _customCatIdx = 0;
                _state = BrowserState.GarageCustomize;
                return;
            }

            if (input.FilterNext)
            {
                GarageManager.EmergencyRecover();
                GbayRenderer.PlaySelect();
                GTA.UI.Screen.ShowSubtitle("~g~Garage recovery complete. You were moved outside.", 3500);
                _state = BrowserState.TopMenu;
                return;
            }

            // Footer
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);
            bool backClicked = DrawCenteredBackButton(input);

            // Keep the action on the left so every page can reserve the lower
            // right for its consistent high-contrast control legend.
            float custBtnX = BROWSER_LEFT + 0.10f;
            float custBtnW = 0.16f;
            bool custHover = customizationAvailable && GbayRenderer.HitTest(input.MouseX, input.MouseY,
                custBtnX, FOOTER_CY, custBtnW, FOOTER_H);
            Color custBg = !customizationAvailable
                ? GbayRenderer.CardBorder
                : custHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen;
            GbayRenderer.DrawRect(custBtnX, FOOTER_CY, custBtnW, FOOTER_H - 0.01f, custBg);
            string customizeLabel = !customizationAvailable ? "Fixed Interior"
                : davisGarage ? "Customize Auto Shop" : "Customize Three Floors";
            GbayRenderer.DrawTextFit(customizeLabel,
                custBtnX, FOOTER_Y + 0.012f,
                0.26f, 0.19f, custBtnW - 0.014f,
                customizationAvailable ? GbayRenderer.TextWhite : GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED, true);

            if (custHover && input.MouseClick)
            {
                GbayRenderer.PlaySelect();
                _customFloor = GarageManager.IsPlayerInFloorGarage ? GarageManager.CurrentFloor : 0;
                _customCatIdx = 0;
                _state = BrowserState.GarageCustomize;
                return;
            }

            DrawControlHint(
                "ARROWS BROWSE/GARAGE   ENTER SELL   Y RECOVER");

            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
            }
        }

        private void DrawGarageLocationTabs(FrameInput input)
        {
            const float tabW = 0.165f;
            float[] tabX =
            {
                BROWSER_CX - tabW * 1.5f, BROWSER_CX - tabW * 0.5f,
                BROWSER_CX + tabW * 0.5f, BROWSER_CX + tabW * 1.5f,
            };
            string[] labels =
            {
                "Eclipse Towers", "Three-Floor", "Davis Auto Shop", "Garment Factory",
            };

            for (int i = 0; i < labels.Length; i++)
            {
                bool hover = GbayRenderer.HitTest(
                    input.MouseX, input.MouseY, tabX[i], TAB_CY, tabW, TAB_H);
                if (i == _garageLocationIndex)
                    DrawFocusedRect(tabX[i], TAB_CY, tabW - 0.006f,
                        TAB_H - 0.006f, GbayRenderer.BtnGreenHover);
                else if (hover)
                    GbayRenderer.DrawRect(
                        tabX[i], TAB_CY, tabW - 0.004f, TAB_H, GbayRenderer.TabHover);
                if (i == _garageLocationIndex)
                    GbayRenderer.DrawRect(tabX[i], TAB_Y + TAB_H - 0.004f,
                        tabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);
                GbayRenderer.DrawText(labels[i], tabX[i], TAB_Y + 0.012f, 0.28f,
                    i == _garageLocationIndex
                        ? GbayRenderer.TabActive : GbayRenderer.TabInactive,
                    GbayRenderer.FONT_CONDENSED, true);

                if (hover && input.MouseClick && i != _garageLocationIndex)
                    SetGarageLocation(i);
            }

            if ((input.DirX < 0 || input.CategoryPrev) && _garageLocationIndex > 0)
                SetGarageLocation(_garageLocationIndex - 1);
            else if ((input.DirX > 0 || input.CategoryNext) && _garageLocationIndex < 3)
                SetGarageLocation(_garageLocationIndex + 1);
        }

        private void SetGarageLocation(int location)
        {
            _garageLocationIndex = Math.Max(0, Math.Min(3, location));
            _garageVehicleIdx = 0;
            _garageHoverIdx = -1;
            GbayRenderer.PlayNav();
        }

        private void BeginSell(string model, string plateText, int modelHash,
            int index, int garageLocation)
        {
            if (GarageManager.IsProtectedStoryVehicle(
                    model, plateText, modelHash))
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Story-owned personal vehicles cannot be sold.", 3000);
                ClientLog.Warn("GBAY", "vehicle_sale_rejected", new Dictionary<string, object> {
                    { "model", model }, { "reason", "protected_story_vehicle" }
                });
                return;
            }
            _pendingSellModel = model;
            _pendingSellPlate = plateText ?? "";
            _pendingSellModelHash = modelHash;
            _pendingSellIndex = index;
            _pendingSellGarageLocation = garageLocation;
            _state = BrowserState.GarageSellConfirm;
            GbayRenderer.PlaySelect();
        }

        private void DrawGarageSellConfirm(FrameInput input)
        {
            DrawGarageView(new FrameInput());
            GbayRenderer.DrawRect(BROWSER_CX, 0.5f, 1f, 1f, GbayRenderer.ModalScrim);
            GbayRenderer.DrawRect(BROWSER_CX, 0.5f, MODAL_W, 0.30f, GbayRenderer.ModalBg);
            string name = GarageManager.GetVehicleDisplayName(
                _pendingSellModel, _pendingSellModelHash);
            int value = _shop.GetSellPrice(
                _pendingSellModel, _pendingSellPlate, _pendingSellModelHash);
            GbayRenderer.DrawTitleBadge(
                "CONFIRM VEHICLE SALE", BROWSER_CX, 0.405f,
                0.30f, 0.055f, 0.40f);
            GbayRenderer.DrawText(name, BROWSER_CX, 0.46f, 0.38f,
                GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);
            GbayRenderer.DrawText(value > 0 ? $"Sale value: ${value:N0}" : "Remove from garage (no credit)",
                BROWSER_CX, 0.52f, 0.34f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);
            const float sellActionY = 0.61f;
            const float sellActionW = 0.15f;
            float sellConfirmX = BROWSER_CX - 0.09f;
            float sellBackX = BROWSER_CX + 0.09f;
            bool sellConfirmHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                sellConfirmX, sellActionY, sellActionW, BACK_BTN_H);
            bool sellBackHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                sellBackX, sellActionY, sellActionW, BACK_BTN_H);
            GbayRenderer.DrawBorderedRect(sellConfirmX, sellActionY, sellActionW, BACK_BTN_H,
                sellConfirmHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen,
                sellConfirmHover ? FocusBorderColor() : GbayRenderer.CardBorderSel,
                sellConfirmHover ? FocusBorderWidth() : 0.002f);
            GbayRenderer.DrawText("Confirm", sellConfirmX, sellActionY - 0.014f, 0.28f,
                GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);
            GbayRenderer.DrawBorderedRect(sellBackX, sellActionY, sellActionW, BACK_BTN_H,
                sellBackHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen,
                sellBackHover ? FocusBorderColor() : GbayRenderer.CardBorderSel,
                sellBackHover ? FocusBorderWidth() : 0.002f);
            GbayRenderer.DrawText("Back", sellBackX, sellActionY - 0.014f, 0.28f,
                GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);
            if (input.Accept || (input.MouseClick && sellConfirmHover))
            {
                _shop.ExecuteSellVehicle(
                    _pendingSellModel, _pendingSellIndex, _pendingSellGarageLocation,
                    _pendingSellPlate, _pendingSellModelHash);
                _garageVehicleIdx = Math.Max(0, _pendingSellIndex - 1);
                _pendingSellIndex = -1;
                _pendingSellModel = "";
                _pendingSellPlate = "";
                _pendingSellModelHash = 0;
                _pendingSellGarageLocation = 0;
                _state = BrowserState.GarageView;
            }
            else if (input.Back || input.MouseRightClick ||
                     (input.MouseClick && sellBackHover))
            {
                _pendingSellIndex = -1;
                _pendingSellModel = "";
                _pendingSellPlate = "";
                _pendingSellModelHash = 0;
                _pendingSellGarageLocation = 0;
                _state = BrowserState.GarageView;
                GbayRenderer.PlayBack();
            }
        }

        // ------------------------------------------------------------------ //
        //  Weapon Browser                                                     //
        // ------------------------------------------------------------------ //

        private void DrawWeaponBrowser(FrameInput input)
        {
            UpdateWeaponSearchKeyboard();
            float aspect = GbayRenderer.GetAspectRatio();
            float cardW = CARD_H / aspect;

            // Browser background
            float bgCY = (BROWSER_TOP + BROWSER_BOTTOM) / 2f;
            float bgH = BROWSER_BOTTOM - BROWSER_TOP;
            GbayRenderer.DrawRect(BROWSER_CX, bgCY, BROWSER_W, bgH,
                GbayRenderer.BodyBg);

            // Header
            DrawWeaponHeader();

            // Category tabs
            DrawWeaponCategoryTabs(input, aspect);

            // Grid
            DrawWeaponGrid(input, cardW);

            // Footer
            bool previousPageClicked;
            bool nextPageClicked;
            bool backClicked = DrawWeaponFooter(
                input, out previousPageClicked, out nextPageClicked);

            // Handle input
            HandleWeaponBrowserInput(
                input, backClicked, previousPageClicked, nextPageClicked);
        }

        private void DrawWeaponHeader()
        {
            GbayRenderer.DrawRect(BROWSER_CX, HEADER_CY, BROWSER_W, HEADER_H,
                GbayRenderer.HeaderBg);

            GbayRenderer.DrawGbayWordmark(
                BROWSER_LEFT + 0.035f, HEADER_Y + 0.010f, 0.43f, true);

            GbayRenderer.DrawTitleBadge(
                "WEAPONS", BROWSER_LEFT + 0.18f, HEADER_CY,
                0.17f, 0.044f, 0.35f);

            string money = $"${Game.Player.Money:N0}";
            GbayRenderer.DrawText(money, BROWSER_RIGHT - 0.01f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.HeaderText, GbayRenderer.FONT_CHALET,
                false, false, true);
        }

        private void DrawWeaponCategoryTabs(FrameInput input, float aspect)
        {
            GbayRenderer.DrawRect(BROWSER_CX, TAB_CY, BROWSER_W, TAB_H,
                GbayRenderer.TabBg);

            int visibleCount = Math.Min(MAX_VISIBLE_TABS, WEAPON_CATEGORIES.Length - _weaponTabScrollOffset);
            const float arrowW = 0.032f;
            float tabAreaW = BROWSER_W - arrowW * 2f - 0.016f;
            float singleTabW = tabAreaW / MAX_VISIBLE_TABS;
            float tabStartX = BROWSER_LEFT + arrowW + 0.008f;

            _weaponHoverTab = -1;

            for (int i = 0; i < visibleCount; i++)
            {
                int catIdx = _weaponTabScrollOffset + i;
                float tabCX = tabStartX + singleTabW * i + singleTabW / 2f;
                bool isActive = catIdx == _weaponCategoryIndex;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    tabCX, TAB_CY, singleTabW - 0.004f, TAB_H);

                if (isHover)
                    _weaponHoverTab = catIdx;

                if (isActive)
                    DrawFocusedRect(tabCX, TAB_CY, singleTabW - 0.006f,
                        TAB_H - 0.006f, GbayRenderer.BtnGreenHover);
                else if (isHover)
                    GbayRenderer.DrawRect(tabCX, TAB_CY, singleTabW - 0.004f,
                        TAB_H, GbayRenderer.TabHover);

                if (isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_Y + TAB_H - 0.004f,
                        singleTabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);

                Color textColor = isActive ? GbayRenderer.TabActive : GbayRenderer.TabInactive;
                string label = WEAPON_CATEGORIES[catIdx].Label;
                GbayRenderer.DrawTextFit(label, tabCX, TAB_Y + 0.01f,
                    0.32f, 0.22f, singleTabW - 0.012f, textColor,
                    GbayRenderer.FONT_CONDENSED, true);
            }

            float leftArrowX = BROWSER_LEFT + arrowW / 2f;
            float rightArrowX = BROWSER_RIGHT - arrowW / 2f;
            bool canScrollLeft = _weaponTabScrollOffset > 0;
            bool canScrollRight = _weaponTabScrollOffset + MAX_VISIBLE_TABS < WEAPON_CATEGORIES.Length;
            bool leftHover = canScrollLeft && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, leftArrowX, TAB_CY, arrowW, TAB_H);
            bool rightHover = canScrollRight && GbayRenderer.HitTest(
                input.MouseX, input.MouseY, rightArrowX, TAB_CY, arrowW, TAB_H);
            GbayRenderer.DrawRect(leftArrowX, TAB_CY, arrowW, TAB_H,
                leftHover ? GbayRenderer.BtnGreenHover : GbayRenderer.TabBg);
            GbayRenderer.DrawRect(rightArrowX, TAB_CY, arrowW, TAB_H,
                rightHover ? GbayRenderer.BtnGreenHover : GbayRenderer.TabBg);
            if (canScrollLeft)
            {
                GbayRenderer.DrawText("<", leftArrowX, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET, true);
            }
            if (canScrollRight)
            {
                GbayRenderer.DrawText(">", rightArrowX, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET, true);
            }
            if (input.MouseClick && leftHover)
            {
                _weaponTabScrollOffset = Math.Max(0,
                    _weaponTabScrollOffset - (MAX_VISIBLE_TABS - 1));
                GbayRenderer.PlayNav();
            }
            else if (input.MouseClick && rightHover)
            {
                _weaponTabScrollOffset = Math.Min(
                    Math.Max(0, WEAPON_CATEGORIES.Length - MAX_VISIBLE_TABS),
                    _weaponTabScrollOffset + (MAX_VISIBLE_TABS - 1));
                GbayRenderer.PlayNav();
            }
        }

        private void DrawWeaponGrid(FrameInput input, float cardW)
        {
            float gridW = GRID_COLS * cardW + (GRID_COLS - 1) * CARD_GAP_X;
            float gridStartX = BROWSER_CX - gridW / 2f;
            float gridStartY = GRID_TOP + 0.01f;

            int startIdx = _weaponPage * PAGE_SIZE;
            int count = Math.Min(PAGE_SIZE, _weaponFiltered.Count - startIdx);

            _weaponHoverCard = -1;

            for (int i = 0; i < count; i++)
            {
                int col = i % GRID_COLS;
                int row = i / GRID_COLS;
                float cardLeft = gridStartX + col * (cardW + CARD_GAP_X);
                float cardTop = gridStartY + row * (CARD_H + CARD_GAP_Y);
                float cardCX = cardLeft + cardW / 2f;
                float cardCY = cardTop + CARD_H / 2f;

                bool isSelected = i == _weaponSelectedCard;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    cardCX, cardCY, cardW, CARD_H);

                if (isHover)
                    _weaponHoverCard = i;

                WeaponCard card = _weaponFiltered[startIdx + i];
                DrawWeaponCard(card, cardLeft, cardTop, cardW, isSelected, isHover);
            }

            if (count == 0)
            {
                GbayRenderer.DrawText("No weapons in this category",
                    BROWSER_CX, 0.45f, 0.4f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);
            }
        }

        private void DrawWeaponCard(WeaponCard card, float left, float top,
                                     float cardW, bool selected, bool hovered)
        {
            float cx = left + cardW / 2f;
            float cy = top + CARD_H / 2f;

            Color bgColor = selected ? GbayRenderer.CardSelected
                          : hovered ? GbayRenderer.CardHover
                          : GbayRenderer.CardBg;
            Color borderColor = selected ? FocusBorderColor()
                              : GbayRenderer.CardBorder;

            GbayRenderer.DrawBorderedRect(cx, cy, cardW, CARD_H,
                bgColor, borderColor, selected ? FocusBorderWidth() : 0.002f);

            // Top area: category-colored placeholder (55% of card height)
            float topAreaH = CARD_H * 0.55f;
            float topAreaCY = top + topAreaH / 2f;

            GbayRenderer.DrawRect(cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f,
                Color.FromArgb(255, 30, 35, 32));
            bool previewDrawn = GbayRenderer.DrawWeaponPreviewTexture(
                card.WeaponName, cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f);
            if (!previewDrawn)
            {
                Color topColor = GetWeaponCategoryColor(card.Category, hovered || selected);
                GbayRenderer.DrawRect(cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f,
                    topColor);

                // Readable category fallback while a capture is unavailable.
                GbayRenderer.DrawTextFit(card.Category, cx, top + topAreaH * 0.35f,
                    0.28f, 0.20f, cardW - 0.018f, GbayRenderer.TextDark,
                    GbayRenderer.FONT_CONDENSED, true);
            }

            // Text area below
            float textTop = top + topAreaH + 0.005f;
            float textLeft = left + 0.008f;

            // Weapon name
            GbayRenderer.DrawTextFit(card.DisplayName, textLeft, textTop + 0.005f,
                0.33f, 0.22f, cardW - 0.016f, GbayRenderer.TextDark,
                GbayRenderer.FONT_CHALET);

            // Price, OWNED status, or ammo info
            if (card.Owned)
            {
                // Check if this card has a pending ammo confirm
                bool isPendingConfirm = _ammoConfirmPending &&
                    card.WeaponName == _ammoConfirmWeapon;

                if (isPendingConfirm)
                {
                    // Highlight border for pending confirm
                    GbayRenderer.DrawBorderedRect(cx, cy, cardW, CARD_H,
                        bgColor, Color.FromArgb(255, 255, 200, 50), 0.003f);

                    string confirmText = _ammoConfirmCost > 0
                        ? $"REFILL {_ammoConfirmRounds} rnds - ${_ammoConfirmCost:N0}"
                        : $"REFILL {_ammoConfirmRounds} rnds - FREE";
                    GbayRenderer.DrawTextFit(confirmText, textLeft, textTop + 0.038f,
                        0.24f, 0.17f, cardW - 0.016f,
                        Color.FromArgb(255, 168, 104, 0), GbayRenderer.FONT_CONDENSED);
                }
                else
                {
                    // Show ammo status
                    int rounds;
                    int cost = _shop.GetAmmoRefillInfo(card.WeaponName, out rounds);

                    if (cost == GbayShop.AmmoCapacityUnavailable)
                    {
                        GbayRenderer.DrawTextFit("AMMO DATA UNAVAILABLE", textLeft,
                            textTop + 0.038f, 0.24f, 0.17f, cardW - 0.016f,
                            Color.FromArgb(255, 180, 70, 45), GbayRenderer.FONT_CONDENSED);
                    }
                    else if (cost == GbayShop.AmmoNotApplicable)
                    {
                        // Melee / no-ammo
                        GbayRenderer.DrawText("OWNED", textLeft, textTop + 0.038f,
                            0.30f, GbayRenderer.TextPriceFree, GbayRenderer.FONT_CHALET);
                    }
                    else if (cost == 0 && rounds == 0)
                    {
                        GbayRenderer.DrawTextFit("FULLY STOCKED", textLeft, textTop + 0.038f,
                            0.26f, 0.20f, cardW - 0.016f,
                            GbayRenderer.TextPriceFree, GbayRenderer.FONT_CONDENSED);
                    }
                    else
                    {
                        string ammoText = cost > 0
                            ? $"OWNED - Refill ${cost:N0}"
                            : $"OWNED - Refill {rounds} rnds";
                        GbayRenderer.DrawTextFit(ammoText, textLeft, textTop + 0.038f,
                            0.24f, 0.17f, cardW - 0.016f,
                            Color.FromArgb(255, 150, 100, 0), GbayRenderer.FONT_CONDENSED);
                    }
                }
            }
            else
            {
                string priceText;
                if (!card.PurchaseAvailable)
                    priceText = "PRICE UNAVAILABLE";
                else if (card.QuantityPriced && card.Price > 0)
                    priceText = $"{card.PurchaseQuantity} x ${card.UnitPrice:N0} = ${card.Price:N0}";
                else if (card.QuantityPriced)
                    priceText = $"{card.PurchaseQuantity} ITEMS - FREE";
                else
                    priceText = card.Price <= 0 ? "FREE" : $"${card.Price:N0}";
                Color priceColor = card.Price <= 0
                    ? GbayRenderer.TextPriceFree : GbayRenderer.TextPrice;
                GbayRenderer.DrawTextFit(priceText, textLeft, textTop + 0.038f,
                    0.30f, 0.19f, cardW - 0.016f,
                    card.PurchaseAvailable ? priceColor
                        : Color.FromArgb(255, 180, 70, 45),
                    GbayRenderer.FONT_CHALET);
            }
        }

        private bool DrawWeaponFooter(
            FrameInput input, out bool previousPageClicked, out bool nextPageClicked)
        {
            previousPageClicked = false;
            nextPageClicked = false;
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                _ammoConfirmPending
                    ? Color.FromArgb(230, 60, 50, 20)
                    : GbayRenderer.FooterBg);

            if (_ammoConfirmPending)
            {
                string displayName = WeaponList.DisplayNames.ContainsKey(_ammoConfirmWeapon)
                    ? WeaponList.DisplayNames[_ammoConfirmWeapon] : _ammoConfirmWeapon;
                string costText = _ammoConfirmCost > 0
                    ? $"${_ammoConfirmCost:N0}" : "FREE";
                string prompt = $"ENTER CONFIRM {displayName} " +
                    $"({_ammoConfirmRounds}) {costText}   ESC CANCEL";
                DrawControlHint(prompt, BROWSER_RIGHT - 0.01f,
                    FOOTER_CY, 0.52f, 0.038f);
                return false;
            }
            else
            {
                DrawPager(input, _weaponPage, _weaponTotalPages, _weaponFiltered.Count,
                    out previousPageClicked, out nextPageClicked);

                bool backClicked = DrawCenteredBackButton(input);

                string filter = _weaponOwnershipFilter == 1 ? "OWNED"
                    : _weaponOwnershipFilter == 2 ? "AVAILABLE" : "ALL";
                string search = _weaponSearch.Length > 0 ? "SEARCH ON" : "SEARCH";
                string hints = $"Y {filter}   X {search}   R3 FAVORITE   LB/RB PAGES";
                DrawControlHint(hints);
                return backClicked;
            }
        }

        private void HandleWeaponBrowserInput(
            FrameInput input, bool backClicked,
            bool previousPageClicked, bool nextPageClicked)
        {
            // Handle pending ammo confirm first
            if (_ammoConfirmPending)
            {
                if (input.Accept || (input.MouseClick && _weaponHoverCard >= 0
                    && _weaponPage * PAGE_SIZE + _weaponHoverCard == _ammoConfirmCardIdx))
                {
                    GbayRenderer.PlaySelect();
                    _shop.ExecuteRefillAmmo(_ammoConfirmWeapon);
                    _ammoConfirmPending = false;
                    RebuildWeaponFilteredList();
                    return;
                }

                if (input.Back || input.MouseRightClick)
                {
                    GbayRenderer.PlayBack();
                    _ammoConfirmPending = false;
                    return;
                }

                // While confirm is pending, block other inputs
                return;
            }

            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
                return;
            }

            if (input.FilterNext)
            {
                _weaponOwnershipFilter = (_weaponOwnershipFilter + 1) % 3;
                _weaponPage = 0; _weaponSelectedCard = 0;
                RebuildWeaponFilteredList(); GbayRenderer.PlayNav(); return;
            }
            if (input.Favorite && _weaponFiltered.Count > 0)
            {
                int favoriteIdx = _weaponPage * PAGE_SIZE + _weaponSelectedCard;
                if (favoriteIdx < _weaponFiltered.Count)
                    GbayPreferences.ToggleWeapon(_weaponFiltered[favoriteIdx].WeaponName);
                if (WEAPON_CATEGORIES[_weaponCategoryIndex].FavoritesOnly)
                {
                    RebuildWeaponFilteredList();
                    _weaponPage = Math.Min(_weaponPage, _weaponTotalPages - 1);
                    _weaponSelectedCard = Math.Max(0,
                        Math.Min(_weaponSelectedCard, GetWeaponPageCount() - 1));
                }
                GbayRenderer.PlayNav(); return;
            }
            if (input.Search && !_weaponKeyboardActive)
            {
                Function.Call(Hash.DISPLAY_ONSCREEN_KEYBOARD, 0, "FMMC_KEY_TIP8", "",
                    _weaponSearch, "", "", "", 32);
                _weaponKeyboardActive = true;
                return;
            }

            // Category tab click
            if (input.MouseClick && _weaponHoverTab >= 0 && _weaponHoverTab != _weaponCategoryIndex)
            {
                _weaponCategoryIndex = _weaponHoverTab;
                _weaponPage = 0;
                _weaponSelectedCard = 0;
                RebuildWeaponFilteredList();
                GbayRenderer.PlayNav();
                return;
            }

            // Category scroll (Z/X)
            if (input.CategoryPrev && _weaponCategoryIndex > 0)
            {
                _weaponCategoryIndex--;
                _weaponPage = 0;
                _weaponSelectedCard = 0;
                EnsureWeaponTabVisible(_weaponCategoryIndex);
                RebuildWeaponFilteredList();
                GbayRenderer.PlayNav();
            }
            else if (input.CategoryNext && _weaponCategoryIndex < WEAPON_CATEGORIES.Length - 1)
            {
                _weaponCategoryIndex++;
                _weaponPage = 0;
                _weaponSelectedCard = 0;
                EnsureWeaponTabVisible(_weaponCategoryIndex);
                RebuildWeaponFilteredList();
                GbayRenderer.PlayNav();
            }

            // Page navigation: shoulder keys, mouse wheel, or footer buttons.
            bool previousPage = input.PageLeft || previousPageClicked || input.ScrollDelta < 0;
            bool nextPage = input.PageRight || nextPageClicked || input.ScrollDelta > 0;
            if (previousPage && _weaponPage > 0)
            {
                _weaponPage--;
                _weaponSelectedCard = Math.Min(_weaponSelectedCard, GetWeaponPageCount() - 1);
                GbayRenderer.PlayNav();
                return;
            }
            else if (nextPage && _weaponPage < _weaponTotalPages - 1)
            {
                _weaponPage++;
                _weaponSelectedCard = Math.Min(_weaponSelectedCard, GetWeaponPageCount() - 1);
                GbayRenderer.PlayNav();
                return;
            }

            // Grid navigation (arrows)
            if ((input.DirX != 0 || input.DirY != 0) && _weaponFiltered.Count > 0)
            {
                int col = _weaponSelectedCard % GRID_COLS;
                int row = _weaponSelectedCard / GRID_COLS;
                int maxIdx = GetWeaponPageCount() - 1;

                if (input.DirX < 0 && _weaponSelectedCard == 0 && _weaponPage > 0)
                {
                    _weaponPage--;
                    _weaponSelectedCard = Math.Max(0, GetWeaponPageCount() - 1);
                    GbayRenderer.PlayNav();
                    return;
                }
                if (input.DirX > 0 && _weaponSelectedCard == maxIdx &&
                    _weaponPage < _weaponTotalPages - 1)
                {
                    _weaponPage++;
                    _weaponSelectedCard = 0;
                    GbayRenderer.PlayNav();
                    return;
                }
                if (input.DirY < 0 && row == 0 && _weaponPage > 0)
                {
                    _weaponPage--;
                    _weaponSelectedCard = Math.Min(
                        (GRID_ROWS - 1) * GRID_COLS + col, GetWeaponPageCount() - 1);
                    GbayRenderer.PlayNav();
                    return;
                }
                if (input.DirY > 0 && _weaponSelectedCard + GRID_COLS > maxIdx &&
                    _weaponPage < _weaponTotalPages - 1)
                {
                    _weaponPage++;
                    _weaponSelectedCard = Math.Min(col, GetWeaponPageCount() - 1);
                    GbayRenderer.PlayNav();
                    return;
                }

                if (input.DirX != 0)
                    col = Math.Max(0, Math.Min(col + input.DirX, GRID_COLS - 1));
                if (input.DirY != 0)
                    row = Math.Max(0, Math.Min(row + input.DirY, GRID_ROWS - 1));

                int newIdx = Math.Min(row * GRID_COLS + col, maxIdx);
                if (newIdx != _weaponSelectedCard)
                {
                    _weaponSelectedCard = newIdx;
                    GbayRenderer.PlayNav();
                }
            }

            // Mouse hover updates selection
            if (_weaponHoverCard >= 0 && _weaponHoverCard != _weaponSelectedCard)
                _weaponSelectedCard = _weaponHoverCard;

            // Select weapon (purchase or ammo refill)
            bool accepted = input.Accept || (input.MouseClick && _weaponHoverCard >= 0);
            if (accepted && _weaponFiltered.Count > 0)
            {
                int idx = _weaponPage * PAGE_SIZE + _weaponSelectedCard;
                if (idx < _weaponFiltered.Count)
                {
                    WeaponCard card = _weaponFiltered[idx];

                    if (card.Owned)
                    {
                        // Owned weapon — prompt for ammo refill
                        int rounds;
                        int cost = _shop.GetAmmoRefillInfo(card.WeaponName, out rounds);

                        if (cost == GbayShop.AmmoCapacityUnavailable)
                        {
                            GbayRenderer.PlayError();
                            GTA.UI.Screen.ShowSubtitle(
                                "~r~Ammo data is unavailable for this weapon.", 3000);
                        }
                        else if (cost == GbayShop.AmmoNotApplicable)
                        {
                            // Melee / no-ammo weapon
                            GbayRenderer.PlayError();
                            GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                        }
                        else if (cost == 0 && rounds == 0)
                        {
                            // Fully stocked
                            GbayRenderer.PlayError();
                            GTA.UI.Screen.ShowSubtitle("~g~Already fully stocked.", 3000);
                        }
                        else
                        {
                            // Show ammo confirm
                            GbayRenderer.PlaySelect();
                            _ammoConfirmPending = true;
                            _ammoConfirmWeapon = card.WeaponName;
                            _ammoConfirmCost = cost;
                            _ammoConfirmRounds = rounds;
                            _ammoConfirmCardIdx = idx;
                        }
                    }
                    else
                    {
                        // Not owned — purchase weapon
                        if (!card.PurchaseAvailable)
                        {
                            GbayRenderer.PlayError();
                            GTA.UI.Screen.ShowSubtitle(
                                "~r~Purchase quantity is unavailable for this item.", 3000);
                            return;
                        }
                        GbayRenderer.PlaySelect();
                        _shop.ExecuteGiveWeapon(card.WeaponName, card.UnitPrice);
                        RebuildWeaponFilteredList();
                    }
                }
            }
        }

        private void RebuildWeaponFilteredList()
        {
            _weaponFiltered.Clear();

            Ped player = Game.Player.Character;
            WeaponCategory activeCategory = WEAPON_CATEGORIES[_weaponCategoryIndex];
            string[] weapons = activeCategory.Weapons;

            foreach (string weaponName in weapons)
            {
                string displayName = WeaponList.DisplayNames.ContainsKey(weaponName)
                    ? WeaponList.DisplayNames[weaponName] : weaponName;

                int price = 0;
                if (WeaponList.Prices.ContainsKey(weaponName))
                    price = WeaponList.Prices[weaponName];

                string category = WeaponList.CategoryNames.ContainsKey(weaponName)
                    ? WeaponList.CategoryNames[weaponName] : "";
                WeaponPurchaseQuote quote = _shop.GetWeaponPurchaseQuote(
                    weaponName, price);

                // Check if player already owns this weapon
                Hash weaponHash = (Hash)CharacterInventory.GetWeaponHash(weaponName);
                bool owned = Function.Call<bool>(
                    (Hash)0x8DECB02F88F428BC, player, weaponHash, false) ||
                    CharacterInventory.IsOwned(weaponName, false);  // HAS_PED_GOT_WEAPON

                if (_weaponOwnershipFilter == 1 && !owned) continue;
                if (_weaponOwnershipFilter == 2 && owned) continue;
                if (activeCategory.FavoritesOnly &&
                    !GbayPreferences.IsWeaponFavorite(weaponName)) continue;
                if (_weaponSearch.Length > 0 &&
                    displayName.IndexOf(_weaponSearch, StringComparison.OrdinalIgnoreCase) < 0 &&
                    weaponName.IndexOf(_weaponSearch, StringComparison.OrdinalIgnoreCase) < 0)
                    continue;

                _weaponFiltered.Add(new WeaponCard
                {
                    WeaponName = weaponName,
                    DisplayName = displayName,
                    Category = category,
                    UnitPrice = price,
                    Price = quote.TotalPrice,
                    PurchaseQuantity = quote.Quantity,
                    QuantityPriced = quote.QuantityPriced,
                    PurchaseAvailable = quote.Status == WeaponPurchaseStatus.Available,
                    Owned = owned,
                });
            }

            _weaponTotalPages = Math.Max(1, (_weaponFiltered.Count + PAGE_SIZE - 1) / PAGE_SIZE);
        }

        private void UpdateWeaponSearchKeyboard()
        {
            if (!_weaponKeyboardActive) return;
            int status = Function.Call<int>(Hash.UPDATE_ONSCREEN_KEYBOARD);
            if (status == 0) return;
            if (status == 1)
                _weaponSearch = Function.Call<string>(Hash.GET_ONSCREEN_KEYBOARD_RESULT) ?? "";
            _weaponKeyboardActive = false;
            _weaponPage = 0; _weaponSelectedCard = 0;
            RebuildWeaponFilteredList();
        }

        private static Color GetWeaponCategoryColor(string category, bool bright)
        {
            int r, g, b;
            switch (category)
            {
                case "Pistols":        r = 140; g = 160; b = 200; break;
                case "SMGs":           r = 160; g = 140; b = 180; break;
                case "Shotguns":       r = 200; g = 140; b = 120; break;
                case "Assault Rifles": r = 140; g = 180; b = 140; break;
                case "Machine Guns":   r = 180; g = 160; b = 120; break;
                case "Sniper Rifles":  r = 120; g = 160; b = 180; break;
                case "Heavy Weapons":  r = 200; g = 130; b = 130; break;
                case "Melee":          r = 170; g = 170; b = 150; break;
                case "Throwables":     r = 200; g = 170; b = 100; break;
                case "Miscellaneous":  r = 160; g = 160; b = 160; break;
                default:               r = 180; g = 190; b = 185; break;
            }

            if (bright)
            {
                r = Math.Min(255, r + 20);
                g = Math.Min(255, g + 20);
                b = Math.Min(255, b + 20);
            }

            return Color.FromArgb(255, r, g, b);
        }

        private void EnsureWeaponTabVisible(int categoryIndex)
        {
            if (categoryIndex < _weaponTabScrollOffset)
                _weaponTabScrollOffset = categoryIndex;
            else if (categoryIndex >= _weaponTabScrollOffset + MAX_VISIBLE_TABS)
                _weaponTabScrollOffset = categoryIndex - MAX_VISIBLE_TABS + 1;
        }

        private int GetWeaponPageCount()
        {
            int startIdx = _weaponPage * PAGE_SIZE;
            return Math.Min(PAGE_SIZE, _weaponFiltered.Count - startIdx);
        }

        // ------------------------------------------------------------------ //
        //  Helpers                                                            //
        // ------------------------------------------------------------------ //

        private static Color GetCategoryColor(string model, bool bright)
        {
            string cls = VehicleList.ClassNames.ContainsKey(model)
                ? VehicleList.ClassNames[model] : "";

            // Each class gets a distinct muted color for visual variety
            int r, g, b;
            switch (cls)
            {
                case "Compacts":       r = 100; g = 170; b = 200; break;
                case "Coupes":         r = 160; g = 140; b = 200; break;
                case "Sedans":         r = 140; g = 160; b = 180; break;
                case "Suvs":           r = 120; g = 170; b = 140; break;
                case "Muscle":         r = 200; g = 140; b = 120; break;
                case "Sportsclassics": r = 180; g = 160; b = 120; break;
                case "Super":          r = 200; g = 120; b = 140; break;
                case "Offroad":        r = 160; g = 150; b = 120; break;
                case "Motorcycles":    r = 140; g = 140; b = 160; break;
                case "Vans":           r = 150; g = 170; b = 160; break;
                case "Boats":          r = 100; g = 160; b = 200; break;
                case "Helicopters":    r = 140; g = 180; b = 200; break;
                case "Planes":         r = 160; g = 190; b = 210; break;
                case "Military":       r = 130; g = 150; b = 120; break;
                case "Industrial":     r = 170; g = 160; b = 140; break;
                case "Openwheel":      r = 200; g = 160; b = 100; break;
                case "Emergency":      r = 200; g = 130; b = 130; break;
                case "Cycles":         r = 130; g = 180; b = 150; break;
                case "Service":        r = 160; g = 160; b = 160; break;
                case "Special":        r = 180; g = 140; b = 180; break;
                default:               r = 180; g = 190; b = 185; break;
            }

            if (bright)
            {
                r = Math.Min(255, r + 20);
                g = Math.Min(255, g + 20);
                b = Math.Min(255, b + 20);
            }

            return Color.FromArgb(255, r, g, b);
        }

        private void RebuildFilteredList()
        {
            _filtered.Clear();

            Category activeCategory = CATEGORIES[_activeCategoryIndex];
            string[] models = activeCategory.Models;
            foreach (string model in models)
            {
                string displayName = VehicleList.DisplayNames.ContainsKey(model)
                    ? VehicleList.DisplayNames[model] : model;
                bool owned = GarageManager.IsVehicleOwned(model);
                if (_vehicleOwnershipFilter == 1 && !owned) continue;
                if (_vehicleOwnershipFilter == 2 && owned) continue;
                if (activeCategory.FavoritesOnly &&
                    !GbayPreferences.IsVehicleFavorite(model)) continue;
                if (_vehicleSearch.Length > 0 &&
                    displayName.IndexOf(_vehicleSearch, StringComparison.OrdinalIgnoreCase) < 0 &&
                    model.IndexOf(_vehicleSearch, StringComparison.OrdinalIgnoreCase) < 0)
                    continue;

                // Split display name into manufacturer and vehicle name
                string mfg = "";
                string name = displayName;
                int spaceIdx = displayName.IndexOf(' ');
                if (spaceIdx > 0)
                {
                    mfg = displayName.Substring(0, spaceIdx);
                    name = displayName.Substring(spaceIdx + 1);
                }

                int price = 0;
                if (VehicleList.Prices.ContainsKey(model))
                    price = VehicleList.Prices[model];

                _filtered.Add(new VehicleCard
                {
                    Model = model,
                    DisplayName = name,
                    Manufacturer = mfg,
                    Price = _shop.FreeMode ? 0 : price,
                });
            }

            _totalPages = Math.Max(1, (_filtered.Count + PAGE_SIZE - 1) / PAGE_SIZE);
            UpdateActiveDicts();
        }

        private void UpdateVehicleSearchKeyboard()
        {
            if (!_vehicleKeyboardActive) return;
            int status = Function.Call<int>(Hash.UPDATE_ONSCREEN_KEYBOARD);
            if (status == 0) return;
            if (status == 1)
                _vehicleSearch = Function.Call<string>(Hash.GET_ONSCREEN_KEYBOARD_RESULT) ?? "";
            _vehicleKeyboardActive = false;
            _currentPage = 0; _selectedCard = 0;
            RebuildFilteredList();
        }

        private void UpdateActiveDicts()
        {
            var needed = new HashSet<string>();

            // Collect dicts for current page + next page (pre-fetch)
            for (int page = _currentPage; page <= _currentPage + 1; page++)
            {
                int start = page * PAGE_SIZE;
                int count = Math.Min(PAGE_SIZE, _filtered.Count - start);
                for (int i = 0; i < count; i++)
                {
                    if (VehicleList.PreviewDict.TryGetValue(
                            _filtered[start + i].Model, out string dict))
                        needed.Add(dict);
                }
            }

            // Release dicts no longer needed
            foreach (string d in _activeDicts)
                if (!needed.Contains(d))
                    GbayRenderer.ReleaseDict(d);

            // Request new dicts
            foreach (string d in needed)
                GbayRenderer.RequestDict(d);

            _activeDicts.Clear();
            _activeDicts.UnionWith(needed);
        }

        private void ReleaseAllDicts()
        {
            foreach (string d in _activeDicts)
                GbayRenderer.ReleaseDict(d);
            _activeDicts.Clear();
            GbayRenderer.ReleaseDict("allin1_gear_01");
            GbayRenderer.ReleaseDict("phat_logo");
            GbayRenderer.ReleaseDict("allin1_logo");
        }

        private void EnsureTabVisible(int categoryIndex)
        {
            if (categoryIndex < _tabScrollOffset)
                _tabScrollOffset = categoryIndex;
            else if (categoryIndex >= _tabScrollOffset + MAX_VISIBLE_TABS)
                _tabScrollOffset = categoryIndex - MAX_VISIBLE_TABS + 1;
        }

        private int GetPageCount()
        {
            int startIdx = _currentPage * PAGE_SIZE;
            return Math.Min(PAGE_SIZE, _filtered.Count - startIdx);
        }
    }
}
