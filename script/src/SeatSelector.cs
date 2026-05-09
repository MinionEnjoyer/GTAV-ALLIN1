// SeatSelector.cs — Hold-F seat selection for entering specific vehicle seats.
//
// Hold F near a vehicle (or inside one) to bring up a seat picker HUD.
// Arrow keys navigate available seats; release F to confirm entry.
// Tap F still works normally for default vehicle enter/exit.
//
// Player-only — does not affect NPC behavior.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class SeatSelector : Script
    {
        // ------------------------------------------------------------------ //
        //  Constants                                                          //
        // ------------------------------------------------------------------ //

        private const int HOLD_THRESHOLD_MS = 300;
        private const float NEARBY_RADIUS = 6f;
        private const float MAX_DIST_WHILE_SELECTING = 10f;
        private const int EXECUTE_TIMEOUT_MS = 5000;

        // F key is Control.Enter on foot (23) and Control.VehicleExit in vehicle (75).
        // We read both via IS_DISABLED_CONTROL_PRESSED and suppress both when selecting.
        private const int CONTROL_ENTER = 23;
        private const int CONTROL_VEHICLE_EXIT = 75;

        private static readonly string LOG_PATH =
            Path.Combine("scripts", "ALLIN1_SeatSelector.log");

        // HUD layout (normalized screen coords, bottom-right area)
        private const float HUD_RIGHT = 0.97f;
        private const float HUD_TOP = 0.55f;
        private const float CELL_W = 0.075f;
        private const float CELL_H = 0.035f;
        private const float CELL_PAD = 0.004f;
        private const float TITLE_H = 0.03f;
        private const float FOOTER_H = 0.025f;

        // HUD colors
        private static readonly Color COL_BG = Color.FromArgb(200, 20, 20, 20);
        private static readonly Color COL_TITLE_BG = Color.FromArgb(220, 35, 135, 70);
        private static readonly Color COL_SELECTED = Color.FromArgb(255, 45, 180, 80);
        private static readonly Color COL_PLAYER = Color.FromArgb(255, 60, 160, 220);
        private static readonly Color COL_OCCUPIED = Color.FromArgb(200, 160, 50, 50);
        private static readonly Color COL_FREE = Color.FromArgb(200, 60, 60, 60);
        private static readonly Color COL_TEXT = Color.FromArgb(255, 255, 255, 255);
        private static readonly Color COL_TEXT_DIM = Color.FromArgb(180, 180, 180, 180);

        // ------------------------------------------------------------------ //
        //  Types                                                              //
        // ------------------------------------------------------------------ //

        private enum State { Idle, Selecting, Executing }

        private struct SeatInfo
        {
            internal int Index;      // -1 = Driver, 0 = Passenger, 1+ = rear/extra
            internal string Label;
            internal bool Free;
            internal bool IsPlayer;
            internal int GridRow;    // row in the 2-column layout
            internal int GridCol;    // 0 = left (driver side), 1 = right
        }

        // ------------------------------------------------------------------ //
        //  State                                                              //
        // ------------------------------------------------------------------ //

        private State _state = State.Idle;

        // Hold detection
        private int _holdStart;

        // Selecting state
        private Vehicle _targetVeh;
        private readonly List<SeatInfo> _seats = new List<SeatInfo>();
        private int _selectedIdx;
        private bool _playerInVehicle;

        // Executing state
        private int _executeStart;
        private int _targetSeatIdx;

        // ------------------------------------------------------------------ //
        //  Constructor                                                        //
        // ------------------------------------------------------------------ //

        public SeatSelector()
        {
            Tick += OnTick;
            Interval = 0;
        }

        // ------------------------------------------------------------------ //
        //  Main Loop                                                          //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            try
            {
                if (Game.IsLoading)
                    return;

                Ped player = Game.Player.Character;
                if (player == null || player.IsDead)
                {
                    Reset();
                    return;
                }

                switch (_state)
                {
                    case State.Idle:
                        TickIdle(player);
                        break;
                    case State.Selecting:
                        TickSelecting(player);
                        break;
                    case State.Executing:
                        TickExecuting(player);
                        break;
                }
            }
            catch (Exception ex)
            {
                LogError("OnTick", ex);
                Reset();
            }
        }

        // ------------------------------------------------------------------ //
        //  Idle — monitor F key hold                                          //
        // ------------------------------------------------------------------ //

        private void TickIdle(Ped player)
        {
            // F key maps to different controls on foot vs in vehicle — check both
            bool fHeld = Function.Call<bool>(
                    Hash.IS_DISABLED_CONTROL_PRESSED, 0, CONTROL_ENTER)
                || Function.Call<bool>(
                    Hash.IS_DISABLED_CONTROL_PRESSED, 0, CONTROL_VEHICLE_EXIT);

            if (!fHeld)
            {
                _holdStart = 0;
                return;
            }

            // F is being held — start or continue timing
            int now = Game.GameTime;
            if (_holdStart == 0)
                _holdStart = now;

            int elapsed = now - _holdStart;
            if (elapsed < HOLD_THRESHOLD_MS)
                return; // Still under threshold — let normal F behavior proceed

            // Threshold reached — try to find a vehicle and enter Selecting
            _playerInVehicle = player.IsInVehicle();
            Vehicle veh = _playerInVehicle
                ? player.CurrentVehicle
                : FindNearbyVehicle(player);

            if (veh == null || !veh.Exists())
            {
                _holdStart = 0;
                return;
            }

            // Suppress default enter/exit now that we've committed to selection
            SuppressEnterExit();

            // Build seat list and enter Selecting
            _targetVeh = veh;
            BuildSeatList(player);

            if (_seats.Count == 0)
            {
                _holdStart = 0;
                return;
            }

            // Default selection: first free seat (or first seat if all occupied)
            _selectedIdx = 0;
            for (int i = 0; i < _seats.Count; i++)
            {
                if (_seats[i].Free && !_seats[i].IsPlayer)
                {
                    _selectedIdx = i;
                    break;
                }
            }

            _state = State.Selecting;
            GbayRenderer.PlayNav();
        }

        // ------------------------------------------------------------------ //
        //  Selecting — HUD + navigation                                       //
        // ------------------------------------------------------------------ //

        private void TickSelecting(Ped player)
        {
            // Suppress vehicle enter/exit every frame while selecting
            SuppressEnterExit();

            // Validate vehicle still exists and is in range
            if (_targetVeh == null || !_targetVeh.Exists()
                || player.Position.DistanceTo(_targetVeh.Position) > MAX_DIST_WHILE_SELECTING)
            {
                Reset();
                return;
            }

            // Check if F was released → confirm selection
            bool fHeld = Function.Call<bool>(
                    Hash.IS_DISABLED_CONTROL_PRESSED, 0, CONTROL_ENTER)
                || Function.Call<bool>(
                    Hash.IS_DISABLED_CONTROL_PRESSED, 0, CONTROL_VEHICLE_EXIT);

            if (!fHeld)
            {
                ConfirmSelection(player);
                return;
            }

            // Check Esc/Back → cancel
            if (Game.IsControlJustPressed(Control.FrontendCancel))
            {
                GbayRenderer.PlayBack();
                Reset();
                return;
            }

            // Refresh seat availability each frame (occupants can change)
            BuildSeatList(player);
            if (_seats.Count == 0)
            {
                Reset();
                return;
            }

            // Clamp selection index after rebuild
            if (_selectedIdx >= _seats.Count)
                _selectedIdx = _seats.Count - 1;

            // Arrow key navigation
            HandleNavigation();

            // Draw HUD
            DrawHud();
        }

        private void HandleNavigation()
        {
            int dX = 0, dY = 0;

            if (Game.IsControlJustPressed(Control.FrontendLeft))
                dX = -1;
            else if (Game.IsControlJustPressed(Control.FrontendRight))
                dX = 1;

            if (Game.IsControlJustPressed(Control.FrontendUp))
                dY = -1;
            else if (Game.IsControlJustPressed(Control.FrontendDown))
                dY = 1;

            if (dX == 0 && dY == 0)
                return;

            SeatInfo cur = _seats[_selectedIdx];
            int targetRow = cur.GridRow + dY;
            int targetCol = cur.GridCol + dX;

            // Find the seat at the target grid position
            int bestIdx = -1;
            for (int i = 0; i < _seats.Count; i++)
            {
                if (_seats[i].GridRow == targetRow && _seats[i].GridCol == targetCol)
                {
                    bestIdx = i;
                    break;
                }
            }

            // If exact match not found but we're moving vertically, try same column
            if (bestIdx < 0 && dY != 0)
            {
                for (int i = 0; i < _seats.Count; i++)
                {
                    if (_seats[i].GridRow == targetRow)
                    {
                        bestIdx = i;
                        break;
                    }
                }
            }

            if (bestIdx >= 0 && bestIdx != _selectedIdx)
            {
                _selectedIdx = bestIdx;
                GbayRenderer.PlayNav();
            }
        }

        // ------------------------------------------------------------------ //
        //  Confirm & Execute                                                  //
        // ------------------------------------------------------------------ //

        private void ConfirmSelection(Ped player)
        {
            SeatInfo seat = _seats[_selectedIdx];

            // Already in this seat
            if (seat.IsPlayer)
            {
                GbayRenderer.PlayError();
                Reset();
                return;
            }

            // Seat occupied by NPC
            if (!seat.Free)
            {
                GbayRenderer.PlayError();
                Reset();
                return;
            }

            GbayRenderer.PlaySelect();

            _targetSeatIdx = seat.Index;
            _executeStart = Game.GameTime;

            if (!_playerInVehicle)
            {
                // Outside vehicle — animated entry into specific seat
                Function.Call(Hash.TASK_ENTER_VEHICLE,
                    player.Handle, _targetVeh.Handle, 5000, _targetSeatIdx, 2f, 1, 0);
            }
            else
            {
                // Inside vehicle — check if we can shuffle or need to warp
                int currentSeat = GetPlayerSeatIndex(player);
                bool adjacentFront = (currentSeat == -1 && seat.Index == 0)
                                  || (currentSeat == 0 && seat.Index == -1);

                if (adjacentFront)
                {
                    Function.Call(Hash.TASK_SHUFFLE_TO_NEXT_VEHICLE_SEAT, player.Handle);
                }
                else
                {
                    player.Task.WarpIntoVehicle(_targetVeh, (VehicleSeat)_targetSeatIdx);
                }
            }

            _state = State.Executing;
        }

        // ------------------------------------------------------------------ //
        //  Executing — wait for player to land in seat                        //
        // ------------------------------------------------------------------ //

        private void TickExecuting(Ped player)
        {
            // Check timeout
            if (Game.GameTime - _executeStart > EXECUTE_TIMEOUT_MS)
            {
                Reset();
                return;
            }

            // Check if player reached the target seat
            if (player.IsInVehicle()
                && player.CurrentVehicle == _targetVeh
                && GetPlayerSeatIndex(player) == _targetSeatIdx)
            {
                Reset();
                return;
            }

            // Check if vehicle became invalid
            if (_targetVeh == null || !_targetVeh.Exists())
            {
                Reset();
                return;
            }
        }

        // ------------------------------------------------------------------ //
        //  Vehicle & Seat Helpers                                             //
        // ------------------------------------------------------------------ //

        private Vehicle FindNearbyVehicle(Ped player)
        {
            Vehicle[] nearby = World.GetNearbyVehicles(player, NEARBY_RADIUS);
            Vehicle best = null;
            float bestDist = float.MaxValue;

            foreach (Vehicle v in nearby)
            {
                if (v == null || !v.Exists())
                    continue;

                float d = player.Position.DistanceTo(v.Position);
                if (d < bestDist)
                {
                    bestDist = d;
                    best = v;
                }
            }

            return best;
        }

        private void BuildSeatList(Ped player)
        {
            _seats.Clear();

            if (_targetVeh == null || !_targetVeh.Exists())
                return;

            int maxPass = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS, _targetVeh.Handle);

            for (int idx = -1; idx < maxPass; idx++)
            {
                var seat = (VehicleSeat)idx;
                Ped occupant = _targetVeh.GetPedOnSeat(seat);
                bool free = _targetVeh.IsSeatFree(seat);
                bool isPlayer = (occupant != null && occupant.Exists()
                                 && occupant == player);

                string label;
                switch (idx)
                {
                    case -1: label = "Driver"; break;
                    case 0:  label = "Passenger"; break;
                    case 1:  label = "Left Rear"; break;
                    case 2:  label = "Right Rear"; break;
                    default: label = $"Extra {idx - 2}"; break;
                }

                // Grid layout: 2 columns
                // Row 0: Driver (col 0), Passenger (col 1)
                // Row 1: Left Rear (col 0), Right Rear (col 1)
                // Row 2+: extras paired left/right
                int row, col;
                if (idx == -1)      { row = 0; col = 0; }
                else if (idx == 0)  { row = 0; col = 1; }
                else
                {
                    row = (idx + 1) / 2;  // 1,2→1  3,4→2  5,6→3 ...
                    col = (idx + 1) % 2 == 0 ? 1 : 0;
                }

                _seats.Add(new SeatInfo
                {
                    Index = idx,
                    Label = label,
                    Free = free || isPlayer,
                    IsPlayer = isPlayer,
                    GridRow = row,
                    GridCol = col,
                });
            }
        }

        private int GetPlayerSeatIndex(Ped player)
        {
            if (_targetVeh == null || !player.IsInVehicle())
                return -2; // not in vehicle

            int maxPass = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS, _targetVeh.Handle);

            for (int idx = -1; idx < maxPass; idx++)
            {
                Ped occupant = _targetVeh.GetPedOnSeat((VehicleSeat)idx);
                if (occupant != null && occupant == player)
                    return idx;
            }

            return -2;
        }

        // ------------------------------------------------------------------ //
        //  HUD Drawing                                                        //
        // ------------------------------------------------------------------ //

        private void DrawHud()
        {
            if (_seats.Count == 0 || _targetVeh == null)
                return;

            // Determine grid dimensions
            int maxRow = 0;
            foreach (SeatInfo s in _seats)
                if (s.GridRow > maxRow)
                    maxRow = s.GridRow;
            int rowCount = maxRow + 1;

            // Panel dimensions
            float gridW = CELL_W * 2 + CELL_PAD * 3;
            float gridH = CELL_H * rowCount + CELL_PAD * (rowCount + 1);
            float panelW = gridW;
            float panelH = TITLE_H + gridH + FOOTER_H;

            // Panel position (right-aligned)
            float panelX = HUD_RIGHT - panelW / 2;
            float panelY = HUD_TOP + panelH / 2;

            // Background
            GbayRenderer.DrawRect(panelX, panelY, panelW, panelH, COL_BG);

            // Title bar
            float titleY = HUD_TOP + TITLE_H / 2;
            GbayRenderer.DrawRect(panelX, titleY, panelW, TITLE_H, COL_TITLE_BG);

            string vehLabel = _targetVeh.LocalizedName ?? "Vehicle";
            GbayRenderer.DrawText(vehLabel, panelX, titleY - 0.011f,
                0.28f, COL_TEXT, GbayRenderer.FONT_CONDENSED, true);

            // Seat cells
            float gridTop = HUD_TOP + TITLE_H;
            foreach (SeatInfo s in _seats)
            {
                float cellX = (HUD_RIGHT - panelW)
                            + CELL_PAD + s.GridCol * (CELL_W + CELL_PAD) + CELL_W / 2;
                float cellY = gridTop
                            + CELL_PAD + s.GridRow * (CELL_H + CELL_PAD) + CELL_H / 2;

                // Cell color
                Color bg;
                int listIdx = _seats.IndexOf(s);
                if (listIdx == _selectedIdx)
                    bg = COL_SELECTED;
                else if (s.IsPlayer)
                    bg = COL_PLAYER;
                else if (!s.Free)
                    bg = COL_OCCUPIED;
                else
                    bg = COL_FREE;

                GbayRenderer.DrawRect(cellX, cellY, CELL_W, CELL_H, bg);

                // Cell label
                Color tc = (listIdx == _selectedIdx || s.IsPlayer)
                    ? COL_TEXT : COL_TEXT_DIM;
                GbayRenderer.DrawText(s.Label, cellX, cellY - 0.011f,
                    0.24f, tc, GbayRenderer.FONT_CONDENSED, true);
            }

            // Footer
            float footerY = HUD_TOP + TITLE_H + gridH + FOOTER_H / 2;
            string footerText = _playerInVehicle
                ? "Release F: switch  |  ESC: cancel"
                : "Release F: enter  |  ESC: cancel";
            GbayRenderer.DrawText(footerText, panelX, footerY - 0.009f,
                0.2f, COL_TEXT_DIM, GbayRenderer.FONT_CONDENSED, true);
        }

        // ------------------------------------------------------------------ //
        //  Utilities                                                          //
        // ------------------------------------------------------------------ //

        private void SuppressEnterExit()
        {
            Game.DisableControlThisFrame(Control.Enter);
            Game.DisableControlThisFrame(Control.VehicleExit);
        }

        private void Reset()
        {
            _state = State.Idle;
            _holdStart = 0;
            _targetVeh = null;
            _seats.Clear();
            _selectedIdx = 0;
            _executeStart = 0;
            _targetSeatIdx = 0;
            _playerInVehicle = false;
        }

        private void LogError(string context, Exception ex)
        {
            try
            {
                string msg = $"[{DateTime.Now:HH:mm:ss}] SeatSelector.{context}: {ex.Message}\n{ex.StackTrace}\n";
                File.AppendAllText(LOG_PATH, msg);
            }
            catch
            {
                // Ignore logging failures
            }
        }
    }
}
