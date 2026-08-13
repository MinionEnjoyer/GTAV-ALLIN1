using GTA;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class ProtagonistIdentityTests
    {
        [Theory]
        [InlineData(unchecked((int)PedHash.Michael))]
        [InlineData(unchecked((int)PedHash.Franklin))]
        [InlineData(unchecked((int)PedHash.Trevor))]
        public void Story_protagonists_resolve_to_their_own_identity(int modelHash)
        {
            bool resolved = GbayShop.TryResolveProtagonist(modelHash, out PedHash character);

            Assert.True(resolved);
            Assert.Equal(modelHash, (int)character);
        }

        [Fact]
        public void Unsupported_models_do_not_fall_back_to_michael()
        {
            bool resolved = GbayShop.TryResolveProtagonist(123456789, out PedHash character);

            Assert.False(resolved);
            Assert.Equal(0, (int)character);
        }
    }
}
