#!/usr/bin/env python3
"""ps5lz4 - LZ4 HC packing of PS5 games for APR-EMU, run entirely on a NAS.

Pipeline for each game (folder, .exfat, .ffpfs or .ffpfsc):

  1. source    use the folder as is, or extract the image with MkPFS into the
               work area (.ffpfsc inner images are checked against their
               .vhash sidecar when one exists)
  2. check     only games that use AMPR (libSceAmpr import or APR-EMU in
               fakelib/) can read LZ4 packs; anything else is skipped
  3. pack      ampr_pack_cli: LZ4 HC (level 9 by default), AMPR index,
               PackedStdio runtime, byte-for-byte check against the source
  4. verify    ampr_pack_cli verify: manifest, CRC sidecar, every chunk
               decoded, every packed file compared byte for byte again
  5. restore   unpack into a scratch folder and compare every file with the
               source; only ampr_emu.index and fakelib/libSceAmpr.sprx may
               differ, and the runtime must be the pinned PackedStdio build
  6. publish   move the result to OUTPUT/<name>-lz4, write the report, remove
               the work folder

Originals are never written: the library is mounted read-only and every
removal is limited to the work area. A failed or interrupted job keeps its
work folder; running it again resumes after the last finished step.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.0.0"

LIBRARY = Path(os.environ.get("PS5LZ4_LIBRARY", "/library"))
OUTPUT = Path(os.environ.get("PS5LZ4_OUTPUT", "/output"))
STATE = Path(os.environ.get("PS5LZ4_STATE", "/state"))
WORK = OUTPUT / ".ps5lz4-work"
PACKER = os.environ.get("PS5LZ4_PACKER", "/usr/local/bin/ampr_pack_cli")
MKPFS = os.environ.get("PS5LZ4_MKPFS", "mkpfs")
PROFILES = Path(os.environ.get("PS5LZ4_PROFILES", "/opt/ps5lz4/profiles"))
CUSTOM_PROFILES = STATE / "profiles"
LOGS = STATE / "logs"
REPORTS = STATE / "reports"
LOCK_PATH = STATE / "run.lock"
QUEUE_PATH = STATE / "queue.json"
# The same folders as the NAS sees them, for reports.
HOST_LIBRARY = os.environ.get("PS5LZ4_HOST_LIBRARY", str(LIBRARY))
HOST_OUTPUT = os.environ.get("PS5LZ4_HOST_OUTPUT", str(OUTPUT))
FREE_MARGIN = int(float(os.environ.get("PS5LZ4_FREE_MARGIN_GB", "20")) * 1024**3)

# Pinned APR-EMU PackedStdio runtime embedded in ampr_pack_cli.
RUNTIME_SHA256 = "69e6c4d5e4f5fb83c9e01815db5861c4c75734acbf4595cafa50d4c218116d1a"
RUNTIME_REL = "fakelib/libSceAmpr.sprx"
RUNTIME_FILE = Path(os.environ.get("PS5LZ4_RUNTIME", "/opt/ps5lz4/libSceAmpr.sprx"))
# Community game reports from the original project (compat/compat.json,
# refreshed by the fork sync and baked into each image).
COMPAT_FILE = Path(os.environ.get("PS5LZ4_COMPAT", "/opt/ps5lz4/compat.json"))
COMPAT_REPO = "theghostonline/PS5-LZ4-Compression"
PLAY_STATES = {  # ours -> (report form answer, label)
    "works": ("Works", "works"),
    "issues": ("Works with issues", "works with issues"),
    "nostart": ("Won't start (black screen or crash on launch)", "won't start"),
    "crash": ("Crashes in game", "crashes in game"),
}

IMAGE_EXTS = {".exfat": "exfat", ".ffpfs": "ffpfs", ".ffpfsc": "ffpfsc"}
TITLE_RE = re.compile(r"(PPSA|CUSA|PPSM)\d{5}", re.I)
VHASH_MAGIC = b"PFSCVHS1"
EXFAT_SIG = b"EXFAT   "

STEPS = ("source", "check", "pack", "verify", "restore", "publish")

_child: subprocess.Popen | None = None
_stop_requested = False


class JobError(Exception):
    """A step failed; the work folder is kept."""


class Interrupted(JobError):
    """Stopped from outside; the game stays queued and resumes."""


class Skip(Exception):
    """The game can't be handled safely and is left alone."""


# --------------------------------------------------------------------------
# small helpers

def now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def human(n: float | int | None) -> str:
    if n is None:
        return "-"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def write_json(path: Path, data) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def tree_bytes(root: Path) -> tuple[int, int]:
    """(file count, total bytes) of every regular file under root."""
    files = total = 0
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if os.path.isfile(p) and not os.path.islink(p):
                files += 1
                total += st.st_size
    return files, total


def free_bytes(path: Path) -> int:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def under(path: Path, root: Path) -> bool:
    try:
        Path(os.path.abspath(path)).relative_to(os.path.abspath(root))
        return True
    except ValueError:
        return False


def remove_work_path(path: Path) -> None:
    """rm -rf, but only inside the work area; never the library or output."""
    if not path.exists() and not path.is_symlink():
        return
    if not under(path, WORK) or os.path.abspath(path) == os.path.abspath(WORK):
        raise RuntimeError(f"refusing to delete outside the work area: {path}")
    if under(path, LIBRARY):
        raise RuntimeError(f"refusing to delete inside the library: {path}")
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return s or "game"


def nice_prefix() -> list[str]:
    prefix = []
    if shutil.which("nice"):
        prefix += ["nice", "-n", "10"]
    if shutil.which("ionice"):
        prefix += ["ionice", "-c2", "-n7"]
    return prefix


def workers() -> int:
    env = os.environ.get("PS5LZ4_WORKERS")
    if env:
        return max(1, int(env))
    n = os.cpu_count() or 4
    # Same rule as the PS5 engine: leave one core, 2..8 workers.
    return max(2, min(8, n - 1))


# --------------------------------------------------------------------------
# game metadata and AMPR compatibility

def parse_param_json(data: bytes) -> tuple[str, str]:
    try:
        j = json.loads(data.decode("utf-8", "replace"))
    except ValueError:
        return "", ""
    title_id = str(j.get("titleId") or "")
    name = ""
    loc = j.get("localizedParameters") or {}
    lang = loc.get("defaultLanguage") or "en-US"
    for key in (lang, "en-US", "en-GB"):
        entry = loc.get(key) if isinstance(loc, dict) else None
        if isinstance(entry, dict) and entry.get("titleName"):
            name = str(entry["titleName"])
            break
    if not name and isinstance(loc, dict):
        for entry in loc.values():
            if isinstance(entry, dict) and entry.get("titleName"):
                name = str(entry["titleName"])
                break
    return title_id, name


def stream_has(chunks, needle: bytes) -> bool:
    tail = b""
    for chunk in chunks:
        buf = tail + chunk
        if needle in buf:
            return True
        tail = buf[-(len(needle) - 1):]
    return False


def file_chunks(path: Path, size: int = 4 << 20):
    with open(path, "rb") as f:
        while True:
            b = f.read(size)
            if not b:
                return
            yield b


def find_game_root(top: Path) -> Path | None:
    """The shallowest folder holding eboot.bin (any letter case, any depth),
    the same rule exfat_inspect uses on the image directory."""
    hits = []
    for dirpath, _dirs, names in os.walk(top):
        if any(n.lower() == "eboot.bin" for n in names):
            hits.append(Path(dirpath))
    if not hits:
        return None
    return min(hits, key=lambda d: (len(d.relative_to(top).parts), str(d)))


PROGRAM_MAGICS = (b"\x7fELF", b"\x4f\x15\x3d\x1d", b"\x54\x14\xf5\xee")
DEEP_SCAN_MAX = 512 << 20


def program_like(name: str) -> bool:
    low = name.lower()
    return low.endswith((".prx", ".sprx", ".elf", ".self", ".bin"))


def deep_reason(rel: str) -> str:
    return (f"{rel} imports libSceAmpr (deep scan, outside eboot.bin/sce_module: "
            "test the packed game on the PS5 before deleting anything)")


def deep_scan_folder(root: Path) -> str | None:
    """Every program file in the game, not only eboot.bin and sce_module."""
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() != "fakelib"]
        for name in sorted(names):
            if not program_like(name):
                continue
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if rel.lower() == "eboot.bin" or rel.lower().startswith("sce_module/"):
                continue
            try:
                if p.stat().st_size > DEEP_SCAN_MAX:
                    continue
                with open(p, "rb") as f:
                    if f.read(4) not in PROGRAM_MAGICS:
                        continue
            except OSError:
                continue
            if stream_has(file_chunks(p), b"libSceAmpr"):
                return rel
    return None


def ampr_status_folder(root: Path) -> tuple[str, str]:
    """('packed'|'compatible'|'incompatible', reason) for a game folder.

    Mirrors the PS5 engine (populate_lz4_state / title_imports_ampr)."""
    if (root / "ampr_assets.index").exists():
        return "packed", "already LZ4 packed (ampr_assets.index present)"
    for d in root.iterdir():
        if d.is_dir() and d.name.lower() == "fakelib":
            for f in d.iterdir():
                if f.is_file() and f.name.lower() == "libsceampr.sprx":
                    return "compatible", "ships APR-EMU (fakelib/libSceAmpr.sprx)"
    eboot = root / "eboot.bin"
    if eboot.is_file() and stream_has(file_chunks(eboot), b"libSceAmpr"):
        return "compatible", "eboot.bin imports libSceAmpr"
    mod = root / "sce_module"
    if mod.is_dir():
        for f in sorted(mod.iterdir()):
            if f.is_file() and f.name.lower().endswith(".prx") and \
                    stream_has(file_chunks(f), b"libSceAmpr"):
                return "compatible", f"sce_module/{f.name} imports libSceAmpr"
    hit = deep_scan_folder(root)
    if hit:
        return "compatible", deep_reason(hit)
    return "incompatible", ("does not use AMPR: no program file imports libSceAmpr "
                            "(deep scan), so APR-EMU would never load")


def _chain(first: bytes, rest):
    yield first
    yield from rest


def exfat_inspect(image: Path) -> dict:
    """Title, name, size and AMPR status read straight from an .exfat image."""
    from mkpfs.exfat import ExfatReader  # pinned MkPFS 1.1.0

    with open(image, "rb") as fh:
        reader = ExfatReader(fh)
        files = {e.rel_path.lower(): e for e in reader.iter_files()}
        prefix = ""
        if "eboot.bin" not in files:
            roots = sorted(k[: -len("eboot.bin")] for k in files if k.endswith("/eboot.bin"))
            prefix = roots[0] if roots else ""
        def get(rel: str):
            return files.get((prefix + rel).lower())
        title_id = name = ""
        pj = get("sce_sys/param.json")
        if pj:
            title_id, name = parse_param_json(b"".join(reader.read_file(pj)))
        total = sum(e.length for e in files.values())
        if get("ampr_assets.index"):
            status = ("packed", "already LZ4 packed (ampr_assets.index present)")
        elif get("fakelib/libsceampr.sprx"):
            status = ("compatible", "ships APR-EMU (fakelib/libSceAmpr.sprx)")
        elif get("eboot.bin") and stream_has(reader.read_file(get("eboot.bin")), b"libSceAmpr"):
            status = ("compatible", "eboot.bin imports libSceAmpr")
        else:
            status = ("incompatible", "does not use AMPR: no program file imports libSceAmpr "
                                      "(deep scan), so APR-EMU would never load")
            for key, entry in sorted(files.items()):
                if key.startswith(prefix + "sce_module/") and key.endswith(".prx") and \
                        stream_has(reader.read_file(entry), b"libSceAmpr"):
                    status = ("compatible", f"{entry.rel_path} imports libSceAmpr")
                    break
            else:
                for key, entry in sorted(files.items()):
                    rel = key[len(prefix):]
                    if (not key.startswith(prefix) or not program_like(key)
                            or rel == "eboot.bin" or rel.startswith(("sce_module/", "fakelib/"))
                            or entry.length > DEEP_SCAN_MAX):
                        continue
                    chunks = reader.read_file(entry)
                    first = next(chunks, b"")
                    if first[:4] not in PROGRAM_MAGICS:
                        continue
                    if stream_has(_chain(first, chunks),
                                  b"libSceAmpr"):
                        status = ("compatible", deep_reason(entry.rel_path[len(prefix):]))
                        break
        listing = {e.rel_path[len(prefix):]: e.length for e in files.values()}
        return {"title_id": title_id, "name": name, "logical_bytes": total,
                "files": len(files), "status": status[0], "reason": status[1],
                "game_prefix": prefix, "listing": listing}


