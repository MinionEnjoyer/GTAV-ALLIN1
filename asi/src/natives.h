// natives.h — Thin wrappers around GTA V native functions used by ALLIN1.
// Each wrapper calls invoke<>() from the ScriptHookV SDK nativeCaller.h.
// Native hashes sourced from https://nativedb.dotindustries.dev/
#pragma once

#include "../lib/ScriptHookV/inc/nativeCaller.h"
#include "../lib/ScriptHookV/inc/types.h"

// =============================================================================
// PLAYER
// =============================================================================

namespace PLAYER {
    static inline Ped PLAYER_PED_ID() {
        return invoke<Ped>(0xD80958FC74E988A6);
    }
    static inline Player PLAYER_ID() {
        return invoke<Player>(0x4F8644AF03D0E0D6);
    }
}

// =============================================================================
// PED
// =============================================================================

namespace PED {
    static inline BOOL IS_PED_IN_ANY_VEHICLE(Ped ped, BOOL atGetIn) {
        return invoke<BOOL>(0x997ABD671D25CA0B, ped, atGetIn);
    }
    static inline Ped CREATE_RANDOM_PED(float x, float y, float z) {
        return invoke<Ped>(0xB4AC7D0CF06BFE8F, x, y, z);
    }
    static inline void SET_PED_INTO_VEHICLE(Ped ped, Vehicle vehicle, int seatIndex) {
        invoke<Void>(0xF75B0D629E1C063D, ped, vehicle, seatIndex);
    }
    static inline void SET_PED_RANDOM_COMPONENT_VARIATION(Ped ped, int p1) {
        invoke<Void>(0xC8A9481A01E63C28, ped, p1);
    }
}

// =============================================================================
// VEHICLE
// =============================================================================

namespace VEHICLE {
    static inline Vehicle CREATE_VEHICLE(Hash modelHash, float x, float y, float z,
                                          float heading, BOOL isNetwork, BOOL bScriptHostVeh,
                                          BOOL p7) {
        return invoke<Vehicle>(0xAF35D0D2583051B0, modelHash, x, y, z,
                               heading, isNetwork, bScriptHostVeh, p7);
    }
    static inline void SET_VEHICLE_ON_GROUND_PROPERLY(Vehicle vehicle, float p1) {
        invoke<Void>(0x49733E92263139D1, vehicle, p1);
    }
    static inline void SET_VEHICLE_ENGINE_ON(Vehicle vehicle, BOOL value, BOOL instantly,
                                              BOOL disableAutoStart) {
        invoke<Void>(0x2497C4717C8B881E, vehicle, value, instantly, disableAutoStart);
    }
    static inline void SET_VEHICLE_COLOURS(Vehicle vehicle, int colourPrimary,
                                            int colourSecondary) {
        invoke<Void>(0x4F1D4BE3A7F24601, vehicle, colourPrimary, colourSecondary);
    }
    static inline void SET_VEHICLE_NUMBER_PLATE_TEXT(Vehicle vehicle, const char* text) {
        invoke<Void>(0x95A88F0B409CDA47, vehicle, text);
    }
    static inline int GET_NUM_VEHICLE_COLOURS(Vehicle vehicle) {
        return invoke<int>(0x3B3D65CD5DEAED59, vehicle);
    }
}

// =============================================================================
// STREAMING
// =============================================================================

namespace STREAMING {
    static inline void REQUEST_MODEL(Hash model) {
        invoke<Void>(0x963D27A58DF860AC, model);
    }
    static inline BOOL HAS_MODEL_LOADED(Hash model) {
        return invoke<BOOL>(0x98A4EB5D89A0C952, model);
    }
    static inline void SET_MODEL_AS_NO_LONGER_NEEDED(Hash model) {
        invoke<Void>(0xE532F5D78798DAAB, model);
    }
    static inline BOOL IS_MODEL_IN_CDIMAGE(Hash model) {
        return invoke<BOOL>(0x35B9E0803292B641, model);
    }
    static inline BOOL IS_MODEL_A_VEHICLE(Hash model) {
        return invoke<BOOL>(0xA0C09F3ED4B8CFE2, model);
    }
}

// =============================================================================
// ENTITY
// =============================================================================

