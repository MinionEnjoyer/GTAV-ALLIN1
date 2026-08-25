# ALLIN1 content extension API

The ALLIN1 content extension API lets a managed mod package describe content
that the launcher and Story Mode runtime can discover in a consistent way. It
is a declarative API: a package supplies a versioned `mod.toml` and a versioned
`allin1.content.json` descriptor.

The current API can declare:

- launcher-managed systems and typed settings;
- GBAY sections and catalog files;
- package-to-package requirements;
- game-runtime DLLs installed below `scripts/`; and
- descriptive capability identifiers for discovery and auditing.

It does **not** let a package inject arbitrary launcher pages, widgets, buttons,
Python modules, or shell commands. The launcher renders supported declarations
with its own controls and owns the install, enable, disable, update, uninstall,
and settings actions.

## Package layout

A minimal content extension looks like this:

```text
example.content-settings/
|-- mod.toml
`-- allin1.content.json
```

The complete safe example is in
[`mods/examples/content-extension/`](../mods/examples/content-extension/).

Packages that contribute catalogs or runtime assemblies include those payloads
too. Every declared catalog and runtime assembly must also be owned by an exact
`[[files]].destination` in `mod.toml`.

## `mod.toml` schema version 2

Content extensions use package schema version 2 and must contain an `[allin1]`
table:

```toml
schema_version = 2
id = "example.content-settings"
name = "Example Declarative Content Settings"
version = "1.0.0"
type = "config"
description = "A safe settings-only content extension example."
editions = ["legacy", "enhanced"]
dependencies = []
conflicts = []

[allin1]
api_version = 1
content = "allin1.content.json"
requires = []

