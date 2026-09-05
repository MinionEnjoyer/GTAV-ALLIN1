# Suppressor sleeve animation tracking

## Current: confirmed Enhanced fix; release version 1.2.1 — 2026-09-04

The user confirmed that the suppressor now works. The matching live session
`7e8f3fdb2a93` identifies Enhanced, candidate 1.2.3 and DLL SHA-256
`73126d69254b76e044e709d5a5a5c57fc24f6cb1ea1d1a4971726649f8d0b9a1`.
It selects mount 9 instead of name-lookup alias 10; during reload the alias
separates by approximately 0.38 m while the sleeve remains at the selected mount.
The user's rendered-motion observation confirms the fix beyond native telemetry.

Public release metadata is 1.2.1 by the maintainer's explicit request. Rebuild
both hosted and standalone DLLs with that identity and preserve the working
gameplay code and edition-specific assets. Legacy carries the same source fix;
do not treat the Enhanced run as a new Legacy gameplay validation. Historical
candidate numbers and hashes below remain unchanged as test provenance.

The user's follow-up clarified that Legacy is the target of this release carryover.
Both 1.2.1 hosted and standalone builds now pass 292 tests, and both edition
packages pass launcher and SDK validation. Legacy's installed SHVDN 3.9.0
exposes the public Name/Tag/Parent hierarchy properties used by the fix.
All gameplay source files compare exactly with the successful candidate;
only release metadata/documentation changed. Existing Gen8 and Gen9 DLC hashes
are unchanged. Complete ALLIN1 ZIPs, standalone OIVs and the combined release
are in `.work/suppressors-release-1.2.1-20260904/downloads/`; a retained source
patch against the immutable baseline accompanies the local validation record.
No release asset upload or game installation was performed in this release pass.
The working Enhanced installation remains candidate 1.2.3; Legacy's existing
1.2.0 managed package remains disabled pending an explicitly requested test setup.

On the user's subsequent push request, source was applied to a clean clone of
`MinionEnjoyer/GTAV-SUPPRESSORS-ENHANCED`, retested (292 standalone / 292 hosted),
and pushed to `main` as `274ef3279a6f3c1e86adb50d86cccb3bcecacbc1`.
Checkout: `.work/suppressors-publish-1.2.1-20260904/`. The 24-file commit includes
the source, tests, example profile, release metadata and shipping documentation;
no local logs, binaries or unrelated ALLIN1 edits. Remote main was verified at
that commit. This is a source push, not a new GitHub Release or tag.

## Historical: 1.2.3 duplicate-mount candidate — 2026-09-04

The user confirmed that 1.2.2 still visibly jumps. Its session `14053ff44b0c`
reports native name lookup bone 10 (`WAPSupp`), no hidden samples and approximately
0.000063 m post-update error. This validates attachment to the *selected* bone,
not that the selected bone matches the rendered component.

The installed Vector archive matches the private 0.5.0 candidate SHA-256
`6129db9d1692e61e1fcea4076fd9b4bb67989cc6ec91f498299942adb3fb7e76`.
Its audited model readback contains duplicate `WAPSupp` tags (4230): bone 10
is a zero-rest-offset child of bone 9, and bone 9 mounts to `Gun_Main_Bone`.
The installed Enhanced SHVDN exposes public Name/Tag/Parent hierarchy properties.

1.2.3 resolves a verified duplicate same-name/tag parent chain to the outer
mount. It does not hard-code Vector indices or alter model geometry. Missing
hierarchy support, different tags/names or corrupt chains retain native lookup.
The next run must show `suppressor_mount_resolved`, expected 10 -> 9 for this
Vector. Native samples also record the lookup/selected indices and their
script-time separation. This is a targeted bone-selection hypothesis, **not a
confirmed rendered-motion fix**; gameplay verification remains outstanding.

292 tests pass in each build. The 20-file source patch reapplies to the immutable
1.2.0 archive and matches current source. Artifacts and receipts:
`.work/suppressor-mount-resolution-20260904/`. Hosted DLL SHA-256:
`73126d69254b76e044e709d5a5a5c57fc24f6cb1ea1d1a4971726649f8d0b9a1`.
Installed on Enhanced with GTA closed. Backup:
`D:/ALLIN1-SDK-Backups/suppressor-mount-resolution/20260904_134343_969773/`.
Vector DLC/profile, heat assets and saved condition are unchanged.

