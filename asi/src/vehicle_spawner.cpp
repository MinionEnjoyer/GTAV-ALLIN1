// vehicle_spawner.cpp — Spawns GTA Online DLC vehicles into Story Mode traffic.
//
// Instead of replacing game data files (popgroups.ymt, dlclist.xml, etc.)
// and hooking the RAGE filesystem, this approach uses ScriptHookV's native
// API to directly spawn vehicles at nearby road nodes.
//
// The "MPBitset" decorator prevents the game's shop_controller.ysc script
// from despawning DLC vehicles in single player.

#include "vehicle_spawner.h"
#include "natives.h"
#include "log.h"

#include <vector>
#include <algorithm>
#include <cmath>

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

static constexpr int   MAX_SPAWNED          = 15;   // Max vehicles we manage at once
static constexpr float SPAWN_DISTANCE_MIN   = 80.0f;  // Don't spawn closer than this
static constexpr float SPAWN_DISTANCE_MAX   = 200.0f; // Don't spawn further than this
static constexpr float CLEANUP_DISTANCE     = 300.0f;  // Release vehicles beyond this range
static constexpr int   SPAWN_COOLDOWN_MS    = 8000;    // Min ms between spawn attempts
static constexpr int   MODEL_LOAD_TIMEOUT   = 5000;    // Max ms to wait for model load
static constexpr int   DECORATOR_TYPE_INT   = 3;       // Decorator type enum for int

// Driving style: normal traffic behaviour
// 786603 = stop at lights, avoid vehicles, avoid empty vehicles, avoid peds,
//          avoid objects, stop at destination, use shortest path
static constexpr int   DRIVING_STYLE        = 786603;
static constexpr float TRAFFIC_SPEED        = 20.0f;   // m/s (~72 km/h)

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

struct SpawnedVehicle {
    Vehicle handle;
    Hash    model;
    Ped     driver;
};

static std::vector<Hash>           g_dlcModels;
static std::vector<SpawnedVehicle> g_spawned;
static int                         g_lastSpawnTime = 0;
static bool                        g_initialised   = false;

// ---------------------------------------------------------------------------
// DLC vehicle discovery
// ---------------------------------------------------------------------------

static void BuildVehicleList() {
    g_dlcModels.clear();

    int count = DLC::GET_NUM_DLC_VEHICLES();
    LogWrite("  DLC vehicle count from native: %d", count);

    for (int i = 0; i < count; i++) {
        Hash model = DLC::GET_DLC_VEHICLE_MODEL(i);
        if (model != 0) {
            // Verify it's actually a loadable vehicle model
            if (STREAMING::IS_MODEL_IN_CDIMAGE(model) &&
                STREAMING::IS_MODEL_A_VEHICLE(model)) {
                g_dlcModels.push_back(model);
            }
        }
    }

    LogWrite("  Valid DLC vehicle models: %d", (int)g_dlcModels.size());
}

// ---------------------------------------------------------------------------
// Model loading helpers
// ---------------------------------------------------------------------------

static bool LoadModel(Hash model) {
    if (STREAMING::HAS_MODEL_LOADED(model))
        return true;

    STREAMING::REQUEST_MODEL(model);

    int start = MISC::GET_GAME_TIMER();
    while (!STREAMING::HAS_MODEL_LOADED(model)) {
        if (MISC::GET_GAME_TIMER() - start > MODEL_LOAD_TIMEOUT)
            return false;
        scriptWait(0);
    }
    return true;
}

// ---------------------------------------------------------------------------
// Spawn a single vehicle at a nearby road node
// ---------------------------------------------------------------------------

