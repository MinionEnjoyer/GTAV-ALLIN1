cmake_minimum_required(VERSION 3.15)
project(ALLIN1_ASI LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# ScriptHookV import library
# ---------------------------------------------------------------------------
# Real ScriptHookV.lib from the SDK (contains C++ mangled symbols).

set(SHV_LIB "${CMAKE_CURRENT_SOURCE_DIR}/lib/ScriptHookV/ScriptHookV.lib"
    CACHE FILEPATH "Path to ScriptHookV import library")

# ---------------------------------------------------------------------------
# ALLIN1 ASI plugin
# ---------------------------------------------------------------------------

add_library(ALLIN1 SHARED
    src/main.cpp
    src/log.h
    src/natives.h
    src/vehicle_models.h
    src/vehicle_spawner.h
    src/vehicle_spawner.cpp
)

target_include_directories(ALLIN1 PRIVATE
    lib/ScriptHookV/inc
)

# Output as .asi — ScriptHookV loads these from the game directory
set_target_properties(ALLIN1 PROPERTIES
    SUFFIX ".asi"
    PREFIX ""
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

# Link ScriptHookV import lib + system libraries
target_link_libraries(ALLIN1 PRIVATE
    "${SHV_LIB}"
    shlwapi
)

# Release optimizations
if(MSVC)
    target_compile_options(ALLIN1 PRIVATE
        $<$<CONFIG:Release>:/O2 /GL>
    )
    target_link_options(ALLIN1 PRIVATE
        $<$<CONFIG:Release>:/LTCG>
    )
endif()
