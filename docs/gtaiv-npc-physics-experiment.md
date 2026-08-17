# GTA IV-style NPC physics experiment

This branch tests a runtime-only approximation of GTA IV's heavier pedestrian
reactions. It does not copy GTA IV assets and does not patch GTA V archives.

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
This ALLIN1 prototype instead sends supported NaturalMotion messages after a
nearby ambient human takes fresh weapon damage, receives a close vehicle bump,
or is hurt by a nearby explosion.

## Safety boundary

The prototype excludes:

- the player;
- non-human peds and deaths without a freshly observed damage event;
- mission entities and persistent peds;
- peds occupying vehicles; and
- health changes without a weapon-damage flag.

It scans at 100 ms within 70 metres, processes at most 32 candidates per scan,
and applies separate per-ped weapon and vehicle-impact cooldowns. Every helper
has a short timeout. These limits keep the experiment bounded during normal
play.

## Enabling it

Use the manager's **Experimental GTA IV-style NPC physics** checkbox, save the
configuration, install/update ALLIN1, and restart GTA V. The equivalent manual
setting in `scripts/ALLIN1.toml` is:

```toml
[script]
gta_iv_npc_physics = true
```

Set it to `false` and restart to restore vanilla behavior. No RPF repair is
required.

## Changelog-guided tuning

The expanded runtime preset now includes:

- minimum global Euphoria stiffness with controlled foot friction;
- longer, looser balancing with additional recovery steps;
- body-region reactions based on GTA's last-damaged bone;
- delayed leg collapse and active stepping after leg shots;
- gut/spine tension for torso wounds;
- one- or two-handed wound reaching while standing, falling, or grounded;
- subtle, chance-based grounded head-trauma leg movement;
- chance-based knee drops on freshly observed lethal hits;
- a chance for armed peds to retain point-gun behavior while balancing;
- balanced electroshock and on-fire reactions;
- protective upper-body flinching near explosions;
- low-speed car-push balancing with short, weak bonnet bracing; and
- higher-speed no-forward-roll falls with reduced rebound and tumbling.

The runtime version intentionally does not alter global ragdoll pool limits,
vehicle crash elasticity, material penetration, animal bounds, motorcycle
bailout tuning, or archive-level task defaults. Those changelog items require
replacement game data and would make this experiment less reversible and more
likely to conflict with other mods.

This cannot recreate GTA IV one-to-one. GTA V's own task selection, animation
graph, ped skeleton, collision response, and underlying NaturalMotion behavior
assets remain in control. If the runtime approach proves too narrow, a later
experiment can package opt-in archive tuning as a separate manager-owned mod.
