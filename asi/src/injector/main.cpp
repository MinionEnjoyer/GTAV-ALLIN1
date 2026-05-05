// ALLIN1-Launcher — Inject ALLIN1.dll into GTA V at runtime.
//
// Bypasses BattlEye's proxy-DLL block by injecting after the game has
// started, using the standard CreateRemoteThread + LoadLibraryA technique.
//
// Usage: place next to ALLIN1.dll in the GTA V root folder.
//        1. Run ALLIN1-Launcher.exe  (requests admin via UAC prompt)
//        2. Launch GTA V normally (through Steam / Rockstar Launcher)
//        3. The launcher detects the game and injects automatically

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <shlwapi.h>
#include <cstdio>
#include <cstring>

#pragma comment(lib, "shlwapi.lib")
#pragma comment(lib, "advapi32.lib")

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

static const char* DLL_NAME         = "ALLIN1.dll";
static const char* GAME_EXES[]      = { "GTA5.exe", "GTA5_Enhanced.exe" };
static const int   GAME_EXE_COUNT   = 2;
static const int   POLL_TIMEOUT_SEC = 120;
static const int   POLL_INTERVAL_MS = 1000;
static const int   INIT_DELAY_MS    = 5000;

// ---------------------------------------------------------------------------
// Privilege escalation
// ---------------------------------------------------------------------------

/// Enable SeDebugPrivilege so we can open the game process with full access.
/// Without this, VirtualAllocEx / WriteProcessMemory fail with ERROR_ACCESS_DENIED
/// even when running as administrator.
static bool EnableDebugPrivilege() {
    HANDLE hToken = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(),
                          TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &hToken)) {
        return false;
    }

    LUID luid{};
    if (!LookupPrivilegeValueA(nullptr, "SeDebugPrivilege", &luid)) {
        CloseHandle(hToken);
        return false;
    }

    TOKEN_PRIVILEGES tp{};
    tp.PrivilegeCount = 1;
    tp.Privileges[0].Luid = luid;
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;

    BOOL ok = AdjustTokenPrivileges(hToken, FALSE, &tp, sizeof(tp), nullptr, nullptr);
    DWORD err = GetLastError();
    CloseHandle(hToken);

    // AdjustTokenPrivileges returns TRUE even if it couldn't set the
    // privilege — check GetLastError for ERROR_NOT_ALL_ASSIGNED.
    return ok && err == ERROR_SUCCESS;
}

// ---------------------------------------------------------------------------
// Process discovery
// ---------------------------------------------------------------------------

/// Find a running process by name.  Returns the PID or 0 if not found.
static DWORD FindProcess(const char* name) {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return 0;

    PROCESSENTRY32 entry{};
    entry.dwSize = sizeof(entry);

    DWORD pid = 0;
    if (Process32First(snap, &entry)) {
        do {
            if (_stricmp(entry.szExeFile, name) == 0) {
                pid = entry.th32ProcessID;
                break;
            }
        } while (Process32Next(snap, &entry));
    }

    CloseHandle(snap);
    return pid;
}

/// Find any running GTA V process.  Returns the PID and sets exeName to the
/// matched executable name, or returns 0 if not found.
static DWORD FindGameProcess(const char** exeName) {
    for (int i = 0; i < GAME_EXE_COUNT; ++i) {
        DWORD pid = FindProcess(GAME_EXES[i]);
        if (pid) {
            if (exeName) *exeName = GAME_EXES[i];
            return pid;
        }
    }
    return 0;
}

/// Build the full path to ALLIN1.dll (same directory as this exe).
static bool GetDllPath(char* out, DWORD size) {
    if (!GetModuleFileNameA(nullptr, out, size)) return false;
    PathRemoveFileSpecA(out);
    PathAppendA(out, DLL_NAME);
    return GetFileAttributesA(out) != INVALID_FILE_ATTRIBUTES;
}

// ---------------------------------------------------------------------------
// Injection
// ---------------------------------------------------------------------------

