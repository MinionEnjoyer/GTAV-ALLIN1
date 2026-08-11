// GbayRenderer.cs -- Drawing primitives and theme constants for the GBAY browser UI.
//
// All coordinates use GTA's normalized 0.0-1.0 screen space.
// DRAW_RECT uses center-based coordinates (x,y = center of rect).

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using GTA.Native;

namespace ALLIN1
{
    internal static class GbayRenderer
    {
        internal static float UiScale { get; set; } = 1f;
        internal static bool ColorblindMode { get; set; }

        private static Color Accessible(Color color)
        {
            if (!ColorblindMode || color.G <= color.R + 25 || color.G <= color.B + 25)
                return color;
            return Color.FromArgb(color.A, 35, Math.Min(190, (int)color.G), 210);
        }
        // ------------------------------------------------------------------ //
        //  Theme Colors                                                       //
        // ------------------------------------------------------------------ //

        // Header / branding
        internal static readonly Color HeaderBg       = Color.FromArgb(255, 35, 135, 70);
        internal static readonly Color HeaderText     = Color.FromArgb(255, 255, 255, 255);

        // Tab strip
        internal static readonly Color TabBg          = Color.FromArgb(255, 38, 145, 72);
        internal static readonly Color TabActive      = Color.FromArgb(255, 255, 255, 255);
        internal static readonly Color TabInactive    = Color.FromArgb(255, 180, 210, 190);
        internal static readonly Color TabHover       = Color.FromArgb(80, 255, 255, 255);
        internal static readonly Color TabIndicator   = Color.FromArgb(255, 255, 255, 255);

        // Body / background
        internal static readonly Color BodyBg         = Color.FromArgb(245, 248, 250, 252);
        internal static readonly Color Scrim          = Color.FromArgb(180, 0, 0, 0);

        // Cards
        internal static readonly Color CardBg         = Color.FromArgb(250, 255, 255, 255);
        internal static readonly Color CardHover      = Color.FromArgb(255, 230, 245, 235);
        internal static readonly Color CardSelected   = Color.FromArgb(255, 210, 240, 220);
        internal static readonly Color CardTopDefault = Color.FromArgb(255, 220, 230, 225);
        internal static readonly Color CardTopHover   = Color.FromArgb(255, 200, 225, 210);
        internal static readonly Color CardBorder     = Color.FromArgb(255, 210, 220, 215);
        internal static readonly Color CardBorderSel  = Color.FromArgb(255, 45, 156, 80);

        // Text
        internal static readonly Color TextDark       = Color.FromArgb(255, 30, 30, 35);
        internal static readonly Color TextMfg        = Color.FromArgb(255, 45, 156, 80);
        internal static readonly Color TextPrice      = Color.FromArgb(255, 35, 130, 65);
        internal static readonly Color TextPriceFree  = Color.FromArgb(255, 100, 100, 100);
        internal static readonly Color TextDim        = Color.FromArgb(255, 140, 150, 145);
        internal static readonly Color TextWhite      = Color.FromArgb(255, 255, 255, 255);

        // Footer
        internal static readonly Color FooterBg       = Color.FromArgb(255, 240, 244, 240);

        // Modal overlay
        internal static readonly Color ModalBg        = Color.FromArgb(250, 255, 255, 255);
        internal static readonly Color ModalScrim     = Color.FromArgb(210, 0, 0, 0);

        // Buttons
        internal static readonly Color BtnGreen       = Color.FromArgb(255, 45, 156, 80);
        internal static readonly Color BtnGreenHover  = Color.FromArgb(255, 35, 135, 65);
        internal static readonly Color BtnGray        = Color.FromArgb(255, 160, 170, 165);
        internal static readonly Color BtnGrayHover   = Color.FromArgb(255, 140, 150, 145);

        // ------------------------------------------------------------------ //
        //  Font Constants                                                     //
        // ------------------------------------------------------------------ //

