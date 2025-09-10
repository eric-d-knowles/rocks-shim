#!/bin/bash

# Wheel checker script
# Usage: ./wheelcheck.sh [wheel_path]

# Default wheel path or use first argument
wheel=${1:-"rocks_shim-0.1.0-cp311-cp311-linux_x86_64.whl"}

# Check if wheel file exists
if [[ ! -f "$wheel" ]]; then
    echo "Error: Wheel file '$wheel' not found!"
    echo "Usage: $0 [wheel_path]"
    exit 1
fi

echo "Checking wheel: $wheel"
echo

# Clean staging dir
rm -rf /tmp/wheelcheck && mkdir -p /tmp/wheelcheck/.libs

# Extract the extension and its bundled libs
unzip -j "$wheel" 'rocks_shim/rocks_shim*.so' -d /tmp/wheelcheck >/dev/null
unzip -j "$wheel" 'rocks_shim/.libs/librocksdb.so*' -d /tmp/wheelcheck/.libs >/dev/null

echo "[RUNPATH / RPATH]"
readelf -d /tmp/wheelcheck/rocks_shim*.so | egrep 'RUNPATH|RPATH' || echo "!! No RUNPATH/RPATH recorded"

echo
echo "[ldd resolution]"
LD_LIBRARY_PATH=/tmp/wheelcheck/.libs ldd /tmp/wheelcheck/rocks_shim*.so

echo
echo "[Suspicious paths (conda/miniforge)?]"
LD_LIBRARY_PATH=/tmp/wheelcheck/.libs ldd /tmp/wheelcheck/rocks_shim*.so \
  | grep -E 'conda|miniforge' || echo "✓ No conda/miniforge paths"

echo
echo "[Debug: Files in .libs directory]"
ls -la /tmp/wheelcheck/.libs/

echo
echo "[Debug: RPATH expansion test]"
echo "Extension RPATH should resolve to:"
echo "  \$ORIGIN -> $(dirname $(readlink -f /tmp/wheelcheck/rocks_shim*.so))"
echo "  \$ORIGIN/.libs -> $(dirname $(readlink -f /tmp/wheelcheck/rocks_shim*.so))/.libs"

echo
echo "Check complete!"
