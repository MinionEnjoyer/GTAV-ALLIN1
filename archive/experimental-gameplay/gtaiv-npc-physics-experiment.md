# GTA IV-style NPC physics experiment

This branch tests an approximation of GTA IV's heavier pedestrian reactions.
The primary layer sends runtime NaturalMotion messages. An optional archive
layer installs the audited E.R.O. 1.9.4 `behaviours.xml` and
`physicstasks.ymt` payload into OpenRPF `mods` copies. It does not copy GTA IV
assets or modify stock GTA V archives.

## Prior art

- [Euphoria Ragdoll Overhaul (E.R.O.)](https://www.gta5-mods.com/misc/euphoria-ragdoll-overhaul-ero)
  changes balancing, wound reactions, car impacts, and bailout behavior. Its
  stated goal is to bring GTA V closer to GTA IV, Red Dead Redemption, and Max
  Payne 3.
- [Unrealistic Euphoria Ragdoll Overhaul](https://www.gta5-mods.com/misc/blorpis-s-ragdoll-overhaul)
  tunes falling, bracing, stagger balance, friction, stiffness, gunshots, and
  bailout reactions. It installs replacement `physicstasks` and NaturalMotion
  behavior files.
- [GTA IV Euphoria Physics Recreation](https://www.gta5-mods.com/misc/my-own-euphoria-mod-v-0-3)
  is another data-file recreation rather than an engine transplant.
- [ScriptHookVDotNet](https://github.com/scripthookvdotnet/scripthookvdotnet/blob/main/source/scripting_v3/GTA/Entities/Peds/Ped.cs)
  exposes GTA V's NaturalMotion/Euphoria helpers to managed scripts. Relevant
  helpers include `ConfigureBalance`, `StaggerFall`, and `CatchFall`.

The established overhauls mainly replace archive-level tuning data. That can
affect every Euphoria task, but it also creates compatibility and removal costs.
The ALLIN1 runtime layer sends supported NaturalMotion messages after a nearby
ambient human takes fresh weapon, melee, fire, or explosion damage, receives a
close vehicle bump, or is pushed by the player. The optional archive layer
supplies global fall, balance, impact, and bailout defaults that scripts cannot
reliably replace.

## Safety boundary

The prototype excludes:

- the player;
- non-human peds and damage without fresh health/armor or collision evidence;
- mission entities and persistent peds;
- vehicle occupants.

It scans at 100 ms within 70 metres, processes the nearest 64 candidates per
scan, and applies separate per-ped damage, vehicle-impact, and player-push
cooldowns. Every helper has a short timeout. These limits keep the experiment
bounded during normal play.

## Enabling it

Use the manager's **Experimental GTA IV-style NPC physics** checkbox, save the
configuration, install/update ALLIN1, and restart GTA V. The equivalent manual
setting in `scripts/ALLIN1.toml` is:

```toml
[script]
gta_iv_npc_physics = true
gta_iv_npc_physics_debug = true
```

Diagnostics are written as rotating JSON lines to
`scripts/ALLIN1_npc_physics.log`. Heartbeats show candidate counts, exclusions,
accepted reactions, NaturalMotion stages, exceptions, and delayed reaction
outcomes. Stage entries explicitly report managed dispatch rather than claiming
engine-side visual acknowledgement. Delayed samples include the pre-reaction
baseline, displacement, velocity/height deltas, ragdoll transitions, and whether
a physical response was observable. Expected damage during an active reaction is
classified separately from genuinely ambiguous damage provenance.

Set `gta_iv_npc_physics` to `false` and restart to disable the runtime layer.
Archive tuning, if installed, remains global until explicitly removed.

## Optional archive tuning

E.R.O. is third-party work and is not redistributed with ALLIN1. Obtain the
author's E.R.O. 1.9.4 ZIP/OIV, then validate it before installation:

```powershell
tools\RpfPatcher\RpfPatcher.exe validate-euphoria "E.R.O 1.9.4.zip"
tools\RpfPatcher\RpfPatcher.exe install-euphoria `
  "D:\Path\To\Grand Theft Auto V" "E.R.O 1.9.4.zip"
```

On GTA V Enhanced, `install-euphoria` refuses to continue unless
`--allow-enhanced` is supplied. The payload is legacy-era tuning and Enhanced
support remains experimental. Close GTA V before installing or removing it.

Installation changes only `mods/update/update.rpf`, `mods/common.rpf`, and
`mods/x64a.rpf`. The tool creates `.allin1-euphoria.bak` rollback snapshots,
preflights all three archives before writing, rolls the full set back if an
install or verification step fails, verifies all installed entries
byte-for-byte, and writes `scripts/ALLIN1_euphoria_tuning.json`. Verification
is read-only and also validates that marker:

```powershell
tools\RpfPatcher\RpfPatcher.exe verify-euphoria `
  "D:\Path\To\Grand Theft Auto V" "E.R.O 1.9.4.zip"
```

Remove the archive layer with:

```powershell
tools\RpfPatcher\RpfPatcher.exe remove-euphoria `
  "D:\Path\To\Grand Theft Auto V"
```

Removal restores each complete archive snapshot, not only the two tuning
files. Do not install unrelated changes into those three `mods` archives
between this experiment and removal unless you first preserve those changes
separately.

## Changelog-guided tuning

The expanded runtime preset now includes:

- moderate live-reaction Euphoria stiffness with 25% relaxation and controlled
  foot friction, while lethal reactions retain a much looser profile;
- longer balancing with additional recovery steps and one delayed live-hit
  reinforcement after GTA's initial shot task;
- body-region reactions based on GTA's last-damaged bone;
- delayed leg collapse and active stepping after leg shots;
- gut/spine tension for torso wounds;
- one- or two-handed wound reaching while standing, falling, or grounded;
- explicit skeletal, physics, and IK hand-bone recognition: a hand hit suppresses
  point-gun/bracing behavior, lengthens the injured-arm response, and drops the
  currently held weapon;
- subtle, chance-based grounded head-trauma leg movement, gated by both ground
  proximity and body tilt so an upright ped is not treated as floor-bound;
- chance-based knee drops on freshly observed lethal hits;
- a chance for armed peds to retain point-gun behavior while balancing;
- balanced electroshock and on-fire reactions;
- protective upper-body flinching near explosions;
- unmodified native reactions for low-speed car pushes (no ScriptControl,
  balancing, or bracing message that could start a ragdoll); and
- higher-speed no-forward-roll falls with reduced rebound and tumbling.

Neither layer alters global ragdoll pool limits, material penetration, animal
bounds, or weapon force data. The current E.R.O. payload intentionally follows
1.9.4: it does not install the retired `pedbounds.xml` or `materials.dat` files.

## Ambient combat cohesion

The runtime experiment also coordinates a small number of nearby ambient
allies when a living teammate is badly injured and physically down. One healthy
ally approaches and performs a bounded stabilization action while a second
armed ally seeks defensive cover and engages a known threat. Stabilization
never revives a dead ped, never exceeds the ped's maximum health, and sends the
casualty toward cover instead of immediately returning them to an exposed
firing position. Player peds and vehicle occupants are excluded. Story and
cutscene entities remain excluded, while hostile open-world police and military
responders may participate even when Rockstar marks them persistent or as
runtime mission entities. All requests, phases, completions,
interruptions, and cover assignments are included in the physics diagnostic
log and heartbeat counters.

## Police tactical coordination

**Enhanced Police AI** is enabled by default on this experiment branch. The
launcher's Gameplay page writes `enhanced_police_ai` under `[script]` in
`scripts/ALLIN1.toml`; clearing the option disables it independently from the
experimental NPC physics toggle. Existing configurations without the key use
the enabled default until the launcher writes an explicit value.

During open-world wanted combat at two stars or higher, nearby armed officers
can be grouped into at most two six-person tactical elements. The coordinator
does not replace mission AI and excludes vehicle occupants, downed officers,
active rappellers, and anyone assigned to an injured-ally response.

Only a healthy six-officer element with no local casualties may form compact,
individually spaced rally slots for an assault. The complete element must hold
the stack for at least three seconds; a partial element never launches on a
timeout. Two officers remain in defensive support while the rest close on
separated assault positions simultaneously. A failed assembly falls back to a
defensive line instead of sending a lone officer forward.

Smaller, wounded, locally casualty-heavy, or anti-vehicle elements form a
firing line. Casualties influence only elements within 22 metres rather than
every officer inside the global coordination radius. Each officer receives a
separate defensive sector, moves there while aiming, then seeks cover tied to
that sector. Cover searches use threat-relative cover nodes rather than treating
a nav-safe road coordinate as cover. A line is never reported as established
without its required majority. If the player moves beyond the engagement
anchor or a tactical cycle expires, the surviving element recomputes its
perimeter instead of being released directly into vanilla `FightAgainst`.
Tactical cycles and reassignment cooldowns are bounded, and squad formation,
readiness, cover
acquisition/failure, rush, fallback, release, and loss events are written to
`ALLIN1_npc_physics.log`.

Suitable arriving police cars with at least three healthy law occupants can
stage ahead of the player's travel path. The car stops broadside as hard cover,
the occupants dismount as one reserved element, and that element is forced into
a defensive line. Point-blank, badly damaged, mission, and undersized vehicle
responses remain under vanilla control.

An established line can publish a casualty collection point nine metres behind
it and a separate helicopter landing point farther to the rear. A stabilized
casualty and rescuer route to that point instead of treating the exposed impact
location as the end of the response. If a reconnaissance helicopter has a free
passenger seat and the landing zone is not occupied by another vehicle, it can
switch to a bounded Land-and-Wait CASEVAC task, board the casualty, depart the
engagement, and then return to reconnaissance. No aircraft is spawned and
mission/cutscene helicopters remain excluded.

Enhanced Police AI also permits disarmed officers to recover real nearby weapon
pickup objects, or replace an existing sidearm with a better pickup, only while
out of the player's line of fire and outside a tactical assignment. The
allowlist is limited to conventional pistols, shotguns, SMGs, PDWs, and carbines;
explosives, heavy weapons, and special weapons are never selected. Recovery
searches, safety aborts, commands, and completions are diagnostic events.

## Fast-rope landing recovery

Open-world helicopter rappellers are tracked through Rockstar's actual
`SCRIPT_TASK_RAPPEL_FROM_HELI` status. A recovery is applied only when that task
transitions into an uncontrolled airborne fall and the measured descent or
vertical drop crosses the hard-landing threshold. Normal ground dismounts are
left alone. The impact recovery scales from 1.4 to 3.6 seconds and can reassert
the ragdoll at most twice if the original combat task tries to snap the ped
upright. Story missions and cutscenes disable this layer.

## Aerial reconnaissance

Eligible open-world police and military helicopters no longer all behave as
direct-fire gunships. Every eligible aircraft begins in reconnaissance. When a
fully coordinated ground assault requests fire support, one recon aircraft with
fresh visual information may commit to a dedicated close-air-support sortie;
every other aircraft remains recon.
Recon aircraft maintain a moving stand-off
orbit around their last visually confirmed player position, use Rockstar's
police sighting report to relay contact, and reduce door-gunner fire cadence.

An ambient rappel request is redirected through the ground perimeter instead
of being accepted over the active engagement. The aircraft first looks for a
flat, pedestrian-navigable rooftop behind an established firing line. If no
local roof passes the surface and threat-distance checks, it uses a separated
ground insertion point behind that line. The helicopter receives a persistent
approach waypoint and releases its crew only after holding a stable 8--24 metre
hover over the approved point. The empty aircraft is then immediately eligible
for a waiting casualty-collection CASEVAC request. Without an established line,
the crew remains aboard and the aircraft continues reconnaissance.

Reconnaissance waypoints advance only when the aircraft reaches a waypoint or
must newly leave the unsafe inner perimeter. A moved intelligence anchor or an
old task does not refresh the same absolute `GoTo` mission. If a leg remains
far from its target and makes no measurable progress, ALLIN1 logs
`aerial_recon_leg_stalled`, ends only its scripted pilot task, and lets the
ambient helicopter AI resume. Script control is reacquired only if the aircraft
later enters the unsafe inner perimeter. This avoids the repeated task
replacement that could leave helicopters hovering in place.

Some ambient deployments do not expose `SCRIPT_TASK_RAPPEL_FROM_HELI` while the
officer is still seated. An intercepted airborne seat exit is therefore treated
as a deployment request, logged as
`aerial_rappel_request_inferred_from_exit`, and routed through the same safe
insertion planner. Throttled `aerial_safe_rappel_deferred` events identify a
missing firing line or a rejected rear zone and include rooftop raycast,
slope, elevation, navmesh, and threat-distance rejection counts. CASEVAC waits
similarly report `aerial_casevac_deferred` with the unavailable-aircraft,
insertion-busy, seat, landing-obstruction, or threat-proximity reason.

Visual contact expires after 20 seconds. The role is not assigned to landed or
damaged aircraft, non-law crews, story missions, cutscenes, or helicopters that
are currently deploying rappellers. Crew fire cadence is restored when the
role ends. CAS retains normal gunner cadence and is the only tracked aircraft
given an attack chase. Once committed, that aircraft remains CAS until the
ground move ends, its intelligence becomes stale, or sustained player fire
forces it to break off. It then suppresses its guns and flies out rather than
oscillating back into recon. An assigned reconnaissance aircraft may accept
the bounded CASEVAC phase described above; it remains tracked while landing so
the ordinary airborne eligibility check does not cancel the evacuation.

This cannot recreate GTA IV one-to-one. GTA V's own task selection, animation
graph, ped skeleton, collision response, and underlying NaturalMotion behavior
assets remain in control. Archive tuning broadens coverage, but Enhanced can
still select or interpret tasks differently from the legacy build it targeted.
