"""Copy a small unmodified CSV excerpt from the read-only hardware run."""
import csv
import hashlib
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "cn/rtp/results/T3/loss5/run1"
DEST = Path(__file__).resolve().parents[1] / "samples" / "cn-loss5"
FIELDS = {"receiver.csv": "t_arrival_rx_ns", "frames_rx.csv": "t_playout_rx_ns", "ai.csv": "t_enqueue_rx_ns",
          "sender.csv": "t_capture_mono_ns", "results_tx.csv": "t_capture_mono_ns",
          "receiver_rtcp.csv": "t_mono_ns", "sender_rtcp.csv": "t_mono_ns"}


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    provenance = {"source": str(SOURCE), "kind": "hardware CSV excerpt, not synthetic", "selection": "first 8 seconds of each file's local clock", "files": {}}
    for filename, field in FIELDS.items():
        src = SOURCE / filename
        with src.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = list(reader)
        origin = int(rows[0][field])
        excerpt = [row for row in rows if row[field] and int(row[field]) - origin <= 8_000_000_000]
        with (DEST / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(excerpt)
        provenance["files"][filename] = {"rows": len(excerpt), "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            "excerpt_sha256": hashlib.sha256((DEST / filename).read_bytes()).hexdigest()}
    (DEST / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
