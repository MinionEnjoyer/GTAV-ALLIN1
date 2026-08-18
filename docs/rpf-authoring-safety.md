# RPF authoring safety

ALLIN1 uses two separate RPF components:

- **OpenRPF** is the GTA V Enhanced runtime loader. It redirects the game to
  the `mods` tree and is never downloaded or replaced by ALLIN1.
- **CodeWalker.Core** is the development-time reader/writer used by
  `RpfPatcher.exe`. `runtools.ps1` pins the Enhanced-aware
  `crxhvrd/CodeWalkerProjects` commit
  `0bf552913d96da9ad1f266eb5c7d6d75b96c89f2` so an upstream change cannot
  silently alter serialized archives.

The original files under GTA V's `update` directory remain untouched. ALLIN1
stages payloads, writes only beneath `mods`, verifies each generated archive,
and keeps feature-specific rollback material. A structurally readable archive
is not considered proven safe until GTA V Enhanced reaches Story Mode with it
registered.

## Runtime quarantine

The independent `allin1_smoke` weapon DLC is quarantined because it produced
repeatable startup hangs despite passing structural XML/RPF verification.
Install / Repair removes the archive, records the exclusion, and retains the
script-only smoke fallback. The launcher also refuses to start if a quarantined
archive or an incomplete `allin1_*` pack reappears.

## Rules for new packs

1. Build to a staging directory; never write directly into the active pack.
2. Validate required metadata, nested archives, references, and hashes.
3. Install and register the pack transactionally while GTA is closed.
4. Run a Story Mode canary before enabling the pack by default.
5. On failure, unregister only that pack and preserve known-good ALLIN1 packs.

Whole-archive swaps and launcher-network workarounds from older GTA V modding
guides are not part of this workflow.
