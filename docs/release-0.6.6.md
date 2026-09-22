# ALLIN1 0.6.6 release guide

> Historical release record — superseded by [0.6.7](release-0.6.7.md).

0.6.6 is an owner-approved **unsigned manual-download portable release**. It
supersedes v0.6.5. The SDK remains independently distributed and is not bundled
in this archive. Exact artifact checksums and build reports accompany
publication; publication does not turn untested lifecycle or live-game checks
into passes.

## Release scope

- The supported configurable ambient-population feature is the **Traffic**
  editor. Ped and weapon spawner work remains on an experimental branch and is
  deliberately excluded from this release.
- Launcher/service recovery now handles timeouts, disconnects and uncertain
  writes conservatively: retained drafts require a fresh review and are never
  replayed automatically.
- Reactor V remains pinned to the exact verified 0.2.6 native runtime. The
  separate [Reactor V 0.2.7 installer-only release](https://github.com/MinionEnjoyer/GTAV-REACTOR-V/releases/tag/v0.2.7)
  fixes preservation of ALLIN1's default/generated `index.json` files while
  installing that runtime; it does not introduce or qualify a newer native
  runtime.
- Launcher package handling is aligned with the current SDK package contract,
  including schema-2
  exact-member preconditions for managed package validation.

Reactor and the SDK keep their own release identities. Install/Repair uses the
exact Reactor dependency pinned by this Launcher. Dependency verification and
offline artifact checks do not prove that a component loaded in-game.

## Re-release 2 installer fixes

- Batch install/uninstall invoke quoted virtual-environment executables
  directly, including when the installation path contains spaces, `&` or `!`.
- Manual game paths are passed as data rather than interpolated into Python
  source; installation errors identify both editions' executable names.
- Reactor compatibility failures report the expected and detected SHA-256.
  Enhanced 0.2.6 supports the qualified Steam `1.0.1158.16` executable; matching
  version text from another storefront does not establish compatibility.

These source changes require rebuilt downloads to reach packaged installations.
The re-release uses distinct `-r2` filenames so users can distinguish them
from the original v0.6.6 archives. The original SHA-256 values are retained in
the top-level release notes for identification; use the adjacent `-r2`
checksum assets for installation verification.

## Mandatory 0.6.6 full-release milestone

The broader qualification target remains separate from this approved portable
publication. React/Tauri is the only GUI; Tcl/Tk and legacy adapters must remain
absent from source and frozen distributions. Shared Python services, CLI and
Agent API compatibility are retained.

## Remaining work

| Gate | Requirement |
| --- | --- |
| Automated checks | Full tests and unchanged coverage thresholds: Launcher 91%, SDK 80%; skips are not passes |
| Package integrity | Source-bound shell, service, resources and portable inventory; matching core/bridge binaries |
| Native lifecycle | Final-build install, upgrade, repair, uninstall, rollback, missing dependencies, long paths and data preservation |
| Live Legacy/Enhanced | Independent final-build in-game acceptance remains unverified |
| Pristine Windows | A clean Windows dependency/install qualification remains unverified |
| Updater trust | Unsigned manual downloads only; automatic-update signature checks stay enforced |

Prior packaged startup or lifecycle observations do not certify a newly built
artifact. Consult the attached candidate report for exact commands and results.
No test threshold or containment/ownership check is waived by publication.

## Upgrade and recovery

Use the complete portable directory, not an executable copied without resources.
Keep the sibling `runtime/` and `resources/` directories. Extract into a fresh
directory; do not overlay an older `sidecar/` installation. Retain recovery
backups until the new installation is verified. Repair and rollback must reject
changed or unowned targets rather than overwrite them.

The Launcher exposes manual release lookup; it does not install its own updates.
SDK signed-update installation remains disabled until trusted metadata and keys
are available. SHA-256 verifies byte consistency, not publisher identity. Do not
disable Windows security protections to install an unsigned release.

## References

See the [Launcher manual](launcher-guide.md), [developer guide](development.md),
[traffic editor guide](content-injectors.md),
[preview-pack guide](gbay-default-previews.md) and
[release harness](react-release-harness.md). Earlier decisions remain in the
[historical architecture audit](architecture-review-react-0.6.4.md) and
[release history](archive/release-notes-before-0.6.4.md).
