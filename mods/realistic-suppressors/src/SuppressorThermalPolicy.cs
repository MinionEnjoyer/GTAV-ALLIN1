// SuppressorThermalPolicy.cs -- deterministic, research-calibrated heat and
// durability model for every stock GTA V weapon that accepts a removable
// suppressor. Calibration and primary sources: docs/realistic-suppressors.md.

using System;
using System.Collections.Generic;

namespace RealisticSuppressors
{
    internal enum SuppressorHeatStage
    {
        Normal,
        Damaging,
        Glowing,
        Critical,
    }

    internal sealed class SuppressorThermalProfile
    {
        internal SuppressorThermalProfile(
            string weaponName, uint weaponHash, uint componentHash,
            SuppressorWeaponClass weaponClass, string profileCode,
            string thermalBasis, float heatPerShotCelsius,
            float coolingHalfLifeSeconds, float damageOnsetCelsius,
            float criticalCelsius, int ratedLifeRounds)
        {
            WeaponName = weaponName;
            WeaponHash = weaponHash;
            ComponentHash = componentHash;
            WeaponClass = weaponClass;
            ProfileCode = profileCode;
            ThermalBasis = thermalBasis;
            HeatPerShotCelsius = heatPerShotCelsius;
            CoolingHalfLifeSeconds = coolingHalfLifeSeconds;
            DamageOnsetCelsius = damageOnsetCelsius;
            CriticalCelsius = criticalCelsius;
            RatedLifeRounds = ratedLifeRounds;
        }

        internal string WeaponName { get; }
        internal uint WeaponHash { get; }
        internal uint ComponentHash { get; }
        internal SuppressorWeaponClass WeaponClass { get; }
        internal string ProfileCode { get; }
        internal string ThermalBasis { get; }
        internal float HeatPerShotCelsius { get; }
        internal float CoolingHalfLifeSeconds { get; }
        internal float DamageOnsetCelsius { get; }
        internal float CriticalCelsius { get; }
        internal int RatedLifeRounds { get; }
    }

    internal readonly struct SuppressorThermalStep
    {
        internal SuppressorThermalStep(
            float temperatureCelsius, float durability,
            float durabilityLost)
        {
            TemperatureCelsius = temperatureCelsius;
            Durability = durability;
            DurabilityLost = durabilityLost;
        }

        internal float TemperatureCelsius { get; }
        internal float Durability { get; }
        internal float DurabilityLost { get; }
        internal bool Broke => Durability <= 0f;
    }

    internal readonly struct SuppressorGlowVisual
    {
        internal SuppressorGlowVisual(
            bool visible, float intensity, string overlayModelName,
            int opacity)
        {
            Visible = visible;
            Intensity = intensity;
            OverlayModelName = overlayModelName;
            Opacity = opacity;
        }

        internal bool Visible { get; }
        internal float Intensity { get; }
        internal string OverlayModelName { get; }
        internal int Opacity { get; }
    }

    internal readonly struct SuppressorSmokeVisual
    {
        internal SuppressorSmokeVisual(
            bool visible, float intensity, float primaryScale,
            float secondaryScale, float alpha, int emitterCount)
        {
            Visible = visible;
            Intensity = intensity;
            PrimaryScale = primaryScale;
            SecondaryScale = secondaryScale;
            Alpha = alpha;
            EmitterCount = emitterCount;
        }

        internal bool Visible { get; }
        internal float Intensity { get; }
        internal float PrimaryScale { get; }
        internal float SecondaryScale { get; }
        internal float Alpha { get; }
        internal int EmitterCount { get; }
    }

    internal static class SuppressorThermalPolicy
    {
        internal const float AmbientCelsius = 20f;
        internal const float GlowOnsetCelsius = 525f;
        internal const float MaximumTrackedCelsius = 1600f;
        internal const float SecondarySmokeStartIntensity = 0.60f;
        internal const float SecondarySmokeStopIntensity = 0.45f;
        internal const float CriticalSmokeBoostOnset = 0.82f;
        private const float HotWearFactor = 24f;

