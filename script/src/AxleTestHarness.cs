// AxleTestHarness.cs -- Isolated Story Mode test for a four-axle Chernobog.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal enum AxleTestWheelRole
    {
        Front,
        Middle1,
        Middle2,
        Rear,
    }

    /// <summary>
    /// Mirrors the launcher's keyboard-conflict policy at the runtime boundary.
    /// The seat-selector binding participates only while that feature is enabled.
    /// </summary>
    internal static class AxleTestKeyPolicy
    {
        internal static bool TryFindF11Conflict(
            string gbayKey,
            string nightVisionKey,
            string worldVectorKey,
            bool seatSelectorEnabled,
            string seatSelectorKey,
            out string conflictingSetting)
        {
            if (IsF11(gbayKey))
                conflictingSetting = "gbay_key";
            else if (IsF11(nightVisionKey))
                conflictingSetting = "night_vision_key";
            else if (IsF11(worldVectorKey))
                conflictingSetting = "world_vector_key";
            else if (seatSelectorEnabled && IsF11(seatSelectorKey))
                conflictingSetting = "seat_selector_key";
            else
            {
                conflictingSetting = "";
                return false;
            }
            return true;
        }

        private static bool IsF11(string value) =>
            string.Equals(value?.Trim(), "F11", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Pure, bone-semantic policy for the four-axle, all-drive/all-steer
    /// Chernobog acceptance layout. Runtime collection order is irrelevant.
    /// </summary>
    internal static class FourAxleChernobogLayout
    {
        internal const int ExpectedWheelCount = 8;
        internal const float SteeringMultiplierTolerance = 0.001f;

        private static readonly VehicleWheelBoneId[] ExpectedBones =
        {
            VehicleWheelBoneId.WheelLeftFront,
            VehicleWheelBoneId.WheelRightFront,
            VehicleWheelBoneId.WheelLeftMiddle1,
            VehicleWheelBoneId.WheelRightMiddle1,
            VehicleWheelBoneId.WheelLeftMiddle2,
            VehicleWheelBoneId.WheelRightMiddle2,
            VehicleWheelBoneId.WheelLeftRear,
            VehicleWheelBoneId.WheelRightRear,
        };

        internal static IReadOnlyList<VehicleWheelBoneId> Bones => ExpectedBones;

        internal static bool TryGetRole(
            VehicleWheelBoneId bone, out AxleTestWheelRole role)
        {
            switch (bone)
            {
                case VehicleWheelBoneId.WheelLeftFront:
                case VehicleWheelBoneId.WheelRightFront:
                    role = AxleTestWheelRole.Front;
                    return true;
                case VehicleWheelBoneId.WheelLeftMiddle1:
                case VehicleWheelBoneId.WheelRightMiddle1:
                    role = AxleTestWheelRole.Middle1;
                    return true;
                case VehicleWheelBoneId.WheelLeftMiddle2:
                case VehicleWheelBoneId.WheelRightMiddle2:
                    role = AxleTestWheelRole.Middle2;
                    return true;
                case VehicleWheelBoneId.WheelLeftRear:
                case VehicleWheelBoneId.WheelRightRear:
                    role = AxleTestWheelRole.Rear;
                    return true;
                default:
                    role = default;
                    return false;
            }
        }

        internal static bool IsSteered(AxleTestWheelRole role) =>
            Enum.IsDefined(typeof(AxleTestWheelRole), role);

        internal static bool IsDriven(AxleTestWheelRole role) =>
            Enum.IsDefined(typeof(AxleTestWheelRole), role);

        internal static bool HasExpectedSteeringMultiplier(
            AxleTestWheelRole role,
            float actual,
            FourAxleSteeringGeometrySolution solution) =>
            solution != null &&
            Math.Abs(actual - solution.SteeringMultiplierFor(role)) <=
                SteeringMultiplierTolerance;

        internal static bool TryValidate(
            IEnumerable<VehicleWheelBoneId> bones,
            int reportedWheelCount,
            out string failure)
        {
            failure = "";
            if (reportedWheelCount != ExpectedWheelCount)
            {
                failure = $"game reported {reportedWheelCount} wheels; " +
                    $"the test requires exactly {ExpectedWheelCount}";
                return false;
            }

            if (bones == null)
            {
                failure = "the game returned no wheel mapping";
                return false;
            }

            VehicleWheelBoneId[] mapped = bones.ToArray();
            if (mapped.Length != ExpectedWheelCount)
            {
                failure = $"mapped {mapped.Length} wheel objects; " +
                    $"expected {ExpectedWheelCount}";
                return false;
            }

            var unique = new HashSet<VehicleWheelBoneId>(mapped);
            if (unique.Count != mapped.Length)
            {
                failure = "the wheel mapping contains duplicate canonical bones";
                return false;
            }

            foreach (VehicleWheelBoneId bone in ExpectedBones)
            {
                if (!unique.Contains(bone))
                {
                    failure = $"required wheel bone {bone} is missing";
                    return false;
                }
            }

            foreach (VehicleWheelBoneId bone in unique)
            {
                if (!TryGetRole(bone, out _))
                {
                    failure = $"unexpected physical wheel bone {bone}";
                    return false;
                }
            }
            return true;
        }
    }

    /// <summary>
    /// One canonical left/right wheel-bone pair expressed in vehicle-local
    /// coordinates. Only longitudinal Y participates in steering geometry;
    /// mesh, tyre, material, and visual-family choices are intentionally absent.
    /// </summary>
    internal readonly struct AxleTestWheelPairPosition
    {
        internal AxleTestWheelPairPosition(
            AxleTestWheelRole role, double leftY, double rightY)
        {
            Role = role;
            LeftY = leftY;
            RightY = rightY;
        }

        internal AxleTestWheelRole Role { get; }
        internal double LeftY { get; }
        internal double RightY { get; }
    }

    /// <summary>
    /// Immutable result retained by the runtime after spawn. Verification and
    /// telemetry reuse these exact gains rather than silently recalculating a
    /// different vehicle state later in the test drive.
    /// </summary>
    internal sealed class FourAxleSteeringGeometrySolution
    {
        private readonly IReadOnlyDictionary<AxleTestWheelRole, double> _centers;
        private readonly IReadOnlyDictionary<AxleTestWheelRole, float> _multipliers;

        internal FourAxleSteeringGeometrySolution(
            double frontY,
            double middle1Y,
            double middle2Y,
            double rearY,
            double pivotY,
            AxleTestWheelRole referenceRole,
            double referenceLockDegrees,
            double turnRadius,
            float frontMultiplier,
            float middle1Multiplier,
            float middle2Multiplier,
            float rearMultiplier)
        {
            _centers = new Dictionary<AxleTestWheelRole, double>
            {
                { AxleTestWheelRole.Front, frontY },
                { AxleTestWheelRole.Middle1, middle1Y },
                { AxleTestWheelRole.Middle2, middle2Y },
                { AxleTestWheelRole.Rear, rearY },
            };
            _multipliers = new Dictionary<AxleTestWheelRole, float>
            {
                { AxleTestWheelRole.Front, frontMultiplier },
                { AxleTestWheelRole.Middle1, middle1Multiplier },
                { AxleTestWheelRole.Middle2, middle2Multiplier },
                { AxleTestWheelRole.Rear, rearMultiplier },
            };
            PivotY = pivotY;
            ReferenceRole = referenceRole;
            ReferenceLockDegrees = referenceLockDegrees;
            TurnRadius = turnRadius;
        }

        internal double FrontY => AxleYFor(AxleTestWheelRole.Front);
        internal double Middle1Y => AxleYFor(AxleTestWheelRole.Middle1);
        internal double Middle2Y => AxleYFor(AxleTestWheelRole.Middle2);
        internal double RearY => AxleYFor(AxleTestWheelRole.Rear);
        internal double PivotY { get; }
        internal AxleTestWheelRole ReferenceRole { get; }
        internal double ReferenceLockDegrees { get; }
        internal double TurnRadius { get; }
        internal float FrontMultiplier => SteeringMultiplierFor(AxleTestWheelRole.Front);
        internal float Middle1Multiplier => SteeringMultiplierFor(AxleTestWheelRole.Middle1);
        internal float Middle2Multiplier => SteeringMultiplierFor(AxleTestWheelRole.Middle2);
        internal float RearMultiplier => SteeringMultiplierFor(AxleTestWheelRole.Rear);

        internal double AxleYFor(AxleTestWheelRole role)
        {
            if (_centers.TryGetValue(role, out double value)) return value;
            throw new ArgumentOutOfRangeException(nameof(role), role,
                "unsupported four-axle role");
        }

        internal float SteeringMultiplierFor(AxleTestWheelRole role)
        {
            if (_multipliers.TryGetValue(role, out float value)) return value;
            throw new ArgumentOutOfRangeException(nameof(role), role,
                "unsupported four-axle role");
        }
    }

    /// <summary>
    /// Pure center-line steering calculator shared by runtime policy tests.
    /// The neutral pivot is halfway between the two middle axle centers. At a
    /// 35-degree reference lock the farthest steered lever normalizes to one;
    /// position ahead of or behind the pivot alone determines steering phase.
    /// </summary>
    internal static class FourAxleSteeringGeometry
    {
        internal const double ReferenceLockDegrees = 35.0;
        internal const double PairPositionTolerance = 0.25;
        internal const double PositionEpsilon = 1.0e-4;

        internal static bool TryCalculate(
            IEnumerable<AxleTestWheelPairPosition> pairs,
            out FourAxleSteeringGeometrySolution solution,
            out string failure)
        {
            solution = null;
            failure = "";
            if (pairs == null)
            {
                failure = "canonical wheel-bone positions are missing";
                return false;
            }

            AxleTestWheelPairPosition[] rows = pairs.ToArray();
            if (rows.Length != 4)
            {
                failure = $"received {rows.Length} axle position rows; expected 4";
                return false;
            }

            var centers = new Dictionary<AxleTestWheelRole, double>();
            foreach (AxleTestWheelPairPosition row in rows)
            {
                if (centers.ContainsKey(row.Role))
                {
                    failure = $"canonical axle role {row.Role} is duplicated";
                    return false;
                }
                if (!IsFinite(row.LeftY) || !IsFinite(row.RightY))
                {
                    failure = $"canonical axle role {row.Role} has a nonfinite Y position";
                    return false;
                }
                if (Math.Abs(row.LeftY - row.RightY) > PairPositionTolerance)
                {
                    failure = $"canonical axle role {row.Role} has ambiguous " +
                        "left/right longitudinal positions";
                    return false;
                }
                centers.Add(row.Role, (row.LeftY + row.RightY) / 2.0);
            }

            foreach (AxleTestWheelRole role in new[]
            {
                AxleTestWheelRole.Front,
                AxleTestWheelRole.Middle1,
                AxleTestWheelRole.Middle2,
                AxleTestWheelRole.Rear,
            })
            {
                if (!centers.ContainsKey(role))
                {
                    failure = $"canonical axle role {role} is missing";
                    return false;
                }
            }

            double frontY = centers[AxleTestWheelRole.Front];
            double middle1Y = centers[AxleTestWheelRole.Middle1];
            double middle2Y = centers[AxleTestWheelRole.Middle2];
            double rearY = centers[AxleTestWheelRole.Rear];
            if (frontY - middle1Y <= PositionEpsilon ||
                middle1Y - middle2Y <= PositionEpsilon ||
                middle2Y - rearY <= PositionEpsilon)
            {
                failure = "canonical axle centers must be distinct and ordered " +
                    "front, middle1, middle2, rear in vehicle-local Y";
                return false;
            }

            double pivotY = (middle1Y + middle2Y) / 2.0;
            var offsets = new Dictionary<AxleTestWheelRole, double>
            {
                { AxleTestWheelRole.Front, frontY - pivotY },
                { AxleTestWheelRole.Middle1, middle1Y - pivotY },
                { AxleTestWheelRole.Middle2, middle2Y - pivotY },
                { AxleTestWheelRole.Rear, rearY - pivotY },
            };
            if (offsets.Values.Any(value => Math.Abs(value) <= PositionEpsilon))
            {
                failure = "a steered axle coincides with the neutral midpoint pivot";
                return false;
            }

            AxleTestWheelRole referenceRole = offsets
                .OrderByDescending(item => Math.Abs(item.Value))
                .ThenBy(item => item.Key)
                .First().Key;
            double referenceLever = Math.Abs(offsets[referenceRole]);
            double lockRadians = ReferenceLockDegrees * Math.PI / 180.0;
            double turnRadius = referenceLever / Math.Tan(lockRadians);
            if (!IsFinite(turnRadius) || turnRadius <= PositionEpsilon)
            {
                failure = "canonical geometry cannot produce a stable turn radius";
                return false;
            }

            var gains = offsets.ToDictionary(
                item => item.Key,
                item => Math.Atan(item.Value / turnRadius) / lockRadians);
            if (gains.Values.Any(value => !IsFinite(value) ||
                Math.Abs(value) > 1.0 + PositionEpsilon))
            {
                failure = "canonical geometry produced an invalid steering gain";
                return false;
            }

            foreach (AxleTestWheelRole role in gains.Keys.ToArray())
                gains[role] = Math.Max(-1.0, Math.Min(1.0, gains[role]));
            if (!(gains[AxleTestWheelRole.Front] >
                    gains[AxleTestWheelRole.Middle1] &&
                gains[AxleTestWheelRole.Middle1] > 0.0 &&
                gains[AxleTestWheelRole.Middle2] < 0.0 &&
                gains[AxleTestWheelRole.Middle2] >
                    gains[AxleTestWheelRole.Rear]))
            {
                failure = "canonical geometry did not produce progressive " +
                    "same-phase front and counter-phase rear steering";
                return false;
            }

            solution = new FourAxleSteeringGeometrySolution(
                frontY,
                middle1Y,
                middle2Y,
                rearY,
                pivotY,
                referenceRole,
                ReferenceLockDegrees,
                turnRadius,
                (float)gains[AxleTestWheelRole.Front],
                (float)gains[AxleTestWheelRole.Middle1],
                (float)gains[AxleTestWheelRole.Middle2],
                (float)gains[AxleTestWheelRole.Rear]);
            return true;
        }

        private static bool IsFinite(double value) =>
            !double.IsNaN(value) && !double.IsInfinity(value);
    }

    /// <summary>
    /// Opt-in F11 test harness. It uses ScriptHookVDotNet's public bone-aware
    /// wheel API; it never assumes native wheel indices or writes raw memory.
    /// </summary>
    public sealed class AxleTestHarness : Script
    {
        private const string Component = "AXLE-TEST";
        private const string TestModel = "chernobog";
        private const int CollisionTimeoutMs = 3500;
        private const int VerificationIntervalMs = 500;
        private const int TelemetryIntervalMs = 2000;
        private const float TestHeading = 104f;

        private static readonly Vector3 TestPosition =
            new Vector3(1743.70f, 3280.20f, 41.10f);

        private sealed class WheelSnapshot
        {
            internal bool Steering;
            internal bool Driving;
            internal float SteeringLimitMultiplier;
        }

        private readonly bool _enabled;
        private Vehicle _testVehicle;
        private Dictionary<VehicleWheelBoneId, WheelSnapshot> _originalWheels;
        private FourAxleSteeringGeometrySolution _steeringGeometry;
        private int _testVehicleHandle;
        private int _testModelHash;
        private string _ownershipToken;
        private bool _launching;
        private int _nextVerificationAt;
        private int _nextTelemetryAt;

        public AxleTestHarness()
        {
            bool configured = NpcPhysicsExperiment.ReadBooleanSetting(
                "axle_test_harness", false);
            bool packageEnabled = Allin1ExtensionApi.IsPackageEnabled(
                Allin1ExtensionApi.ExperimentalGameplayPackageId);
            bool keyConflict = AxleTestKeyPolicy.TryFindF11Conflict(
                NpcPhysicsExperiment.ReadStringSetting("gbay_key", "F9"),
                NpcPhysicsExperiment.ReadStringSetting("night_vision_key", "N"),
                NpcPhysicsExperiment.ReadStringSetting("world_vector_key", "F10"),
                NpcPhysicsExperiment.ReadBooleanSetting(
                    "seat_selector_enabled", true),
                NpcPhysicsExperiment.ReadStringSetting("seat_selector_key", "L"),
                out string conflictingSetting);
            _enabled = configured && packageEnabled && !keyConflict;

            if (!_enabled)
            {
                if (configured && !packageEnabled)
                    ClientLog.Warn(Component, "test_harness_blocked", Fields(
                        "reason", "experimental package disabled"));
                else if (configured && keyConflict)
                    ClientLog.Warn(Component, "test_harness_blocked",
                        new Dictionary<string, object>
                        {
                            { "reason", "F11 conflicts with another ALLIN1 key" },
                            { "setting", conflictingSetting },
                        });
                return;
            }

            KeyDown += OnKeyDown;
            Tick += OnTick;
            Aborted += OnAborted;
            Interval = 0;
            ClientLog.Info(Component, "test_harness_enabled", new Dictionary<string, object>
            {
                { "key", "F11" },
                { "model", TestModel },
                { "layout", "four-axle/all-drive/all-steer" },
                { "steering_geometry", "canonical vehicle-local wheel-bone Y" },
                { "neutral_pivot", "midpoint between middle1 and middle2" },
                { "reference_lock_degrees",
                    FourAxleSteeringGeometry.ReferenceLockDegrees },
                { "x", TestPosition.X }, { "y", TestPosition.Y },
                { "z", TestPosition.Z }, { "heading", TestHeading },
            });
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (!_enabled || e.KeyCode != Keys.F11 || _launching)
                return;
            SpawnTestDrive();
        }

        private void SpawnTestDrive()
        {
            if (Game.IsLoading)
            {
                Notify("~y~Axle test unavailable while the game is loading.");
                return;
            }
            if (IsNetworkSessionActive())
            {
                ClientLog.Warn(Component, "spawn_blocked", Fields(
                    "reason", "network session active"));
                Notify("~r~Axle testing is available in Story Mode only.");
                return;
            }
            if (GbayShop.IsMenuActive || GarageManager.IsTransitionInProgress)
            {
                Notify("~y~Close GBAY or finish the current transition first.");
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists() || player.IsDead)
            {
                Notify("~r~The axle test could not find an active character.");
                return;
            }
            if (Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY, player.Handle) != 0)
            {
                Notify("~y~Go outside before starting the axle test.");
                return;
            }

            _launching = true;
            Vehicle candidate = null;
            bool focusSet = false;
            bool fadedOut = false;
            try
            {
                FadeOut();
                fadedOut = true;
                DisposePreviousTestVehicle(true);

                Function.Call(Hash.SET_FOCUS_POS_AND_VEL,
                    TestPosition.X, TestPosition.Y, TestPosition.Z,
                    0f, 0f, 0f);
                focusSet = true;
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    TestPosition.X, TestPosition.Y, TestPosition.Z);

                candidate = VehicleHelper.CreateVehicle(
                    TestModel, TestPosition, TestHeading, 7000);
                if (candidate == null || !candidate.Exists())
                    throw new InvalidOperationException(
                        "the Chernobog model could not be spawned");

                WaitForCollision(candidate);
                if (IsNetworkSessionActive())
                    throw new InvalidOperationException(
                        "a network session became active during setup");
                Function.Call(Hash.SET_ENTITY_HEADING, candidate.Handle, TestHeading);
                Function.Call(Hash.SET_VEHICLE_ON_GROUND_PROPERLY, candidate.Handle);

                string ownershipToken = CreateOwnershipToken();
                Function.Call(Hash.SET_VEHICLE_NUMBER_PLATE_TEXT,
                    candidate.Handle, ownershipToken);

                Dictionary<VehicleWheelBoneId, WheelSnapshot> snapshot =
                    CaptureAndValidate(candidate);
                FourAxleSteeringGeometrySolution steeringGeometry =
                    CalculateSteeringGeometry(candidate);
                ApplyAndVerify(candidate, steeringGeometry);
                if (IsNetworkSessionActive())
                    throw new InvalidOperationException(
                        "a network session became active before test entry");

                candidate.IsPersistent = true;
                candidate.IsPositionFrozen = false;
                candidate.IsCollisionEnabled = true;
                Function.Call(Hash.SET_VEHICLE_HANDBRAKE, candidate.Handle, false);
                Function.Call(Hash.SET_VEHICLE_UNDRIVEABLE, candidate.Handle, false);
                Function.Call(Hash.SET_ENTITY_DYNAMIC, candidate.Handle, true);
                Function.Call(Hash.FREEZE_ENTITY_POSITION, candidate.Handle, false);
                Function.Call(Hash.ACTIVATE_PHYSICS, candidate.Handle);
                Function.Call(Hash.SET_VEHICLE_ENGINE_ON,
                    candidate.Handle, true, true, false);
                candidate.IsEngineRunning = true;
                player.SetIntoVehicle(candidate, VehicleSeat.Driver);

                _testVehicle = candidate;
                _originalWheels = snapshot;
                _steeringGeometry = steeringGeometry;
                _testVehicleHandle = candidate.Handle;
                _testModelHash = candidate.Model.Hash;
                _ownershipToken = ownershipToken;
                candidate = null;
                _nextVerificationAt = Game.GameTime + VerificationIntervalMs;
                _nextTelemetryAt = Game.GameTime + TelemetryIntervalMs;
                ClientLog.Info(Component, "test_drive_spawned", VehicleFields(
                    _testVehicle, _steeringGeometry,
                    "configuration", "S-S | S-S all-drive"));
                Notify("~g~Chernobog 4-axle steering applied~w~\n" +
                    $"Front {_steeringGeometry.FrontMultiplier:+0%;-0%;0%} · " +
                    $"M1 {_steeringGeometry.Middle1Multiplier:+0%;-0%;0%} · " +
                    $"M2 {_steeringGeometry.Middle2Multiplier:+0%;-0%;0%} · " +
                    $"rear {_steeringGeometry.RearMultiplier:+0%;-0%;0%}");
            }
            catch (Exception ex)
            {
                if (candidate != null && candidate.Exists() &&
                    !IsNetworkSessionActive())
                    candidate.Delete();
                ClientLog.Error(Component, "test_drive_failed", ex);
                Notify("~r~Axle test failed:~w~ " + ex.Message);
            }
            finally
            {
                if (focusSet) Function.Call(Hash.CLEAR_FOCUS);
                if (fadedOut) Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
                _launching = false;
            }
        }

        private static Dictionary<VehicleWheelBoneId, WheelSnapshot>
            CaptureAndValidate(Vehicle vehicle)
        {
            VehicleWheel[] wheels = vehicle.Wheels.GetAllWheels();
            VehicleWheelBoneId[] bones = wheels.Select(wheel => wheel.BoneId).ToArray();
            if (!FourAxleChernobogLayout.TryValidate(
                bones, vehicle.Wheels.Count, out string failure))
            {
                ClientLog.Warn(Component, "wheel_mapping_rejected",
                    new Dictionary<string, object>
                    {
                        { "model", TestModel },
                        { "reported_count", vehicle.Wheels.Count },
                        { "mapped_count", wheels.Length },
                        { "bones", string.Join(",", bones.Select(value => value.ToString())) },
                        { "reason", failure },
                    });
                throw new InvalidOperationException(failure);
            }

            var snapshot = new Dictionary<VehicleWheelBoneId, WheelSnapshot>();
            foreach (VehicleWheel wheel in wheels)
            {
                snapshot.Add(wheel.BoneId, new WheelSnapshot
                {
                    Steering = wheel.IsSteeringWheel,
                    Driving = wheel.IsDrivingWheel,
                    SteeringLimitMultiplier = wheel.SteeringLimitMultiplier,
                });
            }
            return snapshot;
        }

        private static FourAxleSteeringGeometrySolution
            CalculateSteeringGeometry(Vehicle vehicle)
        {
            // Canonical EntityBone.RelativePosition is public SHVDN state in
            // vehicle-local coordinates. Visual meshes never enter this path.
            AxleTestWheelPairPosition[] positions =
            {
                ReadCanonicalWheelPair(
                    vehicle,
                    AxleTestWheelRole.Front,
                    "wheel_lf",
                    "wheel_rf"),
                ReadCanonicalWheelPair(
                    vehicle,
                    AxleTestWheelRole.Middle1,
                    "wheel_lm1",
                    "wheel_rm1"),
                ReadCanonicalWheelPair(
                    vehicle,
                    AxleTestWheelRole.Middle2,
                    "wheel_lm2",
                    "wheel_rm2"),
                ReadCanonicalWheelPair(
                    vehicle,
                    AxleTestWheelRole.Rear,
                    "wheel_lr",
                    "wheel_rr"),
            };
            if (!FourAxleSteeringGeometry.TryCalculate(
                positions, out FourAxleSteeringGeometrySolution solution,
                out string failure))
            {
                ClientLog.Warn(Component, "steering_geometry_rejected",
                    new Dictionary<string, object>
                    {
                        { "model", TestModel },
                        { "reason", failure },
                        { "front_left_y", positions[0].LeftY },
                        { "front_right_y", positions[0].RightY },
                        { "middle_left_y", positions[1].LeftY },
                        { "middle_right_y", positions[1].RightY },
                        { "middle2_left_y", positions[2].LeftY },
                        { "middle2_right_y", positions[2].RightY },
                        { "rear_left_y", positions[3].LeftY },
                        { "rear_right_y", positions[3].RightY },
                    });
                throw new InvalidOperationException(failure);
            }
            return solution;
        }

        private static AxleTestWheelPairPosition ReadCanonicalWheelPair(
            Vehicle vehicle,
            AxleTestWheelRole role,
            string leftBoneName,
            string rightBoneName)
        {
            if (vehicle == null || !vehicle.Exists())
                throw new InvalidOperationException(
                    "the vehicle no longer exists while reading wheel geometry");
            if (!vehicle.Bones.Contains(leftBoneName) ||
                !vehicle.Bones.Contains(rightBoneName))
                throw new InvalidOperationException(
                    $"canonical wheel bones {leftBoneName}/{rightBoneName} are missing");

            EntityBone leftBone = vehicle.Bones[leftBoneName];
            EntityBone rightBone = vehicle.Bones[rightBoneName];
            if (leftBone == null || rightBone == null ||
                !leftBone.IsValid || !rightBone.IsValid)
                throw new InvalidOperationException(
                    $"canonical wheel bones {leftBoneName}/{rightBoneName} are invalid");

            Vector3 left = leftBone.RelativePosition;
            Vector3 right = rightBone.RelativePosition;
            return new AxleTestWheelPairPosition(role, left.Y, right.Y);
        }

        private static void ApplyAndVerify(
            Vehicle vehicle,
            FourAxleSteeringGeometrySolution steeringGeometry)
        {
            if (steeringGeometry == null)
                throw new InvalidOperationException(
                    "the bone-derived steering geometry is unavailable");
            VehicleWheel[] wheels = vehicle.Wheels.GetAllWheels();
            VehicleWheelBoneId[] bones = wheels.Select(wheel => wheel.BoneId).ToArray();
            if (!FourAxleChernobogLayout.TryValidate(
                bones, vehicle.Wheels.Count, out string failure))
                throw new InvalidOperationException(failure);

            foreach (VehicleWheel wheel in wheels)
            {
                if (!FourAxleChernobogLayout.TryGetRole(
                    wheel.BoneId, out AxleTestWheelRole role))
                    throw new InvalidOperationException(
                        $"unrecognized wheel bone {wheel.BoneId}");
                bool steering = FourAxleChernobogLayout.IsSteered(role);
                bool driving = FourAxleChernobogLayout.IsDriven(role);
                wheel.IsSteeringWheel = steering;
                wheel.IsDrivingWheel = driving;
                wheel.SteeringLimitMultiplier =
                    steeringGeometry.SteeringMultiplierFor(role);
            }

            foreach (VehicleWheel wheel in vehicle.Wheels.GetAllWheels())
            {
                FourAxleChernobogLayout.TryGetRole(
                    wheel.BoneId, out AxleTestWheelRole role);
                bool expectedSteering = FourAxleChernobogLayout.IsSteered(role);
                bool expectedDriving = FourAxleChernobogLayout.IsDriven(role);
                if (wheel.IsSteeringWheel != expectedSteering ||
                    wheel.IsDrivingWheel != expectedDriving ||
                    !FourAxleChernobogLayout.HasExpectedSteeringMultiplier(
                        role, wheel.SteeringLimitMultiplier,
                        steeringGeometry))
                    throw new InvalidOperationException(
                        $"game rejected the {wheel.BoneId} axle targets " +
                        $"(steer={expectedSteering}, drive={expectedDriving}, " +
                        $"multiplier=" +
                        $"{steeringGeometry.SteeringMultiplierFor(role):+0.00;-0.00;0.00})");
            }
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!_enabled || _launching || Game.IsLoading ||
                _testVehicle == null)
                return;
            if (IsNetworkSessionActive())
            {
                ClientLog.Warn(Component, "test_drive_detached",
                    Fields("reason", "network session became active"));
                ClearTrackedVehicle();
                return;
            }
            if (!IsOwnedTestVehicle(_testVehicle))
            {
                ClientLog.Warn(Component, "test_drive_detached",
                    Fields("reason", "owned vehicle identity changed"));
                ClearTrackedVehicle();
                return;
            }

            int now = Game.GameTime;
            if (unchecked(now - _nextVerificationAt) >= 0)
            {
                _nextVerificationAt = now + VerificationIntervalMs;
                try
                {
                    if (!HasExpectedFlags(_testVehicle, _steeringGeometry))
                    {
                        ApplyAndVerify(_testVehicle, _steeringGeometry);
                        ClientLog.Warn(Component, "wheel_flags_reapplied",
                            VehicleFields(_testVehicle, _steeringGeometry));
                    }
                }
                catch (Exception ex)
                {
                    ClientLog.Error(Component, "wheel_verification_failed", ex,
                        VehicleFields(_testVehicle, _steeringGeometry));
                    Notify("~r~Axle test stopped: wheel mapping changed.");
                    RestoreOriginalWheelState();
                    if (!IsNetworkSessionActive())
                        ReleaseHarnessVehicle(_testVehicle);
                    ClearTrackedVehicle();
                    return;
                }
            }

            if (unchecked(now - _nextTelemetryAt) >= 0)
            {
                _nextTelemetryAt = now + TelemetryIntervalMs;
                ClientLog.Info(Component, "test_drive_telemetry",
                    VehicleFields(_testVehicle, _steeringGeometry,
                        "player_is_driver",
                        Game.Player.Character != null &&
                        Game.Player.Character.Exists() &&
                        Game.Player.Character.CurrentVehicle == _testVehicle));
            }
        }

        private static bool HasExpectedFlags(
            Vehicle vehicle,
            FourAxleSteeringGeometrySolution steeringGeometry)
        {
            if (steeringGeometry == null)
                return false;
            VehicleWheel[] wheels = vehicle.Wheels.GetAllWheels();
            if (!FourAxleChernobogLayout.TryValidate(
                wheels.Select(wheel => wheel.BoneId),
                vehicle.Wheels.Count, out _))
                return false;
            foreach (VehicleWheel wheel in wheels)
            {
                FourAxleChernobogLayout.TryGetRole(
                    wheel.BoneId, out AxleTestWheelRole role);
                if (wheel.IsSteeringWheel != FourAxleChernobogLayout.IsSteered(role) ||
                    wheel.IsDrivingWheel != FourAxleChernobogLayout.IsDriven(role) ||
                    !FourAxleChernobogLayout.HasExpectedSteeringMultiplier(
                        role, wheel.SteeringLimitMultiplier,
                        steeringGeometry))
                    return false;
            }
            return true;
        }

        private static void WaitForCollision(Vehicle vehicle)
        {
            int startedAt = Game.GameTime;
            bool loaded = Function.Call<bool>(
                Hash.HAS_COLLISION_LOADED_AROUND_ENTITY, vehicle.Handle);
            while (!loaded && Game.GameTime - startedAt < CollisionTimeoutMs)
            {
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    TestPosition.X, TestPosition.Y, TestPosition.Z);
                Script.Wait(50);
                loaded = Function.Call<bool>(
                    Hash.HAS_COLLISION_LOADED_AROUND_ENTITY, vehicle.Handle);
            }
            if (!loaded)
                throw new InvalidOperationException(
                    "Sandy Shores collision did not load in time");
        }

        private static void FadeOut()
        {
            if (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                Function.Call(Hash.DO_SCREEN_FADE_OUT, 350);
            int startedAt = Game.GameTime;
            while (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT) &&
                Game.GameTime - startedAt < 1500)
                Script.Wait(0);
            if (!Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                Function.Call(Hash.DO_SCREEN_FADE_OUT, 0);
        }

        private void DisposePreviousTestVehicle(bool deleteVehicle)
        {
            if (_testVehicle == null)
                return;
            if (IsNetworkSessionActive())
            {
                ClearTrackedVehicle();
                return;
            }
            if (!IsOwnedTestVehicle(_testVehicle))
            {
                ClearTrackedVehicle();
                return;
            }
            RestoreOriginalWheelState();
            if (!IsNetworkSessionActive() && _testVehicle.Exists())
            {
                if (deleteVehicle)
                    _testVehicle.Delete();
                else
                    _testVehicle.MarkAsNoLongerNeeded();
            }
            ClearTrackedVehicle();
        }

        private void RestoreOriginalWheelState()
        {
            if (IsNetworkSessionActive() || _testVehicle == null ||
                !IsOwnedTestVehicle(_testVehicle) ||
                _originalWheels == null)
                return;
            try
            {
                foreach (VehicleWheel wheel in _testVehicle.Wheels.GetAllWheels())
                {
                    if (!_originalWheels.TryGetValue(
                        wheel.BoneId, out WheelSnapshot state))
                        continue;
                    wheel.IsSteeringWheel = state.Steering;
                    wheel.IsDrivingWheel = state.Driving;
                    wheel.SteeringLimitMultiplier =
                        state.SteeringLimitMultiplier;
                }
                ClientLog.Info(Component, "wheel_state_restored",
                    VehicleFields(_testVehicle, _steeringGeometry));
            }
            catch (Exception ex)
            {
                ClientLog.Error(Component, "wheel_state_restore_failed", ex,
                    VehicleFields(_testVehicle, _steeringGeometry));
            }
        }

        private void OnAborted(object sender, EventArgs e)
        {
            bool online = IsNetworkSessionActive();
            try
            {
                if (!online && _testVehicle != null &&
                    IsOwnedTestVehicle(_testVehicle))
                {
                    RestoreOriginalWheelState();
                    if (!IsNetworkSessionActive())
                        ReleaseHarnessVehicle(_testVehicle);
                }
            }
            finally
            {
                if (!online && !IsNetworkSessionActive())
                {
                    Function.Call(Hash.CLEAR_FOCUS);
                    if (Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT))
                        Function.Call(Hash.DO_SCREEN_FADE_IN, 0);
                }
                ClearTrackedVehicle();
            }
        }

        private bool IsOwnedTestVehicle(Vehicle vehicle)
        {
            if (vehicle == null || !vehicle.Exists() ||
                vehicle.Handle != _testVehicleHandle ||
                vehicle.Model.Hash != _testModelHash ||
                string.IsNullOrEmpty(_ownershipToken))
                return false;
            try
            {
                string plate = Function.Call<string>(
                    Hash.GET_VEHICLE_NUMBER_PLATE_TEXT, vehicle.Handle);
                return string.Equals(
                    plate?.Trim(), _ownershipToken,
                    StringComparison.OrdinalIgnoreCase);
            }
            catch (Exception)
            {
                return false;
            }
        }

        private static void ReleaseHarnessVehicle(Vehicle vehicle)
        {
            if (vehicle == null || !vehicle.Exists()) return;
            Function.Call(Hash.DECOR_REMOVE, vehicle.Handle, "MPBitset");
            vehicle.IsPersistent = false;
            vehicle.MarkAsNoLongerNeeded();
        }

        private void ClearTrackedVehicle()
        {
            _testVehicle = null;
            _originalWheels = null;
            _steeringGeometry = null;
            _testVehicleHandle = 0;
            _testModelHash = 0;
            _ownershipToken = null;
        }

        private static string CreateOwnershipToken() =>
            string.Format("AX{0:X6}", Game.GameTime & 0xFFFFFF);

        private static bool IsNetworkSessionActive()
        {
            try
            {
                return Function.Call<bool>(Hash.NETWORK_IS_SESSION_ACTIVE);
            }
            catch (Exception ex)
            {
                ClientLog.Error(Component, "network_state_check_failed", ex);
                return true;
            }
        }

        private static Dictionary<string, object> VehicleFields(
            Vehicle vehicle,
            FourAxleSteeringGeometrySolution steeringGeometry = null,
            string extraKey = null,
            object extraValue = null)
        {
            var fields = new Dictionary<string, object>
            {
                { "model", TestModel },
                { "handle", vehicle != null && vehicle.Exists() ? vehicle.Handle : 0 },
                { "speed_mps", vehicle != null && vehicle.Exists() ? vehicle.Speed : 0f },
                { "steering_angle", vehicle != null && vehicle.Exists()
                    ? vehicle.SteeringAngle : 0f },
                { "reported_wheels", vehicle != null && vehicle.Exists()
                    ? vehicle.Wheels.Count : 0 },
            };
            if (steeringGeometry != null)
            {
                fields["steering_geometry"] = "canonical vehicle-local wheel-bone Y";
                fields["steering_pivot_y"] = steeringGeometry.PivotY;
                fields["steering_reference_axle"] =
                    steeringGeometry.ReferenceRole.ToString();
                fields["steering_reference_lock_degrees"] =
                    steeringGeometry.ReferenceLockDegrees;
                fields["steering_turn_radius"] = steeringGeometry.TurnRadius;
                fields["front_axle_y"] = steeringGeometry.FrontY;
                fields["middle1_axle_y"] = steeringGeometry.Middle1Y;
                fields["middle2_axle_y"] = steeringGeometry.Middle2Y;
                fields["rear_axle_y"] = steeringGeometry.RearY;
                fields["front_steering_multiplier"] =
                    steeringGeometry.FrontMultiplier;
                fields["middle1_steering_multiplier"] =
                    steeringGeometry.Middle1Multiplier;
                fields["middle2_steering_multiplier"] =
                    steeringGeometry.Middle2Multiplier;
                fields["rear_steering_multiplier"] =
                    steeringGeometry.RearMultiplier;
            }
            if (vehicle != null && vehicle.Exists())
            {
                try
                {
                    fields["wheel_flags"] = string.Join(";",
                        vehicle.Wheels.GetAllWheels()
                            .OrderBy(wheel => wheel.BoneId)
                            .Select(wheel =>
                            {
                                bool recognized = FourAxleChernobogLayout.TryGetRole(
                                    wheel.BoneId, out AxleTestWheelRole role);
                                string target =
                                    recognized && steeringGeometry != null
                                    ? steeringGeometry.SteeringMultiplierFor(role)
                                        .ToString("+0.00;-0.00;0.00")
                                    : "?";
                                return
                                    $"{wheel.BoneId}:" +
                                    $"S{(wheel.IsSteeringWheel ? 1 : 0)}" +
                                    $"D{(wheel.IsDrivingWheel ? 1 : 0)}" +
                                    $"M{wheel.SteeringLimitMultiplier:+0.00;-0.00;0.00}" +
                                    $"T{target}";
                            }));
                }
                catch (Exception ex)
                {
                    fields["wheel_flags_error"] = ex.GetType().Name;
                }
            }
            if (!string.IsNullOrEmpty(extraKey))
                fields[extraKey] = extraValue;
            return fields;
        }

        private static Dictionary<string, object> Fields(string key, object value) =>
            new Dictionary<string, object> { { key, value } };

        private static void Notify(string message)
        {
            GTA.UI.Notification.Show(message);
        }
    }
}
