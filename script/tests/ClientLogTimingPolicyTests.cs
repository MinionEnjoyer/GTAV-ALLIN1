using System.IO;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class ClientLogTimingPolicyTests
    {
        [Theory]
        [InlineData(0, 50, false)]
        [InlineData(50, 50, false)]
        [InlineData(51, 50, true)]
        [InlineData(1000, -1, false)]
        public void Slow_operation_flag_is_strictly_greater_than_threshold(
            long elapsedMilliseconds, long thresholdMilliseconds,
            bool expected)
        {
            Assert.Equal(expected, ClientLog.IsSlowOperation(
                elapsedMilliseconds, thresholdMilliseconds));
        }

        [Fact]
        public void Runtime_log_exposes_a_portable_scripts_path()
        {
            Assert.Equal("scripts/ALLIN1_client.log", ClientLog.PortablePath);
            Assert.Equal("ALLIN1_client.log",
                Path.GetFileName(ClientLog.RuntimePath));
            Assert.DoesNotContain(
                System.Environment.UserName,
                ClientLog.PortablePath,
                System.StringComparison.OrdinalIgnoreCase);
        }
    }
}
