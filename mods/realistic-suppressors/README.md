# Realistic Suppressors

Realistic Suppressors is a standalone GTA V Story Mode script mod. The ALLIN1
launcher can install, configure, disable, enable, and uninstall its independent
`RealisticSuppressors.dll`; the gameplay implementation is not compiled into
`ALLIN1.dll`.

## Install with the ALLIN1 launcher

1. Build the release payload or use a distributed package that already contains
   `payload/RealisticSuppressors.dll`.
2. Open **Packages** in the ALLIN1 launcher.
3. Choose **Import & install package** and select this folder's `mod.toml`.
4. Apply the package settings and restart Story Mode.

Uninstalling removes the receipt-owned DLL and descriptor without touching
`ALLIN1.dll` or other mods. Per-character suppressor condition is user data in
`%LOCALAPPDATA%/RealisticSuppressors/condition.json` and is intentionally kept
for a future reinstall.

For a source build, run
`dotnet build RealisticSuppressors.csproj -c Release`; the Release target stages
only `RealisticSuppressors.dll` in `payload/` for the launcher package.
