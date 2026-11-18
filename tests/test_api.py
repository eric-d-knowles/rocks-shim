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


def test_scan_profile_reads_a_database_written_by_the_write_profile():
    """The scan profile is for one-pass reads: it must open a database the
    write profile produced (packed24 merges included), iterate a range, and
    report its live files; and it must not reserve the serving profile's
    4 GiB block cache."""
    with tempfile.TemporaryDirectory() as d:
        path = str(pathlib.Path(d) / "db")
        db = rs.open(path, mode="rw", profile="write:packed24", create_if_missing=True)
        with db.write_batch(disable_wal=True) as wb:
            for i in range(20000):
                wb.merge(f"key{i:08d}".encode(), _packed((1990, 1, 1)))
                wb.merge(f"key{i:08d}".encode(), _packed((1990, 2, 1), (2000, 1, 1)))
        db.finalize_bulk(); db.compact_all(); db.close()

        db = rs.open(path, mode="r", profile="scan:packed24")
        try:
            it = db.iterator(fill_cache=False, readahead_size=2 << 20)
            it.seek(b"key00010000")
            n = 0
            while it.valid() and it.key() < b"key00010100":
                n += 1; it.next()
            assert n == 100
            assert _unpack(db.get(b"key00000042")) == [(1990, 3, 2), (2000, 1, 1)]
            assert db.live_files()
            cap = db.get_property("rocksdb.block-cache-capacity")
            assert cap is not None and int(cap) <= 64 << 20
        finally:
            db.close()


def test_sst_merge_entries_are_summed_after_ingest():
    """The pivot stage writes merge operands into SST files from many workers;
    ingested into a packed24 database they must sum with each other and with
    what the database already holds, and compressed files must ingest too."""
    with tempfile.TemporaryDirectory() as d:
        db = rs.open(str(pathlib.Path(d) / "db"), mode="rw", profile="write:packed24", create_if_missing=True)
        try:
            with db.write_batch(disable_wal=True) as wb:
                wb.merge(b"cat", _packed((1990, 1, 1)))
            db.finalize_bulk()
            paths = []
            for i, comp in enumerate(("zstd", "lz4", "none")):
                w = rs.SstFileWriter(compression=comp)
                p = str(pathlib.Path(d) / f"part{i}.sst")
                w.open(p)
                w.merge(b"cat", _packed((1990, 10, 1)))
                w.merge(b"dog", _packed((2000, 1, 1)))
                w.finish()
                paths.append(p)
            for p in paths:
                db.ingest([p], move=True)
            db.compact_all()
            assert _unpack(db.get(b"cat")) == [(1990, 31, 4)]
            assert _unpack(db.get(b"dog")) == [(2000, 3, 3)]
        finally:
            db.close()
    try:
        rs.SstFileWriter(compression="gzip")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown compression must be rejected")


def test_merge_sst_files_combines_parts_into_one_file():
    """Workers spill many small sorted files of merge operands; merging them
    into one file per worker keeps the number of level-0 files small enough
    for the final compaction. Keys shared by parts must be summed."""
    with tempfile.TemporaryDirectory() as d:
        parts = []
        for i, rows in enumerate(([(b"ant", [(1990, 1, 1)]), (b"cat", [(1990, 2, 1), (2000, 1, 1)])],
                                  [(b"cat", [(1990, 3, 1)]), (b"dog", [(1995, 1, 1)])],
                                  [(b"cat", [(1980, 1, 1)]), (b"zebra", [(2000, 1, 1)])])):
            w = rs.SstFileWriter(compression="lz4")
            p = str(pathlib.Path(d) / f"part{i}.sst")
            w.open(p)
            for k, triples in rows:
                w.merge(k, _packed(*triples))
            w.finish()
            parts.append(p)
        out = str(pathlib.Path(d) / "unit.sst")
        n = rs.merge_sst_files(parts, out, compression="zstd", merge_operator="packed24")
        assert n == 4                                               # ant, cat, dog, zebra
        assert all(pathlib.Path(p).exists() for p in parts)         # parts are left to the caller
        db = rs.open(str(pathlib.Path(d) / "db"), mode="rw", profile="write:packed24", create_if_missing=True)
        try:
            with db.write_batch(disable_wal=True) as wb:
                wb.merge(b"cat", _packed((1990, 10, 10)))           # what the database already holds
            db.finalize_bulk()
            db.ingest([out], move=True)
            db.compact_all()
            assert _unpack(db.get(b"cat")) == [(1980, 1, 1), (1990, 15, 12), (2000, 1, 1)]
            assert _unpack(db.get(b"ant")) == [(1990, 1, 1)] and _unpack(db.get(b"zebra")) == [(2000, 1, 1)]
            assert int(db.get_property("rocksdb.estimate-num-keys")) == 4
        finally:
            db.close()
        try:
            rs.merge_sst_files(parts, str(pathlib.Path(d) / "x.sst"), merge_operator="none")
        except RuntimeError:
            pass
        else:
            raise AssertionError("a key in several parts must be rejected without an operator")