static bool SpawnOneVehicle() {
    if (g_dlcModels.empty())
        return false;

    Ped player = PLAYER::PLAYER_PED_ID();
    Vector3 playerPos = ENTITY::GET_ENTITY_COORDS(player, TRUE);

    // Pick a random road node 80-200m away from the player.
    // Try several random offsets to find a valid node.
    Vector3 nodePos = {};
    float nodeHeading = 0.0f;
    bool foundNode = false;

    for (int attempt = 0; attempt < 10; attempt++) {
        float angle = (float)(MISC::GET_RANDOM_INT_IN_RANGE(0, 360)) * 3.14159f / 180.0f;
        float dist  = SPAWN_DISTANCE_MIN +
                      (float)(MISC::GET_RANDOM_INT_IN_RANGE(0, 100)) / 100.0f *
                      (SPAWN_DISTANCE_MAX - SPAWN_DISTANCE_MIN);

        float testX = playerPos.x + dist * cosf(angle);
        float testY = playerPos.y + dist * sinf(angle);
        float testZ = playerPos.z;

        if (PATHFIND::GET_CLOSEST_VEHICLE_NODE_WITH_HEADING(
                testX, testY, testZ, &nodePos, &nodeHeading, 1, 3.0f, 0)) {
            // Verify the node isn't too close to the player
            float actualDist = MISC::GET_DISTANCE_BETWEEN_COORDS(
                playerPos.x, playerPos.y, playerPos.z,
                nodePos.x, nodePos.y, nodePos.z, TRUE);
            if (actualDist >= SPAWN_DISTANCE_MIN) {
                foundNode = true;
                break;
            }
        }
    }

    if (!foundNode)
        return false;

    // Pick a random DLC vehicle
    int idx = MISC::GET_RANDOM_INT_IN_RANGE(0, (int)g_dlcModels.size());
    Hash model = g_dlcModels[idx];

    // Load the model
    if (!LoadModel(model)) {
        LogWrite("  Failed to load model 0x%08X", model);
        return false;
    }

    // Create the vehicle
    Vehicle veh = VEHICLE::CREATE_VEHICLE(model, nodePos.x, nodePos.y, nodePos.z,
                                           nodeHeading, FALSE, FALSE, FALSE);
    if (veh == 0) {
        STREAMING::SET_MODEL_AS_NO_LONGER_NEEDED(model);
        return false;
    }

    VEHICLE::SET_VEHICLE_ON_GROUND_PROPERLY(veh, 5.0f);
    VEHICLE::SET_VEHICLE_ENGINE_ON(veh, TRUE, TRUE, FALSE);

    // Random colour from the vehicle's valid colour range
    int colour1 = MISC::GET_RANDOM_INT_IN_RANGE(0, 160);
    int colour2 = MISC::GET_RANDOM_INT_IN_RANGE(0, 160);
    VEHICLE::SET_VEHICLE_COLOURS(veh, colour1, colour2);

    // Set the MPBitset decorator — this prevents shop_controller.ysc from
    // despawning the vehicle in Story Mode.
    DECORATOR::DECOR_SET_INT(veh, "MPBitset", 0);

    // Create a random ped driver
    Ped driver = PED::CREATE_RANDOM_PED(nodePos.x, nodePos.y, nodePos.z);
    if (driver != 0) {
        PED::SET_PED_INTO_VEHICLE(driver, veh, -1);  // -1 = driver seat
        TASK::TASK_VEHICLE_DRIVE_WANDER(driver, veh, TRAFFIC_SPEED, DRIVING_STYLE);
    }

    // Release the model from streaming (vehicle is already created)
    STREAMING::SET_MODEL_AS_NO_LONGER_NEEDED(model);

    // Mark as no longer needed by script so the game can clean up when far away
    ENTITY::SET_ENTITY_AS_NO_LONGER_NEEDED(&veh);
    if (driver != 0) {
        ENTITY::SET_ENTITY_AS_NO_LONGER_NEEDED(&driver);
    }

    // Track it
    g_spawned.push_back({ veh, model, driver });

    return true;
}

// ---------------------------------------------------------------------------
// Remove vehicles that no longer exist or are far away
// ---------------------------------------------------------------------------

static void CleanupVehicles() {
    Ped player = PLAYER::PLAYER_PED_ID();
    Vector3 playerPos = ENTITY::GET_ENTITY_COORDS(player, TRUE);

    auto it = g_spawned.begin();
    while (it != g_spawned.end()) {
        bool remove = false;

        if (!ENTITY::DOES_ENTITY_EXIST(it->handle)) {
            remove = true;
        } else {
            Vector3 vehPos = ENTITY::GET_ENTITY_COORDS(it->handle, TRUE);
            float dist = MISC::GET_DISTANCE_BETWEEN_COORDS(
                playerPos.x, playerPos.y, playerPos.z,
                vehPos.x, vehPos.y, vehPos.z, TRUE);
            if (dist > CLEANUP_DISTANCE) {
                remove = true;
            }
        }

        if (remove) {
            it = g_spawned.erase(it);
        } else {
            ++it;
        }
    }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

void SpawnerInit() {
    if (g_initialised)
        return;

    LogWrite("SpawnerInit: building vehicle list...");

    // Register the MPBitset decorator so we can use it
    DECORATOR::DECOR_REGISTER("MPBitset", DECORATOR_TYPE_INT);

    BuildVehicleList();

    g_lastSpawnTime = MISC::GET_GAME_TIMER();
    g_initialised = true;

    LogWrite("SpawnerInit: complete, %d DLC models available", (int)g_dlcModels.size());
}

void SpawnerTick() {
    if (!g_initialised)
        return;

    // Rebuild vehicle list if it was empty (DLC might not have been loaded yet
    // at init time).
    if (g_dlcModels.empty()) {
        BuildVehicleList();
        if (g_dlcModels.empty())
            return;
    }

    // Cleanup stale entries
    CleanupVehicles();

    // Check spawn cooldown
    int now = MISC::GET_GAME_TIMER();
    if (now - g_lastSpawnTime < SPAWN_COOLDOWN_MS)
        return;

    // Don't exceed our vehicle cap
    if ((int)g_spawned.size() >= MAX_SPAWNED)
        return;

    // Only spawn when the player is in a vehicle (driving around),
    // so we don't clutter the area when on foot.
    Ped player = PLAYER::PLAYER_PED_ID();
    if (!PED::IS_PED_IN_ANY_VEHICLE(player, FALSE))
        return;

    if (SpawnOneVehicle()) {
        g_lastSpawnTime = now;
    }
}
