# ALLIN1 0.6.5 release guide

> **Historical release record — superseded by 0.6.6.** Use the
> [0.6.6 release guide](release-0.6.6.md) for current instructions and limits.

0.6.5 is an owner-approved **unsigned manual-download portable release**, approved
September 7, 2026. It supersedes v0.6.4. The SDK is independently distributed.
Exact artifact checksums and build reports accompany the release; publication
does not turn untested lifecycle or live-game checks into passes.

## Release scope

- Shared bundled CPython runtime for services, CLI and preview workers; no
  user-installed Python, frozen service executable or frozen preview executable.
- Reactor passive speedometer: large, adjacent speed and gear text, transparent
  background, MPH/KMH and optional sequential shifting.
- Downloadable GBAY default previews: 935 vehicles, 111 weapons and 10 gear items.
  Valid generated previews retain priority; caches are shared across editions.
- Blender category scenes, missing-only generation, Quick Launch, cancellation,
  clearer progress and warning acknowledgement.
- Expanded purchasable vehicle coverage and custom-weapon preview assembly fixes.
- Readability, scrolling and confirmation improvements across Launcher and GBAY.

Reactor keeps its independent version. Install/Repair uses the exact dependency
release pinned by this Launcher, including passive-HUD support. The pre-release
Enhanced HUD was confirmed working by the tester before the final layout change;
that is not a final-byte Legacy/Enhanced acceptance claim.

## Mandatory 0.6.5 full-release milestone

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
| Updater trust | Unsigned manual downloads only; automatic-update signature checks stay enforced |

Prior packaged startup or lifecycle observations do not certify a newly built
artifact. Consult the attached candidate report for exact commands and results.
No test threshold or containment/ownership check is waived by publication.

## Upgrade and recovery

Use the complete portable directory, not an executable copied without resources.
The rebuilt 0.6.5 package uses sibling `runtime/` and `resources/` directories.
Extract into a fresh directory; do not overlay an older `sidecar/` installation.
New Blender previews still require Blender; downloaded/cached previews do not.
Retain recovery backups until the new installation is verified. Repair and
rollback must reject changed or unowned targets rather than overwrite them.
SDK management consumes the versioned portable contract and exact inventories.

The Launcher exposes manual release lookup; it does not install its own updates.
SDK signed-update installation remains disabled until trusted metadata and keys
are available. SHA-256 verifies byte consistency, not publisher identity. Do not
disable Windows security protections to install an unsigned release.

## References

See the [Launcher manual](launcher-guide.md), [developer guide](development.md),
[preview-pack guide](gbay-default-previews.md) and [release harness](react-release-harness.md).
Earlier decisions remain in the [historical architecture audit](architecture-review-react-0.6.4.md)
and [release history](archive/release-notes-before-0.6.4.md).
