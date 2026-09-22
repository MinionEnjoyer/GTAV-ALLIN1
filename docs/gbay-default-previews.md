# GBAY default previews

In **Setup → GBAY default previews**, choose all images or weapons, vehicles, or
gear. Review shows the count and download size before installation. GTA must be
closed.

`data/default_previews.json` pins every public GTAV-ALLIN1 GitHub release ZIP by
URL, size, and SHA-256. Every archive entry/PNG is validated before game
publication. ZIPs contain only images and an index; verified ZIPs are cached for
offline reuse by the other edition.

Downloads use `plugins/ReactorV/ui/assets/allin1/default-{category}`. Generated
images use `generated-{category}`, always win, and are never edited or removed by
a download. Displaying defaults requires the current preview-aware Reactor bridge.

Normal UI launches default to **Missing previews only**, reusing intact defaults
or generated art and rendering only gaps. Uncheck it after visual/source changes.
Quick Launch skips preview work but retains normal source/safety validation.

The shared review/apply API uses `action: "download_previews"` and optional
`categories: ["weapons", "vehicles", "gear"]` (omit for all). Read the resulting
`preview_download` plan, then confirm its returned review ID/hash through normal
apply. UI, CLI service client, and agents use this guarded path; it never starts
the game.

To publish, run `tools/package_default_previews.py` against game preview folders,
then attach its three ZIPs plus `manifest.json` and `inventory.json` as a
non-latest GTAV-ALLIN1 preview-only GitHub release. Include only
catalog-whitelisted vanilla identities with valid source-index hashes. Copy the
generated manifest to this launcher's data directory. The complete pack is 111
weapons,
935 vehicles (including Tampa), and 10 gear previews; custom weapons render
locally.