def load_bundled_profiles() -> list[dict]:
    return read_json(PROFILES / "index.json", []) or []


def detect_engine(root: Path) -> str:
    if (root / "toc").is_file() and (root / "dag").is_file() and (root / "d").is_dir():
        return "insomniac"
    for base in ("", "Media"):
        if (root / base / "StreamingAssets").is_dir():
            for base2 in ("", "Media"):
                for marker in ("Data/globalgamemanagers", "Data/data.unity3d",
                               "Data/Managed/Metadata/global-metadata.dat"):
                    if (root / base2 / marker).is_file():
                        return "unity"
    return ""


def choose_profile(title_id: str, name: str, root: Path) -> tuple[str | None, str]:
    """(toml path or None, description). Custom beats bundled beats scan."""
    if title_id:
        custom = CUSTOM_PROFILES / f"{title_id.upper()}.toml"
        if custom.is_file():
            return str(custom), f"custom ({custom.name})"
    norm = "".join(c.lower() for c in name if c.isalnum())
    bundled = load_bundled_profiles()
    for p in bundled:
        ids = [t.upper() for t in p.get("titleIds", [])]
        names = [n for n in p.get("names", []) if len(n) >= 4]
        if (title_id and title_id.upper() in ids) or any(n in norm for n in names):
            return str(PROFILES / p["file"]), f"bundled {p['id']} (title match)"
    engine = detect_engine(root)
    for p in bundled:
        if engine and p.get("engine") == engine:
            return str(PROFILES / p["file"]), f"bundled {p['id']} ({engine} engine layout)"
    return None, "automatic scan-based profile"


# --------------------------------------------------------------------------
# library

class Entry:
    def __init__(self, path: Path, kind: str):
        self.path = path
        self.kind = kind  # folder | exfat | ffpfs | ffpfsc
        self.rel = str(path.relative_to(LIBRARY))
        stem = path.name if kind == "folder" else path.name[: -len(path.suffix)]
        self.id = safe_name(stem)
        self.title_id = ""
        self.name = ""
        self.duplicate_of: str | None = None
        m = TITLE_RE.search(path.name)
        if m:
            self.title_id = m.group(0).upper()

    @property
    def output(self) -> Path:
        return OUTPUT / f"{self.id}-lz4"

    @property
    def work(self) -> Path:
        return WORK / self.id

    def size(self) -> int:
        if self.kind == "folder":
            return tree_bytes(self.path)[1]
        return self.path.stat().st_size


