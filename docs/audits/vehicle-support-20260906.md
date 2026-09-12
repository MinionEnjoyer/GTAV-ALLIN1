# ALLIN1 vehicle coverage audit

> **Historical snapshot — September 6, 2026.** The findings, counts, source
> identity, and raw evidence below describe that audit only; they are not the
> current vehicle-catalog policy. See the [current complete vehicle catalog
> policy](../complete-vehicle-catalog.md) for the later browse-only expansion.

Date: 2026-09-06 (America/Los_Angeles). Read-only implementation audit; report artifacts only.

## Verdict

ALLIN1 has broad vehicle infrastructure, but its built-in marketplace is not a complete GTA V / GTA Online roster. The strongest immediate defect is classification, not a lack of a new engine system: **78 native Sports models are recorded as Sports Classics**, and that same classification feeds traffic replacement.

Against the **935 distinct Rockstar model identifiers** in the local archive inventory, ALLIN1 lists **717 (76.7%)**. **218 are absent**. Another **25 are listed but have no supported GBAY delivery destination**, because their route is an unimplemented hangar. The other **692 have a storage route in code**, not a blanket in-game PASS.

This is model coverage, not a count of today's purchasable retail vehicles. Variants, mission vehicles, trailers, trains and submarines remain visible in the denominator instead of being silently discarded. Story and Online are overlapping sets, not two mutually exclusive catalogs.

## Evidence and boundaries

