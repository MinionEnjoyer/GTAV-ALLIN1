cmake_minimum_required(VERSION 3.15)
project(ALLIN1_ASI LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MinHook sources (vendored, BSD-2-Clause)
set(MINHOOK_SOURCES
    lib/MinHook/src/hook.c
    lib/MinHook/src/trampoline.c
    lib/MinHook/src/buffer.c
    lib/MinHook/src/hde/hde64.c
)

add_library(ALLIN1 SHARED
    src/main.cpp
    src/structs.h
    src/pattern_scan.h
    src/pattern_scan.cpp
    src/despawn_fix.h
    src/despawn_fix.cpp
    src/file_redirect.h
    src/file_redirect.cpp
    ${MINHOOK_SOURCES}
)

target_include_directories(ALLIN1 PRIVATE
    lib/MinHook/include
)

# Output as .asi — ScriptHookV loads these from the game directory
set_target_properties(ALLIN1 PROPERTIES
    SUFFIX ".asi"
    PREFIX ""
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

# Link system libraries
target_link_libraries(ALLIN1 PRIVATE psapi shlwapi)

# Release optimizations
if(MSVC)
    target_compile_options(ALLIN1 PRIVATE
        $<$<CONFIG:Release>:/O2 /GL>
    )
    target_link_options(ALLIN1 PRIVATE
        $<$<CONFIG:Release>:/LTCG>
    )
endif()