namespace ENTITY {
    static inline Vector3 GET_ENTITY_COORDS(Entity entity, BOOL alive) {
        return invoke<Vector3>(0x3FEF770D40960D5A, entity, alive);
    }
    static inline float GET_ENTITY_HEADING(Entity entity) {
        return invoke<float>(0xE83D4F9BA2A85C7A, entity);
    }
    static inline BOOL DOES_ENTITY_EXIST(Entity entity) {
        return invoke<BOOL>(0x7239B21A38F536BA, entity);
    }
    static inline void SET_ENTITY_AS_NO_LONGER_NEEDED(Entity* entity) {
        invoke<Void>(0xB736A491E64A32CF, entity);
    }
    static inline void SET_ENTITY_AS_MISSION_ENTITY(Entity entity, BOOL p1, BOOL p2) {
        invoke<Void>(0xAD738C3085FE7E11, entity, p1, p2);
    }
    static inline BOOL IS_ENTITY_DEAD(Entity entity, BOOL p1) {
        return invoke<BOOL>(0x5F9532F3B5CC2551, entity, p1);
    }
    static inline float GET_ENTITY_SPEED(Entity entity) {
        return invoke<float>(0xD5037BA82E12416F, entity);
    }
}

// =============================================================================
// PATHFIND
// =============================================================================

namespace PATHFIND {
    // Gets the closest vehicle node to the given coordinates.
    // outPosition: receives the node position
    // outHeading: receives the node heading
    // nodeType: 1 = regular road node
    static inline BOOL GET_CLOSEST_VEHICLE_NODE_WITH_HEADING(
        float x, float y, float z,
        Vector3* outPosition, float* outHeading,
        int nodeType, float p6, int p7) {
        return invoke<BOOL>(0xFF071FB798B803B0,
            x, y, z, outPosition, outHeading, nodeType, p6, p7);
    }
    static inline BOOL GET_NTH_CLOSEST_VEHICLE_NODE(
        float x, float y, float z, int nthClosest,
        Vector3* outPosition, int unknown1, int unknown2, int unknown3) {
        return invoke<BOOL>(0xE50E52416CCF948B,
            x, y, z, nthClosest, outPosition, unknown1, unknown2, unknown3);
    }
}

// =============================================================================
// TASK
// =============================================================================

namespace TASK {
    // Makes a ped drive a vehicle and wander around.
    static inline void TASK_VEHICLE_DRIVE_WANDER(Ped ped, Vehicle vehicle,
                                                   float speed, int drivingStyle) {
        invoke<Void>(0x480142959D337D00, ped, vehicle, speed, drivingStyle);
    }
}

// =============================================================================
// DECORATOR (for despawn prevention)
// =============================================================================

namespace DECORATOR {
    static inline BOOL DECOR_REGISTER(const char* propertyName, int type) {
        return invoke<BOOL>(0x9FD90732F56403CE, propertyName, type);
    }
    static inline BOOL DECOR_SET_INT(Entity entity, const char* propertyName, int value) {
        return invoke<BOOL>(0x0CE3AA5E1CA19E10, entity, propertyName, value);
    }
    static inline int DECOR_GET_INT(Entity entity, const char* propertyName) {
        return invoke<int>(0xA06C969B02A97298, entity, propertyName);
    }
    static inline BOOL DECOR_EXIST_ON(Entity entity, const char* propertyName) {
        return invoke<BOOL>(0x05661B80A8C9165F, entity, propertyName);
    }
}

// =============================================================================
// GAMEPLAY / MISC
// =============================================================================

namespace MISC {
    static inline int GET_GAME_TIMER() {
        return invoke<int>(0x9CD27B0045628463);
    }
    static inline int GET_RANDOM_INT_IN_RANGE(int startRange, int endRange) {
        return invoke<int>(0xD53343AA4FB7DD28, startRange, endRange);
    }
    static inline float GET_DISTANCE_BETWEEN_COORDS(
        float x1, float y1, float z1,
        float x2, float y2, float z2,
        BOOL useZ) {
        return invoke<float>(0xF1B760881820C952, x1, y1, z1, x2, y2, z2, useZ);
    }
}

// =============================================================================
// GAMEPLAY HASH
// =============================================================================

namespace GAMEPLAY {
    static inline Hash GET_HASH_KEY(const char* string) {
        return invoke<Hash>(0xD24D37CC275948CC, string);
    }
}

// =============================================================================
// SCRIPT (for yield / wait)
// =============================================================================

namespace SCRIPT {
    // Not a native — use scriptWait() from the SDK directly.
}
