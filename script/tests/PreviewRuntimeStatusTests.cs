using Xunit;

namespace ALLIN1.Tests
{
    public sealed class PreviewRuntimeStatusTests
    {
        [Theory]
        [InlineData(true, false, false, false, "preview streaming verified")]
        [InlineData(false, true, false, true, "plug-in file installed; preview stream not yet verified")]
        [InlineData(false, false, true, true, "OpenRPF plug-in disabled (fallback active)")]
        [InlineData(false, false, false, true, "ASI loader detected; OpenRPF plug-in missing")]
        [InlineData(false, false, false, false, "ASI loader and OpenRPF plug-in missing")]
        public void DescribesObservedCapabilityWithoutOverclaiming(
            bool streamed, bool plugin, bool disabled, bool asiLoader, string expected)
        {
            Assert.Equal(expected,
                PreviewRuntimeStatus.Describe(streamed, plugin, disabled, asiLoader));
        }
    }
}
