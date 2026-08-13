// SeatSelector.cs — Hold the configured key to select a specific vehicle seat.
//
// Hold the selector key near a vehicle (or inside one) to bring up a seat
// picker HUD. Arrow keys navigate available seats; release the key to confirm.
//
// Seat changes are animation-only. The selector never warps the player. A
// reachable front and rear seat pairs use GTA's shuffle task; changes between
// rows and external positions (including turret mounts) use a normal exit
// followed by a normal pathfind-and-enter task.
//
// Player-only — does not affect NPC behavior.

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
    public class SeatSelector : Script
    {
        // ------------------------------------------------------------------ //
        //  Constants                                                          //
        // ------------------------------------------------------------------ //

        private int _holdThresholdMs = 350;
        private Keys _selectorKey = Keys.L;
        private const float NEARBY_RADIUS = 3.5f;
        private const float MAX_DIST_WHILE_SELECTING = 5f;
        private const int EXECUTE_TIMEOUT_MS = 25000;
        private const int ENTER_TIMEOUT_MS = 14000;
        private const int EXIT_TIMEOUT_MS = 7000;
        private const int EXIT_SETTLE_MS = 1200;
        private const int SHUFFLE_TIMEOUT_MS = 4500;
        private const float MAX_EXTERNAL_SWITCH_SPEED = 1.25f;
        private const int NORMAL_ENTER_FLAG = 1;
        private const int NORMAL_EXIT_FLAG = 0;

        // F key is Control.Enter on foot (23) and Control.VehicleExit in vehicle (75).
        // We read both via IS_DISABLED_CONTROL_PRESSED and suppress both when selecting.
        private const int CONTROL_ENTER = 23;
        private const int CONTROL_VEHICLE_EXIT = 75;

        private static readonly string LOG_PATH =
            Path.Combine("scripts", "ALLIN1_SeatSelector.log");

        // GTA exposes mounted weapon stations as ordinary high-numbered seats.
        // Keep model-specific names here so the selector does not present a
        // turret as a generic "Extra" seat. The Turreted Limo's roof gun is
        // passenger index 3 (the first external seat).
        private static readonly Dictionary<int, Dictionary<int, string>>
            SPECIAL_SEAT_LABELS = new Dictionary<int, Dictionary<int, string>>
            {
                {
                    Game.GenerateHash("limo2"),
                    new Dictionary<int, string> { { 3, "Turret" } }
                },
            };

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

        private enum ExecutionPhase
        {
            None,
            Entering,
            Shuffling,
            Exiting,
            WaitingAfterExit,
            Reentering,
        }

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
        private int _phaseStart;
        private int _targetSeatIdx;
        private int _sourceSeatIdx;
        private ExecutionPhase _executionPhase;
        private bool _enabled = true;

        // ------------------------------------------------------------------ //
        //  Constructor                                                        //
        // ------------------------------------------------------------------ //

        public SeatSelector()
        {
            LoadConfig();
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

                if (!_enabled)
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
            bool fHeld = IsSelectorHeld();

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
            if (elapsed < _holdThresholdMs)
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
            bool fHeld = IsSelectorHeld();

            if (!fHeld)
            {
                ConfirmSelection(player);
                return;
            }

            // Check Esc/Back → cancel
            if (Game.IsControlJustPressed(GTA.Control.FrontendCancel))
            {
                GbayRenderer.PlayBack();
                Reset();
                return;
            }

            // Refresh seat availability each frame (occupants can change),
            // preserving the selected physical seat rather than list position.
            int selectedSeat = _seats[_selectedIdx].Index;
            BuildSeatList(player);
            if (_seats.Count == 0)
            {
                Reset();
                return;
            }

            // Clamp selection index after rebuild
            if (_selectedIdx >= _seats.Count)
                _selectedIdx = _seats.Count - 1;
            for (int i = 0; i < _seats.Count; i++)
                if (_seats[i].Index == selectedSeat) _selectedIdx = i;

            // Arrow key navigation
            HandleNavigation();

            // Draw HUD
            DrawHud();
        }

        private void HandleNavigation()
        {
            int dX = 0, dY = 0;

            if (Game.IsControlJustPressed(GTA.Control.FrontendLeft))
                dX = -1;
            else if (Game.IsControlJustPressed(GTA.Control.FrontendRight))
                dX = 1;

            if (Game.IsControlJustPressed(GTA.Control.FrontendUp))
                dY = -1;
            else if (Game.IsControlJustPressed(GTA.Control.FrontendDown))
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
                if (_seats[i].GridRow == targetRow && _seats[i].GridCol == targetCol
                    && (_seats[i].Free || _seats[i].IsPlayer))
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
                    if (_seats[i].GridRow == targetRow
                        && (_seats[i].Free || _seats[i].IsPlayer))
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

            // Re-read immediately before acting; an NPC can claim a seat on
            // the same frame the player releases the selector key.
            if (_targetVeh == null || !_targetVeh.Exists()
                || (!_targetVeh.IsSeatFree((VehicleSeat)seat.Index) && !seat.IsPlayer))
            {
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle("~y~That seat is no longer available.", 2000);
                Reset();
                return;
            }

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
            _sourceSeatIdx = GetPlayerSeatIndex(player);

            if (!_playerInVehicle)
            {
                // Outside vehicle — only allow entry if very close to the vehicle
                float dist = player.Position.DistanceTo(_targetVeh.Position);
                if (dist > NEARBY_RADIUS)
                {
                    GbayRenderer.PlayError();
                    Reset();
                    return;
                }

                BeginEnter(player, false);
            }
            else
            {
                if (_sourceSeatIdx == -2)
                {
                    GbayRenderer.PlayError();
                    Reset();
                    return;
                }

                if (CanShuffleInside(_sourceSeatIdx, _targetSeatIdx))
                    BeginShuffle(player);
                else
                {
                    if (!CanBeginExternalRoute())
                    {
                        GbayRenderer.PlayError();
                        GTA.UI.Screen.ShowSubtitle(
                            "~y~Stop the vehicle before changing rows or using an external seat.",
                            3000);
                        Reset();
                        return;
                    }

                    BeginExit(player, "different_row_or_external_seat");
                }
            }

            _state = State.Executing;
        }

        // ------------------------------------------------------------------ //
        //  Executing — wait for player to land in seat                        //
        // ------------------------------------------------------------------ //

        private void TickExecuting(Ped player)
        {
            if (Game.IsControlJustPressed(GTA.Control.FrontendCancel))
            {
                CancelExecution(player, "cancelled_by_player", true);
                return;
            }

            // One overall guard covers the complete exit/walk-around/re-entry
            // route. Phase-specific guards below provide more useful recovery.
            if (Game.GameTime - _executeStart > EXECUTE_TIMEOUT_MS)
            {
                CancelExecution(player, "overall_timeout", true);
                return;
            }

            // Check if vehicle became invalid
            if (_targetVeh == null || !_targetVeh.Exists())
            {
                ClientLog.Info("SeatSelector", "seat_switch_cancelled",
                    new Dictionary<string, object> { { "reason", "vehicle_invalid" } });
                Reset();
                return;
            }

            // Always test success before availability. While the entry animation
            // finishes, GTA may already report the target seat as occupied.
            if (HasReachedTarget(player))
            {
                ClientLog.Info("SeatSelector", "seat_switch_completed",
                    new Dictionary<string, object>
                    {
                        { "from_seat", _sourceSeatIdx },
                        { "seat", _targetSeatIdx },
                    });
                Reset();
                return;
            }

            Ped occupant = _targetVeh.GetPedOnSeat((VehicleSeat)_targetSeatIdx);
            if (occupant != null && occupant.Exists() && occupant != player)
            {
                GTA.UI.Screen.ShowSubtitle("~y~That seat is no longer available.", 2000);
                CancelExecution(player, "seat_claimed", true);
                return;
            }

            int phaseElapsed = Game.GameTime - _phaseStart;
            switch (_executionPhase)
            {
                case ExecutionPhase.Shuffling:
                    TickShuffle(player, phaseElapsed);
                    break;

                case ExecutionPhase.Exiting:
                    if (!player.IsInVehicle())
                        SetExecutionPhase(
                            ExecutionPhase.WaitingAfterExit,
                            "exit_animation_settle");
                    else if (phaseElapsed > EXIT_TIMEOUT_MS)
                        CancelExecution(player, "exit_timeout", true);
                    break;

                case ExecutionPhase.WaitingAfterExit:
                    // IsInVehicle becomes false before GTA has finished the
                    // leave-vehicle animation. Starting another task during
                    // that tail cancels entry to external seats such as limo2's
                    // roof turret. Let the ped finish planting both feet first.
                    if (player.IsInVehicle())
                        CancelExecution(player, "returned_to_vehicle_during_exit", true);
                    else if (phaseElapsed >= EXIT_SETTLE_MS)
                        BeginEnter(player, true);
                    break;

                case ExecutionPhase.Entering:
                case ExecutionPhase.Reentering:
                    if (player.IsInVehicle() && player.CurrentVehicle != _targetVeh)
                        CancelExecution(player, "entered_different_vehicle", true);
                    else if (phaseElapsed > ENTER_TIMEOUT_MS)
                        CancelExecution(player, "entry_timeout", true);
                    break;

                default:
                    CancelExecution(player, "invalid_execution_phase", true);
                    break;
            }
        }

        private void TickShuffle(Ped player, int phaseElapsed)
        {
            if (!player.IsInVehicle() || player.CurrentVehicle != _targetVeh)
            {
                // A shuffle task should never put the player outside. If game
                // behavior or another script interrupted it, continue with the
                // normal animated entry route from the player's current position.
                BeginEnter(player, true);
                return;
            }

            if (phaseElapsed <= SHUFFLE_TIMEOUT_MS)
                return;

            // A same-row seat remains internally accessible. If a particular
            // layout rejects GTA's shuffle task, stop safely instead of opening
            // a door and converting the request into an external route.
            CancelExecution(player, "same_row_shuffle_timeout", true);
            GTA.UI.Screen.ShowSubtitle(
                "~y~This vehicle blocked the interior seat shuffle.", 3000);
        }

        private bool HasReachedTarget(Ped player)
        {
            return player.IsInVehicle()
                && player.CurrentVehicle == _targetVeh
                && GetPlayerSeatIndex(player) == _targetSeatIdx;
        }

        private bool CanShuffleInside(int currentSeat, int targetSeat)
        {
            // TASK_SHUFFLE_TO_NEXT_VEHICLE_SEAT has no target-seat argument, so
            // use it only for unambiguous two-seat cabin rows. GTA's standard
            // four-door topology numbers the front pair -1/0 and rear pair 1/2.
            // Higher indices remain conservative because they include jump,
            // limousine, cargo, and externally mounted turret positions.
            bool frontPair = IsSeatPair(currentSeat, targetSeat, -1, 0);
            bool rearPair = IsSeatPair(currentSeat, targetSeat, 1, 2);
            if ((!frontPair && !rearPair) ||
                _targetVeh == null || !_targetVeh.Exists())
                return false;

            int model = _targetVeh.Model.Hash;
            return !Function.Call<bool>(Hash.IS_THIS_MODEL_A_BIKE, model)
                && !Function.Call<bool>(Hash.IS_THIS_MODEL_A_BICYCLE, model)
                && !Function.Call<bool>(Hash.IS_THIS_MODEL_A_BOAT, model)
                && !Function.Call<bool>(Hash.IS_THIS_MODEL_A_HELI, model)
                && !Function.Call<bool>(Hash.IS_THIS_MODEL_A_PLANE, model)
                && !Function.Call<bool>(Hash.IS_THIS_MODEL_A_TRAIN, model);
        }

        private static bool IsSeatPair(
            int currentSeat, int targetSeat, int first, int second)
        {
            return (currentSeat == first && targetSeat == second)
                || (currentSeat == second && targetSeat == first);
        }

        private bool CanBeginExternalRoute()
        {
            return _targetVeh != null
                && _targetVeh.Exists()
                && Math.Abs(_targetVeh.Speed) <= MAX_EXTERNAL_SWITCH_SPEED;
        }

        private void BeginShuffle(Ped player)
        {
            SetExecutionPhase(ExecutionPhase.Shuffling, "interior_shuffle");
            Function.Call(Hash.TASK_SHUFFLE_TO_NEXT_VEHICLE_SEAT,
                player.Handle, _targetVeh.Handle);
        }

        private void BeginExit(Ped player, string route)
        {
            SetExecutionPhase(ExecutionPhase.Exiting, route);
            Function.Call(Hash.TASK_LEAVE_VEHICLE,
                player.Handle, _targetVeh.Handle, NORMAL_EXIT_FLAG);
        }

        private void BeginEnter(Ped player, bool reentry)
        {
            SetExecutionPhase(
                reentry ? ExecutionPhase.Reentering : ExecutionPhase.Entering,
                reentry ? "external_reentry" : "outside_entry");

            // Flag 1 is GTA's normal animated approach/entry. Do not use flags
            // 3 or 16: both are documented warp modes.
            Function.Call(Hash.TASK_ENTER_VEHICLE,
                player.Handle, _targetVeh.Handle, ENTER_TIMEOUT_MS,
                _targetSeatIdx, 2f, NORMAL_ENTER_FLAG, 0);
        }

        private void SetExecutionPhase(ExecutionPhase phase, string route)
        {
            _executionPhase = phase;
            _phaseStart = Game.GameTime;
            ClientLog.Info("SeatSelector", "seat_switch_phase",
                new Dictionary<string, object>
                {
                    { "phase", phase.ToString() },
                    { "route", route },
                    { "from_seat", _sourceSeatIdx },
                    { "target_seat", _targetSeatIdx },
                });
        }

        private void CancelExecution(Ped player, string reason, bool clearTasks)
        {
            if (clearTasks && player != null && player.Exists())
                Function.Call(Hash.CLEAR_PED_TASKS, player.Handle);

            ClientLog.Info("SeatSelector", "seat_switch_cancelled",
                new Dictionary<string, object>
                {
                    { "reason", reason },
                    { "phase", _executionPhase.ToString() },
                    { "from_seat", _sourceSeatIdx },
                    { "target_seat", _targetSeatIdx },
                });
            if (reason.EndsWith("timeout", StringComparison.OrdinalIgnoreCase))
                GTA.UI.Screen.ShowSubtitle("~y~Seat switch timed out safely.", 2000);
            Reset();
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

                string label = GetSeatLabel(_targetVeh.Model.Hash, idx);

                // Grid layout: 2 columns matching vehicle sides
                // Col 0 = left (driver side), Col 1 = right (passenger side)
                // Row 0: Driver (-1), Passenger (0)
                // Row 1: Left Rear (1), Right Rear (2)
                // Row 2+: extras paired — odd idx left, even idx right
                int row, col;
                if (idx == -1)      { row = 0; col = 0; } // Driver = left
                else if (idx == 0)  { row = 0; col = 1; } // Passenger = right
                else if (idx == 1)  { row = 1; col = 0; } // Left Rear = left
                else if (idx == 2)  { row = 1; col = 1; } // Right Rear = right
                else
                {
                    // Extra seats: 3,4→row 2  5,6→row 3 ...
                    row = (idx - 1) / 2 + 1;
                    col = (idx % 2 == 1) ? 0 : 1; // odd idx = left, even = right
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

        private static string GetSeatLabel(int modelHash, int seatIndex)
        {
            Dictionary<int, string> modelLabels;
            string specialLabel;
            if (SPECIAL_SEAT_LABELS.TryGetValue(modelHash, out modelLabels)
                && modelLabels.TryGetValue(seatIndex, out specialLabel))
                return specialLabel;

            switch (seatIndex)
            {
                case -1: return "Driver";
                case 0:  return "Passenger";
                case 1:  return "Left Rear";
                case 2:  return "Right Rear";
                default: return $"Extra {seatIndex - 2}";
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
                ? $"Release {_selectorKey}: switch  |  ESC: cancel"
                : $"Release {_selectorKey}: enter  |  ESC: cancel";
            GbayRenderer.DrawText(footerText, panelX, footerY - 0.009f,
                0.2f, COL_TEXT_DIM, GbayRenderer.FONT_CONDENSED, true);
        }

        // ------------------------------------------------------------------ //
        //  Utilities                                                          //
        // ------------------------------------------------------------------ //

        private void SuppressEnterExit()
        {
            if (_selectorKey != Keys.F)
                return;
            Game.DisableControlThisFrame(GTA.Control.Enter);
            Game.DisableControlThisFrame(GTA.Control.VehicleExit);
        }

        private bool IsSelectorHeld()
        {
            if (_selectorKey != Keys.F)
                return Game.IsKeyPressed(_selectorKey);
            return Function.Call<bool>(Hash.IS_CONTROL_PRESSED, 0, CONTROL_ENTER)
                || Function.Call<bool>(Hash.IS_CONTROL_PRESSED, 0, CONTROL_VEHICLE_EXIT)
                || Function.Call<bool>(Hash.IS_DISABLED_CONTROL_PRESSED, 0, CONTROL_ENTER)
                || Function.Call<bool>(Hash.IS_DISABLED_CONTROL_PRESSED, 0, CONTROL_VEHICLE_EXIT);
        }

        private void LoadConfig()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.toml");
            if (!File.Exists(path)) return;
            try
            {
                foreach (string raw in File.ReadAllLines(path))
                {
                    string line = raw.Trim();
                    int eq = line.IndexOf('=');
                    if (eq < 0) continue;
                    string key = line.Substring(0, eq).Trim();
                    string value = line.Substring(eq + 1).Trim();
                    if (key.Equals("seat_selector_enabled", StringComparison.OrdinalIgnoreCase))
                        _enabled = line.Substring(eq + 1).Trim().Equals(
                            "true", StringComparison.OrdinalIgnoreCase);
                    else if (key.Equals("seat_selector_key", StringComparison.OrdinalIgnoreCase))
                    {
                        string cleaned = value.Trim().Trim('"', '\'');
                        if (Enum.TryParse(cleaned, true, out Keys parsed))
                            _selectorKey = parsed;
                    }
                    else if (key.Equals("hold_duration_ms", StringComparison.OrdinalIgnoreCase)
                        && int.TryParse(value, out int duration))
                        _holdThresholdMs = Math.Max(100, Math.Min(2000, duration));
                }
            }
            catch (Exception ex)
            {
                LogError("LoadConfig", ex);
            }
        }

        private void Reset()
        {
            _state = State.Idle;
            _holdStart = 0;
            _targetVeh = null;
            _seats.Clear();
            _selectedIdx = 0;
            _executeStart = 0;
            _phaseStart = 0;
            _targetSeatIdx = 0;
            _sourceSeatIdx = -2;
            _playerInVehicle = false;
            _executionPhase = ExecutionPhase.None;
        }

        private void LogError(string context, Exception ex)
        {
            ClientLog.Error("SeatSelector", context, ex);
        }
    }
}
