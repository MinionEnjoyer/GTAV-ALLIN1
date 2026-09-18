namespace ALLIN1
{
    internal enum GbayWeaponComponentPurchaseReadiness
    {
        Ready,
        PreviewNotActive,
        PreviewPending,
        PreviewRejected,
        PreviewNotConfirmed
    }

    /// <summary>
    /// Pure decisions for the world-space component preview. Keeping these
    /// choices outside the GTA-facing workbench makes focus events idempotent
    /// and keeps a failed streamed model from being attempted repeatedly.
    /// </summary>
    internal static class GbayWeaponPreviewPolicy
    {
        internal static bool IsCurrentComponentPreview(
            int previewComponent, int requestedComponent) =>
            requestedComponent != 0 && previewComponent == requestedComponent;

        internal static bool ShouldRejectModel(
            int model, bool inCdImage, bool valid) =>
            model != 0 && (!inCdImage || !valid);

        internal static bool ShouldWaitForModel(
            int model, bool loaded) => model != 0 && !loaded;

        internal static bool ShouldKeepPendingComponent(
            int pendingComponent, int requestedComponent) =>
            pendingComponent != 0 && pendingComponent == requestedComponent;

        internal static bool HasStreamDeadlineElapsed(
            int now, int deadline) =>
            deadline != 0 && unchecked(now - deadline) >= 0;

        /// <summary>
        /// A component purchase is transactional only after its streamed
        /// in-world preview has attached successfully. A pending or rejected
        /// preview must never reach the money, inventory, or live-ped path.
        /// </summary>
        internal static GbayWeaponComponentPurchaseReadiness
            GetComponentPurchaseReadiness(bool previewOpen,
                int requestedComponent, int previewComponent,
                int pendingComponent, bool rejected)
        {
            if (!previewOpen)
                return GbayWeaponComponentPurchaseReadiness.PreviewNotActive;
            if (requestedComponent == 0)
                return GbayWeaponComponentPurchaseReadiness.PreviewNotConfirmed;
            if (rejected)
                return GbayWeaponComponentPurchaseReadiness.PreviewRejected;
            if (pendingComponent == requestedComponent)
                return GbayWeaponComponentPurchaseReadiness.PreviewPending;
            return previewComponent == requestedComponent
                ? GbayWeaponComponentPurchaseReadiness.Ready
                : GbayWeaponComponentPurchaseReadiness.PreviewNotConfirmed;
        }

        internal static bool RunComponentPurchaseTransaction(
            GbayWeaponComponentPurchaseReadiness readiness,
            System.Func<bool> transaction) =>
            readiness == GbayWeaponComponentPurchaseReadiness.Ready &&
            transaction != null && transaction();
    }
}
