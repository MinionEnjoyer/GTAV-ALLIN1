#include "despawn_fix.h"
#include "pattern_scan.h"
#include "structs.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>

void PatchDespawnGlobal() {
    // --- Find the global variable table ---
    auto addr = FindPattern(
        "\x4C\x8D\x05\x00\x00\x00\x00\x4D\x8B\x08\x4D\x85\xC9\x74\x11",
        "xxx????xxxxxxxx");
    if (!addr) return;

    GlobalTable globalTable;
    globalTable.GlobalBasePtr = reinterpret_cast<int64_t**>(
        addr + *reinterpret_cast<int*>(addr + 3) + 7);

    // --- Find the script table ---
    addr = FindPattern(
        "\x48\x03\x15\x00\x00\x00\x00\x4C\x23\xC2\x49\x8B\x08",
        "xxx????xxxxxx");
    if (!addr) return;

    auto* scriptTable = reinterpret_cast<ScriptTable*>(
        addr + *reinterpret_cast<int*>(addr + 3) + 7);

    // Wait for the script table to be populated.
    while (*reinterpret_cast<int64_t*>(scriptTable) == 0)
        Sleep(100);

    // --- Find shop_controller.ysc ---
    ScriptTableItem* item = scriptTable->FindScript(0x39DA738B);
    if (!item) return;

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
                        int searchEnd = k + 30;
                        for (int m = k + 1; m < searchEnd; m++) {
                            auto* gpos = shopController->GetCodePositionAddress(funcOff + m);
                            if (!gpos) break;

                            if (*gpos == 0x5F) {
                                int globalIndex = *reinterpret_cast<int*>(
                                    shopController->GetCodePositionAddress(funcOff + m + 1))
                                    & 0xFFFFFF;

                                // Set the global to 1 — disables DLC vehicle despawn.
                                *globalTable.AddressOf(globalIndex) = 1;
                                return;
                            }
                        }
                        return;
                    }
                }
                return;
            }
        }
        return;
    }
}
