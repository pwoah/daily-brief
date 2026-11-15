#!/usr/bin/env python3
"""Build the Daily Brief page from RSS/Atom feeds. Standard library only, no AI.

Usage: python build.py            -> writes public/index.html
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
FEEDS = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
TEMPLATE = (ROOT / "template.html").read_text(encoding="utf-8")
OUT = ROOT / "public" / "index.html"

TZ = ZoneInfo("America/Vancouver")
MAX_AGE = timedelta(hours=36)   # only stories from roughly the last day and a half
PER_SECTION = 9
UA = "Mozilla/5.0 (DailyBrief RSS builder; +https://github.com)"

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA_DC = "{http://purl.org/dc/elements/1.1/}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        d = parsedate_to_datetime(text)  # RSS: RFC 822
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))  # Atom: ISO 8601
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def clean(text, limit=220):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def parse_feed(raw, source):
    root = ET.fromstring(raw)
    items = []
    if root.tag == ATOM + "feed":
        for e in root.findall(ATOM + "entry"):
            link = ""
            for l in e.findall(ATOM + "link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            items.append({
                "title": clean(e.findtext(ATOM + "title"), 160),
                "url": link,
                "teaser": clean(e.findtext(ATOM + "summary") or e.findtext(ATOM + "content")),
                "date": parse_date(e.findtext(ATOM + "updated") or e.findtext(ATOM + "published")),
                "source": source,
            })
    else:  # RSS 2.0 and RSS 1.0/RDF: match child tags by local name, ignoring namespaces
        def kid(e, *names):
            for c in e:
                if c.tag.rsplit("}", 1)[-1] in names and (c.text or "").strip():
                    return c.text
            return ""
        for e in root.iter():
            if e.tag.rsplit("}", 1)[-1] != "item":
                continue
            items.append({
                "title": clean(kid(e, "title"), 160),
                "url": kid(e, "link").strip(),
                "teaser": clean(kid(e, "description")),
                "date": parse_date(kid(e, "pubDate", "date")),
                "source": source,
            })
    return [i for i in items if i["title"] and i["url"].startswith("http")]


def load(feed):
    try:
        items = parse_feed(fetch(feed["url"]), feed["source"])
        for i in items:
            i["paywall"] = feed.get("paywall", False)
        return feed, items, None
    except Exception as exc:  # one broken feed must never break the page
        return feed, [], f"{feed['source']}: {exc.__class__.__name__}"


def norm(title):
    return re.sub(r"[^a-z0-9 ]", "", title.lower())[:70]


def main():
    now = datetime.now(timezone.utc)
    jobs = [dict(f, section=s["name"]) for s in FEEDS for f in s["feeds"]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(load, jobs))

    errors = [err for _, _, err in results if err]
    by_section = {s["name"]: [] for s in FEEDS}
    for feed, items, _ in results:
        by_section[feed["section"]].extend(items)

    sections = []
    seen = set()
    for s in FEEDS:
        fresh = [i for i in by_section[s["name"]] if i["date"] and now - i["date"] <= MAX_AGE]
        pool_ = fresh or by_section[s["name"]]  # fall back to the newest available if a feed has no dates
        oldest = datetime.min.replace(tzinfo=timezone.utc)
        by_src = {}
        for i in sorted(pool_, key=lambda i: i["date"] or oldest, reverse=True):
            by_src.setdefault(i["source"], []).append(i)
        mixed = []
        while any(by_src.values()):
            for q in by_src.values():
                if q:
                    mixed.append(q.pop(0))
        picked = []
        for i in mixed:
            k = norm(i["title"])
            if k in seen:
                continue
            seen.add(k)
            picked.append({
                "title": i["title"], "url": i["url"], "teaser": i["teaser"], "source": i["source"],
                "time": i["date"].astimezone(TZ).strftime("%b %-d, %-I:%M %p") if i["date"] else "",
                "paywall": bool(i.get("paywall")),
                "_d": (i["date"] or oldest).timestamp(),
            })
            if len(picked) >= PER_SECTION:
                break
        picked.sort(key=lambda x: x["_d"], reverse=True)
        for x in picked:
            del x["_d"]
        if picked:
            sections.append({"name": s["name"], "items": picked})

    data = {
        "built": now.astimezone(TZ).strftime("%A, %B %-d, %Y · %-I:%M %p"),
        "builtIso": now.isoformat(),
        "sections": sections,
        "errors": errors,
    }
    page = TEMPLATE.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    total = sum(len(s["items"]) for s in sections)
    print(f"Wrote {OUT} with {total} stories in {len(sections)} sections; {len(errors)} feed errors")
    for e in errors:
        print("  ", e)
    if total == 0:
        sys.exit("No stories at all; refusing to publish an empty page.")


if __name__ == "__main__":
    main()
