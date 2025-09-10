#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <rocks_shim/rocks_shim.hpp>
#include <rocksdb/env.h>

namespace py = pybind11;
namespace rs = ::rshim;  // adjust if your namespace differs

static inline py::bytes to_bytes(const std::string& s) { return py::bytes(s.data(), s.size()); }

PYBIND11_MODULE(rocks_shim, m) {
  m.doc() = "Minimal RocksDB shim (FetchContent, static codecs)";

  py::class_<rs::Iterator, std::shared_ptr<rs::Iterator>>(m, "Iterator")
    .def("seek",  [](rs::Iterator& it, py::bytes lower){ it.Seek(std::string(lower)); })
    .def("valid", &rs::Iterator::Valid)
    .def("key",   [](rs::Iterator& it){ return to_bytes(it.Key()); })
    .def("value", [](rs::Iterator& it){ return to_bytes(it.Value()); })
    .def("next",  &rs::Iterator::Next);

  py::class_<rs::WriteBatch, std::shared_ptr<rs::WriteBatch>>(m, "WriteBatch")
    .def("__enter__", [](std::shared_ptr<rs::WriteBatch> self){ return self; })
    .def("__exit__",  [](rs::WriteBatch& self, py::object et, py::object, py::object){
        if (et.is_none()) {
          py::gil_scoped_release _g;
          self.Commit();
        } else {
          self.Discard();
        }
        return false;
    })
    .def("put",    [](rs::WriteBatch& wb, py::bytes k, py::bytes v){ wb.Put(std::string(k), std::string(v)); })
    .def("delete", [](rs::WriteBatch& wb, py::bytes k){ wb.Delete(std::string(k)); })
    .def("merge",  [](rs::WriteBatch& wb, py::bytes k, py::bytes v){ wb.Merge(std::string(k), std::string(v)); });

  py::class_<rs::DB, std::shared_ptr<rs::DB>>(m, "DB")
    .def_static("open",
      [](const std::string& path, bool read_only, bool create_if_missing){
        rs::OpenArgs a; a.path = path; a.read_only = read_only; a.create_if_missing = create_if_missing;
        a.profile = read_only ? "read" : "write";
        return rs::DB::Open(a);
      },
      py::arg("path"), py::kw_only(), py::arg("read_only")=false, py::arg("create_if_missing")=false)
    .def("__enter__", [](std::shared_ptr<rs::DB> self){ return self; })
    .def("__exit__",  [](rs::DB& self, py::object, py::object, py::object){ self.Close(); return false; })
    .def("close", &rs::DB::Close)
    .def("get",   [](rs::DB& db, py::bytes k)->py::object{
        py::gil_scoped_release _g;
        std::string out;
        if (!db.Get(std::string(k), &out)) return py::none();
        return to_bytes(out);
      })
    .def("put",    [](rs::DB& db, py::bytes k, py::bytes v){ py::gil_scoped_release _g; db.Put(std::string(k), std::string(v)); })
    .def("delete", [](rs::DB& db, py::bytes k){ py::gil_scoped_release _g; db.Delete(std::string(k)); })
    .def("merge",  [](rs::DB& db, py::bytes k, py::bytes v){ py::gil_scoped_release _g; db.Merge(std::string(k), std::string(v)); })
    .def("iterator",     &rs::DB::NewIterator,   py::keep_alive<0,1>())
    // NEW: per-batch WAL/sync controls
    .def("write_batch",
         &rs::DB::NewWriteBatch,
         py::kw_only(), py::arg("disable_wal") = false, py::arg("sync") = false,
         py::keep_alive<0,1>())
    .def("finalize_bulk",&rs::DB::FinalizeBulk,  py::call_guard<py::gil_scoped_release>())
    .def("compact_all",  &rs::DB::CompactAll,    py::call_guard<py::gil_scoped_release>())
    .def("set_profile",  &rs::DB::SetProfile)
    .def("get_property", &rs::DB::GetProperty)
    .def("ingest", &rs::DB::IngestExternalFiles,
         py::arg("paths"), py::kw_only(), py::arg("move")=true, py::arg("write_global_seqno")=false,
         py::call_guard<py::gil_scoped_release>());

  // module-level convenience
  m.def("open",
    [](const std::string& path, std::string mode, std::string profile, bool create_if_missing){
      rs::OpenArgs a; a.path = path; a.read_only = (mode == "ro");
      a.create_if_missing = create_if_missing && !a.read_only;
      a.profile = profile.empty() ? (a.read_only ? "read" : "write") : profile;
      return rs::DB::Open(a);
    },
    py::arg("path"), py::kw_only(), py::arg("mode")="rw", py::arg("profile")="write", py::arg("create_if_missing")=true);
}
