# ALLIN1 0.6.4 release guide

**Status: owner-approved unsigned Launcher portable release.** Native packaged
startup and preference persistence have passed. Full installer lifecycle and
fresh in-game acceptance remain untested. The SDK is independently released.

The owner approved publishing `v0.6.4` after the packaged startup E2E pass.
It supersedes `v0.6.4-rc.1` on the Latest channel as a manual-download portable
release. It does not bypass updater trust checks or certify the broader
qualification milestone below. Exact build identities and disclosed test scope
remain authoritative; untested checks are not passes.

## Mandatory 0.6.4 full-release milestone

**Both Launcher and SDK must be complete React/Tauri v2 replacements before the
full 0.6.4 release.** A mixed Tkinter/React distribution does not meet this milestone.
This remains the broader qualification target, not a claim that the portable
publication completed every acceptance check.

- Verify complete workflow and secondary-action parity, with happy-path,
  failure/recovery and draft-preservation tests; page coverage alone is insufficient.
- Switch all supported GUI entrypoints to Tauri. Remove Tkinter UI modules,
  adapters, imports and legacy GUI build jobs from active product source; remove
  Tcl/Tk and `_tkinter` from distributed runtimes. Verify source, actual startup
  processes and extracted installer/portable contents. Preserve shared Python
  services, CLI compatibility and SDK Agent API support.
- Qualify standalone builds, native dialogs, preferences/handoffs, cancellation,
  crash/close/restart and full Windows lifecycle, including missing dependencies,
  spaces/long paths and preservation of user data.
- Pass full required automated gates at unchanged coverage thresholds (Launcher
  91%, SDK 80%). Required skipped checks remain untested, not passes.
- Tie packages and approved Legacy/Enhanced acceptance to the same reviewed
  source, final artifact/dependency hashes and independent sessions.
- Obtain separate publication approval for explicitly unsigned manual downloads;
  automatic-update signature verification remains enforced.

Tkinter source removal is complete: both GUI aliases route to Tauri, legacy
adapters/build jobs are removed, and source/frozen-payload guards prevent
reintroduction. This satisfies the source-removal part only, not the remaining
packaged-process, lifecycle, coverage or live-acceptance requirements.

## Release scope

- React/Tauri v2 Launcher with a versioned Python service, explicit review/apply
  flows, preserved independent drafts and SDK handoff.
- Existing SDK React authoring, native previews, RPF workflows, receipts,
  standalone assistant settings and source-backed module happy paths.
- Safe archive/checksum/rollback containment, exact payload agreement, retained
  recovery backups and compatible SDK portable-package consumption.
- Release evidence with versioned checks, independent session/build anchors,
  edition/freshness checks and actual artifact/dependency hashes.
- Structured progress/purchase telemetry and explicit separation of SDK previews
  from Reactor in-game acceptance.
- Current manuals and source-generated CLI/configuration references; historical
  documents cannot establish current qualification.

## SDK assessment

The SDK is in **late functional migration, not final release qualification**.
Its main strength is shared Python authoring/validation behind real React
workflows. Its weak points are remaining secondary/native interactions, large
root components, limited packaged lifecycle evidence and incomplete updater trust setup.
The Launcher has a frozen standalone distribution with preference import,
Content/Package settings, local assistant provisioning, CLI and agent access.
Native startup, all workspaces, local save review, sidebar persistence and
close/reopen have passed. Full native lifecycle qualification remains unfinished.

Avoid a misleading single “percent migrated.” A module opening, a reviewed
authoring happy path, a no-skip test run, a verified archive and a live acceptance
session measure different things. Removing Tkinter does not promote an older
binary or bypass qualification of the packaged replacement.

## Remaining work

| Gate | Status / requirement |
| --- | --- |
| Launcher frozen distribution | Candidate builder has explicit resources/build identity and preference import; use a fresh source-bound report, not an older executable |
| Secondary Launcher parity | Content/package catalogs/settings, local assistant provisioning, activity/manual-release controls, keyboard shortcuts and independent draft/recovery tests implemented; exhaustive native interaction acceptance remains |
| SDK secondary parity | Follow the SDK's detailed feature-parity matrix; native dialogs, process recovery and selected authoring gaps remain |
| Automated coverage | Launcher must meet 91%; SDK must meet 80%. Do not lower thresholds or convert skips to passes |
| Package integrity | Fresh native components, resources, portable ZIP and installer must agree exactly; PE headers alone are insufficient |
| Native lifecycle | Clean install, upgrade, repair, uninstall, rollback, missing dependencies, space/long paths and user-data preservation |
| Live Legacy/Enhanced | NOT TESTED for a final candidate; requires explicit approval and independently bound evidence |
| Manual publishing | Unsigned disclosure, reviewed source, exact checksums/build identity and separate publication approval required |

