// GbayBrowserCustomize.cs -- Garage floor customization UI (partial class).
//
// Allows players to customize the visual theme of each garage floor
// by selecting entity set options per category (Floor, Style, Walls, Decor, Lighting).
// Accessible from the My Garage view via the "Customize Floors" button or Q key.

using System.Drawing;
using GTA;

namespace ALLIN1
{
    internal partial class GbayBrowser
    {
        // Garage customization state
        private int _customFloor;      // which floor is being edited (0-2)
        private int _customCatIdx;     // selected category row (0-4)
        private int _customHoverCat = -1;
        private int _customHoverOpt = -1;

        private void DrawGarageCustomize(FrameInput input)
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
            GbayRenderer.DrawText("CUSTOMIZE GARAGE", BROWSER_LEFT + 0.07f, HEADER_Y + 0.018f,
                0.38f, GbayRenderer.TabActive, GbayRenderer.FONT_CONDENSED);

            // Eclipse Towers is one garage. Multi-floor tabs are only valid
            // while the player is inside the dedicated three-floor garage.
            int floorCount = GarageManager.IsPlayerInFloorGarage ? 3 : 1;
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
                if (isActive || isHover)
                    GbayRenderer.DrawRect(tabCX, HEADER_CY, floorTabW, HEADER_H - 0.01f, tabBg);

                GbayRenderer.DrawText(floorCount == 1 ? "Garage" : $"Floor {f + 1}", tabCX, HEADER_Y + 0.018f,
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
            float rowH = 0.12f;
            float rowGap = 0.015f;
            float optBtnW = 0.18f;
            float optBtnH = 0.05f;
            float optGap = 0.015f;
            float optStartX = BROWSER_CX - ((GarageManager.CUSTOM_OPTION_COUNT * optBtnW +
                (GarageManager.CUSTOM_OPTION_COUNT - 1) * optGap) / 2f);

            _customHoverCat = -1;
            _customHoverOpt = -1;

            for (int cat = 0; cat < GarageManager.CUSTOM_CATEGORY_COUNT; cat++)
            {
                float catY = rowTop + cat * (rowH + rowGap);
                float catCY = catY + rowH / 2f;
                bool isCatSelected = cat == _customCatIdx;
                int currentChoice = GarageManager.GetFloorThemeChoice(_customFloor, cat);

                // Category row background
                Color rowBg = isCatSelected
                    ? Color.FromArgb(30, 100, 200, 100)
                    : Color.FromArgb(15, 255, 255, 255);
                GbayRenderer.DrawRect(BROWSER_CX, catCY, BROWSER_W - 0.04f, rowH, rowBg);

                // Category label (left)
                GbayRenderer.DrawText(GarageManager.CUSTOM_CATEGORY_NAMES[cat],
                    BROWSER_LEFT + 0.06f, catY + 0.015f,
                    0.38f, isCatSelected ? GbayRenderer.TextDark : GbayRenderer.TextMfg,
                    GbayRenderer.FONT_CHALET);

                // Option buttons (centered below label)
                float optY = catY + 0.05f;
                float optCY = optY + optBtnH / 2f;

                for (int opt = 0; opt < GarageManager.CUSTOM_OPTION_COUNT; opt++)
                {
                    float btnX = optStartX + opt * (optBtnW + optGap);
                    float btnCX = btnX + optBtnW / 2f;

                    bool isChosen = opt == currentChoice;
                    bool isOptHover = GbayRenderer.HitTest(input.MouseX, input.MouseY,
                        btnCX, optCY, optBtnW, optBtnH);

                    if (isOptHover)
                    {
                        _customHoverCat = cat;
                        _customHoverOpt = opt;
                    }

                    Color btnBg;
                    Color btnText;
                    if (isChosen)
                    {
                        btnBg = GbayRenderer.BtnGreenHover;
                        btnText = GbayRenderer.TextWhite;
                    }
                    else if (isOptHover)
                    {
                        btnBg = GbayRenderer.CardHover;
                        btnText = GbayRenderer.TextDark;
                    }
                    else
                    {
                        btnBg = GbayRenderer.CardBg;
                        btnText = GbayRenderer.TextDark;
                    }

                    GbayRenderer.DrawBorderedRect(btnCX, optCY, optBtnW, optBtnH,
                        btnBg, isChosen ? GbayRenderer.CardBorderSel : GbayRenderer.CardBorder, 0.002f);
                    GbayRenderer.DrawText(GarageManager.CUSTOM_OPTION_LABELS[cat][opt],
                        btnCX, optY + 0.01f, 0.28f, btnText,
                        GbayRenderer.FONT_CONDENSED, true);

                    // Mouse click to select
                    if (isOptHover && input.MouseClick && !isChosen)
                    {
                        GarageManager.SetFloorThemeChoice(_customFloor, cat, opt);
                        GbayRenderer.PlaySelect();
                    }
                }
            }

            // Keyboard input
            HandleGarageCustomizeInput(input);

            // Footer
            GbayRenderer.DrawRect(BROWSER_CX, FOOTER_CY, BROWSER_W, FOOTER_H,
                GbayRenderer.FooterBg);

            string inGarageHint = GarageManager.IsPlayerInFloorGarage
                ? "  (changes apply live)" : "";
            string floorHint = floorCount > 1 ? "   [Z/X] Floor" : "";
            GbayRenderer.DrawText(
                $"[Up/Down] Category   [Left/Right] Option{floorHint}   [Esc] Back{inGarageHint}",
                BROWSER_CX, FOOTER_Y + 0.012f, 0.24f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED, true);
        }

        private void HandleGarageCustomizeInput(FrameInput input)
        {
            // Navigate categories (Up/Down)
            if (input.DirY != 0)
            {
                int next = _customCatIdx + input.DirY;
                if (next >= 0 && next < GarageManager.CUSTOM_CATEGORY_COUNT)
                {
                    _customCatIdx = next;
                    GbayRenderer.PlayNav();
                }
            }

            // Change option (Left/Right)
            if (input.DirX != 0)
            {
                int current = GarageManager.GetFloorThemeChoice(_customFloor, _customCatIdx);
                int next = current + input.DirX;
                if (next >= 0 && next < GarageManager.CUSTOM_OPTION_COUNT)
                {
                    GarageManager.SetFloorThemeChoice(_customFloor, _customCatIdx, next);
                    GbayRenderer.PlaySelect();
                }
            }

            // Switch floor (Z/X)
            if (GarageManager.IsPlayerInFloorGarage && input.CategoryPrev && _customFloor > 0)
            {
                _customFloor--;
                GbayRenderer.PlayNav();
            }
            else if (GarageManager.IsPlayerInFloorGarage && input.CategoryNext && _customFloor < 2)
            {
                _customFloor++;
                GbayRenderer.PlayNav();
            }

            // Back
            if (input.Back || input.MouseRightClick)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.GarageView;
            }
        }
    }
}
