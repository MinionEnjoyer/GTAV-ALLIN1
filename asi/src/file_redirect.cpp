// File redirection for ALLIN1.asi.
//
// Hooks the RAGE engine's fiDeviceLocal::OpenBulk function to redirect
// reads of specific game data files to loose files in the ALLIN1/ folder.
//
// Approach: Pattern-scan for fiDeviceLocal::OpenBulk (the low-level
// function called when the game opens a file from disk).  Hook it with
// MinHook.  In the hook, check if the requested path matches one of our
// replacement files.  If the corresponding loose file exists in ALLIN1/,
// open it instead.  Otherwise fall through to the original function.
//
// Based on the ClosedIV (MIT-style) and FiveM (Apache-2.0) approaches
// to RAGE virtual filesystem hooking.

#include "file_redirect.h"
#include "pattern_scan.h"
#include "log.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <Shlwapi.h>
#include <MinHook.h>
#include <cstdint>
#include <cstring>
#include <cwchar>

#pragma comment(lib, "shlwapi.lib")

// ---------------------------------------------------------------------------
// Replacement file registry
// ---------------------------------------------------------------------------

struct RedirectEntry {
    const char* pathSuffix;      // Substring to match in the raw filesystem path
    const wchar_t* localName;    // Filename inside ALLIN1/ folder
    bool active;                 // Whether the local file exists on disk
};

static RedirectEntry g_entries[] = {
    { "dlclist.xml",      L"dlclist.xml",    false },
    { "gameconfig.xml",   L"gameconfig.xml", false },
    { "popgroups.ymt",    L"popgroups.ymt",  false },
};
static constexpr int NUM_ENTRIES = sizeof(g_entries) / sizeof(g_entries[0]);

static wchar_t g_dataFolder[MAX_PATH] = {};

// ---------------------------------------------------------------------------
// OpenBulk hook
// ---------------------------------------------------------------------------

// Original function pointer (filled by MinHook).
// Signature: HANDLE OpenBulk(fiDeviceLocal* this, const char* path, uint64_t* offset)
typedef HANDLE(__fastcall* OpenBulk_t)(void* device, const char* path, uint64_t* offset);
static OpenBulk_t g_origOpenBulk = nullptr;

static HANDLE __fastcall HookedOpenBulk(void* device, const char* path, uint64_t* offset) {
    if (path) {
        for (int i = 0; i < NUM_ENTRIES; i++) {
            if (!g_entries[i].active) continue;
            if (!strstr(path, g_entries[i].pathSuffix)) continue;

            // Build the full local path: <gameRoot>\ALLIN1\<filename>
            wchar_t localPath[MAX_PATH];
            swprintf_s(localPath, MAX_PATH, L"%s\\%s", g_dataFolder, g_entries[i].localName);

            // Open the local file directly via Win32.
            *offset = 0;
            HANDLE h = CreateFileW(
                localPath,
                GENERIC_READ,
                FILE_SHARE_READ,
                nullptr,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL | FILE_FLAG_RANDOM_ACCESS,
                nullptr);

            if (h != INVALID_HANDLE_VALUE)
                return h;

            // If the local file can't be opened, fall through to original.
            break;
        }
    }
    return g_origOpenBulk(device, path, offset);
}

// ---------------------------------------------------------------------------
// GetFileSize hook — needed so the game allocates the right buffer size
// ---------------------------------------------------------------------------

typedef uint64_t(__fastcall* GetFileSize_t)(void* device, const char* path);
static GetFileSize_t g_origGetFileSize = nullptr;

static uint64_t __fastcall HookedGetFileSize(void* device, const char* path) {
    if (path) {
        for (int i = 0; i < NUM_ENTRIES; i++) {
            if (!g_entries[i].active) continue;
            if (!strstr(path, g_entries[i].pathSuffix)) continue;

            wchar_t localPath[MAX_PATH];
            swprintf_s(localPath, MAX_PATH, L"%s\\%s", g_dataFolder, g_entries[i].localName);

            WIN32_FILE_ATTRIBUTE_DATA attr;
            if (GetFileAttributesExW(localPath, GetFileExInfoStandard, &attr))
                return attr.nFileSizeLow |
                       (static_cast<uint64_t>(attr.nFileSizeHigh) << 32);
            break;
        }
    }
    return g_origGetFileSize(device, path);
}

