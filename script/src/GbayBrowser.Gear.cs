// GbayBrowser.Gear.cs -- GBAY protection and equipment storefront.

using System;
using System.Collections.Generic;
using System.Drawing;
using GTA;

namespace ALLIN1
{
    internal struct GearCard
    {
        internal string GearId;
        internal string DisplayName;
        internal string Category;
        internal int Price;
        internal bool Owned;
        internal bool Equipped;
    }

    internal partial class GbayBrowser
    {
        private struct GearCategory
        {
            internal string Label;
            internal string[] Items;

            internal GearCategory(string label, string[] items)
            {
                Label = label;
                Items = items;
            }
        }

        private static readonly GearCategory[] GEAR_CATEGORIES =
        {
            new GearCategory("All", GearList.All),
            new GearCategory("Protection", GearList.Protection),
            new GearCategory("Equipment", GearList.Equipment),
        };

        private readonly List<GearCard> _gearFiltered = new List<GearCard>();
        private int _gearCategoryIndex;
        private int _gearPage;
        private int _gearTotalPages;
        private int _gearSelectedCard;
        private int _gearHoverCard = -1;
        private int _gearHoverTab = -1;
        private int _gearHoverUnequipCard = -1;

        private void OpenGearBrowser()
        {
            _state = BrowserState.GearBrowser;
            _gearCategoryIndex = 0;
            _gearPage = 0;
            _gearSelectedCard = 0;
            GbayRenderer.RequestDict("allin1_gear_01");
            RebuildGearList();
        }

        private void DrawGearBrowser(FrameInput input)
        {
            float aspect = GbayRenderer.GetAspectRatio();
            float cardW = CARD_H * CARD_VISUAL_ASPECT / aspect;
            float bgCY = (BROWSER_TOP + BROWSER_BOTTOM) / 2f;

            GbayRenderer.DrawElevatedPanel(BROWSER_CX, bgCY, BROWSER_W,
                BROWSER_BOTTOM - BROWSER_TOP, GbayRenderer.BodyBg);
            DrawGearHeader();
            DrawGearCategoryTabs(input);
            DrawGearGrid(input, cardW);

            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);
            bool previousClicked;
            bool nextClicked;
            DrawPager(input, _gearPage, _gearTotalPages, _gearFiltered.Count,
                out previousClicked, out nextClicked);
            bool backClicked = DrawCenteredBackButton(input);
            DrawControlHint("ENTER BUY/EQUIP   Y UNEQUIP   LB/RB PAGES");

            HandleGearInput(input, previousClicked, nextClicked, backClicked);
        }

        private void DrawGearHeader()
        {
            GbayRenderer.DrawRect(BROWSER_CX, HEADER_CY, BROWSER_W, HEADER_H,
                GbayRenderer.HeaderBg);
            GbayRenderer.DrawHeaderAccent(
                BROWSER_CX, HEADER_Y + HEADER_H, BROWSER_W);
            GbayRenderer.DrawGbayWordmark(
                BROWSER_LEFT + 0.035f, HEADER_Y + 0.010f, 0.43f, true);
            GbayRenderer.DrawTitleBadge(
                "GEAR", BROWSER_LEFT + 0.16f, HEADER_CY,
                0.13f, 0.044f, 0.35f);
            GbayRenderer.DrawMoneyBadge($"${Game.Player.Money:N0}",
                BROWSER_RIGHT - 0.01f, HEADER_CY);
        }

