# Vector suppressor and inline attachment actions

Status (2026-09-04): implemented, built, tested and **installed in Enhanced**.

The installed Suppressors Enhanced v1.2.0 was enabled, not disabled. The
2026-09-04 08:54 UTC session reports compatible Enhanced heat assets, enabled
stealth/breakage/smoke, then `unprofiled_weapon` for `3449971877` at 08:55:36.
That is `WEAPON_A1_KRISS_VECTOR` (`0xCDA264A5`): native silenced audio worked,
but the mod deliberately skipped heat/wear for an unknown thermal identity.

The new `A1V45` profile binds that weapon to its actual stock
`COMPONENT_AT_PI_SUPP` (`0xC304849A`), classified as an SMG. It uses the existing
.45-class gameplay approximation: 2.3 °C per shot, 240-second cooling half-life,
325 °C wear/smoke onset, 650 °C critical, and 8,000-round nominal life.
These are game tuning values, not measured KRISS hardware specifications.
The normal heat overlay, smoke, breakage, persistence and replacement logic
remain unchanged. A short burst should not produce an instantly glowing can.
Its durability identity stays separate from the donor SMG.

The repository still carries the older v1.1.0 mod. The profile was backported
there, but the staged runtime is built from the archived **v1.2.0** source at
`D:/Codex-Project-Archives/GTAV-SUPPRESSORS-ENHANCED-v1.2.0-20260904T043845Z.zip`
(SHA-256 `0401747dfcd998b730475d282097df31a26e1a80a3b654a03af6f201badf0b21`).
The archive is untouched; the working copy is
`.work/suppressors-vector-1.2.0/`. Build information identifies the local update
as `1.2.0-vector-profile.1`. This is an explicit mod-side profile, not a new
arbitrary JSON-profile loader or an alteration to the Vector DLC.

GBAY's Reactor attachment cards now pair the original component with a distinct
host-supplied `-unequip` command. The visible equipped card offers UNEQUIP,
retains ownership, and routes through the existing confirmation/live validation.
No equip-to-remove toggles or client-invented mutation parameters were added.
Matching uses exact node identity, never display labels. Controller card order
uses the same paired action. Older/unpaired descriptors retain their explicit
removal action as a compatibility fallback. The legacy native fallback menu
has not been redesigned in this pass.

Validation: 1,044 ALLIN1 tests; 229 Reactor web tests; 218 v1.2.0 suppressor
tests in standalone and hosted configurations; 176 older backport tests.
Browser layout fixture confirmed inline actions for both scope and suppressor,
and no removal action for the required magazine. No in-game validation yet.

Staged output: `.work/vector-runtime-update-20260904/`. It includes the matched
core/bridge pair, v1.2.0 hosted suppressor DLL, compiled React UI assets and an
archive-relative source patch. This is a private developer update, not an
ALLIN1 importable package. Before installing, require GTA closed, back up the
exact affected files, resolve the installed Reactor UI location, preserve its
unrelated assets, and update the suppressor package through receipt-aware
installation. Do not replace a receipt-owned DLL without keeping its managed
checksum accurate. Saves, condition data and the installed Vector DLC should
remain untouched. Test attachment removal/re-equip/save-reload and sustained
suppressed fire after installation.

## Installation verification — 2026-09-04

Installed on explicit user approval while GTA was closed. The staged v1.2.0
profile DLL, matching ALLIN1 bridge/contract and GBAY React bundles are live.
The already-matching ALLIN1 core was not rewritten. The two owning receipts
were upgraded with the exact new hashes; complete validated repair packages
are retained in `.work/vector-runtime-managed-packages-20260904/`. Original
uninstall backup references and package metadata remain intact. Existing
unreferenced React bundles were retained rather than deleted.

This was a guarded, receipt-aware loose-file upgrade: it did not unregister
or reinstall any DLC. Eight paths changed, including the two receipts;
662 other checked files, settings, the Vector DLC and `mods/update/update.rpf`
remained byte-identical. All three installed package receipts verified.
The runtime pair validates as 0.6.1. In-game behavior still needs user testing.

Verified external backups, including the prior standalone SDK, are at
`D:/ALLIN1-SDK-Backups/vector-runtime-refinement/20260904_092137_418324/`.
The detailed result is `.work/vector-runtime-update-20260904/installed.json`.
The SDK NSIS upgrade also completed successfully, and its installed sidecar
passed the standalone resource/helper/protocol smoke test. The new executable
matches the release build apart from Tauri's expected NSIS bundle marker.

The Vector profile in this build remains compiled into Suppressors Enhanced.
Creator-authored per-weapon JSON profiles are a proposed follow-up, not an
existing loader or feature of the installed update.

Follow-up: creator JSON discovery has since been implemented and tested in a
separate **1.3.0 candidate**, with a Vector 0.5.0 package that owns its profile.
That candidate is not installed yet. See [Creator-defined suppressor profiles](suppressor-json-profiles.md).
