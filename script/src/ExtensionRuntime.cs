// Receipt-authorized extension registry and public runtime contracts.
//
// The desktop launcher owns registry.json. The game client consumes it as an
// immutable authorization snapshot; third-party code cannot add itself to the
// registry from inside the game process.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using GTA;

namespace ALLIN1
{
    /// <summary>Information supplied to a receipt-authorized save participant.</summary>
    public sealed class StorySaveContext
    {
        internal StorySaveContext(DateTime writeTimeUtc, string reason)
        {
            WriteTimeUtc = writeTimeUtc;
            Reason = reason ?? "story_save_written";
        }

        public DateTime WriteTimeUtc { get; }
        public string Reason { get; }
    }

    /// <summary>Information supplied when staged session state must be discarded.</summary>
    public sealed class StorySessionEndContext
    {
        internal StorySessionEndContext(DateTime lastSaveWriteTimeUtc, string reason)
        {
            LastSaveWriteTimeUtc = lastSaveWriteTimeUtc;
            Reason = reason ?? "session_ended";
        }

        public DateTime LastSaveWriteTimeUtc { get; }
        public string Reason { get; }
    }

    /// <summary>
    /// A Story-save transaction participant. Keep purchases in memory until
    /// Commit is called; Discard must remove any remaining uncommitted state.
    /// </summary>
    public interface IStorySaveParticipant
    {
        void Commit(StorySaveContext context);
        void Discard(StorySessionEndContext context);
    }

    /// <summary>
    /// Optional bridge between a receipt-authorized weapon mod and GBAY's
    /// generic component storefront. Implementations can mark a component as
    /// consumed and observe only completed, successfully applied purchases.
    /// </summary>
    public interface IWeaponComponentLifecycleParticipant
    {
        bool IsComponentConsumed(string weaponName, int componentHash);
        void OnComponentPurchased(
            string weaponName, int componentHash, int attachmentPoint);
    }

    /// <summary>A declarative GBAY route backed by a receipt-authorized callback.</summary>
    public sealed class GbayAddonAction
    {
        private readonly Action _callback;

        internal GbayAddonAction(
            string packageId, string route, string label, string description,
            int order, Action callback, Assembly callbackAssembly,
            int authorizationGeneration)
        {
            PackageId = packageId;
            Route = route;
            Label = label;
            Description = description;
            Order = order;
            _callback = callback;
            CallbackAssembly = callbackAssembly;
            AuthorizationGeneration = authorizationGeneration;
        }

        public string PackageId { get; }
        public string Route { get; }
        public string Label { get; }
        public string Description { get; }
        public int Order { get; }

        internal Assembly CallbackAssembly { get; }
        internal int AuthorizationGeneration { get; set; }

        internal void Invoke()
        {
            _callback();
        }
    }

    /// <summary>A contained, launcher-authorized GBAY catalog declaration.</summary>
    public sealed class GbayCatalogDeclaration
    {
        internal GbayCatalogDeclaration(
            string packageId, string id, string kind,
            string source, string sourcePath)
        {
            PackageId = packageId;
            Id = id;
            Kind = kind;
            Source = source;
            SourcePath = sourcePath;
        }

        public string PackageId { get; }
        public string Id { get; }
        public string Kind { get; }
        public string Source { get; }
        public string SourcePath { get; }
        public bool Exists => File.Exists(SourcePath);
    }

    /// <summary>
    /// Stable v1 query and registration surface for ALLIN1 content packages.
    /// Registration is accepted only when the launcher registry enables the
    /// package and the callback's assembly matches a receipt-owned runtime file.
    /// </summary>
    public static class Allin1ExtensionApi
    {
        public const int ApiVersion = 1;
        public const string OnlineContentPackageId = "allin1.online-content";
        public const string ExperimentalGameplayPackageId =
            "allin1.experimental-gameplay";

        private static readonly object Sync = new object();
        private static readonly string ScriptsDirectory = ResolveScriptsDirectory(
            ResolveAssemblySourcePath(typeof(Allin1ExtensionApi).Assembly),
            AppDomain.CurrentDomain.BaseDirectory);
        private static readonly string RegistryPath = Path.Combine(
            ScriptsDirectory, ".allin1", "extensions", "registry.json");
        private static RuntimeExtensionRegistry _registry;
        private static DateTime _registryWriteUtc = DateTime.MinValue;
        private static long _registryLength = -1;
        private static int _registryGeneration;
        private static readonly Dictionary<string, GbayAddonAction> GbayActions =
            new Dictionary<string, GbayAddonAction>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, StorySaveParticipant> SaveParticipants =
            new Dictionary<string, StorySaveParticipant>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, WeaponComponentParticipant>
            WeaponComponentParticipants =
                new Dictionary<string, WeaponComponentParticipant>(
                    StringComparer.OrdinalIgnoreCase);
        private static DateTime _lastNotifiedSaveUtc = DateTime.MinValue;

        /// <summary>True when a valid launcher-authored registry is active.</summary>
        public static bool RegistryAvailable
        {
            get
            {
                lock (Sync)
                {
                    RuntimeExtensionRegistry registry = RegistryLocked();
                    return registry.Present && registry.Valid;
                }
            }
        }

        /// <summary>
        /// True while ALLIN1's GBAY browser is open. External gameplay scripts
        /// can use this to ignore transient workbench previews.
        /// </summary>
        public static bool IsGbayMenuActive => GbayShop.IsMenuActive;

        /// <summary>
        /// Return whether a package is enabled. Missing registry files retain
        /// compatibility for the two official packages only; malformed registry
        /// files fail closed.
        /// </summary>
        public static bool IsPackageEnabled(string packageId)
        {
            if (!RuntimeExtensionRegistry.IsSafeId(packageId)) return false;
            lock (Sync)
            {
                return RegistryLocked().IsEnabled(packageId);
            }
        }

        /// <summary>Return a detached snapshot of enabled package identifiers.</summary>
        public static IReadOnlyList<string> GetEnabledPackageIds()
        {
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                return registry.Packages.Values
                    .Where(value => registry.IsEnabled(value.Id))
                    .Select(value => value.Id)
                    .OrderBy(value => value, StringComparer.OrdinalIgnoreCase)
                    .ToArray();
            }
        }

