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
        internal static readonly Color TabInactive    = Color.FromArgb(255, 214, 232, 220);
        internal static readonly Color TabHover       = Color.FromArgb(80, 255, 255, 255);
        internal static readonly Color TabIndicator   = Color.FromArgb(255, 255, 255, 255);

        // Body / background
        internal static readonly Color BodyBg         = Color.FromArgb(250, 239, 244, 241);
        internal static readonly Color Scrim          = Color.FromArgb(180, 0, 0, 0);

        // Cards
        internal static readonly Color CardBg         = Color.FromArgb(250, 255, 255, 255);
        internal static readonly Color CardHover      = Color.FromArgb(255, 230, 245, 235);
        internal static readonly Color CardSelected   = Color.FromArgb(255, 218, 240, 226);
        internal static readonly Color CardTopDefault = Color.FromArgb(255, 220, 230, 225);
        internal static readonly Color CardTopHover   = Color.FromArgb(255, 200, 225, 210);
        internal static readonly Color CardBorder     = Color.FromArgb(255, 178, 190, 184);
        internal static readonly Color CardBorderSel  = Color.FromArgb(255, 20, 112, 55);

        // Text
        internal static readonly Color TextDark       = Color.FromArgb(255, 30, 30, 35);
        internal static readonly Color TextMfg        = Color.FromArgb(255, 45, 156, 80);
        internal static readonly Color TextPrice      = Color.FromArgb(255, 35, 130, 65);
        internal static readonly Color TextPriceFree  = Color.FromArgb(255, 100, 100, 100);
        internal static readonly Color TextDim        = Color.FromArgb(255, 82, 94, 88);
        internal static readonly Color TextWhite      = Color.FromArgb(255, 255, 255, 255);

        // Footer
        internal static readonly Color FooterBg       = Color.FromArgb(255, 225, 233, 228);

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
        /// Draw a filled rounded rectangle without depending on an external
        /// texture. Horizontal bands approximate circular corners while
        /// compensating for the screen aspect ratio.
        /// </summary>
        internal static void DrawRoundedRect(
            float x, float y, float w, float h, float radius, Color c)
        {
            const int slices = 32;
            float aspect = Math.Max(1f, GetAspectRatio());
            float r = Math.Max(0f, Math.Min(radius, h * 0.5f));
            float rx = Math.Min(w * 0.5f, r / aspect);
            if (r <= 0f || rx <= 0f)
            {
                DrawRect(x, y, w, h, c);
                return;
            }

            float coreW = Math.Max(0f, w - rx * 2f);
            float bandH = h / slices;
            for (int i = 0; i < slices; i++)
            {
                float offset = -h * 0.5f + (i + 0.5f) * bandH;
                float cornerY = Math.Max(0f, Math.Abs(offset) - (h * 0.5f - r));
                float normalized = Math.Min(1f, cornerY / r);
                float capW = rx * (float)Math.Sqrt(1f - normalized * normalized);
                DrawRect(x, y + offset, coreW + capW * 2f,
                    bandH + 0.0006f, c);
            }
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
        private static readonly Dictionary<string, DateTime> _requestStarted =
            new Dictionary<string, DateTime>();

        /// Each dictionary gets its own wall-clock timeout. A shared frame/check
        /// counter used to expire every requested dictionary after roughly one
        /// second on an eight-card page because each card incremented it.
        private static readonly TimeSpan DICT_LOAD_TIMEOUT = TimeSpan.FromSeconds(30);

        private const string PHAT_LOGO_DICT = "phat_logo";
        private const string PHAT_LOGO_TEX  = "phat";
        private const string BRAND_LOGO_DICT = "allin1_logo";
        private const string BRAND_LOGO_TEX = "allin1";

        internal static string PreviewDiagnostics
        {
            get
            {
                int pending = Math.Max(0, _requestedDicts.Count - _loadedDicts.Count);
                return $"{_loadedDicts.Count} loaded / {pending} pending / " +
                    $"{_failedDicts.Count} unavailable; vector placeholders enabled";
            }
        }

        internal static string OpenRpfStatus
        {
            get
            {
                string scripts = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
                string root = Directory.GetParent(scripts)?.FullName ?? scripts;
                string openRpf = Path.Combine(root, "OpenRPF.asi");
                string openIv = Path.Combine(root, "OpenIV.asi");
                if (IsUsablePlugin(openRpf) || IsUsablePlugin(openIv))
                    return "plug-in detected";

                string disabledRoot = Path.Combine(
                    root, "allin1_backups", "DisabledPlugins");
                if (File.Exists(Path.Combine(disabledRoot, "OpenRPF.asi.disabled")) ||
                    File.Exists(Path.Combine(disabledRoot, "OpenIV.asi.disabled")))
                    return "OpenRPF plug-in disabled (fallback active)";

                bool asiLoader = File.Exists(Path.Combine(root, "dinput8.dll")) ||
                    File.Exists(Path.Combine(root, "dsound.dll")) ||
                    File.Exists(Path.Combine(root, "xinput1_4.dll"));
                return asiLoader
                    ? "ASI loader detected; OpenRPF plug-in missing"
                    : "ASI loader and OpenRPF plug-in missing";
            }
        }

        private static bool IsUsablePlugin(string path)
        {
            try { return File.Exists(path) && new FileInfo(path).Length > 0; }
            catch (IOException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
        }

        /// <summary>Request a texture dictionary for async streaming.</summary>
        internal static void RequestDict(string dict)
        {
            if (_failedDicts.Contains(dict))
                return;
            if (_requestedDicts.Add(dict))
            {
                _requestStarted[dict] = DateTime.UtcNow;
                Function.Call(Hash.REQUEST_STREAMED_TEXTURE_DICT, dict, false);
                ClientLog.Info("Preview", "texture_requested",
                    new Dictionary<string, object> { { "dictionary", dict } });
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
                _requestStarted.Remove(dict);
                ClientLog.Info("Preview", "texture_loaded",
                    new Dictionary<string, object> { { "dictionary", dict } });
                return true;
            }

            if (_requestStarted.TryGetValue(dict, out DateTime started) &&
                DateTime.UtcNow - started >= DICT_LOAD_TIMEOUT)
            {
                _failedDicts.Add(dict);
                _requestedDicts.Remove(dict);
                _requestStarted.Remove(dict);
                ClientLog.Warn("Preview", "texture_unavailable",
                    new Dictionary<string, object>
                    {
                        { "dictionary", dict },
                        { "timeout_seconds", (int)DICT_LOAD_TIMEOUT.TotalSeconds },
                    });
            }

            return false;
        }

        /// <summary>Release a texture dictionary from VRAM.</summary>
        internal static void ReleaseDict(string dict)
        {
            bool wasRequested = _requestedDicts.Remove(dict);
            if (wasRequested || _loadedDicts.Contains(dict))
                Function.Call(Hash.SET_STREAMED_TEXTURE_DICT_AS_NO_LONGER_NEEDED, dict);
            _loadedDicts.Remove(dict);
            _failedDicts.Remove(dict);
            _requestStarted.Remove(dict);
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

        private static bool DrawCatalogPreviewTexture(
            string itemId, Dictionary<string, string> previewDict,
            float x, float y, float w, float h)
        {
            if (!previewDict.TryGetValue(itemId, out string dict))
                return false;
            if (!IsDictLoaded(dict))
            {
                RequestDict(dict);
                return false;
            }
            DrawSprite(dict, itemId.ToLowerInvariant(), x, y, w, h, Color.White);
            return true;
        }

        /// <summary>Draw a captured Ammu-Nation weapon preview when available.</summary>
        internal static bool DrawWeaponPreviewTexture(
            string weaponName, float x, float y, float w, float h)
        {
            return DrawCatalogPreviewTexture(
                weaponName, WeaponList.PreviewDict, x, y, w, h);
        }

        /// <summary>Draw a captured equipment preview when available.</summary>
        internal static bool DrawEquipmentPreviewTexture(
            string gearId, float x, float y, float w, float h)
        {
            return DrawCatalogPreviewTexture(
                gearId, GearList.PreviewDict, x, y, w, h);
        }

        private static void DrawLogoFallback(
            string dictionary, float x, float y, float h)
        {
            RequestDict(dictionary);
            DrawRect(x, y, h * 0.78f, h * 0.72f, HeaderBg);
            DrawText("GBAY", x, y - h * 0.16f, h * 4.2f, TextWhite,
                FONT_PRICEDOWN, true);
        }

        /// <summary>
        /// Fit a source image inside a normalized screen-space box while
        /// compensating for widescreen coordinates. This preserves the
        /// texture's pixel aspect ratio at every game resolution.
        /// </summary>
        private static void ContainSprite(
            float sourceWidth, float sourceHeight, float maxW, float maxH,
            out float width, out float height)
        {
            float screenAspect = Math.Max(1f, GetAspectRatio());
            float sourceAspect = sourceWidth / sourceHeight;
            height = maxH;
            width = height * sourceAspect / screenAspect;
            if (width > maxW)
            {
                width = maxW;
                height = width * screenAspect / sourceAspect;
            }
        }

        /// <summary>Draw the PHAT loading meme from the DLC texture dictionary.</summary>
        internal static void DrawLogo(float x, float y, float h)
        {
            if (!IsDictLoaded(PHAT_LOGO_DICT))
            {
                DrawLogoFallback(PHAT_LOGO_DICT, x, y, h);
                return;
            }
            ContainSprite(440f, 559f, h, h, out float w, out float fittedH);
            DrawSprite(PHAT_LOGO_DICT, PHAT_LOGO_TEX,
                x, y, w, fittedH, Color.White);
        }

        /// <summary>Contain-fit the ALLIN1 brand mark on the About page.</summary>
        internal static void DrawBrandLogo(
            float x, float y, float maxW, float maxH)
        {
            if (!IsDictLoaded(BRAND_LOGO_DICT))
            {
                DrawLogoFallback(BRAND_LOGO_DICT, x, y, maxH);
                return;
            }
            ContainSprite(1536f, 1024f, maxW, maxH,
                out float width, out float height);
            DrawSprite(BRAND_LOGO_DICT, BRAND_LOGO_TEX,
                x, y, width, height, Color.White);
        }

        /// <summary>
        /// Draw the GBAY wordmark with GTA's Pricedown-style display font.
        /// PHAT remains exclusive to the loading screen.
        /// </summary>
        internal static void DrawGbayWordmark(
            float x, float y, float scale, bool light = false)
        {
            Color foreground = light ? TextWhite : HeaderBg;
            DrawText("GBAY", x + 0.002f, y + 0.003f, scale,
                Color.FromArgb(150, 10, 20, 14), FONT_PRICEDOWN, true);
            DrawText("GBAY", x, y, scale, foreground,
                FONT_PRICEDOWN, true);
        }

        /// <summary>Draw the main-menu GBAY title on a clean rounded panel.</summary>
        internal static void DrawGbayHeader(
            float x, float centerY, float w, float h)
        {
            Color shadow = Color.FromArgb(100, 6, 28, 15);
            Color border = Color.FromArgb(255, 20, 111, 55);
            Color face = Color.FromArgb(255, 39, 154, 78);
            float radius = h * 0.23f;

            DrawRoundedRect(x, centerY + 0.005f, w, h, radius, shadow);
            DrawRoundedRect(x, centerY, w, h, radius, border);
            DrawRoundedRect(x, centerY, w - 0.006f, h - 0.008f,
                Math.Max(0f, radius - 0.004f), face);

            float textY = centerY - h * 0.31f;
            DrawText("GBAY", x + 0.001f, textY + 0.002f, 0.70f,
                Color.FromArgb(105, 5, 30, 15), FONT_PRICEDOWN, true);
            DrawText("GBAY", x, textY, 0.70f, TextWhite,
                FONT_PRICEDOWN, true);
        }

        /// <summary>
        /// Draw a consistent rounded green title badge with fitted white text.
        /// Used by every GBAY screen and modal title outside the main wordmark.
        /// </summary>
        internal static void DrawTitleBadge(
            string text, float x, float centerY, float w, float h,
            float scale = 0.38f, int font = FONT_CONDENSED)
        {
            float radius = h * 0.24f;
            DrawRoundedRect(x, centerY + 0.003f, w, h, radius,
                Color.FromArgb(85, 3, 22, 10));
            DrawRoundedRect(x, centerY, w, h, radius,
                Color.FromArgb(255, 18, 105, 51));
            DrawRoundedRect(x, centerY, w - 0.004f, h - 0.005f,
                Math.Max(0f, radius - 0.002f), BtnGreen);
            DrawTextFit(text, x, centerY - h * 0.30f, scale,
                Math.Min(0.20f, scale), w - 0.018f, TextWhite,
                font, true);
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
        /// Draw one line while shrinking only as much as required to keep it
        /// inside the supplied width. This prevents long catalog names and
        /// diagnostics from running into adjacent controls.
        /// </summary>
        internal static void DrawTextFit(
            string text, float x, float y, float preferredScale,
            float minimumScale, float maxWidth, Color c,
            int font = FONT_CHALET, bool centered = false,
            bool shadow = false, bool rightAlign = false)
        {
            float scale = preferredScale;
            while (scale > minimumScale && GetTextWidth(text, scale, font) > maxWidth)
                scale -= 0.015f;
            DrawText(text, x, y, Math.Max(minimumScale, scale), c,
                font, centered, shadow, rightAlign);
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