The same pass fixes ALLIN1's preloader consumer row disappearing on a runtime-only
snapshot, labels fully stocked ammunition FULL rather than FREE, and enforces
positive refill prices outside explicit Free Mode with overflow-safe quotes.
The neutral standalone Reactor composition is unchanged. Existing readability
changes were also built into the consumer UI. 1,053 ALLIN1 tests, 236 web tests
and 65 browser readability checks passed. The paired core/bridge and consumer UI
were installed with receipts; shared Reactor native binaries remained unchanged.
Backup: `D:/ALLIN1-SDK-Backups/preloader-ammo/20260904_134354_801733/`.
Two obsolete generated JS/CSS assets were retired; recovery copies are in that
backup. Local generated launcher UI has its previous files under
`.work/preloader-ammo-mount-20260904/previous-generated-ui/`.

## Historical: 1.2.2 hidden-handoff candidate (superseded after unsuccessful live test)

Installed in Enhanced with GTA closed. **Rendered firing/reload motion still
needs the user's in-game test; this is not a confirmed gameplay fix.**

The 1.2.1 live session `4b8ed669bd9d` loaded the correct DLL and Vector profile
without warnings, but the user still saw jumping. That session had only seven
events and no transform samples. It cannot establish a wrong bone versus
animation/render timing. Earlier mock tests assumed successful pose propagation;
they did not prove GTA's actual rendered behavior.

This candidate:

- Keeps a stable attachment instead of binding every tick or forcing updates
  through the player's entire attachment hierarchy. It updates our child prop.
