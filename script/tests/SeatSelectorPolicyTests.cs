using ALLIN1;
using GTA.Math;
using System;
using System.Collections.Generic;
using System.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class SeatSelectorPolicyTests
    {
        [Theory]
        [InlineData(-114627507, "Roof Turret")]
        [InlineData(1254014755, "Bed Turret")]
        public void Mounted_weapon_seat_uses_model_specific_turret_label(
            int modelHash, string expected)
        {
            Assert.Equal(expected, SeatSelector.GetSeatLabel(modelHash, 3));
        }

        [Fact]
        public void Generated_catalog_covers_every_supported_game_and_dlc_vehicle()
        {
            Assert.True(VehicleSeatLayoutCatalog.All.Count >= 900);
            var models = new HashSet<string>(
                VehicleSeatLayoutCatalog.All.Values.Select(item => item.Model),
                StringComparer.OrdinalIgnoreCase);

            foreach (string model in VehicleList.All)
                Assert.Contains(model, models);
            Assert.All(VehicleSeatLayoutCatalog.All.Values,
                item => Assert.True(item.SeatCount >= 1, item.Model));
        }

        [Fact]
        public void High_risk_vehicle_roles_match_rockstar_layout_metadata()
        {
            VehicleSeatLayoutRecord technical = Catalog("technical");
            VehicleSeatLayoutRecord barrage = Catalog("barrage");
            VehicleSeatLayoutRecord insurgent = Catalog("insurgent3");
            VehicleSeatLayoutRecord apc = Catalog("apc");
            VehicleSeatLayoutRecord khanjali = Catalog("khanjali");
            VehicleSeatLayoutRecord valkyrie = Catalog("valkyrie");

            Assert.Equal(3, technical.SeatCount);
            Assert.Equal("Bed Turret", technical.Labels[1]);
            Assert.Equal("Top Turret", barrage.Labels[1]);
            Assert.Equal("Rear Turret", barrage.Labels[2]);
            Assert.Equal("Roof Turret", insurgent.Labels[7]);
            Assert.Equal(3, apc.Turrets.Count);
            Assert.Equal(3, khanjali.Turrets.Count);
            Assert.Equal(3, valkyrie.Turrets.Count);
        }

        [Fact]
        public void Unconventional_non_turret_seats_are_not_mislabeled_as_guns()
        {
            VehicleSeatLayoutRecord limo = Catalog("limo2");
            VehicleSeatLayoutRecord boxville = Catalog("boxville4");
            VehicleSeatLayoutRecord savage = Catalog("savage");

            Assert.Equal(new[] { 3 }, limo.Turrets.OrderBy(index => index));
            Assert.Equal("Left Rear", limo.Labels[1]);
            Assert.Equal("Right Rear", limo.Labels[2]);
            Assert.Empty(boxville.Turrets);
            Assert.Empty(savage.Turrets);
        }

        [Fact]
        public void Catalog_records_seat_and_access_geometry_separately()
        {
            VehicleSeatLayoutRecord caracara = Catalog("caracara");
            VehicleSeatLayoutRecord insurgent = Catalog("insurgent");
            VehicleSeatLayoutRecord dinghy = Catalog("dinghy5");

            Assert.Equal(5, caracara.SeatCount);
            Assert.Equal(4, caracara.DoorCount);
            Assert.Equal(9, insurgent.SeatCount);
            Assert.Equal(4, insurgent.DoorCount);
            Assert.Equal(1, insurgent.HatchCount);
            Assert.Equal(0, dinghy.DoorCount);
        }

        [Fact]
        public void Caracara_turret_uses_authored_external_climb_points()
        {
            var offsets = SeatSelector.GetExternalApproachOffsets(1254014755, 3);

            Assert.NotNull(offsets);
            Assert.Equal(3, offsets.Length);
            Assert.Contains(offsets, point => point.X < 0 && point.Y < 0);
            Assert.Contains(offsets, point => point.X > 0 && point.Y < 0);
            Assert.Equal(3, SeatSelector.GetNativeEntryRequestSeat(
                1254014755, 3, true));
        }

        [Theory]
        [InlineData(1254014755, 0)]
        [InlineData(-114627507, 3)]
        public void Ordinary_and_limo_seats_do_not_use_caracara_staging(
            int modelHash, int seatIndex)
        {
            Assert.Null(SeatSelector.GetExternalApproachOffsets(modelHash, seatIndex));
            Assert.Equal(seatIndex, SeatSelector.GetNativeEntryRequestSeat(
                modelHash, seatIndex, true));
        }

        [Fact]
        public void Caracara_rear_seats_use_authored_door_positions()
        {
            var left = SeatSelector.GetExternalApproachOffsets(1254014755, 1);
            var right = SeatSelector.GetExternalApproachOffsets(1254014755, 2);

            Assert.Single(left);
            Assert.Single(right);
            Assert.Equal(-1.2486f, left[0].X, 4);
            Assert.Equal(-0.1472f, left[0].Y, 4);
            Assert.Equal(1.2244f, right[0].X, 4);
            Assert.Equal(-0.2042f, right[0].Y, 4);
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
        public void Caracara_exposes_cab_and_turret_but_not_unreachable_rear_seats()
        {
            Assert.True(SeatSelector.IsSeatSelectable(1254014755, -1));
            Assert.True(SeatSelector.IsSeatSelectable(1254014755, 0));
            Assert.False(SeatSelector.IsSeatSelectable(1254014755, 1));
            Assert.False(SeatSelector.IsSeatSelectable(1254014755, 2));
            Assert.True(SeatSelector.IsSeatSelectable(1254014755, 3));
            Assert.True(SeatSelector.IsSeatSelectable(0, 1));
        }

        [Fact]
        public void Caracara_sparse_grid_navigation_reaches_the_turret()
        {
            int[] seats = { -1, 0, 3 };
            bool[] available = { true, true, true };

            Assert.Equal(3, SeatSelector.FindNavigationTarget(
                -1, 0, 1, seats, available));
            Assert.Equal(-1, SeatSelector.FindNavigationTarget(
                3, 0, -1, seats, available));
            Assert.Equal(0, SeatSelector.FindNavigationTarget(
                -1, 1, 0, seats, available));
        }

        [Fact]
        public void Sparse_navigation_does_not_select_an_unavailable_turret()
        {
            int[] seats = { -1, 0, 3 };
            bool[] available = { true, true, false };

            Assert.Equal(-1, SeatSelector.FindNavigationTarget(
                -1, 0, 1, seats, available));
        }

        [Fact]
        public void Metadata_preserves_sparse_high_seat_indices()
        {
            Assert.Equal(4, SeatSelector.GetSeatEnumerationPassengerLimit(
                1254014755, 2));
            Assert.Equal(6, SeatSelector.GetSeatEnumerationPassengerLimit(
                123456789, 6));
        }

        [Fact]
        public void Caracara_turret_uses_native_context_entry()
        {
            Assert.True(SeatSelector.ShouldUseNativeContextEntry(
                1254014755, 3));
            Assert.False(SeatSelector.ShouldUseNativeContextEntry(
                1254014755, 0));
            Assert.False(SeatSelector.ShouldUseNativeContextEntry(
                -114627507, 3));
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

        private static VehicleSeatLayoutRecord Catalog(string model)
        {
            return Assert.Single(VehicleSeatLayoutCatalog.All.Values,
                item => string.Equals(item.Model, model,
                    StringComparison.OrdinalIgnoreCase));
        }

    }
}
