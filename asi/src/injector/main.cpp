// ALLIN1-Launcher — Inject ALLIN1.dll into GTA V at runtime.
//
// Bypasses BattlEye's proxy-DLL block by injecting after the game has
// started, using the standard CreateRemoteThread + LoadLibraryA technique.
//
// Usage: place next to ALLIN1.dll in the GTA V root and run it.
//        The launcher will start GTA V (via Steam) and inject the DLL.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <shlwapi.h>
#include <cstdio>
#include <cstring>

#pragma comment(lib, "shlwapi.lib")

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

static const char* DLL_NAME         = "ALLIN1.dll";
static const char* GAME_EXES[]      = { "GTA5.exe", "GTA5_Enhanced.exe" };
static const int   GAME_EXE_COUNT   = 2;
static const int   POLL_TIMEOUT_SEC = 60;
static const int   POLL_INTERVAL_MS = 1000;

// Steam App IDs
static const wchar_t* STEAM_URI_ENHANCED = L"steam://rungameid/3240220";
static const wchar_t* STEAM_URI_LEGACY   = L"steam://rungameid/271590";

// ---------------------------------------------------------------------------
// Helpers
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

/// Find any running GTA V process.  Returns the PID or 0.
static DWORD FindGameProcess() {
    for (int i = 0; i < GAME_EXE_COUNT; ++i) {
        DWORD pid = FindProcess(GAME_EXES[i]);
        if (pid) return pid;
    }
    return 0;
}

/// Check which edition is installed by looking for GTA5_Enhanced.exe next to
/// our own executable.
static bool IsEnhanced() {
    char path[MAX_PATH];
    GetModuleFileNameA(nullptr, path, MAX_PATH);
    PathRemoveFileSpecA(path);
    PathAppendA(path, "GTA5_Enhanced.exe");
    return GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES;
}

/// Build the full path to ALLIN1.dll (same directory as this exe).
static bool GetDllPath(char* out, DWORD size) {
    if (!GetModuleFileNameA(nullptr, out, size)) return false;
    PathRemoveFileSpecA(out);
    PathAppendA(out, DLL_NAME);
    return GetFileAttributesA(out) != INVALID_FILE_ATTRIBUTES;
}

/// Inject a DLL into a target process.  Returns true on success.
static bool InjectDLL(DWORD pid, const char* dllPath) {
    HANDLE hProc = OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
        PROCESS_VM_OPERATION  | PROCESS_VM_WRITE | PROCESS_VM_READ,
        FALSE, pid);
    if (!hProc) {
        printf("[ERROR] OpenProcess failed (err %lu). Try running as admin.\n",
               GetLastError());
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
        printf("[ERROR] CreateRemoteThread failed (err %lu). "
               "Try running as admin.\n", GetLastError());
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
    printf("ALLIN1 Launcher — GTA V MP Vehicle Injector\n");
    printf("=============================================\n\n");

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

    // 2. Check if game is already running.
    DWORD pid = FindGameProcess();
    if (pid) {
        printf("[OK] GTA V already running (PID %lu)\n", pid);
    } else {
        // Launch via Steam.
        bool enhanced = IsEnhanced();
        const wchar_t* uri = enhanced ? STEAM_URI_ENHANCED : STEAM_URI_LEGACY;
        printf("[..] Launching GTA V %s via Steam...\n",
               enhanced ? "Enhanced" : "Legacy");
        ShellExecuteW(nullptr, L"open", uri, nullptr, nullptr, SW_SHOWNORMAL);

        // 3. Wait for the game process to appear.
        printf("[..] Waiting for GTA V to start");
        int waited = 0;
        while (waited < POLL_TIMEOUT_SEC) {
            Sleep(POLL_INTERVAL_MS);
            waited++;
            printf(".");
            pid = FindGameProcess();
            if (pid) break;
        }
        printf("\n");

        if (!pid) {
            printf("[ERROR] GTA V did not start within %d seconds.\n",
                   POLL_TIMEOUT_SEC);
            printf("Launch the game manually, then run this launcher again.\n");
            printf("\nPress Enter to exit...");
            getchar();
            return 1;
        }
        printf("[OK] GTA V started (PID %lu)\n", pid);

        // Give the game a moment to initialise before injecting.
        printf("[..] Waiting for game to initialise...\n");
        Sleep(5000);
    }

    // 4. Inject.
    printf("[..] Injecting %s...\n", DLL_NAME);
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