        internal const int FONT_CHALET     = 0;  // Body text
        internal const int FONT_CONDENSED  = 4;  // Tab labels, small text
        internal const int FONT_PRICEDOWN  = 7;  // GBAY logo

        // ------------------------------------------------------------------ //
        //  Texture Dictionaries                                               //
        // ------------------------------------------------------------------ //

        private static bool _texturesRequested;

        internal static void EnsureTextures()
        {
            if (_texturesRequested)
                return;
            Function.Call(Hash.REQUEST_STREAMED_TEXTURE_DICT, "commonmenu", false);
            _texturesRequested = true;
        }

        internal static bool TexturesLoaded()
        {
            return Function.Call<bool>(Hash.HAS_STREAMED_TEXTURE_DICT_LOADED, "commonmenu");
        }

        // ------------------------------------------------------------------ //
        //  Aspect Ratio                                                       //
        // ------------------------------------------------------------------ //

        internal static float GetAspectRatio()
        {
            return Function.Call<float>(Hash.GET_ASPECT_RATIO, false);
        }

        // ------------------------------------------------------------------ //
        //  Drawing Primitives                                                 //
        // ------------------------------------------------------------------ //

        /// <summary>
        /// Draw a filled rectangle. x,y = center, w,h = size (all 0.0-1.0).
        /// </summary>
        internal static void DrawRect(float x, float y, float w, float h, Color c)
        {
            c = Accessible(c);
            Function.Call(Hash.DRAW_RECT, x, y, w, h, c.R, c.G, c.B, c.A);
        }

        /// <summary>
        /// Draw a rectangle with a border by drawing a slightly larger rect
        /// behind the fill rect.
        /// </summary>
        internal static void DrawBorderedRect(float x, float y, float w, float h,
                                               Color fill, Color border, float bw)
        {
            DrawRect(x, y, w + bw * 2, h + bw * 2, border);
            DrawRect(x, y, w, h, fill);
        }

        /// <summary>
        /// Draw a sprite from a built-in texture dictionary.
        /// </summary>
        internal static void DrawSprite(string dict, string name,
                                         float x, float y, float w, float h,
                                         Color c, float rotation = 0f)
        {
            Function.Call(Hash.DRAW_SPRITE, dict, name, x, y, w, h,
                          rotation, c.R, c.G, c.B, c.A);
        }

        // ------------------------------------------------------------------ //
        //  Streamed Preview Textures (DLC-based .ytd dictionaries)             //
        // ------------------------------------------------------------------ //

        private static readonly HashSet<string> _requestedDicts = new HashSet<string>();
        private static readonly HashSet<string> _loadedDicts = new HashSet<string>();
        private static readonly HashSet<string> _failedDicts = new HashSet<string>();
        private static int _failCheckCounter;

        /// After this many consecutive IsDictLoaded checks returning false
        /// (across all dicts), stop polling. Roughly 10s at 60fps.
        private const int FAIL_CHECK_LIMIT = 600;

        private const string LOGO_DICT = "allin1_logo";
        private const string LOGO_TEX  = "phat";

        internal static string PreviewDiagnostics =>
            $"{_loadedDicts.Count} loaded / {_failedDicts.Count} unavailable; vector placeholders enabled";

        internal static string OpenRpfStatus
        {
            get
            {
                string scripts = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
                string root = Directory.GetParent(scripts)?.FullName ?? scripts;
                return File.Exists(Path.Combine(root, "OpenRPF.asi")) ||
                       File.Exists(Path.Combine(root, "OpenIV.asi")) ? "detected" : "not detected (fallback active)";
            }
        }

        /// <summary>Request a texture dictionary for async streaming.</summary>
        internal static void RequestDict(string dict)
        {
            if (_failedDicts.Contains(dict))
                return;
            if (_requestedDicts.Add(dict))
            {
                Function.Call(Hash.REQUEST_STREAMED_TEXTURE_DICT, dict, false);
            }
        }

