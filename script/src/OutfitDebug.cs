// OutfitDebug.cs -- Debug overlay that displays all ped component/prop IDs.
//
// Press F10 to toggle the overlay on/off.
// Shows all 12 component slots (drawable + texture) and all prop slots.
// Use this during the Paleto Score heist to capture the juggernaut suit IDs.

using System;
using System.Windows.Forms;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    public class OutfitDebug : Script
    {
        private bool _active;

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
                _active = !_active;
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
            DrawDebugText("=== OUTFIT DEBUG (F10 toggle) ===", x, y, scale, font);
            y += lineH;

            // Model hash
            int modelHash = player.Model.Hash;
            string charName = "Unknown";
            if (player.Model == new Model(PedHash.Michael)) charName = "Michael";
            else if (player.Model == new Model(PedHash.Franklin)) charName = "Franklin";
            else if (player.Model == new Model(PedHash.Trevor)) charName = "Trevor";
            DrawDebugText($"Character: {charName} (0x{modelHash:X8})", x, y, scale, font);
            y += lineH * 1.5f;

            // Components header
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

                string line = $"{COMP_NAMES[i]}: D={drawable}/{maxDrawable}  T={texture}/{maxTexture}";
                DrawDebugText(line, x, y, scale, font);
                y += lineH;
            }

            y += lineH * 0.5f;

            // Props header
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

                string status = drawable < 0 ? "NONE" : $"D={drawable}/{maxDrawable}  T={texture}/{maxTexture}";
                string line = $"{PROP_NAMES[p]}: {status}";
                DrawDebugText(line, x, y, scale, font);
                y += lineH;
            }

            y += lineH * 0.5f;

            // Health/armor info
            DrawDebugText($"Health: {player.Health}/{player.MaxHealth}  Armor: {player.Armor}", x, y, scale, font);
        }

        private static void DrawDebugText(string text, float x, float y,
            float scale, int font)
        {
            Function.Call(Hash.SET_TEXT_FONT, font);
            Function.Call(Hash.SET_TEXT_SCALE, 0f, scale);
            Function.Call(Hash.SET_TEXT_COLOUR, 255, 255, 255, 255);
            Function.Call(Hash.SET_TEXT_DROP_SHADOW);
            Function.Call(Hash.SET_TEXT_OUTLINE);
            Function.Call(Hash.BEGIN_TEXT_COMMAND_DISPLAY_TEXT, "STRING");
            Function.Call(Hash.ADD_TEXT_COMPONENT_SUBSTRING_PLAYER_NAME, text);
            Function.Call(Hash.END_TEXT_COMMAND_DISPLAY_TEXT, x, y);
        }
    }
}
