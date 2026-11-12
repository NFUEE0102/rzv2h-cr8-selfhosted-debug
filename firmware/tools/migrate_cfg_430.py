#!/usr/bin/env python3
"""Migrate an RZ/V FSP 3.1.0 e2 studio project (configuration.xml + .cproject) to RZ FSP 4.3.0.

What 4.3.0 changed for the components these projects use (derived by diffing the packs'
.module_descriptions between the 3.1.0 and 4.3.0 packs; Renesas' own migrator, rz-fsp#17, does the
same job but only up to 4.2.0 and from an exe this build does not depend on):
  * component groups "all" -> "rzv" (Renesas RZ/V components), every version -> 4.3.0,
    pack names -> <vendor>.<name>.4.3.0.pack
  * every RZ/V module / config / property / option id gains an "rzv." segment:
    module.driver.timer_on_gpt -> module.driver.rzv.timer_on_gpt, module.driver.timer.mode ->
    module.driver.rzv.timer.mode, config.driver.gpt -> config.driver.rzv.gpt,
    module.middleware.rm_freertos_port -> module.middleware.rzv.rm_freertos_port,
    config.bsp.rz / config.bsp.rz.cr8 -> config.bsp.rzv / config.bsp.rzv.cr8
  * the three OpenAMP components (all / open-amp / libmetal, vendor Linaro, class Middleware) are
    one component Linaro / library / OpenAMP-freertos / all with module module.driver.openamp.freertos
  * FreeRTOS: config.awsfreertos.thread.include_xeventgroupsetbitfromisr and
    include_xresumefromisr no longer exist; configUSE_MUTEXES must be enabled, because the newer
    libmetal builds metal_mutex on xSemaphoreCreateMutex()
  * FSP tree rzv/ -> rz/ (rzv_gen/ and rzv_cfg/ keep their names); the FreeRTOS ports moved from
    rm_freertos_port/cr and /cm to /cr8 and /cm33
Every id and option value that survives is then checked against the ids the installed 4.3.0 packs
declare; unknown ones are listed and the script exits 1, so nothing is migrated by guesswork.

usage: migrate_cfg_430.py <project dir> [--e2studio DIR] [--check]
"""
import argparse
import glob
import io
import os
import re
import sys
import zipfile

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("--e2studio", default=None, help="e2 studio 2026-10 install (default: newest C:\\Renesas\\rzv\\e2studio_* or ~/rzv-tools/e2studio)")
ap.add_argument("--check", action="store_true", help="validate only, write nothing")
A = ap.parse_args()
P = os.path.abspath(A.project)

e2s = A.e2studio
if not e2s:
    cands = sorted(glob.glob("C:/Renesas/rzv/e2studio_*") + glob.glob("C:/Renesas/rz/e2studio_*"), reverse=True)
    e2s = cands[0] if cands else os.path.expanduser("~/rzv-tools/e2studio")
PACKS = glob.glob(os.path.join(e2s, "internal/projectgen/rz_fsp/packs/*.pack")) + glob.glob(os.path.join(e2s, "internal/projectgen/rz_fsp/*/packs/*.pack"))
if not PACKS:
    sys.exit(f"no packs under {e2s}; pass --e2studio")
PACK_NAMES = {os.path.basename(p) for p in PACKS}


def rd(p):
    return io.open(p, encoding="utf-8", newline="").read()


def wr(p, s):
    if not A.check:
        io.open(p, "w", encoding="utf-8", newline="").write(s)


def pack_430(old):
    """Renesas.RZV.3.1.0.pack -> Renesas.RZV.4.3.0.pack, Amazon.FreeRTOS-Kernel.10.6.1+fsp.3.1.0.pack ->
    Amazon.FreeRTOS-Kernel.4.3.0.pack, Linaro.OpenAMP.1.0.0+fsp.3.1.0.pack -> Linaro.OpenAMP-freertos.4.3.0.pack"""
    stem = re.sub(r"\.\d+\.\d+\.\d+(\+fsp\.\d+\.\d+\.\d+)?\.pack$", "", old)
    if stem == "Linaro.OpenAMP":
        stem = "Linaro.OpenAMP-freertos"
    new = f"{stem}.4.3.0.pack"
    if new not in PACK_NAMES:
        sys.exit(f"FAIL pack {new} (for {old}) is not installed")
    return new


