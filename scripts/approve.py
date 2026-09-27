"""Approve a draft: move drafts/<id>-*.json to approved/, optionally with a scheduled date.

Usage:
    python scripts/approve.py T-001
    python scripts/approve.py T-001 --date 2026-10-03
    python scripts/approve.py --list          # show drafts and approved items
"""
from __future__ import annotations

import argparse
import datetime as dt

from common import APPROVED, DRAFTS, POSTED, list_drafts, load_json, save_json


def show():
    for label, folder in (("DRAFTS", DRAFTS), ("APPROVED", APPROVED), ("POSTED", POSTED)):
        print(f"{label}:")
        for p in list_drafts(folder):
            d = load_json(p)
            extra = d.get("scheduled_date") or d.get("posted", {}).get("date", "")
            warn = "  ⚠ " + "; ".join(d["review_warnings"]) if d.get("review_warnings") else ""
            print(f"  {d['id']:7} {d['service']:9} {d['topic'][:50]:50} {extra}{warn}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("id", nargs="?")
    ap.add_argument("--date", help="YYYY-MM-DD; leave empty to publish at the next run")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list or not args.id:
        show()
        return 0
    matches = [p for p in list_drafts(DRAFTS) if p.name.startswith(args.id + "-")]
    if not matches:
        print(f"No draft starting with {args.id}")
        return 1
    src = matches[0]
    d = load_json(src)
    if args.date:
        dt.date.fromisoformat(args.date)
        d["scheduled_date"] = args.date
    d["status"] = "approved"
    d["review_warnings"] = []
    dest = APPROVED / src.name
    save_json(dest, d)
    src.unlink()
    print(f"✓ {src.name} → approved/ (scheduled: {d.get('scheduled_date') or 'next run'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
