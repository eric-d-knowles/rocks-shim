"""Emit the lines around the first real error in a build log as GitHub
annotations (at most 10, 8 lines each). Usage: annotate_errors.py <log>"""
import re
import sys

lines = open(sys.argv[1], errors="replace").read().splitlines()
# Precise markers: ninja's failed step, compiler/linker diagnostics, CMake and
# Python errors. Probe results like "pthread - Failed" and docker noise don't match.
pat = re.compile(r"^\s*FAILED: |\berror: |\bError: |CMake Error|Traceback \(most recent|undefined reference|No space left|ld returned")
hits = [i for i, line in enumerate(lines) if pat.search(line) and "Wno-error" not in line]
start = max(0, hits[0] - 15) if hits else max(0, len(lines) - 80)
chunk = lines[start:start + 80]
for i in range(0, len(chunk), 8):
    part = chunk[i:i + 8]
    body = "%0A".join(re.sub(r"\x1b\[[0-9;]*m", "", l).replace("%", "%25")[:400] for l in part)
    print(f"::error title=build log {start + i + 1}-{start + i + len(part)}::{body}")
