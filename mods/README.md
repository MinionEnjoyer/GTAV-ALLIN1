# Optional mod packages

The launcher can install local, user-supplied mod packages without bundling or
downloading third-party mods. Select **Mods > Import & install package** and open
the package's `mod.toml` file.

A package is a directory containing `mod.toml` plus the payload files named by
its `[[files]]` entries. Packages placed under `mods/catalog/<mod-id>/` appear in
the launcher's local catalog automatically.

Supported package types:

- `asi`: root-level `.asi`, `.dll`, `.ini`, and `.toml` files
- `script`: files installed below `scripts/`
- `rpf`: `.rpf` archives installed below `mods/`
- `config`: configuration/data files installed below `scripts/` or `mods/`

The examples are inert templates: rename `mod.toml.example` to `mod.toml` only
inside a real package containing the referenced payload. The launcher validates
paths, editions, declared dependencies, conflicts, and optional SHA-256 hashes.
It records installed files, backs up replaced files, supports enable/disable,
and restores backups during uninstall.

