// src/cpp/db.cc
#include <rocks_shim/rocks_shim.hpp>
#include <rocks_shim/packed24_merge.hpp>

#include <rocksdb/cache.h>
#include <rocksdb/db.h>
#include <rocksdb/env.h>
#include <rocksdb/filter_policy.h>
#include <rocksdb/options.h>
#include <rocksdb/table.h>
#include <rocksdb/utilities/options_util.h>

#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace rshim {

namespace {

// --- helpers for "profile[:suffix]" ---
static inline std::string merge_suffix(const std::string& prof) {
  auto pos = prof.find(':');
  return pos == std::string::npos ? std::string() : prof.substr(pos + 1);
}
static inline std::string base_profile(const std::string& prof) {
  auto pos = prof.find(':');
  return pos == std::string::npos ? prof : prof.substr(0, pos);
}

// ---------------- Iterator ----------------
struct ItImpl : public Iterator {
  std::unique_ptr<rocksdb::Iterator> it;

  explicit ItImpl(std::unique_ptr<rocksdb::Iterator> x) : it(std::move(x)) {}

  void Seek(const std::string& lower) override { it->Seek(lower); }
  bool Valid() const override { return it->Valid(); }

  rocksdb::Slice Key() const override { return it->key(); }
  rocksdb::Slice Value() const override { return it->value(); }
  }
};

// ---------------- WriteBatch ----------------
struct WbImpl : public WriteBatch {
  rocksdb::DB* db;
  rocksdb::WriteBatch batch;
  bool disable_wal = false;
  bool sync = false;

  explicit WbImpl(rocksdb::DB* d, bool dis=false, bool sy=false)
      : db(d), disable_wal(dis), sync(sy) {}

  void Put(const std::string& k, const std::string& v) override { batch.Put(k, v); }
  void Delete(const std::string& k) override { batch.Delete(k); }
  void Merge(const std::string& k, const std::string& v) override { batch.Merge(k, v); }

  void Commit() override {
    rocksdb::WriteOptions wo;
    wo.disableWAL = disable_wal;
    wo.sync = sync;
    auto st = db->Write(wo, &batch);
    if (!st.ok()) throw std::runtime_error(st.ToString());
    batch.Clear();
  }

  void Discard() override { batch.Clear(); }
};

