using System.Linq;
using Xunit;

namespace RealisticSuppressors.Tests
{
    public sealed class SuppressorShotObservationTests
    {
        [Fact]
        public void AmmoDeltaCountsAQuickShotAfterShootingFlagClears()
        {
            Assert.Equal(1, RealisticSuppressorController.CountRoundsFired(
                12, 11, false, true, false));
        }

        [Fact]
        public void AmmoDeltaCountsEveryRoundInAFrame()
        {
            Assert.Equal(4, RealisticSuppressorController.CountRoundsFired(
                30, 26, true, true, false));
        }

        [Fact]
        public void WeaponChangeNeverTreatsDifferentClipsAsShots()
        {
            Assert.Equal(0, RealisticSuppressorController.CountRoundsFired(
                30, 12, false, false, true));
        }

        [Fact]
        public void ShootingEdgeFallsBackWhenAmmoCannotBeRead()
        {
            Assert.Equal(1, RealisticSuppressorController.CountRoundsFired(
                -1, -1, true, false, false));
        }

        [Theory]
        [InlineData(20f, "SUPPRESSOR 20 °C")]
        [InlineData(525.4f, "SUPPRESSOR 525 °C")]
        [InlineData(-10f, "SUPPRESSOR 20 °C")]
        [InlineData(2000f, "SUPPRESSOR 1600 °C")]
        public void TemperatureDebugUsesACompactBoundedCelsiusReadout(
            float temperature, string expected)
        {
            Assert.Equal(expected,
                RealisticSuppressorController.TemperatureDebugText(
                    temperature));
        }

        [Fact]
        public void TemperatureDebugNormalizesInvalidValuesToAmbient()
        {
            Assert.Equal("SUPPRESSOR 20 °C",
                RealisticSuppressorController.TemperatureDebugText(
                    float.NaN));
        }
    }

    public sealed class RealisticSuppressorPolicyTests
    {
        [Theory]
        [InlineData(0, 18f)]
        [InlineData(1, 23f)]
        [InlineData(2, 29f)]
        [InlineData(3, 34f)]
        [InlineData(4, 38f)]
        [InlineData(5, 26f)]
        public void Weapon_classes_keep_distinct_actionable_hearing_radii(
            int weaponClass, float expected)
        {
            Assert.Equal(expected,
                RealisticSuppressorPolicy.BaseAudibleRadius(
                    (SuppressorWeaponClass)weaponClass));
        }

        [Fact]
        public void Indoor_echo_and_repeated_fire_expand_but_cap_the_report()
        {
            Assert.Equal(29f, RealisticSuppressorPolicy.AudibleRadius(
                SuppressorWeaponClass.Rifle, 1, false), 3);
            Assert.Equal(37.7f, RealisticSuppressorPolicy.AudibleRadius(
                SuppressorWeaponClass.Rifle, 1, true), 3);
            Assert.Equal(55f, RealisticSuppressorPolicy.AudibleRadius(
                SuppressorWeaponClass.Sniper, 12, true), 3);
        }

        [Theory]
        [InlineData(1000, -1000, 3, 2, 2)]
        [InlineData(2500, 1000, 3, 2, 5)]
        [InlineData(2501, 1000, 3, 2, 2)]
        [InlineData(1100, 1000, 11, 5, 12)]
        [InlineData(1100, 1000, 4, 0, 4)]
        public void Burst_counter_accumulates_inside_a_bounded_window(
            int now, int lastShotAt, int previous, int fired,
            int expected)
        {
            Assert.Equal(expected,
                RealisticSuppressorPolicy.UpdateBurstCount(
                    now, lastShotAt, previous, fired));
        }

        [Fact]
        public void Burst_counter_handles_game_timer_rollover()
        {
            Assert.Equal(4,
                RealisticSuppressorPolicy.UpdateBurstCount(
                    int.MinValue + 10, int.MaxValue - 10, 3, 1));
        }

