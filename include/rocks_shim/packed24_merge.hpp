// src/cpp/packed24_merge.hpp
#pragma once
#include <rocksdb/merge_operator.h>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>

namespace rshim {
namespace detail {

// LE helpers
inline uint64_t ld64(const unsigned char* p) {
  uint64_t x;
  std::memcpy(&x, p, sizeof(x));   // safe unaligned load
  return x;
}
inline void st64(unsigned char* p, uint64_t x) {
  std::memcpy(p, &x, sizeof(x));   // safe unaligned store
}

// Debug-only guards (compiled out in -DNDEBUG)
inline void debug_check_stream(const unsigned char* p, size_t n) {
#ifndef NDEBUG
  assert(n % 24 == 0);
  const unsigned char* e = p + n;
  uint64_t prev = 0;
  bool have_prev = false;
  while (p < e) {
    uint64_t k = ld64(p);
    if (have_prev) assert(k >= prev);
    prev = k; have_prev = true;
    p += 24;
  }
#else
  (void)p; (void)n;
#endif
}

// Unchecked merge of two valid, monotonic streams
inline void merge_packed24_unchecked(const unsigned char* pa, size_t asz,
                                     const unsigned char* pb, size_t bsz,
                                     std::string* out) {
#ifndef NDEBUG
  debug_check_stream(pa, asz);
  debug_check_stream(pb, bsz);
#endif
  const unsigned char* const aend = pa + asz;
  const unsigned char* const bend = pb + bsz;

  // Worst-case resize once; we’ll shrink at the end.
  out->resize(asz + bsz);
  unsigned char* po = reinterpret_cast<unsigned char*>(&(*out)[0]);
  size_t out_bytes = 0;

  while (pa < aend && pb < bend) {
    uint64_t ka = ld64(pa);
    uint64_t kb = ld64(pb);
    if (ka == kb) {
      st64(po + 0,  ka);
      st64(po + 8,  ld64(pa + 8)  + ld64(pb + 8));
      st64(po + 16, ld64(pa + 16) + ld64(pb + 16));
      pa += 24; pb += 24; po += 24; out_bytes += 24;
    } else if (ka < kb) {
      std::memcpy(po, pa, 24);
      pa += 24; po += 24; out_bytes += 24;
    } else {
      std::memcpy(po, pb, 24);
      pb += 24; po += 24; out_bytes += 24;
    }
  }
  if (pa < aend) { const size_t n = static_cast<size_t>(aend - pa); std::memcpy(po, pa, n); po += n; out_bytes += n; }
  if (pb < bend) { const size_t n = static_cast<size_t>(bend - pb); std::memcpy(po, pb, n); po += n; out_bytes += n; }

  out->resize(out_bytes);
}

} // namespace detail

// Associative & commutative operator.
class Packed24Merge final : public rocksdb::AssociativeMergeOperator {
 public:
  bool Merge(const rocksdb::Slice& /*key*/,
             const rocksdb::Slice* existing_value,
             const rocksdb::Slice& value,
             std::string* new_value,
             rocksdb::Logger* /*logger*/) const override {
    if (!existing_value || existing_value->size() == 0) {
      new_value->assign(value.data(), value.size());
      return true;
    }
    if (value.size() == 0) {
      new_value->assign(existing_value->data(), existing_value->size());
      return true;
    }
#ifndef NDEBUG
    // Debug guard only; compiled out in release.
    if ((existing_value->size() % 24) != 0 || (value.size() % 24) != 0) return false;
#endif
    detail::merge_packed24_unchecked(
        reinterpret_cast<const unsigned char*>(existing_value->data()), existing_value->size(),
        reinterpret_cast<const unsigned char*>(value.data()), value.size(),
        new_value);
    return true;
  }

  bool PartialMerge(const rocksdb::Slice& /*key*/,
                    const rocksdb::Slice& left_operand,
                    const rocksdb::Slice& right_operand,
                    std::string* new_value,
                    rocksdb::Logger* /*logger*/) const override {
    if (left_operand.size() == 0) { new_value->assign(right_operand.data(), right_operand.size()); return true; }
    if (right_operand.size() == 0){ new_value->assign(left_operand.data(), left_operand.size());  return true; }
#ifndef NDEBUG
    if ((left_operand.size() % 24) != 0 || (right_operand.size() % 24) != 0) return false;
#endif
    detail::merge_packed24_unchecked(
        reinterpret_cast<const unsigned char*>(left_operand.data()), left_operand.size(),
        reinterpret_cast<const unsigned char*>(right_operand.data()), right_operand.size(),
        new_value);
    return true;
  }

  const char* Name() const override { return "Packed24Merge"; }
};

} // namespace rshim