// ---------------- Enhanced Options helper ----------------
inline void apply_profile(const OpenArgs& a, rocksdb::Options& o) {
  // Core toggles (profile-agnostic)
  o.create_if_missing = a.read_only ? false : a.create_if_missing;
  o.level_compaction_dynamic_level_bytes = true;
  o.enable_pipelined_write = true;

  // Get base profile and suffix
  const std::string base = base_profile(a.profile);
  const std::string msuf = merge_suffix(a.profile);

  // Merge operator by profile suffix
  if (msuf == "packed24") {
    o.merge_operator.reset(new Packed24Merge());
  }

  // Configuration by profile base
  if (base == "read") {
    // -------- Files / I/O path (NVMe assumed)
    o.max_open_files = -1;                            // keep file handles hot
    o.max_file_opening_threads = 8;                   // plenty; higher rarely helps
    o.allow_mmap_reads = false;                       // let RocksDB (not OS) cache data
    o.use_direct_reads = true;                        // bypass page cache for reads
    o.use_direct_io_for_flush_and_compaction = true;  // ditto for write path ops
    o.bytes_per_sync = 1 << 20;                       // smooth compaction writeback (1 MiB)
    o.compaction_readahead_size = 0;                  // NVMe: explicit readahead not helpful

    // -------- Concurrency / background work
    o.max_background_jobs = 16;                       // total (compactions + flush)
    o.max_background_compactions = 12;
    o.max_background_flushes = 4;
    o.use_adaptive_mutex = true;

    // -------- LSM shape / compaction posture
    o.compaction_pri = rocksdb::kMinOverlappingRatio;
    o.level0_file_num_compaction_trigger = 4;
    o.level0_slowdown_writes_trigger     = 12;
    o.level0_stop_writes_trigger         = 20;

    // -------- SST sizing
    o.target_file_size_base = 256ull << 20;           // 256 MiB
    o.max_bytes_for_level_base = 2ull << 30;          // 2 GiB L1 base

    // -------- Memtables (keep modest but not tiny)
    o.write_buffer_size = 64ull << 20;                // 64 MiB per memtable
    o.max_write_buffer_number = 3;
    o.min_write_buffer_number_to_merge = 1;
    o.allow_concurrent_memtable_write = true;

    // -------- Compression
    o.compression = rocksdb::kLZ4Compression;         // fast mid-levels
    o.bottommost_compression = rocksdb::kZSTD;        // compact cold data
    {
      rocksdb::CompressionOptions copt;
      copt.level = 3;                                 // mild ZSTD for speed
      copt.max_dict_bytes = 0;                        // keep CPU light
      o.compression_opts = copt;
    }

    // -------- Table / cache options
    rocksdb::BlockBasedTableOptions bbt;
    bbt.format_version = 5;

    // Two-level index + partitioned filters = fast point lookups + predictable RAM
    bbt.index_type = rocksdb::BlockBasedTableOptions::kTwoLevelIndexSearch;
    bbt.partition_filters = true;
    bbt.cache_index_and_filter_blocks = true;
    bbt.cache_index_and_filter_blocks_with_high_priority = true;
    bbt.pin_top_level_index_and_filter = true;
    bbt.pin_l0_filter_and_index_blocks_in_cache = true;

    // Bloom filters (whole-key). 10 bits/key ≈ ~0.1% FP rate.
    bbt.filter_policy.reset(rocksdb::NewBloomFilterPolicy(/*bits_per_key=*/10, /*use_block_based=*/false));
    bbt.whole_key_filtering = true;

    // Data block tuning
    bbt.block_size = 16 * 1024;
    bbt.data_block_index_type = rocksdb::BlockBasedTableOptions::kDataBlockBinaryAndHash;
    bbt.data_block_hash_table_util_ratio = 0.75;

    // Checksums
    bbt.checksum = rocksdb::kXXH3;

    // Block cache (RAM budget)
    {
      rocksdb::LRUCacheOptions cache_opts;
      cache_opts.capacity = 160ull << 30;             // 160 GiB
      cache_opts.num_shard_bits = 8;                  // good default at this size
      cache_opts.strict_capacity_limit = true;        // avoid cache runaway
      cache_opts.high_pri_pool_ratio = 0.30;          // 30% reserved for index/filter/hot
      bbt.block_cache = rocksdb::NewLRUCache(cache_opts);
    }

    o.table_factory.reset(rocksdb::NewBlockBasedTableFactory(bbt));

    // -------- Housekeeping / observability
    o.stats_dump_period_sec = 60;
    o.skip_stats_update_on_db_open = true;

  } else if (base == "write") {
    // -------- I/O (bulk ingest posture)
    o.allow_mmap_reads = false;
    o.use_direct_reads = false;                       // reads not a priority during ingest
    o.use_direct_io_for_flush_and_compaction = true;  // avoid page-cache trashing
    o.bytes_per_sync = 1 << 20;                       // 1 MiB smoothing
    o.wal_bytes_per_sync = 1 << 20;
    o.compaction_readahead_size = 0;                  // NVMe: readahead not needed

    // -------- Turn OFF auto-compactions; we’ll compact manually later
    o.disable_auto_compactions = true;

    // Avoid write slowdowns tied to compaction debt (let L0 grow)
    o.soft_pending_compaction_bytes_limit = 0;
    o.hard_pending_compaction_bytes_limit = 0;

    // -------- Concurrency
    o.use_adaptive_mutex = true;
    o.enable_pipelined_write = true;
    o.enable_write_thread_adaptive_yield = true;
    o.two_write_queues = true;
    o.unordered_write = true;                         // flip to false if you need global order

    o.max_background_jobs = 24;
    o.max_background_compactions = 16;                // harmless while disabled; useful if you flip later
    o.max_background_flushes = 8;
    o.max_subcompactions = 8;

    // -------- LSM posture for bulk ingest (let L0 grow without stalling)
    o.compaction_pri = rocksdb::kByCompensatedSize;
    o.level0_file_num_compaction_trigger = 1'000'000'000;
    o.level0_slowdown_writes_trigger     = 1'000'000'500;
    o.level0_stop_writes_trigger         = 1'000'001'000;

    // Large files → fewer flushes/metadata churn
    o.target_file_size_base = 512ull << 20;           // 512 MiB
    o.max_bytes_for_level_base = 4ull << 30;          // 4 GiB L1 (used after compaction is re-enabled)

    // -------- Memtables / WAL
    o.allow_concurrent_memtable_write = true;
    o.write_buffer_size = 256ull << 20;               // 256 MiB per memtable
    o.max_write_buffer_number = 8;
    o.min_write_buffer_number_to_merge = 2;
    o.max_total_wal_size = 8ull << 30;                // 8 GiB

    // -------- Compression (keep CPU light during ingest)
    o.compression = rocksdb::kNoCompression;
    o.bottommost_compression = rocksdb::kZSTD;        // applied when you compact later
    {
      rocksdb::CompressionOptions c;
      c.level = 3;
      c.max_dict_bytes = 0;
      o.compression_opts = c;
    }

    // -------- Table options (skip Bloom during ingest)
    rocksdb::BlockBasedTableOptions bbt;
    bbt.format_version = 5;
    bbt.filter_policy.reset();
    bbt.whole_key_filtering = false;

    bbt.block_size = 32 * 1024;                       // 32 KiB blocks (good for streaming writes)
    bbt.data_block_index_type = rocksdb::BlockBasedTableOptions::kDataBlockBinarySearch;
    bbt.checksum = rocksdb::kXXH3;

    // Cache can be small; we’re not optimizing reads now
    {
      rocksdb::LRUCacheOptions c;
      c.capacity = 16ull << 30;                       // 16 GiB
      c.num_shard_bits = 8;
      c.strict_capacity_limit = true;
      c.high_pri_pool_ratio = 0.20;
      bbt.block_cache = rocksdb::NewLRUCache(c);
    }

    bbt.cache_index_and_filter_blocks = true;
    bbt.cache_index_and_filter_blocks_with_high_priority = true;
    bbt.pin_top_level_index_and_filter = true;

    o.table_factory.reset(rocksdb::NewBlockBasedTableFactory(bbt));

    // -------- Housekeeping
    o.max_open_files = -1;
    o.max_file_opening_threads = 8;
    o.stats_dump_period_sec = 60;
    o.skip_stats_update_on_db_open = true;
  }
};

