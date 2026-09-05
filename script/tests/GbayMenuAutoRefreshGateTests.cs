using Xunit;
using System;
using System.Reflection;

namespace ALLIN1.Tests
{
    public sealed class GbayMenuAutoRefreshGateTests
    {
        [Fact]
        public void RefreshesOnMenuEntryCharacterChangeAndBoundedCadence()
        {
            var gate = new GbayMenuAutoRefreshGate();

            Assert.True(gate.ShouldRefresh(
                GbayMenuRefreshKind.Weapons, 101, 1000));
            Assert.False(gate.ShouldRefresh(
                GbayMenuRefreshKind.Weapons, 101,
                1000 + GbayMenuAutoRefreshGate.PollIntervalMilliseconds - 1));
            Assert.True(gate.ShouldRefresh(
                GbayMenuRefreshKind.Weapons, 101,
                1000 + GbayMenuAutoRefreshGate.PollIntervalMilliseconds));
            Assert.True(gate.ShouldRefresh(
                GbayMenuRefreshKind.Weapons, 202,
                1001 + GbayMenuAutoRefreshGate.PollIntervalMilliseconds));
            Assert.True(gate.ShouldRefresh(
                GbayMenuRefreshKind.Gear, 202,
                1002 + GbayMenuAutoRefreshGate.PollIntervalMilliseconds));
        }

        [Fact]
        public void NonCachedMenusDoNotPollAndReentryRefreshes()
        {
            var gate = new GbayMenuAutoRefreshGate();

            Assert.False(gate.ShouldRefresh(
                GbayMenuRefreshKind.None, 101, 1000));
            Assert.False(gate.ShouldRefresh(
                GbayMenuRefreshKind.None, 202, 5000));
            Assert.True(gate.ShouldRefresh(
                GbayMenuRefreshKind.Vehicles, 202, 5001));
        }

        [Fact]
        public void CadenceRemainsCorrectAcrossGameTimerWrap()
        {
            var gate = new GbayMenuAutoRefreshGate();
            int start = int.MaxValue - 200;

            Assert.True(gate.ShouldRefresh(
                GbayMenuRefreshKind.Gear, 101, start));
            int afterWrap = unchecked(start +
                GbayMenuAutoRefreshGate.PollIntervalMilliseconds);
            Assert.True(gate.ShouldRefresh(
                GbayMenuRefreshKind.Gear, 101, afterWrap));
        }

        [Fact]
        public void GarageIdentityRequiresStableSlotModelHashAndPlate()
        {
            Assert.True(GbayMenuAutoRefreshGate.SameGarageVehicle(
                "metrobus", " BUS 42 ", 123, 4,
                "METROBUS", "bus 42", 123, 4));
            Assert.False(GbayMenuAutoRefreshGate.SameGarageVehicle(
                "metrobus", "BUS 42", 123, 4,
                "metrobus", "BUS 42", 123, 5));
            Assert.False(GbayMenuAutoRefreshGate.SameGarageVehicle(
                "metrobus", "BUS 42", 123, 4,
                "metrobus", "BUS 43", 123, 4));
        }

        [Fact]
        public void AddonRefreshPreservesPackageAndRouteAcrossReordering()
        {
            GbayAddonAction first = Addon("first", "route:a");
            GbayAddonAction selected = Addon("selected", "route:b");
            GbayAddonAction last = Addon("last", "route:c");

            Assert.Equal(2, GbayMenuAutoRefreshGate.FindAddonSelectionIndex(
                new[] { first, last, selected },
                selected.PackageId, selected.Route, fallbackIndex: 1));
            Assert.Equal(1, GbayMenuAutoRefreshGate.FindAddonSelectionIndex(
                new[] { first, last },
                selected.PackageId, selected.Route, fallbackIndex: 1));
            Assert.Equal(0, GbayMenuAutoRefreshGate.FindAddonSelectionIndex(
                Array.Empty<GbayAddonAction>(),
                selected.PackageId, selected.Route, fallbackIndex: 9));
        }

        private static GbayAddonAction Addon(string packageId, string route) =>
            new GbayAddonAction(
                packageId, route, packageId, route, 0, () => { },
                Assembly.GetExecutingAssembly(), 1);

