#!/bin/bash
# A script to build and repair manylinux wheels inside a generic Ubuntu 18.04 container.

set -e -x

# The project directory (containing pyproject.toml) will be mounted at /io
PROJECT_DIR=/io
# Define the Python version we will install and build against
PYTHON_VERSION=3.8
PIP_BIN="/usr/bin/pip${PYTHON_VERSION}"
PYTHON_BIN="/usr/bin/python${PYTHON_VERSION}"

# 1. Install required build tools and a modern Python version.
#    This is necessary because a generic Ubuntu image lacks these by default.
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y git cmake ninja-build python3.8 python3.8-dev python3.8-distutils python3-pip

# 2. Install Python build dependencies using the newly installed pip
#    We use python3.8 -m pip to ensure we're using the correct one.
"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install scikit-build-core pybind11 ninja auditwheel

# 3. Build the initial, non-portable wheel
#    The wheel will be placed in a temporary directory.
"${PYTHON_BIN}" -m pip wheel "$PROJECT_DIR" --no-deps -w "$PROJECT_DIR/wheelhouse_temp"

# 4. Repair the wheel with auditwheel
#    This bundles external libraries and applies the correct manylinux tag.
#    The final, portable wheel will be in the 'wheelhouse' directory.
for whl in "$PROJECT_DIR/wheelhouse_temp"/*.whl; do
    auditwheel repair "$whl" -w "$PROJECT_DIR/wheelhouse"
done

# 5. Clean up and show the results
rm -rf "$PROJECT_DIR/wheelhouse_temp"

echo "Build complete. Portable wheels are in wheelhouse/:"
ls -l "$PROJECT_DIR/wheelhouse"
```

### Your New Workflow (Entirely on the Cluster)

Now, you can run the entire build process from your SSH session.

1.  **Make the script executable** (if you haven't already):
    ```bash
    chmod +x scripts/build-wheels.sh
    ```

2.  **Run the build** inside the pre-existing Ubuntu 18.04 container using `--fakeroot`:
    ```bash
    singularity exec --fakeroot --bind .:/io /scratch/work/public/singularity/ubuntu-18.04.6.sif /io/scripts/build-wheels.sh
    