        private void DrawGearCategoryTabs(FrameInput input)
        {
            GbayRenderer.DrawRect(BROWSER_CX, TAB_CY, BROWSER_W, TAB_H,
                GbayRenderer.TabBg);
            float tabW = BROWSER_W / GEAR_CATEGORIES.Length;
            _gearHoverTab = -1;

            for (int i = 0; i < GEAR_CATEGORIES.Length; i++)
            {
                float tabX = BROWSER_LEFT + tabW * i + tabW / 2f;
                bool active = i == _gearCategoryIndex;
                bool hover = GbayRenderer.HitTest(
                    input.MouseX, input.MouseY, tabX, TAB_CY,
                    tabW - 0.004f, TAB_H);
                if (hover) _gearHoverTab = i;

                if (active)
                    DrawFocusedRect(tabX, TAB_CY, tabW - 0.006f,
                        TAB_H - 0.006f, GbayRenderer.BtnGreenHover);
                else if (hover)
                    GbayRenderer.DrawRect(tabX, TAB_CY, tabW - 0.004f,
                        TAB_H, GbayRenderer.TabHover);

                if (active)
                    GbayRenderer.DrawRect(tabX, TAB_Y + TAB_H - 0.004f,
                        tabW - 0.01f, 0.004f, GbayRenderer.TabIndicator);

                GbayRenderer.DrawText(GEAR_CATEGORIES[i].Label, tabX,
                    TAB_Y + 0.012f, 0.31f,
                    active ? GbayRenderer.TabActive : GbayRenderer.TabInactive,
                    GbayRenderer.FONT_CONDENSED, true);
            }
        }

        private void DrawGearGrid(FrameInput input, float cardW)
        {
            float gridW = GRID_COLS * cardW + (GRID_COLS - 1) * CARD_GAP_X;
            float gridStartX = BROWSER_CX - gridW / 2f;
            float gridStartY = GRID_TOP + 0.01f;
            int start = _gearPage * PAGE_SIZE;
            int count = Math.Min(PAGE_SIZE, _gearFiltered.Count - start);
            _gearHoverCard = -1;
            _gearHoverUnequipCard = -1;

            for (int i = 0; i < count; i++)
            {
                int col = i % GRID_COLS;
                int row = i / GRID_COLS;
                float left = gridStartX + col * (cardW + CARD_GAP_X);
                float top = gridStartY + row * (CARD_H + CARD_GAP_Y);
                float cx = left + cardW / 2f;
                float cy = top + CARD_H / 2f;
                bool selected = i == _gearSelectedCard;
                bool hover = GbayRenderer.HitTest(
                    input.MouseX, input.MouseY, cx, cy, cardW, CARD_H);
                if (hover) _gearHoverCard = i;
                GearCard card = _gearFiltered[start + i];
                float unequipX = left + cardW - 0.031f;
                float unequipY = top + 0.018f;
                bool unequipHover = card.Equipped && GbayRenderer.HitTest(
                    input.MouseX, input.MouseY, unequipX, unequipY,
                    0.054f, 0.026f);
                if (unequipHover) _gearHoverUnequipCard = i;
                DrawGearCard(card, left, top, cardW,
                    selected, hover, unequipHover);
            }
        }

        private void DrawGearCard(
            GearCard card, float left, float top, float cardW,
            bool selected, bool hovered, bool unequipHovered)
        {
            float cx = left + cardW / 2f;
            float cy = top + CARD_H / 2f;
            GbayRenderer.DrawCatalogCardSurface(
                cx, cy, cardW, CARD_H, selected, hovered);

            float previewH = CARD_H * 0.55f;
            float previewCY = top + previewH / 2f;
            GbayRenderer.DrawRect(cx, previewCY, cardW - 0.004f,
                previewH - 0.004f, Color.FromArgb(255, 30, 35, 32));
            if (!GbayRenderer.DrawEquipmentPreviewTexture(
                    card.GearId, cx, previewCY,
                    cardW - 0.004f, previewH - 0.004f))
            {
                Color fallback = card.Category == "Protection"
                    ? Color.FromArgb(255, 195, 220, 204)
                    : Color.FromArgb(255, 205, 220, 214);
                GbayRenderer.DrawRect(cx, previewCY, cardW - 0.004f,
                    previewH - 0.004f, fallback);
                GbayRenderer.DrawText(card.Category, cx,
                    top + previewH * 0.35f, 0.27f, GbayRenderer.TextDark,
                    GbayRenderer.FONT_CONDENSED, true);
            }

            // The compact overlay is a direct mouse action while Y provides
            // the same controller/keyboard action for the selected card.
            // Unequipped gear is discarded and must be purchased again.
            if (card.Equipped)
            {
                float unequipX = left + cardW - 0.031f;
                float unequipY = top + 0.018f;
                Color actionBg = unequipHovered
                    ? GbayRenderer.BtnGreenHover : GbayRenderer.BtnGreen;
                GbayRenderer.DrawBorderedRect(unequipX, unequipY,
                    0.054f, 0.026f, actionBg, GbayRenderer.TextWhite, 0.0015f);
                GbayRenderer.DrawText("UNEQUIP", unequipX,
                    unequipY - 0.009f, 0.215f, GbayRenderer.TextWhite,
                    GbayRenderer.FONT_CONDENSED, true);
            }

            float textTop = top + previewH + 0.005f;
            float textLeft = left + 0.008f;
            GbayRenderer.DrawTextFit(card.DisplayName, textLeft,
                textTop + 0.005f, 0.39f, 0.28f, cardW - 0.016f,
                GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);
            string price = card.Equipped ? "EQUIPPED" : card.Owned ? "OWNED"
                : card.Price <= 0 ? "FREE" : $"${card.Price:N0}";
            Color statusText = card.Equipped ? GbayRenderer.TextWhite
                : card.Owned || card.Price <= 0
                    ? GbayRenderer.Success : GbayRenderer.TextPrice;
            Color statusFill = card.Equipped ? GbayRenderer.HeaderBg
                : card.Owned || card.Price <= 0
                    ? GbayRenderer.AccentSoft : GbayRenderer.AccentSoft;
            GbayRenderer.DrawStatusPill(price,
                left + cardW - 0.058f, textTop + 0.091f, 0.104f,
                statusFill, statusText);
        }

