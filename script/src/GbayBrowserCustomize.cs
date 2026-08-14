// GbayBrowserCustomize.cs -- Garage floor customization UI (partial class).
//
// Allows players to customize the visual theme of the regular garages and the
// Davis Auto Shop.  Davis uses its own variable-length categories because the
// Tuners interior has nine styles/tints plus optional upgrade entity sets.

using System.Drawing;
using GTA;

namespace ALLIN1
{
    internal partial class GbayBrowser
    {
        // Garage customization state
        private int _customFloor;      // which floor is being edited (0-2)
        private int _customCatIdx;     // selected category row (0-4)

        private void DrawGarageCustomize(FrameInput input)
        {
            bool floorGarage = _garageLocationIndex == 1;
            bool davisGarage = _garageLocationIndex == 2;
            if (!floorGarage && !davisGarage)
            {
                _state = BrowserState.GarageView;
                return;
            }
            int categoryCount = davisGarage
                ? GarageManager.DAVIS_CUSTOM_CATEGORY_COUNT
                : GarageManager.CUSTOM_CATEGORY_COUNT;
            if (_customCatIdx >= categoryCount) _customCatIdx = categoryCount - 1;

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
                davisGarage ? "CUSTOMIZE AUTO SHOP" : "CUSTOMIZE THREE FLOORS",
                BROWSER_LEFT + 0.21f, HEADER_CY,
                0.23f, 0.044f, 0.34f);

            // Eclipse Garage is one garage. Multi-floor tabs are only valid
            // while the player is inside Harmony Garage.
            int floorCount = floorGarage ? 3 : 1;
            if (floorCount == 1) _customFloor = 0;
            float floorTabW = 0.08f;
            float floorTabStartX = BROWSER_RIGHT - (floorCount == 1 ? 0.10f : 0.28f);
            for (int f = 0; f < floorCount; f++)
            {
                float tabX = floorTabStartX + f * (floorTabW + 0.01f);
                float tabCX = tabX + floorTabW / 2f;
                bool isActive = f == _customFloor;
                bool isHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                    tabCX, HEADER_CY, floorTabW, HEADER_H);

                Color tabBg = isActive ? GbayRenderer.BtnGreenHover
                            : isHover ? GbayRenderer.TabHover
                            : Color.FromArgb(0, 0, 0, 0);
                if (isActive)
                    DrawFocusedRect(tabCX, HEADER_CY, floorTabW,
                        HEADER_H - 0.014f, tabBg);
                else if (isHover)
                    GbayRenderer.DrawRect(tabCX, HEADER_CY, floorTabW,
                        HEADER_H - 0.01f, tabBg);

                string floorLabel = davisGarage ? "Auto Shop"
                    : floorCount == 1 ? "Garage" : $"Floor {f + 1}";
                GbayRenderer.DrawText(floorLabel, tabCX, HEADER_Y + 0.018f,
                    0.32f, isActive ? GbayRenderer.TextWhite : GbayRenderer.HeaderText,
                    GbayRenderer.FONT_CONDENSED, true);

                if (isHover && input.MouseClick && !isActive)
                {
                    _customFloor = f;
                    GbayRenderer.PlayNav();
                }
            }

            // Category rows
            float rowTop = TAB_Y + 0.02f;
            float rowH = davisGarage ? 0.095f : 0.12f;
            float rowGap = davisGarage ? 0.009f : 0.015f;
            float optBtnH = 0.05f;

            for (int cat = 0; cat < categoryCount; cat++)
            {
                float catY = rowTop + cat * (rowH + rowGap);
                float catCY = catY + rowH / 2f;
                bool isCatSelected = cat == _customCatIdx;
                int currentChoice = davisGarage
                    ? GarageManager.GetDavisCustomizationChoice(cat)
                    : GarageManager.GetFloorThemeChoice(_customFloor, cat);

                // Category row background
                Color rowBg = isCatSelected
                    ? Color.FromArgb(30, 100, 200, 100)
                    : Color.FromArgb(15, 255, 255, 255);
                GbayRenderer.DrawRect(BROWSER_CX, catCY, BROWSER_W - 0.04f, rowH, rowBg);

                // Category label (left)
                string categoryName = davisGarage
                    ? GarageManager.DAVIS_CUSTOM_CATEGORY_NAMES[cat]
                    : GarageManager.CUSTOM_CATEGORY_NAMES[cat];
                GbayRenderer.DrawText(categoryName,
                    BROWSER_LEFT + 0.06f, catY + 0.015f,
                    0.38f, isCatSelected ? GbayRenderer.TextDark : GbayRenderer.TextMfg,
                    GbayRenderer.FONT_CHALET);

                // Option buttons (centered below label)
                float optY = catY + 0.05f;
                float optCY = optY + optBtnH / 2f;

                int optionCount = davisGarage
                    ? GarageManager.GetDavisCustomizationOptionCount(cat)
                    : GarageManager.GetFloorCustomizationOptionCount(cat);
                if (davisGarage)
                {
                    DrawDavisCustomizationCarousel(input, cat, currentChoice,
                        optionCount, optCY, optBtnH, isCatSelected);
                    continue;
                }

                DrawFloorCustomizationCarousel(input, cat, currentChoice,
                    optionCount, optCY, optBtnH, isCatSelected);
            }

