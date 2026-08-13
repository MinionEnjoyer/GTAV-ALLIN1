using ALLIN1;
using System.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class SeatTestToolPolicyTests
    {
        [Fact]
        public void Fast_success_is_a_pass()
        {
            Assert.Equal("pass", SeatTestTool.ClassifyTrial(
                true, "completed", "target_reached", 4500));
        }

        [Fact]
        public void Slow_success_is_retained_as_an_outlier()
        {
            Assert.Equal("slow_success", SeatTestTool.ClassifyTrial(
                true, "completed", "target_reached", 15000));
        }

        [Theory]
        [InlineData("entered_wrong_external_seat", "wrong_seat")]
        [InlineData("preexit_route_blocked", "route_prediction")]
        [InlineData("entry_timeout", "timeout")]
        [InlineData("seat_claimed", "seat_conflict")]
        public void Failures_are_grouped_for_path_refinement(
            string reason, string expected)
        {
            Assert.Equal(expected, SeatTestTool.ClassifyTrial(
                false, "cancelled", reason, 5000));
        }

        [Fact]
        public void A_clean_rollback_is_reported_separately()
        {
            Assert.Equal("rolled_back", SeatTestTool.ClassifyTrial(
                false, "rolled_back", "external_entry_failed", 8000));
        }

        [Fact]
        public void Fleet_covers_known_physical_turrets_and_unconventional_seats()
        {
            string[] fleet = SeatTestTool.GetUnconventionalFleetModels();

            Assert.Contains("limo2", fleet);
            Assert.Contains("caracara", fleet);
            Assert.Contains("technical", fleet);
            Assert.Contains("insurgent3", fleet);
            Assert.Contains("barrage", fleet);
            Assert.Contains("valkyrie", fleet);
            Assert.Contains("dinghy5", fleet);
            Assert.True(fleet.Length >= 25);
            Assert.Equal(fleet.Length, fleet.Distinct().Count());
            foreach (string model in fleet)
                Assert.Contains(model, VehicleList.All);
        }

        [Theory]
        [InlineData("tampa3")]
        [InlineData("speedo4")]
        [InlineData("mule4")]
        [InlineData("avenger")]
        public void Fleet_excludes_remote_driver_weapons_and_interior_consoles(
            string model)
        {
            Assert.DoesNotContain(
                model, SeatTestTool.GetUnconventionalFleetModels());
        }

        [Fact]
        public void Fleet_does_not_call_ordinary_passenger_seats_turrets()
        {
            Assert.Equal("auxiliary interior seats",
                SeatTestTool.GetUnconventionalFleetStationType("boxville4"));
            Assert.Equal("unconventional helicopter passengers",
                SeatTestTool.GetUnconventionalFleetStationType("savage"));
            Assert.Equal("bed turret",
                SeatTestTool.GetUnconventionalFleetStationType("technical3"));
        }
    }
}
