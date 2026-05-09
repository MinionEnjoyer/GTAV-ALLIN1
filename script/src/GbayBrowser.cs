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
        TopMenu,
        VehicleBrowser,
        VehiclePreview,
        DeliveryConfirm,
        GarageView,
        WeaponBrowser,
        GearBrowser,
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
        internal int Price;
        internal bool Owned;
    }

    internal struct GearCard
    {
        internal string GearId;
        internal string DisplayName;
        internal string Category;
        internal int Price;
        internal bool Owned;
    }

    internal class GbayBrowser
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

        // Card dimensions (computed per-frame for aspect ratio)
        private const float CARD_H         = 0.23f;
        private const float CARD_GAP_X     = 0.015f;
        private const float CARD_GAP_Y     = 0.022f;

        // Top menu button layout
        private const float TOP_BTN_W      = 0.35f;
        private const float TOP_BTN_H      = 0.065f;
        private const float TOP_BTN_GAP    = 0.018f;

        // Delivery modal
        private const float MODAL_W        = 0.45f;
        private const float MODAL_ITEM_H   = 0.055f;

        // ------------------------------------------------------------------ //
        //  Category Definitions                                               //
        // ------------------------------------------------------------------ //

        private struct Category
        {
            internal string Label;
            internal string[] Models;

            internal Category(string label, string[] models)
            {
                Label = label;
                Models = models;
            }
        }

        private static readonly Category[] CATEGORIES =
        {
            new Category("All",             VehicleList.All),
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

            internal WeaponCategory(string label, string[] weapons)
            {
                Label = label;
                Weapons = weapons;
            }
        }

        private static readonly WeaponCategory[] WEAPON_CATEGORIES =
        {
            new WeaponCategory("All",             WeaponList.All),
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

        private static readonly WeaponCategory[] GEAR_CATEGORIES =
        {
            new WeaponCategory("All",        GearList.All),
            new WeaponCategory("Protection", GearList.Protection),
            new WeaponCategory("Equipment",  GearList.Equipment),
        };

        // ------------------------------------------------------------------ //
        //  State                                                              //
        // ------------------------------------------------------------------ //

        private readonly GbayShop _shop;
        private BrowserState _state = BrowserState.Closed;

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

        // Gear browser
        private int _gearCategoryIndex;
        private int _gearPage;
        private int _gearTotalPages;
        private int _gearSelectedCard;
        private int _gearHoverCard = -1;
        private int _gearTabScrollOffset;
        private int _gearHoverTab = -1;
        private readonly List<GearCard> _gearFiltered = new List<GearCard>();

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
                _state = BrowserState.TopMenu;
                _topMenuIndex = 0;
                GbayRenderer.EnsureTextures();
                GbayRenderer.RequestDict("allin1_logo");
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

            // Preview and delivery states handle their own background
            if (_state != BrowserState.VehiclePreview &&
                _state != BrowserState.DeliveryConfirm ||
                _state == BrowserState.DeliveryConfirm && _previewVehicle == null)
            {
                GbayRenderer.DrawScrim();
            }

            switch (_state)
            {
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
                        UpdatePreviewCamera();
                    else
                        DrawBrowser(new FrameInput());
                    DrawDeliveryModal(input);
                    break;
                case BrowserState.GarageView:
                    DrawGarageView(input);
                    break;
                case BrowserState.WeaponBrowser:
                    DrawWeaponBrowser(input);
                    break;
                case BrowserState.GearBrowser:
                    DrawGearBrowser(input);
                    break;
            }

            GbayRenderer.DrawCursor();
        }

        // ------------------------------------------------------------------ //
        //  Top Menu                                                           //
        // ------------------------------------------------------------------ //

        private void DrawTopMenu(FrameInput input)
        {
            // Layout constants for 4 buttons + logo, centered on screen
            float panelW = 0.40f;
            float panelH = 0.50f;
            float panelCY = 0.50f;
            float panelTop = panelCY - panelH / 2f;  // 0.25

            GbayRenderer.DrawRect(BROWSER_CX, panelCY, panelW, panelH,
                GbayRenderer.ModalBg);

            // Logo
            float logoH = 0.10f;
            float logoCY = panelTop + 0.03f + logoH / 2f;  // 0.33
            GbayRenderer.DrawLogo(BROWSER_CX, logoCY, logoH);

            // Buttons
            string[] labels = { "Vehicles", "Weapons", "Gear", "My Garage" };
            bool[] enabled = { true, true, true, true };
            float startY = panelTop + 0.03f + logoH + 0.025f;  // 0.405

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

                GbayRenderer.DrawRect(BROWSER_CX, btnCY, TOP_BTN_W, TOP_BTN_H, bg);
                GbayRenderer.DrawText(labels[i], BROWSER_CX, btnY + 0.014f,
                    0.45f, text, GbayRenderer.FONT_CHALET, true);
            }

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
                    _state = BrowserState.GearBrowser;
                    _gearCategoryIndex = 0;
                    _gearPage = 0;
                    _gearSelectedCard = 0;
                    _gearTabScrollOffset = 0;
                    RebuildGearFilteredList();
                }
                else if (activateIdx == 3) // My Garage
                {
                    _state = BrowserState.GarageView;
                    _garageVehicleIdx = 0;
                }
            }

            if (input.Back || input.MouseRightClick)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.Closed;
            }
        }

        // ------------------------------------------------------------------ //
        //  Vehicle Browser                                                    //
        // ------------------------------------------------------------------ //

        private void DrawBrowser(FrameInput input)
        {
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
            DrawFooter();

            // Handle input
            HandleBrowserInput(input);
        }

        private void DrawHeader()
        {
            GbayRenderer.DrawRect(BROWSER_CX, HEADER_CY, BROWSER_W, HEADER_H,
                GbayRenderer.HeaderBg);

            // Logo (left)
            GbayRenderer.DrawLogo(BROWSER_LEFT + 0.035f, HEADER_CY, HEADER_H * 0.85f);

            // Section label
            GbayRenderer.DrawText("VEHICLES", BROWSER_LEFT + 0.07f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.TabActive, GbayRenderer.FONT_CONDENSED);

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
            float tabAreaW = BROWSER_W - 0.04f; // leave room for scroll arrows
            float singleTabW = tabAreaW / MAX_VISIBLE_TABS;
            float tabStartX = BROWSER_LEFT + 0.02f;

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

                // Hover background
                if (isHover && !isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_CY, singleTabW - 0.004f,
                        TAB_H, GbayRenderer.TabHover);

                // Active indicator (white bar at bottom of tab)
                if (isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_Y + TAB_H - 0.004f,
                        singleTabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);

                // Label
                Color textColor = isActive ? GbayRenderer.TabActive : GbayRenderer.TabInactive;
                string label = CATEGORIES[catIdx].Label;
                GbayRenderer.DrawText(label, tabCX, TAB_Y + 0.01f,
                    0.32f, textColor, GbayRenderer.FONT_CONDENSED, true);
            }

            // Scroll arrows if there are more tabs than visible
            if (_tabScrollOffset > 0)
            {
                GbayRenderer.DrawText("<", BROWSER_LEFT + 0.008f, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET);
            }
            if (_tabScrollOffset + MAX_VISIBLE_TABS < CATEGORIES.Length)
            {
                GbayRenderer.DrawText(">", BROWSER_RIGHT - 0.018f, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET);
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
            Color borderColor = selected ? GbayRenderer.CardBorderSel
                              : GbayRenderer.CardBorder;

            GbayRenderer.DrawBorderedRect(cx, cy, cardW, CARD_H,
                bgColor, borderColor, 0.002f);

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

            // Text area below the preview image
            float textTop = top + topAreaH + 0.004f;
            float textLeft = left + 0.010f;
            float textRight = left + cardW - 0.010f;

            // Manufacturer (small, uppercase feel)
            GbayRenderer.DrawText(card.Manufacturer, textLeft, textTop + 0.006f,
                0.25f, GbayRenderer.TextMfg, GbayRenderer.FONT_CONDENSED);

            // Vehicle name (prominent)
            GbayRenderer.DrawText(card.DisplayName, textLeft, textTop + 0.030f,
                0.32f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

            // Price (right-aligned, bottom of text area)
            string priceText = card.Price <= 0 ? "FREE" : $"${card.Price:N0}";
            Color priceColor = card.Price <= 0
                ? GbayRenderer.TextPriceFree : GbayRenderer.TextPrice;
            GbayRenderer.DrawText(priceText, textRight, textTop + 0.062f,
                0.30f, priceColor, GbayRenderer.FONT_CHALET, false, false, true);
        }

        private void DrawFooter()
        {
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);

            // Page indicator
            string pageText = $"Page {_currentPage + 1}/{Math.Max(1, _totalPages)}";
            GbayRenderer.DrawText(pageText, BROWSER_LEFT + 0.02f, FOOTER_Y + 0.012f,
                0.32f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

            // Control hints
            string hints = "[Q/E] Page   [Z/X] Category   [Enter] Buy   [Esc] Back";
            GbayRenderer.DrawText(hints, BROWSER_RIGHT - 0.01f, FOOTER_Y + 0.012f,
                0.28f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED,
                false, false, true);
        }

        private void HandleBrowserInput(FrameInput input)
        {
            if (input.Back || input.MouseRightClick)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
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

            // Page navigation (Q/E)
            if (input.PageLeft && _currentPage > 0)
            {
                _currentPage--;
                _selectedCard = Math.Min(_selectedCard, GetPageCount() - 1);
                UpdateActiveDicts();
                GbayRenderer.PlayNav();
            }
            else if (input.PageRight && _currentPage < _totalPages - 1)
            {
                _currentPage++;
                _selectedCard = Math.Min(_selectedCard, GetPageCount() - 1);
                UpdateActiveDicts();
                GbayRenderer.PlayNav();
            }

            // Grid navigation (arrows)
            if (input.DirX != 0 || input.DirY != 0)
            {
                int col = _selectedCard % GRID_COLS;
                int row = _selectedCard / GRID_COLS;
                int maxIdx = GetPageCount() - 1;

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
                    $"~r~Insufficient funds.~w~ Need ~g~${price:N0}~w~ (have ${Game.Player.Money:N0})",
                    3000);
                return;
            }

            _pendingModel = model;
            _pendingPrice = price;

            GbayRenderer.PlaySelect();
            _state = BrowserState.DeliveryConfirm;
        }

        private void DrawDeliveryModal(FrameInput input)
        {
            // Modal scrim
            GbayRenderer.DrawRect(0.5f, 0.5f, 1f, 1f, GbayRenderer.ModalScrim);

            // Modal panel
            float modalH = 0.22f;
            float modalTop = 0.5f - modalH / 2f;

            GbayRenderer.DrawBorderedRect(BROWSER_CX, 0.5f, MODAL_W, modalH,
                GbayRenderer.ModalBg, GbayRenderer.CardBorderSel, 0.003f);

            // Title
            string displayName = VehicleList.DisplayNames.ContainsKey(_pendingModel)
                ? VehicleList.DisplayNames[_pendingModel] : _pendingModel;
            GbayRenderer.DrawText(displayName, BROWSER_CX, modalTop + 0.015f,
                0.38f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);

            // Price
            string priceText = _shop.FreeMode || _pendingPrice <= 0
                ? "FREE" : $"${_pendingPrice:N0}";
            GbayRenderer.DrawText(priceText, BROWSER_CX, modalTop + 0.05f,
                0.30f, GbayRenderer.TextPrice, GbayRenderer.FONT_CHALET, true);

            // Garage info
            int used = GarageManager.GetUsedSlots();
            int cap = GarageManager.GetCapacity();
            bool isFull = used >= cap;
            string garageInfo = $"Eclipse Towers Garage ({used}/{cap})";
            Color garageColor = isFull ? GbayRenderer.TextDim : GbayRenderer.TextDark;
            GbayRenderer.DrawText(garageInfo, BROWSER_CX, modalTop + 0.09f,
                0.32f, garageColor, GbayRenderer.FONT_CHALET, true);

            if (isFull)
            {
                GbayRenderer.DrawText("Garage is full!", BROWSER_CX, modalTop + 0.125f,
                    0.28f, Color.FromArgb(255, 200, 80, 80), GbayRenderer.FONT_CONDENSED, true);
            }

            // Footer hint
            GbayRenderer.DrawText("[Enter] Confirm   [Esc] Cancel",
                BROWSER_CX, modalTop + 0.17f, 0.24f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED, true);

            // Accept
            if ((input.Accept || input.MouseClick) && !isFull)
            {
                GbayRenderer.PlaySelect();
                _shop.ExecuteDeliverToGarage(_pendingModel, _pendingPrice);
                ClosePreview();
                _state = BrowserState.VehicleBrowser;
            }

            if (input.Back || input.MouseRightClick)
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

            _previewModel = card.Model;
            _previewDisplayName = card.DisplayName;
            _previewManufacturer = card.Manufacturer;
            _previewPrice = card.Price;
            _previewAngle = 0f;
            _previewZoom = 1.0f;

            // Spawn vehicle first — CreateVehicle waits for model to load
            _previewVehicle = VehicleHelper.CreateVehicle(
                _previewModel, PREVIEW_POS, 0f);

            if (_previewVehicle == null)
            {
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle("~r~Failed to load vehicle model.", 3000);
                return;
            }

            // Now that model is loaded, get dimensions for camera framing
            int hash = _previewVehicle.Model.Hash;

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
            GbayRenderer.DrawText(_previewManufacturer, 0.5f, 0.008f,
                0.30f, GbayRenderer.TextMfg, GbayRenderer.FONT_CONDENSED, true);

            // Vehicle name
            GbayRenderer.DrawText(_previewDisplayName, 0.5f, 0.032f,
                0.52f, GbayRenderer.TextWhite, GbayRenderer.FONT_CHALET, true);

            // Price (right side)
            string priceText = _previewPrice <= 0 ? "FREE" : $"${_previewPrice:N0}";
            GbayRenderer.DrawText(priceText, 0.92f, 0.025f,
                0.42f, GbayRenderer.TextPrice, GbayRenderer.FONT_CHALET,
                false, false, true);

            // Bottom bar with controls
            float footerY = 0.93f;
            float footerH = 0.07f;
            GbayRenderer.DrawRect(0.5f, footerY + footerH / 2f, 1f, footerH,
                Color.FromArgb(180, 0, 0, 0));
            GbayRenderer.DrawText(
                "[Left/Right] Rotate   [Q/E] Zoom   [Enter] Purchase   [Esc] Back",
                0.5f, footerY + 0.018f, 0.28f, GbayRenderer.TextWhite,
                GbayRenderer.FONT_CONDENSED, true);

            // Input: Buy
            if (input.Accept)
            {
                OpenDeliveryConfirm(_previewModel, _previewPrice);
            }

            // Input: Back
            if (input.Back || input.MouseRightClick)
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
            GbayRenderer.DrawLogo(BROWSER_LEFT + 0.035f, HEADER_CY, HEADER_H * 0.85f);
            GbayRenderer.DrawText("MY GARAGE", BROWSER_LEFT + 0.07f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.TabActive, GbayRenderer.FONT_CONDENSED);

            // Capacity info (right side of header)
            int used = GarageManager.GetUsedSlots();
            int cap = GarageManager.GetCapacity();
            string capText = $"Eclipse Towers ({used}/{cap})";
            GbayRenderer.DrawText(capText, BROWSER_RIGHT - 0.01f, HEADER_Y + 0.018f,
                0.32f, GbayRenderer.HeaderText, GbayRenderer.FONT_CHALET,
                false, false, true);

            // Vehicle list
            var vehicles = GarageManager.GetStoredVehicles();

            float listTop = TAB_Y + 0.02f;
            float itemH = 0.055f;

            _garageHoverIdx = -1;

            if (vehicles.Count == 0)
            {
                GbayRenderer.DrawText("No vehicles stored",
                    BROWSER_CX, listTop + 0.10f, 0.35f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);
                GbayRenderer.DrawText("Purchase vehicles from the Vehicles tab to store them here.",
                    BROWSER_CX, listTop + 0.15f, 0.26f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CONDENSED, true);
            }
            else
            {
                for (int i = 0; i < vehicles.Count; i++)
                {
                    var sv = vehicles[i];
                    float itemY = listTop + i * itemH;
                    float itemCY = itemY + itemH / 2f;
                    bool isSel = i == _garageVehicleIdx;
                    bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                        BROWSER_CX, itemCY, BROWSER_W - 0.08f, itemH);

                    if (isHover)
                        _garageHoverIdx = i;

                    if (isSel || isHover)
                        GbayRenderer.DrawRect(BROWSER_CX, itemCY,
                            BROWSER_W - 0.08f, itemH, GbayRenderer.CardHover);

                    string name = VehicleList.DisplayNames.ContainsKey(sv.Model)
                        ? VehicleList.DisplayNames[sv.Model] : sv.Model;

                    // Slot number
                    GbayRenderer.DrawText($"#{sv.Slot + 1}", BROWSER_LEFT + 0.06f, itemY + 0.012f,
                        0.28f, GbayRenderer.TextMfg, GbayRenderer.FONT_CONDENSED);

                    // Vehicle name
                    GbayRenderer.DrawText(name, BROWSER_LEFT + 0.10f, itemY + 0.012f,
                        0.32f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

                    // Remove button
                    float removeBtnX = BROWSER_RIGHT - 0.08f;
                    bool removeHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                        removeBtnX, itemCY, 0.08f, itemH);

                    Color removeBg = removeHover
                        ? Color.FromArgb(255, 200, 60, 60)
                        : Color.FromArgb(255, 180, 80, 80);
                    GbayRenderer.DrawRect(removeBtnX, itemCY, 0.07f, itemH - 0.01f,
                        removeBg);
                    GbayRenderer.DrawText("Remove", removeBtnX, itemY + 0.012f,
                        0.25f, GbayRenderer.TextWhite, GbayRenderer.FONT_CONDENSED, true);

                    if (removeHover && input.MouseClick)
                    {
                        GarageManager.RemoveVehicle(i);
                        GbayRenderer.PlaySelect();
                        GTA.UI.Screen.ShowSubtitle(
                            $"~y~{name}~w~ removed from garage.", 3000);
                        _garageVehicleIdx = Math.Max(0, _garageVehicleIdx - 1);
                        return;
                    }
                }
            }

            // Keyboard navigation
            if (input.DirY != 0 && vehicles.Count > 0)
            {
                int next = _garageVehicleIdx + input.DirY;
                if (next >= 0 && next < vehicles.Count)
                {
                    _garageVehicleIdx = next;
                    GbayRenderer.PlayNav();
                }
            }

            if (_garageHoverIdx >= 0)
                _garageVehicleIdx = _garageHoverIdx;

            // Keyboard remove
            if (input.Accept && vehicles.Count > 0 && _garageVehicleIdx < vehicles.Count)
            {
                var sv = vehicles[_garageVehicleIdx];
                string name = VehicleList.DisplayNames.ContainsKey(sv.Model)
                    ? VehicleList.DisplayNames[sv.Model] : sv.Model;
                GarageManager.RemoveVehicle(_garageVehicleIdx);
                GbayRenderer.PlaySelect();
                GTA.UI.Screen.ShowSubtitle(
                    $"~y~{name}~w~ removed from garage.", 3000);
                _garageVehicleIdx = Math.Max(0, _garageVehicleIdx - 1);
            }

            // Back
            if (input.Back || input.MouseRightClick)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
            }

            // Footer
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);
            GbayRenderer.DrawText("[Enter] Remove   [Esc] Back",
                BROWSER_CX, FOOTER_Y + 0.012f, 0.24f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED, true);
        }

        // ------------------------------------------------------------------ //
        //  Weapon Browser                                                     //
        // ------------------------------------------------------------------ //

        private void DrawWeaponBrowser(FrameInput input)
        {
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
            DrawWeaponFooter();

            // Handle input
            HandleWeaponBrowserInput(input);
        }

        private void DrawWeaponHeader()
        {
            GbayRenderer.DrawRect(BROWSER_CX, HEADER_CY, BROWSER_W, HEADER_H,
                GbayRenderer.HeaderBg);

            GbayRenderer.DrawLogo(BROWSER_LEFT + 0.035f, HEADER_CY, HEADER_H * 0.85f);

            GbayRenderer.DrawText("WEAPONS", BROWSER_LEFT + 0.07f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.TabActive, GbayRenderer.FONT_CONDENSED);

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
            float tabAreaW = BROWSER_W - 0.04f;
            float singleTabW = tabAreaW / MAX_VISIBLE_TABS;
            float tabStartX = BROWSER_LEFT + 0.02f;

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

                if (isHover && !isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_CY, singleTabW - 0.004f,
                        TAB_H, GbayRenderer.TabHover);

                if (isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_Y + TAB_H - 0.004f,
                        singleTabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);

                Color textColor = isActive ? GbayRenderer.TabActive : GbayRenderer.TabInactive;
                string label = WEAPON_CATEGORIES[catIdx].Label;
                GbayRenderer.DrawText(label, tabCX, TAB_Y + 0.01f,
                    0.32f, textColor, GbayRenderer.FONT_CONDENSED, true);
            }

            if (_weaponTabScrollOffset > 0)
            {
                GbayRenderer.DrawText("<", BROWSER_LEFT + 0.008f, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET);
            }
            if (_weaponTabScrollOffset + MAX_VISIBLE_TABS < WEAPON_CATEGORIES.Length)
            {
                GbayRenderer.DrawText(">", BROWSER_RIGHT - 0.018f, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET);
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
            Color borderColor = selected ? GbayRenderer.CardBorderSel
                              : GbayRenderer.CardBorder;

            GbayRenderer.DrawBorderedRect(cx, cy, cardW, CARD_H,
                bgColor, borderColor, 0.002f);

            // Top area: category-colored placeholder (55% of card height)
            float topAreaH = CARD_H * 0.55f;
            float topAreaCY = top + topAreaH / 2f;

            Color topColor = GetWeaponCategoryColor(card.Category, hovered || selected);
            GbayRenderer.DrawRect(cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f,
                topColor);

            // Category label in the placeholder area
            GbayRenderer.DrawText(card.Category, cx, top + topAreaH * 0.35f,
                0.28f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true);

            // Text area below
            float textTop = top + topAreaH + 0.004f;
            float textLeft = left + 0.010f;
            float textRight = left + cardW - 0.010f;

            // Weapon name (prominent)
            GbayRenderer.DrawText(card.DisplayName, textLeft, textTop + 0.010f,
                0.32f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

            // Price, OWNED status, or ammo info
            if (card.Owned)
            {
                bool isPendingConfirm = _ammoConfirmPending &&
                    card.WeaponName == _ammoConfirmWeapon;

                if (isPendingConfirm)
                {
                    GbayRenderer.DrawBorderedRect(cx, cy, cardW, CARD_H,
                        bgColor, Color.FromArgb(255, 255, 200, 50), 0.003f);

                    string confirmText = _ammoConfirmCost > 0
                        ? $"REFILL {_ammoConfirmRounds} rnds - ${_ammoConfirmCost:N0}"
                        : $"REFILL {_ammoConfirmRounds} rnds - FREE";
                    GbayRenderer.DrawText(confirmText, textLeft, textTop + 0.042f,
                        0.24f, Color.FromArgb(255, 255, 200, 50), GbayRenderer.FONT_CONDENSED);
                }
                else
                {
                    int rounds;
                    int cost = _shop.GetAmmoRefillInfo(card.WeaponName, out rounds);

                    if (cost == -1)
                    {
                        GbayRenderer.DrawText("OWNED", textRight, textTop + 0.042f,
                            0.28f, GbayRenderer.TextPriceFree, GbayRenderer.FONT_CHALET,
                            false, false, true);
                    }
                    else if (cost == 0 && rounds == 0)
                    {
                        GbayRenderer.DrawText("FULLY STOCKED", textRight, textTop + 0.042f,
                            0.24f, GbayRenderer.TextPriceFree, GbayRenderer.FONT_CONDENSED,
                            false, false, true);
                    }
                    else
                    {
                        string ammoText = cost > 0
                            ? $"Refill ${cost:N0}"
                            : $"Refill {rounds} rnds";
                        GbayRenderer.DrawText("OWNED", textLeft, textTop + 0.042f,
                            0.26f, GbayRenderer.TextPriceFree, GbayRenderer.FONT_CONDENSED);
                        GbayRenderer.DrawText(ammoText, textRight, textTop + 0.042f,
                            0.24f, Color.FromArgb(255, 200, 180, 80), GbayRenderer.FONT_CONDENSED,
                            false, false, true);
                    }
                }
            }
            else
            {
                string priceText = card.Price <= 0 ? "FREE" : $"${card.Price:N0}";
                Color priceColor = card.Price <= 0
                    ? GbayRenderer.TextPriceFree : GbayRenderer.TextPrice;
                GbayRenderer.DrawText(priceText, textRight, textTop + 0.042f,
                    0.30f, priceColor, GbayRenderer.FONT_CHALET, false, false, true);
            }
        }

        private void DrawWeaponFooter()
        {
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
                string prompt = $"[Enter] Confirm Ammo Refill: {displayName} ({_ammoConfirmRounds} rounds) for {costText}   [Esc] Cancel";
                GbayRenderer.DrawText(prompt, BROWSER_CX, FOOTER_Y + 0.012f,
                    0.26f, Color.FromArgb(255, 255, 220, 100), GbayRenderer.FONT_CONDENSED, true);
            }
            else
            {
                string pageText = $"Page {_weaponPage + 1}/{Math.Max(1, _weaponTotalPages)}";
                GbayRenderer.DrawText(pageText, BROWSER_LEFT + 0.02f, FOOTER_Y + 0.012f,
                    0.32f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

                string hints = "[Q/E] Page   [Z/X] Category   [Enter] Buy   [Esc] Back";
                GbayRenderer.DrawText(hints, BROWSER_RIGHT - 0.01f, FOOTER_Y + 0.012f,
                    0.28f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED,
                    false, false, true);
            }
        }

        private void HandleWeaponBrowserInput(FrameInput input)
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

            if (input.Back || input.MouseRightClick)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
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

            // Page navigation (Q/E)
            if (input.PageLeft && _weaponPage > 0)
            {
                _weaponPage--;
                _weaponSelectedCard = Math.Min(_weaponSelectedCard, GetWeaponPageCount() - 1);
                GbayRenderer.PlayNav();
            }
            else if (input.PageRight && _weaponPage < _weaponTotalPages - 1)
            {
                _weaponPage++;
                _weaponSelectedCard = Math.Min(_weaponSelectedCard, GetWeaponPageCount() - 1);
                GbayRenderer.PlayNav();
            }

            // Grid navigation (arrows)
            if (input.DirX != 0 || input.DirY != 0)
            {
                int col = _weaponSelectedCard % GRID_COLS;
                int row = _weaponSelectedCard / GRID_COLS;
                int maxIdx = GetWeaponPageCount() - 1;

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

                        if (cost == -1)
                        {
                            // Melee / no-ammo weapon
                            GbayRenderer.PlayError();
                            GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                        }
                        else if (cost == 0 && rounds == 0)
                        {
                            // Fully stocked
                            GbayRenderer.PlayError();
                            GTA.UI.Screen.ShowSubtitle("~g~Already fully stocked!", 3000);
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
                        GbayRenderer.PlaySelect();
                        _shop.ExecuteGiveWeapon(card.WeaponName, card.Price);
                        RebuildWeaponFilteredList();
                    }
                }
            }
        }

        private void RebuildWeaponFilteredList()
        {
            _weaponFiltered.Clear();

            Ped player = Game.Player.Character;
            string[] weapons = WEAPON_CATEGORIES[_weaponCategoryIndex].Weapons;

            foreach (string weaponName in weapons)
            {
                string displayName = WeaponList.DisplayNames.ContainsKey(weaponName)
                    ? WeaponList.DisplayNames[weaponName] : weaponName;

                int price = 0;
                if (WeaponList.Prices.ContainsKey(weaponName))
                    price = WeaponList.Prices[weaponName];

                string category = WeaponList.CategoryNames.ContainsKey(weaponName)
                    ? WeaponList.CategoryNames[weaponName] : "";

                // Check if player already owns this weapon
                bool owned = player.Weapons.HasWeapon((WeaponHash)Game.GenerateHash(weaponName));

                _weaponFiltered.Add(new WeaponCard
                {
                    WeaponName = weaponName,
                    DisplayName = displayName,
                    Category = category,
                    Price = _shop.FreeMode ? 0 : price,
                    Owned = owned,
                });
            }

            _weaponTotalPages = Math.Max(1, (_weaponFiltered.Count + PAGE_SIZE - 1) / PAGE_SIZE);
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
        //  Gear Browser                                                       //
        // ------------------------------------------------------------------ //

        private void DrawGearBrowser(FrameInput input)
        {
            float aspect = GbayRenderer.GetAspectRatio();
            float cardW = CARD_H / aspect;

            float bgCY = (BROWSER_TOP + BROWSER_BOTTOM) / 2f;
            float bgH = BROWSER_BOTTOM - BROWSER_TOP;
            GbayRenderer.DrawRect(BROWSER_CX, bgCY, BROWSER_W, bgH,
                GbayRenderer.BodyBg);

            DrawGearHeader();
            DrawGearCategoryTabs(input, aspect);
            DrawGearGrid(input, cardW);
            DrawGearFooter();
            HandleGearBrowserInput(input);
        }

        private void DrawGearHeader()
        {
            GbayRenderer.DrawRect(BROWSER_CX, HEADER_CY, BROWSER_W, HEADER_H,
                GbayRenderer.HeaderBg);

            GbayRenderer.DrawLogo(BROWSER_LEFT + 0.035f, HEADER_CY, HEADER_H * 0.85f);

            GbayRenderer.DrawText("GEAR", BROWSER_LEFT + 0.07f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.TabActive, GbayRenderer.FONT_CONDENSED);

            string money = $"${Game.Player.Money:N0}";
            GbayRenderer.DrawText(money, BROWSER_RIGHT - 0.01f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.HeaderText, GbayRenderer.FONT_CHALET,
                false, false, true);
        }

        private void DrawGearCategoryTabs(FrameInput input, float aspect)
        {
            GbayRenderer.DrawRect(BROWSER_CX, TAB_CY, BROWSER_W, TAB_H,
                GbayRenderer.TabBg);

            int visibleCount = Math.Min(MAX_VISIBLE_TABS, GEAR_CATEGORIES.Length - _gearTabScrollOffset);
            float tabAreaW = BROWSER_W - 0.04f;
            float singleTabW = tabAreaW / MAX_VISIBLE_TABS;
            float tabStartX = BROWSER_LEFT + 0.02f;

            _gearHoverTab = -1;

            for (int i = 0; i < visibleCount; i++)
            {
                int catIdx = _gearTabScrollOffset + i;
                float tabCX = tabStartX + singleTabW * i + singleTabW / 2f;
                bool isActive = catIdx == _gearCategoryIndex;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    tabCX, TAB_CY, singleTabW - 0.004f, TAB_H);

                if (isHover)
                    _gearHoverTab = catIdx;

                if (isHover && !isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_CY, singleTabW - 0.004f,
                        TAB_H, GbayRenderer.TabHover);

                if (isActive)
                    GbayRenderer.DrawRect(tabCX, TAB_Y + TAB_H - 0.004f,
                        singleTabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);

                Color textColor = isActive ? GbayRenderer.TabActive : GbayRenderer.TabInactive;
                string label = GEAR_CATEGORIES[catIdx].Label;
                GbayRenderer.DrawText(label, tabCX, TAB_Y + 0.01f,
                    0.32f, textColor, GbayRenderer.FONT_CONDENSED, true);
            }

            if (_gearTabScrollOffset > 0)
            {
                GbayRenderer.DrawText("<", BROWSER_LEFT + 0.008f, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET);
            }
            if (_gearTabScrollOffset + MAX_VISIBLE_TABS < GEAR_CATEGORIES.Length)
            {
                GbayRenderer.DrawText(">", BROWSER_RIGHT - 0.018f, TAB_Y + 0.008f,
                    0.35f, GbayRenderer.TabActive, GbayRenderer.FONT_CHALET);
            }
        }

        private void DrawGearGrid(FrameInput input, float cardW)
        {
            float gridW = GRID_COLS * cardW + (GRID_COLS - 1) * CARD_GAP_X;
            float gridStartX = BROWSER_CX - gridW / 2f;
            float gridStartY = GRID_TOP + 0.01f;

            int startIdx = _gearPage * PAGE_SIZE;
            int count = Math.Min(PAGE_SIZE, _gearFiltered.Count - startIdx);

            _gearHoverCard = -1;

            for (int i = 0; i < count; i++)
            {
                int col = i % GRID_COLS;
                int row = i / GRID_COLS;
                float cardLeft = gridStartX + col * (cardW + CARD_GAP_X);
                float cardTop = gridStartY + row * (CARD_H + CARD_GAP_Y);
                float cardCX = cardLeft + cardW / 2f;
                float cardCY = cardTop + CARD_H / 2f;

                bool isSelected = i == _gearSelectedCard;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    cardCX, cardCY, cardW, CARD_H);

                if (isHover)
                    _gearHoverCard = i;

                GearCard card = _gearFiltered[startIdx + i];
                DrawGearCard(card, cardLeft, cardTop, cardW, isSelected, isHover);
            }

            if (count == 0)
            {
                GbayRenderer.DrawText("No gear in this category",
                    BROWSER_CX, 0.45f, 0.4f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);
            }
        }

        private void DrawGearCard(GearCard card, float left, float top,
                                   float cardW, bool selected, bool hovered)
        {
            float cx = left + cardW / 2f;
            float cy = top + CARD_H / 2f;

            Color bgColor = selected ? GbayRenderer.CardSelected
                          : hovered ? GbayRenderer.CardHover
                          : GbayRenderer.CardBg;
            Color borderColor = selected ? GbayRenderer.CardBorderSel
                              : GbayRenderer.CardBorder;

            GbayRenderer.DrawBorderedRect(cx, cy, cardW, CARD_H,
                bgColor, borderColor, 0.002f);

            float topAreaH = CARD_H * 0.55f;
            float topAreaCY = top + topAreaH / 2f;

            Color topColor = GetGearCategoryColor(card.Category, hovered || selected);
            GbayRenderer.DrawRect(cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f,
                topColor);

            GbayRenderer.DrawText(card.Category, cx, top + topAreaH * 0.35f,
                0.28f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true);

            float textTop = top + topAreaH + 0.004f;
            float textLeft = left + 0.010f;
            float textRight = left + cardW - 0.010f;

            // Item name (prominent)
            GbayRenderer.DrawText(card.DisplayName, textLeft, textTop + 0.010f,
                0.32f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

            // Status or price (right-aligned)
            if (card.Owned)
            {
                string statusText = GearList.IsArmor(card.GearId) ? "EQUIPPED" : "OWNED";
                GbayRenderer.DrawText(statusText, textRight, textTop + 0.042f,
                    0.28f, GbayRenderer.TextPriceFree, GbayRenderer.FONT_CHALET,
                    false, false, true);
            }
            else
            {
                string priceText = card.Price <= 0 ? "FREE" : $"${card.Price:N0}";
                Color priceColor = card.Price <= 0
                    ? GbayRenderer.TextPriceFree : GbayRenderer.TextPrice;
                GbayRenderer.DrawText(priceText, textRight, textTop + 0.042f,
                    0.30f, priceColor, GbayRenderer.FONT_CHALET, false, false, true);
            }
        }

        private void DrawGearFooter()
        {
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);

            string pageText = $"Page {_gearPage + 1}/{Math.Max(1, _gearTotalPages)}";
            GbayRenderer.DrawText(pageText, BROWSER_LEFT + 0.02f, FOOTER_Y + 0.012f,
                0.32f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

            string hints = "[Q/E] Page   [Z/X] Category   [Enter] Buy   [Esc] Back";
            GbayRenderer.DrawText(hints, BROWSER_RIGHT - 0.01f, FOOTER_Y + 0.012f,
                0.28f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED,
                false, false, true);
        }

        private void HandleGearBrowserInput(FrameInput input)
        {
            if (input.Back || input.MouseRightClick)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
                return;
            }

            if (input.MouseClick && _gearHoverTab >= 0 && _gearHoverTab != _gearCategoryIndex)
            {
                _gearCategoryIndex = _gearHoverTab;
                _gearPage = 0;
                _gearSelectedCard = 0;
                RebuildGearFilteredList();
                GbayRenderer.PlayNav();
                return;
            }

            if (input.CategoryPrev && _gearCategoryIndex > 0)
            {
                _gearCategoryIndex--;
                _gearPage = 0;
                _gearSelectedCard = 0;
                EnsureGearTabVisible(_gearCategoryIndex);
                RebuildGearFilteredList();
                GbayRenderer.PlayNav();
            }
            else if (input.CategoryNext && _gearCategoryIndex < GEAR_CATEGORIES.Length - 1)
            {
                _gearCategoryIndex++;
                _gearPage = 0;
                _gearSelectedCard = 0;
                EnsureGearTabVisible(_gearCategoryIndex);
                RebuildGearFilteredList();
                GbayRenderer.PlayNav();
            }

            if (input.PageLeft && _gearPage > 0)
            {
                _gearPage--;
                _gearSelectedCard = Math.Min(_gearSelectedCard, GetGearPageCount() - 1);
                GbayRenderer.PlayNav();
            }
            else if (input.PageRight && _gearPage < _gearTotalPages - 1)
            {
                _gearPage++;
                _gearSelectedCard = Math.Min(_gearSelectedCard, GetGearPageCount() - 1);
                GbayRenderer.PlayNav();
            }

            if (input.DirX != 0 || input.DirY != 0)
            {
                int col = _gearSelectedCard % GRID_COLS;
                int row = _gearSelectedCard / GRID_COLS;
                int maxIdx = GetGearPageCount() - 1;

                if (input.DirX != 0)
                    col = Math.Max(0, Math.Min(col + input.DirX, GRID_COLS - 1));
                if (input.DirY != 0)
                    row = Math.Max(0, Math.Min(row + input.DirY, GRID_ROWS - 1));

                int newIdx = Math.Min(row * GRID_COLS + col, maxIdx);
                if (newIdx != _gearSelectedCard)
                {
                    _gearSelectedCard = newIdx;
                    GbayRenderer.PlayNav();
                }
            }

            if (_gearHoverCard >= 0 && _gearHoverCard != _gearSelectedCard)
                _gearSelectedCard = _gearHoverCard;

            bool accepted = input.Accept || (input.MouseClick && _gearHoverCard >= 0);
            if (accepted && _gearFiltered.Count > 0)
            {
                int idx = _gearPage * PAGE_SIZE + _gearSelectedCard;
                if (idx < _gearFiltered.Count)
                {
                    GearCard card = _gearFiltered[idx];

                    if (card.Owned && !GearList.IsArmor(card.GearId))
                    {
                        GbayRenderer.PlayError();
                        GTA.UI.Screen.ShowSubtitle("~y~Already owned.", 3000);
                    }
                    else
                    {
                        GbayRenderer.PlaySelect();
                        _shop.ExecuteGiveGear(card.GearId, card.Price);
                        RebuildGearFilteredList();
                    }
                }
            }
        }

        private void RebuildGearFilteredList()
        {
            _gearFiltered.Clear();

            Ped player = Game.Player.Character;
            string[] items = GEAR_CATEGORIES[_gearCategoryIndex].Weapons;

            foreach (string gearId in items)
            {
                string displayName = GearList.DisplayNames.ContainsKey(gearId)
                    ? GearList.DisplayNames[gearId] : gearId;

                int price = 0;
                if (GearList.Prices.ContainsKey(gearId))
                    price = GearList.Prices[gearId];

                string category = GearList.CategoryNames.ContainsKey(gearId)
                    ? GearList.CategoryNames[gearId] : "";

                bool owned;
                if (GearList.IsArmor(gearId))
                {
                    // Armor tier is "owned" if current armor >= that tier's value
                    int tierValue = GearList.ArmorValues[gearId];
                    owned = player.Armor >= tierValue;
                }
                else
                {
                    owned = player.Weapons.HasWeapon((WeaponHash)Game.GenerateHash(gearId));
                }

                _gearFiltered.Add(new GearCard
                {
                    GearId = gearId,
                    DisplayName = displayName,
                    Category = category,
                    Price = _shop.FreeMode ? 0 : price,
                    Owned = owned,
                });
            }

            _gearTotalPages = Math.Max(1, (_gearFiltered.Count + PAGE_SIZE - 1) / PAGE_SIZE);
        }

        private static Color GetGearCategoryColor(string category, bool bright)
        {
            int r, g, b;
            switch (category)
            {
                case "Protection": r = 100; g = 150; b = 200; break;
                case "Equipment":  r = 180; g = 170; b = 130; break;
                default:           r = 160; g = 170; b = 165; break;
            }

            if (bright)
            {
                r = Math.Min(255, r + 20);
                g = Math.Min(255, g + 20);
                b = Math.Min(255, b + 20);
            }

            return Color.FromArgb(255, r, g, b);
        }

        private void EnsureGearTabVisible(int categoryIndex)
        {
            if (categoryIndex < _gearTabScrollOffset)
                _gearTabScrollOffset = categoryIndex;
            else if (categoryIndex >= _gearTabScrollOffset + MAX_VISIBLE_TABS)
                _gearTabScrollOffset = categoryIndex - MAX_VISIBLE_TABS + 1;
        }

        private int GetGearPageCount()
        {
            int startIdx = _gearPage * PAGE_SIZE;
            return Math.Min(PAGE_SIZE, _gearFiltered.Count - startIdx);
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

            string[] models = CATEGORIES[_activeCategoryIndex].Models;
            foreach (string model in models)
            {
                string displayName = VehicleList.DisplayNames.ContainsKey(model)
                    ? VehicleList.DisplayNames[model] : model;

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
