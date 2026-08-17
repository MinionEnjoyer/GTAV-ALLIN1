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
    }
}