        /// <summary>Check if a texture dictionary has been requested.</summary>
        internal static bool IsDictRequested(string dict) => _requestedDicts.Contains(dict);

        /// <summary>Check if a streamed texture dictionary is loaded.</summary>
        internal static bool IsDictLoaded(string dict)
        {
            if (_loadedDicts.Contains(dict))
                return true;
            if (_failedDicts.Contains(dict))
                return false;
            if (!_requestedDicts.Contains(dict))
                return false;

            if (Function.Call<bool>(Hash.HAS_STREAMED_TEXTURE_DICT_LOADED, dict))
            {
                _loadedDicts.Add(dict);
                ClientLog.Info("Preview", "texture_loaded",
                    new Dictionary<string, object> { { "dictionary", dict } });
                return true;
            }

            _failCheckCounter++;
            if (_failCheckCounter > FAIL_CHECK_LIMIT)
            {
                _failedDicts.UnionWith(_requestedDicts);
                _requestedDicts.Clear();
            }

            return false;
        }

        /// <summary>Release a texture dictionary from VRAM.</summary>
        internal static void ReleaseDict(string dict)
        {
            if (_requestedDicts.Remove(dict))
            {
                Function.Call(Hash.SET_STREAMED_TEXTURE_DICT_AS_NO_LONGER_NEEDED, dict);
                _loadedDicts.Remove(dict);
            }
        }

        /// <summary>Check if a preview texture exists for this model.</summary>
        internal static bool HasPreviewTexture(string model)
        {
            if (!VehicleList.PreviewDict.TryGetValue(model, out string dict))
                return false;
            return IsDictLoaded(dict);
        }

        /// <summary>Draw a vehicle preview via DRAW_SPRITE. Returns true if drawn.</summary>
        internal static bool DrawPreviewTexture(string model,
                                                 float x, float y, float w, float h)
        {
            if (!VehicleList.PreviewDict.TryGetValue(model, out string dict))
                return false;
            if (!IsDictLoaded(dict))
            {
                RequestDict(dict);
                return false;
            }
            DrawSprite(dict, model, x, y, w, h, Color.White);
            return true;
        }

        /// <summary>Draw the PHAT logo from the DLC texture dict.</summary>
        internal static void DrawLogo(float x, float y, float h)
        {
            if (!IsDictLoaded(LOGO_DICT))
            {
                RequestDict(LOGO_DICT);
                DrawRect(x, y, h * 0.78f, h * 0.72f, HeaderBg);
                DrawText("GBAY", x, y - h * 0.16f, h * 4.2f, TextWhite,
                    FONT_PRICEDOWN, true);
                return;
            }
            float w = h * (440f / 559f);
            DrawSprite(LOGO_DICT, LOGO_TEX, x, y, w, h, Color.White);
        }

        /// <summary>
        /// Draw text using GTA native text commands.
        /// </summary>
        internal static void DrawText(string text, float x, float y,
                                       float scale, Color c,
                                       int font = FONT_CHALET,
                                       bool centered = false,
                                       bool shadow = false,
                                       bool rightAlign = false)
        {
            c = Accessible(c);
            scale *= UiScale;
            Function.Call(Hash.SET_TEXT_FONT, font);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.SET_TEXT_COLOUR, c.R, c.G, c.B, c.A);

            if (centered)
                Function.Call(Hash.SET_TEXT_CENTRE, true);

            if (rightAlign)
            {
                Function.Call(Hash.SET_TEXT_RIGHT_JUSTIFY, true);
                Function.Call(Hash.SET_TEXT_WRAP, 0f, x);
            }

            if (shadow)
                Function.Call(Hash.SET_TEXT_DROP_SHADOW);

            Function.Call(Hash.BEGIN_TEXT_COMMAND_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            Function.Call(Hash.END_TEXT_COMMAND_DISPLAY_TEXT, x, y);
        }

