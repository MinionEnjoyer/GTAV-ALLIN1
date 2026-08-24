using System;
using System.IO;
using Xunit;

namespace RealisticSuppressors.Tests
{
    public sealed class SuppressorStatePolicyTests
    {
        [Theory]
        [InlineData(-0.25f, 0f)]
        [InlineData(0f, 0f)]
        [InlineData(0.35f, 0.35f)]
        [InlineData(1f, 1f)]
        [InlineData(1.25f, 1f)]
        public void DurabilityIsClampedToPhysicalCondition(
            float value, float expected)
        {
            Assert.Equal(expected,
                SuppressorStatePolicy.ClampDurability(value), 5);
        }

        [Fact]
        public void InvalidDurabilityDefaultsToNewCondition()
        {
            Assert.Equal(SuppressorStatePolicy.NewCondition,
                SuppressorStatePolicy.ClampDurability(float.NaN));
        }

        [Fact]
        public void ComponentKeysAreStableAndCaseInsensitive()
        {
            Assert.Equal("WEAPON_CARBINERIFLE:837445AA",
                SuppressorStatePolicy.ComponentKey(
                    " weapon_carbinerifle ", 0x837445AAu));
        }

        [Theory]
        [InlineData(false, 0f, true, true, false)]
        [InlineData(true, 0f, true, false, true)]
        [InlineData(true, 0f, false, true, true)]
        [InlineData(true, 0.35f, true, false, true)]
        [InlineData(true, 0.35f, false, true, true)]
        [InlineData(true, 0.35f, false, false, false)]
        public void ReplacementRequiresARealAttachmentLifecycleSignal(
            bool broken, float persisted, bool purchaseObserved,
            bool observedAbsentAfterBreak, bool expected)
        {
            Assert.Equal(expected,
                SuppressorStatePolicy.IsReplacementAttachment(
                    broken, persisted, purchaseObserved,
                    observedAbsentAfterBreak));
        }
    }

    public sealed class SuppressorStateStoreTests
    {
        private const uint Suppressor = 0x837445AAu;
        private const uint OtherSuppressor = 0xA73D4664u;

        [Fact]
        public void StateIsIsolatedByCharacterWeaponAndComponent()
        {
            using (var fixture = new StateFixture())
            {
                var store = new SuppressorStateStore(fixture.StatePath);

                Assert.True(store.SetDurability("Michael",
                    "WEAPON_CARBINERIFLE", Suppressor, 0.4f));
                Assert.Equal(0.4f, store.GetDurability("michael",
                    "weapon_carbinerifle", Suppressor), 5);
                Assert.Equal(1f, store.GetDurability("franklin",
                    "WEAPON_CARBINERIFLE", Suppressor), 5);
                Assert.Equal(1f, store.GetDurability("michael",
                    "WEAPON_ASSAULTRIFLE", Suppressor), 5);
                Assert.Equal(1f, store.GetDurability("michael",
                    "WEAPON_CARBINERIFLE", OtherSuppressor), 5);
            }
        }

        [Fact]
        public void CommitPersistsConditionForANewStoreInstance()
        {
            using (var fixture = new StateFixture())
            {
                var first = new SuppressorStateStore(fixture.StatePath);
                Assert.True(first.SetDurability("Trevor",
                    "WEAPON_SNIPERRIFLE", Suppressor, 0.27f));
                Assert.True(first.Dirty);

                first.Commit();

                Assert.False(first.Dirty);
                Assert.True(File.Exists(fixture.StatePath));
                var reloaded = new SuppressorStateStore(
                    fixture.StatePath);
                Assert.Equal(0.27f, reloaded.GetDurability("trevor",
                    "weapon_sniperrifle", Suppressor), 5);
                Assert.False(reloaded.Dirty);
            }
        }

        [Fact]
        public void DiscardRestoresTheLastCommittedSnapshot()
        {
            using (var fixture = new StateFixture())
            {
                var store = new SuppressorStateStore(fixture.StatePath);
                store.SetDurability("Franklin", "WEAPON_PISTOL",
                    Suppressor, 0.8f);
                store.Commit();
                int originalGeneration = store.Generation;

                store.SetDurability("Franklin", "WEAPON_PISTOL",
                    Suppressor, 0.1f);
                Assert.Equal(0.1f, store.GetDurability("franklin",
                    "WEAPON_PISTOL", Suppressor), 5);

                store.Discard();

                Assert.Equal(0.8f, store.GetDurability("franklin",
                    "WEAPON_PISTOL", Suppressor), 5);
                Assert.False(store.Dirty);
                Assert.Equal(originalGeneration + 1,
                    store.Generation);
            }
        }

        [Fact]
        public void CorruptStateFallsBackToNewCondition()
        {
            using (var fixture = new StateFixture())
            {
                Directory.CreateDirectory(fixture.Root);
                File.WriteAllText(fixture.StatePath,
                    "{ this is not valid json");

                var store = new SuppressorStateStore(fixture.StatePath);

                Assert.Equal(1f, store.GetDurability("michael",
                    "WEAPON_CARBINERIFLE", Suppressor), 5);
                Assert.False(store.Dirty);
            }
        }

        [Fact]
        public void InvalidIdentityCannotCreatePersistentState()
        {
            using (var fixture = new StateFixture())
            {
                var store = new SuppressorStateStore(fixture.StatePath);

                Assert.False(store.SetDurability("npc",
                    "WEAPON_CARBINERIFLE", Suppressor, 0f));
                Assert.False(store.SetDurability("Michael", " ",
                    Suppressor, 0f));
                Assert.False(store.Dirty);
                store.Commit();
                Assert.False(File.Exists(fixture.StatePath));
            }
        }

        private sealed class StateFixture : IDisposable
        {
            internal StateFixture()
            {
                Root = Path.Combine(Path.GetTempPath(),
                    "RealisticSuppressors.Tests",
                    Guid.NewGuid().ToString("N"));
                StatePath = Path.Combine(Root, "condition.json");
            }

            internal string Root { get; }
            internal string StatePath { get; }

            public void Dispose()
            {
                if (Directory.Exists(Root))
                    Directory.Delete(Root, true);
            }
        }
    }
}
