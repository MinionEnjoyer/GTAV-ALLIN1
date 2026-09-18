# Content injectors

The Launcher’s **Content** page has three population editors: **Pedestrians**,
**Traffic**, and **Weapons**. These are Story Mode runtime policies, not binary
replacement installers. Install compatible content through Packages first.
Existing package controls remain under **Existing content**.

## Configure and review

1. Select the correct GTA edition/path in Setup, then open a Content editor.
2. Load its authorized catalog. Only enabled, managed packages with validated
   catalog ownership can contribute models; a model name alone is insufficient.
3. Enable the policy and select the desired entries. Use the slider or manual
   number input for chance, weight, or pedestrian count.
4. Review the changes and confirm with GTA closed. Restart the game/scripts to
   use the policy. A changed file or catalog invalidates a pending review.

Pedestrian and weapon injection default to **off**. With no traffic policy file,
the existing traffic configuration is unchanged. These controls do not alter
player purchases, saved loadouts, original GTA assets, or installation receipts.
Turning an injector off does not uninstall its models or remove GBAY listings.
The Weapons editor has two independent settings: **Enable same-tier weapon
replacement** is the master switch; **Active during story missions** permits
eligible ambient weapon replacements while a mission is running. Turning the
master switch off always stops the injector and retains the mission preference.
Mission activity is off by default, including for existing policies without the
new setting. Enabling it does not permit editing protected mission characters.
Pedestrians affect ambient NPCs only: they do not replace Franklin, Michael,
Trevor, or mission/story characters.

| Editor | List behavior | Limits |
| --- | --- | --- |
| Pedestrians | Disabled, Add to population, or Replace an explicit vanilla ambient model | Up to 20 tracked additions; replacement starts with 36 vetted civilian targets |
| Traffic | Include/exclude authorized package road vehicles and set relative weights, 0.1–20 | Existing Gameplay traffic enablement, population caps, cooldowns and class checks still apply |
| Weapons | Include custom firearms with relative weights, 1–100 | Replaces an armed ambient NPC’s firearm only within pistol, SMG, shotgun or rifle categories; never arms an unarmed NPC |

Chance is the probability of an eligible replacement opportunity, not a promise
that that percentage of every person/vehicle in the world will change. Weight is
relative to other compatible entries. Pedestrian additions are controlled by the
addition cap and cooldown, separately from replacement chance.

The traffic policy’s master switch pauses the traffic spawner; it cannot override
Gameplay’s disabled traffic setting. Its list filters **custom package vehicles**.
The curated stock/DLC civilian pool is retained when traffic is enabled. Package
vehicles must already have the `traffic.catalog` capability, enabled package
`traffic_enabled` setting, and catalog-item traffic opt-in. The editor cannot
grant those permissions or force an aircraft into road traffic.

## Safety and troubleshooting

In game, open **GBAY → Diagnostics → Ped spawner / Weapon spawner** for live
compact live counts and FPS, matching the Traffic status format (for example,
`3/20 managed, 105 FPS` or `4 swaps, 105 FPS`). Details show eligible choices,
session spawns or replacement chance. Pauses, throttling and quarantined models
remain visible; detailed scan/attempt/rejection counters stay in the client log.
Zero swaps can mean no safe, already-armed ambient NPC was eligible, rather than
a disabled injector. These are status views; configuration
remains in the Launcher's Content editors.

Added pedestrians are retained for 90 seconds before returning to ordinary game
cleanup. They appear gradually, off-screen and at least 60 metres away, with one
creation attempt every 3 seconds (6 when adaptively throttled). The addition
cap is an upper bound, not an immediate spawn count. Missions, wanted levels and
other safety pauses release this temporary ownership without deleting peds.

Ped model streaming advances across ticks, with one pending operation and a
3-second timeout. A single model stays warm for up to 30 seconds between uses;
changing models, disabling the policy or entering a safety pause releases it.
Ped scans examine at most 4 candidates (2 when throttled); both injectors yield
after a soft 2 ms scan budget, while always allowing one unseen candidate to
avoid starvation. A native query or creation cannot be interrupted mid-call.
Weapon scans retain their 15/30-second cadence and never arm unarmed NPCs.
Minute summaries include scan, model-create and configuration timing peaks to
help distinguish script work from other causes of driving hitches.