// ---------------- DB impl ----------------
struct DbImpl : public DB {
  std::unique_ptr<rocksdb::DB> db;
  OpenArgs args;

  DbImpl(std::unique_ptr<rocksdb::DB> d, OpenArgs a)
      : db(std::move(d)), args(std::move(a)) {}

  [[nodiscard]] bool Get(const std::string& k, std::string* out) override {
    rocksdb::ReadOptions ro;
    auto s = db->Get(ro, k, out);
    if (s.IsNotFound()) return false;
    if (!s.ok()) throw std::runtime_error(s.ToString());
    return true;
  }

  void Put(const std::string& k, const std::string& v) override {
    rocksdb::WriteOptions wo;
    auto s = db->Put(wo, k, v);
    if (!s.ok()) throw std::runtime_error(s.ToString());
  }

  void Delete(const std::string& k) override {
    rocksdb::WriteOptions wo;
    auto s = db->Delete(wo, k);
    if (!s.ok()) throw std::runtime_error(s.ToString());
  }

  void Merge(const std::string& k, const std::string& v) override {
    rocksdb::WriteOptions wo;
    auto s = db->Merge(wo, k, v);
    if (!s.ok()) throw std::runtime_error(s.ToString());
  }

  std::shared_ptr<Iterator> NewIterator() override {
    rocksdb::ReadOptions ro;
    return std::make_shared<ItImpl>(std::unique_ptr<rocksdb::Iterator>(db->NewIterator(ro)));
  }

  // Per-batch WAL/sync control
  std::shared_ptr<WriteBatch> NewWriteBatch(bool disable_wal=false, bool sync=false) override {
    return std::make_shared<WbImpl>(db.get(), disable_wal, sync);
  }

  void Close() override {
    if (!db) return;
    rocksdb::CancelAllBackgroundWork(db.get(), /*wait=*/false);
    db->Close(); // no-op; documents intent
    db.reset();
  }

  // ----- Optional API (wired) -----
  void FinalizeBulk() override {
    // Make any WAL durable if it was enabled (ignore NotSupported).
    auto st1 = db->FlushWAL(/*sync=*/true);
    if (!st1.ok() && !st1.IsNotSupported()) throw std::runtime_error(st1.ToString());

    // Flush all memtables to SSTs.
    rocksdb::FlushOptions fo;
    fo.wait = true;
    auto st2 = db->Flush(fo);
    if (!st2.ok()) throw std::runtime_error(st2.ToString());
  }

  void CompactAll() override {
    rocksdb::CompactRangeOptions cro;
    cro.change_level = false;
    cro.bottommost_level_compaction = rocksdb::BottommostLevelCompaction::kForce; // force rebuild at bottom
    cro.allow_write_stall = true; // let RocksDB throttle if needed during full compaction
    auto st = db->CompactRange(cro, nullptr, nullptr);
    if (!st.ok()) throw std::runtime_error(st.ToString());
  }

  std::optional<std::string> GetProperty(const std::string& name) override {
    std::string out;
    if (!db->GetProperty(name, &out)) return std::nullopt;
    return out;
  }

  void IngestExternalFiles(const std::vector<std::string>& paths,
                           bool move, bool write_global_seqno) override {
    rocksdb::IngestExternalFileOptions io;
    io.move_files = move;
    io.write_global_seqno = write_global_seqno;
    auto st = db->IngestExternalFile(paths, io);
    if (!st.ok()) throw std::runtime_error(st.ToString());
  }
};

}  // namespace

// -------- Factory --------
std::shared_ptr<DB> DB::Open(const OpenArgs& args) {
  rocksdb::Options o;
  apply_profile(args, o);

  rocksdb::DB* raw = nullptr;
  rocksdb::Status st = args.read_only
                         ? rocksdb::DB::OpenForReadOnly(o, args.path, &raw)
                         : rocksdb::DB::Open(o, args.path, &raw);
  if (!st.ok()) throw std::runtime_error(st.ToString());
  return std::make_shared<DbImpl>(std::unique_ptr<rocksdb::DB>(raw), args);
}

} // namespace rshim
