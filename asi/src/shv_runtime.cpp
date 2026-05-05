// shv_runtime.cpp — Runtime resolution of ScriptHookV.dll exports.
//
// Instead of linking against ScriptHookV.lib (which creates a hard
// import dependency), we load all functions via GetProcAddress at
// runtime.  This lets the ASI loader load our plugin even before
// ScriptHookV.dll's full initialisation sequence completes.

#include "../lib/ScriptHookV/inc/main.h"
#include "log.h"

// ---------------------------------------------------------------------------
// Function pointer storage
// ---------------------------------------------------------------------------

T_scriptWait                     p_scriptWait                     = nullptr;
T_scriptRegister                 p_scriptRegister                 = nullptr;
T_scriptRegisterAdditionalThread p_scriptRegisterAdditionalThread = nullptr;
T_scriptUnregister               p_scriptUnregister               = nullptr;
T_nativeInit                     p_nativeInit                     = nullptr;
T_nativePush64                   p_nativePush64                   = nullptr;
T_nativeCall                     p_nativeCall                     = nullptr;
T_getGlobalPtr                   p_getGlobalPtr                   = nullptr;

// ---------------------------------------------------------------------------
// Resolution helper
// ---------------------------------------------------------------------------

template <typename T>
static bool Resolve(HMODULE mod, const char* name, T& out) {
    out = reinterpret_cast<T>(GetProcAddress(mod, name));
    if (!out) {
        LogWrite("  SHV_Init: MISSING export '%s'", name);
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Public init
// ---------------------------------------------------------------------------

bool SHV_Init() {
    HMODULE shv = GetModuleHandleA("ScriptHookV.dll");
    if (!shv) {
        LogWrite("SHV_Init: ScriptHookV.dll not loaded — cannot resolve exports");
        return false;
    }
    LogWrite("SHV_Init: ScriptHookV.dll found at 0x%p", shv);

    bool ok = true;
    ok &= Resolve(shv, "scriptWait",                     p_scriptWait);
    ok &= Resolve(shv, "scriptRegister",                 p_scriptRegister);
    ok &= Resolve(shv, "scriptRegisterAdditionalThread", p_scriptRegisterAdditionalThread);
    ok &= Resolve(shv, "scriptUnregister",               p_scriptUnregister);
    ok &= Resolve(shv, "nativeInit",                     p_nativeInit);
    ok &= Resolve(shv, "nativePush64",                   p_nativePush64);
    ok &= Resolve(shv, "nativeCall",                     p_nativeCall);
    ok &= Resolve(shv, "getGlobalPtr",                   p_getGlobalPtr);

    if (ok) {
        LogWrite("SHV_Init: all exports resolved successfully");
    } else {
        LogWrite("SHV_Init: FAILED — some exports missing");
    }
    return ok;
}
