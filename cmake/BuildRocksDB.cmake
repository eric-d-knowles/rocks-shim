# BuildRocksDB.cmake - Build RocksDB and dependencies for portable wheel packaging
include(ExternalProject)

# Configuration
set(ROCKSDB_VERSION "10.5.1")
set(SNAPPY_VERSION "1.1.10")
set(LZ4_VERSION "1.9.4")
set(VENDOR_CACHE_TAG 7)
set(THIRD_PARTY_DIR ${CMAKE_BINARY_DIR}/third_party_${VENDOR_CACHE_TAG})
set(CODECS_INSTALL_PREFIX ${THIRD_PARTY_DIR}/codec-install)
set(ROCKSDB_INSTALL_PREFIX ${THIRD_PARTY_DIR}/rocksdb-install)

# Library directory name. manylinux2014 installs to 'lib64' and Debian-based
# hosts to 'lib'; we pass it to the RocksDB build explicitly so it is the same
# everywhere.
set(ROCKSDB_LIB_DIR_NAME "lib64")
set(ROCKSDB_LIB_DIR ${ROCKSDB_INSTALL_PREFIX}/${ROCKSDB_LIB_DIR_NAME})

# CMake 3.24+ timestamp handling
if(CMAKE_VERSION VERSION_GREATER_EQUAL "3.24")
  set(_DOWNLOAD_EXTRACT_TIMESTAMP DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
endif()

# Where the sources come from: release tarballs (default) or shallow git
# clones of the same tags, for build hosts that allow git but not arbitrary
# downloads (e.g. behind an allow-listing proxy).
option(ROCKS_SHIM_VENDOR_GIT "Fetch RocksDB, Snappy and LZ4 with git instead of release tarballs" OFF)
if(ROCKS_SHIM_VENDOR_GIT)
  set(_SNAPPY_SOURCE GIT_REPOSITORY https://github.com/google/snappy.git GIT_TAG ${SNAPPY_VERSION} GIT_SHALLOW TRUE GIT_SUBMODULES "")
  set(_LZ4_SOURCE GIT_REPOSITORY https://github.com/lz4/lz4.git GIT_TAG v${LZ4_VERSION} GIT_SHALLOW TRUE GIT_SUBMODULES "")
  set(_ROCKSDB_SOURCE GIT_REPOSITORY https://github.com/facebook/rocksdb.git GIT_TAG v${ROCKSDB_VERSION} GIT_SHALLOW TRUE GIT_SUBMODULES "")
else()
  set(_SNAPPY_SOURCE URL "https://github.com/google/snappy/archive/refs/tags/${SNAPPY_VERSION}.tar.gz")
  set(_LZ4_SOURCE URL "https://github.com/lz4/lz4/archive/refs/tags/v${LZ4_VERSION}.tar.gz")
  set(_ROCKSDB_SOURCE URL "https://github.com/facebook/rocksdb/archive/refs/tags/v${ROCKSDB_VERSION}.tar.gz")
endif()

# Common settings
set(_WARNING_FLAGS -DCMAKE_C_FLAGS=-Wno-error=attributes -DCMAKE_CXX_FLAGS=-Wno-error=attributes)
set(_ISOLATED_ENV ${CMAKE_COMMAND} -E env LDFLAGS= CFLAGS= CXXFLAGS= CPPFLAGS= LIBRARY_PATH= LD_RUN_PATH= PKG_CONFIG_PATH=)

# Build Snappy (static)
ExternalProject_Add(snappy_ep
  ${_SNAPPY_SOURCE}
  SOURCE_DIR ${THIRD_PARTY_DIR}/snappy-src
  BINARY_DIR ${THIRD_PARTY_DIR}/snappy-build
  CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${CODECS_INSTALL_PREFIX}
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DBUILD_SHARED_LIBS=OFF
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DSNAPPY_BUILD_TESTS=OFF
    -DSNAPPY_BUILD_BENCHMARKS=OFF
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    ${_WARNING_FLAGS}
  BUILD_COMMAND ${_ISOLATED_ENV} ${CMAKE_COMMAND} --build <BINARY_DIR>
  UPDATE_COMMAND ""
  ${_DOWNLOAD_EXTRACT_TIMESTAMP}
)

# Build LZ4 (static)
ExternalProject_Add(lz4_ep
  ${_LZ4_SOURCE}
  SOURCE_DIR ${THIRD_PARTY_DIR}/lz4-src
  BINARY_DIR ${THIRD_PARTY_DIR}/lz4-build
  SOURCE_SUBDIR build/cmake
  CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${CODECS_INSTALL_PREFIX}
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DBUILD_SHARED_LIBS=OFF
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DLZ4_BUILD_CLI=OFF
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    ${_WARNING_FLAGS}
  BUILD_COMMAND ${_ISOLATED_ENV} ${CMAKE_COMMAND} --build <BINARY_DIR>
  UPDATE_COMMAND ""
  ${_DOWNLOAD_EXTRACT_TIMESTAMP}
)

# Build RocksDB (shared)
ExternalProject_Add(rocksdb_ep
  ${_ROCKSDB_SOURCE}
  SOURCE_DIR ${THIRD_PARTY_DIR}/rocksdb-src
  BINARY_DIR ${THIRD_PARTY_DIR}/rocksdb-build
  CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${ROCKSDB_INSTALL_PREFIX}
    -DCMAKE_INSTALL_LIBDIR=${ROCKSDB_LIB_DIR_NAME}
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DCMAKE_PREFIX_PATH=${CODECS_INSTALL_PREFIX}
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DBUILD_SHARED_LIBS=ON
    -DPORTABLE=ON
    -DUSE_RTTI=ON
    -DWITH_SNAPPY=ON
    -DWITH_LZ4=ON
    -DWITH_ZSTD=OFF
    -DWITH_TESTS=OFF -DWITH_TOOLS=OFF -DWITH_GFLAGS=OFF
    -DFAIL_ON_WARNINGS=OFF
    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-rpath,'\\\$ORIGIN'"
    ${_WARNING_FLAGS}
  BUILD_COMMAND ${_ISOLATED_ENV} ${CMAKE_COMMAND} --build <BINARY_DIR> --target install
  # Use the correct lib dir for copying
  INSTALL_COMMAND ${CMAKE_COMMAND} -E copy_directory ${ROCKSDB_LIB_DIR} ${CMAKE_BINARY_DIR}/.libs
  DEPENDS snappy_ep lz4_ep
  UPDATE_COMMAND ""
  ${_DOWNLOAD_EXTRACT_TIMESTAMP}
  # Use the correct lib dir for byproducts
  BUILD_BYPRODUCTS
    ${ROCKSDB_LIB_DIR}/librocksdb.so
    ${ROCKSDB_LIB_DIR}/librocksdb.so.10
    ${ROCKSDB_LIB_DIR}/librocksdb.so.10.5.1
)

# Create imported target
add_library(rocksdb_external SHARED IMPORTED GLOBAL)
add_dependencies(rocksdb_external rocksdb_ep)

# Use the correct lib dir for the imported location
set_target_properties(rocksdb_external PROPERTIES
  IMPORTED_LOCATION ${ROCKSDB_LIB_DIR}/librocksdb.so
)

message(STATUS "RocksDB ${ROCKSDB_VERSION} will be built and bundled (skipping hash checks)")
