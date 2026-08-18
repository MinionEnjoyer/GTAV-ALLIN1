using ALLIN1;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class StructuredLogKeyPolicyTests
    {
        [Theory]
        [InlineData("component", "field_component")]
        [InlineData("MESSAGE", "field_message")]
        [InlineData("exception", "field_exception")]
        [InlineData("weapon", "weapon")]
        [InlineData("component_hash", "component_hash")]
        [InlineData("", "field")]
        public void Payload_fields_cannot_overwrite_log_envelope_keys(
            string key, string expected)
        {
            Assert.Equal(expected, StructuredLogKeyPolicy.Normalize(key));
        }
    }
}
