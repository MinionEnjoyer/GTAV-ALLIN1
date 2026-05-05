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

static constexpr int   MAX_DRIVEN           = 20;      // Max driven vehicles we manage
static constexpr int   MAX_PARKED           = 10;      // Max parked vehicles we manage
static constexpr float SPAWN_DISTANCE_MIN   = 60.0f;   // Don't spawn closer than this
static constexpr float SPAWN_DISTANCE_MAX   = 180.0f;  // Don't spawn further than this
static constexpr float PARKED_DISTANCE_MIN  = 30.0f;   // Parked cars can be closer
static constexpr float PARKED_DISTANCE_MAX  = 120.0f;
static constexpr float CLEANUP_DISTANCE     = 350.0f;  // Release vehicles beyond this range
static constexpr int   DRIVEN_COOLDOWN_MS   = 5000;    // Ms between driven spawns
static constexpr int   PARKED_COOLDOWN_MS   = 3000;    // Ms between parked spawns
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
    Ped     driver;     // 0 for parked vehicles
    bool    parked;
};

static std::vector<Hash>           g_dlcModels;
static std::vector<SpawnedVehicle> g_spawned;
static int                         g_lastDrivenTime = 0;
static int                         g_lastParkedTime = 0;
static bool                        g_initialised    = false;
static int                         g_totalSpawned   = 0;

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
// Find a road node at a given distance range from the player
// ---------------------------------------------------------------------------