def _open(d, name="db", **kw):
    return rs.open(str(pathlib.Path(d) / name), mode="rw", create_if_missing=True, **kw)


def _raises(kind, fn):
    try:
        fn()
    except kind as exc:
        return str(exc)
    raise AssertionError(f"expected {kind.__name__}")


def test_merge_operator_is_named_on_its_own_or_as_the_profile_suffix():
    assert rs.merge_operators() == ["packed24", "uint64add", "stringappend", "max", "put"]
    with tempfile.TemporaryDirectory() as d:
        # the argument and the suffix install the same operator
        for i, kw in enumerate([dict(profile="write", merge_operator="packed24"), dict(profile="write:packed24"),
                                dict(profile="write:packed24", merge_operator="packed24"),
                                dict(merge_operator="packed24")]):
            db = _open(d, f"db{i}", **kw)
            try:
                db.merge(b"cat", _packed((1990, 1, 1)))
                db.merge(b"cat", _packed((1990, 5, 1), (2000, 2, 2)))
                assert _unpack(db.get(b"cat")) == [(1990, 6, 2), (2000, 2, 2)]
            finally:
                db.close()
        # naming two different operators, or one that does not exist, is an error
        assert "different merge operators" in _raises(
            ValueError, lambda: _open(d, "x1", profile="write:packed24", merge_operator="uint64add"))
        assert "Unknown merge operator: 'packed42'" in _raises(ValueError, lambda: _open(d, "x2", profile="write:packed42"))
        assert "Valid: packed24, uint64add" in _raises(ValueError, lambda: _open(d, "x3", merge_operator="sum"))
        # "none" and "" mean no operator
        db = _open(d, "plain", profile="write", merge_operator="none")
        db.put(b"k", b"v")
        assert db.get(b"k") == b"v"
        db.close()


def test_rocksdb_stock_operators():
    with tempfile.TemporaryDirectory() as d:
        cases = {
            "uint64add": ([struct.pack("<Q", 5), struct.pack("<Q", 7), struct.pack("<Q", 30)], struct.pack("<Q", 42)),
            "stringappend": ([b"a", b"b", b"c"], b"a,b,c"),
            "max": ([b"pear", b"apple", b"plum"], b"plum"),
            "put": ([b"first", b"second", b"last"], b"last"),
        }
        for name, (operands, expected) in cases.items():
            db = _open(d, name, profile="write", merge_operator=name)
            try:
                for v in operands:
                    db.merge(b"k", v)
                assert db.get(b"k") == expected, (name, db.get(b"k"))
                db.finalize_bulk()
                db.compact_all()
                assert db.get(b"k") == expected, (name, "after compaction", db.get(b"k"))
            finally:
                db.close()