        [Theory]
        [InlineData(5f, 100f, 100f, 20f, false, false, false, false,
            3)]
        [InlineData(15f, 100f, 100f, 20f, false, true, false, false,
            3)]
        [InlineData(20.01f, 100f, 100f, 20f, false, true, false, false,
            0)]
        [InlineData(100f, 8f, 100f, 20f, false, false, false, false,
            2)]
        [InlineData(100f, 8.01f, 100f, 20f, false, false, false, false,
            0)]
        [InlineData(100f, 100f, 14f, 20f, false, false, false, false,
            2)]
        [InlineData(100f, 100f, 14.01f, 20f, false, false, false, false,
            0)]
        [InlineData(60f, 100f, 100f, 20f, false, false, true, true,
            4)]
        [InlineData(65.01f, 100f, 100f, 20f, false, false, true, true,
            0)]
        [InlineData(60f, 100f, 100f, 20f, false, false, true, false,
            0)]
        [InlineData(100f, 100f, 100f, 20f, true, false, false, false,
            1)]
        public void Witnesses_require_a_realistic_sound_visual_or_combat_cue(
            float shooterDistance, float projectileDistance,
            float impactDistance, float audibleRadius, bool alreadyAlerted,
            bool canHear, bool clearLos, bool facing,
            int expected)
        {
            Assert.Equal((SuppressorWitnessReason)expected,
                RealisticSuppressorPolicy.CredibleWitnessReason(
                    shooterDistance, projectileDistance, impactDistance,
                    audibleRadius, alreadyAlerted, canHear, clearLos,
                    facing));
        }

        [Fact]
        public void Invalid_distances_never_invent_a_witness()
        {
            Assert.Equal(SuppressorWitnessReason.None,
                RealisticSuppressorPolicy.CredibleWitnessReason(
                    float.NaN, float.PositiveInfinity,
                    float.PositiveInfinity, 20f, false, true, true,
                    true));
        }

        [Theory]
        [InlineData(5f, 0f, 0f)]
        [InlineData(5f, 3f, 3f)]
        [InlineData(-2f, 0f, 2f)]
        [InlineData(12f, 0f, 2f)]
        public void Bullet_crack_distance_uses_the_bounded_shot_segment(
            float pointX, float pointY, float expected)
        {
            float distance = RealisticSuppressorPolicy.DistanceToSegment(
                new SuppressorPoint(pointX, pointY, 0f),
                new SuppressorPoint(0f, 0f, 0f),
                new SuppressorPoint(10f, 0f, 0f));
            Assert.Equal(expected, distance, 3);
        }

        [Theory]
        [InlineData(true, false, false, 0, true, true, false, true)]
        [InlineData(false, false, false, 0, true, true, false, false)]
        [InlineData(true, true, false, 0, true, true, false, false)]
        [InlineData(true, false, true, 0, true, true, false, false)]
        [InlineData(true, false, false, 1, true, true, false, false)]
        [InlineData(true, false, false, 0, false, true, false, false)]
        [InlineData(true, false, false, 0, true, false, false, false)]
        [InlineData(true, false, false, 0, true, true, true, false)]
        public void Crime_is_suppressed_only_for_a_clean_unwitnessed_shot(
            bool enabled, bool mission, bool cutscene, int wanted,
            bool shooting, bool silenced, bool witness, bool expected)
        {
            Assert.Equal(expected,
                RealisticSuppressorPolicy.ShouldSuppressCrime(
                    enabled, mission, cutscene, wanted, shooting,
                    silenced, witness));
        }

        [Theory]
        [InlineData(true, false, false, 0, true, false, true)]
        [InlineData(false, false, false, 0, true, false, false)]
        [InlineData(true, true, false, 0, true, false, false)]
        [InlineData(true, false, true, 0, true, false, false)]
        [InlineData(true, false, false, 1, true, false, false)]
        [InlineData(true, false, false, 0, false, false, false)]
        [InlineData(true, false, false, 0, true, true, false)]
        public void Prearm_only_covers_a_clean_silenced_unwitnessed_state(
            bool enabled, bool mission, bool cutscene, int wanted,
            bool silenced, bool potentialWitness, bool expected)
        {
            Assert.Equal(expected,
                RealisticSuppressorPolicy.ShouldPreArmCrime(
                    enabled, mission, cutscene, wanted, silenced,
                    potentialWitness));
        }

