# ALLIN1 Launcher documentation

**0.6.7 — unsigned portable release; broader qualification remains incomplete.**
This is a curated reading path; the [catalog](catalog.json) lists and classifies
the maintained public documents. Historical evidence qualifies only its named
source/session, not current binaries; architecture proposals are not acceptance results.

## Current guides

- [Launcher manual](launcher-guide.md): install, configure, launch and recover.
- [Traffic population editor](content-injectors.md): configurable authorized vehicle population.
- [GBAY preview downloads and caching](gbay-default-previews.md).
- [0.6.7 release guide](release-0.6.7.md): qualification limits and upgrades; [changelog](../RELEASE_NOTES.md).
- [Development and validation](development.md): canonical setup and checks; [desktop internals](../desktop/README.md).

## Contracts and references

- Interfaces: [CLI](cli-reference.md), [configuration](configuration-reference.md), [content-extension API](content-extension-api.md).
- Packaging: [format/examples](../mods/README.md), [edition-aware bundles](edition-bundles.md), [RPF safety](rpf-authoring-safety.md).
- Catalogs: [vehicles and purchase policy](complete-vehicle-catalog.md), [weapons](gbay-weapon-catalogs.md).
- Driving: [speedometer/telemetry](driving-telemetry.md), [trailer hitches](trailer-hitches.md).
- Validation: [off-game hardening](hardening-harness.md), [React release/Tkinter retirement](react-release-harness.md).
- [Optional assistant](optional-assistant.md).

## Architecture and proposals

- [MPClothes compatibility architecture](mpclothes-compatibility-architecture.md)
- [YMT limit-expansion research and architecture](ymt-limit-expansion-research-and-architecture.md)

## Separate-product references

Integration references retain separate release ownership:
[Suppressors Enhanced](realistic-suppressors.md).

## Historical evidence — not current instructions

- [0.6.4](release-0.6.4.md) and [0.6.5](release-0.6.5.md) release guides, plus [earlier release notes](archive/release-notes-before-0.6.4.md)
- [0.6.4 React architecture-review checkpoint](architecture-review-react-0.6.4.md)
- [Enhanced smoke RPF port](enhanced-smoke-rpf-port.md)
- [Test-tool capability review](test-tools-capability-review.md)

## Documentation maintenance

Checkout-only references: `tests/IN_GAME_CHECKLIST.md` (live acceptance) and
`native/map-host/README.md` (disabled native architecture).

Run the [documentation checks](development.md#documentation-checks) for inventory,
local links/anchors and source-derived CLI/configuration agreement. External
URLs and historical claims are not verified. Old local manuals remain in
`.work/documentation-archive/`, outside release payloads.
