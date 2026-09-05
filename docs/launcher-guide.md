# ALLIN1 Launcher guide — 0.6.4 development

0.6.4 is unreleased. The desktop is React/Tauri v2; Python provides its services
and command-line tools, with no Tkinter fallback. Do not assume an
older downloaded build has every action described here.

## Before starting

Use GTA V Story Mode only. Select Legacy or Enhanced explicitly and verify its
directory. Close the game before installing, repairing, updating, disabling or
removing packages. Keep save files, authored content and recovery receipts.
Do not use the modded launch configuration in GTA Online.

Install trusted, compatible ScriptHookV and the complete ScriptHookVDotNet
Enhanced runtime for the selected edition. The readiness check identifies
missing components; “prerequisites present” does not mean the ALLIN1 client is
installed. Review the Install / Repair plan to add it.

Reactor V is the preferred in-game UI path. It is a separately versioned
dependency with edition-specific validation, not the desktop React renderer.
Dependency downloads require consent. The compatibility renderer and older RPF
artwork path are not proof that Reactor acceptance passed.

## Legacy Python distribution

The batch names remain compatible, but no longer start a Python GUI:

1. Obtain and verify the exact package version you intend to use.
2. Run `install.bat` to prepare its Python environment and review prerequisite
   installation prompts. This is an installation action, not a read-only check.
3. Install a complete Tauri desktop, or set `ALLIN1_LAUNCHER_EXECUTABLE` to a
   complete local candidate's `allin1-launcher-desktop.exe`. Then open
   `manager.bat`; `allin1-gui` forwards to it without a console window.
4. Select the correct game path/edition, review Install / Repair and confirm.
5. Launch only when readiness permits, then use the configured GBAY key in Story
   Mode. Its source default is F9.

The standalone SDK is optional. Not having the ALLIN1 game client installed
does not prevent SDK package authoring.

## React development application

Follow [development setup](development.md). Debug builds use the repository's
Python service; the [candidate builder](../desktop/README.md) produces a frozen
service, native shell and hash-bound resources. Neither is release-qualified.
Do not distribute the development executable by itself.

The React service uses `%LOCALAPPDATA%\ALLIN1\Launcher` for its state by default.
Existing repository configuration may be read as a compatibility starting point;
it is not silently migrated by merely opening a page. Save through a reviewed
action. Setup's **Import previous Launcher preferences** previews a previous
folder's `config.toml` and named profiles, copies only missing files, and preserves
existing preferences and the old folder. A changed source invalidates the review.
Profiles and package/SDK state are not interchangeable with GTA save data.

The UI holds editable drafts; Python validates and writes. A review is bound to
the selected inputs/state, expires, and is consumed once. If source files or
configuration change, reload and review again rather than reusing a token.

## Workspaces

| Workspace | Use | Current limits |
| --- | --- | --- |
| Setup | Choose paths/edition; inspect readiness; save profiles; review save, sync, install/repair, uninstall and launch | Native installer/launch lifecycle not yet qualified |
| Gameplay | Edit existing gameplay configuration and content-bound behavior | Secondary-control descriptions/grouping still need parity review |
| Content | Inspect builtin and installed third-party content; edit schema-labelled settings; save bound preinstall preferences; enable/disable installed entries | Package-owned unbound settings require installation; native interaction acceptance remains |
| Input | Configure keyboard/controller mappings and accessibility values | Verify conflicts and game behavior; desktop tests are not live input acceptance |
| Packages | Inspect a local package and its destinations; edit initial settings; review install, enable, disable or uninstall; browse included content and SDK examples | Reinstall preserves existing settings; native dialog/lifecycle acceptance remains |
| Characters | Edit per-character money/skills, loadouts/ammo, outfit components/props/presets and garage data | Native dialogs and secondary controls still need full parity verification |
| SDK Manager | Inspect/install/remove SDK; open SDK tools; independently configure, import, download or remove an optional assistant pack | Actual upstream downloads, inference and native packaged lifecycle remain separate acceptance work |
| Activity | Read/copy session progress and saved action history; open log folder; export diagnostics; check updates | Clearing the view preserves the journal; complete update-install/rollback UI remains incomplete |
| Help Center | Search task-oriented help in independently scrolling topic/article panels | Guidance must distinguish legacy and React actions |

F1 opens help; Ctrl+1 through Ctrl+9 navigate Launcher workspaces. Theme/sidebar
state is local presentation state. Collapsing a panel does not approve an action.
Do not force-close an unresolved writer; close/restart guards exist to preserve
in-flight operations and drafts. Saving one workspace must not discard another
workspace's draft.

## Package lifecycle and trust

Inspect the package identity, author, edition, file destinations, dependencies
and ownership before confirming. A checksum proves byte consistency, not that
untrusted code is safe. The Launcher does not execute package-provided Python
widgets or shell commands to construct its UI.

