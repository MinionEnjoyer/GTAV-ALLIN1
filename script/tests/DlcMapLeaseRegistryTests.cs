using Xunit;

namespace ALLIN1.Tests
{
    public sealed class YachtStreamingPolicyTests
    {
        [Theory]
        [InlineData(false, 899f, true)]
        [InlineData(false, 901f, false)]
        [InlineData(true, 1199f, true)]
        [InlineData(true, 1201f, false)]
        public void YachtStreamingUsesHysteresis(
            bool acquired, float distance, bool expected)
        {
            Assert.Equal(expected, YachtStreamingPolicy.ShouldAcquire(
                acquired, distance, 900f, 1200f));
        }
    }
}
