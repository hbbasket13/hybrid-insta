"""Shared helpers for the clinic Instagram pipeline."""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
STYLE = ROOT / "style"
TEMPLATES = ROOT / "templates"
DRAFTS = ROOT / "drafts"
APPROVED = ROOT / "approved"
POSTED = ROOT / "posted"
ASSETS = ROOT / "assets"
REELS = ROOT / "reels"
TOPICS_CSV = ROOT / "topics.csv"

TOPIC_FIELDS = ["id", "service", "format", "topic", "angle", "location_tag", "status"]


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def brand() -> dict:
    return load_json(CONFIG / "brand.json")


def services() -> dict:
    return load_json(CONFIG / "services.json")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_topics() -> list[dict]:
    with open(TOPICS_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_topics(rows: list[dict]) -> None:
    with open(TOPICS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TOPIC_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TOPIC_FIELDS})


def slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "post"


def draft_filename(topic_id: str, topic: str) -> str:
    return f"{topic_id}-{slugify(topic)}.json"


def list_drafts(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*.json") if not p.name.startswith("."))


def env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise SystemExit(f"Missing required environment variable: {name}")
    return val or ""
