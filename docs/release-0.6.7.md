# ALLIN1 0.6.7 release guide

0.6.7 is an unsigned, manual-download portable release prepared September 22, 2026. It refreshes the public launcher, Help Center, dependency review and installer, and relocates the default GBAY artwork to ALLIN1-owned GitHub release assets. The SDK is distributed independently. Reactor V 0.2.8 is a separately versioned runtime dependency, not an installer-only refresh.

## Scope

- Public launcher and supported Traffic configuration; experimental ped/weapon population systems remain excluded.
- Default previews: 935 vehicles, 111 weapons, 10 gear images. Existing SDK-hosted downloads remain for older launchers.
- Explicit, export-only gameconfig capacity profiles; generated profiles are experimental and not runtime-qualified.
- No private test mods, game assets, saves, or local crash-isolation settings are distributed.

## Installation and trust

Extract the complete portable archive into a fresh directory. Keep its runtime and resources together. Do not overlay old installations or copy only the executable. SHA-256 verifies archive consistency, not publisher identity. Automatic-update signature gates remain enforced.

## Remaining work

Publication does not convert skipped or untested checks into passes. Build evidence records the exact source, artifact checksums, automated test results and remaining limitations. Clean Windows lifecycle coverage, both-edition final-build live acceptance, and signed automatic-update qualification are separate gates. The user's successful local Enhanced test is evidence for that configuration only; it does not certify every third-party DLC pack or the Legacy edition.

## References

See [default previews](gbay-default-previews.md), [capacity profiles](content-capacity-profiles.md), [launcher guide](launcher-guide.md), and [release harness](react-release-harness.md).
