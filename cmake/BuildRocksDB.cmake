# BuildRocksDB.cmake - Build RocksDB and dependencies for portable wheel packaging
include(ExternalProject)

# Configuration
set(ROCKSDB_VERSION "10.5.1")
set(SNAPPY_VERSION "1.1.10")
set(LZ4_VERSION "1.9.4")
set(ZSTD_VERSION "1.5.6")
set(VENDOR_CACHE_TAG 9)
# The vendored builds live beside the source tree (not in the per-wheel build
# directory) so that wheels for several Python versions share one RocksDB
# build, and CI can cache it. Override with -DROCKS_SHIM_VENDOR_DIR=...
set(ROCKS_SHIM_VENDOR_DIR "${CMAKE_SOURCE_DIR}/build/vendored_${VENDOR_CACHE_TAG}" CACHE PATH
    "Where RocksDB, Snappy and LZ4 are downloaded, built and installed")
set(THIRD_PARTY_DIR ${ROCKS_SHIM_VENDOR_DIR})
set(CODECS_INSTALL_PREFIX ${THIRD_PARTY_DIR}/codec-install)
set(ROCKSDB_INSTALL_PREFIX ${THIRD_PARTY_DIR}/rocksdb-install)

# Everything is built static and linked into the extension module, so the
# wheel is one self-contained .so: no bundled librocksdb.so, no RPATH, no
# auditwheel copies. Install dirs are pinned to 'lib' (manylinux would pick
# lib64, Debian lib) so the paths below hold on every host.
set(ROCKSDB_LIB_DIR ${ROCKSDB_INSTALL_PREFIX}/lib)
set(CODECS_LIB_DIR ${CODECS_INSTALL_PREFIX}/lib)

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
  set(_ZSTD_SOURCE GIT_REPOSITORY https://github.com/facebook/zstd.git GIT_TAG v${ZSTD_VERSION} GIT_SHALLOW TRUE GIT_SUBMODULES "")
  set(_ROCKSDB_SOURCE GIT_REPOSITORY https://github.com/facebook/rocksdb.git GIT_TAG v${ROCKSDB_VERSION} GIT_SHALLOW TRUE GIT_SUBMODULES "")
else()
  set(_SNAPPY_SOURCE URL "https://github.com/google/snappy/archive/refs/tags/${SNAPPY_VERSION}.tar.gz")
  set(_LZ4_SOURCE URL "https://github.com/lz4/lz4/archive/refs/tags/v${LZ4_VERSION}.tar.gz")
  set(_ZSTD_SOURCE URL "https://github.com/facebook/zstd/archive/refs/tags/v${ZSTD_VERSION}.tar.gz")
  set(_ROCKSDB_SOURCE URL "https://github.com/facebook/rocksdb/archive/refs/tags/v${ROCKSDB_VERSION}.tar.gz")
endif()

# Common settings. The sub-builds get the same make program as this build:
# wheels for several Python versions share the vendored directory, and each
# pip build runs with a different temporary ninja, so a path discovered by
# the first build must not be kept in the sub-builds' caches.
set(_WARNING_FLAGS -DCMAKE_C_FLAGS=-Wno-error=attributes -DCMAKE_CXX_FLAGS=-Wno-error=attributes)
set(_COMMON_ARGS -DCMAKE_MAKE_PROGRAM=${CMAKE_MAKE_PROGRAM} ${_WARNING_FLAGS})
set(_ISOLATED_ENV ${CMAKE_COMMAND} -E env LDFLAGS= CFLAGS= CXXFLAGS= CPPFLAGS= LIBRARY_PATH= LD_RUN_PATH= PKG_CONFIG_PATH=)

# Once the libraries are installed in the vendored directory nothing is
# rebuilt or even reconfigured: later wheel builds (and CI cache hits) link
# against them directly. Bump VENDOR_CACHE_TAG when a setting above changes.
if(EXISTS ${ROCKSDB_LIB_DIR}/librocksdb.a AND EXISTS ${CODECS_LIB_DIR}/libsnappy.a
   AND EXISTS ${CODECS_LIB_DIR}/liblz4.a AND EXISTS ${CODECS_LIB_DIR}/libzstd.a
   AND EXISTS ${ROCKSDB_INSTALL_PREFIX}/include/rocksdb/db.h)
  set(_VENDOR_READY TRUE)
  message(STATUS "Using the RocksDB ${ROCKSDB_VERSION} build already in ${THIRD_PARTY_DIR}")
else()
  set(_VENDOR_READY FALSE)
  message(STATUS "RocksDB ${ROCKSDB_VERSION}, Snappy ${SNAPPY_VERSION}, LZ4 ${LZ4_VERSION} and ZSTD ${ZSTD_VERSION} will be built static in ${THIRD_PARTY_DIR}")
endif()

if(NOT _VENDOR_READY)
# Build Snappy (static)
ExternalProject_Add(snappy_ep
  ${_SNAPPY_SOURCE}
  SOURCE_DIR ${THIRD_PARTY_DIR}/snappy-src
  BINARY_DIR ${THIRD_PARTY_DIR}/snappy-build
  CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${CODECS_INSTALL_PREFIX}
    -DCMAKE_INSTALL_LIBDIR=lib
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DBUILD_SHARED_LIBS=OFF
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DSNAPPY_BUILD_TESTS=OFF
    -DSNAPPY_BUILD_BENCHMARKS=OFF
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    ${_COMMON_ARGS}
  BUILD_COMMAND ${_ISOLATED_ENV} ${CMAKE_COMMAND} --build <BINARY_DIR>
  UPDATE_COMMAND ""
  ${_DOWNLOAD_EXTRACT_TIMESTAMP}
  BUILD_BYPRODUCTS ${CODECS_LIB_DIR}/libsnappy.a
)

# Build LZ4 (static)
ExternalProject_Add(lz4_ep
  ${_LZ4_SOURCE}
  SOURCE_DIR ${THIRD_PARTY_DIR}/lz4-src
  BINARY_DIR ${THIRD_PARTY_DIR}/lz4-build
  SOURCE_SUBDIR build/cmake
  CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${CODECS_INSTALL_PREFIX}
    -DCMAKE_INSTALL_LIBDIR=lib
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DBUILD_SHARED_LIBS=OFF
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DLZ4_BUILD_CLI=OFF
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    ${_COMMON_ARGS}
  BUILD_COMMAND ${_ISOLATED_ENV} ${CMAKE_COMMAND} --build <BINARY_DIR>
  UPDATE_COMMAND ""
  ${_DOWNLOAD_EXTRACT_TIMESTAMP}
  BUILD_BYPRODUCTS ${CODECS_LIB_DIR}/liblz4.a
)

# Build ZSTD (static). The profiles compress the bottommost level with it.
ExternalProject_Add(zstd_ep
  ${_ZSTD_SOURCE}
  SOURCE_DIR ${THIRD_PARTY_DIR}/zstd-src
  BINARY_DIR ${THIRD_PARTY_DIR}/zstd-build
  SOURCE_SUBDIR build/cmake
  CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${CODECS_INSTALL_PREFIX}
    -DCMAKE_INSTALL_LIBDIR=lib
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DZSTD_BUILD_STATIC=ON
    -DZSTD_BUILD_SHARED=OFF
    -DZSTD_BUILD_PROGRAMS=OFF
    -DZSTD_BUILD_TESTS=OFF
    -DZSTD_LEGACY_SUPPORT=OFF
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    ${_COMMON_ARGS}
  BUILD_COMMAND ${_ISOLATED_ENV} ${CMAKE_COMMAND} --build <BINARY_DIR>
  UPDATE_COMMAND ""
  ${_DOWNLOAD_EXTRACT_TIMESTAMP}
  BUILD_BYPRODUCTS ${CODECS_LIB_DIR}/libzstd.a
)

# Build RocksDB (static)
ExternalProject_Add(rocksdb_ep
  ${_ROCKSDB_SOURCE}
  SOURCE_DIR ${THIRD_PARTY_DIR}/rocksdb-src
  BINARY_DIR ${THIRD_PARTY_DIR}/rocksdb-build
  CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${ROCKSDB_INSTALL_PREFIX}
    -DCMAKE_INSTALL_LIBDIR=lib
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DCMAKE_PREFIX_PATH=${CODECS_INSTALL_PREFIX}
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DBUILD_SHARED_LIBS=OFF
    -DROCKSDB_BUILD_SHARED=OFF
    -DPORTABLE=ON
    -DUSE_RTTI=ON
    -DWITH_SNAPPY=ON
    -DWITH_LZ4=ON
    -DWITH_ZSTD=ON
    -DWITH_TESTS=OFF -DWITH_TOOLS=OFF -DWITH_GFLAGS=OFF
    -DFAIL_ON_WARNINGS=OFF
    ${_COMMON_ARGS}
  BUILD_COMMAND ${_ISOLATED_ENV} ${CMAKE_COMMAND} --build <BINARY_DIR> --target install
  INSTALL_COMMAND ""
  DEPENDS snappy_ep lz4_ep zstd_ep
  UPDATE_COMMAND ""
  ${_DOWNLOAD_EXTRACT_TIMESTAMP}
  BUILD_BYPRODUCTS ${ROCKSDB_LIB_DIR}/librocksdb.a
)
endif()  # NOT _VENDOR_READY

# Imported static targets, in link order: rocksdb needs the codecs after it.
add_library(rocksdb_external STATIC IMPORTED GLOBAL)
set_target_properties(rocksdb_external PROPERTIES IMPORTED_LOCATION ${ROCKSDB_LIB_DIR}/librocksdb.a)

add_library(snappy_external STATIC IMPORTED GLOBAL)
set_target_properties(snappy_external PROPERTIES IMPORTED_LOCATION ${CODECS_LIB_DIR}/libsnappy.a)

add_library(lz4_external STATIC IMPORTED GLOBAL)
set_target_properties(lz4_external PROPERTIES IMPORTED_LOCATION ${CODECS_LIB_DIR}/liblz4.a)

add_library(zstd_external STATIC IMPORTED GLOBAL)
set_target_properties(zstd_external PROPERTIES IMPORTED_LOCATION ${CODECS_LIB_DIR}/libzstd.a)

if(NOT _VENDOR_READY)
  add_dependencies(rocksdb_external rocksdb_ep)
  add_dependencies(snappy_external snappy_ep)
  add_dependencies(lz4_external lz4_ep)
  add_dependencies(zstd_external zstd_ep)
endif()

find_package(Threads REQUIRED)
set_target_properties(rocksdb_external PROPERTIES
  INTERFACE_LINK_LIBRARIES "snappy_external;lz4_external;zstd_external;Threads::Threads;${CMAKE_DL_LIBS}")

