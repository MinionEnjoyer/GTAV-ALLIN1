// GbayRenderer.cs -- Drawing primitives and theme constants for the GBAY browser UI.
//
// All coordinates use GTA's normalized 0.0-1.0 screen space.
// DRAW_RECT uses center-based coordinates (x,y = center of rect).

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal static class GbayRenderer
    {
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
        //  SHV Preview Textures (lazy-loaded PNGs via ScriptHookV)             //
        // ------------------------------------------------------------------ //

        // SHV P/Invoke — createTexture loads a PNG into a permanent DirectX
        // texture and returns an integer ID.  drawTexture renders it.  There is
        // no delete/free function, so we cap the total number of loaded textures
        // to avoid exhausting VRAM.

        [DllImport("ScriptHookV.dll", EntryPoint = "createTexture",
                    CallingConvention = CallingConvention.Cdecl)]
        private static extern int SHV_CreateTexture(
            [MarshalAs(UnmanagedType.LPStr)] string texFileName);

        [DllImport("ScriptHookV.dll", EntryPoint = "drawTexture",
                    CallingConvention = CallingConvention.Cdecl)]
        private static extern void SHV_DrawTexture(
            int id, int index, int level, int time,
            float sizeX, float sizeY, float centerX, float centerY,
            float posX, float posY, float rotation, float screenHeightScaleFactor,
            float r, float g, float b, float a);

        // model -> SHV texture ID (-1 = not loaded, -2 = file missing)
        private static readonly Dictionary<string, int> _textures
            = new Dictionary<string, int>();
        private static int _textureCount;

        // 512x288 RGBA = ~576 KB each.  200 textures = ~112 MB — safe.
        private const int MAX_TEXTURES = 200;

        private static int _logoTexId = -1;
        private static string _previewFolder;

        /// <summary>Locate the previews folder next to the script DLL.</summary>
        private static string GetPreviewFolder()
        {
            if (_previewFolder != null) return _previewFolder;
            string dllPath = typeof(GbayRenderer).Assembly.Location;
            string scriptsDir = Path.GetDirectoryName(dllPath);
            _previewFolder = Path.Combine(scriptsDir, "previews");
            return _previewFolder;
        }

        /// <summary>Check if a preview texture is loaded or can be loaded.</summary>
        internal static bool HasPreviewTexture(string model)
        {
            if (_textures.TryGetValue(model, out int id))
                return id >= 0;

            // Not yet attempted — check if PNG exists and we're under cap
            if (_textureCount >= MAX_TEXTURES) return false;
            string path = Path.Combine(GetPreviewFolder(), model + ".png");
            return File.Exists(path);
        }

        /// <summary>Draw a vehicle preview. Lazy-loads the PNG on first use.
        /// Returns true if the texture was drawn.</summary>
        internal static bool DrawPreviewTexture(string model,
                                                 float x, float y, float w, float h)
        {
            int id;
            if (!_textures.TryGetValue(model, out id))
            {
                // First request — try to load
                if (_textureCount >= MAX_TEXTURES)
                    return false;

                string path = Path.Combine(GetPreviewFolder(), model + ".png");
                if (!File.Exists(path))
                {
                    _textures[model] = -2; // missing
                    return false;
                }

                id = SHV_CreateTexture(path);
                _textures[model] = id;
                if (id >= 0) _textureCount++;
            }

            if (id < 0) return false;

            // drawTexture uses top-left positioning and pixel-based sizing.
            // Convert normalized coords to SHV's expected format.
            float aspect = GetAspectRatio();
            SHV_DrawTexture(id, 0, 0, 0,
                w, h,                    // size (normalized)
                0.5f, 0.5f,              // center of texture
                x, y,                    // position (center, normalized)
                0f,                      // rotation
                aspect,                  // screen height scale factor
                1f, 1f, 1f, 1f);         // RGBA (white = no tint)
            return true;
        }

        /// <summary>Draw the PHAT logo (loaded from scripts/PHAT.png).</summary>
        internal static void DrawLogo(float x, float y, float h)
        {
            if (_logoTexId == -1)
            {
                string dllPath = typeof(GbayRenderer).Assembly.Location;
                string scriptsDir = Path.GetDirectoryName(dllPath);
                string logoPath = Path.Combine(scriptsDir, "PHAT.png");
                if (File.Exists(logoPath))
                    _logoTexId = SHV_CreateTexture(logoPath);
                else
                    _logoTexId = -2;
            }
            if (_logoTexId < 0) return;

            float w = h * (440f / 559f);
            float aspect = GetAspectRatio();
            SHV_DrawTexture(_logoTexId, 0, 0, 0,
                w, h, 0.5f, 0.5f, x, y, 0f, aspect,
                1f, 1f, 1f, 1f);
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
            Function.Call(Hash.SET_TEXT_FONT, font);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.SET_TEXT_COLOUR, c.R, c.G, c.B, c.A);

            if (centered)
                Function.Call(Hash.SET_TEXT_CENTRE, true);

            if (rightAlign)
                Function.Call(Hash.SET_TEXT_RIGHT_JUSTIFY, true);

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
            Function.Call(Hash.SET_TEXT_FONT, font);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_GET_SCREEN_WIDTH_OF_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            return Function.Call<float>(Hash.END_TEXT_COMMAND_GET_SCREEN_WIDTH_OF_DISPLAY_TEXT, true);
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
