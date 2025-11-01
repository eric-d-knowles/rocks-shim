#pragma once
#include <memory>       // For std::shared_ptr
#include <string>       // For std::string
#include <string_view>  // For std::string_view
#include <vector>       // For std::vector
#include <optional>     // For std::optional

namespace rshim {

struct OpenArgs {
  std::string path;
  bool        read_only         = false;
  bool        create_if_missing = false;
  std::string profile = "write";
};

class Iterator {
public:
  virtual ~Iterator() = default;
  virtual void Seek(const std::string& lower) = 0;
  virtual bool Valid() const = 0;
  virtual std::string_view Key() const = 0;
  virtual std::string_view Value() const = 0;
  virtual void Next() = 0;
};

class WriteBatch {
public:
  virtual ~WriteBatch() = default;
  virtual void Put(const std::string& k, const std::string& v) = 0;
  virtual void Delete(const std::string& k) = 0;
  virtual void Merge(const std::string& k, const std::string& v) = 0;

  // Batch operations for reduced Python→C++ overhead
  virtual void PutBatch(const std::vector<std::pair<std::string, std::string>>& items) = 0;
  virtual void MergeBatch(const std::vector<std::pair<std::string, std::string>>& items) = 0;

  virtual void Commit() = 0;
  virtual void Discard() {}
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

  // Allow callers to control WAL/sync per batch
  virtual std::shared_ptr<WriteBatch> NewWriteBatch(bool disable_wal = false, bool sync = false) = 0;

  virtual void FinalizeBulk() {}
  virtual void CompactAll() {}
  virtual void CompactRange(const std::optional<std::string>& start,
                           const std::optional<std::string>& end,
                           bool exclusive = true) {}  // Added exclusive parameter with default true
  virtual std::optional<std::string> GetProperty(const std::string&) { return std::nullopt; }
  virtual void IngestExternalFiles(const std::vector<std::string>&, bool /*move*/, bool /*write_global_seqno*/) {}
};

class SstFileWriter {
public:
  static std::shared_ptr<SstFileWriter> Create();
  virtual ~SstFileWriter() = default;

  virtual void Open(const std::string& file_path) = 0;
  virtual void Put(const std::string& key, const std::string& value) = 0;
  virtual void Finish() = 0;
  virtual uint64_t FileSize() = 0;
};

} // namespace rshim