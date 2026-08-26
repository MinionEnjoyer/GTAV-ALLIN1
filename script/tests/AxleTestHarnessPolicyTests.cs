using System;
using System.Linq;
using GTA;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class AxleTestHarnessPolicyTests
    {
        [Theory]
        [InlineData("F11", "N", "F10", true, "L", "gbay_key")]
        [InlineData("F9", "f11", "F10", true, "L", "night_vision_key")]
        [InlineData("F9", "N", " F11 ", true, "L", "world_vector_key")]
        [InlineData("F9", "N", "F10", true, "F11", "seat_selector_key")]
        public void ActiveAllin1BindingsReserveF11(
            string gbayKey,
            string nightVisionKey,
            string worldVectorKey,
            bool seatSelectorEnabled,
            string seatSelectorKey,
            string expectedSetting)
        {
            Assert.True(AxleTestKeyPolicy.TryFindF11Conflict(
                gbayKey, nightVisionKey, worldVectorKey,
                seatSelectorEnabled, seatSelectorKey,
                out string conflictingSetting));
            Assert.Equal(expectedSetting, conflictingSetting);
        }

        [Fact]
        public void DisabledSeatSelectorDoesNotReserveItsKey()
        {
            Assert.False(AxleTestKeyPolicy.TryFindF11Conflict(
                "F9", "N", "F10", false, "F11",
                out string conflictingSetting));
            Assert.Equal("", conflictingSetting);
        }

        [Fact]
        public void ExactFourAxleLayoutValidatesInAnyOrder()
        {
            VehicleWheelBoneId[] shuffled =
            {
                VehicleWheelBoneId.WheelRightMiddle2,
                VehicleWheelBoneId.WheelLeftRear,
                VehicleWheelBoneId.WheelRightFront,
                VehicleWheelBoneId.WheelLeftMiddle1,
                VehicleWheelBoneId.WheelRightRear,
                VehicleWheelBoneId.WheelLeftFront,
                VehicleWheelBoneId.WheelRightMiddle1,
                VehicleWheelBoneId.WheelLeftMiddle2,
            };

            bool valid = FourAxleChernobogLayout.TryValidate(
                shuffled, 8, out string failure);

            Assert.True(valid, failure);
        }

        [Theory]
        [InlineData(VehicleWheelBoneId.WheelLeftFront, 0)]
        [InlineData(VehicleWheelBoneId.WheelRightFront, 0)]
        [InlineData(VehicleWheelBoneId.WheelLeftMiddle1, 1)]
        [InlineData(VehicleWheelBoneId.WheelRightMiddle1, 1)]
        [InlineData(VehicleWheelBoneId.WheelLeftMiddle2, 2)]
        [InlineData(VehicleWheelBoneId.WheelRightMiddle2, 2)]
        [InlineData(VehicleWheelBoneId.WheelLeftRear, 3)]
        [InlineData(VehicleWheelBoneId.WheelRightRear, 3)]
        public void CanonicalBoneDeterminesRoleWithoutIndexArithmetic(
            VehicleWheelBoneId bone, int expectedRole)
        {
            Assert.True(FourAxleChernobogLayout.TryGetRole(
                bone, out AxleTestWheelRole role));
            Assert.Equal((AxleTestWheelRole)expectedRole, role);
        }

        [Theory]
        [InlineData(0)]
        [InlineData(1)]
        [InlineData(2)]
        [InlineData(3)]
        public void EveryPhysicalAxleIsDrivenAndSteered(int roleValue)
        {
            var role = (AxleTestWheelRole)roleValue;
            Assert.True(FourAxleChernobogLayout.IsSteered(role));
            Assert.True(FourAxleChernobogLayout.IsDriven(role));
        }

        [Fact]
        public void GeometryUsesMiddleAxleMidpointAsNeutralPivot()
        {
            FourAxleSteeringGeometrySolution solution = SymmetricSolution();

            Assert.Equal(0.0, solution.PivotY, 8);
            Assert.Equal(35.0, solution.ReferenceLockDegrees, 8);
            Assert.Equal(1f, solution.FrontMultiplier, 6);
            Assert.InRange(solution.Middle1Multiplier, 0f, 0.999999f);
            Assert.InRange(solution.Middle2Multiplier, -0.999999f, 0f);
            Assert.Equal(-1f, solution.RearMultiplier, 6);
        }

        [Fact]
        public void GainsProgressFromSamePhaseFrontToCounterPhaseRear()
        {
            FourAxleSteeringGeometrySolution solution = SymmetricSolution();

            Assert.True(solution.FrontMultiplier > solution.Middle1Multiplier);
            Assert.True(solution.Middle1Multiplier > 0f);
            Assert.True(solution.Middle2Multiplier < 0f);
            Assert.True(solution.Middle2Multiplier > solution.RearMultiplier);
        }

        [Fact]
        public void DecodedChernobogGeometryProducesExpectedProgressiveGains()
        {
            // Vehicle-local Y values decoded from the stock Enhanced
            // mpchristmas2017 chernobog.yft skeleton. Keeping this fixture here
            // catches accidental axle-order or steering-phase regressions.
            AxleTestWheelPairPosition[] positions = Positions(
                front: 3.699462,
                middle1: 1.640160,
                middle2: -1.630180,
                rear: -3.692246);

            Assert.True(FourAxleSteeringGeometry.TryCalculate(
                positions, out FourAxleSteeringGeometrySolution solution,
                out string failure), failure);
            Assert.Equal(0.004990, solution.PivotY, 6);
            Assert.InRange(solution.FrontMultiplier, 0.998f, 1.0f);
            Assert.InRange(solution.Middle1Multiplier, 0.48f, 0.51f);
            Assert.InRange(solution.Middle2Multiplier, -0.51f, -0.48f);
            Assert.Equal(-1f, solution.RearMultiplier, 6);
        }

        [Fact]
        public void FarthestSteeredLeverNormalizesToUnitMagnitude()
        {
            AxleTestWheelPairPosition[] positions = Positions(
                front: 5.0, middle1: 2.0, middle2: 0.0, rear: -8.0);

            Assert.True(FourAxleSteeringGeometry.TryCalculate(
                positions, out FourAxleSteeringGeometrySolution solution,
                out string failure), failure);
            Assert.Equal(AxleTestWheelRole.Rear, solution.ReferenceRole);
            Assert.Equal(-1f, solution.RearMultiplier, 6);
            Assert.InRange(solution.FrontMultiplier, 0f, 0.999999f);
        }

        [Fact]
        public void GeometryRowsCanArriveInAnyOrder()
        {
            AxleTestWheelPairPosition[] positions = Positions(
                front: 6.0, middle1: 2.0, middle2: -2.0, rear: -6.0)
                .Reverse().ToArray();

            Assert.True(FourAxleSteeringGeometry.TryCalculate(
                positions, out FourAxleSteeringGeometrySolution solution,
                out string failure), failure);
            Assert.Equal(0.0, solution.PivotY, 8);
        }

        [Fact]
        public void MissingCanonicalGeometryFailsClosed()
        {
            AxleTestWheelPairPosition[] positions = Positions(
                front: 6.0, middle1: 2.0, middle2: -2.0, rear: -6.0)
                .Where(row => row.Role != AxleTestWheelRole.Middle2)
                .ToArray();

            Assert.False(FourAxleSteeringGeometry.TryCalculate(
                positions, out _, out string failure));
            Assert.Contains("expected 4", failure, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void DuplicateCanonicalGeometryFailsClosed()
        {
            AxleTestWheelPairPosition[] positions = Positions(
                front: 6.0, middle1: 2.0, middle2: -2.0, rear: -6.0);
            positions[3] = Pair(AxleTestWheelRole.Middle2, -6.0);

            Assert.False(FourAxleSteeringGeometry.TryCalculate(
                positions, out _, out string failure));
            Assert.Contains("duplicated", failure, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void NonfiniteCanonicalGeometryFailsClosed()
        {
            AxleTestWheelPairPosition[] positions = Positions(
                front: double.NaN, middle1: 2.0, middle2: -2.0, rear: -6.0);

            Assert.False(FourAxleSteeringGeometry.TryCalculate(
                positions, out _, out string failure));
            Assert.Contains("nonfinite", failure, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void AmbiguousPairGeometryFailsClosed()
        {
            AxleTestWheelPairPosition[] positions = Positions(
                front: 6.0, middle1: 2.0, middle2: -2.0, rear: -6.0);
            positions[0] = new AxleTestWheelPairPosition(
                AxleTestWheelRole.Front, 6.0, 6.5);

            Assert.False(FourAxleSteeringGeometry.TryCalculate(
                positions, out _, out string failure));
            Assert.Contains("ambiguous", failure, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void UnorderedOrCoincidentAxlesFailClosed()
        {
            AxleTestWheelPairPosition[] positions = Positions(
                front: 6.0, middle1: 2.0, middle2: 2.0, rear: -6.0);

            Assert.False(FourAxleSteeringGeometry.TryCalculate(
                positions, out _, out string failure));
            Assert.Contains("distinct", failure, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void MissingMiddleTwoWheelFailsClosed()
        {
            VehicleWheelBoneId[] bones = FourAxleChernobogLayout.Bones
                .Where(bone => bone != VehicleWheelBoneId.WheelRightMiddle2)
                .ToArray();

            Assert.False(FourAxleChernobogLayout.TryValidate(
                bones, 8, out string failure));
            Assert.Contains("mapped 7", failure, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void DuplicateBoneFailsClosed()
        {
            VehicleWheelBoneId[] bones = FourAxleChernobogLayout.Bones.ToArray();
            bones[7] = VehicleWheelBoneId.WheelLeftRear;

            Assert.False(FourAxleChernobogLayout.TryValidate(
                bones, 8, out string failure));
            Assert.Contains("duplicate", failure, StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void GameWheelCountMismatchFailsClosed()
        {
            Assert.False(FourAxleChernobogLayout.TryValidate(
                FourAxleChernobogLayout.Bones, 6, out string failure));
            Assert.Contains("reported 6", failure, StringComparison.OrdinalIgnoreCase);
        }

        private static FourAxleSteeringGeometrySolution SymmetricSolution()
        {
            Assert.True(FourAxleSteeringGeometry.TryCalculate(
                Positions(front: 6.0, middle1: 2.0, middle2: -2.0, rear: -6.0),
                out FourAxleSteeringGeometrySolution solution,
                out string failure), failure);
            return solution;
        }

        private static AxleTestWheelPairPosition[] Positions(
            double front, double middle1, double middle2, double rear) =>
            new[]
            {
                Pair(AxleTestWheelRole.Front, front),
                Pair(AxleTestWheelRole.Middle1, middle1),
                Pair(AxleTestWheelRole.Middle2, middle2),
                Pair(AxleTestWheelRole.Rear, rear),
            };

        private static AxleTestWheelPairPosition Pair(
            AxleTestWheelRole role, double y) =>
            new AxleTestWheelPairPosition(role, y, y);
    }
}