def test_packed24_refuses_a_value_that_is_not_whole_records():
    """The operator reads fixed 24-byte records. A value of another length
    used to be read past its end in a release build; now the merge fails."""
    with tempfile.TemporaryDirectory() as d:
        db = _open(d, profile="write:packed24")
        try:
            db.merge(b"good", _packed((1990, 1, 1)))
            db.merge(b"bad", _packed((1990, 1, 1)))
            db.merge(b"bad", b"x" * 23)
            db.merge(b"alone", b"y" * 25)
            assert _unpack(db.get(b"good")) == [(1990, 1, 1)]
            _raises(RuntimeError, lambda: db.get(b"bad"))
            _raises(RuntimeError, lambda: db.get(b"alone"))
            db.merge(b"empty", b"")                       # an empty operand is whole records: none
            db.merge(b"empty", _packed((2001, 3, 2)))
            assert _unpack(db.get(b"empty")) == [(2001, 3, 2)]
        finally:
            db.close()


def _write_sst(path, entries):
    w = rs.SstFileWriter(compression="zstd")
    w.open(str(path))
    for k, v in entries:
        w.merge(k, v)
    w.finish()


def test_merge_sst_files_uses_the_named_operator_and_keeps_the_order_of_the_parts():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        # counters
        _write_sst(d / "a.sst", [(b"k1", struct.pack("<Q", 1)), (b"k2", struct.pack("<Q", 10))])
        _write_sst(d / "b.sst", [(b"k2", struct.pack("<Q", 5)), (b"k3", struct.pack("<Q", 7))])
        n = rs.merge_sst_files([str(d / "a.sst"), str(d / "b.sst")], str(d / "sum.sst"), merge_operator="uint64add")
        assert n == 3
        db = _open(d, "sum", profile="write", merge_operator="uint64add")
        db.ingest([str(d / "sum.sst")])
        assert [struct.unpack("<Q", db.get(k))[0] for k in (b"k1", b"k2", b"k3")] == [1, 15, 7]
        db.close()
        # an operator for which order matters sees the parts in the order given
        for i, word in enumerate([b"one", b"two", b"three", b"four"]):
            _write_sst(d / f"p{i}.sst", [(b"k", word), (f"only{i}".encode(), word)])
        parts = [str(d / f"p{i}.sst") for i in range(4)]
        for order, expected in ((parts, b"one,two,three,four"), (parts[::-1], b"four,three,two,one")):
            out = d / f"joined{len(expected)}{order is parts}.sst"
            assert rs.merge_sst_files(order, str(out), merge_operator="stringappend") == 5
            db = _open(d, out.stem, profile="write", merge_operator="stringappend")
            db.ingest([str(out)])
            assert db.get(b"k") == expected, db.get(b"k")
            db.close()
        # unknown names are refused; without an operator parts of merge entries cannot be read at all
        assert "Unknown merge operator" in _raises(
            ValueError, lambda: rs.merge_sst_files(parts, str(d / "x.sst"), merge_operator="sum"))
        assert "merge_operator" in _raises(
            RuntimeError, lambda: rs.merge_sst_files(parts, str(d / "y.sst"), merge_operator="none"))
        # packed24 refuses a part that holds a malformed value (the part's reader fails on it)
        _write_sst(d / "m1.sst", [(b"k", _packed((1990, 1, 1)))])
        _write_sst(d / "m2.sst", [(b"k", b"z" * 23)])
        _raises(RuntimeError, lambda: rs.merge_sst_files([str(d / "m1.sst"), str(d / "m2.sst")], str(d / "z.sst"),
                                                         merge_operator="packed24"))
        # the operator has no default: only the caller knows what the parts hold
        assert "merge_operator" in _raises(TypeError, lambda: rs.merge_sst_files(parts, str(d / "w.sst")))


if __name__ == "__main__":
    test_put_get_iterate()
    test_packed24_merge_and_merge_batch()
    test_close_with_live_iterator_and_batch()
    test_bottommost_level_is_zstd_compressed()
    test_live_files_describe_the_key_space()
    test_scan_profile_reads_a_database_written_by_the_write_profile()
    test_sst_merge_entries_are_summed_after_ingest()
    test_merge_sst_files_combines_parts_into_one_file()
    test_merge_operator_is_named_on_its_own_or_as_the_profile_suffix()
    test_rocksdb_stock_operators()
    test_packed24_refuses_a_value_that_is_not_whole_records()
    test_merge_sst_files_uses_the_named_operator_and_keeps_the_order_of_the_parts()
    print("ok")
    sys.exit(0)
