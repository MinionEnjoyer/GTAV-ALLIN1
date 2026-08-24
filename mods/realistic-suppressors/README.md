# Suppressors Enhanced

Suppressors Enhanced is an independent GTA V Enhanced Story Mode mixed mod.
The recommended build integrates with the ALLIN1 launcher for installation,
settings, safe lifecycle management, and Story-save transactions; the gameplay
implementation remains in its own `RealisticSuppressors.dll`. An optional
launcher-independent build provides the same gameplay through a local INI and
does not load or reference `ALLIN1.dll`.

## Install with the ALLIN1 launcher

1. Build the release payload or use a distributed package that already contains
   `payload/RealisticSuppressors.dll` and
   `payload/rs_suppressor_heat/dlc.rpf`.
2. Open **Packages** in the ALLIN1 launcher.
3. Choose **Import & install package** and select this folder's `mod.toml`.
4. Apply the package settings and restart Story Mode.

The package requires SHVDN and OpenRPF. Uninstalling removes the receipt-owned
DLL, descriptor, DLC, and DLC-list registration without touching `ALLIN1.dll`
or other mods. Per-character suppressor condition is user data in
`%LOCALAPPDATA%/RealisticSuppressors/condition.json` and is intentionally kept
for a future reinstall.

## Install without ALLIN1

Build or download `Suppressors-Enhanced-Standalone-1.1.0.oiv`, then open it in
an Enhanced-compatible OIV installer such as the CodeWalker OIV Package
Installer. The standalone build still requires ScriptHookV,
ScriptHookVDotNet 3, and OpenRPF. On first launch it creates
`scripts/RealisticSuppressors/RealisticSuppressors.ini`; edit that file and
restart Story Mode or reload SHVDN scripts to apply settings.

Do not install both builds at once. The standalone build commits condition at
wear checkpoints and uses native attachment changes to detect Ammu-Nation
replacements. It intentionally lacks the ALLIN1 settings UI, receipt-backed
enable/disable controls, Story-save rollback, and GBAY purchase-event bridge.
See `standalone/README.md` for installation and removal details.

The heat visual is a 64-sided, outward-facing emissive sleeve attached directly
to the active suppressor bone. A barely visible red-orange band first appears at
the center of the can, then diffuses toward its low-alpha ends over a continuous
quadratic fade. Early incandescence stays especially restrained: half of the
glow-to-critical temperature range uses only 25% overlay opacity, while full
opacity is reached only at critical heat. The sleeve has 1.5 mm of clearance so
the stock model cannot hide it. Because GTA parents the sleeve to the weapon, it follows sway, recoil,
reloads, and camera movement without painting the receiver, optic, sight
picture, or the player's hands.

Optional heat smoke uses GTA's stock barrel-smoke particle attached to that
same suppressor bone. It begins above the weapon profile's accelerated-wear
temperature, stays restrained through ordinary high heat, then gains a strong
smooth boost across the final 18% before critical and becomes two dense,
can-length trails. It continues until the modeled can cools below the onset.
**Suppressor heat smoke** can disable it independently, while
**Heat smoke intensity** scales its plume from 0.5× to 2.0×.

When optional breakage is enabled, the first transition to failed condition
produces one small front-cap spark burst and spatial metallic pop before the
component is removed. The effect uses no explosion, damage, bullet, force, or
camera-shake native and cannot harm nearby characters or props.

Normal gameplay is notification-free. **Temperature debug** is off by default.
When explicitly enabled, it draws a compact live Celsius readout only while a
supported suppressor is attached to the equipped weapon, without using GTA's
subtitle, help, or notification queues.

## Credits and license

Suppressors Enhanced was created by **MinionEnjoyer** and is distributed under
the GNU General Public License v3.0 or later. See `CREDITS.md` and the repository
`LICENSE` file. ScriptHookV, ScriptHookVDotNet 3, OpenRPF, GTA V, and ALLIN1 are
separate projects or products; required third-party runtimes are not bundled.

For a source build, run
`dotnet build RealisticSuppressors.csproj -c Release`; the Release target stages
`RealisticSuppressors.dll`. The validated Enhanced overlay DLC is a separate
prebuilt package payload.
