cmake_minimum_required(VERSION 3.16)
project(yolo_edge LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(OpenCV 4 REQUIRED COMPONENTS core imgproc imgcodecs dnn)
add_executable(yolo_edge src/main.cpp)
target_include_directories(yolo_edge PRIVATE ${OpenCV_INCLUDE_DIRS})
target_link_libraries(yolo_edge PRIVATE ${OpenCV_LIBS})
set_target_properties(yolo_edge PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/workspace")
if(WIN32)
    file(GLOB runtime_dlls "${CMAKE_CURRENT_SOURCE_DIR}/workspace/*.dll")
    if(runtime_dlls)
        add_custom_command(TARGET yolo_edge POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                ${runtime_dlls} "$<TARGET_FILE_DIR:yolo_edge>"
            COMMAND_EXPAND_LISTS)
    endif()
endif()
