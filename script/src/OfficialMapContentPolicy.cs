namespace ALLIN1
{
    /// <summary>
    /// Player-facing availability for ALLIN1's official destinations.
    ///
    /// These locations use Rockstar DLC IPLs that are registered by both
    /// supported editions and exposed to Story Mode through ALLIN1's verified,
    /// metadata-only garage map bridge. Actual garage entry still validates
    /// both IPL and interior before teleporting, so missing or damaged map
    /// metadata fails closed.
    /// </summary>
    internal static class OfficialMapContentPolicy
    {
        internal const string RuntimeStatus =
            "Verified garage map bridge · loaded on demand";
        internal const string UnknownDestinationStatus =
            "Destination is not recognized by this build";

        internal static bool IsDeliveryDestinationAvailable(int index) =>
            StandaloneMapPack.IsDeliveryDestinationAvailable(index);

        internal static bool IsDeliveryDestinationAvailable(
            int index, bool mapBridgeInstalled) =>
            index >= 0 && index <= 7 &&
            StandaloneMapPack.IsDeliveryDestinationAvailable(
                index, mapBridgeInstalled);

        internal static bool IsWorldPropertyPurchaseAvailable(
            bool alreadyOwned) =>
            IsWorldPropertyPurchaseAvailable(
                alreadyOwned, StandaloneMapPack.IsInstalled);

        internal static bool IsWorldPropertyPurchaseAvailable(
            bool alreadyOwned, bool mapBridgeInstalled) =>
            StandaloneMapPack.IsWorldPropertyPurchaseAvailable(
                alreadyOwned, mapBridgeInstalled);
    }
}
