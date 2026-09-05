using System;
using System.Collections.Generic;
using System.IO;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GrapeseedPhaseBBlackTransitionTests
    {
        [Fact]
        public void Entry_holds_black_and_requests_lease_before_grapeseed_phase_b()
        {
            var phases = new List<OfficialGarageTransitionPhase>();
            long clock = 0;
            var transition = new OfficialGarageTransitionCoordinator(
                "rural", "entry", () => ++clock,
                observation => phases.Add(observation.Phase),
                rollback: () => { }, forceFadeIn: () => { });

            transition.HoldFade(() => { });
            transition.Advance(OfficialGarageTransitionPhase.LeaseRequested);

            Assert.True(transition.FadeHeld);
            Assert.Equal(OfficialGarageTransitionPhase.LeaseRequested,
                transition.Phase);
            Assert.Equal(new[]
            {
                OfficialGarageTransitionPhase.Idle,
                OfficialGarageTransitionPhase.FadeHeld,
                OfficialGarageTransitionPhase.LeaseRequested,
            }, phases);

            string rural = ReadRepositoryFile(
                "script", "src", "GarageManager.Rural.cs");
            string entry = Slice(rural,
                "private static void EnterRuralGarageCore(",
                "private static void LeaveRuralGarage(");
            AssertOrdered(entry,
                "storedDuringEntry = CaptureVehicleState",
                "transition.HoldFade",
                "OfficialGarageTransitionPhase.LeaseRequested",
                "LoadRuralInterior(transition)",
                "storedListDuringEntry.Add(storedDuringEntry)",
                "OfficialGarageTransitionPhase.Occupied");

            string loader = Slice(rural,
                "private static bool LoadRuralInterior(",
                "private static void UnloadRuralInterior(");
            Assert.Contains(
                "DeferredMapContentRuntime.TryAcquireGrapeseedPhaseB(",
                loader);
            Assert.Contains("transition, RURAL_IPLS", loader);
            Assert.DoesNotContain(
                "DeferredMapContentRuntime.TryAcquire(", loader);
            AssertOrdered(loader,
                "OfficialGarageTransitionPhase.LeaseRequested",
                "OfficialGarageTransitionPhase.IplReady",
                "OfficialGarageTransitionPhase.InteriorReady");
        }

        [Fact]
        public void Failed_entry_rolls_back_storage_lease_and_owned_fade()
        {
            var cleanup = new List<string>();
            long clock = 0;
            var transition = new OfficialGarageTransitionCoordinator(
                "rural", "entry", () => ++clock,
                telemetry: null,
                rollback: () => cleanup.Add("lease_and_storage"),
                forceFadeIn: () => cleanup.Add("fade"));

            transition.HoldFade(() => { });
            transition.Advance(OfficialGarageTransitionPhase.LeaseRequested);
            transition.Fail("fixture_failure");

            Assert.True(transition.IsTerminal);
            Assert.False(transition.FadeHeld);
            Assert.Equal(OfficialGarageTransitionPhase.FailedRecovery,
                transition.Phase);
            Assert.Equal(new[] { "lease_and_storage", "fade" }, cleanup);

            string rural = ReadRepositoryFile(
                "script", "src", "GarageManager.Rural.cs");
            string coordinator = Slice(rural,
                "private static OfficialGarageTransitionCoordinator",
                "private static void EnterRuralGarageCore(");
            AssertOrdered(coordinator,
                "_isPlayerInRuralGarage = false",
                "ClearRuralHandles()",
                "_ruralMapLeaseCreatedForCurrentEntry",
                "UnloadRuralInterior(force: forceRelease)");

            string entry = Slice(rural,
                "private static void EnterRuralGarageCore(",
                "private static void LeaveRuralGarage(");
            Assert.Contains("transition.Fail(\"vehicle_persistence_failed\")",
                entry);
            AssertOrdered(entry,
                "if (storageCommitted && storedDuringEntry != null",
                "storedListDuringEntry.Remove(storedDuringEntry)",
                "if (!RuralSave())",
                "rolled back drive-in storage");
        }

        [Fact]
        public void Grapeseed_phase_b_orders_exact_authority_and_black_guards_before_native_acquire()
        {
            string runtime = ReadRepositoryFile(
                "script", "src", "DeferredMapContentRuntime.cs");
            string phaseB = Slice(runtime,
                "internal static DeferredMapContentResult " +
                    "TryAcquireGrapeseedPhaseB(",
                "private static DeferredMapContentResult " +
                    "TryAcquireOfficial(");

            AssertOrdered(phaseB,
                "IsCurrentNativeMutationAuthorized",
                "HasMountedPackProof(",
                "transition == null || !transition.FadeHeld",
                "OfficialGarageTransitionPhase.LeaseRequested",
                "Bridge.IsScreenFadedOut()",
                "IsExactGrapeseedIplSet(requested)",
                "Manager.Acquire(");
            Assert.Contains("blackTransitionVerified: true", phaseB);
            Assert.Contains("allowFallback: false", phaseB);
            Assert.Contains("executeDeferredGroup: true", phaseB);
            Assert.Contains("keepResident: true", phaseB);
            Assert.Contains(
                "GrapeseedStockReferenceBridgePolicy.DormantGroup", phaseB);
        }

        [Fact]
        public void Grapeseed_entry_denial_is_visible_and_actionable()
        {
            string rural = ReadRepositoryFile(
                "script", "src", "GarageManager.Rural.cs");
            string entry = Slice(rural,
                "private static void EnterRuralGarage()",
                "private static OfficialGarageTransitionCoordinator");
            AssertOrdered(entry,
                "CanBeginOfficialGarageEntry(",
                "GrapeseedEntryUnavailableMessage()",
                "return;",
                "BeginTransition(\"EnterRuralGarage\")");
            Assert.Contains("Screen.ShowSubtitle(", entry);

            string runtime = ReadRepositoryFile(
                "script", "src", "DeferredMapContentRuntime.cs");
            string message = Slice(runtime,
                "internal static string GrapeseedEntryUnavailableMessage()",
                "internal static bool CanBeginOfficialGarageEntry(");
            Assert.Contains("verification is still running", message);
            Assert.Contains("Install / Repair", message);
        }

        [Fact]
        public void Mounted_pack_proof_is_rechecked_before_transition_and_native_acquire()
        {
            string runtime = ReadRepositoryFile(
                "script", "src", "DeferredMapContentRuntime.cs");
            string canBegin = Slice(runtime,
                "internal static bool CanBeginOfficialGarageEntry(",
                "internal static DeferredMapContentResult TryAcquire(");
            AssertOrdered(canBegin,
                "IsCurrentNativeMutationAuthorized",
                "HasMountedPackProof(",
                "return OfficialGarageEntryCooldown.TryBegin(");

            string phaseB = Slice(runtime,
                "internal static DeferredMapContentResult " +
                    "TryAcquireGrapeseedPhaseB(",
                "internal static bool HasMountedPackProof(");
            AssertOrdered(phaseB,
                "IsCurrentNativeMutationAuthorized",
                "HasMountedPackProof(",
                "transition == null || !transition.FadeHeld",
                "Manager.Acquire(");
            Assert.Contains("IS_DLC_PRESENT proves", phaseB);
            Assert.Contains("cannot prove dlclist exact-once", phaseB);
        }

        [Fact]
        public void Grapeseed_generic_and_proximity_paths_return_before_any_native_route()
        {
            DeferredMapContentResult result =
                DeferredMapContentRuntime.TryAcquireProximity(
                    DeferredMapProperty.Grapeseed,
                    new[] { GrapeseedStockReferenceBridgePolicy.GrapeseedIpl },
                    50);
            Assert.Equal(DeferredMapContentOutcome.MapPackUnavailable,
                result.Outcome);

            string runtime = ReadRepositoryFile(
                "script", "src", "DeferredMapContentRuntime.cs");
            string official = Slice(runtime,
                "private static DeferredMapContentResult TryAcquireOfficial(",
                "private static DeferredMapContentResult " +
                    "ObserveOfficialGarageAttempt(");
            string guard = Slice(official,
                "if (property == DeferredMapProperty.Grapeseed)",
                "string[] requestedIpls");
            Assert.Contains(
                "grapeseed_phase_b_visible_activation_blocked", guard);
            Assert.Contains(
                "ReportPhaseARuntimeActivationBlocked(requestSource)", guard);
            Assert.Contains("native_group_executed\", false", guard);
            Assert.Contains("ipl_requested\", false", guard);
            Assert.Contains("return observeGarageEntryCooldown", guard);
            Assert.DoesNotContain("Manager.", guard);
            Assert.DoesNotContain("Bridge.", guard);
            Assert.DoesNotContain("Function.Call", guard);
        }

        [Fact]
        public void Story_startup_observes_phase_a_or_warms_only_verified_phase_b()
        {
            string shop = ReadRepositoryFile(
                "script", "src", "GbayShop.cs");
            string initialize = Slice(shop,
                "private void Initialize()",
                "private bool TryInitializeReactorBridge(");
            Assert.Contains(
                "GrapeseedStockReferenceBridgePolicy", initialize);
            Assert.Contains(".ObserveStartupAuthorizationState()", initialize);

            string policy = ReadRepositoryFile(
                "script", "src", "GrapeseedStockReferenceBridgePolicy.cs");
            string observe = Slice(policy,
                "internal static void ObserveStartupAuthorizationState()",
                "internal static void ReportPhaseARuntimeActivationBlocked(");
            AssertOrdered(observe,
                "IsCurrentPhaseABootOnlyContract",
                "ReportPhaseARuntimeActivationBlocked(\"startup_guard\")",
                "return;",
                "IsCurrentRuntimeActivationAuthorized",
                "WarmUpCurrentNativeMutationAuthorization()");

            string blockedEvent = Slice(policy,
                "internal static void ReportPhaseARuntimeActivationBlocked(",
                "internal static void WarmUpCurrentNativeMutationAuthorization(");
            Assert.Contains(
                "grapeseed_phase_a_runtime_activation_blocked", blockedEvent);
            Assert.Contains("{ \"property\", \"grapeseed\" }", blockedEvent);
            Assert.Contains(
                "{ \"required_phase\", \"phase-b-black-transition\" }",
                blockedEvent);
            Assert.Contains("{ \"native_group_executed\", false }",
                blockedEvent);
            Assert.Contains("{ \"ipl_requested\", false }", blockedEvent);
        }

        [Fact]
        public void Verified_grapeseed_lease_stays_resident_but_failed_acquire_is_owned()
        {
            string rural = ReadRepositoryFile(
                "script", "src", "GarageManager.Rural.cs");
            string loader = Slice(rural,
                "private static bool LoadRuralInterior(",
                "private static void SpawnRuralGarageVehicles(");

            Assert.Contains("HasGrapeseedPhaseBCleanupPending", loader);
            Assert.Contains("_ruralMapLeaseCreatedForCurrentEntry = true",
                loader);
            Assert.Contains(
                "force: _ruralMapLeaseCreatedForCurrentEntry", loader);

            string unload = Slice(loader,
                "private static void UnloadRuralInterior(",
                "private static ParkingSlot ResolveRuralSlot(");
            AssertOrdered(unload,
                "DeferredMapContentRuntime.Release(",
                "DeferredMapContentOutcome.KeptResident",
                "return;",
                "_ruralMapLeaseHeld = false",
                "_ruralMapLeaseCreatedForCurrentEntry = false");
        }

        private static string ReadRepositoryFile(params string[] segments)
        {
            string path = RepositoryRoot();
            foreach (string segment in segments)
                path = Path.Combine(path, segment);
            return File.ReadAllText(path);
        }

        private static string RepositoryRoot()
        {
            string current = AppContext.BaseDirectory;
            while (!string.IsNullOrEmpty(current))
            {
                if (File.Exists(Path.Combine(current,
                        "allin1.workspace.json")))
                    return current;
                current = Directory.GetParent(current)?.FullName;
            }
            throw new DirectoryNotFoundException(
                "Could not locate the ALLIN1 repository root.");
        }

        private static string Slice(string value, string start, string end)
        {
            int startAt = value.IndexOf(start, StringComparison.Ordinal);
            Assert.True(startAt >= 0, "Missing source anchor: " + start);
            int endAt = value.IndexOf(end, startAt + start.Length,
                StringComparison.Ordinal);
            Assert.True(endAt > startAt, "Missing source anchor: " + end);
            return value.Substring(startAt, endAt - startAt);
        }

        private static void AssertOrdered(string value, params string[] tokens)
        {
            int previous = -1;
            foreach (string token in tokens)
            {
                int current = value.IndexOf(token, previous + 1,
                    StringComparison.Ordinal);
                Assert.True(current > previous,
                    "Expected ordered source token: " + token);
                previous = current;
            }
        }
    }
}