            // Footer
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);
            bool backClicked = DrawCenteredBackButton(input);

            string inGarageHint = (davisGarage && GarageManager.IsPlayerInDavisGarage) ||
                (!davisGarage && GarageManager.IsPlayerInFloorGarage)
                ? "   LIVE" : "";
            string floorHint = floorCount > 1 ? "   Z/X FLOOR" : "";
            DrawControlHint(
                $"ARROWS SELECT{floorHint}{inGarageHint}");

            // Keyboard input
            HandleGarageCustomizeInput(input, backClicked, davisGarage,
                categoryCount);
        }

        private void DrawDavisCustomizationCarousel(
            FrameInput input, int category, int currentChoice, int optionCount,
            float centerY, float height, bool hasKeyboardFocus)
        {
            const float arrowW = 0.055f;
            const float choiceW = 0.34f;
            const float gap = 0.010f;
            float choiceX = BROWSER_CX + 0.08f;
            float previousX = choiceX - choiceW / 2f - gap - arrowW / 2f;
            float nextX = choiceX + choiceW / 2f + gap + arrowW / 2f;
            bool previousHover = GbayRenderer.HitTest(
                input.MouseX, input.MouseY, previousX, centerY, arrowW, height);
            bool nextHover = GbayRenderer.HitTest(
                input.MouseX, input.MouseY, nextX, centerY, arrowW, height);

            Color arrowFill = GbayRenderer.CardBg;
            GbayRenderer.DrawBorderedRect(previousX, centerY, arrowW, height,
                previousHover ? GbayRenderer.CardHover : arrowFill,
                GbayRenderer.CardBorder, 0.002f);
            GbayRenderer.DrawBorderedRect(nextX, centerY, arrowW, height,
                nextHover ? GbayRenderer.CardHover : arrowFill,
                GbayRenderer.CardBorder, 0.002f);
            GbayRenderer.DrawText("<", previousX, centerY - 0.015f, 0.34f,
                GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);
            GbayRenderer.DrawText(">", nextX, centerY - 0.015f, 0.34f,
                GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);

            GbayRenderer.DrawBorderedRect(choiceX, centerY, choiceW, height,
                GbayRenderer.BtnGreenHover,
                hasKeyboardFocus ? FocusBorderColor() : GbayRenderer.CardBorderSel,
                hasKeyboardFocus ? FocusBorderWidth() : 0.002f);
            string label = GarageManager.DAVIS_CUSTOM_OPTION_LABELS
                [category][currentChoice];
            GbayRenderer.DrawTextFit(
                $"{label}  {currentChoice + 1}/{optionCount}", choiceX,
                centerY - 0.014f, 0.28f, 0.20f, choiceW - 0.018f,
                GbayRenderer.TextWhite, GbayRenderer.FONT_CONDENSED, true);

            if (input.MouseClick && previousHover)
            {
                int previous = (currentChoice - 1 + optionCount) % optionCount;
                GarageManager.SetDavisCustomizationChoice(category, previous);
                GbayRenderer.PlaySelect();
            }
            else if (input.MouseClick && nextHover)
            {
                int next = (currentChoice + 1) % optionCount;
                GarageManager.SetDavisCustomizationChoice(category, next);
                GbayRenderer.PlaySelect();
            }
        }

        private void DrawFloorCustomizationCarousel(
            FrameInput input, int category, int currentChoice, int optionCount,
            float centerY, float height, bool hasKeyboardFocus)
        {
            const float arrowW = 0.055f;
            const float choiceW = 0.34f;
            const float gap = 0.010f;
            float choiceX = BROWSER_CX + 0.08f;
            float previousX = choiceX - choiceW / 2f - gap - arrowW / 2f;
            float nextX = choiceX + choiceW / 2f + gap + arrowW / 2f;
            bool previousHover = GbayRenderer.HitTest(
                input.MouseX, input.MouseY, previousX, centerY, arrowW, height);
            bool nextHover = GbayRenderer.HitTest(
                input.MouseX, input.MouseY, nextX, centerY, arrowW, height);

            GbayRenderer.DrawBorderedRect(previousX, centerY, arrowW, height,
                previousHover ? GbayRenderer.CardHover : GbayRenderer.CardBg,
                GbayRenderer.CardBorder, 0.002f);
            GbayRenderer.DrawBorderedRect(nextX, centerY, arrowW, height,
                nextHover ? GbayRenderer.CardHover : GbayRenderer.CardBg,
                GbayRenderer.CardBorder, 0.002f);
            GbayRenderer.DrawText("<", previousX, centerY - 0.015f, 0.34f,
                GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);
            GbayRenderer.DrawText(">", nextX, centerY - 0.015f, 0.34f,
                GbayRenderer.TextDark, GbayRenderer.FONT_CHALET, true);

            GbayRenderer.DrawBorderedRect(choiceX, centerY, choiceW, height,
                GbayRenderer.BtnGreenHover,
                hasKeyboardFocus ? FocusBorderColor() : GbayRenderer.CardBorderSel,
                hasKeyboardFocus ? FocusBorderWidth() : 0.002f);
            string label = GarageManager.CUSTOM_OPTION_LABELS[category][currentChoice];
            GbayRenderer.DrawTextFit(
                $"{label}  {currentChoice + 1}/{optionCount}", choiceX,
                centerY - 0.014f, 0.28f, 0.20f, choiceW - 0.018f,
                GbayRenderer.TextWhite, GbayRenderer.FONT_CONDENSED, true);

            if (input.MouseClick && previousHover)
            {
                int previous = (currentChoice - 1 + optionCount) % optionCount;
                GarageManager.SetFloorThemeChoice(_customFloor, category, previous);
                GbayRenderer.PlaySelect();
            }
            else if (input.MouseClick && nextHover)
            {
                int next = (currentChoice + 1) % optionCount;
                GarageManager.SetFloorThemeChoice(_customFloor, category, next);
                GbayRenderer.PlaySelect();
            }
        }

        private void HandleGarageCustomizeInput(
            FrameInput input, bool backClicked, bool davisGarage,
            int categoryCount)
        {
            // Navigate categories (Up/Down)
            if (input.DirY != 0)
            {
                int next = _customCatIdx + input.DirY;
                if (next >= 0 && next < categoryCount)
                {
                    _customCatIdx = next;
                    GbayRenderer.PlayNav();
                }
            }

            // Change option (Left/Right)
            if (input.DirX != 0)
            {
                int current = davisGarage
                    ? GarageManager.GetDavisCustomizationChoice(_customCatIdx)
                    : GarageManager.GetFloorThemeChoice(_customFloor, _customCatIdx);
                int optionCount = davisGarage
                    ? GarageManager.GetDavisCustomizationOptionCount(_customCatIdx)
                    : GarageManager.GetFloorCustomizationOptionCount(_customCatIdx);
                int next = (current + input.DirX + optionCount) % optionCount;
                if (next >= 0 && next < optionCount)
                {
                    if (davisGarage)
                        GarageManager.SetDavisCustomizationChoice(_customCatIdx, next);
                    else
                        GarageManager.SetFloorThemeChoice(
                            _customFloor, _customCatIdx, next);
                    GbayRenderer.PlaySelect();
                }
            }

            // Switch floor (Z/X)
            if (!davisGarage && GarageManager.IsPlayerInFloorGarage &&
                input.CategoryPrev && _customFloor > 0)
            {
                _customFloor--;
                GbayRenderer.PlayNav();
            }
            else if (!davisGarage && GarageManager.IsPlayerInFloorGarage &&
                input.CategoryNext && _customFloor < 2)
            {
                _customFloor++;
                GbayRenderer.PlayNav();
            }

            // Back
            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.GarageView;
            }
        }
    }
}
