"""Publish the next approved carousel (and its story) to Instagram via the Graph API.

Usage:
    python scripts/publish.py                # publish the next due item in approved/
    python scripts/publish.py --dry-run      # show what would be published, call nothing
    python scripts/publish.py --file approved/T-001-....json
    python scripts/publish.py --no-story     # skip the story slide

Env:
    IG_ACCESS_TOKEN    long-lived token (either flavour below)
    IG_API             "instagram" (default) = Instagram API with Instagram Login, host graph.instagram.com
                       "facebook"            = Instagram API with Facebook Login, host graph.facebook.com
    IG_USER_ID         Instagram professional account id. Optional for IG_API=instagram (defaults to "me").
    PUBLIC_BASE_URL    where assets/ is reachable publicly, e.g. https://raw.githubusercontent.com/<owner>/<repo>/main
    GRAPH_VERSION      default v21.0

Picks the item whose scheduled_date is today or earlier (or unset), oldest first. Moves it to posted/ on success.
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import time
from pathlib import Path

import requests

from common import APPROVED, ASSETS, POSTED, brand, env, list_drafts, load_json, save_json

HOSTS = {"instagram": "https://graph.instagram.com", "facebook": "https://graph.facebook.com"}


class IG:
    def __init__(self, user_id: str, token: str, version: str, api: str = "instagram"):
        host = HOSTS.get(api)
        if not host:
            raise SystemExit(f"IG_API must be one of {list(HOSTS)}, got {api!r}")
        self.user_id, self.token, self.base = user_id, token, f"{host}/{version}"

    def _post(self, path: str, **params) -> dict:
        params["access_token"] = self.token
        r = requests.post(f"{self.base}/{path}", data=params, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"Graph API error {r.status_code}: {r.text}")
        return r.json()

    def _get(self, path: str, **params) -> dict:
        params["access_token"] = self.token
        r = requests.get(f"{self.base}/{path}", params=params, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"Graph API error {r.status_code}: {r.text}")
        return r.json()

    def wait_ready(self, container_id: str, timeout_s: int = 180) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            info = self._get(container_id, fields="status_code,status")
            code = info.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Container {container_id} failed: {info}")
            time.sleep(5)
        raise RuntimeError(f"Container {container_id} not ready after {timeout_s}s")

    def carousel(self, image_urls: list[str], caption: str) -> str:
        children = []
        for url in image_urls:
            c = self._post(f"{self.user_id}/media", image_url=url, is_carousel_item="true")
            children.append(c["id"])
        for cid in children:
            self.wait_ready(cid)
        parent = self._post(f"{self.user_id}/media", media_type="CAROUSEL",
                            children=",".join(children), caption=caption)
        self.wait_ready(parent["id"])
        pub = self._post(f"{self.user_id}/media_publish", creation_id=parent["id"])
        return pub["id"]

    def reel(self, video_url: str, caption: str, cover_url: str | None = None) -> str:
        params = dict(media_type="REELS", video_url=video_url, caption=caption, share_to_feed="true")
        if cover_url:
            params["cover_url"] = cover_url
        c = self._post(f"{self.user_id}/media", **params)
        self.wait_ready(c["id"], timeout_s=900)
        pub = self._post(f"{self.user_id}/media_publish", creation_id=c["id"])
        return pub["id"]

    def story(self, image_url: str) -> str:
        c = self._post(f"{self.user_id}/media", image_url=image_url, media_type="STORIES")
        self.wait_ready(c["id"])
        pub = self._post(f"{self.user_id}/media_publish", creation_id=c["id"])
        return pub["id"]

    def permalink(self, media_id: str) -> str:
        return self._get(media_id, fields="permalink").get("permalink", "")


def pick_next(today: dt.date) -> Path | None:
    """Oldest due item. Due = scheduled_date (+ optional scheduled_time "HH:MM", Sydney time) is now or earlier."""
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("Australia/Sydney"))
    except Exception:
        now = dt.datetime.utcnow() + dt.timedelta(hours=10)
    stamp = now.strftime("%Y-%m-%d %H:%M")
    due = []
    for p in list_drafts(APPROVED):
        d = load_json(p)
        sched = d.get("scheduled_date")
        when = f"{sched} {d.get('scheduled_time', '00:00')}" if sched else "0000-00-00 00:00"
        if when <= stamp:
            due.append((when, d.get("created", ""), p))
    if not due:
        return None
    due.sort()
    return due[0][2]


def build_caption(d: dict) -> str:
    tags = " ".join(d.get("hashtags", []))
    return f"{d['caption'].strip()}\n.\n.\n.\n{tags}".strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-story", action="store_true")
    args = ap.parse_args()

    today = dt.date.today()
    path = Path(args.file) if args.file else pick_next(today)
    if not path:
        print("Nothing due in approved/.")
        return 0
    d = load_json(path)
    slides = sorted((ASSETS / d["id"]).glob("slide-*.png"))
    if not slides:
        print(f"No rendered slides for {d['id']} — run render.py first.", file=sys.stderr)
        return 1
    if len(slides) != len(d["slides"]):
        print(f"Slide count mismatch for {d['id']}: {len(slides)} png vs {len(d['slides'])} in JSON — re-render.", file=sys.stderr)
        return 1

    base = env("PUBLIC_BASE_URL", required=not args.dry_run).rstrip("/") or "https://example.invalid"
    urls = [f"{base}/assets/{d['id']}/{p.name}" for p in slides]
    story_png = ASSETS / d["id"] / "story.png"
    story_url = f"{base}/assets/{d['id']}/story.png" if story_png.exists() and not args.no_story else None
    is_reel = d.get("style") == "reel"
    video_url = f"{base}/assets/{d['id']}/reel.mp4" if is_reel else None
    if is_reel and not (ASSETS / d["id"] / "reel.mp4").exists():
        print(f"No reel.mp4 for {d['id']} — run render.py first.", file=sys.stderr)
        return 1
    caption = build_caption(d)

    print(f"Publishing {path.name}  [{d['service']}]  {d['topic']}")
    print(f"  {'reel video, ' if is_reel else ''}{len(urls)} slides, story={'yes' if story_url else 'no'}, caption {len(caption)} chars")
    if args.dry_run:
        print("  URLs:\n   " + "\n   ".join(urls))
        print("  Caption:\n" + caption)
        return 0

    # sanity check that the images are actually public before spending API calls
    for u in urls[:1] + ([story_url] if story_url else []):
        r = requests.head(u, allow_redirects=True, timeout=30)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
            print(f"Asset not publicly reachable as an image: {u} ({r.status_code}, {r.headers.get('content-type')})", file=sys.stderr)
            return 1

    api = env("IG_API", "instagram").lower()
    user_id = env("IG_USER_ID", "me" if api == "instagram" else None, required=(api == "facebook"))
    ig = IG(user_id, env("IG_ACCESS_TOKEN", required=True), env("GRAPH_VERSION", "v21.0"), api)
    if is_reel:
        # raw.githubusercontent serves .mp4 as application/octet-stream; jsDelivr mirrors the repo with video/mp4
        import re as _re
        m = _re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)", base)
        candidates = []
        if env("REEL_BASE_URL", ""):
            candidates.append(f"{env('REEL_BASE_URL').rstrip('/')}/assets/{d['id']}/reel.mp4")
        if m:
            candidates.append(f"https://cdn.jsdelivr.net/gh/{m.group(1)}/{m.group(2)}@{m.group(3)}/assets/{d['id']}/reel.mp4")
        candidates.append(video_url)
        media_id, last_err = None, None
        for vu in candidates:
            try:
                print(f"  video: {vu}")
                media_id = ig.reel(vu, caption, cover_url=urls[0])
                break
            except Exception as e:
                last_err = e
                print(f"  ⚠ reel attempt failed: {e}", file=sys.stderr)
        if not media_id:
            raise SystemExit(f"reel publish failed: {last_err}")
    else:
        media_id = ig.carousel(urls, caption)
    link = ig.permalink(media_id)
    print(f"  ✓ {'reel' if is_reel else 'carousel'} published: {media_id} {link}")

    story_id = None
    if story_url:
        try:
            story_id = ig.story(story_url)
            print(f"  ✓ story published: {story_id}")
        except Exception as e:  # story failure should not block the feed post
            print(f"  ⚠ story failed: {e}", file=sys.stderr)

    d["status"] = "posted"
    d["posted"] = {"date": today.isoformat(), "media_id": media_id, "permalink": link, "story_id": story_id}
    dest = POSTED / path.name
    save_json(dest, d)
    path.unlink()
    print(f"  moved to {dest.relative_to(dest.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
