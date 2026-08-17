// Launcher-configurable controller bindings shared by ALLIN1 scripts.
using System;
using System.Collections.Generic;
using System.IO;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal static class ControllerBindings
    {
        internal static bool Enabled { get; private set; } = true;
        internal static Control OpenGbay { get; private set; } = Control.FrontendRdown;
        internal static Control OpenGbayModifier { get; private set; } = Control.FrontendLb;
        internal static Control NightVision { get; private set; } = Control.FrontendLeft;
        internal static Control NightVisionModifier { get; private set; } = Control.FrontendLb;
        internal static Control SeatSelector { get; private set; } = Control.FrontendRight;
        internal static Control SeatSelectorModifier { get; private set; } = Control.FrontendLb;

        internal static Control Accept { get; private set; } = Control.FrontendAccept;
        internal static Control Back { get; private set; } = Control.FrontendCancel;
        internal static Control Up { get; private set; } = Control.FrontendUp;
        internal static Control Down { get; private set; } = Control.FrontendDown;
        internal static Control Left { get; private set; } = Control.FrontendLeft;
        internal static Control Right { get; private set; } = Control.FrontendRight;
        internal static Control PageLeft { get; private set; } = Control.FrontendLb;
        internal static Control PageRight { get; private set; } = Control.FrontendRb;
        internal static Control CategoryPrev { get; private set; } = Control.FrontendLt;
        internal static Control CategoryNext { get; private set; } = Control.FrontendRt;
        internal static Control Filter { get; private set; } = Control.FrontendY;
        internal static Control Search { get; private set; } = Control.FrontendX;
        internal static Control Favorite { get; private set; } = Control.FrontendRdown;

        internal static void Load(string path)
        {
            ResetDefaults();
            if (!File.Exists(path)) return;
            try
            {
                string section = "";
                foreach (string raw in File.ReadAllLines(path))
                {
                    string line = raw.Trim();
                    if (line.Length == 0 || line.StartsWith("#")) continue;
                    if (line.StartsWith("[") && line.EndsWith("]"))
                    {
                        section = line.Substring(1, line.Length - 2).Trim();
                        continue;
                    }
                    if (!section.Equals("script", StringComparison.OrdinalIgnoreCase)) continue;
                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;
                    string key = line.Substring(0, eq).Trim().ToLowerInvariant();
                    string value = line.Substring(eq + 1).Trim().Trim('"', '\'');
                    if (key == "controller_enabled")
                    {
                        Enabled = value.Equals("true", StringComparison.OrdinalIgnoreCase);
                        continue;
                    }
                    if (!Enum.TryParse(value, true, out Control parsed)) continue;
                    Assign(key, parsed);
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("Controller", "bindings_load_failed", ex);
            }
        }

        private static void Assign(string key, Control value)
        {
            switch (key)
            {
                case "controller_open_gbay": OpenGbay = value; break;
                case "controller_open_gbay_modifier": OpenGbayModifier = value; break;
                case "controller_night_vision": NightVision = value; break;
                case "controller_night_vision_modifier": NightVisionModifier = value; break;
                case "controller_seat_selector": SeatSelector = value; break;
                case "controller_seat_selector_modifier": SeatSelectorModifier = value; break;
                case "controller_accept": Accept = value; break;
                case "controller_back": Back = value; break;
                case "controller_up": Up = value; break;
                case "controller_down": Down = value; break;
                case "controller_left": Left = value; break;
                case "controller_right": Right = value; break;
                case "controller_page_left": PageLeft = value; break;
                case "controller_page_right": PageRight = value; break;
                case "controller_category_prev": CategoryPrev = value; break;
                case "controller_category_next": CategoryNext = value; break;
                case "controller_filter": Filter = value; break;
                case "controller_search": Search = value; break;
                case "controller_favorite": Favorite = value; break;
            }
        }

        internal static bool JustPressed(Control control)
        {
            // Disabling controller support must not disable keyboard navigation,
            // because GTA exposes both devices through the same frontend controls.
            if (!Enabled && Game.LastInputMethod == InputMethod.GamePad) return false;
            return Game.IsControlJustPressed(control) || Function.Call<bool>(
                Hash.IS_DISABLED_CONTROL_JUST_PRESSED, 0, (int)control);
        }

        internal static bool Pressed(Control control) => Enabled &&
            (Game.IsControlPressed(control) || Function.Call<bool>(
                Hash.IS_DISABLED_CONTROL_PRESSED, 0, (int)control));

        internal static bool ChordJustPressed(Control modifier, Control action) =>
            Enabled && Pressed(modifier) && JustPressed(action);

        internal static bool ChordPressed(Control modifier, Control action) =>
            Enabled && Pressed(modifier) && Pressed(action);

        internal static IEnumerable<Control> MenuControls
        {
            get
            {
                yield return Accept; yield return Back;
                yield return Up; yield return Down; yield return Left; yield return Right;
                yield return PageLeft; yield return PageRight;
                yield return CategoryPrev; yield return CategoryNext;
                yield return Filter; yield return Search; yield return Favorite;
            }
        }

        private static void ResetDefaults()
        {
            Enabled = true;
            OpenGbay = Control.FrontendRdown; OpenGbayModifier = Control.FrontendLb;
            NightVision = Control.FrontendLeft; NightVisionModifier = Control.FrontendLb;
            SeatSelector = Control.FrontendRight; SeatSelectorModifier = Control.FrontendLb;
            Accept = Control.FrontendAccept; Back = Control.FrontendCancel;
            Up = Control.FrontendUp; Down = Control.FrontendDown;
            Left = Control.FrontendLeft; Right = Control.FrontendRight;
            PageLeft = Control.FrontendLb; PageRight = Control.FrontendRb;
            CategoryPrev = Control.FrontendLt; CategoryNext = Control.FrontendRt;
            Filter = Control.FrontendY; Search = Control.FrontendX;
            Favorite = Control.FrontendRdown;
        }
    }
}
