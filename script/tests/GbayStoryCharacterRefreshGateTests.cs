using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GbayStoryCharacterRefreshGateTests
    {
        [Fact]
        public void SupportedProtagonistChangesProduceOneEdgeEach()
        {
            var gate = new GbayStoryCharacterRefreshGate();
            gate.Seed("michael");

            Assert.False(gate.TryBegin("Michael", 1000, out _));
            Assert.True(gate.TryBegin(
                "franklin", 1000, out string franklin));
            Assert.Equal("franklin", franklin);
            gate.Complete(franklin, succeeded: true);
            Assert.False(gate.TryBegin("franklin", 2000, out _));
            Assert.True(gate.TryBegin(
                "trevor", 2000, out string trevor));
            Assert.Equal("trevor", trevor);
        }

        [Fact]
        public void UnsupportedSwitchAnimationDoesNotReplaceLastProtagonist()
        {
            var gate = new GbayStoryCharacterRefreshGate();
            gate.Seed("michael");

            Assert.False(gate.TryBegin("", 1000, out _));
            Assert.False(gate.TryBegin("player_zero", 1000, out _));
            Assert.Equal("michael", gate.CharacterId);
            Assert.False(gate.TryBegin("michael", 1000, out _));
            Assert.True(gate.TryBegin("franklin", 1000, out _));
        }

        [Fact]
        public void FailedRefreshRetriesThrottledThenSuccessDeduplicates()
        {
            var gate = new GbayStoryCharacterRefreshGate();
            gate.Seed("michael");

            Assert.True(gate.TryBegin(
                "franklin", 1000, out string franklin));
            gate.Complete(franklin, succeeded: false);
            Assert.Equal("michael", gate.CharacterId);

            Assert.False(gate.TryBegin("franklin", 1499, out _));
            Assert.True(gate.TryBegin(
                "franklin", 1500, out franklin));
            gate.Complete(franklin, succeeded: true);
            Assert.Equal("franklin", gate.CharacterId);

            Assert.False(gate.TryBegin("franklin", 1501, out _));
            Assert.False(gate.TryBegin("franklin", 10000, out _));
        }
    }
}
