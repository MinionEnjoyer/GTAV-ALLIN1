// GbayReactorContracts.cs -- optional UI boundary for the GBAY storefront.
//
// ALLIN1 owns every catalog, price, storage, and Story Mode mutation.  UI
// implementations receive detached DTOs and may only request guarded host
// operations through this assembly-neutral contract.  Keeping Reactor types
// out of this file ensures ALLIN1.dll can run when Reactor V is not installed.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    /// <summary>Read-only vehicle catalog query issued by an optional UI.</summary>
    public sealed class Allin1VehicleCatalogRequest
    {
        public string Category { get; set; } = "all";
        public string Search { get; set; } = "";
        public string Ownership { get; set; } = "all";
        public bool FavoritesOnly { get; set; }
        public int Page { get; set; } = 1;
        public int PageSize { get; set; } = 6;

        /// <summary>
        /// Re-authorize installed package catalogs before resolving this
        /// page. UI bridges set this for a newly opened storefront, then use
        /// the resulting snapshot for that presentation's filter/page actions.
        /// Checkout performs its own mandatory refresh and validation.
        /// </summary>
        public bool RefreshCatalog { get; set; } = true;
    }

    /// <summary>Detached storefront row. It grants no purchase authority.</summary>
    public sealed class Allin1VehicleListing
    {
        public string Model { get; internal set; }
        public string Name { get; internal set; }
        public string Manufacturer { get; internal set; }
        public string DisplayName { get; internal set; }
        public string Category { get; internal set; }
        public string Storage { get; internal set; }
        public string PreviewDictionary { get; internal set; }
        public string PreviewTexture { get; internal set; }
        public int Price { get; internal set; }
        public bool Favorite { get; internal set; }
        public bool Owned { get; internal set; }
        public bool Available { get; internal set; }
    }

    /// <summary>Bounded, server-paged storefront result.</summary>
    public sealed class Allin1VehicleCatalogPage
    {
        public string Category { get; internal set; }
        public string Search { get; internal set; }
        public string Ownership { get; internal set; }
        public bool FavoritesOnly { get; internal set; }
        public int Page { get; internal set; }
        public int PageSize { get; internal set; }
        public int PageCount { get; internal set; }
        public int TotalItems { get; internal set; }
        public int Balance { get; internal set; }
        public string CatalogRevision { get; internal set; }
        public IReadOnlyList<Allin1VehicleListing> Items { get; internal set; }
    }

    /// <summary>
    /// Request to enter ALLIN1's authoritative checkout.  The quoted price is
    /// deliberately carried back to the host so a stale UI cannot be charged.
    /// </summary>
    public sealed class Allin1VehicleCheckoutRequest
    {
        public string Model { get; set; } = "";
        public int QuotedPrice { get; set; }
    }

    /// <summary>Typed result from the guarded checkout handoff.</summary>
    public sealed class Allin1VehicleCheckoutResult
    {
        public bool Succeeded { get; internal set; }
        public string Code { get; internal set; }
        public string Message { get; internal set; }
        public string Model { get; internal set; }
        public int QuotedPrice { get; internal set; }
        public string SuggestedDestinationId { get; internal set; }
        public IReadOnlyList<Allin1VehicleDeliveryOption> Destinations
            { get; internal set; } = Array.Empty<Allin1VehicleDeliveryOption>();

        internal static Allin1VehicleCheckoutResult Success(
            string code, string message, string model, int quotedPrice,
            string suggestedDestinationId,
            IReadOnlyList<Allin1VehicleDeliveryOption> destinations) =>
            new Allin1VehicleCheckoutResult
            {
                Succeeded = true,
                Code = code,
                Message = message,
                Model = model,
                QuotedPrice = quotedPrice,
                SuggestedDestinationId = suggestedDestinationId,
                Destinations = destinations ??
                    Array.Empty<Allin1VehicleDeliveryOption>(),
            };

        internal static Allin1VehicleCheckoutResult Failure(
            string code, string message) =>
            new Allin1VehicleCheckoutResult
            {
                Succeeded = false,
                Code = code,
                Message = message,
            };
    }

    /// <summary>Detached delivery destination status for one vehicle quote.</summary>
    public sealed class Allin1VehicleDeliveryOption
    {
        public string Id { get; internal set; }
        public string Label { get; internal set; }
        public int UsedSlots { get; internal set; }
        public int Capacity { get; internal set; }
        public bool Compatible { get; internal set; }
        public bool Available { get; internal set; }
        /// <summary>
        /// Whether this destination's world-entry/map contract is ready.
        /// Available can remain true for garage browsing and waypointing even
        /// when entering the interior must fail closed.
        /// </summary>
        public bool EntryAvailable { get; internal set; }
        public string Status { get; internal set; }
        public string InteriorMode { get; internal set; }
        public string InteriorStatus { get; internal set; }
    }

    /// <summary>
    /// A final delivery request. The browser-provided values are only a quote;
    /// ALLIN1 resolves the destination and re-authorizes the live listing.
    /// </summary>
    public sealed class Allin1VehicleDeliveryRequest
    {
        public string Model { get; set; } = "";
        public int QuotedPrice { get; set; }
        public string DestinationId { get; set; } = "";
    }

    /// <summary>Typed result from ALLIN1's guarded delivery authority.</summary>
    public sealed class Allin1VehicleDeliveryResult
    {
        public bool Succeeded { get; internal set; }
        public string Code { get; internal set; }
        public string Message { get; internal set; }

        internal static Allin1VehicleDeliveryResult Success(
            string code, string message) => new Allin1VehicleDeliveryResult
            {
                Succeeded = true,
                Code = code,
                Message = message,
            };

        internal static Allin1VehicleDeliveryResult Failure(
            string code, string message) => new Allin1VehicleDeliveryResult
            {
                Succeeded = false,
                Code = code,
                Message = message,
            };
    }

    /// <summary>
    /// Typed request to leave the detached Reactor catalog and enter ALLIN1's
    /// established world-space weapon workbench.  The host revalidates live
    /// ownership and location before it creates a preview actor or camera.
    /// </summary>
    public sealed class Allin1WeaponWorkbenchRequest
    {
        public string WeaponId { get; set; } = "";
    }

    /// <summary>Receipt-authorized GBAY extension route.</summary>
    public sealed class Allin1GbayAddonListing
    {
        public string PackageId { get; internal set; }
        public string Route { get; internal set; }
        public string Label { get; internal set; }
        public string Description { get; internal set; }
        public int Order { get; internal set; }
    }

    /// <summary>Live data used by the GBAY home and information routes.</summary>
    public sealed class Allin1GbaySnapshot
    {
        public int Balance { get; internal set; }
        public bool OnlineContentEnabled { get; internal set; }
        public int VehicleCount { get; internal set; }
        public int WeaponCount { get; internal set; }
        public int GearCount { get; internal set; }
        public string Version { get; internal set; }
        public int SessionSeconds { get; internal set; }
        public string GarageLocation { get; internal set; }
        public string TrafficStatus { get; internal set; }
        public string MapContentStatus { get; internal set; }
        public bool SafeMode { get; internal set; }
        public string ArtworkStatus { get; internal set; }
        public string RpfStatus { get; internal set; }
        public string RuntimeLogPath { get; internal set; }
        public IReadOnlyList<Allin1GbayAddonListing> Addons
            { get; internal set; } = Array.Empty<Allin1GbayAddonListing>();
    }

    /// <summary>Guarded result for a receipt-authorized add-on action.</summary>
    public sealed class Allin1GbayActionResult
    {
        public bool Succeeded { get; internal set; }
        public string Code { get; internal set; }
        public string Message { get; internal set; }

        internal static Allin1GbayActionResult Success(
            string code, string message) => new Allin1GbayActionResult
            {
                Succeeded = true,
                Code = code,
                Message = message,
            };

        internal static Allin1GbayActionResult Failure(
            string code, string message) => new Allin1GbayActionResult
            {
                Succeeded = false,
                Code = code,
                Message = message,
            };
    }

    public sealed class Allin1CatalogRequest
    {
        public string Category { get; set; } = "all";
        public string Search { get; set; } = "";
        public string Ownership { get; set; } = "all";
        public bool FavoritesOnly { get; set; }
        public int Page { get; set; } = 1;
        public int PageSize { get; set; } = 6;
    }

    public sealed class Allin1WeaponListing
    {
        public string Id { get; internal set; }
        public string DisplayName { get; internal set; }
        public string Category { get; internal set; }
        public string PreviewDictionary { get; internal set; }
        public string PreviewTexture { get; internal set; }
        public int UnitPrice { get; internal set; }
        public int TotalPrice { get; internal set; }
        public int Quantity { get; internal set; }
        public bool PurchaseAvailable { get; internal set; }
        public bool Owned { get; internal set; }
        public bool Favorite { get; internal set; }
        public bool SmokeProduct { get; internal set; }
        public int Stock { get; internal set; }
        public string AvailabilityStatus { get; internal set; }
    }

    public sealed class Allin1WeaponCatalogPage
    {
        public string Category { get; internal set; }
        public string Search { get; internal set; }
        public string Ownership { get; internal set; }
        public bool FavoritesOnly { get; internal set; }
        public int Page { get; internal set; }
        public int PageCount { get; internal set; }
        public int TotalItems { get; internal set; }
        public int Balance { get; internal set; }
        public IReadOnlyList<Allin1WeaponListing> Items
            { get; internal set; } = Array.Empty<Allin1WeaponListing>();
    }

    public sealed class Allin1WeaponPurchaseRequest
    {
        public string WeaponId { get; set; } = "";
        public int QuotedTotalPrice { get; set; }
    }

    public sealed class Allin1CustomizableWeaponListing
    {
        public string Id { get; internal set; }
        public string DisplayName { get; internal set; }
        public string Category { get; internal set; }
        public string AmmoStatus { get; internal set; }
        public string PreviewDictionary { get; internal set; }
        public string PreviewTexture { get; internal set; }
    }

    public sealed class Allin1CustomizableWeaponPage
    {
        public string Category { get; internal set; }
        public string Search { get; internal set; }
        public string Status { get; internal set; }
        public int Page { get; internal set; }
        public int PageCount { get; internal set; }
        public int TotalItems { get; internal set; }
        public IReadOnlyList<Allin1CustomizableWeaponListing> Items
            { get; internal set; } =
                Array.Empty<Allin1CustomizableWeaponListing>();
    }

    public sealed class Allin1WeaponCustomizationOptionListing
    {
        public string Kind { get; internal set; }
        public string Label { get; internal set; }
        public string Detail { get; internal set; }
        public int Price { get; internal set; }
        public int ComponentHash { get; internal set; }
        public int AttachmentPoint { get; internal set; }
        public int Tint { get; internal set; }
        public bool Owned { get; internal set; }
        public bool Active { get; internal set; }
    }

    public sealed class Allin1WeaponCustomizationPage
    {
        public string WeaponId { get; internal set; }
        public string DisplayName { get; internal set; }
        public string Group { get; internal set; }
        public int Page { get; internal set; }
        public int PageCount { get; internal set; }
        public int TotalItems { get; internal set; }
        public int Balance { get; internal set; }
        public string Status { get; internal set; }
        public IReadOnlyList<Allin1WeaponCustomizationOptionListing> Items
            { get; internal set; } =
                Array.Empty<Allin1WeaponCustomizationOptionListing>();
    }

    public sealed class Allin1WeaponCustomizationApplyRequest
    {
        public string WeaponId { get; set; } = "";
        public string Kind { get; set; } = "";
        public int ComponentHash { get; set; }
        public int AttachmentPoint { get; set; }
        public int Tint { get; set; }
        public int QuotedPrice { get; set; }
    }

    public sealed class Allin1GearListing
    {
        public string Id { get; internal set; }
        public string DisplayName { get; internal set; }
        public string Category { get; internal set; }
        public string PreviewDictionary { get; internal set; }
        public string PreviewTexture { get; internal set; }
        public int Price { get; internal set; }
        public bool Owned { get; internal set; }
        public bool Equipped { get; internal set; }
    }

    public sealed class Allin1GearCatalogPage
    {
        public string Category { get; internal set; }
        public int Page { get; internal set; }
        public int PageCount { get; internal set; }
        public int TotalItems { get; internal set; }
        public int Balance { get; internal set; }
        public IReadOnlyList<Allin1GearListing> Items
            { get; internal set; } = Array.Empty<Allin1GearListing>();
    }

    public sealed class Allin1GearActionRequest
    {
        public string GearId { get; set; } = "";
        public string Operation { get; set; } = "";
        public int QuotedPrice { get; set; }
    }

    public sealed class Allin1GarageVehicleListing
    {
        private bool _sellable;
        private bool _retrievable;

        public string LocationId { get; internal set; }
        public string LocationLabel { get; internal set; }
        public int ListIndex { get; internal set; }
        public string Model { get; internal set; }
        public int ModelHash { get; internal set; }
        public string PlateText { get; internal set; }
        public string DisplayName { get; internal set; }
        public int SellPrice { get; internal set; }
        public bool Sellable
        {
            get { return _sellable; }
            internal set
            {
                _sellable = value;
                if (value) _retrievable = false;
            }
        }
        public bool Retrievable
        {
            get { return _retrievable; }
            internal set
            {
                _retrievable = value;
                if (value) _sellable = false;
            }
        }
    }

    public sealed class Allin1GarageCustomizationOption
    {
        public string Id { get; internal set; }
        public string Label { get; internal set; }
    }

    public sealed class Allin1GarageCustomizationCategory
    {
        public string Id { get; internal set; }
        public string Label { get; internal set; }
        public string SelectedOptionId { get; internal set; }
        public IReadOnlyList<Allin1GarageCustomizationOption> Options
            { get; internal set; } =
                Array.Empty<Allin1GarageCustomizationOption>();
    }

    public sealed class Allin1GarageCustomizationSnapshot
    {
        public string LocationId { get; internal set; }
        public string LocationLabel { get; internal set; }
        public bool Available { get; internal set; }
        public bool LivePreview { get; internal set; }
        public string Status { get; internal set; }
        public IReadOnlyList<Allin1GarageCustomizationCategory> Categories
            { get; internal set; } =
                Array.Empty<Allin1GarageCustomizationCategory>();
    }

    public sealed class Allin1GarageSnapshot
    {
        /// <summary>
        /// Location the player is currently using. When the player is in the
        /// world, ALLIN1 supplies the normal personal-garage default.
        /// </summary>
        public string ActiveLocationId { get; internal set; }
        public IReadOnlyList<Allin1VehicleDeliveryOption> Locations
            { get; internal set; } = Array.Empty<Allin1VehicleDeliveryOption>();
        public IReadOnlyList<Allin1GarageVehicleListing> Vehicles
            { get; internal set; } = Array.Empty<Allin1GarageVehicleListing>();
        public bool EmergencyRecoveryAvailable { get; internal set; }
        public string EmergencyRecoveryStatus { get; internal set; }
        public Allin1GarageCustomizationSnapshot Customization
            { get; internal set; }
    }

    public sealed class Allin1GarageVehicleRequest
    {
        public string LocationId { get; set; } = "";
        public int ListIndex { get; set; }
        public string Model { get; set; } = "";
        public int ModelHash { get; set; }
        public string PlateText { get; set; } = "";
        public int QuotedSellPrice { get; set; }
    }

    /// <summary>
    /// Typed request for a map waypoint. The host resolves the coordinate
    /// from its current, descriptor-backed garage registry; callers cannot
    /// provide arbitrary world coordinates.
    /// </summary>
    public sealed class Allin1GarageWaypointRequest
    {
        public string LocationId { get; set; } = "";
    }

    /// <summary>
    /// Read-only request to open the unified garage surface at one existing
    /// world-entry location. The bridge must validate the location against a
    /// fresh detached garage snapshot; this request grants no map, storage, or
    /// vehicle-mutation authority.
    /// </summary>
    public enum Allin1GarageWorldEntryLocation
    {
        Unknown = 0,
        VespucciHelipad = 1,
        Harbour = 2,
    }

    public sealed class Allin1GaragePresentationRequest
    {
        public Allin1GarageWorldEntryLocation Location { get; set; }
    }

    public sealed class Allin1GarageCustomizationRequest
    {
        public string LocationId { get; set; } = "";
        public string CategoryId { get; set; } = "";
        public string ExpectedOptionId { get; set; } = "";
        public string OptionId { get; set; } = "";
    }

    internal static class GarageReactorPolicy
    {
        internal static bool IsRetrievalOnlyLocation(string locationId) =>
            string.Equals(locationId, "vespucci-helipad",
                StringComparison.OrdinalIgnoreCase) ||
            string.Equals(locationId, "harbour",
                StringComparison.OrdinalIgnoreCase);

        internal static string InteriorMode(string locationId)
        {
            if (string.Equals(locationId, "davis",
                    StringComparison.OrdinalIgnoreCase))
                return "customizable";
            if (string.Equals(locationId, "vespucci-helipad",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(locationId, "yacht-helipad",
                    StringComparison.OrdinalIgnoreCase) ||
                string.Equals(locationId, "harbour",
                    StringComparison.OrdinalIgnoreCase))
                return "specialized";
            return "fixed";
        }

        internal static string InteriorStatus(string locationId)
        {
            switch (InteriorMode(locationId))
            {
                case "customizable":
                    return "Appearance options are saved per Story character.";
                case "specialized":
                    return IsRetrievalOnlyLocation(locationId)
                        ? "Outdoor specialized storage; vehicles are retrieved, not sold here."
                        : "Outdoor specialized storage.";
                default:
                    return "This location uses its finished fixed interior.";
            }
        }
    }

    /// <summary>
    /// Narrow host surface available to the optional Reactor bridge.  It does
    /// not expose GTA natives, garage collections, or writable save files.
    /// </summary>
    public interface IAllin1VehicleStorefront
    {
        IReadOnlyList<string> Categories { get; }
        Allin1GbaySnapshot DescribeGbay();
        Allin1VehicleCatalogPage BrowseVehicles(
            Allin1VehicleCatalogRequest request);
        Allin1VehicleCheckoutResult BeginVehicleCheckout(
            Allin1VehicleCheckoutRequest request);
        Allin1VehicleDeliveryResult ConfirmVehicleDelivery(
            Allin1VehicleDeliveryRequest request);
        bool ToggleVehicleFavorite(string model);
        Allin1GbayActionResult InvokeAddon(string packageId, string route);
        Allin1GbayActionResult OpenRuntimeLogFolder();
        IReadOnlyList<string> WeaponCategories { get; }
        Allin1WeaponCatalogPage BrowseWeapons(Allin1CatalogRequest request);
        Allin1GbayActionResult PurchaseWeapon(
            Allin1WeaponPurchaseRequest request);
        bool ToggleWeaponFavorite(string weaponId);
        Allin1CustomizableWeaponPage BrowseCustomizableWeapons(
            Allin1CatalogRequest request);
        Allin1WeaponCustomizationPage BrowseWeaponCustomization(
            string weaponId, string group, int page, int pageSize,
            bool refresh);
        Allin1GbayActionResult OpenWeaponWorkbench(
            Allin1WeaponWorkbenchRequest request);
        Allin1GbayActionResult ApplyWeaponCustomization(
            Allin1WeaponCustomizationApplyRequest request);
        IReadOnlyList<string> GearCategories { get; }
        Allin1GearCatalogPage BrowseGear(Allin1CatalogRequest request);
        Allin1GbayActionResult ApplyGearAction(
            Allin1GearActionRequest request);
        Allin1GarageSnapshot BrowseGarage();
        Allin1GbayActionResult NavigateToGarage(
            Allin1GarageWaypointRequest request);
        Allin1GbayActionResult SellGarageVehicle(
            Allin1GarageVehicleRequest request);
        Allin1GbayActionResult RetrieveGarageVehicle(
            Allin1GarageVehicleRequest request);
        Allin1GbayActionResult ApplyGarageCustomization(
            Allin1GarageCustomizationRequest request);
        Allin1GbayActionResult EmergencyRecoverGarage();
    }

    /// <summary>
    /// Optional visual-host contract used while Reactor owns the weapon
    /// workbench UI. These calls may create or update the in-world preview,
    /// but PreviewWeaponCustomization must never purchase or persist an item.
    /// </summary>
    public interface IAllin1WeaponPreviewStorefront
    {
        Allin1GbayActionResult BeginWeaponPreview(
            Allin1WeaponWorkbenchRequest request);
        Allin1GbayActionResult PreviewWeaponCustomization(
            Allin1WeaponCustomizationApplyRequest request);
        Allin1GbayActionResult EndWeaponPreview();
    }

    /// <summary>
    /// Implemented by ALLIN1.ReactorBridge.plugin.  ALLIN1 discovers this
    /// interface by reflection only after Reactor's managed host is loaded.
    /// </summary>
    public interface IAllin1MenuBridge : IDisposable
    {
        bool IsMenuActive { get; }
        string Status { get; }
        bool Initialize(IAllin1VehicleStorefront storefront);
        bool TryCancelPendingStartupMenu();
        bool TryPresentPendingStartupMenu();
        bool TryPresentVehicles(Allin1VehicleCatalogRequest request);
        bool TryPresentGarage(Allin1GaragePresentationRequest request);
        bool TryPresentWeaponCustomization();
        bool TryDismissVehicles();
    }

    /// <summary>
    /// Optional lifecycle capability implemented by newer presentation
    /// bridges. The core feature-detects this contract so an older bridge
    /// remains binary-compatible and keeps its established active-state
    /// behavior.
    /// </summary>
    public interface IAllin1MenuLifecycleBridge
    {
        /// <summary>
        /// True only after the active GBAY presentation has acknowledged its
        /// first browser-ready frame. A logically active but not-yet-ready
        /// presentation must not be closed by a second F9 edge.
        /// </summary>
        bool IsMenuReady { get; }
    }

    /// <summary>
    /// Optional character-context capability implemented by newer Reactor
    /// bridges. The core invokes it only on a confirmed Michael, Franklin, or
    /// Trevor identity edge; it is not a timer or a provider polling surface.
    /// Older bridges remain binary compatible and continue to refresh when a
    /// menu is explicitly reopened.
    /// </summary>
    public interface IAllin1StoryCharacterBridge
    {
        /// <summary>
        /// Rebuild every detached snapshot whose ownership or garage content
        /// is scoped to the active Story protagonist.
        /// </summary>
        bool TryRefreshStoryCharacter(string characterId);
    }

    /// <summary>
    /// Optional live-state capability implemented by newer Reactor bridges.
    /// ALLIN1 calls it at a bounded rate only while GBAY is visible. It keeps
    /// balance, ownership, loadouts, garage contents, add-ons, and diagnostics
    /// aligned with the game without exposing a player-operated refresh action.
    /// </summary>
    public interface IAllin1GameStateBridge
    {
        /// <summary>
        /// Atomically rebuild and publish every changed detached menu
        /// projection for the confirmed active Story protagonist.
        /// </summary>
        bool TrySynchronizeGameState(string characterId);
    }

    public sealed class Allin1DrivingHudFrame
    {
        public bool Visible { get; internal set; }
        public float Speed { get; internal set; }
        public string Units { get; internal set; } = "KMH";
        public string Gear { get; internal set; } = "?";
        public bool Manual { get; internal set; }
        public string Notice { get; internal set; } = "";
    }
    public interface IAllin1DrivingHudBridge
    {
        bool TryPublishDrivingHud(Allin1DrivingHudFrame frame);
    }

    internal sealed class GbayVehicleStorefront :
        IAllin1VehicleStorefront, IAllin1WeaponPreviewStorefront, IAllin1HitchStorefront
    {
        public Allin1HitchSnapshot BrowseHitches() => TrailerHitchRuntime.Browse();
        public Allin1GbayActionResult ConnectHitch(string token, bool experimentalConfirmed) => TrailerHitchRuntime.Connect(token, experimentalConfirmed);
        public Allin1GbayActionResult DisconnectHitch(string token) => TrailerHitchRuntime.Disconnect(token);
        private const int MaximumPageSize = 12;
        private const int MaximumSearchLength = 96;
        private static readonly string[] CategoryValues =
        {
            "all", "compacts", "coupes", "sedans", "suvs", "muscle",
            "sports", "sportsclassics", "super", "offroad",
            "motorcycles", "vans", "boats", "helicopters", "planes",
            "military", "industrial", "openwheel", "emergency", "cycles",
            "service", "special",
        };
        private static readonly HashSet<string> CategorySet =
            new HashSet<string>(CategoryValues, StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> OwnershipValues =
            new HashSet<string>(new[] { "all", "owned", "available" },
                StringComparer.OrdinalIgnoreCase);
        private static readonly string[] DestinationIds =
        {
            "eclipse", "harmony", "davis", "garment", "grapeseed",
            "paleto", "vespucci-helipad", "yacht-helipad", "harbour",
        };
        private static readonly string[] DestinationLabels =
        {
            "Eclipse Garage", "Harmony Garage", "Davis Auto Shop",
            "Garment Factory", "Grapeseed Garage", "Paleto Bay Garage",
            "Vespucci Helipad", "Yacht Helipad", "Los Santos Harbour",
        };
        private static readonly string[] WeaponCategoryValues =
        {
            "all", "pistols", "smgs", "shotguns", "rifles",
            "machineguns", "snipers", "heavy", "melee", "throwables",
            "misc",
        };
        private static readonly string[] GearCategoryValues =
        {
            "all", "protection", "equipment",
        };
        private static readonly string[] DavisCustomizationCategoryIds =
        {
            "style", "tint", "car-lift", "personal-quarters",
            "work-area", "storage",
        };

        private readonly GbayShop _shop;
        private string _customizationCacheWeapon = "";
        private IReadOnlyList<GbayBrowser.DetachedWorkbenchRow>
            _customizationCache =
                Array.Empty<GbayBrowser.DetachedWorkbenchRow>();
        private string _customizationCacheStateToken = "";
        private bool _customizationCacheInitialized;

        internal GbayVehicleStorefront(GbayShop shop)
        {
            _shop = shop ?? throw new ArgumentNullException(nameof(shop));
        }

        public IReadOnlyList<string> Categories => CategoryValues.ToArray();
        public IReadOnlyList<string> WeaponCategories =>
            WeaponCategoryValues.ToArray();
        public IReadOnlyList<string> GearCategories =>
            GearCategoryValues.ToArray();

        public Allin1GbaySnapshot DescribeGbay()
        {
            IReadOnlyList<Allin1GbayAddonListing> addons =
                Allin1ExtensionApi.GetGbayActions()
                    .Select(value => new Allin1GbayAddonListing
                    {
                        PackageId = value.PackageId,
                        Route = value.Route,
                        Label = value.Label,
                        Description = value.Description,
                        Order = value.Order,
                    }).ToArray();
            string garage = GarageManager.IsPlayerInFloorGarage
                ? "Harmony Garage"
                : GarageManager.IsPlayerInDavisGarage ? "Davis Auto Shop"
                : GarageManager.IsPlayerInGarmentGarage ? "Garment Factory"
                : GarageManager.IsPlayerInRuralGarage ? "Grapeseed Garage"
                : GarageManager.IsPlayerInPaletoGarage ? "Paleto Bay Garage"
                : GarageManager.IsInGarage ? "Eclipse Garage" : "Outside";
            string traffic = TrafficSpawner.ManagedVehicleCount + " managed, " +
                Math.Round(TrafficSpawner.SmoothedFps) + " FPS" +
                (TrafficSpawner.IsThrottled ? " (adaptive throttle)" : "") +
                (string.IsNullOrEmpty(TrafficSpawner.PauseReason) ? "" :
                    " (paused: " + TrafficSpawner.PauseReason + ")");
            string mapContent = OfficialMapContentPolicy.RuntimeStatus;
            return new Allin1GbaySnapshot
            {
                Balance = Game.Player.Money,
                OnlineContentEnabled = _shop.OnlineContentEnabled,
                VehicleCount = RuntimeVehicleCatalog.GetCategoryModels("all")
                    .Count,
                WeaponCount = RuntimeWeaponCatalog.All.Length,
                GearCount = GearList.All.Length,
                Version = typeof(GbayShop).Assembly.GetName().Version?
                    .ToString(3) ?? "unknown",
                SessionSeconds = Math.Max(0, Game.GameTime / 1000),
                GarageLocation = garage,
                TrafficStatus = traffic,
                MapContentStatus = mapContent,
                SafeMode = ClientWatchdog.SafeMode,
                ArtworkStatus = GbayRenderer.PreviewDiagnostics,
                RpfStatus = GbayRenderer.OpenRpfStatus,
                RuntimeLogPath = ClientLog.PortablePath,
                Addons = addons,
            };
        }

        public Allin1GbayActionResult OpenRuntimeLogFolder()
        {
            try
            {
                string directory = Path.GetDirectoryName(
                    ClientLog.RuntimePath) ?? "";
                if (directory.Length == 0 || !Directory.Exists(directory))
                    return Allin1GbayActionResult.Failure(
                        "runtime_log_folder_missing",
                        "The ALLIN1 runtime log folder is not available.");
                System.Diagnostics.Process.Start(
                    new System.Diagnostics.ProcessStartInfo
                    {
                        FileName = directory,
                        UseShellExecute = true,
                    });
                return Allin1GbayActionResult.Success(
                    "runtime_log_folder_opened",
                    "The ALLIN1 runtime log folder was opened.");
            }
            catch
            {
                // Never expose a machine-specific path or shell error through
                // the detached, agent-visible menu contract.
                return Allin1GbayActionResult.Failure(
                    "runtime_log_folder_open_failed",
                    "Windows could not open the ALLIN1 runtime log folder.");
            }
        }

        public Allin1VehicleCatalogPage BrowseVehicles(
            Allin1VehicleCatalogRequest request)
        {
            request = request ?? new Allin1VehicleCatalogRequest();
            // Package enable/disable and add-on discovery can change while a
            // session is running. Match the legacy browser's reopen behavior
            // so Reactor never starts from a stale catalog snapshot.
            if (request.RefreshCatalog)
                RuntimeVehicleCatalog.Refresh();
            string category = (request.Category ?? "all").Trim()
                .ToLowerInvariant();
            if (!CategorySet.Contains(category)) category = "all";
            string ownership = (request.Ownership ?? "all").Trim()
                .ToLowerInvariant();
            if (!OwnershipValues.Contains(ownership)) ownership = "all";
            string search = (request.Search ?? "").Trim();
            if (search.Length > MaximumSearchLength)
                search = search.Substring(0, MaximumSearchLength);
            int pageSize = Math.Max(1, Math.Min(MaximumPageSize,
                request.PageSize));

            var filtered = new List<string>();
            foreach (string model in RuntimeVehicleCatalog.GetCategoryModels(
                category))
            {
                if (request.FavoritesOnly &&
                    !GbayPreferences.IsVehicleFavorite(model)) continue;
                if (ownership != "all")
                {
                    bool owned = GarageManager.IsVehicleOwned(model);
                    if (ownership == "owned" && !owned) continue;
                    if (ownership == "available" && owned) continue;
                }
                string displayName = RuntimeVehicleCatalog.GetDisplayName(model);
                string manufacturer = RuntimeVehicleCatalog.GetManufacturer(model);
                if (search.Length > 0 &&
                    displayName.IndexOf(search,
                        StringComparison.OrdinalIgnoreCase) < 0 &&
                    manufacturer.IndexOf(search,
                        StringComparison.OrdinalIgnoreCase) < 0 &&
                    RuntimeVehicleCatalog.SearchAliases(model).IndexOf(search,
                        StringComparison.OrdinalIgnoreCase) < 0 &&
                    model.IndexOf(search,
                        StringComparison.OrdinalIgnoreCase) < 0)
                    continue;
                filtered.Add(model);
            }

            int pageCount = Math.Max(1,
                (filtered.Count + pageSize - 1) / pageSize);
            int page = Math.Max(1, Math.Min(pageCount, request.Page));
            string[] selected = filtered
                .Skip((page - 1) * pageSize)
                .Take(pageSize)
                .ToArray();
            var listings = selected.Select(model =>
            {
                RuntimeVehicleCatalog.TryGetPreview(
                    model, out string previewDictionary,
                    out string previewTexture);
                return new Allin1VehicleListing
                {
                    Model = model,
                    Name = RuntimeVehicleCatalog.GetName(model),
                    Manufacturer = RuntimeVehicleCatalog.GetManufacturer(model),
                    DisplayName = RuntimeVehicleCatalog.GetDisplayName(model),
                    Category = RuntimeVehicleCatalog.GetCategory(model),
                    Storage = RuntimeVehicleCatalog.GetStorage(model),
                    PreviewDictionary = previewDictionary ?? "",
                    PreviewTexture = previewTexture ?? "",
                    Price = _shop.FreeMode
                        ? 0 : RuntimeVehicleCatalog.GetPrice(model),
                    Favorite = GbayPreferences.IsVehicleFavorite(model),
                    Owned = GarageManager.IsVehicleOwned(model),
                    Available = RuntimeVehicleCatalog.IsModelAvailable(model),
                };
            }).ToArray();

            return new Allin1VehicleCatalogPage
            {
                Category = category,
                Search = search,
                Ownership = ownership,
                FavoritesOnly = request.FavoritesOnly,
                Page = page,
                PageSize = pageSize,
                PageCount = pageCount,
                TotalItems = filtered.Count,
                Balance = Game.Player.Money,
                CatalogRevision = CatalogRevision(filtered),
                Items = listings,
            };
        }

        public Allin1VehicleCheckoutResult BeginVehicleCheckout(
            Allin1VehicleCheckoutRequest request)
        {
            if (request == null || string.IsNullOrWhiteSpace(request.Model))
                return Allin1VehicleCheckoutResult.Failure(
                    "invalid_listing", "A vehicle listing is required.");
            string model = request.Model.Trim().ToLowerInvariant();
            if (RuntimeVehicleCatalog.IsCatalogOnly(model))
                return Allin1VehicleCheckoutResult.Failure(
                    "catalog_only", "This vehicle is listed for reference; purchasing and delivery are not enabled yet.");
            if (!GbayShop.TryGetCurrentCharacter(out _))
                return Allin1VehicleCheckoutResult.Failure(
                    "unsupported_character",
                    "GBAY is available to Michael, Franklin, and Trevor.");
            if (Game.IsLoading || Game.Player.Character == null ||
                !Game.Player.Character.Exists() || Game.Player.Character.IsDead)
                return Allin1VehicleCheckoutResult.Failure(
                    "story_unavailable", "Story Mode is not ready.");
            if (GarageManager.IsTransitionInProgress)
                return Allin1VehicleCheckoutResult.Failure(
                    "garage_transition",
                    "A garage transition is already in progress.");
            if (!_shop.OnlineContentEnabled)
                return Allin1VehicleCheckoutResult.Failure(
                    "content_unavailable",
                    "ALLIN1 Online Content is not enabled.");
            if (!_shop.ValidateVehiclePurchase(model, request.QuotedPrice))
                return Allin1VehicleCheckoutResult.Failure(
                    "listing_changed",
                    "The listing is no longer valid. GBAY has updated automatically; choose it again.");
            IReadOnlyList<Allin1VehicleDeliveryOption> destinations =
                BuildDeliveryOptions(model);
            string suggested = SuggestedDestination(model, destinations);
            return Allin1VehicleCheckoutResult.Success(
                "delivery_selection",
                "Choose a delivery location to complete the purchase.",
                model, request.QuotedPrice, suggested, destinations);
        }

        public Allin1VehicleDeliveryResult ConfirmVehicleDelivery(
            Allin1VehicleDeliveryRequest request)
        {
            if (request == null || string.IsNullOrWhiteSpace(request.Model) ||
                string.IsNullOrWhiteSpace(request.DestinationId))
                return Allin1VehicleDeliveryResult.Failure(
                    "invalid_delivery", "A vehicle and destination are required.");
            string model = request.Model.Trim().ToLowerInvariant();
            string destination = request.DestinationId.Trim().ToLowerInvariant();
            if (!StoryReady(out string storyFailure))
                return Allin1VehicleDeliveryResult.Failure(
                    "story_unavailable", storyFailure);
            if (!_shop.OnlineContentEnabled)
                return Allin1VehicleDeliveryResult.Failure(
                    "content_unavailable",
                    "ALLIN1 Online Content is not enabled.");
            if (GarageManager.IsTransitionInProgress)
                return Allin1VehicleDeliveryResult.Failure(
                    "garage_transition",
                    "A garage transition is already in progress.");
            if (!_shop.ValidateVehiclePurchase(model, request.QuotedPrice))
                return Allin1VehicleDeliveryResult.Failure(
                    "listing_changed",
                    "The listing changed. Return to Vehicles and choose it again.");

            if (WorldAssetList.IsWorldAsset(model))
            {
                if (!string.Equals(destination, "world-property",
                        StringComparison.OrdinalIgnoreCase))
                    return Allin1VehicleDeliveryResult.Failure(
                        "invalid_destination",
                        "This property does not use a garage destination.");
                Allin1VehicleDeliveryOption propertyOption =
                    BuildDeliveryOptions(model).FirstOrDefault();
                if (propertyOption == null || !propertyOption.Available)
                    return Allin1VehicleDeliveryResult.Failure(
                        "destination_unavailable",
                        propertyOption?.Status ??
                            OfficialMapContentPolicy.UnknownDestinationStatus);
                if (!_shop.ExecutePurchaseWorldAsset(model, request.QuotedPrice))
                    return Allin1VehicleDeliveryResult.Failure(
                        "purchase_rejected",
                        "ALLIN1 could not complete the property purchase.");
                GbayPreferences.RecordVehicle(model);
                return Allin1VehicleDeliveryResult.Success(
                    "purchase_complete", "Property purchase completed.");
            }

            Allin1VehicleDeliveryOption option = BuildDeliveryOptions(model)
                .FirstOrDefault(value => string.Equals(
                    value.Id, destination, StringComparison.OrdinalIgnoreCase));
            if (option == null)
                return Allin1VehicleDeliveryResult.Failure(
                    "invalid_destination", "That delivery location is unknown.");
            if (!option.Available)
                return Allin1VehicleDeliveryResult.Failure(
                    "destination_unavailable", option.Status);

            int locationIndex = Array.FindIndex(
                DestinationIds, value => string.Equals(
                    value, destination, StringComparison.OrdinalIgnoreCase));
            int usedBeforeDelivery = DestinationUsed(locationIndex);
            switch (locationIndex)
            {
                case 1:
                    _shop.ExecuteDeliverToFloorGarage(model, request.QuotedPrice);
                    break;
                case 2:
                    _shop.ExecuteDeliverToDavisGarage(model, request.QuotedPrice);
                    break;
                case 3:
                    _shop.ExecuteDeliverToGarmentGarage(model, request.QuotedPrice);
                    break;
                case 4:
                    _shop.ExecuteDeliverToRuralGarage(model, request.QuotedPrice);
                    break;
                case 5:
                    _shop.ExecuteDeliverToPaletoGarage(model, request.QuotedPrice);
                    break;
                case 6:
                    _shop.ExecuteDeliverToHelipad(model, request.QuotedPrice);
                    break;
                case 7:
                    _shop.ExecuteDeliverToYachtHelipad(model, request.QuotedPrice);
                    break;
                case 8:
                    _shop.ExecuteDeliverToHarbour(model, request.QuotedPrice);
                    break;
                default:
                    _shop.ExecuteDeliverToGarage(model, request.QuotedPrice);
                    break;
            }
            if (DestinationUsed(locationIndex) <= usedBeforeDelivery)
                return Allin1VehicleDeliveryResult.Failure(
                    "purchase_rejected",
                    "GTA did not confirm the vehicle delivery.");
            GbayPreferences.RecordVehicle(model);
            return Allin1VehicleDeliveryResult.Success(
                "delivery_dispatched",
                RuntimeVehicleCatalog.GetDisplayName(model) + " sent to " +
                    option.Label + ".");
        }

        public bool ToggleVehicleFavorite(string model)
        {
            string normalized = (model ?? "").Trim().ToLowerInvariant();
            RuntimeVehicleCatalog.Refresh();
            if (normalized.Length == 0 ||
                !RuntimeVehicleCatalog.IsListed(normalized))
                return false;
            GbayPreferences.ToggleVehicle(normalized);
            return true;
        }

        public Allin1GbayActionResult InvokeAddon(
            string packageId, string route)
        {
            string package = (packageId ?? "").Trim();
            string routeId = (route ?? "").Trim();
            GbayAddonAction action = Allin1ExtensionApi.GetGbayActions()
                .FirstOrDefault(value => string.Equals(
                        value.PackageId, package, StringComparison.Ordinal) &&
                    string.Equals(value.Route, routeId,
                        StringComparison.Ordinal));
            if (action == null)
                return Allin1GbayActionResult.Failure(
                    "addon_unavailable",
                    "That add-on action is no longer receipt-authorized.");
            GbayAddonInvocationResult invocation =
                Allin1ExtensionApi.InvokeGbayAction(action);
            return invocation.Succeeded
                ? Allin1GbayActionResult.Success(
                    invocation.Code, invocation.Message)
                : Allin1GbayActionResult.Failure(
                    invocation.Code, invocation.Message);
        }

        public Allin1WeaponCatalogPage BrowseWeapons(
            Allin1CatalogRequest request)
        {
            RuntimeWeaponCatalog.Refresh();
            request = request ?? new Allin1CatalogRequest();
            string category = NormalizeChoice(
                request.Category, WeaponCategoryValues);
            string ownership = NormalizeOwnership(request.Ownership);
            string search = (request.Search ?? "").Trim();
            if (search.Length > MaximumSearchLength)
                search = search.Substring(0, MaximumSearchLength);
            int pageSize = Math.Max(1, Math.Min(MaximumPageSize,
                request.PageSize));
            string[] source = WeaponIds(category);
            var filtered = new List<Allin1WeaponListing>();
            bool? smokePackAvailable = null;
            bool simplePage = !request.FavoritesOnly && ownership == "all" &&
                search.Length == 0;
            int totalItems;
            int pageCount;
            int page;
            if (simplePage)
            {
                totalItems = source.Length;
                pageCount = Math.Max(1,
                    (totalItems + pageSize - 1) / pageSize);
                page = Math.Max(1, Math.Min(pageCount, request.Page));
                foreach (string weaponId in source
                    .Skip((page - 1) * pageSize).Take(pageSize))
                    filtered.Add(DescribeWeaponListing(
                        weaponId, ref smokePackAvailable));
            }
            else
            {
                foreach (string weaponId in source)
                {
                    Allin1WeaponListing listing = DescribeWeaponListing(
                        weaponId, ref smokePackAvailable);
                    if (request.FavoritesOnly && !listing.Favorite) continue;
                    if (ownership == "owned" && !listing.Owned) continue;
                    if (ownership == "available" && listing.Owned &&
                        !listing.SmokeProduct) continue;
                    if (search.Length > 0 &&
                        listing.DisplayName.IndexOf(search,
                            StringComparison.OrdinalIgnoreCase) < 0 &&
                        weaponId.IndexOf(search,
                            StringComparison.OrdinalIgnoreCase) < 0)
                        continue;
                    filtered.Add(listing);
                }
                totalItems = filtered.Count;
                pageCount = Math.Max(1,
                    (totalItems + pageSize - 1) / pageSize);
                page = Math.Max(1, Math.Min(pageCount, request.Page));
                filtered = filtered.Skip((page - 1) * pageSize)
                    .Take(pageSize).ToList();
            }
            return new Allin1WeaponCatalogPage
            {
                Category = category,
                Search = search,
                Ownership = ownership,
                FavoritesOnly = request.FavoritesOnly,
                Page = page,
                PageCount = pageCount,
                TotalItems = totalItems,
                Balance = Game.Player.Money,
                Items = filtered.ToArray(),
            };
        }

        private Allin1WeaponListing DescribeWeaponListing(
            string weaponId, ref bool? smokePackAvailable)
        {
            bool smoke = SmokeGrenadeCatalog.TryGetProduct(
                weaponId, out SmokeGrenadeProduct product);
            string display = smoke ? product.DisplayName
                : RuntimeWeaponCatalog.DisplayNames.TryGetValue(
                    weaponId, out string weaponName)
                    ? weaponName : weaponId;
            string itemCategory = smoke ? "Throwables"
                : RuntimeWeaponCatalog.CategoryNames.TryGetValue(
                    weaponId, out string categoryName)
                    ? categoryName : "Other";
            int unitPrice = smoke ? product.UnitPrice
                : RuntimeWeaponCatalog.Prices.TryGetValue(
                    weaponId, out int configuredPrice)
                    ? configuredPrice : 0;
            WeaponPurchaseQuote quote = _shop.GetWeaponPurchaseQuote(
                weaponId, unitPrice);
            int stock = smoke
                ? CharacterInventory.GetSmokeQuantity(product.ColorName) : 0;
            bool owned = smoke ? stock > 0 : IsWeaponOwned(weaponId);
            bool runtimeAvailable;
            if (smoke)
            {
                if (!smokePackAvailable.HasValue)
                    smokePackAvailable =
                        SmokeGrenadeCatalog.AvailableCustomWeaponCount() ==
                        SmokeGrenadeCatalog.Products.Length;
                runtimeAvailable = smokePackAvailable.Value;
            }
            else
                runtimeAvailable = Function.Call<bool>(
                    Hash.IS_WEAPON_VALID, Game.GenerateHash(weaponId));
            bool quoteAvailable = quote.Status ==
                WeaponPurchaseStatus.Available;
            bool hasPreview = RuntimeWeaponCatalog.PreviewDict.TryGetValue(
                weaponId, out string previewDictionary);
            return new Allin1WeaponListing
            {
                Id = weaponId,
                DisplayName = display,
                Category = itemCategory,
                PreviewDictionary = hasPreview ? previewDictionary : "",
                PreviewTexture = hasPreview
                    ? weaponId.ToLowerInvariant() : "",
                UnitPrice = unitPrice,
                TotalPrice = quote.TotalPrice,
                Quantity = quote.Quantity,
                PurchaseAvailable = runtimeAvailable && quoteAvailable,
                Owned = owned,
                Favorite = GbayPreferences.IsWeaponFavorite(weaponId),
                SmokeProduct = smoke,
                Stock = stock,
                AvailabilityStatus = !runtimeAvailable
                    ? smoke ? "Smoke weapon pack unavailable"
                        : "Unavailable in this GTA build"
                    : !quoteAvailable ? "Purchase quantity unavailable"
                        : "Available",
            };
        }

        public Allin1GbayActionResult PurchaseWeapon(
            Allin1WeaponPurchaseRequest request)
        {
            if (request == null || string.IsNullOrWhiteSpace(request.WeaponId))
                return Allin1GbayActionResult.Failure(
                    "invalid_weapon", "A weapon listing is required.");
            if (!StoryReady(out string storyFailure))
                return Allin1GbayActionResult.Failure(
                    "story_unavailable", storyFailure);
            if (!_shop.OnlineContentEnabled)
                return Allin1GbayActionResult.Failure(
                    "content_unavailable",
                    "ALLIN1 Online Content is not enabled.");
            string weaponId = request.WeaponId.Trim().ToUpperInvariant();
            RuntimeWeaponCatalog.Refresh();
            if (!WeaponIds("all").Contains(
                    weaponId, StringComparer.OrdinalIgnoreCase))
                return Allin1GbayActionResult.Failure(
                    "invalid_weapon", "That weapon is not in the GBAY catalog.");
            bool smoke = SmokeGrenadeCatalog.TryGetProduct(
                weaponId, out SmokeGrenadeProduct product);
            bool runtimeAvailable = smoke
                ? SmokeGrenadeCatalog.AvailableCustomWeaponCount() ==
                    SmokeGrenadeCatalog.Products.Length
                : Function.Call<bool>(
                    Hash.IS_WEAPON_VALID, Game.GenerateHash(weaponId));
            if (!runtimeAvailable)
                return Allin1GbayActionResult.Failure(
                    "weapon_unavailable",
                    smoke
                        ? "The colored-smoke weapon pack is not fully loaded."
                        : "That weapon is unavailable in this GTA V build.");
            int unitPrice = smoke ? product.UnitPrice
                : RuntimeWeaponCatalog.Prices.TryGetValue(
                    weaponId, out int configuredPrice)
                    ? configuredPrice : 0;
            WeaponPurchaseQuote quote = _shop.GetWeaponPurchaseQuote(
                weaponId, unitPrice);
            if (quote.Status != WeaponPurchaseStatus.Available ||
                request.QuotedTotalPrice != quote.TotalPrice)
                return Allin1GbayActionResult.Failure(
                    "listing_changed",
                    "The weapon listing changed. GBAY has updated automatically; choose it again.");
            if (!smoke && IsWeaponOwned(weaponId))
                return Allin1GbayActionResult.Failure(
                    "already_owned",
                    "That weapon is already owned. Use Customize Weapons.");
            if (!_shop.FreeMode && quote.TotalPrice > Game.Player.Money)
                return Allin1GbayActionResult.Failure(
                    "insufficient_funds", "You no longer have enough money.");

            int beforeStock = smoke
                ? CharacterInventory.GetSmokeQuantity(product.ColorName) : 0;
            if (smoke) _shop.ExecuteGiveSmokeGrenades(weaponId);
            else _shop.ExecuteGiveWeapon(weaponId, unitPrice);
            bool completed = smoke
                ? CharacterInventory.GetSmokeQuantity(product.ColorName) >
                    beforeStock
                : IsWeaponOwned(weaponId);
            if (!completed)
                return Allin1GbayActionResult.Failure(
                    "purchase_rejected",
                    "GTA did not confirm the weapon purchase.");
            return Allin1GbayActionResult.Success(
                "weapon_purchased", "Weapon purchase completed.");
        }

        public bool ToggleWeaponFavorite(string weaponId)
        {
            string normalized = (weaponId ?? "").Trim().ToUpperInvariant();
            if (!WeaponIds("all").Contains(
                    normalized, StringComparer.OrdinalIgnoreCase))
                return false;
            GbayPreferences.ToggleWeapon(normalized);
            return true;
        }

        public Allin1CustomizableWeaponPage BrowseCustomizableWeapons(
            Allin1CatalogRequest request)
        {
            RuntimeWeaponCatalog.Refresh();
            request = request ?? new Allin1CatalogRequest();
            string category = NormalizeChoice(
                request.Category, WeaponCategoryValues);
            string search = (request.Search ?? "").Trim();
            if (search.Length > MaximumSearchLength)
                search = search.Substring(0, MaximumSearchLength);
            int pageSize = Math.Max(1, Math.Min(64, request.PageSize));
            if (!StoryReady(out string storyFailure))
                return EmptyCustomizableWeaponPage(
                    category, search, storyFailure, pageSize);
            if (!_shop.OnlineContentEnabled)
                return EmptyCustomizableWeaponPage(
                    category, search,
                    "ALLIN1 Online Content is not enabled.", pageSize);

            Ped player = Game.Player.Character;
            string[] filtered = WeaponIds(category)
                .Where(value => !SmokeGrenadeCatalog.TryGetProduct(
                    value, out _))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Where(value =>
                {
                    int hash = CharacterInventory.GetWeaponHash(value);
                    if (!Function.Call<bool>(
                            Hash.IS_WEAPON_VALID, hash) ||
                        !Function.Call<bool>(
                            Hash.HAS_PED_GOT_WEAPON,
                            player.Handle, hash, false))
                        return false;
                    if (!HasWeaponCustomizationChoices(player, value, hash)) return false;
                    string display = WeaponDisplayName(value);
                    return search.Length == 0 ||
                        display.IndexOf(search,
                            StringComparison.OrdinalIgnoreCase) >= 0 ||
                        value.IndexOf(search,
                            StringComparison.OrdinalIgnoreCase) >= 0;
                })
                .ToArray();
            int pageCount = Math.Max(1,
                (filtered.Length + pageSize - 1) / pageSize);
            int page = Math.Max(1, Math.Min(pageCount, request.Page));
            Allin1CustomizableWeaponListing[] items = filtered
                .Skip((page - 1) * pageSize)
                .Take(pageSize)
                .Select(value =>
                {
                    bool hasPreview = RuntimeWeaponCatalog.PreviewDict.TryGetValue(
                        value, out string previewDictionary);
                    return new Allin1CustomizableWeaponListing
                    {
                        Id = value,
                        DisplayName = WeaponDisplayName(value),
                        Category = RuntimeWeaponCatalog.CategoryNames.TryGetValue(
                            value, out string itemCategory)
                                ? itemCategory : "Other",
                        AmmoStatus = DescribeAmmoStatus(value),
                        PreviewDictionary = hasPreview
                            ? previewDictionary : "",
                        PreviewTexture = hasPreview
                            ? value.ToLowerInvariant() : "",
                    };
                }).ToArray();
            return new Allin1CustomizableWeaponPage
            {
                Category = category,
                Search = search,
                Status = filtered.Length == 0
                    ? "No held weapons with attachment or finish choices match these filters. Ammo is available on the weapon screen."
                    : filtered.Length > pageSize
                        ? "Showing " + pageSize + " of " + filtered.Length + " customizable weapons. Narrow the category or search to see the others."
                        : "Choose a held weapon with attachment or finish choices.",
                Page = page,
                PageCount = pageCount,
                TotalItems = filtered.Length,
                Items = items,
            };
        }

        public Allin1WeaponCustomizationPage BrowseWeaponCustomization(
            string weaponId, string group, int page, int pageSize,
            bool refresh)
        {
            string normalized = NormalizeWeaponId(weaponId);
            string selectedGroup = NormalizeCustomizationGroup(group);
            // Reactor's weapon workbench is a scrollable attachment browser.
            // Keep the request bounded for safety while allowing the bridge to
            // deliver the complete live option set in one descriptor.
            pageSize = Math.Max(1, Math.Min(512, pageSize));
            if (!TryValidateCustomizableWeapon(
                    normalized, out string failure))
                return EmptyWeaponCustomizationPage(
                    normalized, selectedGroup, failure, pageSize);

            IReadOnlyList<GbayBrowser.DetachedWorkbenchRow> discovered;
            try
            {
                // `refresh` means re-check the live state, not throw away an
                // unchanged component catalog. Every call captures the cheap
                // state token, so automatic Reactor synchronization remains
                // fresh without repeating DLC/native discovery each second.
                discovered = GetWeaponCustomizationCatalog(normalized);
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "detached_weapon_catalog_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "weapon", normalized },
                    });
                return EmptyWeaponCustomizationPage(
                    normalized, selectedGroup,
                    "GTA could not describe compatible upgrades for this weapon.",
                    pageSize);
            }
            Allin1WeaponCustomizationOptionListing[] options = discovered
                .Where(value => CustomizationGroupMatches(
                    selectedGroup, value.Kind))
                .Select(value => DescribeCustomizationOption(
                    normalized, value))
                .ToArray();
            int pageCount = Math.Max(1,
                (options.Length + pageSize - 1) / pageSize);
            int selectedPage = Math.Max(1, Math.Min(pageCount, page));
            return new Allin1WeaponCustomizationPage
            {
                WeaponId = normalized,
                DisplayName = WeaponDisplayName(normalized),
                Group = selectedGroup,
                Page = selectedPage,
                PageCount = pageCount,
                TotalItems = options.Length,
                Balance = Game.Player.Money,
                Status = options.Length == 0
                    ? "This GTA build reported no compatible upgrades."
                    : "Compatible options reported by the live GTA runtime.",
                Items = options.Skip((selectedPage - 1) * pageSize)
                    .Take(pageSize).ToArray(),
            };
        }

        public Allin1GbayActionResult OpenWeaponWorkbench(
            Allin1WeaponWorkbenchRequest request)
        {
            string weapon = NormalizeWeaponId(request?.WeaponId);
            if (!TryValidateCustomizableWeapon(weapon, out string failure))
                return Allin1GbayActionResult.Failure(
                    "weapon_unavailable", failure);
            if (!_shop.TryOpenReactorWeaponWorkbench(
                    weapon, WeaponDisplayName(weapon)))
                return Allin1GbayActionResult.Failure(
                    "workbench_unavailable",
                    "The native weapon preview could not be opened here.");
            return Allin1GbayActionResult.Success(
                "workbench_opened",
                "ALLIN1's world-space weapon workbench is ready.");
        }

        public Allin1GbayActionResult BeginWeaponPreview(
            Allin1WeaponWorkbenchRequest request)
        {
            string weapon = NormalizeWeaponId(request?.WeaponId);
            if (!TryValidateCustomizableWeapon(weapon, out string failure))
                return Allin1GbayActionResult.Failure(
                    "weapon_unavailable", failure);
            if (!_shop.TryOpenReactorWeaponPreview(
                    weapon, WeaponDisplayName(weapon)))
                return Allin1GbayActionResult.Failure(
                    "preview_unavailable",
                    "The in-world weapon preview could not be opened here.");
            return Allin1GbayActionResult.Success(
                "preview_opened",
                "In-world preview active; Reactor remains the menu owner.");
        }

        public Allin1GbayActionResult PreviewWeaponCustomization(
            Allin1WeaponCustomizationApplyRequest request)
        {
            if (request == null)
                return Allin1GbayActionResult.Failure(
                    "invalid_preview", "A weapon option is required.");
            string weapon = NormalizeWeaponId(request.WeaponId);
            if (!TryValidateCustomizableWeapon(weapon, out string failure))
                return Allin1GbayActionResult.Failure(
                    "weapon_unavailable", failure);

            GbayBrowser.DetachedWorkbenchRow option;
            try
            {
                option = GetWeaponCustomizationCatalog(weapon)
                    .FirstOrDefault(value =>
                        CustomizationOptionMatches(value, request));
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "reactor_weapon_preview_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "weapon", weapon },
                        { "kind", request.Kind ?? "" },
                    });
                return Allin1GbayActionResult.Failure(
                    "runtime_unavailable",
                    "GTA could not revalidate this preview option.");
            }
            if (option == null)
                return Allin1GbayActionResult.Failure(
                    "option_changed",
                    "That option is no longer compatible. The workbench has updated automatically.");
            if (!_shop.TryPreviewReactorWeaponOption(
                    weapon, option.Kind, option.ComponentHash,
                    option.AttachmentPoint, option.Tint))
                return Allin1GbayActionResult.Failure(
                    "preview_unavailable",
                    "The in-world preview is no longer active.");
            return Allin1GbayActionResult.Success(
                "preview_updated", "In-world preview updated.");
        }

        public Allin1GbayActionResult EndWeaponPreview()
        {
            _shop.CloseReactorWeaponPreview();
            return Allin1GbayActionResult.Success(
                "preview_closed", "In-world weapon preview closed.");
        }

        public Allin1GbayActionResult ApplyWeaponCustomization(
            Allin1WeaponCustomizationApplyRequest request)
        {
            if (request == null)
                return Allin1GbayActionResult.Failure(
                    "invalid_customization", "A weapon option is required.");
            string weapon = NormalizeWeaponId(request.WeaponId);
            if (!TryValidateCustomizableWeapon(weapon, out string failure))
                return Allin1GbayActionResult.Failure(
                    "weapon_unavailable", failure);

            IReadOnlyList<GbayBrowser.DetachedWorkbenchRow> discovered;
            try
            {
                discovered = GetWeaponCustomizationCatalog(weapon);
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "detached_weapon_revalidate_failed", ex,
                    new Dictionary<string, object>
                    {
                        { "weapon", weapon },
                        { "kind", request.Kind ?? "" },
                    });
                return Allin1GbayActionResult.Failure(
                    "runtime_unavailable",
                    "GTA could not revalidate this weapon option.");
            }
            GbayBrowser.DetachedWorkbenchRow option = discovered
                .FirstOrDefault(value => CustomizationOptionMatches(
                    value, request));
            if (option == null)
                return Allin1GbayActionResult.Failure(
                    "option_changed",
                    "That option is no longer compatible. The workbench has updated automatically.");
            int currentPrice = EffectiveCustomizationPrice(weapon, option);
            if (request.QuotedPrice != currentPrice)
                return Allin1GbayActionResult.Failure(
                    "listing_changed",
                    "The option price changed. The workbench has updated automatically.");
            if (option.Active)
                return Allin1GbayActionResult.Failure(
                    "already_active", "That option is already active.");
            if (!_shop.FreeMode && currentPrice > Game.Player.Money)
                return Allin1GbayActionResult.Failure(
                    "insufficient_funds", "You no longer have enough money.");

            bool applied;
            string kind = (option.Kind ?? "").ToLowerInvariant();
            if (kind == "ammo")
            {
                int charged = _shop.ExecuteRefillAmmo(weapon);
                if (charged == GbayShop.AmmoCapacityUnavailable)
                    return Allin1GbayActionResult.Failure(
                        "ammo_unavailable",
                        "GTA could not resolve this weapon's ammo capacity.");
                if (charged == GbayShop.AmmoNotApplicable)
                    return Allin1GbayActionResult.Failure(
                        "ammo_not_applicable",
                        "This weapon no longer needs an ammunition refill.");
                if (charged < 0)
                    return Allin1GbayActionResult.Failure(
                        "purchase_rejected",
                        "The ammunition refill was not completed.");
                int rounds;
                applied = _shop.GetAmmoRefillInfo(weapon, out rounds) == 0 &&
                    rounds == 0;
            }
            else if (kind == "component")
            {
                GbayWeaponComponentPurchaseReadiness readiness = _shop
                    .GetWorkbenchComponentPurchaseReadiness(
                        weapon, option.ComponentHash);
                if (readiness != GbayWeaponComponentPurchaseReadiness.Ready)
                    return ComponentPurchasePreviewFailure(readiness);
                applied = GbayWeaponPreviewPolicy.RunComponentPurchaseTransaction(
                    readiness, () => _shop.ExecuteWeaponComponentPurchase(
                        weapon, option.ComponentHash,
                        option.AttachmentPoint, option.Price));
            }
            else if (kind == "component_remove")
                applied = _shop.ExecuteWeaponComponentRemoval(
                    weapon, option.ComponentHash, option.AttachmentPoint);
            else if (kind == "component_tint")
                applied = _shop.ExecuteWeaponComponentTintPurchase(
                    weapon, option.ComponentHash, option.AttachmentPoint,
                    option.Tint, option.Price);
            else if (kind == "tint")
                applied = _shop.ExecuteWeaponTintPurchase(
                    weapon, option.Tint, option.Price);
            else
                return Allin1GbayActionResult.Failure(
                    "invalid_customization", "Unknown weapon option type.");

            if (!applied || !CustomizationPostconditionSatisfied(
                    weapon, option))
                return Allin1GbayActionResult.Failure(
                    "apply_rejected",
                    "GTA did not confirm the weapon customization.");
            _customizationCacheWeapon = "";
            _customizationCache =
                Array.Empty<GbayBrowser.DetachedWorkbenchRow>();
            _customizationCacheStateToken = "";
            _customizationCacheInitialized = false;
            return Allin1GbayActionResult.Success(
                "weapon_customized",
                kind == "ammo" ? "Ammunition refilled."
                    : kind == "component_remove" ? "Attachment unequipped; ownership retained."
                    : IsCustomizationOptionOwned(weapon, option)
                        ? "Weapon option equipped."
                        : "Weapon option purchased and equipped.");
        }

        private static Allin1GbayActionResult ComponentPurchasePreviewFailure(
            GbayWeaponComponentPurchaseReadiness readiness)
        {
            if (readiness == GbayWeaponComponentPurchaseReadiness.PreviewPending)
                return Allin1GbayActionResult.Failure("preview_pending",
                    "The attachment model is still loading. Select it again when its preview appears.");
            if (readiness == GbayWeaponComponentPurchaseReadiness.PreviewRejected)
                return Allin1GbayActionResult.Failure("preview_rejected",
                    "GTA could not load that attachment model, so it was not purchased or equipped.");
            if (readiness == GbayWeaponComponentPurchaseReadiness.PreviewNotActive)
                return Allin1GbayActionResult.Failure("preview_unavailable",
                    "Open the weapon workbench before purchasing an attachment.");
            return Allin1GbayActionResult.Failure("preview_unconfirmed",
                "Preview this attachment before purchasing it.");
        }

        public Allin1GearCatalogPage BrowseGear(Allin1CatalogRequest request)
        {
            request = request ?? new Allin1CatalogRequest();
            string category = NormalizeChoice(
                request.Category, GearCategoryValues);
            string[] source = category == "protection" ? GearList.Protection
                : category == "equipment" ? GearList.Equipment : GearList.All;
            int pageSize = Math.Max(1, Math.Min(MaximumPageSize,
                request.PageSize));
            Allin1GearListing[] items = source.Select(gearId =>
            {
                bool hasPreview = GearList.PreviewDict.TryGetValue(
                    gearId, out string previewDictionary);
                return new Allin1GearListing
                {
                    Id = gearId,
                    DisplayName = GearList.DisplayNames.TryGetValue(
                        gearId, out string name) ? name : gearId,
                    Category = GearList.CategoryNames.TryGetValue(
                        gearId, out string itemCategory)
                        ? itemCategory : "Gear",
                    PreviewDictionary = hasPreview ? previewDictionary : "",
                    PreviewTexture = hasPreview
                        ? gearId.ToLowerInvariant() : "",
                    Price = _shop.FreeMode ? 0
                        : GearList.Prices.TryGetValue(
                            gearId, out int price) ? price : 0,
                    Owned = _shop.IsGearOwned(gearId),
                    Equipped = _shop.IsGearEquipped(gearId),
                };
            }).ToArray();
            int pageCount = Math.Max(1,
                (items.Length + pageSize - 1) / pageSize);
            int page = Math.Max(1, Math.Min(pageCount, request.Page));
            return new Allin1GearCatalogPage
            {
                Category = category,
                Page = page,
                PageCount = pageCount,
                TotalItems = items.Length,
                Balance = Game.Player.Money,
                Items = items.Skip((page - 1) * pageSize)
                    .Take(pageSize).ToArray(),
            };
        }

        public Allin1GbayActionResult ApplyGearAction(
            Allin1GearActionRequest request)
        {
            if (request == null || string.IsNullOrWhiteSpace(request.GearId))
                return Allin1GbayActionResult.Failure(
                    "invalid_gear", "A gear listing is required.");
            if (!StoryReady(out string storyFailure))
                return Allin1GbayActionResult.Failure(
                    "story_unavailable", storyFailure);
            if (!GbayShop.IsGearPlayerReady(Game.Player.Character))
                return Allin1GbayActionResult.Failure("gear_unavailable",
                    "Gear is unavailable while the player is changing.");
            if (!_shop.OnlineContentEnabled)
                return Allin1GbayActionResult.Failure(
                    "content_unavailable",
                    "ALLIN1 Online Content is not enabled.");
            string gearId = request.GearId.Trim().ToUpperInvariant();
            if (!GearList.All.Contains(
                    gearId, StringComparer.OrdinalIgnoreCase))
                return Allin1GbayActionResult.Failure(
                    "invalid_gear", "That item is not in the GBAY gear catalog.");
            string operation = (request.Operation ?? "").Trim()
                .ToLowerInvariant();
            int price = _shop.FreeMode ? 0
                : GearList.Prices.TryGetValue(gearId, out int currentPrice)
                    ? currentPrice : 0;
            bool owned = _shop.IsGearOwned(gearId);
            bool equipped = _shop.IsGearEquipped(gearId);
            if (operation == "purchase")
            {
                if (owned)
                    return Allin1GbayActionResult.Failure(
                        "already_owned", "That gear is already owned.");
                if (request.QuotedPrice != price)
                    return Allin1GbayActionResult.Failure(
                        "listing_changed",
                        "The gear price changed. GBAY has updated automatically; choose it again.");
                if (!_shop.FreeMode && price > Game.Player.Money)
                    return Allin1GbayActionResult.Failure(
                        "insufficient_funds",
                        "You no longer have enough money.");
                bool completed = _shop.GiveGearValidated(gearId, price);
                if (gearId == GearList.ARMOR_JUGGERNAUT &&
                    GbayShop.JuggernautPending &&
                    _shop.GearActionCode == "gear_pending")
                    return Allin1GbayActionResult.Failure("gear_pending",
                        "Preparing armor; no charge until equipped.");
                return completed
                    ? Allin1GbayActionResult.Success(_shop.GearActionCode,
                        _shop.GearActionMessage)
                    : Allin1GbayActionResult.Failure(
                        string.IsNullOrWhiteSpace(_shop.GearActionCode)
                            ? "purchase_rejected" : _shop.GearActionCode,
                        string.IsNullOrWhiteSpace(_shop.GearActionMessage)
                            ? "GTA did not confirm the gear purchase."
                            : _shop.GearActionMessage);
            }
            if (operation == "equip")
            {
                if (!owned)
                    return Allin1GbayActionResult.Failure(
                        "not_owned", "Purchase this gear first.");
                if (equipped)
                    return Allin1GbayActionResult.Failure(
                        "already_equipped", "That gear is already equipped.");
                bool completed = _shop.EquipGearValidated(gearId);
                if (gearId == GearList.ARMOR_JUGGERNAUT &&
                    GbayShop.JuggernautPending &&
                    _shop.GearActionCode == "gear_pending")
                    return Allin1GbayActionResult.Failure("gear_pending",
                        "Preparing armor; no charge until equipped.");
                return completed
                    ? Allin1GbayActionResult.Success(_shop.GearActionCode,
                        _shop.GearActionMessage)
                    : Allin1GbayActionResult.Failure(
                        string.IsNullOrWhiteSpace(_shop.GearActionCode)
                            ? "equip_rejected" : _shop.GearActionCode,
                        string.IsNullOrWhiteSpace(_shop.GearActionMessage)
                            ? "GTA did not confirm the gear change."
                            : _shop.GearActionMessage);
            }
            if (operation == "unequip")
            {
                if (!equipped)
                    return Allin1GbayActionResult.Failure(
                        "not_equipped", "That gear is not equipped.");
                bool completed = _shop.UnequipGearValidated(gearId);
                if (gearId == GearList.ARMOR_JUGGERNAUT &&
                    GbayShop.JuggernautPending &&
                    _shop.GearActionCode == "gear_pending")
                    return Allin1GbayActionResult.Failure("gear_pending",
                        "Preparing armor; no charge until equipped.");
                return completed
                    ? Allin1GbayActionResult.Success(_shop.GearActionCode,
                        _shop.GearActionMessage)
                    : Allin1GbayActionResult.Failure(
                        string.IsNullOrWhiteSpace(_shop.GearActionCode)
                            ? "unequip_rejected" : _shop.GearActionCode,
                        string.IsNullOrWhiteSpace(_shop.GearActionMessage)
                            ? "GTA did not confirm the gear change."
                            : _shop.GearActionMessage);
            }
            return Allin1GbayActionResult.Failure(
                "invalid_operation", "Unknown gear operation.");
        }

        public Allin1GarageSnapshot BrowseGarage()
        {
            var locations = new List<Allin1VehicleDeliveryOption>();
            var vehicles = new List<Allin1GarageVehicleListing>();
            for (int location = 0; location < DestinationIds.Length; location++)
            {
                int used = DestinationUsed(location);
                int capacity = DestinationCapacity(location);
                bool mapAvailable =
                    OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                        location);
                locations.Add(new Allin1VehicleDeliveryOption
                {
                    Id = DestinationIds[location],
                    Label = DestinationLabels[location],
                    UsedSlots = used,
                    Capacity = capacity,
                    Compatible = true,
                    // The garage directory, stored-vehicle inventory, and
                    // waypoint action do not need the destination's map
                    // content to be mounted. Map readiness gates entry and
                    // delivery separately; reusing it here made every garage
                    // appear unavailable when the retired broad map bridge
                    // was absent even though the garage services were live.
                    Available = true,
                    EntryAvailable = mapAvailable,
                    Status = used + "/" + capacity + " used",
                    InteriorMode = GarageReactorPolicy.InteriorMode(
                        DestinationIds[location]),
                    InteriorStatus = mapAvailable
                        ? GarageReactorPolicy.InteriorStatus(
                            DestinationIds[location])
                        : "Browsing and navigation are available. Entry map " +
                            "content is not ready; run Install / Repair.",
                });
                List<GarageManager.StoredVehicle> stored =
                    DestinationVehicles(location);
                for (int index = 0; index < stored.Count; index++)
                {
                    GarageManager.StoredVehicle vehicle = stored[index];
                    bool sellable = _shop.CanSellVehicle(
                        vehicle.Model, vehicle.PlateText, vehicle.ModelHash);
                    bool retrievable =
                        GarageReactorPolicy.IsRetrievalOnlyLocation(
                            DestinationIds[location]);
                    vehicles.Add(new Allin1GarageVehicleListing
                    {
                        LocationId = DestinationIds[location],
                        LocationLabel = DestinationLabels[location],
                        ListIndex = index,
                        Model = vehicle.Model,
                        ModelHash = vehicle.ModelHash,
                        PlateText = vehicle.PlateText ?? "",
                        DisplayName = GarageManager.GetVehicleDisplayName(
                            vehicle.Model, vehicle.ModelHash),
                        SellPrice = sellable && !retrievable
                            ? _shop.GetSellPrice(
                            vehicle.Model, vehicle.PlateText,
                            vehicle.ModelHash) : 0,
                        Sellable = sellable && !retrievable,
                        Retrievable = retrievable,
                    });
                }
            }
            bool recoveryAvailable =
                GarageManager.IsEmergencyRecoveryAvailable;
            return new Allin1GarageSnapshot
            {
                ActiveLocationId = GarageManager.ActiveGarageLocationId,
                Locations = locations,
                Vehicles = vehicles,
                EmergencyRecoveryAvailable = recoveryAvailable,
                EmergencyRecoveryStatus = recoveryAvailable
                    ? "A managed garage or transition can be recovered now."
                    : "Use only if a managed garage transition leaves you stuck.",
                Customization = DescribeDavisCustomization(),
            };
        }

        public Allin1GbayActionResult NavigateToGarage(
            Allin1GarageWaypointRequest request)
        {
            if (!StoryReady(out string storyFailure))
                return Allin1GbayActionResult.Failure(
                    "story_unavailable", storyFailure);
            string locationId = (request?.LocationId ?? "").Trim()
                .ToLowerInvariant();
            if (!DestinationIds.Contains(
                    locationId, StringComparer.OrdinalIgnoreCase))
                return Allin1GbayActionResult.Failure(
                    "invalid_garage", "That garage location is not available.");
            if (!GarageManager.TrySetGarageWaypoint(
                    locationId, out string label))
                return Allin1GbayActionResult.Failure(
                    "waypoint_failed", "GTA did not accept the garage waypoint.");
            return Allin1GbayActionResult.Success(
                "waypoint_set", "Route set to " + label + ".");
        }

        public Allin1GbayActionResult SellGarageVehicle(
            Allin1GarageVehicleRequest request)
        {
            if (!StoryReady(out string storyFailure) ||
                GarageManager.IsTransitionInProgress)
                return Allin1GbayActionResult.Failure(
                    "story_unavailable",
                    GarageManager.IsTransitionInProgress
                        ? "A garage transition is already in progress."
                        : storyFailure);
            if (!TryResolveGarageVehicle(request, out int location,
                    out GarageManager.StoredVehicle vehicle,
                    out string failure))
                return Allin1GbayActionResult.Failure(
                    "garage_changed", failure);
            if (GarageReactorPolicy.IsRetrievalOnlyLocation(
                    DestinationIds[location]))
                return Allin1GbayActionResult.Failure(
                    "retrieve_only",
                    DestinationLabels[location] +
                    " vehicles must be retrieved, not sold.");
            if (!_shop.CanSellVehicle(
                    vehicle.Model, vehicle.PlateText, vehicle.ModelHash))
                return Allin1GbayActionResult.Failure(
                    "protected_vehicle",
                    "Story-owned personal vehicles cannot be sold.");
            int price = _shop.GetSellPrice(
                vehicle.Model, vehicle.PlateText, vehicle.ModelHash);
            if (price != request.QuotedSellPrice)
                return Allin1GbayActionResult.Failure(
                    "listing_changed",
                    "The sale value changed. My Garage has updated automatically.");
            int countBeforeSale = DestinationVehicles(location).Count;
            _shop.ExecuteSellVehicle(
                vehicle.Model, request.ListIndex, location,
                vehicle.PlateText, vehicle.ModelHash);
            if (DestinationVehicles(location).Count >= countBeforeSale)
                return Allin1GbayActionResult.Failure(
                    "sale_rejected",
                    "ALLIN1 did not confirm removal from the garage.");
            return Allin1GbayActionResult.Success(
                "vehicle_sold", "Vehicle removed from " +
                    DestinationLabels[location] + ".");
        }

        public Allin1GbayActionResult RetrieveGarageVehicle(
            Allin1GarageVehicleRequest request)
        {
            if (!StoryReady(out string storyFailure) ||
                GarageManager.IsTransitionInProgress)
                return Allin1GbayActionResult.Failure(
                    "story_unavailable",
                    GarageManager.IsTransitionInProgress
                        ? "A garage transition is already in progress."
                        : storyFailure);
            if (!TryResolveGarageVehicle(request, out int location,
                    out GarageManager.StoredVehicle vehicle,
                    out string failure))
                return Allin1GbayActionResult.Failure(
                    "garage_changed", failure);
            if (!GarageReactorPolicy.IsRetrievalOnlyLocation(
                    DestinationIds[location]))
                return Allin1GbayActionResult.Failure(
                    "retrieve_unavailable",
                    "Only the Vespucci Helipad and Los Santos Harbour " +
                    "support retrieval from this menu.");
            bool retrieved = location == 6
                ? _shop.ExecuteRetrieveFromHelipad(request.ListIndex)
                : location == 8 &&
                    _shop.ExecuteRetrieveFromHarbour(request.ListIndex);
            return retrieved
                ? Allin1GbayActionResult.Success(
                    "vehicle_retrieved", vehicle.Model + " retrieved.")
                : Allin1GbayActionResult.Failure(
                    "retrieve_unavailable",
                    "Only the Vespucci Helipad and Los Santos Harbour " +
                    "support retrieval from this menu.");
        }

        public Allin1GbayActionResult ApplyGarageCustomization(
            Allin1GarageCustomizationRequest request)
        {
            if (!StoryReady(out string storyFailure) ||
                GarageManager.IsTransitionInProgress)
                return Allin1GbayActionResult.Failure(
                    "story_unavailable",
                    GarageManager.IsTransitionInProgress
                        ? "Wait for the active garage transition to finish."
                        : storyFailure);
            if (request == null || !string.Equals(
                    request.LocationId, "davis",
                    StringComparison.OrdinalIgnoreCase))
                return Allin1GbayActionResult.Failure(
                    "fixed_interior",
                    "Only the Davis Auto Shop has configurable interior options.");
            if (!GarageManager.IsDavisGarageInitialized)
                return Allin1GbayActionResult.Failure(
                    "customization_unavailable",
                    "The Davis Auto Shop is not initialized.");

            int category = Array.FindIndex(
                DavisCustomizationCategoryIds,
                value => string.Equals(value, request.CategoryId,
                    StringComparison.Ordinal));
            if (category < 0)
                return Allin1GbayActionResult.Failure(
                    "invalid_customization",
                    "That Davis customization category is not available.");
            int option = ParseDavisOptionId(request.OptionId);
            int expected = ParseDavisOptionId(request.ExpectedOptionId);
            int optionCount = GarageManager.GetDavisCustomizationOptionCount(
                category);
            if (option < 0 || option >= optionCount ||
                expected < 0 || expected >= optionCount)
                return Allin1GbayActionResult.Failure(
                    "invalid_customization",
                    "That Davis customization option is not available.");

            int current = GarageManager.GetDavisCustomizationChoice(category);
            if (current == option)
                return Allin1GbayActionResult.Success(
                    "customization_unchanged",
                    "That Davis Auto Shop option is already selected.");
            if (current != expected)
                return Allin1GbayActionResult.Failure(
                    "customization_changed",
                    "The Davis Auto Shop changed. My Garage has updated automatically.");

            GarageManager.SetDavisCustomizationChoice(category, option);
            if (GarageManager.GetDavisCustomizationChoice(category) != option)
                return Allin1GbayActionResult.Failure(
                    "customization_rejected",
                    "ALLIN1 did not confirm the Davis Auto Shop change.");
            return Allin1GbayActionResult.Success(
                "customization_applied",
                GarageManager.DAVIS_CUSTOM_CATEGORY_NAMES[category] +
                " updated to " +
                GarageManager.DAVIS_CUSTOM_OPTION_LABELS[category][option] +
                ".");
        }

        public Allin1GbayActionResult EmergencyRecoverGarage()
        {
            if (!StoryReady(out string storyFailure))
                return Allin1GbayActionResult.Failure(
                    "story_unavailable", storyFailure);
            if (!GarageManager.IsEmergencyRecoveryAvailable)
                return Allin1GbayActionResult.Failure(
                    "recovery_not_needed",
                    "No managed garage transition currently needs recovery.");
            GarageManager.EmergencyRecover();
            return GarageManager.IsEmergencyRecoveryAvailable
                ? Allin1GbayActionResult.Failure(
                    "recovery_incomplete",
                    "The garage recovery did not complete safely.")
                : Allin1GbayActionResult.Success(
                    "garage_recovered",
                    "Garage state reset and the player was returned outside.");
        }

        private static Allin1GarageCustomizationSnapshot
            DescribeDavisCustomization()
        {
            bool storyReady = StoryReady(out string storyFailure);
            bool available = storyReady &&
                GarageManager.IsDavisGarageInitialized &&
                !GarageManager.IsTransitionInProgress;
            var categories = new List<Allin1GarageCustomizationCategory>();
            for (int category = 0;
                category < GarageManager.DAVIS_CUSTOM_CATEGORY_COUNT;
                category++)
            {
                int optionCount = GarageManager.GetDavisCustomizationOptionCount(
                    category);
                var options = new List<Allin1GarageCustomizationOption>();
                for (int option = 0; option < optionCount; option++)
                    options.Add(new Allin1GarageCustomizationOption
                    {
                        Id = DavisOptionId(option),
                        Label = GarageManager.DAVIS_CUSTOM_OPTION_LABELS
                            [category][option],
                    });
                categories.Add(new Allin1GarageCustomizationCategory
                {
                    Id = DavisCustomizationCategoryIds[category],
                    Label = GarageManager.DAVIS_CUSTOM_CATEGORY_NAMES[category],
                    SelectedOptionId = DavisOptionId(
                        GarageManager.GetDavisCustomizationChoice(category)),
                    Options = options,
                });
            }
            return new Allin1GarageCustomizationSnapshot
            {
                LocationId = "davis",
                LocationLabel = "Davis Auto Shop",
                Available = available,
                LivePreview = GarageManager.IsPlayerInDavisGarage,
                Status = available
                    ? GarageManager.IsPlayerInDavisGarage
                        ? "Changes are saved per character and previewed live."
                        : "Changes are saved per character and applied on entry."
                    : GarageManager.IsTransitionInProgress
                        ? "Wait for the garage transition to finish."
                        : GarageManager.IsDavisGarageInitialized
                            ? storyFailure
                            : "The Davis Auto Shop is not initialized.",
                Categories = categories,
            };
        }

        private static string DavisOptionId(int option) =>
            "option-" + option.ToString(CultureInfo.InvariantCulture);

        private static int ParseDavisOptionId(string optionId)
        {
            const string prefix = "option-";
            string value = (optionId ?? "").Trim();
            if (!value.StartsWith(prefix, StringComparison.Ordinal)) return -1;
            return int.TryParse(value.Substring(prefix.Length),
                NumberStyles.None, CultureInfo.InvariantCulture,
                out int option) ? option : -1;
        }

        private Allin1CustomizableWeaponPage EmptyCustomizableWeaponPage(
            string category, string search, string status, int pageSize) =>
            new Allin1CustomizableWeaponPage
            {
                Category = category,
                Search = search,
                Status = status,
                Page = 1,
                PageCount = 1,
                TotalItems = 0,
                Items = Array.Empty<Allin1CustomizableWeaponListing>(),
            };

        private Allin1WeaponCustomizationPage EmptyWeaponCustomizationPage(
            string weapon, string group, string status, int pageSize) =>
            new Allin1WeaponCustomizationPage
            {
                WeaponId = weapon,
                DisplayName = WeaponDisplayName(weapon),
                Group = group,
                Page = 1,
                PageCount = 1,
                TotalItems = 0,
                Balance = Game.Player.Money,
                Status = status,
                Items = Array.Empty<Allin1WeaponCustomizationOptionListing>(),
            };

        private string DescribeAmmoStatus(string weapon)
        {
            int rounds = 0;
            int cost = _shop.GetAmmoRefillInfo(weapon, out rounds);
            if (cost == GbayShop.AmmoCapacityUnavailable)
                return "Capacity unavailable";
            if (cost == GbayShop.AmmoNotApplicable)
                return "Not applicable";
            if (rounds == 0) return "Fully stocked";
            return rounds.ToString("N0", CultureInfo.InvariantCulture) +
                " rounds · " + (cost <= 0 ? "FREE" : "$" +
                    cost.ToString("N0", CultureInfo.InvariantCulture));
        }

        private bool TryValidateCustomizableWeapon(
            string weapon, out string failure)
        {
            if (!StoryReady(out failure)) return false;
            if (!_shop.OnlineContentEnabled)
            {
                failure = "ALLIN1 Online Content is not enabled.";
                return false;
            }
            if (string.IsNullOrWhiteSpace(weapon) ||
                SmokeGrenadeCatalog.TryGetProduct(weapon, out _) ||
                !WeaponIds("all").Contains(
                    weapon, StringComparer.OrdinalIgnoreCase))
            {
                failure = "That weapon is not in the customizable GBAY catalog.";
                return false;
            }
            int hash = CharacterInventory.GetWeaponHash(weapon);
            Ped player = Game.Player.Character;
            if (!Function.Call<bool>(Hash.IS_WEAPON_VALID, hash))
            {
                failure = "That weapon is unavailable in this GTA V build.";
                return false;
            }
            if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    player.Handle, hash, false))
            {
                failure = "Equip or restore this owned weapon before customizing it.";
                return false;
            }
            if (!HasWeaponCustomizationChoices(player, weapon, hash))
            {
                failure = "This weapon has no attachment or finish choices. Buy ammunition on the weapon screen.";
                return false;
            }
            failure = "";
            return true;
        }

        private static bool HasWeaponCustomizationChoices(Ped player, string weapon, int hash)
        {
            int tints = RuntimeWeaponCatalog.SupportedTintCount(weapon,
                Function.Call<int>(Hash.GET_WEAPON_TINT_COUNT, hash));
            if (tints > 1) return true;
            // SHVDN's per-weapon collection uses the live compatible-component
            // table. Do not rebuild the full workbench/DLC catalog per listing.
            var entries = new List<WeaponComponentDefaults.Entry>();
            foreach (WeaponComponent component in player.Weapons[(WeaponHash)(uint)hash].Components)
            {
                int componentHash = unchecked((int)component.ComponentHash);
                int point = (int)component.AttachmentPoint;
                bool defaultAccessory = WeaponCustomizationPolicy.CanUnequipComponent(point) &&
                    WeaponComponentDefaults.IsDefault(hash, componentHash);
                entries.Add(new WeaponComponentDefaults.Entry(componentHash, point, defaultAccessory));
            }
            return WeaponCustomizationPolicy.HasChoices(entries, tints);
        }

        private Allin1WeaponCustomizationOptionListing
            DescribeCustomizationOption(
                string weapon,
                GbayBrowser.DetachedWorkbenchRow row) =>
            new Allin1WeaponCustomizationOptionListing
            {
                Kind = row.Kind ?? "",
                Label = row.Label ?? "Weapon option",
                Detail = row.Detail ?? "",
                Price = EffectiveCustomizationPrice(weapon, row),
                ComponentHash = row.ComponentHash,
                AttachmentPoint = row.AttachmentPoint,
                Tint = row.Tint,
                Owned = IsCustomizationOptionOwned(weapon, row),
                Active = row.Active,
            };

        /// <summary>
        /// Returns the one per-storefront live component catalog. The caller
        /// never receives write authority; rows remain detached descriptions.
        /// </summary>
        internal IReadOnlyList<GbayBrowser.DetachedWorkbenchRow>
            GetWeaponCustomizationCatalog(string weapon)
        {
            string normalized = NormalizeWeaponId(weapon);
            string currentStateToken = _customizationCacheInitialized &&
                string.Equals(_customizationCacheWeapon, normalized,
                    StringComparison.OrdinalIgnoreCase)
                    ? CaptureWeaponCustomizationStateToken(
                        normalized, _customizationCache)
                    : "";
            if (GbayWeaponCatalogCachePolicy.ShouldRebuild(
                    _customizationCacheInitialized,
                    _customizationCacheWeapon,
                    normalized,
                    _customizationCacheStateToken,
                    currentStateToken))
            {
                IReadOnlyList<GbayBrowser.DetachedWorkbenchRow> rebuilt =
                    GbayBrowser.DescribeDetachedWeaponCustomization(
                        _shop, normalized, allowStorefrontCache: false);
                _customizationCache = rebuilt ??
                    Array.Empty<GbayBrowser.DetachedWorkbenchRow>();
                _customizationCacheWeapon = normalized;
                _customizationCacheStateToken =
                    CaptureWeaponCustomizationStateToken(
                        normalized, _customizationCache);
                _customizationCacheInitialized = true;
            }
            return _customizationCache;
        }

        internal bool TryGetCachedWeaponCustomizationCatalog(
            string weapon,
            out IReadOnlyList<GbayBrowser.DetachedWorkbenchRow> rows)
        {
            string normalized = NormalizeWeaponId(weapon);
            if (!_customizationCacheInitialized || !string.Equals(
                    _customizationCacheWeapon, normalized,
                    StringComparison.OrdinalIgnoreCase))
            {
                rows = Array.Empty<GbayBrowser.DetachedWorkbenchRow>();
                return false;
            }
            rows = GetWeaponCustomizationCatalog(normalized);
            return true;
        }

        private string CaptureWeaponCustomizationStateToken(
            string weapon,
            IReadOnlyList<GbayBrowser.DetachedWorkbenchRow> rows)
        {
            var token = new System.Text.StringBuilder(512);
            Ped player = Game.Player.Character;
            int playerHandle = player != null && player.Exists()
                ? player.Handle : 0;
            int playerModel = player != null && player.Exists()
                ? player.Model.Hash : 0;
            int weaponHash = CharacterInventory.GetWeaponHash(weapon);
            bool weaponOwned = playerHandle != 0 && Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON,
                playerHandle, weaponHash, false);
            int rounds = 0;
            int ammoStatus = playerHandle != 0
                ? _shop.GetAmmoRefillInfo(weapon, out rounds)
                : GbayShop.AmmoCapacityUnavailable;
            int liveWeaponTint = weaponOwned
                ? Function.Call<int>(Hash.GET_PED_WEAPON_TINT_INDEX,
                    playerHandle, weaponHash)
                : -1;
            token.Append(weapon).Append('|')
                .Append(playerHandle).Append('|')
                .Append(playerModel).Append('|')
                .Append(weaponOwned ? '1' : '0').Append('|')
                .Append(_shop.OnlineContentEnabled ? '1' : '0').Append('|')
                .Append(_shop.FreeMode ? '1' : '0').Append('|')
                .Append(SafeDlcWeaponCount(storyMode: false)).Append('|')
                .Append(SafeDlcWeaponCount(storyMode: true)).Append('|')
                .Append(ammoStatus).Append(':').Append(rounds).Append('|')
                .Append(CharacterInventory.GetActiveWeaponTint(weapon))
                .Append(':').Append(liveWeaponTint);

            if (rows != null)
            {
                foreach (GbayBrowser.DetachedWorkbenchRow row in rows)
                {
                    if (row == null) continue;
                    string kind = (row.Kind ?? "").ToLowerInvariant();
                    token.Append(';').Append(kind).Append(':')
                        .Append(row.ComponentHash).Append(':')
                        .Append(row.AttachmentPoint).Append(':')
                        .Append(row.Tint).Append(':');
                    if (kind == "component" || kind == "component_remove")
                    {
                        bool liveOwned = playerHandle != 0 &&
                            Function.Call<bool>(
                                Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                                playerHandle, weaponHash,
                                row.ComponentHash);
                        token.Append(liveOwned ? '1' : '0').Append(':')
                            .Append(CharacterInventory
                                .IsWeaponComponentOwned(
                                    weapon, row.ComponentHash) ? '1' : '0')
                            .Append(':').Append(CharacterInventory
                                .GetActiveWeaponComponent(
                                    weapon, row.AttachmentPoint))
                            .Append(':').Append(Allin1ExtensionApi
                                .IsWeaponComponentConsumed(
                                    weapon, row.ComponentHash) ? '1' : '0');
                    }
                    else if (kind == "component_tint")
                    {
                        bool liveComponent = playerHandle != 0 &&
                            Function.Call<bool>(
                                Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                                playerHandle, weaponHash,
                                row.ComponentHash);
                        int liveTint = liveComponent
                            ? Function.Call<int>(
                                Hash.GET_PED_WEAPON_COMPONENT_TINT_INDEX,
                                playerHandle, weaponHash,
                                row.ComponentHash)
                            : -1;
                        token.Append(CharacterInventory
                                .IsWeaponComponentTintOwned(
                                    weapon, row.ComponentHash, row.Tint)
                                    ? '1' : '0')
                            .Append(':').Append(CharacterInventory
                                .GetActiveWeaponComponentTint(
                                    weapon, row.ComponentHash))
                            .Append(':').Append(liveTint);
                    }
                    else if (kind == "tint")
                    {
                        token.Append(CharacterInventory.IsWeaponTintOwned(
                                weapon, row.Tint) ? '1' : '0')
                            .Append(':').Append(CharacterInventory
                                .GetActiveWeaponTint(weapon));
                    }
                }
            }
            return token.ToString();
        }

        private static int SafeDlcWeaponCount(bool storyMode)
        {
            try
            {
                return Math.Max(0, Function.Call<int>(storyMode
                    ? Hash.GET_NUM_DLC_WEAPONS_SP
                    : Hash.GET_NUM_DLC_WEAPONS));
            }
            catch
            {
                return -1;
            }
        }

        private int EffectiveCustomizationPrice(
            string weapon, GbayBrowser.DetachedWorkbenchRow row) =>
            _shop.FreeMode || IsCustomizationOptionOwned(weapon, row) ||
                row.Active
                ? 0 : Math.Max(0, row.Price);

        private static bool IsCustomizationOptionOwned(
            string weapon, GbayBrowser.DetachedWorkbenchRow row) =>
            row.Owned && !(string.Equals(
                    row.Kind, "component", StringComparison.OrdinalIgnoreCase) &&
                Allin1ExtensionApi.IsWeaponComponentConsumed(
                    weapon, row.ComponentHash));

        private static bool CustomizationOptionMatches(
            GbayBrowser.DetachedWorkbenchRow row,
            Allin1WeaponCustomizationApplyRequest request)
        {
            string kind = (request.Kind ?? "").Trim().ToLowerInvariant();
            if (!string.Equals(row.Kind, kind,
                    StringComparison.OrdinalIgnoreCase))
                return false;
            if (kind == "ammo")
                return request.ComponentHash == 0 &&
                    request.AttachmentPoint == 0 && request.Tint == 0;
            if (kind == "component" || kind == "component_remove")
                return row.ComponentHash == request.ComponentHash &&
                    row.AttachmentPoint == request.AttachmentPoint &&
                    request.Tint == 0;
            if (kind == "tint")
                return request.ComponentHash == 0 &&
                    request.AttachmentPoint == 0 && row.Tint == request.Tint;
            return kind == "component_tint" &&
                row.ComponentHash == request.ComponentHash &&
                row.AttachmentPoint == request.AttachmentPoint &&
                row.Tint == request.Tint;
        }

        private bool CustomizationPostconditionSatisfied(
            string weapon, GbayBrowser.DetachedWorkbenchRow applied)
        {
            if (string.Equals(applied.Kind, "ammo",
                    StringComparison.OrdinalIgnoreCase))
            {
                int rounds;
                return _shop.GetAmmoRefillInfo(weapon, out rounds) == 0 &&
                    rounds == 0;
            }
            Ped player = Game.Player.Character;
            if (player == null || !player.Exists()) return false;
            int weaponHash = CharacterInventory.GetWeaponHash(weapon);
            if (string.Equals(applied.Kind, "component_remove", StringComparison.OrdinalIgnoreCase))
                return !Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                        player.Handle, weaponHash, applied.ComponentHash) &&
                    CharacterInventory.GetActiveWeaponComponent(weapon, applied.AttachmentPoint) != applied.ComponentHash &&
                    CharacterInventory.IsWeaponComponentOwned(weapon, applied.ComponentHash);
            if (string.Equals(applied.Kind, "component",
                    StringComparison.OrdinalIgnoreCase))
                return Function.Call<bool>(
                        Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                        player.Handle, weaponHash, applied.ComponentHash) &&
                    CharacterInventory.GetActiveWeaponComponent(
                        weapon, applied.AttachmentPoint) ==
                            applied.ComponentHash;
            if (string.Equals(applied.Kind, "component_tint",
                    StringComparison.OrdinalIgnoreCase))
                return Function.Call<bool>(
                        Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                        player.Handle, weaponHash, applied.ComponentHash) &&
                    Function.Call<int>(
                        Hash.GET_PED_WEAPON_COMPONENT_TINT_INDEX,
                        player.Handle, weaponHash, applied.ComponentHash) ==
                            applied.Tint &&
                    CharacterInventory.GetActiveWeaponComponentTint(
                        weapon, applied.ComponentHash) == applied.Tint;
            return string.Equals(applied.Kind, "tint",
                    StringComparison.OrdinalIgnoreCase) &&
                Function.Call<int>(Hash.GET_PED_WEAPON_TINT_INDEX,
                    player.Handle, weaponHash) == applied.Tint &&
                CharacterInventory.GetActiveWeaponTint(weapon) == applied.Tint;
        }

        private static string NormalizeWeaponId(string weaponId) =>
            (weaponId ?? "").Trim().ToUpperInvariant();

        private static string NormalizeCustomizationGroup(string group)
        {
            string normalized = (group ?? "all").Trim().ToLowerInvariant();
            return normalized == "ammo" || normalized == "components" ||
                normalized == "tints" || normalized == "livery"
                    ? normalized : "all";
        }

        private static bool CustomizationGroupMatches(
            string group, string kind) =>
            group == "all" ||
            group == "ammo" && kind == "ammo" ||
            group == "components" && (kind == "component" || kind == "component_remove") ||
            group == "tints" && kind == "tint" ||
            group == "livery" && kind == "component_tint";

        private static string WeaponDisplayName(string weaponId) =>
            RuntimeWeaponCatalog.DisplayNames.TryGetValue(
                weaponId ?? "", out string name) ? name : weaponId ?? "";

        private static string NormalizeChoice(
            string value, IEnumerable<string> allowed)
        {
            string normalized = (value ?? "all").Trim().ToLowerInvariant();
            return allowed.Contains(normalized, StringComparer.OrdinalIgnoreCase)
                ? normalized : "all";
        }

        private static string NormalizeOwnership(string value)
        {
            string normalized = (value ?? "all").Trim().ToLowerInvariant();
            return OwnershipValues.Contains(normalized) ? normalized : "all";
        }

        private static string[] WeaponIds(string category)
        {
            string[] baseValues;
            switch ((category ?? "all").ToLowerInvariant())
            {
                case "pistols": baseValues = RuntimeWeaponCatalog.Pistols; break;
                case "smgs": baseValues = RuntimeWeaponCatalog.Smgs; break;
                case "shotguns": baseValues = RuntimeWeaponCatalog.Shotguns; break;
                case "rifles": baseValues = RuntimeWeaponCatalog.Rifles; break;
                case "machineguns": baseValues = RuntimeWeaponCatalog.MachineGuns; break;
                case "snipers": baseValues = RuntimeWeaponCatalog.Snipers; break;
                case "heavy": baseValues = RuntimeWeaponCatalog.Heavy; break;
                case "melee": baseValues = RuntimeWeaponCatalog.Melee; break;
                case "throwables":
                    return RuntimeWeaponCatalog.Sort(RuntimeWeaponCatalog.Throwables.Concat(
                        SmokeGrenadeCatalog.ProductIds));
                case "misc": baseValues = RuntimeWeaponCatalog.Misc; break;
                default:
                    return RuntimeWeaponCatalog.Sort(RuntimeWeaponCatalog.All.Concat(
                        SmokeGrenadeCatalog.ProductIds));
            }
            return baseValues.ToArray();
        }

        private static bool IsWeaponOwned(string weaponId)
        {
            Ped player = Game.Player.Character;
            int hash = CharacterInventory.GetWeaponHash(weaponId);
            return player != null && player.Exists() &&
                    Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                        player.Handle, hash, false) ||
                CharacterInventory.IsOwned(weaponId, false);
        }

        private static List<GarageManager.StoredVehicle>
            DestinationVehicles(int location)
        {
            switch (location)
            {
                case 1: return GarageManager.GetFloorGarageStoredVehicles();
                case 2: return GarageManager.GetDavisGarageStoredVehicles();
                case 3: return GarageManager.GetGarmentGarageStoredVehicles();
                case 4: return GarageManager.GetRuralGarageStoredVehicles();
                case 5: return GarageManager.GetPaletoGarageStoredVehicles();
                case 6: return GarageManager.GetHelipadStoredVehicles();
                case 7: return GarageManager.GetYachtHelipadStoredVehicles();
                case 8: return GarageManager.GetHarbourStoredVehicles();
                default: return GarageManager.GetStoredVehicles();
            }
        }

        private static bool TryResolveGarageVehicle(
            Allin1GarageVehicleRequest request, out int location,
            out GarageManager.StoredVehicle vehicle, out string failure)
        {
            location = -1;
            vehicle = null;
            failure = "The garage selection is invalid.";
            if (request == null || string.IsNullOrWhiteSpace(
                    request.LocationId) || request.ListIndex < 0)
                return false;
            location = Array.FindIndex(DestinationIds, value => string.Equals(
                value, request.LocationId.Trim(),
                StringComparison.OrdinalIgnoreCase));
            if (location < 0) return false;
            List<GarageManager.StoredVehicle> vehicles =
                DestinationVehicles(location);
            if (request.ListIndex >= vehicles.Count)
            {
                failure = "The garage changed. My Garage has updated automatically.";
                return false;
            }
            GarageManager.StoredVehicle candidate = vehicles[request.ListIndex];
            if (!string.Equals(candidate.Model, request.Model,
                    StringComparison.OrdinalIgnoreCase) ||
                candidate.ModelHash != request.ModelHash ||
                !string.Equals(candidate.PlateText ?? "",
                    request.PlateText ?? "", StringComparison.Ordinal))
            {
                failure = "The selected vehicle moved or changed. My Garage has updated automatically.";
                return false;
            }
            vehicle = candidate;
            failure = "";
            return true;
        }

        private static bool StoryReady(out string failure)
        {
            if (!GbayShop.TryGetCurrentCharacter(out _))
            {
                failure = "GBAY is available to Michael, Franklin, and Trevor.";
                return false;
            }
            if (Game.IsLoading || Game.Player.Character == null ||
                !Game.Player.Character.Exists() || Game.Player.Character.IsDead)
            {
                failure = "Story Mode is not ready.";
                return false;
            }
            failure = "";
            return true;
        }

        private static IReadOnlyList<Allin1VehicleDeliveryOption>
            BuildDeliveryOptions(string model)
        {
            if (WorldAssetList.IsWorldAsset(model))
            {
                bool owned = YachtManager.FeaturesUnlocked;
                bool mapAvailable =
                    OfficialMapContentPolicy.IsDeliveryDestinationAvailable(7);
                return new[]
                {
                    new Allin1VehicleDeliveryOption
                    {
                        Id = "world-property",
                        Label = "World property",
                        UsedSlots = 0,
                        Capacity = 1,
                        Compatible = true,
                        Available = mapAvailable &&
                            OfficialMapContentPolicy
                                .IsWorldPropertyPurchaseAvailable(owned),
                        EntryAvailable = mapAvailable,
                        Status = !mapAvailable
                            ? OfficialMapContentPolicy.UnknownDestinationStatus
                            : owned ? "Already owned" : "Permanent unlock",
                    },
                };
            }
            var result = new List<Allin1VehicleDeliveryOption>(
                DestinationIds.Length);
            for (int index = 0; index < DestinationIds.Length; index++)
            {
                int used = DestinationUsed(index);
                int capacity = DestinationCapacity(index);
                bool compatible = DestinationCompatible(index, model);
                bool mapAvailable =
                    OfficialMapContentPolicy.IsDeliveryDestinationAvailable(
                        index);
                bool available = mapAvailable && compatible && used < capacity;
                result.Add(new Allin1VehicleDeliveryOption
                {
                    Id = DestinationIds[index],
                    Label = DestinationLabels[index],
                    UsedSlots = used,
                    Capacity = capacity,
                    Compatible = compatible,
                    Available = available,
                    EntryAvailable = mapAvailable,
                    Status = !mapAvailable
                        ? OfficialMapContentPolicy.UnknownDestinationStatus
                        : !compatible ? DestinationIncompatibleReason(
                            index, model)
                        : used >= capacity ? "Full (" + used + "/" +
                            capacity + ")"
                        : used + "/" + capacity + " used",
                });
            }
            return result;
        }

        private static string SuggestedDestination(
            string model, IReadOnlyList<Allin1VehicleDeliveryOption> values)
        {
            if (WorldAssetList.IsWorldAsset(model)) return "world-property";
            int preferred = GarageManager.IsPlayerInFloorGarage ? 1
                : GarageManager.IsPlayerInDavisGarage ? 2
                : GarageManager.IsPlayerInGarmentGarage ? 3
                : GarageManager.IsPlayerInRuralGarage ? 4
                : GarageManager.IsPlayerInPaletoGarage ? 5 : 0;
            if (GarageManager.IsHarbourVehicleEligible(model)) preferred = 8;
            else if (GarageManager.IsHelipadVehicleEligible(model)) preferred = 6;
            if (preferred >= 0 && preferred < values.Count &&
                values[preferred].Available)
                return values[preferred].Id;
            Allin1VehicleDeliveryOption available = values.FirstOrDefault(
                value => value.Available);
            return available?.Id ?? "";
        }

        private static int DestinationUsed(int index)
        {
            switch (index)
            {
                case 1: return GarageManager.GetFloorGarageUsedSlots();
                case 2: return GarageManager.GetDavisGarageUsedSlots();
                case 3: return GarageManager.GetGarmentGarageUsedSlots();
                case 4: return GarageManager.GetRuralGarageUsedSlots();
                case 5: return GarageManager.GetPaletoGarageUsedSlots();
                case 6: return GarageManager.GetHelipadUsedSlots();
                case 7: return GarageManager.GetYachtHelipadUsedSlots();
                case 8: return GarageManager.GetHarbourUsedSlots();
                default: return GarageManager.GetUsedSlots();
            }
        }

        private static int DestinationCapacity(int index)
        {
            switch (index)
            {
                case 1: return GarageManager.GetFloorGarageCapacity();
                case 2: return GarageManager.GetDavisGarageCapacity();
                case 3: return GarageManager.GetGarmentGarageCapacity();
                case 4: return GarageManager.GetRuralGarageCapacity();
                case 5: return GarageManager.GetPaletoGarageCapacity();
                case 6: return GarageManager.GetHelipadCapacity();
                case 7: return GarageManager.GetYachtHelipadCapacity();
                case 8: return GarageManager.GetHarbourCapacity();
                default: return GarageManager.GetCapacity();
            }
        }

        private static bool DestinationCompatible(int index, string model)
        {
            if (index == 6)
                return GarageManager.IsHelipadVehicleEligible(model);
            if (index == 7)
                return YachtManager.FeaturesUnlocked &&
                    GarageManager.IsYachtHelipadVehicleEligible(model);
            if (index == 8)
                return GarageManager.IsHarbourVehicleEligible(model);
            if (!GarageVehicleTypePolicy.IsRegularGarageEligible(model))
                return false;
            int maximumSizeTier = index == 1 ? 2 : 1;
            return GarageManager.GetGarageSizeTier(model) <= maximumSizeTier;
        }

        private static string DestinationIncompatibleReason(
            int index, string model)
        {
            if (index == 7 && !YachtManager.FeaturesUnlocked)
                return "Yacht required";
            if (index == 6) return "Helicopters only";
            if (index == 7) return "Yacht helicopters only";
            if (index == 8) return "Boats only";
            if (string.Equals(RuntimeVehicleCatalog.GetStorage(model), "hangar",
                    StringComparison.OrdinalIgnoreCase))
                return "Hangar unavailable";
            if (GarageVehicleTypePolicy.RequiresSpecializedStorage(model))
                return "Specialized storage required";
            return "Vehicle too large";
        }

        private static string CatalogRevision(IEnumerable<string> models)
        {
            // Stable, non-cryptographic revision used only to identify a view.
            // Purchase authority is always revalidated against live data.
            ulong hash = 14695981039346656037UL;
            int count = 0;
            unchecked
            {
                foreach (string model in models)
                {
                    count++;
                    string value = model + ":" +
                        RuntimeVehicleCatalog.GetPrice(model).ToString(
                            CultureInfo.InvariantCulture);
                    foreach (char character in value)
                    {
                        hash ^= character;
                        hash *= 1099511628211UL;
                    }
                }
            }
            return "v1-" + count.ToString() + "-" + hash.ToString("x16");
        }
    }

    internal static class GbayReactorBridgeLoader
    {
        private const string PluginAssemblyName = "ALLIN1.ReactorBridge";
        private static readonly string PluginPath = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ReactorV",
            "ALLIN1.ReactorBridge.plugin");

        internal static IAllin1MenuBridge TryLoad(
            IAllin1VehicleStorefront storefront, out string status)
        {
            status = "Reactor V is not loaded.";
            if (!IsAssemblyLoaded("RageWebUI.Script") ||
                !IsAssemblyLoaded("RageWebUI.Core"))
                return null;
            if (!File.Exists(PluginPath))
            {
                status = "ALLIN1 Reactor bridge is not installed.";
                return null;
            }

            try
            {
                AssemblyName identity = AssemblyName.GetAssemblyName(PluginPath);
                if (!string.Equals(identity.Name, PluginAssemblyName,
                        StringComparison.Ordinal))
                {
                    status = "ALLIN1 Reactor bridge has an invalid identity.";
                    return null;
                }
                Assembly assembly = AppDomain.CurrentDomain.GetAssemblies()
                    .FirstOrDefault(value => string.Equals(
                        value.GetName().Name, PluginAssemblyName,
                        StringComparison.Ordinal)) ?? Assembly.LoadFrom(PluginPath);
                Type implementation = SafeTypes(assembly).FirstOrDefault(type =>
                    type != null && !type.IsAbstract && !type.IsInterface &&
                    typeof(IAllin1MenuBridge).IsAssignableFrom(type));
                if (implementation == null)
                {
                    status = "ALLIN1 Reactor bridge has no compatible entrypoint.";
                    return null;
                }
                var bridge = (IAllin1MenuBridge)Activator.CreateInstance(
                    implementation);
                if (!bridge.Initialize(storefront))
                {
                    status = string.IsNullOrWhiteSpace(bridge.Status)
                        ? "ALLIN1 Reactor bridge initialization failed."
                        : bridge.Status;
                    bridge.Dispose();
                    return null;
                }
                status = bridge.Status;
                return bridge;
            }
            catch (Exception ex)
            {
                status = ex.GetType().Name + ": " + ex.Message;
                return null;
            }
        }

        private static bool IsAssemblyLoaded(string simpleName) =>
            AppDomain.CurrentDomain.GetAssemblies().Any(value => string.Equals(
                value.GetName().Name, simpleName, StringComparison.Ordinal));

        private static IEnumerable<Type> SafeTypes(Assembly assembly)
        {
            try { return assembly.GetTypes(); }
            catch (ReflectionTypeLoadException ex)
            {
                return ex.Types.Where(value => value != null);
            }
        }
    }
}
