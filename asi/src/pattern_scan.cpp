#include "pattern_scan.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <Psapi.h>
#include <cstring>

#pragma comment(lib, "psapi.lib")

uintptr_t FindPattern(const char* pattern, const char* mask,
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

uintptr_t FindPattern(const char* pattern, const char* mask) {
    MODULEINFO mod = {};
    GetModuleInformation(GetCurrentProcess(), GetModuleHandle(nullptr),
                         &mod, sizeof(mod));
    return FindPattern(pattern, mask,
                       reinterpret_cast<const char*>(mod.lpBaseOfDll),
                       mod.SizeOfImage);
}