// ---------------------------------------------------------------------------
// GetFileTime hook — prevents cache staleness
// ---------------------------------------------------------------------------

typedef uint64_t(__fastcall* GetFileTime_t)(void* device, const char* path);
static GetFileTime_t g_origGetFileTime = nullptr;

static uint64_t __fastcall HookedGetFileTime(void* device, const char* path) {
    if (path) {
        for (int i = 0; i < NUM_ENTRIES; i++) {
            if (!g_entries[i].active) continue;
            if (!strstr(path, g_entries[i].pathSuffix)) continue;

            wchar_t localPath[MAX_PATH];
            swprintf_s(localPath, MAX_PATH, L"%s\\%s", g_dataFolder, g_entries[i].localName);

            WIN32_FILE_ATTRIBUTE_DATA attr;
            if (GetFileAttributesExW(localPath, GetFileExInfoStandard, &attr)) {
                ULARGE_INTEGER li;
                li.LowPart = attr.ftLastWriteTime.dwLowDateTime;
                li.HighPart = attr.ftLastWriteTime.dwHighDateTime;
                return li.QuadPart;
            }
            break;
        }
    }
    return g_origGetFileTime(device, path);
}

// ---------------------------------------------------------------------------
// Pattern database for fiDeviceLocal functions
// ---------------------------------------------------------------------------

struct ScanPattern {
    const char* pattern;
    const char* mask;
};

// fiDeviceLocal::OpenBulk patterns (try multiple for version resilience)
static const ScanPattern g_openBulkPatterns[] = {
    // b2699+ / b3258+ full prologue
    {
        "\x40\x53\x48\x81\xEC\x00\x00\x00\x00\x49\x8B\xD8\x4C\x8B\xC2"
        "\x48\x8D\x4C\x24\x00\xBA\x00\x00\x00\x00\xE8",
        "xxxxx????xxxxxx"
        "xxxx?x????x"
    },
};

// fiDeviceLocal::GetFileSize patterns
static const ScanPattern g_getFileSizePatterns[] = {
    {
        "\x48\x81\xEC\x00\x00\x00\x00\x4C\x8B\xC2\x48\x8D\x4C\x24\x00"
        "\xBA\x00\x00\x00\x00\xE8\x00\x00\x00\x00\x4C\x8D\x44\x24\x00"
        "\x33\xD2\x48\x8B\xC8\xFF\x15\x00\x00\x00\x00\x85\xC0\x75\x04"
        "\x33\xC0\xEB\x0F\x8B\x44\x24\x3C",
        "xxx????xxxxxxx?"
        "x????x????xxxx?"
        "xxxxxxx????xxxx"
        "xxxxxxxx"
    },
};

// fiDeviceLocal::GetFileTime patterns
static const ScanPattern g_getFileTimePatterns[] = {
    {
        "\x48\x81\xEC\x00\x00\x00\x00\x4C\x8B\xC2\x48\x8D\x4C\x24\x00"
        "\xBA\x00\x00\x00\x00\xE8\x00\x00\x00\x00\x4C\x8D\x44\x24\x00"
        "\x33\xD2\x48\x8B\xC8\xFF\x15\x00\x00\x00\x00\x85\xC0\x75\x04"
        "\x33\xC0\xEB\x0F\x8B\x44\x24\x38",
        "xxx????xxxxxxx?"
        "x????x????xxxx?"
        "xxxxxxx????xxxx"
        "xxxxxxxx"
    },
};

