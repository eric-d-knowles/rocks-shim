# rocks-shim

**High-performance Python bindings for RocksDB with bundled dependencies**

`rocks-shim` provides optimized Python bindings for RocksDB, a persistent key-value store for fast storage. Unlike other Python RocksDB bindings, rocks-shim bundles RocksDB and its compression dependencies (Snappy, LZ4, Zstandard) into a self-contained wheel, eliminating system dependency issues and simplifying deployment.

## Features

- **Zero system dependencies** - RocksDB and all compression libraries bundled in wheel
- **Optimized for performance** - C++ implementation with minimal Python overhead
- **Batch operations** - `PutBatch` and `MergeBatch` for reduced Python→C++ call overhead
- **Custom merge operators** - Built-in `packed24` merge operator for efficient streaming data
- **Configurable profiles** - Pre-tuned settings for read-heavy, write-heavy, or bulk operations
- **SST file writing** - Direct creation of RocksDB SST files for bulk ingestion
- **Portable wheels** - Works across different Linux distributions without recompilation

## Installation

```bash
pip install https://github.com/eric-d-knowles/rocks-shim/releases/download/0.3.0/rocks_shim-0.3.0-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
```

Or build from source:

```bash
git clone https://github.com/eric-d-knowles/rocks-shim.git
cd rocks-shim
pip install .
```

### Build Requirements

- Python 3.8+
- CMake 3.20+
- C++17 compatible compiler
- pybind11 2.12+

## Quick Start

### Basic Operations

```python
import rocks_shim as rs

# Open database
db = rs.DB.Open(rs.OpenArgs(
    path="/path/to/db",
    create_if_missing=True,
    profile="write"  # "write", "read", or "bulk"
))

# Put/Get
db.Put("key1", "value1")
value = db.Get("key1")  # Returns value or None

# Delete
db.Delete("key1")

# Close
db.Close()
```

### Iteration

```python
# Iterate over keys
it = db.NewIterator()
it.Seek("start_key")  # Position iterator

while it.Valid():
    key = it.Key()      # Returns bytes-like view
    value = it.Value()  # Returns bytes-like view
    print(f"{key}: {value}")
    it.Next()
```

### Batch Operations

```python
# Use WriteBatch for better performance
batch = db.NewWriteBatch(disable_wal=False, sync=False)

# Individual operations
batch.Put("key1", "value1")
batch.Put("key2", "value2")

# Batch operations (much faster for many items)
items = [("key3", "value3"), ("key4", "value4")]
batch.PutBatch(items)

# Commit all operations
batch.Commit()
```

### Merge Operations

```python
# Use Merge for append/accumulate operations
db.Merge("counter", "value1")
db.Merge("counter", "value2")

# Batch merge
items = [("counter", "value3"), ("counter", "value4")]
batch.MergeBatch(items)
batch.Commit()
```

### SST File Writing

```python
# Create SST files directly for bulk ingestion
writer = rs.SstFileWriter.Create()
writer.Open("/path/to/file.sst")

# Add keys in sorted order
writer.Put("key1", "value1")
writer.Put("key2", "value2")
writer.Put("key3", "value3")

writer.Finish()
file_size = writer.FileSize()

# Ingest into database
db.IngestExternalFiles(
    ["/path/to/file.sst"],
    move=True,              # Move file instead of copy
    write_global_seqno=True # Assign sequence numbers
)
```

## Profiles

rocks-shim includes pre-configured profiles optimized for different workloads:

- **`write`** - Default profile for general write-heavy workloads
  - Optimized block cache and write buffer
  - Balanced compression settings
  
- **`read`** - Optimized for read-heavy workloads
  - Larger block cache
  - More aggressive compression
  
- **`bulk`** - Optimized for bulk data loading
  - Disabled WAL
  - Large write buffers
  - Minimal compaction during writes

```python
# Select profile when opening database
db = rs.DB.Open(rs.OpenArgs(
    path="/path/to/db",
    create_if_missing=True,
    profile="bulk"
))
```

## Advanced Features

### Compaction

```python
# Compact entire database
db.CompactAll()

# Compact a range
db.CompactRange(
    start="key_start",
    end="key_end",
    exclusive=True  # Exclude endpoints
)
```

### Database Properties

```python
# Get RocksDB statistics
stats = db.GetProperty("rocksdb.stats")
if stats:
    print(stats)

# Get approximate size
size = db.GetProperty("rocksdb.total-sst-files-size")
```

### Custom Merge Operator: packed24

The bundled `packed24` merge operator efficiently merges sorted streams of 24-byte records (8-byte key + 8-byte count + 8-byte volume). This is optimized for time-series data with frequency counts.

```python
# Using packed24 requires opening database with "write:packed24" profile
db = rs.DB.Open(rs.OpenArgs(
    path="/path/to/db",
    create_if_missing=True,
    profile="write:packed24"
))

# Each value is 24 bytes: key (8) + count (8) + volume (8)
# Values must be sorted by the first 8 bytes
import struct

record = struct.pack("<QQQ", year, count, volume)
db.Merge("ngram_key", record)
```

## Performance Tips

1. **Use batch operations** - `PutBatch` and `MergeBatch` are significantly faster than individual `Put`/`Merge` calls
2. **Disable WAL for bulk loads** - Use `NewWriteBatch(disable_wal=True)` when durability isn't critical
3. **Use SST file ingestion** - For very large bulk loads, creating SST files externally and ingesting is fastest
4. **Choose the right profile** - Use `bulk` profile for initial data loading, `read` for read-heavy workloads
5. **Compact after bulk operations** - Call `CompactAll()` after large imports to optimize read performance

## Architecture

rocks-shim uses a two-layer design:

1. **C++ layer** - Thin wrapper around RocksDB's C++ API with optimized batch operations
2. **Python bindings** - pybind11-based interface exposing C++ functionality

All dependencies (RocksDB 10.5.1, Snappy 1.1.10, LZ4 1.9.4, Zstandard) are statically linked and bundled in the wheel with proper RPATH configuration for portability.

## Comparison with python-rocksdb

| Feature | rocks-shim | python-rocksdb |
|---------|-----------|----------------|
| Bundled dependencies | ✅ Yes | ❌ No (requires system RocksDB) |
| Batch operations | ✅ Optimized | ⚠️ Basic |
| Custom merge operators | ✅ Built-in packed24 | ❌ Limited |
| SST file writing | ✅ Yes | ❌ No |
| Wheel portability | ✅ manylinux2014 | ⚠️ Platform-specific |
| Configuration profiles | ✅ Pre-tuned | ❌ Manual |

## Citation

If you use rocks-shim in your research, please cite it:

```bibtex
@software{knowles2024rocksshim,
  author = {Knowles, Eric D.},
  title = {rocks-shim: Python bindings for RocksDB with optimized performance},
  year = {2024},
  url = {https://github.com/eric-d-knowles/rocks-shim},
  version = {0.3.0}
}
```

## License

Licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please open an issue or pull request on GitHub.

## Links

- **GitHub**: https://github.com/eric-d-knowles/rocks-shim
- **RocksDB**: https://rocksdb.org/
- **Used by**: [chrono-text](https://github.com/eric-d-knowles/chrono-text) - Tools for temporal linguistic analysis
