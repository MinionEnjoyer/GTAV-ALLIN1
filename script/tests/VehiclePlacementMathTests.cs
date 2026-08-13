using Xunit;

namespace ALLIN1.Tests
{
    public sealed class VehiclePlacementMathTests
    {
        [Fact]
        public void CalculateRootZ_PlacesLowestModelBoundOnFloor()
        {
            float root = VehiclePlacementMath.CalculateRootZ(
                floorZ: -100f,
                minimumModelZ: -0.56f,
                nativeRootZ: -99.5f,
                clearance: 0.02f);

            Assert.Equal(-99.42f, root, 3);
        }

        [Fact]
        public void CalculateRootZ_SupportsModelsWhoseOriginIsAboveLowestBound()
        {
            float root = VehiclePlacementMath.CalculateRootZ(
                floorZ: -67.75f,
                minimumModelZ: -1.2f,
                nativeRootZ: -67.1f,
                clearance: 0f);

            Assert.Equal(-66.55f, root, 3);
        }

        [Theory]
        [InlineData(float.NaN, -0.5f)]
        [InlineData(-100f, float.NaN)]
        [InlineData(-100f, -20f)]
        public void CalculateRootZ_FallsBackForInvalidOrExtremeInputs(
            float floorZ, float minimumModelZ)
        {
            const float nativeRoot = -99.6f;
            Assert.Equal(nativeRoot, VehiclePlacementMath.CalculateRootZ(
                floorZ, minimumModelZ, nativeRoot));
        }

        [Theory]
        [InlineData(-0.5f, 1.5f, true)]
        [InlineData(float.NaN, 1.5f, false)]
        [InlineData(-0.5f, -0.5f, false)]
        [InlineData(-11f, 1.5f, false)]
        public void HasUsableBounds_ValidatesModelExtents(
            float minimumZ, float maximumZ, bool expected)
        {
            Assert.Equal(expected,
                VehiclePlacementMath.HasUsableBounds(minimumZ, maximumZ));
        }

        [Fact]
        public void CalculateMeasuredRootZ_UsesCalibratedOffset()
        {
            float root = VehiclePlacementMath.CalculateMeasuredRootZ(
                floorZ: -100f,
                measuredRootOffset: 0.31f,
                nativeRootZ: -99.7f);

            Assert.Equal(-99.69f, root, 3);
        }

        [Theory]
        [InlineData(float.NaN)]
        [InlineData(-3f)]
        [InlineData(6f)]
        public void CalculateMeasuredRootZ_RejectsInvalidOffsets(float offset)
        {
            const float nativeRoot = -99.7f;
            Assert.Equal(nativeRoot,
                VehiclePlacementMath.CalculateMeasuredRootZ(
                    -100f, offset, nativeRoot));
        }

    }
}
