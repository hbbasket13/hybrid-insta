"""Rewrite drafts/ and approved/ posts so they only reference the Sydney clinics (Chatswood, Sydney CBD).

Idempotent: safe to run on every workflow run. Only touches files that actually change.

Usage:
    python scripts/sydney_only.py
"""
from __future__ import annotations

import json
import re

from common import APPROVED, DRAFTS, list_drafts, load_json, save_json

PHRASES = [
    (r"\b(Milton and Sunnybank|Sunnybank and Milton)\b", "Chatswood and Sydney CBD"),
    (r"Hybrid Physiotherapy works with WorkCover claims in NSW and Queensland\.",
     "Hybrid Physiotherapy works with NSW WorkCover claims."),
    (r" The details differ a little between NSW and Queensland, but the steps are similar\.", ""),
    (r"\bMilton\b", "Chatswood"),
    (r"\bSunnybank\b", "Sydney CBD"),
    (r"\bBrisbane\b", "Sydney"),
    (r"\bQueensland\b", "NSW"),
]

TAGS = {
    "#brisbane": "#sydney", "#brisbanephysio": "#sydneyphysio", "#miltonphysio": "#chatswoodphysio",
    "#sunnybankphysio": "#sydneycbdphysio", "#milton": "#chatswood", "#sunnybank": "#sydneycbd",
    "#brisbanechiro": "#sydneychiro", "#brisbanechiropractor": "#sydneychiropractor",
    "#brisbanepilates": "#sydneypilates", "#brisbanemassage": "#sydneymassage",
    "#brisbaneremedialmassage": "#sydneyremedialmassage", "#queensland": "#nsw",
    "#runbrisbane": "#runsydney", "#brisbanerunners": "#sydneyrunners",
}
FILLER = ["#sydney", "#chatswood", "#sydneycbd", "#northshore", "#nsw", "#hybridphysiotherapy"]
LOC = {"Milton": "Chatswood", "Sunnybank": "Sydney CBD"}


def fix_text(s: str) -> str:
    for pat, rep in PHRASES:
        s = re.sub(pat, rep, s)
    return s


def fix_obj(o):
    if isinstance(o, str):
        return fix_text(o)
    if isinstance(o, list):
        return [fix_obj(x) for x in o]
    if isinstance(o, dict):
        return {k: fix_obj(v) for k, v in o.items()}
    return o


def fix_post(d: dict) -> dict:
    out = dict(d)
    tags = [TAGS.get(t.lower(), t) for t in d.get("hashtags", [])]
    seen, clean = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            clean.append(t)
    for f in FILLER:
        if len(clean) >= 12:
            break
        if f not in seen:
            clean.append(f)
            seen.add(f)
    out["location_tag"] = LOC.get(d.get("location_tag"), d.get("location_tag"))
    for key in ("slides", "caption", "story", "alt_text", "topic"):
        if key in out:
            out[key] = fix_obj(out[key])
    out["hashtags"] = clean
    return out


def main() -> int:
    changed = 0
    for folder in (DRAFTS, APPROVED):
        for p in list_drafts(folder):
            d = load_json(p)
            new = fix_post(d)
            if new != d:
                save_json(p, new)
                changed += 1
                print(f"✓ {folder.name}/{p.name}")
    print(f"Sydney-only fix: {changed} file(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
