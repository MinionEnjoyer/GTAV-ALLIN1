// InteriorScout.cs -- Debug tool for exploring DLC interiors.
//
// Press F10 to teleport to the nightclub garage interior (BA_DLC_INT_02_BA).
// The tool loads the IPL, configures entity sets, and teleports the player.
// Once inside, coordinate display is shown automatically.
//
// Controls while inside:
//   F10       -- Teleport to interior (or cycle through probe positions)
//   Numpad+   -- Move up 1 unit (Z)
//   Numpad-   -- Move down 1 unit (Z)
//   Numpad4   -- Move -5 on X
//   Numpad6   -- Move +5 on X
//   Numpad8   -- Move +5 on Y
//   Numpad2   -- Move -5 on Y
//
// Shows current position, interior ID, and IPL status on screen.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class InteriorScout : Script
    {
        private bool _active;
        private int _probeIndex;

        // IPLs to load — full milo path names (from Enable All Interiors mod)
        private static readonly string[] IPLS =
        {
            "ba_int_placement_ba_interior_1_dlc_int_02_ba_milo_", // garage & storage
            "ba_int_placement_ba_interior_0_dlc_int_01_ba_milo_", // main nightclub
            "ba_int_placement_ba_interior_2_dlc_int_03_ba_milo_", // terrorbyte bay
        };

        // Probe positions to try -- various coordinates near the known interior center
        private static readonly Vector3[] PROBES =
        {
            new Vector3(-1505.78f, -3012.59f, -80.0f),   // documented center
            new Vector3(-1505.78f, -3012.59f, -78.0f),   // 2 units higher
            new Vector3(-1505.78f, -3012.59f, -76.0f),   // 4 units higher
            new Vector3(-1505.78f, -3012.59f, -74.0f),   // 6 units higher
            new Vector3(-1517.0f,  -3010.0f,  -80.0f),   // offset X/Y
            new Vector3(-1493.0f,  -3009.0f,  -80.0f),   // our ped spawn
            new Vector3(-1520.0f,  -3012.59f, -80.0f),   // further west
            new Vector3(-1490.0f,  -3012.59f, -80.0f),   // further east
        };

        // Entity sets to configure
        private static readonly string[] DISABLE_SETS =
        {
            "Int02_ba_garage_blocker",
            "Int02_ba_storage_blocker",
            "Int02_ba_FanBlocker01",
        };

        private static readonly string[] ENABLE_SETS =
        {
            "Int02_ba_floor01",
            "Int02_ba_sec_upgrade_grg",
        };

        public InteriorScout()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.F10)
            {
                if (!_active)
                {
                    _active = true;
                    _probeIndex = 0;
                    LoadAndTeleport();
                }
                else
                {
                    // Cycle to next probe position
                    _probeIndex = (_probeIndex + 1) % PROBES.Length;
                    TeleportTo(PROBES[_probeIndex]);
                }
                return;
            }

            if (!_active) return;

            Ped player = Game.Player.Character;
            Vector3 pos = player.Position;

            switch (e.KeyCode)
            {
                case Keys.Add: // Numpad+
                    TeleportTo(new Vector3(pos.X, pos.Y, pos.Z + 1f));
                    break;
                case Keys.Subtract: // Numpad-
                    TeleportTo(new Vector3(pos.X, pos.Y, pos.Z - 1f));
                    break;
                case Keys.NumPad4:
                    TeleportTo(new Vector3(pos.X - 5f, pos.Y, pos.Z));
                    break;
                case Keys.NumPad6:
                    TeleportTo(new Vector3(pos.X + 5f, pos.Y, pos.Z));
                    break;
                case Keys.NumPad8:
                    TeleportTo(new Vector3(pos.X, pos.Y + 5f, pos.Z));
                    break;
                case Keys.NumPad2:
                    TeleportTo(new Vector3(pos.X, pos.Y - 5f, pos.Z));
                    break;
                case Keys.NumPad1: // Fine -1 X
                    TeleportTo(new Vector3(pos.X - 1f, pos.Y, pos.Z));
                    break;
                case Keys.NumPad3: // Fine +1 X
                    TeleportTo(new Vector3(pos.X + 1f, pos.Y, pos.Z));
                    break;
                case Keys.NumPad7: // Fine -1 Y
                    TeleportTo(new Vector3(pos.X, pos.Y - 1f, pos.Z));
                    break;
                case Keys.NumPad9: // Fine +1 Y
                    TeleportTo(new Vector3(pos.X, pos.Y + 1f, pos.Z));
                    break;
                case Keys.NumPad0: // Toggle noclip/gravity
                    bool frozen = player.IsPositionFrozen;
                    player.IsPositionFrozen = !frozen;
                    GTA.UI.Screen.ShowSubtitle(frozen ? "Unfrozen" : "Frozen in place", 1500);
                    break;
            }
        }

        private void LoadAndTeleport()
        {
            // Load MP DLC maps first — required for Online interiors in SP
            // Native: _LOAD_MP_DLC_MAPS (0x0888C3502DBBEEF5)
            Function.Call((Hash)0x0888C3502DBBEEF5, 1);
            Wait(500);

            // Remove then re-request all IPLs (same pattern as Enable All Interiors mod)
            foreach (string ipl in IPLS)
            {
                Function.Call(Hash.REMOVE_IPL, ipl);
            }
            foreach (string ipl in IPLS)
            {
                Function.Call(Hash.REQUEST_IPL, ipl);
            }

            // Wait for IPLs to load
            Wait(1000);

            // Get interior at the nightclub main coords (like EAI does)
            int interior = Function.Call<int>(
                Hash.GET_INTERIOR_AT_COORDS, -1604.664f, -3012.583f, -80.0f);

            if (interior != 0)
            {
                foreach (string set in DISABLE_SETS)
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, set);
                foreach (string set in ENABLE_SETS)
                    Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, set);
                Function.Call(Hash.REFRESH_INTERIOR, interior);

                GTA.UI.Screen.ShowSubtitle($"~g~Main nightclub interior {interior} configured.", 2000);
            }

            // Also try to get the garage interior specifically
            int garageInterior = Function.Call<int>(
                Hash.GET_INTERIOR_AT_COORDS, -1505.78f, -3012.59f, -80.0f);

            if (garageInterior != 0 && garageInterior != interior)
            {
                foreach (string set in DISABLE_SETS)
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, garageInterior, set);
                foreach (string set in ENABLE_SETS)
                    Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, garageInterior, set);
                Function.Call(Hash.REFRESH_INTERIOR, garageInterior);

                GTA.UI.Screen.ShowSubtitle($"~g~Garage interior {garageInterior} also configured.", 2000);
            }
            else if (garageInterior == 0)
            {
                GTA.UI.Screen.ShowSubtitle("~r~No garage interior found. Teleporting anyway.", 3000);
            }

            // Teleport player
            TeleportTo(PROBES[_probeIndex]);
        }

        private void TeleportTo(Vector3 pos)
        {
            Ped player = Game.Player.Character;
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                pos.X, pos.Y, pos.Z, false, false, false, true);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, true);

            Wait(100);

            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            player.IsPositionFrozen = false;
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!_active) return;

            Ped player = Game.Player.Character;
            Vector3 pos = player.Position;
            float heading = player.Heading;

            // Get interior info
            int interior = Function.Call<int>(
                Hash.GET_INTERIOR_AT_COORDS, pos.X, pos.Y, pos.Z);
            bool iplActive = Function.Call<bool>(Hash.IS_IPL_ACTIVE, IPLS[0]);

            // Check ground Z
            OutputArgument groundZ = new OutputArgument();
            bool hasGround = Function.Call<bool>(Hash.GET_GROUND_Z_FOR_3D_COORD,
                pos.X, pos.Y, pos.Z + 2f, groundZ, false);
            float gz = hasGround ? groundZ.GetResult<float>() : -999f;

            // Line 1: Position + heading
            GbayRenderer.DrawText(
                $"X:{pos.X:F2}  Y:{pos.Y:F2}  Z:{pos.Z:F2}  H:{heading:F1}",
                0.5f, 0.01f, 0.35f, Color.FromArgb(220, 100, 255, 100),
                GbayRenderer.FONT_CONDENSED, true);

            // Line 2: Interior info
            GbayRenderer.DrawText(
                $"Interior:{interior}  IPL:{(iplActive ? "YES" : "NO")}  GroundZ:{gz:F2}  Probe:{_probeIndex + 1}/{PROBES.Length}",
                0.5f, 0.035f, 0.3f, Color.FromArgb(200, 255, 200, 100),
                GbayRenderer.FONT_CONDENSED, true);

            // Line 3: Controls
            GbayRenderer.DrawText(
                "F10:next probe  Num+-:Z  Num4682:XY(5m)  Num1379:XY(1m)  Num0:freeze",
                0.5f, 0.055f, 0.25f, Color.FromArgb(160, 200, 200, 200),
                GbayRenderer.FONT_CONDENSED, true);
        }
    }
}
