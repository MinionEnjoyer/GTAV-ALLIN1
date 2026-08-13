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
    internal sealed class SeatSwitchTelemetry
    {
        internal bool Success { get; set; }
        internal string Outcome { get; set; }
        internal string Reason { get; set; }
        internal int ModelHash { get; set; }
        internal int SourceSeat { get; set; }
        internal int TargetSeat { get; set; }
        internal int LandedSeat { get; set; }
        internal int ObservedWrongSeat { get; set; }
        internal int ElapsedMs { get; set; }
        internal string FinalPhase { get; set; }
        internal string PhaseTrace { get; set; }
        internal bool UsedExternalRoute { get; set; }
        internal bool RouteValidated { get; set; }
        internal int RouteResult { get; set; }
        internal int RouteCandidate { get; set; }
        internal int WaypointCount { get; set; }
    }

    public class SeatSelector : Script
    {
        // ------------------------------------------------------------------ //
        //  Constants                                                          //
        // ------------------------------------------------------------------ //

        private int _holdThresholdMs = 350;
        private Keys _selectorKey = Keys.L;
        private const float NEARBY_RADIUS = 3.5f;
        private const float MAX_DIST_WHILE_SELECTING = 5f;
        private const int EXECUTE_TIMEOUT_MS = 32000;
        private const int ENTER_TIMEOUT_MS = 14000;
        private const int EXIT_TIMEOUT_MS = 7000;
        private const int EXIT_SETTLE_MS = 1200;
        private const int EXTERNAL_APPROACH_TIMEOUT_MS = 7000;
        private const int EXTERNAL_ROUTE_DISCOVERY_GRACE_MS = 1500;
        private const int EXTERNAL_ROUTE_STALL_TIMEOUT_MS = 2500;
        private const int SHUFFLE_TIMEOUT_MS = 4500;
        private const int NATIVE_CONTEXT_ENTRY_HOLD_MS = 2500;
        private const float EXTERNAL_APPROACH_DISTANCE = 0.85f;
        private const float EXTERNAL_ROUTE_PROGRESS_EPSILON = 0.12f;
        private const float EXTERNAL_ROUTE_CLEARANCE = 0.8f;
        private const float EXTERNAL_ROUTE_TRACE_HEIGHT = 0.65f;
        private const float EXTERNAL_ROUTE_TRACE_RADIUS = 0.3f;
        private const float MAX_EXTERNAL_SWITCH_SPEED = 1.25f;
        private const int NATIVE_ENTER_TIMEOUT = -1;
        // A fresh exact-seat request must use None (0). ResumeIfInterrupted (1)
        // lets GTA continue an earlier driver/front-passenger entry task on
        // custom layouts such as LAYOUT_RANGER_CARACARA.
        private const int NORMAL_ENTER_FLAG = 0;
        private const int NORMAL_EXIT_FLAG = 0;

        // GET_NAVMESH_ROUTE_RESULT mirrors GTA's NavMeshRouteResult enum.
        private const int NAV_ROUTE_TASK_NOT_FOUND = 0;
        private const int NAV_ROUTE_NOT_YET_TRIED = 1;
        private const int NAV_ROUTE_NOT_FOUND = 2;
        private const int NAV_ROUTE_FOUND = 3;

        // F key is Control.Enter on foot (23) and Control.VehicleExit in vehicle (75).
        // We read both via IS_DISABLED_CONTROL_PRESSED and suppress both when selecting.
        private const int CONTROL_ENTER = 23;
        private const int CONTROL_VEHICLE_EXIT = 75;

        private static readonly string LOG_PATH =
            Path.Combine("scripts", "ALLIN1_SeatSelector.log");

        // These hashes also have model-specific pathing policy below. Seat
        // names for them and every other game/DLC model come from the generated
        // Rockstar metadata catalog.
        private const int LIMO2_HASH = -114627507;
        private const int CARACARA_HASH = 1254014755;

        // The Caracara layout defines three vehicle-relative climb points for
        // its bed turret. GTA's generic seat task can time out when issued at
        // the front door, so walk to the nearest authored point before asking
        // the normal entry task to play the climb animation.
        private static readonly Vector3[] CARACARA_TURRET_APPROACH_OFFSETS =
        {
            new Vector3(-1.650f, -2.543f, 0.382f),
            new Vector3(1.680f, -2.543f, 0.382f),
            new Vector3(0.050f, -4.118f, 0.382f),
        };

        // The six-wheeler's rear doors sit much farther forward than a generic
        // pickup bounding box suggests. These are the authored EntryTranslation
        // values from mpassault's LAYOUT_RANGER_CARACARA metadata.
        private static readonly Vector3[] CARACARA_REAR_LEFT_APPROACH_OFFSETS =
        {
            new Vector3(-1.2486f, -0.1472f, 0.2500f),
        };
        private static readonly Vector3[] CARACARA_REAR_RIGHT_APPROACH_OFFSETS =
        {
            new Vector3(1.2244f, -0.2042f, 0.2000f),
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
            PlanningExternalRoute,
            Entering,
            Shuffling,
            Exiting,
            WaitingAfterExit,
            Reentering,
            ApproachingExternalSeat,
            RecoveringWrongSeat,
            ReturningToSourceSeat,
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
        private Vector3 _externalApproachPoint;
        private bool _approachIsReentry;
        private bool _nativeContextEntryActive;
        private bool _usesExternalRoute;
        private bool _externalRouteValidated;
        private float _externalRouteBestDistance;
        private int _externalRouteLastProgress;
        private int _externalRouteResult;
        private string _pendingFailureReason;
        private int _observedWrongSeat = -2;
        private readonly List<Vector3> _plannedExternalWaypoints =
            new List<Vector3>();
        private int _externalRouteWaypointIndex;
        private bool _hasPreplannedExternalRoute;
        private readonly List<List<Vector3>> _routePlanCandidates =
            new List<List<Vector3>>();
        private readonly List<string> _phaseTrace = new List<string>();
        private int _routePlanCandidateIndex;
        private int _routePlanSegmentIndex;
        private ShapeTestHandle _routeShapeTest;
        private ExecutionPhase _executionPhase;
        private bool _enabled = true;
        private bool _harnessOwned;

        internal static SeatSelector ActiveInstance { get; private set; }
        internal static event Action<SeatSwitchTelemetry> HarnessSwitchFinished;
        internal bool IsHarnessSwitchRunning =>
            _harnessOwned && _state == State.Executing;

        // ------------------------------------------------------------------ //
        //  Constructor                                                        //
        // ------------------------------------------------------------------ //

        public SeatSelector()
        {
            ActiveInstance = this;
            LoadConfig();
            Tick += OnTick;
            Aborted += OnAborted;
            Interval = 0;
        }

        private void OnAborted(object sender, EventArgs e)
        {
            if (ReferenceEquals(ActiveInstance, this))
                ActiveInstance = null;
        }

        internal bool TryBeginHarnessSwitch(
            Vehicle vehicle, int targetSeat, out string rejectionReason)
        {
            rejectionReason = null;
            if (!_enabled)
            {
                rejectionReason = "selector_disabled";
                return false;
            }
            if (_state != State.Idle)
            {
                rejectionReason = "selector_busy";
                return false;
            }

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead)
            {
                rejectionReason = "player_unavailable";
                return false;
            }
            if (vehicle == null || !vehicle.Exists())
            {
                rejectionReason = "vehicle_invalid";
                return false;
            }

            _targetVeh = vehicle;
            _playerInVehicle = player.IsInVehicle()
                && player.CurrentVehicle == vehicle;
            BuildSeatList(player);
            _selectedIdx = _seats.FindIndex(seat => seat.Index == targetSeat);
            if (_selectedIdx < 0)
            {
                rejectionReason = "target_seat_missing";
                Reset();
                return false;
            }
            if (_seats[_selectedIdx].IsPlayer)
            {
                rejectionReason = "source_equals_target";
                Reset();
                return false;
            }
            if (!_seats[_selectedIdx].Free)
            {
                rejectionReason = "target_seat_occupied";
                Reset();
                return false;
            }

            _harnessOwned = true;
            _phaseTrace.Clear();
            ConfirmSelection(player);
            if (_state != State.Executing)
            {
                rejectionReason = "selector_rejected";
                return false;
            }
            return true;
        }

        internal void AbortHarnessSwitch(string reason)
        {
            if (!_harnessOwned)
                return;
            Ped player = Game.Player.Character;
            CancelExecution(player, reason ?? "seat_lab_aborted", true);
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

                if (!BeginExternalApproach(player, false))
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

                    if (!BeginSimulatedExternalRoutePlan(player))
                    {
                        GbayRenderer.PlayError();
                        GTA.UI.Screen.ShowSubtitle(
                            "~y~No clear walking route between those seats.",
                            3000);
                        ClientLog.Info("SeatSelector", "seat_switch_cancelled",
                            new Dictionary<string, object>
                            {
                                { "reason", "preexit_route_blocked" },
                                { "from_seat", _sourceSeatIdx },
                                { "target_seat", _targetSeatIdx },
                                { "model_hash", _targetVeh.Model.Hash },
                            });
                        PublishHarnessResult(
                            player, false, "cancelled", "preexit_route_blocked");
                        Reset();
                        return;
                    }
                    _state = State.Executing;
                    return;
                }
            }

            _state = State.Executing;
        }

        // ------------------------------------------------------------------ //
        //  Executing — wait for player to land in seat                        //
        // ------------------------------------------------------------------ //

        private void TickExecuting(Ped player)
        {
            if (!_harnessOwned
                && Game.IsControlJustPressed(GTA.Control.FrontendCancel))
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
                PublishHarnessResult(player, false, "cancelled", "vehicle_invalid");
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
                PublishHarnessResult(player, true, "completed", "target_reached");
                Reset();
                return;
            }

            Ped occupant = _targetVeh.GetPedOnSeat((VehicleSeat)_targetSeatIdx);
            if (_executionPhase != ExecutionPhase.RecoveringWrongSeat
                && _executionPhase != ExecutionPhase.ReturningToSourceSeat
                && occupant != null && occupant.Exists() && occupant != player)
            {
                GTA.UI.Screen.ShowSubtitle("~y~That seat is no longer available.", 2000);
                CancelExecution(player, "seat_claimed", true);
                return;
            }

            int phaseElapsed = Game.GameTime - _phaseStart;
            switch (_executionPhase)
            {
                case ExecutionPhase.PlanningExternalRoute:
                    TickSimulatedExternalRoutePlan(player, phaseElapsed);
                    break;

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
                    {
                        if (!BeginExternalApproach(player, true))
                            BeginEnter(player, true);
                    }
                    break;

                case ExecutionPhase.ApproachingExternalSeat:
                    if (player.IsInVehicle())
                        CancelExecution(player, "entered_vehicle_during_approach", true);
                    else
                        TickExternalApproach(player, phaseElapsed);
                    break;

                case ExecutionPhase.Entering:
                case ExecutionPhase.Reentering:
                    if (_nativeContextEntryActive && !player.IsInVehicle()
                        && phaseElapsed <= NATIVE_CONTEXT_ENTRY_HOLD_MS)
                    {
                        // The Caracara turret has three authored climb points,
                        // but TASK_ENTER_VEHICLE redirects seat 3 into the cab.
                        // At the validated climb point, mirror the manual F hold
                        // that GTA's own context system resolves correctly.
                        Function.Call(Hash.ENABLE_CONTROL_ACTION,
                            0, CONTROL_ENTER, true);
                        Function.Call(Hash.SET_CONTROL_VALUE_NEXT_FRAME,
                            0, CONTROL_ENTER, 1f);
                    }
                    if (player.IsInVehicle() && player.CurrentVehicle != _targetVeh)
                        CancelExecution(player, "entered_different_vehicle", true);
                    else if (player.IsInVehicle()
                             && GetPlayerSeatIndex(player) != _targetSeatIdx)
                        HandleWrongSeatEntry(player);
                    else if (phaseElapsed > ENTER_TIMEOUT_MS)
                    {
                        if (_usesExternalRoute)
                            FailExternalRoute(player, "entry_timeout");
                        else
                            CancelExecution(player, "entry_timeout", true);
                    }
                    break;

                case ExecutionPhase.RecoveringWrongSeat:
                    if (!player.IsInVehicle())
                        FailExternalRoute(player, _pendingFailureReason);
                    else if (phaseElapsed > EXIT_TIMEOUT_MS)
                        CancelExecution(player, "wrong_seat_exit_timeout", true);
                    break;

                case ExecutionPhase.ReturningToSourceSeat:
                    if (player.IsInVehicle() && player.CurrentVehicle != _targetVeh)
                        CancelExecution(player, "rollback_entered_different_vehicle", true);
                    else if (player.IsInVehicle()
                             && GetPlayerSeatIndex(player) == _sourceSeatIdx)
                        CompleteSourceSeatRollback();
                    else if (phaseElapsed > ENTER_TIMEOUT_MS)
                        CancelExecution(player, "source_seat_rollback_timeout", true);
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
            _nativeContextEntryActive =
                ShouldUseNativeContextEntry(
                    _targetVeh.Model.Hash, _targetSeatIdx);
            SetExecutionPhase(
                reentry ? ExecutionPhase.Reentering : ExecutionPhase.Entering,
                _nativeContextEntryActive
                    ? (reentry
                        ? "native_context_turret_reentry"
                        : "native_context_turret_entry")
                    : (reentry ? "external_reentry" : "outside_entry"));

            if (_nativeContextEntryActive)
            {
                Function.Call(Hash.CLEAR_PED_TASKS, player.Handle);
                return;
            }

            // A positive native timeout silently enables WarpAfterTime inside
            // GTA's task implementation. Use -1 and enforce our own bounded
            // timeout in TickExecuting so this route can never teleport.
            int nativeSeat = GetNativeEntryRequestSeat(
                _targetVeh.Model.Hash, _targetSeatIdx, _usesExternalRoute);
            Function.Call(Hash.TASK_ENTER_VEHICLE,
                player.Handle, _targetVeh.Handle, NATIVE_ENTER_TIMEOUT,
                nativeSeat, 2f, NORMAL_ENTER_FLAG, 0);
        }

        private void PublishHarnessResult(
            Ped player, bool success, string outcome, string reason)
        {
            if (!_harnessOwned)
                return;

            int landedSeat = -2;
            if (player != null && player.Exists())
                landedSeat = GetPlayerSeatIndex(player);
            var result = new SeatSwitchTelemetry
            {
                Success = success,
                Outcome = outcome ?? "cancelled",
                Reason = reason ?? "unknown",
                ModelHash = _targetVeh != null && _targetVeh.Exists()
                    ? _targetVeh.Model.Hash : 0,
                SourceSeat = _sourceSeatIdx,
                TargetSeat = _targetSeatIdx,
                LandedSeat = landedSeat,
                ObservedWrongSeat = _observedWrongSeat,
                ElapsedMs = _executeStart > 0
                    ? Math.Max(0, Game.GameTime - _executeStart) : 0,
                FinalPhase = _executionPhase.ToString(),
                PhaseTrace = string.Join(" > ", _phaseTrace),
                UsedExternalRoute = _usesExternalRoute,
                RouteValidated = _externalRouteValidated,
                RouteResult = _externalRouteResult,
                RouteCandidate = _routePlanCandidateIndex,
                WaypointCount = _plannedExternalWaypoints.Count,
            };
            try
            {
                HarnessSwitchFinished?.Invoke(result);
            }
            catch (Exception ex)
            {
                ClientLog.Error("SeatSelector", "seat_lab_result_callback_failed", ex);
            }
        }

        private void TickExternalApproach(Ped player, int phaseElapsed)
        {
            float distance = player.Position.DistanceTo(_externalApproachPoint);
            int now = Game.GameTime;
            int routeResult = Function.Call<int>(
                Hash.GET_NAVMESH_ROUTE_RESULT, player.Handle);
            _externalRouteResult = routeResult;

            if (routeResult == NAV_ROUTE_FOUND)
                _externalRouteValidated = true;

            if (distance + EXTERNAL_ROUTE_PROGRESS_EPSILON
                < _externalRouteBestDistance)
            {
                _externalRouteBestDistance = distance;
                _externalRouteLastProgress = now;
            }

            if (distance <= EXTERNAL_APPROACH_DISTANCE
                && _externalRouteValidated)
            {
                if (_externalRouteWaypointIndex + 1
                    < _plannedExternalWaypoints.Count)
                {
                    _externalRouteWaypointIndex++;
                    StartExternalRouteStage(
                        player,
                        _plannedExternalWaypoints[
                            _externalRouteWaypointIndex],
                        _approachIsReentry);
                }
                else
                    BeginEnter(player, _approachIsReentry);
                return;
            }

            string abortReason = GetExternalRouteAbortReason(
                routeResult,
                phaseElapsed,
                now - _externalRouteLastProgress,
                distance);
            if (abortReason != null)
            {
                FailExternalRoute(player, abortReason);
                return;
            }

            if (phaseElapsed > EXTERNAL_APPROACH_TIMEOUT_MS)
                FailExternalRoute(player, "external_approach_timeout");
        }

        private void HandleWrongSeatEntry(Ped player)
        {
            _observedWrongSeat = GetPlayerSeatIndex(player);
            _pendingFailureReason = "entered_wrong_external_seat";
            if (GetPlayerSeatIndex(player) == _sourceSeatIdx)
                CompleteSourceSeatRollback();
            else
                BeginWrongSeatRecovery(player, _pendingFailureReason);
        }

        private void BeginWrongSeatRecovery(Ped player, string reason)
        {
            _pendingFailureReason = reason;
            SetExecutionPhase(
                ExecutionPhase.RecoveringWrongSeat,
                "wrong_external_seat_exit");
            Function.Call(Hash.TASK_LEAVE_VEHICLE,
                player.Handle, _targetVeh.Handle, NORMAL_EXIT_FLAG);
        }

        private void FailExternalRoute(Ped player, string reason)
        {
            if (BeginSourceSeatRollback(player, reason))
                return;

            CancelExecution(player, reason, true);
            GTA.UI.Screen.ShowSubtitle(
                "~y~No valid path to that external seat.", 2500);
        }

        private bool BeginSourceSeatRollback(Ped player, string reason)
        {
            if (_sourceSeatIdx == -2 || player == null || !player.Exists()
                || player.IsInVehicle() || _targetVeh == null
                || !_targetVeh.Exists())
                return false;

            Ped occupant = _targetVeh.GetPedOnSeat((VehicleSeat)_sourceSeatIdx);
            if (occupant != null && occupant.Exists() && occupant != player)
                return false;

            Function.Call(Hash.CLEAR_PED_TASKS, player.Handle);
            _pendingFailureReason = reason ?? "external_route_failed";
            _executeStart = Game.GameTime;
            SetExecutionPhase(
                ExecutionPhase.ReturningToSourceSeat,
                "restore_source_seat");
            Function.Call(Hash.TASK_ENTER_VEHICLE,
                player.Handle, _targetVeh.Handle, NATIVE_ENTER_TIMEOUT,
                _sourceSeatIdx, 2f, NORMAL_ENTER_FLAG, 0);
            GTA.UI.Screen.ShowSubtitle(
                "~y~External route failed; returning to the previous seat.",
                2500);
            return true;
        }

        private void CompleteSourceSeatRollback()
        {
            ClientLog.Info("SeatSelector", "seat_switch_rolled_back",
                new Dictionary<string, object>
                {
                    { "reason", _pendingFailureReason
                        ?? "external_route_failed" },
                    { "source_seat", _sourceSeatIdx },
                    { "target_seat", _targetSeatIdx },
                });
            GTA.UI.Screen.ShowSubtitle(
                "~y~External route failed; previous seat restored.", 2500);
            PublishHarnessResult(
                Game.Player.Character,
                false,
                "rolled_back",
                _pendingFailureReason ?? "external_route_failed");
            Reset();
        }

        private bool BeginSimulatedExternalRoutePlan(Ped player)
        {
            _plannedExternalWaypoints.Clear();
            _hasPreplannedExternalRoute = false;
            _routePlanCandidates.Clear();

            var dimensions = _targetVeh.Model.Dimensions;
            Vector3 minimum = dimensions.Item1;
            Vector3 maximum = dimensions.Item2;
            Vector3[] sourceOffsets = GetSeatAccessOffsets(
                _targetVeh.Model.Hash, _sourceSeatIdx, minimum, maximum);
            Vector3[] targetOffsets = GetSeatAccessOffsets(
                _targetVeh.Model.Hash, _targetSeatIdx, minimum, maximum);
            if (sourceOffsets.Length == 0 || targetOffsets.Length == 0)
                return false;

            Vector3 playerOffset = _targetVeh.GetPositionOffset(player.Position);
            var candidates = new List<Tuple<float, List<Vector3>>>();

            foreach (Vector3 source in sourceOffsets)
            {
                // Prefer the exit point nearest the occupied seat, while still
                // considering every authored option if obstacles block it.
                float sourceBias = playerOffset.DistanceTo(source) * 0.05f;
                foreach (Vector3 target in targetOffsets)
                {
                    foreach (Vector3[] localRoute
                             in BuildLocalExternalRouteCandidates(
                                 source, target, minimum, maximum))
                    {
                        var worldRoute = new List<Vector3>(localRoute.Length);
                        foreach (Vector3 point in localRoute)
                            worldRoute.Add(_targetVeh.GetOffsetPosition(point));
                        if (worldRoute.Count < 2)
                            continue;

                        float length = sourceBias;
                        for (int i = 1; i < worldRoute.Count; i++)
                            length += worldRoute[i - 1].DistanceTo(worldRoute[i]);
                        candidates.Add(Tuple.Create(length, worldRoute));
                    }
                }
            }

            if (candidates.Count == 0)
                return false;

            candidates.Sort((left, right) => left.Item1.CompareTo(right.Item1));
            foreach (var candidate in candidates)
                _routePlanCandidates.Add(candidate.Item2);

            _routePlanCandidateIndex = 0;
            _routePlanSegmentIndex = 1;
            SetExecutionPhase(
                ExecutionPhase.PlanningExternalRoute,
                "simulate_external_route");
            StartRoutePlanShapeTest();
            return true;
        }

        private void TickSimulatedExternalRoutePlan(
            Ped player, int phaseElapsed)
        {
            if (!player.IsInVehicle() || player.CurrentVehicle != _targetVeh
                || GetPlayerSeatIndex(player) != _sourceSeatIdx)
            {
                CancelExecution(player, "left_source_seat_during_plan", false);
                return;
            }

            if (phaseElapsed > EXTERNAL_APPROACH_TIMEOUT_MS)
            {
                CancelExecution(player, "preexit_route_plan_timeout", false);
                return;
            }

            var result = _routeShapeTest.GetResult();
            if (result.Item1 == ShapeTestStatus.NotReady)
                return;

            bool clear = result.Item1 == ShapeTestStatus.Ready
                && !result.Item2.DidHit;
            if (!clear)
            {
                AdvanceToNextRoutePlanCandidate(player);
                return;
            }

            List<Vector3> candidate =
                _routePlanCandidates[_routePlanCandidateIndex];
            _routePlanSegmentIndex++;
            if (_routePlanSegmentIndex < candidate.Count)
            {
                StartRoutePlanShapeTest();
                return;
            }

            _plannedExternalWaypoints.AddRange(candidate);
            _hasPreplannedExternalRoute = true;
            ClientLog.Info("SeatSelector", "preexit_route_planned",
                new Dictionary<string, object>
                {
                    { "from_seat", _sourceSeatIdx },
                    { "target_seat", _targetSeatIdx },
                    { "waypoints", candidate.Count },
                    { "candidate", _routePlanCandidateIndex },
                });
            BeginExit(player, "different_row_or_external_seat");
        }

        private void AdvanceToNextRoutePlanCandidate(Ped player)
        {
            _routePlanCandidateIndex++;
            _routePlanSegmentIndex = 1;
            if (_routePlanCandidateIndex >= _routePlanCandidates.Count)
            {
                GTA.UI.Screen.ShowSubtitle(
                    "~y~No clear walking route between those seats.", 3000);
                CancelExecution(player, "preexit_route_blocked", false);
                return;
            }
            StartRoutePlanShapeTest();
        }

        private void StartRoutePlanShapeTest()
        {
            List<Vector3> candidate =
                _routePlanCandidates[_routePlanCandidateIndex];
            Vector3 lift = new Vector3(
                0f, 0f, EXTERNAL_ROUTE_TRACE_HEIGHT);
            Vector3 start = candidate[_routePlanSegmentIndex - 1] + lift;
            Vector3 end = candidate[_routePlanSegmentIndex] + lift;
            const IntersectFlags traceFlags = IntersectFlags.Map
                | IntersectFlags.Vehicles | IntersectFlags.Objects;
            _routeShapeTest = ShapeTest.StartTestCapsule(
                start,
                end,
                EXTERNAL_ROUTE_TRACE_RADIUS,
                traceFlags,
                _targetVeh,
                ShapeTestOptions.Default);
        }

        internal static Vector3[] GetSeatAccessOffsets(
            int modelHash,
            int seatIndex,
            Vector3 minimum,
            Vector3 maximum)
        {
            Vector3[] authored = GetExternalApproachOffsets(
                modelHash, seatIndex);
            if (authored != null)
                return authored;

            float side = Math.Max(Math.Abs(minimum.X), Math.Abs(maximum.X))
                + EXTERNAL_ROUTE_CLEARANCE;
            bool left = seatIndex == -1
                || (seatIndex >= 1 && seatIndex % 2 == 1);
            bool front = seatIndex <= 0;
            float y = front ? maximum.Y * 0.35f : minimum.Y * 0.35f;
            return new[] { new Vector3(left ? -side : side, y, 0f) };
        }

        internal static Vector3[] BuildLocalExternalRoute(
            Vector3 source,
            Vector3 target,
            Vector3 minimum,
            Vector3 maximum)
        {
            Vector3[][] candidates = BuildLocalExternalRouteCandidates(
                source, target, minimum, maximum);
            return candidates[0];
        }

        internal static Vector3[][] BuildLocalExternalRouteCandidates(
            Vector3 source,
            Vector3 target,
            Vector3 minimum,
            Vector3 maximum)
        {
            float side = Math.Max(Math.Abs(minimum.X), Math.Abs(maximum.X))
                + EXTERNAL_ROUTE_CLEARANCE;
            float sourceSide = ResolveRouteSide(source.X, target.X);
            float targetSide = ResolveRouteSide(target.X, source.X);
            float z = Math.Max(source.Z, target.Z);

            if (sourceSide == targetSide)
            {
                return new[] { CompactRoute(new[]
                {
                    source,
                    new Vector3(sourceSide * side, source.Y, z),
                    new Vector3(targetSide * side, target.Y, z),
                    target,
                }) };
            }

            float frontY = maximum.Y + EXTERNAL_ROUTE_CLEARANCE;
            float rearY = minimum.Y - EXTERNAL_ROUTE_CLEARANCE;
            Vector3[] frontRoute = CompactRoute(new[]
            {
                source,
                new Vector3(sourceSide * side, frontY, z),
                new Vector3(targetSide * side, frontY, z),
                target,
            });
            Vector3[] rearRoute = CompactRoute(new[]
            {
                source,
                new Vector3(sourceSide * side, rearY, z),
                new Vector3(targetSide * side, rearY, z),
                target,
            });
            return RouteLength(frontRoute) <= RouteLength(rearRoute)
                ? new[] { frontRoute, rearRoute }
                : new[] { rearRoute, frontRoute };
        }

        private static float ResolveRouteSide(float primary, float fallback)
        {
            if (Math.Abs(primary) > 0.1f)
                return primary < 0f ? -1f : 1f;
            return fallback < 0f ? -1f : 1f;
        }

        private static Vector3[] CompactRoute(Vector3[] points)
        {
            var result = new List<Vector3>();
            foreach (Vector3 point in points)
            {
                if (result.Count == 0
                    || result[result.Count - 1].DistanceTo(point) >= 0.1f)
                    result.Add(point);
            }
            return result.ToArray();
        }

        private static float RouteLength(Vector3[] points)
        {
            float length = 0f;
            for (int i = 1; i < points.Length; i++)
                length += points[i - 1].DistanceTo(points[i]);
            return length;
        }

        private bool BeginExternalApproach(Ped player, bool reentry)
        {
            if (_hasPreplannedExternalRoute
                && _plannedExternalWaypoints.Count > 0)
            {
                _externalRouteWaypointIndex = 0;
                while (_externalRouteWaypointIndex + 1
                        < _plannedExternalWaypoints.Count
                       && player.Position.DistanceTo(
                           _plannedExternalWaypoints[
                               _externalRouteWaypointIndex])
                          <= EXTERNAL_APPROACH_DISTANCE)
                    _externalRouteWaypointIndex++;

                StartExternalRouteStage(
                    player,
                    _plannedExternalWaypoints[_externalRouteWaypointIndex],
                    reentry);
                return true;
            }

            Vector3[] offsets = GetExternalApproachOffsets(
                _targetVeh.Model.Hash, _targetSeatIdx);
            if (offsets == null || offsets.Length == 0)
                return false;

            Vector3 nearest = _targetVeh.GetOffsetPosition(offsets[0]);
            float nearestDistance = player.Position.DistanceTo(nearest);
            for (int i = 1; i < offsets.Length; i++)
            {
                Vector3 candidate = _targetVeh.GetOffsetPosition(offsets[i]);
                float distance = player.Position.DistanceTo(candidate);
                if (distance < nearestDistance)
                {
                    nearest = candidate;
                    nearestDistance = distance;
                }
            }

            _plannedExternalWaypoints.Clear();
            _plannedExternalWaypoints.Add(nearest);
            _externalRouteWaypointIndex = 0;
            StartExternalRouteStage(player, nearest, reentry);
            return true;
        }

        private void StartExternalRouteStage(
            Ped player, Vector3 target, bool reentry)
        {
            float distance = player.Position.DistanceTo(target);
            _externalApproachPoint = target;
            _approachIsReentry = reentry;
            _usesExternalRoute = true;
            _externalRouteValidated = distance <= EXTERNAL_APPROACH_DISTANCE;
            _externalRouteBestDistance = distance;
            _externalRouteLastProgress = Game.GameTime;
            _externalRouteResult = NAV_ROUTE_NOT_YET_TRIED;
            SetExecutionPhase(
                ExecutionPhase.ApproachingExternalSeat,
                reentry ? "external_reentry_approach" : "outside_entry_approach");
            Function.Call(Hash.TASK_FOLLOW_NAV_MESH_TO_COORD,
                player.Handle,
                target.X, target.Y, target.Z,
                1.25f, -1, 0.35f, false, 0f);
        }

        internal static Vector3[] GetExternalApproachOffsets(
            int modelHash, int seatIndex)
        {
            if (modelHash != CARACARA_HASH)
                return null;
            switch (seatIndex)
            {
                case 1: return CARACARA_REAR_LEFT_APPROACH_OFFSETS;
                case 2: return CARACARA_REAR_RIGHT_APPROACH_OFFSETS;
                case 3: return CARACARA_TURRET_APPROACH_OFFSETS;
                default: return null;
            }
        }

        internal static int GetNativeEntryRequestSeat(
            int modelHash, int seatIndex, bool usesExternalRoute)
        {
            // The predictor has already selected and validated the authored
            // access point. Preserve the requested station; asking for the
            // nearest passenger lets GTA redirect bed and turret stations to
            // the front cabin on custom layouts.
            return seatIndex;
        }

        internal static bool ShouldUseNativeContextEntry(
            int modelHash, int seatIndex)
        {
            return modelHash == CARACARA_HASH && seatIndex == 3;
        }

        internal static bool IsSeatSelectable(int modelHash, int seatIndex)
        {
            // LAYOUT_RANGER_CARACARA advertises two rear cabin indices, but
            // GTA exposes no usable outside entry for either station. Do not
            // offer transitions that can only be reached by a setup warp.
            return modelHash != CARACARA_HASH
                || (seatIndex != 1 && seatIndex != 2);
        }

        internal static string GetExternalRouteAbortReason(
            int routeResult,
            int routeElapsedMs,
            int noProgressMs,
            float distance)
        {
            if (distance <= EXTERNAL_APPROACH_DISTANCE)
                return null;
            if (routeResult == NAV_ROUTE_NOT_FOUND)
                return "external_route_not_found";
            if (routeElapsedMs > EXTERNAL_ROUTE_DISCOVERY_GRACE_MS
                && routeResult == NAV_ROUTE_TASK_NOT_FOUND)
                return "external_route_task_missing";
            if (noProgressMs > EXTERNAL_ROUTE_STALL_TIMEOUT_MS)
                return "external_route_stalled";
            return null;
        }

        private void SetExecutionPhase(ExecutionPhase phase, string route)
        {
            _executionPhase = phase;
            _phaseStart = Game.GameTime;
            _phaseTrace.Add($"{phase}:{route}");
            ClientLog.Info("SeatSelector", "seat_switch_phase",
                new Dictionary<string, object>
                {
                    { "phase", phase.ToString() },
                    { "route", route },
                    { "from_seat", _sourceSeatIdx },
                    { "target_seat", _targetSeatIdx },
                    { "model_hash", _targetVeh != null && _targetVeh.Exists()
                        ? _targetVeh.Model.Hash : 0 },
                    { "external_route", _usesExternalRoute },
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
                    { "route_result", _externalRouteResult },
                    { "route_validated", _externalRouteValidated },
                });
            if (reason.EndsWith("timeout", StringComparison.OrdinalIgnoreCase))
                GTA.UI.Screen.ShowSubtitle("~y~Seat switch timed out safely.", 2000);
            PublishHarnessResult(player, false, "cancelled", reason);
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
                if (!IsSeatSelectable(_targetVeh.Model.Hash, idx))
                    continue;
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

        internal static string GetSeatLabel(int modelHash, int seatIndex)
        {
            string catalogLabel = VehicleSeatLayoutCatalog.GetLabel(
                modelHash, seatIndex);
            if (!string.IsNullOrWhiteSpace(catalogLabel))
                return catalogLabel;

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
            _usesExternalRoute = false;
            _externalRouteValidated = false;
            _externalRouteBestDistance = 0f;
            _externalRouteLastProgress = 0;
            _externalRouteResult = NAV_ROUTE_TASK_NOT_FOUND;
            _pendingFailureReason = null;
            _observedWrongSeat = -2;
            _plannedExternalWaypoints.Clear();
            _externalRouteWaypointIndex = 0;
            _hasPreplannedExternalRoute = false;
            _routePlanCandidates.Clear();
            _phaseTrace.Clear();
            _routePlanCandidateIndex = 0;
            _routePlanSegmentIndex = 0;
            _routeShapeTest = default(ShapeTestHandle);
            _state = State.Idle;
            _holdStart = 0;
            _targetVeh = null;
            _seats.Clear();
            _selectedIdx = 0;
            _executeStart = 0;
            _phaseStart = 0;
            _targetSeatIdx = 0;
            _sourceSeatIdx = -2;
            _externalApproachPoint = Vector3.Zero;
            _approachIsReentry = false;
            _nativeContextEntryActive = false;
            _playerInVehicle = false;
            _executionPhase = ExecutionPhase.None;
            _harnessOwned = false;
        }

        private void LogError(string context, Exception ex)
        {
            ClientLog.Error("SeatSelector", context, ex);
        }
    }
}
