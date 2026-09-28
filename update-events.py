#!/usr/bin/env python3
"""Nightly refresh of events.json for the Welcome to Montreal guide.

Pulls upcoming Montreal events from the Ticketmaster Discovery API
(free consumer key stored in the Secure Vault as custom.ticketmaster),
rewrites events.json, commits, and pushes to GitHub via push-commit.py.
Exits quietly (code 0, note on stdout) when no key is stored yet.
"""
import base64
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import dynamic_credentials as dc  # noqa: E402

REPO_DIR = "/home/hatch/workspace/welcome-montreal"
OWNER, REPO = "brandonlacoste9-tech", "welcome-montreal"
TM_HOST = "app.ticketmaster.com"

SEGMENT_TO_CAT = {"Music": "concert", "Sports": "sport", "Arts & Theatre": "show"}


def run(*args, cwd=REPO_DIR):
    return subprocess.run(args, capture_output=True, text=True, cwd=cwd, check=True).stdout.strip()


def fetch_events():
    now = dt.datetime.now(dt.timezone.utc)
    end = now + dt.timedelta(days=90)
    base = (
        f"https://{TM_HOST}/discovery/v2/events.json"
        f"?city=Montreal&countryCode=CA"
        f"&startDateTime={now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&endDateTime={end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&size=100&sort=date,asc&locale=en"
    )
    direct = os.environ.get("TM_API_KEY")  # transient one-off override, never stored
    if direct:
        base += f"&apikey={urllib.parse.quote(direct.strip(), safe='')}"
        url = base
    else:
        url = dc.url_with_surrogate_query_param(base, "custom.ticketmaster", allowed_hosts=[TM_HOST])
    req = urllib.request.Request(url, headers={"User-Agent": "welcome-montreal/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def to_category(event):
    try:
        seg = event["classifications"][0]["segment"]["name"]
    except (KeyError, IndexError, TypeError):
        return "show"
    if seg == "Miscellaneous":
        try:
            genre = event["classifications"][0].get("genre", {}).get("name", "")
            if "festival" in genre.lower():
                return "festival"
        except (KeyError, AttributeError):
            pass
        return "show"
    return SEGMENT_TO_CAT.get(seg, "show")


def best_image(event):
    imgs = [i for i in (event.get("images") or []) if i.get("url")]
    if not imgs:
        return ""
    wide = [i for i in imgs if i.get("ratio") == "16_9"]
    pool = wide or imgs
    pool.sort(key=lambda i: abs((i.get("width") or 0) - 1024))
    return pool[0]["url"]


def main():
    try:
        data = fetch_events()
    except dc.DynamicCredentialError as exc:
        print(f"no ticketmaster key stored yet ({exc}); skipping")
        return 0
    raw = (data.get("_embedded") or {}).get("events", [])
    events = []
    for e in raw:
        try:
            venue = (e.get("_embedded") or {}).get("venues", [{}])[0].get("name", "")
            events.append({
                "name": e.get("name", ""),
                "date": (e.get("dates") or {}).get("start", {}).get("localDate", ""),
                "venue": venue,
                "category": to_category(e),
                "url": e.get("url", ""),
                "image": best_image(e),
            })
        except (KeyError, TypeError):
            continue
    events = [e for e in events if e["name"] and e["date"]]
    payload = {"updated": dt.date.today().isoformat(), "events": events}
    with open(f"{REPO_DIR}/events.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    run("git", "add", "events.json")
    if not run("git", "status", "--porcelain"):
        print("no changes")
        return 0
    run("git", "-c", "user.email=brandonlacoste9-tech@users.noreply.github.com",
        "-c", "user.name=brandonlacoste9-tech",
        "commit", "-m", f"nightly events refresh {payload['updated']} ({len(events)} events)")
    sha = run("git", "rev-parse", "HEAD")
    out = run("python3", "/home/hatch/workspace/skills/github/bin/push-commit.py", OWNER, REPO, sha)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