        internal static float CoolTemperature(
            float temperatureCelsius, int elapsedMilliseconds,
            float coolingHalfLifeSeconds)
        {
            float temperature = ClampFinite(
                temperatureCelsius, AmbientCelsius,
                MaximumTrackedCelsius, AmbientCelsius);
            if (elapsedMilliseconds <= 0 ||
                coolingHalfLifeSeconds <= 0f)
                return temperature;
            double halfLives = elapsedMilliseconds /
                (coolingHalfLifeSeconds * 1000d);
            double decay = Math.Pow(0.5d, halfLives);
            return AmbientCelsius +
                (temperature - AmbientCelsius) * (float)decay;
        }

        internal static SuppressorThermalStep ApplyShots(
            SuppressorThermalProfile profile,
            float temperatureCelsius, float durability,
            int roundsFired, bool breakageEnabled,
            float durabilityScale)
        {
            if (profile == null)
                return new SuppressorThermalStep(
                    AmbientCelsius, Clamp01(durability), 0f);
            float temperature = ClampFinite(
                temperatureCelsius, AmbientCelsius,
                MaximumTrackedCelsius, AmbientCelsius);
            float remaining = Clamp01(durability);
            int rounds = Math.Max(0, Math.Min(100, roundsFired));
            float scale = ClampFinite(
                durabilityScale, 0.1f, 10f, 1f);
            float lost = 0f;
            for (int round = 0; round < rounds; round++)
            {
                temperature = Math.Min(MaximumTrackedCelsius,
                    temperature + profile.HeatPerShotCelsius);
                if (!breakageEnabled || remaining <= 0f) continue;
                float hotRatio = DamageRatio(profile, temperature);
                float wearMultiplier = 1f +
                    HotWearFactor * hotRatio * hotRatio;
                float wear = wearMultiplier /
                    (Math.Max(1, profile.RatedLifeRounds) * scale);
                wear = Math.Min(remaining, wear);
                remaining -= wear;
                lost += wear;
            }
            return new SuppressorThermalStep(
                temperature, Clamp01(remaining), lost);
        }

        internal static float DamageRatio(
            SuppressorThermalProfile profile, float temperatureCelsius)
        {
            if (profile == null) return 0f;
            float range = Math.Max(1f,
                profile.CriticalCelsius - profile.DamageOnsetCelsius);
            return Math.Max(0f,
                (temperatureCelsius - profile.DamageOnsetCelsius) /
                    range);
        }

        internal static SuppressorHeatStage HeatStage(
            SuppressorThermalProfile profile, float temperatureCelsius)
        {
            if (profile == null ||
                temperatureCelsius < profile.DamageOnsetCelsius)
                return SuppressorHeatStage.Normal;
            if (temperatureCelsius >= profile.CriticalCelsius)
                return SuppressorHeatStage.Critical;
            if (temperatureCelsius >= GlowOnsetCelsius)
                return SuppressorHeatStage.Glowing;
            return SuppressorHeatStage.Damaging;
        }

        internal static float GlowIntensity(
            SuppressorThermalProfile profile, float temperatureCelsius)
        {
            if (profile == null ||
                temperatureCelsius < GlowOnsetCelsius) return 0f;
            float range = Math.Max(1f,
                profile.CriticalCelsius - GlowOnsetCelsius);
            return Math.Min(1f, Math.Max(0f,
                (temperatureCelsius - GlowOnsetCelsius) / range));
        }

        internal static SuppressorGlowVisual GlowVisual(
            SuppressorThermalProfile profile, float temperatureCelsius)
        {
            if (profile == null || temperatureCelsius <= GlowOnsetCelsius)
                return new SuppressorGlowVisual(
                    false, 0f, null, 0);

            float physical = GlowIntensity(profile, temperatureCelsius);
            string modelName = HeatOverlayModelName(profile.ComponentHash);
            if (modelName == null)
                return new SuppressorGlowVisual(
                    false, physical, null, 0);

            return new SuppressorGlowVisual(
                true, physical, modelName,
                HeatOverlayOpacity(physical));
        }

        internal static float SmokeIntensity(
            SuppressorThermalProfile profile, float temperatureCelsius)
        {
            if (profile == null) return 0f;
            float temperature = ClampFinite(
                temperatureCelsius, AmbientCelsius,
                MaximumTrackedCelsius, AmbientCelsius);
            if (temperature <= profile.DamageOnsetCelsius) return 0f;
            float range = Math.Max(1f,
                profile.CriticalCelsius - profile.DamageOnsetCelsius);
            return Clamp01(
                (temperature - profile.DamageOnsetCelsius) / range);
        }