        /// <summary>Read one effective package setting emitted by the launcher.</summary>
        public static bool TryGetSetting(
            string packageId, string key, out object value)
        {
            value = null;
            if (!RuntimeExtensionRegistry.IsSafeId(packageId) ||
                string.IsNullOrWhiteSpace(key))
                return false;
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                RuntimeExtensionPackage package;
                if (!registry.Packages.TryGetValue(packageId, out package) ||
                    !registry.IsEnabled(packageId))
                    return false;
                return package.Settings.TryGetValue(key.Trim(), out value);
            }
        }

        public static bool GetBooleanSetting(
            string packageId, string key, bool defaultValue = false)
        {
            object value;
            return TryGetSetting(packageId, key, out value) && value is bool boolean
                ? boolean : defaultValue;
        }

        public static string GetStringSetting(
            string packageId, string key, string defaultValue = "")
        {
            object value;
            return TryGetSetting(packageId, key, out value) && value is string text
                ? text : defaultValue;
        }

        public static int GetIntegerSetting(
            string packageId, string key, int defaultValue = 0)
        {
            object value;
            return TryGetSetting(packageId, key, out value) && value is int number
                ? number : defaultValue;
        }

        public static double GetNumberSetting(
            string packageId, string key, double defaultValue = 0d)
        {
            object value;
            if (!TryGetSetting(packageId, key, out value) || value is bool)
                return defaultValue;
            try
            {
                return Convert.ToDouble(value, CultureInfo.InvariantCulture);
            }
            catch (Exception)
            {
                return defaultValue;
            }
        }

        public static bool HasCapability(string packageId, string capability)
        {
            if (!RuntimeExtensionRegistry.IsSafeId(packageId) ||
                !RuntimeExtensionRegistry.IsSafeId(capability))
                return false;
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                RuntimeExtensionPackage package;
                return registry.Packages.TryGetValue(packageId, out package) &&
                    registry.IsEnabled(packageId) &&
                    package.Capabilities.Contains(capability);
            }
        }

        /// <summary>
        /// Return contained GBAY catalog metadata for an enabled package that
        /// declared the gbay.catalogs capability. Catalog JSON interpretation
        /// remains the responsibility of a compatible registered route.
        /// </summary>
        public static IReadOnlyList<GbayCatalogDeclaration> GetGbayCatalogs(
            string packageId)
        {
            if (!RuntimeExtensionRegistry.IsSafeId(packageId))
                return new GbayCatalogDeclaration[0];
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                RuntimeExtensionPackage package;
                if (!registry.Packages.TryGetValue(packageId, out package) ||
                    !registry.IsEnabled(packageId) ||
                    !package.Capabilities.Contains("gbay.catalogs"))
                    return new GbayCatalogDeclaration[0];
                return CurrentGbayCatalogs(package);
            }
        }

        internal static IReadOnlyList<GbayCatalogDeclaration>
            CurrentGbayCatalogs(RuntimeExtensionPackage package)
        {
            if (package == null)
                return new GbayCatalogDeclaration[0];
            return package.Catalogs
                .Where(value => value.IsCurrent())
                .Select(value => new GbayCatalogDeclaration(
                    package.Id, value.Id, value.Kind,
                    value.Source, value.SourcePath))
                .ToArray();
        }

        /// <summary>
        /// Bind a callback to a non-built-in route declared by this package's
        /// content manifest. The returned handle unregisters the callback.
        /// </summary>
        public static IDisposable RegisterGbayAction(
            string packageId, string route, Action callback)
        {
            if (callback == null) throw new ArgumentNullException(nameof(callback));
            if (callback.GetInvocationList().Length != 1)
                throw new ArgumentException(
                    "GBAY actions must contain exactly one callback.",
                    nameof(callback));
            Assembly callbackAssembly = callback.Method.Module.Assembly;
            lock (Sync)
            {
                RuntimeExtensionPackage package = AuthorizedPackageLocked(
                    packageId, "gbay.sections", callbackAssembly);
                RuntimeGbaySection section = package.Sections.FirstOrDefault(value =>
                    string.Equals(value.Route, route, StringComparison.OrdinalIgnoreCase));
                if (section == null)
                    throw new InvalidOperationException(
                        "GBAY route is not declared by the package registry: " + route);
                if (section.Route.StartsWith("builtin:", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException(
                        "Built-in GBAY routes cannot be replaced by extension callbacks.");
                string registrationKey = package.Id + "\0" + section.Route;
                if (GbayActions.ContainsKey(registrationKey))
                    throw new InvalidOperationException(
                        "GBAY route is already registered: " + section.Route);
                GbayActions[registrationKey] = new GbayAddonAction(
                    package.Id, section.Route, section.Label,
                    section.Description, section.Order, callback,
                    callbackAssembly,
                    _registryGeneration);
                return new ExtensionRegistration(() =>
                {
                    lock (Sync) GbayActions.Remove(registrationKey);
                });
            }
        }

        /// <summary>
        /// Register a staged transaction participant. Commit is called only
        /// after a native Story Mode save file advances; Discard is called when
        /// the script session ends so unsaved purchases cannot survive it.
        /// </summary>
        public static IDisposable RegisterStorySaveParticipant(
            string packageId, string participantId,
            IStorySaveParticipant participant)
        {
            if (participant == null)
                throw new ArgumentNullException(nameof(participant));
            if (!RuntimeExtensionRegistry.IsSafeId(participantId))
                throw new ArgumentException("Invalid participant id", nameof(participantId));
            participantId = participantId.Trim().ToLowerInvariant();
            Assembly participantAssembly = ParticipantImplementationAssembly(
                participant, typeof(IStorySaveParticipant));
            if (participantAssembly == null)
                throw new ArgumentException(
                    "Commit and Discard must be implemented by the participant assembly.",
                    nameof(participant));
            lock (Sync)
            {
                RuntimeExtensionPackage package = AuthorizedPackageLocked(
                    packageId, "story-save.transactions",
                    participantAssembly);
                string registrationKey = package.Id + "\0" + participantId;
                if (SaveParticipants.ContainsKey(registrationKey))
                    throw new InvalidOperationException(
                        "Story-save participant is already registered: " + participantId);
                SaveParticipants[registrationKey] = new StorySaveParticipant(
                    package.Id, participantId, participant,
                    participantAssembly, _registryGeneration);
                return new ExtensionRegistration(() =>
                {
                    lock (Sync) SaveParticipants.Remove(registrationKey);
                });
            }
        }

        /// <summary>
        /// Synchronize a native weapon-ammo mutation into ALLIN1's optional
        /// per-character inventory ledger. The proof callback is not invoked;
        /// its declaring assembly is validated against the enabled package's
        /// receipt-owned runtime file before the ledger can be changed.
        /// </summary>
        public static void RecordWeaponAmmo(
            string packageId, string weaponName, int ammo,
            Action authorizationProof)
        {
            if (authorizationProof == null)
                throw new ArgumentNullException(nameof(authorizationProof));
            if (authorizationProof.GetInvocationList().Length != 1)
                throw new ArgumentException(
                    "Authorization proof must contain exactly one callback.",
                    nameof(authorizationProof));
            if (string.IsNullOrWhiteSpace(weaponName) ||
                !weaponName.Trim().StartsWith(
                    "WEAPON_", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException(
                    "A GTA weapon name is required.", nameof(weaponName));
            if (ammo < 0 || ammo > 99999)
                throw new ArgumentOutOfRangeException(nameof(ammo));

            Assembly callbackAssembly =
                authorizationProof.Method.Module.Assembly;
            lock (Sync)
            {
                AuthorizedPackageLocked(
                    packageId, "story-save.transactions",
                    callbackAssembly);
            }
            CharacterInventory.RecordWeaponAmmo(
                weaponName.Trim().ToUpperInvariant(), ammo);
        }

        /// <summary>
        /// Register a generic weapon-component lifecycle participant. GBAY
        /// queries consumed state before pricing and reports only purchases
        /// that were charged/applied successfully.
        /// </summary>
        public static IDisposable RegisterWeaponComponentLifecycleParticipant(
            string packageId, string participantId,
            IWeaponComponentLifecycleParticipant participant)
        {
            if (participant == null)
                throw new ArgumentNullException(nameof(participant));
            if (!RuntimeExtensionRegistry.IsSafeId(participantId))
                throw new ArgumentException(
                    "Invalid participant id", nameof(participantId));
            participantId = participantId.Trim().ToLowerInvariant();
            Assembly participantAssembly = ParticipantImplementationAssembly(
                participant,
                typeof(IWeaponComponentLifecycleParticipant));
            if (participantAssembly == null)
                throw new ArgumentException(
                    "Lifecycle methods must be implemented by the participant assembly.",
                    nameof(participant));
            lock (Sync)
            {
                RuntimeExtensionPackage package = AuthorizedPackageLocked(
                    packageId, "weapon.components.lifecycle",
                    participantAssembly);
                string registrationKey = package.Id + "\0" + participantId;
                if (WeaponComponentParticipants.ContainsKey(registrationKey))
                    throw new InvalidOperationException(
                        "Weapon-component participant is already registered: " +
                        participantId);
                WeaponComponentParticipants[registrationKey] =
                    new WeaponComponentParticipant(
                        package.Id, participantId, participant,
                        participantAssembly, _registryGeneration);
                return new ExtensionRegistration(() =>
                {
                    lock (Sync)
                        WeaponComponentParticipants.Remove(registrationKey);
                });
            }
        }

        /// <summary>Reload the launcher-authored registry on the next API query.</summary>
        public static void ReloadRegistry()
        {
            lock (Sync)
            {
                _registry = null;
                _registryWriteUtc = DateTime.MinValue;
                _registryLength = -1;
            }
        }

        // Test-only seams exercise callback dispatch without weakening the
        // receipt/assembly checks on the public registration methods.
        internal static IDisposable RegisterGbayActionForTests(
            string packageId, string route, Action callback)
        {
            lock (Sync)
            {
                RegistryLocked();
                string key = packageId + "\0" + route;
                var action = new GbayAddonAction(
                    packageId, route, "Test action", "", 100, callback,
                    callback.Method.Module.Assembly, _registryGeneration);
                GbayActions.Add(key, action);
                return new ExtensionRegistration(() =>
                {
                    lock (Sync) GbayActions.Remove(key);
                });
            }
        }

        internal static IDisposable RegisterStorySaveParticipantForTests(
            string packageId, string participantId,
            IStorySaveParticipant participant)
        {
            lock (Sync)
            {
                RegistryLocked();
                string key = packageId + "\0" + participantId;
                SaveParticipants.Add(key, new StorySaveParticipant(
                    packageId, participantId, participant,
                    participant.GetType().Assembly, _registryGeneration));
                return new ExtensionRegistration(() =>
                {
                    lock (Sync) SaveParticipants.Remove(key);
                });
            }
        }

        internal static void ResetCallbacksForTests()
        {
            lock (Sync)
            {
                GbayActions.Clear();
                SaveParticipants.Clear();
                WeaponComponentParticipants.Clear();
                _lastNotifiedSaveUtc = DateTime.MinValue;
                _registry = null;
                _registryWriteUtc = DateTime.MinValue;
                _registryLength = -1;
                _registryGeneration = 0;
            }
        }

        internal static string ResolveScriptsDirectory(
            string assemblyLocation, string fallbackBaseDirectory)
        {
            try
            {
                if (!string.IsNullOrWhiteSpace(assemblyLocation))
                {
                    string assemblyDirectory = Path.GetDirectoryName(
                        Path.GetFullPath(assemblyLocation));
                    if (!string.IsNullOrWhiteSpace(assemblyDirectory))
                        return assemblyDirectory;
                }
            }
            catch (Exception) { }
            return Path.GetFullPath(fallbackBaseDirectory);
        }

        /// <summary>
        /// Return the original on-disk source of an assembly. ScriptHookVDotNet
        /// shadow-copies script assemblies, so Location can name its cache while
        /// CodeBase still names the launcher-authorized file under scripts.
        /// </summary>
        internal static string ResolveAssemblySourcePath(Assembly assembly)
        {
            if (assembly == null) return null;
            string codeBase = null;
            string location = null;
            try { codeBase = assembly.CodeBase; }
            catch (Exception) { }
            try { location = assembly.Location; }
            catch (Exception) { }
            return ResolveAssemblySourcePath(codeBase, location);
        }

        internal static string ResolveAssemblySourcePath(
            string codeBase, string location)
        {
            if (!string.IsNullOrWhiteSpace(codeBase))
            {
                try
                {
                    Uri source;
                    if (Uri.TryCreate(codeBase, UriKind.Absolute, out source) &&
                        source.IsFile)
                    {
                        string localPath = source.LocalPath;
                        if (!string.IsNullOrWhiteSpace(localPath))
                            return Path.GetFullPath(localPath);
                    }
                }
                catch (Exception) { }
            }
            if (!string.IsNullOrWhiteSpace(location))
            {
                try { return Path.GetFullPath(location); }
                catch (Exception) { }
            }
            return null;
        }

        private static Assembly ParticipantImplementationAssembly(
            object participant, Type interfaceType)
        {
            if (participant == null || interfaceType == null ||
                !interfaceType.IsInstanceOfType(participant))
                return null;
            Type participantType = participant.GetType();
            Assembly assembly = participantType.Assembly;
            try
            {
                InterfaceMapping mapping = participantType.GetInterfaceMap(
                    interfaceType);
                return mapping.TargetMethods.All(method =>
                    method.Module.Assembly == assembly) ? assembly : null;
            }
            catch (Exception)
            {
                return null;
            }
        }

        internal static IReadOnlyList<GbayAddonAction> GetGbayActions()
        {
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                foreach (string key in GbayActions.Keys.ToArray())
                {
                    GbayAddonAction action = GbayActions[key];
                    if (!AuthorizesGbayAction(registry, action))
                        GbayActions.Remove(key);
                }
                return GbayActions.Values
                    .OrderBy(value => value.Order)
                    .ThenBy(value => value.Label, StringComparer.OrdinalIgnoreCase)
                    .ToArray();
            }
        }

        internal static void InvokeGbayAction(GbayAddonAction action)
        {
            if (action == null) return;
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                string key = action.PackageId + "\0" + action.Route;
                GbayAddonAction current;
                if (!GbayActions.TryGetValue(key, out current) ||
                    !ReferenceEquals(current, action) ||
                    !AuthorizesGbayAction(registry, action))
                    return;
            }
            try
            {
                action.Invoke();
                ClientLog.Info("Extensions", "gbay_action_invoked",
                    new Dictionary<string, object> {
                        { "package", action.PackageId }, { "route", action.Route }
                    });
            }
            catch (Exception ex)
            {
                ClientLog.Error("Extensions", "gbay_action_failed", ex,
                    new Dictionary<string, object> {
                        { "package", action.PackageId }, { "route", action.Route }
                    });
            }
        }

        internal static IDisposable
            RegisterWeaponComponentLifecycleParticipantForTests(
                string packageId, string participantId,
                IWeaponComponentLifecycleParticipant participant)
        {
            lock (Sync)
            {
                RegistryLocked();
                string key = packageId + "\0" + participantId;
                WeaponComponentParticipants.Add(key,
                    new WeaponComponentParticipant(
                        packageId, participantId, participant,
                        participant.GetType().Assembly,
                        _registryGeneration));
                return new ExtensionRegistration(() =>
                {
                    lock (Sync)
                        WeaponComponentParticipants.Remove(key);
                });
            }
        }

        internal static bool IsWeaponComponentConsumed(
            string weaponName, int componentHash)
        {
            if (string.IsNullOrWhiteSpace(weaponName) || componentHash == 0)
                return false;
            WeaponComponentParticipant[] participants;
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                foreach (string key in
                    WeaponComponentParticipants.Keys.ToArray())
                {
                    if (!AuthorizesWeaponComponentParticipant(
                            registry, WeaponComponentParticipants[key]))
                        WeaponComponentParticipants.Remove(key);
                }
                participants = WeaponComponentParticipants.Values.ToArray();
            }
            foreach (WeaponComponentParticipant participant in participants)
            {
                try
                {
                    if (participant.Participant.IsComponentConsumed(
                            weaponName, componentHash))
                        return true;
                }
                catch (Exception ex)
                {
                    ClientLog.Error("Extensions",
                        "weapon_component_consumed_query_failed", ex,
                        new Dictionary<string, object>
                        {
                            { "package", participant.PackageId },
                            { "participant", participant.Id },
                            { "weapon", weaponName },
                            { "component_hash", componentHash },
                        });
                }
            }
            return false;
        }

        internal static void NotifyWeaponComponentPurchased(
            string weaponName, int componentHash, int attachmentPoint)
        {
            if (string.IsNullOrWhiteSpace(weaponName) || componentHash == 0)
                return;
            WeaponComponentParticipant[] participants;
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                foreach (string key in
                    WeaponComponentParticipants.Keys.ToArray())
                {
                    if (!AuthorizesWeaponComponentParticipant(
                            registry, WeaponComponentParticipants[key]))
                        WeaponComponentParticipants.Remove(key);
                }
                participants = WeaponComponentParticipants.Values.ToArray();
            }
            foreach (WeaponComponentParticipant participant in participants)
            {
                try
                {
                    participant.Participant.OnComponentPurchased(
                        weaponName, componentHash, attachmentPoint);
                }
                catch (Exception ex)
                {
                    ClientLog.Error("Extensions",
                        "weapon_component_purchase_notification_failed", ex,
                        new Dictionary<string, object>
                        {
                            { "package", participant.PackageId },
                            { "participant", participant.Id },
                            { "weapon", weaponName },
                            { "component_hash", componentHash },
                            { "attachment_point", attachmentPoint },
                        });
                }
            }
        }

        internal static void NotifyStorySave(DateTime writeTimeUtc, string reason)
        {
            StorySaveParticipant[] participants;
            StorySaveParticipant[] revoked;
            lock (Sync)
            {
                if (writeTimeUtc <= _lastNotifiedSaveUtc) return;
                _lastNotifiedSaveUtc = writeTimeUtc;
                RuntimeExtensionRegistry registry = RegistryLocked();
                revoked = RemoveUnauthorizedSaveParticipantsLocked(registry);
                participants = SaveParticipants.Values.ToArray();
            }
            DiscardParticipants(
                revoked, writeTimeUtc, "authorization_revoked");
            StorySaveContext context = new StorySaveContext(writeTimeUtc, reason);
            foreach (StorySaveParticipant participant in participants)
            {
                try
                {
                    participant.Participant.Commit(context);
                }
                catch (Exception ex)
                {
                    ClientLog.Error("Extensions", "story_save_participant_failed", ex,
                        new Dictionary<string, object> {
                            { "package", participant.PackageId },
                            { "participant", participant.Id }
                        });
                }
            }
        }

        internal static void NotifySessionEnd(
            DateTime lastSaveWriteTimeUtc, string reason)
        {
            StorySaveParticipant[] participants;
            StorySaveParticipant[] revoked;
            lock (Sync)
            {
                RuntimeExtensionRegistry registry = RegistryLocked();
                revoked = RemoveUnauthorizedSaveParticipantsLocked(registry);
                participants = SaveParticipants.Values.ToArray();
            }
            DiscardParticipants(
                revoked, lastSaveWriteTimeUtc, "authorization_revoked");
            DiscardParticipants(participants, lastSaveWriteTimeUtc, reason);
        }

        private static StorySaveParticipant[]
            RemoveUnauthorizedSaveParticipantsLocked(
                RuntimeExtensionRegistry registry)
        {
            var removed = new List<StorySaveParticipant>();
            foreach (string key in SaveParticipants.Keys.ToArray())
            {
                StorySaveParticipant participant = SaveParticipants[key];
                if (AuthorizesSaveParticipant(registry, participant))
                    continue;
                SaveParticipants.Remove(key);
                removed.Add(participant);
            }
            return removed.ToArray();
        }

        private static void DiscardParticipants(
            IEnumerable<StorySaveParticipant> participants,
            DateTime lastSaveWriteTimeUtc, string reason)
        {
            var context = new StorySessionEndContext(
                lastSaveWriteTimeUtc, reason);
            foreach (StorySaveParticipant participant in participants)
            {
                try
                {
                    participant.Participant.Discard(context);
                }
                catch (Exception ex)
                {
                    ClientLog.Error("Extensions",
                        "story_save_participant_discard_failed", ex,
                        new Dictionary<string, object> {
                            { "package", participant.PackageId },
                            { "participant", participant.Id }
                        });
                }
            }
        }

        private static RuntimeExtensionPackage AuthorizedPackageLocked(
            string packageId, string capability, Assembly callbackAssembly)
        {
            if (!RuntimeExtensionRegistry.IsSafeId(packageId))
                throw new ArgumentException("Invalid package id", nameof(packageId));
            RuntimeExtensionPackage package;
            RuntimeExtensionRegistry registry = RegistryLocked();
            if (!registry.Present)
                throw new InvalidOperationException(
                    "Runtime registrations require a launcher-authored extension registry.");
            if (!registry.Packages.TryGetValue(packageId, out package) ||
                !registry.IsEnabled(packageId))
                throw new InvalidOperationException(
                    "Content package is not enabled: " + packageId);
            if (!package.Capabilities.Contains(capability))
                throw new InvalidOperationException(
                    "Content package did not declare capability: " + capability);
            if (callbackAssembly == null || !package.AuthorizesAssembly(
                    callbackAssembly, ScriptsDirectory))
                throw new InvalidOperationException(
                    "Callback assembly is not authorized by the package receipt.");
            return package;
        }

        private static bool AuthorizesGbayAction(
            RuntimeExtensionRegistry registry, GbayAddonAction action)
        {
            if (action.AuthorizationGeneration == _registryGeneration)
                return true;
            RuntimeExtensionPackage package;
            bool authorized = registry.Present && registry.Valid &&
                registry.Packages.TryGetValue(action.PackageId, out package) &&
                registry.IsEnabled(action.PackageId) &&
                package.Capabilities.Contains("gbay.sections") &&
                package.Sections.Any(value =>
                    !value.Route.StartsWith(
                        "builtin:", StringComparison.OrdinalIgnoreCase) &&
                    string.Equals(value.Route, action.Route,
                        StringComparison.OrdinalIgnoreCase)) &&
                package.AuthorizesAssembly(
                    action.CallbackAssembly, ScriptsDirectory);
            if (authorized)
                action.AuthorizationGeneration = _registryGeneration;
            return authorized;
        }

        private static bool AuthorizesSaveParticipant(
            RuntimeExtensionRegistry registry, StorySaveParticipant participant)
        {
            if (participant.AuthorizationGeneration == _registryGeneration)
                return true;
            RuntimeExtensionPackage package;
            bool authorized = registry.Present && registry.Valid &&
                registry.Packages.TryGetValue(
                    participant.PackageId, out package) &&
                registry.IsEnabled(participant.PackageId) &&
                package.Capabilities.Contains("story-save.transactions") &&
                package.AuthorizesAssembly(
                    participant.CallbackAssembly, ScriptsDirectory);
            if (authorized)
                participant.AuthorizationGeneration = _registryGeneration;
            return authorized;
        }

        private static bool AuthorizesWeaponComponentParticipant(
            RuntimeExtensionRegistry registry,
            WeaponComponentParticipant participant)
        {
            if (participant.AuthorizationGeneration == _registryGeneration)
                return true;
            RuntimeExtensionPackage package;
            bool authorized = registry.Present && registry.Valid &&
                registry.Packages.TryGetValue(
                    participant.PackageId, out package) &&
                registry.IsEnabled(participant.PackageId) &&
                package.Capabilities.Contains(
                    "weapon.components.lifecycle") &&
                package.AuthorizesAssembly(
                    participant.CallbackAssembly, ScriptsDirectory);
            if (authorized)
                participant.AuthorizationGeneration = _registryGeneration;
            return authorized;
        }

        private static RuntimeExtensionRegistry RegistryLocked()
        {
            FileInfo info = new FileInfo(RegistryPath);
            DateTime writeUtc = info.Exists ? info.LastWriteTimeUtc : DateTime.MinValue;
            long length = info.Exists ? info.Length : -1;
            if (_registry != null && writeUtc == _registryWriteUtc &&
                length == _registryLength)
                return _registry;
            try
            {
                _registry = RuntimeExtensionRegistry.Load(RegistryPath, ScriptsDirectory);
            }
            catch (Exception primary)
            {
                // A stale backup may describe a package that the user has since
                // disabled or uninstalled. A present but malformed primary is
                // therefore an authorization failure, never a fallback signal.
                _registry = RuntimeExtensionRegistry.Invalid(
                    ScriptsDirectory, primary.Message);
                ClientLog.Error("Extensions", "registry_invalid", primary);
            }
            _registryWriteUtc = writeUtc;
            _registryLength = length;
            unchecked { _registryGeneration++; }
            return _registry;
        }

        private sealed class StorySaveParticipant
        {
            internal StorySaveParticipant(
                string packageId, string id, IStorySaveParticipant participant,
                Assembly callbackAssembly, int authorizationGeneration)
            {
                PackageId = packageId;
                Id = id;
                Participant = participant;
                CallbackAssembly = callbackAssembly;
                AuthorizationGeneration = authorizationGeneration;
            }

            internal string PackageId { get; }
            internal string Id { get; }
            internal IStorySaveParticipant Participant { get; }
            internal Assembly CallbackAssembly { get; }
            internal int AuthorizationGeneration { get; set; }
        }

        private sealed class WeaponComponentParticipant
        {
            internal WeaponComponentParticipant(
                string packageId, string id,
                IWeaponComponentLifecycleParticipant participant,
                Assembly callbackAssembly, int authorizationGeneration)
            {
                PackageId = packageId;
                Id = id;
                Participant = participant;
                CallbackAssembly = callbackAssembly;
                AuthorizationGeneration = authorizationGeneration;
            }

            internal string PackageId { get; }
            internal string Id { get; }
            internal IWeaponComponentLifecycleParticipant Participant
                { get; }
            internal Assembly CallbackAssembly { get; }
            internal int AuthorizationGeneration { get; set; }
        }
    }

    /// <summary>Core save monitor; content packages subscribe through the API.</summary>
    public sealed class ExtensionRuntimeHost : Script
    {
        private DateTime _lastStorySaveWriteUtc;

        public ExtensionRuntimeHost()
        {
            _lastStorySaveWriteUtc = StorySaveMonitor.LatestStorySaveWriteUtc();
            Interval = 500;
            Tick += OnTick;
            Aborted += OnAborted;
        }

        private void OnTick(object sender, EventArgs args)
        {
            DateTime latest = StorySaveMonitor.LatestStorySaveWriteUtc();
            if (latest <= _lastStorySaveWriteUtc) return;
            _lastStorySaveWriteUtc = latest;
            Allin1ExtensionApi.NotifyStorySave(latest, "story_save_written");
        }

        private void OnAborted(object sender, EventArgs args)
        {
            DateTime latest = StorySaveMonitor.LatestStorySaveWriteUtc();
            if (latest > _lastStorySaveWriteUtc)
            {
                _lastStorySaveWriteUtc = latest;
                Allin1ExtensionApi.NotifyStorySave(
                    latest, "story_save_written_on_shutdown");
            }
            // Commit clears transactions included in the latest save. Discard
            // then clears anything still staged after that boundary. A hard
            // process exit naturally loses in-memory staging even if Aborted
            // cannot run.
            Allin1ExtensionApi.NotifySessionEnd(
                _lastStorySaveWriteUtc, "script_aborted");
        }
    }

    internal sealed class StorySaveScope
    {
        internal StorySaveScope(string profileDirectory)
        {
            ProfileDirectory = Path.GetFullPath(profileDirectory);
        }

        internal string ProfileDirectory { get; }

        internal DateTime LatestStorySaveWriteUtc()
        {
            return StorySaveMonitor.LatestStorySaveWriteUtc(ProfileDirectory);
        }
    }

    internal static class StorySaveMonitor
    {
        private static readonly object ScopeSync = new object();
        private static StorySaveScope _activeScope;

        internal static DateTime LatestStorySaveWriteUtc()
        {
            lock (ScopeSync)
            {
                if (_activeScope == null)
                {
                    string documents = Environment.GetFolderPath(
                        Environment.SpecialFolder.MyDocuments);
                    string scripts = Allin1ExtensionApi.ResolveScriptsDirectory(
                        Allin1ExtensionApi.ResolveAssemblySourcePath(
                            typeof(Allin1ExtensionApi).Assembly),
                        AppDomain.CurrentDomain.BaseDirectory);
                    _activeScope = CreateActiveScope(documents, scripts);
                }
                return _activeScope?.LatestStorySaveWriteUtc() ??
                    DateTime.MinValue;
            }
        }

        internal static StorySaveScope CreateActiveScope(
            string documentsDirectory, string scriptsDirectory)
        {
            string gameFolder = SaveGameFolderForScripts(scriptsDirectory);
            string profiles = Path.Combine(
                documentsDirectory, "Rockstar Games", gameFolder, "Profiles");
            if (!Directory.Exists(profiles)) return null;

            string selected = null;
            DateTime latest = DateTime.MinValue;
            try
            {
                foreach (string profile in Directory.EnumerateDirectories(
                    profiles, "*", SearchOption.TopDirectoryOnly))
                {
                    DateTime candidate = LatestStorySaveWriteUtc(profile);
                    if (candidate > latest)
                    {
                        latest = candidate;
                        selected = profile;
                    }
                }
            }
            catch (IOException) { return null; }
            catch (UnauthorizedAccessException) { return null; }
            return selected == null ? null : new StorySaveScope(selected);
        }

        internal static string SaveGameFolderForScripts(string scriptsDirectory)
        {
            string scripts = Path.GetFullPath(scriptsDirectory).TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string gameRoot = Directory.GetParent(scripts)?.FullName ?? scripts;
            if (File.Exists(Path.Combine(gameRoot, "GTA5_Enhanced.exe")))
                return "GTAV Enhanced";
            if (File.Exists(Path.Combine(gameRoot, "GTA5.exe")))
                return "GTA V";
            return gameRoot.IndexOf(
                "Enhanced", StringComparison.OrdinalIgnoreCase) >= 0
                ? "GTAV Enhanced" : "GTA V";
        }

        internal static DateTime LatestStorySaveWriteUtc(
            string profileDirectory)
        {
            if (string.IsNullOrWhiteSpace(profileDirectory) ||
                !Directory.Exists(profileDirectory))
                return DateTime.MinValue;
            DateTime latest = DateTime.MinValue;
            try
            {
                foreach (string path in Directory.EnumerateFiles(
                    profileDirectory, "SGTA5*", SearchOption.TopDirectoryOnly))
                {
                    if (Path.GetExtension(path).Length != 0) continue;
                    DateTime write = File.GetLastWriteTimeUtc(path);
                    if (write > latest) latest = write;
                }
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
            return latest;
        }
    }

    internal sealed class ExtensionRegistration : IDisposable
    {
        private Action _dispose;

        internal ExtensionRegistration(Action dispose)
        {
            _dispose = dispose;
        }

        public void Dispose()
        {
            Action dispose = _dispose;
            _dispose = null;
            dispose?.Invoke();
        }
    }

    internal sealed class RuntimeGbaySection
    {
        internal string Id;
        internal string Label;
        internal string Description;
        internal string Route;
        internal int Order;
    }

    internal sealed class RuntimeFileAuthorization
    {
        internal string RelativePath;
        internal string Sha256;
    }

    internal sealed class RuntimeGbayCatalog
    {
        internal string Id;
        internal string Kind;
        internal string Source;
        internal string SourcePath;
        internal string Sha256;

        internal bool IsCurrent()
        {
            try
            {
                if (!File.Exists(SourcePath)) return false;
                return string.IsNullOrEmpty(Sha256) || string.Equals(
                    RuntimeExtensionRegistry.Sha256(SourcePath), Sha256,
                    StringComparison.OrdinalIgnoreCase);
            }
            catch (IOException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
            catch (CryptographicException) { return false; }
        }
    }

    internal sealed class RuntimeExtensionPackage
    {
        internal string Id;
        internal string Name;
        internal string Version;
        internal string Source;
        internal bool Enabled;
        internal HashSet<string> Capabilities =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        internal Dictionary<string, object> Settings =
            new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
        internal List<RuntimeGbaySection> Sections = new List<RuntimeGbaySection>();
        internal List<RuntimeGbayCatalog> Catalogs = new List<RuntimeGbayCatalog>();
        internal List<RuntimeFileAuthorization> RuntimeFiles =
            new List<RuntimeFileAuthorization>();

        internal bool AuthorizesAssembly(Assembly assembly, string scriptsDirectory)
        {
            string location = Allin1ExtensionApi.ResolveAssemblySourcePath(assembly);
            if (string.IsNullOrWhiteSpace(location)) return false;
            if (string.Equals(Source, "built-in", StringComparison.OrdinalIgnoreCase))
            {
                return assembly == typeof(Allin1ExtensionApi).Assembly;
            }
            string gameRoot = Directory.GetParent(
                Path.GetFullPath(scriptsDirectory).TrimEnd(
                    Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))?.FullName;
            if (string.IsNullOrEmpty(gameRoot)) return false;
            foreach (RuntimeFileAuthorization runtimeFile in RuntimeFiles)
            {
                string expectedPath = RuntimeExtensionRegistry.ContainedRuntimePath(
                    gameRoot, runtimeFile.RelativePath);
                if (expectedPath == null || !string.Equals(
                        expectedPath, location, StringComparison.OrdinalIgnoreCase))
                    continue;
                try
                {
                    if (!File.Exists(location)) return false;
                    return string.Equals(
                        RuntimeExtensionRegistry.Sha256(location), runtimeFile.Sha256,
                        StringComparison.OrdinalIgnoreCase);
                }
                catch (IOException) { return false; }
                catch (UnauthorizedAccessException) { return false; }
                catch (CryptographicException) { return false; }
            }
            return false;
        }
    }

    internal sealed class RuntimeExtensionRegistry
    {
        private static readonly Regex Identifier = new Regex(
            "^[a-z0-9][a-z0-9._-]{1,95}$", RegexOptions.CultureInvariant);
        private static readonly Regex Route = new Regex(
            "^[a-z][a-z0-9._:-]{0,95}$", RegexOptions.CultureInvariant);
        private static readonly Regex Digest = new Regex(
            "^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
        private static readonly Regex SettingKey = new Regex(
            "^[a-z][a-z0-9_-]{0,63}$", RegexOptions.CultureInvariant);
        private static readonly HashSet<string> CatalogKinds =
            new HashSet<string>(new[] {
                "vehicle", "weapon", "gear", "service", "property"
            }, StringComparer.OrdinalIgnoreCase);

        internal bool Present;
        internal bool Valid;
        internal string Error;
        internal string ScriptsDirectory;
        internal Dictionary<string, RuntimeExtensionPackage> Packages =
            new Dictionary<string, RuntimeExtensionPackage>(
                StringComparer.OrdinalIgnoreCase);

        internal static bool IsSafeId(string value)
        {
            return value != null && Identifier.IsMatch(value.Trim().ToLowerInvariant());
        }

        internal bool IsEnabled(string packageId)
        {
            RuntimeExtensionPackage package;
            if (!Packages.TryGetValue(packageId, out package) || !package.Enabled)
                return false;
            if (IsOfficialId(packageId) && Present)
            {
                return string.Equals(
                    package.Source, "built-in", StringComparison.OrdinalIgnoreCase);
            }
            return true;
        }

        private static bool IsOfficialId(string packageId)
        {
            return string.Equals(packageId,
                       Allin1ExtensionApi.OnlineContentPackageId,
                       StringComparison.OrdinalIgnoreCase) ||
                string.Equals(packageId,
                       Allin1ExtensionApi.ExperimentalGameplayPackageId,
                       StringComparison.OrdinalIgnoreCase);
        }

        internal static RuntimeExtensionRegistry Load(
            string path, string scriptsDirectory)
        {
            if (!File.Exists(path)) return Legacy(scriptsDirectory);
            return Parse(File.ReadAllText(path), scriptsDirectory);
        }

        internal static RuntimeExtensionRegistry Parse(
            string json, string scriptsDirectory)
        {
            object rootValue = PortableJsonParser.Parse(json);
            Dictionary<string, object> root = AsObject(rootValue, "registry");
            if (Integer(root, "schema_version") != 1 ||
                Integer(root, "api_version") != Allin1ExtensionApi.ApiVersion)
                throw new InvalidDataException("Unsupported extension registry version");
            object[] extensions = AsArray(Value(root, "extensions"), "extensions");
            if (extensions.Length > 256)
                throw new InvalidDataException("Extension registry exceeds its package limit");
            var registry = new RuntimeExtensionRegistry {
                Present = true,
                Valid = true,
                ScriptsDirectory = Path.GetFullPath(scriptsDirectory),
            };
            foreach (object extensionValue in extensions)
            {
                Dictionary<string, object> extension = AsObject(
                    extensionValue, "extension");
                if (Integer(extension, "schema_version") != 1 ||
                    Integer(extension, "api_version") !=
                        Allin1ExtensionApi.ApiVersion)
                    throw new InvalidDataException(
                        "Unsupported content extension version");
                string id = Text(extension, "id").ToLowerInvariant();
                if (!IsSafeId(id) || registry.Packages.ContainsKey(id))
                    throw new InvalidDataException("Invalid or duplicate extension id: " + id);
                var package = new RuntimeExtensionPackage {
                    Id = id,
                    Name = OptionalText(extension, "name", id),
                    Version = OptionalText(extension, "version", "unknown"),
                    Source = Text(extension, "source").ToLowerInvariant(),
                    Enabled = Boolean(extension, "enabled"),
                };
                if (package.Source != "built-in" && package.Source != "package")
                    throw new InvalidDataException(
                        "Invalid extension source: " + package.Source);
                if (!string.IsNullOrWhiteSpace(
                        OptionalText(extension, "blocked_reason", "")))
                    package.Enabled = false;
                foreach (object capability in AsOptionalArray(
                    extension, "capabilities"))
                {
                    string value = Convert.ToString(
                        capability, CultureInfo.InvariantCulture)?.Trim();
                    if (!IsSafeId(value))
                        throw new InvalidDataException("Invalid extension capability");
                    package.Capabilities.Add(value);
                }
                Dictionary<string, object> settings = AsOptionalObject(
                    extension, "settings");
                foreach (KeyValuePair<string, object> setting in settings)
                {
                    if (!SettingKey.IsMatch(setting.Key))
                        throw new InvalidDataException("Invalid extension setting key");
                    package.Settings[setting.Key] = setting.Value;
                }
                Dictionary<string, object> gbay = AsOptionalObject(extension, "gbay");
                var sectionIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                var sectionRoutes = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (object sectionValue in AsOptionalArray(gbay, "sections"))
                {
                    Dictionary<string, object> section = AsObject(
                        sectionValue, "GBAY section");
                    string route = Text(section, "route");
                    string sectionId = Text(section, "id").ToLowerInvariant();
                    if (!IsSafeId(sectionId) || !sectionIds.Add(sectionId) ||
                        !Route.IsMatch(route) || !sectionRoutes.Add(route))
                        throw new InvalidDataException("Invalid GBAY route: " + route);
                    package.Sections.Add(new RuntimeGbaySection {
                        Id = sectionId,
                        Label = Text(section, "label"),
                        Description = OptionalText(section, "description", ""),
                        Route = route,
                        Order = OptionalInteger(section, "order", 100),
                    });
                }
                var catalogIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                string gameRoot = Directory.GetParent(
                    registry.ScriptsDirectory.TrimEnd(
                        Path.DirectorySeparatorChar,
                        Path.AltDirectorySeparatorChar))?.FullName;
                foreach (object catalogValue in AsOptionalArray(gbay, "catalogs"))
                {
                    Dictionary<string, object> catalog = AsObject(
                        catalogValue, "GBAY catalog");
                    string catalogId = Text(catalog, "id").ToLowerInvariant();
                    string kind = Text(catalog, "kind").ToLowerInvariant();
                    string source = Text(catalog, "source").Replace('\\', '/');
                    string sourcePath = ContainedCatalogPath(gameRoot, source);
                    if (!IsSafeId(catalogId) || !catalogIds.Add(catalogId) ||
                        !CatalogKinds.Contains(kind) ||
                        sourcePath == null)
                        throw new InvalidDataException("Invalid GBAY catalog: " + catalogId);
                    package.Catalogs.Add(new RuntimeGbayCatalog {
                        Id = catalogId,
                        Kind = kind,
                        Source = source,
                        SourcePath = sourcePath,
                    });
                }
                var catalogFiles = new Dictionary<string, RuntimeFileAuthorization>(
                    StringComparer.OrdinalIgnoreCase);
                foreach (object fileValue in AsOptionalArray(
                    extension, "catalog_files"))
                {
                    Dictionary<string, object> file = AsObject(
                        fileValue, "catalog file");
                    string relative = Text(file, "path").Replace('\\', '/');
                    string sha256 = Text(file, "sha256").ToLowerInvariant();
                    if (ContainedCatalogPath(gameRoot, relative) == null ||
                        !Digest.IsMatch(sha256) || catalogFiles.ContainsKey(relative))
                        throw new InvalidDataException(
                            "Invalid catalog file authorization");
                    catalogFiles.Add(relative, new RuntimeFileAuthorization {
                        RelativePath = relative,
                        Sha256 = sha256,
                    });
                }
                foreach (RuntimeGbayCatalog catalog in package.Catalogs)
                {
                    RuntimeFileAuthorization authorization;
                    if (catalogFiles.TryGetValue(catalog.Source, out authorization))
                    {
                        catalog.Sha256 = authorization.Sha256;
                        catalogFiles.Remove(catalog.Source);
                    }
                    else if (string.Equals(
                        package.Source, "package", StringComparison.OrdinalIgnoreCase))
                    {
                        throw new InvalidDataException(
                            "Package catalog lacks receipt authorization: " +
                            catalog.Source);
                    }
                }
                if (catalogFiles.Count != 0)
                    throw new InvalidDataException(
                        "Catalog receipt does not match a declared GBAY catalog");
                var runtimePaths = new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase);
                foreach (object fileValue in AsOptionalArray(
                    extension, "runtime_files"))
                {
                    Dictionary<string, object> file = AsObject(
                        fileValue, "runtime file");
                    string relative = Text(file, "path").Replace('\\', '/');
                    string sha256 = Text(file, "sha256").ToLowerInvariant();
                    if (!relative.EndsWith(".dll", StringComparison.OrdinalIgnoreCase) ||
                        !runtimePaths.Add(relative) || ContainedRuntimePath(
                            Directory.GetParent(registry.ScriptsDirectory.TrimEnd(
                                Path.DirectorySeparatorChar,
                                Path.AltDirectorySeparatorChar))?.FullName,
                            relative) == null || !Digest.IsMatch(sha256))
                        throw new InvalidDataException("Invalid runtime file authorization");
                    package.RuntimeFiles.Add(new RuntimeFileAuthorization {
                        RelativePath = relative, Sha256 = sha256,
                    });
                }
                registry.Packages.Add(id, package);
            }
            return registry;
        }

        internal static RuntimeExtensionRegistry Legacy(string scriptsDirectory)
        {
            var registry = new RuntimeExtensionRegistry {
                Present = false,
                Valid = true,
                ScriptsDirectory = Path.GetFullPath(scriptsDirectory),
            };
            registry.Packages.Add(
                Allin1ExtensionApi.OnlineContentPackageId,
                new RuntimeExtensionPackage {
                    Id = Allin1ExtensionApi.OnlineContentPackageId,
                    Name = "ALLIN1 Online Content", Version = "legacy",
                    Source = "legacy", Enabled = true,
                });
            registry.Packages.Add(
                Allin1ExtensionApi.ExperimentalGameplayPackageId,
                new RuntimeExtensionPackage {
                    Id = Allin1ExtensionApi.ExperimentalGameplayPackageId,
                    Name = "ALLIN1 Experimental Gameplay", Version = "legacy",
                    Source = "legacy", Enabled = true,
                });
            return registry;
        }

        internal static RuntimeExtensionRegistry Invalid(
            string scriptsDirectory, string error)
        {
            return new RuntimeExtensionRegistry {
                Present = true,
                Valid = false,
                Error = error,
                ScriptsDirectory = Path.GetFullPath(scriptsDirectory),
            };
        }

        internal static string ContainedRuntimePath(
            string gameRoot, string relative)
        {
            if (string.IsNullOrWhiteSpace(gameRoot) ||
                string.IsNullOrWhiteSpace(relative)) return null;
            string normalized = relative.Replace('\\', '/');
            string[] parts = normalized.Split('/');
            if (parts.Length < 2 ||
                !string.Equals(parts[0], "scripts", StringComparison.OrdinalIgnoreCase) ||
                parts.Any(part => string.IsNullOrWhiteSpace(part) || part == "." ||
                    part == ".." || part.Contains(":")))
                return null;
            string root = Path.GetFullPath(gameRoot).TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) +
                Path.DirectorySeparatorChar;
            string candidate = Path.GetFullPath(Path.Combine(
                root, Path.Combine(parts)));
            return candidate.StartsWith(root, StringComparison.OrdinalIgnoreCase)
                ? candidate : null;
        }

        internal static string ContainedCatalogPath(
            string gameRoot, string relative)
        {
            if (string.IsNullOrWhiteSpace(gameRoot) ||
                string.IsNullOrWhiteSpace(relative)) return null;
            string normalized = relative.Replace('\\', '/');
            string[] parts = normalized.Split('/');
            if (parts.Length == 0 ||
                parts.Any(part => string.IsNullOrWhiteSpace(part) || part == "." ||
                    part == ".." || part.Contains(":")) ||
                !normalized.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
                return null;
            string root = Path.GetFullPath(gameRoot).TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) +
                Path.DirectorySeparatorChar;
            string candidate = Path.GetFullPath(Path.Combine(
                root, Path.Combine(parts)));
            return candidate.StartsWith(root, StringComparison.OrdinalIgnoreCase)
                ? candidate : null;
        }

        internal static string Sha256(string path)
        {
            using (var stream = File.OpenRead(path))
            using (var digest = SHA256.Create())
            {
                return string.Concat(digest.ComputeHash(stream)
                    .Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
            }
        }

        private static object Value(Dictionary<string, object> data, string key)
        {
            object value;
            if (!data.TryGetValue(key, out value))
                throw new InvalidDataException("Missing registry field: " + key);
            return value;
        }

        private static string Text(Dictionary<string, object> data, string key)
        {
            object value = Value(data, key);
            string text = value as string;
            if (string.IsNullOrWhiteSpace(text))
                throw new InvalidDataException("Invalid registry text field: " + key);
            return text.Trim();
        }

        private static string OptionalText(
            Dictionary<string, object> data, string key, string fallback)
        {
            object value;
            if (!data.TryGetValue(key, out value) || value == null) return fallback;
            string text = value as string;
            if (text == null)
                throw new InvalidDataException("Invalid registry text field: " + key);
            return text.Trim();
        }

        private static int Integer(Dictionary<string, object> data, string key)
        {
            return Convert.ToInt32(Value(data, key), CultureInfo.InvariantCulture);
        }

        private static int OptionalInteger(
            Dictionary<string, object> data, string key, int fallback)
        {
            object value;
            return data.TryGetValue(key, out value)
                ? Convert.ToInt32(value, CultureInfo.InvariantCulture) : fallback;
        }

        private static bool Boolean(Dictionary<string, object> data, string key)
        {
            object value = Value(data, key);
            if (!(value is bool))
                throw new InvalidDataException("Invalid registry boolean field: " + key);
            return (bool)value;
        }

        private static Dictionary<string, object> AsObject(object value, string label)
        {
            var result = value as Dictionary<string, object>;
            if (result == null)
                throw new InvalidDataException(label + " must be an object");
            return result;
        }

        private static Dictionary<string, object> AsOptionalObject(
            Dictionary<string, object> data, string key)
        {
            object value;
            if (!data.TryGetValue(key, out value) || value == null)
                return new Dictionary<string, object>();
            return AsObject(value, key);
        }

        private static object[] AsArray(object value, string label)
        {
            object[] array = value as object[];
            if (array != null) return array;
            var list = value as ArrayList;
            if (list != null) return list.ToArray();
            throw new InvalidDataException(label + " must be an array");
        }

        private static object[] AsOptionalArray(
            Dictionary<string, object> data, string key)
        {
            object value;
            return data.TryGetValue(key, out value) && value != null
                ? AsArray(value, key) : new object[0];
        }
    }
}
