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
    }

    internal struct VehicleCard
    {
        internal string Model;
        internal string DisplayName;
        internal string Manufacturer;
        internal int Price;
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
        private const float TOP_BTN_H      = 0.08f;
        private const float TOP_BTN_GAP    = 0.025f;

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
        private int _deliveryIndex;
        private int _deliveryHover = -1;
        private readonly List<DeliveryOption> _deliveryOptions = new List<DeliveryOption>();

        // Garage view
        private int _garageSafehouseIdx;
        private int _garageVehicleIdx;
        private int _garageHoverIdx = -1;
        private GarageManager.Safehouse[] _garageSafehouses;

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

        private struct DeliveryOption
        {
            internal string Label;
            internal string Info;
            internal string SafehouseId;
            internal bool IsFull;
        }

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
                        UpdatePreviewCamera(); // keep camera orbiting behind modal
                    else
                        DrawBrowser(new FrameInput());
                    DrawDeliveryModal(input);
                    break;
                case BrowserState.GarageView:
                    DrawGarageView(input);
                    break;
            }

            GbayRenderer.DrawCursor();
        }

        // ------------------------------------------------------------------ //
        //  Top Menu                                                           //
        // ------------------------------------------------------------------ //

        private void DrawTopMenu(FrameInput input)
        {
            // Background panel
            float panelW = 0.40f;
            float panelH = 0.40f;
            GbayRenderer.DrawRect(BROWSER_CX, 0.5f, panelW, panelH,
                GbayRenderer.ModalBg);

            // Logo
            GbayRenderer.DrawLogo(BROWSER_CX, 0.36f, 0.12f);

            // Buttons
            string[] labels = { "Vehicles", "Weapons", "My Garages" };
            bool[] enabled = { true, false, true };
            float startY = 0.42f;

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
                GbayRenderer.DrawText(labels[i], BROWSER_CX, btnY + 0.018f,
                    0.50f, text, GbayRenderer.FONT_CHALET, true);

                if (i == 1) // Weapons -- show "Coming Soon"
                {
                    GbayRenderer.DrawText("Coming Soon", BROWSER_CX, btnY + 0.050f,
                        0.32f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true);
                }
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
                else if (activateIdx == 2) // My Garages
                {
                    _state = BrowserState.GarageView;
                    _garageSafehouseIdx = 0;
                    _garageVehicleIdx = 0;
                    _garageSafehouses = GarageManager.GetSafehouses(
                        GbayShop.GetCurrentCharacter());
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

            if (GbayRenderer.HasPreviewTexture(card.Model))
            {
                // Draw dark background behind texture (in case of letterboxing)
                GbayRenderer.DrawRect(cx, topAreaCY, cardW - 0.004f, topAreaH - 0.004f,
                    Color.FromArgb(255, 20, 20, 20));
                // Draw preview image
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
            GbayRenderer.DrawText(card.Manufacturer, textLeft, textTop,
                0.26f, GbayRenderer.TextMfg, GbayRenderer.FONT_CONDENSED);

            // Vehicle name
            GbayRenderer.DrawText(card.DisplayName, textLeft, textTop + 0.028f,
                0.33f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);

            // Price
            string priceText = card.Price <= 0 ? "FREE" : $"${card.Price:N0}";
            Color priceColor = card.Price <= 0
                ? GbayRenderer.TextPriceFree : GbayRenderer.TextPrice;
            GbayRenderer.DrawText(priceText, textLeft, textTop + 0.058f,
                0.30f, priceColor, GbayRenderer.FONT_CHALET);
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
            _deliveryIndex = 0;
            _deliveryHover = -1;

            // Build delivery options (garage-only)
            _deliveryOptions.Clear();

            PedHash character = GbayShop.GetCurrentCharacter();
            var safehouses = GarageManager.GetSafehouses(character);
            foreach (var sh in safehouses)
            {
                int used = GarageManager.GetUsedSlots(sh.Id);
                int cap = GarageManager.GetCapacity(sh.Id);
                _deliveryOptions.Add(new DeliveryOption
                {
                    Label = sh.Name,
                    Info = $"{used}/{cap}",
                    SafehouseId = sh.Id,
                    IsFull = used >= cap,
                });
            }

            GbayRenderer.PlaySelect();
            _state = BrowserState.DeliveryConfirm;
        }

        private void DrawDeliveryModal(FrameInput input)
        {
            // Modal scrim
            GbayRenderer.DrawRect(0.5f, 0.5f, 1f, 1f, GbayRenderer.ModalScrim);

            // Modal panel
            float itemCount = _deliveryOptions.Count;
            float modalH = 0.12f + itemCount * MODAL_ITEM_H + 0.04f;
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

            // Options
            float optStartY = modalTop + 0.09f;
            float optLeft = BROWSER_CX - MODAL_W / 2f + 0.02f;
            float optRight = BROWSER_CX + MODAL_W / 2f - 0.02f;

            _deliveryHover = -1;

            for (int i = 0; i < _deliveryOptions.Count; i++)
            {
                var opt = _deliveryOptions[i];
                float optY = optStartY + i * MODAL_ITEM_H;
                float optCY = optY + MODAL_ITEM_H / 2f;
                bool isSel = i == _deliveryIndex;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    BROWSER_CX, optCY, MODAL_W - 0.04f, MODAL_ITEM_H);

                if (isHover && !opt.IsFull)
                    _deliveryHover = i;

                // Background highlight
                if ((isSel || isHover) && !opt.IsFull)
                {
                    GbayRenderer.DrawRect(BROWSER_CX, optCY, MODAL_W - 0.04f,
                        MODAL_ITEM_H, GbayRenderer.CardHover);
                }

                // Label
                Color labelColor = opt.IsFull ? GbayRenderer.TextDim : GbayRenderer.TextDark;
                GbayRenderer.DrawText(opt.Label, optLeft, optY + 0.008f,
                    0.30f, labelColor, GbayRenderer.FONT_CHALET);

                // Info (right side)
                Color infoColor = opt.IsFull ? GbayRenderer.TextDim : GbayRenderer.TextMfg;
                GbayRenderer.DrawText(opt.Info, optRight, optY + 0.008f,
                    0.28f, infoColor, GbayRenderer.FONT_CONDENSED, false, false, true);
            }

            // Footer hint
            float hintY = optStartY + _deliveryOptions.Count * MODAL_ITEM_H + 0.01f;
            GbayRenderer.DrawText("[Enter] Confirm   [Esc] Cancel",
                BROWSER_CX, hintY, 0.24f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED, true);

            // Input
            if (input.DirY != 0)
            {
                int next = _deliveryIndex + input.DirY;
                // Skip full safehouses
                while (next >= 0 && next < _deliveryOptions.Count
                       && _deliveryOptions[next].IsFull)
                    next += input.DirY;

                if (next >= 0 && next < _deliveryOptions.Count)
                {
                    _deliveryIndex = next;
                    GbayRenderer.PlayNav();
                }
            }

            // Mouse hover
            if (_deliveryHover >= 0)
                _deliveryIndex = _deliveryHover;

            // Accept
            bool accepted = input.Accept ||
                            (input.MouseClick && _deliveryHover >= 0);
            if (accepted && _deliveryIndex >= 0 && _deliveryIndex < _deliveryOptions.Count)
            {
                var selected = _deliveryOptions[_deliveryIndex];
                if (!selected.IsFull)
                {
                    GbayRenderer.PlaySelect();
                    _shop.ExecuteDeliverToSafehouse(
                        _pendingModel, _pendingPrice,
                        selected.SafehouseId, selected.Label);
                    ClosePreview();
                    _state = BrowserState.VehicleBrowser;
                }
                else
                {
                    GbayRenderer.PlayError();
                }
            }

            if (input.Back || input.MouseRightClick)
            {
                GbayRenderer.PlayBack();
                // Return to preview if we came from there, otherwise browser
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
            GbayRenderer.DrawText("MY GARAGES", BROWSER_LEFT + 0.07f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.TabActive, GbayRenderer.FONT_CONDENSED);

            // "Mark on Map" button (right side of header)
            float gpsBtnW = 0.12f;
            float gpsBtnH = 0.04f;
            float gpsBtnX = BROWSER_RIGHT - 0.08f;
            float gpsBtnY = HEADER_CY;
            bool gpsHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                gpsBtnX, gpsBtnY, gpsBtnW, gpsBtnH);
            Color gpsBg = gpsHover ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen;
            GbayRenderer.DrawRect(gpsBtnX, gpsBtnY, gpsBtnW, gpsBtnH, gpsBg);
            GbayRenderer.DrawText("Mark on Map", gpsBtnX, gpsBtnY - 0.012f,
                0.28f, GbayRenderer.TextWhite, GbayRenderer.FONT_CONDENSED, true);

            if (gpsHover && input.MouseClick && _garageSafehouses != null
                && _garageSafehouses.Length > 0)
            {
                var sh = _garageSafehouses[_garageSafehouseIdx];
                var pos = sh.Slots[0].Position;
                Function.Call((Hash)0xFE43368D2AA4F2FC, pos.X, pos.Y);
                GbayRenderer.PlaySelect();
                GTA.UI.Screen.ShowSubtitle(
                    $"~g~GPS set to ~w~{sh.Name}", 3000);
            }

            if (_garageSafehouses == null || _garageSafehouses.Length == 0)
            {
                GbayRenderer.DrawText("No safehouses available",
                    BROWSER_CX, 0.4f, 0.4f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);

                if (input.Back || input.MouseRightClick)
                {
                    GbayRenderer.PlayBack();
                    _state = BrowserState.TopMenu;
                }
                return;
            }

            // Safehouse tabs (horizontal)
            float tabStartX = BROWSER_LEFT + 0.02f;
            float tabW = 0.20f;
            float tabTop = TAB_Y;

            GbayRenderer.DrawRect(BROWSER_CX, TAB_CY, BROWSER_W, TAB_H,
                GbayRenderer.TabBg);

            for (int i = 0; i < _garageSafehouses.Length; i++)
            {
                var sh = _garageSafehouses[i];
                float tCX = tabStartX + i * (tabW + 0.01f) + tabW / 2f;
                bool isActive = i == _garageSafehouseIdx;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    tCX, TAB_CY, tabW, TAB_H);

                if (isHover && input.MouseClick && i != _garageSafehouseIdx)
                {
                    _garageSafehouseIdx = i;
                    _garageVehicleIdx = 0;
                    GbayRenderer.PlayNav();
                }

                if (isActive)
                    GbayRenderer.DrawRect(tCX, TAB_Y + TAB_H - 0.004f,
                        tabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);

                int used = GarageManager.GetUsedSlots(sh.Id);
                int cap = GarageManager.GetCapacity(sh.Id);
                string label = $"{sh.Name} ({used}/{cap})";
                Color tc = isActive ? GbayRenderer.TabActive : GbayRenderer.TabInactive;
                GbayRenderer.DrawText(label, tCX, tabTop + 0.008f,
                    0.25f, tc, GbayRenderer.FONT_CONDENSED, true);
            }

            // Vehicle list for selected safehouse
            var safehouse = _garageSafehouses[_garageSafehouseIdx];
            var vehicles = GarageManager.GetStoredVehicles(safehouse.Id);

            float listTop = GRID_TOP + 0.02f;
            float itemH = 0.055f;

            _garageHoverIdx = -1;

            if (vehicles.Count == 0)
            {
                GbayRenderer.DrawText("No vehicles stored",
                    BROWSER_CX, listTop + 0.05f, 0.35f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);
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

                    GbayRenderer.DrawText(name, BROWSER_LEFT + 0.06f, itemY + 0.012f,
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
                        GarageManager.RemoveVehicle(safehouse.Id, i);
                        GbayRenderer.PlaySelect();
                        GTA.UI.Screen.ShowSubtitle(
                            $"~y~{name}~w~ removed from ~b~{safehouse.Name}", 3000);
                        // Reset index since list shifted
                        _garageVehicleIdx = Math.Max(0, _garageVehicleIdx - 1);
                        return; // skip rest of frame, list changed
                    }
                }
            }

            // Keyboard navigation for garage
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

            // Keyboard remove (Enter on selected)
            if (input.Accept && vehicles.Count > 0 && _garageVehicleIdx < vehicles.Count)
            {
                var sv = vehicles[_garageVehicleIdx];
                string name = VehicleList.DisplayNames.ContainsKey(sv.Model)
                    ? VehicleList.DisplayNames[sv.Model] : sv.Model;
                GarageManager.RemoveVehicle(safehouse.Id, _garageVehicleIdx);
                GbayRenderer.PlaySelect();
                GTA.UI.Screen.ShowSubtitle(
                    $"~y~{name}~w~ removed from ~b~{safehouse.Name}", 3000);
                _garageVehicleIdx = Math.Max(0, _garageVehicleIdx - 1);
            }

            // Safehouse tab switching (Z/X)
            if (input.CategoryPrev && _garageSafehouseIdx > 0)
            {
                _garageSafehouseIdx--;
                _garageVehicleIdx = 0;
                GbayRenderer.PlayNav();
            }
            else if (input.CategoryNext && _garageSafehouseIdx < _garageSafehouses.Length - 1)
            {
                _garageSafehouseIdx++;
                _garageVehicleIdx = 0;
                GbayRenderer.PlayNav();
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
            GbayRenderer.DrawText("[Z/X] Safehouse   [Enter] Remove   [Esc] Back",
                BROWSER_CX, FOOTER_Y + 0.012f, 0.24f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED, true);
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