static bool FindRoadNode(Vector3 playerPos, float minDist, float maxDist,
                          Vector3* outPos, float* outHeading) {
    for (int attempt = 0; attempt < 10; attempt++) {
        float angle = (float)(MISC::GET_RANDOM_INT_IN_RANGE(0, 360)) * 3.14159f / 180.0f;
        float dist  = minDist +
                      (float)(MISC::GET_RANDOM_INT_IN_RANGE(0, 100)) / 100.0f *
                      (maxDist - minDist);

        float testX = playerPos.x + dist * cosf(angle);
        float testY = playerPos.y + dist * sinf(angle);
        float testZ = playerPos.z;

        if (PATHFIND::GET_CLOSEST_VEHICLE_NODE_WITH_HEADING(
                testX, testY, testZ, outPos, outHeading, 1, 3.0f, 0)) {
            float actualDist = MISC::GET_DISTANCE_BETWEEN_COORDS(
                playerPos.x, playerPos.y, playerPos.z,
                outPos->x, outPos->y, outPos->z, TRUE);
            if (actualDist >= minDist) {
                return true;
            }
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// Pick a random model and create a vehicle at the given position
// ---------------------------------------------------------------------------

static Vehicle CreateRandomDLCVehicle(Vector3 pos, float heading, Hash* outModel) {
    int idx = MISC::GET_RANDOM_INT_IN_RANGE(0, (int)g_dlcModels.size());
    Hash model = g_dlcModels[idx];

    if (!LoadModel(model)) {
        LogWrite("  Failed to load model 0x%08X", model);
        return 0;
    }

    Vehicle veh = VEHICLE::CREATE_VEHICLE(model, pos.x, pos.y, pos.z,
                                           heading, FALSE, FALSE, FALSE);
    if (veh == 0) {
        STREAMING::SET_MODEL_AS_NO_LONGER_NEEDED(model);
        return 0;
    }

    VEHICLE::SET_VEHICLE_ON_GROUND_PROPERLY(veh, 5.0f);

    // Random colour
    int colour1 = MISC::GET_RANDOM_INT_IN_RANGE(0, 160);
    int colour2 = MISC::GET_RANDOM_INT_IN_RANGE(0, 160);
    VEHICLE::SET_VEHICLE_COLOURS(veh, colour1, colour2);

    // MPBitset decorator — prevents despawning in Story Mode
    DECORATOR::DECOR_SET_INT(veh, "MPBitset", 0);

    STREAMING::SET_MODEL_AS_NO_LONGER_NEEDED(model);
    *outModel = model;
    return veh;
}

// ---------------------------------------------------------------------------
// Spawn a driven vehicle (with AI driver wandering)
// ---------------------------------------------------------------------------

static bool SpawnDrivenVehicle() {
    if (g_dlcModels.empty()) return false;

    Ped player = PLAYER::PLAYER_PED_ID();
    Vector3 playerPos = ENTITY::GET_ENTITY_COORDS(player, TRUE);

    Vector3 nodePos = {};
    float nodeHeading = 0.0f;
    if (!FindRoadNode(playerPos, SPAWN_DISTANCE_MIN, SPAWN_DISTANCE_MAX,
                       &nodePos, &nodeHeading))
        return false;

    Hash model = 0;
    Vehicle veh = CreateRandomDLCVehicle(nodePos, nodeHeading, &model);
    if (veh == 0) return false;

    VEHICLE::SET_VEHICLE_ENGINE_ON(veh, TRUE, TRUE, FALSE);

    // Create a random ped driver
    Ped driver = PED::CREATE_RANDOM_PED(nodePos.x, nodePos.y, nodePos.z);
    if (driver != 0) {
        PED::SET_PED_INTO_VEHICLE(driver, veh, -1);  // -1 = driver seat
        TASK::TASK_VEHICLE_DRIVE_WANDER(driver, veh, TRAFFIC_SPEED, DRIVING_STYLE);
    }

    // Mark as no longer needed by script so the game can clean up when far away
    ENTITY::SET_ENTITY_AS_NO_LONGER_NEEDED(&veh);
    if (driver != 0) {
        ENTITY::SET_ENTITY_AS_NO_LONGER_NEEDED(&driver);
    }

    g_spawned.push_back({ veh, model, driver, false });
    g_totalSpawned++;
    LogWrite("  Spawned DRIVEN vehicle #%d (model 0x%08X) at %.0f, %.0f, %.0f",
             g_totalSpawned, model, nodePos.x, nodePos.y, nodePos.z);
    return true;
}

// ---------------------------------------------------------------------------
// Spawn a parked vehicle (no driver, just sitting at a road node)
// ---------------------------------------------------------------------------

static bool SpawnParkedVehicle() {
    if (g_dlcModels.empty()) return false;

    Ped player = PLAYER::PLAYER_PED_ID();
    Vector3 playerPos = ENTITY::GET_ENTITY_COORDS(player, TRUE);

    Vector3 nodePos = {};
    float nodeHeading = 0.0f;
    if (!FindRoadNode(playerPos, PARKED_DISTANCE_MIN, PARKED_DISTANCE_MAX,
                       &nodePos, &nodeHeading))
        return false;

    // Offset the parked car slightly to the side of the road
    float sideOffset = 3.5f;
    float rad = nodeHeading * 3.14159f / 180.0f;
    nodePos.x += sideOffset * cosf(rad + 1.5708f);  // perpendicular offset
    nodePos.y += sideOffset * sinf(rad + 1.5708f);

    Hash model = 0;
    Vehicle veh = CreateRandomDLCVehicle(nodePos, nodeHeading, &model);
    if (veh == 0) return false;

    // Parked: engine off, handbrake on
    VEHICLE::SET_VEHICLE_ENGINE_ON(veh, FALSE, TRUE, TRUE);

    ENTITY::SET_ENTITY_AS_NO_LONGER_NEEDED(&veh);

    g_spawned.push_back({ veh, model, 0, true });
    g_totalSpawned++;
    LogWrite("  Spawned PARKED vehicle #%d (model 0x%08X) at %.0f, %.0f, %.0f",
             g_totalSpawned, model, nodePos.x, nodePos.y, nodePos.z);
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
// Count helpers
// ---------------------------------------------------------------------------

static int CountDriven() {
    int n = 0;
    for (auto& s : g_spawned) if (!s.parked) n++;
    return n;
}

static int CountParked() {
    int n = 0;
    for (auto& s : g_spawned) if (s.parked) n++;
    return n;
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

    int now = MISC::GET_GAME_TIMER();
    g_lastDrivenTime = now;
    g_lastParkedTime = now;
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

    int now = MISC::GET_GAME_TIMER();

    // Spawn driven vehicles
    if (now - g_lastDrivenTime >= DRIVEN_COOLDOWN_MS && CountDriven() < MAX_DRIVEN) {
        if (SpawnDrivenVehicle()) {
            g_lastDrivenTime = now;
        }
    }

    // Spawn parked vehicles
    if (now - g_lastParkedTime >= PARKED_COOLDOWN_MS && CountParked() < MAX_PARKED) {
        if (SpawnParkedVehicle()) {
            g_lastParkedTime = now;
        }
    }
}
