#pragma once

// Initialise the vehicle spawner (called once from ScriptMain before the loop).
void SpawnerInit();

// Called every tick from the script fibre. Handles spawning & cleanup.
void SpawnerTick();
