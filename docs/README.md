# ALLIN1 Launcher documentation

**0.6.5 — unsigned portable release; broader qualification remains incomplete.** Start with the [release guide](release-0.6.5.md) and [Launcher manual](launcher-guide.md).

Current manuals describe implemented behavior and explicit limits. Reference contracts and architecture proposals do not prove native/live acceptance. Historical evidence applies only to its named source/session. Independent mods retain separate release ownership.

## Current guides

- [Product overview and quick start](../README.md)
- [Release notes](../RELEASE_NOTES.md)
- [React/Tauri desktop setup](../desktop/README.md)
- [Development and validation](development.md)
- [Launcher manual](launcher-guide.md)
- [0.6.5 release guide and known limits](release-0.6.5.md)

## Contracts and references

- [CLI command reference](cli-reference.md)
- [Configuration defaults](configuration-reference.md)
- [Content-extension API](content-extension-api.md)
- [GBAY weapon catalogs](gbay-weapon-catalogs.md)
- [GTA IV-style NPC physics experiment](gtaiv-npc-physics-experiment.md)
- [Optional assistant](optional-assistant.md)
- [React release and Tkinter-retirement harness](react-release-harness.md)
- [RPF authoring safety](rpf-authoring-safety.md)

## Architecture and proposals

- [MPClothes compatibility architecture](mpclothes-compatibility-architecture.md)
- [YMT limit-expansion research and architecture](ymt-limit-expansion-research-and-architecture.md)

## Separate-product references

- [Suppressors Enhanced](realistic-suppressors.md)
- [Suppressor JSON profiles](suppressor-json-profiles.md)
- [Suppressor sleeve tracking](suppressor-sleeve-tracking.md)
- [Vector suppressor integration](vector-suppressor-integration.md)

## Historical evidence — not current instructions

- [Earlier release notes](archive/release-notes-before-0.6.4.md)
- [0.6.4 React architecture-review checkpoint](architecture-review-react-0.6.4.md)
- [Enhanced smoke RPF port](enhanced-smoke-rpf-port.md)
- [Test-tool capability review](test-tools-capability-review.md)

## Documentation maintenance

Additional source references:

- Current acceptance checklist and historical cases: `tests/IN_GAME_CHECKLIST.md` (developer checkout only, not shipped tests).
- [Package format and examples](../mods/README.md).
- Disabled native map-host architecture: `native/map-host/README.md` (developer checkout only; excluded from release inputs).

The versioned [catalog](catalog.json) classifies every project manual in this index. Source-derived CLI and configuration references must match code. The offline audit checks local links/headings and uncategorized documents; it does not fetch external websites or certify historical claims.

See [development checks](development.md#documentation-checks). The old ignored local `documentation.md` is now a pointer; its previous contents and the former Launcher README are retained in `.work/documentation-archive/` and excluded from release payloads.
