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
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common import APPROVED, ASSETS, DRAFTS, TEMPLATES, brand, list_drafts, load_json, services


def render_html(draft: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    tpl = env.get_template("carousel.html")
    svc = services()[draft["service"]]
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--html-only", action="store_true")
    args = ap.parse_args()

    if args.file:
        targets = [Path(args.file)]
    else:
        targets = list_drafts(DRAFTS) + list_drafts(APPROVED)
        if not args.all:
            targets = [t for t in targets if needs_render(t)]
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
