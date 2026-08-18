using Xunit;

namespace ALLIN1.Tests
{
    public sealed class EnhancedSmokePolicyTests
    {
        [Theory]
        [InlineData(2842195391u, 2842195391u, true)]
        [InlineData(126349499u, 2842195391u, false)]
        public void Only_the_custom_grenade_hash_is_enhanced(
            uint projectileWeaponHash, uint customWeaponHash,
            bool expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.IsCustomSmokeProjectile(
                    unchecked((int)projectileWeaponHash),
                    unchecked((int)customWeaponHash)));
        }

        [Theory]
        [InlineData(999, 1000, 1000, 23000, false)]
        [InlineData(1000, 1000, 1000, 23000, true)]
        [InlineData(4999, 1000, 5000, 23000, false)]
        [InlineData(5000, 1000, 5000, 23000, true)]
        [InlineData(23000, 1000, 23000, 23000, false)]
        public void Pulses_emit_only_inside_the_active_window(
            int now, int activateAt, int nextPulseAt, int expiresAt,
            bool expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.ShouldEmitPulse(
                    now, activateAt, nextPulseAt, expiresAt));
        }

        [Theory]
        [InlineData(0, 140)]
        [InlineData(4499, 140)]
        [InlineData(4500, 360)]
        [InlineData(39000, 360)]
        public void Supplemental_smoke_bursts_then_settles_to_a_safe_rate(
            int elapsedMs, int expectedIntervalMs)
        {
            Assert.Equal(expectedIntervalMs,
                EnhancedSmokePolicy.SupplementalPulseIntervalMs(elapsedMs));
        }

        [Theory]
        [InlineData(0, 4)]
        [InlineData(4499, 4)]
        [InlineData(4500, 2)]
        public void Supplemental_smoke_reduces_emitter_count_after_bloom(
            int elapsedMs, int expectedEmitterCount)
        {
            Assert.Equal(expectedEmitterCount,
                EnhancedSmokePolicy.SupplementalEmitterCount(elapsedMs));
        }

        [Theory]
        [InlineData(0, "red", 2.90f)]
        [InlineData(4499, "purple", 2.90f)]
        [InlineData(4500, "blue", 2.20f)]
        [InlineData(0, "white", 1.45f)]
        [InlineData(4500, "WHITE", 1.10f)]
        public void Colored_supplemental_smoke_is_twice_the_white_plume_scale(
            int elapsedMs, string colorName, float expectedScale)
        {
            Assert.Equal(expectedScale,
                EnhancedSmokePolicy.SupplementalScale(
                    elapsedMs, colorName));
        }

        [Theory]
        [InlineData(0, 2.15f)]
        [InlineData(1, 2.60f)]
        [InlineData(2, 3.05f)]
        [InlineData(3, 2.15f)]
        public void Supplemental_smoke_spreads_across_a_larger_cloud(
            int variation, float expectedRadius)
        {
            Assert.Equal(expectedRadius,
                EnhancedSmokePolicy.SupplementalRadius(variation), 3);
        }

        [Theory]
        [InlineData(0, false)]
        [InlineData(1, true)]
        [InlineData(2, false)]
        [InlineData(19, false)]
        [InlineData(20, true)]
        public void Supplemental_smoke_logging_is_sampled(
            int pulseIndex, bool expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.ShouldLogSupplementalPulse(pulseIndex));
        }

        [Theory]
        [InlineData(22999, 23000, false)]
        [InlineData(23000, 23000, true)]
        [InlineData(23001, 23000, true)]
        public void Fields_expire_at_the_end_of_their_window(
            int now, int expiresAt, bool expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.IsExpired(now, expiresAt));
        }

        [Theory]
        [InlineData(499, 300, 0.1f, 0f, 0.01f, false, true, false)]
        [InlineData(500, 299, 0.1f, 0f, 0.01f, false, true, false)]
        [InlineData(500, 300, 0.35f, 0.18f, 0.08f, false, true, true)]
        [InlineData(1200, 0, 8f, -4f, 2f, true, true, false)]
        [InlineData(500, 300, 0.1f, 0f, 0.01f, true, true, false)]
        [InlineData(500, 300, 0.1f, 0f, 0.01f, false, false, false)]
        [InlineData(500, 300, 0.1f, 0f, 0.081f, false, true, false)]
        public void Projectiles_activate_only_after_grounded_settlement(
            int elapsedMs, int stationaryMs, float speed,
            float verticalSpeed, float displacement,
            bool isInAir, bool hasCollided, bool expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.ShouldConsumeCustomProjectile(
                    elapsedMs, stationaryMs, speed,
                    verticalSpeed, displacement,
                    isInAir, hasCollided));
        }

        [Theory]
        [InlineData("white", true)]
        [InlineData("red", false)]
        [InlineData("purple", false)]
        public void Only_white_smoke_uses_the_multicomponent_primary_loop(
            string color, bool expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.ShouldUsePrimaryLoop(color));
            Assert.Equal(expected,
                EnhancedSmokePolicy.CanUseNativeFallback(color));
        }

        [Theory]
        [InlineData(8f, 1000, 2000, true)]
        [InlineData(8.01f, 1000, 2000, false)]
        [InlineData(1f, 2000, 2000, false)]
        public void Nearby_active_fields_are_deduplicated(
            float distance, int now, int expiresAt, bool expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.IsDuplicateField(
                    distance, now, expiresAt));
        }

        [Theory]
        [InlineData("red", "red")]
        [InlineData(" Purple ", "purple")]
        [InlineData("cyan", "white")]
        [InlineData(null, "white")]
        public void Player_smoke_colours_are_normalized(
            string requested, string expected)
        {
            Assert.Equal(expected,
                EnhancedSmokePolicy.NormalizeColorName(requested));
        }

        [Theory]
        [InlineData("casualty_extraction", "blue", false, "orange")]
        [InlineData("dedicated_casevac_landing", "purple", true, "orange")]
        [InlineData("smoke_grenade_detonated", "green", true, "green")]
        [InlineData("withdrawal", "red", false, "white")]
        public void Casualty_smoke_has_a_dedicated_signal_colour(
            string reason, string playerColor, bool playerOwned,
            string expected)
        {
            Assert.Equal(expected, EnhancedSmokePolicy.ColorForReason(
                reason, playerColor, playerOwned));
        }
    }
}
