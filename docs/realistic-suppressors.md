# Realistic suppressors

Realistic Suppressors is its own GTA V Story Mode script mod. It is installed,
configured, enabled, disabled, and uninstalled as the independent
`realistic-suppressors` package through the ALLIN1 launcher; it is not part of
ALLIN1, ALLIN1 Online Content, or `ALLIN1.dll`.

The mod gives attached suppressors a practical stealth benefit while preserving
the cues that make a shot detectable. It also simulates suppressor temperature,
visible incandescence, persistent condition, and optional permanent failure for
all 39 stock GTA V weapons that accept a removable suppressor. That includes
vanilla weapon/suppressor combinations purchased through Ammu-Nation; a
suppressor does not need to come from an ALLIN1 storefront to use the model.

## Install and remove

1. Open **Packages** in the ALLIN1 launcher.
2. Choose **Import & install package** and select the distributed
   `realistic-suppressors/mod.toml`.
3. Confirm the package is enabled, apply its settings, and restart Story Mode.

The launcher receipt owns only
`scripts/RealisticSuppressors/RealisticSuppressors.dll` and the package's
installed content descriptor. Disable and re-enable operations act on those
standalone files. Uninstall removes them without removing or replacing
`scripts/ALLIN1.dll`, ALLIN1 Online Content, or another mod.

Per-character condition is user state, not an installed payload. It is stored
at `%LOCALAPPDATA%\RealisticSuppressors\condition.json` and is intentionally
retained after uninstall so reinstalling the mod can resume the saved condition.
Condition changes use the receipt-authorized Story-save transaction lifecycle:
they commit after a real Story Mode save and discard with an unsaved session.

## Settings

After installing the package, open **Content**, select **Realistic Suppressors**,
and open its **Realistic Suppressors** system.

| Setting | Default | Effect |
|---|---:|---|
| **Realistic suppressor stealth** | On | Enables witness-aware firearm-report suppression. Heat, glow, and the separate breakage option continue to work when this stealth switch is off. |
| **Suppressor wear and breakage** | On | Enables condition loss and permanent failure. Turning it off retains heating, cooling, warnings, and glow without reducing condition or removing a suppressor. |
| **Suppressor durability multiplier** | 1.0× | Scales service life from 0.5× to 3.0×. It has no effect while breakage is off. |

Apply changed settings and reload scripts or restart Story Mode.

## Stealth behavior

A suppressor is quieter, not silent. With no existing wanted level and outside
missions and cutscenes, the mod suppresses the firearm report only when it cannot
find a credible witness. A shot remains actionable when a human NPC:

- is close enough to hear the muzzle report;
- is already alert, fighting, or fleeing;
- has a clear view and is facing the shooter;
- is close to the bullet's complete flight path; or
- is close to the impact.

Indoor reflections and a sustained burst expand the effective hearing radius.
The controller does not erase an existing wanted level, globally reduce player
noise, suppress unrelated crimes, or change authored mission behavior. Mk II
muzzle brakes are explicitly excluded.

## Heat, wear, and failure

Each equipped can cools exponentially toward 20 °C while it is held or stowed.
Every shot adds the weapon profile's temperature increment. The runtime then
applies deterministic wear:

```text
hot = max(0, (temperature - damage onset) / (critical - damage onset))
wear per shot = (1 + 24 × hot²) / (rated life × durability multiplier)
```

Below the accelerated-wear onset temperature, a shot consumes one rated-life
unit. At the critical temperature it consumes 25 units, and still hotter fire
is more severe.
This makes rapid fire substantially more destructive than the same number of
spaced shots without inventing a random failure roll. At zero condition the
component is removed from the live weapon and recorded as consumed in the mod's
condition state. A new suppressor purchased and attached through vanilla
Ammu-Nation is detected after the failed component has been verified absent and
a fresh live attachment appears. The controller pauses while GTA has disabled
player control, so a temporary native-shop preview cannot count as that fresh
attachment. When ALLIN1 and GBAY are also installed, the
same replacement works there through the host's generic, receipt-authorized
weapon-component lifecycle bridge. GBAY checks the mod's consumed state before
pricing and reports only a successfully charged and applied purchase; temporary
workbench previews are not replacements. Either completed path starts the new
component at full condition.
Re-equipping a component that never completed a removal is not mistaken for a
replacement.

