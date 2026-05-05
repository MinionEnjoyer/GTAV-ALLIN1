/*
	THIS FILE IS A PART OF GTA V SCRIPT HOOK SDK
				http://dev-c.com
			(C) Alexander Blade 2015-2024

	Runtime-linked header for ScriptHookV.dll.
	All functions are resolved via GetProcAddress at startup so the ASI
	has no hard import dependency on ScriptHookV.dll.
*/

#pragma once

#include <windows.h>

// ---------------------------------------------------------------------------
// Function pointer types
// ---------------------------------------------------------------------------

typedef void  (*T_scriptWait)(DWORD time);
typedef void  (*T_scriptRegister)(HMODULE module, void(*)());
typedef void  (*T_scriptRegisterAdditionalThread)(HMODULE module, void(*)());
typedef void  (*T_scriptUnregister)(HMODULE module);
typedef void  (*T_nativeInit)(UINT64 hash);
typedef void  (*T_nativePush64)(UINT64 val);
typedef PUINT64 (*T_nativeCall)();
typedef UINT64* (*T_getGlobalPtr)(int globalId);
typedef int   (*T_worldGetAllVehicles)(int* arr, int arrSize);
typedef int   (*T_worldGetAllPeds)(int* arr, int arrSize);
typedef int   (*T_worldGetAllObjects)(int* arr, int arrSize);
typedef int   (*T_worldGetAllPickups)(int* arr, int arrSize);

typedef void(*KeyboardHandler)(DWORD key, WORD repeats, BYTE scanCode,
    BOOL isExtended, BOOL isWithAlt, BOOL wasDownBefore, BOOL isUpNow);

typedef void  (*T_keyboardHandlerRegister)(KeyboardHandler handler);
typedef void  (*T_keyboardHandlerUnregister)(KeyboardHandler handler);

typedef void(*PresentCallback)(void*);

typedef void  (*T_presentCallbackRegister)(PresentCallback cb);
typedef void  (*T_presentCallbackUnregister)(PresentCallback cb);
typedef int   (*T_createTexture)(const char* texFileName);
typedef void  (*T_drawTexture)(int id, int index, int level, int time,
    float sizeX, float sizeY, float centerX, float centerY,
    float posX, float posY, float rotation, float screenHeightScaleFactor,
    float r, float g, float b, float a);
typedef int   (*T_getGameVersion)();
typedef BYTE* (*T_getScriptHandleBaseAddress)(int handle);

// ---------------------------------------------------------------------------
// Global function pointers (defined in shv_runtime.cpp)
// ---------------------------------------------------------------------------

extern T_scriptWait                     p_scriptWait;
extern T_scriptRegister                 p_scriptRegister;
extern T_scriptRegisterAdditionalThread p_scriptRegisterAdditionalThread;
extern T_scriptUnregister               p_scriptUnregister;
extern T_nativeInit                     p_nativeInit;
extern T_nativePush64                   p_nativePush64;
extern T_nativeCall                     p_nativeCall;
extern T_getGlobalPtr                   p_getGlobalPtr;

// ---------------------------------------------------------------------------
// Resolve all function pointers. Returns true if all required functions found.
// ---------------------------------------------------------------------------

bool SHV_Init();

// ---------------------------------------------------------------------------
// Inline wrappers — same names as the import-linked SDK so call sites
// (nativeCaller.h, natives.h, main.cpp) don't need any changes.
// ---------------------------------------------------------------------------

inline void    scriptWait(DWORD time)                               { p_scriptWait(time); }
inline void    scriptRegister(HMODULE m, void(*f)())                { p_scriptRegister(m, f); }
inline void    scriptRegisterAdditionalThread(HMODULE m, void(*f)()){ p_scriptRegisterAdditionalThread(m, f); }
inline void    scriptUnregister(HMODULE m)                          { p_scriptUnregister(m); }
inline void    nativeInit(UINT64 hash)                              { p_nativeInit(hash); }
inline void    nativePush64(UINT64 val)                             { p_nativePush64(val); }
inline PUINT64 nativeCall()                                         { return p_nativeCall(); }
inline UINT64* getGlobalPtr(int globalId)                           { return p_getGlobalPtr(globalId); }

// ---------------------------------------------------------------------------
// Convenience helpers
// ---------------------------------------------------------------------------

static inline void WAIT(DWORD time) { scriptWait(time); }
static inline void TERMINATE() { scriptWait(MAXDWORD); }