        internal static SuppressorSmokeVisual SmokeVisual(
            SuppressorThermalProfile profile, float temperatureCelsius,
            float intensityScale)
        {
            float physical = SmokeIntensity(profile, temperatureCelsius);
            if (physical <= 0f)
                return new SuppressorSmokeVisual(
                    false, 0f, 0f, 0f, 0f, 0);

            // The stock barrel-smoke effect already owns particle lifetime
            // and buoyancy. Scaling its loop makes the plume denser, while a
            // second emitter along the hot can adds the long, turbulent trail
            // only at sustained high temperatures. A hotter can also remains
            // above the smoke onset longer as the thermal model cools.
            float userScale = ClampFinite(
                intensityScale, 0.5f, 2f, 1f);
            float eased = SmoothStep(physical);
            float density = (float)Math.Sqrt(eased);
            float criticalBoost = CriticalSmokeBoost(physical);
            float alpha = Math.Min(1f,
                (0.04f + 0.56f * density +
                    0.40f * criticalBoost) *
                (float)Math.Sqrt(userScale));
            float primaryScale = Math.Min(2.75f,
                (0.18f + 0.62f * eased +
                    0.72f * criticalBoost) * userScale);
            int emitterCount = ShouldUseSecondarySmoke(
                physical, false) ? 2 : 1;
            float secondaryScale = Math.Min(2.25f,
                (0.16f + 0.48f * eased +
                    0.58f * criticalBoost) * userScale);
            return new SuppressorSmokeVisual(
                true, physical, primaryScale,
                secondaryScale, alpha, emitterCount);
        }

        internal static bool ShouldUseSecondarySmoke(
            float physicalIntensity, bool alreadyRunning)
        {
            float physical = ClampFinite(
                physicalIntensity, 0f, 1f, 0f);
            return alreadyRunning
                ? physical > SecondarySmokeStopIntensity
                : physical >= SecondarySmokeStartIntensity;
        }

        internal static float CriticalSmokeBoost(float physicalIntensity)
        {
            float physical = ClampFinite(
                physicalIntensity, 0f, 1f, 0f);
            float range = 1f - CriticalSmokeBoostOnset;
            return SmoothStep((physical - CriticalSmokeBoostOnset) /
                Math.Max(0.001f, range));
        }

        internal static string HeatOverlayModelName(uint componentHash)
        {
            switch (componentHash)
            {
                case 0x837445AA: // w_at_ar_supp
                    return "rs_suppressor_heat_ar";
                case 0xA73D4664: // w_at_ar_supp_02
                    return "rs_suppressor_heat_ar02";
                case 0xC304849A: // w_at_pi_supp
                case 0x65EA7EBB: // w_at_pi_supp_02
                case 0x9307D6FA: // w_pi_ceramic_supp
                case 0x1E02B7E0: // w_pi_pistol_xm3_supp
                    return "rs_suppressor_heat_pi";
                case 0xE608B35E: // w_at_sr_supp
                    return "rs_suppressor_heat_sr";
                case 0xAC42DF71: // w_at_sr_supp_03
                    return "rs_suppressor_heat_sr03";
                default:
                    return null;
            }
        }

        internal static bool ShouldBeginBreakEvent(
            bool requested, bool alreadyLogged)
        {
            return requested && !alreadyLogged;
        }

        internal static float BreakEffectAxialOffset(uint componentHash)
        {
            // Local +X distances place the cosmetic failure burst just
            // inside each suppressor's front cap. They match the authored
            // heat-sleeve lengths while leaving the weapon and player clear.
            switch (componentHash)
            {
                case 0x837445AA: // w_at_ar_supp
                    return 0.222f;
                case 0xA73D4664: // w_at_ar_supp_02
                    return 0.195f;
                case 0xC304849A: // w_at_pi_supp
                case 0x65EA7EBB: // w_at_pi_supp_02
                case 0x9307D6FA: // w_pi_ceramic_supp
                case 0x1E02B7E0: // w_pi_pistol_xm3_supp
                    return 0.135f;
                case 0xE608B35E: // w_at_sr_supp
                    return 0.324f;
                case 0xAC42DF71: // w_at_sr_supp_03
                    return 0.312f;
                default:
                    return 0f;
            }
        }

