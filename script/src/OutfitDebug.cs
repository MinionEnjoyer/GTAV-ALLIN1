// OutfitDebug.cs -- Visual outfit editor with rendered character and clickable buttons.
//
// F10 = Toggle editor on/off
//
// When open, the player ped is teleported to a showroom position,
// a camera orbits around them, and a panel of clickable buttons lets
// the user browse component slots, drawables, and textures.
//
// All interaction is mouse-driven (no keyboard required beyond F10).

using System;
using System.Drawing;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class OutfitDebug : Script
    {
        private bool _active;

        // Camera / showroom
        private Camera _camera;
        private float _orbitAngle;
        private float _orbitRadius = 2.2f;
        private float _orbitHeight = 0.4f;
        private static readonly Vector3 SHOWROOM_POS = new Vector3(10f, 10f, 1000f);
        private const float ORBIT_SPEED = 0.3f;

        // Saved player state (restore on close)
        private Vector3 _savedPos;
        private float _savedHeading;

        // Slot selection
        private int _selectedSlot;       // index into current list
        private bool _propMode;          // false = components, true = props

        private static readonly string[] COMP_NAMES =
        {
            "Head",
            "Beard/Mask",
            "Hair",
            "Torso",
            "Legs",
            "Hands",
            "Shoes",
            "Neck/Scarf",
            "Shirt/Acc",
            "Body Armor",
            "Decals",
            "Aux/Torso2",
        };

        private static readonly string[] PROP_NAMES =
        {
            "Hat/Helmet",
            "Glasses",
            "Ears",
        };

        private static readonly int[] PROP_SLOTS = { 0, 1, 2 };

        // UI layout
        private const float PANEL_X = 0.02f;       // left edge
        private const float PANEL_W = 0.24f;        // panel width
        private const float PANEL_TOP = 0.04f;
        private const float ROW_H = 0.032f;
        private const float BTN_H = 0.030f;
        private const float BTN_W = 0.035f;
        private const float SMALL_GAP = 0.004f;
        private const float TEXT_SCALE = 0.28f;

        // Colors
        private static readonly Color PanelBg = Color.FromArgb(210, 15, 15, 20);
        private static readonly Color RowNormal = Color.FromArgb(60, 255, 255, 255);
        private static readonly Color RowSelected = Color.FromArgb(120, 80, 200, 120);
        private static readonly Color BtnNormal = Color.FromArgb(200, 50, 50, 60);
        private static readonly Color BtnHover = Color.FromArgb(255, 70, 160, 90);
        private static readonly Color TextWhite = Color.FromArgb(255, 255, 255, 255);
        private static readonly Color TextYellow = Color.FromArgb(255, 255, 255, 100);
        private static readonly Color TextGreen = Color.FromArgb(255, 100, 255, 130);
        private static readonly Color TextDim = Color.FromArgb(255, 160, 160, 160);
        private static readonly Color TabActive = Color.FromArgb(255, 60, 180, 100);
        private static readonly Color TabInactive = Color.FromArgb(180, 40, 40, 50);

        public OutfitDebug()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        // ------------------------------------------------------------------ //
        //  Open / Close                                                       //
        // ------------------------------------------------------------------ //

        private void Open()
        {
            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;

            _savedPos = player.Position;
            _savedHeading = player.Heading;

            // Teleport player to showroom
            player.Position = SHOWROOM_POS;
            player.Heading = 0f;
            player.IsPositionFrozen = true;
            player.IsCollisionEnabled = false;
            player.IsInvincible = true;

            // Wait a frame for position to settle
            Script.Wait(0);

            // Create orbiting camera
            _orbitAngle = (float)(Math.PI * 0.75);
            Vector3 camPos = GetOrbitPos();
            _camera = World.CreateCamera(camPos, Vector3.Zero, 50f);
            _camera.PointAt(player);
            World.RenderingCamera = _camera;

            _selectedSlot = 0;
            _propMode = false;
            _active = true;

            // Disable player control while in editor
            Game.Player.CanControlCharacter = false;
        }

        private void Close()
        {
            Ped player = Game.Player.Character;

            // Restore camera
            if (_camera != null)
            {
                World.RenderingCamera = null;
                _camera.Delete();
                _camera = null;
            }

            // Restore player
            if (player != null && player.Exists())
            {
                player.IsPositionFrozen = false;
                player.IsCollisionEnabled = true;
                player.IsInvincible = false;
                player.Position = _savedPos;
                player.Heading = _savedHeading;
            }

            Game.Player.CanControlCharacter = true;
            _active = false;
        }

        private Vector3 GetOrbitPos()
        {
            float x = SHOWROOM_POS.X + _orbitRadius * (float)Math.Cos(_orbitAngle);
            float y = SHOWROOM_POS.Y + _orbitRadius * (float)Math.Sin(_orbitAngle);
            float z = SHOWROOM_POS.Z + _orbitHeight;
            return new Vector3(x, y, z);
        }

        // ------------------------------------------------------------------ //
        //  Key Handler                                                        //
        // ------------------------------------------------------------------ //

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.F10)
            {
                if (_active) Close();
                else Open();
            }

            if (!_active) return;

            if (e.KeyCode == Keys.Escape)
                Close();
        }

        // ------------------------------------------------------------------ //
        //  Tick — Draw UI + Handle Mouse                                      //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            if (!_active) return;

            try
            {
                Ped player = Game.Player.Character;
                if (player == null || player.IsDead)
                {
                    Close();
                    return;
                }

                // Clamp selected slot to valid range for current mode
                int maxSlots = _propMode ? PROP_SLOTS.Length : 12;
                if (_selectedSlot >= maxSlots)
                    _selectedSlot = 0;

                // Keep player frozen at showroom
                player.IsPositionFrozen = true;

                // Auto-orbit camera
                _orbitAngle += Game.LastFrameTime * ORBIT_SPEED;
                if (_camera != null)
                {
                    _camera.Position = GetOrbitPos();
                    _camera.PointAt(player);
                }

                // Enable mouse cursor
                Function.Call((Hash)0xAAE7CE1D63167423); // _SET_MOUSE_CURSOR_ACTIVE_THIS_FRAME
                Function.Call((Hash)0x8DB8CFFD58B62552, 1); // _SET_MOUSE_CURSOR_SPRITE

                // Disable player control each frame
                Game.Player.CanControlCharacter = false;
                Function.Call(Hash.DISABLE_ALL_CONTROL_ACTIONS, 0);

                // Get mouse position
                float mx = Function.Call<float>(Hash.GET_DISABLED_CONTROL_NORMAL, 0, 239);
                float my = Function.Call<float>(Hash.GET_DISABLED_CONTROL_NORMAL, 0, 240);
                bool clicked = Function.Call<bool>(Hash.IS_DISABLED_CONTROL_JUST_PRESSED, 0, 237);

                // Draw panel
                DrawPanel(player, mx, my, clicked);
            }
            catch (Exception ex)
            {
                // Prevent script death — log and close gracefully
                GTA.UI.Screen.ShowSubtitle($"~r~Outfit editor error: {ex.Message}", 5000);
                Close();
            }
        }

        // ------------------------------------------------------------------ //
        //  UI Drawing                                                         //
        // ------------------------------------------------------------------ //

        private void DrawPanel(Ped player, float mx, float my, bool clicked)
        {
            int maxSlots = _propMode ? PROP_SLOTS.Length : 12;
            string[] names = _propMode ? PROP_NAMES : COMP_NAMES;

            // Header + tabs + slot list + footer
            float headerH = ROW_H * 2f;
            float tabsH = ROW_H * 1.2f;
            float listH = maxSlots * ROW_H;
            float footerH = ROW_H * 2.5f;
            float totalH = headerH + tabsH + listH + footerH + SMALL_GAP * 4;

            float panelCX = PANEL_X + PANEL_W / 2f;
            float panelCY = PANEL_TOP + totalH / 2f;

            // Panel background
            DrawRect(panelCX, panelCY, PANEL_W, totalH, PanelBg);

            float curY = PANEL_TOP + SMALL_GAP;

            // --- Header: Character name + Health ---
            string charName = GetCharacterName(player);
            DrawTextShadow($"Outfit Editor - {charName}", PANEL_X + 0.008f, curY,
                0.32f, TextGreen);
            curY += ROW_H;
            DrawTextShadow($"Health: {player.Health}/{player.MaxHealth}  Armor: {player.Armor}",
                PANEL_X + 0.008f, curY, 0.24f, TextDim);
            curY += ROW_H + SMALL_GAP;

            // --- Mode tabs: Components | Props ---
            float tabW = (PANEL_W - SMALL_GAP * 3) / 2f;
            float tabH = ROW_H * 1.0f;
            float tab1CX = PANEL_X + SMALL_GAP + tabW / 2f;
            float tab2CX = PANEL_X + SMALL_GAP * 2 + tabW + tabW / 2f;
            float tabCY = curY + tabH / 2f;

            bool hoverTab1 = HitTest(mx, my, tab1CX, tabCY, tabW, tabH);
            bool hoverTab2 = HitTest(mx, my, tab2CX, tabCY, tabW, tabH);

            DrawRect(tab1CX, tabCY, tabW, tabH, !_propMode ? TabActive : (hoverTab1 ? BtnHover : TabInactive));
            DrawRect(tab2CX, tabCY, tabW, tabH, _propMode ? TabActive : (hoverTab2 ? BtnHover : TabInactive));
            DrawTextCentered("Components", tab1CX, curY + 0.005f, 0.26f, TextWhite);
            DrawTextCentered("Props", tab2CX, curY + 0.005f, 0.26f, TextWhite);

            if (clicked && hoverTab1 && _propMode)
            {
                _propMode = false;
                _selectedSlot = 0;
                PlayNav();
            }
            if (clicked && hoverTab2 && !_propMode)
            {
                _propMode = true;
                _selectedSlot = 0;
                PlayNav();
            }

            curY += tabH + SMALL_GAP;

            // --- Slot list ---
            for (int i = 0; i < maxSlots; i++)
            {
                int slot = _propMode ? PROP_SLOTS[i] : i;
                bool isSelected = i == _selectedSlot;

                int drawable, texture, maxDrawable, maxTexture;
                try
                {
                    if (_propMode)
                    {
                        drawable = Function.Call<int>(Hash.GET_PED_PROP_INDEX, player, slot);
                        texture = drawable >= 0
                            ? Function.Call<int>(Hash.GET_PED_PROP_TEXTURE_INDEX, player, slot)
                            : 0;
                        maxDrawable = Function.Call<int>(
                            Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS, player, slot);
                        maxTexture = drawable >= 0 && maxDrawable > 0
                            ? Function.Call<int>(
                                Hash.GET_NUMBER_OF_PED_PROP_TEXTURE_VARIATIONS, player, slot, drawable)
                            : 0;
                    }
                    else
                    {
                        drawable = Function.Call<int>(Hash.GET_PED_DRAWABLE_VARIATION, player, slot);
                        texture = Function.Call<int>(Hash.GET_PED_TEXTURE_VARIATION, player, slot);
                        maxDrawable = Function.Call<int>(
                            Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, player, slot);
                        maxTexture = maxDrawable > 0
                            ? Function.Call<int>(
                                Hash.GET_NUMBER_OF_PED_TEXTURE_VARIATIONS, player, slot, drawable)
                            : 0;
                    }
                }
                catch
                {
                    drawable = 0; texture = 0; maxDrawable = 0; maxTexture = 0;
                }

                float rowCX = panelCX;
                float rowCY = curY + ROW_H / 2f;

                // Row background (highlight selected)
                bool hoverRow = HitTest(mx, my, rowCX, rowCY, PANEL_W - SMALL_GAP * 2, ROW_H);
                Color rowBg = isSelected ? RowSelected : (hoverRow ? RowNormal : Color.Transparent);
                if (rowBg.A > 0)
                    DrawRect(rowCX, rowCY, PANEL_W - SMALL_GAP * 2, ROW_H, rowBg);

                // Click row to select
                if (clicked && hoverRow && !isSelected)
                {
                    _selectedSlot = i;
                    PlayNav();
                }

                // Slot name
                float nameX = PANEL_X + 0.008f;
                Color nameColor = isSelected ? TextYellow : TextWhite;
                string slotLabel = _propMode ? $"P{slot}" : $"{slot}";
                DrawTextShadow($"{slotLabel} {names[i]}", nameX, curY + 0.005f,
                    0.22f, nameColor);

                // Drawable/texture values (right side)
                string valStr;
                if (_propMode && drawable < 0)
                    valStr = "NONE";
                else
                    valStr = $"D{drawable}/{maxDrawable} T{texture}/{maxTexture}";

                float valX = PANEL_X + PANEL_W - 0.008f;
                DrawTextRight(valStr, valX, curY + 0.005f, 0.22f,
                    isSelected ? TextGreen : TextDim);

                curY += ROW_H;
            }

            curY += SMALL_GAP;

            // --- Control buttons for selected slot ---
            DrawControlButtons(player, mx, my, clicked, curY);
        }

        private void DrawControlButtons(Ped player, float mx, float my, bool clicked, float y)
        {
            int slotIdx = _selectedSlot;
            if (_propMode && slotIdx >= PROP_SLOTS.Length)
                slotIdx = 0;
            int slot = _propMode ? PROP_SLOTS[slotIdx] : slotIdx;

            int drawable, texture, maxDrawable, maxTexture;
            try
            {
                if (_propMode)
                {
                    drawable = Function.Call<int>(Hash.GET_PED_PROP_INDEX, player, slot);
                    texture = drawable >= 0
                        ? Function.Call<int>(Hash.GET_PED_PROP_TEXTURE_INDEX, player, slot)
                        : 0;
                    maxDrawable = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS, player, slot);
                    maxTexture = drawable >= 0 && maxDrawable > 0
                        ? Function.Call<int>(
                            Hash.GET_NUMBER_OF_PED_PROP_TEXTURE_VARIATIONS, player, slot, drawable)
                        : 0;
                }
                else
                {
                    drawable = Function.Call<int>(Hash.GET_PED_DRAWABLE_VARIATION, player, slot);
                    texture = Function.Call<int>(Hash.GET_PED_TEXTURE_VARIATION, player, slot);
                    maxDrawable = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, player, slot);
                    maxTexture = maxDrawable > 0
                        ? Function.Call<int>(
                            Hash.GET_NUMBER_OF_PED_TEXTURE_VARIATIONS, player, slot, drawable)
                        : 0;
                }
            }
            catch
            {
                drawable = 0; texture = 0; maxDrawable = 0; maxTexture = 0;
            }

            float rowY = y;
            float leftX = PANEL_X + SMALL_GAP;

            // Row 1: Drawable  [<]  value  [>]
            {
                float cx = leftX + 0.008f;
                DrawTextShadow("Drawable", cx, rowY + 0.005f, 0.24f, TextWhite);

                float btnLeft = PANEL_X + PANEL_W * 0.45f;
                float btnCY = rowY + BTN_H / 2f;

                // [<] button
                bool h1 = DrawButton("<", btnLeft + BTN_W / 2f, btnCY, BTN_W, BTN_H, mx, my);
                if (clicked && h1)
                {
                    CycleDrawable(player, slot, -1);
                    PlayNav();
                }

                // Value display
                string dStr = (_propMode && drawable < 0) ? "NONE" : $"{drawable}";
                DrawTextCentered(dStr, btnLeft + BTN_W + 0.020f, rowY + 0.005f,
                    0.26f, TextGreen);

                // [>] button
                float btn2X = btnLeft + BTN_W + 0.040f + BTN_W / 2f;
                bool h2 = DrawButton(">", btn2X, btnCY, BTN_W, BTN_H, mx, my);
                if (clicked && h2)
                {
                    CycleDrawable(player, slot, 1);
                    PlayNav();
                }
            }

            rowY += BTN_H + SMALL_GAP;

            // Row 2: Texture  [<]  value  [>]
            {
                float cx = leftX + 0.008f;
                DrawTextShadow("Texture", cx, rowY + 0.005f, 0.24f, TextWhite);

                float btnLeft = PANEL_X + PANEL_W * 0.45f;
                float btnCY = rowY + BTN_H / 2f;

                bool h1 = DrawButton("<", btnLeft + BTN_W / 2f, btnCY, BTN_W, BTN_H, mx, my);
                if (clicked && h1)
                {
                    CycleTexture(player, slot, -1);
                    PlayNav();
                }

                string tStr = (_propMode && drawable < 0) ? "-" : $"{texture}";
                DrawTextCentered(tStr, btnLeft + BTN_W + 0.020f, rowY + 0.005f,
                    0.26f, TextGreen);

                float btn2X = btnLeft + BTN_W + 0.040f + BTN_W / 2f;
                bool h2 = DrawButton(">", btn2X, btnCY, BTN_W, BTN_H, mx, my);
                if (clicked && h2)
                {
                    CycleTexture(player, slot, 1);
                    PlayNav();
                }
            }

            rowY += BTN_H + SMALL_GAP * 2;

            // Close button
            {
                float closeBtnW = PANEL_W - SMALL_GAP * 4;
                float closeCX = PANEL_X + PANEL_W / 2f;
                float closeCY = rowY + BTN_H / 2f;

                bool hClose = DrawButton("Close [F10]", closeCX, closeCY,
                    closeBtnW, BTN_H, mx, my);
                if (clicked && hClose)
                    Close();
            }
        }

        // ------------------------------------------------------------------ //
        //  Drawable / Texture Cycling                                         //
        // ------------------------------------------------------------------ //

        private void CycleDrawable(Ped player, int slot, int dir)
        {
            try
            {
                if (_propMode)
                {
                    int current = Function.Call<int>(Hash.GET_PED_PROP_INDEX, player, slot);
                    int max = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS, player, slot);
                    if (max <= 0) return;

                    int next = current + dir;
                    if (next < -1) next = max - 1;
                    if (next >= max) next = -1;

                    if (next < 0)
                        Function.Call(Hash.CLEAR_PED_PROP, player, slot);
                    else
                        Function.Call(Hash.SET_PED_PROP_INDEX, player, slot, next, 0, true);
                }
                else
                {
                    int current = Function.Call<int>(
                        Hash.GET_PED_DRAWABLE_VARIATION, player, slot);
                    int max = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, player, slot);
                    if (max <= 0) return;

                    int next = (current + dir + max) % max;
                    Function.Call(Hash.SET_PED_COMPONENT_VARIATION, player, slot, next, 0, 0);
                }
            }
            catch { }
        }

        private void CycleTexture(Ped player, int slot, int dir)
        {
            try
            {
            if (_propMode)
            {
                int drawable = Function.Call<int>(Hash.GET_PED_PROP_INDEX, player, slot);
                if (drawable < 0) return;

                int currentTex = Function.Call<int>(
                    Hash.GET_PED_PROP_TEXTURE_INDEX, player, slot);
                int maxTex = Function.Call<int>(
                    Hash.GET_NUMBER_OF_PED_PROP_TEXTURE_VARIATIONS, player, slot, drawable);
                if (maxTex <= 0) return;

                int nextTex = (currentTex + dir + maxTex) % maxTex;
                Function.Call(Hash.SET_PED_PROP_INDEX, player, slot, drawable, nextTex, true);
            }
            else
            {
                int drawable = Function.Call<int>(
                    Hash.GET_PED_DRAWABLE_VARIATION, player, slot);
                int currentTex = Function.Call<int>(
                    Hash.GET_PED_TEXTURE_VARIATION, player, slot);
                int maxTex = Function.Call<int>(
                    Hash.GET_NUMBER_OF_PED_TEXTURE_VARIATIONS, player, slot, drawable);
                if (maxTex <= 0) return;

                int nextTex = (currentTex + dir + maxTex) % maxTex;
                Function.Call(Hash.SET_PED_COMPONENT_VARIATION, player, slot, drawable, nextTex, 0);
            }
            }
            catch { }
        }

        // ------------------------------------------------------------------ //
        //  Drawing Helpers                                                    //
        // ------------------------------------------------------------------ //

        private static void DrawRect(float cx, float cy, float w, float h, Color c)
        {
            Function.Call(Hash.DRAW_RECT, cx, cy, w, h, c.R, c.G, c.B, c.A);
        }

        private static void DrawTextShadow(string text, float x, float y,
            float scale, Color c)
        {
            Function.Call(Hash.SET_TEXT_FONT, 0);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.SET_TEXT_COLOUR, c.R, c.G, c.B, c.A);
            Function.Call(Hash.SET_TEXT_DROP_SHADOW);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            Function.Call(Hash.END_TEXT_COMMAND_DISPLAY_TEXT, x, y);
        }

        private static void DrawTextCentered(string text, float x, float y,
            float scale, Color c)
        {
            Function.Call(Hash.SET_TEXT_FONT, 0);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.SET_TEXT_COLOUR, c.R, c.G, c.B, c.A);
            Function.Call(Hash.SET_TEXT_CENTRE, true);
            Function.Call(Hash.SET_TEXT_DROP_SHADOW);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            Function.Call(Hash.END_TEXT_COMMAND_DISPLAY_TEXT, x, y);
        }

        private static void DrawTextRight(string text, float x, float y,
            float scale, Color c)
        {
            Function.Call(Hash.SET_TEXT_FONT, 0);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.SET_TEXT_COLOUR, c.R, c.G, c.B, c.A);
            Function.Call(Hash.SET_TEXT_RIGHT_JUSTIFY, true);
            Function.Call(Hash.SET_TEXT_WRAP, 0f, x);
            Function.Call(Hash.SET_TEXT_DROP_SHADOW);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            Function.Call(Hash.END_TEXT_COMMAND_DISPLAY_TEXT, x, y);
        }

        /// <summary>Draw a button and return true if hovered.</summary>
        private static bool DrawButton(string label, float cx, float cy,
            float w, float h, float mx, float my)
        {
            bool hovered = HitTest(mx, my, cx, cy, w, h);
            DrawRect(cx, cy, w, h, hovered ? BtnHover : BtnNormal);
            DrawTextCentered(label, cx, cy - h * 0.35f, 0.24f, TextWhite);
            return hovered;
        }

        private static bool HitTest(float px, float py,
            float rx, float ry, float rw, float rh)
        {
            float left = rx - rw / 2f;
            float top = ry - rh / 2f;
            return px >= left && px <= left + rw && py >= top && py <= top + rh;
        }

        private static void PlayNav()
        {
            Function.Call(Hash.PLAY_SOUND_FRONTEND, -1,
                "NAV_UP_DOWN", "HUD_FRONTEND_DEFAULT_SOUNDSET", true);
        }

        private static string GetCharacterName(Ped player)
        {
            if (player.Model == new Model(PedHash.Michael)) return "Michael";
            if (player.Model == new Model(PedHash.Franklin)) return "Franklin";
            if (player.Model == new Model(PedHash.Trevor)) return "Trevor";
            return "Unknown";
        }
    }
}
