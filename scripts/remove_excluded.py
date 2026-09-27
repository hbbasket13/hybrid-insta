"""Delete posts listed in config/excluded_topics.json (by id or exact topic) from drafts/ and approved/,
plus their rendered assets. Idempotent: safe to run on every workflow run.

Usage:
    python scripts/remove_excluded.py
"""
from __future__ import annotations

import shutil

from common import APPROVED, ASSETS, CONFIG, DRAFTS, list_drafts, load_json


def main() -> int:
    cfg = load_json(CONFIG / "excluded_topics.json")
    ids = set(cfg.get("ids", []))
    topics = {t.strip().lower() for t in cfg.get("topics", [])}
    removed = 0
    for folder in (DRAFTS, APPROVED):
        for p in list_drafts(folder):
            d = load_json(p)
            if d.get("id") in ids or str(d.get("topic", "")).strip().lower() in topics:
                p.unlink()
                a = ASSETS / str(d.get("id"))
                if a.is_dir():
                    shutil.rmtree(a)
                removed += 1
                print(f"✗ removed {folder.name}/{p.name}")
    for i in ids:
        a = ASSETS / i
        if a.is_dir():
            shutil.rmtree(a)
            print(f"✗ removed assets/{i}")
    print(f"Excluded topics: {removed} post(s) removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
