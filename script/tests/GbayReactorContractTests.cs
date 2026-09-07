using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using Newtonsoft.Json.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GbayReactorContractTests
    {
        [Fact]
        public void MissingCatalogArtworkDoesNotInventBundledImageUrls()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly plugin = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "ALLIN1.ReactorBridge.plugin"));
            Type bridge = Assert.Single(plugin.GetTypes(), type =>
                type.FullName == "ALLIN1.ReactorBridge.Allin1ReactorBridge");
            MethodInfo validate = bridge.GetMethod(
                "CatalogArtworkNode",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(validate);

            Assert.Null(validate.Invoke(null, new object[] {
                "missing-test-card", "Missing", "vehicles", "old_dictionary", "missing_test_vehicle", null
            }));
            Assert.Null(validate.Invoke(null, new object[] {
                "unsafe-test-card", "Unsafe", "vehicles", "old_dictionary", "../escape", null
            }));
        }

        [Fact]
        public void OptionalStartupIntentContractFailsClosedAgainstOlderCoreShape()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly plugin = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "ALLIN1.ReactorBridge.plugin"));
            Type adapter = Assert.Single(plugin.GetTypes(), type =>
                type.FullName == "ALLIN1.ReactorBridge.StartupIntentContract");
            MethodInfo capabilityCheck = adapter.GetMethod(
                "HasRequiredMethods",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(capabilityCheck);

            // System.String stands in for a valid older Core type that simply
            // lacks the optional methods. Reflection capability detection must
            // return false rather than binding a MissingMethodException path.
            Assert.False((bool)capabilityCheck.Invoke(
                null, new object[] { typeof(string) }));
            Type currentContract = Assembly.LoadFrom(Path.Combine(
                    packageDirectory,
                    "RageWebUI.Core.dll"))
                .GetType("RageWebUI.Core.PreloadHandoff");
            Assert.NotNull(currentContract);
            Assert.True((bool)capabilityCheck.Invoke(
                null, new object[] { currentContract }));
        }

        [Fact]
        public void OptionalReadinessContractFallsBackWithoutStaticInterfaceBinding()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly plugin = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "ALLIN1.ReactorBridge.plugin"));
            Type adapter = Assert.Single(plugin.GetTypes(), type =>
                type.FullName ==
                    "ALLIN1.ReactorBridge.MenuPresentationReadinessContract");
            MethodInfo resolve = adapter.GetMethod(
                "Resolve", BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(resolve);

            // A valid older handle shape simply lacks the optional method.
            // Resolution must return null so active-is-ready remains usable.
            Assert.Null(resolve.Invoke(null, new object[] { typeof(string) }));

            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            Type currentHandle = core.GetType(
                "ReactorV.Integration.ReactorExtensionHandle",
                throwOnError: true);
            MethodInfo readiness = Assert.IsAssignableFrom<MethodInfo>(
                resolve.Invoke(null, new object[] { currentHandle }));
            Assert.Equal("IsMenuPresentationReady", readiness.Name);
            Assert.Equal(typeof(bool), readiness.ReturnType);
        }

        [Fact]
        public void CoreScriptHasNoStaticReactorAssemblyDependency()
        {
            string[] references = typeof(GbayShop).Assembly
                .GetReferencedAssemblies()
                .Select(value => value.Name)
                .ToArray();

            Assert.DoesNotContain("RageWebUI.Core", references);
            Assert.DoesNotContain("RageWebUI.Script", references);
        }

        [Fact]
        public void VehicleCatalogRequestUsesBoundedPageDefaults()
        {
            var request = new Allin1VehicleCatalogRequest();

            Assert.Equal("all", request.Category);
            Assert.Equal("all", request.Ownership);
            Assert.Equal(1, request.Page);
            Assert.Equal(6, request.PageSize);
            Assert.False(request.FavoritesOnly);
            Assert.True(request.RefreshCatalog);
        }

        [Fact]
        public void OptionalBridgeLoaderFailsClosedWithoutReactorHost()
        {
            IAllin1MenuBridge bridge = GbayReactorBridgeLoader.TryLoad(
                null, out string status);

            Assert.Null(bridge);
            Assert.False(string.IsNullOrWhiteSpace(status));
        }

        [Fact]
        public void PackagedBridgeReportsExactPresentationReadiness()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var lifecycle = Assert.IsAssignableFrom<
                    IAllin1MenuLifecycleBridge>(bridge);
                Assert.True(bridge.Initialize(new PackagedBridgeStorefront()),
                    bridge.Status);
                InvokeHost(core, "SetMenuPresentationHostAvailable", true);

                Assert.True(bridge.TryPresentVehicles(
                    new Allin1VehicleCatalogRequest()));
                Assert.True(bridge.IsMenuActive);
                Assert.False(lifecycle.IsMenuReady);
                Assert.False(bridge.TryPresentVehicles(
                    new Allin1VehicleCatalogRequest()));
                Assert.Empty(Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuDismissals")));

                var presentations = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations"));
                JObject presentation = Assert.IsType<JObject>(
                    Assert.Single(presentations));
                string presentationId =
                    presentation.Value<string>("presentationId");
                Assert.True((bool)InvokeHost(
                    core,
                    "MarkMenuPresentationActive",
                    "allin1.gbay",
                    "home",
                    presentationId,
                    null));
                Assert.False(lifecycle.IsMenuReady);

                Assert.True((bool)InvokeHost(
                    core, "MarkMenuPresentationReady", presentationId));
                Assert.True(lifecycle.IsMenuReady);

                Assert.True(bridge.TryDismissVehicles());
                // A requested close remains logically active until the host
                // acknowledges that exact presentation hidden. This blocks a
                // rapid F9 reopen from racing the compositor hide.
                Assert.True(bridge.IsMenuActive);
                Assert.False(lifecycle.IsMenuReady);
                var dismissals = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuDismissals"));
                Assert.Single(dismissals);
                Assert.NotNull(InvokeHost(
                    core,
                    "AcknowledgeMenuPresentationHidden",
                    presentationId));
                Assert.False(bridge.IsMenuActive);
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgeRefreshesCharacterBoundSnapshotsOncePerEdge()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront();
                Assert.True(bridge.Initialize(storefront), bridge.Status);
                var characterBridge = Assert.IsAssignableFrom<
                    IAllin1StoryCharacterBridge>(bridge);

                storefront.ActiveCharacter = "franklin";
                Assert.True(characterBridge.TryRefreshStoryCharacter(
                    "franklin"), bridge.Status);
                Assert.Equal(2, storefront.DescribeCount);
                Assert.Equal(2, storefront.RefreshRequests.Count);
                Assert.Equal(new[] { false, false },
                    storefront.RefreshRequests);
                Assert.Equal(2, storefront.WeaponBrowseCount);
                Assert.Equal(2, storefront.CustomWeaponBrowseCount);
                Assert.Equal(2, storefront.GearBrowseCount);
                Assert.Equal(2, storefront.GarageBrowseCount);
                JObject garage = DescribeMenu(core, "garage");
                Assert.Contains(garage.Descendants().OfType<JObject>(),
                    node => node["boundParameters"]?.Value<string>("model") ==
                        "franklin_car");

                // A duplicate edge is idempotent and cannot turn the game's
                // per-frame protagonist observation into provider polling.
                Assert.True(characterBridge.TryRefreshStoryCharacter(
                    "FRANKLIN"), bridge.Status);
                Assert.Equal(2, storefront.DescribeCount);
                Assert.Equal(2, storefront.RefreshRequests.Count);
                Assert.Equal(2, storefront.GarageBrowseCount);

                Assert.False(characterBridge.TryRefreshStoryCharacter(
                    "lamar"));
                Assert.Equal(2, storefront.DescribeCount);
                Assert.Equal(2, storefront.GarageBrowseCount);

                storefront.ActiveCharacter = "trevor";
                Assert.True(characterBridge.TryRefreshStoryCharacter(
                    "trevor"), bridge.Status);
                Assert.Equal(3, storefront.DescribeCount);
                Assert.Equal(3, storefront.RefreshRequests.Count);
                Assert.Equal(3, storefront.GarageBrowseCount);
                garage = DescribeMenu(core, "garage");
                Assert.Contains(garage.Descendants().OfType<JObject>(),
                    node => node["boundParameters"]?.Value<string>("model") ==
                        "trevor_car");
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgeSynchronizesEveryGameBackedMenuWithoutManualRefresh()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront();
                Assert.True(bridge.Initialize(storefront), bridge.Status);
                var liveState = Assert.IsAssignableFrom<
                    IAllin1GameStateBridge>(bridge);

                Assert.False(liveState.TrySynchronizeGameState("michael"));
                Assert.Equal(1, storefront.DescribeCount);

                InvokeHost(core, "SetMenuPresentationHostAvailable", true);
                Assert.True(bridge.TryPresentVehicles(
                    new Allin1VehicleCatalogRequest()), bridge.Status);
                JObject queued = Assert.IsType<JObject>(Assert.Single(
                    Assert.IsType<JArray>(InvokeHost(
                        core, "DrainMenuPresentations"))));
                Assert.True((bool)InvokeHost(
                    core, "MarkMenuPresentationActive",
                    "allin1.gbay", "home",
                    queued.Value<string>("presentationId"), null));
                InvokeHost(core, "DrainEvents");

                storefront.RuntimeBalance = 123456;
                storefront.AdditionalGarageVehicles = 1;
                Assert.True(liveState.TrySynchronizeGameState("michael"),
                    bridge.Status);
                JObject stateChanged = Assert.IsType<JObject>(Assert.Single(
                    Assert.IsType<JArray>(InvokeHost(core, "DrainEvents"))));
                Assert.Equal("allin1.gbay",
                    stateChanged.Value<string>("extensionId"));
                Assert.Equal("state.changed",
                    stateChanged.Value<string>("eventId"));
                JObject statePayload = Assert.IsType<JObject>(
                    stateChanged["payload"]);
                Assert.True(statePayload.Value<long>("revision") > 0);
                Assert.Contains("home",
                    statePayload["menus"].Values<string>());
                Assert.Contains("garage",
                    statePayload["menus"].Values<string>());

                foreach (string menuId in new[]
                    { "home", "vehicles", "weapons", "gear" })
                {
                    JObject menu = DescribeMenu(core, menuId);
                    Assert.Contains(menu.Descendants().OfType<JObject>(),
                        node => node.Value<string>("id") == "balance" &&
                            node.Value<string>("value") == "$123,456");
                }
                Assert.Contains(DescribeMenu(core, "garage").Descendants()
                    .OfType<JObject>(), node =>
                        node["boundParameters"]?.Value<string>("model") ==
                            "fixture_1");
                Assert.Contains(DescribeMenu(core, "diagnostics").Descendants()
                    .OfType<JObject>(), node =>
                        node.Value<string>("id") == "session" &&
                        node.Value<string>("value") != "42 seconds");

                foreach (string menuId in new[]
                    {
                        "home", "vehicles", "weapons", "weapons.customize",
                        "gear", "garage", "addons", "diagnostics", "about",
                    })
                {
                    Assert.DoesNotContain(
                        DescribeMenu(core, menuId).Descendants()
                            .OfType<JObject>(),
                        node => new[]
                        {
                            "gbay.refresh", "weapon.customize.refresh",
                            "garage.refresh", "diagnostics.refresh",
                        }.Contains(node.Value<string>("actionId"),
                            StringComparer.Ordinal));
                }
                Assert.All(storefront.RefreshRequests,
                    refresh => Assert.False(refresh));
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgeRoutesWorldEntryToFilteredGarageAndFailsClosed()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront();
                Assert.True(bridge.Initialize(storefront), bridge.Status);
                InvokeHost(core, "SetMenuPresentationHostAvailable", true);

                // Unknown enum values and locations missing from the fresh
                // detached snapshot cannot open an arbitrary or map-backed
                // route.
                Assert.False(bridge.TryPresentGarage(
                    new Allin1GaragePresentationRequest
                    {
                        Location = (Allin1GarageWorldEntryLocation)999,
                    }));
                Assert.False(bridge.TryPresentGarage(
                    new Allin1GaragePresentationRequest
                    {
                        Location =
                            Allin1GarageWorldEntryLocation.VespucciHelipad,
                    }));
                Assert.Empty(Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations")));

                Assert.True(bridge.TryPresentGarage(
                    new Allin1GaragePresentationRequest
                    {
                        Location = Allin1GarageWorldEntryLocation.Harbour,
                    }), bridge.Status);
                var presentations = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations"));
                JObject presentation = Assert.IsType<JObject>(
                    Assert.Single(presentations));
                Assert.Equal("home", presentation.Value<string>("menuId"));
                JObject context = Assert.IsType<JObject>(
                    presentation["context"]);
                Assert.Equal("gbay/garage", context.Value<string>("route"));
                Assert.Equal("garage",
                    context.Value<string>("initialSection"));
                Assert.Equal("harbour",
                    context.Value<string>("initialLocation"));
                Assert.Equal("MY GARAGE", context.Value<string>("section"));

                JObject garage = DescribeMenu(core, "garage");
                JObject locationFilter = garage.Descendants()
                    .OfType<JObject>()
                    .Single(node => node.Value<string>("id") ==
                        "location-filter");
                Assert.Equal("harbour",
                    locationFilter.Value<string>("selectedId"));
                Assert.Contains(garage.Descendants().OfType<JObject>(),
                    node => node["boundParameters"]?.Value<string>("model") ==
                        "dinghy");
                Assert.DoesNotContain(garage.Descendants().OfType<JObject>(),
                    node => node["boundParameters"]?.Value<string>("model") ==
                        "adder");
                Assert.Equal(3, storefront.GarageBrowseCount);
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgePresentsCachedHomeAndCompletesGuardedDelivery()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            string corePath = Path.Combine(packageDirectory, "RageWebUI.Core.dll");
            string pluginPath = Path.Combine(
                packageDirectory, "ALLIN1.ReactorBridge.plugin");
            Assert.True(File.Exists(corePath), "Pinned Reactor Core was not staged.");
            Assert.True(File.Exists(pluginPath), "Packaged Reactor bridge was not staged.");

            Assembly core = Assembly.LoadFrom(corePath);
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(pluginPath);
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront();

                Assert.True(bridge.Initialize(storefront), bridge.Status);
                Assert.Equal(new[] { false }, storefront.RefreshRequests);
                Assert.Equal(1, storefront.DescribeCount);
                Assert.Equal(1, storefront.WeaponBrowseCount);
                Assert.Equal(1, storefront.CustomWeaponBrowseCount);
                Assert.Equal(0, storefront.CustomOptionBrowseCount);
                Assert.Equal(1, storefront.GearBrowseCount);
                Assert.Equal(1, storefront.GarageBrowseCount);

                JObject addons = DescribeMenu(core, "addons");
                JObject addon = addons.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "addon.invoke");
                storefront.AddonResult = Allin1GbayActionResult.Failure(
                    "addon_callback_failed", "Fixture add-on failed.");
                object addonFailure = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "addons",
                    addon.Value<string>("id"), "activate", new JObject(),
                    true, "addon.invoke:fixture-failure");
                Type addonFailureType = addonFailure.GetType();
                Assert.False((bool)addonFailureType.GetProperty("Succeeded")
                    .GetValue(addonFailure));
                Assert.Equal("addon_callback_failed",
                    addonFailureType.GetProperty("ErrorCode")
                        .GetValue(addonFailure));
                Assert.Equal("fixture.package", storefront.AddonPackageId);
                Assert.Equal("fixture:action", storefront.AddonRoute);

                JObject home = DescribeMenu(core, "home");
                Assert.Equal("GBAY", home.Value<string>("label"));
                string[] destinations = home["nodes"]
                    .OfType<JObject>()
                    .Where(node => node.Value<string>("kind") == "submenu")
                    .Select(node => node.Value<string>("label"))
                    .ToArray();
                Assert.Equal(new[]
                {
                    "Vehicles", "Purchase Weapons", "Customize Weapons",
                    "Gear", "My Garage", "Add-ons", "Diagnostics", "About",
                }, destinations);

                JObject about = DescribeMenu(core, "about");
                Assert.Contains(about.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "version" &&
                        node.Value<string>("value") == "0.6.1");
                Assert.Contains(about.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "edition" &&
                        !string.IsNullOrWhiteSpace(node.Value<string>("value")));
                Assert.Contains(about.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "runtime" &&
                        node.Value<string>("value").Contains("ScriptHookVDotNet"));
                Assert.Contains(about.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "creator" &&
                        node.Value<string>("value") == "MinionEnjoyer");
                Assert.Contains(about.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "support" &&
                        node.Value<string>("value") ==
                            "buymeacoffee.com/minionenjoyer");
                JObject supportAction = about.Descendants()
                    .OfType<JObject>()
                    .Single(node => node.Value<string>("actionId") ==
                        "about.support");
                object unconfirmedSupport = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "about",
                    supportAction.Value<string>("id"), "activate",
                    new JObject(), false, null);
                Assert.False((bool)unconfirmedSupport.GetType()
                    .GetProperty("Succeeded").GetValue(unconfirmedSupport));

                JObject diagnostics = DescribeMenu(core, "diagnostics");
                Assert.Contains(diagnostics.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "session" &&
                        node.Value<string>("value") == "42 seconds");
                Assert.Contains(diagnostics.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "runtime-log" &&
                        node.Value<string>("value") ==
                            "scripts/ALLIN1_client.log");
                Assert.Contains(diagnostics.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "map-content" &&
                        node.Value<string>("value") ==
                            "Quarantined for startup stability");
                Assert.DoesNotContain(
                    diagnostics.Descendants().OfType<JObject>(),
                    node => node.Value<string>("actionId") ==
                        "diagnostics.refresh");
                Assert.Equal(1, storefront.DescribeCount);
                Assert.Equal(new[] { false }, storefront.RefreshRequests);
                Assert.Equal(1, storefront.WeaponBrowseCount);
                Assert.Equal(1, storefront.CustomWeaponBrowseCount);
                Assert.Equal(1, storefront.GearBrowseCount);
                Assert.Equal(1, storefront.GarageBrowseCount);
                JObject openLogFolder = diagnostics.Descendants()
                    .OfType<JObject>()
                    .Single(node => node.Value<string>("actionId") ==
                        "diagnostics.open-log-folder");
                object unconfirmedOpenLogFolder = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "diagnostics",
                    openLogFolder.Value<string>("id"), "activate",
                    new JObject(), false, null);
                Assert.True((bool)unconfirmedOpenLogFolder.GetType()
                    .GetProperty("ConfirmationRequired")
                    .GetValue(unconfirmedOpenLogFolder));
                Assert.Equal(0, storefront.OpenRuntimeLogFolderCount);
                object openLogFolderResult = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "diagnostics",
                    openLogFolder.Value<string>("id"), "activate",
                    new JObject(), true,
                    "diagnostics.open-log-folder:fixture-1");
                AssertActionSucceeded(
                    openLogFolderResult, out JToken openLogFolderValue);
                Assert.Equal(1, storefront.OpenRuntimeLogFolderCount);
                Assert.Equal("scripts/ALLIN1_client.log",
                    openLogFolderValue.Value<string>("portablePath"));

                JObject vehicles = DescribeMenu(core, "vehicles");
                JObject vehicleNode = vehicles
                    .Descendants()
                    .OfType<JObject>()
                    .Single(node =>
                        node.Value<string>("kind") == "action" &&
                        node.Value<string>("actionId") == "vehicle.checkout");
                Assert.Equal("adder", vehicleNode["boundParameters"]
                    .Value<string>("model"));
                Assert.Contains("Manufacturer: Truffade",
                    vehicleNode.Value<string>("description"));
                Assert.DoesNotContain(vehicles.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("kind") == "media" &&
                    node.Value<string>("id") == vehicleNode.Value<string>("id") + "-preview");
                Assert.Single(vehicles.Descendants().OfType<JObject>(),
                    node => node.Value<string>("actionId") == "vehicle.favorite");
                JObject vehicleFavorite = vehicles.Descendants()
                    .OfType<JObject>()
                    .Single(node => node.Value<string>("actionId") ==
                        "vehicle.favorite");
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "vehicles",
                    vehicleFavorite.Value<string>("id"), "activate",
                    new JObject(), false, null), out _);
                Assert.True(storefront.VehicleFavorite);
                vehicles = DescribeMenu(core, "vehicles");
                vehicleFavorite = vehicles.Descendants()
                    .OfType<JObject>()
                    .Single(node => node.Value<string>("actionId") ==
                        "vehicle.favorite");
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "vehicles",
                    vehicleFavorite.Value<string>("id"), "activate",
                    new JObject(), false, null), out _);
                Assert.False(storefront.VehicleFavorite);

                InvokeHost(core, "SetMenuPresentationHostAvailable", true);
                Assert.True(bridge.TryPresentVehicles(
                    new Allin1VehicleCatalogRequest()));
                // F9 synchronizes every game-backed projection from the
                // authorized in-memory catalogs. No player refresh or package
                // rescan is involved. The two reversible favorite checks
                // above each rebuilt only the detached vehicle view.
                Assert.Equal(new[] { false, false, false, false },
                    storefront.RefreshRequests);
                Assert.Equal(2, storefront.DescribeCount);
                Assert.Equal(2, storefront.WeaponBrowseCount);
                Assert.Equal(2, storefront.CustomWeaponBrowseCount);
                Assert.Equal(0, storefront.CustomOptionBrowseCount);
                Assert.Equal(2, storefront.GearBrowseCount);
                Assert.Equal(2, storefront.GarageBrowseCount);

                var presentations = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations"));
                JObject presentation = Assert.IsType<JObject>(
                    Assert.Single(presentations));
                Assert.Equal("allin1.gbay",
                    presentation.Value<string>("extensionId"));
                Assert.Equal("home", presentation.Value<string>("menuId"));
                JObject context = Assert.IsType<JObject>(presentation["context"]);
                Assert.Equal("gbay/home", context.Value<string>("route"));
                Assert.Equal("allin1-shell",
                    context.Value<string>("presentationStyle"));
                Assert.Equal("home", context.Value<string>("initialSection"));
                Assert.Equal("GBAY", context.Value<string>("brand"));
                Assert.Equal("HOME", context.Value<string>("section"));
                Assert.False(string.IsNullOrWhiteSpace(
                    context.Value<string>("menuRevision")));

                Assert.True((bool)InvokeHost(
                    core,
                    "MarkMenuPresentationActive",
                    "allin1.gbay",
                    "home",
                    presentation.Value<string>("presentationId"),
                    null));
                Assert.True(bridge.IsMenuActive);

                object checkoutResult = InvokeHost(
                    core,
                    "InvokeMenu",
                    "allin1.gbay",
                    "vehicles",
                    vehicleNode.Value<string>("id"),
                    "activate",
                    new JObject(),
                    false,
                    null);
                AssertActionSucceeded(checkoutResult, out JToken checkoutValue);
                Assert.Equal("refresh", checkoutValue.Value<string>("presentation"));
                Assert.Equal("delivery", checkoutValue.Value<string>("view"));
                Assert.Equal("adder", storefront.Checkout.Model);
                Assert.Equal(1000000, storefront.Checkout.QuotedPrice);

                JObject delivery = DescribeMenu(core, "vehicles");
                Assert.Equal("CHOOSE DELIVERY", delivery.Value<string>("label"));
                JObject destination = delivery
                    .Descendants()
                    .OfType<JObject>()
                    .Single(node =>
                        node.Value<string>("actionId") ==
                            "vehicle.delivery.confirm" &&
                        node["boundParameters"]?.Value<string>("destination") ==
                            "harmony");

                object unconfirmedDelivery = InvokeHost(
                    core,
                    "InvokeMenu",
                    "allin1.gbay",
                    "vehicles",
                    destination.Value<string>("id"),
                    "activate",
                    new JObject(),
                    false,
                    null);
                Assert.True((bool)unconfirmedDelivery.GetType()
                    .GetProperty("ConfirmationRequired")
                    .GetValue(unconfirmedDelivery));
                Assert.Null(storefront.Delivery);

                object unkeyedDelivery = InvokeHost(
                    core,
                    "InvokeMenu",
                    "allin1.gbay",
                    "vehicles",
                    destination.Value<string>("id"),
                    "activate",
                    new JObject(),
                    true,
                    null);
                Assert.False((bool)unkeyedDelivery.GetType()
                    .GetProperty("Succeeded").GetValue(unkeyedDelivery));
                Assert.Null(storefront.Delivery);

                object deliveryResult = InvokeHost(
                    core,
                    "InvokeMenu",
                    "allin1.gbay",
                    "vehicles",
                    destination.Value<string>("id"),
                    "activate",
                    new JObject(),
                    true,
                    "vehicle.delivery:fixture-1");
                AssertActionSucceeded(deliveryResult, out JToken deliveryValue);
                Assert.Equal("refresh", deliveryValue.Value<string>("presentation"));
                Assert.Equal("harmony", storefront.Delivery.DestinationId);
                Assert.Equal("VEHICLES",
                    DescribeMenu(core, "vehicles").Value<string>("label"));

                object searchResult = InvokeHost(
                    core,
                    "InvokeMenu",
                    "allin1.gbay",
                    "vehicles",
                    "search",
                    "set-value",
                    new JObject { ["value"] = "adder" },
                    false,
                    null);
                AssertActionSucceeded(searchResult, out _);
                Assert.Equal(new[]
                    { false, false, false, false, false, false },
                    storefront.RefreshRequests);

                Assert.DoesNotContain(
                    DescribeMenu(core, "home").Descendants()
                        .OfType<JObject>(),
                    node => node.Value<string>("actionId") ==
                        "gbay.refresh");
                int describeCountBeforeSynchronization =
                    storefront.DescribeCount;
                int requestCountBeforeSynchronization =
                    storefront.RefreshRequests.Count;
                var stateBridge = Assert.IsAssignableFrom<
                    IAllin1GameStateBridge>(bridge);
                Assert.True(stateBridge.TrySynchronizeGameState("michael"),
                    bridge.Status);
                Assert.Equal(describeCountBeforeSynchronization + 1,
                    storefront.DescribeCount);
                Assert.Equal(requestCountBeforeSynchronization + 1,
                    storefront.RefreshRequests.Count);
                Assert.All(storefront.RefreshRequests,
                    refresh => Assert.False(refresh));
                Assert.True(storefront.CustomWeaponBrowseCount >= 1);
                Assert.Equal(0, storefront.CustomOptionBrowseCount);

                Assert.True(bridge.TryDismissVehicles());
                CompleteExtensionDismissal(core);
                Assert.False(bridge.IsMenuActive);

                // A native pre-provider F9 is represented by one typed,
                // process-scoped auto-reset intent. The ready ALLIN1
                // extension consumes it once and only presents its default
                // cached menu; no raw input or arbitrary action is replayed.
                string startupIntentName =
                    @"Local\ReactorV.DefaultMenuIntent." +
                    Process.GetCurrentProcess().Id;
                  using (var startupIntent = new EventWaitHandle(
                      false,
                      EventResetMode.AutoReset,
                      startupIntentName))
                  using (var startupIntentClaimed = new EventWaitHandle(
                      false,
                      EventResetMode.AutoReset,
                      @"Local\ReactorV.DefaultMenuIntentClaimed." +
                          Process.GetCurrentProcess().Id))
                  using (var startupIntentActive = new EventWaitHandle(
                      false,
                      EventResetMode.ManualReset,
                      @"Local\ReactorV.DefaultMenuIntentActive." +
                          Process.GetCurrentProcess().Id))
                  using (var startupIntentCancelled = new EventWaitHandle(
                      true,
                      EventResetMode.ManualReset,
                      @"Local\ReactorV.DefaultMenuIntentCancelled." +
                          Process.GetCurrentProcess().Id))
                  {
                      startupIntent.Reset();
                      startupIntentClaimed.Reset();
                      startupIntentCancelled.Reset();
                      startupIntentActive.Set();
                      startupIntent.Set();
                      Assert.True(bridge.TryPresentPendingStartupMenu());
                    Assert.False(bridge.TryPresentPendingStartupMenu());
                }
                presentations = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations"));
                presentation = Assert.IsType<JObject>(
                    Assert.Single(presentations));
                Assert.Equal("allin1.gbay",
                    presentation.Value<string>("extensionId"));
                Assert.Equal("home", presentation.Value<string>("menuId"));
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void StartupIntentSurvivesTransientHostNotReadyThenQueuesOnce()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            int processId = Process.GetCurrentProcess().Id;
            using var intent = new EventWaitHandle(
                false,
                EventResetMode.AutoReset,
                @"Local\ReactorV.DefaultMenuIntent." + processId);
            using var claimed = new EventWaitHandle(
                false,
                EventResetMode.AutoReset,
                @"Local\ReactorV.DefaultMenuIntentClaimed." + processId);
            using var active = new EventWaitHandle(
                false,
                EventResetMode.ManualReset,
                @"Local\ReactorV.DefaultMenuIntentActive." + processId);
            using var cancelled = new EventWaitHandle(
                true,
                EventResetMode.ManualReset,
                @"Local\ReactorV.DefaultMenuIntentCancelled." + processId);
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                Assert.True(bridge.Initialize(new PackagedBridgeStorefront()),
                    bridge.Status);

                intent.Reset();
                claimed.Reset();
                cancelled.Reset();
                active.Set();
                intent.Set();

                // The provider extension exists, but the presentation host is
                // transiently unavailable. Reservation is restored rather
                // than losing the user's early F9.
                Assert.False(bridge.TryPresentPendingStartupMenu());
                InvokeHost(core, "SetMenuPresentationHostAvailable", true);
                Assert.True(bridge.TryPresentPendingStartupMenu());
                Assert.False(bridge.TryPresentPendingStartupMenu());

                var queued = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations"));
                JObject presentation = Assert.IsType<JObject>(
                    Assert.Single(queued));
                Assert.Equal(processId,
                    presentation["context"]!
                        .Value<int>("reactorStartupIntentProcessId"));
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgeMarksOwnedPermanentWeaponsAndDisablesRepurchase()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront
                {
                    WeaponOwned = true,
                };
                Assert.True(bridge.Initialize(storefront), bridge.Status);

                JObject weapons = DescribeMenu(core, "weapons");
                JObject weapon = weapons.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "weapon.purchase");

                Assert.EndsWith("·  OWNED", weapon.Value<string>("label"));
                Assert.False(weapon.Value<bool>("enabled"));
                Assert.Contains("Price: $500",
                    weapon.Value<string>("description"));
                Assert.Contains("Ownership: Owned",
                    weapon.Value<string>("description"));

                object disabledPurchase = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons",
                    weapon.Value<string>("id"), "activate", new JObject(),
                    true, "weapon.purchase:owned-fixture");
                Type disabledType = disabledPurchase.GetType();
                Assert.False((bool)disabledType.GetProperty("Succeeded")
                    .GetValue(disabledPurchase));
                Assert.Equal("menu_node_unavailable", disabledType
                    .GetProperty("ErrorCode").GetValue(disabledPurchase));
                Assert.Null(storefront.WeaponPurchase);

                storefront.WeaponOwned = false;
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons",
                    "search", "set-value", new JObject { ["value"] = "" },
                    false, null), out _);
                weapons = DescribeMenu(core, "weapons");
                weapon = weapons.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "weapon.purchase");
                Assert.DoesNotContain("OWNED", weapon.Value<string>("label"));
                Assert.True(weapon.Value<bool>("enabled"));
                Assert.Contains("Ownership: Available",
                    weapon.Value<string>("description"));

                storefront.WeaponOwned = true;
                storefront.WeaponSmokeProduct = true;
                storefront.WeaponStock = 3;
                storefront.WeaponQuantity = 3;
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons",
                    "search", "set-value", new JObject { ["value"] = "" },
                    false, null), out _);
                weapons = DescribeMenu(core, "weapons");
                weapon = weapons.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "weapon.purchase");
                Assert.DoesNotContain("OWNED", weapon.Value<string>("label"));
                Assert.True(weapon.Value<bool>("enabled"));
                Assert.Contains("Ownership: 3 in stock",
                    weapon.Value<string>("description"));
                Assert.Contains("Quantity: 3",
                    weapon.Value<string>("description"));
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgeExposesGuardedWeaponsGearAndGarageActions()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront();
                Assert.True(bridge.Initialize(storefront), bridge.Status);

                JObject weapons = DescribeMenu(core, "weapons");
                JObject weapon = weapons.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "weapon.purchase");
                JObject weaponFavorite = weapons.Descendants()
                    .OfType<JObject>()
                    .Single(node => node.Value<string>("actionId") ==
                        "weapon.favorite");
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons",
                    weaponFavorite.Value<string>("id"), "activate",
                    new JObject(), false, null), out _);
                Assert.True(storefront.WeaponFavorite);
                weapons = DescribeMenu(core, "weapons");
                weaponFavorite = weapons.Descendants()
                    .OfType<JObject>()
                    .Single(node => node.Value<string>("actionId") ==
                        "weapon.favorite");
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons",
                    weaponFavorite.Value<string>("id"), "activate",
                    new JObject(), false, null), out _);
                Assert.False(storefront.WeaponFavorite);
                Assert.Equal("WEAPON_PISTOL",
                    weapon["boundParameters"].Value<string>("weapon"));
                Assert.Contains("Price: $500",
                    weapon.Value<string>("description"));
                Assert.DoesNotContain(weapons.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("kind") == "media" &&
                    node.Value<string>("id") == weapon.Value<string>("id") + "-preview");
                object weaponResult = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons",
                    weapon.Value<string>("id"), "activate", new JObject(),
                    true, "weapon.purchase:fixture-1");
                AssertActionSucceeded(weaponResult, out JToken weaponValue);
                Assert.Equal("refresh",
                    weaponValue.Value<string>("presentation"));
                Assert.Equal("WEAPON_PISTOL",
                    storefront.WeaponPurchase.WeaponId);
                Assert.Equal(500,
                    storefront.WeaponPurchase.QuotedTotalPrice);

                JObject gear = DescribeMenu(core, "gear");
                JObject gearAction = gear.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "gear.apply");
                Assert.DoesNotContain(gear.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("kind") == "media" &&
                    node.Value<string>("id") == gearAction.Value<string>("id") + "-preview");
                object gearResult = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "gear",
                    gearAction.Value<string>("id"), "activate", new JObject(),
                    true, "gear.apply:fixture-1");
                AssertActionSucceeded(gearResult, out JToken gearValue);
                Assert.Equal("refresh", gearValue.Value<string>("presentation"));
                Assert.Equal("armor_heavy", storefront.GearAction.GearId);
                Assert.Equal("purchase", storefront.GearAction.Operation);
                Assert.Equal(5000, storefront.GearAction.QuotedPrice);

                JObject garage = DescribeMenu(core, "garage");
                JObject locationFilter = garage.Descendants()
                    .OfType<JObject>()
                    .Single(node =>
                        node.Value<string>("id") == "location-filter" &&
                        node.Value<string>("actionId") == "garage.location");
                Assert.Equal("harmony",
                    locationFilter.Value<string>("selectedId"));
                JObject harmonyWaypoint = garage.Descendants()
                    .OfType<JObject>()
                    .Single(node =>
                        node.Value<string>("actionId") ==
                            "garage.waypoint" &&
                        node["boundParameters"]?.Value<string>("location") ==
                            "harmony");
                JObject harmonyStatus = garage.Descendants()
                    .OfType<JObject>()
                    .Single(node =>
                        node.Value<string>("kind") == "status" &&
                        node.Value<string>("id") == "location-harmony");
                Assert.Contains("Active", harmonyStatus.Value<string>("value"));
                Assert.Contains("1/20 used",
                    harmonyStatus.Value<string>("value"));
                Assert.DoesNotContain("not available",
                    harmonyStatus.Value<string>("value"),
                    StringComparison.OrdinalIgnoreCase);
                Assert.Equal("location-waypoint-harmony",
                    harmonyWaypoint.Value<string>("id"));
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    harmonyWaypoint.Value<string>("id"), "activate",
                    new JObject(), false, null), out JToken waypointValue);
                Assert.Equal("refresh",
                    waypointValue.Value<string>("presentation"));
                Assert.Equal("harmony",
                    storefront.GarageWaypoint.LocationId);
                object invalidLocation = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    locationFilter.Value<string>("id"), "set-value",
                    new JObject { ["value"] = "not-a-garage" },
                    false, null);
                Assert.False((bool)invalidLocation.GetType()
                    .GetProperty("Succeeded").GetValue(invalidLocation));

                object harmonyLocation = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    locationFilter.Value<string>("id"), "set-value",
                    new JObject { ["value"] = "harmony" },
                    false, null);
                AssertActionSucceeded(harmonyLocation, out JToken locationValue);
                Assert.Equal("refresh",
                    locationValue.Value<string>("presentation"));
                garage = DescribeMenu(core, "garage");
                Assert.Contains(garage.Descendants().OfType<JObject>(),
                    node => node["boundParameters"]?.Value<string>("model") ==
                        "adder");
                Assert.DoesNotContain(garage.Descendants().OfType<JObject>(),
                    node => node["boundParameters"]?.Value<string>("model") ==
                        "dinghy");
                Assert.Contains(garage.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "interior-mode" &&
                        node.Value<string>("label") == "Fixed interior" &&
                        node.Value<string>("value").Contains(
                            "fixed interior"));

                locationFilter = garage.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("id") == "location-filter");
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    locationFilter.Value<string>("id"), "set-value",
                    new JObject { ["value"] = "all" },
                    false, null), out _);
                garage = DescribeMenu(core, "garage");
                JObject sell = garage.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "garage.sell" &&
                        node["boundParameters"]?.Value<string>("model") ==
                            "adder");
                Assert.Contains(garage.Descendants().OfType<JObject>(),
                    node => node.Value<string>("actionId") ==
                            "garage.retrieve" &&
                        node["boundParameters"]?.Value<string>("model") ==
                            "dinghy");
                Assert.DoesNotContain(garage.Descendants().OfType<JObject>(),
                    node => node.Value<string>("actionId") == "garage.sell" &&
                        node["boundParameters"]?.Value<string>("model") ==
                        "dinghy");
                object unconfirmedSell = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    sell.Value<string>("id"), "activate", new JObject(),
                    false, null);
                Assert.True((bool)unconfirmedSell.GetType()
                    .GetProperty("ConfirmationRequired")
                    .GetValue(unconfirmedSell));
                Assert.Null(storefront.GarageSale);
                object sellResult = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    sell.Value<string>("id"), "activate", new JObject(),
                    true, "garage.sell:fixture-1");
                AssertActionSucceeded(sellResult, out JToken sellValue);
                Assert.Equal("refresh", sellValue.Value<string>("presentation"));
                Assert.Equal("harmony", storefront.GarageSale.LocationId);
                Assert.Equal("adder", storefront.GarageSale.Model);
                Assert.Equal(500000,
                    storefront.GarageSale.QuotedSellPrice);

                garage = DescribeMenu(core, "garage");
                locationFilter = garage.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("id") == "location-filter");
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    locationFilter.Value<string>("id"), "set-value",
                    new JObject { ["value"] = "davis" },
                    false, null), out _);
                garage = DescribeMenu(core, "garage");
                JObject davisStyle = garage.Descendants().OfType<JObject>()
                    .Single(node => node.Value<string>("id") == "davis-style" &&
                        node.Value<string>("actionId") == "garage.customize");
                Assert.Equal("option-0",
                    davisStyle.Value<string>("selectedId"));
                Assert.Equal("davis",
                    davisStyle["boundParameters"].Value<string>("location"));
                Assert.Equal("style",
                    davisStyle["boundParameters"].Value<string>("category"));
                object unkeyedCustomization = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    davisStyle.Value<string>("id"), "set-value",
                    new JObject { ["value"] = "option-1" },
                    true, null);
                Assert.False((bool)unkeyedCustomization.GetType()
                    .GetProperty("Succeeded").GetValue(unkeyedCustomization));
                Assert.Null(storefront.GarageCustomization);
                object customizationResult = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    davisStyle.Value<string>("id"), "set-value",
                    new JObject { ["value"] = "option-1" },
                    true, "garage.customize:fixture-1");
                AssertActionSucceeded(
                    customizationResult, out JToken customizationValue);
                Assert.Equal("refresh",
                    customizationValue.Value<string>("presentation"));
                Assert.Equal("davis",
                    storefront.GarageCustomization.LocationId);
                Assert.Equal("style",
                    storefront.GarageCustomization.CategoryId);
                Assert.Equal("option-0",
                    storefront.GarageCustomization.ExpectedOptionId);
                Assert.Equal("option-1",
                    storefront.GarageCustomization.OptionId);
                garage = DescribeMenu(core, "garage");
                Assert.Equal("option-1", garage.Descendants()
                    .OfType<JObject>().Single(node =>
                        node.Value<string>("id") == "davis-style")
                    .Value<string>("selectedId"));

                JObject recovery = garage.Descendants().OfType<JObject>()
                    .Single(node => node.Value<string>("actionId") ==
                        "garage.recover");
                object unconfirmedRecovery = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    recovery.Value<string>("id"), "activate", new JObject(),
                    false, "garage.recover:fixture-unconfirmed");
                Assert.False((bool)unconfirmedRecovery.GetType()
                    .GetProperty("Succeeded").GetValue(unconfirmedRecovery));
                Assert.Equal(0, storefront.GarageRecoveryCount);
                object recoveryResult = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    recovery.Value<string>("id"), "activate", new JObject(),
                    true, "garage.recover:fixture-1");
                AssertActionSucceeded(recoveryResult, out JToken recoveryValue);
                Assert.Equal("close",
                    recoveryValue.Value<string>("presentation"));
                Assert.Equal(1, storefront.GarageRecoveryCount);

                garage = DescribeMenu(core, "garage");
                locationFilter = garage.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("id") == "location-filter");
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    locationFilter.Value<string>("id"), "set-value",
                    new JObject { ["value"] = "all" },
                    false, null), out _);
                garage = DescribeMenu(core, "garage");
                JObject retrieve = garage.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") == "garage.retrieve");
                object unkeyedRetrieve = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    retrieve.Value<string>("id"), "activate", new JObject(),
                    true, null);
                Assert.False((bool)unkeyedRetrieve.GetType()
                    .GetProperty("Succeeded").GetValue(unkeyedRetrieve));
                Assert.Null(storefront.GarageRetrieval);
                object retrieveResult = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "garage",
                    retrieve.Value<string>("id"), "activate", new JObject(),
                    true, "garage.retrieve:fixture-1");
                AssertActionSucceeded(retrieveResult, out JToken retrieveValue);
                Assert.Equal("close",
                    retrieveValue.Value<string>("presentation"));
                Assert.Equal("harbour",
                    storefront.GarageRetrieval.LocationId);
                Assert.Equal("dinghy", storefront.GarageRetrieval.Model);
                Assert.DoesNotContain(
                    DescribeMenu(core, "garage").Descendants().OfType<JObject>(),
                    node => node["boundParameters"]?.Value<string>("model") ==
                        "dinghy");

                JObject customize = DescribeMenu(core, "weapons.customize");
                Assert.Equal(0, storefront.CustomOptionBrowseCount);
                Assert.DoesNotContain(customize.Descendants().OfType<JObject>(),
                    node => string.Equals(node.Value<string>("label"),
                        "Load owned weapons", StringComparison.Ordinal));
                Assert.Contains(customize.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "owned-weapons" &&
                        node.Value<string>("kind") == "grid");
                Assert.DoesNotContain(customize.Descendants().OfType<JObject>(),
                    node => node.Value<string>("actionId") ==
                        "weapon.customize.refresh");
                Assert.Equal(0, storefront.CustomOptionBrowseCount);

                customize = DescribeMenu(core, "weapons.customize");
                JObject owned = customize.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") ==
                        "weapon.customize.select");
                Assert.Equal("WEAPON_PISTOL",
                    owned["boundParameters"].Value<string>("weapon"));
                Assert.DoesNotContain(customize.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("kind") == "media" &&
                    node.Value<string>("id") == owned.Value<string>("id") + "-preview");
                InvokeHost(core, "SetMenuPresentationHostAvailable", true);
                if (!bridge.IsMenuActive)
                {
                    Assert.True(bridge.TryPresentVehicles(
                        new Allin1VehicleCatalogRequest()));
                    var queued = Assert.IsType<JArray>(
                        InvokeHost(core, "DrainMenuPresentations"));
                    JObject presentation = queued.OfType<JObject>().Last();
                    Assert.True((bool)InvokeHost(core,
                        "MarkMenuPresentationActive", "allin1.gbay", "home",
                        presentation.Value<string>("presentationId"), null));
                }
                object selected = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons.customize",
                    owned.Value<string>("id"), "activate", new JObject(),
                    false, null);
                AssertActionSucceeded(selected, out JToken selectedValue);
                Assert.Equal("refresh",
                    selectedValue.Value<string>("presentation"));
                Assert.Equal("reactor-weapon-workbench",
                    selectedValue.Value<string>("view"));
                Assert.Equal("WEAPON_PISTOL",
                    storefront.WeaponWorkbench.WeaponId);
                Assert.Null(storefront.WeaponCustomization);
                Assert.True(storefront.CustomOptionBrowseCount > 0);
                Assert.NotNull(storefront.WeaponPreview);
                storefront.AmmoStocked = true;
                AssertActionSucceeded(InvokeHost(core, "InvokeMenu", "allin1.gbay",
                    "weapons.customize", "option-group", "set-value",
                    new JObject { ["value"] = "ammo" }, false, null), out _);
                JObject ammoNode = DescribeMenu(core, "weapons.customize").Descendants()
                    .OfType<JObject>().Single(node => node.Value<string>("actionId") ==
                        "weapon.customize.apply");
                Assert.Contains("Status: Fully stocked", ammoNode.Value<string>("description"));
                Assert.Contains("Price: FULL", ammoNode.Value<string>("description"));
                Assert.False(ammoNode.Value<bool>("enabled"));
                Assert.Contains(DescribeMenu(core, "weapons.customize")
                    .Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "world-preview" &&
                        node.Value<string>("value") ==
                            "Active alongside Reactor");
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgeKeepsReactorVisibleWithWorldWeaponPreview()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront();
                Assert.True(bridge.Initialize(storefront), bridge.Status);

                JObject list = DescribeMenu(core, "weapons.customize");
                Assert.Contains(list.Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "owned-weapons");
                Assert.DoesNotContain(list.Descendants().OfType<JObject>(),
                    node => string.Equals(node.Value<string>("label"),
                        "Load owned weapons", StringComparison.Ordinal));
                JObject weapon = list.Descendants().OfType<JObject>().Single(
                    node => node.Value<string>("actionId") ==
                        "weapon.customize.select");
                InvokeHost(core, "SetMenuPresentationHostAvailable", true);
                Assert.True(bridge.TryPresentVehicles(
                    new Allin1VehicleCatalogRequest()));
                var queued = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations"));
                JObject presentation = queued.OfType<JObject>().Last();
                Assert.True((bool)InvokeHost(core,
                    "MarkMenuPresentationActive", "allin1.gbay", "home",
                    presentation.Value<string>("presentationId"), null));
                AssertActionSucceeded(InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons.customize",
                    weapon.Value<string>("id"), "activate", new JObject(),
                    false, null), out JToken handoff);
                Assert.Equal("refresh", handoff.Value<string>("presentation"));
                Assert.Equal("reactor-weapon-workbench",
                    handoff.Value<string>("view"));
                Assert.Equal("WEAPON_PISTOL",
                    storefront.WeaponWorkbench.WeaponId);
                Assert.True(storefront.CustomOptionBrowseCount > 0);
                Assert.Equal(64, storefront.LastCustomOptionPageSize);
                Assert.NotNull(storefront.WeaponPreview);
                JObject menu = DescribeMenu(core, "weapons.customize");
                Assert.Contains(menu.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("actionId") ==
                        "weapon.customize.preview");
                Assert.Contains(menu.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("actionId") ==
                        "weapon.customize.apply");
                Assert.DoesNotContain(menu.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("kind") == "pagination");
                JObject removal = menu.Descendants().OfType<JObject>().Single(node =>
                    node.Value<string>("actionId") == "weapon.customize.apply" &&
                    node["boundParameters"]?.Value<string>("kind") == "component_remove");
                Assert.True(removal.Value<bool>("enabled"));
                Assert.Equal(0, removal["boundParameters"].Value<int>("quotedprice"));
                Assert.Contains("Unequip", removal.Value<string>("label"));
                Assert.EndsWith("-unequip", removal.Value<string>("id"));
                string componentCardId = removal.Value<string>("id").Substring(
                    0, removal.Value<string>("id").Length - "-unequip".Length);
                Assert.Contains(menu.Descendants().OfType<JObject>(), node =>
                    node.Value<string>("id") == componentCardId &&
                    node["boundParameters"]?.Value<string>("kind") == "component");
                object unconfirmed = InvokeHost(core, "InvokeMenu", "allin1.gbay", "weapons.customize",
                    removal.Value<string>("id"), "activate", new JObject(), false, null);
                Assert.Equal("confirmation_required", unconfirmed.GetType().GetProperty("ErrorCode").GetValue(unconfirmed));
                Assert.Null(storefront.WeaponCustomization);
                AssertActionSucceeded(InvokeHost(core, "InvokeMenu", "allin1.gbay", "weapons.customize",
                    removal.Value<string>("id"), "activate", new JObject(), true, "unequip-test-1"), out _);
                Assert.Equal("component_remove", storefront.WeaponCustomization.Kind);
                Assert.Equal(123456, storefront.WeaponCustomization.ComponentHash);
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void FailedWorldPreviewLeavesPopulatedReactorPageVisible()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront
                {
                    ThrowOnWeaponWorkbench = true,
                };
                Assert.True(bridge.Initialize(storefront), bridge.Status);

                InvokeHost(core, "SetMenuPresentationHostAvailable", true);
                Assert.True(bridge.TryPresentVehicles(
                    new Allin1VehicleCatalogRequest()));
                var queued = Assert.IsType<JArray>(
                    InvokeHost(core, "DrainMenuPresentations"));
                JObject presentation = queued.OfType<JObject>().Last();
                Assert.True((bool)InvokeHost(core,
                    "MarkMenuPresentationActive", "allin1.gbay", "home",
                    presentation.Value<string>("presentationId"), null));

                JObject weapon = DescribeMenu(core, "weapons.customize")
                    .Descendants().OfType<JObject>().Single(node =>
                        node.Value<string>("actionId") ==
                            "weapon.customize.select");
                object failed = InvokeHost(
                    core, "InvokeMenu", "allin1.gbay", "weapons.customize",
                    weapon.Value<string>("id"), "activate", new JObject(),
                    false, null);
                Type failedType = failed.GetType();
                Assert.False((bool)failedType.GetProperty("Succeeded")
                    .GetValue(failed));
                Assert.Equal("workbench_failed", failedType
                    .GetProperty("ErrorCode").GetValue(failed));
                Assert.Null(storefront.WeaponWorkbench);
                Assert.Contains(DescribeMenu(core, "weapons.customize")
                    .Descendants().OfType<JObject>(),
                    node => node.Value<string>("id") == "owned-weapons");
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        [Fact]
        public void PackagedBridgePublishesActiveGarageAsOneScrollableCollection()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-package", "scripts", "ReactorV");
            Assembly core = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "RageWebUI.Core.dll"));
            InvokeHost(core, "Reset");
            IAllin1MenuBridge bridge = null;
            try
            {
                Assembly plugin = Assembly.LoadFrom(Path.Combine(
                    packageDirectory, "ALLIN1.ReactorBridge.plugin"));
                Type bridgeType = Assert.Single(plugin.GetTypes(), type =>
                    !type.IsAbstract &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                bridge = (IAllin1MenuBridge)Activator.CreateInstance(bridgeType);
                var storefront = new PackagedBridgeStorefront
                {
                    AdditionalGarageVehicles = 120,
                };
                Assert.True(bridge.Initialize(storefront), bridge.Status);

                JObject garage = DescribeMenu(core, "garage");
                string compact = garage.ToString(Newtonsoft.Json.Formatting.None);
                Assert.True(compact.Length < 60 * 1024, compact.Length.ToString());
                Assert.Equal(121, garage.Descendants().OfType<JObject>().Count(
                    node => node.Value<string>("actionId") == "garage.sell" ||
                        node.Value<string>("actionId") == "garage.retrieve"));
                Assert.DoesNotContain(garage.Descendants().OfType<JObject>(),
                    node => node.Value<string>("kind") == "pagination" ||
                        node.Value<string>("actionId") == "garage.page");
            }
            finally
            {
                bridge?.Dispose();
                InvokeHost(core, "Reset");
            }
        }

        private static JObject DescribeMenu(Assembly core, string menuId)
        {
            var menus = Assert.IsType<JArray>(InvokeHost(
                core, "DescribeMenus", "allin1.gbay", menuId));
            return Assert.IsType<JObject>(Assert.Single(menus));
        }

        private static string CompleteExtensionDismissal(Assembly core)
        {
            var dismissals = Assert.IsType<JArray>(
                InvokeHost(core, "DrainMenuDismissals"));
            JObject dismissal = Assert.IsType<JObject>(
                Assert.Single(dismissals));
            string presentationId = dismissal.Value<string>("presentationId");
            Assert.False(string.IsNullOrWhiteSpace(presentationId));
            Assert.NotNull(InvokeHost(
                core,
                "AcknowledgeMenuPresentationHidden",
                presentationId));

            Type lifecycleType = core.GetType(
                "ReactorV.Integration.ReactorLifecycleStage",
                throwOnError: true);
            object overlayClosed = Enum.Parse(lifecycleType, "OverlayClosed");
            InvokeHost(
                core,
                "NotifyLifecycle",
                overlayClosed,
                new JObject());
            return presentationId;
        }

        private static void AssertActionSucceeded(
            object result, out JToken value)
        {
            Type resultType = result.GetType();
            bool succeeded = (bool)resultType.GetProperty("Succeeded")
                .GetValue(result);
            string errorCode = resultType.GetProperty("ErrorCode")?
                .GetValue(result)?.ToString();
            string errorMessage = resultType.GetProperty("ErrorMessage")?
                .GetValue(result)?.ToString();
            Assert.True(succeeded, (errorCode ?? "unknown") + ": " +
                (errorMessage ?? "unknown"));
            value = Assert.IsAssignableFrom<JToken>(
                resultType.GetProperty("Value").GetValue(result));
        }

        private static object InvokeHost(
            Assembly core, string methodName, params object[] arguments)
        {
            Type host = core.GetType(
                "ReactorV.Integration.ReactorHostApi", throwOnError: true);
            MethodInfo method = host.GetMethods(
                    BindingFlags.Static | BindingFlags.NonPublic)
                .Where(candidate => candidate.Name == methodName)
                .Where(candidate =>
                {
                    ParameterInfo[] parameters = candidate.GetParameters();
                    return parameters.Length >= arguments.Length &&
                        parameters.Skip(arguments.Length).All(parameter =>
                            parameter.IsOptional || parameter.HasDefaultValue);
                })
                .OrderBy(candidate => candidate.GetParameters().Length)
                .FirstOrDefault();
            Assert.NotNull(method);
            ParameterInfo[] selectedParameters = method.GetParameters();
            object[] invokeArguments = new object[selectedParameters.Length];
            Array.Copy(arguments, invokeArguments, arguments.Length);
            for (int index = arguments.Length;
                 index < selectedParameters.Length;
                 index++)
            {
                invokeArguments[index] = selectedParameters[index].DefaultValue;
            }

            return method.Invoke(null, invokeArguments);
        }

        private sealed class PackagedBridgeStorefront :
            IAllin1VehicleStorefront, IAllin1WeaponPreviewStorefront
        {
            private static readonly IReadOnlyList<string> CategoryValues =
                new[] { "all", "super" };
            private static readonly IReadOnlyList<string> WeaponCategoryValues =
                new[] { "all", "pistols" };
            private static readonly IReadOnlyList<string> GearCategoryValues =
                new[] { "all", "protection" };

            public IReadOnlyList<string> Categories => CategoryValues;
            public IReadOnlyList<string> WeaponCategories =>
                WeaponCategoryValues;
            public IReadOnlyList<string> GearCategories => GearCategoryValues;
            internal Allin1VehicleCheckoutRequest Checkout { get; private set; }
            internal Allin1VehicleDeliveryRequest Delivery { get; private set; }
            internal Allin1WeaponPurchaseRequest WeaponPurchase
                { get; private set; }
            internal Allin1WeaponCustomizationApplyRequest WeaponCustomization
                { get; private set; }
            internal Allin1WeaponWorkbenchRequest WeaponWorkbench
                { get; private set; }
            internal Allin1WeaponCustomizationApplyRequest WeaponPreview
                { get; private set; }
            internal int WeaponPreviewCloseCount { get; private set; }
            internal Allin1GearActionRequest GearAction { get; private set; }
            internal Allin1GarageVehicleRequest GarageSale { get; private set; }
            internal Allin1GarageVehicleRequest GarageRetrieval
                { get; private set; }
            internal Allin1GarageCustomizationRequest GarageCustomization
                { get; private set; }
            internal Allin1GarageWaypointRequest GarageWaypoint
                { get; private set; }
            internal int GarageRecoveryCount { get; private set; }
            internal int OpenRuntimeLogFolderCount { get; private set; }
            internal string AddonPackageId { get; private set; }
            internal string AddonRoute { get; private set; }
            internal Allin1GbayActionResult AddonResult { get; set; } =
                Allin1GbayActionResult.Success(
                    "addon_invoked", "Fixture action invoked.");
            internal List<bool> RefreshRequests { get; } = new List<bool>();
            internal List<bool> CustomOptionRefreshRequests
                { get; } = new List<bool>();
            internal int DescribeCount { get; private set; }
            internal int WeaponBrowseCount { get; private set; }
            internal int CustomWeaponBrowseCount { get; private set; }
            internal int CustomOptionBrowseCount { get; private set; }
            internal int LastCustomOptionPageSize { get; private set; }
            internal int GearBrowseCount { get; private set; }
            internal int GarageBrowseCount { get; private set; }
            internal int AdditionalGarageVehicles { get; set; }
            internal string ActiveCharacter { get; set; } = "michael";
            internal int RuntimeBalance { get; set; } = 2500000;
            internal bool VehicleFavorite { get; private set; }
            internal bool WeaponFavorite { get; private set; }
            internal bool WeaponOwned { get; set; }
            internal bool WeaponSmokeProduct { get; set; }
            internal int WeaponStock { get; set; } = 1;
            internal int WeaponQuantity { get; set; } = 1;
            internal bool ThrowOnWeaponWorkbench { get; set; }
            private bool _sold;
            private bool _retrieved;
            private bool _garageRecoveryAvailable = true;
            private string _davisStyle = "option-0";

            public Allin1GbaySnapshot DescribeGbay()
            {
                DescribeCount++;
                return new Allin1GbaySnapshot
                {
                    Balance = RuntimeBalance,
                    OnlineContentEnabled = true,
                    VehicleCount = 1,
                    WeaponCount = 111,
                    GearCount = 11,
                    Version = "0.6.1",
                    SessionSeconds = 41 + DescribeCount,
                    GarageLocation = "Outside",
                    TrafficStatus = "0 managed, 60 FPS",
                    MapContentStatus = "Quarantined for startup stability",
                    ArtworkStatus = "ready",
                    RpfStatus = "ready",
                    RuntimeLogPath = "scripts/ALLIN1_client.log",
                    Addons = new[]
                    {
                        new Allin1GbayAddonListing
                        {
                            PackageId = "fixture.package",
                            Route = "fixture:action",
                            Label = "Fixture action",
                            Description = "A receipt-authorized fixture.",
                        },
                    },
                };
            }

            public Allin1VehicleCatalogPage BrowseVehicles(
                Allin1VehicleCatalogRequest request)
            {
                RefreshRequests.Add(request.RefreshCatalog);
                return new Allin1VehicleCatalogPage
                {
                    Category = request.Category,
                    Search = request.Search,
                    Ownership = request.Ownership,
                    FavoritesOnly = request.FavoritesOnly,
                    Page = 1,
                    PageSize = 6,
                    PageCount = 1,
                    TotalItems = 1,
                    Balance = RuntimeBalance,
                    CatalogRevision = "fixture-v1",
                    Items = new[]
                    {
                        new Allin1VehicleListing
                        {
                            Model = "adder",
                            Name = "Adder",
                            Manufacturer = "Truffade",
                            DisplayName = "Truffade Adder",
                            Category = "super",
                            Storage = "garage",
                            PreviewDictionary = "allin1_vehicles_01",
                            PreviewTexture = "adder",
                            Price = 1000000,
                            Available = true,
                            Owned = string.Equals(
                                ActiveCharacter, "franklin",
                                StringComparison.Ordinal),
                            Favorite = VehicleFavorite,
                        },
                    },
                };
            }

            public Allin1VehicleCheckoutResult BeginVehicleCheckout(
                Allin1VehicleCheckoutRequest request)
            {
                Checkout = request;
                return Allin1VehicleCheckoutResult.Success(
                    "delivery_selection",
                    "Choose a delivery location.",
                    request.Model,
                    request.QuotedPrice,
                    "harmony",
                    new[]
                    {
                        new Allin1VehicleDeliveryOption
                        {
                            Id = "eclipse",
                            Label = "Eclipse Garage",
                            Capacity = 10,
                            Available = false,
                            Compatible = true,
                            Status = "Full (10/10)",
                        },
                        new Allin1VehicleDeliveryOption
                        {
                            Id = "harmony",
                            Label = "Harmony Garage",
                            UsedSlots = 2,
                            Capacity = 20,
                            Available = true,
                            // The directory and waypoint remain available even
                            // when this fixture's interior entry is withheld.
                            EntryAvailable = false,
                            Compatible = true,
                            Status = "2/20 used",
                        },
                    });
            }

            public Allin1VehicleDeliveryResult ConfirmVehicleDelivery(
                Allin1VehicleDeliveryRequest request)
            {
                Delivery = request;
                return Allin1VehicleDeliveryResult.Success(
                    "delivery_dispatched", "Adder sent to Harmony Garage.");
            }

            public bool ToggleVehicleFavorite(string model)
            {
                if (!string.Equals(model, "adder",
                        StringComparison.OrdinalIgnoreCase)) return false;
                VehicleFavorite = !VehicleFavorite;
                return true;
            }

            public Allin1WeaponCatalogPage BrowseWeapons(
                Allin1CatalogRequest request)
            {
                WeaponBrowseCount++;
                return new Allin1WeaponCatalogPage
                {
                    Category = request.Category,
                    Search = request.Search,
                    Ownership = request.Ownership,
                    FavoritesOnly = request.FavoritesOnly,
                    Page = 1,
                    PageCount = 1,
                    TotalItems = 1,
                    Balance = RuntimeBalance,
                    Items = new[]
                    {
                        new Allin1WeaponListing
                        {
                            Id = "WEAPON_PISTOL",
                            DisplayName = "Pistol",
                            Category = "pistols",
                            PreviewDictionary = "allin1_weapon_01",
                            PreviewTexture = "weapon_pistol",
                            UnitPrice = 500,
                            TotalPrice = 500,
                            Quantity = WeaponQuantity,
                            PurchaseAvailable = true,
                            Owned = WeaponOwned,
                            SmokeProduct = WeaponSmokeProduct,
                            Favorite = WeaponFavorite,
                            Stock = WeaponStock,
                            AvailabilityStatus = "Available",
                        },
                    },
                };
            }

            public Allin1GbayActionResult PurchaseWeapon(
                Allin1WeaponPurchaseRequest request)
            {
                WeaponPurchase = request;
                return Allin1GbayActionResult.Success(
                    "weapon_purchased", "Pistol purchased.");
            }

            public bool ToggleWeaponFavorite(string weaponId)
            {
                if (!string.Equals(weaponId, "WEAPON_PISTOL",
                        StringComparison.OrdinalIgnoreCase)) return false;
                WeaponFavorite = !WeaponFavorite;
                return true;
            }

            public Allin1CustomizableWeaponPage BrowseCustomizableWeapons(
                Allin1CatalogRequest request)
            {
                CustomWeaponBrowseCount++;
                return new Allin1CustomizableWeaponPage
                {
                    Category = request.Category,
                    Search = request.Search,
                    Status = "Choose a currently held weapon to customize.",
                    Page = 1,
                    PageCount = 1,
                    TotalItems = 1,
                    Items = new[]
                    {
                        new Allin1CustomizableWeaponListing
                        {
                            Id = "WEAPON_PISTOL",
                            DisplayName = "Pistol",
                            Category = "Pistols",
                            AmmoStatus = "50 rounds · $100",
                            PreviewDictionary = "allin1_weapon_01",
                            PreviewTexture = "weapon_pistol",
                        },
                    },
                };
            }

            internal bool AmmoStocked;
            public Allin1WeaponCustomizationPage BrowseWeaponCustomization(
                string weaponId, string group, int page, int pageSize,
                bool refresh)
            {
                CustomOptionBrowseCount++;
                LastCustomOptionPageSize = pageSize;
                CustomOptionRefreshRequests.Add(refresh);
                var values = new[]
                {
                    new Allin1WeaponCustomizationOptionListing
                    {
                        Kind = "ammo",
                        Label = "Ammunition refill",
                        Detail = AmmoStocked ? "Fully stocked" : "50 rounds",
                        Price = AmmoStocked ? 0 : 100,
                        Active = AmmoStocked,
                    },
                    new Allin1WeaponCustomizationOptionListing
                    {
                        Kind = "component",
                        Label = "Suppressor",
                        Detail = "Muzzle",
                        Price = WeaponCustomization == null ? 750 : 0,
                        ComponentHash = 123456,
                        AttachmentPoint = 5,
                        Owned = WeaponCustomization != null,
                        Active = WeaponCustomization != null,
                    },
                    new Allin1WeaponCustomizationOptionListing
                    {
                        Kind = "tint",
                        Label = "Gold finish",
                        Detail = "Weapon finish",
                        Price = 250,
                        Tint = 2,
                    },
                    new Allin1WeaponCustomizationOptionListing
                    {
                        Kind = "component_remove", Label = "Unequip Suppressor",
                        Detail = "Keep owned attachment", Owned = true, Price = 0,
                        ComponentHash = 123456, AttachmentPoint = 5,
                    },
                    new Allin1WeaponCustomizationOptionListing
                    {
                        Kind = "component_tint",
                        Label = "Livery color 4",
                        Detail = "Active livery color",
                        Price = 150,
                        ComponentHash = 456789,
                        AttachmentPoint = 9,
                        Tint = 3,
                    },
                };
                Allin1WeaponCustomizationOptionListing[] filtered = values
                    .Where(value => group == "all" ||
                        group == "ammo" && value.Kind == "ammo" ||
                        group == "components" && (value.Kind == "component" || value.Kind == "component_remove") ||
                        group == "tints" && value.Kind == "tint" ||
                        group == "livery" && value.Kind == "component_tint")
                    .ToArray();
                return new Allin1WeaponCustomizationPage
                {
                    WeaponId = weaponId,
                    DisplayName = "Pistol",
                    Group = group,
                    Page = 1,
                    PageCount = 1,
                    TotalItems = filtered.Length,
                    Balance = RuntimeBalance,
                    Status = "Compatible options reported by the live GTA runtime.",
                    Items = filtered,
                };
            }

            public Allin1GbayActionResult OpenWeaponWorkbench(
                Allin1WeaponWorkbenchRequest request)
            {
                if (ThrowOnWeaponWorkbench)
                    throw new InvalidOperationException(
                        "Fixture native workbench failure.");
                WeaponWorkbench = request;
                return Allin1GbayActionResult.Success(
                    "workbench_opened", "Native weapon workbench opened.");
            }

            public Allin1GbayActionResult BeginWeaponPreview(
                Allin1WeaponWorkbenchRequest request)
            {
                if (ThrowOnWeaponWorkbench)
                    throw new InvalidOperationException(
                        "Fixture world preview failure.");
                WeaponWorkbench = request;
                return Allin1GbayActionResult.Success(
                    "preview_opened", "World preview opened.");
            }

            public Allin1GbayActionResult PreviewWeaponCustomization(
                Allin1WeaponCustomizationApplyRequest request)
            {
                WeaponPreview = request;
                return Allin1GbayActionResult.Success(
                    "preview_updated", "World preview updated.");
            }

            public Allin1GbayActionResult EndWeaponPreview()
            {
                WeaponPreviewCloseCount++;
                return Allin1GbayActionResult.Success(
                    "preview_closed", "World preview closed.");
            }

            public Allin1GbayActionResult ApplyWeaponCustomization(
                Allin1WeaponCustomizationApplyRequest request)
            {
                WeaponCustomization = request;
                return Allin1GbayActionResult.Success(
                    "weapon_customized", "Weapon option purchased and equipped.");
            }

            public Allin1GearCatalogPage BrowseGear(
                Allin1CatalogRequest request)
            {
                GearBrowseCount++;
                return new Allin1GearCatalogPage
                {
                    Category = request.Category,
                    Page = 1,
                    PageCount = 1,
                    TotalItems = 1,
                    Balance = RuntimeBalance,
                    Items = new[]
                    {
                        new Allin1GearListing
                        {
                            Id = "armor_heavy",
                            DisplayName = "Heavy Armor",
                            Category = "protection",
                            PreviewDictionary = "allin1_gear_01",
                            PreviewTexture = "armor_heavy",
                            Price = 5000,
                            Owned = false,
                            Equipped = false,
                        },
                    },
                };
            }

            public Allin1GbayActionResult ApplyGearAction(
                Allin1GearActionRequest request)
            {
                GearAction = request;
                return Allin1GbayActionResult.Success(
                    "gear_updated", "Heavy Armor purchased.");
            }

            public Allin1GarageSnapshot BrowseGarage()
            {
                GarageBrowseCount++;
                var vehicles = new List<Allin1GarageVehicleListing>();
                if (!_sold)
                {
                    string personalModel = string.Equals(
                        ActiveCharacter, "michael",
                        StringComparison.Ordinal)
                        ? "adder"
                        : ActiveCharacter + "_car";
                    vehicles.Add(new Allin1GarageVehicleListing
                    {
                        LocationId = "harmony",
                        LocationLabel = "Harmony Garage",
                        ListIndex = 0,
                        Model = personalModel,
                        ModelHash = 1234,
                        PlateText = "GBAY",
                        DisplayName = string.Equals(
                            personalModel, "adder",
                            StringComparison.Ordinal)
                            ? "Truffade Adder"
                            : ActiveCharacter + " fixture car",
                        SellPrice = 500000,
                        Sellable = true,
                    });
                }
                if (!_retrieved)
                    vehicles.Add(new Allin1GarageVehicleListing
                    {
                        LocationId = "harbour",
                        LocationLabel = "Harbour",
                        ListIndex = 0,
                        Model = "dinghy",
                        ModelHash = 5678,
                        PlateText = "BOAT",
                        DisplayName = "Nagasaki Dinghy",
                        SellPrice = 10000,
                        Sellable = true,
                        Retrievable = true,
                    });
                for (int index = 1; index <= AdditionalGarageVehicles; index++)
                    vehicles.Add(new Allin1GarageVehicleListing
                    {
                        LocationId = "harmony",
                        LocationLabel = "Harmony Garage",
                        ListIndex = index,
                        Model = "fixture_" + index,
                        ModelHash = 9000 + index,
                        PlateText = "A1" + index,
                        DisplayName = "Fixture vehicle " + index +
                            " with a deliberately descriptive storage label",
                        SellPrice = 1000 + index,
                        Sellable = true,
                    });
                return new Allin1GarageSnapshot
                {
                    ActiveLocationId = "harmony",
                    Locations = new[]
                    {
                        new Allin1VehicleDeliveryOption
                        {
                            Id = "harmony",
                            Label = "Harmony Garage",
                            UsedSlots = 1,
                            Capacity = 20,
                            Available = true,
                            EntryAvailable = true,
                            Compatible = true,
                            Status = "1/20 used",
                            InteriorMode = "fixed",
                            InteriorStatus =
                                "This location uses its finished fixed interior.",
                        },
                        new Allin1VehicleDeliveryOption
                        {
                            Id = "davis",
                            Label = "Davis Auto Shop",
                            UsedSlots = 0,
                            Capacity = 10,
                            Available = true,
                            EntryAvailable = true,
                            Compatible = true,
                            Status = "0/10 used",
                            InteriorMode = "customizable",
                            InteriorStatus =
                                "Appearance options are saved per Story character.",
                        },
                        new Allin1VehicleDeliveryOption
                        {
                            Id = "harbour",
                            Label = "Harbour",
                            UsedSlots = 1,
                            Capacity = 8,
                            Available = true,
                            EntryAvailable = true,
                            Compatible = true,
                            Status = "1/8 used",
                            InteriorMode = "specialized",
                            InteriorStatus =
                                "Outdoor specialized storage; vehicles are retrieved, not sold here.",
                        },
                    },
                    Vehicles = vehicles,
                    EmergencyRecoveryAvailable = _garageRecoveryAvailable,
                    EmergencyRecoveryStatus = _garageRecoveryAvailable
                        ? "A managed garage can be recovered now."
                        : "Use only if a managed garage transition leaves you stuck.",
                    Customization = new Allin1GarageCustomizationSnapshot
                    {
                        LocationId = "davis",
                        LocationLabel = "Davis Auto Shop",
                        Available = true,
                        LivePreview = false,
                        Status = "Changes are saved per character and applied on entry.",
                        Categories = new[]
                        {
                            new Allin1GarageCustomizationCategory
                            {
                                Id = "style",
                                Label = "Style",
                                SelectedOptionId = _davisStyle,
                                Options = new[]
                                {
                                    new Allin1GarageCustomizationOption
                                    {
                                        Id = "option-0",
                                        Label = "Undressed",
                                    },
                                    new Allin1GarageCustomizationOption
                                    {
                                        Id = "option-1",
                                        Label = "Flawless",
                                    },
                                },
                            },
                        },
                    },
                };
            }

            public Allin1GbayActionResult NavigateToGarage(
                Allin1GarageWaypointRequest request)
            {
                GarageWaypoint = request;
                return Allin1GbayActionResult.Success(
                    "waypoint_set", "Route set to Harmony Garage.");
            }

            public Allin1GbayActionResult SellGarageVehicle(
                Allin1GarageVehicleRequest request)
            {
                GarageSale = request;
                _sold = true;
                return Allin1GbayActionResult.Success(
                    "vehicle_sold", "Adder sold.");
            }

            public Allin1GbayActionResult RetrieveGarageVehicle(
                Allin1GarageVehicleRequest request)
            {
                GarageRetrieval = request;
                _retrieved = true;
                return Allin1GbayActionResult.Success(
                    "vehicle_retrieved", "Dinghy retrieved.");
            }

            public Allin1GbayActionResult ApplyGarageCustomization(
                Allin1GarageCustomizationRequest request)
            {
                GarageCustomization = request;
                if (!string.Equals(request.LocationId, "davis",
                        StringComparison.Ordinal) ||
                    !string.Equals(request.CategoryId, "style",
                        StringComparison.Ordinal) ||
                    !string.Equals(request.ExpectedOptionId, _davisStyle,
                        StringComparison.Ordinal) ||
                    !new[] { "option-0", "option-1" }.Contains(
                        request.OptionId, StringComparer.Ordinal))
                    return Allin1GbayActionResult.Failure(
                        "customization_changed", "Fixture rejected stale state.");
                _davisStyle = request.OptionId;
                return Allin1GbayActionResult.Success(
                    "customization_applied", "Davis style updated.");
            }

            public Allin1GbayActionResult EmergencyRecoverGarage()
            {
                GarageRecoveryCount++;
                if (!_garageRecoveryAvailable)
                    return Allin1GbayActionResult.Failure(
                        "recovery_not_needed", "No recovery is needed.");
                _garageRecoveryAvailable = false;
                return Allin1GbayActionResult.Success(
                    "garage_recovered", "Garage state reset.");
            }

            public Allin1GbayActionResult InvokeAddon(
                string packageId, string route)
            {
                AddonPackageId = packageId;
                AddonRoute = route;
                return AddonResult;
            }

            public Allin1GbayActionResult OpenRuntimeLogFolder()
            {
                OpenRuntimeLogFolderCount++;
                return Allin1GbayActionResult.Success(
                    "runtime_log_folder_opened",
                    "The ALLIN1 runtime log folder was opened.");
            }
        }
    }
}