[[files]]
source = "allin1.content.json"
destination = "scripts/ExampleContent/allin1.content.json"
```

The `[allin1]` fields are:

| Field | Required | Meaning |
| --- | --- | --- |
| `api_version` | Yes | Must be `1` for the current launcher. |
| `content` | Yes | Safe package-relative path to the content descriptor. |
| `requires` | No | Other enabled ALLIN1-managed packages required by this package. |

The package `id` and `version` must exactly match the corresponding values in
`allin1.content.json`. Paths must be relative, must not contain drive letters or
`..`, and must stay inside the package or game directory selected by the
installer.

Package schema version 1 remains supported for classic managed packages that do
not expose content-extension metadata. A version 1 package cannot contain an
`[allin1]` table, and a version 2 package must contain one.

## Content descriptor

The descriptor is UTF-8 JSON. Its top-level structure is:

```json
{
  "schema_version": 1,
  "api_version": 1,
  "id": "example.content-settings",
  "name": "Example Declarative Content Settings",
  "version": "1.0.0",
  "description": "A safe settings-only content extension example.",
  "capabilities": ["launcher.settings"],
  "systems": [],
  "gbay": {
    "sections": [],
    "catalogs": []
  },
  "runtime": {
    "assemblies": []
  }
}
```

`schema_version` and `api_version` must both be `1`. IDs are stable lowercase
identifiers made from letters, numbers, dots, dashes, and underscores. An ID is
between 2 and 96 characters in the content descriptor; because it must match the
package ID, keep package extension IDs at 64 characters or fewer. The
`allin1.*` namespace is reserved for launcher-bundled content packs.

A descriptor must contribute at least one system, GBAY section, GBAY catalog,
or runtime assembly. IDs must be unique within their respective collections,
and setting keys must be unique across the whole content package.

## Systems and typed settings

A system groups related settings for display in the launcher's content
workspace and for consumption by a compatible runtime:

```json
{
  "id": "display-options",
  "name": "Display options",
  "description": "Example settings rendered by the launcher.",
  "category": "Example",
  "experimental": false,
  "enabled_by_default": true,
  "settings": [
    {
      "key": "show_hints",
      "label": "Show hints",
      "type": "boolean",
      "default": true,
      "description": "Show short help text from this example.",
      "group": "General"
    }
  ]
}
```

System fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | Yes | Stable system identifier. |
| `name` | Yes | Human-readable name. |
| `description` | No | Short explanation shown to users. |
| `category` | No | Launcher grouping; defaults to `Other`. |
| `experimental` | No | Marks the system experimental; defaults to `false`. |
| `enabled_by_default` | No | Default-state metadata for consumers; defaults to `true`. It does not create a separate launcher toggle by itself. |
| `settings` | No | Array of typed settings. |

Supported setting types:

| Type | Value | Useful optional fields |
| --- | --- | --- |
| `boolean` | JSON `true` or `false` | None |
| `integer` | JSON integer, excluding booleans | `minimum`, `maximum`, `step` |
| `number` | Finite JSON number, excluding booleans | `minimum`, `maximum`, `step` |
| `string` | JSON string | None |
| `choice` | One string from `choices` | Required `choices` array |

Every setting requires `key`, `label`, `type`, and a type-correct `default`.
`description` and `group` are optional. Numeric bounds must be finite,
`minimum` must not exceed `maximum`, and `step` must be positive. Setting keys
start with a lowercase letter and may then contain lowercase letters, numbers,
dashes, and underscores.

The launcher stores extension-owned settings by package namespace. A runtime
consumer should read the effective settings from the generated registry rather
than inventing a second settings file.

### Core compatibility bindings

`config_key` is a compatibility bridge reserved for descriptors bundled with
the launcher. It is limited to these namespaces:

```text
general.<field>
traffic.<field>
vehicles.<field>
script.<field>
```

The referenced field must actually exist and the declared setting type must be
compatible with its value. Installed third-party packages are rejected if they
declare `config_key`; their settings always remain safely namespaced to the
extension. A declaration cannot create or take ownership of a core
configuration field.

## Capability identifiers

`capabilities` is an optional list of lowercase, identifier-like strings such
as `launcher.settings`, `gbay.catalogs`, `traffic.catalog`,
`story-save.transactions`, or `weapon.components.lifecycle`. Capability
identifiers describe what a package expects to contribute so tools and users
can inspect it.

Capabilities are declarative permission requests and discovery hints, not
executable hooks or proof that a consumer implements the feature. Typed
settings require `launcher.settings`, GBAY sections require `gbay.sections`,
and catalogs require `gbay.catalogs`. The runtime also checks a relevant
capability before accepting supported callback registrations. Declaring one
does not by itself grant file, network, process, arbitrary launcher UI, or
game-runtime access.

## GBAY sections and catalogs

GBAY metadata is declared under the `gbay` object:

```json
{
  "gbay": {
    "sections": [
      {
        "id": "example-services",
        "label": "Example Services",
        "description": "Services supplied by the example package.",
        "route": "example:services",
        "order": 250
      }
    ],
    "catalogs": [
      {
        "id": "example-service-catalog",
        "kind": "service",
        "source": "scripts/ExampleContent/services.json"
      }
    ]
  }
}
```

A section declares a stable `id`, display `label`, optional `description`, a
supported route identifier, and an integer `order` that defaults to `100`.
Routes start with a lowercase letter and may contain lowercase letters,
numbers, dots, underscores, dashes, and colons.

A catalog declares:

- a stable `id`;
- a `kind`: `vehicle`, `weapon`, `gear`, `service`, or `property`; and
- `source`, a safe game-relative JSON destination owned by the package.

For example, a catalog source of
`scripts/ExampleContent/services.json` requires a matching file entry:

```toml
[[files]]
source = "services.json"
destination = "scripts/ExampleContent/services.json"
```

The extension descriptor registers the section, route, and catalog location. It
does not inject an arbitrary screen or decide how an unsupported route is
rendered. Catalog item fields are defined by the GBAY consumer for that catalog
kind; the extension parser validates the catalog kind, path, and package
ownership, but does not reinterpret an unknown item format.

### Vehicle catalog v1

A `kind = "vehicle"` catalog uses the renderer-neutral contract in
`content/allin1-vehicle-catalog.schema.json`. The same catalog can feed the
native GBAY menu, developer tools, or a future web-based storefront without
giving the renderer control over purchases or saves.

```json
{
  "schema_version": 1,
  "id": "example-vehicles",
  "name": "Example Vehicles",
  "vehicles": [
    {
      "model": "examplecar",
      "name": "Example Car",
      "manufacturer": "Example Motors",
      "category": "sports",
      "price": 125000,
      "storage": "garage",
      "source_pack": "examplecars",
      "size_tier": 1,
      "preview_dictionary": "example_previews",
      "preview_texture": "examplecar",
      "traffic": {
        "enabled": false,
        "weight": 1.0
      }
    }
  ]
}
```

Vehicle packages must follow these rules:

- the catalog source must exactly match a package-owned file destination;
- `id` must match the catalog declaration and model names must be unique;
- each `source_pack` must name a DLC pack installed by that package;
- third-party packages cannot claim `source_pack = "base"` or replace an
  official GTA model;
- boats use `harbour`, helicopters use `helipad`, and planes use `hangar`;
- all other categories use `garage`;
- a listing does not enter traffic merely because it appears in GBAY; and
- unavailable models are rejected again in game before money is charged.

Each catalog may contain at most 2,048 entries. The game runtime merges up to
8,192 receipt-authorized dynamic entries in deterministic package/catalog/model
order, with official Story listings taking precedence over third-party names.

The package must require `allin1.online-content>=0.5.5`, declare `gbay.catalogs`, and
use a schema-2 `mixed` package when it combines an RPF DLC pack with the loose
catalog JSON. To offer ambient traffic, it must additionally declare
`traffic.catalog` and `launcher.settings`, then provide a boolean
`traffic_enabled` setting whose default is `false`. A model enters the package
traffic pool only when all three gates agree: the package setting is enabled,
the catalog item's `traffic.enabled` is true, and the runtime confirms that the
installed model is a road vehicle in the declared class. Boats, aircraft,
emergency vehicles, and other specialized categories cannot opt into this
traffic path.

Traffic `weight` is relative and bounded from `0.1` through `20.0`. The runtime
retains its mission, interior, wanted-level, visibility, road, cleanup, and
performance safeguards. Area-specific traffic targeting is intentionally not
part of catalog v1; an authoring field is not exposed until the runtime can
enforce it consistently.

### Optional web renderer boundary

An HTML/React GBAY client can be added as an optional renderer over the same
typed catalogs. It must receive bounded state snapshots and return typed user
intents such as navigate, search, favorite, preview, purchase request, and back.
It must never receive direct native, filesystem, money, delivery, package, or
save authority. The C# runtime remains responsible for model validation,
pricing, staged Story-save transactions, storage compatibility, and every world
mutation.

The native GBAY renderer remains the required safe fallback. A future browser
host should load only packaged local assets, block remote navigation and script
injection, use one controller/input abstraction, and fall back automatically if
the host is missing, fails its health check, or stops acknowledging messages.
React is therefore a build-time UI choice, not a new extension permission or a
requirement for catalog authors.

### GBAY transaction rule

All GBAY purchases, refunds, deliveries, ownership changes, ammunition, gear,
and other economy changes must follow the Story-save rule:

1. Stage the change for the current Story Mode session.
2. Apply it to the live character or world as needed.
3. Commit it permanently only when the player completes a real Story Mode save.
4. If the session reloads or exits without a newer save, discard the staged
   change and restore the last committed state.

The descriptor cannot enforce transaction behavior on arbitrary runtime code.
Runtime authors are responsible for using the ALLIN1 transaction/save flow and
must not write a GBAY purchase directly to permanent storage. Launcher settings,
package receipts, and package enable/disable state are launcher configuration,
not Story Mode purchases, so they are persisted when the user applies the
corresponding launcher action.

## Runtime assemblies

Managed Story Mode code can be declared under `runtime.assemblies`:

```json
{
  "runtime": {
    "assemblies": [
      {
        "path": "scripts/ExampleContent/ExampleContent.dll",
        "entry_point": "ExampleContent.EntryPoint"
      }
    ]
  }
}
```

Each `path` must be a game-relative `.dll` path below `scripts/`, and it must
exactly match a `[[files]].destination` owned by the same package. `entry_point`
is optional non-empty metadata for a compatible runtime host.

The launcher never imports a runtime DLL into Python. Installing the file and
declaring it in metadata does not add launcher code or custom launcher UI. The
game's compatible managed-script/runtime environment is responsible for loading
supported code. Extension metadata alone does not guarantee that an assembly
will execute or that its entry point contract is supported.

Runtime DLLs are executable in-process code and must be treated as trusted code.
Only install packages from a source you trust.

### Game-runtime API

Managed extensions compile against the public types in `ALLIN1.dll`. The v1
surface is exposed by `ALLIN1.Allin1ExtensionApi`:

- `ApiVersion` reports the supported runtime contract.
- `RegistryAvailable` reports whether the game-local registry was loaded.
- `IsPackageEnabled`, `GetEnabledPackageIds`, and `HasCapability` expose the
  launcher's current authorization snapshot.
- `TryGetSetting` and the typed `GetBooleanSetting`, `GetStringSetting`,
  `GetIntegerSetting`, and `GetNumberSetting` helpers read effective,
  package-namespaced settings.
- `GetGbayCatalogs(packageId)` returns read-only, contained catalog declarations
  for an enabled package with `gbay.catalogs`.
- `RegisterGbayAction(packageId, route, callback)` connects one declared,
  non-built-in GBAY route to one callback.
- `RegisterStorySaveParticipant(packageId, participantId, participant)` joins
  the Story-save transaction lifecycle.
- `RecordWeaponAmmo(packageId, weaponName, ammo, authorizationProof)` mirrors a
  native absolute-ammo mutation into ALLIN1's optional character inventory
  ledger. The proof delegate is not invoked; its declaring assembly supplies
  receipt authorization.
- `RegisterWeaponComponentLifecycleParticipant(packageId, participantId,
  participant)` joins the generic GBAY component-pricing and completed-purchase
  lifecycle.
- `IsGbayMenuActive` reports whether GBAY is open so an external gameplay mod
  can ignore transient workbench previews.
- `ReloadRegistry` asks the runtime to re-read the launcher's declarative
  registry after a supported host lifecycle event.

The machine-readable v1 surface is checked in at
`data/runtime_api_contract.json`. The SDK verifies that contract against the
public C# declarations, then connects package API calls, capabilities,
interfaces, settings, runtime assemblies, entry points, and Workbench
relationships without loading either DLL.

The game runtime accepts a registration only when the package is enabled, the
required capability and route were declared, and the registering assembly's
path and SHA-256 match its launcher receipt. A package cannot replace a
`builtin:` route. Keep the returned registration handles alive and dispose them
when the script stops.

`RecordWeaponAmmo` requires `story-save.transactions` plus the same enabled,
receipt-matched assembly authorization. It does not grant inventory or perform
the GTA native mutation; it is a narrow synchronization bridge that lets a
standalone mod coexist with ALLIN1 without becoming part of `ALLIN1.dll`.

```csharp
using System;
using ALLIN1;
using GTA;

