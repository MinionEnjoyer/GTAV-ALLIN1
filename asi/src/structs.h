#pragma once
// GTA V script engine structures.
// These mirror the in-memory layout used by the RAGE engine's script VM.
// Padding fields are required to match the exact binary offsets.
// Sourced from community reverse-engineering efforts (public knowledge).

#include <cstdint>
#include <cstddef>

struct ScriptHeader {
    char padding1[16];                  // 0x00
    unsigned char** codeBlocksOffset;   // 0x10
    char padding2[4];                   // 0x18
    int codeLength;                     // 0x1C
    char padding3[4];                   // 0x20
    int localCount;                     // 0x24
    char padding4[4];                   // 0x28
    int nativeCount;                    // 0x2C
    int64_t* localOffset;              // 0x30
    char padding5[8];                   // 0x38
    int64_t* nativeOffset;             // 0x40
    char padding6[16];                  // 0x48
    int nameHash;                       // 0x58
    char padding7[4];                   // 0x5C
    char* name;                         // 0x60
    char** stringsOffset;               // 0x68
    int stringSize;                     // 0x70
    char padding8[12];                  // 0x74
    // END_OF_HEADER                    // 0x80  (total size = 128 bytes)

    bool IsValid() const { return codeLength > 0; }

    int CodePageCount() const {
        return (codeLength + 0x3FFF) >> 14;
    }

    int GetCodePageSize(int page) const {
        if (page < 0 || page >= CodePageCount()) return 0;
        return (page == CodePageCount() - 1) ? (codeLength & 0x3FFF) : 0x4000;
    }

    unsigned char* GetCodePageAddress(int page) const {
        return codeBlocksOffset[page];
    }

    unsigned char* GetCodePositionAddress(int codePosition) const {
        if (codePosition < 0 || codePosition >= codeLength) return nullptr;
        return &codeBlocksOffset[codePosition >> 14][codePosition & 0x3FFF];
    }

    char* GetString(int stringPosition) const {
        if (stringPosition < 0 || stringPosition >= stringSize) return nullptr;
        return &stringsOffset[stringPosition >> 14][stringPosition & 0x3FFF];
    }
};

struct ScriptTableItem {
    ScriptHeader* header;
    char padding[4];
    int hash;

    bool IsLoaded() const { return header != nullptr; }
};

struct ScriptTable {
    ScriptTableItem* TablePtr;
    char padding[16];
    int count;

    ScriptTableItem* FindScript(int hash) {
        if (TablePtr == nullptr) return nullptr;
        for (int i = 0; i < count; i++) {
            if (TablePtr[i].hash == hash) return &TablePtr[i];
        }
        return nullptr;
    }
};

struct GlobalTable {
    int64_t** GlobalBasePtr;

    int64_t* AddressOf(int index) const {
        return &GlobalBasePtr[(index >> 18) & 0x3F][index & 0x3FFFF];
    }

    bool IsInitialised() const {
        return *GlobalBasePtr != nullptr;
    }
};
