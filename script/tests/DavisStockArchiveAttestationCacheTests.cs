using System;
using System.Threading;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class DavisStockArchiveAttestationCacheTests
    {
        private static readonly string ShaA = new string('a', 64);
        private static readonly string ShaB = new string('b', 64);

        [Fact]
        public void Concurrent_warmups_share_one_background_verification()
        {
            var cache = new AsyncSourceArchiveAttestationCache();
            SourceArchiveAttestationIdentity identity = Identity(
                size: 100, mtime: 200, sha: ShaA);
            int checks = 0;
            using (var entered = new ManualResetEventSlim(false))
            using (var release = new ManualResetEventSlim(false))
            {
                Assert.True(cache.Begin(identity, current =>
                {
                    Interlocked.Increment(ref checks);
                    entered.Set();
                    release.Wait(TimeSpan.FromSeconds(5));
                    return true;
                }));
                Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));

                Assert.False(cache.Begin(identity, current =>
                {
                    Interlocked.Increment(ref checks);
                    return true;
                }));
                Assert.False(cache.IsCompletedVerified(identity));
                Assert.Equal(1, Volatile.Read(ref checks));

                release.Set();
                Assert.True(SpinWait.SpinUntil(
                    () => cache.IsCompletedVerified(identity), 5000));
                Assert.Equal(1, Volatile.Read(ref checks));
            }
        }

        [Fact]
        public void Failed_or_pending_verification_remains_fail_closed()
        {
            var cache = new AsyncSourceArchiveAttestationCache();
            SourceArchiveAttestationIdentity identity = Identity(
                size: 100, mtime: 200, sha: ShaA);
            using (var entered = new ManualResetEventSlim(false))
            using (var release = new ManualResetEventSlim(false))
            {
                cache.Begin(identity, current =>
                {
                    entered.Set();
                    release.Wait(TimeSpan.FromSeconds(5));
                    return false;
                });
                Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
                Assert.False(cache.IsCompletedVerified(identity));
                release.Set();
                Assert.True(SpinWait.SpinUntil(
                    () => cache.IsCompleted(identity), 5000));
                Assert.False(cache.IsCompletedVerified(identity));
            }
        }

        [Fact]
        public void Any_identity_change_invalidates_the_verified_result()
        {
            var cache = new AsyncSourceArchiveAttestationCache();
            SourceArchiveAttestationIdentity original = Identity(
                size: 100, mtime: 200, sha: ShaA);
            Assert.True(cache.Begin(original, current => true));
            Assert.True(SpinWait.SpinUntil(
                () => cache.IsCompletedVerified(original), 5000));

            SourceArchiveAttestationIdentity changedPath =
                new SourceArchiveAttestationIdentity(
                    System.IO.Path.Combine(System.IO.Path.GetTempPath(),
                        "different.rpf"), 100, 200, ShaA);
            SourceArchiveAttestationIdentity changedSize = Identity(
                size: 101, mtime: 200, sha: ShaA);
            SourceArchiveAttestationIdentity changedMtime = Identity(
                size: 100, mtime: 201, sha: ShaA);
            SourceArchiveAttestationIdentity changedHash = Identity(
                size: 100, mtime: 200, sha: ShaB);

            Assert.False(cache.IsCompletedVerified(changedPath));
            Assert.False(cache.IsCompletedVerified(changedSize));
            Assert.False(cache.IsCompletedVerified(changedMtime));
            Assert.False(cache.IsCompletedVerified(changedHash));

            using (var release = new ManualResetEventSlim(false))
            {
                Assert.True(cache.Begin(changedMtime, current =>
                {
                    release.Wait(TimeSpan.FromSeconds(5));
                    return true;
                }));
                Assert.False(cache.IsCompletedVerified(original));
                Assert.False(cache.IsCompletedVerified(changedMtime));
                release.Set();
                Assert.True(SpinWait.SpinUntil(
                    () => cache.IsCompletedVerified(changedMtime), 5000));
            }
        }

        [Fact]
        public void Stale_worker_cannot_authorize_a_new_identity()
        {
            var cache = new AsyncSourceArchiveAttestationCache();
            SourceArchiveAttestationIdentity first = Identity(
                size: 100, mtime: 200, sha: ShaA);
            SourceArchiveAttestationIdentity second = Identity(
                size: 100, mtime: 201, sha: ShaA);
            using (var firstEntered = new ManualResetEventSlim(false))
            using (var releaseFirst = new ManualResetEventSlim(false))
            using (var releaseSecond = new ManualResetEventSlim(false))
            {
                cache.Begin(first, current =>
                {
                    firstEntered.Set();
                    releaseFirst.Wait(TimeSpan.FromSeconds(5));
                    return true;
                });
                Assert.True(firstEntered.Wait(TimeSpan.FromSeconds(5)));
                cache.Begin(second, current =>
                {
                    releaseSecond.Wait(TimeSpan.FromSeconds(5));
                    return true;
                });

                releaseFirst.Set();
                Thread.Sleep(50);
                Assert.False(cache.IsCompletedVerified(first));
                Assert.False(cache.IsCompletedVerified(second));

                releaseSecond.Set();
                Assert.True(SpinWait.SpinUntil(
                    () => cache.IsCompletedVerified(second), 5000));
                Assert.False(cache.IsCompletedVerified(first));
            }
        }

        private static SourceArchiveAttestationIdentity Identity(
            long size, long mtime, string sha) =>
            new SourceArchiveAttestationIdentity(
                System.IO.Path.Combine(System.IO.Path.GetTempPath(),
                    "mptuner", "dlc.rpf"), size, mtime, sha);
    }
}