        internal static int HeatOverlayOpacity(float physicalIntensity)
        {
            float physical = Clamp01(physicalIntensity);
            if (physical <= 0f) return 0;

            // SET_ENTITY_ALPHA is quantized by GTA to five useful visible
            // levels. Hold each lower level longer so the texture's bright
            // center appears first and the shoulders spread toward the ends
            // instead of the whole can becoming opaque midway to critical.
            int level = physical >= 0.96f ? 5 :
                physical >= 0.80f ? 4 :
                physical >= 0.60f ? 3 :
                physical >= 0.38f ? 2 : 1;
            return level * 51;
        }

        internal static int ContinuousRoundsToGlow(
            SuppressorThermalProfile profile)
        {
            if (profile == null || profile.HeatPerShotCelsius <= 0f)
                return 0;
            return (int)Math.Ceiling(
                (GlowOnsetCelsius - AmbientCelsius) /
                    profile.HeatPerShotCelsius);
        }

        internal static int ContinuousRoundsToFailure(
            SuppressorThermalProfile profile, float durabilityScale)
        {
            if (profile == null) return 0;
            float temperature = AmbientCelsius;
            float durability = 1f;
            for (int rounds = 1; rounds <= 100000; rounds++)
            {
                SuppressorThermalStep step = ApplyShots(
                    profile, temperature, durability, 1, true,
                    durabilityScale);
                temperature = step.TemperatureCelsius;
                durability = step.Durability;
                if (step.Broke) return rounds;
            }
            return int.MaxValue;
        }

        private static float Clamp01(float value) =>
            ClampFinite(value, 0f, 1f, 1f);

        private static float SmoothStep(float value)
        {
            float bounded = Clamp01(value);
            return bounded * bounded * (3f - 2f * bounded);
        }

        private static float ClampFinite(
            float value, float minimum, float maximum,
            float fallback)
        {
            if (float.IsNaN(value) || float.IsInfinity(value))
                return fallback;
            return Math.Max(minimum, Math.Min(maximum, value));
        }
    }

