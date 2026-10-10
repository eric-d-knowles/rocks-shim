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


if __name__ == "__main__":
    test_put_get_iterate()
    test_packed24_merge_and_merge_batch()
    print("ok")
    sys.exit(0)
