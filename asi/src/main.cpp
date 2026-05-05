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

void ScriptMain() {
    LogInit();
    LogWrite("ALLIN1.asi ScriptMain started");

    SpawnerInit();

    while (true) {
        SpawnerTick();
        WAIT(0);
    }
}

BOOL APIENTRY DllMain(HMODULE hInstance, DWORD reason, LPVOID lpReserved) {
    switch (reason) {
    case DLL_PROCESS_ATTACH:
        scriptRegister(hInstance, ScriptMain);
        break;
    case DLL_PROCESS_DETACH:
        scriptUnregister(hInstance);
        LogClose();
        break;
    }
    return TRUE;
}
