# GTA V ALLIN1 0.6.6 — unsigned portable release

## What's new

- The Content → Traffic editor remains the supported configurable population
  feature. Ped and weapon ambient-spawner work has moved to the separate
  experimental branch and is not part of this release.
- Hardened Launcher/service recovery around disconnects, timeouts, interrupted
  writes and explicit reconnection. A retained draft is not replayed after an
  uncertain service operation.
- Pins the Reactor V dependency to 0.2.6 and ships the matching composed UI.
  The separate [Reactor V 0.2.7 installer-only release](https://github.com/MinionEnjoyer/GTAV-REACTOR-V/releases/tag/v0.2.7)
  preserves ALLIN1 default/generated `index.json` files when installing 0.2.6.
  It does not change this release's
  exact 0.2.6 native-runtime dependency or asset pins.
- Aligns the Launcher with the current SDK package contract, including schema-2 exact
  member preconditions used by managed package validation.

## Download and trust

**Unsigned manual download.** Publisher code signing is not planned for 0.6.6.
Windows may show an unknown-publisher or reputation warning; do not disable
security protections.

Use official release assets after publication. Verify SHA-256 checksums, build
identity and companion versions before installation. Checksums detect changed
bytes; they do not authenticate a publisher or prove safety. Automatic-update
signature verification remains enforced; unsigned manual distribution does not
enable automatic-update installation.

## Release status

**Release `v0.6.6`.** This owner-approved portable release supersedes v0.6.5.
Extract the complete ZIP into a new folder and run
`allin1-launcher-desktop.exe`; keep its `runtime` and `resources` folders
together. Use a fresh extraction rather than overlaying an older build.

Automated and packaged checks are recorded separately from live-game
acceptance. This is not a pristine-Windows dependency test, an NSIS installer
release, or fresh final-build Legacy/Enhanced in-game acceptance. Unperformed
or skipped checks remain untested. Build reports intentionally keep
`release_qualified` false where broader qualification gates are incomplete;
publication approval does not turn those checks into passes.

## Re-release 2 — installer fixes

This re-release publishes new, uniquely named `-r2` archives built from the
repaired 0.6.6 source. It fixes batch entrypoints in installation paths with
spaces, `&`, or `!`, passes a manually entered game path as data rather than
interpolated Python source, and improves missing-executable and Reactor
compatibility diagnostics. It does not change the product version, add a
Reactor runtime, or qualify native installer lifecycle or live-game behavior.
Reactor 0.2.7 is installer-only and retains the verified 0.2.6 runtime.

Do not mistake the original archives for these repaired downloads. Their
recorded SHA-256 values are retained for identification only:

- `ALLIN1-Launcher-0.6.6-portable.zip`:
  `efa9202dc425a0d67398d5d9969edc0f6b7f2b14842922db48375995b76a2fcb`
- `GTAV-ALLIN1-0.6.6-windows.zip`:
  `9d68ffd879c05c62be0fa00f76d6e751d2122b2541dec3192f812a7e4dced521`

Download only the `ALLIN1-Launcher-0.6.6-r2-portable.zip` and
`GTAV-ALLIN1-0.6.6-r2-windows.zip` assets for this re-release, and verify each
against its adjacent `.sha256` asset. The new checksums are intentionally
different because the repaired archives have different bytes.

See the [Launcher manual](docs/launcher-guide.md),
[release checklist](docs/release-0.6.6.md) and
[earlier release history](docs/archive/release-notes-before-0.6.4.md).