    internal static class SuppressorThermalProfiles
    {
        // Weapon/component compatibility comes from DurtyFree's generated
        // b3717 weapons.json dump. Thermal profiles are inferred from the
        // weapon models because GTA exposes broad ammo pools, not cartridges.
        private static readonly SuppressorThermalProfile[] Profiles =
        {
            P("WEAPON_PISTOL", 0x1B06D571, 0x65EA7EBB,
                SuppressorWeaponClass.Sidearm, "SP", "9mm service pistol",
                1.8f, 210f, 325f, 675f, 10000),
            P("WEAPON_COMBATPISTOL", 0x5EF9FEC4, 0xC304849A,
                SuppressorWeaponClass.Sidearm, "SP", "9mm service pistol",
                1.8f, 210f, 325f, 675f, 10000),
            P("WEAPON_APPISTOL", 0x22D8FE39, 0xC304849A,
                SuppressorWeaponClass.Sidearm, "MP", "machine pistol",
                2.0f, 240f, 350f, 700f, 8000),
            P("WEAPON_PISTOL50", 0x99AEEB3B, 0xA73D4664,
                SuppressorWeaponClass.Sidearm, "P50", ".50-class pistol",
                3.4f, 270f, 325f, 625f, 6000),
            P("WEAPON_MICROSMG", 0x13532244, 0xA73D4664,
                SuppressorWeaponClass.SubmachineGun, "MP", "compact 9mm SMG",
                2.0f, 240f, 350f, 700f, 8000),
            P("WEAPON_SMG", 0x2BE6766B, 0xC304849A,
                SuppressorWeaponClass.SubmachineGun, "MP", "9mm SMG",
                2.0f, 240f, 350f, 700f, 8000),
            P("WEAPON_ASSAULTSMG", 0xEFE7E2DF, 0xA73D4664,
                SuppressorWeaponClass.SubmachineGun, "PDW", "high-pressure PDW",
                3.0f, 270f, 400f, 750f, 7000),
            P("WEAPON_ASSAULTRIFLE", 0xBFEFFF6D, 0xA73D4664,
                SuppressorWeaponClass.Rifle, "I762", "7.62x39-class rifle",
                5.2f, 330f, 460f, 825f, 4500),
            P("WEAPON_CARBINERIFLE", 0x83BF0278, 0x837445AA,
                SuppressorWeaponClass.Rifle, "S556", "standard 5.56 carbine",
                4.2f, 300f, 480f, 850f, 5000),
            P("WEAPON_ADVANCEDRIFLE", 0xAF113F99, 0x837445AA,
                SuppressorWeaponClass.Rifle, "L556", "long-barrel 5.56",
                3.8f, 300f, 480f, 850f, 5500),
            P("WEAPON_PUMPSHOTGUN", 0x1D073A89, 0xE608B35E,
                SuppressorWeaponClass.Shotgun, "SG", "12-gauge",
                5.0f, 360f, 350f, 700f, 4000),
            P("WEAPON_ASSAULTSHOTGUN", 0xE284C527, 0x837445AA,
                SuppressorWeaponClass.Shotgun, "SG", "rapid 12-gauge",
                5.0f, 360f, 350f, 700f, 4000),
            P("WEAPON_BULLPUPSHOTGUN", 0x9D61E50F, 0xA73D4664,
                SuppressorWeaponClass.Shotgun, "SG", "12-gauge",
                5.0f, 360f, 350f, 700f, 4000),
            P("WEAPON_SNIPERRIFLE", 0x05FC3C11, 0xA73D4664,
                SuppressorWeaponClass.Sniper, "MAG", ".338-class magnum",
                9.0f, 420f, 400f, 700f, 2500),
            P("WEAPON_HEAVYPISTOL", 0xD205520E, 0xC304849A,
                SuppressorWeaponClass.Sidearm, "HP", ".45-class pistol",
                2.3f, 240f, 325f, 650f, 8000),
            P("WEAPON_BULLPUPRIFLE", 0x7F229F94, 0x837445AA,
                SuppressorWeaponClass.Rifle, "L556", "full-length 5.56",
                3.8f, 300f, 480f, 850f, 5500),
            P("WEAPON_SPECIALCARBINE", 0xC0A3098D, 0xA73D4664,
                SuppressorWeaponClass.Rifle, "C556", "short 5.56 carbine",
                4.8f, 300f, 460f, 825f, 4500),
            P("WEAPON_SNSPISTOL_MK2", 0x88374054, 0x65EA7EBB,
                SuppressorWeaponClass.Sidearm, "CP", "compact pistol",
                1.4f, 180f, 300f, 625f, 12000),
            P("WEAPON_MARKSMANRIFLE_MK2", 0x6A6C02E0, 0x837445AA,
                SuppressorWeaponClass.Sniper, "F762", "full-power 7.62",
                6.5f, 360f, 425f, 750f, 4000),
            P("WEAPON_PUMPSHOTGUN_MK2", 0x555AF99A, 0xAC42DF71,
                SuppressorWeaponClass.Shotgun, "SG", "12-gauge",
                5.0f, 360f, 350f, 700f, 4000),
            P("WEAPON_BULLPUPRIFLE_MK2", 0x84D6FAFD, 0x837445AA,
                SuppressorWeaponClass.Rifle, "L556", "full-length 5.56",
                3.8f, 300f, 480f, 850f, 5500),
            P("WEAPON_SPECIALCARBINE_MK2", 0x969C3D67, 0xA73D4664,
                SuppressorWeaponClass.Rifle, "C556", "short 5.56 carbine",
                4.8f, 300f, 460f, 825f, 4500),
            P("WEAPON_PISTOLXM3", 0x1BC4FDB9, 0x1E02B7E0,
                SuppressorWeaponClass.Sidearm, "SP", "9mm pistol",
                1.8f, 210f, 325f, 675f, 10000),
            P("WEAPON_VINTAGEPISTOL", 0x083839C4, 0xC304849A,
                SuppressorWeaponClass.Sidearm, "CP", "compact pistol",
                1.4f, 180f, 300f, 625f, 12000),
            P("WEAPON_HEAVYSHOTGUN", 0x3AABBBAA, 0xA73D4664,
                SuppressorWeaponClass.Shotgun, "SG", "rapid 12-gauge",
                5.0f, 360f, 350f, 700f, 4000),
            P("WEAPON_MARKSMANRIFLE", 0xC734385A, 0x837445AA,
                SuppressorWeaponClass.Sniper, "F762", "full-power 7.62",
                6.5f, 360f, 425f, 750f, 4000),
            P("WEAPON_CERAMICPISTOL", 0x2B5EF5EC, 0x9307D6FA,
                SuppressorWeaponClass.Sidearm, "SP", "9mm service pistol",
                1.8f, 210f, 325f, 675f, 10000),
            P("WEAPON_MILITARYRIFLE", 0x9D1F17E6, 0x837445AA,
                SuppressorWeaponClass.Rifle, "L556", "full-length 5.56",
                3.8f, 300f, 480f, 850f, 5500),
            P("WEAPON_COMBATSHOTGUN", 0x05A96BA4, 0x837445AA,
                SuppressorWeaponClass.Shotgun, "SG", "rapid 12-gauge",
                5.0f, 360f, 350f, 700f, 4000),
            P("WEAPON_MACHINEPISTOL", 0xDB1AA450, 0xC304849A,
                SuppressorWeaponClass.SubmachineGun, "MP", "9mm machine pistol",
                2.0f, 240f, 350f, 700f, 8000),
            P("WEAPON_CARBINERIFLE_MK2", 0xFAD1F1C9, 0x837445AA,
                SuppressorWeaponClass.Rifle, "S556", "standard 5.56 carbine",
                4.2f, 300f, 480f, 850f, 5000),
            P("WEAPON_SMG_MK2", 0x78A97CD0, 0xC304849A,
                SuppressorWeaponClass.SubmachineGun, "MP", "9mm SMG",
                2.0f, 240f, 350f, 700f, 8000),
            P("WEAPON_ASSAULTRIFLE_MK2", 0x394F415C, 0xA73D4664,
                SuppressorWeaponClass.Rifle, "I762", "7.62x39-class rifle",
                5.2f, 330f, 460f, 825f, 4500),
            P("WEAPON_HEAVYSNIPER_MK2", 0x0A914799, 0xAC42DF71,
                SuppressorWeaponClass.Sniper, "BMG", ".50 BMG-class",
                15.0f, 480f, 375f, 650f, 1500),
            P("WEAPON_PISTOL_MK2", 0xBFE256D4, 0x65EA7EBB,
                SuppressorWeaponClass.Sidearm, "SP", "9mm service pistol",
                1.8f, 210f, 325f, 675f, 10000),
            P("WEAPON_TACTICALRIFLE", 0xD1D5F52B, 0xA73D4664,
                SuppressorWeaponClass.Rifle, "L556", "long-barrel 5.56",
                3.8f, 300f, 480f, 850f, 5500),
            P("WEAPON_HEAVYRIFLE", 0xC78D71B4, 0x837445AA,
                SuppressorWeaponClass.Rifle, "F762", "full-power 7.62",
                6.5f, 360f, 425f, 750f, 4000),
            P("WEAPON_TECPISTOL", 0x14E5AFD5, 0xA73D4664,
                SuppressorWeaponClass.SubmachineGun, "MP", "compact 9mm SMG",
                2.0f, 240f, 350f, 700f, 8000),
            P("WEAPON_BATTLERIFLE", 0x72B66B11, 0x837445AA,
                SuppressorWeaponClass.Rifle, "F762", "full-power 7.62",
                6.5f, 360f, 425f, 750f, 4000),
        };