Work is bounded and performed away from the player, off screen. Player entities,
mission/scripted or persistent entities, occupied/interacting peds and active
encounters are protected. Loading, cutscenes, character switching, interiors and
garage transitions suppress population changes. Missions also pause weapons
unless **Active during story missions** is enabled; the ped/traffic mission
rules are unchanged. Wanted levels
still pause pedestrian spawning, but do not pause weapon replacement. Weapon
scans and replacement validation continue during pursuits; individual NPC
safety checks still exclude nearby, visible, in-vehicle or actively fighting
NPCs, as well as protected mission/scripted characters.
Missing/invalid models are rejected; pedestrian model loading has a timeout.
Loaded pedestrian metadata is rechecked across up to three short, tick-based
retries before a non-human model is quarantined. The human-only requirement and
three-second loading deadline still apply. `PedPopulation` logs include the
model hash, whether metadata was checked, the observed ped/human flags, and
retry/recovery/quarantine decisions.
No existing NPC is deleted until its staged replacement passes the safety checks.

An empty list means no compatible **authorized** catalog is available. Installing
a loose model without a managed catalog will not populate it. A disabled package,
missing DLC ownership, unsupported category or altered catalog may also exclude
an entry. Read the catalog warning before reviewing a reset of an invalid policy.
The native runtime’s model/class checks remain authoritative: desktop validation
does not prove animation quality, appearance, or live-game compatibility.

Policies live below the selected game’s `scripts/.allin1/` directory:
`ped-population.json`, `traffic-population.json`, `weapon-population.json`.
Keep these files with your configuration backups. Runtime logs identify
`PedPopulation`, `WeaponPopulation` and `Traffic` activity/rejections.

## CLI and agent API

All editors use the same public review/apply boundary as the desktop:

| Inspect module | Response field | Review action |
| --- | --- | --- |
| `ped_manager` | `ped_population` | `ped_population_save` |
| `vehicle_manager` | `traffic_population` | `traffic_population_save` |
| `weapon_manager` | `weapon_population` | `weapon_population_save` |

Send `inspect` with the module and selected `config`, then edit the returned
`document`. Send `review` with its action, the same config, the edited `document`,
and `expected_document_sha256` from inspection. Display the review before sending
`apply` with `review_id`, `review_sha256` and `confirmed: true`. CLI durable plans
use the existing approval hash workflow. Write authority and a closed game are
required; there is no automatic replay after an interrupted operation.

For weapons, set `document.enabled` for the master switch and
`document.active_during_missions` for mission activity. Both are booleans.
Schema-v1 documents omitting `active_during_missions` remain supported and
normalize to `false`; inspection does not rewrite the installed policy. The
same review/apply flow handles both options. Weapon configuration and minute
summary logs include the mission preference so a test can confirm it loaded.

## Ped package authoring

Weapon and vehicle packages reuse the existing
[weapon catalog](gbay-weapon-catalogs.md) and
[content-extension contracts](content-extension-api.md). Ped packages add the
explicit `ped.population` capability and a catalog declaration of `kind: "ped"`.
It uses the existing descriptor’s `gbay.catalogs` array for transport but does
**not** create a GBAY shop item or require the `gbay.catalogs` capability unless
the package also declares ordinary GBAY catalogs.

Catalog payload example:

```json
{
  "schema_version": 1,
  "id": "example.ped-catalog",
  "name": "Example ambient pedestrians",
  "peds": [
    {"model": "example_civilian", "name": "Example civilian", "source_pack": "examplepeds"}
  ]
}
```

Declare that file as an exact managed manifest destination, for example
`scripts/ExamplePeds/catalog.json`, and use the same source in the descriptor’s
catalog declaration. The installed receipt must declare the `examplepeds` DLC
pack and bind the catalog hash. IDs and model names are validated, catalogs are
bounded to 4 MiB, and ambiguous/malformed declarations fail closed. This is a
data contract, not automatic conversion of arbitrary ped archives. Validate a
new package in Story Mode before distributing it.