# ------------------------------------------------------------------ configuration.xml
x = rd(f"{P}/configuration.xml")
nl = "\r\n" if "\r\n" in x else "\n"
if '<option key="#FSPVersion#" value="4.3.0"/>' in x:
    print("configuration.xml: already 4.3.0")
else:
    if '<option key="#FSPVersion#" value="3.1.0"/>' not in x:
        sys.exit("FAIL configuration.xml is not an FSP 3.1.0 project")
    x = x.replace('<option key="#FSPVersion#" value="3.1.0"/>', '<option key="#FSPVersion#" value="4.3.0"/>')

    # ---- components ----
    def comp(m):
        blk = m.group(0)
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        if attrs["vendor"] == "Linaro" and attrs["group"] == "OpenAMP":
            if attrs["subgroup"] != "all":
                return ""                                   # open-amp / libmetal merge into "all"
            attrs.update({"class": "library", "group": "OpenAMP-freertos", "subgroup": "all"})
            blk = re.sub(r"<description>.*?</description>", "<description>Open Asymmetric Multi-Processing</description>", blk)
        if attrs["vendor"] == "Renesas" and attrs["group"] == "all":
            attrs["group"] = "rzv"
        attrs["version"] = "4.3.0"
        head = "<component " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + ">"
        blk = blk.replace("<component " + m.group(1) + ">", head)
        blk = re.sub(r"<originalPack>([^<]+)</originalPack>", lambda mm: "<originalPack>" + pack_430(mm.group(1)) + "</originalPack>", blk)
        return blk
    x, n = re.subn(r"    <component ([^>]*)>.*?</component>" + nl, comp, x, flags=re.S)
    if n < 5:
        sys.exit("FAIL raComponentSelection not found")

    # ---- ids: the rzv. segment ----
    x = re.sub(r"\bmodule\.driver\.(?!rzv\.|openamp)", "module.driver.rzv.", x)
    x = re.sub(r"\bmodule\.middleware\.(?!rzv\.)", "module.middleware.rzv.", x)
    x = re.sub(r"\bconfig\.driver\.(?!rzv\.|openamp)", "config.driver.rzv.", x)
    x = re.sub(r'config id="config\.bsp\.rz(?=[".])', 'config id="config.bsp.rzv', x)
    # 3.1.0 wrote a value that matched no option id (its own default); 4.3.0 names the option
    x = x.replace("module.driver.rzv.timer.interrupt_skip.adc.none", "module.driver.rzv.timer.interrupt_skip.skip_sources.interrupt_skip.adc.none")

    # ---- OpenAMP: three modules -> one ----
    m = re.search(r'    <module id="module\.driver\.openamp\.(\d+)"/>' + nl, x)
    if not m:
        sys.exit("FAIL openamp module not found")
    oa = m.group(1)
    x = x.replace(m.group(0), f'    <module id="module.driver.openamp.freertos.{oa}"/>' + nl)
    x = re.sub(r'    <module id="module\.driver\.openamp\.(open-amp|libmetal)\.\d+"/>' + nl, "", x)
    stack = re.search(r'      <stack module="module\.driver\.openamp\.\d+">' + nl + r'.*?      </stack>' + nl, x, re.S)
    if not stack:
        sys.exit("FAIL openamp stack not found")
    x = x.replace(stack.group(0), f'      <stack module="module.driver.openamp.freertos.{oa}"/>' + nl)

    # ---- FreeRTOS properties that no longer exist ----
    x = re.sub(r'      <property id="config\.awsfreertos\.thread\.include_x(eventgroupsetbitfromisr|resumefromisr)" value="[^"]*"/>' + nl, "", x)
    wr(f"{P}/configuration.xml", x)
    print("configuration.xml: migrated")

