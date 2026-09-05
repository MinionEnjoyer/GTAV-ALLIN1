# ALLIN1 native map-host scaffold

This directory contains the disabled-by-default policy layer for a future
edition-specific native host for the generated `allin1_maps` deferred property
groups. It is intentionally not included in release packaging.

The implemented, off-game-testable boundary provides:

- an exact six-property allowlist matching the generated DLC metadata;
- package, pack, layout, marker, edition, archive-fingerprint, and group receipt
  validation;
- ref-counted acquire/release behavior and a yacht lease retained until forced
  shutdown;
- typed property requests only—there is no arbitrary group/hash operation;
- fail-closed backend behavior, snapshots, and structured log events; and
- separate Legacy/Enhanced ScriptHookV loading scaffolds, disabled at build and
  runtime by default.

Alloc8or's Legacy and Gen9 native databases now confirm the same canonical
content-change-set ABI on both editions:

- `0x6BEDF5769AC2DC07` is
  `void EXECUTE_CONTENT_CHANGESET_GROUP_FOR_ALL(Hash hash)`; and
- `0x3C1978285B036B25` is
  `void REVERT_CONTENT_CHANGESET_GROUP_FOR_ALL(Hash hash)`.

Those functions operate on a global group hash; they are not pack-scoped. The
database confirmation therefore removes signature uncertainty, but it does not
prove that an arbitrary third-party group is safe to execute on Enhanced.
`plugin_entry.cpp` deliberately contains no native invocation, its backend
always refuses activation, and the host is never prepared or enabled. A
production backend still requires fixed compiled group hashes, ScriptHook-thread
request dispatch, verified installed-pack evidence, and a live Enhanced
isolation canary before either scaffold may be renamed, packaged, installed, or
enabled.

Off-game policy tests:

```powershell
cmake -S native/map-host -B build/map-host -G Ninja
cmake --build build/map-host
ctest --test-dir build/map-host --output-on-failure
```

The optional disabled ScriptHookV targets require an explicit official SDK path
and an explicit opt-in CMake flag. Both the stock `inc/` + `lib/` SDK layout and
the older flat-library development layout are accepted. They remain
nonfunctional safety scaffolds.
