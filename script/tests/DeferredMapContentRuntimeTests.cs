using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class DeferredMapContentRuntimeTests
    {
        [Fact]
        public void Reference_bridge_verification_cache_avoids_hot_path_rechecks()
        {
            var cache = new TimedBooleanVerificationCache();
            int checks = 0;
            Func<bool> verifier = () =>
            {
                checks++;
                return true;
            };

            Assert.True(cache.GetOrVerify(1000, 5000, verifier));
            Assert.True(cache.GetOrVerify(5999, 5000, verifier));
            Assert.Equal(1, checks);

            Assert.True(cache.GetOrVerify(6000, 5000, verifier));
            Assert.Equal(2, checks);
        }

        [Fact]
        public void Reference_bridge_verification_cache_caches_blocked_result()
        {
            var cache = new TimedBooleanVerificationCache();
            int checks = 0;
            Func<bool> verifier = () =>
            {
                checks++;
                return false;
            };

            Assert.False(cache.GetOrVerify(2000, 5000, verifier));
            Assert.False(cache.GetOrVerify(3000, 5000, verifier));
            Assert.Equal(1, checks);

            Assert.False(cache.GetOrVerify(7000, 5000, verifier));
            Assert.Equal(2, checks);
        }

        [Fact]
        public void Property_groups_match_generated_content_contract()
        {
            Assert.Equal("ALLIN1_MAP_GRAPESEED",
                DeferredMapContentGroups.Resolve(
                    DeferredMapProperty.Grapeseed));
            Assert.Equal("ALLIN1_MAP_YACHT",
                DeferredMapContentGroups.Resolve(DeferredMapProperty.Yacht));
            Assert.Equal("ALLIN1_MAP_DAVIS",
                DeferredMapContentGroups.Resolve(DeferredMapProperty.Davis));
            Assert.Equal("ALLIN1_MAP_HARMONY",
                DeferredMapContentGroups.Resolve(DeferredMapProperty.Harmony));
            Assert.Equal("ALLIN1_MAP_PALETO",
                DeferredMapContentGroups.Resolve(DeferredMapProperty.Paleto));
            Assert.Equal("ALLIN1_MAP_GARMENT_FACTORY",
                DeferredMapContentGroups.Resolve(
                    DeferredMapProperty.GarmentFactory));
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.Yacht));
            Assert.False(DeferredMapContentGroups.KeepResident(
                DeferredMapProperty.Davis));
        }

        [Fact]
        public void Unavailable_map_pack_debounces_only_the_failed_property()
        {
            var cooldown = new OfficialGarageMapEntryCooldown();
            var unavailable = new DeferredMapContentResult(
                DeferredMapContentOutcome.MapPackUnavailable,
                "map pack unavailable", 0);

            Assert.True(cooldown.TryBegin(
                DeferredMapProperty.GarmentFactory, 1000, out int remaining));
            Assert.Equal(0, remaining);
            cooldown.Observe(
                DeferredMapProperty.GarmentFactory, unavailable, 1000);

            Assert.False(cooldown.TryBegin(
                DeferredMapProperty.GarmentFactory, 4999, out remaining));
            Assert.Equal(1001, remaining);
            Assert.True(cooldown.TryBegin(
                DeferredMapProperty.Paleto, 4999, out remaining));
            Assert.Equal(0, remaining);
            Assert.True(cooldown.TryBegin(
                DeferredMapProperty.GarmentFactory, 6000, out remaining));
            Assert.Equal(0, remaining);
        }

        [Theory]
        [InlineData((int)DeferredMapContentOutcome.MapPackUnavailable,
            "not installed", true)]
        [InlineData((int)DeferredMapContentOutcome.TimedOut,
            "IPL activation timed out", true)]
        [InlineData((int)DeferredMapContentOutcome.UnsafeRuntimeState,
            "game_loading", true)]
        [InlineData((int)DeferredMapContentOutcome.UnsafeRuntimeState,
            "story_runtime_settling:3200", true)]
        [InlineData((int)DeferredMapContentOutcome.UnsafeRuntimeState,
            "player_unavailable", true)]
        [InlineData((int)DeferredMapContentOutcome.UnsafeRuntimeState,
            "game_transition_active", false)]
        [InlineData((int)DeferredMapContentOutcome.InvalidDescriptor,
            "invalid", false)]
        public void Retry_policy_only_debounces_unavailable_or_loading_results(
            int outcome, string detail, bool expected)
        {
            var result = new DeferredMapContentResult(
                (DeferredMapContentOutcome)outcome, detail, 0);

            Assert.Equal(expected,
                OfficialGarageMapEntryRetryPolicy.ShouldDebounce(result));
        }

        [Fact]
        public void Non_debounced_result_clears_a_previous_denial()
        {
            var cooldown = new OfficialGarageMapEntryCooldown();
            cooldown.Observe(DeferredMapProperty.Harmony,
                new DeferredMapContentResult(
                    DeferredMapContentOutcome.MapPackUnavailable,
                    "unavailable", 0), 1000);
            cooldown.Observe(DeferredMapProperty.Harmony,
                new DeferredMapContentResult(
                    DeferredMapContentOutcome.Activated,
                    "ready", 20), 1200);

            Assert.True(cooldown.TryBegin(
                DeferredMapProperty.Harmony, 1201, out int remaining));
            Assert.Equal(0, remaining);
        }

        [Fact]
        public void Acquire_executes_group_and_waits_for_required_ipls()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(bridge, log);
            var descriptor = Descriptor(DeferredMapProperty.Harmony,
                "harmony_primary", "harmony_collision");

            DeferredMapContentResult result = manager.Acquire(
                descriptor, 500, false);

            Assert.True(result.Success);
            Assert.Equal(DeferredMapContentOutcome.Activated, result.Outcome);
            Assert.Equal(1, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Contains("harmony_primary", bridge.ActiveIpls);
            Assert.Contains("harmony_collision", bridge.ActiveIpls);
            Assert.Equal(1, manager.ReferenceCount(descriptor.GroupName));
            Assert.Contains("activation_ready", log.Messages);
        }

        [Fact]
        public void Leases_reference_count_and_only_last_release_reverts()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Davis, "davis_shop");

            Assert.True(manager.Acquire(descriptor).Success);
            Assert.Equal(DeferredMapContentOutcome.ReferenceAcquired,
                manager.Acquire(descriptor).Outcome);
            Assert.Equal(2, manager.ReferenceCount(descriptor.GroupName));

            Assert.Equal(DeferredMapContentOutcome.ReferenceAcquired,
                manager.Release(descriptor).Outcome);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Contains("davis_shop", bridge.ActiveIpls);

            Assert.Equal(DeferredMapContentOutcome.Released,
                manager.Release(descriptor).Outcome);
            Assert.Equal(1, bridge.RevertCount);
            Assert.DoesNotContain("davis_shop", bridge.ActiveIpls);
        }

        [Fact]
        public void Unsafe_runtime_fails_closed_before_any_native_call()
        {
            var bridge = new FakeBridge
            {
                RuntimeSafe = false,
                UnsafeReason = "game_loading",
            };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(
                bridge, log);

            DeferredMapContentResult result = manager.Acquire(
                Descriptor(DeferredMapProperty.Paleto, "casino_garage"));

            Assert.False(result.Success);
            Assert.Equal(DeferredMapContentOutcome.UnsafeRuntimeState,
                result.Outcome);
            Assert.Equal("game_loading", result.Detail);
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Empty(bridge.RequestedIpls);
            Assert.Equal(15000, bridge.MonotonicMilliseconds);
            Assert.Contains("activation_queued_unsafe_runtime", log.Messages);
            Assert.Contains("activation_deferred_unsafe_runtime", log.Messages);
        }

        [Fact]
        public void Loading_screen_closure_fails_before_group_or_ipl_mutation()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(bridge, log);
            var descriptor = new DeferredMapContentDescriptor(
                DeferredMapProperty.Yacht, new[] { "hei_yacht_heist" },
                groupMutationAllowed: false,
                groupMutationBlockReason:
                    "official_closure_requires_loading_screen:MPHEIST_PRE_MAP_CHANGES");

            DeferredMapContentResult result = manager.Acquire(descriptor);

            Assert.Equal(DeferredMapContentOutcome.UnsafeRuntimeState,
                result.Outcome);
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Empty(bridge.RequestedIpls);
            Assert.Equal(0, manager.ReferenceCount(descriptor.GroupName));
            Assert.Contains("activation_blocked_unsafe_official_closure",
                log.Messages);
        }

        [Fact]
        public void Loading_screen_closure_fails_before_group_revert()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(bridge, log);
            var safe = Descriptor(
                DeferredMapProperty.Yacht, "hei_yacht_heist");
            var blocked = new DeferredMapContentDescriptor(
                DeferredMapProperty.Yacht, new[] { "hei_yacht_heist" },
                groupMutationAllowed: false,
                groupMutationBlockReason:
                    "official_closure_requires_loading_screen:MPHEIST_PRE_MAP_CHANGES");

            Assert.True(manager.Acquire(safe).Success);
            DeferredMapContentResult result = manager.Release(blocked);

            Assert.Equal(DeferredMapContentOutcome.UnsafeRuntimeState,
                result.Outcome);
            Assert.Equal(1, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Empty(bridge.RemovedIpls);
            Assert.Equal(1, manager.ReferenceCount(safe.GroupName));
            Assert.Contains("release_blocked_unsafe_official_closure",
                log.Messages);
        }

        [Fact]
        public void Story_readiness_can_warm_before_the_first_garage_request()
        {
            var readiness = new StoryRuntimeReadinessGate(10000);

            Assert.False(readiness.Observe(
                500, false, true, false, out string reason));
            Assert.Equal("story_runtime_settling:0", reason);
            Assert.False(readiness.Observe(
                10499, false, true, false, out reason));
            Assert.Equal("story_runtime_settling:9999", reason);
            Assert.True(readiness.Observe(
                10500, false, true, false, out reason));
            Assert.Equal(string.Empty, reason);

            Assert.False(readiness.Observe(
                10600, true, true, false, out reason));
            Assert.Equal("game_loading", reason);
            Assert.False(readiness.Observe(
                20000, false, true, false, out reason));
            Assert.Equal("story_runtime_settling:0", reason);

            Assert.False(readiness.Observe(
                30000, false, true, true, out reason));
            Assert.Equal("game_transition_active", reason);
            Assert.False(readiness.Observe(
                40000, false, true, false, out reason));
            Assert.Equal("story_runtime_settling:0", reason);
        }

        [Fact]
        public void Early_request_waits_for_story_then_gets_full_activation_budget()
        {
            var bridge = new FakeBridge
            {
                RuntimeSafe = false,
                RuntimeSafeAfterMilliseconds = 10000,
                UnsafeReason = "story_runtime_settling:0",
                ActivateOnRequest = true,
                ActivationDelayMilliseconds = 75,
            };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(bridge, log);

            DeferredMapContentResult result = manager.Acquire(
                Descriptor(DeferredMapProperty.Harmony, "harmony_primary"),
                100, false, false);

            Assert.True(result.Success);
            Assert.Equal(DeferredMapContentOutcome.Activated, result.Outcome);
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Equal(10000, bridge.FirstRequestAtMilliseconds);
            Assert.True(bridge.MonotonicMilliseconds >= 10075);
            Assert.Contains("activation_queued_unsafe_runtime", log.Messages);
            Assert.Contains("activation_runtime_ready_after_queue", log.Messages);
            Assert.Contains("registered_ipl_activation_ready", log.Messages);
        }

        [Fact]
        public void Timeout_rolls_back_group_then_uses_monolithic_fallback()
        {
            var bridge = new FakeBridge
            {
                ActivateOnRequest = false,
                FallbackSucceeds = true,
            };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(bridge, log);
            var descriptor = Descriptor(
                DeferredMapProperty.GarmentFactory, "hacker_garage");

            DeferredMapContentResult result = manager.Acquire(
                descriptor, 100, true);

            Assert.True(result.Success);
            Assert.Equal(DeferredMapContentOutcome.FallbackActivated,
                result.Outcome);
            Assert.Equal(1, bridge.ExecuteCount);
            Assert.Equal(1, bridge.RevertCount);
            Assert.Equal(1, bridge.FallbackCount);
            Assert.Contains("hacker_garage", bridge.ActiveIpls);
            Assert.Contains("activation_rolled_back", log.Messages);
            Assert.Contains("fallback_activation_ready", log.Messages);

            manager.Release(descriptor);
            Assert.Equal(1, bridge.RevertCount);
            Assert.DoesNotContain("hacker_garage", bridge.ActiveIpls);
        }

        [Fact]
        public void Legacy_layout_uses_fallback_without_executing_custom_group()
        {
            var bridge = new FakeBridge { FallbackSucceeds = true };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Davis, "davis_shop");

            DeferredMapContentResult result = manager.Acquire(
                descriptor, 500, true, false);

            Assert.Equal(DeferredMapContentOutcome.FallbackActivated,
                result.Outcome);
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Equal(1, bridge.FallbackCount);
        }

        [Fact]
        public void Startup_registered_layout_uses_only_ipl_lifetime_calls()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(bridge, log);
            var descriptor = Descriptor(
                DeferredMapProperty.Davis, "davis_shop");

            DeferredMapContentResult result = manager.Acquire(
                descriptor, 500, false, false);

            Assert.Equal(DeferredMapContentOutcome.Activated, result.Outcome);
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
            Assert.Equal(0, bridge.FallbackCount);
            Assert.Contains("davis_shop", bridge.RequestedIpls);
            Assert.Contains("registered_ipl_activation_ready", log.Messages);

            Assert.Equal(DeferredMapContentOutcome.Released,
                manager.Release(descriptor).Outcome);
            Assert.Contains("davis_shop", bridge.RemovedIpls);
            Assert.Equal(0, bridge.RevertCount);
        }

        [Fact]
        public void Startup_ipl_reentrant_acquire_defers_without_corrupting_lease()
        {
            var bridge = new FakeBridge
            {
                ActivateOnRequest = true,
                ActivationDelayMilliseconds = 50,
            };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Davis, "davis_shop");
            DeferredMapContentResult reentrant = default;
            int callbacks = 0;
            bridge.OnYield = () =>
            {
                if (Interlocked.Increment(ref callbacks) != 1) return;
                reentrant = manager.Acquire(
                    descriptor, 500, false, false);
            };

            DeferredMapContentResult outer = manager.Acquire(
                descriptor, 500, false, false);

            Assert.Equal(DeferredMapContentOutcome.Activated, outer.Outcome);
            Assert.Equal(DeferredMapContentOutcome.UnsafeRuntimeState,
                reentrant.Outcome);
            Assert.Equal("startup_ipl_activation_in_progress",
                reentrant.Detail);
            Assert.Equal(1, manager.ReferenceCount(descriptor.GroupName));
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Equal(0, bridge.RevertCount);
        }

        [Fact]
        public async Task Startup_ipl_concurrent_acquire_does_not_wait_on_lease_monitor()
        {
            var enteredYield = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var resumeYield = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var contenderEntered = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            var bridge = new FakeBridge
            {
                ActivateOnRequest = true,
                ActivationDelayMilliseconds = 50,
            };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Davis, "davis_shop");
            int callbacks = 0;
            bridge.OnYield = () =>
            {
                if (Interlocked.Increment(ref callbacks) != 1) return;
                enteredYield.TrySetResult(true);
                resumeYield.Task.GetAwaiter().GetResult();
            };

            // Dedicated workers prevent thread-pool starvation from being
            // mistaken for contention on the lease monitor. Keep the same
            // 500 ms bound, measured only after the contender actually starts.
            Task<DeferredMapContentResult> owner = Task.Factory.StartNew(() =>
                manager.Acquire(descriptor, 500, false, false),
                CancellationToken.None, TaskCreationOptions.LongRunning,
                TaskScheduler.Default);
            Task<DeferredMapContentResult> contender = null;
            bool completedBeforeOwnerResumed = false;
            try
            {
                Assert.Same(enteredYield.Task, await Task.WhenAny(
                    enteredYield.Task, Task.Delay(TimeSpan.FromSeconds(2))));
                contender = Task.Factory.StartNew(() =>
                {
                    contenderEntered.TrySetResult(true);
                    return manager.Acquire(descriptor, 500, false, false);
                }, CancellationToken.None, TaskCreationOptions.LongRunning,
                    TaskScheduler.Default);
                Assert.Same(contenderEntered.Task, await Task.WhenAny(
                    contenderEntered.Task, Task.Delay(TimeSpan.FromSeconds(2))));
                Task first = await Task.WhenAny(contender, Task.Delay(500));
                completedBeforeOwnerResumed = ReferenceEquals(first, contender);
            }
            finally
            {
                resumeYield.TrySetResult(true);
            }
            Assert.Same(owner, await Task.WhenAny(
                owner, Task.Delay(TimeSpan.FromSeconds(2))));
            Assert.Same(contender, await Task.WhenAny(
                contender, Task.Delay(TimeSpan.FromSeconds(2))));
            DeferredMapContentResult ownerResult = await owner;
            DeferredMapContentResult contenderResult = await contender;

            Assert.True(completedBeforeOwnerResumed);
            Assert.Equal(DeferredMapContentOutcome.UnsafeRuntimeState,
                contenderResult.Outcome);
            Assert.Equal(DeferredMapContentOutcome.Activated,
                ownerResult.Outcome);
            Assert.Equal(1, manager.ReferenceCount(descriptor.GroupName));
        }

        [Fact]
        public void Custom_descriptor_uses_its_lease_key_without_group_native()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = new DeferredMapContentDescriptor(
                "acme.maps:warehouse", "acme.maps:warehouse:main",
                new[] { "acme_warehouse" });

            DeferredMapContentResult result = manager.Acquire(
                descriptor, 500, false, false);

            Assert.True(result.Success);
            Assert.Equal("acme.maps:warehouse", descriptor.PropertyKey);
            Assert.Equal(0, bridge.ExecuteCount);
            Assert.Contains("acme_warehouse", bridge.RequestedIpls);
            Assert.Equal(DeferredMapContentOutcome.Released,
                manager.Release(descriptor).Outcome);
            Assert.Equal(0, bridge.RevertCount);
        }

        [Fact]
        public void Timeout_without_fallback_reports_failure_and_leaves_no_lease()
        {
            var bridge = new FakeBridge { ActivateOnRequest = false };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Grapeseed, "rural_garage");

            DeferredMapContentResult result = manager.Acquire(
                descriptor, 100, false);

            Assert.False(result.Success);
            Assert.Equal(DeferredMapContentOutcome.TimedOut, result.Outcome);
            Assert.Equal(1, bridge.RevertCount);
            Assert.Equal(0, manager.ReferenceCount(descriptor.GroupName));
        }

        [Fact]
        public void Failed_activation_rollback_retains_owned_cleanup_lease()
        {
            var bridge = new FakeBridge
            {
                ActivateOnRequest = false,
                ThrowOnRevert = true,
            };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Davis, "davis_phase_b_ipl");

            DeferredMapContentResult failed = manager.Acquire(
                descriptor, 100, allowFallback: true,
                executeDeferredGroup: true,
                blackTransitionVerified: true);

            Assert.Equal(DeferredMapContentOutcome.NativeFailure,
                failed.Outcome);
            Assert.Equal(0, bridge.FallbackCount);
            Assert.Equal(1, manager.ReferenceCount(descriptor.GroupName));
            Assert.True(manager.IsCleanupPending(descriptor.GroupName));

            bridge.ThrowOnRevert = false;
            Assert.Equal(DeferredMapContentOutcome.Released,
                manager.Release(descriptor, force: true).Outcome);
            Assert.Equal(0, manager.ReferenceCount(descriptor.GroupName));
            Assert.False(manager.IsCleanupPending(descriptor.GroupName));
        }

        [Fact]
        public void Preexisting_ipls_are_neither_executed_nor_removed()
        {
            var bridge = new FakeBridge();
            bridge.ActiveIpls.Add("already_here");
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Harmony, "already_here");

            Assert.Equal(DeferredMapContentOutcome.AlreadyActive,
                manager.Acquire(descriptor).Outcome);
            Assert.Equal(0, bridge.ExecuteCount);

            Assert.True(manager.Release(descriptor).Success);
            Assert.Contains("already_here", bridge.ActiveIpls);
            Assert.Empty(bridge.RemovedIpls);
            Assert.Equal(0, bridge.RevertCount);
        }

        [Fact]
        public void Yacht_release_is_scoped_and_does_not_require_forced_shutdown()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Yacht, "hei_yacht_heist");

            Assert.True(manager.Acquire(descriptor).Success);
            Assert.Equal(DeferredMapContentOutcome.Released,
                manager.Release(descriptor).Outcome);
            Assert.DoesNotContain("hei_yacht_heist", bridge.ActiveIpls);
            Assert.Equal(1, bridge.RevertCount);
            Assert.Equal(0, manager.ReferenceCount(descriptor.GroupName));
        }

        [Fact]
        public void Failed_native_release_retains_lease_for_cleanup_retry()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var manager = new DeferredMapContentLeaseManager(
                bridge, new FakeLogger());
            var descriptor = Descriptor(
                DeferredMapProperty.Harmony, "harmony_primary");

            Assert.True(manager.Acquire(descriptor).Success);
            bridge.ThrowOnRevert = true;

            Assert.Equal(DeferredMapContentOutcome.NativeFailure,
                manager.Release(descriptor).Outcome);
            Assert.Equal(1, manager.ReferenceCount(descriptor.GroupName));

            bridge.ThrowOnRevert = false;
            Assert.Equal(DeferredMapContentOutcome.Released,
                manager.Release(descriptor).Outcome);
            Assert.Equal(0, manager.ReferenceCount(descriptor.GroupName));
        }

        [Fact]
        public void Active_ipl_release_timeout_retains_lease_for_cleanup_retry()
        {
            var bridge = new FakeBridge { ActivateOnRequest = true };
            var log = new FakeLogger();
            var manager = new DeferredMapContentLeaseManager(bridge, log);
            var descriptor = Descriptor(
                DeferredMapProperty.Grapeseed, "rural_garage");

            Assert.True(manager.Acquire(descriptor).Success);
            bridge.IgnoreRemoveRequests = true;

            DeferredMapContentResult timedOut = manager.Release(
                descriptor, false, 100);
            Assert.Equal(DeferredMapContentOutcome.TimedOut, timedOut.Outcome);
            Assert.False(timedOut.ReleaseComplete);
            Assert.Equal(1, manager.ReferenceCount(descriptor.GroupName));
            Assert.Contains("release_completed_with_active_ipls", log.Messages);

            bridge.IgnoreRemoveRequests = false;
            DeferredMapContentResult released = manager.Release(descriptor);
            Assert.Equal(DeferredMapContentOutcome.Released, released.Outcome);
            Assert.True(released.ReleaseComplete);
            Assert.Equal(0, manager.ReferenceCount(descriptor.GroupName));
        }

        [Theory]
        [InlineData("layout=pruned-local-v3-startup-registered-ipl", 4)]
        [InlineData("layout=pruned-local-v3-deferred", 2)]
        [InlineData("layout=pruned-local-v4-unregistered", 5)]
        [InlineData("layout=official-reference-v2-deferred", 6)]
        [InlineData("layout=pruned-local-v3-startup-registered-ipl\narchive_registration=disabled", 5)]
        [InlineData("layout=pruned-local-v2-legacy-monolithic", 1)]
        [InlineData("layout=pruned-local-v2", 1)]
        [InlineData("pack=allin1_maps", 1)]
        [InlineData("", 3)]
        [InlineData("   \r\n", 3)]
        [InlineData("layout=future-layout", 3)]
        [InlineData("layout=future-deferred-layout", 3)]
        [InlineData("layout=pruned-local-v3-deferred-preview", 3)]
        [InlineData("layout=future-startup-registered-ipl", 3)]
        [InlineData("layout=future-request-ipl", 3)]
        [InlineData("layout=future-monolithic-layout", 3)]
        public void Map_pack_marker_classification_is_fail_closed(
            string marker, int expected)
        {
            Assert.Equal((StandaloneMapPackLayout)expected,
                StandaloneMapPack.ClassifyMarker(marker));
        }

        [Theory]
        [InlineData(0, false)]
        [InlineData(1, true)]
        [InlineData(2, false)]
        [InlineData(3, false)]
        [InlineData(4, false)]
        [InlineData(5, false)]
        [InlineData(6, true)]
        public void Validated_registered_layouts_can_issue_map_requests(
            int layout, bool expected)
        {
            Assert.Equal(expected, StandaloneMapPack.IsRuntimeUsable(
                (StandaloneMapPackLayout)layout));
        }

        [Fact]
        public void Retired_startup_receipt_cannot_authorize_runtime_use()
        {
            string hashA = new string('a', 64);
            string hashB = new string('b', 64);
            string marker =
                "layout=pruned-local-v3-startup-registered-ipl\n" +
                "archive_registration=startup\n" +
                "activation=verified-startup-registration\n" +
                "receipt=allin1_maps.runtime.json\n" +
                "asset_count=15\n" +
                "archive_bytes=170810368\n" +
                "archive_sha256=" + hashA + "\n" +
                "gameconfig_sha256=" + hashB + "\n";
            string receipt =
                "{\"schema\":1,\"status\":\"verified\"," +
                "\"layout\":\"pruned-local-v3-startup-registered-ipl\"," +
                "\"edition\":\"enhanced\"," +
                "\"gameconfig_entry\":\"common/data/gameconfig.xml\"," +
                "\"asset_count\":15,\"archive_bytes\":170810368," +
                "\"archive_sha256\":\"" + hashA + "\"," +
                "\"gameconfig_sha256\":\"" + hashB + "\",\"pools\":{}}";

            Assert.False(StandaloneMapPack.IsVerifiedStartupReceipt(
                marker, receipt, 170810368, "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedStartupReceipt(
                marker, receipt, 170810367, "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedStartupReceipt(
                marker, receipt.Replace(hashA, new string('c', 64)),
                170810368, "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedStartupReceipt(
                marker.Replace("verified-startup-registration", "pending"),
                receipt, 170810368, "enhanced"));
        }

        [Fact]
        public void Reference_bridge_receipt_requires_fixed_groups_and_archive_hash()
        {
            string hash = new string('a', 64);
            string marker =
                "layout=official-reference-v2-deferred\n" +
                "archive_registration=metadata-bridge\n" +
                "activation=property-group-runtime\n" +
                "receipt=allin1_maps.runtime.json\n" +
                "group_contract=allin1-official-map-groups-v2\n" +
                "asset_count=0\n" +
                "reference_count=17\n" +
                "archive_bytes=4096\n" +
                "archive_sha256=" + hash + "\n";
            string receipt = ReferenceReceipt(hash);

            Assert.True(StandaloneMapPack.IsVerifiedReferenceBridgeReceipt(
                marker, receipt, 4096, hash, "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedReferenceBridgeReceipt(
                marker, receipt, 4095, hash, "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedReferenceBridgeReceipt(
                marker, receipt.Replace("MPTUNER_MAP_UPDATE", "GROUP_MAP"),
                4096, hash, "enhanced"));
            Assert.False(StandaloneMapPack.IsVerifiedReferenceBridgeReceipt(
                marker.Replace("reference_count=17", "reference_count=16"),
                receipt, 4096, hash, "enhanced"));
        }

        [Fact]
        public void Loading_screen_receipt_blocks_visible_runtime_group_mutation()
        {
            string receipt = VisibleRuntimeReceipt(
                DeferredMapContentGroups.Yacht,
                requiresLoadingScreen: true);

            Assert.False(
                StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    receipt, DeferredMapContentGroups.Yacht,
                    out string reason));
            Assert.Equal(
                "official_closure_requires_loading_screen:TEST_CHANGESET",
                reason);
        }

        [Fact]
        public void Receipt_must_explicitly_prove_no_loading_screen_is_required()
        {
            string safeReceipt = VisibleRuntimeReceipt(
                DeferredMapContentGroups.Harmony);
            string incompleteReceipt = safeReceipt.Replace(
                "\"requires_loading_screen\":false,", string.Empty);

            Assert.True(
                StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    safeReceipt, DeferredMapContentGroups.Harmony,
                    out string safeReason));
            Assert.Equal(string.Empty, safeReason);
            Assert.False(
                StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    incompleteReceipt, DeferredMapContentGroups.Harmony,
                    out string blockedReason));
            Assert.Equal("official_closure_loading_contract_missing",
                blockedReason);
        }

        [Theory]
        [InlineData("transition", false, "", "",
            "official_closure_loading_context:")]
        [InlineData("", true, "", "",
            "official_closure_uses_cache_loader:")]
        [InlineData("", false, "platform:/world.rpf", "",
            "official_closure_invalidates_files:")]
        [InlineData("", false, "", "platform:/world.rpf",
            "official_closure_disables_files:")]
        public void Visible_runtime_receipt_rejects_world_replacement_signals(
            string loadingContext, bool useCacheLoader, string invalidated,
            string disabled, string expectedReasonPrefix)
        {
            string receipt = VisibleRuntimeReceipt(
                DeferredMapContentGroups.Harmony,
                loadingContext: loadingContext,
                useCacheLoader: useCacheLoader,
                invalidated: invalidated,
                disabled: disabled);

            Assert.False(
                StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    receipt, DeferredMapContentGroups.Harmony,
                    out string reason));
            Assert.StartsWith(expectedReasonPrefix, reason);
        }

        [Fact]
        public void Visible_runtime_receipt_requires_exact_enabled_references()
        {
            string safe = VisibleRuntimeReceipt(
                DeferredMapContentGroups.Harmony);
            string unexpected = VisibleRuntimeReceipt(
                DeferredMapContentGroups.Harmony,
                enabledReference: "dlc_other:/%PLATFORM%/maps/other.rpf");
            string omitted = VisibleRuntimeReceipt(
                DeferredMapContentGroups.Harmony, enabledReference: "");

            Assert.True(
                StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    safe, DeferredMapContentGroups.Harmony, out _));
            Assert.False(
                StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    unexpected, DeferredMapContentGroups.Harmony,
                    out string unexpectedReason));
            Assert.StartsWith(
                "official_closure_enables_unexpected_reference:",
                unexpectedReason);
            Assert.False(
                StandaloneMapPack.IsOfficialClosureSafeForVisibleRuntimeReceipt(
                    omitted, DeferredMapContentGroups.Harmony,
                    out string omittedReason));
            Assert.StartsWith("official_closure_omits_reference:",
                omittedReason);
        }

        [Fact]
        public void Reference_source_receipt_tracks_effective_per_archive_overlays()
        {
            string root = Path.Combine(Path.GetTempPath(),
                "allin1-map-source-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                string[] identities =
                {
                    "mpheist|dlc.rpf|stock",
                    "mptuner|dlc.rpf|stock",
                    "mpbattle|dlc.rpf|stock",
                    "mpbattle|dlc1.rpf|mods",
                    "mpvinewood|dlc.rpf|stock",
                    "mp2024_02|dlc.rpf|stock",
                };
                var items = new List<string>();
                foreach (string identity in identities)
                {
                    string[] parts = identity.Split('|');
                    string relative = Path.Combine(
                        "update", "x64", "dlcpacks", parts[0], parts[1]);
                    string path = Path.Combine(root,
                        parts[2] == "mods" ? Path.Combine("mods", relative) :
                        relative);
                    Directory.CreateDirectory(Path.GetDirectoryName(path));
                    File.WriteAllText(path, identity);
                    long mtimeNs = (File.GetLastWriteTimeUtc(path) -
                        new DateTime(1970, 1, 1, 0, 0, 0,
                            DateTimeKind.Utc)).Ticks * 100L;
                    items.Add("{\"pack\":\"" + parts[0] +
                        "\",\"archive\":\"" + parts[1] +
                        "\",\"source\":\"" + parts[2] +
                        "\",\"path\":\"" +
                        (parts[2] == "mods" ? "mods/" : string.Empty) +
                        relative.Replace('\\', '/') +
                        "\",\"size\":" + new FileInfo(path).Length +
                        ",\"mtime_ns\":" + mtimeNs + "}");
                }
                string receipt = "{\"source_archives\":[" +
                    string.Join(",", items) + "]}";

                Assert.True(StandaloneMapPack.AreReferenceSourcesCurrent(
                    receipt, root));

                string lateOverride = Path.Combine(root, "mods", "update",
                    "x64", "dlcpacks", "mptuner", "dlc.rpf");
                Directory.CreateDirectory(Path.GetDirectoryName(lateOverride));
                File.WriteAllText(lateOverride, "new overlay");
                Assert.False(StandaloneMapPack.AreReferenceSourcesCurrent(
                    receipt, root));
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        private static string VisibleRuntimeReceipt(
            string group, bool requiresLoadingScreen = false,
            string loadingContext = "", bool useCacheLoader = false,
            string invalidated = "", string disabled = "",
            string enabledReference = null)
        {
            const string reference =
                "dlc_test:/%PLATFORM%/maps/property_shell.rpf";
            if (enabledReference == null) enabledReference = reference;
            return "{\"groups\":[{\"group\":\"" + group + "\"," +
                "\"references\":[\"" + reference + "\"]," +
                "\"routes\":[{\"changeset\":\"TEST_CHANGESET\"," +
                "\"requires_loading_screen\":" +
                (requiresLoadingScreen ? "true" : "false") + "," +
                "\"loading_screen_context\":\"" + loadingContext + "\"," +
                "\"use_cache_loader\":" +
                (useCacheLoader ? "true" : "false") + "," +
                "\"files_to_invalidate\":" + JsonStringList(invalidated) + "," +
                "\"files_to_disable\":" + JsonStringList(disabled) + "," +
                "\"files_to_enable\":" + JsonStringList(enabledReference) +
                "}]}]}";
        }

        private static string JsonStringList(string value) =>
            string.IsNullOrEmpty(value) ? "[]" : "[\"" + value + "\"]";

        private static string ReferenceReceipt(string hash) =>
            "{\"schema\":1,\"status\":\"verified\"," +
            "\"package_id\":\"allin1.online-content\"," +
            "\"pack_name\":\"allin1_maps\"," +
            "\"layout\":\"official-reference-v2-deferred\"," +
            "\"edition\":\"enhanced\"," +
            "\"group_contract\":\"allin1-official-map-groups-v2\"," +
            "\"asset_count\":0,\"reference_count\":17," +
            "\"archive_bytes\":4096,\"archive_sha256\":\"" + hash + "\"," +
            "\"groups\":[" +
            ReferenceGroup("grapeseed", "GRAPESEED", 3) + "," +
            ReferenceGroup("yacht", "YACHT", 6) + "," +
            ReferenceGroup("davis", "DAVIS", 2) + "," +
            ReferenceGroup("harmony", "HARMONY", 2) + "," +
            ReferenceGroup("paleto", "PALETO", 2) + "," +
            ReferenceGroup("garment_factory", "GARMENT_FACTORY", 2) +
            "]}";

        private static string ReferenceGroup(
            string property, string suffix, int references)
        {
            var values = new List<string>();
            for (int index = 0; index < references; index++)
                values.Add("\"dlc_test:/%PLATFORM%/maps/" + property +
                    index + ".rpf\"");
            return "{\"property\":\"" + property +
                "\",\"group\":\"ALLIN1_MAP_" + suffix +
                "\",\"references\":[" + string.Join(",", values) +
                "],\"routes\":" + ReferenceRoutes(property) + "}";
        }

        private static string ReferenceRoutes(string property)
        {
            switch (property)
            {
                case "grapeseed":
                    return "[{\"pack\":\"mpheist\",\"changeset\":" +
                        "\"MPHEIST_GTA5_CITYE_HOLLYWOOD_01\"}]";
                case "yacht":
                    return "[{\"pack\":\"mpheist\",\"changeset\":" +
                        "\"MPHEIST_PRE_MAP_CHANGES\"}," +
                        "{\"pack\":\"mpheist\",\"changeset\":" +
                        "\"MPHEIST_GTA5_LODLIGHTS\"}," +
                        "{\"pack\":\"mpheist\",\"changeset\":" +
                        "\"MPHEIST_GTA5_HILLS_CITYHILLS_01\"}]";
                case "davis":
                    return "[{\"pack\":\"mptuner\",\"changeset\":" +
                        "\"MPTUNER_MAP_UPDATE\"}]";
                case "harmony":
                    return "[{\"pack\":\"mpbattle\",\"changeset\":" +
                        "\"MPBATTLE_INTERIOR_ADDITIONS\"}]";
                case "paleto":
                    return "[{\"pack\":\"mpvinewood\",\"changeset\":" +
                        "\"mpVinewood_INTERIOR_ADDITIONS\"}]";
                default:
                    return "[{\"pack\":\"mp2024_02\",\"changeset\":" +
                        "\"MP2024_02_MAP_UPDATE\"}]";
            }
        }

        private static DeferredMapContentDescriptor Descriptor(
            DeferredMapProperty property, params string[] ipls) =>
            new DeferredMapContentDescriptor(property, ipls);

        private sealed class FakeBridge : IDeferredMapContentBridge
        {
            internal readonly HashSet<string> ActiveIpls =
                new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            internal readonly List<string> RequestedIpls = new List<string>();
            internal readonly List<string> RemovedIpls = new List<string>();
            internal bool ActivateOnRequest;
            internal bool FallbackSucceeds;
            internal bool RuntimeSafe = true;
            internal int RuntimeSafeAfterMilliseconds = -1;
            internal string UnsafeReason = string.Empty;
            internal int ActivationDelayMilliseconds;
            internal int ExecuteCount;
            internal int FirstRequestAtMilliseconds = -1;
            internal int RevertCount;
            internal int FallbackCount;
            internal bool ThrowOnRevert;
            internal bool IgnoreRemoveRequests;
            internal Action OnYield;
            private readonly Dictionary<string, int> _requestedAt =
                new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

            public string Edition => "test";
            public int MonotonicMilliseconds { get; private set; }
            public bool IsScreenFadedOut() => true;
            public bool IsDlcPresent(string packName) => true;

            public bool IsRuntimeSafe(out string reason)
            {
                if (!RuntimeSafe && RuntimeSafeAfterMilliseconds >= 0 &&
                    MonotonicMilliseconds >= RuntimeSafeAfterMilliseconds)
                {
                    reason = string.Empty;
                    return true;
                }
                reason = UnsafeReason;
                return RuntimeSafe;
            }

            public uint GenerateHash(string value) => 0xA11u;
            public void ExecuteGroup(uint groupHash)
            {
                ExecuteCount++;
            }
            public void RevertGroup(uint groupHash)
            {
                RevertCount++;
                if (ThrowOnRevert)
                    throw new InvalidOperationException("revert failed");
            }

            public void RequestIpl(string ipl)
            {
                RequestedIpls.Add(ipl);
                if (FirstRequestAtMilliseconds < 0)
                    FirstRequestAtMilliseconds = MonotonicMilliseconds;
                if (!ActivateOnRequest)
                    return;
                if (ActivationDelayMilliseconds <= 0)
                {
                    ActiveIpls.Add(ipl);
                    return;
                }
                if (!_requestedAt.ContainsKey(ipl))
                    _requestedAt[ipl] = MonotonicMilliseconds;
            }

            public void RemoveIpl(string ipl)
            {
                RemovedIpls.Add(ipl);
                if (!IgnoreRemoveRequests)
                    ActiveIpls.Remove(ipl);
            }

            public bool IsIplActive(string ipl)
            {
                if (!ActiveIpls.Contains(ipl) && ActivateOnRequest &&
                    _requestedAt.TryGetValue(ipl, out int requestedAt) &&
                    MonotonicMilliseconds - requestedAt >=
                        ActivationDelayMilliseconds)
                    ActiveIpls.Add(ipl);
                return ActiveIpls.Contains(ipl);
            }
            public void Yield(int milliseconds)
            {
                OnYield?.Invoke();
                MonotonicMilliseconds += Math.Max(1, milliseconds);
            }

            public bool TryActivateFallback(string[] ipls, int timeoutMs)
            {
                FallbackCount++;
                if (!FallbackSucceeds) return false;
                foreach (string ipl in ipls) ActiveIpls.Add(ipl);
                return true;
            }
        }

        private sealed class FakeLogger : IDeferredMapContentLogger
        {
            internal readonly List<string> Messages = new List<string>();

            public void Info(string message,
                IDictionary<string, object> fields) => Messages.Add(message);
            public void Warn(string message,
                IDictionary<string, object> fields) => Messages.Add(message);
            public void Error(string message, Exception exception,
                IDictionary<string, object> fields) => Messages.Add(message);
        }
    }
}
