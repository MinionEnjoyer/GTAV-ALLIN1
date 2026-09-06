# allin1 command reference — 0.6.4

Generated from the Click command tree by `documentation_audit.py`; do not edit individual rows.

Use `allin1 COMMAND --help` for argument types, choices, defaults and complete safety requirements.
Listing a command here does not authorize execution, imply React UI parity, or qualify a game write.

| Command | Purpose | Parameters |
| --- | --- | --- |
| `allin1` | ALLIN1 - GTA V Story Mode mod manager and add-on content tool. | --config / -c, --verbose / -v, --version |
| `allin1 analyze-client-log` | Convert an in-game structured client log into a smoke-test report. | log_file, --edition, --output |
| `allin1 apply-update` | Apply a local checksum-verified release archive transactionally. | archive, destination, --backup-dir |
| `allin1 assistant` | Manage the optional local or compatible-API assistant component. |  |
| `allin1 assistant configure` | Configure an installed pack, existing local model, or compatible API. | --mode, --workflow, --profile, --endpoint, --model-name, --api-key-env, --runtime-path, --model-path, --context-tokens, --temperature, --provider-control, --thinking, --model-sha256, --llama-cpp-revision, --root, --yes |
| `allin1 assistant hardware-check` | Check whether this PC can safely run a managed local model pack. | --profile, --root |
| `allin1 assistant install-package` | Install a checksum-complete ALLIN1 assistant model pack. | archive, --root, --yes |
| `allin1 assistant install-qwen` | Download and install Qwen plus llama.cpp from their upstream projects. | --profile, --root, --yes |
| `allin1 assistant prompt` | Forward a read-only question to the installed SDK assistant console. | prompt, --root, --repository-root, --workspace-root, --manifest, --gta-path, --operation-mode, --source, --symbol, --telemetry, --telemetry-pattern, --timeout, --startup-timeout, --max-tokens |
| `allin1 assistant settings-propose` | Ask Qwen for a typed advisory diff; this command never applies it. | extension_id, intent, --gta-path, --root, --output, --timeout, --startup-timeout, --max-tokens |
| `allin1 assistant status` | Show assistant installation and configuration without starting a model. | --root |
| `allin1 assistant uninstall` | Remove the managed assistant pack without touching custom model files. | --root, --yes |
| `allin1 assistant verify` | Fully verify every managed runtime and model file against its recorded hash. | --root |
| `allin1 audit-previews` | Inspect captured previews for blank, transparent, or poor framing. | directory |
| `allin1 build-release` | Build and verify the minimal public Windows release archive. | --output / -o |
| `allin1 content` | Validate and manage versioned ALLIN1 content extensions. |  |
| `allin1 content disable` | Disable an installed content package. | extension_id, --yes, --gta-path |
| `allin1 content enable` | Enable an installed content package. | extension_id, --yes, --gta-path |
| `allin1 content install-package` | Install a validated mod.toml, package folder, or bounded ZIP package. | source, --gta-path, --yes, --repair-managed |
| `allin1 content list` | List bundled descriptors and, when available, installed package state. | --gta-path, --json-output |
| `allin1 content set` | Set a typed package setting (VALUE accepts JSON or plain text). | extension_id, key, value, --gta-path, --yes |
| `allin1 content settings-apply` | Explicitly apply an exact previewed proposal through the launcher writer. | proposal, --gta-path, --confirm-proposal-id, --yes |
| `allin1 content settings-catalog` | Print the compact typed catalog and live package-state hashes. | extension_id, --gta-path |
| `allin1 content settings-preview` | Preview a typed proposal without writing package settings. | proposal, --gta-path |
| `allin1 content validate` | Validate a content descriptor, mod.toml, package folder, or ZIP. | manifest |
| `allin1 diagnostics` | Create a redacted troubleshooting bundle for bug reports. | --output / -o, --scripts-dir |
| `allin1 export-catalog` | Export vehicle database as JSON for the web catalog. | --output / -o |
| `allin1 generate-vehiclelist` | Regenerate VehicleList.cs with display names and prices. | --output / -o |
| `allin1 generate-weaponlist` | Regenerate WeaponList.cs from weapons.toml + prices_weapons.toml. | --output / -o |
| `allin1 health-check` | Run the pre-launch dependency, duplicate, and integrity scanner. | gta_path, --json-output |
| `allin1 import-previews` | Validate and import curated catalog preview PNGs. | source, --kind |
| `allin1 install` | Install MP vehicles into your GTA V single player. | --reactor, --rpf-loader |
| `allin1 launcher` | Inspect, review and apply Launcher workflows. | --project-root, --state-root, --allow-writes, --allow-game-writes, --allow-launch |
| `allin1 launcher agent-api` | Serve schema-v1 JSON lines over stdio; keep this process alive for reviews. |  |
| `allin1 launcher apply` | Apply a current plan with explicit process authority and approval. | --plan, --approval-sha256, --confirm |
| `allin1 launcher catalog` | List versioned operations, action parameters, risks and SDK handoff flow. |  |
| `allin1 launcher inspect` | Read a workspace or an SDK-exported ZIP/manifest; never install it. | --module, --source, --config-json |
| `allin1 launcher request` | Execute a cataloged read operation. | operation, --payload |
| `allin1 launcher review` | Validate a proposed action and print a plan without executing it. | --request, --output |
| `allin1 list` | List all available MP vehicles. | --class / -c |
| `allin1 map-canary` | Run fixed-scope developer map-registration canaries. |  |
| `allin1 map-canary grapeseed-stock-black-promote` | Promote an observed Grapeseed Phase A to its black transition. | --gta-path, --session, --yes, --confirm-canary |
| `allin1 map-canary grapeseed-stock-black-rollback` | Restore Grapeseed's exact Phase-A marker and receipt. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary grapeseed-stock-black-status` | Read exact Grapeseed Phase-B evidence. | --gta-path |
| `allin1 map-canary grapeseed-stock-boot-install` | Install the execution-disabled Enhanced Grapeseed bridge. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary grapeseed-stock-boot-rollback` | Restore the prior pack and remove only Grapeseed's DLC registration. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary grapeseed-stock-boot-status` | Read exact Grapeseed Phase-A evidence. | --gta-path |
| `allin1 map-canary install` | Install the Enhanced Davis registration-only canary; never start GTA. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary rollback` | Restore the exact pre-canary pack and dlclist while GTA is closed. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary startup-install` | Install the Enhanced Davis-only startup/IPL v3 canary. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary startup-rollback` | Restore the exact pre-startup-canary pack and dlclist. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary startup-status` | Read the Davis-only startup/IPL v3 evidence. | --gta-path |
| `allin1 map-canary status` | Read the Davis canary checkpoint and installed evidence. | --gta-path |
| `allin1 map-canary stock-black-promote` | Promote one observed Phase-A bridge to the Davis black transition. | --gta-path, --session, --yes, --confirm-canary |
| `allin1 map-canary stock-black-rollback` | Restore the exact Phase-A marker and receipt while GTA is closed. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary stock-black-status` | Read exact Enhanced stock-reference Phase-B evidence. | --gta-path |
| `allin1 map-canary stock-boot-install` | Install the execution-disabled Enhanced stock-reference boot canary. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary stock-boot-rollback` | Restore the exact pre-Phase-A pack and dlclist.xml. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary stock-boot-status` | Read exact Enhanced stock-reference Phase-A evidence. | --gta-path |
| `allin1 map-canary streaming-install` | Install the Enhanced Davis isolated-streaming v2 canary. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary streaming-rollback` | Restore the exact pre-streaming-canary pack and dlclist. | --gta-path, --yes, --confirm-canary |
| `allin1 map-canary streaming-status` | Read the Davis isolated-streaming v2 evidence. | --gta-path |
| `allin1 open-launcher` | Open/focus a non-mutating Launcher workspace handoff. | --workspace, --package-id, --traffic / --no-traffic, --launcher-path |
| `allin1 qualification-report` | Create a release qualification dashboard JSON file. | output, --coverage-report, --minimum-coverage, --script-assembly, --smoke-report, --acceptance-context |
| `allin1 repair-garage` | Repair slots and quarantine invalid entries in an ALLIN1 garage save. | garage_file |
| `allin1 rollback-update` | Restore the files saved by the last transactional update. | destination, backup |
| `allin1 sdk` | Inspect and link declarative GTA V add-on integrations. |  |
| `allin1 sdk audit-folder` | Audit every supported package archive in a test/mod staging folder. | folder, --output / -o, --draft-dir |
| `allin1 sdk compile-vehicle-data` | Join vehicle, handling, variation, tuning, asset, and registration data. | source, --output-dir / -o |
| `allin1 sdk dlc-inventory` | Inventory DLC folders, registrations, ownership, and stale entries. | gta_path, --output / -o |
| `allin1 sdk extract-rpf-entry` | Extract one exact root or nested-RPF entry without modifying the archive. | archive, entry_path, --archive-path, --gta-path, --output / -o |
| `allin1 sdk import-package` | Scan a loose DLC folder or OIV/ZIP/RAR/7z and generate a reviewable draft. | source, --output / -o |
| `allin1 sdk index-rpf` | Export a structured, searchable RPF index as JSON and CSV. | archive, --gta-path, --output / -o |
| `allin1 sdk inspect-package-rpfs` | Extract only packaged RPFs to temporary storage and inspect them read-only. | source, --output-dir / -o, --gta-path |
| `allin1 sdk inspect-rpf` | Inspect a loose RPF with the edition-aware read-only helper. | archive, --gta-path, --output / -o |
| `allin1 sdk link` | Write a human-readable linked integration and install-plan report. | manifest, --output / -o |
| `allin1 sdk list` | List the add-on examples included with the ALLIN1 SDK. |  |
| `allin1 sdk oiv-plan` | Preview an OIV recipe without executing it or touching the game. | source, --output / -o, --managed-package |
| `allin1 sdk plan-rpf-replacement` | Create a checksummed replacement plan; perform no RPF writes. | archive, entry_path, payload, --archive-path, --gta-path, --output / -o |
| `allin1 sdk validate` | Validate fields and cross-file references in addon.json. | manifest |
| `allin1 status` | Show current installation status. |  |
| `allin1 uninstall` | Remove ALLIN1 files from GTA V directory. |  |
| `allin1 verify-preview-artifacts` | Verify that a built YTD directory covers the complete vehicle catalog. | directory |
| `allin1 verify-release` | Verify a public release ZIP without extracting or installing it. | archive |
