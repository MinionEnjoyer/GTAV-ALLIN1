using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using ALLIN1;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using RageWebUI.Core;
using ReactorV.Integration;

namespace ALLIN1.ReactorBridge
{
    /// <summary>
    /// Optional presentation adapter. ALLIN1 remains the authority for every
    /// catalog, receipt, preference, and Story Mode mutation. This assembly
    /// translates detached DTOs into one persistent Reactor GBAY surface.
    /// </summary>
    public sealed class Allin1ReactorBridge :
        IAllin1MenuBridge, IAllin1MenuLifecycleBridge,
        IAllin1StoryCharacterBridge, IAllin1GameStateBridge, IAllin1DrivingHudBridge,
        IReactorExtensionLifecycle
    {
        private const string ExtensionId = "allin1.gbay";
        private const string HomeMenuId = "home";
        private const string VehiclesMenuId = "vehicles";
        private const string HitchesMenuId = "vehicle-hitches";
        private const string WeaponsMenuId = "weapons";
        private const string CustomizeMenuId = "weapons.customize";
        private const string GearMenuId = "gear";
        private const string GarageMenuId = "garage";
        private const string AddonsMenuId = "addons";
        private const string DiagnosticsMenuId = "diagnostics";
        private const string AboutMenuId = "about";
        // Each customization node has a distinct read-only preview companion.
        // Sixty-four options keep the complete per-group scroll list beneath
        // Reactor's 60 KiB menu transport contract, even with bounded labels.
        private const int WeaponCustomizationScrollLimit = 64;
        private const string SupportUrl =
            "https://buymeacoffee.com/minionenjoyer";
        private readonly object _sync = new object();
        private IAllin1VehicleStorefront? _storefront;
        private IReactorExtensionHandle? _handle;
        private IReactorMenuPresentationHandle? _presentation;
        // Resolve the additive readiness member by reflection. Keeping the
        // optional v2 interface out of this assembly's static type graph lets
        // the same bridge load against an older Reactor Core and fall back to
        // the original active-is-ready contract.
        private MethodInfo? _presentationReadyMethod;
        private Allin1VehicleCatalogRequest _request = DefaultRequest();
        private Allin1VehicleCatalogPage? _page;
        private Allin1CatalogRequest _weaponRequest = DefaultCatalogRequest();
        private Allin1WeaponCatalogPage? _weaponPage;
        private Allin1CatalogRequest _customWeaponRequest =
            new Allin1CatalogRequest { Category = "all", Page = 1, PageSize = 64 };
        private Allin1CustomizableWeaponPage? _customWeaponPage;
        private Allin1WeaponCustomizationPage? _customizationPage;
        private string _customizationGroup = "components";
        private Allin1CatalogRequest _gearRequest = DefaultCatalogRequest();
        private Allin1GearCatalogPage? _gearPage;
        private Allin1GarageSnapshot? _garage;
        private string _garageLocation = "all";
        private Allin1VehicleCheckoutResult? _checkout;
        private Allin1GbaySnapshot? _snapshot;
        private long _menuRevision = 1;
        private string _storyCharacterId = "";
        private readonly Dictionary<string, string> _publishedState =
            new Dictionary<string, string>(StringComparer.Ordinal);
        private bool _disposed;

        public bool IsMenuActive
        {
            get
            {
                lock (_sync)
                    return !_disposed && _presentation != null &&
                        _presentation.IsMenuPresented(HomeMenuId);
            }
        }

        public bool IsMenuReady
        {
            get
            {
                lock (_sync)
                {
                    if (_disposed || _presentation == null ||
                        !_presentation.IsMenuPresented(HomeMenuId))
                        return false;

                    // Readiness is an additive Reactor capability. Hosts that
                    // expose only the original logical-presentation contract
                    // retain the previous active-is-ready behavior.
                    if (_presentationReadyMethod == null)
                        return true;
                    try
                    {
                        object? value = _presentationReadyMethod.Invoke(
                            _handle,
                            new object[] { HomeMenuId });
                        return value is bool ready && ready;
                    }
                    catch
                    {
                        // A broken optional capability must fail closed. It is
                        // safer to withhold F9 close than to dismiss a surface
                        // whose exact ready generation cannot be confirmed.
                        return false;
                    }
                }
            }
        }

        public string Status { get; private set; } = "Not initialized.";

        public bool TryPublishDrivingHud(Allin1DrivingHudFrame frame)
        {
            lock (_sync)
            {
                if (_disposed || _handle == null || frame == null ||
                    typeof(ReactorApi).Assembly.GetType("RageWebUI.Core.PassiveHudContract") == null)
                    return false;
                return _handle.TryPublishEvent("hud.frame", new JObject {
                    ["schema"] = 1, ["visible"] = frame.Visible, ["kind"] = "speedometer",
                    ["speed"] = frame.Speed, ["units"] = frame.Units, ["gear"] = frame.Gear,
                    ["manual"] = frame.Manual, ["notice"] = frame.Notice,
                });
            }
        }

        public bool TryRefreshStoryCharacter(string characterId)
        {
            lock (_sync)
            {
                string normalized = (characterId ?? "").Trim()
                    .ToLowerInvariant();
                if (normalized != "michael" && normalized != "franklin" &&
                    normalized != "trevor")
                    return false;
                if (!Available())
                    return false;
                if (string.Equals(_storyCharacterId, normalized,
                        StringComparison.Ordinal))
                    return true;

                try
                {
                    // Build every character-bound value before publishing any
                    // of it. A failed provider call therefore cannot leave
                    // Reactor showing a mixture of two protagonists.
                    Allin1GbaySnapshot snapshot =
                        _storefront!.DescribeGbay();
                    Allin1VehicleCatalogPage page =
                        _storefront.BrowseVehicles(_request);
                    Allin1WeaponCatalogPage weaponPage =
                        _storefront.BrowseWeapons(_weaponRequest);
                    Allin1CustomizableWeaponPage customWeaponPage =
                        _storefront.BrowseCustomizableWeapons(
                            _customWeaponRequest);
                    Allin1GearCatalogPage gearPage =
                        _storefront.BrowseGear(_gearRequest);
                    Allin1GarageSnapshot garage =
                        _storefront.BrowseGarage();

                    StopWeaponPreviewCore();
                    _snapshot = snapshot;
                    _page = page;
                    _request.Page = page.Page;
                    _weaponPage = weaponPage;
                    _weaponRequest.Page = weaponPage.Page;
                    _customWeaponPage = customWeaponPage;
                    _customWeaponRequest.Page = customWeaponPage.Page;
                    _customizationPage = null;
                    _customizationGroup = "components";
                    _gearPage = gearPage;
                    _gearRequest.Page = gearPage.Page;
                    _garage = garage;
                    AdoptGarageDefault(garage, force: true);
                    _checkout = null;
                    _storyCharacterId = normalized;
                    PublishSynchronizedMenus(force: true);
                    Status = "Ready for " + normalized + " (menu revision " +
                        _menuRevision + ").";
                    return true;
                }
                catch (Exception ex)
                {
                    Status = "Character refresh failed: " +
                        ex.GetType().Name + ": " + ex.Message;
                    return false;
                }
            }
        }

        public bool TrySynchronizeGameState(string characterId)
        {
            lock (_sync)
            {
                string normalized = (characterId ?? "").Trim()
                    .ToLowerInvariant();
                if (normalized != "michael" && normalized != "franklin" &&
                    normalized != "trevor")
                    return false;
                if (!Available() || _presentation == null ||
                    !_presentation.IsMenuPresented(HomeMenuId))
                    return false;
                if (!string.Equals(_storyCharacterId, normalized,
                        StringComparison.Ordinal))
                    return TryRefreshStoryCharacter(normalized);
                return TrySynchronizeGameStateCore();
            }
        }

        public bool Initialize(IAllin1VehicleStorefront storefront)
        {
            if (storefront == null) throw new ArgumentNullException(nameof(storefront));
            lock (_sync)
            {
                if (_disposed || _handle != null) return false;
                _storefront = storefront;
                try
                {
                    // Build the detached cache while the extension host is
                    // warming. F9 later presents these descriptors without
                    // disk/catalog/native discovery work.
                    _request.RefreshCatalog = false;
                    _snapshot = storefront.DescribeGbay();
                    _page = storefront.BrowseVehicles(_request);
                    _weaponPage = storefront.BrowseWeapons(_weaponRequest);
                    // Customize Weapons opens ready-to-use. Ownership is
                    // detached from the live ped here and refreshed again for
                    // every presentation; the user never has to press a
                    // redundant "load/check owned weapons" button.
                    _customWeaponPage =
                        storefront.BrowseCustomizableWeapons(
                            _customWeaponRequest);
                    _customWeaponRequest.Page = _customWeaponPage.Page;
                    _gearPage = storefront.BrowseGear(_gearRequest);
                    _garage = storefront.BrowseGarage();
                    AdoptGarageDefault(_garage, force: true);
                    _handle = ReactorApi.RegisterExtension(
                        new ReactorExtensionDescriptor(
                            ExtensionId,
                            "ALLIN1 GBAY",
                            typeof(Allin1ReactorBridge).Assembly
                                .GetName().Version?.ToString() ?? "0.0.0",
                            "ALLIN1's persistent Story Mode marketplace shell.",
                            new[]
                            {
                                "storefront.vehicles",
                                "storefront.delivery",
                                "storefront.weapons",
                                "storefront.gear",
                                "storefront.garage",
                                "storefront.sections",
                                "presentation.passive-hud.v1",
                                ReactorExtensionCapabilities.DefaultF9MenuOwner,
                            }),
                        builder =>
                        {
                            RegisterActions(builder);
                            builder.AddEvent(new ReactorEventDescriptor("hud.frame", "Passive driving readout; no menu or input ownership.", 4096));
                            builder.AddEvent(new ReactorEventDescriptor(
                                "state.changed",
                                "Published after ALLIN1 atomically updates one or more live GBAY menu projections.",
                                2048));
                            builder.AddMenu(BuildHomeMenu(_snapshot));
                            builder.AddMenu(BuildVehiclesMenu(_page));
                            if (_storefront is IAllin1HitchStorefront) builder.AddMenu(BuildHitchesMenu());
                            builder.AddMenu(BuildWeaponsMenu(_weaponPage));
                            builder.AddMenu(BuildCustomizeMenu());
                            builder.AddMenu(BuildGearMenu(_gearPage));
                            builder.AddMenu(BuildGarageMenu(_garage));
                            builder.AddMenu(BuildAddonsMenu(_snapshot));
                            builder.AddMenu(BuildDiagnosticsMenu(_snapshot));
                            builder.AddMenu(BuildAboutMenu(_snapshot));
                            builder.UseLifecycle(this);
                        });
                    _presentation = _handle as IReactorMenuPresentationHandle;
                    if (_presentation == null)
                    {
                        _handle.Dispose();
                        _handle = null;
                        Status = "Reactor V is missing the menu-presentation " +
                            "contract required by this ALLIN1 build. Update Reactor V.";
                        ClearState();
                        return false;
                    }
                    _presentationReadyMethod =
                        MenuPresentationReadinessContract.Resolve(
                            _handle.GetType());
                    Status = "Ready (menu revision " + _menuRevision +
                        ", catalog " + (_page.CatalogRevision ?? "unknown") + ").";
                    return true;
                }
                catch (Exception ex)
                {
                    Status = ex.GetType().Name + ": " + ex.Message;
                    _handle?.Dispose();
                    _handle = null;
                    _presentation = null;
                    _presentationReadyMethod = null;
                    ClearState();
                    return false;
                }
            }
        }

        public bool TryPresentVehicles(Allin1VehicleCatalogRequest request)
        {
            return TryPresentVehiclesCore(request, startupIntentProcessId: null);
        }

        public bool TryPresentGarage(Allin1GaragePresentationRequest request)
        {
            lock (_sync)
            {
                if (_disposed || _handle == null || _presentation == null ||
                    _storefront == null || request == null ||
                    !TryResolveWorldEntryLocation(
                        request.Location, out string locationId))
                {
                    Status = "That world-entry garage route is unavailable.";
                    return false;
                }

                // A presentation edge synchronizes every detached projection,
                // so this garage and all sibling menus start from current game
                // state without asking the player to refresh anything.
                if (!TrySynchronizeGameStateCore())
                    return false;
                Allin1GarageSnapshot garage = _garage!;
                Allin1VehicleDeliveryOption? location =
                    (garage.Locations ??
                        Array.Empty<Allin1VehicleDeliveryOption>())
                    .FirstOrDefault(value => value != null &&
                        string.Equals(value.Id, locationId,
                            StringComparison.OrdinalIgnoreCase));
                // BrowseGarage.Available means that this location can be
                // browsed and waypointed. World-entry presentation retains
                // the stricter map-delivery gate independently.
                if (location == null || !location.EntryAvailable)
                {
                    Status = "That garage location is not available in the " +
                        "current ALLIN1 session.";
                    return false;
                }

                _garage = garage;
                _garageLocation = locationId;
                UpdateMenu(BuildGarageMenu(_garage));
                var context = new JObject
                {
                    ["route"] = "gbay/garage",
                    ["presentationStyle"] = "allin1-shell",
                    ["initialSection"] = GarageMenuId,
                    ["initialLocation"] = locationId,
                    ["brand"] = "GBAY",
                    ["section"] = "MY GARAGE",
                    ["menuRevision"] = RevisionText(),
                };
                bool presented = _presentation.TryPresentMenu(
                    HomeMenuId, context);
                Status = presented
                    ? "My Garage opened at " + location.Label + "."
                    : "Reactor overlay host is not ready.";
                return presented;
            }
        }

        public bool TryPresentWeaponCustomization()
        {
            lock (_sync)
            {
                if (_disposed || _handle == null || _presentation == null ||
                    _storefront == null)
                    return false;
                StopWeaponPreviewCore();
                _customizationPage = null;
                _customizationGroup = "components";
                if (!TrySynchronizeGameStateCore())
                    return false;
                UpdateMenu(BuildCustomizeMenu());
                var context = new JObject
                {
                    ["route"] = "gbay/weapons/customize",
                    ["presentationStyle"] = "allin1-shell",
                    ["initialSection"] = CustomizeMenuId,
                    ["brand"] = "GBAY",
                    ["section"] = "CUSTOMIZE WEAPONS",
                    ["menuRevision"] = RevisionText(),
                };
                bool presented = _presentation.TryPresentMenu(
                    HomeMenuId, context);
                Status = presented
                    ? "Returned to Customize Weapons."
                    : "Reactor overlay host is not ready.";
                return presented;
            }
        }

        private bool TryPresentVehiclesCore(
            Allin1VehicleCatalogRequest request,
            int? startupIntentProcessId)
        {
            lock (_sync)
            {
                if (_disposed || _handle == null || _presentation == null ||
                    _storefront == null || _page == null)
                    return false;
                // Presentation is open-only. Closing has its own typed path;
                // a stale open decision must never turn into an unreported
                // close if another caller wins the lifecycle race.
                if (_presentation.IsMenuPresented(HomeMenuId))
                {
                    Status = "GBAY is already presented or is finishing a transition.";
                    return false;
                }

                // Synchronize all game-backed projections on the presentation
                // edge. The vehicle catalog remains the authorized in-memory
                // catalog; this performs no package/RPF discovery.
                _checkout = null;
                StopWeaponPreviewCore();
                _customizationPage = null;
                if (!TrySynchronizeGameStateCore())
                    return false;
                var context = new JObject
                {
                    ["route"] = "gbay/home",
                    ["presentationStyle"] = "allin1-shell",
                    ["initialSection"] = "home",
                    ["brand"] = "GBAY",
                    ["section"] = "HOME",
                    ["catalogRevision"] = _page.CatalogRevision,
                    ["menuRevision"] = RevisionText(),
                };
                if (startupIntentProcessId.HasValue)
                {
                    context["reactorStartupIntentProcessId"] =
                        startupIntentProcessId.Value;
                }
                bool presented = _presentation.TryPresentMenu(HomeMenuId, context);
                Status = presented
                    ? "GBAY presented from cached menu revision " + _menuRevision + "."
                    : "Reactor overlay host is not ready.";
                return presented;
            }
        }

        /// <summary>
        /// Converts one native bootstrap F9 intent into the normal cached
        /// ALLIN1 home presentation, but only after this extension is fully
        /// registered and Reactor has completed the process-scoped ownership
        /// handoff. No key identity or arbitrary browser action is replayed.
        /// </summary>
        public bool TryPresentPendingStartupMenu()
        {
            lock (_sync)
            {
                if (_disposed || _handle == null || _presentation == null ||
                    _storefront == null || _page == null ||
                    _presentation.IsMenuPresented(HomeMenuId))
                    return false;

                int processId = Process.GetCurrentProcess().Id;
                if (!StartupIntentContract.IsAvailable ||
                    !StartupIntentContract.ManagedOwnsF9(processId) ||
                    !StartupIntentContract.TryConsume(processId))
                {
                    if (!StartupIntentContract.IsAvailable)
                    {
                        Status = "This Reactor V build does not expose the " +
                            "optional startup-intent contract; normal GBAY F9 remains available.";
                    }
                    return false;
                }

                bool presented = TryPresentVehiclesCore(
                    new Allin1VehicleCatalogRequest(), processId);
                if (!presented)
                    StartupIntentContract.TryRestore(processId);
                Status = presented
                    ? "GBAY queued from the native startup intent."
                    : "Reactor was not ready to queue GBAY; the bounded startup " +
                        "intent remains available unless the user cancelled it.";
                return presented;
            }
        }

        public bool TryCancelPendingStartupMenu()
        {
            lock (_sync)
            {
                if (_disposed || !StartupIntentContract.IsAvailable)
                    return false;
                int processId = Process.GetCurrentProcess().Id;
                if (!StartupIntentContract.IsActive(processId) ||
                    !StartupIntentContract.TryCancel(processId))
                    return false;

                _presentation?.TryDismissMenu(HomeMenuId);
                StartupIntentContract.TrySignalBootstrapClose(processId);
                ResetHiddenCheckout();
                Status = "Startup GBAY request cancelled.";
                return true;
            }
        }

        public bool TryDismissVehicles()
        {
            lock (_sync)
            {
                if (_disposed || _presentation == null ||
                    !_presentation.IsMenuPresented(HomeMenuId))
                    return false;
                bool dismissed = _presentation.TryDismissMenu(HomeMenuId);
                if (dismissed)
                    StopWeaponPreviewCore();
                ResetHiddenCheckout();
                Status = dismissed ? "GBAY dismissed."
                    : "Reactor could not dismiss GBAY.";
                return dismissed;
            }
        }

        public void OnLifecycle(ReactorLifecycleContext context)
        {
            if (context == null) return;
            lock (_sync)
            {
                if (context.Stage == ReactorLifecycleStage.OverlayClosed)
                {
                    StopWeaponPreviewCore();
                    ResetHiddenCheckout();
                    Status = "GBAY closed.";
                }
                else if (context.Stage == ReactorLifecycleStage.StoryUnavailable)
                {
                    StopWeaponPreviewCore();
                    ResetHiddenCheckout();
                    Status = "GBAY closed.";
                }
                else if (context.Stage == ReactorLifecycleStage.Unloading)
                {
                    StopWeaponPreviewCore();
                    Status = "GBAY unloading.";
                }
            }
        }

        public void Dispose()
        {
            lock (_sync)
            {
                if (_disposed) return;
                StopWeaponPreviewCore();
                _disposed = true;
                _handle?.Dispose();
                _handle = null;
                _presentation = null;
                _presentationReadyMethod = null;
                ClearState();
                Status = "Disposed.";
            }
        }

        private void ClearState()
        {
            _storefront = null;
            _page = null;
            _snapshot = null;
            _checkout = null;
            _weaponPage = null;
            _customWeaponPage = null;
            _customizationPage = null;
            _customizationGroup = "components";
            _gearPage = null;
            _garage = null;
            _garageLocation = "all";
            _storyCharacterId = "";
            _publishedState.Clear();
        }

        private void ResetHiddenCheckout()
        {
            if (_checkout == null || _handle == null || _page == null) return;
            _checkout = null;
            UpdateMenu(BuildVehiclesMenu(_page));
        }

        private void RegisterActions(ReactorExtensionBuilder builder)
        {
            if (_storefront is IAllin1HitchStorefront)
            {
                foreach (bool experimental in new[] { false, true })
                {
                    bool confirmation = experimental;
                    builder.AddAction(new ReactorActionDescriptor(
                        experimental ? "hitch.connect.experimental" : "hitch.connect", experimental ? "Confirm experimental physical hitch" : "Connect trailer",
                        ReactorActionRisk.Gameplay, new[] { new ReactorParameterDescriptor("token", ReactorValueType.String, required: true, maximumLength: 32) },
                        requiresConfirmation: true, description: experimental ? "Experimental physics: stop both vehicles. The joint may behave differently between editions." : "Rechecks driver, proximity, occupancy and authored hitch bones."),
                        (_, values) => HitchAction(values.Value<string>("token") ?? "", disconnect: false, experimental: confirmation));
                }
                builder.AddAction(new ReactorActionDescriptor("hitch.disconnect", "Disconnect trailer", ReactorActionRisk.Gameplay,
                    new[] { new ReactorParameterDescriptor("token", ReactorValueType.String, required: true, maximumLength: 32) }, requiresConfirmation: true),
                    (_, values) => HitchAction(values.Value<string>("token") ?? "", disconnect: true, experimental: false));
            }
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.search", "Search vehicles", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        maximumLength: 96) }),
                (_, values) => UpdateView(() =>
                {
                    _request.Search = values.Value<string>("value") ?? "";
                    _request.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.category", "Choose category", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: _storefront!.Categories) }),
                (_, values) => UpdateView(() =>
                {
                    _request.Category = values.Value<string>("value") ?? "all";
                    _request.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.favorites", "Show favorites", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.Boolean, required: true) }),
                (_, values) => UpdateView(() =>
                {
                    _request.FavoritesOnly = values.Value<bool>("value");
                    _request.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.ownership", "Filter ownership", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: new[] { "all", "owned", "available" }) }),
                (_, values) => UpdateView(() =>
                {
                    _request.Ownership = values.Value<string>("value") ?? "all";
                    _request.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.page", "Change page", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.Integer, required: true,
                        minimum: 1, maximum: 100000) }),
                (_, values) => UpdateView(() =>
                    _request.Page = values.Value<int>("value")));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.checkout", "Choose delivery", ReactorActionRisk.Read,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "model", ReactorValueType.String, required: true,
                            maximumLength: 64),
                        new ReactorParameterDescriptor(
                            "quotedprice", ReactorValueType.Integer, required: true,
                            minimum: 0, maximum: 2000000000),
                    },
                    description: "Builds a detached delivery selection; it does not purchase."),
                BeginCheckout);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.delivery.cancel", "Back to listings",
                    ReactorActionRisk.Read),
                (_, __) => CancelCheckout());
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.delivery.confirm", "Confirm delivery",
                    ReactorActionRisk.Persistent,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "model", ReactorValueType.String, required: true,
                            maximumLength: 64),
                        new ReactorParameterDescriptor(
                            "quotedprice", ReactorValueType.Integer, required: true,
                            minimum: 0, maximum: 2000000000),
                        new ReactorParameterDescriptor(
                            "destination", ReactorValueType.String, required: true,
                            maximumLength: 64),
                    },
                    requiresConfirmation: true,
                    description: "Revalidates the live listing and destination before delivery."),
                ConfirmDelivery);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "vehicle.favorite", "Toggle favorite",
                    ReactorActionRisk.Gameplay,
                    new[] { new ReactorParameterDescriptor(
                        "model", ReactorValueType.String, required: true,
                        maximumLength: 64) },
                    description: "Immediately toggles this reversible catalog preference."),
                ToggleFavorite);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.search", "Search weapons", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        maximumLength: 96) }),
                (_, values) => UpdateWeaponView(() =>
                {
                    _weaponRequest.Search = values.Value<string>("value") ?? "";
                    _weaponRequest.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.category", "Choose weapon category",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: _storefront!.WeaponCategories) }),
                (_, values) => UpdateWeaponView(() =>
                {
                    _weaponRequest.Category =
                        values.Value<string>("value") ?? "components";
                    _weaponRequest.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.ownership", "Filter weapon ownership",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: new[] { "all", "owned", "available" }) }),
                (_, values) => UpdateWeaponView(() =>
                {
                    _weaponRequest.Ownership =
                        values.Value<string>("value") ?? "all";
                    _weaponRequest.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.favorites", "Show favorite weapons",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.Boolean, required: true) }),
                (_, values) => UpdateWeaponView(() =>
                {
                    _weaponRequest.FavoritesOnly =
                        values.Value<bool>("value");
                    _weaponRequest.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.page", "Change weapon page", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.Integer, required: true,
                        minimum: 1, maximum: 100000) }),
                (_, values) => UpdateWeaponView(() =>
                    _weaponRequest.Page = values.Value<int>("value")));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.purchase", "Purchase weapon",
                    ReactorActionRisk.Persistent,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "weapon", ReactorValueType.String, required: true,
                            maximumLength: 64),
                        new ReactorParameterDescriptor(
                            "quotedprice", ReactorValueType.Integer, required: true,
                            minimum: 0, maximum: 2000000000),
                    },
                    requiresConfirmation: true,
                    description: "Revalidates price, ownership, GTA availability, and funds."),
                PurchaseWeapon);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.favorite", "Toggle weapon favorite",
                    ReactorActionRisk.Gameplay,
                    new[] { new ReactorParameterDescriptor(
                        "weapon", ReactorValueType.String, required: true,
                        maximumLength: 64) },
                    description: "Immediately toggles this reversible catalog preference."),
                ToggleWeaponFavorite);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.search", "Search owned weapons",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        maximumLength: 96) }),
                (_, values) => UpdateCustomWeaponView(() =>
                {
                    _customWeaponRequest.Search =
                        values.Value<string>("value") ?? "";
                    _customWeaponRequest.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.category", "Choose weapon category",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: _storefront!.WeaponCategories) }),
                (_, values) => UpdateCustomWeaponView(() =>
                {
                    _customWeaponRequest.Category =
                        values.Value<string>("value") ?? "all";
                    _customWeaponRequest.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.select", "Select owned weapon",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "weapon", ReactorValueType.String, required: true,
                        maximumLength: 64) }),
                SelectCustomWeapon);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.group", "Choose option group",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: new[]
                        {
                            "all", "ammo", "components", "tints", "livery",
                        }) }),
                (_, values) => UpdateCustomizationView(() =>
                {
                    _customizationGroup =
                        values.Value<string>("value") ?? "all";
                }, resetPage: true));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.page", "Change workbench page",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.Integer, required: true,
                        minimum: 1, maximum: 100000) }),
                (_, values) => ChangeCustomizationPage(
                    values.Value<int>("value")));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.back", "Back to owned weapons",
                    ReactorActionRisk.Read),
                (_, __) => CloseCustomizationOptions());
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.preview", "Preview weapon option",
                    ReactorActionRisk.Read,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "weapon", ReactorValueType.String, required: true,
                            maximumLength: 64),
                        new ReactorParameterDescriptor(
                            "kind", ReactorValueType.String, required: true,
                            allowedValues: new[]
                            {
                                "ammo", "component", "component_remove", "tint", "component_tint",
                            }),
                        new ReactorParameterDescriptor(
                            "component", ReactorValueType.Integer, required: true),
                        new ReactorParameterDescriptor(
                            "attachment", ReactorValueType.Integer, required: true),
                        new ReactorParameterDescriptor(
                            "tint", ReactorValueType.Integer, required: true,
                            minimum: 0, maximum: 31),
                    },
                    description: "Updates only the temporary in-world dummy preview."),
                PreviewWeaponCustomization);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.preview.stop", "Close weapon preview",
                    ReactorActionRisk.Read),
                (_, __) => StopWeaponPreview());
            builder.AddAction(
                new ReactorActionDescriptor(
                    "weapon.customize.apply", "Apply weapon option",
                    ReactorActionRisk.Persistent,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "weapon", ReactorValueType.String, required: true,
                            maximumLength: 64),
                        new ReactorParameterDescriptor(
                            "kind", ReactorValueType.String, required: true,
                            allowedValues: new[]
                            {
                                "ammo", "component", "component_remove", "tint", "component_tint",
                            }),
                        new ReactorParameterDescriptor(
                            "component", ReactorValueType.Integer, required: true),
                        new ReactorParameterDescriptor(
                            "attachment", ReactorValueType.Integer, required: true),
                        new ReactorParameterDescriptor(
                            "tint", ReactorValueType.Integer, required: true,
                            minimum: 0, maximum: 31),
                        new ReactorParameterDescriptor(
                            "quotedprice", ReactorValueType.Integer, required: true,
                            minimum: 0, maximum: 2000000000),
                    },
                    requiresConfirmation: true,
                    description: "Re-discovers compatibility, ownership, price, and funds before mutation."),
                ApplyWeaponCustomization);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "gear.category", "Choose gear category",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: _storefront!.GearCategories) }),
                (_, values) => UpdateGearView(() =>
                {
                    _gearRequest.Category =
                        values.Value<string>("value") ?? "all";
                    _gearRequest.Page = 1;
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "gear.page", "Change gear page", ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.Integer, required: true,
                        minimum: 1, maximum: 100000) }),
                (_, values) => UpdateGearView(() =>
                    _gearRequest.Page = values.Value<int>("value")));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "gear.apply", "Buy, equip, or unequip gear",
                    ReactorActionRisk.Persistent,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "gear", ReactorValueType.String, required: true,
                            maximumLength: 64),
                        new ReactorParameterDescriptor(
                            "operation", ReactorValueType.String, required: true,
                            allowedValues: new[] { "purchase", "equip", "unequip" }),
                        new ReactorParameterDescriptor(
                            "quotedprice", ReactorValueType.Integer, required: true,
                            minimum: 0, maximum: 2000000000),
                    },
                    requiresConfirmation: true,
                    description: "Uses ALLIN1's per-character gear lifecycle."),
                ApplyGear);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "garage.location", "Choose garage location",
                    ReactorActionRisk.Read,
                    new[] { new ReactorParameterDescriptor(
                        "value", ReactorValueType.String, required: true,
                        allowedValues: GarageLocationValues()) }),
                (_, values) => UpdateGarageView(() =>
                {
                    _garageLocation =
                        values.Value<string>("value") ?? "all";
                }));
            builder.AddAction(
                new ReactorActionDescriptor(
                    "garage.waypoint", "Navigate to garage",
                    ReactorActionRisk.Gameplay,
                    new[] { new ReactorParameterDescriptor(
                        "location", ReactorValueType.String, required: true,
                        allowedValues: GarageLocationValues()
                            .Where(value => value != "all").ToArray()) },
                    description: "Sets GTA's waypoint to a host-resolved garage entrance; no coordinates are accepted from the menu."),
                NavigateToGarage);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "garage.sell", "Sell garage vehicle",
                    ReactorActionRisk.Persistent,
                    GarageActionParameters(includePrice: true),
                    requiresConfirmation: true,
                    description: "Rechecks model, hash, plate, index, and price before removal."),
                SellGarageVehicle);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "garage.retrieve", "Retrieve specialized vehicle",
                    ReactorActionRisk.Persistent,
                    GarageActionParameters(includePrice: false),
                    requiresConfirmation: true,
                    description: "Retrieves from the helipad or harbour using existing ALLIN1 transitions."),
                RetrieveGarageVehicle);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "garage.customize", "Customize Davis Auto Shop",
                    ReactorActionRisk.Persistent,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "location", ReactorValueType.String,
                            required: true,
                            allowedValues: new[] { "davis" }),
                        new ReactorParameterDescriptor(
                            "category", ReactorValueType.String,
                            required: true,
                            allowedValues: GarageCustomizationCategoryValues()),
                        new ReactorParameterDescriptor(
                            "expected", ReactorValueType.String,
                            required: true,
                            allowedValues: GarageCustomizationOptionValues()),
                        new ReactorParameterDescriptor(
                            "value", ReactorValueType.String,
                            required: true,
                            allowedValues: GarageCustomizationOptionValues()),
                    },
                    requiresConfirmation: true,
                    description: "Revalidates the current per-character Davis layout before saving."),
                ApplyGarageCustomization);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "garage.recover", "Emergency garage recovery",
                    ReactorActionRisk.Persistent,
                    requiresConfirmation: true,
                    description: "Runs only while ALLIN1 confirms a managed garage or transition is stuck."),
                (_, __) => EmergencyRecoverGarage());
            builder.AddAction(
                new ReactorActionDescriptor(
                    "addon.invoke", "Open add-on action",
                    ReactorActionRisk.Gameplay,
                    new[]
                    {
                        new ReactorParameterDescriptor(
                            "package", ReactorValueType.String, required: true,
                            maximumLength: 96),
                        new ReactorParameterDescriptor(
                            "route", ReactorValueType.String, required: true,
                            maximumLength: 128),
                    },
                    requiresConfirmation: true,
                    description: "Invokes only a currently receipt-authorized ALLIN1 route."),
                InvokeAddon);
            builder.AddAction(
                new ReactorActionDescriptor(
                    "diagnostics.open-log-folder",
                    "Open ALLIN1 runtime log folder",
                    ReactorActionRisk.Gameplay,
                    requiresConfirmation: true,
                    description: "Opens only the fixed ALLIN1 scripts folder; no path is accepted from the menu."),
                (_, __) => OpenRuntimeLogFolder());
            builder.AddAction(
                new ReactorActionDescriptor(
                    "about.support", "Open ALLIN1 support page",
                    ReactorActionRisk.Gameplay,
                    requiresConfirmation: true,
                    description: "Opens the fixed ALLIN1 support URL outside GTA V."),
                (_, __) => OpenSupportPage());
        }

        private ReactorActionResult UpdateView(Action update)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                update();
                // Search/filter/page changes operate on the authorized in-memory
                // catalog. No catalog scan, menu rebuild, or native UI handoff
                // occurs here. Package discovery belongs to startup/install,
                // while live game state synchronizes automatically.
                _request.RefreshCatalog = false;
                _page = _storefront!.BrowseVehicles(_request);
                _request.Page = _page.Page;
                _checkout = null;
                UpdateMenu(BuildVehiclesMenu(_page));
                return ReactorActionResult.Success(PagePayload(
                    _page, "refresh", "Listings updated."));
            }
        }

        private ReactorActionResult BeginCheckout(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                var request = new Allin1VehicleCheckoutRequest
                {
                    Model = values.Value<string>("model") ?? "",
                    QuotedPrice = values.Value<int>("quotedprice"),
                };
                Allin1VehicleCheckoutResult result =
                    _storefront!.BeginVehicleCheckout(request);
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(result.Code, result.Message);
                _checkout = result;
                UpdateMenu(BuildVehiclesMenu(_page!));
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["view"] = "delivery",
                    ["code"] = result.Code,
                    ["message"] = result.Message,
                    ["model"] = result.Model,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult CancelCheckout()
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                _checkout = null;
                UpdateMenu(BuildVehiclesMenu(_page!));
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["view"] = "catalog",
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult ConfirmDelivery(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available() || _checkout == null)
                    return ReactorActionResult.Failure(
                        "checkout_expired", "Choose the vehicle again.");
                string model = values.Value<string>("model") ?? "";
                int quotedPrice = values.Value<int>("quotedprice");
                if (!string.Equals(model, _checkout.Model,
                        StringComparison.OrdinalIgnoreCase) ||
                    quotedPrice != _checkout.QuotedPrice)
                    return ReactorActionResult.Failure(
                        "checkout_changed", "The active checkout does not match this request.");
                var request = new Allin1VehicleDeliveryRequest
                {
                    Model = model,
                    QuotedPrice = quotedPrice,
                    DestinationId = values.Value<string>("destination") ?? "",
                };
                Allin1VehicleDeliveryResult result =
                    _storefront!.ConfirmVehicleDelivery(request);
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(result.Code, result.Message);

                _checkout = null;
                _request.RefreshCatalog = false;
                _page = _storefront.BrowseVehicles(_request);
                _snapshot = _storefront.DescribeGbay();
                _garage = _storefront.BrowseGarage();
                _weaponPage = _storefront.BrowseWeapons(_weaponRequest);
                _gearPage = _storefront.BrowseGear(_gearRequest);
                UpdateMenu(BuildVehiclesMenu(_page));
                UpdateMenu(BuildHomeMenu(_snapshot));
                UpdateMenu(BuildWeaponsMenu(_weaponPage));
                UpdateMenu(BuildGearMenu(_gearPage));
                UpdateMenu(BuildGarageMenu(_garage));
                return ReactorActionResult.Success(PagePayload(
                    _page, "refresh", result.Message));
            }
        }

        private ReactorActionResult ToggleFavorite(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                string model = values.Value<string>("model") ?? "";
                if (!_storefront!.ToggleVehicleFavorite(model))
                    return ReactorActionResult.Failure(
                        "invalid_listing", "That vehicle is not in the current catalog.");
                _request.RefreshCatalog = false;
                _page = _storefront.BrowseVehicles(_request);
                UpdateMenu(BuildVehiclesMenu(_page));
                return ReactorActionResult.Success(PagePayload(
                    _page, "refresh", "Favorite updated."));
            }
        }

        private ReactorActionResult UpdateWeaponView(Action update)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                update();
                _weaponPage = _storefront!.BrowseWeapons(_weaponRequest);
                _weaponRequest.Page = _weaponPage.Page;
                UpdateMenu(BuildWeaponsMenu(_weaponPage));
                return ReactorActionResult.Success(CatalogPayload(
                    _weaponPage.Page, _weaponPage.PageCount,
                    _weaponPage.TotalItems, "Weapons updated."));
            }
        }

        private ReactorActionResult PurchaseWeapon(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result = _storefront!.PurchaseWeapon(
                    new Allin1WeaponPurchaseRequest
                    {
                        WeaponId = values.Value<string>("weapon") ?? "",
                        QuotedTotalPrice = values.Value<int>("quotedprice"),
                    });
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(result.Code, result.Message);
                _weaponPage = _storefront.BrowseWeapons(_weaponRequest);
                _snapshot = _storefront.DescribeGbay();
                _gearPage = _storefront.BrowseGear(_gearRequest);
                RefreshLoadedCustomizationState();
                UpdateMenu(BuildWeaponsMenu(_weaponPage));
                UpdateMenu(BuildHomeMenu(_snapshot));
                UpdateMenu(BuildGearMenu(_gearPage));
                if (_customWeaponPage != null)
                    UpdateMenu(BuildCustomizeMenu());
                return ReactorActionResult.Success(CatalogPayload(
                    _weaponPage.Page, _weaponPage.PageCount,
                    _weaponPage.TotalItems, result.Message));
            }
        }

        private ReactorActionResult ToggleWeaponFavorite(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                if (!_storefront!.ToggleWeaponFavorite(
                        values.Value<string>("weapon") ?? ""))
                    return ReactorActionResult.Failure(
                        "invalid_weapon", "That weapon is not in the GBAY catalog.");
                _weaponPage = _storefront.BrowseWeapons(_weaponRequest);
                UpdateMenu(BuildWeaponsMenu(_weaponPage));
                return ReactorActionResult.Success(CatalogPayload(
                    _weaponPage.Page, _weaponPage.PageCount,
                    _weaponPage.TotalItems, "Favorite updated."));
            }
        }

        private ReactorActionResult UpdateCustomWeaponView(Action update)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                update();
                StopWeaponPreviewCore();
                _customizationPage = null;
                _customWeaponPage = _storefront!.BrowseCustomizableWeapons(
                    _customWeaponRequest);
                _customWeaponRequest.Page = _customWeaponPage.Page;
                UpdateMenu(BuildCustomizeMenu());
                return ReactorActionResult.Success(CatalogPayload(
                    _customWeaponPage.Page, _customWeaponPage.PageCount,
                    _customWeaponPage.TotalItems, _customWeaponPage.Status));
            }
        }

        private ReactorActionResult SelectCustomWeapon(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available() || _customWeaponPage == null)
                    return ReactorActionResult.Failure(
                        "catalog_not_ready",
                        "Owned weapons are still being read from the current character.");
                string weapon = values.Value<string>("weapon") ?? "";
                if (!_customWeaponPage.Items.Any(value => string.Equals(
                        value.Id, weapon, StringComparison.OrdinalIgnoreCase)))
                {
                    // Re-read the game once before rejecting a stale card.
                    // The player never has to discover or operate a refresh
                    // control just because another system changed loadout.
                    TrySynchronizeGameStateCore();
                    if (_customWeaponPage == null ||
                        !_customWeaponPage.Items.Any(value => string.Equals(
                            value.Id, weapon,
                            StringComparison.OrdinalIgnoreCase)))
                        return ReactorActionResult.Failure(
                            "stale_weapon",
                            "That weapon is no longer held. The list has updated automatically.");
                }
                IAllin1WeaponPreviewStorefront? previewHost =
                    _storefront as IAllin1WeaponPreviewStorefront;
                if (previewHost == null)
                    return ReactorActionResult.Failure(
                        "preview_contract_unavailable",
                        "Update ALLIN1 to use the Reactor weapon preview.");

                Allin1WeaponCustomizationPage page = _storefront!
                    .BrowseWeaponCustomization(
                        weapon, _customizationGroup, 1,
                        WeaponCustomizationScrollLimit, refresh: true);
                Allin1GbayActionResult result;
                try
                {
                    result = previewHost.BeginWeaponPreview(
                        new Allin1WeaponWorkbenchRequest
                        {
                            WeaponId = weapon,
                        });
                }
                catch (Exception ex)
                {
                    Status = "Weapon workbench setup failed: " +
                        ex.GetType().Name + ".";
                    return ReactorActionResult.Failure(
                        "workbench_failed",
                        "The in-world weapon preview could not be opened safely.");
                }
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(
                        result.Code, result.Message);

                _customizationPage = page;
                PreviewFirstCustomizationOption();
                UpdateMenu(BuildCustomizeMenu());
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["view"] = "reactor-weapon-workbench",
                    ["weapon"] = weapon,
                    ["code"] = result.Code,
                    ["message"] = result.Message,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult UpdateCustomizationView(
            Action update, bool resetPage)
        {
            lock (_sync)
            {
                if (!Available() || _customizationPage == null)
                    return ReactorActionResult.Failure(
                        "weapon_not_selected", "Choose an owned weapon first.");
                string weapon = _customizationPage.WeaponId;
                update();
                _customizationPage = _storefront!.BrowseWeaponCustomization(
                    weapon, _customizationGroup, 1,
                    WeaponCustomizationScrollLimit, refresh: false);
                PreviewFirstCustomizationOption();
                UpdateMenu(BuildCustomizeMenu());
                return ReactorActionResult.Success(CatalogPayload(
                    _customizationPage.Page,
                    _customizationPage.PageCount,
                    _customizationPage.TotalItems,
                    _customizationPage.Status));
            }
        }

        private ReactorActionResult ChangeCustomizationPage(int page)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                if (_customizationPage != null)
                {
                    string weapon = _customizationPage.WeaponId;
                    _customizationPage = _storefront!
                        .BrowseWeaponCustomization(
                            weapon, _customizationGroup, page,
                            WeaponCustomizationScrollLimit,
                            refresh: false);
                    PreviewFirstCustomizationOption();
                    UpdateMenu(BuildCustomizeMenu());
                    return ReactorActionResult.Success(CatalogPayload(
                        _customizationPage.Page,
                        _customizationPage.PageCount,
                        _customizationPage.TotalItems,
                        _customizationPage.Status));
                }
                _customWeaponRequest.Page = page;
                return UpdateCustomWeaponView(() => { });
            }
        }

        private ReactorActionResult CloseCustomizationOptions()
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                StopWeaponPreviewCore();
                _customizationPage = null;
                UpdateMenu(BuildCustomizeMenu());
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["view"] = "owned-weapons",
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult ApplyWeaponCustomization(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available() || _customizationPage == null)
                    return ReactorActionResult.Failure(
                        "weapon_not_selected", "Choose an owned weapon first.");
                var request = new Allin1WeaponCustomizationApplyRequest
                {
                    WeaponId = values.Value<string>("weapon") ?? "",
                    Kind = values.Value<string>("kind") ?? "",
                    ComponentHash = values.Value<int>("component"),
                    AttachmentPoint = values.Value<int>("attachment"),
                    Tint = values.Value<int>("tint"),
                    QuotedPrice = values.Value<int>("quotedprice"),
                };
                if (!string.Equals(request.WeaponId,
                        _customizationPage.WeaponId,
                        StringComparison.OrdinalIgnoreCase) ||
                    !_customizationPage.Items.Any(value =>
                        CustomizationOptionMatches(value, request)))
                    return ReactorActionResult.Failure(
                        "stale_option",
                        "The selected weapon options will update automatically.");
                Allin1GbayActionResult result = _storefront!
                    .ApplyWeaponCustomization(request);
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(
                        result.Code, result.Message);

                _customizationPage = _storefront.BrowseWeaponCustomization(
                    request.WeaponId, _customizationGroup,
                    1, WeaponCustomizationScrollLimit, refresh: true);
                _customWeaponPage = _storefront.BrowseCustomizableWeapons(
                    _customWeaponRequest);
                _snapshot = _storefront.DescribeGbay();
                PreviewWeaponCustomizationCore(request);
                UpdateMenu(BuildCustomizeMenu());
                UpdateMenu(BuildHomeMenu(_snapshot));
                return ReactorActionResult.Success(CatalogPayload(
                    _customizationPage.Page,
                    _customizationPage.PageCount,
                    _customizationPage.TotalItems, result.Message));
            }
        }

        private ReactorActionResult PreviewWeaponCustomization(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available() || _customizationPage == null)
                    return ReactorActionResult.Failure(
                        "weapon_not_selected", "Choose an owned weapon first.");
                var request = new Allin1WeaponCustomizationApplyRequest
                {
                    WeaponId = values.Value<string>("weapon") ?? "",
                    Kind = values.Value<string>("kind") ?? "",
                    ComponentHash = values.Value<int>("component"),
                    AttachmentPoint = values.Value<int>("attachment"),
                    Tint = values.Value<int>("tint"),
                    QuotedPrice = 0,
                };
                if (!string.Equals(request.WeaponId,
                        _customizationPage.WeaponId,
                        StringComparison.OrdinalIgnoreCase) ||
                    !_customizationPage.Items.Any(value =>
                        CustomizationPreviewMatches(value, request)))
                    return ReactorActionResult.Failure(
                        "stale_option",
                        "The selected weapon options will update automatically.");
                Allin1GbayActionResult? result =
                    PreviewWeaponCustomizationCore(request);
                if (result == null)
                    return ReactorActionResult.Failure(
                        "preview_contract_unavailable",
                        "Update ALLIN1 to use the Reactor weapon preview.");
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(
                        result.Code, result.Message);
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "retain",
                    ["view"] = "reactor-weapon-workbench",
                    ["weapon"] = request.WeaponId,
                    ["message"] = result.Message,
                });
            }
        }

        private ReactorActionResult StopWeaponPreview()
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                StopWeaponPreviewCore();
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "retain",
                    ["message"] = "In-world weapon preview closed.",
                });
            }
        }

        private Allin1GbayActionResult? PreviewWeaponCustomizationCore(
            Allin1WeaponCustomizationApplyRequest request)
        {
            IAllin1WeaponPreviewStorefront? previewHost =
                _storefront as IAllin1WeaponPreviewStorefront;
            return previewHost?.PreviewWeaponCustomization(request);
        }

        private void StopWeaponPreviewCore()
        {
            IAllin1WeaponPreviewStorefront? previewHost =
                _storefront as IAllin1WeaponPreviewStorefront;
            previewHost?.EndWeaponPreview();
        }

        private void PreviewFirstCustomizationOption()
        {
            Allin1WeaponCustomizationPage? page = _customizationPage;
            Allin1WeaponCustomizationOptionListing? option =
                page?.Items.FirstOrDefault();
            if (page == null || option == null) return;
            PreviewWeaponCustomizationCore(
                CustomizationRequest(page.WeaponId, option));
        }

        private static Allin1WeaponCustomizationApplyRequest
            CustomizationRequest(
                string weapon,
                Allin1WeaponCustomizationOptionListing option) =>
            new Allin1WeaponCustomizationApplyRequest
            {
                WeaponId = weapon ?? "",
                Kind = option?.Kind ?? "",
                ComponentHash = option?.ComponentHash ?? 0,
                AttachmentPoint = option?.AttachmentPoint ?? 0,
                Tint = option?.Tint ?? 0,
                QuotedPrice = option?.Price ?? 0,
            };

        private static bool CustomizationPreviewMatches(
            Allin1WeaponCustomizationOptionListing option,
            Allin1WeaponCustomizationApplyRequest request) =>
            string.Equals(option.Kind, request.Kind,
                StringComparison.OrdinalIgnoreCase) &&
            option.ComponentHash == request.ComponentHash &&
            option.AttachmentPoint == request.AttachmentPoint &&
            option.Tint == request.Tint;

        private static bool CustomizationOptionMatches(
            Allin1WeaponCustomizationOptionListing option,
            Allin1WeaponCustomizationApplyRequest request) =>
            string.Equals(option.Kind, request.Kind,
                StringComparison.OrdinalIgnoreCase) &&
            option.ComponentHash == request.ComponentHash &&
            option.AttachmentPoint == request.AttachmentPoint &&
            option.Tint == request.Tint &&
            option.Price == request.QuotedPrice;

        private ReactorActionResult UpdateGearView(Action update)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                update();
                _gearPage = _storefront!.BrowseGear(_gearRequest);
                _gearRequest.Page = _gearPage.Page;
                UpdateMenu(BuildGearMenu(_gearPage));
                return ReactorActionResult.Success(CatalogPayload(
                    _gearPage.Page, _gearPage.PageCount,
                    _gearPage.TotalItems, "Gear updated."));
            }
        }

        private ReactorActionResult ApplyGear(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result = _storefront!.ApplyGearAction(
                    new Allin1GearActionRequest
                    {
                        GearId = values.Value<string>("gear") ?? "",
                        Operation = values.Value<string>("operation") ?? "",
                        QuotedPrice = values.Value<int>("quotedprice"),
                    });
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(result.Code, result.Message);
                _gearPage = _storefront.BrowseGear(_gearRequest);
                _snapshot = _storefront.DescribeGbay();
                _weaponPage = _storefront.BrowseWeapons(_weaponRequest);
                UpdateMenu(BuildGearMenu(_gearPage));
                UpdateMenu(BuildHomeMenu(_snapshot));
                UpdateMenu(BuildWeaponsMenu(_weaponPage));
                return ReactorActionResult.Success(CatalogPayload(
                    _gearPage.Page, _gearPage.PageCount,
                    _gearPage.TotalItems, result.Message));
            }
        }

        private ReactorActionResult UpdateGarageView(Action update)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                update();
                UpdateMenu(BuildGarageMenu(_garage!));
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["message"] = "My Garage view updated.",
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult NavigateToGarage(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                string locationId =
                    values.Value<string>("location") ?? "";
                Allin1GbayActionResult result =
                    _storefront!.NavigateToGarage(
                        new Allin1GarageWaypointRequest
                        {
                            LocationId = locationId,
                        });
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(
                        result.Code, result.Message);
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["message"] = result.Message,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult SellGarageVehicle(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result = _storefront!.SellGarageVehicle(
                    GarageRequest(values, includePrice: true));
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(result.Code, result.Message);
                _garage = _storefront.BrowseGarage();
                _snapshot = _storefront.DescribeGbay();
                _weaponPage = _storefront.BrowseWeapons(_weaponRequest);
                _gearPage = _storefront.BrowseGear(_gearRequest);
                UpdateMenu(BuildGarageMenu(_garage));
                UpdateMenu(BuildHomeMenu(_snapshot));
                UpdateMenu(BuildWeaponsMenu(_weaponPage));
                UpdateMenu(BuildGearMenu(_gearPage));
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["message"] = result.Message,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult RetrieveGarageVehicle(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result =
                    _storefront!.RetrieveGarageVehicle(
                        GarageRequest(values, includePrice: false));
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(result.Code, result.Message);
                _garage = _storefront.BrowseGarage();
                _snapshot = _storefront.DescribeGbay();
                UpdateMenu(BuildGarageMenu(_garage));
                UpdateMenu(BuildHomeMenu(_snapshot));
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "close",
                    ["message"] = result.Message,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult ApplyGarageCustomization(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result =
                    _storefront!.ApplyGarageCustomization(
                        new Allin1GarageCustomizationRequest
                        {
                            LocationId =
                                values.Value<string>("location") ?? "",
                            CategoryId =
                                values.Value<string>("category") ?? "",
                            ExpectedOptionId =
                                values.Value<string>("expected") ?? "",
                            OptionId = values.Value<string>("value") ?? "",
                        });
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(
                        result.Code, result.Message);
                _garage = _storefront.BrowseGarage();
                UpdateMenu(BuildGarageMenu(_garage));
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["message"] = result.Message,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult EmergencyRecoverGarage()
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result =
                    _storefront!.EmergencyRecoverGarage();
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(
                        result.Code, result.Message);
                _garage = _storefront.BrowseGarage();
                _snapshot = _storefront.DescribeGbay();
                UpdateMenu(BuildGarageMenu(_garage));
                UpdateMenu(BuildHomeMenu(_snapshot));
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "close",
                    ["message"] = result.Message,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private static IReadOnlyList<ReactorParameterDescriptor>
            GarageActionParameters(bool includePrice)
        {
            var result = new List<ReactorParameterDescriptor>
            {
                new ReactorParameterDescriptor(
                    "location", ReactorValueType.String, required: true,
                    maximumLength: 64),
                new ReactorParameterDescriptor(
                    "index", ReactorValueType.Integer, required: true,
                    minimum: 0, maximum: 10000),
                new ReactorParameterDescriptor(
                    "model", ReactorValueType.String, required: true,
                    maximumLength: 64),
                new ReactorParameterDescriptor(
                    "modelhash", ReactorValueType.Integer, required: true),
                new ReactorParameterDescriptor(
                    "plate", ReactorValueType.String, required: true,
                    maximumLength: 32),
            };
            if (includePrice)
                result.Add(new ReactorParameterDescriptor(
                    "quotedprice", ReactorValueType.Integer, required: true,
                    minimum: 0, maximum: 2000000000));
            return result;
        }

        private IReadOnlyList<string> GarageLocationValues() =>
            new[] { "all" }.Concat(
                    (_garage?.Locations ??
                        Array.Empty<Allin1VehicleDeliveryOption>())
                    .Select(value => value.Id))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

        private IReadOnlyList<string> GarageCustomizationCategoryValues() =>
            (_garage?.Customization?.Categories ??
                Array.Empty<Allin1GarageCustomizationCategory>())
            .Select(value => value.Id)
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        private IReadOnlyList<string> GarageCustomizationOptionValues() =>
            (_garage?.Customization?.Categories ??
                Array.Empty<Allin1GarageCustomizationCategory>())
            .SelectMany(value => value.Options ??
                Array.Empty<Allin1GarageCustomizationOption>())
            .Select(value => value.Id)
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        private static Allin1GarageVehicleRequest GarageRequest(
            JObject values, bool includePrice) =>
            new Allin1GarageVehicleRequest
            {
                LocationId = values.Value<string>("location") ?? "",
                ListIndex = values.Value<int>("index"),
                Model = values.Value<string>("model") ?? "",
                ModelHash = values.Value<int>("modelhash"),
                PlateText = values.Value<string>("plate") ?? "",
                QuotedSellPrice = includePrice
                    ? values.Value<int>("quotedprice") : 0,
            };

        private ReactorActionResult InvokeAddon(
            ReactorActionContext context, JObject values)
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result = _storefront!.InvokeAddon(
                    values.Value<string>("package") ?? "",
                    values.Value<string>("route") ?? "");
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(result.Code, result.Message);
                _snapshot = _storefront.DescribeGbay();
                UpdateDynamicMenus();
                return ReactorActionResult.Success(new JObject
                {
                    ["presentation"] = "refresh",
                    ["code"] = result.Code,
                    ["message"] = result.Message,
                    ["menuRevision"] = RevisionText(),
                });
            }
        }

        private ReactorActionResult OpenRuntimeLogFolder()
        {
            lock (_sync)
            {
                if (!Available()) return Unavailable();
                Allin1GbayActionResult result =
                    _storefront!.OpenRuntimeLogFolder();
                if (!result.Succeeded)
                    return ReactorActionResult.Failure(
                        result.Code, result.Message);
                return ReactorActionResult.Success(new JObject
                {
                    ["message"] = result.Message,
                    ["portablePath"] = _snapshot!.RuntimeLogPath,
                });
            }
        }

        private bool Available() =>
            !_disposed && _handle != null && _storefront != null &&
            _page != null && _snapshot != null && _weaponPage != null &&
            _gearPage != null && _garage != null;

        private static ReactorActionResult Unavailable() =>
            ReactorActionResult.Failure(
                "bridge_unavailable", "ALLIN1 GBAY is not available.");

        private static ReactorActionResult OpenSupportPage()
        {
            try
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = SupportUrl,
                    UseShellExecute = true,
                });
                return ReactorActionResult.Success(new JObject
                {
                    ["message"] = "ALLIN1 support page opened.",
                });
            }
            catch
            {
                // Do not leak machine-specific browser or shell details into
                // the agent-facing action result.
                return ReactorActionResult.Failure(
                    "support_launch_failed",
                    "Windows could not open the ALLIN1 support page.");
            }
        }

        private bool TrySynchronizeGameStateCore()
        {
            try
            {
                // Build every provider result before replacing any published
                // state. A provider failure cannot leave the browser with a
                // mixture of old and new balance, ownership, and garage data.
                Allin1GbaySnapshot snapshot = _storefront!.DescribeGbay();
                _request.RefreshCatalog = false;
                Allin1VehicleCatalogPage page =
                    _storefront.BrowseVehicles(_request);
                Allin1WeaponCatalogPage weaponPage =
                    _storefront.BrowseWeapons(_weaponRequest);
                Allin1CustomizableWeaponPage customWeaponPage =
                    _storefront.BrowseCustomizableWeapons(
                        _customWeaponRequest);
                Allin1GearCatalogPage gearPage =
                    _storefront.BrowseGear(_gearRequest);
                Allin1GarageSnapshot garage = _storefront.BrowseGarage();

                Allin1WeaponCustomizationPage? customizationPage = null;
                bool selectedWeaponStillHeld = false;
                if (_customizationPage != null)
                {
                    selectedWeaponStillHeld = customWeaponPage.Items.Any(
                        value => string.Equals(
                            value.Id, _customizationPage.WeaponId,
                            StringComparison.OrdinalIgnoreCase));
                    if (selectedWeaponStillHeld)
                    {
                        customizationPage = _storefront
                            .BrowseWeaponCustomization(
                                _customizationPage.WeaponId,
                                _customizationGroup,
                                1,
                                WeaponCustomizationScrollLimit,
                                refresh: true);
                    }
                }

                _snapshot = snapshot;
                _page = page;
                _request.Page = page.Page;
                _weaponPage = weaponPage;
                _weaponRequest.Page = weaponPage.Page;
                _customWeaponPage = customWeaponPage;
                _customWeaponRequest.Page = customWeaponPage.Page;
                _gearPage = gearPage;
                _gearRequest.Page = gearPage.Page;
                _garage = garage;
                AdoptGarageDefault(garage, force: false);
                if (_customizationPage != null && !selectedWeaponStillHeld)
                {
                    StopWeaponPreviewCore();
                    _customizationGroup = "components";
                }
                _customizationPage = customizationPage;

                PublishSynchronizedMenus(force: false);
                Status = "Live game state synchronized (menu revision " +
                    _menuRevision + ").";
                return true;
            }
            catch (Exception ex)
            {
                Status = "Game-state synchronization failed: " +
                    ex.GetType().Name + ": " + ex.Message;
                return false;
            }
        }

        private void PublishSynchronizedMenus(bool force)
        {
            var changed = new List<string>();
            if (_storefront is IAllin1HitchStorefront)
                PublishIfChanged(HitchesMenuId, BuildHitchesMenu(), force, changed);
            PublishIfChanged(
                VehiclesMenuId, BuildVehiclesMenu(_page!), force, changed);
            PublishIfChanged(
                HomeMenuId, BuildHomeMenu(_snapshot!), force, changed);
            PublishIfChanged(
                WeaponsMenuId, BuildWeaponsMenu(_weaponPage!), force, changed);
            PublishIfChanged(
                CustomizeMenuId, BuildCustomizeMenu(), force, changed);
            PublishIfChanged(
                GearMenuId, BuildGearMenu(_gearPage!), force, changed);
            PublishIfChanged(
                GarageMenuId, BuildGarageMenu(_garage!), force, changed);
            PublishIfChanged(
                AddonsMenuId, BuildAddonsMenu(_snapshot!), force, changed);
            PublishIfChanged(
                DiagnosticsMenuId, BuildDiagnosticsMenu(_snapshot!), force,
                changed);
            PublishIfChanged(
                AboutMenuId, BuildAboutMenu(_snapshot!), force, changed);

            if (changed.Count > 0)
            {
                _handle!.TryPublishEvent(
                    "state.changed",
                    new JObject
                    {
                        ["revision"] = _menuRevision,
                        ["menus"] = new JArray(changed),
                    });
            }
        }

        private void PublishIfChanged(
            string menuId, ReactorMenuDescriptor descriptor, bool force,
            ICollection<string> changed)
        {
            string fingerprint = JsonConvert.SerializeObject(
                descriptor, Formatting.None);
            if (!force && _publishedState.TryGetValue(
                    menuId, out string previous) &&
                string.Equals(previous, fingerprint,
                    StringComparison.Ordinal))
                return;
            UpdateMenu(descriptor);
            _publishedState[menuId] = fingerprint;
            changed.Add(menuId);
        }

        private void UpdateAllMenus()
        {
            UpdateMenu(BuildVehiclesMenu(_page!));
            UpdateDynamicMenus();
        }

        private void UpdateDynamicMenus()
        {
            UpdateMenu(BuildHomeMenu(_snapshot!));
            UpdateMenu(BuildWeaponsMenu(_weaponPage!));
            UpdateMenu(BuildCustomizeMenu());
            UpdateMenu(BuildGearMenu(_gearPage!));
            UpdateMenu(BuildGarageMenu(_garage!));
            UpdateMenu(BuildAddonsMenu(_snapshot!));
            UpdateMenu(BuildDiagnosticsMenu(_snapshot!));
            UpdateMenu(BuildAboutMenu(_snapshot!));
        }

        private void UpdateMenu(ReactorMenuDescriptor descriptor)
        {
            _handle!.UpdateMenu(descriptor);
            unchecked { _menuRevision++; }
        }

        private ReactorMenuDescriptor BuildHomeMenu(Allin1GbaySnapshot snapshot)
        {
            bool content = snapshot.OnlineContentEnabled;
            return new ReactorMenuDescriptor(
                HomeMenuId,
                "GBAY",
                new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "balance", "Balance", "$" + snapshot.Balance.ToString("N0"),
                        "success"),
                    new ReactorSubmenuNode(
                        "vehicles", "Vehicles", VehiclesMenuId,
                        "Browse and deliver road vehicles", content),
                    new ReactorSubmenuNode(
                        "purchase-weapons", "Purchase Weapons", WeaponsMenuId,
                        "Buy firearms and ammunition", content),
                    new ReactorSubmenuNode(
                        "customize-weapons", "Customize Weapons", CustomizeMenuId,
                        "Ammo, components, finishes, and livery colors", content),
                    new ReactorSubmenuNode(
                        "gear", "Gear", GearMenuId,
                        "Armor, equipment, and field gear", content),
                    new ReactorSubmenuNode(
                        "garage", "My Garage", GarageMenuId,
                        "Manage every personal storage location", content),
                    new ReactorSubmenuNode(
                        "addons", "Add-ons", AddonsMenuId,
                        snapshot.Addons.Count > 0
                            ? "Open installed content-pack actions"
                            : "No installed add-on actions",
                        snapshot.Addons.Count > 0),
                    new ReactorSubmenuNode(
                        "diagnostics", "Diagnostics", DiagnosticsMenuId,
                        "Installation, content, and runtime status"),
                    new ReactorSubmenuNode(
                        "about", "About", AboutMenuId,
                        "ALLIN1 version, credits, and support"),
                },
                "Story Mode marketplace",
                icon: "gbay",
                order: 0);
        }

        private ReactorMenuDescriptor BuildVehiclesMenu(
            Allin1VehicleCatalogPage page)
        {
            if (_checkout != null)
                return BuildDeliveryMenu(_checkout);

            var categories = _storefront!.Categories.Select(value =>
                new ReactorChoiceOption(value, CategoryLabel(value))).ToArray();
            var ownership = new[]
            {
                new ReactorChoiceOption("all", "All listings"),
                new ReactorChoiceOption("owned", "Owned"),
                new ReactorChoiceOption("available", "Not owned"),
            };
            ReactorMenuNode[] cards = page.Items.Count == 0
                ? new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "empty", "No vehicles", "Change the search or filters.",
                        "neutral"),
                }
                : page.Items.Select(listing =>
                    (ReactorMenuNode)new ReactorActionNode(
                        VehicleNodeId(listing.Model),
                        listing.DisplayName,
                        "vehicle.checkout",
                        ListingDescription(listing),
                        enabled: listing.Available,
                        visible: true,
                        boundParameters: ListingParameters(listing))).ToArray();
            ReactorMenuNode[] favoriteActions = page.Items.Select(listing =>
                (ReactorMenuNode)new ReactorActionNode(
                    "favorite-" + VehicleNodeSuffix(listing.Model),
                    listing.Favorite ? "Remove favorite" : "Add favorite",
                    "vehicle.favorite",
                    listing.DisplayName,
                    enabled: true,
                    visible: true,
                    boundParameters: new JObject
                    {
                        ["model"] = listing.Model,
                    })).ToArray();
            ReactorMenuNode[] artwork = page.Items
                .Select(listing => CatalogArtworkNode(
                    VehicleNodeId(listing.Model),
                    listing.DisplayName,
                    "vehicles",
                    listing.PreviewDictionary,
                    listing.PreviewTexture, listing.Model))
                .Where(node => node != null)
                .Cast<ReactorMenuNode>()
                .ToArray();

            var nodes = new List<ReactorMenuNode>
            {
                new ReactorStatusNode(
                    "balance", "Balance", "$" + page.Balance.ToString("N0"),
                    "success"),
                new ReactorSearchNode(
                    "search", "Search", "vehicle.search", page.Search,
                    "Vehicle or manufacturer", 96),
                new ReactorChoiceNode(
                    "category", "Category", "vehicle.category", categories,
                    page.Category),
                new ReactorChoiceNode(
                    "ownership", "Ownership", "vehicle.ownership", ownership,
                    page.Ownership),
                new ReactorToggleNode(
                    "favorites", "Favorites only", "vehicle.favorites",
                    page.FavoritesOnly),
                new ReactorStatusNode(
                    "results", "Listings",
                    page.TotalItems.ToString(CultureInfo.InvariantCulture) +
                        " matching vehicles", "neutral"),
            };
            nodes.Add(new ReactorGridNode(
                "catalog", "Vehicles", cards, columns: 3));
            if (_storefront is IAllin1HitchStorefront)
                nodes.Insert(0, new ReactorSubmenuNode("vehicle-hitches", "Trailer hitches", HitchesMenuId, "Connect or disconnect a trailer on your current vehicle."));
            nodes.AddRange(artwork);
            if (favoriteActions.Length > 0)
                nodes.Add(new ReactorListNode(
                    "favorite-actions", "Favorites", favoriteActions,
                    "Favorite controls for the six visible listings."));
            nodes.Add(new ReactorPaginationNode(
                "pages", "Page", "vehicle.page", page.Page, page.PageCount));
            return new ReactorMenuDescriptor(
                VehiclesMenuId, "VEHICLES", nodes,
                "Browse the ALLIN1 vehicle catalog and choose a guarded delivery.",
                icon: "vehicle", order: 10);
        }

        private ReactorMenuDescriptor BuildHitchesMenu()
        {
            var snapshot = ((IAllin1HitchStorefront)_storefront!).BrowseHitches();
            var nodes = new List<ReactorMenuNode> { new ReactorStatusNode("hitch-status", "Current vehicle", snapshot.Status) };
            if (!string.IsNullOrEmpty(snapshot.DisconnectToken))
                nodes.Add(new ReactorActionNode("hitch-detach", "Disconnect trailer", "hitch.disconnect", "Stop both vehicles first.",
                    enabled: true, visible: true, boundParameters: new JObject { ["token"] = snapshot.DisconnectToken }));
            foreach (var option in snapshot.Options)
                nodes.Add(new ReactorActionNode("hitch-" + option.Token, option.Label,
                    option.Experimental ? "hitch.connect.experimental" : "hitch.connect", option.Status,
                    enabled: option.Available, visible: true, boundParameters: new JObject { ["token"] = option.Token }));
            nodes.Add(new ReactorSubmenuNode("hitch-back", "Back to vehicles", VehiclesMenuId));
            return new ReactorMenuDescriptor(HitchesMenuId, "TRAILER HITCHES", nodes,
                "SDK-authored front/rear profiles and native hitch detection. One live connection per vehicle.", icon: "vehicle", order: 11);
        }

        private ReactorActionResult HitchAction(string token, bool disconnect, bool experimental)
        {
            lock (_sync)
            {
                if (!Available() || !(_storefront is IAllin1HitchStorefront hitches)) return Unavailable();
                var result = disconnect ? hitches.DisconnectHitch(token) : hitches.ConnectHitch(token, experimental);
                UpdateMenu(BuildHitchesMenu());
                return result.Succeeded ? ReactorActionResult.Success(new JObject { ["message"] = result.Message, ["presentation"] = "refresh", ["menuRevision"] = RevisionText() })
                    : ReactorActionResult.Failure(result.Code, result.Message);
            }
        }

        private ReactorMenuDescriptor BuildDeliveryMenu(
            Allin1VehicleCheckoutResult checkout)
        {
            ReactorMenuNode[] destinations = checkout.Destinations.Select(value =>
                (ReactorMenuNode)new ReactorActionNode(
                    "destination-" + value.Id,
                    value.Label,
                    "vehicle.delivery.confirm",
                    value.Status,
                    enabled: value.Available,
                    visible: true,
                    boundParameters: new JObject
                    {
                        ["model"] = checkout.Model,
                        ["quotedprice"] = checkout.QuotedPrice,
                        ["destination"] = value.Id,
                    })).ToArray();
            var nodes = new List<ReactorMenuNode>
            {
                new ReactorStatusNode(
                    "checkout-vehicle", "Vehicle",
                    checkout.Model, "neutral"),
                new ReactorStatusNode(
                    "checkout-price", "Price",
                    checkout.QuotedPrice <= 0 ? "FREE" : "$" +
                        checkout.QuotedPrice.ToString("N0"), "success"),
                new ReactorGridNode(
                    "delivery-destinations", "Choose delivery location",
                    destinations, columns: 3),
                new ReactorActionNode(
                    "delivery-back", "Back to Vehicles",
                    "vehicle.delivery.cancel",
                    "Cancel this quote without changing Story Mode."),
            };
            return new ReactorMenuDescriptor(
                VehiclesMenuId, "CHOOSE DELIVERY", nodes,
                checkout.Message, icon: "vehicle", order: 10);
        }

        private ReactorMenuDescriptor BuildWeaponsMenu(
            Allin1WeaponCatalogPage page)
        {
            ReactorChoiceOption[] categories = _storefront!.WeaponCategories
                .Select(value => new ReactorChoiceOption(
                    value, WeaponCategoryLabel(value))).ToArray();
            var ownership = new[]
            {
                new ReactorChoiceOption("all", "All listings"),
                new ReactorChoiceOption("owned", "Owned"),
                new ReactorChoiceOption("available", "Not owned"),
            };
            ReactorMenuNode[] cards = page.Items.Count == 0
                ? new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "empty", "No weapons", "Change the search or filters."),
                }
                : page.Items.Select(value =>
                    (ReactorMenuNode)new ReactorActionNode(
                        "weapon-" + VehicleNodeSuffix(value.Id),
                        WeaponCardLabel(value),
                        "weapon.purchase",
                        WeaponDescription(value),
                        enabled: value.PurchaseAvailable &&
                            (!value.Owned || value.SmokeProduct),
                        visible: true,
                        boundParameters: new JObject
                        {
                            ["weapon"] = value.Id,
                            ["quotedprice"] = value.TotalPrice,
                        })).ToArray();
            ReactorMenuNode[] favorites = page.Items.Select(value =>
                (ReactorMenuNode)new ReactorActionNode(
                    "weapon-favorite-" + VehicleNodeSuffix(value.Id),
                    value.Favorite ? "Remove favorite" : "Add favorite",
                    "weapon.favorite",
                    value.DisplayName,
                    enabled: true,
                    visible: true,
                    boundParameters: new JObject
                    {
                        ["weapon"] = value.Id,
                    })).ToArray();
            ReactorMenuNode[] artwork = page.Items
                .Select(value => CatalogArtworkNode(
                    "weapon-" + VehicleNodeSuffix(value.Id),
                    value.DisplayName,
                    "weapons",
                    value.PreviewDictionary,
                    value.PreviewTexture, value.Id))
                .Where(node => node != null)
                .Cast<ReactorMenuNode>()
                .ToArray();
            var nodes = new List<ReactorMenuNode>
            {
                new ReactorStatusNode(
                    "balance", "Balance", "$" + page.Balance.ToString("N0"),
                    "success"),
                new ReactorSearchNode(
                    "search", "Search", "weapon.search", page.Search,
                    "Weapon name", 96),
                new ReactorChoiceNode(
                    "category", "Category", "weapon.category", categories,
                    page.Category),
                new ReactorChoiceNode(
                    "ownership", "Ownership", "weapon.ownership", ownership,
                    page.Ownership),
                new ReactorToggleNode(
                    "favorites", "Favorites only", "weapon.favorites",
                    page.FavoritesOnly),
                new ReactorStatusNode(
                    "results", "Listings", page.TotalItems + " matching weapons"),
                new ReactorGridNode(
                    "catalog", "Weapons", cards, columns: 3),
            };
            nodes.AddRange(artwork);
            if (favorites.Length > 0)
                nodes.Add(new ReactorListNode(
                    "favorite-actions", "Favorites", favorites));
            nodes.Add(new ReactorPaginationNode(
                "pages", "Page", "weapon.page", page.Page, page.PageCount));
            return new ReactorMenuDescriptor(
                WeaponsMenuId, "PURCHASE WEAPONS", nodes,
                "Buy firearms, throwables, and smoke-grenade bundles.",
                icon: "weapon", order: 20);
        }

        private ReactorMenuDescriptor BuildCustomizeMenu()
        {
            if (_customWeaponPage == null)
                return new ReactorMenuDescriptor(
                    CustomizeMenuId,
                    "CUSTOMIZE WEAPONS",
                    new ReactorMenuNode[]
                    {
                        new ReactorStatusNode(
                            "availability", "Checking current character",
                            "Waiting for owned weapons", "neutral",
                            "Owned weapons become available automatically when " +
                            "the player and storefront are ready."),
                    },
                    "Refill ammunition and manage compatible components, " +
                    "weapon finishes, and active-livery colors.",
                    icon: "weapon", order: 30);

            if (_customizationPage == null)
            {
                ReactorChoiceOption[] categories = _storefront!
                    .WeaponCategories.Select(value =>
                        new ReactorChoiceOption(
                            value, WeaponCategoryLabel(value))).ToArray();
                ReactorMenuNode[] weapons = _customWeaponPage.Items.Count == 0
                    ? new ReactorMenuNode[]
                    {
                        new ReactorStatusNode(
                            "empty", "No held weapons",
                            BoundText(_customWeaponPage.Status, 240), "neutral"),
                    }
                    : _customWeaponPage.Items.Select(value =>
                        (ReactorMenuNode)new ReactorActionNode(
                            "custom-weapon-" + VehicleNodeSuffix(value.Id),
                            BoundText(value.DisplayName, 96),
                            "weapon.customize.select",
                            "Category: " + BoundText(value.Category, 64) +
                                " · Ammo: " + BoundText(value.AmmoStatus, 128),
                            enabled: true,
                            visible: true,
                            boundParameters: new JObject
                            {
                                ["weapon"] = value.Id,
                            })).ToArray();
                ReactorMenuNode[] artwork = _customWeaponPage.Items
                    .Select(value => CatalogArtworkNode(
                        "custom-weapon-" + VehicleNodeSuffix(value.Id),
                        value.DisplayName,
                        "weapons",
                        value.PreviewDictionary,
                        value.PreviewTexture, value.Id))
                    .Where(node => node != null)
                    .Cast<ReactorMenuNode>()
                    .ToArray();
                var nodes = new List<ReactorMenuNode>
                {
                    new ReactorSearchNode(
                        "custom-search", "Search",
                        "weapon.customize.search",
                        _customWeaponPage.Search, "Owned weapon", 96),
                    new ReactorChoiceNode(
                        "custom-category", "Category",
                        "weapon.customize.category", categories,
                        _customWeaponPage.Category),
                    new ReactorStatusNode(
                        "custom-results", "Owned weapons",
                        _customWeaponPage.TotalItems + " currently held"),
                    new ReactorGridNode(
                        "owned-weapons", "Owned weapons",
                        weapons, columns: 3),
                };
                nodes.AddRange(artwork);
                nodes.Add(new ReactorStatusNode("custom-scroll-status", "Weapon list",
                    BoundText(_customWeaponPage.Status, 240)));
                return new ReactorMenuDescriptor(
                    CustomizeMenuId,
                    "CUSTOMIZE WEAPONS",
                    nodes,
                    BoundText(_customWeaponPage.Status, 240),
                    icon: "weapon", order: 30);
            }

            var groups = new[]
            {
                new ReactorChoiceOption("ammo", "Ammunition"),
                new ReactorChoiceOption("components", "Components"),
                new ReactorChoiceOption("tints", "Weapon finishes"),
                new ReactorChoiceOption("livery", "Livery colors"),
            };
            ReactorMenuNode[] options = _customizationPage.Items.Count == 0
                ? new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "empty-options", "No options",
                        BoundText(_customizationPage.Status, 240), "neutral"),
                }
                : _customizationPage.Items.SelectMany(value =>
                {
                    bool stockedAmmo = value.Kind == "ammo" && value.Active;
                    string status = stockedAmmo ? "Fully stocked"
                        : value.Kind == "component_remove" ? "Unequip · ownership retained"
                        : value.Active ? "Active"
                        : value.Owned ? "Owned — equip" : "Available";
                    string price = stockedAmmo ? "FULL"
                        : value.Price <= 0
                        ? "FREE" : "$" + value.Price.ToString("N0");
                    // Pair the explicit removal command with the original
                    // component card. React never infers removal authority
                    // from a label or turns an equip request into a toggle.
                    bool removal = value.Kind == "component_remove";
                    string nodeId = "custom-option-" + VehicleNodeSuffix(
                            _customizationPage.WeaponId + ":" + (removal ? "component" : value.Kind) +
                            ":" + value.ComponentHash + ":" +
                            value.AttachmentPoint + ":" + value.Tint) +
                            (removal ? "-unequip" : "");
                    string description =
                        "Type: " + CustomizationKindLabel(value.Kind) +
                        " · Status: " + status + " · Price: " + price +
                        " · Detail: " + BoundText(value.Detail, 180);
                    var previewParameters = new JObject
                    {
                        ["weapon"] = _customizationPage.WeaponId,
                        ["kind"] = value.Kind,
                        ["component"] = value.ComponentHash,
                        ["attachment"] = value.AttachmentPoint,
                        ["tint"] = value.Tint,
                    };
                    var applyParameters = (JObject)previewParameters.DeepClone();
                    applyParameters["quotedprice"] = value.Price;
                    return new ReactorMenuNode[]
                    {
                        new ReactorActionNode(
                            nodeId,
                            BoundText(value.Label, 112),
                            "weapon.customize.apply",
                            description,
                            enabled: !value.Active,
                            visible: true,
                            boundParameters: applyParameters),
                        // Reactor's ALLIN1 surface treats this paired node as
                        // a focus action. It remains a normal typed read action
                        // for other menu clients and never shares apply authority.
                        new ReactorActionNode(
                            nodeId + "-preview",
                            "Preview " + BoundText(value.Label, 96),
                            "weapon.customize.preview",
                            "Temporarily show this option on the in-world dummy.",
                            enabled: true,
                            visible: true,
                            boundParameters: previewParameters),
                    };
                }).ToArray();
            return new ReactorMenuDescriptor(
                CustomizeMenuId,
                "CUSTOMIZE " + BoundText(
                    _customizationPage.DisplayName, 72).ToUpperInvariant(),
                new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "custom-balance", "Balance",
                        "$" + _customizationPage.Balance.ToString("N0"),
                        "success"),
                    new ReactorStatusNode(
                        "selected-weapon", "Weapon",
                        BoundText(_customizationPage.DisplayName, 96),
                        "neutral"),
                    new ReactorStatusNode(
                        "world-preview", "In-world preview",
                        "Active alongside Reactor", "success",
                        "The camera and dummy are hosted by ALLIN1 while all " +
                        "workbench controls remain in this React menu."),
                    new ReactorChoiceNode(
                        "option-group", "Options",
                        "weapon.customize.group", groups,
                        _customizationPage.Group),
                    new ReactorStatusNode(
                        "option-results", "Compatible options",
                        _customizationPage.TotalItems + " matching options"),
                    new ReactorGridNode(
                        "workbench-options", "Workbench options",
                        options, columns: 3),
                    new ReactorActionNode(
                        "back-to-owned-weapons", "Back to owned weapons",
                        "weapon.customize.back",
                        "Return without changing the selected weapon."),
                    new ReactorActionNode(
                        "stop-world-preview", "Close world preview",
                        "weapon.customize.preview.stop",
                        "Release the dummy and camera when leaving this section."),
                },
                "ALLIN1's guarded customization service validates every change against " +
                "the live game and previews it on a world-space character.",
                icon: "weapon", order: 30);
        }

        private ReactorMenuDescriptor BuildGearMenu(
            Allin1GearCatalogPage page)
        {
            ReactorChoiceOption[] categories = _storefront!.GearCategories
                .Select(value => new ReactorChoiceOption(
                    value, CategoryLabel(value))).ToArray();
            ReactorMenuNode[] cards = page.Items.Select(value =>
            {
                string operation = value.Equipped ? "unequip"
                    : value.Owned ? "equip" : "purchase";
                string action = value.Equipped ? "Remove (repurchase required)"
                    : value.Owned ? "Equip" : "Purchase";
                string price = value.Price <= 0
                    ? "FREE" : "$" + value.Price.ToString("N0");
                return (ReactorMenuNode)new ReactorActionNode(
                    "gear-" + VehicleNodeSuffix(value.Id),
                    value.DisplayName,
                    "gear.apply",
                    "Category: " + value.Category + " · Status: " + action +
                        " · Price: " + price,
                    enabled: true,
                    visible: true,
                    boundParameters: new JObject
                    {
                        ["gear"] = value.Id,
                        ["operation"] = operation,
                        ["quotedprice"] = value.Price,
                    });
            }).ToArray();
            ReactorMenuNode[] artwork = page.Items
                .Select(value => CatalogArtworkNode(
                    "gear-" + VehicleNodeSuffix(value.Id),
                    value.DisplayName,
                    "gear",
                    value.PreviewDictionary,
                    value.PreviewTexture, value.Id))
                .Where(node => node != null)
                .Cast<ReactorMenuNode>()
                .ToArray();
            var nodes = new List<ReactorMenuNode>
            {
                new ReactorStatusNode(
                    "balance", "Balance", "$" + page.Balance.ToString("N0"),
                    "success"),
                new ReactorChoiceNode(
                    "category", "Category", "gear.category", categories,
                    page.Category),
                new ReactorGridNode(
                    "catalog", "Gear", cards, columns: 3),
            };
            nodes.AddRange(artwork);
            nodes.Add(new ReactorPaginationNode(
                "pages", "Page", "gear.page", page.Page, page.PageCount));
            return new ReactorMenuDescriptor(
                GearMenuId, "GEAR", nodes,
                "Armor and equipment use ALLIN1's per-character inventory.",
                icon: "gear", order: 40);
        }

        private ReactorMenuDescriptor BuildGarageMenu(
            Allin1GarageSnapshot garage)
        {
            var locationOptions = new List<ReactorChoiceOption>
            {
                new ReactorChoiceOption("all", "All locations"),
            };
            locationOptions.AddRange(garage.Locations.Select(value =>
                new ReactorChoiceOption(value.Id, value.Label)));
            // Reactor's garage selector joins choice values to status nodes by
            // the exact `location-{id}` identity. Keep that read-only status
            // separate from the waypoint command: using the waypoint node as
            // the only location row made every selector entry fall back to
            // "Unavailable" even while the garage service was healthy.
            ReactorMenuNode[] locationStatusNodes = garage.Locations.Select(
                value => (ReactorMenuNode)new ReactorStatusNode(
                    "location-" + value.Id,
                    value.Label,
                    (string.Equals(value.Id, garage.ActiveLocationId,
                        StringComparison.OrdinalIgnoreCase)
                            ? "Active · " : "") + value.Status,
                    "neutral"))
                .ToArray();
            ReactorMenuNode[] locationWaypointNodes = garage.Locations.Select(
                value => (ReactorMenuNode)new ReactorActionNode(
                    "location-waypoint-" + value.Id,
                    "Navigate to " + value.Label,
                    "garage.waypoint",
                    "Set a GPS route to this garage.",
                    enabled: true,
                    visible: true,
                    boundParameters: new JObject
                    {
                        ["location"] = value.Id,
                    }))
                .ToArray();
            Allin1GarageVehicleListing[] filtered = garage.Vehicles
                .Where(value => _garageLocation == "all" || string.Equals(
                    value.LocationId, _garageLocation,
                    StringComparison.OrdinalIgnoreCase))
                .ToArray();
            var vehicleNodes = new List<ReactorMenuNode>();
            foreach (Allin1GarageVehicleListing value in filtered)
            {
                var bound = new JObject
                {
                    ["location"] = value.LocationId,
                    ["index"] = value.ListIndex,
                    ["model"] = value.Model,
                    ["modelhash"] = value.ModelHash,
                    ["plate"] = value.PlateText,
                };
                string identity = value.LocationId + "-" + value.ListIndex;
                string location = "Location: " + value.LocationLabel +
                    " · Plate: " + (string.IsNullOrWhiteSpace(value.PlateText)
                        ? "None" : value.PlateText);
                if (value.Retrievable)
                {
                    vehicleNodes.Add(new ReactorActionNode(
                        "stored-" + identity + "-retrieve",
                        "Retrieve " + value.DisplayName,
                        "garage.retrieve",
                        location + " · Move this vehicle into the world.",
                        enabled: true,
                        visible: true,
                        boundParameters: (JObject)bound.DeepClone()));
                }
                else if (value.Sellable)
                {
                    string price = value.SellPrice > 0
                        ? "$" + value.SellPrice.ToString("N0") : "Remove";
                    JObject sellBound = (JObject)bound.DeepClone();
                    sellBound["quotedprice"] = value.SellPrice;
                    vehicleNodes.Add(new ReactorActionNode(
                        "stored-" + identity + "-sell",
                        value.SellPrice > 0
                            ? "Sell " + value.DisplayName
                            : "Remove " + value.DisplayName,
                        "garage.sell",
                        location + " · Sale value: " + price,
                        enabled: true,
                        visible: true,
                        boundParameters: sellBound));
                }
                else
                    vehicleNodes.Add(new ReactorStatusNode(
                        "stored-" + identity + "-protected",
                        value.DisplayName,
                        location + " · Story-protected vehicle.",
                        "warning"));
            }
            if (vehicleNodes.Count == 0)
                vehicleNodes.Add(new ReactorStatusNode(
                    "empty", "No vehicles",
                    _garageLocation == "all"
                        ? "No vehicles are stored."
                        : "No vehicles are stored at this location."));
            var nodes = new List<ReactorMenuNode>
            {
                new ReactorChoiceNode(
                    "location-filter", "Location", "garage.location",
                    locationOptions, _garageLocation),
                new ReactorListNode(
                    "locations", "Storage", locationStatusNodes
                        .Concat(locationWaypointNodes).ToArray()),
                new ReactorStatusNode(
                    "results", "Stored vehicles",
                    filtered.Length + " matching vehicles"),
                new ReactorGridNode(
                    "vehicles", "Stored vehicles",
                    vehicleNodes.ToArray(), columns: 2),
            };
            AddGarageInteriorNodes(nodes, garage);
            nodes.Add(new ReactorActionNode(
                "emergency-recovery", "Emergency Recovery",
                "garage.recover",
                string.IsNullOrWhiteSpace(garage.EmergencyRecoveryStatus)
                    ? "Use only if a managed garage transition leaves you stuck."
                    : garage.EmergencyRecoveryStatus,
                // Recovery authority is intentionally checked at invocation.
                // A cached descriptor must not strand a player who entered a
                // garage after GBAY initialized.
                enabled: true,
                visible: true));
            return new ReactorMenuDescriptor(
                GarageMenuId,
                "MY GARAGE",
                nodes,
                "Browse, sell, and retrieve vehicles through guarded ALLIN1 services.",
                icon: "garage", order: 50);
        }

        private void AdoptGarageDefault(
            Allin1GarageSnapshot garage, bool force)
        {
            Allin1VehicleDeliveryOption[] locations =
                (garage?.Locations ??
                    Array.Empty<Allin1VehicleDeliveryOption>())
                .Where(value => value != null &&
                    !string.IsNullOrWhiteSpace(value.Id))
                .ToArray();
            if (locations.Length == 0)
            {
                if (force) _garageLocation = "all";
                return;
            }

            bool currentExists = locations.Any(value => string.Equals(
                value.Id, _garageLocation,
                StringComparison.OrdinalIgnoreCase));
            if (!force && _garageLocation != "all" && currentExists)
                return;

            string active = (garage?.ActiveLocationId ?? "").Trim();
            Allin1VehicleDeliveryOption selected = locations.FirstOrDefault(
                value => string.Equals(value.Id, active,
                    StringComparison.OrdinalIgnoreCase)) ?? locations[0];
            _garageLocation = selected.Id;
        }

        private void AddGarageInteriorNodes(
            List<ReactorMenuNode> nodes, Allin1GarageSnapshot garage)
        {
            if (string.Equals(_garageLocation, "davis",
                    StringComparison.OrdinalIgnoreCase) &&
                garage.Customization != null)
            {
                Allin1GarageCustomizationSnapshot customization =
                    garage.Customization;
                nodes.Add(new ReactorStatusNode(
                    "interior-mode", "Davis Auto Shop interior",
                    string.IsNullOrWhiteSpace(customization.Status)
                        ? "Appearance options are saved per Story character."
                        : customization.Status,
                    customization.Available ? "success" : "warning"));
                foreach (Allin1GarageCustomizationCategory category in
                    customization.Categories ??
                        Array.Empty<Allin1GarageCustomizationCategory>())
                {
                    ReactorChoiceOption[] options = (category.Options ??
                            Array.Empty<Allin1GarageCustomizationOption>())
                        .Select(value => new ReactorChoiceOption(
                            value.Id, value.Label))
                        .ToArray();
                    if (options.Length == 0) continue;
                    nodes.Add(new ReactorChoiceNode(
                        "davis-" + category.Id,
                        category.Label,
                        "garage.customize",
                        options,
                        category.SelectedOptionId,
                        customization.LivePreview
                            ? "Saved per character · live preview active."
                            : "Saved per character · applied when Davis loads.",
                        enabled: customization.Available,
                        visible: true,
                        boundParameters: new JObject
                        {
                            ["location"] = customization.LocationId,
                            ["category"] = category.Id,
                            ["expected"] = category.SelectedOptionId,
                        }));
                }
                return;
            }

            if (_garageLocation == "all")
            {
                nodes.Add(new ReactorStatusNode(
                    "interior-mode", "Garage interiors",
                    "Davis Auto Shop is customizable. Other locations use " +
                    "finished fixed interiors."));
                return;
            }

            Allin1VehicleDeliveryOption? location = garage.Locations
                .FirstOrDefault(value => string.Equals(
                    value.Id, _garageLocation,
                    StringComparison.OrdinalIgnoreCase));
            string mode = location?.InteriorMode ?? "fixed";
            string label = mode == "specialized"
                ? "Specialized storage"
                : "Fixed interior";
            string interiorStatus = location?.InteriorStatus ?? "";
            nodes.Add(new ReactorStatusNode(
                "interior-mode", label,
                string.IsNullOrWhiteSpace(interiorStatus)
                    ? mode == "specialized"
                        ? "This location uses outdoor specialized storage."
                        : "This location uses its finished fixed interior."
                    : interiorStatus));
        }

        private static string WeaponCategoryLabel(string value)
        {
            switch ((value ?? "").ToLowerInvariant())
            {
                case "smgs": return "SMGs";
                case "machineguns": return "Machine Guns";
                case "snipers": return "Sniper Rifles";
                case "heavy": return "Heavy Weapons";
                case "misc": return "Miscellaneous";
                default: return CategoryLabel(value ?? "");
            }
        }

        private void RefreshLoadedCustomizationState()
        {
            if (_customWeaponPage == null) return;
            _customWeaponPage = _storefront!.BrowseCustomizableWeapons(
                _customWeaponRequest);
            _customWeaponRequest.Page = _customWeaponPage.Page;
            if (_customizationPage == null) return;
            _customizationPage = _storefront.BrowseWeaponCustomization(
                _customizationPage.WeaponId, _customizationGroup,
                1, WeaponCustomizationScrollLimit, refresh: true);
        }

        private static string CustomizationKindLabel(string kind)
        {
            switch ((kind ?? "").ToLowerInvariant())
            {
                case "ammo": return "Ammunition";
                case "component": return "Component";
                case "tint": return "Weapon finish";
                case "component_tint": return "Livery color";
                case "component_remove": return "Unequip attachment";
                default: return "Option";
            }
        }

        private static string BoundText(string value, int maximum)
        {
            string normalized = (value ?? "").Trim();
            if (normalized.Length <= maximum) return normalized;
            return normalized.Substring(0, Math.Max(0, maximum - 1)) + "…";
        }

        private static string WeaponDescription(Allin1WeaponListing value)
        {
            string price = value.TotalPrice <= 0
                ? "FREE" : "$" + value.TotalPrice.ToString("N0");
            string status = value.SmokeProduct
                ? value.Stock + " in stock"
                : value.Owned ? "Owned" : "Available";
            string quantity = value.Quantity > 1
                ? " · Quantity: " + value.Quantity : "";
            return "Price: " + price + " · Ownership: " + status +
                " · Category: " + value.Category + quantity +
                " · Status: " + value.AvailabilityStatus;
        }

        private static string WeaponCardLabel(Allin1WeaponListing value)
        {
            if (value.Owned && !value.SmokeProduct)
                return value.DisplayName + "  ·  OWNED";
            return value.DisplayName;
        }

        private static ReactorMenuDescriptor BuildAddonsMenu(
            Allin1GbaySnapshot snapshot)
        {
            ReactorMenuNode[] nodes = snapshot.Addons.Count == 0
                ? new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "empty", "No add-ons",
                        "No enabled content-pack actions are registered.",
                        "neutral"),
                }
                : snapshot.Addons.Select((value, index) =>
                    (ReactorMenuNode)new ReactorActionNode(
                        "addon-" + index,
                        value.Label,
                        "addon.invoke",
                        value.Description,
                        enabled: true,
                        visible: true,
                        boundParameters: new JObject
                        {
                            ["package"] = value.PackageId,
                            ["route"] = value.Route,
                        })).ToArray();
            return new ReactorMenuDescriptor(
                AddonsMenuId, "ADD-ONS", nodes,
                "Receipt-authorized actions from enabled ALLIN1 packages.",
                icon: "addon", order: 60);
        }

        private static ReactorMenuDescriptor BuildDiagnosticsMenu(
            Allin1GbaySnapshot snapshot) => new ReactorMenuDescriptor(
                DiagnosticsMenuId,
                "DIAGNOSTICS",
                new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "client", "ALLIN1 client", snapshot.Version, "success"),
                    new ReactorStatusNode(
                        "session", "Session duration",
                        snapshot.SessionSeconds + " seconds", "neutral"),
                    new ReactorStatusNode(
                        "location", "Garage location",
                        snapshot.GarageLocation, "neutral"),
                    new ReactorStatusNode(
                        "traffic", "Traffic", snapshot.TrafficStatus, "neutral"),
                    new ReactorStatusNode(
                        "map-content", "Garage map content",
                        string.IsNullOrWhiteSpace(snapshot.MapContentStatus)
                            ? "Unknown" : snapshot.MapContentStatus,
                        snapshot.MapContentStatus?.IndexOf(
                            "Ready", StringComparison.OrdinalIgnoreCase) >= 0
                                ? "success" : "warning"),
                    new ReactorStatusNode(
                        "safe-mode", "Safe mode",
                        snapshot.SafeMode ? "Active" : "Off",
                        snapshot.SafeMode ? "warning" : "success"),
                    new ReactorStatusNode(
                        "artwork", "GBAY artwork",
                        snapshot.ArtworkStatus, "neutral"),
                    new ReactorStatusNode(
                        "rpf", "RPF support", snapshot.RpfStatus, "neutral"),
                    new ReactorStatusNode(
                        "runtime-log", "Runtime log",
                        string.IsNullOrWhiteSpace(snapshot.RuntimeLogPath)
                            ? "scripts/ALLIN1_client.log"
                            : snapshot.RuntimeLogPath,
                        "neutral"),
                    new ReactorActionNode(
                        "open-runtime-log-folder",
                        "Open runtime log folder",
                        "diagnostics.open-log-folder",
                        "Open the folder containing the current ALLIN1 runtime log."),
                    new ReactorStatusNode(
                        "support", "Support bundle",
                        "Export from the desktop launcher", "neutral"),
                },
                "Installation, content, and runtime status.",
                icon: "diagnostics", order: 70);

        private static ReactorMenuDescriptor BuildAboutMenu(
            Allin1GbaySnapshot snapshot) => new ReactorMenuDescriptor(
                AboutMenuId,
                "ABOUT ALLIN1",
                new ReactorMenuNode[]
                {
                    new ReactorStatusNode(
                        "version", "Version", snapshot.Version, "success"),
                    new ReactorStatusNode(
                        "edition", "GTA edition", DetectedGameEdition(),
                        "success"),
                    new ReactorStatusNode(
                        "runtime", "Script runtime", DetectedScriptRuntime(),
                        "success"),
                    new ReactorStatusNode(
                        "purpose", "ALLIN1",
                        "Bring GTA Online DLC content into Story Mode with one click.",
                        "neutral"),
                    new ReactorStatusNode(
                        "creator", "Created and maintained by", "MinionEnjoyer",
                        "neutral"),
                    new ReactorStatusNode(
                        "support", "Support",
                        "buymeacoffee.com/minionenjoyer", "neutral"),
                    new ReactorActionNode(
                        "open-support", "Open support page", "about.support",
                        "Open the fixed ALLIN1 support page in your browser."),
                },
                "Version, credits, and support.", icon: "about", order: 80);

        private static string DetectedGameEdition()
        {
            try
            {
                return GtaEditionDetector.Detect(
                    GtaEditionDetector.SafeCurrentProcessExecutable(),
                    GtaEditionDetector.SafeAssemblyLocation(
                        typeof(GbayShop).Assembly),
                    GtaEditionDetector.SafeAssemblyLocation(
                        typeof(Allin1ReactorBridge).Assembly),
                    AppDomain.CurrentDomain.BaseDirectory,
                    Environment.CurrentDirectory);
            }
            catch
            {
                // Detection is informational only; never block the About route.
            }
            return "Unknown";
        }

        private static string DetectedScriptRuntime()
        {
            try
            {
                Type? scriptBase = typeof(GbayShop).BaseType;
                AssemblyName? assembly = scriptBase?.Assembly.GetName();
                if (assembly != null)
                {
                    string version = assembly.Version?.ToString(3) ?? "unknown";
                    return (assembly.Name ?? "ScriptHookVDotNet") + " v" + version;
                }
            }
            catch
            {
                // Runtime identity is advisory and must remain fail-safe.
            }
            return "Unavailable";
        }

        private static bool TryResolveWorldEntryLocation(
            Allin1GarageWorldEntryLocation location, out string locationId)
        {
            switch (location)
            {
                case Allin1GarageWorldEntryLocation.VespucciHelipad:
                    locationId = "vespucci-helipad";
                    return true;
                case Allin1GarageWorldEntryLocation.Harbour:
                    locationId = "harbour";
                    return true;
                default:
                    locationId = "";
                    return false;
            }
        }

        private JObject PagePayload(
            Allin1VehicleCatalogPage page, string presentation, string message)
        {
            return new JObject
            {
                ["presentation"] = presentation,
                ["page"] = page.Page,
                ["pageCount"] = page.PageCount,
                ["totalItems"] = page.TotalItems,
                ["catalogRevision"] = page.CatalogRevision,
                ["menuRevision"] = RevisionText(),
                ["message"] = message,
            };
        }

        private JObject CatalogPayload(
            int page, int pageCount, int totalItems, string message) =>
            new JObject
            {
                ["presentation"] = "refresh",
                ["page"] = page,
                ["pageCount"] = pageCount,
                ["totalItems"] = totalItems,
                ["message"] = message,
                ["menuRevision"] = RevisionText(),
            };

        private string RevisionText() => _menuRevision.ToString(
            CultureInfo.InvariantCulture);

        private static JObject ListingParameters(Allin1VehicleListing value) =>
            new JObject
            {
                ["model"] = value.Model,
                ["quotedprice"] = value.Price,
            };

        private static readonly Lazy<Dictionary<string, string>> WeaponArtwork =
            new Lazy<Dictionary<string, string>>(() => ReadCatalogArtwork("weapons", 128));
        private static readonly Lazy<Dictionary<string, string>> VehicleArtwork =
            new Lazy<Dictionary<string, string>>(() => ReadCatalogArtwork("vehicles", 2048));
        private static readonly Lazy<Dictionary<string, string>> GearArtwork =
            new Lazy<Dictionary<string, string>>(() => ReadCatalogArtwork("gear", 128));

        private static Dictionary<string, string> ReadCatalogArtwork(string category, int limit) =>
            CatalogPreviewArtwork.Read(
                Path.GetDirectoryName(GtaEditionDetector.SafeCurrentProcessExecutable()) ?? "", category, limit);

        private static ReactorMediaNode? CatalogArtworkNode(
            string cardId,
            string label,
            string category,
            string previewDictionary,
            string previewTexture,
            string? weaponId = null)
        {
            var images = category == "weapons" ? WeaponArtwork.Value :
                category == "vehicles" ? VehicleArtwork.Value : GearArtwork.Value;
            if (!images.TryGetValue(weaponId ?? previewTexture, out string path)) return null;
            return new ReactorMediaNode(cardId + "-preview", label + " preview",
                path, "image", label + " preview");
        }

        private static string ListingDescription(Allin1VehicleListing value)
        {
            bool catalogOnly = string.Equals(value.Storage, "catalog_only", StringComparison.OrdinalIgnoreCase);
            string price = catalogOnly ? "CATALOG ONLY" : value.Price <= 0
                ? "FREE" : "$" + value.Price.ToString("N0");
            string ownership = catalogOnly ? "Not offered yet" : value.Owned ? "Owned" : "Available";
            string favorite = value.Favorite ? " · Favorite" : "";
            string manufacturer = string.IsNullOrWhiteSpace(value.Manufacturer)
                ? "Unknown" : value.Manufacturer;
            string preview = string.IsNullOrWhiteSpace(value.PreviewDictionary)
                ? "Unavailable"
                : value.PreviewDictionary + "/" + value.PreviewTexture;
            return "Price: " + price + " · Ownership: " + ownership +
                favorite + " · Manufacturer: " + manufacturer +
                " · Model: " + value.Model + " · Category: " +
                CategoryLabel(value.Category) + " · Preview: " + preview;
        }

        private static string CategoryLabel(string value)
        {
            string normalized = value ?? "";
            switch (normalized.ToLowerInvariant())
            {
                case "all": return "All";
                case "sportsclassics": return "Sports Classics";
                case "offroad": return "Off-Road";
                case "openwheel": return "Open Wheel";
                case "suvs": return "SUVs";
                default:
                    return string.IsNullOrWhiteSpace(normalized)
                        ? "Other"
                        : char.ToUpperInvariant(normalized[0]) +
                          normalized.Substring(1);
            }
        }

        private static string VehicleNodeId(string model)
        {
            return "vehicle-" + VehicleNodeSuffix(model);
        }

        private static string VehicleNodeSuffix(string model)
        {
            ulong hash = 14695981039346656037UL;
            unchecked
            {
                foreach (char value in (model ?? "").ToLowerInvariant())
                {
                    hash ^= value;
                    hash *= 1099511628211UL;
                }
            }
            return hash.ToString("x16", CultureInfo.InvariantCulture);
        }

        private static Allin1VehicleCatalogRequest DefaultRequest() =>
            new Allin1VehicleCatalogRequest
            {
                Category = "all",
                Ownership = "all",
                Page = 1,
                PageSize = 6,
                RefreshCatalog = false,
            };

        private static Allin1CatalogRequest DefaultCatalogRequest() =>
            new Allin1CatalogRequest
            {
                Category = "all",
                Ownership = "all",
                Page = 1,
                PageSize = 6,
            };
    }

    /// <summary>
    /// Reflection-only adapter for Reactor's additive presentation-readiness
    /// capability. The bridge must remain loadable with a Core build that
    /// predates this member.
    /// </summary>
    internal static class MenuPresentationReadinessContract
    {
        internal static MethodInfo? Resolve(Type? handleType)
        {
            if (handleType == null) return null;
            MethodInfo? method = handleType.GetMethod(
                "IsMenuPresentationReady",
                BindingFlags.Public | BindingFlags.Instance,
                binder: null,
                types: new[] { typeof(string) },
                modifiers: null);
            return method != null && method.ReturnType == typeof(bool)
                ? method
                : null;
        }
    }

    /// <summary>
    /// Optional startup contract resolved entirely by reflection. Published
    /// Reactor V 0.2.0 builds that predate these methods keep normal GBAY
    /// functionality instead of throwing MissingMethodException when the
    /// optional early-F9 path is inspected.
    /// </summary>
    internal static class StartupIntentContract
    {
        private static readonly Type? ContractType =
            typeof(ReactorApi).Assembly.GetType(
                "RageWebUI.Core.PreloadHandoff",
                throwOnError: false,
                ignoreCase: false);
        private static readonly MethodInfo? ManagedOwnsF9Method =
            Find("ManagedOwnsF9");
        private static readonly MethodInfo? ConsumeMethod =
            Find("TryConsumeDefaultMenuIntent");
        private static readonly MethodInfo? RestoreMethod =
            Find("TryRestoreDefaultMenuIntent");
        private static readonly MethodInfo? ActiveMethod =
            Find("IsDefaultMenuIntentActive");
        private static readonly MethodInfo? CancelMethod =
            Find("TryCancelDefaultMenuIntent");

        internal static bool IsAvailable =>
            HasRequiredMethods(ContractType);

        internal static bool HasRequiredMethods(Type? contractType)
        {
            if (contractType == null) return false;
            return RequiredMethod(contractType, "ManagedOwnsF9") != null &&
                RequiredMethod(contractType, "TryConsumeDefaultMenuIntent") != null &&
                RequiredMethod(contractType, "TryRestoreDefaultMenuIntent") != null &&
                RequiredMethod(contractType, "IsDefaultMenuIntentActive") != null &&
                RequiredMethod(contractType, "TryCancelDefaultMenuIntent") != null;
        }

        internal static bool ManagedOwnsF9(int processId) =>
            InvokeBoolean(ManagedOwnsF9Method, processId);

        internal static bool TryConsume(int processId) =>
            InvokeBoolean(ConsumeMethod, processId);

        internal static bool TryRestore(int processId) =>
            InvokeBoolean(RestoreMethod, processId);

        internal static bool IsActive(int processId) =>
            InvokeBoolean(ActiveMethod, processId);

        internal static bool TryCancel(int processId) =>
            InvokeBoolean(CancelMethod, processId);

        internal static bool TrySignalBootstrapClose(int processId)
        {
            try
            {
                using (var close = EventWaitHandle.OpenExisting(
                           @"Local\ReactorV.BootstrapHostClose." + processId))
                    return close.Set();
            }
            catch (UnauthorizedAccessException) { return false; }
            catch (WaitHandleCannotBeOpenedException) { return false; }
        }

        private static MethodInfo? Find(string name) =>
            ContractType == null ? null : RequiredMethod(ContractType, name);

        private static MethodInfo? RequiredMethod(Type contractType, string name) =>
            contractType.GetMethod(
                name,
                BindingFlags.Public | BindingFlags.Static,
                binder: null,
                types: new[] { typeof(int) },
                modifiers: null)?.ReturnType == typeof(bool)
                ? contractType.GetMethod(
                    name,
                    BindingFlags.Public | BindingFlags.Static,
                    binder: null,
                    types: new[] { typeof(int) },
                    modifiers: null)
                : null;

        private static bool InvokeBoolean(MethodInfo? method, int processId)
        {
            if (method == null || processId <= 0) return false;
            try { return method.Invoke(null, new object[] { processId }) is bool result && result; }
            catch (TargetInvocationException) { return false; }
            catch (ArgumentException) { return false; }
            catch (MethodAccessException) { return false; }
        }
    }
}
