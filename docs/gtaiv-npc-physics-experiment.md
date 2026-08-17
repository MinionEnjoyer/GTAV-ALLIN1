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
This first ALLIN1 prototype instead sends supported NaturalMotion messages only
after a nearby ambient human ped takes fresh weapon damage.

## Safety boundary

The prototype excludes:

- the player;
- dead or non-human peds;
- mission entities and persistent peds;
- peds occupying vehicles; and
- health changes without a weapon-damage flag.

It scans at 100 ms within 70 metres, processes at most 32 candidates per scan,
and applies a per-ped reaction cooldown. The behavior times out after 4.5
seconds. These limits are intentionally conservative for the first in-game
test.

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

## First-pass tuning

The preset currently favors:

- more and larger recovery steps;
- a longer balance window before collapse;
- lower leg, spine, and arm stiffness;
- gradual loss of lower-body strength while staggering; and
- active catch-fall arm behavior.

This cannot recreate GTA IV one-to-one. GTA V's own task selection, animation
graph, ped skeleton, collision response, and underlying NaturalMotion behavior
assets remain in control. If the runtime approach proves too narrow, a later
experiment can package opt-in archive tuning as a separate manager-owned mod.
