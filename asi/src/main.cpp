// ALLIN1.asi — GTA V ASI plugin for spawning GTA Online vehicles in SP traffic.
//
// Uses ScriptHookV's native API to:
//   1. Enumerate available DLC vehicles at runtime
//   2. Spawn them at nearby road nodes with AI drivers
//   3. Apply the MPBitset decorator to prevent despawning
//
// Requires ScriptHookV (from dev-c.com) to be installed in the game folder.

#include "../lib/ScriptHookV/inc/main.h"
#include "log.h"
#include "vehicle_spawner.h"

static HMODULE g_hModule = nullptr;

void ScriptMain() {
    LogInit();
    LogWrite("ALLIN1.asi ScriptMain started");

    SpawnerInit();

    // Main script loop — runs as a ScriptHookV fibre, yielding each frame.
    while (true) {
        SpawnerTick();
        scriptWait(0);
    }
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD dwReason, LPVOID) {
    if (dwReason == DLL_PROCESS_ATTACH) {
        g_hModule = hinstDLL;
        scriptRegister(hinstDLL, ScriptMain);
    } else if (dwReason == DLL_PROCESS_DETACH) {
        scriptUnregister(hinstDLL);
        LogClose();
    }
    return TRUE;
}