Persistent condition and replacement tracking are supported for Michael,
Franklin, and Trevor. If a trainer substitutes an unsupported player model,
the mod keeps thermal simulation and glow active but safely suspends destructive
wear because that model has no supported saved-character replacement path.

The first visible glow begins at 525 °C. A small orange/red glow is rendered at
the weapon's muzzle bone and intensifies toward the profile's critical
temperature. Heat is a runtime state; durable condition is saved per character,
weapon, and suppressor component.

## Weapon profiles

GTA does not expose a reliable cartridge or suppressor model for every weapon.
The compatibility mapping is exact to the stock game data, while cartridge,
barrel-length, and pressure classes are documented inferences from the depicted
weapons. `Rated life` is normal-temperature game life; hot firing accelerates it
with the equation above. `Glow` and `failure` rounds are deterministic 1.0×
results for uninterrupted fire from 20 °C. They are calibration points for the
gameplay model, not recommended real-world firing schedules.

| Profile | GTA weapons | °C/shot | Cooling half-life | Damage onset | Critical | Rated life | Glow | Failure |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CP — compact pistol | SNS Pistol Mk II, Vintage Pistol | 1.4 | 180 s | 300 °C | 625 °C | 12,000 | 361 | 625 |
| SP — service pistol | Pistol, Combat Pistol, Pistol Mk II, WM 29 Pistol, Ceramic Pistol | 1.8 | 210 s | 325 °C | 675 °C | 10,000 | 281 | 525 |
| HP — heavy pistol | Heavy Pistol | 2.3 | 240 s | 325 °C | 650 °C | 8,000 | 220 | 399 |
| P50 — .50-class pistol | Pistol .50 | 3.4 | 270 s | 325 °C | 625 °C | 6,000 | 149 | 267 |
| MP — machine pistol / SMG | AP Pistol, Micro SMG, SMG, Machine Pistol, SMG Mk II, Tactical SMG | 2.0 | 240 s | 350 °C | 700 °C | 8,000 | 253 | 472 |
| PDW — high-pressure PDW | Assault SMG | 3.0 | 270 s | 400 °C | 750 °C | 7,000 | 169 | 351 |
| L556 — long 5.56 | Advanced Rifle, Bullpup Rifle, Bullpup Rifle Mk II, Military Rifle, Service Carbine | 3.8 | 300 s | 480 °C | 850 °C | 5,500 | 133 | 304 |
| S556 — standard 5.56 | Carbine Rifle, Carbine Rifle Mk II | 4.2 | 300 s | 480 °C | 850 °C | 5,000 | 121 | 276 |
| C556 — short 5.56 | Special Carbine, Special Carbine Mk II | 4.8 | 300 s | 460 °C | 825 °C | 4,500 | 106 | 237 |
| I762 — intermediate 7.62 | Assault Rifle, Assault Rifle Mk II | 5.2 | 330 s | 460 °C | 825 °C | 4,500 | 98 | 223 |
| F762 — full-power 7.62 | Marksman Rifle, Marksman Rifle Mk II, Heavy Rifle, Battle Rifle | 6.5 | 360 s | 425 °C | 750 °C | 4,000 | 78 | 169 |
| MAG — magnum rifle | Sniper Rifle | 9.0 | 420 s | 400 °C | 700 °C | 2,500 | 57 | 111 |
| BMG — .50 BMG-class | Heavy Sniper Mk II | 15.0 | 480 s | 375 °C | 650 °C | 1,500 | 34 | 63 |
| SG — 12-gauge | Pump Shotgun, Assault Shotgun, Bullpup Shotgun, Pump Shotgun Mk II, Heavy Shotgun, Combat Shotgun | 5.0 | 360 s | 350 °C | 700 °C | 4,000 | 101 | 199 |

