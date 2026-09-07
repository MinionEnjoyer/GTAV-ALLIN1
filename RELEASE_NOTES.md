# GTA V ALLIN1 0.6.5 — unsigned portable release

## What's new

- Minimal Reactor speedometer with large speed/gear readouts, MPH/KMH, a compact
  transparent layout and optional sequential shifting controls.
- Downloadable default GBAY previews: all 935 vanilla vehicles, 111 weapons and
  10 gear items. Verified caches work across Legacy and Enhanced; generated and
  custom artwork takes priority.
- Blender preview scenes for road, air and water vehicles, weapons, gear and
  throwables; missing-only generation, category controls and Quick Launch.
- Better launcher progress, readable controls, warning acknowledgement and
  cancellation. Refined GBAY workbench scrolling and confirmation layouts.
- Expanded vehicle purchasing/garage coverage and corrected preview discovery,
  including Tampa and stock attachments used by custom weapons.

## Download and trust

**Unsigned manual download.** Publisher code signing is not planned for 0.6.5.
No SignPath certificate or approval is promised. Windows may show an
unknown-publisher or reputation warning; do not disable security protections.

Use official release assets after publication. Verify SHA-256 checksums, the
build identity and companion versions before installation. Checksums detect
changed bytes; they do not authenticate a publisher or prove safety.
Automatic-update signature verification, wherever required, remains enforced;
unsigned manual distribution does not enable automatic-update installation.

## Release status

**Release `v0.6.5`.** This owner-approved portable release supersedes
`v0.6.4`. Extract the entire ZIP into a new folder and run
`allin1-launcher-desktop.exe`; keep its `sidecar` and `resources` folders together.
Python is bundled; the Windows WebView2 runtime must be available.

Enhanced passive-HUD operation was confirmed by the tester before the final
size/layout adjustment. Automated and packaged checks are recorded separately
from in-game acceptance. This is not a pristine dependency test, an NSIS
installer release, or fresh final-build Legacy/Enhanced in-game acceptance.
Unperformed or skipped checks remain untested. Build reports intentionally keep
`release_qualified` false where the broader qualification gates are incomplete;
publication approval does not turn those checks into passes.

See the [Launcher manual](docs/launcher-guide.md),
[release checklist](docs/release-0.6.5.md) and
[earlier release history](docs/archive/release-notes-before-0.6.4.md).
