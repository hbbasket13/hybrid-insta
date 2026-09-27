"""Generate Instagram drafts (carousel JSON or reel scripts) from topics.csv using the Claude API.

Usage:
    python scripts/generate.py            # generate up to 3 pending topics
    python scripts/generate.py --count 5
    python scripts/generate.py --id T-003 # regenerate one topic (even if already drafted)
    python scripts/generate.py --dry-run  # print the prompt, call nothing

Output:
    drafts/<id>-<slug>.json   for carousels (then run render.py to make PNGs)
    reels/<id>-<slug>.md      for reel scripts (shoot manually, caption is ready)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

from common import (CONFIG, DRAFTS, REELS, STYLE, brand, draft_filename, env,
                    read_text, read_topics, save_json, services, slugify,
                    write_topics)

MODEL = env("CLAUDE_MODEL", "claude-sonnet-4-5")

CAROUSEL_SCHEMA = """
Return ONLY a JSON object (no markdown fences) with exactly this shape:
{
  "slides": [
    {"kind": "cover", "headline": "<max 9 words>", "sub": "<max 14 words>"},
    {"kind": "body", "title": "<max 7 words>", "body": "<max 45 words>"},
    ... 4 to 6 body slides ...
    {"kind": "cta", "headline": "<max 8 words>", "body": "<max 30 words: which service helps + what the first visit involves>"}
  ],
  "caption": "<80-150 words, first line is the hook, ends with the disclaimer line>",
  "hashtags": ["#tag1", "... 12 to 18 tags ..."],
  "alt_text": "<one sentence describing the carousel for screen readers>",
  "story": {"headline": "<max 8 words>", "body": "<max 25 words, the single most useful takeaway>"}
}
Rules: total slides 6-8. Use straight quotes only inside strings (escape them). No emojis in slide text; 0-2 emojis allowed in the caption.
"""

REEL_SCHEMA = """
Return ONLY a JSON object (no markdown fences) with exactly this shape:
{
  "hook": "<spoken opening line, max 12 words, on screen in the first 2 seconds>",
  "duration_seconds": <15-30>,
  "shots": [
    {"t": "0-3s", "say": "<what the practitioner says>", "show": "<what is on camera>", "text_overlay": "<max 6 words>"},
    ... 4 to 7 shots ...
  ],
  "cover_text": "<max 6 words for the reel cover>",
  "caption": "<60-120 words, hook first line, ends with the disclaimer line>",
  "hashtags": ["#tag1", "... 10 to 15 tags ..."],
  "shooting_notes": "<2-3 sentences: framing, lighting, what to avoid>"
}
"""


def build_system_prompt(service_key: str) -> str:
    svc = services()[service_key]
    b = brand()
    return "\n\n".join([
        "You write Instagram content for an Australian allied-health clinic. You are meticulous about advertising compliance.",
        f"CLINIC: {b['clinic_name']} ({b['handle']}). Locations: " + "; ".join(l["line"] for l in b["locations"]) + f". Booking: {b['booking_url']} (say 'link in bio').",
        f"SERVICE VOICE ({svc['label']}): {svc['voice']}",
        "VOICE GUIDE:\n" + read_text(STYLE / "voice.md"),
        "COMPLIANCE (mandatory):\n" + read_text(CONFIG / "compliance.md"),
        f"DISCLAIMER LINE (verbatim): {b['disclaimer']}",
    ])


def build_user_prompt(row: dict) -> str:
    fmt = row["format"]
    schema = CAROUSEL_SCHEMA if fmt == "carousel" else REEL_SCHEMA
    return (
        f"FORMAT: {fmt}\nSERVICE: {row['service']}\nTOPIC: {row['topic']}\nANGLE: {row['angle']}\n"
        f"LOCATION TO MENTION ONCE (caption or CTA): {row['location_tag']}\n\n{schema}"
    )


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start:end + 1])


def call_claude(system: str, user: str) -> dict:
    import anthropic  # imported lazily so --dry-run works without the SDK

    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    msg = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0.7,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    try:
        return extract_json(text)
    except (ValueError, json.JSONDecodeError):
        # one repair attempt: ask the model to fix its own JSON
        fix = client.messages.create(
            model=MODEL, max_tokens=4000, temperature=0,
            messages=[{"role": "user", "content": "Fix this so it is valid JSON. Return only the JSON.\n\n" + text}],
        )
        return extract_json("".join(b.text for b in fix.content if getattr(b, "type", "") == "text"))


def validate_carousel(data: dict) -> list[str]:
    problems = []
    slides = data.get("slides", [])
    if not 6 <= len(slides) <= 8:
        problems.append(f"slide count {len(slides)} not in 6-8")
    if slides and slides[0].get("kind") != "cover":
        problems.append("first slide is not cover")
    if slides and slides[-1].get("kind") != "cta":
        problems.append("last slide is not cta")
    banned = re.compile(r"\b(cure|guarantee[ds]?|pain-free for life|before and after|before/after|testimonial|#1|best physio)\b", re.I)
    blob = json.dumps(data, ensure_ascii=False)
    m = banned.search(blob)
    if m:
        problems.append(f"banned phrase found: '{m.group(0)}'")
    if brand()["disclaimer"].split("—")[0].strip().lower() not in data.get("caption", "").lower():
        problems.append("caption missing disclaimer")
    return problems


def write_reel_markdown(row: dict, data: dict) -> str:
    lines = [
        f"# {row['topic']}  ({row['id']} · {row['service']})",
        "",
        f"**Hook (first 2s, on screen):** {data['hook']}",
        f"**Target length:** {data.get('duration_seconds', 20)}s   ·   **Cover text:** {data.get('cover_text', '')}",
        "",
        "## Shot list",
        "",
        "| Time | Say | Show | Overlay |",
        "|---|---|---|---|",
    ]
    for s in data.get("shots", []):
        lines.append(f"| {s.get('t', '')} | {s.get('say', '')} | {s.get('show', '')} | {s.get('text_overlay', '')} |")
    lines += [
        "",
        "## Shooting notes",
        "",
        data.get("shooting_notes", ""),
        "",
        "## Caption (copy-paste)",
        "",
        data.get("caption", ""),
        "",
        " ".join(data.get("hashtags", [])),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--id", help="regenerate a specific topic id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = read_topics()
    if args.id:
        targets = [r for r in rows if r["id"] == args.id]
        if not targets:
            print(f"No topic with id {args.id}", file=sys.stderr)
            return 1
    else:
        targets = [r for r in rows if r["status"].strip().lower() == "pending"][: args.count]
    if not targets:
        print("Nothing pending in topics.csv")
        return 0

    today = dt.date.today().isoformat()
    for row in targets:
        system = build_system_prompt(row["service"])
        user = build_user_prompt(row)
        print(f"→ {row['id']} [{row['format']}/{row['service']}] {row['topic']}")
        if args.dry_run:
            print("----- SYSTEM -----\n" + system + "\n----- USER -----\n" + user)
            continue

        data = call_claude(system, user)

        if row["format"] == "carousel":
            problems = validate_carousel(data)
            if problems:
                print("   ⚠ regenerating once:", "; ".join(problems))
                data = call_claude(system, user + "\n\nPrevious attempt had these problems, fix them: " + "; ".join(problems))
                problems = validate_carousel(data)
            record = {
                "id": row["id"],
                "service": row["service"],
                "format": "carousel",
                "topic": row["topic"],
                "location_tag": row["location_tag"],
                "created": today,
                "scheduled_date": None,
                "status": "draft",
                "review_warnings": problems,
                **data,
            }
            out = DRAFTS / draft_filename(row["id"], row["topic"])
            save_json(out, record)
            print(f"   saved {out.relative_to(out.parents[1])}" + ("  ⚠ " + "; ".join(problems) if problems else ""))
        else:
            out = REELS / f"{row['id']}-{slugify(row['topic'])}.md"
            out.write_text(write_reel_markdown(row, data), encoding="utf-8")
            print(f"   saved {out.relative_to(out.parents[1])}")

        row["status"] = "drafted"

    if not args.dry_run:
        write_topics(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