The Combat PDW's suppressor is integral rather than an attachable component. It
receives the same witness-aware stealth benefit, but is intentionally excluded
from attachment wear, glow, removal, and repurchase because GTA provides no
separate suppressor component to consume or replace.

## Research basis

There is no defensible universal round count at which all real suppressors
break. Manufacturer limits are normally expressed as firing schedules,
temperature cautions, barrel restrictions, and service-life ranges. The mod uses
those published anchors instead of claiming a single real-world failure number:

- [YHM Turbo K-RB manual](https://www-wp.silencercentral.com/wp/wp-content/uploads/2023/09/YHM_Turbo-K-RB_user-manual.pdf): approximately 225 °F of suppressor-temperature rise per 30-round 5.56 magazine. This is the basis for the standard 5.56 profile's 4.2 °C per shot.
- [Griffin PSR manual](https://griffinarmament.com/wp-content/uploads/2025/06/GriffinPsrManual.pdf): no more than three 30-round magazines at full-auto cadence, followed by a 15-round-per-minute schedule.
- [Griffin Spartan III manual](https://www.griffinarmament.com/content/manuals/Spartan-3-Manual.pdf): two magazines followed by a 10-round-per-minute schedule, with finish damage possible above roughly 900 °F after about 100 rapid rounds.
- [SIG Sauer rifle suppressor manual](https://www.sigsauer.com/media/sigsauer/resources/17SIG2349_RifleSuppressorOwnersManual_8501925-01_REV00_LR.pdf): heavy semiautomatic or prolonged automatic fire reduces service life, shorter barrels heat suppressors faster, and continued overheating can cause failure.
- [B&T rifle suppressor manual](https://bt-usa.com/wp-content/uploads/2024/07/TM-SD_RIFLE-EN.pdf): a minimum specified service life of 5,000 rounds for conventional rifle suppressors.
- [B&T 2025 suppressor catalogue](https://bt-ag.ch/wp-content/uploads/catalog/B%26T_Catalogue_Suppressors_2025_EN.pdf): service life beyond 20,000 rounds under moderate use, illustrating why firing schedule matters more than one fixed round count.
- [Dead Air Nomax manual](https://deadairsilencers.com/wp-content/uploads/2024/07/Nomax-Manual-Web-1.pdf): a 10-round-per-minute schedule for high-pressure .33/.338 applications, supporting stricter magnum profiles.
- [Instrumented 5.56 thermal test](https://david.bookstaber.com/Interests/2007/03/freebore-boost-effects/): roughly 410 °F after 30 rounds in under 90 seconds and an observed cooling half-life near five minutes, used as a cooling cross-check.
- [NIST fire temperature report](https://www.nist.gov/system/files/documents/el/fire_research/R0002205.pdf): visible red incandescence beginning around 525 °C, used as the common glow threshold.
- [DurtyFree GTA V b3717 weapon data](https://github.com/DurtyFree/gta-v-data-dumps/blob/26292ec7cb4c8cb8525cfede86ab5685328b916b/weapons.json): the stock weapon-to-suppressor-component compatibility map.

These values are a gameplay model, not firearm-maintenance or safety guidance.
Always follow the actual manufacturer's current manual for real equipment.

## Diagnostics and testing

The standalone log at
`%LOCALAPPDATA%\RealisticSuppressors\RealisticSuppressors.log` records
`shot_evaluated` entries containing the witness reason, audible radius,
temperature, durability, heat stage, and profile. A permanent failure emits
`component_broken` with the native-removal and condition-update results.

The manual Legacy/Enhanced validation flow is in
[tests/IN_GAME_CHECKLIST.md](../tests/IN_GAME_CHECKLIST.md).
