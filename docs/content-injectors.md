# Traffic population editor

The Launcher’s **Content → Traffic** page configures the supported ambient
traffic policy. It is a Story Mode runtime policy, not a binary replacement
installer. Install compatible vehicle content through Packages first; package
controls remain under **Existing content**.

## Configure and review

1. Select the correct GTA edition and path in Setup, then open **Content → Traffic**.
2. Load the authorized catalog. Only enabled managed packages with validated
   catalog ownership can contribute models.
3. Enable the policy, select entries, and set relative weights from `0.1` to
   `20.0`.
4. Review the changes and confirm with GTA closed. Restart the game/scripts to
   use the policy. A changed file or catalog invalidates a pending review.

The traffic policy’s master switch pauses the traffic spawner; it cannot
override Gameplay’s disabled traffic setting. Its list filters custom package
road vehicles while retaining the curated stock/DLC civilian pool. Package
vehicles must have the `traffic.catalog` capability, enabled package
`traffic_enabled` setting, and catalog-item traffic opt-in. The editor cannot
grant those permissions or force an aircraft into road traffic.

Chance is the probability of an eligible replacement opportunity, not a promise
that a percentage of every vehicle in the world will change. Weight is relative
to other compatible entries. Turning traffic off does not uninstall models,
remove GBAY listings, alter player purchases, saved loadouts, original GTA
assets, or installation receipts.

## Safety and troubleshooting

The existing traffic status in **GBAY → Diagnostics** reports managed counts,
performance throttling, and pause reasons. Detailed activity and rejection
information is written to the client log as `Traffic` events.

An empty list means no compatible authorized catalog is available. A disabled
package, missing DLC ownership, unsupported category, or altered catalog can
also exclude an entry. Read catalog warnings before reviewing a policy. The
native runtime’s model and class checks remain authoritative.

The policy is stored at the selected game path as
`scripts/.allin1/traffic-population.json`; include it with configuration
backups.

## CLI and agent API

Use the same review/apply boundary as the desktop editor:

| Inspect module | Response field | Review action |
| --- | --- | --- |
| `vehicle_manager` | `traffic_population` | `traffic_population_save` |

Send `inspect` with the module and selected `config`, edit the returned
`document`, then send `review` with the edited document and its
`expected_document_sha256`. Display the review before sending `apply` with
`review_id`, `review_sha256`, and `confirmed: true`. Write authority and a
closed game are required; interrupted operations are never replayed
automatically.

## Vehicle package authoring

Vehicle packages use the [content-extension contracts](content-extension-api.md)
and may opt into ambient traffic only with `traffic.catalog`,
`launcher.settings`, a default-off `traffic_enabled` setting, and a compatible
vehicle catalog entry. See the vehicle catalog section of the content-extension
API for the complete ownership and runtime safety contract.
