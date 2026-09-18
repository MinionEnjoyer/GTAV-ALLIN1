# GTA V ALLIN1 0.6.6 — unsigned portable release

## What's new

- The Content → Traffic editor remains the supported configurable population
  feature. Ped and weapon ambient-spawner work has moved to the separate
  experimental branch and is not part of this release.
- Hardened Launcher/service recovery around disconnects, timeouts, interrupted
  writes and explicit reconnection. A retained draft is not replayed after an
  uncertain service operation.
- Pins the Reactor V dependency to 0.2.6 and ships the matching composed UI.
  The installer now accepts the current `default-gear/index.json` catalogue
  layout as well as generated catalogue indexes.
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

See the [Launcher manual](docs/launcher-guide.md),
[release checklist](docs/release-0.6.6.md) and
[earlier release history](docs/archive/release-notes-before-0.6.4.md).