        /// <summary>
        /// Get the rendered width of a text string in normalized screen space.
        /// </summary>
        internal static float GetTextWidth(string text, float scale, int font = FONT_CHALET)
        {
            scale *= UiScale;
            Function.Call(Hash.SET_TEXT_FONT, font);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_GET_SCREEN_WIDTH_OF_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            return Function.Call<float>(Hash.END_TEXT_COMMAND_GET_SCREEN_WIDTH_OF_DISPLAY_TEXT, true);
        }

        /// <summary>
        /// Draw text that wraps to a second line if it exceeds maxWidth.
        /// Returns the number of lines drawn (1 or 2).
        /// </summary>
        internal static int DrawTextWrapped(string text, float x, float y,
            float scale, Color c, float maxWidth, int font = FONT_CHALET,
            float lineSpacing = 0.018f)
        {
            if (GetTextWidth(text, scale, font) <= maxWidth)
            {
                DrawText(text, x, y, scale, c, font);
                return 1;
            }

            // Split into words and build lines
            string[] words = text.Split(' ');
            string line1 = "";
            int wordIdx = 0;

            for (; wordIdx < words.Length; wordIdx++)
            {
                string test = line1.Length == 0 ? words[wordIdx] : line1 + " " + words[wordIdx];
                if (GetTextWidth(test, scale, font) > maxWidth && line1.Length > 0)
                    break;
                line1 = test;
            }

            string line2 = wordIdx < words.Length
                ? string.Join(" ", words, wordIdx, words.Length - wordIdx)
                : "";

            DrawText(line1, x, y, scale, c, font);
            if (line2.Length > 0)
            {
                DrawText(line2, x, y + lineSpacing, scale, c, font);
                return 2;
            }
            return 1;
        }

        // ------------------------------------------------------------------ //
        //  Composite Elements                                                 //
        // ------------------------------------------------------------------ //

        /// <summary>
        /// Full-screen semi-transparent overlay behind the browser.
        /// </summary>
        internal static void DrawScrim()
        {
            DrawRect(0.5f, 0.5f, 1f, 1f, Scrim);
        }

        /// <summary>
        /// Enable and draw the mouse cursor.
        /// </summary>
        internal static void DrawCursor()
        {
            Function.Call((Hash)0xAAE7CE1D63167423); // _SET_MOUSE_CURSOR_ACTIVE_THIS_FRAME
            Function.Call((Hash)0x8DB8CFFD58B62552, 1); // _SET_MOUSE_CURSOR_SPRITE (normal arrow)
        }

        // ------------------------------------------------------------------ //
        //  Sound                                                              //
        // ------------------------------------------------------------------ //

        internal static void PlayNav()
        {
            Function.Call(Hash.PLAY_SOUND_FRONTEND, -1,
                "NAV_UP_DOWN", "HUD_FRONTEND_DEFAULT_SOUNDSET", true);
        }

        internal static void PlaySelect()
        {
            Function.Call(Hash.PLAY_SOUND_FRONTEND, -1,
                "SELECT", "HUD_FRONTEND_DEFAULT_SOUNDSET", true);
        }

        internal static void PlayBack()
        {
            Function.Call(Hash.PLAY_SOUND_FRONTEND, -1,
                "BACK", "HUD_FRONTEND_DEFAULT_SOUNDSET", true);
        }

        internal static void PlayError()
        {
            Function.Call(Hash.PLAY_SOUND_FRONTEND, -1,
                "ERROR", "HUD_FRONTEND_DEFAULT_SOUNDSET", true);
        }

        // ------------------------------------------------------------------ //
        //  Hit Testing                                                        //
        // ------------------------------------------------------------------ //

        /// <summary>
        /// Test if a point is inside a center-based rectangle.
        /// </summary>
        internal static bool HitTest(float px, float py,
                                      float rx, float ry, float rw, float rh)
        {
            float left = rx - rw / 2f;
            float top = ry - rh / 2f;
            return px >= left && px <= left + rw && py >= top && py <= top + rh;
        }
    }
}