- Supplies the final native attachment lifetime flag explicitly, consistent
  with current [SHVDN's Entity.AttachTo implementation](https://github.com/scripthookvdotnet/scripthookvdotnet/blob/main/source/scripting_v3/GTA/Entities/Entity.cs).
  This contract correction alone is not proven to explain the reported jumps.
- Re-resolves the named bone in the current skeleton; model changes also
  invalidate the cached binding, even if GTA reuses a handle.
- Prepares new heat tiers hidden, checks native attachment and zero-offset
  position, and only then replaces the old tier. Failed candidates are deleted,
  retain the old tier, and retry no faster than every 250 ms.
- Hides an attached sleeve if native transforms are nonfinite or more than
  2.5 cm from the bone origin. This is a drift guard, not proof of rendered
  rotation/alignment. It could hide an effect if the game never supplies a valid
  pose; report that as a failure, not a visual success.
- Emits `heat_overlay_pose_window` at most once per second while a sleeve is
  active, independent of verbose logging: sample/rebind/hidden/invalid counts,
  firing/reload samples, maximum position error, and worst-sample world positions
  and parent/bone identity. Native script-time measurements do not prove that
  the renderer subsequently uses the same pose.

287 tests pass in each of the hosted and standalone builds. Tests now include
independently supplied bad positions, rejected attachments, invalid transforms,
reused handles, persistent binding, hidden-handoff source contracts, worst-case
aggregation, JSON safety and timer wrap. Both SDK and launcher validate the
candidate package. The source patch was reapplied to the immutable 1.2.0 archive
and all 18 changed files were compared with the working source.

Artifacts: `.work/suppressor-pose-handoff-20260904/` (includes package, source
patch, TRX results and installation record). Hosted DLL SHA-256:
`fabafbcf695e331faebe577ab559388dd939e6f7f76588910b7433e49d32aeb4`.
Backup: `D:/ALLIN1-SDK-Backups/suppressor-pose-handoff/20260904_132728_932660/`.

Only the suppressor DLL, content version, managed receipt and derived
registry/preload were updated. 629 other checked game files, the Vector model,
weapon profile, heat DLC, saved condition and existing uninstall backup
references were preserved. No public release was published and GTA was not
launched. Test a hot Vector in first/third person, sustained fire, partial/empty
reload, heat-tier transitions and weapon switching; compare a stock suppressed
SMG if the symptom remains.

## Historical: 1.2.1 candidate (superseded after unsuccessful live test)

Status: source patched and hosted/standalone builds tested; **installed in
Enhanced on 2026-09-04, not yet gameplay-verified**. The reported symptom is the glowing sleeve jumping in front
of the weapon during firing/reloading in Enhanced. Smoke was not confirmed to
be affected.

## Diagnosis and change

The installed JSON-profile development build is `1.3.0-json-profiles.1`. Its
latest Enhanced session loaded the Vector profile with zero discovery warnings,
accepted the Enhanced heat assets, and started the sleeve on `WAPSupp` using
`rs_suppressor_heat_pi_01`. The log establishes activation, not correct motion.

The active source previously refreshed the sleeve every frame only on Legacy.
Enhanced reused the attachment when the parent handle and bone index were
unchanged, even though the animated bone pose can change. It also returned from
the model-streaming path before updating the old visible sleeve. These are
plausible causes of the reported stale-position symptom; live reproduction is
still required to establish that this patch resolves it.

The candidate now synchronizes the ped attachment hierarchy, reattaches the
sleeve to the current weapon bone, and processes the weapon's children every
visible frame on both editions. Existing sleeves refresh before model loading
or fade branches can return; newly created sleeves use the same attachment
sequence. There is no edition or unchanged-handle shortcut in this sequence.
Zero local offsets, synchronized rotation and disabled collision are retained.
This uses the existing engine attachment system, not manual world-position
teleporting. Heat thresholds, fade curves, smoke, wear, scope offsets, weapon
definitions and saved condition are unchanged.

Source: `.work/suppressors-vector-1.2.0/mods/realistic-suppressors/`. This is the
maintainer's archived 1.2.0 working copy with the JSON discovery changes and
corrected 1.2.1 release metadata. The older main-repository 1.1.0 source was not
substituted or rebuilt for this fix.

## Verification

- 277 tests pass for the standalone build and 277 for the ALLIN1-hosted build.
- New tests exercise repeated simulated recoil/reload poses with stable handles,
  weapon/bone changes, invalid attachments and parent-before-child call order.
- A controller source-contract test checks that existing sleeve refresh precedes
  the streaming paths and that the attachment method has no edition guard.
- These tests do not run GTA or prove rendered alignment. No game save, receipt,
  installed DLL, DLC or profile is changed by building the candidate.

Candidate artifacts and checksum validation are recorded under
`.work/suppressor-sleeve-tracking-20260904/`. The hosted Enhanced package reuses
the previously validated heat DLC bytes; no asset rebuild is part of this fix.
The standalone artifact is a DLL update candidate, not a complete OIV installer.

## Enhanced installation — 2026-09-04

Installed on explicit approval with GTA closed. The live hosted DLL now matches
SHA-256 `31286a7b0b334519671eaf90573f13c134c30b14c56e8d40990cfd24d4bc2210`.
The package receipt, content metadata and derived extension registry identify
1.2.1. Only the DLL, content metadata, receipt and derived registry/preload were
updated; 629 other checked game files and external condition data were unchanged.
The Vector profile/DLC and suppressor heat assets were preserved. Original
uninstall backup references remain intact; a full repair package and rollback
copies are in `D:/ALLIN1-SDK-Backups/suppressor-sleeve-tracking/20260904_125049_578160/`.
See `.work/suppressor-sleeve-tracking-20260904/installed.json` for the installation
receipt. GTA was not launched; firing/reload alignment still needs live testing.

## In-game test after an explicitly approved installation

Use a receipt-aware update with GTA closed, retaining the current package and
uninstall backups. The previous installed development label was 1.3.0, but the maintainer
designated this release as 1.2.1; do not simply relabel the existing DLL or receipt.
Do not replace an owned DLL without updating its managed checksum.

With a suppressed Vector heated until the sleeve is visible, check first- and
third-person idle, sustained fire, partial/empty reloads, aiming transitions and
weapon switching. Confirm the sleeve follows the actual suppressor through heat
tier transitions. Repeat on a stock suppressed SMG as a control. If it still
jumps, capture a short clip and the current build's log before changing weapon
geometry or introducing compensating offsets.
