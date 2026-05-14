cmake_minimum_required(VERSION 3.16)

project(TourPass LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
option(TOURPASS_USE_GTEST "Build GoogleTest-based tests with FetchContent" OFF)

include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party
)

set(TOURPASS_SOURCES
    src/models.cpp
    src/api.cpp
    src/graph.cpp
    src/llm.cpp
    src/planner.cpp
    src/search.cpp
    src/data_loader.cpp
)

add_executable(tourpass
    src/main.cpp
    ${TOURPASS_SOURCES}
)

add_executable(tourpass_tests
    tests/test_main.cpp
    ${TOURPASS_SOURCES}
)

if (WIN32)
    target_link_libraries(tourpass PRIVATE ws2_32)
    target_link_libraries(tourpass_tests PRIVATE ws2_32)
endif()

enable_testing()
add_test(NAME tourpass_tests COMMAND tourpass_tests)
set_tests_properties(tourpass_tests PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

if (TOURPASS_USE_GTEST)
    include(FetchContent)
    FetchContent_Declare(
        googletest
        URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    )
    set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)

    add_executable(tourpass_gtests
        tests/gtest_main.cpp
        ${TOURPASS_SOURCES}
    )
    target_link_libraries(tourpass_gtests PRIVATE GTest::gtest_main)
    if (WIN32)
        target_link_libraries(tourpass_gtests PRIVATE ws2_32)
    endif()
    include(GoogleTest)
    gtest_discover_tests(
        tourpass_gtests
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )
endif()
