using ALLIN1;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class PoliceTacticsPolicyTests
    {
        [Fact]
        public void Coordination_requires_open_world_wanted_combat_and_a_squad()
        {
            Assert.True(PoliceTacticsPolicy.CanCoordinate(
                true, false, false, 3, true, 4));
            Assert.False(PoliceTacticsPolicy.CanCoordinate(
                true, true, false, 3, true, 4));
            Assert.False(PoliceTacticsPolicy.CanCoordinate(
                true, false, false, 1, true, 4));
            Assert.False(PoliceTacticsPolicy.CanCoordinate(
                true, false, false, 3, true, 2));
        }

        [Theory]
        [InlineData(6, 0.90f, 0, false, (int)PoliceTactic.StackAndRush)]
        [InlineData(5, 0.95f, 0, false, (int)PoliceTactic.DefensiveLine)]
        [InlineData(6, 0.79f, 0, false, (int)PoliceTactic.DefensiveLine)]
        [InlineData(6, 0.90f, 1, false, (int)PoliceTactic.DefensiveLine)]
        [InlineData(4, 0.95f, 0, false, (int)PoliceTactic.DefensiveLine)]
        [InlineData(6, 0.55f, 0, false, (int)PoliceTactic.DefensiveLine)]
        [InlineData(6, 0.90f, 3, false, (int)PoliceTactic.DefensiveLine)]
        [InlineData(6, 0.90f, 0, true, (int)PoliceTactic.DefensiveLine)]
        public void Tactical_advantage_selects_a_coordinated_rush_otherwise_a_line(
            int officers, float healthRatio, int casualties,
            bool playerInVehicle, int expected)
        {
            Assert.Equal((PoliceTactic)expected, PoliceTacticsPolicy.SelectTactic(
                officers, healthRatio, casualties, playerInVehicle));
        }

        [Theory]
        [InlineData(3, 3)]
        [InlineData(4, 4)]
        [InlineData(5, 5)]
        [InlineData(6, 6)]
        public void Stack_waits_for_the_complete_element(
            int squadSize, int expectedReady)
        {
            Assert.Equal(expectedReady,
                PoliceTacticsPolicy.RequiredStackReady(squadSize));
        }

        [Fact]
        public void Stack_releases_together_or_falls_back_when_assembly_fails()
        {
            Assert.False(PoliceTacticsPolicy.ShouldReleaseStack(
                6, 6, 2500));
            Assert.True(PoliceTacticsPolicy.ShouldReleaseStack(
                6, 6, 3000));
            Assert.False(PoliceTacticsPolicy.ShouldReleaseStack(
                5, 6, 9000));
            Assert.True(PoliceTacticsPolicy.ShouldFallbackToLine(
                5, 6, 8000));
            Assert.False(PoliceTacticsPolicy.ShouldFallbackToLine(
                6, 6, 8000));
        }

        [Theory]
        [InlineData(3, 2)]
        [InlineData(4, 3)]
        [InlineData(5, 3)]
        [InlineData(6, 4)]
        public void Firing_line_requires_a_real_majority_before_publishing(
            int squadSize, int expectedReady)
        {
            Assert.Equal(expectedReady,
                PoliceTacticsPolicy.RequiredFiringLineReady(squadSize));
        }

        [Fact]
        public void Firing_line_timeout_never_promotes_zero_ready_officers()
        {
            Assert.False(PoliceTacticsPolicy.ShouldEstablishFiringLine(
                0, 6, 10000));
            Assert.False(PoliceTacticsPolicy.ShouldEstablishFiringLine(
                1, 6, 10000));
            Assert.True(PoliceTacticsPolicy.ShouldAbandonFiringLineFormation(
                1, 6, PoliceTacticsPolicy.FiringLineMaximumWaitMs));
            Assert.False(PoliceTacticsPolicy.ShouldEstablishFiringLine(
                2, 6, PoliceTacticsPolicy.FiringLineMaximumWaitMs));
            Assert.True(PoliceTacticsPolicy.ShouldEstablishFiringLine(
                4, 6, PoliceTacticsPolicy.FiringLineMaximumWaitMs));
        }

        [Theory]
        [InlineData(5.4f, false, true)]
        [InlineData(8f, true, true)]
        [InlineData(8f, false, false)]
        [InlineData(11f, true, false)]
        public void Defensive_formation_accepts_nearby_cover_without_advancing(
            float distance, bool inCover, bool expected)
        {
            Assert.Equal(expected,
                PoliceTacticsPolicy.IsFormationMemberReady(
                    distance, inCover));
        }

        [Fact]
        public void Casualty_collection_point_requires_an_established_rear_zone()
        {
            Assert.True(PoliceTacticsPolicy.CanPublishCasualtyCollectionPoint(
                4, 6, 9f, 31f));
            Assert.False(PoliceTacticsPolicy.CanPublishCasualtyCollectionPoint(
                1, 6, 9f, 31f));
            Assert.False(PoliceTacticsPolicy.CanPublishCasualtyCollectionPoint(
                4, 6, 3f, 31f));
            Assert.False(PoliceTacticsPolicy.CanPublishCasualtyCollectionPoint(
                4, 6, 9f, 20f));
        }

        [Theory]
        [InlineData(4, 0)]
        [InlineData(5, 0)]
        [InlineData(6, 2)]
        public void Rush_keeps_a_bounded_support_element(
            int squadSize, int expectedSupport)
        {
            Assert.Equal(expectedSupport,
                PoliceTacticsPolicy.RushSupportCount(squadSize));
        }

        [Fact]
        public void A_forming_rush_falls_back_after_losing_its_advantage()
        {
            Assert.True(PoliceTacticsPolicy.CanSustainRushAdvantage(
                6, 0.80f, false));
            Assert.False(PoliceTacticsPolicy.CanSustainRushAdvantage(
                4, 0.90f, false));
            Assert.False(PoliceTacticsPolicy.CanSustainRushAdvantage(
                6, 0.50f, false));
            Assert.False(PoliceTacticsPolicy.CanSustainRushAdvantage(
                6, 0.90f, true));
        }

        [Theory]
        [InlineData(true, false, false, 3, true, true, 4, 55f, true)]
        [InlineData(true, false, false, 1, true, true, 4, 55f, false)]
        [InlineData(true, false, false, 3, true, true, 2, 55f, false)]
        [InlineData(true, false, false, 3, true, true, 4, 20f, false)]
        [InlineData(true, false, false, 3, true, true, 4, 111f, false)]
        public void Vehicle_containment_requires_a_viable_arriving_element(
            bool enabled, bool mission, bool cutscene, int wanted,
            bool driveable, bool lawDriver, int occupants, float distance,
            bool expected)
        {
            Assert.Equal(expected,
                PoliceTacticsPolicy.CanStageVehicleContainment(
                    enabled, mission, cutscene, wanted, driveable,
                    lawDriver, occupants, distance));
        }


        [Theory]
        [InlineData(7f, 40f, false, true)]
        [InlineData(7f, 30f, false, false)]
        [InlineData(12f, 45f, true, true)]
        [InlineData(20f, 45f, true, false)]
        [InlineData(7f, 80f, false, false)]
        public void Containment_dismounts_only_on_a_safe_perimeter(
            float distanceToTarget, float distanceToPlayer,
            bool timedOut, bool expected)
        {
            Assert.Equal(expected,
                PoliceTacticsPolicy.CanDismountContainment(
                    distanceToTarget, distanceToPlayer, timedOut));
        }

        [Theory]
        [InlineData(3, 3, 0.90f, false)]
        [InlineData(3, 2, 0.90f, true)]
        [InlineData(6, 4, 0.90f, true)]
        [InlineData(6, 5, 0.50f, true)]
        [InlineData(2, 1, 0.20f, false)]
        public void Damaged_elements_withdraw_instead_of_recycling_losses(
            int initial, int remaining, float healthRatio, bool expected)
        {
            Assert.Equal(expected,
                PoliceTacticsPolicy.ShouldWithdrawDamagedElement(
                    initial, remaining, healthRatio));
        }

        [Theory]
        [InlineData(true, false, false, 4, true, 35f, 0, true)]
        [InlineData(true, false, false, 4, true, 8f, 0, false)]
        [InlineData(true, false, false, 4, true, 71f, 0, false)]
        [InlineData(true, false, false, 4, true, 35f, 5000, false)]
        [InlineData(true, true, false, 4, true, 35f, 0, false)]
        public void Protective_smoke_is_bounded_to_live_open_world_withdrawals(
            bool enabled, bool mission, bool cutscene, int wanted,
            bool throwerReady, float distance, int cooldown, bool expected)
        {
            Assert.Equal(expected,
                PoliceTacticsPolicy.CanDeployProtectiveSmoke(
                    enabled, mission, cutscene, wanted, throwerReady,
                    distance, cooldown));
        }

        [Theory]
        [InlineData(2, 0, 2000, false)]
        [InlineData(2, 1, 2000, false)]
        [InlineData(2, 2, 2000, true)]
        [InlineData(2, 0, 4200, true)]
        [InlineData(0, 0, 0, true)]
        public void Withdrawal_coverer_holds_until_the_moving_element_is_safe(
            int movers, int arrived, int elapsedMs, bool expected)
        {
            Assert.Equal(expected,
                PoliceTacticsPolicy.ShouldReleaseWithdrawalCoverer(
                    movers, arrived, elapsedMs));
        }
    }
}