public sealed class ExampleContentScript : Script, IStorySaveParticipant
{
    private readonly IDisposable _gbayRegistration;
    private readonly IDisposable _saveRegistration;
    private bool _purchaseStaged;

    public ExampleContentScript()
    {
        _gbayRegistration = Allin1ExtensionApi.RegisterGbayAction(
            "example.content", "example:services", OpenServices);
        _saveRegistration = Allin1ExtensionApi.RegisterStorySaveParticipant(
            "example.content", "service-purchases", this);
        Aborted += (_, __) => {
            _gbayRegistration.Dispose();
            _saveRegistration.Dispose();
        };
    }

    private void OpenServices()
    {
        foreach (GbayCatalogDeclaration catalog in
                 Allin1ExtensionApi.GetGbayCatalogs("example.content"))
        {
            // Read the declared JSON format understood by this route.
            // Stage purchases in memory; do not persist them here.
        }
    }

    public void Commit(StorySaveContext context)
    {
        if (!_purchaseStaged) return;
        // Persist the staged transaction now that a native save advanced.
        _purchaseStaged = false;
    }

    public void Discard(StorySessionEndContext context)
    {
        // Remove anything that was staged after the last committed save.
        _purchaseStaged = false;
    }
}
```

Catalog declarations intentionally do not define one universal item schema.
The registered route owns the meaning and presentation of its catalog JSON;
the launcher owns validation, installation, containment, discovery, settings,
and lifecycle. This keeps the launcher extensible without accepting arbitrary
third-party Python, shell commands, or widget injection.

### Weapon-component lifecycle bridge

The `weapon.components.lifecycle` capability is a narrow, generic bridge for a
standalone weapon mod that tracks component ownership or consumption. A
receipt-authorized implementation of
`IWeaponComponentLifecycleParticipant` supplies two methods:

```csharp
bool IsComponentConsumed(string weaponName, int componentHash);
void OnComponentPurchased(
    string weaponName, int componentHash, int attachmentPoint);