/// Inject a DLL into a target process.  Returns true on success.
static bool InjectDLL(DWORD pid, const char* dllPath) {
    HANDLE hProc = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!hProc) {
        printf("[ERROR] OpenProcess failed (err %lu).\n", GetLastError());
        printf("        Make sure you ran this launcher as Administrator.\n");
        return false;
    }

    size_t pathLen = strlen(dllPath) + 1;
    void* remoteMem = VirtualAllocEx(
        hProc, nullptr, pathLen, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remoteMem) {
        printf("[ERROR] VirtualAllocEx failed (err %lu).\n", GetLastError());
        CloseHandle(hProc);
        return false;
    }

    if (!WriteProcessMemory(hProc, remoteMem, dllPath, pathLen, nullptr)) {
        printf("[ERROR] WriteProcessMemory failed (err %lu).\n", GetLastError());
        VirtualFreeEx(hProc, remoteMem, 0, MEM_RELEASE);
        CloseHandle(hProc);
        return false;
    }

    FARPROC loadLib = GetProcAddress(GetModuleHandleA("kernel32.dll"),
                                     "LoadLibraryA");
    if (!loadLib) {
        printf("[ERROR] Could not find LoadLibraryA.\n");
        VirtualFreeEx(hProc, remoteMem, 0, MEM_RELEASE);
        CloseHandle(hProc);
        return false;
    }

    HANDLE hThread = CreateRemoteThread(
        hProc, nullptr, 0,
        reinterpret_cast<LPTHREAD_START_ROUTINE>(loadLib),
        remoteMem, 0, nullptr);
    if (!hThread) {
        printf("[ERROR] CreateRemoteThread failed (err %lu).\n", GetLastError());
        VirtualFreeEx(hProc, remoteMem, 0, MEM_RELEASE);
        CloseHandle(hProc);
        return false;
    }

    WaitForSingleObject(hThread, 10000);

    CloseHandle(hThread);
    VirtualFreeEx(hProc, remoteMem, 0, MEM_RELEASE);
    CloseHandle(hProc);
    return true;
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

int main() {
    printf("ALLIN1 Launcher - GTA V MP Vehicle Injector\n");
    printf("=============================================\n\n");

    // 0. Acquire SeDebugPrivilege (required for cross-process memory access).
    if (EnableDebugPrivilege()) {
        printf("[OK] Debug privilege enabled\n");
    } else {
        printf("[!!] Could not enable debug privilege.\n");
        printf("     Make sure you run this launcher as Administrator.\n\n");
    }

    // 1. Locate ALLIN1.dll next to this exe.
    char dllPath[MAX_PATH];
    if (!GetDllPath(dllPath, MAX_PATH)) {
        printf("[ERROR] %s not found next to this executable.\n", DLL_NAME);
        printf("Make sure ALLIN1-Launcher.exe and %s are in the GTA V folder.\n",
               DLL_NAME);
        printf("\nPress Enter to exit...");
        getchar();
        return 1;
    }
    printf("[OK] Found %s\n", dllPath);

    // 2. Check if game is already running, otherwise wait for the user to
    //    launch it.
    const char* detectedExe = nullptr;
    DWORD pid = FindGameProcess(&detectedExe);
    if (pid) {
        printf("[OK] %s already running (PID %lu)\n", detectedExe, pid);
    } else {
        printf("[..] Waiting for GTA V to start...\n");
        printf("     Launch GTA V now (through Steam or Rockstar Launcher).\n\n");

        int waited = 0;
        while (waited < POLL_TIMEOUT_SEC) {
            Sleep(POLL_INTERVAL_MS);
            waited++;
            if (waited % 10 == 0) {
                printf("[..] Still waiting... (%d/%d sec)\n",
                       waited, POLL_TIMEOUT_SEC);
            }
            pid = FindGameProcess(&detectedExe);
            if (pid) break;
        }

        if (!pid) {
            printf("[ERROR] GTA V did not start within %d seconds.\n",
                   POLL_TIMEOUT_SEC);
            printf("Start GTA V first, then run this launcher again.\n");
            printf("\nPress Enter to exit...");
            getchar();
            return 1;
        }
        printf("[OK] Detected %s (PID %lu)\n", detectedExe, pid);

        // Give the game a moment to initialise before injecting.
        printf("[..] Waiting for game to initialise...\n");
        Sleep(INIT_DELAY_MS);
    }

    // 3. Inject.
    printf("[..] Injecting %s into %s...\n", DLL_NAME, detectedExe);
    if (!InjectDLL(pid, dllPath)) {
        printf("\n[ERROR] Injection failed.\n");
        printf("Press Enter to exit...");
        getchar();
        return 1;
    }

    printf("[OK] %s injected successfully!\n", DLL_NAME);
    printf("\nMP vehicles are now active in Story Mode.\n");
    printf("You can close this window.\n");

    Sleep(3000);
    return 0;
}