        [Fact]
        public void WeaponWorkbenchFailsClosedForRemovedOrChangedWeapon()
        {
            Assert.True(GbayWeaponWorkbenchStatePolicy.HasExpectedPlayerWeapon(
                owned: true, expectedWeaponHash: 42,
                selectedWeaponHash: 42));
            Assert.False(GbayWeaponWorkbenchStatePolicy.HasExpectedPlayerWeapon(
                owned: false, expectedWeaponHash: 42,
                selectedWeaponHash: 42));
            Assert.False(GbayWeaponWorkbenchStatePolicy.HasExpectedPlayerWeapon(
                owned: true, expectedWeaponHash: 42,
                selectedWeaponHash: 99));

            Assert.False(
                GbayWeaponWorkbenchStatePolicy.ShouldAbortPreviewMismatch(
                    recoveryAttempted: false, mismatchMilliseconds: 5000));
            Assert.False(
                GbayWeaponWorkbenchStatePolicy.ShouldAbortPreviewMismatch(
                    recoveryAttempted: true,
                    mismatchMilliseconds:
                        GbayWeaponWorkbenchStatePolicy
                            .PreviewMismatchAbortMilliseconds - 1));
            Assert.True(
                GbayWeaponWorkbenchStatePolicy.ShouldAbortPreviewMismatch(
                    recoveryAttempted: true,
                    mismatchMilliseconds:
                        GbayWeaponWorkbenchStatePolicy
                            .PreviewMismatchAbortMilliseconds));
        }

        [Fact]
        public void WeaponCatalogReusesIdenticalStateAcrossRefreshRequests()
        {
            Assert.False(GbayWeaponCatalogCachePolicy.ShouldRebuild(
                initialized: true,
                cachedWeapon: "WEAPON_COMBATPISTOL",
                requestedWeapon: "weapon_combatpistol",
                cachedStateToken: "michael|owned|components:42",
                currentStateToken: "michael|owned|components:42"));
        }

        [Fact]
        public void WeaponCatalogInvalidatesForWeaponOrRelevantGameState()
        {
            Assert.True(GbayWeaponCatalogCachePolicy.ShouldRebuild(
                initialized: false,
                cachedWeapon: "",
                requestedWeapon: "WEAPON_COMBATPISTOL",
                cachedStateToken: "",
                currentStateToken: "michael|owned"));
            Assert.True(GbayWeaponCatalogCachePolicy.ShouldRebuild(
                initialized: true,
                cachedWeapon: "WEAPON_PISTOL",
                requestedWeapon: "WEAPON_COMBATPISTOL",
                cachedStateToken: "michael|owned",
                currentStateToken: "michael|owned"));
            Assert.True(GbayWeaponCatalogCachePolicy.ShouldRebuild(
                initialized: true,
                cachedWeapon: "WEAPON_COMBATPISTOL",
                requestedWeapon: "WEAPON_COMBATPISTOL",
                cachedStateToken: "michael|owned|component:1",
                currentStateToken: "franklin|owned|component:1"));
            Assert.True(GbayWeaponCatalogCachePolicy.ShouldRebuild(
                initialized: true,
                cachedWeapon: "WEAPON_COMBATPISTOL",
                requestedWeapon: "WEAPON_COMBATPISTOL",
                cachedStateToken: "michael|owned|component:1",
                currentStateToken: "michael|owned|component:2"));
            Assert.True(GbayWeaponCatalogCachePolicy.ShouldRebuild(
                initialized: true,
                cachedWeapon: "WEAPON_COMBATPISTOL",
                requestedWeapon: "WEAPON_COMBATPISTOL",
                cachedStateToken: "michael|content:0|dlc:80|ammo:30",
                currentStateToken: "michael|content:1|dlc:80|ammo:30"));
            Assert.True(GbayWeaponCatalogCachePolicy.ShouldRebuild(
                initialized: true,
                cachedWeapon: "WEAPON_COMBATPISTOL",
                requestedWeapon: "WEAPON_COMBATPISTOL",
                cachedStateToken: "michael|content:1|dlc:80|ammo:30",
                currentStateToken: "michael|content:1|dlc:81|ammo:30"));
        }
    }
}
