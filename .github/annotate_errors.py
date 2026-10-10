"""Emit the lines around the first error in a build log as GitHub annotations.
Usage: annotate_errors.py <log>  (at most 10 annotations of 8 lines each)."""
import re
import sys

lines = open(sys.argv[1], errors="replace").read().splitlines()
pat = re.compile(r"\berror\b|\bError\b|FAILED|fatal|Traceback|undefined reference", re.I)
hits = [i for i, line in enumerate(lines) if pat.search(line) and "Wno-error" not in line]
start = max(0, (hits[0] if hits else len(lines)) - 15)
chunk = lines[start:start + 80]
for i in range(0, len(chunk), 8):
    body = "%0A".join(l.replace("%", "%25")[:400] for l in chunk[i:i + 8])
    print(f"::error title=build log {start + i + 1}-{start + i + len(chunk[i:i + 8])}::{body}")
