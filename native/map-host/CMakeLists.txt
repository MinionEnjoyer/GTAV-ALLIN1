cmake_minimum_required(VERSION 3.20)
project(ALLIN1MapHostScaffold LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(CTest)
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/ResolveScriptHookVSdk.cmake")

add_library(allin1_map_host_policy STATIC
    src/map_host.cpp
)
target_include_directories(allin1_map_host_policy PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
if(MSVC)
    target_compile_options(allin1_map_host_policy PRIVATE /W4 /permissive-)
else()
    target_compile_options(allin1_map_host_policy PRIVATE
        -Wall -Wextra -Wpedantic -Werror)
endif()

if(BUILD_TESTING)
    add_executable(allin1_map_host_policy_tests
        tests/map_host_tests.cpp
    )
    target_link_libraries(allin1_map_host_policy_tests PRIVATE
        allin1_map_host_policy
    )
    if(MSVC)
        target_compile_options(allin1_map_host_policy_tests PRIVATE
            /W4 /permissive-)
    else()
        target_compile_options(allin1_map_host_policy_tests PRIVATE
            -Wall -Wextra -Wpedantic -Werror)
    endif()
    add_test(NAME allin1_map_host_policy
             COMMAND allin1_map_host_policy_tests)
endif()

# Off by default. These targets prove the edition-specific ScriptHookV loading
# boundary only; their backend is deliberately unwired and the host defaults
# to disabled. They are not production artifacts.
option(ALLIN1_MAP_HOST_BUILD_DISABLED_SCRIPTHOOK_STUBS
       "Build disabled edition-specific ScriptHookV ABI scaffolds" OFF)
set(ALLIN1_SCRIPTHOOKV_SDK "" CACHE PATH
    "Path to the official ScriptHookV SDK root")

if(ALLIN1_MAP_HOST_BUILD_DISABLED_SCRIPTHOOK_STUBS)
    allin1_resolve_scripthookv_sdk(
        "${ALLIN1_SCRIPTHOOKV_SDK}"
        ALLIN1_SCRIPTHOOKV_MAIN_HEADER
        ALLIN1_SCRIPTHOOKV_LIBRARY
    )
    if(NOT ALLIN1_SCRIPTHOOKV_MAIN_HEADER OR
       NOT ALLIN1_SCRIPTHOOKV_LIBRARY)
        message(FATAL_ERROR
            "ALLIN1_SCRIPTHOOKV_SDK must point to an official local SDK "
            "containing inc/main.h and either lib/ScriptHookV.lib "
            "(stock layout) or ScriptHookV.lib (flat fallback)")
    endif()
    get_filename_component(ALLIN1_SCRIPTHOOKV_INCLUDE_DIR
        "${ALLIN1_SCRIPTHOOKV_MAIN_HEADER}" DIRECTORY)

    foreach(edition IN ITEMS Legacy Enhanced)
        string(TOUPPER "${edition}" edition_upper)
        add_library("ALLIN1MapHost${edition}Scaffold" SHARED
            src/plugin_entry.cpp
        )
        target_include_directories("ALLIN1MapHost${edition}Scaffold" PRIVATE
            "${ALLIN1_SCRIPTHOOKV_INCLUDE_DIR}"
        )
        target_compile_definitions("ALLIN1MapHost${edition}Scaffold" PRIVATE
            "ALLIN1_MAP_HOST_EDITION_${edition_upper}=1"
        )
        if(MSVC)
            target_compile_options("ALLIN1MapHost${edition}Scaffold" PRIVATE
                /W4 /permissive- /wd4505)
        endif()
        target_link_libraries("ALLIN1MapHost${edition}Scaffold" PRIVATE
            allin1_map_host_policy
            "${ALLIN1_SCRIPTHOOKV_LIBRARY}"
        )
        set_target_properties("ALLIN1MapHost${edition}Scaffold" PROPERTIES
            PREFIX ""
            SUFFIX ".asi"
            OUTPUT_NAME "ALLIN1MapHost-${edition}-DISABLED-SCAFFOLD"
        )
    endforeach()
endif()