# ---- FreeRTOS mutexes: the libmetal shipped with 4.3.0 implements metal_mutex with
# xSemaphoreCreateMutex() (3.1.0 used an atomic flag), so configUSE_MUTEXES must be 1 or the link
# fails with "undefined reference to xSemaphoreCreateMutex". Idempotent, also for migrated projects.
MUTEX_OFF = '"config.awsfreertos.thread.configuse_mutexes" value="config.awsfreertos.thread.configuse_mutexes.disabled"'
if "module.driver.openamp.freertos" in x and MUTEX_OFF in x:
    x = x.replace(MUTEX_OFF, MUTEX_OFF.replace(".disabled", ".enabled"))
    wr(f"{P}/configuration.xml", x)
    print("configuration.xml: configUSE_MUTEXES enabled (libmetal mutex = FreeRTOS semaphore)")

# ------------------------------------------------------------------ .cproject: generated tree rzv/ -> rz/
cp = f"{P}/.cproject"
if os.path.exists(cp):
    s = rd(cp)
    t = s
    for old, new in [
        ("/rzv/fsp/src/rm_freertos_port/cr}", "/rz/fsp/src/rm_freertos_port/cr8}"),
        ("/rzv/fsp/src/rm_freertos_port/cm}", "/rz/fsp/src/rm_freertos_port/cm33}"),
        ("${ProjName}/rzv/", "${ProjName}/rz/"),
        # rzv_gen/ and rzv_cfg/ keep their names: the 4.3.0 generator still writes them for RZ/V projects
    ]:
        t = t.replace(old, new)
    # object lists the generator keeps in .cproject (CM33 template): rzv/... .o -> rz/... .o
    t = re.sub(r'value="rzv/', 'value="rz/', t)
    if t != s:
        wr(cp, t)
        print(".cproject: rzv/ -> rz/")
    else:
        print(".cproject: already rz/")

# ------------------------------------------------------------------ validate against the installed 4.3.0 packs
ids = set()
for pk in PACKS:
    try:
        z = zipfile.ZipFile(pk)
    except zipfile.BadZipFile:
        continue
    for n in z.namelist():
        if n.startswith(".module_descriptions/") or (n.endswith((".xml", ".xmi", ".pdsc")) and not n.startswith(("rz/", "rzv/"))):
            try:
                t = z.read(n).decode("utf-8", errors="replace")
            except Exception:
                continue
            ids.update(re.findall(r'\bid="([^"]+)"', t))
x = rd(f"{P}/configuration.xml")
unknown = set()
for pid, val in re.findall(r'<property id="([^"]+)" value="([^"]*)"/>', x):
    if pid.startswith(("_", "rtos.")):
        continue
    if pid not in ids:
        unknown.add(("property", pid))
    if val.startswith(("module.", "config.", "enum.", "board.", "interface.")) and val not in ids:
        unknown.add(("value", val))
for mid in re.findall(r'<module id="([^"]+)"', x):
    if re.sub(r"\.\d+$", "", mid) not in ids:
        unknown.add(("module", mid))
for cid in re.findall(r'<config id="([^"]+)"', x):
    if cid not in ids:
        unknown.add(("config", cid))
for rq in re.findall(r'requires="([^"]+)"', x):
    if rq not in ids:
        unknown.add(("requires", rq))
for pk in re.findall(r"<originalPack>([^<]+)</originalPack>", x):
    if pk not in PACK_NAMES:
        unknown.add(("pack", pk))
if unknown:
    print(f"UNKNOWN in 4.3.0 packs ({len(unknown)}):")
    for k, v in sorted(unknown):
        print(f"  {k:9} {v}")
    sys.exit(1)
print(f"validated: every module/config/property/value/pack id exists in the 4.3.0 packs ({len(ids)} ids known)")
