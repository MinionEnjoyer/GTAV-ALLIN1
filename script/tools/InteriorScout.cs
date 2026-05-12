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
using System.IO;
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

        // Probe positions to try -- first probe is the confirmed ped spawn (B2 garage floor)
        private static readonly Vector3[] PROBES =
        {
            new Vector3(-1507.65f, -3031.08f, -79.23f),  // confirmed ped spawn (B2 garage)
            new Vector3(-1507.55f, -3014.50f, -79.24f),  // elevator 1 position
            new Vector3(-1505.78f, -3012.59f, -80.0f),   // documented center
            new Vector3(-1505.78f, -3012.59f, -78.0f),   // 2 units higher
            new Vector3(-1517.0f,  -3010.0f,  -80.0f),   // offset X/Y
            new Vector3(-1493.0f,  -3009.0f,  -80.0f),   // east side
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

        // Entity set names to probe on the garage interior (Int02_ba).
        // Comprehensive list based on Int01 naming patterns + common garage names.
        private static readonly string[] ENTITY_SET_PROBES =
        {
            // Known working
            "Int02_ba_garage_blocker",
            "Int02_ba_storage_blocker",
            "Int02_ba_FanBlocker01",
            "Int02_ba_floor01",
            "Int02_ba_floor02",
            "Int02_ba_floor03",
            "Int02_ba_sec_upgrade_grg",
            // Floor styles (extrapolated from Int01 Style patterns)
            "Int02_ba_Style01",
            "Int02_ba_Style02",
            "Int02_ba_Style03",
            "Int02_ba_style01",
            "Int02_ba_style02",
            "Int02_ba_style03",
            // Security / upgrades
            "Int02_ba_security_upgrade",
            "Int02_ba_equipment_upgrade",
            "Int02_ba_equipment_setup",
            "Int02_ba_upgrade01",
            "Int02_ba_upgrade02",
            "Int02_ba_upgrade03",
            // Garage specific
            "Int02_ba_garage01",
            "Int02_ba_garage02",
            "Int02_ba_garage03",
            "Int02_ba_garage_a",
            "Int02_ba_garage_b",
            "Int02_ba_garage_c",
            "Int02_ba_garage_d",
            "Int02_ba_garage_floor01",
            "Int02_ba_garage_floor02",
            "Int02_ba_garage_floor03",
            "Int02_ba_garage_level01",
            "Int02_ba_garage_level02",
            "Int02_ba_garage_level03",
            // Storage
            "Int02_ba_storage01",
            "Int02_ba_storage02",
            "Int02_ba_storage03",
            "Int02_ba_storage_a",
            "Int02_ba_storage_b",
            "Int02_ba_storage_c",
            // Decorative / misc
            "Int02_ba_Clutter",
            "Int02_ba_clutter",
            "Int02_ba_Worklamps",
            "Int02_ba_worklamps",
            "Int02_ba_deliverytruck",
            "Int02_ba_lightgrid_01",
            "Int02_ba_lights",
            "Int02_ba_neon",
            "Int02_ba_neon01",
            "Int02_ba_neon02",
            "Int02_ba_trad_lights",
            "Int02_ba_dry_ice",
            "Int02_ba_Screen",
            // Vehicles / lifts
            "Int02_ba_carmod",
            "Int02_ba_mod_booth",
            "Int02_ba_no_mod_booth",
            "Int02_ba_vehiclelift",
            "Int02_ba_carlift",
            // Blockers
            "Int02_ba_blocker",
            "Int02_ba_blocker01",
            "Int02_ba_blocker02",
            "Int02_ba_FanBlocker02",
            "Int02_ba_door_blocker",
            // B levels (if they exist as separate sets)
            "Int02_ba_b1",
            "Int02_ba_b2",
            "Int02_ba_b3",
            "Int02_ba_b4",
            "Int02_ba_B1",
            "Int02_ba_B2",
            "Int02_ba_B3",
            "Int02_ba_B4",
            "Int02_ba_level_b1",
            "Int02_ba_level_b2",
            "Int02_ba_level_b3",
            "Int02_ba_level_b4",
            // Wall / decor variants
            "Int02_ba_walls_01",
            "Int02_ba_walls_02",
            "Int02_ba_walls_03",
            "Int02_ba_decor_01",
            "Int02_ba_decor_02",
            "Int02_ba_decor_03",
            // Tint
            "Int02_ba_tint_01",
            "Int02_ba_tint_02",
            "Int02_ba_tint_03",
        };

        private List<string> _activeEntitySets = new List<string>();
        private bool _entitySetScanDone;
        private int _entitySetPage; // for paging results display


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

            if (e.KeyCode == Keys.F11 && _active)
            {
                ScanEntitySets();
                return;
            }

            if (e.KeyCode == Keys.F12 && _active && _entitySetScanDone)
            {
                _entitySetPage = (_entitySetPage + 1) % Math.Max(1, (_activeEntitySets.Count + 7) / 8);
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
                Hash.GET_INTERIOR_AT_COORDS, -1505.782f, -3012.587f, -80.0f);

            if (interior != 0)
            {
                foreach (string set in DISABLE_SETS)
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, set);
                foreach (string set in ENABLE_SETS)
                    Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, set);
                Function.Call(Hash.REFRESH_INTERIOR, interior);

                GTA.UI.Screen.ShowSubtitle($"~g~Garage interior {interior} configured.", 2000);
            }
            else
            {
                GTA.UI.Screen.ShowSubtitle("~r~No garage interior found. Teleporting anyway.", 3000);
            }

            // Teleport player and activate floor garage state so elevator works
            TeleportTo(PROBES[_probeIndex]);
            GarageManager.DebugSetInFloorGarage(true);
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

        /// <summary>
        /// Scans all probe entity set names against the current interior.
        /// For each name, tries to activate it, checks if it became active,
        /// then deactivates it. Records which names are valid.
        /// Writes results to ALLIN1_entity_sets.log.
        /// </summary>
        private void ScanEntitySets()
        {
            string logPath = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory,
                "ALLIN1_entity_sets.log");

            try
            {
                Ped player = Game.Player.Character;
                Vector3 pos = player.Position;

                int interior = Function.Call<int>(
                    Hash.GET_INTERIOR_AT_COORDS, pos.X, pos.Y, pos.Z);

                if (interior == 0)
                    interior = Function.Call<int>(
                        Hash.GET_INTERIOR_AT_COORDS, -1505.78f, -3012.59f, -80.0f);
                if (interior == 0)
                    interior = Function.Call<int>(
                        Hash.GET_INTERIOR_AT_COORDS, -1604.664f, -3012.583f, -80.0f);

                if (interior == 0)
                {
                    File.WriteAllText(logPath, "ERROR: No interior found at any known coords.\n");
                    GTA.UI.Screen.ShowSubtitle("~r~No interior found. Check log.", 3000);
                    return;
                }

                _activeEntitySets.Clear();
                _entitySetPage = 0;

                var log = new System.Text.StringBuilder();
                log.AppendLine($"Entity Set Scan - Interior {interior}");
                log.AppendLine($"Player pos: {pos.X:F2}, {pos.Y:F2}, {pos.Z:F2}");
                log.AppendLine($"Timestamp: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                log.AppendLine($"Probing {ENTITY_SET_PROBES.Length} names...");
                log.AppendLine();

                // First: test with a known-garbage name to see if IS_ACTIVE lies
                string garbageName = "Int02_ba_ZZZZZ_DOES_NOT_EXIST_99";
                Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, garbageName);
                bool garbageActive = Function.Call<bool>(
                    (Hash)0x35F7DD45E8C0A16D, interior, garbageName);
                Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, garbageName);

                log.AppendLine($"Garbage test: activate+check '{garbageName}' = {garbageActive}");
                log.AppendLine();

                if (garbageActive)
                {
                    // IS_ACTIVE returns true for anything after ACTIVATE — useless.
                    // Fall back: only check IS_ACTIVE WITHOUT activating first.
                    // This finds sets currently active + won't false-positive on junk.
                    log.AppendLine("NOTE: IS_ACTIVE lies after ACTIVATE. Using passive scan.");
                    log.AppendLine();

                    foreach (string setName in ENTITY_SET_PROBES)
                    {
                        bool isActive = Function.Call<bool>(
                            (Hash)0x35F7DD45E8C0A16D, interior, setName);
                        log.AppendLine($"  {(isActive ? "ACTIVE" : "inactive")}: {setName}");
                        if (isActive)
                            _activeEntitySets.Add(setName);
                    }
                }
                else
                {
                    // ACTIVATE + IS_ACTIVE is reliable — use it
                    foreach (string setName in ENTITY_SET_PROBES)
                    {
                        Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, setName);
                        bool isActive = Function.Call<bool>(
                            (Hash)0x35F7DD45E8C0A16D, interior, setName);
                        if (isActive)
                        {
                            _activeEntitySets.Add(setName);
                            log.AppendLine($"  VALID: {setName}");
                            Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, setName);
                        }
                    }

                    // Restore known good state
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_garage_blocker");
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_storage_blocker");
                    Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_FanBlocker01");
                    Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_floor01");
                    Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_sec_upgrade_grg");
                    Function.Call(Hash.REFRESH_INTERIOR, interior);
                }

                log.AppendLine();
                log.AppendLine($"Total valid: {_activeEntitySets.Count} / {ENTITY_SET_PROBES.Length}");

                File.WriteAllText(logPath, log.ToString());
                _entitySetScanDone = true;

                GTA.UI.Screen.ShowSubtitle(
                    $"~g~Scan done: {_activeEntitySets.Count} valid. Saved to ALLIN1_entity_sets.log", 5000);
            }
            catch (Exception ex)
            {
                File.WriteAllText(logPath, $"EXCEPTION: {ex.Message}\n{ex.StackTrace}\n");
                GTA.UI.Screen.ShowSubtitle("~r~Scan crashed. Check ALLIN1_entity_sets.log", 5000);
            }
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
                "F10:probe  F11:scan entity sets  F12:page results  Num:move",
                0.5f, 0.055f, 0.25f, Color.FromArgb(160, 200, 200, 200),
                GbayRenderer.FONT_CONDENSED, true);

            // Entity set scan results
            if (_entitySetScanDone && _activeEntitySets.Count > 0)
            {
                int perPage = 8;
                int totalPages = (_activeEntitySets.Count + perPage - 1) / perPage;
                int start = _entitySetPage * perPage;
                int end = Math.Min(start + perPage, _activeEntitySets.Count);

                GbayRenderer.DrawText(
                    $"Entity Sets ({_activeEntitySets.Count} found) - Page {_entitySetPage + 1}/{totalPages}",
                    0.5f, 0.08f, 0.3f, Color.FromArgb(220, 255, 200, 50),
                    GbayRenderer.FONT_CONDENSED, true);

                for (int i = start; i < end; i++)
                {
                    float y = 0.10f + (i - start) * 0.02f;
                    GbayRenderer.DrawText(
                        _activeEntitySets[i],
                        0.5f, y, 0.28f, Color.FromArgb(220, 200, 255, 200),
                        GbayRenderer.FONT_CONDENSED, true);
                }
            }
            else if (_entitySetScanDone)
            {
                GbayRenderer.DrawText(
                    "No valid entity sets found for this interior",
                    0.5f, 0.08f, 0.3f, Color.FromArgb(220, 255, 100, 100),
                    GbayRenderer.FONT_CONDENSED, true);
            }
        }
    }
}
