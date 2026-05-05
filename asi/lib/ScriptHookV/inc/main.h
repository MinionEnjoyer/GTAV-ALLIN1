/*
	THIS FILE IS A PART OF GTA V SCRIPT HOOK SDK
				http://dev-c.com
			(C) Alexander Blade 2015-2024

	Minimal header for linking against ScriptHookV.dll at runtime.
	The user must install ScriptHookV separately (from dev-c.com).
*/

#pragma once

#include <windows.h>

// ScriptHookV exports — resolved at load time via ScriptHookV.lib
#define SHV_IMPORT extern "C" __declspec(dllimport)

/* ---- Script fibre management ---- */

SHV_IMPORT void scriptWait(DWORD time);
SHV_IMPORT void scriptRegister(HMODULE module, void(*LP_SCRIPT_MAIN)());
SHV_IMPORT void scriptRegisterAdditionalThread(HMODULE module, void(*LP_SCRIPT_MAIN)());
SHV_IMPORT void scriptUnregister(HMODULE module);

/* ---- Native function invocation ---- */

SHV_IMPORT void   nativeInit(UINT64 hash);
SHV_IMPORT void   nativePush64(UINT64 val);
SHV_IMPORT PUINT64 nativeCall();

/* ---- Game globals ---- */

SHV_IMPORT UINT64* getGlobalPtr(int globalId);

/* ---- World entity enumeration ---- */

SHV_IMPORT int worldGetAllVehicles(int* arr, int arrSize);
SHV_IMPORT int worldGetAllPeds(int* arr, int arrSize);
SHV_IMPORT int worldGetAllObjects(int* arr, int arrSize);
SHV_IMPORT int worldGetAllPickups(int* arr, int arrSize);

/* ---- Input ---- */

typedef void(*KeyboardHandler)(DWORD key, WORD repeats, BYTE scanCode,
    BOOL isExtended, BOOL isWithAlt, BOOL wasDownBefore, BOOL isUpNow);

SHV_IMPORT void keyboardHandlerRegister(KeyboardHandler handler);
SHV_IMPORT void keyboardHandlerUnregister(KeyboardHandler handler);

/* ---- Rendering ---- */

typedef void(*PresentCallback)(void*);

SHV_IMPORT void presentCallbackRegister(PresentCallback cb);
SHV_IMPORT void presentCallbackUnregister(PresentCallback cb);

/* ---- Textures ---- */

SHV_IMPORT int  createTexture(const char* texFileName);
SHV_IMPORT void drawTexture(int id, int index, int level, int time,
    float sizeX, float sizeY, float centerX, float centerY,
    float posX, float posY, float rotation, float screenHeightScaleFactor,
    float r, float g, float b, float a);

/* ---- Misc ---- */

SHV_IMPORT int  getGameVersion();
SHV_IMPORT BYTE* getScriptHandleBaseAddress(int handle);

/* ---- Convenience helpers ---- */

static inline void WAIT(DWORD time) { scriptWait(time); }
static inline void TERMINATE() { scriptWait(MAXDWORD); }