The normal Launcher package library includes `%LOCALAPPDATA%\ALLIN1\Packages`,
the same location used by SDK exports. Explicit isolated preview/test hosts use
their own state instead. Inspecting an example does not install it into GTA.

Manifests and archive members must agree exactly and use safe relative paths.
Traversal, Windows aliases, duplicate destinations and link escapes are rejected
before destination writes. Do not rename `allin1-sdk.exe` or another member to
work around an older Launcher's filename check; use a compatible validated build.

Enable/disable/uninstall act on receipt-owned files. If a managed file changed
externally, preserve it and inspect ownership instead of forcing a removal.
SDK removal retains a recoverable installation directory and user files; this is
not equivalent to deleting every SDK-related project or cache on the machine.

The optional [Suppressors Enhanced](realistic-suppressors.md) mod is independently
installed and released. Its 1.2.1 work is not bundled into Launcher/SDK 0.6.4.
Other independent mods, including GTA-V-FPV, keep their own contracts.

## SDK and assistant

The SDK can be installed and used independently of the Launcher and gameplay
client. The Launcher understands the new SDK portable metadata and retained
recovery layout; it does not turn a bare executable into a complete SDK package.
Opening an SDK workspace is navigation, not an implicit package install.

The React Launcher now exposes its own optional assistant configuration,
hardware assessment, reviewed pinned-source download, pack import and removal.
It does not start inference when a pack is installed or a mode is saved. In the SDK, Standalone setup can
save a compatible API or existing local runtime/model configuration without
downloading or starting it. See [assistant boundaries](optional-assistant.md).

## Updates, repair and recovery

Activity shows the current/latest Launcher versions and opens the fixed official
release page. This matches the previous Tk manual-download workflow. The 0.6.4
channel is explicitly unsigned manual download; lookup never installs an update.
Automatic-update signature requirements remain enforced.

The update services validate archive and checksum names together, stage under
contained roots and retain uniquely named backups. Rollback receipts bind the
target and before/after bytes. A stale, wrong-target or tampered receipt is
rejected; this prevents restoring arbitrary files over a different installation.
Keep the original receipt and backup when investigating a failed update.

Repair revalidates package identity and owned payloads; user content is not
discardable just because it lives near a managed installation. A failed or
uncertain write requires evidence inspection, not automatic process termination.
Client removal preserves character/garage saves and their backups, customization,
GBAY preferences, configuration and the legacy `ALLIN1` user-data folder. The
review states that this is not a data purge. Repair also retains the old data
folder; unknown files are not disposable merely because they use an old path.
Read-only status checks do not update the remembered game-path cache.

If the service connection stalls or fails, **Reconnect service** keeps drafts,
invalidates prior reviews and never replays a save. The native broker rejects
malformed/oversized responses and waits at most two minutes without a response
frame. Reconnect cannot terminate a still-running writer with an unknown outcome.
After an interrupted write, verify the files and receipts before reviewing again.
Saving one character document does not refresh the original identity of an
unsaved draft for another document; external changes must be reviewed explicitly.

## Configuration and game behavior

The [generated configuration reference](configuration-reference.md) lists every
source default; saved preferences and content-bound values may differ. Common
controls include `script.gbay_ui_backend`, `script.gbay_key`,
`script.seat_selector_key`, `traffic.enabled`, safe mode and accessibility values.
The seat selector default is L, not the old hold-F prototype.

Official content supplies GBAY categories, purchases, weapons/gear, garage and
character persistence. Reactor presents the in-game UI. The retired F10 world
vector overlay is **not** part of this release. Native runtime behavior still
requires edition-specific acceptance against the final paired binaries.

## Troubleshooting

| Symptom | Safe next check |
| --- | --- |
| Access denied at a game path | Verify the actual path/edition, that GTA is closed, file ownership/permissions and security-software history. Do not grant broad permissions or disable protection as a blanket fix. |
| ALLIN1 missing despite prerequisites | Prerequisites are dependencies, not the client. Review Install / Repair for the selected edition. |
| SDK archive member/checksum mismatch | Re-download the exact matching distribution and use a compatible Launcher. Preserve the rejected archive for diagnosis; do not rename members. |
| GBAY fails to open | Check key/backend settings, readiness, Reactor dependency/receipt and matching core/bridge identity. Collect current-session diagnostics. |
| A custom weapon is missing | Confirm the package is installed/enabled for this edition and supplies valid catalog metadata; authoring alone does not register it in GBAY. |
| Review no longer applies | Reload current state, preserve drafts and review again. The source may have changed or the review expired. |
| Uninstall/rollback refuses | Inspect receipt ownership and backup identity; retain modified user files and recovery evidence. |

Export diagnostics to a new location outside GTA. Review the redacted bundle
before sharing it; do not share API keys or full private projects. Include the
exact app version/build identity, edition, operation and failure time. “The same
version number” is insufficient when development binaries differ.

See [CLI reference](cli-reference.md), [release gates](release-0.6.4.md) and
[documentation index](README.md).
