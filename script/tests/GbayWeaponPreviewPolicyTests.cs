using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GbayWeaponPreviewPolicyTests
    {
        [Fact]
        public void SameFocusedComponentDoesNotRestagePreview()
        {
            Assert.True(GbayWeaponPreviewPolicy.IsCurrentComponentPreview(42, 42));
            Assert.False(GbayWeaponPreviewPolicy.IsCurrentComponentPreview(42, 43));
            Assert.False(GbayWeaponPreviewPolicy.IsCurrentComponentPreview(0, 42));
        }

        [Fact]
        public void NonzeroModelFailsClosedWhenNativeMetadataRejectsIt()
        {
            Assert.True(GbayWeaponPreviewPolicy.ShouldRejectModel(7, false, true));
            Assert.True(GbayWeaponPreviewPolicy.ShouldRejectModel(7, true, false));
            Assert.False(GbayWeaponPreviewPolicy.ShouldRejectModel(0, false, false));
            Assert.False(GbayWeaponPreviewPolicy.ShouldRejectModel(7, true, true));
        }

        [Fact]
        public void StreamWaitAndDeadlineAreBoundedIncludingTimerWrap()
        {
            Assert.True(GbayWeaponPreviewPolicy.ShouldWaitForModel(7, false));
            Assert.False(GbayWeaponPreviewPolicy.ShouldWaitForModel(7, true));
            Assert.False(GbayWeaponPreviewPolicy.ShouldWaitForModel(0, false));
            Assert.False(GbayWeaponPreviewPolicy.HasStreamDeadlineElapsed(99, 100));
            Assert.True(GbayWeaponPreviewPolicy.HasStreamDeadlineElapsed(100, 100));
            Assert.True(GbayWeaponPreviewPolicy.HasStreamDeadlineElapsed(
                unchecked(int.MinValue + 5), unchecked(int.MaxValue - 5)));
        }

        [Fact]
        public void RepeatedFocusKeepsTheOriginalPendingDeadline()
        {
            const int component = 72;
            const int originalDeadline = 1500;
            Assert.True(GbayWeaponPreviewPolicy.ShouldKeepPendingComponent(
                component, component));
            Assert.False(GbayWeaponPreviewPolicy.ShouldKeepPendingComponent(
                component, component + 1));
            Assert.True(GbayWeaponPreviewPolicy.HasStreamDeadlineElapsed(
                originalDeadline, originalDeadline));
        }

        [Fact]
        public void ComponentPurchaseRequiresAnAttachedPreview()
        {
            const int component = 72;
            Assert.Equal(GbayWeaponComponentPurchaseReadiness.Ready,
                GbayWeaponPreviewPolicy.GetComponentPurchaseReadiness(
                    true, component, component, 0, false));
            Assert.Equal(GbayWeaponComponentPurchaseReadiness.PreviewPending,
                GbayWeaponPreviewPolicy.GetComponentPurchaseReadiness(
                    true, component, 0, component, false));
            Assert.Equal(GbayWeaponComponentPurchaseReadiness.PreviewRejected,
                GbayWeaponPreviewPolicy.GetComponentPurchaseReadiness(
                    true, component, 0, 0, true));
            Assert.Equal(GbayWeaponComponentPurchaseReadiness.PreviewNotConfirmed,
                GbayWeaponPreviewPolicy.GetComponentPurchaseReadiness(
                    true, component, 0, 0, false));
            Assert.Equal(GbayWeaponComponentPurchaseReadiness.PreviewNotActive,
                GbayWeaponPreviewPolicy.GetComponentPurchaseReadiness(
                    false, component, component, 0, false));
            Assert.Equal(GbayWeaponComponentPurchaseReadiness.PreviewNotConfirmed,
                GbayWeaponPreviewPolicy.GetComponentPurchaseReadiness(
                    true, 0, 0, 0, false));
        }

        [Fact]
        public void PendingOrRejectedPreviewCannotRunPurchaseTransaction()
        {
            int charges = 0;
            int inventoryWrites = 0;
            System.Func<bool> transaction = () =>
            {
                charges++;
                inventoryWrites++;
                return true;
            };

            Assert.False(GbayWeaponPreviewPolicy.RunComponentPurchaseTransaction(
                GbayWeaponComponentPurchaseReadiness.PreviewPending,
                transaction));
            Assert.False(GbayWeaponPreviewPolicy.RunComponentPurchaseTransaction(
                GbayWeaponComponentPurchaseReadiness.PreviewRejected,
                transaction));
            Assert.Equal(0, charges);
            Assert.Equal(0, inventoryWrites);
            Assert.True(GbayWeaponPreviewPolicy.RunComponentPurchaseTransaction(
                GbayWeaponComponentPurchaseReadiness.Ready, transaction));
            Assert.Equal(1, charges);
            Assert.Equal(1, inventoryWrites);
        }
    }
}
