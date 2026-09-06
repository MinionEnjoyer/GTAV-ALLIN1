# GTA V ALLIN1 0.6.4 — unsigned portable release

## What's new

- React/Tauri v2 Launcher workspaces backed by reviewed Python service operations.
- Independent workspace drafts, clearer content settings and deliberate SDK
  handoffs.
- Safer updater/rollback containment, retained recovery backups and compatible
  Tauri SDK package verification.
- Release evidence tied to the tested build, edition and session, with expanded
  UI/service regression tests and reorganized manuals.
- A cleaner Launcher layout, collapsible green sidebar arrow, readable field
  hints, paired sliders/manual input and reviewed confirmation dialogs.
- Launcher CLI and stdio agent API for catalog discovery, workspace inspection
  and explicitly approved operations through the same service as the UI.
- Fixed packaged startup with Windows extended-length resource paths, without
  weakening checksum or link protections; added a frozen regression check.

## Download and trust

**Unsigned manual download.** Publisher code signing is not planned for 0.6.4.
No SignPath certificate or approval is promised. Windows may show an
unknown-publisher or reputation warning; do not disable security protections.

Use official release assets after publication. Verify SHA-256 checksums, the
build identity and companion versions before installation. Checksums detect
changed bytes; they do not authenticate a publisher or prove safety.
Automatic-update signature verification, wherever required, remains enforced;
unsigned manual distribution does not enable automatic-update installation.

## Release status

**Release `v0.6.4`.** This owner-approved portable release supersedes
`v0.6.4-rc.1`. Extract the entire ZIP into a new folder and run
`allin1-launcher-desktop.exe`; keep its `sidecar` and `resources` folders together.
Python is bundled; the Windows WebView2 runtime must be available.

Native startup, all nine workspaces, sidebar collapse/restore, setting search,
reviewed local saves, folder-dialog cancellation and close/reopen persistence
passed on this development machine with isolated preferences. The packaged
CLI and agent API were also exercised. This is not a pristine dependency test,
an NSIS installer release, or fresh Legacy/Enhanced in-game acceptance.
Unperformed or skipped checks remain untested. Build reports intentionally keep
`release_qualified` false where the broader qualification gates are incomplete;
publication approval does not turn those checks into passes.

See the [Launcher manual](docs/launcher-guide.md),
[release checklist](docs/release-0.6.4.md) and
[earlier release history](docs/archive/release-notes-before-0.6.4.md).
