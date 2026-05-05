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
    LogWrite("ALLIN1.asi ScriptMain started");

    SpawnerInit();

    // Main script loop — runs as a ScriptHookV fibre, yielding each frame.
    while (true) {
        SpawnerTick();
        scriptWait(0);
    }
}

// Background thread that waits for ScriptHookV.dll to be loaded by the
// ASI loader, then resolves its exports and registers our script.
// We can't do this in DllMain because the ASI loader loads our DLL before
// ScriptHookV.dll is in memory.
static DWORD WINAPI InitThread(LPVOID) {
    LogInit();
    LogWrite("ALLIN1.asi InitThread: waiting for ScriptHookV.dll...");

    // Poll for ScriptHookV.dll — the ASI loader will load it shortly.
    for (int i = 0; i < 300; i++) {  // up to 30 seconds
        if (GetModuleHandleA("ScriptHookV.dll") != nullptr)
            break;
        Sleep(100);
    }

    if (!SHV_Init()) {
        LogWrite("ALLIN1.asi: ScriptHookV not available after waiting — aborting");
        LogClose();
        return 0;
    }

    scriptRegister(g_hModule, ScriptMain);
    LogWrite("ALLIN1.asi: script registered");
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD dwReason, LPVOID) {
    if (dwReason == DLL_PROCESS_ATTACH) {
        g_hModule = hinstDLL;
        DisableThreadLibraryCalls(hinstDLL);
        CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr);
    } else if (dwReason == DLL_PROCESS_DETACH) {
        if (p_scriptUnregister) {
            scriptUnregister(hinstDLL);
        }
        LogClose();
    }
    return TRUE;
}
