cmake_minimum_required(VERSION 3.15)
project(ALLIN1 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# ALLIN1.dll — the plugin (injected into GTA V at runtime)
# ---------------------------------------------------------------------------

# MinHook sources (vendored, BSD-2-Clause)
set(MINHOOK_SOURCES
    lib/MinHook/src/hook.c
    lib/MinHook/src/trampoline.c
    lib/MinHook/src/buffer.c
    lib/MinHook/src/hde/hde64.c
)

add_library(ALLIN1_Plugin SHARED
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

target_include_directories(ALLIN1_Plugin PRIVATE
    lib/MinHook/include
)

set_target_properties(ALLIN1_Plugin PROPERTIES
    OUTPUT_NAME "ALLIN1"
    SUFFIX ".dll"
    PREFIX ""
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

target_link_libraries(ALLIN1_Plugin PRIVATE psapi shlwapi)

# ---------------------------------------------------------------------------
# ALLIN1-Launcher.exe — injector that loads ALLIN1.dll into GTA V
# ---------------------------------------------------------------------------

add_executable(ALLIN1_Launcher
    src/injector/main.cpp
)

set_target_properties(ALLIN1_Launcher PROPERTIES
    OUTPUT_NAME "ALLIN1-Launcher"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

target_link_libraries(ALLIN1_Launcher PRIVATE shlwapi)

# Embed UAC manifest — launcher needs admin rights to inject into GTA V
if(MSVC)
    set_property(TARGET ALLIN1_Launcher APPEND_STRING PROPERTY
        LINK_FLAGS " /MANIFEST:EMBED /MANIFESTINPUT:${CMAKE_CURRENT_SOURCE_DIR}/src/injector/launcher.manifest"
    )
endif()

# ---------------------------------------------------------------------------
# Release optimizations
# ---------------------------------------------------------------------------

if(MSVC)
    foreach(tgt ALLIN1_Plugin ALLIN1_Launcher)
        target_compile_options(${tgt} PRIVATE
            $<$<CONFIG:Release>:/O2 /GL>
        )
        target_link_options(${tgt} PRIVATE
            $<$<CONFIG:Release>:/LTCG>
        )
    endforeach()
endif()
