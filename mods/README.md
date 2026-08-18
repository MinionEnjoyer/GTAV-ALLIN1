# Optional mod packages

The launcher can install local, user-supplied mod packages without bundling or
downloading third-party mods. Select **Mods > Import & install package** and open
the package's `mod.toml` file.

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

The examples are inert templates: rename `mod.toml.example` to `mod.toml` only
inside a real package containing the referenced payload. The launcher validates
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
source = "OpenIV/Enhanced/interior.ymap"
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
