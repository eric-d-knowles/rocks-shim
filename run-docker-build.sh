#!/bin/bash
# A wrapper script to build manylinux wheels for the current architecture.
# This script detects the host architecture and invokes the main build script
# inside the appropriate manylinux Docker container.

set -e

# Ensure the script is run from the project root
if [ ! -f "pyproject.toml" ]; then
    echo "ERROR: This script must be run from the project root directory."
    exit 1
fi

# Detect the host architecture
ARCH=$(uname -m)
DOCKER_IMAGE=""

if [ "$ARCH" == "x86_64" ]; then
    echo "--- Detected Intel (x86_64) architecture ---"
    DOCKER_IMAGE="quay.io/pypa/manylinux2014_x86_64"
elif [ "$ARCH" == "arm64" ] || [ "$ARCH" == "aarch64" ]; then
    echo "--- Detected Apple Silicon/ARM (aarch64) architecture ---"
    DOCKER_IMAGE="quay.io/pypa/manylinux_2_28_aarch64"
else
    echo "ERROR: Unsupported architecture: $ARCH"
    exit 1
fi

echo "Using Docker image: ${DOCKER_IMAGE}"

# Run the main build script inside the container
docker run --rm -v "$(pwd)":/io "$DOCKER_IMAGE" /io/scripts/build-wheels.sh

echo "Wrapper script finished successfully."
