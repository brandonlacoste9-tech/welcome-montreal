#!/usr/bin/env python3
"""Nightly refresh of events.json for the Welcome to Montreal guide.

Pulls upcoming Montreal events from two sources:
  1. Ticketmaster Discovery API (free consumer key in the Secure Vault as
     custom.ticketmaster) — concerts, sports, big shows.
  2. Tourinsoft SIT Québec tourism feed (free, no key) — official Québec
     tourism listings: festivals, markets, cultural events.
Merges them (Ticketmaster first, Tourinsoft deduped by name, capped),
rewrites events.json, commits, and pushes to GitHub via push-commit.py.
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
TS_EVENTS_URL = ("https://api-v3.tourinsoft.com/api/syndications/"
                  "mto.tourinsoft.com/c6ab1c9e-f594-463e-b036-5a029197f3a9?format=json")

SEGMENT_TO_CAT = {"Music": "concert", "Sports": "sport", "Arts & Theatre": "show"}

# Tourinsoft theme labels (French) -> event category. Checked in order.
TS_THEME_CAT = [
    (("sports et plein air",), "sport"),
    (("musique", "chanson"), "concert"),
    (("noël", "halloween", "festival", "foire", "carnaval",
      "gastronomie et plaisirs gourmands"), "festival"),
]
TS_PER_CAT = 15  # cap on Tourinsoft additions per category per refresh


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


def fetch_tourinsoft():
    """Free, keyless SIT Québec tourism feed (Tourisme Montréal syndication)."""
    req = urllib.request.Request(TS_EVENTS_URL, headers={"User-Agent": "welcome-montreal/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def ts_category(record):
    labels = []
    for t in (record.get("Themes") or []):
        for th in (t.get("Theme") or []):
            labels.append((th.get("ThesLibelle") or "").lower())
    for keywords, cat in TS_THEME_CAT:
        if any(kw in lbl for lbl in labels for kw in keywords):
            return cat
    return "show"


def ts_start_date(record):
    dates = [p.get("Datedebut", "")[:10]
             for p in (record.get("PeriodeOuvertures") or []) if p.get("Datedebut")]
    return min(dates) if dates else ""


def to_tourinsoft_events(data, today, cutoff):
    out = []
    for r in (data.get("value") or []):
        city = (r.get("Structure") or {}).get("City", "")
        if not city.lower().startswith(("montr", "montreal")):
            continue
        start = ts_start_date(r)
        if not (today <= start <= cutoff):
            continue
        name = (r.get("SyndicObjectName") or "").strip()
        if not name:
            continue
        adr = (r.get("Adresses") or [{}])[0]
        venue = (adr.get("Nomdupointdeservice") or "").strip()
        url = ""
        for s in (r.get("SiteInternets") or []):
            if (s.get("Moyendecommunication") or {}).get("ThesLibelle") == "Site internet":
                url = (s.get("Coordonnees") or "").strip()
                if url:
                    break
        out.append({
            "name": name,
            "date": start,
            "venue": venue,
            "category": ts_category(r),
            "url": url,
            "image": "",
        })
    out.sort(key=lambda e: e["date"])
    return out


def norm_name(name):
    return "".join(c for c in name.lower() if c.isalnum())


def main():
    today = dt.date.today()
    cutoff = (today + dt.timedelta(days=90)).isoformat()
    today_s = today.isoformat()

    try:
        data = fetch_events()
    except dc.DynamicCredentialError as exc:
        print(f"no ticketmaster key stored yet ({exc}); ticketmaster skipped")
        data = None
    tm_events = []
    if data:
        raw = (data.get("_embedded") or {}).get("events", [])
        for e in raw:
            try:
                venue = (e.get("_embedded") or {}).get("venues", [{}])[0].get("name", "")
                tm_events.append({
                    "name": e.get("name", ""),
                    "date": (e.get("dates") or {}).get("start", {}).get("localDate", ""),
                    "venue": venue,
                    "category": to_category(e),
                    "url": e.get("url", ""),
                    "image": best_image(e),
                })
            except (KeyError, TypeError):
                continue
    tm_events = [e for e in tm_events if e["name"] and e["date"]]

    try:
        ts_data = fetch_tourinsoft()
    except Exception as exc:  # keyless feed; a failure must not kill the TM refresh
        print(f"tourinsoft fetch failed ({exc}); tourinsoft skipped")
        ts_data = None
    ts_events = to_tourinsoft_events(ts_data or {}, today_s, cutoff) if ts_data else []

    seen = {norm_name(e["name"]) for e in tm_events}
    merged = list(tm_events)
    added = 0
    per_cat = {}
    for e in ts_events:  # already date-sorted; per-category caps keep the mix
        key = norm_name(e["name"])
        n = per_cat.get(e["category"], 0)
        if key in seen or n >= TS_PER_CAT:
            continue
        seen.add(key)
        per_cat[e["category"]] = n + 1
        merged.append(e)
        added += 1

    payload = {"updated": today_s, "events": merged}
    with open(f"{REPO_DIR}/events.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    run("git", "add", "events.json")
    if not run("git", "status", "--porcelain"):
        print("no changes")
        return 0
    run("git", "-c", "user.email=brandonlacoste9-tech@users.noreply.github.com",
        "-c", "user.name=brandonlacoste9-tech",
        "commit", "-m", f"nightly events refresh {payload['updated']} ({len(merged)} events: "
                     f"{len(tm_events)} ticketmaster + {added} tourinsoft)")
    sha = run("git", "rev-parse", "HEAD")
    out = run("python3", "/home/hatch/workspace/skills/github/bin/push-commit.py", OWNER, REPO, sha)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