        [Theory]
        [InlineData(0x837445AAu, true)]
        [InlineData(0xA73D4664u, true)]
        [InlineData(0xC304849Au, true)]
        [InlineData(0x65EA7EBBu, true)]
        [InlineData(0xE608B35Eu, true)]
        [InlineData(0xAC42DF71u, true)]
        [InlineData(0x9307D6FAu, true)]
        [InlineData(0x1E02B7E0u, true)]
        [InlineData(0xB99402D4u, false)] // COMPONENT_AT_MUZZLE_01
        [InlineData(0u, false)]
        public void Fallback_detection_never_treats_a_muzzle_brake_as_a_suppressor(
            uint componentHash, bool expected)
        {
            Assert.Equal(expected,
                RealisticSuppressorPolicy.IsKnownSuppressorHash(
                    componentHash));
        }
    }

    public sealed class SuppressorThermalPolicyTests
    {
        private static SuppressorThermalProfile StandardCarbine()
        {
            Assert.True(SuppressorThermalProfiles.TryGet(
                0x83BF0278u, out SuppressorThermalProfile profile));
            return profile;
        }

        [Fact]
        public void Every_supported_weapon_has_one_explicit_valid_profile()
        {
            Assert.Equal(39, SuppressorThermalProfiles.All.Count);
            var weaponHashes = new System.Collections.Generic.HashSet<uint>();
            foreach (SuppressorThermalProfile profile in
                SuppressorThermalProfiles.All)
            {
                Assert.True(weaponHashes.Add(profile.WeaponHash));
                Assert.True(RealisticSuppressorPolicy
                    .IsKnownSuppressorHash(profile.ComponentHash));
                Assert.True(profile.HeatPerShotCelsius > 0f);
                Assert.True(profile.CoolingHalfLifeSeconds > 0f);
                Assert.True(profile.DamageOnsetCelsius <
                    profile.CriticalCelsius);
                Assert.True(profile.RatedLifeRounds > 0);
            }
        }

        [Fact]
        public void Cooling_is_exponential_above_ambient()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            Assert.Equal(SuppressorThermalPolicy.AmbientCelsius,
                SuppressorThermalPolicy.CoolTemperature(
                    SuppressorThermalPolicy.AmbientCelsius,
                    120000, profile.CoolingHalfLifeSeconds), 3);
            Assert.Equal(120f,
                SuppressorThermalPolicy.CoolTemperature(
                    220f,
                    (int)(profile.CoolingHalfLifeSeconds * 1000f),
                    profile.CoolingHalfLifeSeconds), 3);
        }

        [Fact]
        public void Thirty_standard_carbine_rounds_match_research_heat_rate()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorThermalStep result = SuppressorThermalPolicy
                .ApplyShots(profile,
                    SuppressorThermalPolicy.AmbientCelsius, 1f,
                    30, true, 1f);

