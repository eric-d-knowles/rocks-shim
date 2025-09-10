#!/usr/bin/env python3
import importlib.util
import pathlib
import subprocess
import sys
import os


def smoke_test(pkg_name: str):
    try:
        # Locate package
        spec = importlib.util.find_spec(pkg_name)
        if spec is None:
            print(f"❌ Package {pkg_name!r} not found in current environment")
            sys.exit(1)
        pkg_path = pathlib.Path(spec.origin).parent
        print(f"✅ Found {pkg_name} at: {pkg_path}")

        # Check if .libs directory exists and what's in it
        libs_dir = pkg_path / ".libs"
        if libs_dir.exists():
            print(f"📁 .libs directory contents:")
            try:
                result = subprocess.run(["ls", "-la", str(libs_dir)],
                                        capture_output=True, text=True)
                print(result.stdout)
            except Exception as e:
                print(f"   Error listing .libs: {e}")
        else:
            print("❌ .libs directory not found!")

        # List compiled extensions
        exts = list(pkg_path.glob("**/*.so")) + list(pkg_path.glob("**/*.pyd"))
        if not exts:
            print("ℹ️ No compiled extension modules found")
        else:
            print("🔎 Extension modules:")
            for ext in exts:
                print(f"   {ext}")

                # Check RPATH/RUNPATH
                if sys.platform.startswith("linux"):
                    try:
                        print("   📋 RPATH/RUNPATH:")
                        rpath_out = subprocess.check_output(
                            ["readelf", "-d", str(ext)], text=True
                        )
                        for line in rpath_out.split('\n'):
                            if 'RPATH' in line or 'RUNPATH' in line:
                                print(f"      {line.strip()}")
                    except Exception as e:
                        print(f"      (readelf failed: {e})")

                    # Show what RPATH expands to
                    ext_dir = ext.parent
                    print(f"   🎯 RPATH expansion:")
                    print(f"      $ORIGIN resolves to: {ext_dir}")
                    print(f"      $ORIGIN/.libs resolves to: {ext_dir / '.libs'}")
                    print(f"      $ORIGIN/.libs exists: {(ext_dir / '.libs').exists()}")

                    if (ext_dir / '.libs').exists():
                        try:
                            result = subprocess.run(["ls", "-la", str(ext_dir / '.libs')],
                                                    capture_output=True, text=True)
                            print(f"      Contents of $ORIGIN/.libs:")
                            for line in result.stdout.strip().split('\n'):
                                if line.strip():
                                    print(f"        {line}")
                        except Exception as e:
                            print(f"      Error listing $ORIGIN/.libs: {e}")

                # Run ldd
                if sys.platform.startswith("linux"):
                    try:
                        print("   🔗 Library dependencies:")
                        out = subprocess.check_output(["ldd", str(ext)], text=True)
                        for line in out.split('\n'):
                            if line.strip():
                                if 'not found' in line:
                                    print(f"      ❌ {line.strip()}")
                                elif 'librocksdb' in line:
                                    print(f"      🎯 {line.strip()}")
                                else:
                                    print(f"        {line.strip()}")
                    except Exception as e:
                        print(f"   (ldd failed: {e})")
                elif sys.platform == "darwin":
                    try:
                        out = subprocess.check_output(["otool", "-L", str(ext)], text=True)
                        print(out)
                    except Exception as e:
                        print(f"   (otool failed: {e})")
                else:
                    print("   Skipping dependency check (unsupported platform)")

                print()  # Add spacing between extensions

        # Try to actually import the package
        print("🧪 Attempting to import...")
        try:
            imported_module = importlib.import_module(pkg_name)
            print(f"✅ Successfully imported {pkg_name}")

            # If it has common test attributes/methods, try them
            if hasattr(imported_module, '__version__'):
                print(f"   Version: {imported_module.__version__}")
            if hasattr(imported_module, 'test') and callable(imported_module.test):
                print("   Running module test...")
                imported_module.test()

            # Test actual functionality to see if libraries are really working
            print("🚀 Testing basic functionality...")
            try:
                # Try to access any basic attribute or method
                if hasattr(imported_module, '__file__'):
                    print(f"   Module file: {imported_module.__file__}")

                # List available attributes
                attrs = [attr for attr in dir(imported_module) if not attr.startswith('_')]
                if attrs:
                    print(f"   Available public attributes: {', '.join(attrs[:5])}")
                    if len(attrs) > 5:
                        print(f"   ... and {len(attrs) - 5} more")

                    # Try to call something basic if available
                    for attr_name in ['DB', 'RocksDB', 'open', 'create', 'connect']:
                        if hasattr(imported_module, attr_name):
                            attr = getattr(imported_module, attr_name)
                            print(f"   Found {attr_name}: {type(attr)}")
                            break

            except Exception as e:
                print(f"   ⚠️ Error testing functionality: {e}")

        except Exception as e:
            print(f"❌ Failed to import {pkg_name}: {e}")
            print(f"   Error type: {type(e).__name__}")
            import traceback
            print("   Full traceback:")
            traceback.print_exc()

        # Final runtime library resolution test
        print("\n🔍 Runtime library resolution test...")
        try:
            # Use LD_DEBUG to see what's actually happening at runtime
            env = os.environ.copy()
            env['LD_DEBUG'] = 'libs'
            result = subprocess.run([
                sys.executable, '-c',
                f'import {pkg_name}; print("Import successful with LD_DEBUG")'
            ], env=env, capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print("✅ Runtime import successful")
                # Look for librocksdb resolution in the debug output
                for line in result.stderr.split('\n'):
                    if 'librocksdb' in line.lower():
                        print(f"   🎯 {line.strip()}")
            else:
                print("❌ Runtime import failed")
                print(f"   stderr: {result.stderr}")

        except Exception as e:
            print(f"   Runtime test failed: {e}")

        # Alternative: use ldd with the actual Python process
        print("\n🔍 Process-based library check...")
        try:
            # Start python and import the module, then check its memory maps
            result = subprocess.run([
                'python', '-c',
                f'import os; import {pkg_name}; import time; print("PID:", os.getpid()); time.sleep(1)'
            ], capture_output=True, text=True, timeout=10)
            print(f"   Import exit code: {result.returncode}")
            if result.stdout:
                print(f"   stdout: {result.stdout.strip()}")
            if result.stderr:
                print(f"   stderr: {result.stderr.strip()}")
        except Exception as e:
            print(f"   Process test failed: {e}")

    except Exception as e:
        print(f"❌ Error while testing {pkg_name!r}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python smoke_test.py <package_name>")
        sys.exit(1)
    smoke_test(sys.argv[1])
