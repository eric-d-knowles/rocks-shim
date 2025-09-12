#!/bin/bash
# Wrapper script to build manylinux wheels using Docker
# This script runs on the host and launches the Docker container

set -e

# Configuration
MANYLINUX_TAG="${MANYLINUX_TAG:-manylinux2014_x86_64}"  # Can be overridden
DOCKER_IMAGE="quay.io/pypa/${MANYLINUX_TAG}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHEELHOUSE_DIR="${PROJECT_ROOT}/wheelhouse"

echo "Building manylinux wheels using ${DOCKER_IMAGE}"
echo "Project root: ${PROJECT_ROOT}"

# Ensure wheelhouse directory exists and is clean
mkdir -p "${WHEELHOUSE_DIR}"
rm -rf "${WHEELHOUSE_DIR}"/*

# Run the build inside Docker container
docker run --rm \
    -v "${PROJECT_ROOT}:/io:Z" \
    -w /io \
    "${DOCKER_IMAGE}" \
    /io/scripts/build-wheels-internal.sh

echo ""
echo "Build complete! Wheels available in:"
ls -la "${WHEELHOUSE_DIR}"
