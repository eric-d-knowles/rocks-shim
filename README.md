# rocks-shim

**High-performance Python bindings for RocksDB with bundled dependencies**

`rocks-shim` provides optimized Python bindings for RocksDB, a persistent key-value store for fast storage. Unlike other Python RocksDB bindings, rocks-shim links RocksDB and its compression dependencies (Snappy, LZ4, ZSTD) statically into a single extension module, eliminating system dependency issues and simplifying deployment.

## Features

- **Zero system dependencies** - RocksDB and all compression libraries bundled in wheel
- **Optimized for performance** - C++ implementation with minimal Python overhead
- **Batch operations** - `PutBatch` and `MergeBatch` for reduced Python→C++ call overhead
- **Custom merge operators** - Built-in `packed24` merge operator for efficient streaming data
- **Configurable profiles** - Pre-tuned `write` (bulk ingest) and `read` (serving) settings
- **SST file writing** - Direct creation of RocksDB SST files for bulk ingestion
- **Portable wheels** - Works across different Linux distributions without recompilation

## Installation

Wheels for Linux x86_64 (Python 3.11-3.13) are attached to each
[release](https://github.com/eric-d-knowles/rocks-shim/releases); install
the one for your Python version, e.g.

```bash
pip install https://github.com/eric-d-knowles/rocks-shim/releases/download/v0.7.0/rocks_shim-0.7.0-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
```

Or build from source (RocksDB, Snappy, LZ4 and ZSTD are downloaded and built
during the install, which takes 15-30 minutes; they are kept under `build/`
so a rebuild is fast):

```bash
git clone https://github.com/eric-d-knowles/rocks-shim.git
cd rocks-shim
pip install .
```

### Build Requirements

- Python 3.9+
- CMake 3.20+ and Ninja (installed automatically by scikit-build-core if missing)
- C++17 compiler
- network access to github.com (release tarballs; pass
  `-C cmake.define.ROCKS_SHIM_VENDOR_GIT=ON` to fetch by git clone instead)

### Releasing

Publish a GitHub release with a version tag (e.g. `v0.7.0`, matching
`pyproject.toml`). The `wheels` workflow builds the manylinux wheels with
[cibuildwheel](https://cibuildwheel.pypa.io) inside the official manylinux
container, runs `tests/` against each wheel, and attaches them to the
release. "Run workflow" on the Actions tab builds them as an artifact
without a release. The same build can be run locally with Docker:
`pipx run cibuildwheel --platform linux`.

## Quick Start

### Basic Operations

```python
import rocks_shim as rs

# Open database
db = rs.DB.Open(rs.OpenArgs(
    path="/path/to/db",
    create_if_missing=True,
    profile="write"  # "write", "read" or "scan"
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
it = db.iterator()
it.seek(b"start_key")   # position the iterator

while it.valid():
    key = it.key()        # bytes
    value = it.value()    # bytes
    print(f"{key}: {value}")
    it.next()

# A one-pass scan should not pull every block through the block cache
# (each profile reserves a 4 GiB cache per process, and a scan would fill
# it). Workers that scan a key range once should open their iterator with
# fill_cache=False; readahead_size (bytes) adds explicit readahead.
it = db.iterator(fill_cache=False, readahead_size=2 << 20)
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

rocks-shim includes pre-configured profiles for the two phases of a corpus
database's life:

- **`write`** - bulk ingest. Auto-compaction off, 1 GiB memtables, level 0
  written uncompressed, no Bloom filters. Call `finalize_bulk()` and then
  `compact_all()` when the load is complete: the compaction writes the
  bottommost level with ZSTD (level 3).
- **`read`** - serving lookups for a long-lived process. Every file is
  opened at start with its index and filter pinned, direct I/O, partitioned
  Bloom filters, 4 GiB block cache. Memory grows with the size of the
  database.
- **`scan`** - one pass over a key range, then close: a worker that filters
  its share of a database, a frequency count, a partitioning step. Only the
  files the scan touches are kept open (`max_open_files` 256), nothing is
  pinned, 64 MiB block cache; open the iterator with `fill_cache=False` and
  a `readahead_size`. About 200 MB per process whatever the database's size.

Both accept a `:packed24` suffix (`write:packed24`) that installs the
`packed24` merge operator described below.

```python
# Select profile when opening database
db = rs.DB.Open(rs.OpenArgs(
    path="/path/to/db",
    create_if_missing=True,
    profile="read"
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

### Key distribution without a scan

```python
# One tuple per SST file: (smallest_key, largest_key, size_bytes, level).
# Sorting by key and accumulating sizes gives density-balanced key ranges
# for parallel workers in milliseconds, without reading the data.
for lo, hi, size, level in db.live_files():
    ...
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
4. **Choose the right profile** - Use the `write` profile for loading, `read` for read-heavy workloads
5. **Compact after bulk operations** - Call `CompactAll()` after large imports to optimize read performance

## Architecture

rocks-shim uses a two-layer design:

1. **C++ layer** - Thin wrapper around RocksDB's C++ API with optimized batch operations
2. **Python bindings** - pybind11-based interface exposing C++ functionality

RocksDB 10.5.1, Snappy 1.1.10, LZ4 1.9.4 and ZSTD 1.5.6 are built from source and linked statically into the extension module, so the wheel is a single self-contained `.so` with no bundled shared libraries and no RPATH dependencies. RocksDB's symbols are kept private to the module.

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
  version = {0.7.0}
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

## Support and Maintenance

This project is provided as-is for research and development purposes. While issues and pull requests are welcome, there is no guarantee of response time or ongoing maintenance. The code is shared in the spirit of open science, but support is provided on a best-effort basis only.

For critical production use, consider forking and maintaining your own version.
