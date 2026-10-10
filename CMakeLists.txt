cmake_minimum_required(VERSION 3.20)
project(rocks_shim LANGUAGES CXX)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Find dependencies
set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

# Build RocksDB
include(cmake/BuildRocksDB.cmake)

# Create extension
pybind11_add_module(rocks_shim MODULE src/cpp/module.cpp src/cpp/db.cc)

target_compile_features(rocks_shim PRIVATE cxx_std_17)
target_include_directories(rocks_shim PRIVATE
  include
  ${THIRD_PARTY_DIR}/rocksdb-install/include
)
target_link_libraries(rocks_shim PRIVATE rocksdb_external)
# Keep RocksDB's symbols private to the module, so another extension that
# links its own RocksDB can live in the same process.
if(NOT APPLE)
  target_link_options(rocks_shim PRIVATE "-Wl,--exclude-libs,ALL")
endif()

# The wheel is the module plus __init__.py; nothing else to bundle.
install(TARGETS rocks_shim LIBRARY DESTINATION ".")
install(FILES ${CMAKE_SOURCE_DIR}/src/rocks_shim/__init__.py DESTINATION ".")