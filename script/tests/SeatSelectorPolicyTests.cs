using ALLIN1;
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
            Assert.Equal(
                "clipset@veh@technical@turret@rds@enter_exit",
                SeatSelector.GetExternalEntryClipset(1254014755, 3, 0));
            Assert.Equal(
                "clipset@veh@technical@turret@rps@enter_exit",
                SeatSelector.GetExternalEntryClipset(1254014755, 3, 1));
            Assert.Equal(
                "clipset@veh@technical@turret@rear@enter_exit",
                SeatSelector.GetExternalEntryClipset(1254014755, 3, 2));
        }

        [Theory]
        [InlineData(1254014755, 2)]
        [InlineData(-114627507, 3)]
        public void Ordinary_and_limo_seats_do_not_use_caracara_staging(
            int modelHash, int seatIndex)
        {
            Assert.Null(SeatSelector.GetExternalApproachOffsets(modelHash, seatIndex));
            Assert.Null(SeatSelector.GetExternalEntryClipset(modelHash, seatIndex, 0));
        }
    }
}
