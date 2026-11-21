cmake_minimum_required(VERSION 3.16)
project(gits_delivery_smoke LANGUAGES CXX)
add_executable(delivery_smoke main.cpp)
target_compile_features(delivery_smoke PRIVATE cxx_std_17)
target_include_directories(delivery_smoke PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/workspace/include"
)

enable_testing()
add_test(NAME demo_math COMMAND delivery_smoke)
set_tests_properties(demo_math PROPERTIES
    PASS_REGULAR_EXPRESSION "2 [+] 3 = 5"
)
