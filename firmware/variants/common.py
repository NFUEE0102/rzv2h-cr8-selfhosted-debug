"""shared helpers for the variant transforms: anchored, asserted, idempotent edits"""
import io
import os
import sys


def rd(p):
    return io.open(p, encoding="utf-8", errors="surrogateescape", newline="").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8", errors="surrogateescape", newline="").write(s)


def sub1(s, old, new, what):
    n = s.count(old)
    if n != 1:
        sys.exit(f"FAIL {what}: anchor found {n}x (need 1): {old[:80]!r}")
    return s.replace(old, new, 1)


def patch(path, pairs, allow_multi=False, done_marker=None):
    """apply (old, new) pairs to a file; every old must exist (unique unless allow_multi)"""
    s = rd(path)
    if done_marker and done_marker in s:
        print(f"  {os.path.basename(path)}: already patched")
        return
    for old, new in pairs:
        n = s.count(old)
        if n == 0:
            sys.exit(f"FAIL not found in {path}: {old[:80]!r}")
        if n > 1 and not allow_multi:
            sys.exit(f"FAIL not unique ({n}x) in {path}: {old[:80]!r}")
        s = s.replace(old, new)
    wr(path, s)
    print(f"  patched {os.path.relpath(path)}")


def proj_arg(argv):
    if len(argv) < 2 or not os.path.isdir(argv[1]):
        sys.exit(f"usage: {os.path.basename(argv[0])} <project dir> [options]")
    return os.path.abspath(argv[1])
