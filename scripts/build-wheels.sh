#!/bin/bash
# A script to build and repair manylinux wheels, processing one Python version at a time.
# This is intended to be run inside a PPA manylinux container (e.g., via Docker).

set -e -x

# The project directory (containing pyproject.toml) will be mounted at /io
PROJECT_DIR=/io

# 1. Install Python build dependencies for all available Python versions
#    This only needs to be done once. We'll use the first available pip.
FIRST_PYBIN=$(find /opt/python/cp3* -name "pip" | head -n 1)
"$FIRST_PYBIN" install --upgrade pip
"$FIRST_PYBIN" install scikit-build-core pybind11 ninja auditwheel

# 2. Build and repair the wheel for each Python version, one by one.
for PYBIN_DIR in /opt/python/cp3*/bin; do
    PYBIN="${PYBIN_DIR}/python"
    echo "--- Building wheel for $(${PYBIN} --version) ---"

    # Build the wheel into a temporary directory
    "${PYBIN}" -m pip wheel "$PROJECT_DIR" --no-deps -w "$PROJECT_DIR/wheelhouse_temp"

    # The temp directory should now contain exactly one wheel. Find it.
    WHEEL_FILE=$(find "$PROJECT_DIR/wheelhouse_temp" -name "*.whl" | head -n 1)

    # Repair it immediately and place it in the final directory
    if [ -f "$WHEEL_FILE" ]; then
        auditwheel repair "$WHEEL_FILE" -w "$PROJECT_DIR/wheelhouse"
    else
        echo "ERROR: No wheel file found to repair for $(${PYBIN} --version)"
        exit 1
    fi

    # Clean up the temp directory for the next loop
    rm -rf "$PROJECT_DIR/wheelhouse_temp"/*
done

# 3. Final cleanup and show the results
rm -rf "$PROJECT_DIR/wheelhouse_temp"

echo "Build complete. Portable wheels are in wheelhouse/:"
ls -l "$PROJECT_DIR/wheelhouse"l. Find it.
    WHEEL_FILE=$(find "$PROJECT_DIR/wheelhouse_temp" -name "*.whl" | head -n 1)

    # Repair it immediately and place it in the final directory
    if [ -f "$WHEEL_FILE" ]; then
        auditwheel repair "$WHEEL_FILE" -w "$PROJECT_DIR/wheelhouse"
    else
        echo "ERROR: No wheel file found to repair for $(${PYBIN} --version)"
        exit 1
    fi

    # Clean up the temp directory for the next loop
    rm -rf "$PROJECT_DIR/wheelhouse_temp"/*
done

# 3. Final cleanup and show the results
rm -rf "$PROJECT_DIR/wheelhouse_temp"

echo "Build complete. Portable wheels are in wheelhouse/:"
ls -l "$PROJECT_DIR/wheelhouse"
