using ALLIN1;
using GTA.Math;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class SeatSelectorPolicyTests
    {
        [Theory]
        [InlineData(-114627507)]
        [InlineData(1254014755)]
        public void Mounted_weapon_seat_is_labeled_turret(int modelHash)
        {
            Assert.Equal("Turret", SeatSelector.GetSeatLabel(modelHash, 3));
        }

        [Fact]
        public void Caracara_turret_uses_authored_external_climb_points()
        {
            var offsets = SeatSelector.GetExternalApproachOffsets(1254014755, 3);

            Assert.NotNull(offsets);
            Assert.Equal(3, offsets.Length);
            Assert.Contains(offsets, point => point.X < 0 && point.Y < 0);
            Assert.Contains(offsets, point => point.X > 0 && point.Y < 0);
            Assert.Equal(-2, SeatSelector.GetNativeEntryRequestSeat(
                1254014755, 3, true));
        }

        [Theory]
        [InlineData(1254014755, 2)]
        [InlineData(-114627507, 3)]
        public void Ordinary_and_limo_seats_do_not_use_caracara_staging(
            int modelHash, int seatIndex)
        {
            Assert.Null(SeatSelector.GetExternalApproachOffsets(modelHash, seatIndex));
            Assert.Equal(seatIndex, SeatSelector.GetNativeEntryRequestSeat(
                modelHash, seatIndex, true));
        }

        [Fact]
        public void Caracara_normal_seats_keep_the_requested_index()
        {
            Assert.Equal(3, SeatSelector.GetNativeEntryRequestSeat(
                1254014755, 3, false));
            Assert.Equal(2, SeatSelector.GetNativeEntryRequestSeat(
                1254014755, 2, true));
        }

        [Fact]
        public void Every_standard_seat_has_a_vehicle_relative_access_point()
        {
            var minimum = new Vector3(-1f, -2f, -0.5f);
            var maximum = new Vector3(1f, 2f, 1f);

            Assert.True(SeatSelector.GetSeatAccessOffsets(
                0, -1, minimum, maximum)[0].X < 0f);
            Assert.True(SeatSelector.GetSeatAccessOffsets(
                0, 0, minimum, maximum)[0].X > 0f);
            Assert.True(SeatSelector.GetSeatAccessOffsets(
                0, 1, minimum, maximum)[0].Y < 0f);
            Assert.True(SeatSelector.GetSeatAccessOffsets(
                0, 2, minimum, maximum)[0].Y < 0f);
        }

        [Fact]
        public void Opposite_side_route_goes_around_vehicle_bounds()
        {
            var minimum = new Vector3(-1f, -2f, -0.5f);
            var maximum = new Vector3(1f, 2f, 1f);
            var route = SeatSelector.BuildLocalExternalRoute(
                new Vector3(-1.8f, 0.7f, 0f),
                new Vector3(1.8f, -0.7f, 0f),
                minimum,
                maximum);

            Assert.True(route.Length >= 4);
            Assert.Contains(route, point =>
                point.Y > maximum.Y || point.Y < minimum.Y);
            Assert.Equal(-1.8f, route[0].X, 3);
            Assert.Equal(1.8f, route[route.Length - 1].X, 3);
        }

        [Fact]
        public void Caracara_turret_plan_ends_at_an_authored_climb_point()
        {
            var minimum = new Vector3(-1.2f, -2.8f, -0.5f);
            var maximum = new Vector3(1.2f, 2.2f, 1.5f);
            Vector3 target = SeatSelector.GetSeatAccessOffsets(
                1254014755, 3, minimum, maximum)[0];
            Vector3 source = SeatSelector.GetSeatAccessOffsets(
                1254014755, -1, minimum, maximum)[0];
            Vector3[] route = SeatSelector.BuildLocalExternalRoute(
                source, target, minimum, maximum);

            Assert.Equal(target.X, route[route.Length - 1].X, 3);
            Assert.Equal(target.Y, route[route.Length - 1].Y, 3);
        }

        [Theory]
        [InlineData(2, 100, 100, 4.0f, "external_route_not_found")]
        [InlineData(0, 1600, 100, 4.0f, "external_route_task_missing")]
        [InlineData(3, 2000, 2600, 4.0f, "external_route_stalled")]
        public void Invalid_external_routes_abort_safely(
            int routeResult,
            int routeElapsedMs,
            int noProgressMs,
            float distance,
            string expected)
        {
            Assert.Equal(expected, SeatSelector.GetExternalRouteAbortReason(
                routeResult, routeElapsedMs, noProgressMs, distance));
        }

        [Theory]
        [InlineData(1, 500, 500, 4.0f)]
        [InlineData(3, 2000, 100, 4.0f)]
        [InlineData(0, 5000, 5000, 0.5f)]
        public void Valid_or_progressing_external_routes_continue(
            int routeResult,
            int routeElapsedMs,
            int noProgressMs,
            float distance)
        {
            Assert.Null(SeatSelector.GetExternalRouteAbortReason(
                routeResult, routeElapsedMs, noProgressMs, distance));
        }

    }
}