            Assert.Equal(146f, result.TemperatureCelsius, 3);
            Assert.Equal(30f / profile.RatedLifeRounds,
                result.DurabilityLost, 5);
        }

        [Theory]
        [InlineData("CP", 625)]
        [InlineData("SP", 525)]
        [InlineData("HP", 399)]
        [InlineData("P50", 267)]
        [InlineData("MP", 472)]
        [InlineData("PDW", 351)]
        [InlineData("L556", 304)]
        [InlineData("S556", 276)]
        [InlineData("C556", 237)]
        [InlineData("I762", 223)]
        [InlineData("F762", 169)]
        [InlineData("MAG", 111)]
        [InlineData("BMG", 63)]
        [InlineData("SG", 199)]
        public void Every_profile_has_a_deterministic_abuse_failure_point(
            string profileCode, int expectedRounds)
        {
            SuppressorThermalProfile profile = SuppressorThermalProfiles.All
                .First(value => value.ProfileCode == profileCode);

            Assert.Equal(expectedRounds, SuppressorThermalPolicy
                .ContinuousRoundsToFailure(profile, 1f));
        }

        [Fact]
        public void Durability_setting_scales_the_continuous_failure_point()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            int fragile = SuppressorThermalPolicy
                .ContinuousRoundsToFailure(profile, 0.5f);
            int standard = SuppressorThermalPolicy
                .ContinuousRoundsToFailure(profile, 1f);
            int durable = SuppressorThermalPolicy
                .ContinuousRoundsToFailure(profile, 3f);

            Assert.True(fragile < standard);
            Assert.True(standard < durable);
        }

        [Fact]
        public void Critical_temperature_causes_twenty_five_times_baseline_wear()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorThermalStep result = SuppressorThermalPolicy
                .ApplyShots(profile,
                    profile.CriticalCelsius -
                        profile.HeatPerShotCelsius,
                    1f, 1, true, 1f);

            Assert.Equal(25f / profile.RatedLifeRounds,
                result.DurabilityLost, 5);
        }

        [Fact]
        public void Rapid_fire_heats_and_wears_more_than_spaced_fire()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            float rapidTemperature =
                SuppressorThermalPolicy.AmbientCelsius;
            float rapidDurability = 1f;
            for (int round = 0; round < 140; round++)
            {
                SuppressorThermalStep step = SuppressorThermalPolicy
                    .ApplyShots(profile, rapidTemperature,
                        rapidDurability, 1, true, 1f);
                rapidTemperature = step.TemperatureCelsius;
                rapidDurability = step.Durability;
            }

            float spacedTemperature =
                SuppressorThermalPolicy.AmbientCelsius;
            float spacedDurability = 1f;
            for (int round = 0; round < 140; round++)
            {
                spacedTemperature = SuppressorThermalPolicy
                    .CoolTemperature(spacedTemperature, 15000,
                        profile.CoolingHalfLifeSeconds);
                SuppressorThermalStep step = SuppressorThermalPolicy
                    .ApplyShots(profile, spacedTemperature,
                        spacedDurability, 1, true, 1f);
                spacedTemperature = step.TemperatureCelsius;
                spacedDurability = step.Durability;
            }

            Assert.True(rapidTemperature > spacedTemperature);
            Assert.True(rapidDurability < spacedDurability);
        }

        [Fact]
        public void Disabling_breakage_preserves_heat_and_glow_without_wear()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorThermalStep result = SuppressorThermalPolicy
                .ApplyShots(profile, 500f, 0.25f,
                    100, false, 1f);

            Assert.True(result.TemperatureCelsius >
                SuppressorThermalPolicy.GlowOnsetCelsius);
            Assert.True(SuppressorThermalPolicy.GlowIntensity(
                profile, result.TemperatureCelsius) > 0f);
            Assert.Equal(0.25f, result.Durability, 5);
            Assert.Equal(0f, result.DurabilityLost, 5);
            Assert.False(result.Broke);
        }

        [Fact]
        public void Durability_scale_changes_wear_inversely()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorThermalStep shortLife = SuppressorThermalPolicy
                .ApplyShots(profile, 20f, 1f, 10, true, 0.5f);
            SuppressorThermalStep longLife = SuppressorThermalPolicy
                .ApplyShots(profile, 20f, 1f, 10, true, 3f);

            Assert.Equal(6f,
                shortLife.DurabilityLost / longLife.DurabilityLost, 3);
        }

        [Fact]
        public void Glow_has_a_physical_onset_and_clamps_at_critical()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            Assert.Equal(0f, SuppressorThermalPolicy.GlowIntensity(
                profile,
                SuppressorThermalPolicy.GlowOnsetCelsius - 0.01f));
            Assert.True(SuppressorThermalPolicy.GlowIntensity(
                profile,
                SuppressorThermalPolicy.GlowOnsetCelsius + 1f) > 0f);
            Assert.Equal(1f, SuppressorThermalPolicy.GlowIntensity(
                profile, profile.CriticalCelsius));
        }

        [Fact]
        public void Glow_visual_starts_with_the_dim_attached_overlay_level()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorGlowVisual hidden = SuppressorThermalPolicy.GlowVisual(
                profile, SuppressorThermalPolicy.GlowOnsetCelsius - 0.01f);
            SuppressorGlowVisual onset = SuppressorThermalPolicy.GlowVisual(
                profile, SuppressorThermalPolicy.GlowOnsetCelsius);
            SuppressorGlowVisual faint = SuppressorThermalPolicy.GlowVisual(
                profile, SuppressorThermalPolicy.GlowOnsetCelsius + 20f);

            Assert.False(hidden.Visible);
            Assert.False(onset.Visible);
            Assert.True(faint.Visible);
            Assert.Equal("rs_suppressor_heat_ar",
                faint.OverlayModelName);
            Assert.Equal(51, faint.Opacity);
        }

        [Fact]
        public void Glow_visual_strength_is_monotonic_to_critical()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorGlowVisual onset = SuppressorThermalPolicy.GlowVisual(
                profile, SuppressorThermalPolicy.GlowOnsetCelsius);
            SuppressorGlowVisual middle = SuppressorThermalPolicy.GlowVisual(
                profile, (SuppressorThermalPolicy.GlowOnsetCelsius +
                    profile.CriticalCelsius) * 0.5f);
            SuppressorGlowVisual critical = SuppressorThermalPolicy.GlowVisual(
                profile, profile.CriticalCelsius);
            Assert.Equal(0, onset.Opacity);
            Assert.True(middle.Opacity > onset.Opacity);
            Assert.True(critical.Opacity >= middle.Opacity);
            Assert.Equal(255, critical.Opacity);
            Assert.Equal(1f, critical.Intensity, 5);
        }

        [Theory]
        [InlineData(0f, 0)]
        [InlineData(0.01f, 51)]
        [InlineData(0.379f, 51)]
        [InlineData(0.38f, 102)]
        [InlineData(0.60f, 153)]
        [InlineData(0.80f, 204)]
        [InlineData(0.959f, 204)]
        [InlineData(0.96f, 255)]
        [InlineData(1f, 255)]
        public void Glow_opacity_holds_low_levels_until_near_critical(
            float intensity, int expectedOpacity)
        {
            Assert.Equal(expectedOpacity,
                SuppressorThermalPolicy.HeatOverlayOpacity(intensity));
        }

        [Fact]
        public void Heat_smoke_begins_above_the_profile_damage_onset()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorSmokeVisual below = SuppressorThermalPolicy
                .SmokeVisual(profile,
                    profile.DamageOnsetCelsius - 0.01f, 1f);
            SuppressorSmokeVisual onset = SuppressorThermalPolicy
                .SmokeVisual(profile, profile.DamageOnsetCelsius, 1f);
            SuppressorSmokeVisual above = SuppressorThermalPolicy
                .SmokeVisual(profile,
                    profile.DamageOnsetCelsius + 1f, 1f);

            Assert.False(below.Visible);
            Assert.False(onset.Visible);
            Assert.True(above.Visible);
            Assert.Equal(1, above.EmitterCount);
            Assert.True(above.PrimaryScale > 0f);
            Assert.True(above.Alpha > 0f);
        }

        [Fact]
        public void Heat_smoke_becomes_denser_and_adds_a_hot_emitter()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            float range = profile.CriticalCelsius -
                profile.DamageOnsetCelsius;
            SuppressorSmokeVisual warm = SuppressorThermalPolicy
                .SmokeVisual(profile,
                    profile.DamageOnsetCelsius + range * 0.10f, 1f);
            SuppressorSmokeVisual hot = SuppressorThermalPolicy
                .SmokeVisual(profile,
                    profile.DamageOnsetCelsius + range * 0.60f, 1f);
            SuppressorSmokeVisual critical = SuppressorThermalPolicy
                .SmokeVisual(profile, profile.CriticalCelsius, 1f);

            Assert.Equal(1, warm.EmitterCount);
            Assert.Equal(2, hot.EmitterCount);
            Assert.Equal(2, critical.EmitterCount);
            Assert.True(hot.Intensity > warm.Intensity);
            Assert.True(hot.PrimaryScale > warm.PrimaryScale);
            Assert.True(hot.Alpha > warm.Alpha);
            Assert.True(critical.PrimaryScale > hot.PrimaryScale);
            Assert.True(critical.SecondaryScale > hot.SecondaryScale);
            Assert.True(critical.Alpha > hot.Alpha);
            Assert.True(critical.PrimaryScale > hot.PrimaryScale * 2f);
        }

        [Fact]
        public void Critical_smoke_boost_is_smooth_and_reserved_for_high_heat()
        {
            Assert.Equal(0f, SuppressorThermalPolicy
                .CriticalSmokeBoost(0.82f), 5);
            float rising = SuppressorThermalPolicy
                .CriticalSmokeBoost(0.91f);
            Assert.InRange(rising, 0.49f, 0.51f);
            Assert.Equal(1f, SuppressorThermalPolicy
                .CriticalSmokeBoost(1f), 5);
        }

        [Fact]
        public void Secondary_heat_smoke_uses_hysteresis_to_avoid_popping()
        {
            Assert.False(SuppressorThermalPolicy
                .ShouldUseSecondarySmoke(0.59f, false));
            Assert.True(SuppressorThermalPolicy
                .ShouldUseSecondarySmoke(0.60f, false));
            Assert.True(SuppressorThermalPolicy
                .ShouldUseSecondarySmoke(0.46f, true));
            Assert.False(SuppressorThermalPolicy
                .ShouldUseSecondarySmoke(0.45f, true));
        }

        [Fact]
        public void Heat_smoke_intensity_setting_is_bounded_and_cosmetic()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorSmokeVisual minimum = SuppressorThermalPolicy
                .SmokeVisual(profile, profile.CriticalCelsius, 0.1f);
            SuppressorSmokeVisual maximum = SuppressorThermalPolicy
                .SmokeVisual(profile, profile.CriticalCelsius, 9f);
            SuppressorSmokeVisual clampedMinimum = SuppressorThermalPolicy
                .SmokeVisual(profile, profile.CriticalCelsius, 0.5f);
            SuppressorSmokeVisual clampedMaximum = SuppressorThermalPolicy
                .SmokeVisual(profile, profile.CriticalCelsius, 2f);

            Assert.Equal(clampedMinimum.PrimaryScale,
                minimum.PrimaryScale, 5);
            Assert.Equal(clampedMinimum.Alpha, minimum.Alpha, 5);
            Assert.Equal(clampedMaximum.PrimaryScale,
                maximum.PrimaryScale, 5);
            Assert.Equal(clampedMaximum.Alpha, maximum.Alpha, 5);
            Assert.Equal(minimum.Intensity, maximum.Intensity, 5);
            Assert.Equal(minimum.EmitterCount, maximum.EmitterCount);
        }

        [Fact]
        public void A_hotter_can_remains_smoky_longer_while_cooling()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            float range = profile.CriticalCelsius -
                profile.DamageOnsetCelsius;
            float warm = profile.DamageOnsetCelsius + range * 0.35f;
            float critical = profile.CriticalCelsius;
            int warmSeconds = 0;
            int criticalSeconds = 0;
            while (SuppressorThermalPolicy.SmokeIntensity(
                    profile, warm) > 0f && warmSeconds < 10000)
            {
                warm = SuppressorThermalPolicy.CoolTemperature(
                    warm, 1000, profile.CoolingHalfLifeSeconds);
                warmSeconds++;
            }
            while (SuppressorThermalPolicy.SmokeIntensity(
                    profile, critical) > 0f && criticalSeconds < 10000)
            {
                critical = SuppressorThermalPolicy.CoolTemperature(
                    critical, 1000, profile.CoolingHalfLifeSeconds);
                criticalSeconds++;
            }

            Assert.InRange(warmSeconds, 1, 9999);
            Assert.InRange(criticalSeconds, 1, 9999);
            Assert.True(criticalSeconds > warmSeconds);
        }

        [Fact]
        public void Invalid_smoke_input_is_safely_hidden()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            Assert.False(SuppressorThermalPolicy.SmokeVisual(
                profile, float.NaN, 1f).Visible);
            Assert.False(SuppressorThermalPolicy.SmokeVisual(
                null, profile.CriticalCelsius, 1f).Visible);
        }

        [Theory]
        [InlineData(0x837445AAu, "rs_suppressor_heat_ar")]
        [InlineData(0xA73D4664u, "rs_suppressor_heat_ar02")]
        [InlineData(0xC304849Au, "rs_suppressor_heat_pi")]
        [InlineData(0x65EA7EBBu, "rs_suppressor_heat_pi")]
        [InlineData(0x9307D6FAu, "rs_suppressor_heat_pi")]
        [InlineData(0x1E02B7E0u, "rs_suppressor_heat_pi")]
        [InlineData(0xE608B35Eu, "rs_suppressor_heat_sr")]
        [InlineData(0xAC42DF71u, "rs_suppressor_heat_sr03")]
        public void Every_stock_component_maps_to_a_sized_overlay(
            uint componentHash, string expectedModel)
        {
            Assert.Equal(expectedModel,
                SuppressorThermalPolicy.HeatOverlayModelName(
                    componentHash));
        }

        [Fact]
        public void Unknown_component_has_no_overlay_model()
        {
            Assert.Null(SuppressorThermalPolicy.HeatOverlayModelName(
                0xDEADBEEFu));
        }

        [Theory]
        [InlineData(true, false, true)]
        [InlineData(true, true, false)]
        [InlineData(false, false, false)]
        [InlineData(false, true, false)]
        public void Break_effect_is_latched_to_the_first_failure_only(
            bool requested, bool alreadyLogged, bool expected)
        {
            Assert.Equal(expected,
                SuppressorThermalPolicy.ShouldBeginBreakEvent(
                    requested, alreadyLogged));
        }

        [Theory]
        [InlineData(0x837445AAu, 0.222f)]
        [InlineData(0xA73D4664u, 0.195f)]
        [InlineData(0xC304849Au, 0.135f)]
        [InlineData(0x65EA7EBBu, 0.135f)]
        [InlineData(0x9307D6FAu, 0.135f)]
        [InlineData(0x1E02B7E0u, 0.135f)]
        [InlineData(0xE608B35Eu, 0.324f)]
        [InlineData(0xAC42DF71u, 0.312f)]
        public void Break_effect_uses_a_can_specific_front_cap_offset(
            uint componentHash, float expected)
        {
            Assert.Equal(expected,
                SuppressorThermalPolicy.BreakEffectAxialOffset(
                    componentHash), 3);
        }

        [Fact]
        public void Every_profile_can_place_its_break_effect_on_the_can()
        {
            Assert.All(SuppressorThermalProfiles.All, profile =>
                Assert.True(SuppressorThermalPolicy
                    .BreakEffectAxialOffset(profile.ComponentHash) > 0f,
                    profile.WeaponName));
            Assert.Equal(0f, SuppressorThermalPolicy
                .BreakEffectAxialOffset(0xDEADBEEFu));
        }

        [Fact]
        public void Batched_and_sequential_shots_are_deterministic()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            SuppressorThermalStep batch = SuppressorThermalPolicy
                .ApplyShots(profile, 500f, 1f, 10, true, 1f);
            float temperature = 500f;
            float durability = 1f;
            float lost = 0f;
            for (int round = 0; round < 10; round++)
            {
                SuppressorThermalStep step = SuppressorThermalPolicy
                    .ApplyShots(profile, temperature, durability,
                        1, true, 1f);
                temperature = step.TemperatureCelsius;
                durability = step.Durability;
                lost += step.DurabilityLost;
            }

            Assert.Equal(batch.TemperatureCelsius, temperature, 5);
            Assert.Equal(batch.Durability, durability, 5);
            Assert.Equal(batch.DurabilityLost, lost, 5);
        }

        [Fact]
        public void Invalid_or_negative_time_never_creates_heat_or_nan()
        {
            SuppressorThermalProfile profile = StandardCarbine();
            Assert.Equal(220f, SuppressorThermalPolicy.CoolTemperature(
                220f, -10, profile.CoolingHalfLifeSeconds), 3);
            float normalized = SuppressorThermalPolicy.CoolTemperature(
                float.NaN, 1000, profile.CoolingHalfLifeSeconds);
            Assert.Equal(SuppressorThermalPolicy.AmbientCelsius,
                normalized, 3);
            Assert.False(float.IsNaN(normalized));
        }
    }
}
