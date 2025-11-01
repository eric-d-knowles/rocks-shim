#!/usr/bin/env python3
"""Test script for SstFileWriter functionality."""
import tempfile
import shutil
import rocks_shim

def test_sst_writer():
    # Create temporary directories
    sst_dir = tempfile.mkdtemp()
    db_dir = tempfile.mkdtemp()

    try:
        print("1. Creating SST file with SstFileWriter...")
        sst_path = f"{sst_dir}/test.sst"

        # Create and write SST file
        writer = rocks_shim.SstFileWriter()
        writer.open(sst_path)

        # Add some test data (keys must be in sorted order)
        test_data = [
            (b"key1", b"value1"),
            (b"key2", b"value2"),
            (b"key3", b"value3"),
        ]

        for key, value in test_data:
            writer.put(key, value)
            print(f"   Added: {key} -> {value}")

        file_size = writer.file_size()
        print(f"   File size before finish: {file_size} bytes")

        writer.finish()
        final_size = writer.file_size()
        print(f"   File size after finish: {final_size} bytes")
        print(f"✅ SST file created successfully at {sst_path}")

        print("\n2. Opening database and ingesting SST file...")
        db = rocks_shim.DB.open(db_dir, create_if_missing=True)

        # Ingest the SST file
        db.ingest([sst_path], move=False)
        print("✅ SST file ingested successfully")

        print("\n3. Verifying data...")
        for key, expected_value in test_data:
            value = db.get(key)
            if value == expected_value:
                print(f"   ✅ {key} -> {value}")
            else:
                print(f"   ❌ {key} -> expected {expected_value}, got {value}")
                raise ValueError(f"Data mismatch for key {key}")

        print("\n4. Testing context manager...")
        sst_path2 = f"{sst_dir}/test2.sst"
        with rocks_shim.SstFileWriter() as writer2:
            writer2.open(sst_path2)
            writer2.put(b"key4", b"value4")
            # finish() called automatically by __exit__

        db.ingest([sst_path2], move=True)
        value4 = db.get(b"key4")
        if value4 == b"value4":
            print(f"   ✅ Context manager test passed: key4 -> {value4}")
        else:
            raise ValueError(f"Context manager test failed: expected b'value4', got {value4}")

        db.close()
        print("\n✅ All tests passed!")

    finally:
        # Cleanup
        shutil.rmtree(sst_dir, ignore_errors=True)
        shutil.rmtree(db_dir, ignore_errors=True)

if __name__ == "__main__":
    test_sst_writer()
