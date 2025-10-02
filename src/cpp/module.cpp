#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <rocks_shim/rocks_shim.hpp>

namespace py = pybind11;
namespace rs = ::rshim;

PYBIND11_MODULE(rocks_shim, m) {
  m.doc() = "High-performance RocksDB shim for Python";

  // --- Iterator Bindings ---
  py::class_<rs::Iterator, std::shared_ptr<rs::Iterator>>(m, "Iterator")
    .def("seek", &rs::Iterator::Seek, py::arg("lower"), py::call_guard<py::gil_scoped_release>())
    .def("valid", &rs::Iterator::Valid)
    .def("key", [](const rs::Iterator& self) {
        auto key_sv = self.Key();
        return py::bytes(key_sv.data(), key_sv.size());
     })
    .def("value", [](const rs::Iterator& self) {
        auto val_sv = self.Value();
        return py::bytes(val_sv.data(), val_sv.size());
     })
    .def("next", &rs::Iterator::Next, py::call_guard<py::gil_scoped_release>());

  // --- WriteBatch Bindings ---
  py::class_<rs::WriteBatch, std::shared_ptr<rs::WriteBatch>>(m, "WriteBatch")
    .def("__enter__", [](std::shared_ptr<rs::WriteBatch> self){ return self; })
    .def("__exit__",  [](rs::WriteBatch& self, py::object exc_type, py::object, py::object){
        if (exc_type.is_none()) {
          py::gil_scoped_release release;
          self.Commit();
        } else {
          self.Discard();
        }
        return false;
    })
    .def("put",    [](rs::WriteBatch& self, py::bytes k, py::bytes v){ self.Put(std::string(k), std::string(v)); })
    .def("delete", [](rs::WriteBatch& self, py::bytes k){ self.Delete(std::string(k)); })
    .def("merge",  [](rs::WriteBatch& self, py::bytes k, py::bytes v){ self.Merge(std::string(k), std::string(v)); });

  // --- DB Bindings ---
  py::class_<rs::DB, std::shared_ptr<rs::DB>>(m, "DB")
    .def_static("open",
      [](const std::string& path, bool read_only, bool create_if_missing, const std::string& profile){
        rs::OpenArgs a;
        a.path = path;
        a.read_only = read_only;
        a.create_if_missing = create_if_missing;
        a.profile = profile.empty() ? (read_only ? "read" : "write") : profile;

        py::gil_scoped_release release;
        return rs::DB::Open(a);
      },
      py::arg("path"), py::kw_only(), py::arg("read_only")=false, py::arg("create_if_missing")=false, py::arg("profile") = "")
    .def("__enter__", [](std::shared_ptr<rs::DB> self){ return self; })
    .def("__exit__",  [](rs::DB& self, py::object, py::object, py::object){ self.Close(); return false; })
    .def("close", &rs::DB::Close, py::call_guard<py::gil_scoped_release>())
    .def("__getitem__", [](rs::DB& self, py::bytes k) {
        py::gil_scoped_release release;
        std::string out;
        if (self.Get(std::string(k), &out)) {
            return py::bytes(out);
        }
        throw py::key_error("Key not found");
    })
    .def("get", [](rs::DB& self, py::bytes k) -> py::object {
        py::gil_scoped_release release;
        std::string out;
        if (self.Get(std::string(k), &out)) {
            return py::bytes(out);
        }
        return py::none();
      })
    .def("put",    [](rs::DB& self, py::bytes k, py::bytes v){ py::gil_scoped_release r; self.Put(std::string(k), std::string(v)); })
    .def("delete", [](rs::DB& self, py::bytes k){ py::gil_scoped_release r; self.Delete(std::string(k)); })
    .def("merge",  [](rs::DB& self, py::bytes k, py::bytes v){ py::gil_scoped_release r; self.Merge(std::string(k), std::string(v)); })
    .def("iterator", &rs::DB::NewIterator, py::keep_alive<0,1>())
    .def("write_batch", &rs::DB::NewWriteBatch,
         py::kw_only(), py::arg("disable_wal") = false, py::arg("sync") = false,
         py::keep_alive<0,1>())
    .def("finalize_bulk", &rs::DB::FinalizeBulk, py::call_guard<py::gil_scoped_release>())
    .def("compact_all", &rs::DB::CompactAll, py::call_guard<py::gil_scoped_release>())
    .def("compact_range", [](rs::DB& self, py::object start, py::object end, bool exclusive) {
        py::gil_scoped_release release;
        std::optional<std::string> start_key;
        std::optional<std::string> end_key;

        if (!start.is_none()) {
          start_key = std::string(py::bytes(start));
        }
        if (!end.is_none()) {
          end_key = std::string(py::bytes(end));
        }

        self.CompactRange(start_key, end_key, exclusive);
      },
      py::arg("start") = py::none(), py::arg("end") = py::none(), py::arg("exclusive") = true,
      "Compact a specific key range")
    .def("get_property", &rs::DB::GetProperty, py::arg("name"))
    .def("ingest", &rs::DB::IngestExternalFiles,
         py::arg("paths"), py::kw_only(), py::arg("move")=true, py::arg("write_global_seqno")=false);

  // Module-level open function for api.py compatibility
  m.def("open",
    [](const std::string& path, const std::string& mode, bool create_if_missing, const std::string& profile){
      rs::OpenArgs a;
      a.path = path;
      a.read_only = (mode == "r");
      a.create_if_missing = create_if_missing;
      a.profile = profile.empty() ? (a.read_only ? "read" : "write") : profile;

      py::gil_scoped_release release;
      return rs::DB::Open(a);
    },
    py::arg("path"), py::kw_only(), py::arg("mode")="rw",
    py::arg("create_if_missing")=false, py::arg("profile") = "");
}