        private static readonly Dictionary<uint, SuppressorThermalProfile>
            ByWeaponHash = BuildIndex();

        internal static IReadOnlyList<SuppressorThermalProfile> All => Profiles;

        internal static bool TryGet(
            uint weaponHash, out SuppressorThermalProfile profile) =>
            ByWeaponHash.TryGetValue(weaponHash, out profile);

        private static Dictionary<uint, SuppressorThermalProfile> BuildIndex()
        {
            var result = new Dictionary<uint, SuppressorThermalProfile>();
            foreach (SuppressorThermalProfile profile in Profiles)
                result[profile.WeaponHash] = profile;
            return result;
        }

        private static SuppressorThermalProfile P(
            string weaponName, uint weaponHash, uint componentHash,
            SuppressorWeaponClass weaponClass, string profileCode,
            string thermalBasis, float heatPerShotCelsius,
            float coolingHalfLifeSeconds, float damageOnsetCelsius,
            float criticalCelsius, int ratedLifeRounds) =>
            new SuppressorThermalProfile(
                weaponName, weaponHash, componentHash, weaponClass,
                profileCode, thermalBasis, heatPerShotCelsius,
                coolingHalfLifeSeconds, damageOnsetCelsius,
                criticalCelsius, ratedLifeRounds);
    }
}
