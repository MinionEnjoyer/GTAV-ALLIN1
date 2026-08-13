// SeatTestTool.cs -- Controlled, repeatable vehicle seat-switch laboratory.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class SeatTestTool : Script
    {
        private const Keys TOGGLE_KEY = Keys.F11;
        private const int SETUP_SETTLE_MS = 900;
        private const int VEHICLE_PHYSICS_SETTLE_MS = 2500;
        private const int TRIAL_COOLDOWN_MS = 750;
        private const int HARNESS_TIMEOUT_MS = 36000;
        private const int SLOW_SUCCESS_MS = 12000;
        private const float LAB_HEADING = 105f;
        private const float WATER_LAB_HEADING = 52.71f;
        private const float LAB_CLEAR_RADIUS = 80f;

        // Sandy Shores airfield gives the pathfinder a large, flat surface and
        // avoids mission interiors, city traffic, and restrictive compounds.
        private static readonly Vector3 LAB_POSITION =
            new Vector3(1746.83f, 3272.71f, 41.13f);

        // Del Perro's open water keeps the weaponized Dinghy afloat while
        // retaining enough clearance for native exterior boarding routes.
        private static readonly Vector3 WATER_LAB_POSITION =
            new Vector3(-1597.6020f, -1311.9710f, 0.9543f);

        private enum LabArena
        {
            Ground,
            Water,
        }

        private sealed class FleetVehicleSpec
        {
            internal string SpawnName;
            internal string DisplayName;
            internal string StationType;
            internal LabArena Arena;
        }

        // Deliberately limited to physical seats and gunner stations. Vehicles
        // whose weapons are controlled remotely by the driver do not belong in
        // a seat-routing test and would create misleading failures.
        private static readonly FleetVehicleSpec[] UNCONVENTIONAL_FLEET =
        {
            Fleet("limo2", "Benefactor Turreted Limo", "roof turret"),
            Fleet("caracara", "Vapid Caracara", "bed turret"),
            Fleet("technical", "Karin Technical", "bed turret"),
            Fleet("technical3", "Karin Technical Custom", "bed turret"),
            Fleet("insurgent", "HVY Insurgent Pick-Up", "roof turret"),
            Fleet("insurgent3", "HVY Insurgent Pick-Up Custom", "roof turret"),
            Fleet("halftrack", "Bravado Half-track", "rear turret"),
            Fleet("barrage", "HVY Barrage", "top and rear turrets"),
            Fleet("menacer", "HVY Menacer", "roof turret"),
            Fleet("apc", "HVY APC", "turret operator"),
            Fleet("chernobog", "Chernobog", "missile operator"),
            Fleet("khanjali", "TM-02 Khanjali", "gunner stations"),
            Fleet("dune3", "BF Dune FAV", "passenger gunner"),
            Fleet("boxville4", "Brute Armored Boxville", "auxiliary interior seats"),
            Fleet("vetir", "Vetir", "unconventional troop seats"),
            Fleet("wastelander", "MTL Wastelander", "exposed passenger seats"),
            Fleet("guardian", "Vapid Guardian", "exposed passenger seats"),
            Fleet("valkyrie", "Buckingham Valkyrie", "side gunners"),
            Fleet("savage", "Savage", "unconventional helicopter passengers"),
            Fleet("hunter", "FH-1 Hunter", "front turret"),
            Fleet("annihilator2", "Western Annihilator Stealth", "rappel seats"),
            Fleet("bombushka", "RM-10 Bombushka", "gunner stations"),
            Fleet("mogul", "Mammoth Mogul", "rear turret"),
            Fleet("tula", "Mammoth Tula", "gunner stations"),
            Fleet("volatol", "Volatol", "gunner stations"),
            Fleet("dinghy5", "Nagasaki Weaponized Dinghy", "bow gunner",
                LabArena.Water),
        };

        internal static bool IsActive { get; private set; }

        private enum LabState
        {
            Idle,
            SettlingVehicle,
            SettingSource,
            WaitingForSetup,
            RunningTrial,
            CoolingDown,
            PreparingFleetVehicle,
        }

        private sealed class TrialSpec
        {
            internal int SourceSeat;
            internal int TargetSeat;
        }

        public sealed class TrialResult
        {
            public int Number { get; set; }
            public int SourceSeat { get; set; }
            public string SourceLabel { get; set; }
            public int TargetSeat { get; set; }
            public string TargetLabel { get; set; }
            public bool Success { get; set; }
            public string Outcome { get; set; }
            public string Reason { get; set; }
            public string Classification { get; set; }
            public int LandedSeat { get; set; }
            public int ObservedWrongSeat { get; set; }
            public int ElapsedMs { get; set; }
            public string FinalPhase { get; set; }
            public string PhaseTrace { get; set; }
            public bool UsedExternalRoute { get; set; }
            public bool RouteValidated { get; set; }
            public int RouteResult { get; set; }
            public int RouteCandidate { get; set; }
            public int WaypointCount { get; set; }
        }

        public sealed class RunReport
        {
            public int SchemaVersion { get; set; } = 1;
            public string StartedUtc { get; set; }
            public string FinishedUtc { get; set; }
            public string VehicleName { get; set; }
            public int ModelHash { get; set; }
            // SeatCount is retained for report compatibility and means seats
            // exposed by ALLIN1. NativeSeatCount is GTA's runtime declaration.
            public int SeatCount { get; set; }
            public int NativeSeatCount { get; set; }
            public int MetadataSeatCount { get; set; }
            public int OccupantAccessDoorCount { get; set; }
            public int AccessHatchCount { get; set; }
            public string RockstarLayout { get; set; }
            public bool RuntimeMetadataSeatMismatch { get; set; }
            public int TrialCount { get; set; }
            public int Passed { get; set; }
            public int Outliers { get; set; }
            public string SpawnName { get; set; }
            public string StationType { get; set; }
            public string Arena { get; set; }
            public string TestLocation { get; set; }
            public List<TrialResult> Trials { get; set; } =
                new List<TrialResult>();
        }

        public sealed class FleetVehicleSummary
        {
            public string SpawnName { get; set; }
            public string VehicleName { get; set; }
            public string StationType { get; set; }
            public string Arena { get; set; }
            public string Status { get; set; }
            public string Reason { get; set; }
            public int ModelHash { get; set; }
            public int SeatCount { get; set; }
            public int TrialCount { get; set; }
            public int Passed { get; set; }
            public int Outliers { get; set; }
            public string Report { get; set; }
        }

        public sealed class FleetRunReport
        {
            public int SchemaVersion { get; set; } = 1;
            public string Scope { get; set; } =
                "Physical turret, gunner, and unconventional passenger seats";
            public string StartedUtc { get; set; }
            public string FinishedUtc { get; set; }
            public string Status { get; set; }
            public int VehicleCount { get; set; }
            public int Completed { get; set; }
            public int Skipped { get; set; }
            public int TrialCount { get; set; }
            public int Passed { get; set; }
            public int Outliers { get; set; }
            public List<FleetVehicleSummary> Vehicles { get; set; } =
                new List<FleetVehicleSummary>();
        }

        private LabState _state;
        private int _stateStarted;
        private int _trialStarted;
        private Vehicle _testVehicle;
        private Vehicle _savedVehicle;
        private int _savedVehicleSeat = -2;
        private Vector3 _savedPlayerPosition;
        private float _savedPlayerHeading;
        private bool _savedPlayerInvincible;
        private readonly List<int> _seats = new List<int>();
        private readonly List<TrialSpec> _trials = new List<TrialSpec>();
        private int _nativeSeatCount;
        private int _trialIndex;
        private SeatSwitchTelemetry _pendingTelemetry;
        private RunReport _report;
        private string _outputDirectory;
        private string _rollingPath;
        private string _outlierPath;
        private bool _fleetMode;
        private int _fleetIndex;
        private FleetVehicleSpec _fleetSpec;
        private FleetRunReport _fleetReport;
        private string _fleetReportPath;
        private Vector3 _activeLabPosition = LAB_POSITION;
        private float _activeLabHeading = LAB_HEADING;

        public SeatTestTool()
        {
            KeyDown += OnKeyDown;
            Tick += OnTick;
            Aborted += OnAborted;
            SeatSelector.HarnessSwitchFinished += OnHarnessSwitchFinished;
            Interval = 0;
        }

        private void OnAborted(object sender, EventArgs e)
        {
            SeatSelector.HarnessSwitchFinished -= OnHarnessSwitchFinished;
            if (IsActive)
                StopLab(false, "script_reloaded");
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode != TOGGLE_KEY)
                return;

            if (IsActive)
                StopLab(false, "aborted_by_user");
            else if (e.Shift)
                StartFleetLab();
            else
                StartLab();
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!IsActive)
                return;

            try
            {
                SuppressWorldInterference();
                DrawStatus();

                Ped player = Game.Player.Character;
                if (player == null || !player.Exists() || player.IsDead)
                {
                    StopLab(false, "player_unavailable");
                    return;
                }
                if (_state == LabState.PreparingFleetVehicle)
                {
                    PrepareNextFleetVehicle();
                    return;
                }
                if (_testVehicle == null || !_testVehicle.Exists())
                {
                    StopLab(false, "test_vehicle_lost");
                    return;
                }

                _testVehicle.IsInvincible = true;
                _testVehicle.IsPositionFrozen = false;
                _testVehicle.IsCollisionEnabled = true;
                Function.Call(Hash.SET_VEHICLE_HANDBRAKE,
                    _testVehicle.Handle, true);
                Game.Player.WantedLevel = 0;

                switch (_state)
                {
                    case LabState.SettlingVehicle:
                        if (Game.GameTime - _stateStarted
                            >= VEHICLE_PHYSICS_SETTLE_MS)
                        {
                            _state = LabState.SettingSource;
                            _stateStarted = Game.GameTime;
                        }
                        break;
                    case LabState.SettingSource:
                        PrepareTrialSource(player);
                        break;
                    case LabState.WaitingForSetup:
                        TickWaitingForSetup(player);
                        break;
                    case LabState.RunningTrial:
                        TickRunningTrial();
                        break;
                    case LabState.CoolingDown:
                        if (Game.GameTime - _stateStarted >= TRIAL_COOLDOWN_MS)
                            AdvanceTrial();
                        break;
                    case LabState.PreparingFleetVehicle:
                        break;
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("SeatLab", "tick_failed", ex);
                StopLab(false, "seat_lab_exception");
            }
        }

        private void StartLab()
        {
            Ped player;
            if (!CanStartLab(out player))
                return;
            Vehicle source = player != null && player.IsInVehicle()
                ? player.CurrentVehicle : FindNearbyVehicle(player, 12f);
            if (source == null || !source.Exists())
            {
                GbayRenderer.PlayError();
                GTA.UI.Notification.Show(
                    "~y~Seat Lab:~w~ enter or stand near the vehicle model to test.");
                return;
            }

            CaptureSession(player);
            InitializeOutputDirectory();
            _fleetMode = false;
            _fleetSpec = null;
            _fleetReport = null;
            IsActive = true;

            int modelHash = source.Model.Hash;
            string vehicleName = source.LocalizedName;
            if (string.IsNullOrWhiteSpace(vehicleName))
                vehicleName = $"Model {modelHash}";
            string failure;
            if (!TryBeginVehicleRun(
                    modelHash, null, vehicleName, "focused vehicle",
                    IsBoatModel(modelHash) ? LabArena.Water : LabArena.Ground,
                    out failure))
            {
                StopLab(false, failure);
                return;
            }

            GbayRenderer.PlaySelect();
            GTA.UI.Notification.Show(
                $"~g~Seat Lab started~w~: {vehicleName}, {_trials.Count} trials. F11 aborts.");
        }

        private void StartFleetLab()
        {
            Ped player;
            if (!CanStartLab(out player))
                return;

            CaptureSession(player);
            InitializeOutputDirectory();
            _fleetMode = true;
            _fleetIndex = 0;
            _fleetSpec = null;
            _report = null;
            _fleetReport = new FleetRunReport
            {
                StartedUtc = DateTime.UtcNow.ToString("O"),
                Status = "running",
                VehicleCount = UNCONVENTIONAL_FLEET.Length,
            };
            string stamp = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
            _fleetReportPath = Path.Combine(
                _outputDirectory, $"fleet-{stamp}.json");
            IsActive = true;
            _state = LabState.PreparingFleetVehicle;
            _stateStarted = Game.GameTime;
            GbayRenderer.PlaySelect();
            GTA.UI.Notification.Show(
                $"~g~Seat Lab fleet started~w~: {UNCONVENTIONAL_FLEET.Length} "
                + "physical gunner/unconventional-seat vehicles. F11 aborts.");
            ClientLog.Info("SeatLab", "fleet_started",
                new Dictionary<string, object>
                {
                    { "vehicles", UNCONVENTIONAL_FLEET.Length },
                    { "report", _fleetReportPath },
                });
        }

        private bool CanStartLab(out Ped player)
        {
            player = Game.Player.Character;
            if (Game.IsLoading
                || Function.Call<bool>(Hash.IS_CUTSCENE_ACTIVE)
                || Function.Call<bool>(Hash.GET_MISSION_FLAG))
            {
                GbayRenderer.PlayError();
                GTA.UI.Notification.Show(
                    "~y~Seat Lab is unavailable during loading, missions, or cutscenes.");
                return false;
            }
            if (SeatSelector.ActiveInstance == null)
            {
                GbayRenderer.PlayError();
                GTA.UI.Notification.Show("~r~Seat Lab:~w~ seat selector is not loaded.");
                return false;
            }
            if (player == null || !player.Exists() || player.IsDead)
            {
                GbayRenderer.PlayError();
                GTA.UI.Notification.Show("~r~Seat Lab:~w~ player is unavailable.");
                return false;
            }
            return true;
        }

        private void CaptureSession(Ped player)
        {
            _savedPlayerPosition = player.Position;
            _savedPlayerHeading = player.Heading;
            _savedPlayerInvincible = player.IsInvincible;
            _savedVehicle = player.IsInVehicle() ? player.CurrentVehicle : null;
            _savedVehicleSeat = GetSeatIndex(player, _savedVehicle);
        }

        private void InitializeOutputDirectory()
        {
            _outputDirectory = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_seat_tests");
            Directory.CreateDirectory(_outputDirectory);
            _outlierPath = Path.Combine(
                _outputDirectory, "ALLIN1_seat_outliers.jsonl");
        }

        private void PrepareNextFleetVehicle()
        {
            DeleteTestVehicle();
            while (_fleetIndex < UNCONVENTIONAL_FLEET.Length)
            {
                _fleetSpec = UNCONVENTIONAL_FLEET[_fleetIndex];
                int modelHash = Game.GenerateHash(_fleetSpec.SpawnName);
                string failure;
                if (TryBeginVehicleRun(
                        modelHash,
                        _fleetSpec.SpawnName,
                        _fleetSpec.DisplayName,
                        _fleetSpec.StationType,
                        _fleetSpec.Arena,
                        out failure))
                {
                    GTA.UI.Notification.Show(
                        $"~g~Seat Lab~w~ {_fleetIndex + 1}/{UNCONVENTIONAL_FLEET.Length}: "
                        + $"{_fleetSpec.DisplayName}, {_trials.Count} trials.");
                    return;
                }

                AddSkippedFleetVehicle(_fleetSpec, modelHash, failure);
                _fleetIndex++;
            }
            FinishFleetRun();
        }

        private bool TryBeginVehicleRun(
            int modelHash,
            string spawnName,
            string vehicleName,
            string stationType,
            LabArena arena,
            out string failure)
        {
            failure = null;
            _activeLabPosition = arena == LabArena.Water
                ? WATER_LAB_POSITION : LAB_POSITION;
            _activeLabHeading = arena == LabArena.Water
                ? WATER_LAB_HEADING : LAB_HEADING;

            ClearLabArea(_activeLabPosition);
            var model = new Model(modelHash);
            model.Request(5000);
            if (!model.IsLoaded)
            {
                model.MarkAsNoLongerNeeded();
                failure = "model_failed_to_load";
                return false;
            }

            _testVehicle = World.CreateVehicle(
                model, _activeLabPosition, _activeLabHeading);
            model.MarkAsNoLongerNeeded();
            if (_testVehicle == null || !_testVehicle.Exists())
            {
                failure = "vehicle_create_failed";
                return false;
            }

            _testVehicle.IsPersistent = true;
            _testVehicle.IsInvincible = true;
            if (arena == LabArena.Ground)
                _testVehicle.PlaceOnGround();
            _testVehicle.IsPositionFrozen = false;
            _testVehicle.IsCollisionEnabled = true;
            Function.Call(Hash.SET_ENTITY_DYNAMIC,
                _testVehicle.Handle, true);
            Function.Call(Hash.ACTIVATE_PHYSICS, _testVehicle.Handle);
            Function.Call(Hash.SET_VEHICLE_ENGINE_ON,
                _testVehicle.Handle, false, true, true);
            Function.Call(Hash.SET_VEHICLE_HANDBRAKE, _testVehicle.Handle, true);
            Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, _testVehicle.Handle, 0f);

            Ped player = Game.Player.Character;
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player.Handle);
            player.Position = _testVehicle.GetOffsetPosition(
                new Vector3(-3f, -3f, 0.2f));
            player.Heading = _activeLabHeading;
            player.IsInvincible = true;
            Game.Player.WantedLevel = 0;

            BuildTrialMatrix(modelHash);
            if (_seats.Count == 0 || _trials.Count == 0)
            {
                DeleteTestVehicle();
                failure = "vehicle_has_no_testable_seats";
                return false;
            }

            string stamp = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
            _rollingPath = Path.Combine(
                _outputDirectory, $"{stamp}-{modelHash}.jsonl");
            VehicleSeatLayoutRecord metadata =
                VehicleSeatLayoutCatalog.Get(modelHash);
            _report = new RunReport
            {
                StartedUtc = DateTime.UtcNow.ToString("O"),
                VehicleName = vehicleName,
                ModelHash = modelHash,
                SpawnName = spawnName,
                StationType = stationType,
                Arena = arena.ToString().ToLowerInvariant(),
                SeatCount = _seats.Count,
                NativeSeatCount = _nativeSeatCount,
                MetadataSeatCount = metadata?.SeatCount ?? 0,
                OccupantAccessDoorCount = metadata?.DoorCount ?? 0,
                AccessHatchCount = metadata?.HatchCount ?? 0,
                RockstarLayout = metadata?.Layout,
                RuntimeMetadataSeatMismatch = metadata != null
                    && metadata.SeatCount != _nativeSeatCount,
                TrialCount = _trials.Count,
                TestLocation =
                    $"{_activeLabPosition.X:F2},{_activeLabPosition.Y:F2},"
                    + $"{_activeLabPosition.Z:F2}",
            };

            _trialIndex = 0;
            _pendingTelemetry = null;
            _state = LabState.SettlingVehicle;
            _stateStarted = Game.GameTime;
            ClientLog.Info("SeatLab", "run_started",
                new Dictionary<string, object>
                {
                    { "vehicle", vehicleName },
                    { "model_hash", modelHash },
                    { "seats", _seats.Count },
                    { "native_seats", _nativeSeatCount },
                    { "metadata_seats", metadata?.SeatCount ?? 0 },
                    { "metadata_mismatch", metadata != null
                        && metadata.SeatCount != _nativeSeatCount },
                    { "trials", _trials.Count },
                    { "fleet_mode", _fleetMode },
                });
            return true;
        }

        private void BuildTrialMatrix(int modelHash)
        {
            _seats.Clear();
            _trials.Clear();
            int maxPassengers = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS,
                _testVehicle.Handle);
            _nativeSeatCount = Math.Max(1, maxPassengers + 1);
            for (int seat = -1; seat < maxPassengers; seat++)
            {
                if (SeatSelector.IsSeatSelectable(modelHash, seat))
                    _seats.Add(seat);
            }

            // First prove each station is directly accessible from outside.
            foreach (int target in _seats)
                _trials.Add(new TrialSpec { SourceSeat = -2, TargetSeat = target });

            // Then exercise the full directed seat-to-seat matrix. Direction
            // matters because exits and climb points are not symmetric.
            foreach (int source in _seats)
            {
                foreach (int target in _seats)
                {
                    if (source == target)
                        continue;
                    _trials.Add(new TrialSpec
                    {
                        SourceSeat = source,
                        TargetSeat = target,
                    });
                }
            }
        }

        private void PrepareTrialSource(Ped player)
        {
            TrialSpec trial = _trials[_trialIndex];
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player.Handle);

            if (trial.SourceSeat == -2)
            {
                if (player.IsInVehicle())
                {
                    Function.Call(Hash.TASK_LEAVE_VEHICLE,
                        player.Handle, player.CurrentVehicle.Handle, 16);
                }
                var dimensions = _testVehicle.Model.Dimensions;
                Vector3[] offsets = SeatSelector.GetSeatAccessOffsets(
                    _testVehicle.Model.Hash,
                    trial.TargetSeat,
                    dimensions.Item1,
                    dimensions.Item2);
                Vector3 local = offsets.Length > 0
                    ? offsets[0] : new Vector3(-2f, 0f, 0f);
                local.X += local.X < 0f ? -0.35f : 0.35f;
                Vector3 start = _testVehicle.GetOffsetPosition(local);
                Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET,
                    player.Handle,
                    start.X, start.Y, start.Z,
                    false, false, false);
                player.Heading = HeadingTowards(
                    player.Position, _testVehicle.Position);
            }
            else
            {
                Function.Call(Hash.SET_PED_INTO_VEHICLE,
                    player.Handle, _testVehicle.Handle, trial.SourceSeat);
            }

            _pendingTelemetry = null;
            _state = LabState.WaitingForSetup;
            _stateStarted = Game.GameTime;
        }

        private void TickWaitingForSetup(Ped player)
        {
            if (Game.GameTime - _stateStarted < SETUP_SETTLE_MS)
                return;

            TrialSpec trial = _trials[_trialIndex];
            int actualSource = GetSeatIndex(player, _testVehicle);
            if (actualSource != trial.SourceSeat)
            {
                RecordResult(NewHarnessFailure(
                    trial,
                    "setup_failed",
                    $"source_setup_landed_{actualSource}",
                    actualSource));
                BeginCooldown();
                return;
            }

            string rejection;
            _trialStarted = Game.GameTime;
            if (!SeatSelector.ActiveInstance.TryBeginHarnessSwitch(
                    _testVehicle, trial.TargetSeat, out rejection))
            {
                RecordResult(NewHarnessFailure(
                    trial,
                    "selector_rejected",
                    rejection ?? "selector_rejected",
                    actualSource));
                BeginCooldown();
                return;
            }

            _state = LabState.RunningTrial;
            _stateStarted = Game.GameTime;
        }

        private void TickRunningTrial()
        {
            if (_pendingTelemetry != null)
            {
                RecordResult(FromTelemetry(_pendingTelemetry));
                _pendingTelemetry = null;
                BeginCooldown();
                return;
            }

            if (Game.GameTime - _trialStarted <= HARNESS_TIMEOUT_MS)
                return;

            SeatSelector.ActiveInstance?.AbortHarnessSwitch("seat_lab_timeout");
            if (_pendingTelemetry == null)
            {
                TrialSpec trial = _trials[_trialIndex];
                RecordResult(NewHarnessFailure(
                    trial,
                    "harness_timeout",
                    "seat_lab_timeout_without_result",
                    GetSeatIndex(Game.Player.Character, _testVehicle)));
                BeginCooldown();
            }
        }

        private void BeginCooldown()
        {
            _state = LabState.CoolingDown;
            _stateStarted = Game.GameTime;
        }

        private void AdvanceTrial()
        {
            _trialIndex++;
            if (_trialIndex >= _trials.Count)
            {
                FinishRun();
                return;
            }
            _state = LabState.SettingSource;
            _stateStarted = Game.GameTime;
        }

        private void OnHarnessSwitchFinished(SeatSwitchTelemetry telemetry)
        {
            if (IsActive && _state == LabState.RunningTrial)
                _pendingTelemetry = telemetry;
        }

        private TrialResult FromTelemetry(SeatSwitchTelemetry telemetry)
        {
            TrialSpec trial = _trials[_trialIndex];
            return new TrialResult
            {
                Number = _trialIndex + 1,
                SourceSeat = trial.SourceSeat,
                SourceLabel = GetSeatLabel(_report.ModelHash, trial.SourceSeat),
                TargetSeat = trial.TargetSeat,
                TargetLabel = GetSeatLabel(_report.ModelHash, trial.TargetSeat),
                Success = telemetry.Success,
                Outcome = telemetry.Outcome,
                Reason = telemetry.Reason,
                Classification = ClassifyTrial(
                    telemetry.Success,
                    telemetry.Outcome,
                    telemetry.Reason,
                    telemetry.ElapsedMs),
                LandedSeat = telemetry.LandedSeat,
                ObservedWrongSeat = telemetry.ObservedWrongSeat,
                ElapsedMs = telemetry.ElapsedMs,
                FinalPhase = telemetry.FinalPhase,
                PhaseTrace = telemetry.PhaseTrace,
                UsedExternalRoute = telemetry.UsedExternalRoute,
                RouteValidated = telemetry.RouteValidated,
                RouteResult = telemetry.RouteResult,
                RouteCandidate = telemetry.RouteCandidate,
                WaypointCount = telemetry.WaypointCount,
            };
        }

        private TrialResult NewHarnessFailure(
            TrialSpec trial, string classification, string reason, int landedSeat)
        {
            return new TrialResult
            {
                Number = _trialIndex + 1,
                SourceSeat = trial.SourceSeat,
                SourceLabel = GetSeatLabel(_report.ModelHash, trial.SourceSeat),
                TargetSeat = trial.TargetSeat,
                TargetLabel = GetSeatLabel(_report.ModelHash, trial.TargetSeat),
                Success = false,
                Outcome = "harness_failure",
                Reason = reason,
                Classification = classification,
                LandedSeat = landedSeat,
                ObservedWrongSeat = -2,
                ElapsedMs = Math.Max(0, Game.GameTime - _stateStarted),
                FinalPhase = "Harness",
                PhaseTrace = "",
            };
        }

        private void RecordResult(TrialResult result)
        {
            _report.Trials.Add(result);
            if (result.Classification == "pass")
                _report.Passed++;
            else
                _report.Outliers++;

            var serializer = new JavaScriptSerializer();
            string json = serializer.Serialize(result);
            File.AppendAllText(_rollingPath, json + Environment.NewLine);
            if (result.Classification != "pass")
            {
                var envelope = new Dictionary<string, object>
                {
                    { "recorded_utc", DateTime.UtcNow.ToString("O") },
                    { "vehicle", _report.VehicleName },
                    { "model_hash", _report.ModelHash },
                    { "trial", result },
                };
                File.AppendAllText(
                    _outlierPath,
                    serializer.Serialize(envelope) + Environment.NewLine);
            }
        }

        private void FinishRun()
        {
            _report.FinishedUtc = DateTime.UtcNow.ToString("O");
            var serializer = new JavaScriptSerializer
            {
                MaxJsonLength = int.MaxValue,
            };
            string safeName = SanitizeFileName(_report.VehicleName);
            string reportPath = Path.Combine(
                _outputDirectory,
                $"latest-{safeName}-{_report.ModelHash}.json");
            File.WriteAllText(reportPath, serializer.Serialize(_report));

            var catalogEntry = new Dictionary<string, object>
            {
                { "finished_utc", _report.FinishedUtc },
                { "vehicle", _report.VehicleName },
                { "model_hash", _report.ModelHash },
                { "seat_count", _report.SeatCount },
                { "trial_count", _report.TrialCount },
                { "passed", _report.Passed },
                { "outliers", _report.Outliers },
                { "report", Path.GetFileName(reportPath) },
            };
            File.AppendAllText(
                Path.Combine(_outputDirectory, "ALLIN1_seat_catalog.jsonl"),
                serializer.Serialize(catalogEntry) + Environment.NewLine);

            ClientLog.Info("SeatLab", "run_completed",
                new Dictionary<string, object>
                {
                    { "model_hash", _report.ModelHash },
                    { "passed", _report.Passed },
                    { "outliers", _report.Outliers },
                    { "report", reportPath },
                });
            if (_fleetMode)
            {
                _fleetReport.Completed++;
                _fleetReport.TrialCount += _report.TrialCount;
                _fleetReport.Passed += _report.Passed;
                _fleetReport.Outliers += _report.Outliers;
                _fleetReport.Vehicles.Add(new FleetVehicleSummary
                {
                    SpawnName = _fleetSpec.SpawnName,
                    VehicleName = _report.VehicleName,
                    StationType = _report.StationType,
                    Arena = _report.Arena,
                    Status = "completed",
                    ModelHash = _report.ModelHash,
                    SeatCount = _report.SeatCount,
                    TrialCount = _report.TrialCount,
                    Passed = _report.Passed,
                    Outliers = _report.Outliers,
                    Report = Path.GetFileName(reportPath),
                });
                WriteFleetReport("running");
                _fleetIndex++;
                _state = LabState.PreparingFleetVehicle;
                _stateStarted = Game.GameTime;
                return;
            }

            GTA.UI.Notification.Show(
                $"~g~Seat Lab complete~w~: {_report.Passed}/{_report.TrialCount} passed, "
                + $"~y~{_report.Outliers} outliers~w~. Report saved.");
            StopLab(true, "completed");
        }

        private void AddSkippedFleetVehicle(
            FleetVehicleSpec spec, int modelHash, string reason)
        {
            _fleetReport.Skipped++;
            _fleetReport.Vehicles.Add(new FleetVehicleSummary
            {
                SpawnName = spec.SpawnName,
                VehicleName = spec.DisplayName,
                StationType = spec.StationType,
                Arena = spec.Arena.ToString().ToLowerInvariant(),
                Status = "skipped",
                Reason = reason,
                ModelHash = modelHash,
            });
            ClientLog.Warn("SeatLab",
                $"fleet_vehicle_skipped model={spec.SpawnName} reason={reason}");
            WriteFleetReport("running");
        }

        private void FinishFleetRun()
        {
            WriteFleetReport("completed");
            ClientLog.Info("SeatLab", "fleet_completed",
                new Dictionary<string, object>
                {
                    { "completed", _fleetReport.Completed },
                    { "skipped", _fleetReport.Skipped },
                    { "trials", _fleetReport.TrialCount },
                    { "passed", _fleetReport.Passed },
                    { "outliers", _fleetReport.Outliers },
                    { "report", _fleetReportPath },
                });
            GTA.UI.Notification.Show(
                $"~g~Seat Lab fleet complete~w~: {_fleetReport.Completed} tested, "
                + $"{_fleetReport.Skipped} skipped, {_fleetReport.Passed}/"
                + $"{_fleetReport.TrialCount} transitions passed. Report saved.");
            StopLab(true, "fleet_completed");
        }

        private void WriteFleetReport(string status)
        {
            if (_fleetReport == null || string.IsNullOrWhiteSpace(_fleetReportPath))
                return;
            _fleetReport.Status = status;
            _fleetReport.FinishedUtc = status == "running"
                ? null : DateTime.UtcNow.ToString("O");
            var serializer = new JavaScriptSerializer
            {
                MaxJsonLength = int.MaxValue,
            };
            string json = serializer.Serialize(_fleetReport);
            File.WriteAllText(_fleetReportPath, json);
            File.WriteAllText(
                Path.Combine(_outputDirectory,
                    "latest-unconventional-seat-fleet.json"),
                json);
        }

        private void StopLab(bool completed, string reason)
        {
            if (!IsActive && _testVehicle == null)
                return;

            try
            {
                if (_fleetMode && !completed && _fleetReport != null)
                {
                    CheckpointAbortedFleetVehicle(reason);
                    WriteFleetReport("aborted");
                }
                SeatSelector.ActiveInstance?.AbortHarnessSwitch(reason);
                Ped player = Game.Player.Character;
                if (player != null && player.Exists())
                {
                    Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player.Handle);
                    player.IsInvincible = _savedPlayerInvincible;
                    if (_savedVehicle != null && _savedVehicle.Exists()
                        && _savedVehicleSeat >= -1)
                    {
                        Function.Call(Hash.SET_PED_INTO_VEHICLE,
                            player.Handle, _savedVehicle.Handle, _savedVehicleSeat);
                    }
                    else
                    {
                        player.Position = _savedPlayerPosition;
                        player.Heading = _savedPlayerHeading;
                    }
                }
                DeleteTestVehicle();
            }
            catch (Exception ex)
            {
                ClientLog.Error("SeatLab", "restore_failed", ex);
            }
            finally
            {
                IsActive = false;
                _state = LabState.Idle;
                _testVehicle = null;
                _savedVehicle = null;
                _pendingTelemetry = null;
                _fleetMode = false;
                _fleetSpec = null;
                _fleetReport = null;
                _fleetReportPath = null;
                _report = null;
                _seats.Clear();
                _trials.Clear();
            }

            if (!completed)
            {
                ClientLog.Warn("SeatLab", $"run_stopped reason={reason}");
                GTA.UI.Notification.Show(
                    $"~y~Seat Lab stopped~w~: {reason}. Partial JSONL retained.");
            }
        }

        private void CheckpointAbortedFleetVehicle(string reason)
        {
            if (_state == LabState.PreparingFleetVehicle
                || _fleetSpec == null || _report == null)
                return;
            int measured = _report.Trials.Count;
            _fleetReport.TrialCount += measured;
            _fleetReport.Passed += _report.Passed;
            _fleetReport.Outliers += _report.Outliers;
            _fleetReport.Vehicles.Add(new FleetVehicleSummary
            {
                SpawnName = _fleetSpec.SpawnName,
                VehicleName = _report.VehicleName,
                StationType = _report.StationType,
                Arena = _report.Arena,
                Status = "aborted",
                Reason = reason,
                ModelHash = _report.ModelHash,
                SeatCount = _report.SeatCount,
                TrialCount = measured,
                Passed = _report.Passed,
                Outliers = _report.Outliers,
                Report = Path.GetFileName(_rollingPath),
            });
        }

        private void DeleteTestVehicle()
        {
            if (_testVehicle == null || !_testVehicle.Exists())
            {
                _testVehicle = null;
                return;
            }
            Ped player = Game.Player.Character;
            if (player != null && player.Exists()
                && player.IsInVehicle() && player.CurrentVehicle == _testVehicle)
            {
                Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player.Handle);
                Vector3 safe = _testVehicle.GetOffsetPosition(
                    new Vector3(-5f, -5f, 1f));
                Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET,
                    player.Handle, safe.X, safe.Y, safe.Z,
                    false, false, false);
            }
            _testVehicle.IsPersistent = true;
            _testVehicle.Delete();
            _testVehicle = null;
        }

        private void SuppressWorldInterference()
        {
            Function.Call(Hash.DISABLE_ALL_CONTROL_ACTIONS, 0);
            // SeatSelector injects the normal on-foot F/Enter control at an
            // authored turret climb point. Keep that one action available so
            // GTA can resolve the native mount animation during automated runs.
            Function.Call(Hash.ENABLE_CONTROL_ACTION, 0, 23, true);
            Function.Call(Hash.SET_PED_DENSITY_MULTIPLIER_THIS_FRAME, 0f);
            Function.Call(Hash.SET_SCENARIO_PED_DENSITY_MULTIPLIER_THIS_FRAME, 0f, 0f);
            Function.Call(Hash.SET_VEHICLE_DENSITY_MULTIPLIER_THIS_FRAME, 0f);
            Function.Call(Hash.SET_RANDOM_VEHICLE_DENSITY_MULTIPLIER_THIS_FRAME, 0f);
            Function.Call(Hash.SET_PARKED_VEHICLE_DENSITY_MULTIPLIER_THIS_FRAME, 0f);
            Function.Call(Hash.SET_GARBAGE_TRUCKS, false);
            Function.Call(Hash.SET_RANDOM_BOATS, false);
        }

        private static void ClearLabArea(Vector3 position)
        {
            Function.Call(Hash.CLEAR_AREA_OF_PEDS,
                position.X, position.Y, position.Z,
                LAB_CLEAR_RADIUS, 1);
            Function.Call(Hash.CLEAR_AREA_OF_VEHICLES,
                position.X, position.Y, position.Z,
                LAB_CLEAR_RADIUS,
                false, false, false, false, false, false, 0);
            Function.Call(Hash.CLEAR_AREA_OF_OBJECTS,
                position.X, position.Y, position.Z,
                20f, 0);
        }

        private void DrawStatus()
        {
            if (_report == null || _trials.Count == 0)
                return;

            TrialSpec trial = _trials[Math.Min(_trialIndex, _trials.Count - 1)];
            int done = _report.Trials.Count;
            float progress = _report.TrialCount > 0
                ? (float)done / _report.TrialCount : 0f;
            float panelX = 0.19f;
            float panelY = 0.14f;
            float panelW = 0.33f;
            float panelH = 0.19f;
            GbayRenderer.DrawBorderedRect(
                panelX, panelY, panelW, panelH,
                Color.FromArgb(225, 8, 16, 12),
                GbayRenderer.BtnGreen, 0.002f);
            GbayRenderer.DrawText(
                "SEAT LAB",
                panelX, 0.055f, 0.40f,
                Color.White, GbayRenderer.FONT_CONDENSED, true, true);
            if (_fleetMode)
            {
                GbayRenderer.DrawText(
                    $"FLEET {_fleetIndex + 1}/{UNCONVENTIONAL_FLEET.Length}",
                    0.43f, 0.057f, 0.22f,
                    GbayRenderer.TextMfg, GbayRenderer.FONT_CONDENSED,
                    true, true);
            }
            GbayRenderer.DrawTextFit(
                _report.VehicleName,
                0.04f, 0.085f, 0.30f, 0.25f, 0.34f,
                GbayRenderer.TextMfg,
                GbayRenderer.FONT_CHALET, false, true);
            string transition =
                $"{GetSeatLabel(_report.ModelHash, trial.SourceSeat)}  ->  "
                + GetSeatLabel(_report.ModelHash, trial.TargetSeat);
            GbayRenderer.DrawTextFit(
                transition,
                0.04f, 0.115f, 0.30f, 0.22f, 0.30f,
                Color.White, GbayRenderer.FONT_CHALET, false, true);
            GbayRenderer.DrawRect(
                panelX, 0.161f, 0.29f, 0.014f,
                Color.FromArgb(220, 45, 55, 48));
            if (progress > 0f)
            {
                float width = 0.29f * progress;
                GbayRenderer.DrawRect(
                    0.045f + width / 2f,
                    0.161f,
                    width,
                    0.014f,
                    GbayRenderer.BtnGreen);
            }
            GbayRenderer.DrawText(
                $"{done}/{_report.TrialCount}   Passed {_report.Passed}   "
                + $"Outliers {_report.Outliers}",
                panelX, 0.174f, 0.24f,
                Color.White, GbayRenderer.FONT_CONDENSED, true, true);
            GbayRenderer.DrawText(
                "F11: abort and restore session",
                panelX, 0.202f, 0.21f,
                GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED, true, true);
        }

        internal static string ClassifyTrial(
            bool success, string outcome, string reason, int elapsedMs)
        {
            if (success)
                return elapsedMs > SLOW_SUCCESS_MS ? "slow_success" : "pass";

            string normalized = (reason ?? "").ToLowerInvariant();
            if (normalized.Contains("wrong") || normalized.Contains("landed"))
                return "wrong_seat";
            if (normalized.Contains("route") || normalized.Contains("path"))
                return "route_prediction";
            if (normalized.Contains("timeout") || normalized.Contains("stall"))
                return "timeout";
            if (string.Equals(outcome, "rolled_back", StringComparison.OrdinalIgnoreCase))
                return "rolled_back";
            if (normalized.Contains("occupied") || normalized.Contains("claimed"))
                return "seat_conflict";
            return "switch_failed";
        }

        internal static string[] GetUnconventionalFleetModels()
        {
            var result = new string[UNCONVENTIONAL_FLEET.Length];
            for (int i = 0; i < UNCONVENTIONAL_FLEET.Length; i++)
                result[i] = UNCONVENTIONAL_FLEET[i].SpawnName;
            return result;
        }

        internal static string GetUnconventionalFleetStationType(string model)
        {
            foreach (FleetVehicleSpec spec in UNCONVENTIONAL_FLEET)
            {
                if (string.Equals(spec.SpawnName, model,
                    StringComparison.OrdinalIgnoreCase))
                    return spec.StationType;
            }
            return null;
        }

        private static FleetVehicleSpec Fleet(
            string spawnName,
            string displayName,
            string stationType,
            LabArena arena = LabArena.Ground)
        {
            return new FleetVehicleSpec
            {
                SpawnName = spawnName,
                DisplayName = displayName,
                StationType = stationType,
                Arena = arena,
            };
        }

        private static bool IsBoatModel(int modelHash)
        {
            return Function.Call<bool>(Hash.IS_THIS_MODEL_A_BOAT, modelHash);
        }

        private static Vehicle FindNearbyVehicle(Ped player, float radius)
        {
            if (player == null || !player.Exists())
                return null;
            Vehicle[] nearby = World.GetNearbyVehicles(player, radius);
            Vehicle closest = null;
            float best = float.MaxValue;
            foreach (Vehicle vehicle in nearby)
            {
                if (vehicle == null || !vehicle.Exists())
                    continue;
                float distance = player.Position.DistanceTo(vehicle.Position);
                if (distance < best)
                {
                    closest = vehicle;
                    best = distance;
                }
            }
            return closest;
        }

        private static int GetSeatIndex(Ped player, Vehicle vehicle)
        {
            if (player == null || !player.Exists()
                || vehicle == null || !vehicle.Exists()
                || !player.IsInVehicle() || player.CurrentVehicle != vehicle)
                return -2;
            int maxPassengers = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS, vehicle.Handle);
            for (int seat = -1; seat < maxPassengers; seat++)
            {
                Ped occupant = vehicle.GetPedOnSeat((VehicleSeat)seat);
                if (occupant != null && occupant.Exists() && occupant == player)
                    return seat;
            }
            return -2;
        }

        private static string GetSeatLabel(int modelHash, int seat)
        {
            return seat == -2 ? "Outside" : SeatSelector.GetSeatLabel(modelHash, seat);
        }

        private static float HeadingTowards(Vector3 from, Vector3 to)
        {
            float radians = (float)Math.Atan2(to.X - from.X, to.Y - from.Y);
            float degrees = radians * 180f / (float)Math.PI;
            return degrees < 0f ? degrees + 360f : degrees;
        }

        private static string SanitizeFileName(string value)
        {
            string result = value ?? "vehicle";
            foreach (char invalid in Path.GetInvalidFileNameChars())
                result = result.Replace(invalid, '-');
            return result.Replace(' ', '-').ToLowerInvariant();
        }
    }
}
