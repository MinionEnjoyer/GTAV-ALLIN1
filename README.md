<p align="center">
  <img src="src/allin1/assets/ALLIN1.png" alt="ALLIN1 Launcher" width="120" height="120" />
</p>

# ALLIN1 Launcher

A Windows launcher and guarded package manager for **GTA V Story Mode**, supporting Legacy and Enhanced.

**0.6.4** — **unsigned prerelease.** Both desktop interfaces use **React in Tauri v2**; Tkinter source and GUI build targets are removed. Python remains the shared service/CLI backend. This is not a fully qualified stable release: native-window, installer and live acceptance remain untested for these candidates.

Start with the [0.6.4 release guide](docs/release-0.6.4.md), [Launcher manual](docs/launcher-guide.md), or [documentation index](docs/README.md).

0.6.4 prereleases are **unsigned manual downloads**, without a
promised SignPath certificate. Verify official release checksums and build
identity after publication; checksums are not publisher authentication. Existing
automatic-update trust checks remain enforced. See the [0.6.4 notes](RELEASE_NOTES.md).

## Product boundaries

| Component | Responsibility |
| --- | --- |
| Launcher | Paths/edition, profiles, dependency consent, configuration, package lifecycle, diagnostics and launching |
| ALLIN1 SDK | Independent package/asset authoring and inspection; optional Launcher handoff |
| ALLIN1 Online Content | GBAY catalogs, vehicles/weapons/gear, garages, properties, character systems and traffic |
| ALLIN1 Experimental Gameplay | Optional NPC physics/police features; off by default |
| Reactor V | Separately provisioned in-game renderer dependency; not the SDK viewport |
| Suppressors Enhanced / weapon pack bundle / GTA VR / FPV | Independent projects, not ALLIN1 release components |

These four projects are not bundled in the ALLIN1 Launcher or SDK and have separate releases and test gates. Generic package management, weapon authoring and GBAY integration remain ALLIN1 capabilities; supporting a package does not make it bundled content.

## What is available

The existing services support explicit Legacy/Enhanced selection, install/repair, receipt-owned package import/enable/disable/uninstall, profiles, readiness checks, diagnostics, SDK management and character/garage configuration. Official content supplies GBAY purchasing, category catalogs, owned loadouts and persistent per-character garages.

React exposes nine Launcher workspaces: Setup, Gameplay, Content, Input, Packages, Characters, SDK Manager, Activity and Help Center. Core workflows, local Qwen provisioning and catalog settings have real-Python synthetic tests. Native packaged lifecycle and exhaustive interaction acceptance remain unqualified. See the [release guide](docs/release-0.6.4.md#remaining-work), not page counts, for release status.

## Using ALLIN1 safely

- Use Story Mode only. Never use the modded configuration in GTA Online.
- Confirm the exact game edition and path before a review. Close GTA before installation, repair, updates or removal.
- Use trusted, version-compatible ScriptHookV/ScriptHookVDotNet Enhanced dependencies. Dependency installation requires deliberate consent.
- Review package identity, destinations, ownership and compatibility before applying changes.
- Retain backups and receipts. Do not rename payload files to bypass package validation.
- SDK package-only authoring does not require the Launcher or ALLIN1 gameplay client.

For Python source users, the [compatibility entrypoints](docs/launcher-guide.md#legacy-python-distribution) now launch an installed Tauri desktop; Python installation alone supplies no GUI. Downloaded builds must be checked against their own published version and artifact identity.

## Development

Install the Python project in an isolated environment, then install the locked frontend dependencies:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop tauri dev
```

The Tauri development host currently uses this checkout's `.venv/Scripts/python.exe`. Rust/MSVC, WebView2 and the Node/pnpm versions recorded in the project are required. The development application can perform real operations after review; use an isolated test setup.

For repeatable disposable checks that do not launch GTA:

```powershell
.venv/Scripts/python.exe tools/react_release_harness.py --product launcher
.venv/Scripts/python.exe tools/documentation_audit.py
```

The [developer guide](docs/development.md) explains coverage, cross-repository tests and native prerequisites. A green targeted harness is not a full coverage gate or release approval.

## Documentation and support

- [Launcher manual](docs/launcher-guide.md): installation modes, all workspaces, recovery and troubleshooting.
- [Configuration reference](docs/configuration-reference.md): every source-default field.
- [CLI reference](docs/cli-reference.md): generated command and parameter inventory.
- [Content extension API](docs/content-extension-api.md): package ownership and typed settings.
- [Release notes](RELEASE_NOTES.md): current unreleased changes and historical releases.
- [ALLIN1 SDK](https://github.com/MinionEnjoyer/ALLIN1-SDK): independently usable authoring tools.
- [Project support](https://buymeacoffee.com/minionenjoyer).

GPL-3.0-or-later; see [LICENSE](LICENSE).
