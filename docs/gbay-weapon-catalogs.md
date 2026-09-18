# GBAY add-on firearm catalogs v1

The package-weapon catalog runtime update adds receipt-authorized firearms to
both native GBAY and the Reactor storefront. The generated stock WeaponList is
not edited. These are data catalogs, not scripts or spawn commands.

The current release target is **0.6.6**. Earlier local experiments
reused 0.6.1, so that number alone cannot establish catalog support. Ship/apply
only the verified matching core and Reactor bridge pair; importing a weapon ZIP
does not upgrade the core. Historical fixture requirements used
`allin1.online-content>=0.6.1`; a new public package must declare the first
unambiguous qualified client release that actually supports its contract.

## Package contract

Use schema-2 `mod.toml`, type `mixed`, a declared DLC pack with its exact owned
`mods/update/x64/dlcpacks/<pack>/dlc.rpf` destination, and the `openrpf`
dependency. Declare the `gbay.catalogs` capability and a `kind: "weapon"`
catalog whose source is an exact package-owned JSON file destination.

```json
{
  "schema_version": 1,
  "id": "example-weapons",
  "name": "Example Weapons",
  "weapons": [{
    "weapon": "WEAPON_EXAMPLE_SMG",
    "name": "Example SMG",
    "category": "smgs",
    "price": 7500,
    "ammo_cost_per_round": 2,
    "source_pack": "examplepack"
  }]
}
```

All fields shown are required; unknown fields are rejected. Catalog ID must
match the declaration. IDs/names are bounded; names cannot contain GTA text
formatting tokens or control characters. Weapon IDs are uppercase
`WEAPON_[A-Z0-9_]{1,56}`; source packs are lowercase and must be declared by the
same package. This proves declared package ownership, not binary metadata
provenance; the runtime also requires a valid loaded native weapon at purchase.

Categories: `pistols`, `smgs`, `shotguns`, `rifles`, `machineguns`,
`snipers`, `heavy`. V1 adds single firearm purchases only, not melee,
throwables, vehicles, components, or bundles. Prices must be integers from zero
to 2,000,000,000; per-round ammo prices from zero to 1,000,000. Booleans and
fractional values are not integers.

Limits: 4 MiB per JSON file, 1–2,048 entries per catalog, 8,192 dynamic entries
merged at runtime. Duplicate names/hashes and stock/official smoke collisions
are rejected. Conflicting catalogs are rejected as a whole; package ID then
catalog ID ordinal ordering establishes deterministic precedence.

## Runtime behavior and boundaries

- Discovery uses enabled, capability-authorized package receipts.
- Read bytes must match the receipt SHA-256, including after discovery.
- Snapshots rebuild on storefront/list refresh and checkout; removed or invalid
  catalogs lose listing authority without changing the stock baseline.
- Checkout verifies current listing/price, native availability, duplicate
  ownership, funds, and native grant before charging.
- Ammo refill rechecks listing, native availability and physical ownership.
- Character inventory continues using its existing staged Story-save flow.
- V1 uses the no-artwork fallback; it does not mislabel stock preview art.
- Both storefronts sort by weapon category, then display name and stable ID.
  Add-on SMGs are interleaved with stock SMGs; smoke products stay in Throwables.
- V1 does not declare model/material tint support. Add-on firearms therefore do
  not offer weapon tints merely because the donor reports a native palette.
  Purchase validation and inventory restoration use the same restriction.
- Known optional scope, suppressor, grip and flashlight slots have an explicit
  `component_remove` action. Removal is free, retains ownership and persists
  across restoration; it never acts as a purchase or resets suppressor wear.
  Magazines, barrels, receivers and unrecognized slots do not offer a bare None.
- Native DLC component discovery is unchanged. A weapon listing does not
  manufacture missing component shop metadata or custom animation assets.
- Native DLC `bActiveByDefault` metadata makes default parts owned/free and
  excludes them from Unequip. No English-label match or Vector-specific hash is
  used for this authority. After accessory removal, an unambiguous default is
  restored only to an empty slot. Inventory restoration similarly repairs empty
  default sight slots. Ambiguous defaults and unknown metadata are not guessed.

The local KRISS Vector package builder lives in the SDK at
`tools/build_kriss_vector_allin1_package.py`. It preserves the tested Enhanced
DLC byte-for-byte and emits animation audit evidence, a private install ZIP,
and a separate hash-paired runtime update. No live installation or publishing
occurs during that build.
