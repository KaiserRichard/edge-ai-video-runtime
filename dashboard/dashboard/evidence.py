"""Read-only evidence API. URLs contain a root ID and a strictly relative path."""
from collections import deque
import csv
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import math
import mimetypes
import os
from pathlib import Path, PureWindowsPath
import stat
from urllib.parse import unquote
from .paths import input_path

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parent
CN = REPOSITORY / "cn/rtp"
OS = REPOSITORY / "os"
ROOTS = {
    "cn-t2": CN / "results/T2", "cn-t3": CN / "results/T3", "cn-t5": CN / "results/T5",
    "cn-report": CN / "report", "os-results": OS / "results",
    "os-study": OS / "results", "os-docs": OS / "docs",
    "supervisor": REPOSITORY / "sim/os_supervisor/output",
    "sample": PROJECT / "samples/cn-loss5",
    "published": PROJECT / "dashboard/content/vi",
}
EXTENSIONS = {".csv", ".log", ".txt", ".md", ".json", ".jsonl", ".png", ".jpg", ".jpeg", ".svg"}


class EvidenceError(ValueError):
    pass


def _reparse(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def resolve(root, relative="", *, directory=False):
    if root not in ROOTS or not isinstance(relative, str):
        raise EvidenceError("unknown evidence root")
    # Reject encoded paths even when a query decoder has already removed one layer.
    # Canonical URLs encode query separators, never path characters or backslashes.
    if (unquote(relative) != relative or "%" in relative or "\\" in relative or
            ":" in relative or "\x00" in relative or relative.startswith("/") or
            PureWindowsPath(relative).is_absolute() or any(c in relative for c in "?#")):
        raise EvidenceError("only plain relative paths are allowed")
    parts = relative.split("/") if relative else []
    if any(p in ("", ".", "..") or p.rstrip(" .") != p for p in parts):
        raise EvidenceError("invalid path component")
    base = ROOTS[root].absolute()
    if not base.exists() or _reparse(base):
        raise EvidenceError("source root unavailable")
    candidate = base
    for part in parts:
        candidate /= part
        if not candidate.exists() or _reparse(candidate):
            raise EvidenceError("missing file or symlink/reparse point")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise EvidenceError("outside evidence root")
    if directory:
        if not resolved.is_dir():
            raise EvidenceError("not a directory")
    elif not resolved.is_file() or resolved.suffix.lower() not in EXTENSIONS:
        raise EvidenceError("unsupported evidence file")
    return resolved


def identify(path):
    path = input_path(str(path).replace("\\", "/"))
    if not path.is_absolute():
        path = REPOSITORY / path
    for key, root in ROOTS.items():
        try:
            return dict(root=key, path=path.relative_to(root).as_posix())
        except ValueError:
            pass
    return None


def used_in(root, relative):
    """Manifest-backed reverse links, plus explicit semantics of experiment folders."""
    import json
    found = set()
    manifest = PROJECT / "dashboard/content/vi/img/evidence_manifest.json"
    if manifest.exists():
        absolute = str(ROOTS[root] / relative).casefold()
        for fig in json.loads(manifest.read_text(encoding="utf-8"))["figures"]:
            if any(str(input_path(s)).casefold() == absolute for s in fig["sources"]):
                found.add(f'{fig["lesson"]:02}')
    if root == "sample" or root == "cn-t3":
        found.update(["01", "02", "03", "04", "05"])
    elif root == "cn-t2":
        found.update(["01", "02"])
    elif root == "cn-t5":
        found.update(["05", "06"])
    elif root == "cn-report" and relative == "hw_tables.md":
        found.update(f"{i:02}" for i in range(1, 8))
    elif root == "supervisor":
        found.add("10")
    elif root == "os-study":
        if relative.startswith("2026-10-30_os_t3_contention/"):
            found.add("08")
        elif relative.startswith("2026-10-30_os_t4_policy/"):
            found.add("09")
        elif "supervisor" in relative or "reaction" in relative:
            found.add("10")
    found.update(lesson_usage().get((root, relative), ()))
    return sorted(found)


@lru_cache(maxsize=1)
def lesson_usage():
    # Deferred import avoids a module cycle. source_items only identifies paths.
    from .learning import lessons, source_items
    usage = {}
    for lesson in lessons():
        for ref in source_items(lesson["id"]):
            usage.setdefault((ref["root"], ref["path"]), set()).add(lesson["id"])
    return usage


def kind(root, relative):
    if root == "supervisor" or root == "cn-report" and relative == "sim_tables.md":
        return "MÔ PHỎNG"
    if root in ("published", "os-docs"):
        return "TÀI LIỆU / HÌNH (xem nhãn trong nguồn)"
    if root == "cn-report":
        return "BẢNG ĐO" if relative == "hw_tables.md" else "TÀI LIỆU"
    return "ĐO THẬT"


def listing(root=None, relative="", page=1):
    if root is None:
        return dict(roots=[dict(id=k, path=str(v), available=v.exists()) for k, v in ROOTS.items()])
    folder = resolve(root, relative, directory=True)
    items = []
    for p in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
        if p.name.startswith(".") or _reparse(p) or (p.is_file() and p.suffix.lower() not in EXTENSIONS):
            continue
        rel = p.relative_to(ROOTS[root]).as_posix()
        items.append(dict(name=p.name, path=rel, directory=p.is_dir(), size=p.stat().st_size if p.is_file() else None, lessons=used_in(root, rel) if p.is_file() else [], badge=kind(root, rel)))
    page = max(1, int(page))
    return dict(root=root, path=relative, page=page, total=len(items), pages=max(1, math.ceil(len(items) / 60)), items=items[(page-1)*60:page*60])


def provenance(root, relative):
    p = resolve(root, relative)
    digest = hashlib.sha256()
    with p.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    info = p.stat()
    return dict(path=str(p), size=info.st_size, modified=datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(), sha256=digest.hexdigest(), lessons=used_in(root, relative), badge=kind(root, relative))


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def preview(root, relative, page=1, column=None, time_column=None):
    p = resolve(root, relative)
    result = dict(root=root, path=relative, source=str(p), lessons=used_in(root, relative), badge=kind(root, relative))
    if p.suffix.lower() == ".csv":
        page = max(1, int(page))
        with p.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames or []
            if column is not None and column not in columns:
                raise EvidenceError("unknown plot column")
            if time_column is not None and time_column != "__row__" and time_column not in columns:
                raise EvidenceError("unknown time column")
            rows, total, plotted = [], 0, []
            numeric = set()
            time_column = time_column or next((c for c in columns if c.startswith("t_") or c in ("timestamp", "time_s")), None)
            # Bounded deterministic reservoir: every compaction doubles the stride.
            stride = 1
            for index, row in enumerate(reader):
                total += 1
                if (page-1)*50 <= index < page*50:
                    rows.append(row)
                if len(numeric) < len(columns):
                    numeric.update(c for c in columns if number(row.get(c)) is not None)
                if column and index % stride == 0:
                    y = number(row.get(column))
                    x = number(row.get(time_column)) if time_column and time_column != "__row__" else index
                    if x is not None and y is not None:
                        plotted.append([x, y])
                    if len(plotted) >= 4000:
                        plotted = plotted[::2]
                        stride *= 2
        # Sorting only changes plot order; the paginated table preserves file order.
        plotted.sort(key=lambda item: item[0])
        # Display elapsed seconds on known time columns. Subtraction stays on
        # this one CSV column; it never compares clocks from different machines.
        unit = next((suffix for suffix in ("ns", "us", "ms", "s") if time_column and time_column.endswith("_"+suffix)), None)
        origin = plotted[0][0] if plotted and unit else None
        if origin is not None:
            divisor = {"ns":1e9, "us":1e6, "ms":1e3, "s":1}[unit]
            plotted = [[(x-origin)/divisor, y] for x,y in plotted]
        time_note = (f"X: giây từ mốc {origin:g} trong cột {time_column} ({unit}); cùng một đồng hồ. Bảng giữ giá trị gốc."
                     if origin is not None else "X: giá trị gốc trong CSV; đơn vị theo tên cột. Không trừ đồng hồ khác máy.")
        result.update(kind="csv", columns=columns, numeric=[c for c in columns if c in numeric], time_column=time_column,
                      rows=rows, total=total, page=page, pages=max(1, math.ceil(total/50)), plot=plotted, plot_stride=stride,
                      time_origin=origin, plot_xunit="s (elapsed)" if origin is not None else time_column or "row", time_note=time_note)
    elif p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg"):
        result.update(kind="image")
    else:
        with p.open(encoding="utf-8-sig", errors="replace") as stream:
            tail = deque(stream, maxlen=200)
        # Bound exceptionally long log lines as well as line count.
        result.update(kind="log", text="".join(tail)[-200000:], note="200 dòng cuối; tối đa 200 kB")
    return result