- Local source HEAD: `855f552caf8ccd87dedb41088c4a0fd5b04b187b`. This working copy contains unrelated drafts; audited source hashes are retained in the JSON appendix. No build, installed DLL or released ZIP has been certified by this audit.
- Fresh read-only scans of **both local installations** found 935/935 resolved vehicle/layout records from 104 archives each, with zero warnings. Their model sets match the checked-in Enhanced seat inventory exactly.
- Local executable versions: Legacy 1.0.3889.0; Enhanced 1.0.1158.13.
- The archive scanner enumerates metadata files; it does **not** evaluate every active dlclist/content flag, entitlement, model streaming request or edition-specific native behavior. Both disks containing a model does not establish Legacy support.
- The pinned [DurtyFree extracted model dump](https://github.com/DurtyFree/gta-v-data-dumps/blob/b8f9dfaee5139fe372f264df4030506d1450fd8a/vehicles.json) supplies classes/types/display names for 921 models (revision b8f9dfaee5139fe372f264df4030506d1450fd8a, December 15, 2025). The 14 additional local models come from `mp2026_01`; their class evidence comes from our recorded native grounding audit. Type labels for those 14 are explicitly inference, not a fresh type extraction.
- Rockstar's [Title Update 1.73 notes](https://support.rockstargames.com/articles/4vRqEDvjUs9h7nqRUgc8YO/gtav-title-update-1-73-notes-ps5-ps4-xbox-series-x-or-s-xbox-one-pc-enhanced-legacy) confirm the 2026 content and the Enhanced restriction for the Armored Caracara. This audit supplements the older public dump rather than presenting it as current by itself.
- Existing grounding evidence is dated August 13, 2026. It is not a new in-game test run.
- No game was launched, no save was edited, no game archive was patched, and no vehicle was purchased or spawned during this audit.

Fresh raw reports: [Legacy](../../.work/vehicle-support-audit-20260906/legacy-seats.json), [Enhanced](../../.work/vehicle-support-audit-20260906/enhanced-seats.json). The full 935-row comparison and source hashes are in [vehicle-support-20260906.json](vehicle-support-20260906.json); a readable matrix is in [vehicle-support-matrix-20260906.md](vehicle-support-matrix-20260906.md).

## What “supported” currently means

| Layer | Observed coverage | What it establishes |
|---|---|---|
| Static Online catalog | 463 | A model/name/price entry; not proof it is Online-exclusive |
| Official Story catalog | 256 | Curated base metadata entries; installed by the official content package |
| Unique combined catalog | 717 | 463 + 256 minus vigero/stretch overlap |
| Regular garage route | 651 | Subject to runtime availability, map, money, capacity and size checks |
| Helipad route | 25 | Subject to helicopter eligibility and destination constraints |
| Harbour route | 16 | Subject to boat eligibility and destination constraints |
| Hangar route | 25 | Declared route; no implemented delivery destination |
| Seat/layout metadata | 935 | Resolved metadata; not proof of every seat animation or entry |
| Recorded stable ground placement | 821 total; 652 listed | Prior bounded placement evidence, not comprehensive vehicle operation |
| Stable-grounding models missing from GBAY | 169 | Existing infrastructure reaches beyond the storefront |

Static and Story duplicates are intentionally deduplicated, with static listings taking precedence. `RuntimeVehicleCatalog.IsModelAvailable` checks listing membership and native `IsInCdImage && IsVehicle`. Purchases revalidate the listing, price and funds. The dynamic catalog also checks native type against declared storage.

Existing generic garage rules may accept an already-acquired vehicle absent from GBAY. Therefore **not listed means unavailable through the built-in catalog**, not “the engine cannot spawn it” or “every ALLIN1 subsystem rejects it.”

## Findings

### 1. High priority: 78 Sports models are misclassified

The mismatch exists in `data/vehicles.toml`, the JSON export, and generated `VehicleList.cs`; it is not merely an outdated generated file. Examples include the Kuruma, Elegy Retro Custom, Jester RR, Itali RSX, Comet S2, Cypher, and Pariah.

`VehicleList.Sports` contains **only cartuccia**. `VehicleList.Sportsclassics` contains 101 models, of which 78 are native SPORT models in the reference dump. `TrafficSpawner.CLASS_MAP` consumes these arrays directly. This changes storefront grouping and places modern sports models into the pool intended for classic-sports replacements. The stricter native-class validation applied to third-party traffic entries does not repair the built-in arrays.

Evidence: [TOML](../../data/vehicles.toml#L849), [generated arrays](../../script/src/VehicleList.cs#L792), [traffic mapping](../../script/src/TrafficSpawner.cs#L64).

There are 107 normalized catalog-vs-native class differences in the older-dump intersection. **Do not treat all 107 as bugs**: military/special storefront groupings and commercial-to-industrial folding include intentional choices. The 78-model Sports cluster is the clear systemic defect.

### 2. High priority: the Story/base-versus-Online split leaves whole DLC groups out

The Story generator reads the base `vehicles.meta` from update.rpf and deliberately filters its supported types. It does not merge all the earlier DLC metadata. The other catalog describes itself as Online-exclusive. Those approaches leave earlier shared Story/Online DLC models between the two lists.

The entire `mpbusiness`, `mpbusiness2`, `mpbeach`, `mphipster`, `mppilot`, `mplts`, `mpindependence`, `mpchristmas2` and `spupgrade` model groups are absent from GBAY. This includes ordinary, recognizable omissions, not just new or exotic vehicles.

Examples:
- Zentorno, Turismo R, Jester, Massacro, Alpha, Huntley S.
- Panto, Rhapsody, Glendale, Warrener, Bifta, Dubsta 6x6.
- Dukes, Duke O'Death, Blista Compact, Stallion and their special variants.
- Hakuchou, Innovation, Thrust, Sovereign.
- Swift, Speeder, Besra and Dodo; aircraft additionally require addressing the existing hangar limitation.

There are also later gaps: Calico GTF, Greenwood, Broadway, Eudora, Brigham, Retinue Mk II, Weaponized Ignus, Insurgent (unarmed), Sparrow variants, Veto Classic/Modern and others. Some service/mission variants warrant intentional exclusion rather than automatic sale.

Evidence: [Story generator](../../src/allin1/generators/story_vehicle_catalog.py#L130), [catalog contract test](../../tests/test_vehicle_catalog.py#L376). A test asserting exactly 256 Story entries checks the current curation, not complete Rockstar coverage.

### 3. High priority: 25 listings have no purchase-to-storage route

The code routes 24 planes plus the Thruster to `hangar`. The destination UI and Reactor contract explicitly report **Hangar unavailable**. A listing or preview does not establish a functioning ownership workflow.

Affected models:
`alkonost`, `alphaz1`, `avenger`, `bombushka`, `duster2`, `howard`, `hydra`, `luxor2`, `microlight`, `mogul`, `molotok`, `nimbus`, `nokota`, `pyro`, `raiju`, `rogue`, `seabreeze`, `starling`, `streamer216`, `strikeforce`, `thruster`, `titan2`, `tula`, `velum2`, `volatol`.

A further 19 conventional aircraft are unlisted. The broad native PLANE class also includes three blimps, treated separately in the missing-model grouping. There is an `ExecuteDeliverHere` helper, but no call site was found in the inspected source; it cannot be counted as a user-accessible workaround.

Evidence: [storage routing](../../script/src/RuntimeVehicleCatalog.cs#L652), [Reactor destinations](../../script/src/GbayReactorContracts.cs#L2670), [delivery refusal](../../script/src/GbayBrowser.cs#L1729).

### 4. Coverage gaps need different treatment

| Missing-model group | Count |
|---|---|
| Special transport (trailers, rail, blimps, submarines) | 47 |
| Unlisted conventional aircraft | 19 |
| Drift-specific model variants | 27 |
| Arena War-era models, including RC Bandito | 32 |
| Other catalog gaps (ordinary vehicles and special/service variants) | 93 |

These groups are mutually exclusive and total 218. “Arena War-era” includes 31 other models plus RC Bandito; “other catalog gaps” includes ordinary vehicles, special/service models and mission duplicates. They are not all safe candidates for normal garage sales.

The 2026 pack has **10/14 listed**. Its unlisted records are `driftcoquette`, `driftdominator8`, `driftelegy`, and `trflat2`. The recent ten main vehicle entries are already present; the largest problem is accumulated omissions, not simply lagging the newest update.

All 27 `drift*` variants in this inventory are unlisted. Having a base car or a native mod-slot persistence mechanism does not prove that its drift conversion is implemented.

### 5. Legacy and Enhanced need separate support claims

The shared static catalog has no per-entry edition field. Runtime model checks are the meaningful last gate, not a blanket promise that both versions offer every entry.

The five `mpg9ec` model entries have four listings—Arbiter GT, Astron Custom, Cyclone II and S95—but Weaponized Ignus (`ignus2`) is missing. Rockstar describes the [PC Enhanced vehicle/HSW additions](https://www.rockstargames.com/newswire/article/akk98a4o755825/free-upgrade-for-grand-theft-auto-v-on-pc-coming-march-4) separately. The 2026 Armored Caracara is also explicitly edition-restricted in the official update notes.

Local Legacy files containing these metadata records must not be interpreted as evidence that they load or behave correctly in Legacy. **No edition-specific live PASS is assigned to any model here.**

### 6. Vehicle features are not equivalent to Online feature parity

ALLIN1 has generic model creation, colors, persistent storage, 50 saved native mod slots/toggles, liveries, extras and related vehicle state. This is useful infrastructure. It does not itself establish full HSW/Benny's/Arena conversion workflows, Imani equipment, aircraft workshops, business interiors, RC control or vehicle-specific scripted abilities.

For example, a Terrorbyte listing is not proof of an operational Online business terminal. A supported model, its mission integration, and its complete upgrade ecosystem are distinct claims.

The getaway compatibility code covers three named Story preparation contexts and preserves eligibility checks such as seats, police/taxi exclusions, health and speed. It is not general compatibility with every Story mission. Grounding and seat inventories likewise establish narrower facts than a full buy/deliver/save/reload/drive/special-ability test.

### 7. Traffic is a separate, inconsistent coverage surface

406 static TOML entries declare popgroup assignments, while the script's configured road-class pools cover 354 static entries. These are **different mechanisms**, not an assertion that 406 or 354 vehicles will be simultaneously active. Story catalog entries intentionally disable additional package traffic to avoid duplicating the base population.

Any roster correction should review both mechanisms. Correcting a GBAY listing alone does not guarantee traffic participation, and a model in traffic need not be purchasable.

## Coverage by Rockstar class

Classes are native/reference classes, not ALLIN1 storefront groupings.

| Rockstar class | Models | Listed | Missing | Listed but no delivery destination |
|---|---|---|---|---|
| BOAT | 26 | 16 | 10 | 0 |
| COMMERCIAL | 24 | 19 | 5 | 0 |
| COMPACT | 18 | 13 | 5 | 0 |
| COUPE | 21 | 19 | 2 | 0 |
| CYCLE | 9 | 9 | 0 | 0 |
| EMERGENCY | 35 | 35 | 0 | 0 |
| HELICOPTER | 31 | 25 | 6 | 0 |
| INDUSTRIAL | 12 | 12 | 0 | 0 |
| MILITARY | 17 | 12 | 5 | 1 |
| MOTORCYCLE | 59 | 50 | 9 | 0 |
| MUSCLE | 97 | 63 | 34 | 0 |
| OFF_ROAD | 71 | 55 | 16 | 0 |
| OPEN_WHEEL | 4 | 4 | 0 | 0 |
| PLANE | 46 | 24 | 22 | 24 |
| RAIL | 11 | 0 | 11 | 0 |
| SEDAN | 48 | 43 | 5 | 0 |
| SERVICE | 14 | 11 | 3 | 0 |
| SPORT | 126 | 99 | 27 | 0 |
| SPORT_CLASSIC | 54 | 39 | 15 | 0 |
| SUPER | 66 | 63 | 3 | 0 |
| SUV | 51 | 48 | 3 | 0 |
| UTILITY | 53 | 21 | 32 | 0 |
| VAN | 42 | 37 | 5 | 0 |

## Coverage by source metadata pack

Pack names describe source records; they are not a universal Story/Online availability or unlock classification.

| Metadata pack | Models | Listed | Missing |
|---|---|---|---|
| `base` | 298 | 256 | 42 |
| `mp2023_01` | 17 | 13 | 4 |
| `mp2023_02` | 33 | 18 | 15 |
| `mp2024_01` | 21 | 17 | 4 |
| `mp2024_02` | 18 | 14 | 4 |
| `mp2025_01` | 19 | 14 | 5 |
| `mp2025_02` | 15 | 11 | 4 |
| `mp2026_01` | 14 | 10 | 4 |
| `mpapartment` | 25 | 18 | 7 |
| `mpassault` | 16 | 13 | 3 |
| `mpbattle` | 14 | 12 | 2 |
| `mpbeach` | 4 | 0 | 4 |
| `mpbiker` | 21 | 18 | 3 |
| `mpbusiness` | 4 | 0 | 4 |
| `mpbusiness2` | 4 | 0 | 4 |
| `mpchristmas2` | 4 | 0 | 4 |
| `mpchristmas2017` | 30 | 29 | 1 |
| `mpchristmas2018` | 46 | 14 | 32 |
| `mpchristmas3` | 17 | 13 | 4 |
| `mpexecutive` | 14 | 12 | 2 |
| `mpg9ec` | 5 | 4 | 1 |
| `mpgunrunning` | 19 | 15 | 4 |
| `mphalloween` | 2 | 0 | 2 |
| `mpheist` | 21 | 15 | 6 |
| `mpheist3` | 20 | 18 | 2 |
| `mpheist4` | 21 | 16 | 5 |
| `mphipster` | 7 | 0 | 7 |
| `mpimportexport` | 24 | 20 | 4 |
| `mpindependence` | 2 | 0 | 2 |
| `mpjanuary2016` | 2 | 2 | 0 |
| `mplowrider` | 8 | 7 | 1 |
| `mplowrider2` | 7 | 5 | 2 |
| `mplts` | 3 | 0 | 3 |
| `mpluxe` | 6 | 5 | 1 |
| `mpluxe2` | 6 | 6 | 0 |
| `mppilot` | 4 | 0 | 4 |
| `mpsecurity` | 17 | 15 | 2 |
| `mpsmuggler` | 19 | 19 | 0 |
| `mpspecialraces` | 4 | 4 | 0 |
| `mpstunt` | 15 | 15 | 0 |
| `mpsum` | 15 | 14 | 1 |
| `mpsum2` | 18 | 17 | 1 |
| `mptuner` | 18 | 16 | 2 |
| `mpvalentines` | 1 | 0 | 1 |
| `mpvalentines2` | 1 | 0 | 1 |
| `mpvinewood` | 22 | 21 | 1 |
| `mpxmas_604490` | 1 | 1 | 0 |
| `spupgrade` | 13 | 0 | 13 |

## Recommended order — no changes made

1. Correct the 78-model class defect and verify the GBAY and traffic arrays together.
2. Review the 93 mixed ordinary/service/mission omissions, starting with ordinary cars and bikes and the wholly missing earlier DLC groups. Explicitly label the remainder instead of silently dropping them.
3. Make the 25 hangar-dependent entries honestly unavailable in support claims; deciding whether to build a hangar is separate scope, not a catalog-only fix.
4. Keep drift, Arena, rail/trailer/submarine and special-function support explicit. Do not auto-add every record to traffic or garages.
5. Validate representative purchase/delivery/save/reload behavior per edition before claiming complete runtime coverage.

## Verification performed

- Case-insensitive model matching, duplicate detection and exact set comparisons across TOML, JSON catalog, generated C# All array, Story catalog, public dump and both fresh local metadata scans.
- All 463 TOML model/name/category values match the exported JSON; all 463 model identifiers match the generated C# All array.
- All 921 public-dump identifiers occur in the 935-model local inventory. The extra 14 are exactly the 2026 pack records.
- 90 existing Python catalog/generator tests passed. A pytest cache permissions warning did not affect results. These tests do not assert complete Rockstar coverage and passed despite the classification issue.
- Report counts are internally reconciled: 717 + 218 = 935; 651 + 25 + 16 + 25 = 717; 692 + 25 = 717.
