cmake_minimum_required(VERSION 3.16)
project(earthbound C)
set(CMAKE_C_STANDARD 11)

# Emit compile_commands.json so clangd/IDEs resolve include paths and types.
# A root-level symlink (../../compile_commands.json) points at this file.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(EB_VIEWPORT_WIDTH 256 CACHE STRING "Viewport width in pixels")
set(EB_VIEWPORT_HEIGHT 224 CACHE STRING "Viewport height in pixels")

# The desktop build is warning-clean: warnings fail it (-DEB_WERROR=OFF to relax).
option(EB_WERROR "Treat compiler warnings as errors" ON)

# Smooth camera hooks (runtime option --smooth-camera / EB_SMOOTH_CAMERA=1)
set(EB_SMOOTH_CAMERA ON CACHE BOOL "Build the smooth-camera presentation hooks")

# Build game library from src/
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../../src
                 ${CMAKE_CURRENT_BINARY_DIR}/game_lib)

# Find SDL2
find_package(SDL2 QUIET)
if(NOT SDL2_FOUND)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(SDL2 REQUIRED sdl2)
endif()

# Platform executable. Use GLOB_RECURSE (not plain GLOB): a non-recursive
# `file(GLOB ... CONFIGURE_DEPENDS ...)` silently returns empty on some
# filesystems (notably the Docker Desktop virtiofs mount used by the i386 build
# in port/unix/docker), which drops every platform/*.c object and breaks the
# link. GLOB_RECURSE + CONFIGURE_DEPENDS works there and matches src/CMakeLists.txt.
# platform/ has no subdirectories, so this is equivalent to a flat glob.
file(GLOB_RECURSE PLATFORM_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/platform/*.c")
# Online co-op (net/net.h)
file(GLOB_RECURSE NET_SOURCES CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/net/*.c")
add_executable(earthbound main.c ${PLATFORM_SOURCES} ${NET_SOURCES})
target_include_directories(earthbound PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# The game revision for the netplay compatibility check (net/build_id.cmake),
# refreshed on every build.
set(NET_BUILD_ID_DIR "${CMAKE_CURRENT_BINARY_DIR}/net_generated")
add_custom_target(net_build_id
    COMMAND ${CMAKE_COMMAND} -DROOT=${CMAKE_CURRENT_SOURCE_DIR}/../..
        -DOUT=${NET_BUILD_ID_DIR}/net_build_id.h -P ${CMAKE_CURRENT_SOURCE_DIR}/net/build_id.cmake
    BYPRODUCTS ${NET_BUILD_ID_DIR}/net_build_id.h
    COMMENT "Netplay build id")
add_dependencies(earthbound net_build_id)
target_include_directories(earthbound PRIVATE ${NET_BUILD_ID_DIR})

target_link_libraries(earthbound earthbound_game)

if(TARGET SDL2::SDL2)
    target_link_libraries(earthbound SDL2::SDL2)
else()
    target_include_directories(earthbound PRIVATE ${SDL2_INCLUDE_DIRS})
    target_link_libraries(earthbound ${SDL2_LIBRARIES})
    target_link_directories(earthbound PRIVATE ${SDL2_LIBRARY_DIRS})
endif()

# Platform code needs SDL2 headers and game library headers (inherited via PUBLIC)
target_include_directories(earthbound PRIVATE
    ${SDL2_INCLUDE_DIRS}
)

eb_target_warnings(earthbound)

# Online co-op through a relay (net/relay.c, relay/README.md) needs libcurl with
# WebSockets: 8.14 or newer (earlier releases flag message fragments differently). macOS's own libcurl has none; Homebrew's curl
# (keg-only: `brew install curl`) has. Without it the build plays direct UDP
# Sessions only, and starts straight into the game (no launcher).
option(EB_NET_RELAY "Build relay support when libcurl 8.14+ is found" ON)
set(EB_HAVE_RELAY OFF)
if(EB_NET_RELAY)
    if(APPLE)
        list(APPEND CMAKE_PREFIX_PATH /opt/homebrew/opt/curl /usr/local/opt/curl)
    endif()
    find_package(CURL 8.14 QUIET)
    if(CURL_FOUND)
        set(EB_HAVE_RELAY ON)
        target_link_libraries(earthbound CURL::libcurl)
        target_compile_definitions(earthbound PRIVATE EB_NET_RELAY)
        message(STATUS "Relay support: libcurl ${CURL_VERSION_STRING}")
    else()
        message(STATUS "Relay support: off (needs libcurl 8.14+; macOS: brew install curl)")
    endif()
endif()

if(WIN32)
    # Our own main() (no SDL2main), a console program so headless runs print;
    # Winsock for netplay
    target_compile_definitions(earthbound PRIVATE SDL_MAIN_HANDLED)
    target_link_libraries(earthbound ws2_32)
    # SDL2.dll next to the exe, so it starts from Explorer without MSYS2 on PATH
    if(TARGET SDL2::SDL2)
        add_custom_command(TARGET earthbound POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different $<TARGET_RUNTIME_DLLS:earthbound> $<TARGET_FILE_DIR:earthbound>
            COMMAND_EXPAND_LISTS)
    endif()
    # libcurl's own DLLs (TLS, zlib, nghttp2, ...) too, found next to the compiler
    if(EB_HAVE_RELAY)
        get_filename_component(EB_TOOLCHAIN_BIN "${CMAKE_C_COMPILER}" DIRECTORY)
        add_custom_command(TARGET earthbound POST_BUILD
            COMMAND ${CMAKE_COMMAND} -DEXE=$<TARGET_FILE:earthbound> -DDIRS=${EB_TOOLCHAIN_BIN}
                -DOBJDUMP=${CMAKE_OBJDUMP} -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/copy_runtime_dlls.cmake)
    endif()
endif()

# Sanitizer support
option(ENABLE_ASAN "Enable AddressSanitizer" OFF)
option(ENABLE_UBSAN "Enable UndefinedBehaviorSanitizer" OFF)

set(_SANITIZERS "")
if(ENABLE_ASAN)
    list(APPEND _SANITIZERS "address")
endif()
if(ENABLE_UBSAN)
    list(APPEND _SANITIZERS "undefined")
endif()

if(_SANITIZERS)
    list(JOIN _SANITIZERS "," _SANITIZER_FLAGS)
    target_compile_options(earthbound PRIVATE -fsanitize=${_SANITIZER_FLAGS} -fno-omit-frame-pointer)
    target_link_options(earthbound PRIVATE -fsanitize=${_SANITIZER_FLAGS})
endif()
