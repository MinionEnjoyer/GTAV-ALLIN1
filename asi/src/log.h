#pragma once
// Simple file logger for ALLIN1.asi diagnostics.
// Writes to ALLIN1/ALLIN1.log next to the game executable.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <Shlwapi.h>
#include <cstdio>
#include <cstdarg>

#pragma comment(lib, "shlwapi.lib")

inline FILE* g_logFile = nullptr;

inline void LogInit() {
    if (g_logFile) return;

    wchar_t exePath[MAX_PATH];
    GetModuleFileNameW(nullptr, exePath, MAX_PATH);
    PathRemoveFileSpecW(exePath);

    // Create the ALLIN1/ directory if it doesn't exist
    wchar_t dirPath[MAX_PATH];
    swprintf_s(dirPath, MAX_PATH, L"%s\\ALLIN1", exePath);
    CreateDirectoryW(dirPath, nullptr);

    wchar_t logPath[MAX_PATH];
    swprintf_s(logPath, MAX_PATH, L"%s\\ALLIN1\\ALLIN1.log", exePath);
    g_logFile = _wfopen(logPath, L"w");

    // Fall back to writing next to the game exe if subfolder fails
    if (!g_logFile) {
        swprintf_s(logPath, MAX_PATH, L"%s\\ALLIN1.log", exePath);
        g_logFile = _wfopen(logPath, L"w");
    }
}

inline void LogWrite(const char* fmt, ...) {
    if (!g_logFile) return;

    va_list args;
    va_start(args, fmt);
    vfprintf(g_logFile, fmt, args);
    va_end(args);

    fprintf(g_logFile, "\n");
    fflush(g_logFile);
}

inline void LogClose() {
    if (g_logFile) {
        fclose(g_logFile);
        g_logFile = nullptr;
    }
}
