#!/bin/bash
# Simple script to build a single wheel for development using Python 3.11

set -e -x

PROJECT_DIR=/io
WHEELHOUSE="${PROJECT_DIR}/wheelhouse"
PYTHON_BIN="/opt/_internal/cpython-3.11.13/bin/python"

echo "=== Building development wheel with Python 3.11 ==="

# Install build dependencies
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install scikit-build-core pybind11 ninja auditwheel

# Clean and create wheelhouse
rm -rf "$WHEELHOUSE"
mkdir -p "$WHEELHOUSE"

echo "Building wheel..."
"$PYTHON_BIN" -m pip wheel "$PROJECT_DIR" --no-deps -w "$WHEELHOUSE"

# Find and repair the wheel
WHEEL_FILE=$(find "$WHEELHOUSE" -name '*.whl' | head -n 1)

if [[ -f "$WHEEL_FILE" ]]; then
    echo "Repairing wheel: $(basename "$WHEEL_FILE")"
    auditwheel repair "$WHEEL_FILE" -w "$WHEELHOUSE"
    
    # Remove the original unrepaired wheel
    rm "$WHEEL_FILE"
    
    echo "Done! Portable wheel available in wheelhouse/:"
    ls -la "$WHEELHOUSE"
else
    echo "ERROR: No wheel file found"
    exit 1
fi
