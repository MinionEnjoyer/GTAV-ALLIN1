# Resolve the official ScriptHookV SDK without assuming a flattened archive.
#
# Alexander Blade's stock SDK layout places headers under inc/ and the import
# library under lib/. Some existing ALLIN1 development fixtures use a flat
# fallback with ScriptHookV.lib at the SDK root, so retain that compatibility
# after preferring the stock location.
function(allin1_resolve_scripthookv_sdk sdk_root out_header out_library)
    set(_header "${sdk_root}/inc/main.h")
    set(_resolved_header "")
    set(_resolved_library "")

    if(EXISTS "${_header}")
        set(_resolved_header "${_header}")
    endif()

    foreach(_candidate IN ITEMS
            "${sdk_root}/lib/ScriptHookV.lib"
            "${sdk_root}/ScriptHookV.lib")
        if(EXISTS "${_candidate}")
            set(_resolved_library "${_candidate}")
            break()
        endif()
    endforeach()

    set(${out_header} "${_resolved_header}" PARENT_SCOPE)
    set(${out_library} "${_resolved_library}" PARENT_SCOPE)
endfunction()
