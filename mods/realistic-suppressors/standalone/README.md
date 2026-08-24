# Suppressors Enhanced — standalone installation

The ALLIN1 launcher is the recommended installation route because it provides a
settings UI, dependency checks, transactional Story Mode save integration, and
safe package enable/disable operations. This standalone build is for GTA V
Enhanced players who do not use ALLIN1.

## Requirements

- GTA V Enhanced Story Mode
- ScriptHookV
- ScriptHookVDotNet 3
- OpenRPF
- An Enhanced-compatible OIV installer, such as the CodeWalker OIV Package
  Installer included in this repository's `tools/CodeWalker` project

Do not install the standalone and ALLIN1 builds at the same time. They use the
same script and DLC paths.

## Install

1. Close GTA V.
2. Open `Suppressors-Enhanced-Standalone-1.1.0.oiv` in the CodeWalker OIV
   Package Installer.
3. Select the GTA V Enhanced folder and install the package.
4. Start Story Mode. The mod creates
   `scripts/RealisticSuppressors/RealisticSuppressors.ini` on first launch.
5. Edit that file to change settings, then restart Story Mode or reload SHVDN
   scripts.

The OIV installer copies the standalone DLL and heat DLC, adds only the
`dlcpacks:/rs_suppressor_heat/` registration, and records a reversible install.
Use its **Manage Mods** screen to uninstall cleanly.

## Standalone behavior

Gameplay, weapon profiles, glow, smoke, stealth, wear, and spark-pop failure are
the same as the ALLIN1 build. Standalone mode commits condition at each wear
checkpoint and detects replacement through the live vanilla weapon attachment.
It does not provide ALLIN1's settings UI, receipt authorization, Story-save
rollback, or GBAY purchase-event bridge.

Durable condition remains in
`%LOCALAPPDATA%\RealisticSuppressors\condition.json` after uninstall so a later
reinstall can resume it. Delete that file manually only if you want to reset all
suppressor condition.

## Credits and license

Created by **MinionEnjoyer**. Suppressors Enhanced is licensed under the GNU
General Public License v3.0 or later; the package includes `CREDITS.md` and
`LICENSE.txt`. Required third-party runtimes are not bundled.
