"""Import scheduled posts from batches/*.jsonl into approved/.

Each line of a batch file is one carousel post (same fields as a draft) plus "scheduled_date": "YYYY-MM-DD".
The file is deleted after a successful import, and any drafts/ file with the same id is removed
so it isn't rendered or approved twice.

Usage:
    python scripts/import_batch.py
"""
from __future__ import annotations

import datetime as dt
import json

from common import APPROVED, DRAFTS, ROOT, draft_filename, save_json

BATCHES = ROOT / "batches"


def main() -> int:
    files = sorted(BATCHES.glob("*.jsonl")) if BATCHES.exists() else []
    if not files:
        print("No batch files.")
        return 0
    today = dt.date.today().isoformat()
    total = 0
    for f in files:
        posts = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
        for p in posts:
            dt.date.fromisoformat(p["scheduled_date"])  # validate
            p.setdefault("format", "carousel")
            p.setdefault("created", today)
            p["status"] = "approved"
            p["review_warnings"] = []
            name = draft_filename(p["id"], p["topic"])
            for old in DRAFTS.glob(f"{p['id']}-*.json"):
                old.unlink()
            for old in APPROVED.glob(f"{p['id']}-*.json"):
                old.unlink()
            save_json(APPROVED / name, p)
            total += 1
        f.unlink()
        print(f"✓ {f.name}: {len(posts)} posts → approved/")
    print(f"Imported {total} posts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
