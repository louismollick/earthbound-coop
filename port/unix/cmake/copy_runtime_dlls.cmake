# Copy every non-Windows DLL that EXE loads (directly or through another DLL) next
# to it, from DIRS (the MSYS2 toolchain's bin), so the folder runs from Explorer.
# Run as a post-build step (port/unix/CMakeLists.txt) with -DEXE, -DDIRS, -DOBJDUMP.
if(NOT OBJDUMP)
    message(WARNING "copy_runtime_dlls: no objdump; copy libcurl's DLLs next to the exe by hand")
    return()
endif()
set(CMAKE_GET_RUNTIME_DEPENDENCIES_PLATFORM "windows+pe")
set(CMAKE_GET_RUNTIME_DEPENDENCIES_TOOL "objdump")
set(CMAKE_GET_RUNTIME_DEPENDENCIES_COMMAND "${OBJDUMP}")
file(GET_RUNTIME_DEPENDENCIES
    EXECUTABLES "${EXE}"
    RESOLVED_DEPENDENCIES_VAR deps
    UNRESOLVED_DEPENDENCIES_VAR missing
    DIRECTORIES ${DIRS}
    PRE_EXCLUDE_REGEXES "^api-ms-" "^ext-ms-"
    POST_EXCLUDE_REGEXES "[Ww][Ii][Nn][Dd][Oo][Ww][Ss][/\\\\][Ss][Yy][Ss][Tt][Ee][Mm]32")
get_filename_component(dest "${EXE}" DIRECTORY)
foreach(dll IN LISTS deps)
    file(COPY "${dll}" DESTINATION "${dest}")
endforeach()