```

Before showing an owned-price bypass, GBAY asks registered participants whether
the exact weapon/component pair has been consumed. After a purchase has been
charged, applied to the live weapon, and recorded successfully, GBAY sends the
completed-purchase notification. Browsing or previewing a component does not
send that notification. Implementations should keep the consumed-state query
side-effect free, validate the exact weapon/component pairs they own, and use
`IsGbayMenuActive` to avoid interpreting temporary workbench previews as native
reattachments.

Registration requires the package to declare
`weapon.components.lifecycle`. The runtime also verifies that the registering
assembly path and SHA-256 match the launcher's package receipt, and drops the
participant when that authorization is revoked. This bridge does not make the
weapon mod part of ALLIN1 and does not give it a custom launcher page or a way
to synthesize GBAY transactions.

## Package requirements

`[allin1].requires` describes dependencies on other enabled ALLIN1-managed
packages. Supported forms are:

```toml
requires = [
  "shared.library",
  "content.base>=1.2",
  "exact.api==2.0.1"
]
```

Only `>=` and `==` comparisons are supported. Compared versions contain one to
four numeric components. Requirement IDs must be unique, and a package cannot
require itself.

Required packages must be installed, enabled, and version-compatible before the
dependent package can be installed or enabled. The launcher prevents disabling
or uninstalling a package while an enabled dependent still requires it.

This is separate from the top-level `dependencies` list, which declares core
loaders such as `scripthookv`, `shvdn`, and `openrpf`.

## Install and runtime lifecycle

The managed lifecycle is:

1. **Inspect and validate.** The launcher validates both manifests, IDs,
   versions, paths, payload presence, editions, loaders, requirements,
   conflicts, and declared hashes.
2. **Install.** Payloads are copied using the package's managed file list.
   Replaced files are backed up and the launcher writes a receipt containing
   the installed-file hashes and normalized extension descriptor.
3. **Register.** The launcher rebuilds the game-local extension registry from
   trusted built-ins and valid package receipts.
4. **Configure.** The launcher validates and saves typed settings in the
   extension's own namespace, then rebuilds the registry.
5. **Enable or disable.** Managed payloads and registry state are changed
   together. Package requirements and enabled dependents are checked.
6. **Update or uninstall.** Ownership and hashes are verified before files are
   replaced or removed. Backups are restored where applicable and the registry
   is rebuilt.

Restart Story Mode after installing, updating, enabling, or disabling runtime
content. Do not modify managed files behind the launcher's back; safety checks
may refuse an operation when a file no longer matches its receipt.

For each configured game installation, generated state is kept below:

```text
<GTA V>/scripts/.allin1/extensions/registry.json
<GTA V>/scripts/.allin1/extensions/settings.json
<GTA V>/scripts/.allin1/mods/<package-id>.json
```

These locations are launcher-owned. A package cannot declare a destination
below `scripts/.allin1/` and should never edit registry, settings, or receipt
files directly.

Mutable gameplay state should likewise not be written into a receipt-owned DLL
or descriptor path. A package may keep documented user state outside the game
installation, for example below `%LOCALAPPDATA%\<PackageName>`. Because that
state is not in the managed file list, disable and uninstall operations do not
delete it. Packages that intentionally retain such state must say so clearly
and document its location.

## Security model

The content API reduces accidental and hidden behavior by keeping launcher
integration declarative:

- paths are contained and traversal is rejected;
- core launcher and loader destinations are reserved;
- catalogs and runtime assemblies must be owned by the package;
- installed file hashes are recorded in package receipts;
- declared catalog files are hash-checked while rebuilding the registry and
  again whenever the game-runtime API exposes them;
- enabled runtime assemblies must match their receipt hashes to be authorized
  in the generated registry;
- Story-save and weapon-component callbacks are accepted only from an enabled,
  capability-declaring, receipt-matched assembly and are dropped after
  authorization is revoked;
- corrupt receipts are ignored rather than authorizing executable content;
- settings are type-checked and namespaced; and
- the launcher does not execute extension-supplied Python or shell commands.

A matching hash proves that an installed file is the file recorded at install
time. It does not prove that third-party code is harmless. Review source and
publisher trust before installing executable packages. The local registry and
receipts are not signed and the managed game runtime is full-trust; this is an
ownership and lifecycle boundary, not a sandbox against another already-running
mod or a user with local file access.

## Compatibility and versioning

- `mod.toml` schema 1 is retained for non-extension packages.
- Content extensions require `mod.toml` schema 2, `[allin1].api_version = 1`,
  and content descriptor schema/API 1.
- Older launchers that do not support schema 2 will reject these packages
  instead of silently ignoring extension metadata.
- Use `editions = ["legacy"]`, `editions = ["enhanced"]`, or both to state game
  compatibility. Each installed game edition has its own registry and settings.
- Keep package, system, setting, section, and catalog IDs stable across releases.
  IDs connect saved settings, dependencies, receipts, and runtime consumers.
- Increment the package and content descriptor versions together.
- Add a new API or schema version only when the consumer supports it. Do not
  relabel incompatible data as API 1.

## Release checklist

Before distributing a content extension:

- validate that `mod.toml` and `allin1.content.json` IDs and versions match;
- test every declared edition;
- include every catalog and runtime path as an exact package destination;
- add SHA-256 values to release `[[files]]` entries;
- verify defaults, ranges, choices, and package requirements;
- test install, update, disable, re-enable, and uninstall;
- test Story-save commit and no-save rollback for every GBAY action;
- confirm runtime changes require and survive a clean Story Mode restart; and
- document any trusted executable code included with the package.
