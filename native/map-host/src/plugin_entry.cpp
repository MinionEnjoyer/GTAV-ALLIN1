// Safe ScriptHookV loading scaffold.
//
// This file intentionally does not invoke a content-change-set native.
// Alloc8or's Legacy and Gen9 databases confirm the canonical execute/revert
// signatures, but both operate globally by group hash rather than within one
// verified pack. Wiring them before a registered-pack isolation canary would
// violate the host's fail-closed contract.

#include "allin1/map_host.hpp"
#include "main.h"

#include <windows.h>

namespace {

using namespace allin1::maps;

class DebugLogger final : public ILogger {
public:
    void Write(const LogEvent& event) noexcept override {
        const std::string message =
            "ALLIN1 MapHost [" + event.code + "] " + event.detail + "\n";
        OutputDebugStringA(message.c_str());
    }
};

class UnwiredBackend final : public IMapGroupBackend {
public:
    bool Acquire(const AllowedGroup&, std::string& error) noexcept override {
        error = "global content-change-set ABI is deliberately unwired";
        return false;
    }
    bool Release(const AllowedGroup&, std::string& error) noexcept override {
        error = "global content-change-set ABI is deliberately unwired";
        return false;
    }
};

#if defined(ALLIN1_MAP_HOST_EDITION_ENHANCED)
constexpr Edition kEdition = Edition::Enhanced;
#else
constexpr Edition kEdition = Edition::Legacy;
#endif

DebugLogger g_logger;
UnwiredBackend g_backend;
// HostOptions defaults to disabled. No receipt is loaded and no map group is
// touched during process attach or ScriptMain startup.
MapHost g_host(kEdition, g_backend, g_logger);

void ScriptMain() {
    g_logger.Write({LogLevel::Info, "map_host_scaffold_loaded", kEdition, {},
                    {}, 0,
                    "disabled policy scaffold loaded; activation ABI unwired"});
    while (true) WAIT(1000);
}

}  // namespace

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) scriptRegister(module, ScriptMain);
    // Never perform lease cleanup under the Windows loader lock. A future
    // wired backend must call MapHost::Shutdown from its ScriptHook thread
    // before unregistering. This scaffold cannot acquire a lease.
    if (reason == DLL_PROCESS_DETACH) scriptUnregister(module);
    return TRUE;
}
