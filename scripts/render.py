"""Render carousel drafts to PNG slides with Playwright (Chromium).

Usage:
    python scripts/render.py                 # render every draft in drafts/ and approved/ lacking PNGs
    python scripts/render.py --all           # re-render everything (after a template/brand change)
    python scripts/render.py --file drafts/T-001-desk-worker.json
    python scripts/render.py --html-only     # write assets/<id>/preview.html without screenshots

Output: assets/<id>/slide-01.png ... slide-NN.png, story.png, preview.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common import APPROVED, ASSETS, DRAFTS, TEMPLATES, brand, list_drafts, load_json, services


CHARACTERS = ASSETS.parent / "characters"
STRINGS = {
    "ko": {"book": "예약", "phone": "전화", "chatswood_hint": "(I-MED 영상의학 내)", "cbd_hint": "(QVB 근처)",
           "story_tag": "전체 내용은 피드에서 확인하세요", "disclaimer": "일반 건강 정보이며 개인 진료를 대신하지 않아요"},
    "en": {"book": "Book", "phone": "Call", "chatswood_hint": "(inside I-MED Radiology)", "cbd_hint": "(near QVB)",
           "story_tag": "Full post on our feed", "disclaimer": "General information only — not a substitute for an individual assessment."},
}


def load_characters() -> tuple[dict, dict]:
    """Inline SVG per character name, with ids namespaced so several can share one page."""
    import re
    chars, ratio = {}, {}
    bundle = CHARACTERS / "bundle.json"
    sources = list(json.loads(bundle.read_text(encoding="utf-8")).items()) if bundle.exists() else \
        [(p.stem, p.read_text(encoding="utf-8")) for p in sorted(CHARACTERS.glob("*.svg"))]
    for name, svg in sources:
        svg = re.sub(r"<\?xml[^>]*>\s*", "", svg)
        ids = set(re.findall(r'id="([^"]+)"', svg))
        for i in ids:
            svg = svg.replace(f'id="{i}"', f'id="{name}-{i}"').replace(f"url(#{i})", f"url(#{name}-{i})").replace(f'href="#{i}"', f'href="#{name}-{i}"')
        m = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg)
        if m:
            w, h = float(m.group(3)), float(m.group(4))
            ratio[name] = w / h if h else 1
        chars[name] = svg
    return chars, ratio


def render_html(draft: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    svc = services()[draft["service"]]
    if draft.get("style") == "comic":
        tpl = env.get_template("comic.html")
        chars, ratio = load_characters()
        lang = draft.get("lang", "en")
        t = STRINGS.get(lang, STRINGS["en"])
        return tpl.render(brand=brand(), svc=svc, slides=draft["slides"], story=draft.get("story"), lang=lang,
                          chars=chars, chars_ratio=ratio, t=t, disclaimer=t["disclaimer"])
    tpl = env.get_template("carousel.html")
    return tpl.render(brand=brand(), svc=svc, slides=draft["slides"], story=draft.get("story"))


def render_draft(path: Path, html_only: bool = False) -> Path:
    draft = load_json(path)
    out_dir = ASSETS / draft["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(draft)
    preview = out_dir / "preview.html"
    preview.write_text(html, encoding="utf-8")
    if html_only:
        return out_dir

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        page.goto(preview.resolve().as_uri())
        try:
            page.wait_for_load_state("networkidle", timeout=8000)  # let Google Fonts arrive if network exists
        except Exception:
            pass
        page.wait_for_timeout(300)
        sections = page.locator("section.slide")
        n = sections.count()
        for old in out_dir.glob("slide-*.png"):
            old.unlink()
        for i in range(n):
            el = sections.nth(i)
            idx = el.get_attribute("data-index")
            name = "story.png" if idx == "story" else f"slide-{int(idx):02d}.png"
            el.screenshot(path=str(out_dir / name), type="png")
        browser.close()
    return out_dir


def needs_render(path: Path) -> bool:
    draft = load_json(path)
    out_dir = ASSETS / draft["id"]
    return not (out_dir / "slide-01.png").exists() or (out_dir / "slide-01.png").stat().st_mtime < path.stat().st_mtime


def prune_stale(paths: list[Path]) -> int:
    """Delete slide PNGs left over after a post lost slides (e.g. 7 -> 6), so publish counts match."""
    removed = 0
    for path in paths:
        draft = load_json(path)
        if draft.get("style") == "prerendered":
            continue
        n = len(draft.get("slides", []))
        for png in (ASSETS / draft["id"]).glob("slide-*.png"):
            try:
                idx = int(png.stem.split("-")[1])
            except (IndexError, ValueError):
                continue
            if idx > n:
                png.unlink()
                removed += 1
                print(f"✗ removed stale {draft['id']}/{png.name}")
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()

    prune_stale(list_drafts(DRAFTS) + list_drafts(APPROVED))
    if args.file:
        targets = [Path(args.file)]
    else:
        targets = list_drafts(DRAFTS) + list_drafts(APPROVED)
        if not args.all:
            targets = [t for t in targets if needs_render(t)]
    # style "prerendered": slides were rendered outside this repo and imported as PNGs - never re-render them
    targets = [t for t in targets if load_json(t).get("style") != "prerendered"]
    if not targets:
        print("Nothing to render.")
        return 0
    for t in targets:
        out = render_draft(t, html_only=args.html_only)
        pngs = sorted(out.glob("*.png"))
        print(f"✓ {t.name} → {out.relative_to(out.parents[1])}/ ({len(pngs)} png)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
