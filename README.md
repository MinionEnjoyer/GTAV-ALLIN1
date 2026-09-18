<p align="center">
  <img src="src/allin1/assets/ALLIN1.png" alt="ALLIN1 Launcher" width="120" height="120" />
</p>

# ALLIN1 Launcher

A Windows launcher and guarded package manager for **GTA V Story Mode**, supporting Legacy and Enhanced.

**0.6.6** — unsigned portable release. React/Tauri v2 provides the desktop UI;
shared Python services power it, the CLI and agent API. Start with the
[Launcher manual](docs/launcher-guide.md) or [release notes](RELEASE_NOTES.md).

## Product boundaries

The Launcher manages installation and launch workflows; gameplay comes from
installed content packages. The optional [ALLIN1 SDK](https://github.com/MinionEnjoyer/ALLIN1-SDK)
authors and inspects packages independently. Reactor V is a separately
provisioned in-game renderer. Package support does not imply bundled content;
check each release's contents and dependencies. The former built-in Experimental
Gameplay package is retired. Independently installed user-authored experimental
packages remain separate receipt-owned content, subject to their own
compatibility and safety checks.

## What is available

- Edition/path selection, profiles, dependency consent, installation and repair.
- Receipt-owned package import, enable/disable and removal; diagnostics and SDK management.
- GBAY catalog and character/garage configuration, with downloaded, cached or locally generated previews.

## Using ALLIN1 safely

- Story Mode only—never GTA Online. Confirm edition/path and close GTA before changing its installation.
- Review package identity, destinations, ownership and compatibility; explicitly consent to trusted, version-compatible dependencies.
- Keep backups and receipts. Never rename payloads to bypass validation.

Portable builds include Python. Keep `runtime/` and `resources/` beside the
executable and extract upgrades into a fresh folder. Blender is needed only for
generating new Blender previews, not downloaded/cached images. Python source
[GUI entrypoints](docs/launcher-guide.md#legacy-python-distribution) require an installed Tauri desktop.

Verify official checksums and artifact identity: checksums do not authenticate a
publisher. Automatic-update trust checks remain enforced. Full installer
lifecycle and fresh final-build Legacy/Enhanced in-game acceptance remain
untested; see the [release guide and qualification limits](docs/release-0.6.6.md#remaining-work).

## Development

Use the [developer guide](docs/development.md) for canonical setup, prerequisites
and validation commands. Automated write tests use disposable fixtures, never
real game data. A targeted harness pass is not release approval. Public
contributions should also follow [CONTRIBUTING.md](CONTRIBUTING.md); report
sensitive issues through the process in [SECURITY.md](SECURITY.md).

## Documentation and support

- [Documentation index](docs/README.md): user guides, developer references and historical evidence.
- [Configuration](docs/configuration-reference.md), [CLI](docs/cli-reference.md) and [content-extension API](docs/content-extension-api.md).
- [Project support](https://buymeacoffee.com/minionenjoyer).

GPL-3.0-or-later; see [LICENSE](LICENSE).
