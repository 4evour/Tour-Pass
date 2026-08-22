cmake_minimum_required(VERSION 3.16)

project(TourPass LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
add_compile_options($<$<CXX_COMPILER_ID:MSVC>:/utf-8>)
option(TOURPASS_BUILD_TESTS "Build the tourpass_tests executable" OFF)
option(TOURPASS_USE_GTEST "Build GoogleTest-based tests with FetchContent" OFF)
option(TOURPASS_ENABLE_OPENSSL "Enable HTTPS LLM calls when OpenSSL is available" ON)
option(TOURPASS_ENABLE_POSTGRES "Enable PostgreSQL storage backend when libpq is available" ON)
find_package(Threads REQUIRED)
if (TOURPASS_ENABLE_OPENSSL)
    find_package(OpenSSL QUIET)
endif()
if (TOURPASS_ENABLE_POSTGRES)
    find_package(PostgreSQL QUIET)
endif()

set(TOURPASS_SOURCES
    src/models.cpp
    src/api.cpp
    src/auth.cpp
    src/graph.cpp
    src/llm.cpp
    src/planner.cpp
    src/search.cpp
    src/service_runtime.cpp
    src/sqlite_store.cpp
    src/data_loader.cpp
    src/travel_time_provider.cpp
)

if (PostgreSQL_FOUND)
    list(APPEND TOURPASS_SOURCES src/pg_store.cpp)
endif()

add_library(sqlite3 STATIC third_party/sqlite3.c)
target_compile_definitions(sqlite3 PRIVATE SQLITE_THREADSAFE=1 SQLITE_DEFAULT_MEMSTATUS=0)
target_include_directories(sqlite3 PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/third_party)

add_executable(tourpass
    src/main.cpp
    ${TOURPASS_SOURCES}
)
target_include_directories(tourpass PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party
)
target_compile_options(tourpass PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Wall -Wextra -Wno-unused-parameter>
)

if (WIN32)
    target_link_libraries(tourpass PRIVATE ws2_32 winhttp)
endif()
target_link_libraries(tourpass PRIVATE Threads::Threads)
target_link_libraries(tourpass PRIVATE sqlite3)
if (OpenSSL_FOUND)
    target_compile_definitions(tourpass PRIVATE CPPHTTPLIB_OPENSSL_SUPPORT)
    target_link_libraries(tourpass PRIVATE OpenSSL::SSL OpenSSL::Crypto)
endif()
if (PostgreSQL_FOUND)
    target_compile_definitions(tourpass PRIVATE TOURPASS_HAS_POSTGRES)
    target_include_directories(tourpass PRIVATE ${PostgreSQL_INCLUDE_DIRS})
    target_link_libraries(tourpass PRIVATE ${PostgreSQL_LIBRARIES})
endif()

if(TOURPASS_BUILD_TESTS)
    add_executable(tourpass_tests
        tests/test_main.cpp
        ${TOURPASS_SOURCES}
    )
    target_include_directories(tourpass_tests PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/third_party
    )
    target_compile_options(tourpass_tests PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Wall -Wextra -Wno-unused-parameter>
    )
    if (WIN32)
        target_link_libraries(tourpass_tests PRIVATE ws2_32 winhttp)
    endif()
    target_link_libraries(tourpass_tests PRIVATE Threads::Threads)
    target_link_libraries(tourpass_tests PRIVATE sqlite3)
    if (OpenSSL_FOUND)
        target_compile_definitions(tourpass_tests PRIVATE CPPHTTPLIB_OPENSSL_SUPPORT)
        target_link_libraries(tourpass_tests PRIVATE OpenSSL::SSL OpenSSL::Crypto)
    endif()
    if (PostgreSQL_FOUND)
        target_compile_definitions(tourpass_tests PRIVATE TOURPASS_HAS_POSTGRES)
        target_include_directories(tourpass_tests PRIVATE ${PostgreSQL_INCLUDE_DIRS})
        target_link_libraries(tourpass_tests PRIVATE ${PostgreSQL_LIBRARIES})
    endif()
    enable_testing()
    add_test(NAME tourpass_tests COMMAND tourpass_tests)
    set_tests_properties(tourpass_tests PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
endif()

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
    target_include_directories(tourpass_gtests PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/third_party
    )
    target_compile_options(tourpass_gtests PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-Wall -Wextra -Wno-unused-parameter>
    )
    target_link_libraries(tourpass_gtests PRIVATE GTest::gtest_main)
    target_link_libraries(tourpass_gtests PRIVATE Threads::Threads)
    target_link_libraries(tourpass_gtests PRIVATE sqlite3)
    if (OpenSSL_FOUND)
        target_compile_definitions(tourpass_gtests PRIVATE CPPHTTPLIB_OPENSSL_SUPPORT)
        target_link_libraries(tourpass_gtests PRIVATE OpenSSL::SSL OpenSSL::Crypto)
    endif()
    if (WIN32)
        target_link_libraries(tourpass_gtests PRIVATE ws2_32 winhttp)
    endif()
    include(GoogleTest)
    gtest_discover_tests(
        tourpass_gtests
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )
endif()