        private void HandleGearInput(
            FrameInput input, bool previousClicked, bool nextClicked,
            bool backClicked)
        {
            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.ReleaseDict("allin1_gear_01");
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
                return;
            }

            if (input.MouseClick && _gearHoverTab >= 0 &&
                _gearHoverTab != _gearCategoryIndex)
            {
                SetGearCategory(_gearHoverTab);
                return;
            }
            if (input.CategoryPrev && _gearCategoryIndex > 0)
                SetGearCategory(_gearCategoryIndex - 1);
            else if (input.CategoryNext &&
                     _gearCategoryIndex < GEAR_CATEGORIES.Length - 1)
                SetGearCategory(_gearCategoryIndex + 1);

            bool previous = input.PageLeft || previousClicked || input.ScrollDelta < 0;
            bool next = input.PageRight || nextClicked || input.ScrollDelta > 0;
            if (previous && _gearPage > 0)
            {
                _gearPage--;
                _gearSelectedCard = Math.Min(_gearSelectedCard, GetGearPageCount() - 1);
                GbayRenderer.PlayNav();
                return;
            }
            if (next && _gearPage < _gearTotalPages - 1)
            {
                _gearPage++;
                _gearSelectedCard = Math.Min(_gearSelectedCard, GetGearPageCount() - 1);
                GbayRenderer.PlayNav();
                return;
            }

            if ((input.DirX != 0 || input.DirY != 0) && _gearFiltered.Count > 0)
            {
                int col = _gearSelectedCard % GRID_COLS;
                int row = _gearSelectedCard / GRID_COLS;
                int max = GetGearPageCount() - 1;
                if (input.DirX != 0)
                    col = Math.Max(0, Math.Min(GRID_COLS - 1, col + input.DirX));
                if (input.DirY != 0)
                    row = Math.Max(0, Math.Min(GRID_ROWS - 1, row + input.DirY));
                int selected = Math.Min(max, row * GRID_COLS + col);
                if (selected != _gearSelectedCard)
                {
                    _gearSelectedCard = selected;
                    GbayRenderer.PlayNav();
                }
            }

            if (_gearHoverCard >= 0 && (input.MouseMoved || input.MouseClick))
                _gearSelectedCard = _gearHoverCard;

            if (input.MouseClick && _gearHoverUnequipCard >= 0)
            {
                int unequipIndex = _gearPage * PAGE_SIZE + _gearHoverUnequipCard;
                if (unequipIndex < _gearFiltered.Count)
                {
                    GbayRenderer.PlaySelect();
                    _shop.ExecuteUnequipGear(_gearFiltered[unequipIndex].GearId);
                    _gearSelectedCard = _gearHoverUnequipCard;
                    RebuildGearList();
                }
                return;
            }

