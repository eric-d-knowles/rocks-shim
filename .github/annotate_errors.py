"""Emit the lines around the first real error in a build log as GitHub
annotations (at most 10, 8 lines each). Usage: annotate_errors.py <log>"""
import re
import sys

lines = open(sys.argv[1], errors="replace").read().splitlines()
pat = re.compile(r"\berror\b|FAILED|fatal|Traceback|undefined reference|No space left", re.I)
benign = re.compile(r"Wno-error|-Werror|No such image|error_if|errors=|error\.py|Error response from daemon")
hits = [i for i, line in enumerate(lines) if pat.search(line) and not benign.search(line)]
# cibuildwheel's own closing summary repeats the failure; prefer the first cause.
first = hits[0] if hits else len(lines) - 60
start = max(0, first - 15)
chunk = lines[start:start + 80]
for i in range(0, len(chunk), 8):
    part = chunk[i:i + 8]
    body = "%0A".join(re.sub(r"\x1b\[[0-9;]*m", "", l).replace("%", "%25")[:400] for l in part)
    print(f"::error title=build log {start + i + 1}-{start + i + len(part)}::{body}")
