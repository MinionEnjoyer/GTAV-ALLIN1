#pragma once
// Byte pattern scanner for GTA V memory.
// Scans the main module (GTA5.exe) or a specific memory region for a byte
// pattern with wildcard mask support.

#include <cstdint>
#include <cstddef>

// Scan a specific memory region for a pattern.
// mask: 'x' = must match, '?' = wildcard.
// Returns address of the first match, or 0 if not found.
uintptr_t FindPattern(const char* pattern, const char* mask,
                      const char* start, size_t size);

// Scan the entire main module (GTA5.exe) for a pattern.
uintptr_t FindPattern(const char* pattern, const char* mask);
