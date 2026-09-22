# Content capacity profile builder

The `allin1 capacity` commands build **export-only, unqualified candidates** from a complete extracted stock `gameconfig.xml`. They do not edit RPF archives, install native limit adjusters, or certify compatibility with a game update.

## Workflow

1. Extract `common/data/gameconfig.xml` from the current installation's **stock** `update/update.rpf`, not its mods overlay.
2. Run `allin1 capacity inspect stock-gameconfig.xml`. Review the edition, pools, and `source_sha256`.
3. Export a candidate, using the fingerprint returned by inspection:

```text
allin1 capacity build stock-gameconfig.xml --edition enhanced --game-build 1.0.1158.16 --source-sha256 <fingerprint> --preset addon-headroom --output capacity-candidate
```

The output directory must be new, with an existing parent. It contains the original XML bytes, generated `gameconfig.xml`, and `profile.json` with fingerprints and before/after pool values. Preserve the receipt with any test results. Source fingerprints authenticate the exact extracted file bytes; the CLI removes a UTF-8 BOM and normalizes CRLF line endings only for safe XML parsing.

The default `stock` preset changes nothing. `addon-headroom` uses ALLIN1's existing experimental per-edition targets; these are not universal safe limits and are **not qualified for this executable merely because generation succeeds**. Explicit `--pool MetaDataStore=4000` overrides are available. Existing larger values are preserved. Unknown or ambiguous pools, unsupported schemas, invalid values, edition mismatches, and stale source hashes are rejected.

After a game update, extract and inspect the new stock XML and build a fresh candidate. Do not copy the old generated XML over the new stock document. A successful build only validates the configuration transformation; manual review and loading tests remain necessary. There is deliberately no automatic installation or automatic profile activation yet.

Enhanced profiles resolve one base `Any` and one PC `x64` pool section for Windows release use. The effective PC entry is changed, leaving console and debug sections intact. Every scope must explicitly declare `Build`, `Platforms`, and `SubPlatforms`; missing, unknown, duplicate same-precedence, or ambiguous selectors are rejected. Repeated names within one section remain an error; repeated base/PC names are legitimate overrides.

## Research and boundaries

Reviewed author documentation on GTA5-Mods:

- [F7YO — Gameconfig for Legacy & Enhanced](https://www.gta5-mods.com/misc/gta-5-gameconfig-300-cars): distinct edition/update variants; separate heap, packfile, and optional weapon-limit tools; traffic-density choices separate from content capacity.
- [BadassBaboon — Expanded & Enhanced Gameconfig](https://www.gta5-mods.com/misc/expanded-enhanced-gameconfig-gta-5-enhanced): documented pool adjustments across asset categories, with explicit Enhanced BVH/native limitations that XML cannot solve.

These pages informed the builder's boundaries. No third-party archive, XML, or tuning table is bundled or copied. The builder leaves traffic, unrelated settings, and native patches alone. It cannot repair malformed models, replace executable compatibility gates, or infer a safe pool size from catalog item counts. Near-full crash-context stores are evidence to investigate, not proof of the crash cause.
