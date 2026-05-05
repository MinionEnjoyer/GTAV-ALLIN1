#pragma once
// Patches the GTA V shop_controller.ysc global variable that controls
// DLC vehicle despawning in Story Mode.  Sets the global to 1 so that
// MP/DLC vehicles injected via popgroups.ymt persist in ambient traffic.
//
// Call this AFTER the script engine has initialised (e.g. after a 5-second
// delay from DLL_PROCESS_ATTACH).

void PatchDespawnGlobal();
