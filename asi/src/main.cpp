// ALLIN1.asi — GTA V ASI plugin for one-click MP vehicle traffic.
//
// Two responsibilities:
// 1. File redirection: hooks the RAGE filesystem to redirect reads of
//    popgroups.ymt, dlclist.xml, and gameconfig.xml to loose files in
//    the ALLIN1/ folder next to GTA5.exe.
// 2. Despawn fix: patches the shop_controller.ysc global variable that
//    causes DLC vehicles to be removed in Story Mode.
//
// If any pattern scan fails (e.g. after a game update), the affected
// subsystem silently does nothing — the game runs normally.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "file_redirect.h"
#include "despawn_fix.h"

static DWORD WINAPI MainThread(LPVOID) {
    // Phase 1: File redirection — install early, before the game loads data.
    // Must happen before the game's initial file loading pass.
    InitFileRedirection();

    // Phase 2: Despawn fix — wait for the script engine to initialise.
    Sleep(5000);
    PatchDespawnGlobal();

    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD dwReason, LPVOID) {
    if (dwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        CreateThread(nullptr, 0, MainThread, nullptr, 0, nullptr);
    }
    return TRUE;
}
