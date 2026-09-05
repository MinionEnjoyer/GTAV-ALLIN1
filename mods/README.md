# Optional mod packages

The launcher can install local, user-supplied mod packages without bundling or
downloading third-party mods. In React, use **Packages** to select and review
the package's `mod.toml` or supported package archive. The older **Mods > Import
& install package** menu belongs to the retained Tkinter interface.

A package is a directory containing `mod.toml` plus the payload files named by
its `[[files]]` and/or `[[rpf_entries]]` entries. Packages placed under
`mods/catalog/<mod-id>/` appear in
the launcher's local catalog automatically.

Supported package types:

- `asi`: root-level `.asi`, `.dll`, `.ini`, and `.toml` files
- `script`: files installed below `scripts/`
- `rpf`: `.rpf` archives installed below `mods/`
- `config`: configuration/data files installed below `scripts/` or `mods/`
- `mixed`: a reviewed combination of supported root plug-ins, scripts, data,
  whole RPF archives, and/or entry-level RPF patches

Most examples are inert templates: rename `mod.toml.example` to `mod.toml` only
inside a real package containing the referenced payload. The
`examples/content-extension/` package is an intentionally safe, non-executable
schema version 2 example that can be inspected as-is. The launcher validates
paths, editions, declared dependencies, conflicts, and optional SHA-256 hashes.
It records installed files, backs up replaced files, supports enable/disable,
and restores backups during uninstall.

Declare `editions = ["legacy"]`, `editions = ["enhanced"]`, or both. The Mods
catalog displays this tag and routes the install to the matching Legacy or
Enhanced directory configured in the launcher. Both game editions may be
installed and managed at the same time. Importer results with insufficient
evidence are tagged **Unresolved** and remain review-only.

For a narrowly scoped patch inside an existing archive, use an RPF or mixed
package with `openrpf` and an entry table:

```toml
type = "mixed"
editions = ["enhanced"]
dependencies = ["openrpf"]

[[rpf_entries]]
source = "payload/Enhanced/interior.ymap"
archive = "mods/x64h.rpf"
entry = "levels/gta5/interiors/interior.ymap"
sha256 = "<64 lowercase hex characters>"
```

The archive must be below `mods/`; if the mods copy is absent, ALLIN1 creates it
from the corresponding stock archive. The installer backs up, writes, verifies,
owns, disables, and restores only the declared entry. It refuses collisions and
external changes instead of overwriting another tool's work.

RPF add-ons that require a `dlclist.xml` entry must also declare
`dlc_packs = ["pack_name"]`, depend on `openrpf`, and own the matching
`mods/update/x64/dlcpacks/pack_name/dlc.rpf` destination. Registration is part
of the same managed lifecycle: install/enable registers it and disable/uninstall
removes it. Raw OIV, ZIP, RAR, and 7z files are inspected in the **Add-on Content
SDK** first; the mod installer intentionally accepts only a reviewed `mod.toml`.
An already-registered pack remains externally owned and is never removed by
ALLIN1.

## Declarative content extensions

Package schema version 2 can register typed launcher settings, GBAY section and
catalog metadata, package requirements, and game-runtime assembly metadata. It
does not permit arbitrary launcher UI, Python, or command injection. Extension
packages use an `[allin1]` table in `mod.toml` and a versioned
`allin1.content.json` descriptor.

Start with the safe example in `examples/content-extension/`, then read the
[content extension API guide](../docs/content-extension-api.md) for the complete
schema, lifecycle, security model, compatibility rules, and required Story-save
behavior for GBAY transactions.
