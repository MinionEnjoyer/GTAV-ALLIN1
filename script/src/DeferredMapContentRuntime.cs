// DeferredMapContentRuntime.cs -- scoped loading for ALLIN1 map DLC groups.
//
// Official garages are backed by Rockstar DLC archives that the installer and
// SDK map detector verify independently. A tiny metadata-only bridge exposes
// one fixed content group per ALLIN1 property. Verified stock bridges execute
// only under the owned black entry transition and remain session-resident
// after success. Failed new acquisitions roll back. Global Online map groups
// are never enabled.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal enum DeferredMapProperty
    {
        Grapeseed,
        Yacht,
        Davis,
        Harmony,
        Paleto,
        GarmentFactory,
    }

    internal static class DeferredMapContentGroups
    {
        internal const string Grapeseed = "ALLIN1_MAP_GRAPESEED";
        internal const string Yacht = "ALLIN1_MAP_YACHT";
        internal const string Davis = "ALLIN1_MAP_DAVIS";
        internal const string Harmony = "ALLIN1_MAP_HARMONY";
        internal const string Paleto = "ALLIN1_MAP_PALETO";
        internal const string GarmentFactory = "ALLIN1_MAP_GARMENT_FACTORY";

        internal static string Resolve(DeferredMapProperty property)
        {
            switch (property)
            {
                case DeferredMapProperty.Grapeseed: return Grapeseed;
                case DeferredMapProperty.Yacht: return Yacht;
                case DeferredMapProperty.Davis: return Davis;
                case DeferredMapProperty.Harmony: return Harmony;
                case DeferredMapProperty.Paleto: return Paleto;
                case DeferredMapProperty.GarmentFactory: return GarmentFactory;
                default: return null;
            }
        }

        // Generic official-map descriptors stay interaction-scoped. The
        // verified Davis Phase-B entry path supplies its session-resident
        // override explicitly, so older/proximity routes cannot inherit it.
        internal static bool KeepResident(DeferredMapProperty property) =>
            false;
    }

    internal sealed class DeferredMapContentDescriptor
    {
        private readonly string _propertyKey;

        internal DeferredMapProperty Property { get; }
        internal string PropertyKey => _propertyKey;
        internal string GroupName { get; }
        internal string[] Ipls { get; }
        internal bool KeepResident { get; }
        internal bool GroupMutationAllowed { get; }
        internal string GroupMutationBlockReason { get; }

        internal DeferredMapContentDescriptor(
            DeferredMapProperty property, IEnumerable<string> ipls,
            bool? keepResident = null, bool groupMutationAllowed = true,
            string groupMutationBlockReason = "")
        {
            Property = property;
            _propertyKey = property.ToString().ToLowerInvariant();
            GroupName = DeferredMapContentGroups.Resolve(property);
            Ipls = (ipls ?? Enumerable.Empty<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
            KeepResident = keepResident ??
                DeferredMapContentGroups.KeepResident(property);
            GroupMutationAllowed = groupMutationAllowed;
            GroupMutationBlockReason = groupMutationBlockReason ?? string.Empty;
        }

        internal DeferredMapContentDescriptor(
            DeferredMapProperty property, string fixedGroupName,
            IEnumerable<string> ipls, bool keepResident,
            bool groupMutationAllowed = true,
            string groupMutationBlockReason = "")
        {
            Property = property;
            _propertyKey = property.ToString().ToLowerInvariant();
            GroupName = (fixedGroupName ?? string.Empty).Trim();
            Ipls = (ipls ?? Enumerable.Empty<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
            KeepResident = keepResident;
            GroupMutationAllowed = groupMutationAllowed;
            GroupMutationBlockReason = groupMutationBlockReason ?? string.Empty;
        }

        // Custom map packages use the same reference-counted IPL lifecycle as
        // built-in properties, but supply their own stable lease key.  The
        // caller must use registered IPL activation; this descriptor does not
        // authorize executing arbitrary content-change groups.
        internal DeferredMapContentDescriptor(
            string propertyKey, string groupName, IEnumerable<string> ipls,
            bool keepResident = false)
        {
            Property = default;
            _propertyKey = (propertyKey ?? string.Empty).Trim();
            GroupName = (groupName ?? string.Empty).Trim();
            Ipls = (ipls ?? Enumerable.Empty<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();
            KeepResident = keepResident;
            GroupMutationAllowed = true;
            GroupMutationBlockReason = string.Empty;
        }

        internal bool IsValid =>
            !string.IsNullOrWhiteSpace(GroupName) && Ipls.Length > 0;
    }

    internal enum DeferredMapContentOutcome
    {
        Activated,
        AlreadyActive,
        ReferenceAcquired,
        FallbackActivated,
        KeptResident,
        Released,
        NotAcquired,
        UnsafeRuntimeState,
        MapPackUnavailable,
        InvalidDescriptor,
        TimedOut,
        NativeFailure,
    }

    internal readonly struct DeferredMapContentResult
    {
        internal DeferredMapContentOutcome Outcome { get; }
        internal string Detail { get; }
        internal int ElapsedMilliseconds { get; }
        internal bool Success =>
            Outcome == DeferredMapContentOutcome.Activated ||
            Outcome == DeferredMapContentOutcome.AlreadyActive ||
            Outcome == DeferredMapContentOutcome.ReferenceAcquired ||
            Outcome == DeferredMapContentOutcome.FallbackActivated ||
            Outcome == DeferredMapContentOutcome.KeptResident ||
            Outcome == DeferredMapContentOutcome.Released;
        internal bool ReleaseComplete =>
            Outcome == DeferredMapContentOutcome.Released ||
            Outcome == DeferredMapContentOutcome.NotAcquired;

        internal DeferredMapContentResult(
            DeferredMapContentOutcome outcome, string detail,
            int elapsedMilliseconds)
        {
            Outcome = outcome;
            Detail = detail ?? string.Empty;
            ElapsedMilliseconds = Math.Max(0, elapsedMilliseconds);
        }
    }

    /// <summary>
    /// Deterministic retry policy for the official map-backed garages.  A
    /// failed map-pack lookup is immediate, so repeated Context presses used
    /// to restart the same transition and emit the same warning/log entry on
    /// every press.  Loading-related failures are also held briefly, while
    /// unrelated policy failures remain immediately retryable.
    /// </summary>
    internal static class OfficialGarageMapEntryRetryPolicy
    {
        internal const int CooldownMilliseconds = 5000;

        internal static bool ShouldDebounce(
            DeferredMapContentResult result)
        {
            if (result.Outcome ==
                    DeferredMapContentOutcome.MapPackUnavailable ||
                result.Outcome == DeferredMapContentOutcome.TimedOut)
                return true;

            if (result.Outcome !=
                DeferredMapContentOutcome.UnsafeRuntimeState) return false;

            string detail = result.Detail ?? string.Empty;
            return detail.StartsWith("game_loading",
                       StringComparison.OrdinalIgnoreCase) ||
                   detail.StartsWith("player_unavailable",
                       StringComparison.OrdinalIgnoreCase) ||
                   detail.StartsWith("story_runtime_settling",
                       StringComparison.OrdinalIgnoreCase);
        }

        internal static int RemainingMilliseconds(
            int nowMilliseconds, int deniedAtMilliseconds,
            int cooldownMilliseconds = CooldownMilliseconds)
        {
            int duration = Math.Max(0, cooldownMilliseconds);
            uint elapsed = unchecked((uint)(
                nowMilliseconds - deniedAtMilliseconds));
            return elapsed >= (uint)duration
                ? 0
                : duration - (int)elapsed;
        }
    }

    internal sealed class OfficialGarageMapEntryCooldown
    {
        private readonly Dictionary<DeferredMapProperty, int> _deniedAt =
            new Dictionary<DeferredMapProperty, int>();

        internal bool TryBegin(
            DeferredMapProperty property, int nowMilliseconds,
            out int remainingMilliseconds)
        {
            if (!_deniedAt.TryGetValue(property, out int deniedAt))
            {
                remainingMilliseconds = 0;
                return true;
            }

            remainingMilliseconds =
                OfficialGarageMapEntryRetryPolicy.RemainingMilliseconds(
                    nowMilliseconds, deniedAt);
            if (remainingMilliseconds > 0) return false;

            _deniedAt.Remove(property);
            return true;
        }

        internal void Observe(
            DeferredMapProperty property, DeferredMapContentResult result,
            int nowMilliseconds)
        {
            if (OfficialGarageMapEntryRetryPolicy.ShouldDebounce(result))
                _deniedAt[property] = nowMilliseconds;
            else
                _deniedAt.Remove(property);
        }
    }

    internal interface IDeferredMapContentBridge
    {
        string Edition { get; }
        int MonotonicMilliseconds { get; }
        bool IsRuntimeSafe(out string reason);
        bool IsScreenFadedOut();
        bool IsDlcPresent(string packName);
        uint GenerateHash(string value);
        void ExecuteGroup(uint groupHash);
        void RevertGroup(uint groupHash);
        void RequestIpl(string ipl);
        void RemoveIpl(string ipl);
        bool IsIplActive(string ipl);
        void Yield(int milliseconds);
        bool TryActivateFallback(string[] ipls, int timeoutMs);
    }

    internal interface IDeferredMapContentLogger
    {
        void Info(string message, IDictionary<string, object> fields);
        void Warn(string message, IDictionary<string, object> fields);
        void Error(string message, Exception exception,
            IDictionary<string, object> fields);
    }

    internal sealed class DeferredMapContentLeaseManager
    {
        private const int MaximumTimeoutMs = 30000;
        private const int PollIntervalMs = 50;
        private const int RuntimeSafetyRetryTimeoutMs = 15000;

        private sealed class Lease
        {
            internal DeferredMapContentDescriptor Descriptor;
            internal int References;
            internal bool OwnsGroup;
            internal bool UsesFallback;
            internal bool RegisteredIplOnly;
            internal bool CleanupPending;
            internal HashSet<string> PreexistingIpls;
        }

        private readonly IDeferredMapContentBridge _bridge;
        private readonly IDeferredMapContentLogger _log;
        private readonly object _leaseGate = new object();
        private readonly Dictionary<string, Lease> _leases =
            new Dictionary<string, Lease>(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> _pendingRegisteredIplActivations =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> _pendingRegisteredIplReleases =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        internal DeferredMapContentLeaseManager(
            IDeferredMapContentBridge bridge,
            IDeferredMapContentLogger logger)
        {
            _bridge = bridge ?? throw new ArgumentNullException(nameof(bridge));
            _log = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        internal DeferredMapContentResult Acquire(
            DeferredMapContentDescriptor descriptor,
            int timeoutMs = 8000, bool allowFallback = true,
            bool executeDeferredGroup = true,
            bool blackTransitionVerified = false)
        {
            // The isolated startup canary never owns a content group. Keep its
            // potentially yielding safety/IPL polling outside _leaseGate so a
            // second SHVDN script cannot block the scheduler on this monitor.
            if (!executeDeferredGroup && !allowFallback)
                return AcquireRegisteredIpl(descriptor, timeoutMs);
            lock (_leaseGate)
                return AcquireCore(descriptor, timeoutMs, allowFallback,
                    executeDeferredGroup, blackTransitionVerified);
        }

        internal DeferredMapContentResult AcquireRegisteredIpl(
            DeferredMapContentDescriptor descriptor, int timeoutMs = 8000)
        {
            int startedAt = _bridge.MonotonicMilliseconds;
            timeoutMs = NormalizeTimeout(timeoutMs);
            IDictionary<string, object> fields = Fields(descriptor, timeoutMs);
            fields["edition"] = _bridge.Edition;
            fields["fallback_allowed"] = false;
            fields["deferred_group"] = false;
            fields["activation_route"] = "startup_registered_ipl";
            _log.Info("activation_requested", fields);

            if (descriptor == null || !descriptor.IsValid)
            {
                _log.Warn("activation_rejected_invalid_descriptor", fields);
                return Result(DeferredMapContentOutcome.InvalidDescriptor,
                    "A registered property and at least one IPL are required.",
                    startedAt);
            }
            if (!descriptor.GroupMutationAllowed)
            {
                fields["reason"] = descriptor.GroupMutationBlockReason;
                _log.Warn("activation_blocked_unsafe_official_closure", fields);
                return Result(DeferredMapContentOutcome.UnsafeRuntimeState,
                    descriptor.GroupMutationBlockReason, startedAt);
            }

            lock (_leaseGate)
            {
                if (IsRegisteredIplOperationPending(descriptor.GroupName))
                    return RegisteredIplOperationPending(
                        "startup_ipl_activation_in_progress", fields,
                        startedAt);
                if (_leases.TryGetValue(descriptor.GroupName,
                        out Lease current))
                {
                    if (!SameIpls(current.Descriptor.Ipls, descriptor.Ipls))
                    {
                        fields["reason"] =
                            "descriptor_changed_while_acquired";
                        _log.Warn(
                            "activation_rejected_descriptor_mismatch", fields);
                        return Result(
                            DeferredMapContentOutcome.InvalidDescriptor,
                            "The active group was requested with a different " +
                            "IPL set.", startedAt);
                    }
                    current.References++;
                    fields["reference_count"] = current.References;
                    _log.Info("activation_reference_acquired", fields);
                    return Result(
                        DeferredMapContentOutcome.ReferenceAcquired,
                        "The property group was already leased.", startedAt);
                }
                _pendingRegisteredIplActivations.Add(descriptor.GroupName);
            }

            HashSet<string> preexisting = null;
            try
            {
                if (!_bridge.IsRuntimeSafe(out string unsafeReason))
                {
                    fields["reason"] = unsafeReason;
                    _log.Info("activation_queued_unsafe_runtime", fields);
                    int runtimeWaitStartedAt = _bridge.MonotonicMilliseconds;
                    if (!WaitForRuntimeSafe(
                            RuntimeSafetyRetryTimeoutMs, out unsafeReason))
                    {
                        fields["reason"] = unsafeReason;
                        fields["runtime_wait_ms"] =
                            Elapsed(runtimeWaitStartedAt);
                        _log.Warn("activation_deferred_unsafe_runtime", fields);
                        return Result(
                            DeferredMapContentOutcome.UnsafeRuntimeState,
                            unsafeReason, startedAt);
                    }
                    fields["runtime_wait_ms"] =
                        Elapsed(runtimeWaitStartedAt);
                    _log.Info("activation_runtime_ready_after_queue", fields);
                }

                int activationStartedAt = _bridge.MonotonicMilliseconds;
                preexisting = new HashSet<string>(
                    descriptor.Ipls.Where(IsIplActiveSafely),
                    StringComparer.OrdinalIgnoreCase);
                fields["preexisting_ipls"] = preexisting.Count;
                if (preexisting.Count == descriptor.Ipls.Length)
                {
                    FinalizeRegisteredIplLease(descriptor, preexisting);
                    _log.Info("activation_already_ready", fields);
                    return Result(DeferredMapContentOutcome.AlreadyActive,
                        "Every required IPL was already active; no group was " +
                        "executed.", startedAt);
                }

                _log.Info("registered_ipl_activation_requested", fields);
                if (WaitForIpls(descriptor.Ipls, true, timeoutMs,
                        activationStartedAt))
                {
                    FinalizeRegisteredIplLease(descriptor, preexisting);
                    fields["elapsed_ms"] = Elapsed(startedAt);
                    _log.Info("registered_ipl_activation_ready", fields);
                    return Result(DeferredMapContentOutcome.Activated,
                        "The startup-registered property IPLs are active.",
                        startedAt);
                }

                RemoveOwnedIpls(descriptor, preexisting);
                fields["elapsed_ms"] = Elapsed(startedAt);
                _log.Warn("registered_ipl_activation_timed_out", fields);
                return Result(DeferredMapContentOutcome.TimedOut,
                    "The registered property IPLs did not become active.",
                    startedAt);
            }
            catch (Exception ex)
            {
                try
                {
                    if (preexisting != null)
                        RemoveOwnedIpls(descriptor, preexisting);
                }
                catch
                {
                    // The primary native failure remains authoritative.
                }
                fields["elapsed_ms"] = Elapsed(startedAt);
                _log.Error("registered_ipl_activation_failed", ex, fields);
                return Result(DeferredMapContentOutcome.NativeFailure,
                    ex.Message, startedAt);
            }
            finally
            {
                lock (_leaseGate)
                    _pendingRegisteredIplActivations.Remove(
                        descriptor.GroupName);
            }
        }

        private DeferredMapContentResult AcquireCore(
            DeferredMapContentDescriptor descriptor,
            int timeoutMs, bool allowFallback,
            bool executeDeferredGroup, bool blackTransitionVerified)
        {
            int startedAt = _bridge.MonotonicMilliseconds;
            timeoutMs = NormalizeTimeout(timeoutMs);
            IDictionary<string, object> fields = Fields(descriptor, timeoutMs);
            fields["edition"] = _bridge.Edition;
            fields["fallback_allowed"] = allowFallback;
            fields["deferred_group"] = executeDeferredGroup;
            fields["black_transition_verified"] = blackTransitionVerified;
            _log.Info("activation_requested", fields);

            if (descriptor == null || !descriptor.IsValid)
            {
                _log.Warn("activation_rejected_invalid_descriptor", fields);
                return Result(DeferredMapContentOutcome.InvalidDescriptor,
                    "A registered property and at least one IPL are required.",
                    startedAt);
            }

            if (!descriptor.GroupMutationAllowed)
            {
                fields["reason"] = descriptor.GroupMutationBlockReason;
                _log.Warn("activation_blocked_unsafe_official_closure", fields);
                return Result(DeferredMapContentOutcome.UnsafeRuntimeState,
                    descriptor.GroupMutationBlockReason, startedAt);
            }

            if (IsRegisteredIplOperationPending(descriptor.GroupName))
                return RegisteredIplOperationPending(
                    "startup_ipl_operation_in_progress", fields, startedAt);

            if (_leases.TryGetValue(descriptor.GroupName, out Lease current))
            {
                if (!SameIpls(current.Descriptor.Ipls, descriptor.Ipls))
                {
                    fields["reason"] = "descriptor_changed_while_acquired";
                    _log.Warn("activation_rejected_descriptor_mismatch", fields);
                    return Result(DeferredMapContentOutcome.InvalidDescriptor,
                        "The active group was requested with a different IPL set.",
                        startedAt);
                }

                current.References++;
                fields["reference_count"] = current.References;
                _log.Info("activation_reference_acquired", fields);
                return Result(DeferredMapContentOutcome.ReferenceAcquired,
                    "The property group was already leased.", startedAt);
            }

            if (!blackTransitionVerified &&
                !_bridge.IsRuntimeSafe(out string unsafeReason))
            {
                fields["reason"] = unsafeReason;
                _log.Info("activation_queued_unsafe_runtime", fields);
                int runtimeWaitStartedAt = _bridge.MonotonicMilliseconds;
                if (!WaitForRuntimeSafe(
                    RuntimeSafetyRetryTimeoutMs, out unsafeReason))
                {
                    fields["reason"] = unsafeReason;
                    fields["runtime_wait_ms"] = Elapsed(runtimeWaitStartedAt);
                    _log.Warn("activation_deferred_unsafe_runtime", fields);
                    return Result(
                        DeferredMapContentOutcome.UnsafeRuntimeState,
                        unsafeReason, startedAt);
                }
                fields["runtime_wait_ms"] = Elapsed(runtimeWaitStartedAt);
                _log.Info("activation_runtime_ready_after_queue", fields);
            }

            // Runtime-settling time belongs to the safety queue, not the
            // caller's IPL activation budget. A request made during the first
            // few seconds of Story Mode still receives its complete content
            // timeout after the safety gate opens.
            int activationStartedAt = _bridge.MonotonicMilliseconds;

            var preexisting = new HashSet<string>(
                descriptor.Ipls.Where(IsIplActiveSafely),
                StringComparer.OrdinalIgnoreCase);
            fields["preexisting_ipls"] = preexisting.Count;

            if (preexisting.Count == descriptor.Ipls.Length)
            {
                _leases[descriptor.GroupName] = new Lease
                {
                    Descriptor = descriptor,
                    References = 1,
                    OwnsGroup = false,
                    UsesFallback = false,
                    PreexistingIpls = preexisting,
                };
                _log.Info("activation_already_ready", fields);
                return Result(DeferredMapContentOutcome.AlreadyActive,
                    "Every required IPL was already active; no group was executed.",
                    startedAt);
            }

            // Legacy v2 packages keep their content in GROUP_MAP/GROUP_MAP_SP.
            // They must go directly through that established IPL probe path;
            // attempting a custom v3 group first creates an avoidable timeout.
            if (!executeDeferredGroup)
            {
                if (!allowFallback)
                {
                    return TryRegisteredIplActivation(
                        descriptor, timeoutMs, startedAt,
                        activationStartedAt, preexisting, fields);
                }
                return TryFallback(descriptor, timeoutMs, startedAt,
                    preexisting, fields, "legacy_layout");
            }

            uint groupHash = _bridge.GenerateHash(descriptor.GroupName);
            fields["group_hash"] = "0x" + groupHash.ToString("X8");
            try
            {
                _bridge.ExecuteGroup(groupHash);
                _log.Info("activation_group_executed", fields);
                if (WaitForIpls(
                    descriptor.Ipls, true, timeoutMs, activationStartedAt))
                {
                    _leases[descriptor.GroupName] = new Lease
                    {
                        Descriptor = descriptor,
                        References = 1,
                        OwnsGroup = true,
                        UsesFallback = false,
                        PreexistingIpls = preexisting,
                    };
                    fields["elapsed_ms"] = Elapsed(startedAt);
                    _log.Info("activation_ready", fields);
                    return Result(DeferredMapContentOutcome.Activated,
                        "The property content group and IPLs are active.", startedAt);
                }

                fields["elapsed_ms"] = Elapsed(startedAt);
                _log.Warn("activation_timed_out", fields);
            }
            catch (Exception ex)
            {
                fields["elapsed_ms"] = Elapsed(startedAt);
                _log.Error("activation_native_failed", ex, fields);
                bool rollbackComplete = RollBackFailedActivation(
                    descriptor, groupHash, preexisting, fields);
                if (!rollbackComplete)
                    return Result(DeferredMapContentOutcome.NativeFailure,
                        ex.Message + "; rollback remains owned for retry.",
                        startedAt);
                if (!allowFallback)
                    return Result(DeferredMapContentOutcome.NativeFailure,
                        ex.Message, startedAt);
                return TryFallback(descriptor, timeoutMs, startedAt,
                    preexisting, fields, "native_failure");
            }

            bool timeoutRollbackComplete = RollBackFailedActivation(
                descriptor, groupHash, preexisting, fields);
            if (!timeoutRollbackComplete)
                return Result(DeferredMapContentOutcome.NativeFailure,
                    "Activation timed out and rollback remains owned for " +
                    "retry.", startedAt);
            if (allowFallback)
                return TryFallback(descriptor, timeoutMs, startedAt,
                    preexisting, fields, "activation_timeout");

            return Result(DeferredMapContentOutcome.TimedOut,
                "The property IPLs did not become active before the timeout.",
                startedAt);
        }

        internal DeferredMapContentResult Release(
            DeferredMapContentDescriptor descriptor,
            bool force = false, int timeoutMs = 1500)
        {
            bool registeredIplOnly;
            lock (_leaseGate)
            {
                registeredIplOnly = descriptor != null &&
                    !string.IsNullOrWhiteSpace(descriptor.GroupName) &&
                    _leases.TryGetValue(descriptor.GroupName, out Lease lease) &&
                    lease.RegisteredIplOnly;
            }
            if (registeredIplOnly)
                return ReleaseRegisteredIpl(descriptor, force, timeoutMs);
            lock (_leaseGate)
                return ReleaseCore(descriptor, force, timeoutMs);
        }

        internal DeferredMapContentResult ReleaseRegisteredIpl(
            DeferredMapContentDescriptor descriptor,
            bool force = false, int timeoutMs = 1500)
        {
            int startedAt = _bridge.MonotonicMilliseconds;
            timeoutMs = NormalizeTimeout(timeoutMs);
            IDictionary<string, object> fields = Fields(descriptor, timeoutMs);
            fields["force"] = force;
            fields["activation_route"] = "startup_registered_ipl";

            if (descriptor == null || !descriptor.IsValid)
                return Result(DeferredMapContentOutcome.InvalidDescriptor,
                    "A valid descriptor is required.", startedAt);
            if (!descriptor.GroupMutationAllowed)
            {
                fields["reason"] = descriptor.GroupMutationBlockReason;
                _log.Warn("release_blocked_unsafe_official_closure", fields);
                return Result(DeferredMapContentOutcome.UnsafeRuntimeState,
                    descriptor.GroupMutationBlockReason, startedAt);
            }

            Lease lease;
            lock (_leaseGate)
            {
                if (IsRegisteredIplOperationPending(descriptor.GroupName))
                    return RegisteredIplOperationPending(
                        "startup_ipl_release_in_progress", fields, startedAt);
                if (!_leases.TryGetValue(descriptor.GroupName, out lease))
                {
                    _log.Info("release_skipped_not_acquired", fields);
                    return Result(DeferredMapContentOutcome.NotAcquired,
                        "The property group is not leased.", startedAt);
                }
                if (!lease.RegisteredIplOnly)
                {
                    fields["reason"] = "lease_route_mismatch";
                    _log.Warn("release_rejected_route_mismatch", fields);
                    return Result(DeferredMapContentOutcome.InvalidDescriptor,
                        "The active lease does not use the registered IPL " +
                        "route.", startedAt);
                }
                if (!SameIpls(lease.Descriptor.Ipls, descriptor.Ipls))
                {
                    fields["reason"] =
                        "descriptor_changed_while_releasing";
                    _log.Warn("release_rejected_descriptor_mismatch", fields);
                    return Result(DeferredMapContentOutcome.InvalidDescriptor,
                        "The active group was released with a different IPL " +
                        "set.", startedAt);
                }
                if (lease.Descriptor.KeepResident && !force)
                {
                    _log.Info("release_kept_resident", fields);
                    return Result(DeferredMapContentOutcome.KeptResident,
                        "The property is configured to remain active for the " +
                        "session.", startedAt);
                }
                if (!force && lease.References > 1)
                {
                    lease.References--;
                    fields["reference_count"] = lease.References;
                    _log.Info("release_reference_retained", fields);
                    return Result(
                        DeferredMapContentOutcome.ReferenceAcquired,
                        "Another consumer still leases this property.",
                        startedAt);
                }
                _pendingRegisteredIplReleases.Add(descriptor.GroupName);
            }

            try
            {
                RemoveOwnedIpls(lease.Descriptor, lease.PreexistingIpls);
                bool inactive = WaitForOwnedIplsInactive(
                    lease, timeoutMs, startedAt);
                fields["elapsed_ms"] = Elapsed(startedAt);
                fields["ipls_inactive"] = inactive;
                fields["fallback"] = false;
                if (!inactive)
                {
                    fields["lease_retained"] = true;
                    _log.Warn("release_completed_with_active_ipls", fields);
                    return Result(DeferredMapContentOutcome.TimedOut,
                        "At least one owned IPL remained active; cleanup can " +
                        "be retried.", startedAt);
                }

                lock (_leaseGate)
                {
                    if (_leases.TryGetValue(descriptor.GroupName,
                            out Lease current) && ReferenceEquals(current, lease))
                        _leases.Remove(descriptor.GroupName);
                }
                _log.Info("release_completed", fields);
                return Result(DeferredMapContentOutcome.Released,
                    "The property content was released.", startedAt);
            }
            catch (Exception ex)
            {
                fields["elapsed_ms"] = Elapsed(startedAt);
                fields["lease_retained"] = true;
                _log.Error("release_native_failed", ex, fields);
                return Result(DeferredMapContentOutcome.NativeFailure,
                    ex.Message, startedAt);
            }
            finally
            {
                lock (_leaseGate)
                    _pendingRegisteredIplReleases.Remove(
                        descriptor.GroupName);
            }
        }

        private DeferredMapContentResult ReleaseCore(
            DeferredMapContentDescriptor descriptor,
            bool force, int timeoutMs)
        {
            int startedAt = _bridge.MonotonicMilliseconds;
            timeoutMs = NormalizeTimeout(timeoutMs);
            IDictionary<string, object> fields = Fields(descriptor, timeoutMs);
            fields["force"] = force;

            if (descriptor == null || !descriptor.IsValid)
                return Result(DeferredMapContentOutcome.InvalidDescriptor,
                    "A valid descriptor is required.", startedAt);

            if (!descriptor.GroupMutationAllowed)
            {
                fields["reason"] = descriptor.GroupMutationBlockReason;
                _log.Warn("release_blocked_unsafe_official_closure", fields);
                return Result(DeferredMapContentOutcome.UnsafeRuntimeState,
                    descriptor.GroupMutationBlockReason, startedAt);
            }

            if (IsRegisteredIplOperationPending(descriptor.GroupName))
                return RegisteredIplOperationPending(
                    "startup_ipl_operation_in_progress", fields, startedAt);

            if (!_leases.TryGetValue(descriptor.GroupName, out Lease lease))
            {
                _log.Info("release_skipped_not_acquired", fields);
                return Result(DeferredMapContentOutcome.NotAcquired,
                    "The property group is not leased.", startedAt);
            }

            if (!SameIpls(lease.Descriptor.Ipls, descriptor.Ipls))
            {
                fields["reason"] = "descriptor_changed_while_releasing";
                _log.Warn("release_rejected_descriptor_mismatch", fields);
                return Result(DeferredMapContentOutcome.InvalidDescriptor,
                    "The active group was released with a different IPL set.",
                    startedAt);
            }

            if (lease.Descriptor.KeepResident && !force)
            {
                _log.Info("release_kept_resident", fields);
                return Result(DeferredMapContentOutcome.KeptResident,
                    "The property is configured to remain active for the session.",
                    startedAt);
            }

            if (!force && lease.References > 1)
            {
                lease.References--;
                fields["reference_count"] = lease.References;
                _log.Info("release_reference_retained", fields);
                return Result(DeferredMapContentOutcome.ReferenceAcquired,
                    "Another consumer still leases this property.", startedAt);
            }

            bool inactive = false;
            try
            {
                foreach (string ipl in lease.Descriptor.Ipls)
                {
                    if (!lease.PreexistingIpls.Contains(ipl))
                        _bridge.RemoveIpl(ipl);
                }

                inactive = WaitForOwnedIplsInactive(
                    lease, timeoutMs, startedAt);
                if (lease.OwnsGroup && !lease.UsesFallback)
                {
                    uint groupHash = _bridge.GenerateHash(
                        lease.Descriptor.GroupName);
                    fields["group_hash"] = "0x" + groupHash.ToString("X8");
                    _bridge.RevertGroup(groupHash);
                }
            }
            catch (Exception ex)
            {
                fields["elapsed_ms"] = Elapsed(startedAt);
                fields["lease_retained"] = true;
                _log.Error("release_native_failed", ex, fields);
                return Result(DeferredMapContentOutcome.NativeFailure,
                    ex.Message, startedAt);
            }

            fields["elapsed_ms"] = Elapsed(startedAt);
            fields["ipls_inactive"] = inactive;
            fields["fallback"] = lease.UsesFallback;
            if (!inactive)
            {
                fields["lease_retained"] = true;
                _log.Warn("release_completed_with_active_ipls", fields);
                return Result(DeferredMapContentOutcome.TimedOut,
                    "At least one owned IPL remained active; cleanup can be retried.",
                    startedAt);
            }

            // Keep the lease registered until every native cleanup call has
            // completed. If a native throws or an IPL remains active, the
            // caller can retry instead of losing ownership bookkeeping.
            _leases.Remove(descriptor.GroupName);
            _log.Info("release_completed", fields);
            return Result(DeferredMapContentOutcome.Released,
                "The property content was released.", startedAt);
        }

        private void FinalizeRegisteredIplLease(
            DeferredMapContentDescriptor descriptor,
            HashSet<string> preexisting)
        {
            lock (_leaseGate)
            {
                if (_leases.ContainsKey(descriptor.GroupName))
                    throw new InvalidOperationException(
                        "A lease appeared while registered IPL activation " +
                        "was pending.");
                _leases[descriptor.GroupName] = new Lease
                {
                    Descriptor = descriptor,
                    References = 1,
                    OwnsGroup = false,
                    UsesFallback = false,
                    RegisteredIplOnly = true,
                    PreexistingIpls = preexisting,
                };
            }
        }

        private void RemoveOwnedIpls(
            DeferredMapContentDescriptor descriptor,
            ISet<string> preexisting)
        {
            foreach (string ipl in descriptor.Ipls)
            {
                if (preexisting == null || !preexisting.Contains(ipl))
                    _bridge.RemoveIpl(ipl);
            }
        }

        private bool IsRegisteredIplOperationPending(string groupName) =>
            !string.IsNullOrWhiteSpace(groupName) &&
            (_pendingRegisteredIplActivations.Contains(groupName) ||
             _pendingRegisteredIplReleases.Contains(groupName));

        private DeferredMapContentResult RegisteredIplOperationPending(
            string reason, IDictionary<string, object> fields, int startedAt)
        {
            fields["reason"] = reason;
            _log.Info("registered_ipl_operation_deferred", fields);
            return Result(DeferredMapContentOutcome.UnsafeRuntimeState,
                reason, startedAt);
        }

        internal void ForceReleaseAll(
            ISet<string> preservedGroups = null, int timeoutMs = 750)
        {
            DeferredMapContentDescriptor[] descriptors;
            HashSet<string> registeredIplGroups;
            lock (_leaseGate)
            {
                descriptors = _leases.Values
                    .Select(value => value.Descriptor).ToArray();
                registeredIplGroups = new HashSet<string>(
                    _leases.Where(pair => pair.Value.RegisteredIplOnly)
                        .Select(pair => pair.Key),
                    StringComparer.OrdinalIgnoreCase);
            }
            foreach (DeferredMapContentDescriptor descriptor in descriptors)
            {
                if (preservedGroups != null &&
                    preservedGroups.Contains(descriptor.GroupName))
                    continue;
                if (registeredIplGroups.Contains(descriptor.GroupName))
                    ReleaseRegisteredIpl(
                        descriptor, force: true, timeoutMs: timeoutMs);
                else
                    Release(descriptor, force: true, timeoutMs: timeoutMs);
            }
        }

        internal int ReferenceCount(string groupName)
        {
            lock (_leaseGate)
                return !string.IsNullOrWhiteSpace(groupName) &&
                    _leases.TryGetValue(groupName, out Lease lease)
                        ? lease.References : 0;
        }

        internal bool IsCleanupPending(string groupName)
        {
            lock (_leaseGate)
                return !string.IsNullOrWhiteSpace(groupName) &&
                    _leases.TryGetValue(groupName, out Lease lease) &&
                    lease.CleanupPending;
        }

        private DeferredMapContentResult TryFallback(
            DeferredMapContentDescriptor descriptor, int timeoutMs,
            int startedAt, HashSet<string> preexisting,
            IDictionary<string, object> fields, string reason)
        {
            fields["fallback_reason"] = reason;
            try
            {
                _log.Info("fallback_activation_requested", fields);
                if (_bridge.TryActivateFallback(descriptor.Ipls, timeoutMs))
                {
                    _leases[descriptor.GroupName] = new Lease
                    {
                        Descriptor = descriptor,
                        References = 1,
                        OwnsGroup = false,
                        UsesFallback = true,
                        PreexistingIpls = preexisting,
                    };
                    fields["elapsed_ms"] = Elapsed(startedAt);
                    _log.Warn("fallback_activation_ready", fields);
                    return Result(DeferredMapContentOutcome.FallbackActivated,
                        "The legacy monolithic map pack supplied the IPLs.",
                        startedAt);
                }
            }
            catch (Exception ex)
            {
                _log.Error("fallback_activation_failed", ex, fields);
                return Result(DeferredMapContentOutcome.NativeFailure,
                    ex.Message, startedAt);
            }

            _log.Warn("fallback_activation_unavailable", fields);
            return Result(
                reason == "native_failure"
                    ? DeferredMapContentOutcome.NativeFailure
                    : DeferredMapContentOutcome.TimedOut,
                "Neither the deferred group nor the fallback map pack became ready.",
                startedAt);
        }

        private DeferredMapContentResult TryRegisteredIplActivation(
            DeferredMapContentDescriptor descriptor, int timeoutMs,
            int startedAt, int activationStartedAt,
            HashSet<string> preexisting,
            IDictionary<string, object> fields)
        {
            fields["activation_route"] = "startup_registered_ipl";
            try
            {
                _log.Info("registered_ipl_activation_requested", fields);
                if (WaitForIpls(
                    descriptor.Ipls, true, timeoutMs, activationStartedAt))
                {
                    _leases[descriptor.GroupName] = new Lease
                    {
                        Descriptor = descriptor,
                        References = 1,
                        OwnsGroup = false,
                        UsesFallback = false,
                        PreexistingIpls = preexisting,
                    };
                    fields["elapsed_ms"] = Elapsed(startedAt);
                    _log.Info("registered_ipl_activation_ready", fields);
                    return Result(DeferredMapContentOutcome.Activated,
                        "The startup-registered property IPLs are active.",
                        startedAt);
                }

                foreach (string ipl in descriptor.Ipls)
                    if (!preexisting.Contains(ipl))
                        _bridge.RemoveIpl(ipl);
                fields["elapsed_ms"] = Elapsed(startedAt);
                _log.Warn("registered_ipl_activation_timed_out", fields);
                return Result(DeferredMapContentOutcome.TimedOut,
                    "The registered property IPLs did not become active.",
                    startedAt);
            }
            catch (Exception ex)
            {
                try
                {
                    foreach (string ipl in descriptor.Ipls)
                        if (!preexisting.Contains(ipl))
                            _bridge.RemoveIpl(ipl);
                }
                catch (Exception cleanupEx)
                {
                    _log.Error("registered_ipl_cleanup_failed", cleanupEx,
                        fields);
                }
                _log.Error("registered_ipl_activation_failed", ex, fields);
                return Result(DeferredMapContentOutcome.NativeFailure,
                    ex.Message, startedAt);
            }
        }

        private bool RollBackFailedActivation(
            DeferredMapContentDescriptor descriptor, uint groupHash,
            HashSet<string> preexisting, IDictionary<string, object> fields)
        {
            try
            {
                foreach (string ipl in descriptor.Ipls)
                    if (!preexisting.Contains(ipl))
                        _bridge.RemoveIpl(ipl);
                _bridge.RevertGroup(groupHash);
                _log.Info("activation_rolled_back", fields);
                return true;
            }
            catch (Exception rollbackEx)
            {
                // Conservatively retain ownership even if ExecuteGroup may
                // have thrown before mutation. Losing the lease would make a
                // broad content-change-set impossible to clean up safely.
                _leases[descriptor.GroupName] = new Lease
                {
                    Descriptor = descriptor,
                    References = 1,
                    OwnsGroup = true,
                    UsesFallback = false,
                    CleanupPending = true,
                    PreexistingIpls = preexisting,
                };
                fields["lease_retained"] = true;
                fields["cleanup_pending"] = true;
                _log.Error("activation_rollback_failed", rollbackEx, fields);
                return false;
            }
        }

        private bool WaitForIpls(
            string[] ipls, bool desiredActive, int timeoutMs, int startedAt)
        {
            do
            {
                bool ready = true;
                foreach (string ipl in ipls)
                {
                    bool active = _bridge.IsIplActive(ipl);
                    if (desiredActive && !active)
                    {
                        _bridge.RequestIpl(ipl);
                        ready = false;
                    }
                    else if (!desiredActive && active)
                    {
                        ready = false;
                    }
                }

                if (ready) return true;
                int remaining = timeoutMs - Elapsed(startedAt);
                if (remaining <= 0) return false;
                _bridge.Yield(Math.Min(PollIntervalMs, remaining));
            }
            while (true);
        }

        private bool WaitForRuntimeSafe(int timeoutMs, out string reason)
        {
            int startedAt = _bridge.MonotonicMilliseconds;
            do
            {
                if (_bridge.IsRuntimeSafe(out reason))
                    return true;
                int remaining = timeoutMs - Elapsed(startedAt);
                if (remaining <= 0)
                    return false;
                _bridge.Yield(Math.Min(PollIntervalMs, remaining));
            }
            while (true);
        }

        private bool WaitForOwnedIplsInactive(
            Lease lease, int timeoutMs, int startedAt)
        {
            string[] owned = lease.Descriptor.Ipls
                .Where(ipl => !lease.PreexistingIpls.Contains(ipl))
                .ToArray();
            if (owned.Length == 0) return true;
            return WaitForIpls(owned, false, timeoutMs, startedAt);
        }

        private bool IsIplActiveSafely(string ipl)
        {
            try { return _bridge.IsIplActive(ipl); }
            catch { return false; }
        }

        private DeferredMapContentResult Result(
            DeferredMapContentOutcome outcome, string detail, int startedAt) =>
            new DeferredMapContentResult(outcome, detail, Elapsed(startedAt));

        private int Elapsed(int startedAt) =>
            unchecked((int)(uint)(_bridge.MonotonicMilliseconds - startedAt));

        private static int NormalizeTimeout(int timeoutMs) =>
            Math.Max(0, Math.Min(MaximumTimeoutMs, timeoutMs));

        private static bool SameIpls(string[] left, string[] right) =>
            new HashSet<string>(left, StringComparer.OrdinalIgnoreCase)
                .SetEquals(right);

        private static IDictionary<string, object> Fields(
            DeferredMapContentDescriptor descriptor, int timeoutMs) =>
            new Dictionary<string, object>
            {
                { "property", descriptor?.PropertyKey ?? "invalid" },
                { "group", descriptor?.GroupName ?? "" },
                { "ipl_count", descriptor?.Ipls?.Length ?? 0 },
                { "timeout_ms", timeoutMs },
                { "keep_resident", descriptor?.KeepResident ?? false },
            };
    }

    internal enum OfficialMapActivationRoute
    {
        Unavailable = 0,
        IsolatedStartupIpl = 1,
        ReferenceBridgeGroup = 2,
    }

    /// <summary>
    /// Routes only the verified metadata-reference bridge. The retired Davis
    /// startup-IPL canary remains represented in the enum for receipt and log
    /// compatibility, but can never resolve to an executable runtime route.
    /// </summary>
    internal static class OfficialMapActivationPolicy
    {
        internal static OfficialMapActivationRoute Resolve(
            bool isolatedStartupIplVerified,
            bool referenceBridgeVerified)
        {
            return referenceBridgeVerified
                ? OfficialMapActivationRoute.ReferenceBridgeGroup
                : OfficialMapActivationRoute.Unavailable;
        }

        internal static bool ExecutesDeferredGroup(
            OfficialMapActivationRoute route) =>
            route == OfficialMapActivationRoute.ReferenceBridgeGroup;

        internal static bool AllowsMutation(
            OfficialMapActivationRoute route,
            bool referenceClosureSafe) =>
            route == OfficialMapActivationRoute.ReferenceBridgeGroup &&
            referenceClosureSafe;

        internal static DeferredMapContentResult Acquire(
            DeferredMapContentLeaseManager manager,
            DeferredMapContentDescriptor descriptor,
            OfficialMapActivationRoute route, int timeoutMs)
        {
            if (manager == null)
                throw new ArgumentNullException(nameof(manager));
            if (route != OfficialMapActivationRoute.ReferenceBridgeGroup)
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    "The startup-registered IPL route is quarantined.", 0);
            return manager.Acquire(
                descriptor, timeoutMs, allowFallback: false,
                executeDeferredGroup: ExecutesDeferredGroup(route));
        }
    }

    internal static class DeferredMapContentRuntime
    {
        private static readonly GtaDeferredMapContentBridge Bridge =
            new GtaDeferredMapContentBridge();
        private static readonly DeferredMapContentLeaseManager Manager =
            new DeferredMapContentLeaseManager(
                Bridge,
                new ClientDeferredMapContentLogger());
        private static readonly OfficialGarageMapEntryCooldown
            OfficialGarageEntryCooldown =
                new OfficialGarageMapEntryCooldown();

        internal static void ObserveStoryRuntimeReadiness()
        {
            Bridge.ObserveStoryRuntime(out _);
        }

        internal static bool IsStoryRuntimeReady(out string reason)
        {
            return Bridge.ObserveStoryRuntime(out reason);
        }

        internal static bool HasDavisPhaseBCleanupPending =>
            Manager.IsCleanupPending(
                DavisStockReferenceBridgePolicy.DormantGroup);

        internal static bool HasGrapeseedPhaseBCleanupPending =>
            Manager.IsCleanupPending(
                GrapeseedStockReferenceBridgePolicy.DormantGroup);

        internal static bool HasGarmentPhaseBCleanupPending =>
            Manager.IsCleanupPending(
                GarmentStockReferenceBridgePolicy.DormantGroup);

        internal static string GarageUnavailableMessage(string displayName)
        {
            string name = string.IsNullOrWhiteSpace(displayName)
                ? "This map-backed garage"
                : displayName;
            return $"~y~{name} could not stream its GTA DLC interior safely. " +
                "Run ALLIN1 Install / Repair, then try again.";
        }

        internal static string GrapeseedEntryUnavailableMessage()
        {
            if (GrapeseedStockReferenceBridgePolicy
                    .IsCurrentNativeMutationAttestationPending)
                return "~y~Grapeseed Garage verification is still running. " +
                    "Try again shortly; if this persists, run ALLIN1 " +
                    "Install / Repair.";
            return GarageUnavailableMessage("Grapeseed Garage");
        }

        internal static bool CanBeginOfficialGarageEntry(
            DeferredMapProperty property, out int retryAfterMilliseconds)
        {
            // Isolated stock-reference garages may begin their black
            // transition only after startup's background full-archive
            // attestation has completed. This keeps multi-gigabyte stock
            // hashes off the entry path and fails closed while any exact
            // marker, receipt, or effective source identity is unavailable.
            bool authorized;
            var interiorBridge = OfficialInteriorStockBridgePolicy.For(property);
            if (interiorBridge != null)
            {
                authorized = interiorBridge.IsCurrentRuntimeActivationAuthorized &&
                    interiorBridge.IsCurrentNativeMutationAuthorized &&
                    HasMountedPackProof(Bridge, interiorBridge.PackName);
                if (!authorized)
                    GTA.UI.Screen.ShowSubtitle(
                        "~y~Garage map verification is not ready. Wait briefly, " +
                        "or run ALLIN1 Install / Repair.", 3500);
            }
            else if (property == DeferredMapProperty.GarmentFactory)
            {
                authorized = GarmentStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized;
                if (authorized)
                    authorized = GarmentStockReferenceBridgePolicy
                        .IsCurrentNativeMutationAuthorized;
                if (authorized)
                    authorized = HasMountedPackProof(
                        Bridge, GarmentStockReferenceBridgePolicy.PackName);
                if (!authorized)
                    ClientLog.Warn("DeferredMap",
                        "garment_phase_b_authorization_unavailable",
                        new Dictionary<string, object>
                        {
                            { "property", "garment_factory" },
                            { "request_source", "garage_entry" },
                            { "native_group_executed", false },
                            { "ipl_requested", false },
                        });
            }
            else if (property == DeferredMapProperty.Grapeseed)
            {
                authorized = GrapeseedStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized;
                if (!authorized)
                {
                    if (GrapeseedStockReferenceBridgePolicy
                            .IsCurrentPhaseABootOnlyContract)
                        GrapeseedStockReferenceBridgePolicy
                            .ReportPhaseARuntimeActivationBlocked(
                                "garage_entry");
                    else
                        ClientLog.Warn("DeferredMap",
                            "grapeseed_phase_b_authorization_unavailable",
                            new Dictionary<string, object>
                            {
                                { "property", "grapeseed" },
                                { "request_source", "garage_entry" },
                                { "native_group_executed", false },
                                { "ipl_requested", false },
                            });
                }
                if (authorized)
                    authorized = GrapeseedStockReferenceBridgePolicy
                        .IsCurrentNativeMutationAuthorized;
                if (authorized)
                {
                    authorized = HasMountedPackProof(
                        Bridge, GrapeseedStockReferenceBridgePolicy.PackName);
                    if (!authorized)
                        ClientLog.Warn("DeferredMap",
                            "grapeseed_phase_b_mounted_pack_unavailable",
                            new Dictionary<string, object>
                            {
                                { "property", "grapeseed" },
                                { "request_source", "garage_entry_guard" },
                                { "native_group_executed", false },
                                { "ipl_requested", false },
                            });
                }
            }
            else
            {
                authorized = DavisStockReferenceBridgePolicy
                    .IsRuntimeActivationAuthorized(property);
                if (authorized && property == DeferredMapProperty.Davis)
                    authorized = DavisStockReferenceBridgePolicy
                        .IsCurrentNativeMutationAuthorized;
            }
            if (!authorized)
            {
                retryAfterMilliseconds = 0;
                return false;
            }
            return OfficialGarageEntryCooldown.TryBegin(
                property, Environment.TickCount,
                out retryAfterMilliseconds);
        }

        internal static DeferredMapContentResult TryAcquire(
            DeferredMapProperty property, IEnumerable<string> ipls,
            int timeoutMs = 8000) =>
            TryAcquireOfficial(property, ipls, timeoutMs,
                observeGarageEntryCooldown: true,
                requestSource: "garage_entry");

        internal static DeferredMapContentResult TryAcquireProximity(
            DeferredMapProperty property, IEnumerable<string> ipls,
            int timeoutMs = 8000) =>
            TryAcquireOfficial(property, ipls, timeoutMs,
                observeGarageEntryCooldown: false,
                requestSource: "proximity_zone");

        internal static DeferredMapContentResult TryAcquireDavisPhaseB(
            OfficialGarageTransitionCoordinator transition,
            IEnumerable<string> ipls, int timeoutMs = 8000)
        {
            int startedAt = Environment.TickCount;
            string[] requested = NormalizeIpls(ipls);
            var fields = new Dictionary<string, object>
            {
                { "transition_id", transition?.TransitionId ?? "missing" },
                { "property", "davis" },
                { "group", DavisStockReferenceBridgePolicy.DormantGroup },
                { "request_source", "garage_entry_black_transition" },
                { "ipl_count", requested.Length },
                { "phase", transition?.Phase.ToString() ?? "missing" },
                { "fade_held", transition?.FadeHeld ?? false },
                { "native_group_executed", false },
                { "ipl_requested", false },
            };

            if (!DavisStockReferenceBridgePolicy
                    .IsCurrentNativeMutationAuthorized)
            {
                ClientLog.Warn("DeferredMap",
                    "davis_phase_b_native_attestation_unavailable", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    "The verified Davis Phase-B receipt or stock archive " +
                    "attestation is unavailable.",
                    ElapsedSince(startedAt));
            }
            if (transition == null || !transition.FadeHeld ||
                transition.Phase !=
                    OfficialGarageTransitionPhase.LeaseRequested)
            {
                ClientLog.Warn("DeferredMap",
                    "davis_phase_b_transition_permit_rejected", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.UnsafeRuntimeState,
                    "Davis activation requires the owned garage-entry black " +
                    "transition at LeaseRequested.", ElapsedSince(startedAt));
            }
            if (!Bridge.IsScreenFadedOut())
            {
                ClientLog.Warn("DeferredMap",
                    "davis_phase_b_black_screen_not_verified", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.UnsafeRuntimeState,
                    "The screen is not fully faded out; no Davis map native " +
                    "was executed.", ElapsedSince(startedAt));
            }
            if (!IsExactDavisIplSet(requested))
            {
                ClientLog.Warn("DeferredMap",
                    "davis_phase_b_ipl_contract_rejected", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.InvalidDescriptor,
                    "The Davis Phase-B IPL set does not match its receipt.",
                    ElapsedSince(startedAt));
            }

            fields["black_screen_verified"] = true;
            fields["keep_resident"] = true;
            ClientLog.Info("DeferredMap",
                "davis_phase_b_black_transition_verified", fields);
            var descriptor = new DeferredMapContentDescriptor(
                DeferredMapProperty.Davis,
                DavisStockReferenceBridgePolicy.DormantGroup,
                requested, keepResident: true);
            DeferredMapContentResult result = Manager.Acquire(
                descriptor, timeoutMs, allowFallback: false,
                executeDeferredGroup: true,
                blackTransitionVerified: true);
            ClientLog.Info("DeferredMap", "davis_phase_b_activation_result",
                new Dictionary<string, object>
                {
                    { "transition_id", transition.TransitionId },
                    { "property", "davis" },
                    { "group", descriptor.GroupName },
                    { "outcome", result.Outcome.ToString().ToLowerInvariant() },
                    { "success", result.Success },
                    { "elapsed_ms", result.ElapsedMilliseconds },
                    { "keep_resident", descriptor.KeepResident },
                });
            return result;
        }

        internal static DeferredMapContentResult TryAcquireInteriorUnderBlackTransition(
            DeferredMapProperty property, OfficialGarageTransitionCoordinator transition,
            IEnumerable<string> ipls, int timeoutMs = 8000)
        {
            var policy = OfficialInteriorStockBridgePolicy.For(property);
            var result = AcquireInteriorUnderBlackTransition(
                Manager, Bridge, property, transition, NormalizeIpls(ipls),
                policy != null && policy.IsCurrentNativeMutationAuthorized, timeoutMs);
            ClientLog.Info("DeferredMap", "interior_black_transition_result",
                new Dictionary<string, object>
                {
                    { "property", property.ToString().ToLowerInvariant() },
                    { "transition_id", transition?.TransitionId ?? "missing" },
                    { "outcome", result.Outcome.ToString() },
                    { "elapsed_ms", result.ElapsedMilliseconds },
                    { "detail", result.Detail },
                });
            return ObserveOfficialGarageAttempt(property, result);
        }

        internal static DeferredMapContentResult AcquireInteriorUnderBlackTransition(
            DeferredMapContentLeaseManager manager, IDeferredMapContentBridge bridge,
            DeferredMapProperty property, OfficialGarageTransitionCoordinator transition,
            string[] requested, bool attested, int timeoutMs)
        {
            var policy = OfficialInteriorStockBridgePolicy.For(property);
            if (policy == null || !attested || !HasMountedPackProof(bridge, policy.PackName))
                return new DeferredMapContentResult(DeferredMapContentOutcome.MapPackUnavailable,
                    "The scoped interior bridge or stock archive is not verified and mounted.", 0);
            if (transition == null || !transition.FadeHeld || transition.Phase !=
                    OfficialGarageTransitionPhase.LeaseRequested || !bridge.IsScreenFadedOut())
                return new DeferredMapContentResult(DeferredMapContentOutcome.UnsafeRuntimeState,
                    "Interior activation requires an owned, fully black entry transition.", 0);
            if (requested == null || requested.Length != policy.Ipls.Length ||
                !new HashSet<string>(requested, StringComparer.OrdinalIgnoreCase).SetEquals(policy.Ipls))
                return new DeferredMapContentResult(DeferredMapContentOutcome.InvalidDescriptor,
                    "Interior IPLs do not match the fixed property contract.", 0);
            return manager.Acquire(new DeferredMapContentDescriptor(property,
                policy.DormantGroup, requested, keepResident: true), timeoutMs,
                allowFallback: false, executeDeferredGroup: true, blackTransitionVerified: true);
        }

        internal static DeferredMapContentResult TryAcquireGarmentPhaseB(
            OfficialGarageTransitionCoordinator transition,
            IEnumerable<string> ipls, int timeoutMs = 8000)
        {
            int startedAt = Environment.TickCount;
            string[] requested = NormalizeIpls(ipls);
            var fields = new Dictionary<string, object>
            {
                { "transition_id", transition?.TransitionId ?? "missing" },
                { "property", "garment_factory" },
                { "group", GarmentStockReferenceBridgePolicy.DormantGroup },
                { "request_source", "garage_entry_black_transition" },
                { "ipl_count", requested.Length },
                { "phase", transition?.Phase.ToString() ?? "missing" },
                { "fade_held", transition?.FadeHeld ?? false },
                { "native_group_executed", false },
                { "ipl_requested", false },
            };

            if (!GarmentStockReferenceBridgePolicy
                    .IsCurrentNativeMutationAuthorized ||
                !HasMountedPackProof(
                    Bridge, GarmentStockReferenceBridgePolicy.PackName))
            {
                ClientLog.Warn("DeferredMap",
                    "garment_phase_b_native_attestation_unavailable", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    "The verified Garment Factory bridge, mounted-pack " +
                    "proof, or stock archive attestation is unavailable.",
                    ElapsedSince(startedAt));
            }
            if (transition == null || !transition.FadeHeld ||
                transition.Phase !=
                    OfficialGarageTransitionPhase.LeaseRequested)
            {
                ClientLog.Warn("DeferredMap",
                    "garment_phase_b_transition_permit_rejected", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.UnsafeRuntimeState,
                    "Garment Factory activation requires the owned " +
                    "garage-entry black transition at LeaseRequested.",
                    ElapsedSince(startedAt));
            }
            if (!Bridge.IsScreenFadedOut())
            {
                ClientLog.Warn("DeferredMap",
                    "garment_phase_b_black_screen_not_verified", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.UnsafeRuntimeState,
                    "The screen is not fully faded out; no Garment Factory " +
                    "map native was executed.", ElapsedSince(startedAt));
            }
            if (!IsExactGarmentIplSet(requested))
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.InvalidDescriptor,
                    "The Garment Factory IPL set does not match its receipt.",
                    ElapsedSince(startedAt));

            fields["black_screen_verified"] = true;
            fields["keep_resident"] = true;
            ClientLog.Info("DeferredMap",
                "garment_phase_b_black_transition_verified", fields);
            var descriptor = new DeferredMapContentDescriptor(
                DeferredMapProperty.GarmentFactory,
                GarmentStockReferenceBridgePolicy.DormantGroup,
                requested, keepResident: true);
            DeferredMapContentResult result = Manager.Acquire(
                descriptor, timeoutMs, allowFallback: false,
                executeDeferredGroup: true,
                blackTransitionVerified: true);
            ClientLog.Info("DeferredMap",
                "garment_phase_b_activation_result",
                new Dictionary<string, object>
                {
                    { "transition_id", transition.TransitionId },
                    { "property", "garment_factory" },
                    { "group", descriptor.GroupName },
                    { "outcome", result.Outcome.ToString().ToLowerInvariant() },
                    { "success", result.Success },
                    { "elapsed_ms", result.ElapsedMilliseconds },
                    { "keep_resident", descriptor.KeepResident },
                });
            return result;
        }

        internal static DeferredMapContentResult TryAcquireGrapeseedPhaseB(
            OfficialGarageTransitionCoordinator transition,
            IEnumerable<string> ipls, int timeoutMs = 8000)
        {
            int startedAt = Environment.TickCount;
            string[] requested = NormalizeIpls(ipls);
            var fields = new Dictionary<string, object>
            {
                { "transition_id", transition?.TransitionId ?? "missing" },
                { "property", "grapeseed" },
                { "group",
                    GrapeseedStockReferenceBridgePolicy.DormantGroup },
                { "request_source", "garage_entry_black_transition" },
                { "ipl_count", requested.Length },
                { "phase", transition?.Phase.ToString() ?? "missing" },
                { "fade_held", transition?.FadeHeld ?? false },
                { "native_group_executed", false },
                { "ipl_requested", false },
            };

            if (!GrapeseedStockReferenceBridgePolicy
                    .IsCurrentNativeMutationAuthorized)
            {
                ClientLog.Warn("DeferredMap",
                    "grapeseed_phase_b_native_attestation_unavailable",
                    fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    "The verified Grapeseed Phase-B receipt or stock archive " +
                    "attestation is unavailable.", ElapsedSince(startedAt));
            }
            // IS_DLC_PRESENT proves that GTA currently recognizes this pack
            // name. It cannot prove dlclist exact-once registration, which is
            // separately enforced by installer/status checks. Recheck here
            // after CanBegin to close the pre-transition TOCTOU window.
            if (!HasMountedPackProof(
                    Bridge, GrapeseedStockReferenceBridgePolicy.PackName))
            {
                ClientLog.Warn("DeferredMap",
                    "grapeseed_phase_b_mounted_pack_unavailable", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    "GTA does not report the verified Grapeseed bridge as " +
                    "mounted. Run ALLIN1 Install / Repair.",
                    ElapsedSince(startedAt));
            }
            if (transition == null || !transition.FadeHeld ||
                transition.Phase !=
                    OfficialGarageTransitionPhase.LeaseRequested)
            {
                ClientLog.Warn("DeferredMap",
                    "grapeseed_phase_b_transition_permit_rejected", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.UnsafeRuntimeState,
                    "Grapeseed activation requires the owned garage-entry " +
                    "black transition at LeaseRequested.",
                    ElapsedSince(startedAt));
            }
            if (!Bridge.IsScreenFadedOut())
            {
                ClientLog.Warn("DeferredMap",
                    "grapeseed_phase_b_black_screen_not_verified", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.UnsafeRuntimeState,
                    "The screen is not fully faded out; no Grapeseed map " +
                    "native was executed.", ElapsedSince(startedAt));
            }
            if (!IsExactGrapeseedIplSet(requested))
            {
                ClientLog.Warn("DeferredMap",
                    "grapeseed_phase_b_ipl_contract_rejected", fields);
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.InvalidDescriptor,
                    "The Grapeseed Phase-B IPL set does not match its receipt.",
                    ElapsedSince(startedAt));
            }

            fields["black_screen_verified"] = true;
            fields["keep_resident"] = true;
            ClientLog.Info("DeferredMap",
                "grapeseed_phase_b_black_transition_verified", fields);
            var descriptor = new DeferredMapContentDescriptor(
                DeferredMapProperty.Grapeseed,
                GrapeseedStockReferenceBridgePolicy.DormantGroup,
                requested, keepResident: true);
            DeferredMapContentResult result = Manager.Acquire(
                descriptor, timeoutMs, allowFallback: false,
                executeDeferredGroup: true,
                blackTransitionVerified: true);
            ClientLog.Info("DeferredMap",
                "grapeseed_phase_b_activation_result",
                new Dictionary<string, object>
                {
                    { "transition_id", transition.TransitionId },
                    { "property", "grapeseed" },
                    { "group", descriptor.GroupName },
                    { "outcome", result.Outcome.ToString().ToLowerInvariant() },
                    { "success", result.Success },
                    { "elapsed_ms", result.ElapsedMilliseconds },
                    { "keep_resident", descriptor.KeepResident },
                });
            return result;
        }

        internal static bool HasMountedPackProof(
            IDeferredMapContentBridge bridge, string packName)
        {
            if (bridge == null || string.IsNullOrWhiteSpace(packName))
                return false;
            try { return bridge.IsDlcPresent(packName); }
            catch { return false; }
        }

        private static DeferredMapContentResult TryAcquireOfficial(
            DeferredMapProperty property, IEnumerable<string> ipls,
            int timeoutMs, bool observeGarageEntryCooldown,
            string requestSource)
        {
            if (OfficialInteriorStockBridgePolicy.For(property) != null)
                return new DeferredMapContentResult(DeferredMapContentOutcome.UnsafeRuntimeState,
                    "This interior requires its owned black entry transition, never proximity activation.", 0);
            if (property == DeferredMapProperty.Davis)
            {
                bool phaseB = DavisStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized;
                ClientLog.Warn("DeferredMap", phaseB
                        ? "davis_phase_b_visible_activation_blocked"
                        : "davis_phase_a_runtime_activation_blocked",
                    new Dictionary<string, object>
                    {
                        { "property", property.ToString().ToLowerInvariant() },
                        { "request_source", requestSource },
                        { "required_phase", phaseB
                            ? "explicit-garage-entry-black-transition"
                            : "phase-b-black-transition" },
                        { "native_group_executed", false },
                        { "ipl_requested", false },
                    });
                var blocked = new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    phaseB
                        ? "Davis Phase B cannot activate from proximity or a " +
                          "visible-world request. Use the explicit garage " +
                          "entry transition."
                        : "Davis Phase A is a boot-only canary; a verified " +
                          "Phase-B black-transition receipt is required.", 0);
                return observeGarageEntryCooldown
                    ? ObserveOfficialGarageAttempt(property, blocked)
                    : blocked;
            }

            if (property == DeferredMapProperty.Grapeseed)
            {
                bool phaseB = GrapeseedStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized;
                bool phaseA = !phaseB && GrapeseedStockReferenceBridgePolicy
                    .IsCurrentPhaseABootOnlyContract;
                if (phaseA)
                    GrapeseedStockReferenceBridgePolicy
                        .ReportPhaseARuntimeActivationBlocked(requestSource);
                else
                    ClientLog.Warn("DeferredMap", phaseB
                            ? "grapeseed_phase_b_visible_activation_blocked"
                            : "grapeseed_stock_reference_bridge_unavailable",
                        new Dictionary<string, object>
                        {
                            { "property", "grapeseed" },
                            { "request_source", requestSource },
                            { "required_phase", phaseB
                                ? "explicit-garage-entry-black-transition"
                                : "phase-b-black-transition" },
                            { "native_group_executed", false },
                            { "ipl_requested", false },
                        });
                var blocked = new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    phaseB
                        ? "Grapeseed Phase B cannot activate from proximity " +
                          "or a visible-world request. Use the explicit " +
                          "garage entry transition."
                        : phaseA
                            ? "Grapeseed Phase A is a boot-only canary; a " +
                              "verified Phase-B black-transition receipt is " +
                              "required."
                            : "The isolated Grapeseed stock-reference bridge " +
                              "is unavailable.", 0);
                return observeGarageEntryCooldown
                    ? ObserveOfficialGarageAttempt(property, blocked)
                    : blocked;
            }

            if (property == DeferredMapProperty.GarmentFactory)
            {
                ClientLog.Warn("DeferredMap",
                    "garment_phase_b_visible_activation_blocked",
                    new Dictionary<string, object>
                    {
                        { "property", "garment_factory" },
                        { "request_source", requestSource },
                        { "required_phase",
                            "explicit-garage-entry-black-transition" },
                        { "native_group_executed", false },
                        { "ipl_requested", false },
                    });
                var blocked = new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    "Garment Factory cannot activate from proximity or a " +
                    "visible-world request. Use the explicit garage entry " +
                    "transition.", 0);
                return observeGarageEntryCooldown
                    ? ObserveOfficialGarageAttempt(property, blocked)
                    : blocked;
            }

            string[] requestedIpls = (ipls ?? Enumerable.Empty<string>())
                .ToArray();
            bool isolatedPackVerified =
                StandaloneMapPack.IsIsolatedStartupPropertyVerified(property);
            bool isolatedStartupIpl = isolatedPackVerified &&
                StandaloneMapPack.IsExactIsolatedStartupIplRequest(
                    property, requestedIpls);
            bool referenceBridge = !isolatedStartupIpl &&
                !isolatedPackVerified &&
                StandaloneMapPack.Layout ==
                    StandaloneMapPackLayout.OfficialReferenceBridge &&
                StandaloneMapPack.IsReferenceBridgeVerified;
            OfficialMapActivationRoute route =
                OfficialMapActivationPolicy.Resolve(
                    isolatedStartupIpl, referenceBridge);

            bool referenceClosureSafe = false;
            string mutationBlockReason = string.Empty;
            if (route == OfficialMapActivationRoute.ReferenceBridgeGroup)
            {
                referenceClosureSafe =
                    StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntime(
                        property, out mutationBlockReason);
            }
            bool mutationAllowed = OfficialMapActivationPolicy.AllowsMutation(
                route, referenceClosureSafe);
            var descriptor = new DeferredMapContentDescriptor(
                property, requestedIpls,
                groupMutationAllowed: mutationAllowed,
                groupMutationBlockReason: mutationBlockReason);

            if (route == OfficialMapActivationRoute.Unavailable)
            {
                ClientLog.Warn("DeferredMap", "official_map_bridge_unavailable",
                    new Dictionary<string, object>
                    {
                        { "property", descriptor.PropertyKey },
                        { "group", descriptor.GroupName ?? string.Empty },
                        { "ipl_count", descriptor.Ipls.Length },
                        { "layout", StandaloneMapPack.Layout.ToString() },
                        { "repair", "Install / Repair" },
                        { "request_source", requestSource },
                        { "isolated_pack_verified", isolatedPackVerified },
                        { "ipl_contract_matched", !isolatedPackVerified ||
                            isolatedStartupIpl },
                    });
                var unavailable = new DeferredMapContentResult(
                        DeferredMapContentOutcome.MapPackUnavailable,
                        "The verified ALLIN1 garage map bridge is unavailable; " +
                        "run Install / Repair.", 0);
                return observeGarageEntryCooldown
                    ? ObserveOfficialGarageAttempt(property, unavailable)
                    : unavailable;
            }

            ClientLog.Info("DeferredMap", "official_ipl_activation_requested",
                new Dictionary<string, object>
                {
                    { "property", descriptor.PropertyKey },
                    { "group", descriptor.GroupName ?? string.Empty },
                    { "ipl_count", descriptor.Ipls.Length },
                    { "source", isolatedStartupIpl
                        ? "verified_isolated_startup_ipl_pack"
                        : "verified_metadata_bridge" },
                    { "request_source", requestSource },
                    { "compatibility_pack_required", true },
                    { "deferred_group",
                        OfficialMapActivationPolicy.ExecutesDeferredGroup(
                            route) },
                });

            // Every group name is resolved from DeferredMapProperty above; no
            // package or user input can supply an arbitrary changeset. The
            // bridge only references files already owned by Rockstar's DLCs.
            // A timeout removes owned IPLs, reverts the property group, and
            // fails before the player is teleported.
            DeferredMapContentResult result =
                OfficialMapActivationPolicy.Acquire(
                    Manager, descriptor, route, timeoutMs);
            return observeGarageEntryCooldown
                ? ObserveOfficialGarageAttempt(property, result)
                : result;
        }

        private static DeferredMapContentResult ObserveOfficialGarageAttempt(
            DeferredMapProperty property, DeferredMapContentResult result)
        {
            OfficialGarageEntryCooldown.Observe(
                property, result, Environment.TickCount);
            return result;
        }

        internal static DeferredMapContentResult Release(
            DeferredMapProperty property, IEnumerable<string> ipls,
            bool force = false, int timeoutMs = 1500)
        {
            var interiorPolicy = OfficialInteriorStockBridgePolicy.For(property);
            if (interiorPolicy != null)
            {
                string[] requested = NormalizeIpls(ipls);
                if (!new HashSet<string>(requested, StringComparer.OrdinalIgnoreCase)
                        .SetEquals(interiorPolicy.Ipls))
                    return new DeferredMapContentResult(DeferredMapContentOutcome.InvalidDescriptor,
                        "Interior release IPLs do not match their property contract.", 0);
                return Manager.Release(new DeferredMapContentDescriptor(property,
                    interiorPolicy.DormantGroup, requested, keepResident: true), force, timeoutMs);
            }
            if (property == DeferredMapProperty.GarmentFactory)
            {
                string[] garmentIpls = NormalizeIpls(ipls);
                if (!IsExactGarmentIplSet(garmentIpls))
                    return new DeferredMapContentResult(
                        DeferredMapContentOutcome.InvalidDescriptor,
                        "The Garment Factory IPL set does not match its " +
                        "receipt.", 0);
                return Manager.Release(new DeferredMapContentDescriptor(
                    DeferredMapProperty.GarmentFactory,
                    GarmentStockReferenceBridgePolicy.DormantGroup,
                    garmentIpls, keepResident: true), force, timeoutMs);
            }

            if (property == DeferredMapProperty.Grapeseed)
            {
                bool ownsGrapeseedLease = Manager.ReferenceCount(
                    GrapeseedStockReferenceBridgePolicy.DormantGroup) > 0;
                if (!ownsGrapeseedLease &&
                    !GrapeseedStockReferenceBridgePolicy
                        .IsCurrentRuntimeActivationAuthorized)
                {
                    ClientLog.Info("DeferredMap",
                        "grapeseed_phase_a_runtime_release_skipped",
                        new Dictionary<string, object>
                        {
                            { "property", "grapeseed" },
                            { "native_group_reverted", false },
                            { "ipl_removed", false },
                        });
                    return new DeferredMapContentResult(
                        DeferredMapContentOutcome.NotAcquired,
                        "Grapeseed Phase A owns no runtime map lease.", 0);
                }
                string[] grapeseedIpls = NormalizeIpls(ipls);
                if (!IsExactGrapeseedIplSet(grapeseedIpls))
                    return new DeferredMapContentResult(
                        DeferredMapContentOutcome.InvalidDescriptor,
                        "The Grapeseed Phase-B IPL set does not match its " +
                        "receipt.", 0);
                return Manager.Release(new DeferredMapContentDescriptor(
                    DeferredMapProperty.Grapeseed,
                    GrapeseedStockReferenceBridgePolicy.DormantGroup,
                    grapeseedIpls, keepResident: true), force, timeoutMs);
            }

            bool ownsDavisLease = property == DeferredMapProperty.Davis &&
                Manager.ReferenceCount(
                    DavisStockReferenceBridgePolicy.DormantGroup) > 0;
            if (!ownsDavisLease && !DavisStockReferenceBridgePolicy
                    .IsRuntimeActivationAuthorized(property))
            {
                ClientLog.Info("DeferredMap",
                    "davis_phase_a_runtime_release_skipped",
                    new Dictionary<string, object>
                    {
                        { "property", property.ToString().ToLowerInvariant() },
                        { "native_group_reverted", false },
                        { "ipl_removed", false },
                    });
                return new DeferredMapContentResult(
                    DeferredMapContentOutcome.NotAcquired,
                    "Davis Phase A owns no runtime map lease.", 0);
            }

            if (property == DeferredMapProperty.Davis)
            {
                string[] davisIpls = NormalizeIpls(ipls);
                if (!IsExactDavisIplSet(davisIpls))
                    return new DeferredMapContentResult(
                        DeferredMapContentOutcome.InvalidDescriptor,
                        "The Davis Phase-B IPL set does not match its receipt.",
                        0);
                return Manager.Release(new DeferredMapContentDescriptor(
                    DeferredMapProperty.Davis,
                    DavisStockReferenceBridgePolicy.DormantGroup,
                    davisIpls, keepResident: true), force, timeoutMs);
            }

            string[] requestedIpls = (ipls ?? Enumerable.Empty<string>())
                .ToArray();
            bool isolatedStartupIpl =
                StandaloneMapPack.IsIsolatedStartupPropertyVerified(property) &&
                StandaloneMapPack.IsExactIsolatedStartupIplRequest(
                    property, requestedIpls);
            bool mutationAllowed = isolatedStartupIpl;
            string mutationBlockReason = string.Empty;
            if (!isolatedStartupIpl)
            {
                mutationAllowed =
                    StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntime(
                        property, out mutationBlockReason);
            }
            return Manager.Release(new DeferredMapContentDescriptor(
                    property, requestedIpls,
                    groupMutationAllowed: mutationAllowed,
                    groupMutationBlockReason: mutationBlockReason),
                force, timeoutMs);
        }

        internal static DeferredMapContentResult TryAcquireRegistered(
            string propertyKey, string groupName, IEnumerable<string> ipls,
            bool keepResident = false, int timeoutMs = 8000) =>
            Manager.Acquire(new DeferredMapContentDescriptor(
                propertyKey, groupName, ipls, keepResident), timeoutMs,
                allowFallback: false, executeDeferredGroup: false);

        internal static DeferredMapContentResult ReleaseRegistered(
            string propertyKey, string groupName, IEnumerable<string> ipls,
            bool keepResident = false, bool force = false,
            int timeoutMs = 1500) =>
            Manager.Release(new DeferredMapContentDescriptor(
                propertyKey, groupName, ipls, keepResident), force,
                timeoutMs);

        internal static void OnScriptAborted(
            IEnumerable<DeferredMapProperty> preservedProperties = null)
        {
            var preservedGroups = new HashSet<string>(
                (preservedProperties ?? Enumerable.Empty<DeferredMapProperty>())
                    .Select(DeferredMapContentGroups.Resolve)
                    .Where(group => !string.IsNullOrWhiteSpace(group)),
                StringComparer.OrdinalIgnoreCase);
            // The Tuners changeset is intentionally session-resident after a
            // successful Phase-B activation. SHVDN aborts during normal game
            // teardown too; reverting a broad cache-loader changeset there
            // adds risk and stalls for no benefit because process teardown
            // resets the map state.
            if (DavisStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized &&
                Manager.ReferenceCount(
                    DavisStockReferenceBridgePolicy.DormantGroup) > 0 &&
                !Manager.IsCleanupPending(
                    DavisStockReferenceBridgePolicy.DormantGroup))
                preservedGroups.Add(
                    DavisStockReferenceBridgePolicy.DormantGroup);
            if (GrapeseedStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized &&
                Manager.ReferenceCount(
                    GrapeseedStockReferenceBridgePolicy.DormantGroup) > 0 &&
                !Manager.IsCleanupPending(
                    GrapeseedStockReferenceBridgePolicy.DormantGroup))
                preservedGroups.Add(
                    GrapeseedStockReferenceBridgePolicy.DormantGroup);
            if (GarmentStockReferenceBridgePolicy
                    .IsCurrentRuntimeActivationAuthorized &&
                Manager.ReferenceCount(
                    GarmentStockReferenceBridgePolicy.DormantGroup) > 0 &&
                !Manager.IsCleanupPending(
                    GarmentStockReferenceBridgePolicy.DormantGroup))
                preservedGroups.Add(
                    GarmentStockReferenceBridgePolicy.DormantGroup);
            foreach (var policy in new[] { OfficialInteriorStockBridgePolicy.Harmony,
                OfficialInteriorStockBridgePolicy.Paleto })
                if (Manager.ReferenceCount(policy.DormantGroup) > 0 &&
                    !Manager.IsCleanupPending(policy.DormantGroup))
                    preservedGroups.Add(policy.DormantGroup);
            Manager.ForceReleaseAll(preservedGroups);
        }

        private static string[] NormalizeIpls(IEnumerable<string> ipls) =>
            (ipls ?? Enumerable.Empty<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

        private static bool IsExactDavisIplSet(string[] ipls) =>
            ipls != null && ipls.Length == 1 && string.Equals(
                ipls[0], DavisStockReferenceBridgePolicy.DavisIpl,
                StringComparison.OrdinalIgnoreCase);

        private static bool IsExactGrapeseedIplSet(string[] ipls) =>
            ipls != null && ipls.Length == 1 && string.Equals(
                ipls[0], GrapeseedStockReferenceBridgePolicy.GrapeseedIpl,
                StringComparison.OrdinalIgnoreCase);

        private static bool IsExactGarmentIplSet(string[] ipls) =>
            ipls != null && ipls.Length ==
                GarmentStockReferenceBridgePolicy.Ipls.Length &&
            !ipls.Except(GarmentStockReferenceBridgePolicy.Ipls,
                StringComparer.OrdinalIgnoreCase).Any();

        private static int ElapsedSince(int startedAt) =>
            unchecked((int)(uint)(Environment.TickCount - startedAt));
    }

    internal sealed class StoryRuntimeReadinessGate
    {
        private readonly int _stableRuntimeMs;
        private int _firstStableStoryTime = -1;

        internal StoryRuntimeReadinessGate(int stableRuntimeMs)
        {
            _stableRuntimeMs = Math.Max(0, stableRuntimeMs);
        }

        internal bool Observe(
            int runtimeMs, bool gameLoading, bool playerAvailable,
            bool unsafeTransition, out string reason)
        {
            if (gameLoading)
            {
                Reset();
                reason = "game_loading";
                return false;
            }
            if (unsafeTransition)
            {
                _firstStableStoryTime = -1;
                reason = "game_transition_active";
                return false;
            }
            if (!playerAvailable)
            {
                Reset();
                reason = "player_unavailable";
                return false;
            }
            if (_firstStableStoryTime < 0 || runtimeMs < _firstStableStoryTime)
                _firstStableStoryTime = runtimeMs;
            int stableMs = runtimeMs - _firstStableStoryTime;
            if (stableMs < _stableRuntimeMs)
            {
                reason = "story_runtime_settling:" + stableMs;
                return false;
            }
            reason = string.Empty;
            return true;
        }

        internal void Reset()
        {
            _firstStableStoryTime = -1;
        }
    }

    internal sealed class GtaDeferredMapContentBridge : IDeferredMapContentBridge
    {
        private const int StableStoryRuntimeMs = 10000;
        private static readonly StoryRuntimeReadinessGate StoryReadiness =
            new StoryRuntimeReadinessGate(StableStoryRuntimeMs);

        // Verified in alloc8or's current Legacy and Gen9 native databases.
        private const ulong ExecuteContentChangesetGroupForAll =
            0x6BEDF5769AC2DC07UL;
        private const ulong RevertContentChangesetGroupForAll =
            0x3C1978285B036B25UL;

        public string Edition
        {
            get
            {
                try
                {
                    string executable = Process.GetCurrentProcess()
                        .MainModule?.FileName ?? string.Empty;
                    return Path.GetFileName(executable)
                        .IndexOf("Enhanced", StringComparison.OrdinalIgnoreCase) >= 0
                            ? "enhanced" : "legacy";
                }
                catch { return "unknown"; }
            }
        }

        public int MonotonicMilliseconds => Environment.TickCount;

        public bool IsRuntimeSafe(out string reason)
        {
            return ObserveStoryRuntime(out reason);
        }

        public bool IsScreenFadedOut() =>
            Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT);

        public bool IsDlcPresent(string packName)
        {
            if (string.IsNullOrWhiteSpace(packName)) return false;
            // DLC::IS_DLC_PRESENT(Hash), verified in alloc8or's NativeDB.
            const ulong IsDlcPresentHash = 0x812595A0644CE1DEUL;
            return Function.Call<bool>((Hash)IsDlcPresentHash,
                GenerateHash(packName));
        }

        internal bool ObserveStoryRuntime(out string reason)
        {
            try
            {
                bool loading = Game.IsLoading;
                Ped player = loading ? null : Game.Player.Character;
                bool playerAvailable = player != null && player.Exists();
                bool unsafeTransition = playerAvailable &&
                    GarageManager.IsUnsafeGarageTransitionActive();
                return StoryReadiness.Observe(
                    Game.GameTime, loading, playerAvailable,
                    unsafeTransition, out reason);
            }
            catch (Exception ex)
            {
                StoryReadiness.Reset();
                reason = "runtime_probe_failed:" + ex.GetType().Name;
                return false;
            }
        }

        public uint GenerateHash(string value) =>
            unchecked((uint)Game.GenerateHash(value ?? string.Empty));

        public void ExecuteGroup(uint groupHash) =>
            Function.Call((Hash)ExecuteContentChangesetGroupForAll, groupHash);

        public void RevertGroup(uint groupHash) =>
            Function.Call((Hash)RevertContentChangesetGroupForAll, groupHash);

        public void RequestIpl(string ipl) =>
            Function.Call(Hash.REQUEST_IPL, ipl);

        public void RemoveIpl(string ipl) =>
            Function.Call(Hash.REMOVE_IPL, ipl);

        public bool IsIplActive(string ipl) =>
            Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl);

        public void Yield(int milliseconds) =>
            Script.Wait(Math.Max(0, milliseconds));

        public bool TryActivateFallback(string[] ipls, int timeoutMs) =>
            StandaloneMapPack.TryActivateLegacyFallback(ipls, timeoutMs);
    }

    internal sealed class ClientDeferredMapContentLogger :
        IDeferredMapContentLogger
    {
        public void Info(string message, IDictionary<string, object> fields) =>
            ClientLog.Info("DeferredMap", message, fields);

        public void Warn(string message, IDictionary<string, object> fields) =>
            ClientLog.Warn("DeferredMap", message, fields);

        public void Error(string message, Exception exception,
            IDictionary<string, object> fields) =>
            ClientLog.Error("DeferredMap", message, exception, fields);
    }
}
