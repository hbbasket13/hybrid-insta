"""Refresh the long-lived Instagram token (60 days) and print the new one.

Usage:
    IG_ACCESS_TOKEN=... python scripts/refresh_token.py                       # IG_API=instagram (default)
    FB_APP_ID=... FB_APP_SECRET=... IG_ACCESS_TOKEN=... IG_API=facebook python scripts/refresh_token.py

IG_API=instagram  → GET graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token
                    (token must be at least 24 hours old and not yet expired; no app secret needed)
IG_API=facebook   → GET graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token
                    (needs FB_APP_ID / FB_APP_SECRET; a Page token never expires and needs no refresh)

In GitHub Actions the workflow writes the new token back into the IG_ACCESS_TOKEN secret with `gh secret set`.
"""
from __future__ import annotations

import requests

from common import env


def main() -> int:
    api = env("IG_API", "instagram").lower()
    version = env("GRAPH_VERSION", "v21.0")
    token = env("IG_ACCESS_TOKEN", required=True)

    if api == "instagram":
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=60)
    elif api == "facebook":
        r = requests.get(f"https://graph.facebook.com/{version}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": env("FB_APP_ID", required=True),
            "client_secret": env("FB_APP_SECRET", required=True),
            "fb_exchange_token": token,
        }, timeout=60)
    else:
        raise SystemExit(f"IG_API must be 'instagram' or 'facebook', got {api!r}")

    if r.status_code >= 400:
        raise SystemExit(f"Refresh failed {r.status_code}: {r.text}")
    print(r.json()["access_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
