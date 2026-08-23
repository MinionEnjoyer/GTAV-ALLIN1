// Receipt-authorized add-on routes for GBAY.
using System;
using System.Collections.Generic;

namespace ALLIN1
{
    internal partial class GbayBrowser
    {
        private int _addonIndex;
        private int _addonScroll;
        private int _addonHover = -1;
        private const int ADDON_VISIBLE_ROWS = 7;

        private void OpenAddons()
        {
            IReadOnlyList<GbayAddonAction> actions =
                Allin1ExtensionApi.GetGbayActions();
            if (actions.Count == 0)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~y~No enabled add-on actions are available.", 2500);
                return;
            }
            _addonIndex = Math.Max(0, Math.Min(_addonIndex, actions.Count - 1));
            _addonScroll = Math.Max(0, Math.Min(
                _addonScroll, Math.Max(0, actions.Count - ADDON_VISIBLE_ROWS)));
            _state = BrowserState.Addons;
        }

        private void DrawAddons(FrameInput input)
        {
            IReadOnlyList<GbayAddonAction> actions =
                Allin1ExtensionApi.GetGbayActions();
            if (actions.Count == 0)
            {
                _state = BrowserState.TopMenu;
                _topMenuIndex = 5;
                return;
            }

            _addonIndex = Math.Max(0, Math.Min(_addonIndex, actions.Count - 1));
            if (_addonIndex < _addonScroll) _addonScroll = _addonIndex;
            if (_addonIndex >= _addonScroll + ADDON_VISIBLE_ROWS)
                _addonScroll = _addonIndex - ADDON_VISIBLE_ROWS + 1;
            _addonScroll = Math.Max(0, Math.Min(
                _addonScroll, Math.Max(0, actions.Count - ADDON_VISIBLE_ROWS)));

            const float panelW = 0.62f;
            const float panelH = 0.82f;
            const float rowW = 0.54f;
            const float rowH = 0.074f;
            const float rowTop = 0.205f;
            const float rowGap = 0.012f;
            GbayRenderer.DrawElevatedPanel(
                BROWSER_CX, 0.49f, panelW, panelH, GbayRenderer.ModalBg);
            GbayRenderer.DrawGbayWordmark(BROWSER_CX, 0.070f, 0.58f);
            GbayRenderer.DrawTitleBadge(
                "ADD-ONS", BROWSER_CX, 0.145f, 0.30f, 0.055f, 0.48f);

            _addonHover = -1;
            int visible = Math.Min(
                ADDON_VISIBLE_ROWS, actions.Count - _addonScroll);
            for (int row = 0; row < visible; row++)
            {
                int index = _addonScroll + row;
                GbayAddonAction action = actions[index];
                float centerY = rowTop + row * (rowH + rowGap) + rowH / 2f;
                bool hover = GbayRenderer.HitTest(
                    input.MouseX, input.MouseY, BROWSER_CX, centerY, rowW, rowH);
                if (hover) _addonHover = index;
                bool selected = index == _addonIndex;
                GbayRenderer.DrawMenuTile(
                    BROWSER_CX, centerY, rowW, rowH,
                    action.Label, action.Description,
                    selected, hover);
            }

            string position = (_addonIndex + 1) + " / " + actions.Count;
            GbayRenderer.DrawText(
                position, BROWSER_CX, 0.815f, 0.225f,
                GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true);
            bool backClicked = DrawCenteredBackButton(
                input, 0.865f, 0.20f, "Back", false);

            if (input.DirY != 0 || input.ScrollDelta != 0)
            {
                int direction = input.DirY != 0
                    ? input.DirY : input.ScrollDelta;
                _addonIndex = (_addonIndex + direction + actions.Count) %
                    actions.Count;
                GbayRenderer.PlayNav();
            }
            int activate = input.MouseClick && _addonHover >= 0
                ? _addonHover : _addonIndex;
            if (input.Accept || (input.MouseClick && _addonHover >= 0))
            {
                GbayRenderer.PlaySelect();
                Allin1ExtensionApi.InvokeGbayAction(actions[activate]);
            }
            if (input.Back || input.MouseRightClick || backClicked)
            {
                GbayRenderer.PlayBack();
                _state = BrowserState.TopMenu;
                _topMenuIndex = 5;
            }
        }
    }
}
