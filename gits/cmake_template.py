CMAKE_TEMPLATE = """\
cmake_minimum_required(VERSION 3.0)
project({project_name})
include($ENV{{GIS_LEAN_ROOT}}/import.cmake)
message("GIS_LEAN_ROOT: " $ENV{{GIS_LEAN_ROOT}})
set(ROOT_DIR {root_dir_path_str})
set(SRC_LIST "")

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_DEBUG   {root_dir_path_str}{dep_work})
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE {root_dir_path_str}{dep_work})

IF (CMAKE_SYSTEM_NAME MATCHES "Linux")
    set(CMAKE_C_FLAGS "${{CMAKE_C_FLAGS}} -pipe")
    set(CMAKE_CXX_FLAGS "${{CMAKE_CXX_FLAGS}} -pipe -std=c++17")
    set(CMAKE_C_FLAGS_DEBUG "${{CMAKE_C_FLAGS_DEBUG}} -g -O0")
    set(CMAKE_CXX_FLAGS_DEBUG "${{CMAKE_CXX_FLAGS_DEBUG}} -g -O0")
    set(CMAKE_C_FLAGS_RELEASE "${{CMAKE_C_FLAGS_RELEASE}} -O3")
    set(CMAKE_CXX_FLAGS_RELEASE "${{CMAKE_CXX_FLAGS_RELEASE}} -O3")
    set(CMAKE_SHARED_LINKER_FLAGS    "-rdynamic -Wl,-z,noexecstack -Wl,-z,relro -Wl,-z,now")
    set(CMAKE_EXE_LINKER_FLAGS    "-rdynamic -Wl,-z,noexecstack -Wl,-z,relro -Wl,-z,now")
ELSEIF (CMAKE_SYSTEM_NAME MATCHES "Windows")
    set(CMAKE_C_FLAGS "${{CMAKE_C_FLAGS}} /std:c11")
    set(CMAKE_CXX_FLAGS "${{CMAKE_CXX_FLAGS}} /std:c++17")
    set(CMAKE_C_FLAGS_DEBUG "${{CMAKE_C_FLAGS_DEBUG}} /Od /MT /GR /permissive- /sdl-")
    set(CMAKE_CXX_FLAGS_DEBUG "${{CMAKE_CXX_FLAGS_DEBUG}} /Od /MT /GR /permissive- /sdl-")
    set(CMAKE_C_FLAGS_RELEASE "${{CMAKE_C_FLAGS_RELEASE}} /O2 /MT /GR /permissive- /sdl-")
    set(CMAKE_CXX_FLAGS_RELEASE "${{CMAKE_CXX_FLAGS_RELEASE}} /O2 /MT /GR /permissive- /sdl-")
    set(CMAKE_SHARED_LINKER_FLAGS    "/DEBUG /NODEFAULTLIB:\"opencv_world346.lib\"")
    set(CMAKE_EXE_LINKER_FLAGS    "/DEBUG /NODEFAULTLIB:\"opencv_world346.lib\"")
ENDIF()
FILE (GLOB_RECURSE  cur_sources
                    {root_dir_path_str}src/*.cpp
                    {root_dir_path_str}src/*.cc
                    {root_dir_path_str}src/*.c
                    )
list(APPEND SRC_LIST ${{cur_sources}})
include_directories({root_dir_path_str}src)


message(STATUS "${{PROJECT_NAME}} SRC_LIST: ${{SRC_LIST}}")
{target_command}
"""

CMAKE_BASE_TEMPLATE = """\
cmake_minimum_required(VERSION 3.0)
project({project_name})
include($ENV{{GIS_LEAN_ROOT}}/import.cmake)
"""