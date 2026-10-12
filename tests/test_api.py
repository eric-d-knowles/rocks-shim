"""Functional tests of the Python API. Run with:  python -m pytest tests/test_api.py
(or  python tests/test_api.py  without pytest)."""
import struct
import tempfile
import pathlib
import sys

import rocks_shim as rs


def _packed(*triples):
    flat = [x for t in triples for x in t]
    return struct.pack(f"<{len(flat)}Q", *flat)


def _unpack(blob):
    n = len(blob) // 8
    v = struct.unpack(f"<{n}Q", blob)
    return [tuple(v[i:i + 3]) for i in range(0, n, 3)]


def test_put_get_iterate():
    with tempfile.TemporaryDirectory() as d:
        db = rs.open(str(pathlib.Path(d) / "db"), mode="rw", profile="write", create_if_missing=True)
        try:
            with db.write_batch() as wb:
                for i in range(100):
                    wb.put(f"k{i:03d}".encode(), f"v{i}".encode())
            assert db.get(b"k007") == b"v7" and db.get(b"missing") is None
            # default iterator
            it = db.iterator()
            it.seek(b"k050")
            seen = []
            while it.valid() and len(seen) < 3:
                seen.append(it.key()); it.next()
            assert seen == [b"k050", b"k051", b"k052"]
            # scan options: no cache fill, explicit readahead
            it = db.iterator(fill_cache=False, readahead_size=1 << 20)
            it.seek(b"")
            n = 0
            while it.valid():
                n += 1; it.next()
            assert n == 100
        finally:
            db.close()


def test_packed24_merge_and_merge_batch():
    with tempfile.TemporaryDirectory() as d:
        db = rs.open(str(pathlib.Path(d) / "db"), mode="rw", profile="write:packed24", create_if_missing=True)
        try:
            with db.write_batch(disable_wal=True) as wb:
                wb.merge(b"cat", _packed((1990, 1, 1), (2000, 2, 2)))
                wb.merge_batch([(b"cat", _packed((1990, 5, 1))), (b"dog", _packed((1990, 1, 1)))])
            db.finalize_bulk()
            assert _unpack(db.get(b"cat")) == [(1990, 6, 2), (2000, 2, 2)]
            assert _unpack(db.get(b"dog")) == [(1990, 1, 1)]
            db.compact_all()
            assert _unpack(db.get(b"cat")) == [(1990, 6, 2), (2000, 2, 2)]
        finally:
            db.close()


def test_close_with_live_iterator_and_batch():
    """Objects that outlive DB.close() must not crash when collected, and the
    closed handle raises instead of dereferencing a null pointer."""
    with tempfile.TemporaryDirectory() as d:
        db = rs.open(str(pathlib.Path(d) / "db"), mode="rw", create_if_missing=True)
        db.put(b"a", b"1")
        it = db.iterator()
        it.seek(b"a")
        wb = db.write_batch()
        wb.put(b"b", b"2")
        db.close()
        assert it.valid() and it.key() == b"a"      # still backed by the live handle
        try:
            db.get(b"a")
        except RuntimeError as e:
            assert "closed" in str(e)
        else:
            raise AssertionError("get on a closed DB should raise")
        del it, wb                                  # last references: the DB is destroyed here
        db2 = rs.open(str(pathlib.Path(d) / "db"), mode="rw", create_if_missing=True)
        try:
            assert db2.get(b"a") == b"1"
        finally:
            db2.close()


def test_bottommost_level_is_zstd_compressed():
    """The profiles write level 0 uncompressed and compress the bottommost
    level with ZSTD; if ZSTD were not linked in, RocksDB would silently fall
    back to no compression and compaction would not shrink the data."""
    with tempfile.TemporaryDirectory() as d:
        db = rs.open(str(pathlib.Path(d) / "db"), mode="rw", profile="write", create_if_missing=True)
        try:
            with db.write_batch(disable_wal=True) as wb:
                for i in range(20000):
                    wb.put(f"key{i:08d}".encode(), b"the quick brown fox " * 10)
            db.finalize_bulk()
            before = int(db.get_property("rocksdb.total-sst-files-size"))
            db.compact_all()
            after = int(db.get_property("rocksdb.total-sst-files-size"))
            assert before > 2_000_000 and after < before / 5, (before, after)
            assert db.get(b"key00000042") == b"the quick brown fox " * 10
        finally:
            db.close()


def test_live_files_describe_the_key_space():
    with tempfile.TemporaryDirectory() as d:
        db = rs.open(str(pathlib.Path(d) / "db"), mode="rw", profile="write", create_if_missing=True)
        try:
            assert db.live_files() == []                      # nothing flushed yet
            with db.write_batch(disable_wal=True) as wb:
                for i in range(50000):
                    wb.put(f"key{i:08d}".encode(), b"v" * 100)
            db.finalize_bulk()
            files = db.live_files()
            assert files, "flushed data must appear as SST files"
            lo = min(f[0] for f in files)
            hi = max(f[1] for f in files)
            assert lo == b"key00000000" and hi == b"key00049999"
            assert all(isinstance(f[2], int) and f[2] > 0 and isinstance(f[3], int) for f in files)
            db.compact_all()
            assert all(f[3] >= 1 for f in db.live_files())    # compaction moved them off level 0
        finally:
            db.close()


if __name__ == "__main__":
    test_put_get_iterate()
    test_packed24_merge_and_merge_batch()
    test_close_with_live_iterator_and_batch()
    test_bottommost_level_is_zstd_compressed()
    test_live_files_describe_the_key_space()
    print("ok")
    sys.exit(0)
