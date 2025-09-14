cmake_minimum_required(VERSION 3.20)
project(rocks_shim LANGUAGES CXX)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Find dependencies
set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

# Build RocksDB
include(cmake/BuildRocksDB.cmake)

# Control the RPATH/RUNPATH for portability
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH OFF)          # Don't add linker search paths to the RPATH
set(CMAKE_INSTALL_RPATH "$ORIGIN:$ORIGIN/.libs")    # Set the desired RPATH for the installed target

# Create extension
pybind11_add_module(rocks_shim MODULE src/cpp/module.cpp src/cpp/db.cc)

target_compile_features(rocks_shim PRIVATE cxx_std_17)
target_include_directories(rocks_shim PRIVATE
  include
  ${THIRD_PARTY_DIR}/rocksdb-install/include
)
target_link_libraries(rocks_shim PRIVATE rocksdb_external)

# Install everything
install(TARGETS rocks_shim LIBRARY DESTINATION ".")
install(FILES ${CMAKE_SOURCE_DIR}/src/rocks_shim/__init__.py DESTINATION ".")
install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/.libs/ DESTINATION ".libs"
  FILES_MATCHING PATTERN "librocksdb.so*")