// ALLIN1.asi — Minimal GTA V ASI plugin to disable DLC vehicle despawn.
//
// GTA V's shop_controller.ysc script has a global variable that gates
// whether MP/DLC vehicles are allowed in single player. When this global
// is 0 (the default in Story Mode), the script actively removes any DLC
// vehicle that spawns. This plugin sets that global to 1, allowing MP
// vehicles injected via popgroups.ymt to persist in ambient traffic.
//
// No ScriptHookV dependency. No config files. No logging.
// If pattern scanning fails (e.g. after a game update), the plugin
// silently does nothing — the game runs normally.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <Psapi.h>
#include <cstdint>
#include "structs.h"

#pragma comment(lib, "psapi.lib")

// ---------------------------------------------------------------------------
// Pattern scanner
// ---------------------------------------------------------------------------

static uintptr_t FindPattern(const char* pattern, const char* mask,
                             const char* start, size_t size) {
    const char* end = start + size;
    const size_t maskLen = strlen(mask) - 1;

    for (size_t i = 0; start < end; start++) {
        if (*start == pattern[i] || mask[i] == '?') {
            if (mask[i + 1] == '\0')
                return reinterpret_cast<uintptr_t>(start) - maskLen;
            i++;
        } else {
            i = 0;
        }
    }
    return 0;
}

static uintptr_t FindPattern(const char* pattern, const char* mask) {
    MODULEINFO mod = {};
    GetModuleInformation(GetCurrentProcess(), GetModuleHandle(nullptr),
                         &mod, sizeof(mod));
    return FindPattern(pattern, mask,
                       reinterpret_cast<const char*>(mod.lpBaseOfDll),
                       mod.SizeOfImage);
}

// ---------------------------------------------------------------------------
// Core logic
// ---------------------------------------------------------------------------

static DWORD WINAPI DisableDespawn(LPVOID) {
    // Give the game time to initialize its script engine.
    Sleep(5000);

    // --- Find the global variable table ---
    auto addr = FindPattern(
        "\x4C\x8D\x05\x00\x00\x00\x00\x4D\x8B\x08\x4D\x85\xC9\x74\x11",
        "xxx????xxxxxxxx");
    if (!addr) return 0;

    GlobalTable globalTable;
    globalTable.GlobalBasePtr = reinterpret_cast<int64_t**>(
        addr + *reinterpret_cast<int*>(addr + 3) + 7);

    // --- Find the script table ---
    addr = FindPattern(
        "\x48\x03\x15\x00\x00\x00\x00\x4C\x23\xC2\x49\x8B\x08",
        "xxx????xxxxxx");
    if (!addr) return 0;

    auto* scriptTable = reinterpret_cast<ScriptTable*>(
        addr + *reinterpret_cast<int*>(addr + 3) + 7);

    // Wait for the script table to be populated.
    while (*reinterpret_cast<int64_t*>(scriptTable) == 0)
        Sleep(100);

    // --- Find shop_controller.ysc ---
    ScriptTableItem* item = scriptTable->FindScript(0x39DA738B);
    if (!item) return 0;

    while (!item->IsLoaded())
        Sleep(100);

    ScriptHeader* shopController = item->header;

    // Wait for globals to be initialised.
    while (!globalTable.IsInitialised())
        Sleep(100);

    // --- Scan shop_controller bytecode for the despawn global variable ---
    for (int i = 0; i < shopController->CodePageCount(); i++) {
        auto sig = FindPattern(
            "\x28\x26\xCE\x6B\x86\x39\x03", "xxxxxxx",
            reinterpret_cast<const char*>(shopController->GetCodePageAddress(i)),
            shopController->GetCodePageSize(i));

        if (!sig) continue;

        // Convert memory address to script-relative code offset.
        int codeOff = static_cast<int>(
            sig - reinterpret_cast<uintptr_t>(shopController->GetCodePageAddress(i))
            + (i << 14));

        // Walk backwards to find the CALL opcode (0x0008012D).
        for (int j = 0; j < 2000; j++) {
            auto* pos = shopController->GetCodePositionAddress(codeOff - j);
            if (!pos) break;

            if (*reinterpret_cast<int*>(pos) == 0x0008012D) {
                // Extract the function offset from the CALL instruction.
                int funcOff = *reinterpret_cast<int*>(
                    shopController->GetCodePositionAddress(codeOff - j + 6)) & 0xFFFFFF;

                // Search the function for GLOBAL_U24 opcode (0x01002E).
                for (int k = 5; k < 0x40; k++) {
                    auto* fpos = shopController->GetCodePositionAddress(funcOff + k);
                    if (!fpos) break;

                    if ((*reinterpret_cast<int*>(fpos) & 0xFFFFFF) == 0x01002E) {
                        // Find the IGET opcode (0x5F) that loads the global index.
                        for (k = k + 1; k < k + 30; k++) {
                            auto* gpos = shopController->GetCodePositionAddress(funcOff + k);
                            if (!gpos) break;

                            if (*gpos == 0x5F) {
                                int globalIndex = *reinterpret_cast<int*>(
                                    shopController->GetCodePositionAddress(funcOff + k + 1))
                                    & 0xFFFFFF;

                                // Set the global to 1 — disables DLC vehicle despawn.
                                *globalTable.AddressOf(globalIndex) = 1;
                                return 0;
                            }
                        }
                        return 0;
                    }
                }
                return 0;
            }
        }
        return 0;
    }

    return 0;
}

// ---------------------------------------------------------------------------
// DLL entry point
// ---------------------------------------------------------------------------

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD dwReason, LPVOID) {
    if (dwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        CreateThread(nullptr, 0, DisableDespawn, nullptr, 0, nullptr);
    }
    return TRUE;
}
