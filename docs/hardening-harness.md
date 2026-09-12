# Off-game hardening harness

Run `python tools/hardening_harness.py` from a prepared checkout. It never
installs dependencies, builds a public archive, runs the installer, or opens a
game. Each run writes fresh evidence to `build/hh/<run-id>/summary.json`; an
existing run id is refused.

The source profile runs the complete Python suite except opt-in
`windows_integration` and `packaged_integration` markers, with the 91% coverage
gate, production TypeScript build, mapped React assertions, Rust tests,
documentation/retirement audits, and—on Windows—C# TRX plus CMake/CTest map-host
policy. `--real-tools` also opts into Windows integration and RpfPatcher
key-context tests. Packaged integration is recorded NOT TESTED, never counted as
source-profile coverage.

Missing prerequisites; failed, missing, empty, or malformed evidence; required
skips; and source-input drift fail the run. Skipped JUnit/TRX tests are listed
with their reasons and mark a layer `INCOMPLETE` (nonzero). Generated
`script/dist` artifacts are separately hashed so intentional C# output is not
source drift. Packaged release, installer lifecycle, and live-game checks remain
explicitly unrun.

## Recovery safeguards

General backup discovery/restore accepts only timestamp snapshot folders: legacy
`YYYYMMDD_HHMMSS` and current timestamp/microsecond/sequence/UUID names.
`ALLIN1_Backups/Mods` package rollback storage is never a general restore source,
including on case-insensitive Windows. Renamed/arbitrary folders are rejected.

Backups become discoverable only after staging; failed hidden staging folders
remain for inspection. Restore preflights destinations and publishes each file
atomically, not as an all-files transaction against disk failure or a hostile
local process. The harness uses disposable fixtures and never modifies installed
game data.
