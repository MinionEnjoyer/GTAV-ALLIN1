# GTA V ALLIN1 0.6.7 — unsigned portable release

## What's new

- GBAY default previews now live in the public ALLIN1 repository: 935 vehicles, 111 weapons and 10 gear images. Existing generated/custom artwork is preserved; older launchers can still use the SDK-hosted downloads.
- Refined desktop spacing, headings, warnings and review controls. Getting Started and essential setup guidance lead the Help Center.
- Dependency review explains required downloads and renews authorization when a verified Reactor cache is missing.
- More robust Python discovery in the Windows installer.
- An export-only gameconfig capacity profile builder validates source hashes, edition/scopes and explicit pool changes. Profiles are experimental, not automatic crash fixes.
- Coordinates with SDK 0.6.7 and the separately versioned [Reactor V 0.2.8 runtime](https://github.com/MinionEnjoyer/GTAV-REACTOR-V/releases/tag/v0.2.8).

## Download and trust

**Unsigned manual download.** Verify the adjacent SHA-256 files and build identity. Checksums detect changed bytes, not publisher identity. Automatic-update signature verification remains enforced. Do not disable Windows security protections.

Download `ALLIN1-Launcher-0.6.7-portable.zip` for the complete launcher, or `GTAV-ALLIN1-0.6.7-windows.zip` for the public source installer distribution. Extract into a fresh folder; do not overlay an old installation. Keep the launcher's runtime and resources together.

## Release status

**Release `v0.6.7`.** Supersedes the 0.6.6 installer refresh and v0.6.5. Experimental third-party content packs and their unresolved compatibility issues are not included.

Automated checks, package integrity and live acceptance are separate evidence. Build reports retain `release_qualified` false where broader lifecycle, pristine-Windows or both-edition final-build acceptance remains incomplete. Skipped checks are not passes. This is not a signed updater or qualified NSIS setup release.

See the [0.6.7 release guide](docs/release-0.6.7.md), [historical 0.6.6 guide](docs/release-0.6.6.md), and [earlier history](docs/archive/release-notes-before-0.6.4.md).