Use each fresh harness report's source inventory and command logs for exact
results. Earlier run counts do not qualify subsequent edits. Independent mod
checks are outside the ALLIN1 release gate; the Suppressors archive consistency
check is retained in its own suite and CI workflow (see the [developer guide](development.md#automated-gates)).
This scope correction does not fix that mod's stale archives or lower ALLIN1's
coverage threshold. Generic package lifecycle and weapon support remain tested.

## Upgrade and compatibility

Both products target 0.6.4. Do not reuse a version to disguise materially
different release binaries. Candidate identity must include the reviewed commit,
dirty-state policy, build ID, source digest, locks, tool/runtime identities,
protocol/schema versions and every artifact hash.

Launcher SDK management recognizes the Tauri portable contract, including
`release.json`, `checksums.json`, shell, sidecar, resource manifest and matching
build identity. A synthetic producer/consumer test proves contract behavior, not
a clean Windows installer lifecycle. Older filename-only workarounds are not
supported upgrade procedures.

Download resolution rejects ambiguous archive/checksum assets, and download
filenames are validated before network access or output creation. Installed
resource subdirectories must match the SDK runtime's exact inventory policy;
unowned root-level projects are retained. Repair refuses conflicting unlisted
resources rather than deleting them or declaring an unusable installation healthy.
Managed portable lifecycle tests cover extended Windows filesystem paths without
changing host policy. This does not waive NSIS's separate path limits or establish
native GUI/third-party-tool support for long paths.

SDK React exposes update lookup. Signed update installation stays disabled until
production metadata/key material is provided. Launcher React matches its former
Tk manual-release lookup/open-page workflow; it does not install Launcher updates.
Backend rollback qualification is separate. Neither should be documented as a fully
automated updater simply because the backend has safe staging helpers.

## Qualification sequence

The selected 0.6.4 distribution mode is **unsigned manual download**. There is no
near-term SignPath certificate promise or mandatory replacement certificate
provider. This waives publisher signing for this channel only, not origin,
containment, checksums, tests or acceptance. Keep automatic-update verification
enforced and do not enable the incomplete update-install UI as a workaround.

1. Review and identify the exact source; reconcile versions and generated paired
   binaries. Preserve dirty work until reviewed rather than silently discarding it.
2. Run [documentation checks](development.md#documentation-checks), full automated
   gates and [migration harness](react-release-harness.md). Record skips/failures.
3. Build and verify a new candidate from those inputs. Compare staged, packaged
   and installed identities; do not substitute an earlier local executable.
4. Exercise the full Windows lifecycle in a disposable environment with
   outside-root and user-data canaries. Inspect child processes and console hiding.
5. With approval, collect actual Legacy/Enhanced acceptance against the final
   binaries and dependencies; validate the independent session anchor.
6. Disclose unsigned distribution, verify final checksums and build identity, and
   publish only with separate approval. Do not claim a publisher signature.

Report **package integrity**, **automated tests** and **live acceptance** as
separate results. A matching log hash, successful executable start, or green
targeted UI test run cannot imply release readiness.

## GitHub and manual-download handoff

Use only the current `RELEASE_NOTES.md` as the 0.6.4 release body; older notes
are in the [history archive](archive/release-notes-before-0.6.4.md). Avoid generated
commit-list appendices or copying the entire README into a release description.
Do not promote a legacy Python/Tkinter ZIP as a standalone React Launcher.

After its freeze pipeline and remaining parity gates are complete, the final
asset list must identify the exact shell/service/resources and any companion
runtime versions, with final SHA-256 checksums and recorded signature status.
Preserve valid third-party signatures without claiming they sign the project.
Windows warnings are not a reason to disable security protections; checksums
prove byte consistency, not publisher authentication.

## Recovery and known limits

Recovery backups and receipts remain available. Rollback rejects changed
targets or invalid manifests, rather than overwriting unowned files. Native
writers with an uncertain outcome must not be killed/restarted automatically.
Keep backups until the replacement has been verified.

No game installation, GTA process, signing configuration or published release is
changed by documentation or source-test work. See the [manual](launcher-guide.md)
and [architecture audit](architecture-review-react-0.6.4.md) for boundaries.
