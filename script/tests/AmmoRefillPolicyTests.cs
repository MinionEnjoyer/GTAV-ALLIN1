using Xunit;

namespace ALLIN1.Tests
{
    public sealed class AmmoRefillPolicyTests
    {
        [Fact]
        public void Native_failure_is_not_misreported_as_melee_or_full()
        {
            AmmoCapacityResult result = AmmoRefillPolicy.Evaluate(false, 0, 0);

            Assert.Equal(AmmoCapacityStatus.Unavailable, result.Status);
            Assert.Equal(0, result.RoundsNeeded);
        }

        [Theory]
        [InlineData(false, 6759, 30, 6759)]
        [InlineData(true, 0, 30, 0)]
        [InlineData(true, 6759, 30, 300)]
        [InlineData(true, 241, 40, 241)]
        [InlineData(true, 20, 1, 10)]
        [InlineData(true, 9999, 0, 600)]
        [InlineData(true, 250, 100, 250)]
        public void Refill_target_is_a_bounded_combat_load(
            bool resolved, int nativeMaximum, int clipMaximum, int expected)
        {
            Assert.Equal(expected, AmmoRefillPolicy.ResolveRefillTarget(
                resolved, nativeMaximum, clipMaximum));
        }

        [Theory]
        [InlineData(0, 0, 1, 0)]
        [InlineData(120, 120, 2, 0)]
        [InlineData(140, 120, 2, 0)]
        [InlineData(20, 120, 3, 100)]
        public void Resolved_capacity_is_classified_without_ambiguous_sentinels(
            int current, int maximum, int expected, int rounds)
        {
            AmmoCapacityResult result = AmmoRefillPolicy.Evaluate(true, current, maximum);

            Assert.Equal((AmmoCapacityStatus)expected, result.Status);
            Assert.Equal(rounds, result.RoundsNeeded);
        }

        [Theory]
        [InlineData(241, true, 241, 241)]
        [InlineData(6143, true, 241, 241)]
        [InlineData(1, true, 6143, 1)]
        [InlineData(-4, true, 241, 0)]
        [InlineData(120, false, 0, 120)]
        public void Component_reapplication_preserves_and_clamps_ammo(
            int before, bool resolved, int maximum, int expected)
        {
            Assert.Equal(expected, AmmoRefillPolicy.ClampPreservedAmmo(
                before, resolved, maximum));
        }
    }
}
