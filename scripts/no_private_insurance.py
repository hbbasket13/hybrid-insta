"""Remove private health insurance talk (health funds, extras cover, HICAPS) from drafts/ and approved/.

Medicare, WorkCover, CTP, NDIS and DVA mentions are kept. Idempotent: safe to run on every workflow run.

Usage:
    python scripts/no_private_insurance.py
"""
from __future__ import annotations

import re

from common import APPROVED, DRAFTS, list_drafts, load_json, save_json

FUND = re.compile(r"HICAPS|health fund|extras|\bfunds?\b|private health|policy's limits|annual limit", re.I)

# Exact phrase fixes applied before sentence removal (keeps the rest of the sentence).
PHRASES = [
    (" and claim with HICAPS if your extras cover includes physio", ""),
    ("Your health fund card, so you can claim on the spot with HICAPS if your extras cover includes the service. ", ""),
    ("Health fund card, referral or claim number", "Referral or claim number"),
    ("We also see people under", "We see people under"),
    ("We accept private, HICAPS, Medicare, NDIS, DVA, WorkCover and CTP funding.",
     "We also see people under Medicare plans, NDIS, DVA, WorkCover and CTP."),
]
DROP_TAGS = {"#hicaps", "#healthfund", "#extrascover", "#privatehealthinsurance", "#healthinsurance"}
FILLER = ["#sydney", "#northshore", "#sydneycbd", "#chatswood", "#alliedhealth", "#hybridphysiotherapy"]
SPLIT = re.compile(r"(?<=[.!?])\s+")
NUM = re.compile(r"^\d+\.\s+")


def fix_phrases(s: str) -> str:
    for a, b in PHRASES:
        s = s.replace(a, b)
    return s


def strip_sentences(text: str) -> str:
    text = fix_phrases(text)
    if not FUND.search(text):
        return text
    paras = []
    for para in text.split("\n\n"):
        kept = [s for s in SPLIT.split(para) if not FUND.search(s)]
        para = " ".join(kept).strip()
        if para:
            paras.append(para)
    return "\n\n".join(paras)


def fix_post(d: dict) -> dict:
    out = dict(d)
    slides = []
    for s in d.get("slides", []):
        s = dict(s)
        if s.get("kind") == "body" and FUND.search(fix_phrases(s.get("title", ""))):
            continue
        for k in ("body", "sub", "headline"):
            if k in s:
                s[k] = strip_sentences(s[k])
        if s.get("kind") == "body" and not s.get("body"):
            continue
        slides.append(s)
    if any(NUM.match(s.get("title", "")) for s in slides if s.get("kind") == "body"):
        n = 1
        for s in slides:
            if s.get("kind") == "body" and NUM.match(s.get("title", "")):
                s["title"] = f"{n}. " + NUM.sub("", s["title"])
                n += 1
    out["slides"] = slides
    if "caption" in out:
        out["caption"] = strip_sentences(out["caption"])
    if isinstance(out.get("story"), dict):
        st = dict(out["story"])
        for k in ("headline", "body"):
            if k in st:
                new = strip_sentences(st[k])
                st[k] = new or st[k]
        out["story"] = st
    tags = [t for t in d.get("hashtags", []) if t.lower() not in DROP_TAGS]
    for f in FILLER:
        if len(tags) >= 12:
            break
        if f not in tags:
            tags.append(f)
    out["hashtags"] = tags
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
    print(f"Private insurance cleanup: {changed} file(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
