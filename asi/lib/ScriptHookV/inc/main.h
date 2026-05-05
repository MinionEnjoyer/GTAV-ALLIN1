/*
	THIS FILE IS A PART OF GTA V SCRIPT HOOK SDK
				http://dev-c.com
			(C) Alexander Blade 2015-2024
*/

#pragma once

#include <windows.h>

#define IMPORT extern "C" __declspec(dllimport)

/* ---- Script management ---- */

IMPORT void scriptWait(DWORD time);
IMPORT void scriptRegister(HMODULE module, void(*LP_SCRIPT_MAIN)());
IMPORT void scriptRegisterAdditionalThread(HMODULE module, void(*LP_SCRIPT_MAIN)());
IMPORT void scriptUnregister(HMODULE module);

/* ---- Native invocation ---- */

IMPORT void    nativeInit(UINT64 hash);
IMPORT void    nativePush64(UINT64 val);
IMPORT PUINT64 nativeCall();

/* ---- Globals ---- */

IMPORT UINT64* getGlobalPtr(int globalId);

/* ---- World enumeration ---- */

IMPORT int worldGetAllVehicles(int* arr, int arrSize);
IMPORT int worldGetAllPeds(int* arr, int arrSize);
IMPORT int worldGetAllObjects(int* arr, int arrSize);
IMPORT int worldGetAllPickups(int* arr, int arrSize);

/* ---- Input ---- */

typedef void(*KeyboardHandler)(DWORD, WORD, BYTE, BOOL, BOOL, BOOL, BOOL);

IMPORT void keyboardHandlerRegister(KeyboardHandler handler);
IMPORT void keyboardHandlerUnregister(KeyboardHandler handler);

/* ---- Present callbacks ---- */

typedef void(*PresentCallback)(void*);

IMPORT void presentCallbackRegister(PresentCallback cb);
IMPORT void presentCallbackUnregister(PresentCallback cb);

/* ---- Textures ---- */

IMPORT int  createTexture(const char* texFileName);
IMPORT void drawTexture(int id, int index, int level, int time,
    float sizeX, float sizeY, float centerX, float centerY,
    float posX, float posY, float rotation, float screenHeightScaleFactor,
    float r, float g, float b, float a);

/* ---- Misc ---- */

IMPORT int   getGameVersion();
IMPORT BYTE* getScriptHandleBaseAddress(int handle);

/* ---- Convenience ---- */

static void WAIT(DWORD time) { scriptWait(time); }
static void TERMINATE() { WAIT(MAXDWORD); }
