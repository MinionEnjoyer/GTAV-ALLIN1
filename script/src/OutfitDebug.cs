// OutfitDebug.cs -- Debug overlay that displays all ped component/prop IDs.
//
// F10            = Toggle overlay on/off
// Numpad 8/2     = Select component/prop slot (up/down)
// Numpad 4/6     = Cycle drawable ID on selected slot
// Numpad 7/9     = Cycle texture ID on selected slot
// F11            = Toggle between component mode and prop mode

using System;
using System.Windows.Forms;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    public class OutfitDebug : Script
    {
        private bool _active;
        private int _selectedSlot;       // which slot is selected for editing
        private bool _propMode;          // false = components, true = props

        private static readonly string[] COMP_NAMES =
        {
            "0  Head",
            "1  Beard/Mask",
            "2  Hair",
            "3  Torso",
            "4  Legs",
            "5  Hands",
            "6  Shoes",
            "7  Neck/Scarf",
            "8  Shirt/Acc",
            "9  Body Armor",
            "10 Decals",
            "11 Aux/Torso2",
        };

        private static readonly string[] PROP_NAMES =
        {
            "P0 Hat/Helmet",
            "P1 Glasses",
            "P2 Ears",
            "P6 Watch",
            "P7 Bracelet",
        };

        private static readonly int[] PROP_SLOTS = { 0, 1, 2, 6, 7 };

        public OutfitDebug()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.F10)
            {
                _active = !_active;
                _selectedSlot = 0;
                _propMode = false;
            }

            if (!_active)
                return;

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead)
                return;

            // F11 = toggle component/prop mode
            if (e.KeyCode == Keys.F11)
            {
                _propMode = !_propMode;
                _selectedSlot = 0;
            }

            // Numpad 8/2 = select slot (up/down)
            int maxSlots = _propMode ? PROP_SLOTS.Length : 12;
            if (e.KeyCode == Keys.NumPad8)
                _selectedSlot = (_selectedSlot - 1 + maxSlots) % maxSlots;
            if (e.KeyCode == Keys.NumPad2)
                _selectedSlot = (_selectedSlot + 1) % maxSlots;

            // Numpad 4/6 = cycle drawable
            if (e.KeyCode == Keys.NumPad4 || e.KeyCode == Keys.NumPad6)
            {
                int dir = e.KeyCode == Keys.NumPad6 ? 1 : -1;

                if (_propMode)
                {
                    int slot = PROP_SLOTS[_selectedSlot];
                    int current = Function.Call<int>(Hash.GET_PED_PROP_INDEX, player, slot);
                    int max = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS, player, slot);

                    // -1 = none, 0..max-1 = valid
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
                    int slot = _selectedSlot;
                    int current = Function.Call<int>(
                        Hash.GET_PED_DRAWABLE_VARIATION, player, slot);
                    int max = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, player, slot);

                    int next = (current + dir + max) % max;
                    Function.Call(Hash.SET_PED_COMPONENT_VARIATION, player, slot, next, 0, 0);
                }
            }

            // Numpad 7/9 = cycle texture
            if (e.KeyCode == Keys.NumPad7 || e.KeyCode == Keys.NumPad9)
            {
                int dir = e.KeyCode == Keys.NumPad9 ? 1 : -1;

                if (_propMode)
                {
                    int slot = PROP_SLOTS[_selectedSlot];
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
                    int slot = _selectedSlot;
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
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!_active)
                return;

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead)
                return;

            float x = 0.01f;
            float y = 0.01f;
            float lineH = 0.022f;
            float scale = 0.30f;
            int font = 0;

            // Header
            string modeLabel = _propMode ? "PROPS" : "COMPONENTS";
            DrawDebugText($"=== OUTFIT DEBUG [{modeLabel}] (F10=close F11=mode) ===", x, y, scale, font);
            y += lineH;

            // Model hash
            int modelHash = player.Model.Hash;
            string charName = "Unknown";
            if (player.Model == new Model(PedHash.Michael)) charName = "Michael";
            else if (player.Model == new Model(PedHash.Franklin)) charName = "Franklin";
            else if (player.Model == new Model(PedHash.Trevor)) charName = "Trevor";
            DrawDebugText($"Character: {charName} (0x{modelHash:X8})", x, y, scale, font);
            y += lineH;
            DrawDebugText("Num8/2=slot  Num4/6=drawable  Num7/9=texture", x, y, scale, font);
            y += lineH * 1.5f;

            if (!_propMode)
            {
                // Components
                DrawDebugText("COMPONENTS:", x, y, scale, font);
                y += lineH;

                for (int i = 0; i < 12; i++)
                {
                    int drawable = Function.Call<int>(Hash.GET_PED_DRAWABLE_VARIATION, player, i);
                    int texture = Function.Call<int>(Hash.GET_PED_TEXTURE_VARIATION, player, i);
                    int maxDrawable = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, player, i);
                    int maxTexture = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_TEXTURE_VARIATIONS, player, i, drawable);

                    bool selected = i == _selectedSlot;
                    string marker = selected ? ">> " : "   ";
                    string line = $"{marker}{COMP_NAMES[i]}: D={drawable}/{maxDrawable}  T={texture}/{maxTexture}";

                    if (selected)
                        DrawDebugTextColored(line, x, y, scale, font, 255, 255, 100, 255);
                    else
                        DrawDebugText(line, x, y, scale, font);
                    y += lineH;
                }
            }
            else
            {
                // Props
                DrawDebugText("PROPS:", x, y, scale, font);
                y += lineH;

                for (int p = 0; p < PROP_SLOTS.Length; p++)
                {
                    int slot = PROP_SLOTS[p];
                    int drawable = Function.Call<int>(Hash.GET_PED_PROP_INDEX, player, slot);
                    int texture = Function.Call<int>(Hash.GET_PED_PROP_TEXTURE_INDEX, player, slot);
                    int maxDrawable = Function.Call<int>(
                        Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS, player, slot);
                    int maxTexture = drawable >= 0
                        ? Function.Call<int>(
                            Hash.GET_NUMBER_OF_PED_PROP_TEXTURE_VARIATIONS, player, slot, drawable)
                        : 0;

                    bool selected = p == _selectedSlot;
                    string marker = selected ? ">> " : "   ";
                    string status = drawable < 0 ? "NONE" : $"D={drawable}/{maxDrawable}  T={texture}/{maxTexture}";
                    string line = $"{marker}{PROP_NAMES[p]}: {status}";

                    if (selected)
                        DrawDebugTextColored(line, x, y, scale, font, 255, 255, 100, 255);
                    else
                        DrawDebugText(line, x, y, scale, font);
                    y += lineH;
                }
            }

            y += lineH * 0.5f;

            // Health/armor info
            DrawDebugText($"Health: {player.Health}/{player.MaxHealth}  Armor: {player.Armor}", x, y, scale, font);
        }

        private static void DrawDebugText(string text, float x, float y,
            float scale, int font)
        {
            DrawDebugTextColored(text, x, y, scale, font, 255, 255, 255, 255);
        }

        private static void DrawDebugTextColored(string text, float x, float y,
            float scale, int font, int r, int g, int b, int a)
        {
            Function.Call(Hash.SET_TEXT_FONT, font);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.SET_TEXT_COLOUR, r, g, b, a);
            Function.Call(Hash.SET_TEXT_DROP_SHADOW);
            Function.Call(Hash.SET_TEXT_OUTLINE);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            Function.Call(Hash.END_TEXT_COMMAND_DISPLAY_TEXT, x, y);
        }
    }
}
