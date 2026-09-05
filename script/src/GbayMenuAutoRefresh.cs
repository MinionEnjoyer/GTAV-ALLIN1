// State-driven refresh policy for the native GBAY compatibility browser.
//
// The browser must never ask the player to refresh ownership or inventory
// screens. This gate bounds polling while forcing an immediate refresh when
// Story Mode changes protagonist or menu context.

using System;
using System.Collections.Generic;

namespace ALLIN1
{
    internal enum GbayMenuRefreshKind
    {
        None,
        Vehicles,
        Weapons,
        Gear,
        Addons,
    }

    internal sealed class GbayMenuAutoRefreshGate
    {
        internal const int PollIntervalMilliseconds = 1500;

        private GbayMenuRefreshKind _kind;
        private int _characterModelHash;
        private int _lastRefreshAt;
        private bool _initialized;

        internal bool ShouldRefresh(
            GbayMenuRefreshKind kind, int characterModelHash,
            int nowMilliseconds)
        {
            if (kind == GbayMenuRefreshKind.None)
            {
                _kind = kind;
                _characterModelHash = characterModelHash;
                _lastRefreshAt = nowMilliseconds;
                _initialized = true;
                return false;
            }

            bool contextChanged = !_initialized || kind != _kind ||
                characterModelHash != _characterModelHash;
            bool cadenceElapsed = _initialized &&
                unchecked((uint)(nowMilliseconds - _lastRefreshAt)) >=
                    PollIntervalMilliseconds;

            _kind = kind;
            _characterModelHash = characterModelHash;
            if (!contextChanged && !cadenceElapsed)
                return false;

            _lastRefreshAt = nowMilliseconds;
            _initialized = true;
            return true;
        }

        internal static bool SameGarageVehicle(
            string expectedModel, string expectedPlate, int expectedModelHash,
            int expectedSlot, string actualModel, string actualPlate,
            int actualModelHash, int actualSlot)
        {
            return expectedSlot == actualSlot &&
                expectedModelHash == actualModelHash &&
                string.Equals(expectedModel ?? "", actualModel ?? "",
                    StringComparison.OrdinalIgnoreCase) &&
                string.Equals((expectedPlate ?? "").Trim(),
                    (actualPlate ?? "").Trim(),
                    StringComparison.OrdinalIgnoreCase);
        }

        internal static int FindAddonSelectionIndex(
            IReadOnlyList<GbayAddonAction> actions,
            string packageId, string route, int fallbackIndex)
        {
            if (actions == null || actions.Count == 0)
                return 0;
            for (int index = 0; index < actions.Count; index++)
            {
                GbayAddonAction action = actions[index];
                if (action != null && string.Equals(
                        action.PackageId, packageId,
                        StringComparison.OrdinalIgnoreCase) &&
                    string.Equals(action.Route, route,
                        StringComparison.Ordinal))
                    return index;
            }
            return Math.Max(0, Math.Min(fallbackIndex, actions.Count - 1));
        }
    }

    internal static class GbayWeaponWorkbenchStatePolicy
    {
        internal const int PreviewMismatchAbortMilliseconds = 1000;

        internal static bool HasExpectedPlayerWeapon(
            bool owned, int expectedWeaponHash, int selectedWeaponHash) =>
            owned && expectedWeaponHash != 0 &&
            selectedWeaponHash == expectedWeaponHash;

        internal static bool ShouldAbortPreviewMismatch(
            bool recoveryAttempted, int mismatchMilliseconds) =>
            recoveryAttempted &&
            mismatchMilliseconds >= PreviewMismatchAbortMilliseconds;
    }

    /// <summary>
    /// Fail-closed identity gate for the expensive live weapon-component
    /// catalog.  A caller may ask to refresh as often as it needs, but an
    /// unchanged request/state token must reuse the already discovered rows.
    /// The token itself is captured by the GTA-facing storefront and includes
    /// the active Story ped, inventory/equip state, ammo, DLC counts, and
    /// content mode.
    /// </summary>
    internal static class GbayWeaponCatalogCachePolicy
    {
        internal static bool ShouldRebuild(
            bool initialized, string cachedWeapon, string requestedWeapon,
            string cachedStateToken, string currentStateToken)
        {
            if (!initialized) return true;
            if (!string.Equals(cachedWeapon ?? "", requestedWeapon ?? "",
                    StringComparison.OrdinalIgnoreCase))
                return true;
            return !string.Equals(cachedStateToken ?? "",
                currentStateToken ?? "", StringComparison.Ordinal);
        }
    }
}
