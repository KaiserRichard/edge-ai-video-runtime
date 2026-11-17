"""Publish canonical repository lessons with portable source paths and hashes."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
DEST = ROOT / "dashboard/content"

def main():
    records = []
    for source_root, dest in [(REPO / "docs/lessons-vi", DEST / "vi"),
                              (REPO / "docs/img", DEST / "img")]:
        for source in sorted(source_root.rglob("*")):
            if not source.is_file():
                continue
            target = dest / source.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            records.append(dict(file=target.relative_to(DEST).as_posix(),
                source=source.relative_to(REPO).as_posix(),
                sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    (DEST / "publication.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n")
    print(f"Published {len(records)} canonical lesson assets")

if __name__ == "__main__":
    main()
