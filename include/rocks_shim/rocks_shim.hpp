#pragma once
#include <memory>
#include <string>
#include <vector>
#include <optional>

namespace rshim {

struct OpenArgs {
  std::string path;
  bool        read_only         = false;
  bool        create_if_missing = false;
  // profile selects base + optional merge-op suffix, e.g.:
  // "read", "write", "bulk", "bulk_write", and variants like "write:packed24"
  std::string profile = "write";
};

class Iterator {
public:
  virtual ~Iterator() = default;
  virtual void Seek(const std::string& lower) = 0;
  virtual bool Valid() const = 0;
  virtual const std::string& Key() const = 0;   // stable until Next/Seek
  virtual const std::string& Value() const = 0; // stable until Next/Seek
  virtual void Next() = 0;
};

class WriteBatch {
public:
  virtual ~WriteBatch() = default;
  virtual void Put(const std::string& k, const std::string& v) = 0;
  virtual void Delete(const std::string& k) = 0;
  virtual void Merge(const std::string& k, const std::string& v) = 0;
  virtual void Commit() = 0;
  virtual void Discard() {}  // optional
};

class DB {
public:
  static std::shared_ptr<DB> Open(const OpenArgs& args);
  virtual ~DB() = default;

  virtual void Close() = 0;

  [[nodiscard]] virtual bool Get(const std::string& k, std::string* out) = 0;
  virtual void Put(const std::string& k, const std::string& v) = 0;
  virtual void Delete(const std::string& k) = 0;
  virtual void Merge(const std::string& k, const std::string& v) = 0;

  virtual std::shared_ptr<Iterator>   NewIterator() = 0;

  // Allow callers to control WAL/sync per batch (matches db.cc + pybind)
  virtual std::shared_ptr<WriteBatch> NewWriteBatch(bool disable_wal = false, bool sync = false) = 0;

  virtual void FinalizeBulk() {}
  virtual void CompactAll() {}
  virtual void SetProfile(const std::string&) {}
  virtual std::optional<std::string> GetProperty(const std::string&) { return std::nullopt; }
  virtual void IngestExternalFiles(const std::vector<std::string>&, bool /*move*/, bool /*write_global_seqno*/) {}
};

} // namespace rshim
