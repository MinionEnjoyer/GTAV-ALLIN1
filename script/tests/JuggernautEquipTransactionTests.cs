using System;
using System.Collections.Generic;
using GTA;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class JuggernautEquipTransactionTests
    {
        [Fact]
        public void BeginDefersAllMutationUntilAnimationLoads()
        {
            var target = new FakeTarget();
            var transaction = new JuggernautEquipTransaction();

            Assert.True(transaction.Begin(target, 100));
            Assert.True(transaction.Pending);
            Assert.Empty(target.Calls);

            transaction.Tick(101);
            Assert.Equal(new[] { "preflight", "request" }, target.Calls);
            Assert.True(transaction.Pending);
            Assert.False(transaction.Active);

            transaction.Tick(102);
            Assert.Equal(new[] { "preflight", "request" }, target.Calls);

            target.AnimationLoadedValue = true;
            transaction.Tick(103);
            Assert.Equal(new[] { "preflight", "request", "preflight", "outfit", "effects", "commit" }, target.Calls);
            Assert.False(transaction.Pending);
            Assert.True(transaction.Active);
        }

        [Fact]
        public void DuplicateBeginIsRejectedWithoutTouchingOriginalRequest()
        {
            var first = new FakeTarget();
            var second = new FakeTarget();
            var transaction = new JuggernautEquipTransaction();

            Assert.True(transaction.Begin(first, 0));
            Assert.False(transaction.Begin(second, 1));
            transaction.Tick(1);

            Assert.Equal(new[] { "preflight", "request" }, first.Calls);
            Assert.Empty(second.Calls);
        }

        [Fact]
        public void TimeoutCancelsAndReleasesExactlyOnce()
        {
            var target = new FakeTarget();
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));

            transaction.Tick(1);
            transaction.Tick(JuggernautEquipTransaction.AnimationTimeoutMs + 1);
            transaction.Tick(JuggernautEquipTransaction.AnimationTimeoutMs + 2);

            Assert.False(transaction.Pending);
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
            Assert.DoesNotContain("outfit", target.Calls);
            Assert.DoesNotContain("commit", target.Calls);
        }

        [Fact]
        public void LoadedAnimationAfterDeadlineIsRejectedWithoutMutation()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));

            transaction.Tick(1);
            transaction.Tick(1 + JuggernautEquipTransaction.AnimationTimeoutMs);

            Assert.False(transaction.Pending);
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
            Assert.DoesNotContain("outfit", target.Calls);
            Assert.DoesNotContain("effects", target.Calls);
            Assert.DoesNotContain("commit", target.Calls);
        }

        [Fact]
        public void ThrowingPollCancelsPendingAndReleasesOnce()
        {
            var target = new FakeTarget();
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));
            transaction.Tick(1);
            target.ThrowAnimationLoaded = true;

            transaction.Tick(2);
            transaction.Tick(3);

            Assert.False(transaction.Pending);
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
            Assert.DoesNotContain("outfit", target.Calls);
        }

        [Fact]
        public void ThrowingBeginSafetyGetterIsRejectedWithoutPendingState()
        {
            var target = new FakeTarget { ThrowSafe = true };
            var transaction = new JuggernautEquipTransaction();

            Assert.False(transaction.Begin(target, 0));
            Assert.False(transaction.Pending);
            Assert.False(transaction.Active);
            Assert.Empty(target.Calls);
        }

        [Fact]
        public void ReplacementOrDeadTargetCancelsWithoutRestore()
        {
            var target = new FakeTarget();
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));
            transaction.Tick(1);

            target.SamePlayer = false;
            transaction.Tick(2);

            Assert.False(transaction.Pending);
            Assert.Equal(1, target.ReleaseCount);
            Assert.DoesNotContain("restore:rollback", target.Calls);
            Assert.DoesNotContain("restore:remove", target.Calls);
        }

        [Fact]
        public void CommitRechecksGateAfterFreshCapture()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            target.OnPreflight = count =>
            {
                if (count == 2) target.CanCommitValue = false;
            };
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));

            transaction.Tick(1);
            transaction.Tick(2);

            Assert.False(transaction.Pending);
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
            Assert.DoesNotContain("outfit", target.Calls);
        }

        [Fact]
        public void EffectFailureRollsBackOnlyTheSameSafeTarget()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            target.ThrowEffects = true;
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));

            transaction.Tick(1);
            transaction.Tick(2);

            Assert.Equal(new[] { "preflight", "request", "preflight", "outfit", "effects", "restore:rollback", "release" }, target.Calls);
            Assert.False(transaction.Pending);
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
            Assert.DoesNotContain("commit", target.Calls);
        }

        [Fact]
        public void PartialOutfitFailureRollsBackBecauseMutationStartsBeforeFirstSetter()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            target.ThrowOutfit = true;
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));

            transaction.Tick(1);
            transaction.Tick(2);

            Assert.Equal(new[] { "preflight", "request", "preflight", "outfit", "restore:rollback", "release" }, target.Calls);
            Assert.False(transaction.Pending);
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
        }

        [Fact]
        public void UnsafeRollbackNeverTouchesReplacementTarget()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            target.OnEffects = () => target.SamePlayer = false;
            target.ThrowEffects = true;
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));

            transaction.Tick(1);
            transaction.Tick(2);

            Assert.DoesNotContain("restore:rollback", target.Calls);
            Assert.Equal(1, target.ReleaseCount);
        }

        [Fact]
        public void RemoveRestoresOnlySafeActiveTargetAndReleasesOnce()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            var transaction = Activate(target);

            Assert.True(transaction.Remove());
            Assert.True(transaction.Remove());

            Assert.Contains("restore:remove", target.Calls);
            Assert.Equal(1, target.ReleaseCount);
            Assert.False(transaction.Active);
        }

        [Fact]
        public void FailedRemovalRetainsActiveStateAndCanRetrySafely()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            target.ThrowRestore = true;
            var transaction = Activate(target);

            Assert.False(transaction.Remove());
            Assert.True(transaction.Active);
            Assert.Equal(0, target.ReleaseCount);
            Assert.Contains("restore:remove", target.Calls);

            target.ThrowRestore = false;
            Assert.True(transaction.Remove());
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
        }

        [Fact]
        public void TemporaryUnsafeRemovalDefersWithoutRestoreOrRelease()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            var transaction = Activate(target);
            target.Safe = false;

            Assert.False(transaction.Remove());
            Assert.True(transaction.Active);
            Assert.DoesNotContain("restore:remove", target.Calls);
            Assert.Equal(0, target.ReleaseCount);

            target.Safe = true;
            Assert.True(transaction.Remove());
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
        }

        [Fact]
        public void ReplacementRemovalDropsStateWithoutClaimingSuccessfulRestore()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            var transaction = Activate(target);
            target.SamePlayer = false;

            Assert.False(transaction.Remove());
            Assert.False(transaction.Active);
            Assert.DoesNotContain("restore:remove", target.Calls);
            Assert.Equal(1, target.ReleaseCount);
        }

        [Fact]
        public void ClearDropsActiveStateWithoutNativeRestore()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            var transaction = Activate(target);

            transaction.Clear("character_switch");

            Assert.DoesNotContain("restore:remove", target.Calls);
            Assert.DoesNotContain("restore:rollback", target.Calls);
            Assert.Equal(1, target.ReleaseCount);
            Assert.False(transaction.Active);
        }

        [Fact]
        public void ActiveReplacementIsDroppedButTransientUnsafeStateIsRetained()
        {
            var target = new FakeTarget { AnimationLoadedValue = true };
            var transaction = Activate(target);

            target.Safe = false;
            transaction.Tick(3);
            Assert.True(transaction.Active);
            Assert.Equal(0, target.ReleaseCount);

            target.SamePlayer = false;
            transaction.Tick(4);
            Assert.False(transaction.Active);
            Assert.Equal(1, target.ReleaseCount);
            Assert.DoesNotContain("restore:remove", target.Calls);
        }

        [Fact]
        public void SupportedVariationPlansHaveUniquePositiveEntries()
        {
            foreach (PedHash character in new[] {
                PedHash.Michael, PedHash.Franklin, PedHash.Trevor })
            {
                JuggernautVariation[] plan =
                    JuggernautVariation.ForCharacter(character);
                Assert.NotEmpty(plan);
                var slots = new HashSet<string>();
                foreach (JuggernautVariation item in plan)
                {
                    Assert.True(slots.Add((item.Prop ? "p:" : "c:") + item.Slot));
                    Assert.True(JuggernautVariation.ValidIndices(
                        item.Drawable, item.Texture, item.Drawable + 1,
                        item.Texture + 1));
                }
            }
        }

        [Fact]
        public void UnsupportedCharacterHasNoOutfitPlan()
        {
            Assert.Empty(JuggernautVariation.ForCharacter((PedHash)123456));
        }

        [Fact]
        public void VariationValidationRejectsZeroAndNegativeCountsOrIndices()
        {
            Assert.False(JuggernautVariation.ValidIndices(0, 0, 0, 1));
            Assert.False(JuggernautVariation.ValidIndices(0, 0, 1, 0));
            Assert.False(JuggernautVariation.ValidIndices(-1, 0, 1, 1));
            Assert.False(JuggernautVariation.ValidIndices(0, -1, 1, 1));
            Assert.False(JuggernautVariation.ValidIndices(1, 0, 1, 1));
            Assert.False(JuggernautVariation.ValidIndices(0, 1, 1, 1));
        }

        private static JuggernautEquipTransaction Activate(FakeTarget target)
        {
            var transaction = new JuggernautEquipTransaction();
            Assert.True(transaction.Begin(target, 0));
            transaction.Tick(1);
            transaction.Tick(2);
            Assert.True(transaction.Active);
            return transaction;
        }

        private sealed class FakeTarget : IJuggernautEquipTarget
        {
            internal readonly List<string> Calls = new List<string>();
            internal bool Safe = true;
            internal bool SamePlayer = true;
            internal bool AnimationLoadedValue;
            internal bool CanCommitValue = true;
            internal bool ThrowSafe;
            internal bool ThrowAnimationLoaded;
            internal bool ThrowOutfit;
            internal bool ThrowEffects;
            internal bool ThrowRestore;
            internal int ReleaseCount;
            internal int PreflightCount;
            internal Action<int> OnPreflight;
            internal Action OnEffects;

            public bool IsSafe
            {
                get
                {
                    if (ThrowSafe) throw new InvalidOperationException("safe");
                    return Safe;
                }
            }
            public bool IsSamePlayer => SamePlayer;
            public bool AnimationLoaded
            {
                get
                {
                    if (ThrowAnimationLoaded)
                        throw new InvalidOperationException("animation_loaded");
                    return AnimationLoadedValue;
                }
            }
            public bool CanCommit => CanCommitValue;

            public void PreflightAndCapture()
            {
                Calls.Add("preflight");
                OnPreflight?.Invoke(++PreflightCount);
            }

            public void RequestAnimation() { Calls.Add("request"); }
            public void ApplyOutfit()
            {
                Calls.Add("outfit");
                if (ThrowOutfit) throw new InvalidOperationException("outfit");
            }
            public void ApplyEffects()
            {
                Calls.Add("effects");
                OnEffects?.Invoke();
                if (ThrowEffects) throw new InvalidOperationException("effects");
            }
            public void Restore(bool rollback)
            {
                Calls.Add(rollback ? "restore:rollback" : "restore:remove");
                if (ThrowRestore) throw new InvalidOperationException("restore");
            }
            public void Commit() { Calls.Add("commit"); }
            public void ReleaseAnimation()
            {
                Calls.Add("release");
                ReleaseCount++;
            }
            public void Trace(string stage, string detail) { }
        }
    }
}