def scan_library() -> list[Entry]:
    entries: list[Entry] = []
    if not LIBRARY.is_dir():
        return entries

    def walk(d: Path, depth: int):
        try:
            children = sorted(d.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for p in children:
            if p.name.startswith("."):
                continue
            try:
                if p.is_dir():
                    if (p / "eboot.bin").is_file():
                        e = Entry(p, "folder")
                        pj = p / "sce_sys" / "param.json"
                        if pj.is_file():
                            tid, name = parse_param_json(pj.read_bytes())
                            e.title_id = tid.upper() or e.title_id
                            e.name = name
                        entries.append(e)
                    elif depth < 3:
                        walk(p, depth + 1)
                elif p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                    entries.append(Entry(p, IMAGE_EXTS[p.suffix.lower()]))
            except PermissionError:
                # One unreadable game must not stop the rest of the library.
                print(f"cannot read {p} as uid {os.getuid()}: fix with "
                      f"chown -R <NAS user> \"{HOST_LIBRARY}/{p.relative_to(LIBRARY)}\"",
                      file=sys.stderr)

    walk(LIBRARY, 0)
    # An already-extracted folder wins over an image of the same game.
    folders = {e.title_id: e for e in entries if e.kind == "folder" and e.title_id}
    for e in entries:
        if e.kind != "folder" and e.title_id in folders:
            e.duplicate_of = folders[e.title_id].rel
    # Two library entries must never share an output folder.
    seen: dict[str, Entry] = {}
    for e in entries:
        if e.id in seen:
            e.id = safe_name(e.rel.replace("/", "__"))
        seen[e.id] = e
    return entries


def resolve_targets(args_targets: list[str], entries: list[Entry]) -> list[Entry]:
    out: list[Entry] = []
    for t in args_targets:
        tl = t.lower().rstrip("/")
        hits = []
        if t.isdigit() and 1 <= int(t) <= len(entries):
            hits = [entries[int(t) - 1]]
        else:
            for e in entries:
                keys = {e.rel.lower(), e.id.lower(), e.path.name.lower(),
                        str(e.path).lower(), e.title_id.lower()}
                if tl in keys:
                    hits.append(e)
        if not hits:
            raise SystemExit(f"no game matches '{t}' (see: ps5lz4 scan)")
        if len(hits) > 1:
            names = ", ".join(h.rel for h in hits)
            raise SystemExit(f"'{t}' matches several entries: {names}")
        out.append(hits[0])
    return out


# --------------------------------------------------------------------------
# job

class Job:
    def __init__(self, entry: Entry, level: int, restore_test: bool,
                 require_vhash: bool):
        self.e = entry
        self.level = level
        self.restore_test = restore_test
        self.require_vhash = require_vhash
        self.work = entry.work
        self.state_path = self.work / "state.json"
        self.log_path = LOGS / f"{entry.id}.log"
        self.state = {}

    # logging -------------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f"[{now()}] {self.e.id}: {msg}"
        print(line, flush=True)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")

    def save(self) -> None:
        write_json(self.state_path, self.state)

    def done(self, step: str) -> bool:
        return step in self.state.get("done", [])

    def mark(self, step: str, **info) -> None:
        self.state.setdefault("done", [])
        if step not in self.state["done"]:
            self.state["done"].append(step)
        self.state.update(info)
        self.state["step"] = step
        self.state["updated"] = now()
        self.save()

    def set_step(self, step: str) -> None:
        self.state["step"] = f"{step} (running)"
        self.state["updated"] = now()
        self.save()

    def need_space(self, nbytes: int, what: str) -> None:
        free = free_bytes(OUTPUT)
        if free < nbytes + FREE_MARGIN:
            raise JobError(f"not enough free space for {what}: need {human(nbytes)} "
                           f"+ {human(FREE_MARGIN)} margin, {human(free)} free on the output volume")

    def run_tool(self, argv: list[str], step: str) -> str:
        """Run a tool niced, its output in the work folder; returns stdout."""
        global _child
        out_path = self.work / f"{step}.out"
        err_path = self.work / f"{step}.err"
        self.log(f"$ {' '.join(argv)}")
        with open(out_path, "w") as out, open(err_path, "w") as err:
            _child = subprocess.Popen(nice_prefix() + argv, stdout=out, stderr=err,
                                      stdin=subprocess.DEVNULL)
            rc = _child.wait()
            _child = None
        if _stop_requested:
            raise Interrupted("stopped by request; run again to resume")
        if rc < 0:
            # Killed by a signal: container restart, NAS reboot, docker stop.
            raise Interrupted(f"{step} interrupted by signal {-rc}; run again to resume")
        if rc != 0:
            tail = err_path.read_text(errors="replace").replace("\r", "\n").strip().splitlines()
            tail = [l for l in tail if not l.startswith("[progress]")][-6:]
            raise JobError(f"{step} failed (exit {rc}): " + " | ".join(tail))
        return out_path.read_text(errors="replace")

    # steps ---------------------------------------------------------------
    def step_source(self) -> Path:
        e = self.e
        if e.kind == "folder":
            root = e.path
            self.mark("source", source_root=str(root), extraction="none (folder used as is)")
            return root
        if self.done("source"):
            root = Path(self.state["source_root"])
            if root.is_dir():
                self.log(f"resume: extracted game already verified at {root}")
                return root
        self.set_step("source")
        image = e.path
        extract = self.work / "extract"
        partial = self.work / "extract.partial"
        outer = self.work / "outer.partial"
        remove_work_path(partial)
        remove_work_path(outer)
        remove_work_path(extract)
        info: dict = {"image_bytes": image.stat().st_size}

        if e.kind == "exfat":
            meta = exfat_inspect(image)
            self.state["precheck"] = {k: meta[k] for k in ("title_id", "name", "status", "reason")}
            if meta["status"] != "compatible":
                raise Skip(meta["reason"])
            self.need_space(meta["logical_bytes"], "extraction")
            self.run_tool([MKPFS, "unpack", "--format", "exfat", "--no-progress",
                           str(image), str(partial)], "extract")
            info["extraction"] = "MkPFS exFAT reader"
            info["vhash"] = "n/a (.exfat has no hash sidecar)"
            root = find_game_root(partial)
            if not root:
                raise JobError("no eboot.bin in the extracted image")
            # Every file the image lists must be on disk with its exact size.
            bad = []
            for rel, length in meta["listing"].items():
                p = root / rel
                if not p.is_file() or p.stat().st_size != length:
                    bad.append(rel)
            if bad:
                raise JobError(f"extraction incomplete: {len(bad)} files missing or wrong size, e.g. {bad[:3]}")
            info["listing_check"] = f"{len(meta['listing'])} files match the image directory"
        else:
            self.need_space(image.stat().st_size * 3, "extraction")
            self.run_tool([MKPFS, "unpack", "--format", "pfs", "--no-progress",
                           str(image), str(outer)], "extract-outer")
            info["extraction"] = "MkPFS PFS reader"
            if find_game_root(outer):
                outer.rename(partial)
                info["vhash"] = "n/a (plain PFS image)"
            else:
                files = [p for p in outer.rglob("*") if p.is_file()]
                if len(files) != 1:
                    raise JobError(f"unexpected image layout: {len(files)} files and no eboot.bin")
                nested = files[0]
                info["nested"] = nested.name
                info["vhash"] = self.check_vhash(image, nested)
                with open(nested, "rb") as f:
                    f.seek(3)
                    fmt = "exfat" if f.read(8) == EXFAT_SIG else "pfs"
                info["nested_format"] = fmt
                self.need_space(nested.stat().st_size, "inner extraction")
                self.run_tool([MKPFS, "unpack", "--format", fmt, "--no-progress",
                               str(nested), str(partial)], "extract-inner")
                remove_work_path(outer)
            root = find_game_root(partial)
            if not root:
                raise JobError("no eboot.bin in the extracted image")
        rel_root = root.relative_to(partial)
        partial.rename(extract)
        root = extract / rel_root
        files, total = tree_bytes(root)
        info.update(source_root=str(root), source_files=files, source_bytes=total)
        self.mark("source", **info)
        self.log(f"extracted {files} files, {human(total)} ({info['vhash']})")
        for f in ("extract.out", "extract.err", "extract-outer.out", "extract-outer.err",
                  "extract-inner.out", "extract-inner.err"):
            remove_work_path(self.work / f)
        return root

    def check_vhash(self, image: Path, nested: Path) -> str:
        sidecar = Path(str(image) + ".vhash")
        if not sidecar.is_file():
            if self.require_vhash:
                raise Skip("no .vhash sidecar to check the extraction against (--require-vhash)")
            return "no .vhash sidecar: extraction not checked against a reference"
        data = sidecar.read_bytes()
        if len(data) < 4096 or data[:8] != VHASH_MAGIC:
            return "invalid .vhash sidecar: not used"
        block = struct.unpack_from("<Q", data, 16)[0]
        nested_size = struct.unpack_from("<Q", data, 32)[0]
        count = struct.unpack_from("<Q", data, 40)[0]
        size = nested.stat().st_size
        if block != 65536 or nested_size != size or count != (size + block - 1) // block \
                or len(data) != 4096 + count * 32:
            if self.require_vhash:
                raise Skip("stale .vhash sidecar (--require-vhash)")
            return "stale .vhash sidecar (sizes differ): not used"
        self.log(f"checking {count} blocks of {nested.name} against {sidecar.name}")
        bad = 0
        with open(nested, "rb") as f:
            for i in range(count):
                b = f.read(block)
                if len(b) < block:
                    b += b"\0" * (block - len(b))
                if hashlib.sha256(b).digest() != data[4096 + i * 32: 4096 + i * 32 + 32]:
                    bad += 1
        if bad:
            raise JobError(f"extracted image does not match {sidecar.name}: {bad} of {count} blocks differ "
                           "(the image or its extraction is damaged)")
        return f"all {count} blocks match {sidecar.name}"

    def step_check(self, root: Path) -> None:
        status, reason = ampr_status_folder(root)
        tid, name = "", ""
        pj = root / "sce_sys" / "param.json"
        if pj.is_file():
            tid, name = parse_param_json(pj.read_bytes())
        self.state.update(title_id=tid or self.e.title_id, title_name=name)
        if status != "compatible":
            raise Skip(reason)
        profile, desc = choose_profile(self.state["title_id"], name, root)
        self.mark("check", ampr=reason, profile_path=profile, profile=desc)
        self.log(f"compatible: {reason}; profile: {desc}")

    def step_pack(self, root: Path) -> Path:
        pack = self.work / "pack"
        if self.done("pack") and (pack / "ampr_assets.index").is_file():
            self.log("resume: packs already built")
            return pack
        self.set_step("pack")
        remove_work_path(pack)
        _files, total = tree_bytes(root)
        self.need_space(total, "LZ4 packs")
        argv = [PACKER, "pack", str(root), str(pack), "--level", str(self.level),
                "--workers", str(workers()), "--embedded-runtime",
                "--install-runtime-if-missing", "--verify-loose", "--learn", str(PROFILES)]
        if self.state.get("profile_path"):
            argv += ["--profile", self.state["profile_path"]]
        t0 = time.time()
        out = self.run_tool(argv, "pack")
        stats = json.loads(out.strip().splitlines()[-1])
        if stats.get("lz4", 0) <= 0:
            # Every file was left loose: LZ4 can't shrink this game's data.
            raise Skip(f"nothing to pack: the packing profile kept all {stats.get('files')} files "
                       f"loose ({stats.get('autoLoose')} of them sampled as incompressible)")
        self.mark("pack", pack_stats=stats, pack_seconds=round(time.time() - t0))
        self.log(f"packed {stats['packed']} files into {stats['packs']} volumes "
                 f"({stats['lz4']} LZ4 + {stats['raw']} raw chunks), {stats['loose']} loose")
        return pack

    def step_verify(self, root: Path, pack: Path) -> None:
        if self.done("verify"):
            return
        self.set_step("verify")
        out = self.run_tool([PACKER, "verify", str(pack), str(root)], "verify")
        stats = json.loads(out.strip().splitlines()[-1])
        # The result must really be AMPR LZ4: manifest, data volumes, runtime.
        problem = lz4_format_problem(pack)
        if problem:
            raise JobError(problem)
        paks = sorted(pack.glob("ampr_assets-*.pak"))
        self.mark("verify", verify_stats=stats, pak_volumes=len(paks), runtime_sha256=RUNTIME_SHA256)
        self.log(f"verify passed: every chunk decoded, {stats['packed']} packed files match the source; "
                 f"{len(paks)} AMPRDAT3 volumes, PackedStdio runtime {RUNTIME_SHA256[:12]}")

    def step_restore(self, root: Path, pack: Path) -> None:
        if self.done("restore") or not self.restore_test:
            if not self.restore_test:
                self.state["restore_test"] = "skipped (--no-restore-test)"
            return
        self.set_step("restore")
        restore = self.work / "restore"
        remove_work_path(restore)
        _files, total = tree_bytes(root)
        self.need_space(total, "restore test")
        self.run_tool([PACKER, "unpack", str(pack), str(restore)], "restore")
        expected_extra = {"ampr_emu.index", RUNTIME_REL}
        same = 0
        problems: list[str] = []
        notes: list[str] = []
        src_files: set[str] = set()
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                sp = Path(dirpath) / name
                rel = sp.relative_to(root).as_posix()
                src_files.add(rel)
                rp = restore / rel
                if rel in expected_extra or rel.lower() == RUNTIME_REL.lower():
                    notes.append(f"{rel} replaced by the PackedStdio runtime"
                                 if rel.lower() == RUNTIME_REL.lower() else f"{rel} rebuilt")
                    continue
                if not rp.is_file():
                    problems.append(f"missing {rel}")
                elif sp.stat().st_size != rp.stat().st_size or not files_equal(sp, rp):
                    problems.append(f"differs {rel}")
                else:
                    same += 1
        for dirpath, _dirs, names in os.walk(restore):
            for name in names:
                rel = (Path(dirpath) / name).relative_to(restore).as_posix()
                if rel not in src_files and rel not in expected_extra:
                    problems.append(f"unexpected {rel}")
                elif rel in expected_extra and rel not in src_files:
                    notes.append(f"{rel} added")
        if problems:
            raise JobError(f"restore test failed ({len(problems)} problems): {problems[:5]}")
        remove_work_path(restore)
        remove_work_path(self.work / "restore.out")
        remove_work_path(self.work / "restore.err")
        self.mark("restore", restore_test=f"passed: {same} files byte-identical after unpack",
                  restore_notes=sorted(set(notes)))
        self.log(f"restore test passed: {same} files byte-identical; {', '.join(sorted(set(notes)))}")

    def step_publish(self, root: Path, pack: Path) -> dict:
        e = self.e
        if e.output.exists():
            raise JobError(f"{e.output} already exists; it is never overwritten")
        programs = ps5_permissions(pack)
        os.rename(pack, e.output)
        out_files, out_bytes = tree_bytes(e.output)
        src_files, src_bytes = tree_bytes(root)
        st = self.state
        report = {
            "id": e.id,
            "source": str(Path(HOST_LIBRARY) / e.rel),
            "source_kind": e.kind,
            "title_id": st.get("title_id"),
            "title_name": st.get("title_name"),
            "output": str(Path(HOST_OUTPUT) / e.output.name),
            "finished": now(),
            "codec": f"LZ4 HC level {self.level}" if self.level >= 5 else f"LZ4 fast level {self.level}",
            "workers": workers(),
            "profile": st.get("profile"),
            "ampr": st.get("ampr"),
            "image_bytes": st.get("image_bytes"),
            "source_files": src_files,
            "source_bytes": src_bytes,
            "output_files": out_files,
            "output_bytes": out_bytes,
            "saved_bytes": src_bytes - out_bytes,
            "saved_percent": round(100.0 * (src_bytes - out_bytes) / src_bytes, 2) if src_bytes else 0,
            "pack": st.get("pack_stats"),
            "pack_seconds": st.get("pack_seconds"),
            "verification": {
                "extraction": st.get("extraction", "none (folder used as is)"),
                "vhash": st.get("vhash", "n/a"),
                "listing_check": st.get("listing_check", "n/a"),
                "pack_byte_compare": "passed (ampr_pack_cli pack: every packed file compared, loose copies re-read)",
                "full_verify": "passed (ampr_pack_cli verify: manifest, CRC, every chunk decoded, byte compare)",
                "restore_test": st.get("restore_test"),
                "restore_notes": st.get("restore_notes", []),
                "format": f"AMPRPAK4 index, {st.get('pak_volumes')} AMPRDAT3 volumes",
                "runtime": f"PackedStdio {RUNTIME_SHA256}",
                "permissions": f"folders and {programs} program files 755, other files 644",
            },
            "verified_on_nas": True,
            "playable_on_ps5": "not tested: needs a console run (see README)",
        }
        if report["image_bytes"]:
            ib = report["image_bytes"]
            report["saved_vs_image_percent"] = round(100.0 * (ib - out_bytes) / ib, 2)
        write_json(REPORTS / f"{e.id}.json", report)
        self.mark("publish", output=str(e.output))
        return report

    def run(self) -> dict:
        e = self.e
        self.work.mkdir(parents=True, exist_ok=True)
        self.state = read_json(self.state_path, {}) or {}
        self.state.setdefault("id", e.id)
        self.state.setdefault("source", e.rel)
        self.state.setdefault("started", now())
        self.state.pop("error", None)
        self.save()
        self.log(f"start {e.kind} {e.rel} (LZ4 level {self.level}, {workers()} workers)")
        if self.state.get("done"):
            self.log(f"resuming after: {', '.join(self.state['done'])}")
        root = self.step_source()
        self.step_check(root)
        pack = self.step_pack(root)
        self.step_verify(root, pack)
        self.step_restore(root, pack)
        report = self.step_publish(root, pack)
        # Success: the work folder (extraction, tool logs) is no longer needed.
        remove_work_path(self.work)
        self.log(f"DONE {human(report['source_bytes'])} -> {human(report['output_bytes'])} "
                 f"(saved {human(report['saved_bytes'])}, {report['saved_percent']}%) -> {report['output']}")
        return report


PROGRAM_EXTS = (".prx", ".sprx", ".elf", ".self")


def ps5_permissions(root: Path) -> int:
    """Modes the PS5 accepts: the game must read everything and execute its
    programs (APR-EMU in fakelib/ does not load without the execute bit).
    Folders and programs 755, everything else 644. Returns program count."""
    programs = 0
    for dirpath, dirs, names in os.walk(root):
        os.chmod(dirpath, 0o755)
        for name in names:
            p = os.path.join(dirpath, name)
            if os.path.islink(p):
                continue
            low = name.lower()
            if low == "eboot.bin" or low.endswith(PROGRAM_EXTS):
                os.chmod(p, 0o755)
                programs += 1
            else:
                os.chmod(p, 0o644)
    return programs


def files_equal(a: Path, b: Path, size: int = 8 << 20) -> bool:
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x = fa.read(size)
            y = fb.read(size)
            if x != y:
                return False
            if not x:
                return True


# --------------------------------------------------------------------------
# results bookkeeping

def result_for(entry: Entry) -> dict:
    rep = read_json(REPORTS / f"{entry.id}.json")
    if rep:
        return {"status": "done", "detail": f"saved {rep.get('saved_percent')}%"}
    skip = read_json(REPORTS / f"{entry.id}.skipped.json")
    if skip:
        return {"status": "skipped", "detail": skip.get("reason", "")}
    st = read_json(entry.work / "state.json")
    if st:
        if st.get("error") and not str(st.get("step", "")).endswith("(interrupted)"):
            return {"status": "failed", "detail": st["error"]}
        return {"status": "partial", "detail": f"after {', '.join(st.get('done', [])) or 'start'}"}
    if entry.output.exists():
        return {"status": "exists", "detail": "output folder exists without a report"}
    return {"status": "pending", "detail": ""}


def process_one(e: Entry, args) -> str:
    """Handle one library entry: 'ok', 'failed' or 'interrupted'."""
    res = result_for(e)
    if res["status"] == "done":
        print(f"[{now()}] {e.id}: already done ({res['detail']}), skipping", flush=True)
        return "ok"
    if res["status"] == "exists":
        print(f"[{now()}] {e.id}: {e.output} exists without a report; not touching it", flush=True)
        return "failed"
    if e.duplicate_of and not args.force_image:
        print(f"[{now()}] {e.id}: skipped, the folder {e.duplicate_of} has the same game "
              "(use --force-image to pack the image)", flush=True)
        return "ok"
    job = Job(e, args.level, not args.no_restore_test, args.require_vhash)
    try:
        job.run()
        (REPORTS / f"{e.id}.skipped.json").unlink(missing_ok=True)
        return "ok"
    except Skip as s:
        job.log(f"SKIPPED: {s}")
        write_json(REPORTS / f"{e.id}.skipped.json",
                   {"id": e.id, "source": e.rel, "reason": str(s), "when": now()})
        # Nothing useful in the work area of a skipped game.
        remove_work_path(e.work)
        return "ok"
    except (JobError, OSError, ValueError, RuntimeError) as err:
        job.state["error"] = str(err)
        job.state["failed"] = now()
        kind = "interrupted" if isinstance(err, Interrupted) else "failed"
        job.state["step"] = str(job.state.get("step", "")).replace(" (running)", "") + f" ({kind})"
        try:
            job.save()
        except OSError:
            pass
        if kind == "interrupted":
            job.log(f"INTERRUPTED: {err}")
            job.log(f"work kept; continue with: ps5lz4 start --resume")
        else:
            job.log(f"FAILED: {err}")
            job.log(f"work folder kept for troubleshooting: {e.work}")
        return kind


def process(entries: list[Entry], args) -> int:
    failures = 0
    queue = read_json(QUEUE_PATH, {}) if args.from_queue else None
    for e in entries:
        if _stop_requested:
            break
        if queue is not None:
            queue["current"] = e.id
            write_json(QUEUE_PATH, queue)
        outcome = process_one(e, args)
        failures += outcome != "ok"
        if queue is not None:
            queue["current"] = None
            if outcome != "interrupted" and not _stop_requested:
                queue.setdefault("failed" if outcome == "failed" else "finished", []).append(e.id)
                queue["remaining"] = [x for x in queue.get("remaining", []) if x != e.id]
            write_json(QUEUE_PATH, queue)
        if outcome == "interrupted":
            break
    return 1 if failures else 0


# --------------------------------------------------------------------------
# commands

def ensure_dirs() -> None:
    for d in (STATE, LOGS, REPORTS, CUSTOM_PROFILES):
        d.mkdir(parents=True, exist_ok=True)
    if OUTPUT.is_dir():
        WORK.mkdir(exist_ok=True)


def acquire_lock():
    fh = open(LOCK_PATH, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.seek(0)
        raise SystemExit(f"another job is running ({fh.read().strip()}); see: ps5lz4 status")
    fh.seek(0)
    fh.truncate()
    fh.write(f"pid={os.getpid()} since={now()}")
    fh.flush()
    return fh


def on_signal(signum, _frame):
    global _stop_requested
    _stop_requested = True
    if _child and _child.poll() is None:
        _child.terminate()


def cmd_run(args) -> int:
    ensure_dirs()
    entries = scan_library()
    if args.from_queue:
        q = read_json(QUEUE_PATH, {}) or {}
        ids = q.get("remaining", [])
        targets = [e for e in entries if e.id in ids]
    elif args.all:
        targets = [e for e in entries if result_for(e)["status"] in ("pending", "partial", "failed")]
    else:
        if not args.targets:
            raise SystemExit("name at least one game, or --all (see: ps5lz4 scan)")
        targets = resolve_targets(args.targets, entries)
    if not targets:
        print("nothing to do")
        return 0
    lock = acquire_lock()
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    try:
        return process(targets, args)
    finally:
        lock.close()


def cmd_start(args) -> int:
    """Queue games and run them in the background with nohup."""
    ensure_dirs()
    entries = scan_library()
    if args.resume:
        q = read_json(QUEUE_PATH, {}) or {}
        if not q.get("remaining"):
            raise SystemExit("no unfinished queue to resume")
    else:
        if args.all:
            targets = [e for e in entries if result_for(e)["status"] in ("pending", "partial", "failed")]
        else:
            if not args.targets:
                raise SystemExit("name at least one game, or --all (see: ps5lz4 scan)")
            targets = resolve_targets(args.targets, entries)
        q = {"created": now(), "remaining": [e.id for e in targets], "finished": [], "failed": [],
             "current": None, "options": {"level": args.level,
                                          "no_restore_test": args.no_restore_test,
                                          "require_vhash": args.require_vhash,
                                          "force_image": args.force_image}}
    # Refuse early if a job holds the lock.
    try:
        with open(LOCK_PATH, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
    except OSError:
        raise SystemExit("a job is already running; see: ps5lz4 status")
    write_json(QUEUE_PATH, q)
    opts = q.get("options", {})
    log = LOGS / f"queue-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    argv = ["nohup", sys.executable, os.path.abspath(__file__), "run", "--from-queue",
            "--level", str(opts.get("level", 9))]
    for flag in ("no_restore_test", "require_vhash", "force_image"):
        if opts.get(flag):
            argv.append("--" + flag.replace("_", "-"))
    with open(log, "a") as out:
        proc = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    print(f"started in the background (pid {proc.pid}): {len(q['remaining'])} game(s)")
    print(f"  queue: {', '.join(q['remaining'])}")
    print(f"  log:   {log}")
    print("  watch: ps5lz4 status   |   stop: ps5lz4 stop   |   continue later: ps5lz4 start --resume")
    return 0


def cmd_stop(_args) -> int:
    try:
        text = LOCK_PATH.read_text()
    except OSError:
        text = ""
    m = re.search(r"pid=(\d+)", text)
    with open(LOCK_PATH, "a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print("no job is running")
            return 0
        except OSError:
            pass
    if not m:
        raise SystemExit("a job is running but its pid is unknown")
    os.kill(int(m.group(1)), signal.SIGTERM)
    print(f"asked job pid {m.group(1)} to stop; its work is kept, continue with: ps5lz4 start --resume")
    return 0


def cmd_scan(args) -> int:
    ensure_dirs()
    entries = scan_library()
    if not entries:
        print(f"no games found in {LIBRARY}")
        return 0
    print(f"{'#':>3}  {'kind':6}  {'size':>10}  {'title':9}  {'status':8}  game")
    for i, e in enumerate(entries, 1):
        res = result_for(e)
        status = res["status"]
        extra = ""
        if args.check and status == "pending":
            try:
                if e.kind == "folder":
                    s, reason = ampr_status_folder(e.path)
                elif e.kind == "exfat":
                    meta = exfat_inspect(e.path)
                    e.title_id = meta["title_id"] or e.title_id
                    s, reason = meta["status"], meta["reason"]
                else:
                    s, reason = "unknown", "checked after extraction"
                extra = f"  [{s}: {reason}]"
            except Exception as err:  # report, don't stop the listing
                extra = f"  [check failed: {err}]"
        if e.duplicate_of:
            extra += f"  (same game as folder {e.duplicate_of})"
        if res["detail"] and status != "pending":
            extra += f"  ({res['detail']})"
        print(f"{i:>3}  {e.kind:6}  {human(e.size()):>10}  {e.title_id or '-':9}  {status:8}  {e.rel}{extra}")
    return 0


def lz4_format_problem(game: Path) -> str | None:
    """None when the folder is a complete AMPR LZ4 game, else what is wrong."""
    index = game / "ampr_assets.index"
    if not index.is_file():
        return "no ampr_assets.index (not LZ4-packed)"
    with open(index, "rb") as f:
        magic = f.read(8)
    if magic != b"AMPRPAK4":
        return f"ampr_assets.index has magic {magic!r}, expected AMPRPAK4"
    paks = sorted(game.glob("ampr_assets-*.pak"))
    if not paks:
        return "no .pak volumes"
    for p in paks:
        with open(p, "rb") as f:
            if f.read(8) != b"AMPRDAT3":
                return f"{p.name} is not an AMPRDAT3 volume"
    runtime = find_runtime(game)
    if runtime is None:
        return f"{RUNTIME_REL} missing"
    sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
    if sha != RUNTIME_SHA256:
        return f"{RUNTIME_REL} is not the PackedStdio runtime ({sha[:12]}); run: apr --fix"
    # ampr_assets.index.runtime is optional: profiles without a [runtime]
    # section (e.g. Insomniac) leave APR-EMU on its default cache settings.
    for side in ("ampr_assets.index.crc", "ampr_emu.index"):
        if not (game / side).is_file():
            return f"{side} missing"
    return None


CHECKS_PATH = STATE / "checks.json"  # before the database; migrated once
DB_PATH = STATE / "ps5lz4.db"


class CheckDB(dict):
    """Results of earlier checks (SQLite in state/ps5lz4.db), keyed by what was
    checked and valid while its signature (sizes, mtimes) is unchanged. Works
    like a dict; save() writes the entries that changed."""

    def __init__(self):
        super().__init__()
        import sqlite3
        self._dirty = set()
        self._db = sqlite3.connect(DB_PATH, timeout=30)
        self._db.execute("CREATE TABLE IF NOT EXISTS checks (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                         "checked TEXT NOT NULL)")
        for key, value in self._db.execute("SELECT key, value FROM checks"):
            try:
                dict.__setitem__(self, key, json.loads(value))
            except ValueError:
                pass
        if not self and CHECKS_PATH.is_file():
            for key, value in (read_json(CHECKS_PATH, {}) or {}).items():
                self[key] = value
            self.save()

    def __setitem__(self, key, value):
        if isinstance(value, dict):
            value.setdefault("checked", now())
        dict.__setitem__(self, key, value)
        self._dirty.add(key)

    def save(self):
        if self._dirty:
            with self._db:
                self._db.executemany("INSERT OR REPLACE INTO checks (key, value, checked) VALUES (?, ?, ?)",
                                     [(k, json.dumps(self[k]), now()) for k in self._dirty if k in self])
            self._dirty.clear()

    def close(self):
        self.save()
        self._db.close()


def file_sig(*paths: Path) -> str:
    parts = []
    for p in paths:
        try:
            st = p.stat()
            parts.append(f"{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append("-")
    return "|".join(parts)


def classify(e: "Entry", res: dict, cache: dict | None = None) -> tuple[str, str, bool]:
    """(verdict, why, can_queue) for one library entry. verdict is one of
    LZ4 / can be LZ4 / not LZ4 / error. AMPR checks of unpacked games are
    cached by path, size and mtime (reading eboot.bin from a 100 GB image
    takes a moment)."""
    st = res["status"]
    if st == "done":
        problem = lz4_format_problem(e.output) if e.output.is_dir() else "output folder missing"
        return ("LZ4", res["detail"], False) if not problem else ("error", problem, False)
    if st == "skipped":
        return "not LZ4", res["detail"], False
    if st == "exists":
        return "error", res["detail"], False
    key = sig = None
    if cache is not None:
        try:
            stt = e.path.stat()
            key, sig = str(e.path), f"{stt.st_size}:{int(stt.st_mtime)}"
        except OSError:
            pass
    hit = cache.get(key) if key else None
    if hit and hit.get("sig") == sig:
        ok, why = hit["ok"], hit["why"]
    else:
        try:
            if e.kind == "folder":
                ok, why = ampr_status_folder(e.path)
            elif e.kind == "exfat":
                meta = exfat_inspect(e.path)
                ok, why = meta["status"], meta["reason"]
            else:
                ok, why = "compatible", "checked after extraction"
        except Exception as err:
            ok, why = "compatible", f"checked when packed ({err})"
        if key:
            cache[key] = {"sig": sig, "ok": ok, "why": why}
    if ok == "compatible":
        if st in ("partial", "failed"):
            why = f"{st}: {res['detail']}"
        return "can be LZ4", why, True
    if ok == "packed":
        return "LZ4", why, False
    return "not LZ4", why, False


def cmd_lz4(args) -> int:
    """One line per game: LZ4 already, can become LZ4, or why not. --fix queues the rest."""
    ensure_dirs()
    entries = scan_library()
    todo: list[Entry] = []
    games = compat_games()
    counts = {"LZ4": 0, "can be LZ4": 0, "not LZ4": 0, "error": 0}
    for e in entries:
        res = result_for(e)
        st = res["status"]
        if e.duplicate_of and st != "done":
            continue  # the folder copy of the same game is listed instead
        verdict, why, can = classify(e, res)
        if can:
            todo.append(e)
        counts[verdict] += 1
        print(f"{verdict:12} {e.title_id or '-':9}  {e.rel}  ({why})")
        c = community_text(e.title_id or "", games)
        if c:
            print(f"{'':12} {'':9}  {c}")
    for out in sorted(OUTPUT.glob("*-lz4")):
        if out.is_dir() and not any(e.output == out for e in entries):
            problem = lz4_format_problem(out)
            counts["LZ4" if not problem else "error"] += 1
            print(f"{'LZ4' if not problem else 'error':12} {'-':9}  {out.name}  "
                  f"({'no library source' if not problem else problem})")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    if not todo:
        print("nothing left to pack")
        return 1 if counts["error"] else 0
    if not args.fix:
        print(f"pack the {len(todo)} that can be LZ4: ps5lz4 lz4 --fix")
        return 0
    start = argparse.Namespace(targets=[e.id for e in todo], all=False, resume=False,
                               level=args.level, no_restore_test=args.no_restore_test,
                               require_vhash=args.require_vhash, force_image=args.force_image)
    return cmd_start(start)


def cmd_status(_args) -> int:
    ensure_dirs()
    running = False
    with open(LOCK_PATH, "a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            running = True
    lock_text = LOCK_PATH.read_text().strip() if LOCK_PATH.exists() else ""
    print(f"job: {'RUNNING (' + lock_text + ')' if running else 'idle'}")
    q = read_json(QUEUE_PATH)
    if q:
        print(f"queue: current={q.get('current') or '-'} remaining={q.get('remaining')} "
              f"finished={q.get('finished')} failed={q.get('failed', [])}")
    print(f"free on output volume: {human(free_bytes(OUTPUT))}")
    if WORK.is_dir():
        for w in sorted(WORK.iterdir()):
            st = read_json(w / "state.json", {}) or {}
            step = str(st.get("step", "?"))
            if not running and step.endswith("(running)"):
                step = step.replace("(running)", "(interrupted; continue with: start --resume)")
            line = f"  work/{w.name}: step={step} done={st.get('done', [])}"
            if st.get("error"):
                line += f"\n      error: {st['error']}"
            print(line)
            if running and "running" in str(st.get("step", "")):
                for errf in sorted(w.glob("*.err")):
                    tail = errf.read_text(errors="replace").replace("\r", "\n").strip().splitlines()
                    if tail:
                        print(f"      {errf.stem}: {tail[-1][:160]}")
    return 0


def compat_games() -> dict:
    data = read_json(COMPAT_FILE, {}) or {}
    return data.get("games") or {}


def community_text(title_id: str, games: dict | None = None) -> str:
    """'community: 3 works, 1 crash (4 reports)' or '' when nobody reported."""
    g = (games if games is not None else compat_games()).get((title_id or "").upper())
    if not g or not g.get("reports"):
        return ""
    parts = [f"{g[k]} {label}" for k, label in (("works", "works"), ("issues", "with issues"),
             ("noStart", "won't start"), ("crash", "crash")) if g.get(k)]
    return f"community: {', '.join(parts)} ({g['reports']} report{'s' if g['reports'] != 1 else ''})"


def ps5_text(rep: dict) -> str:
    st = rep.get("ps5_result")
    return f"PS5 {PLAY_STATES[st][1]}" if st in PLAY_STATES else "PS5 untested"


def cmd_community(args) -> int:
    """Community reports for the library, or record and share your own result."""
    ensure_dirs()
    games = compat_games()
    if not args.game:
        updated = (read_json(COMPAT_FILE, {}) or {}).get("updated", "?")
        print(f"community reports from {COMPAT_REPO} (updated {updated})")
        seen = set()
        for e in scan_library():
            tid = (e.title_id or "").upper()
            if not tid or tid in seen:
                continue
            seen.add(tid)
            rep = read_json(REPORTS / f"{e.id}.json") or {}
            mine = ps5_text(rep) if rep else "not LZ4"
            print(f"{tid:9}  {e.rel[:44]:44}  you: {mine:22}  {community_text(tid, games) or 'no reports yet'}")
        print("\nrecord your result: ps5lz4 community <game> works|issues|nostart|crash")
        return 0
    if args.result not in PLAY_STATES:
        raise SystemExit("result must be one of: " + ", ".join(PLAY_STATES))
    e = resolve_targets([args.game], scan_library())[0]
    rep_path = REPORTS / f"{e.id}.json"
    rep = read_json(rep_path)
    if not rep:
        raise SystemExit(f"{e.id} has no LZ4 report yet; pack it first")
    form, label = PLAY_STATES[args.result]
    rep["ps5_result"] = args.result
    rep["playable_on_ps5"] = f"{label} (reported {now()})"
    write_json(rep_path, rep)
    print(f"saved: {e.id}: PS5 {label}")
    source = {"folder": "Folder", "exfat": "exFAT image", "ffpfsc": "Uncompressed .ffpfsc"}.get(e.kind, "")
    name = (rep.get("title_name") or e.id)[:60]
    params = [("template", "compat.yml"), ("title", f"[Game report] {name}: {form}"),
              ("title_id", rep.get("title_id") or e.title_id), ("game", name), ("status", form),
              ("level", str((rep.get("codec") or "").split()[-1])), ("source", source),
              ("firmware", os.environ.get("PS5LZ4_FIRMWARE", "")),
              ("app_version", f"ps5-lz4 NAS {VERSION}")]
    from urllib.parse import quote
    url = f"https://github.com/{COMPAT_REPO}/issues/new?" + "&".join(
        f"{k}={quote(v)}" for k, v in params if v)
    print("share it with the community (open on your phone or computer, add firmware, submit):")
    print(url)
    return 0


def cmd_report(args) -> int:
    ensure_dirs()
    rows = [read_json(p) for p in sorted(REPORTS.glob("*.json")) if not p.name.endswith(".skipped.json")]
    rows = [r for r in rows if r]
    skipped = [read_json(p) for p in sorted(REPORTS.glob("*.skipped.json"))]
    if args.json:
        print(json.dumps({"done": rows, "skipped": skipped}, indent=2, ensure_ascii=False))
        return 0
    tot_src = tot_out = 0
    games = compat_games()
    print(f"{'game':40} {'title':9} {'original':>10} {'LZ4':>10} {'saved':>10} {'%':>6}  verified")
    for r in rows:
        tot_src += r["source_bytes"]
        tot_out += r["output_bytes"]
        print(f"{r['id'][:40]:40} {r.get('title_id') or '-':9} {human(r['source_bytes']):>10} "
              f"{human(r['output_bytes']):>10} {human(r['saved_bytes']):>10} {r['saved_percent']:>5}%  "
              f"{'NAS ok' if r.get('verified_on_nas') else 'NO'} / {ps5_text(r)}")
        c = community_text(r.get("title_id") or "", games)
        if c:
            print(f"{'':40} {c}")
    if rows:
        pct = 100.0 * (tot_src - tot_out) / tot_src if tot_src else 0
        print(f"{'TOTAL':40} {'':9} {human(tot_src):>10} {human(tot_out):>10} "
              f"{human(tot_src - tot_out):>10} {pct:>5.1f}%")
    for s in skipped:
        if s:
            print(f"skipped: {s['id']}: {s['reason']}")
    # Keep a plain TSV next to the JSON reports.
    with open(REPORTS / "summary.tsv", "w") as f:
        f.write("id\ttitle_id\tsource_bytes\toutput_bytes\tsaved_bytes\tsaved_percent\tcodec\tfinished\n")
        for r in rows:
            f.write(f"{r['id']}\t{r.get('title_id')}\t{r['source_bytes']}\t{r['output_bytes']}\t"
                    f"{r['saved_bytes']}\t{r['saved_percent']}\t{r['codec']}\t{r['finished']}\n")
    return 0


def cmd_verify(args) -> int:
    """Re-check a finished output (all chunks decoded, CRC, manifest)."""
    ensure_dirs()
    target = Path(args.output)
    if not target.is_absolute():
        target = OUTPUT / args.output
    if not (target / "ampr_assets.index").is_file():
        raise SystemExit(f"{target} has no ampr_assets.index")
    argv = [PACKER, "verify", str(target)] + ([args.source] if args.source else [])
    rc = subprocess.call(nice_prefix() + argv)
    rt = find_runtime(target)
    if rt is None or hashlib.sha256(rt.read_bytes()).hexdigest() != RUNTIME_SHA256:
        print("APR-EMU is not the PackedStdio runtime; run: ps5lz4 apr --fix")
        rc = rc or 3
    print("verify passed" if rc == 0 else f"verify FAILED (exit {rc})")
    return rc


def find_runtime(game: Path) -> Path | None:
    for d in game.iterdir():
        if d.is_dir() and d.name.lower() == "fakelib":
            for f in d.iterdir():
                if f.is_file() and f.name.lower() == "libsceampr.sprx":
                    return f
    return None


def lz4_game_sig(g: Path) -> str:
    """Changes when the packs, the runtime or the top level of the folder change."""
    rt = find_runtime(g)
    return file_sig(g, g / "ampr_assets.index", g / "ampr_assets.index.crc", rt or g / RUNTIME_REL)


def cmd_apr(args) -> int:
    """Check every LZ4 game: PackedStdio APR-EMU and on-disk boot files; --fix repairs both.
    Games whose files haven't changed since their last check reuse that result
    (state/ps5lz4.db) unless --full is given."""
    ensure_dirs()
    games = sorted(p for p in OUTPUT.iterdir()
                   if p.is_dir() and (p / "ampr_assets.index").is_file())
    if not games:
        print(f"no LZ4 games in {OUTPUT}")
        return 0
    if args.fix:
        if not RUNTIME_FILE.is_file() or \
                hashlib.sha256(RUNTIME_FILE.read_bytes()).hexdigest() != RUNTIME_SHA256:
            raise SystemExit(f"pinned runtime missing or wrong at {RUNTIME_FILE}; reinstall ps5-lz4")
    db = CheckDB()
    bad = cached = 0
    for g in games:
        key = "apr:" + g.name
        hit = db.get(key)
        if hit and not args.full and hit.get("sig") == lz4_game_sig(g) and (hit.get("ok") or not args.fix):
            cached += 1
            bad += 0 if hit.get("ok") else 1
            print(f"{hit['state']:<45} {g.name}  (cached {hit.get('checked', '')})")
            continue
        rt = find_runtime(g)
        ok = True
        if rt is None:
            state = "MISSING APR-EMU"
        else:
            sha = hashlib.sha256(rt.read_bytes()).hexdigest()
            state = "ok" if sha == RUNTIME_SHA256 else f"WRONG APR-EMU ({sha[:12]}, not PackedStdio)"
        if state != "ok":
            ok = False
            if args.fix:
                dst = rt or (g / RUNTIME_REL)
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.chmod(dst.parent, 0o755)
                tmp = dst.with_name(dst.name + ".tmp")
                shutil.copyfile(RUNTIME_FILE, tmp)
                os.chmod(tmp, 0o755)
                os.replace(tmp, dst)
                state += " -> FIXED"
                ok = True
        # Files the PS5 looks for on disk (PlayGo markers, empty files, some
        # boot files) must exist next to the packs; packs made before
        # upstream 1.4.3 may hold them only inside. --fix writes them out.
        out = subprocess.run([PACKER, "disk-files", str(g)] + (["--repair"] if args.fix else []),
                             capture_output=True, text=True)
        m = re.search(r"missing=(\d+) restored=(\d+)", out.stdout)
        if m and int(m.group(1)):
            state += f"; {m.group(1)} disk file(s) only in packs"
            if args.fix:
                state += f" -> {m.group(2)} restored"
            else:
                ok = False
        elif not m:
            state += f"; disk-file check failed: {(out.stderr or out.stdout).strip()[-120:]}"
            ok = False
        bad += 0 if ok else 1
        db[key] = {"sig": lz4_game_sig(g), "ok": ok, "state": state, "checked": now()}
        print(f"{state:<45} {g.name}")
    db.close()
    if cached:
        print(f"{cached} of {len(games)} unchanged since their last check (results from the database; --full checks again)")
    if bad and not args.fix:
        print(f"{bad} game(s) need repair; run: ps5lz4 apr --fix")
    return 1 if bad and not args.fix else 0


def cmd_clean(args) -> int:
    """Remove the work folder of a failed or skipped game."""
    ensure_dirs()
    for t in args.ids:
        w = WORK / safe_name(t)
        if not w.exists():
            print(f"{t}: no work folder")
            continue
        remove_work_path(w)
        print(f"{t}: removed {w}")
    return 0


def cmd_doctor(_args) -> int:
    ok = True
    def line(good: bool, msg: str):
        nonlocal ok
        ok &= good
        print(f"[{'ok' if good else 'FAIL'}] {msg}")
    print(f"ps5lz4 {VERSION}  arch={os.uname().machine}  cpus={os.cpu_count()}  workers={workers()}")
    line(LIBRARY.is_dir(), f"library {LIBRARY} readable")
    probe = LIBRARY / ".ps5lz4-write-test"
    try:
        probe.write_text("x")
        probe.unlink()
        line(False, "library is WRITABLE: mount it read-only (:ro)")
    except OSError as err:
        line(err.errno in (errno.EROFS, errno.EACCES, errno.EPERM), "library is read-only")
    line(OUTPUT.is_dir() and os.access(OUTPUT, os.W_OK), f"output {OUTPUT} writable")
    line(STATE.is_dir() and os.access(STATE, os.W_OK), f"state {STATE} writable")
    line(WORK.is_dir() and os.access(WORK, os.W_OK), f"work area {WORK} writable")
    try:
        same_fs = os.stat(OUTPUT).st_dev == os.stat(WORK if WORK.exists() else OUTPUT).st_dev
        line(same_fs, "work area on the output volume (atomic publish)")
    except OSError:
        line(False, "work area")
    if OUTPUT.is_dir():
        print(f"     free on output volume: {human(free_bytes(OUTPUT))}")
    try:
        out = subprocess.run([PACKER], capture_output=True, text=True).stderr
        line("verify <packed>" in out, f"packer {PACKER}")
    except OSError as err:
        line(False, f"packer {PACKER}: {err}")
    try:
        out = subprocess.run([MKPFS, "-V"], capture_output=True, text=True)
        txt = (out.stdout + out.stderr).strip().splitlines()
        line(any("1.1.0" in t for t in txt), f"MkPFS: {txt[0] if txt else '?'}")
    except OSError as err:
        line(False, f"MkPFS: {err}")
    line((PROFILES / "index.json").is_file(), f"bundled profiles {PROFILES}")
    print(f"     PackedStdio runtime pinned: {RUNTIME_SHA256}")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# web page: `ui` serves it (own container, LAN only), `agent` runs in the
# ps5-lz4 container and carries out what the page asks for. The page never
# runs jobs itself and needs no Docker socket.

# --------------------------------------------------------------------------
# transfer to the PS5 over FTP (ftpsrv). Runs where there is a network: the
# ps5-lz4-ui container, never the network-less ps5-lz4 container.

SETTINGS_PATH = STATE / "settings.json"
TRANSFERS = STATE / "transfers"


def get_settings() -> dict:
    s = {"ps5_ftp": os.environ.get("PS5LZ4_PS5_FTP", ""),
         "ps5_dest": os.environ.get("PS5LZ4_PS5_DEST", "/mnt/usb0/homebrew"),
         "ps5_wake_key": os.environ.get("PS5LZ4_PS5_WAKE_KEY", "")}
    s.update({k: v for k, v in (read_json(SETTINGS_PATH, {}) or {}).items() if k in s and isinstance(v, str)})
    return s


def save_settings(new: dict) -> dict:
    s = get_settings()
    ftp = str(new.get("ps5_ftp", s["ps5_ftp"])).strip()
    dest = str(new.get("ps5_dest", s["ps5_dest"])).strip().rstrip("/") or "/"
    if ftp and not re.fullmatch(r"[A-Za-z0-9.\-]+(:\d{1,5})?", ftp):
        raise ValueError("FTP address must look like 192.168.1.20:2121")
    if not dest.startswith("/") or ".." in dest.split("/"):
        raise ValueError("destination must be an absolute path on the PS5")
    key = str(new.get("ps5_wake_key", s["ps5_wake_key"])).strip()
    if key and not re.fullmatch(r"[0-9A-Fa-f]{1,8}", key):
        raise ValueError("the Remote Play key is up to 8 hex characters (rp_regist_key in Chiaki)")
    s.update(ps5_ftp=ftp, ps5_dest=dest, ps5_wake_key=key)
    stored = read_json(SETTINGS_PATH, {}) or {}
    stored.update(s)  # keeps the pairing details (RP key, MAC, name)
    write_settings(stored)
    return s


def write_settings(data: dict) -> None:
    write_json(SETTINGS_PATH, data)
    try:
        os.chmod(SETTINGS_PATH, 0o600)  # Remote Play keys
    except OSError:
        pass


# Remote Play discovery, the way Chiaki wakes a PS5 from rest mode: a UDP
# WAKEUP to port 9302 carrying the registration key (rp_regist_key).
PS5_DISCOVERY_PORT = 9302
PS5_DISCOVERY_VERSION = "00030010"


def _discovery_socket():
    """UDP socket on a local port in Chiaki's range (9303-9319) when free."""
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for port in range(9303, 9320):
        try:
            sk.bind(("", port))
            break
        except OSError:
            continue
    return sk


def ps5_status(host: str, timeout: float = 1.5) -> str:
    """'on', 'standby' or 'unknown' (no answer)."""
    import socket
    msg = f"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:{PS5_DISCOVERY_VERSION}\n".encode()
    with _discovery_socket() as sk:
        sk.settimeout(timeout)
        try:
            sk.sendto(msg, (host, PS5_DISCOVERY_PORT))
            data = sk.recv(2048).decode(errors="replace")
        except OSError:
            return "unknown"
    first = data.split("\n", 1)[0]
    if " 200 " in first:
        return "on"
    if " 620 " in first:
        return "standby"
    return "unknown"


def ps5_wake(host: str, key: str) -> None:
    import socket
    credential = int(key, 16)
    msg = ("WAKEUP * HTTP/1.1\nclient-type:vr\nauth-type:R\nmodel:w\napp-type:r\n"
           f"user-credential:{credential}\ndevice-discovery-protocol-version:{PS5_DISCOVERY_VERSION}\n").encode()
    with _discovery_socket() as sk:
        for _ in range(3):
            sk.sendto(msg, (host, PS5_DISCOVERY_PORT))
            time.sleep(0.3)


def ftp_open(host: str, port: int, timeout: float = 3) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ps5_pair(pin: str, account_id: str) -> dict:
    """Remote Play pairing like Chiaki (ps5regist.py, AGPL); stores the keys."""
    sys.path.insert(0, str(Path(__file__).parent))
    import ps5regist
    host = get_settings()["ps5_ftp"].partition(":")[0]
    if not host:
        raise ValueError("set the PS5 address first")
    try:
        res = ps5regist.register(host, pin, account_id)
    except ps5regist.RegistError as err:
        raise ValueError(str(err))
    except OSError as err:
        raise ValueError(f"no connection to the PS5 at {host}: {err}")
    stored = read_json(SETTINGS_PATH, {}) or {}
    stored.update(ps5_wake_key=res["regist_key"], ps5_rp_key=res["rp_key"], ps5_mac=res["mac"],
                  ps5_nickname=res["nickname"], ps5_paired=now())
    write_settings(stored)
    return {"nickname": res["nickname"], "mac": res["mac"], "paired": stored["ps5_paired"]}


def cmd_pair(args) -> int:
    try:
        res = ps5_pair(args.pin, args.account_id)
    except ValueError as err:
        raise SystemExit(f"pairing failed: {err}")
    print(f"paired with {res['nickname'] or 'the PS5'} ({res['mac']}); it can now be woken from rest mode")
    return 0


def cmd_wake(_args) -> int:
    cfg = get_settings()
    host = cfg["ps5_ftp"].partition(":")[0]
    if not host or not cfg["ps5_wake_key"]:
        raise SystemExit("set the PS5 address and the Remote Play key first (web page: Send to PS5)")
    print(f"PS5 is {ps5_status(host)}; sending wake-up")
    ps5_wake(host, cfg["ps5_wake_key"])
    return 0


def transfer_running() -> dict | None:
    for f in TRANSFERS.glob("*.json") if TRANSFERS.is_dir() else []:
        st = read_json(f, {}) or {}
        if st.get("state") == "running":
            try:
                os.kill(int(st.get("pid", 0)), 0)
                return st
            except (OSError, ValueError):
                st.update(state="failed", error="interrupted (container restarted?); press again to resume")
                write_json(f, st)
    return None


def output_for(game: str) -> Path:
    """Resolve a library id/name or an LZ4 folder name to the LZ4 folder."""
    for cand in (OUTPUT / game, OUTPUT / f"{game}-lz4", OUTPUT / f"{safe_name(game)}-lz4"):
        if cand.is_dir() and (cand / "ampr_assets.index").is_file() and cand.parent == OUTPUT:
            return cand
    for e in scan_library():
        if game in (e.id, e.rel, e.title_id) and e.output.is_dir():
            return e.output
    raise SystemExit(f"no finished LZ4 folder for {game!r} in {OUTPUT}")


def cmd_push(args) -> int:
    """Copy a finished LZ4 game to the PS5 over FTP and check it."""
    import ftplib
    ensure_dirs()
    TRANSFERS.mkdir(exist_ok=True)
    cfg = get_settings()
    if not cfg["ps5_ftp"]:
        raise SystemExit("set the PS5 FTP address first (web page: Send to PS5, or PS5LZ4_PS5_FTP)")
    if transfer_running():
        raise SystemExit("a transfer is already running")
    out = output_for(args.game)
    problem = lz4_format_problem(out)
    if problem:
        raise SystemExit(f"{out.name} is not a complete LZ4 game: {problem}")
    host, _, port = cfg["ps5_ftp"].partition(":")
    port = int(port or 2121)
    dest = f"{cfg['ps5_dest']}/{out.name}"
    files = sorted(p for p in out.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    st_path = TRANSFERS / f"{out.name}.json"
    st = {"game": out.name, "dest": f"{cfg['ps5_ftp']}{dest}", "state": "running", "pid": os.getpid(),
          "bytes": 0, "total": total, "files": len(files), "files_done": 0, "skipped": 0,
          "current": "", "started": now(), "error": None, "verified": 0}
    write_json(st_path, st)
    last = [0.0]

    def save(force=False):
        if force or time.time() - last[0] > 1:
            write_json(st_path, st)
            last[0] = time.time()

    def connect():
        f = ftplib.FTP()
        f.connect(host, port, timeout=60)
        f.login()
        f.voidcmd("TYPE I")
        try:
            # ftpsrv decrypts SELF files on download and reports their
            # decrypted size; SELF turns that off for this connection.
            f.sendcmd("SELF")
        except ftplib.all_errors:
            pass
        return f

    def rsize(f, path):
        try:
            f.voidcmd("TYPE I")  # listings switch the connection to ASCII
            return f.size(path)
        except ftplib.all_errors:
            return None

    try:
        if not ftp_open(host, port):
            if not cfg["ps5_wake_key"]:
                raise RuntimeError(f"no FTP server at {host}:{port}: is the PS5 on with ftpsrv running? "
                                   "(add the Remote Play key to wake it from rest mode)")
            st["current"] = f"waking the PS5 (it was {ps5_status(host)})"
            save(True)
            ps5_wake(host, cfg["ps5_wake_key"])
            deadline = time.time() + 240
            while not ftp_open(host, port):
                if time.time() > deadline:
                    raise RuntimeError("woke the PS5 but its FTP server did not answer within 4 minutes "
                                       "(is ftpsrv loaded after rest mode?)")
                if int(time.time()) % 30 == 0:
                    ps5_wake(host, cfg["ps5_wake_key"])
                time.sleep(3)
            time.sleep(5)  # give ftpsrv a moment after resume
        ftp = connect()
        # Two copies of one title confuse ShadowMountPlus.
        tid = ""
        pj = out / "sce_sys" / "param.json"
        if pj.is_file():
            tid = parse_param_json(pj.read_bytes())[0].upper()
        if not tid:
            m = TITLE_RE.search(out.name)
            tid = m.group(0).upper() if m else ""
        try:
            names = [n.rsplit("/", 1)[-1] for n in ftp.nlst(cfg["ps5_dest"])]
        except ftplib.error_perm:
            names = []
            ftp.mkd(cfg["ps5_dest"])
        dupes = [n for n in names if tid and tid in n.upper() and n != out.name]
        if dupes and not args.force:
            raise RuntimeError(f"{cfg['ps5_dest']} on the PS5 already has {tid}: {', '.join(dupes)}. "
                               "Delete or move it first (ShadowMountPlus mounts one copy per title)")
        made = set()

        def mkdirs(path):
            parts, cur = path.strip("/").split("/"), ""
            for part in parts:
                cur += "/" + part
                if cur not in made:
                    try:
                        ftp.mkd(cur)
                    except ftplib.error_perm:
                        pass
                    made.add(cur)

        mkdirs(dest)
        for d in sorted(q for q in out.rglob("*") if q.is_dir()):
            mkdirs(f"{dest}/{d.relative_to(out).as_posix()}")  # empty folders too
        programs = []
        for p in files:
            rel = p.relative_to(out).as_posix()
            remote = f"{dest}/{rel}"
            size = p.stat().st_size
            st["current"] = rel
            with open(p, "rb") as fh:
                if fh.read(4) in PROGRAM_MAGICS:
                    programs.append((p, remote))
            for attempt in range(3):
                try:
                    if rsize(ftp, remote) == size:
                        st["skipped"] += 1
                        break
                    mkdirs(remote.rsplit("/", 1)[0])
                    start = st["bytes"]

                    def cb(chunk, start=start):
                        st["bytes"] += len(chunk)
                        save()
                    with open(p, "rb") as fh:
                        ftp.storbinary(f"STOR {remote}", fh, blocksize=1 << 20, callback=cb)
                    got = rsize(ftp, remote)
                    if got is not None and got != size:
                        st["bytes"] = start
                        raise RuntimeError(f"{rel}: PS5 has {got} bytes, expected {size}")
                    break
                except (ftplib.all_errors, RuntimeError) as err:
                    if "No space" in str(err) or attempt == 2:
                        raise RuntimeError(f"{rel}: {err}")
                    try:
                        ftp.close()
                    except Exception:
                        pass
                    time.sleep(3)
                    ftp = connect()
            else:
                pass
            st["files_done"] += 1
            st["bytes"] = sum(q.stat().st_size for q in files[: st["files_done"]])
            save()
        # Byte check of the program files (the ones ftpsrv would decrypt).
        for p, remote in programs:
            st["current"] = "checking " + p.relative_to(out).as_posix()
            save(True)
            want = hashlib.sha256(p.read_bytes()).hexdigest()
            for attempt in range(2):
                h = hashlib.sha256()
                ftp.retrbinary(f"RETR {remote}", h.update, blocksize=1 << 20)
                if h.hexdigest() == want:
                    break
                if attempt:
                    raise RuntimeError(f"{p.relative_to(out)} differs on the PS5 (SHA-256) after a second upload")
                with open(p, "rb") as fh:  # same size, other bytes: upload it again
                    ftp.storbinary(f"STOR {remote}", fh, blocksize=1 << 20)
            st["verified"] += 1
        ftp.quit()
        st.update(state="done", current="", finished=now())
        save(True)
        print(f"done: {out.name} -> {st['dest']} ({human(total)}, {st['verified']} program files "
              f"checked byte for byte, {st['skipped']} already there)")
        return 0
    except Exception as err:
        st.update(state="failed", error=str(err)[:500], finished=now())
        save(True)
        print(f"FAILED: {err}", file=sys.stderr)
        return 1


REQUESTS = STATE / "requests"
STEPS = ["source", "check", "pack", "verify", "restore", "publish"]
UI_ACTIONS = {  # action -> ps5lz4 arguments (game and result are checked separately)
    "fix": ["lz4", "--fix"],
    "check": ["apr"],
    "check_full": ["apr", "--full"],
    "apr": ["apr", "--fix"],
    "stop": ["stop"],
    "resume": ["start", "--resume"],
    "start": ["start"],
    "community": ["community"],
}


def job_running() -> tuple[bool, str]:
    running = False
    try:
        with open(LOCK_PATH, "a+") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                running = True
    except OSError:
        pass
    text = LOCK_PATH.read_text().strip() if LOCK_PATH.exists() else ""
    return running, text


def work_progress(w: Path) -> tuple[int, int] | None:
    best = None
    for errf in sorted(w.glob("*.err"), key=lambda f: f.stat().st_mtime):
        try:
            with open(errf, "rb") as f:
                f.seek(max(0, f.seek(0, 2) - 4096))
                tail = f.read().decode(errors="replace")
        except OSError:
            continue
        m = re.findall(r"\[progress\] (\d+) / (\d+)", tail)
        if m:
            best = (int(m[-1][0]), int(m[-1][1]))
    return best


def lz4_folder_info(out: Path, cache: dict | None = None) -> dict:
    """Size, file count and pack volumes of an LZ4 game folder (cached by mtime)."""
    try:
        sig = f"{int(out.stat().st_mtime)}:{int((out / 'ampr_assets.index').stat().st_mtime)}"
    except OSError:
        sig = None
    key = "out:" + str(out)
    hit = (cache or {}).get(key)
    if hit and sig and hit.get("sig") == sig:
        return hit["info"]
    files, total = tree_bytes(out)
    info = {"path": str(Path(HOST_OUTPUT) / out.name), "files": files, "bytes": total,
            "paks": len(list(out.glob("ampr_assets-*.pak"))), "problem": lz4_format_problem(out)}
    pj = out / "sce_sys" / "param.json"
    if pj.is_file():
        try:
            info["title_id"], info["name"] = parse_param_json(pj.read_bytes())
        except Exception:
            pass
    if cache is not None and sig:
        cache[key] = {"sig": sig, "info": info}
    return info


def dashboard_data() -> dict:
    ensure_dirs()
    running, lock_text = job_running()
    queue = read_json(QUEUE_PATH, {}) or {}
    cache = CheckDB()
    games = compat_games()
    rows, totals = [], {"lz4": 0, "source": 0, "output": 0}
    entries = scan_library()
    current = queue.get("current") if running else None
    for e in entries:
        res = result_for(e)
        if e.duplicate_of and res["status"] != "done":
            continue
        verdict, why, can = classify(e, res, cache)
        skey = "size:" + str(e.path)
        try:
            ssig = f"{int(e.path.stat().st_mtime)}"
            hit = cache.get(skey)
            if hit and hit.get("sig") == ssig:
                src_size = hit["bytes"]
            else:
                src_size = e.size()
                cache[skey] = {"sig": ssig, "bytes": src_size}
        except OSError:
            src_size = None
        rep = read_json(REPORTS / f"{e.id}.json") or {}
        g = games.get((e.title_id or "").upper()) or {}
        row = {"id": e.id, "rel": e.rel, "kind": e.kind, "source_size": src_size, "title_id": e.title_id,
               "name": rep.get("title_name") or e.name or (e.path.stem if e.kind != "folder" else e.path.name),
               "verdict": verdict, "why": why,
               "can_queue": can, "running": e.id == current,
               "queued": e.id in (queue.get("remaining") or []) and running,
               "source_bytes": rep.get("source_bytes"), "output_bytes": rep.get("output_bytes"),
               "saved_percent": rep.get("saved_percent"), "ps5": rep.get("ps5_result"),
               "community": {k: g.get(k, 0) for k in ("works", "issues", "noStart", "crash", "reports")},
               "output": str(Path(HOST_OUTPUT) / e.output.name) if e.output.is_dir() else None}
        if verdict == "LZ4" and rep:
            totals["lz4"] += 1
            totals["source"] += rep.get("source_bytes", 0)
            totals["output"] += rep.get("output_bytes", 0)
        rows.append(row)
    # LZ4 games in the output folder without a source in the library
    # (original removed, or packed somewhere else).
    known = {e.output.name for e in entries}
    for out in sorted(OUTPUT.iterdir()) if OUTPUT.is_dir() else []:
        if out.name.startswith(".") or out.name in known or not out.is_dir() \
                or not (out / "ampr_assets.index").is_file():
            continue
        info = lz4_folder_info(out, cache)
        rep = {}
        for f in REPORTS.glob("*.json"):
            if f.name == out.name[: -len("-lz4")] + ".json":
                rep = read_json(f, {}) or {}
        tid = (info.get("title_id") or rep.get("title_id") or "").upper()
        if not tid:
            m = TITLE_RE.search(out.name)
            tid = m.group(0).upper() if m else ""
        g = games.get(tid) or {}
        problem = info["problem"]
        rows.append({"id": out.name, "rel": out.name, "kind": "lz4", "title_id": tid,
                     "name": rep.get("title_name") or info.get("name") or out.name,
                     "verdict": "LZ4" if not problem else "error",
                     "why": "only in the LZ4 folder (the original is not in the library)" if not problem else problem,
                     "can_queue": False, "running": False, "queued": False, "output_only": True,
                     "source_bytes": rep.get("source_bytes"), "output_bytes": rep.get("output_bytes") or info["bytes"],
                     "saved_percent": rep.get("saved_percent"), "ps5": rep.get("ps5_result"),
                     "community": {k: g.get(k, 0) for k in ("works", "issues", "noStart", "crash", "reports")},
                     "output": info["path"]})
    cache.close()
    job = None
    if running and current:
        st = read_json(WORK / current / "state.json", {}) or {}
        step = str(st.get("step", "")).split(" ")[0]
        job = {"id": current, "step": step, "done": st.get("done", []), "steps": STEPS,
               "progress": work_progress(WORK / current), "since": lock_text}
    failed = []
    if WORK.is_dir():
        for w in sorted(WORK.iterdir()):
            st = read_json(w / "state.json", {}) or {}
            if st.get("error") and w.name != current:
                failed.append({"id": w.name, "step": st.get("step"), "error": st["error"]})
    done_req = []
    if REQUESTS.is_dir():
        for f in sorted(REQUESTS.glob("*.done.json"), key=lambda f: f.stat().st_mtime)[-5:]:
            done_req.append(read_json(f, {}))
    pending_list = [read_json(f, {}) or {} for f in sorted(REQUESTS.glob("*.req.json"))] if REQUESTS.is_dir() else []
    pending = len(pending_list)
    return {"running": running, "job": job, "queue": queue.get("remaining") or [] if running else [],
            "interrupted": (not running) and bool(queue.get("remaining")),
            "free_bytes": free_bytes(OUTPUT), "games": rows, "totals": totals, "failed": failed,
            "level": int(os.environ.get("PS5LZ4_LEVEL", "9")), "runtime": "PackedStdio 0.4.2.1",
            "compat_updated": (read_json(COMPAT_FILE, {}) or {}).get("updated"),
            "requests": {"pending": pending, "pending_list": pending_list, "recent": done_req[::-1]}, "version": VERSION,
            "settings": {**get_settings(), "ps5_wake_key": "set" if get_settings()["ps5_wake_key"] else "",
                         "paired": {k: (read_json(SETTINGS_PATH, {}) or {}).get(k) for k in ("ps5_nickname", "ps5_paired")}},
            "transfer": transfer_running(),
            "transfers": {f.stem: read_json(f, {}) for f in TRANSFERS.glob("*.json")} if TRANSFERS.is_dir() else {}}


def game_detail(game_id: str) -> dict:
    """Everything known about one game, for the page's detail view."""
    out = None
    rep = read_json(REPORTS / f"{game_id}.json") or {}
    for e in scan_library():
        if e.id == game_id:
            out = e.output
            break
    if out is None and (OUTPUT / game_id).is_dir():
        out = OUTPUT / game_id
        rep = rep or read_json(REPORTS / f"{game_id[: -len('-lz4')]}.json") or {}
    cache = CheckDB()
    folder = lz4_folder_info(out, cache) if out and out.is_dir() else None
    cache.close()
    work = read_json(WORK / game_id / "state.json") or None
    skipped = read_json(REPORTS / f"{game_id}.skipped.json") or None
    tid = ((rep or {}).get("title_id") or (folder or {}).get("title_id") or "").upper()
    if not tid:
        m = TITLE_RE.search(game_id)
        tid = m.group(0).upper() if m else ""
    return {"id": game_id, "report": rep or None, "folder": folder, "work": work, "skipped": skipped,
            "title_id": tid, "community": compat_games().get(tid), "community_repo": COMPAT_REPO}


def cmd_dashboard(_args) -> int:
    print(json.dumps(dashboard_data(), ensure_ascii=False, indent=1))
    return 0


def run_request(req: dict) -> dict:
    action = req.get("action")
    if action not in UI_ACTIONS:
        return {"ok": False, "output": f"unknown action {action!r}"}
    argv = list(UI_ACTIONS[action])
    if action in ("start", "community"):
        game = str(req.get("game") or "")
        if not game or game.startswith("-") or len(game) > 300:
            return {"ok": False, "output": "no game given"}
        argv.append(game)
    if action == "community":
        result = req.get("result")
        if result not in PLAY_STATES:
            return {"ok": False, "output": f"unknown result {result!r}"}
        argv.append(result)
    me = [sys.executable, os.path.abspath(__file__)]
    if action in ("check", "check_full"):
        # "Check all": read-only. Format and APR-EMU of every LZ4 game, and
        # which games can still become LZ4. Nothing is changed.
        rep = subprocess.run(me + argv, capture_output=True, text=True, timeout=6 * 3600)
        lst = subprocess.run(me + ["lz4"], capture_output=True, text=True, timeout=3600)
        text = ("LZ4 games:\n" + (rep.stdout + rep.stderr).strip() +
                "\n\nLibrary:\n" + (lst.stdout + lst.stderr).strip())
        return {"ok": rep.returncode == 0, "output": text[-3000:]}
    out = subprocess.run(me + argv, capture_output=True, text=True, timeout=6 * 3600)
    text = (out.stdout + out.stderr).strip()
    return {"ok": out.returncode == 0, "output": text[-3000:]}


def cmd_agent(_args) -> int:
    """Runs in the ps5-lz4 container: carries out requests from the web page."""
    ensure_dirs()
    REQUESTS.mkdir(exist_ok=True)
    print(f"[{now()}] agent: watching {REQUESTS}", flush=True)
    while True:
        for f in sorted(REQUESTS.glob("*.req.json")):
            req = read_json(f, {}) or {}
            if req.get("action") in ("start", "fix", "resume") and job_running()[0]:
                continue  # waits for the running job; picked up when it is done
            f.unlink(missing_ok=True)
            print(f"[{now()}] agent: {req.get('action')} {req.get('game') or ''}", flush=True)
            try:
                res = run_request(req)
            except Exception as err:
                res = {"ok": False, "output": str(err)}
            res.update(action=req.get("action"), game=req.get("game"), result=req.get("result"),
                       asked=req.get("asked"), finished=now())
            write_json(REQUESTS / (f.name[: -len(".req.json")] + ".done.json"), res)
        olds = sorted(REQUESTS.glob("*.done.json"), key=lambda f: f.stat().st_mtime)
        for f in olds[:-20]:
            f.unlink(missing_ok=True)
        time.sleep(2)


def cmd_ui(args) -> int:
    """Serves the web page. Reads state, writes only request files."""
    import http.server
    ensure_dirs()
    REQUESTS.mkdir(exist_ok=True)
    cache = {"at": 0.0, "body": b""}
    lock = __import__("threading").Lock()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(200, UI_HTML.encode(), "text/html")
            if self.path.startswith("/api/game?"):
                from urllib.parse import parse_qs, urlparse
                gid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
                if not gid or "/" in gid or gid.startswith("."):
                    return self.send(400, b'{"error":"bad id"}')
                try:
                    body = game_detail(gid)
                except Exception as err:
                    body = {"error": str(err)}
                return self.send(200, json.dumps(body, ensure_ascii=False).encode())
            if self.path == "/api/ps5":
                host = get_settings()["ps5_ftp"].partition(":")[0]
                return self.send(200, json.dumps({"status": ps5_status(host) if host else "unset"}).encode())
            if self.path == "/api/community":
                data = read_json(COMPAT_FILE, {}) or {}
                body = {"repo": COMPAT_REPO, "updated": data.get("updated"), "games": data.get("games") or {}}
                return self.send(200, json.dumps(body, ensure_ascii=False).encode())
            if self.path == "/api/dashboard":
                with lock:
                    if time.time() - cache["at"] > 4:
                        try:
                            cache["body"] = json.dumps(dashboard_data(), ensure_ascii=False).encode()
                        except Exception as err:
                            cache["body"] = json.dumps({"error": str(err)}).encode()
                        cache["at"] = time.time()
                    return self.send(200, cache["body"])
            self.send(404, b'{"error":"not found"}')

        def do_POST(self):
            if self.path != "/api/action":
                return self.send(404, b'{"error":"not found"}')
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            except ValueError:
                return self.send(400, b'{"error":"bad request"}')
            if req.get("action") == "pair":
                try:
                    res = ps5_pair(str(req.get("pin") or ""), str(req.get("account_id") or ""))
                except ValueError as err:
                    return self.send(400, json.dumps({"error": str(err)}).encode())
                cache["at"] = 0
                return self.send(200, json.dumps(res).encode())
            if req.get("action") == "wake":
                cfg = get_settings()
                host = cfg["ps5_ftp"].partition(":")[0]
                if not host or not cfg["ps5_wake_key"]:
                    return self.send(400, json.dumps({"error": "PS5 address or Remote Play key missing"}).encode())
                ps5_wake(host, cfg["ps5_wake_key"])
                return self.send(200, b'{"sent":true}')
            if req.get("action") == "settings":
                if req.get("ps5_wake_key") == "set":
                    req.pop("ps5_wake_key")  # unchanged (the page only sees that one is stored)
                try:
                    s = save_settings(req)
                except ValueError as err:
                    return self.send(400, json.dumps({"error": str(err)}).encode())
                cache["at"] = 0
                return self.send(200, json.dumps({**s, "ps5_wake_key": "set" if s["ps5_wake_key"] else ""}).encode())
            if req.get("action") == "push":
                game = str(req.get("game") or "")
                if not game or game.startswith("-") or "/" in game:
                    return self.send(400, b'{"error":"no game"}')
                if not get_settings()["ps5_ftp"]:
                    return self.send(400, json.dumps({"error": "PS5 FTP address missing"}).encode())
                if transfer_running():
                    return self.send(409, b'{"error":"a transfer is already running"}')
                argv = [sys.executable, os.path.abspath(__file__), "push", game] + (["--force"] if req.get("force") else [])
                TRANSFERS.mkdir(exist_ok=True)
                with open(os.devnull, "w") as devnull:
                    subprocess.Popen(argv, stdout=devnull, stderr=devnull, stdin=subprocess.DEVNULL,
                                     start_new_session=True)
                cache["at"] = 0
                return self.send(200, b'{"started":true}')
            if req.get("action") not in UI_ACTIONS:
                return self.send(400, b'{"error":"unknown action"}')
            req = {k: req.get(k) for k in ("action", "game", "result")}
            req["asked"] = now()
            name = f"{int(time.time() * 1000)}-{os.getpid()}"
            write_json(REQUESTS / f"{name}.req.json", req)
            cache["at"] = 0
            self.send(200, json.dumps({"queued": name}).encode())

    srv = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), H)
    print(f"[{now()}] ui on port {args.port}", flush=True)
    srv.serve_forever()
    return 0


UI_HTML = (Path(__file__).with_name("ui.html").read_text()
           if Path(__file__).with_name("ui.html").is_file() else "<p>ui.html missing</p>")


def main() -> int:
    p = argparse.ArgumentParser(prog="ps5lz4", description="LZ4 HC packing of PS5 games for APR-EMU, on the NAS.")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    def job_opts(sp):
        sp.add_argument("--level", type=int, default=int(os.environ.get("PS5LZ4_LEVEL", "9")),
                        help="LZ4 level: 1-4 fast, 5-12 HC (default 9)")
        sp.add_argument("--no-restore-test", action="store_true",
                        help="skip the full unpack-and-compare step (not recommended)")
        sp.add_argument("--require-vhash", action="store_true",
                        help="skip .ffpfsc images without a .vhash sidecar")
        sp.add_argument("--force-image", action="store_true",
                        help="pack an image even when a folder of the same game exists")

    sp = sub.add_parser("doctor", help="check the installation")
    sp.set_defaults(func=cmd_doctor)
    sp = sub.add_parser("scan", help="list the library and each game's state")
    sp.add_argument("--check", action="store_true", help="also check AMPR compatibility (reads eboot)")
    sp.set_defaults(func=cmd_scan)
    sp = sub.add_parser("run", help="pack games now, in the foreground")
    sp.add_argument("targets", nargs="*", help="# from scan, folder/image name, or title ID")
    sp.add_argument("--all", action="store_true", help="every game not done yet")
    sp.add_argument("--from-queue", action="store_true", help=argparse.SUPPRESS)
    job_opts(sp)
    sp.set_defaults(func=cmd_run)
    sp = sub.add_parser("start", help="queue games and run them in the background (nohup)")
    sp.add_argument("targets", nargs="*")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--resume", action="store_true", help="continue the unfinished queue")
    job_opts(sp)
    sp.set_defaults(func=cmd_start)
    sp = sub.add_parser("lz4", help="is each game LZ4? --fix packs every game that can be")
    sp.add_argument("--fix", action="store_true", help="queue every game that can become LZ4")
    job_opts(sp)
    sp.set_defaults(func=cmd_lz4)
    sp = sub.add_parser("status", help="show the running job and the work area")
    sp.set_defaults(func=cmd_status)
    sp = sub.add_parser("stop", help="stop the running job (resumable)")
    sp.set_defaults(func=cmd_stop)
    sp = sub.add_parser("report", help="sizes and savings of finished games")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_report)
    sp = sub.add_parser("verify", help="re-verify a finished output folder")
    sp.add_argument("output", help="output folder name, e.g. MyGame-lz4")
    sp.add_argument("source", nargs="?", help="optional original folder to compare against")
    sp.set_defaults(func=cmd_verify)
    sp = sub.add_parser("apr", help="check every LZ4 game (APR-EMU, on-disk files); --fix repairs")
    sp.add_argument("--fix", action="store_true")
    sp.add_argument("--full", action="store_true", help="check every game again, not only changed ones")
    sp.set_defaults(func=cmd_apr)
    sp = sub.add_parser("community", help="community reports per game; record and share your PS5 result")
    sp.add_argument("game", nargs="?", help="# from scan, name or title ID")
    sp.add_argument("result", nargs="?", help="works | issues | nostart | crash")
    sp.set_defaults(func=cmd_community)
    sp = sub.add_parser("push", help="copy a finished LZ4 game to the PS5 over FTP (runs in ps5-lz4-ui)")
    sp.add_argument("game", help="LZ4 folder name, library name or title ID")
    sp.add_argument("--force", action="store_true", help="copy even if the PS5 has another copy of the title")
    sp.set_defaults(func=cmd_push)
    sp = sub.add_parser("pair", help="pair with the PS5 for Remote Play wake-up, like Chiaki (PIN from the PS5)")
    sp.add_argument("pin", help="8-digit PIN: PS5 Settings > System > Remote Play > Link Device")
    sp.add_argument("account_id", help="PSN account ID: base64 like Chiaki, decimal, or 0x-hex")
    sp.set_defaults(func=cmd_pair)
    sp = sub.add_parser("wake", help="wake the PS5 from rest mode (Remote Play key, like Chiaki)")
    sp.set_defaults(func=cmd_wake)
    sp = sub.add_parser("dashboard", help="everything the web page shows, as JSON")
    sp.set_defaults(func=cmd_dashboard)
    sp = sub.add_parser("agent", help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_agent)
    sp = sub.add_parser("ui", help="serve the web page (own container, see install.sh)")
    sp.add_argument("--port", type=int, default=int(os.environ.get("PS5LZ4_UI_PORT", "5921")))
    sp.set_defaults(func=cmd_ui)
    sp = sub.add_parser("clean", help="delete the work folder of a failed game")
    sp.add_argument("ids", nargs="+")
    sp.set_defaults(func=cmd_clean)
    args = p.parse_args()
    # `ps5lz4 status | head` should just stop, not print a traceback.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