            if (input.FilterNext && _gearFiltered.Count > 0)
            {
                int unequipIndex = _gearPage * PAGE_SIZE + _gearSelectedCard;
                if (unequipIndex < _gearFiltered.Count)
                {
                    GearCard selected = _gearFiltered[unequipIndex];
                    if (selected.Equipped)
                    {
                        GbayRenderer.PlaySelect();
                        _shop.ExecuteUnequipGear(selected.GearId);
                        RebuildGearList();
                    }
                    else
                        GTA.UI.Screen.ShowSubtitle(
                            selected.Owned ? "~y~That item is already unequipped."
                                           : "~y~Purchase this item first.", 2500);
                }
                return;
            }

            bool accept = input.Accept || (input.MouseClick && _gearHoverCard >= 0);
            if (accept && _gearFiltered.Count > 0)
            {
                int index = _gearPage * PAGE_SIZE + _gearSelectedCard;
                if (index < _gearFiltered.Count)
                {
                    GearCard card = _gearFiltered[index];
                    GbayRenderer.PlaySelect();
                    if (card.Equipped)
                        GTA.UI.Screen.ShowSubtitle(
                            "~g~Already equipped.~w~ Press ~y~Y~w~ or select Unequip to remove it.",
                            3000);
                    else if (card.Owned)
                    {
                        _shop.ExecuteEquipGear(card.GearId);
                        RebuildGearList();
                    }
                    else
                    {
                        _shop.ExecuteGiveGear(card.GearId, card.Price);
                        RebuildGearList();
                    }
                }
            }
        }

        private void SetGearCategory(int category)
        {
            _gearCategoryIndex = Math.Max(0,
                Math.Min(GEAR_CATEGORIES.Length - 1, category));
            _gearPage = 0;
            _gearSelectedCard = 0;
            RebuildGearList();
            GbayRenderer.PlayNav();
        }

        private void RebuildGearList(bool preserveSelection = false)
        {
            string selectedGear = null;
            if (preserveSelection && _gearFiltered.Count > 0)
            {
                int selectedIndex = _gearPage * PAGE_SIZE + _gearSelectedCard;
                if (selectedIndex >= 0 && selectedIndex < _gearFiltered.Count)
                    selectedGear = _gearFiltered[selectedIndex].GearId;
            }
            _gearFiltered.Clear();
            foreach (string gearId in GEAR_CATEGORIES[_gearCategoryIndex].Items)
            {
                _gearFiltered.Add(new GearCard
                {
                    GearId = gearId,
                    DisplayName = GearList.DisplayNames.TryGetValue(
                        gearId, out string name) ? name : gearId,
                    Category = GearList.CategoryNames.TryGetValue(
                        gearId, out string category) ? category : "Gear",
                    Price = _shop.FreeMode ? 0
                        : GearList.Prices.TryGetValue(gearId, out int price) ? price : 0,
                    Owned = _shop.IsGearOwned(gearId),
                    Equipped = _shop.IsGearEquipped(gearId),
                });
            }
            _gearTotalPages = Math.Max(
                1, (_gearFiltered.Count + PAGE_SIZE - 1) / PAGE_SIZE);
            int refreshedIndex = preserveSelection &&
                !string.IsNullOrWhiteSpace(selectedGear)
                ? _gearFiltered.FindIndex(card => string.Equals(
                    card.GearId, selectedGear,
                    StringComparison.OrdinalIgnoreCase)) : -1;
            if (refreshedIndex >= 0)
            {
                _gearPage = refreshedIndex / PAGE_SIZE;
                _gearSelectedCard = refreshedIndex % PAGE_SIZE;
            }
            else
            {
                _gearPage = Math.Max(0,
                    Math.Min(_gearPage, _gearTotalPages - 1));
                int count = Math.Max(0, Math.Min(PAGE_SIZE,
                    _gearFiltered.Count - _gearPage * PAGE_SIZE));
                _gearSelectedCard = count == 0 ? 0
                    : Math.Max(0, Math.Min(_gearSelectedCard, count - 1));
            }
        }

        private int GetGearPageCount()
        {
            int start = _gearPage * PAGE_SIZE;
            return Math.Max(0, Math.Min(PAGE_SIZE, _gearFiltered.Count - start));
        }
    }
}
