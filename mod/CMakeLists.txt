cmake_minimum_required(VERSION 3.21)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)

project(ClaudeBridge VERSION 1.0.0)

add_library(${PROJECT_NAME} SHARED src/main.cpp src/editor.cpp src/ui.cpp src/runner.cpp src/net.cpp src/sim.cpp)
# net.cpp тянет winsock2.h — без предкомпилированного Geode (там полный Windows.h с winsock v1)
set_source_files_properties(src/net.cpp PROPERTIES SKIP_PRECOMPILE_HEADERS ON)
target_link_libraries(${PROJECT_NAME} ws2_32)

if (NOT DEFINED ENV{GEODE_SDK})
    message(FATAL_ERROR "GEODE_SDK не задан")
endif()

add_subdirectory($ENV{GEODE_SDK} ${CMAKE_CURRENT_BINARY_DIR}/geode)

setup_geode_mod(${PROJECT_NAME})