static uintptr_t TryPatterns(const ScanPattern* patterns, int count) {
    for (int i = 0; i < count; i++) {
        uintptr_t addr = FindPattern(patterns[i].pattern, patterns[i].mask);
        if (addr) return addr;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

bool InitFileRedirection() {
    // 1. Find game root directory.
    wchar_t exePath[MAX_PATH];
    GetModuleFileNameW(nullptr, exePath, MAX_PATH);
    PathRemoveFileSpecW(exePath);
    LogWrite("  Game root: %ls", exePath);

    // 2. Check for ALLIN1/ data folder.
    swprintf_s(g_dataFolder, MAX_PATH, L"%s\\ALLIN1", exePath);
    if (GetFileAttributesW(g_dataFolder) == INVALID_FILE_ATTRIBUTES) {
        LogWrite("  ALLIN1/ folder not found — aborting file redirection");
        return false;
    }
    LogWrite("  ALLIN1/ folder found");

    // 3. Check which replacement files exist.
    bool anyActive = false;
    for (int i = 0; i < NUM_ENTRIES; i++) {
        wchar_t path[MAX_PATH];
        swprintf_s(path, MAX_PATH, L"%s\\%s", g_dataFolder, g_entries[i].localName);
        g_entries[i].active = (GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES);
        anyActive = anyActive || g_entries[i].active;
        LogWrite("  %s: %s", g_entries[i].pathSuffix,
                 g_entries[i].active ? "found" : "MISSING");
    }
    if (!anyActive) {
        LogWrite("  No replacement files found — aborting");
        return false;
    }

    // 4. Initialise MinHook.
    if (MH_Initialize() != MH_OK) {
        LogWrite("  MinHook init failed");
        return false;
    }
    LogWrite("  MinHook initialised");

    bool hooked = false;

    // 5. Hook OpenBulk.
    uintptr_t openBulkAddr = TryPatterns(
        g_openBulkPatterns,
        sizeof(g_openBulkPatterns) / sizeof(g_openBulkPatterns[0]));
    LogWrite("  OpenBulk pattern scan: %s (0x%llX)",
             openBulkAddr ? "found" : "NOT FOUND", (unsigned long long)openBulkAddr);
    if (openBulkAddr) {
        auto status = MH_CreateHook(reinterpret_cast<LPVOID>(openBulkAddr),
                          reinterpret_cast<LPVOID>(HookedOpenBulk),
                          reinterpret_cast<LPVOID*>(&g_origOpenBulk));
        if (status == MH_OK) {
            MH_EnableHook(reinterpret_cast<LPVOID>(openBulkAddr));
            hooked = true;
            LogWrite("  OpenBulk hook: OK");
        } else {
            LogWrite("  OpenBulk hook: FAILED (MH status %d)", status);
        }
    }

    // 6. Hook GetFileSize (optional — improves reliability).
    uintptr_t getFileSizeAddr = TryPatterns(
        g_getFileSizePatterns,
        sizeof(g_getFileSizePatterns) / sizeof(g_getFileSizePatterns[0]));
    LogWrite("  GetFileSize pattern scan: %s (0x%llX)",
             getFileSizeAddr ? "found" : "NOT FOUND", (unsigned long long)getFileSizeAddr);
    if (getFileSizeAddr) {
        if (MH_CreateHook(reinterpret_cast<LPVOID>(getFileSizeAddr),
                          reinterpret_cast<LPVOID>(HookedGetFileSize),
                          reinterpret_cast<LPVOID*>(&g_origGetFileSize)) == MH_OK) {
            MH_EnableHook(reinterpret_cast<LPVOID>(getFileSizeAddr));
            LogWrite("  GetFileSize hook: OK");
        } else {
            LogWrite("  GetFileSize hook: FAILED");
        }
    }

    // 7. Hook GetFileTime (optional — prevents stale cache).
    uintptr_t getFileTimeAddr = TryPatterns(
        g_getFileTimePatterns,
        sizeof(g_getFileTimePatterns) / sizeof(g_getFileTimePatterns[0]));
    LogWrite("  GetFileTime pattern scan: %s (0x%llX)",
             getFileTimeAddr ? "found" : "NOT FOUND", (unsigned long long)getFileTimeAddr);
    if (getFileTimeAddr) {
        if (MH_CreateHook(reinterpret_cast<LPVOID>(getFileTimeAddr),
                          reinterpret_cast<LPVOID>(HookedGetFileTime),
                          reinterpret_cast<LPVOID*>(&g_origGetFileTime)) == MH_OK) {
            MH_EnableHook(reinterpret_cast<LPVOID>(getFileTimeAddr));
            LogWrite("  GetFileTime hook: OK");
        } else {
            LogWrite("  GetFileTime hook: FAILED");
        }
    }

    if (!hooked) {
        LogWrite("  No hooks installed — uninitialising MinHook");
        MH_Uninitialize();
        return false;
    }

    return true;
}
