# GBAY default previews

In the Launcher, open **Setup → GBAY default previews**. Download all images or
select weapons, vehicles, or gear. Review shows counts and download size before
anything is installed. GTA must be closed.

The manifest in `data/default_previews.json` pins each SDK GitHub release ZIP by
URL, byte size and SHA-256. Every PNG and archive entry is validated before any
game publication. ZIPs contain images and an index only, no models or scripts.
Verified ZIPs are cached so the other game edition can reuse them offline.

Downloaded images use `plugins/ReactorV/ui/assets/allin1/default-{category}`.
Locally generated images use `generated-{category}` and always take precedence.
Downloading never edits or removes generated/custom previews. The current
preview-aware Reactor bridge is required to display the default directories.

Normal UI launches default to **Missing previews only**, which reuses intact
defaults or generated artwork and renders only uncovered entries. Uncheck it to
regenerate after visual/source changes. Quick Launch skips preview work entirely;
it still performs the normal source/safety validation before starting GTA.

The shared review/apply API exposes `action: "download_previews"` with optional
`categories: ["weapons", "vehicles", "gear"]`. Omit categories for all three.
Read the resulting `preview_download` plan, then confirm using the returned
review ID/hash through the ordinary apply operation. This is the same guarded
path used by the UI, CLI service client, and agents; it does not start the game.

Publication: run `tools/package_default_previews.py` against the game preview
folders, then publish its three ZIPs as non-latest SDK GitHub release assets.
Only catalog-whitelisted vanilla identities with valid source-index hashes enter
the pack. Publish its manifest and inventory under the SDK's `previews/gbay/`
folder and copy the same generated manifest into this launcher's data directory.
The complete pack has 111 weapons, 935 vehicles (including Tampa), and 10 gear
previews. All vanilla catalog entries are covered; custom weapons render locally.
