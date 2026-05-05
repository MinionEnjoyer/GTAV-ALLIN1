#pragma once
// File redirection system for ALLIN1.asi.
//
// Hooks the RAGE engine's virtual filesystem to redirect reads of specific
// game data files to loose files in the ALLIN1/ folder next to GTA5.exe.
//
// Redirected files:
//   common/data/dlclist.xml     → ALLIN1/dlclist.xml
//   common/data/gameconfig.xml  → ALLIN1/gameconfig.xml
//   levels/gta5/popgroups.ymt   → ALLIN1/popgroups.ymt
//
// If the ALLIN1/ folder doesn't exist, or pattern scanning fails (e.g. after
// a game update), file redirection silently does nothing — the game loads its
// original files normally.
//
// Call InitFileRedirection() early, before the game loads data files.

bool InitFileRedirection();
