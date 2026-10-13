"""Move non-comic posts out of approved/ into retired/ when config/retire.json says so.

The clinic switched to the Hybi comic format; the older carousel queue is kept in retired/ (not deleted)
so it can be revived later. Idempotent.
"""
from __future__ import annotations

import json
import shutil

from common import APPROVED, CONFIG, ROOT, list_drafts, load_json

RETIRED = ROOT / "retired"


def main() -> int:
    cfg = CONFIG / "retire.json"
    if not cfg.exists() or not load_json(cfg).get("retire_non_comic"):
        print("retire_legacy: nothing to do")
        return 0
    RETIRED.mkdir(exist_ok=True)
    n = 0
    for p in list_drafts(APPROVED):
        d = load_json(p)
        if d.get("style") != "comic":
            shutil.move(str(p), str(RETIRED / p.name))
            n += 1
    print(f"retire_legacy: moved {n} legacy post(s) to retired/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
