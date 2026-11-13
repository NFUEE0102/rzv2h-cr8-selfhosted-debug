#!/usr/bin/env python3
"""Seed the per-user e2 studio pack cache that the FSP generator reads.

e2 studio 2026-10 does not read the packs from <e2studio>/internal/projectgen/rz_fsp/packs
directly: the generator looks in the per-user cache ~/.eclipse/com.renesas.platform_<id>/internal/
projectgen/rz_fsp/ (unified packs/ + modules/, and per-family rzv/{packs,modules,<ver>}), which the
GUI fills on its first start. A host that only ever runs the headless build has an empty cache and
every component fails with "Failed to locate component ... in any software packs". This mirrors the
install into every com.renesas.platform_* cache that lacks the packs (idempotent):
  packs/      every *.pack of the install
  modules/    the .module_descriptions/*.xml of every pack
  <ver>/      devices/{dbg,pg,zone}, linkerscripts/, pinconfig/, pinmapping/ from the *_mcu_* packs
both at rz_fsp/ and at rz_fsp/<family>/ (family = rzv for RZ/V).
Run patch_packs.py afterwards (build.sh / build.ps1 do both, in that order).

Exit status 3 = no cache of this e2 studio generation exists yet (it has never been started by
this user). Any start creates the directory, so build.sh / build.ps1 then start it once on the
disposable work tree, and begin again.

usage: seed_pack_cache.py [--e2studio DIR] [--family rzv] [--force]
"""
import argparse
import glob
import os
import re
import shutil
import sys
import zipfile

ap = argparse.ArgumentParser()
ap.add_argument("--e2studio", default="~/rzv-tools/e2studio")
ap.add_argument("--family", default="rzv")
ap.add_argument("--force", action="store_true", help="re-copy even if the cache already has packs")
A = ap.parse_args()
E2S = os.path.expanduser(A.e2studio)
src = os.path.join(E2S, "internal", "projectgen", "rz_fsp", "packs")
packs = sorted(glob.glob(os.path.join(src, "*.pack")))
if not packs:
    sys.exit(f"no packs in {src}")
ver = None
for p in packs:
    m = re.match(r"Renesas\.RZ\.(\d+\.\d+)\.\d+\.pack$", os.path.basename(p))
    if m:
        ver = m.group(1)
if not ver:
    sys.exit("cannot tell the FSP version from Renesas.RZ.<ver>.pack")

caches = sorted(glob.glob(os.path.expanduser("~/.eclipse/com.renesas.platform_*")))
caches = [c for c in caches if not c.endswith("_download")]
NOT_STARTED_YET = 3
if not caches:
    print("  no ~/.eclipse/com.renesas.platform_* cache yet: this e2 studio has not been started by this user")
    sys.exit(NOT_STARTED_YET)


def seed(root):
    pk = os.path.join(root, "packs")
    md = os.path.join(root, "modules")
    vd = os.path.join(root, ver)
    if os.path.isdir(pk) and glob.glob(os.path.join(pk, "*.pack")) and not A.force:
        print(f"  has packs  {root}")
        return
    os.makedirs(pk, exist_ok=True)
    os.makedirs(md, exist_ok=True)
    for p in packs:
        # copy the pristine archive (patch_packs.py keeps it as <pack>.orig) and drop any stale backup
        # in the cache: patch_packs.py then patches the cache copy from a clean start
        dst_pack = os.path.join(pk, os.path.basename(p))
        shutil.copy2(p + ".orig" if os.path.exists(p + ".orig") else p, dst_pack)
        if os.path.exists(dst_pack + ".orig"):
            os.remove(dst_pack + ".orig")
        z = zipfile.ZipFile(p)
        for n in z.namelist():
            if n.startswith(".module_descriptions/") and n.endswith(".xml"):
                open(os.path.join(md, os.path.basename(n)), "wb").write(z.read(n))
            if "_mcu_" in os.path.basename(p) and n.startswith(".mcu/") and not n.endswith("/"):
                # .mcu/.devices/pg/x.xmi -> <ver>/devices/pg/x.xmi ; .mcu/.pinconfig/x -> <ver>/pinconfig/x
                parts = n.split("/")[1:]
                parts = [q.lstrip(".") for q in parts]
                if parts[0] == "iofiles":
                    continue
                dst = os.path.join(vd, *parts)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                open(dst, "wb").write(z.read(n))
    print(f"  seeded     {root}  ({len(packs)} packs, {len(os.listdir(md))} module descriptions, {ver}/)")


ours = 0
for c in caches:
    base = os.path.join(c, "internal", "projectgen", "rz_fsp")
    # only caches that belong to an e2 studio of this generation (unified rz_fsp packs); a 2025-01
    # cache has rz_fsp/<family>/packs with 3.x packs and no unified packs dir -> leave it alone
    legacy = glob.glob(os.path.join(base, "*", "packs", "Renesas.RZV.3.*.pack"))
    if legacy:                         # never, not even with --force: that cache belongs to another install
        print(f"  skip (3.x) {base}")
        continue
    ours += 1
    seed(base)
    seed(os.path.join(base, A.family))
if not ours:
    print("  no cache for this e2 studio yet (only 3.x ones): it has not been started by this user")
    sys.exit(NOT_STARTED_YET)
