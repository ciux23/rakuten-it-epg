#!/usr/bin/env python3
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

CHANNELS = {
    "rai-1": "Rai1.it",
    "rai-2": "Rai2.it",
    "rai-3": "Rai3.it",
    "rai-4": "Rai4.it",
    "rai-5": "Rai5.it",
    "rai-movie": "RaiMovie.it",
    "rai-premium": "RaiPremium.it",
    "rai-news-24": "RaiNews24.it",
    "rai-sport": "RaiSport.it",
    "rai-radio-2": "RaiRadio2Visual.it",
}

BASE_URL = "https://www.raiplay.it/palinsesto/app/{slug}/{date}.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    ),
}


def fetch_day(slug, date_str):
    url = BASE_URL.format(slug=slug, date=date_str)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"  ⚠️  HTTP {e.code} per {slug} [{date_str}]", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  ⚠️  Errore rete per {slug} [{date_str}]: {e}", file=sys.stderr)
        return []
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"  ⚠️  Risposta non JSON per {slug} [{date_str}]", file=sys.stderr)
        return []
    return data.get("events", [])


def event_to_xmltv_times(event):
    date_str = event["date"]
    hour_str = event["hour"]
    duration_str = event["duration"]
    start_dt = datetime.strptime(f"{date_str} {hour_str}", "%d/%m/%Y %H:%M")
    dur_h, dur_m, dur_s = (int(x) for x in duration_str.split(":"))
    stop_dt = start_dt + timedelta(hours=dur_h, minutes=dur_m, seconds=dur_s)
    tz_offset = " +0200"
    start_xmltv = start_dt.strftime("%Y%m%d%H%M%S") + tz_offset
    stop_xmltv = stop_dt.strftime("%Y%m%d%H%M%S") + tz_offset
    return start_xmltv, stop_xmltv


def fetch_channel_full(slug, xmltv_id, days):
    print(f"→ {slug}")
    all_events = []
    seen_keys = set()
    today = datetime.now()
    for day_offset in range(days):
        date_str = (today + timedelta(days=day_offset)).strftime("%d-%m-%Y")
        events = fetch_day(slug, date_str)
        time.sleep(0.3)
        for ev in events:
            key = (ev.get("date"), ev.get("hour"), ev.get("name"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_events.append(ev)
    print(f"   {len(all_events)} programmi recuperati")
    return {"xmltv_id": xmltv_id, "title": slug, "programs": all_events}


def build_xmltv(channels_data):
    lines = []
    lines.append("<?xml version='1.0' encoding='utf-8'?>")
    lines.append('<tv generator-info-name="rai-epg" generator-info-url="https://www.raiplay.it">')
    for ch in channels_data:
        lines.append(f'  <channel id="{escape(ch["xmltv_id"])}">')
        lines.append(f'    <display-name lang="it">{escape(ch["title"])}</display-name>')
        lines.append("  </channel>")
    for ch in channels_data:
        for ev in ch["programs"]:
            try:
                start_xmltv, stop_xmltv = event_to_xmltv_times(ev)
            except (KeyError, ValueError):
                continue
            title = escape(ev.get("name") or "")
            desc = escape(ev.get("description") or "")
            lines.append(f'  <programme start="{start_xmltv}" stop="{stop_xmltv}" channel="{escape(ch["xmltv_id"])}">')
            lines.append(f'    <title lang="it">{title}</title>')
            if desc:
                lines.append(f'    <desc lang="it">{desc}</desc>')
            lines.append("  </programme>")
    lines.append("</tv>")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Genera EPG XMLTV per i canali Rai")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--out", default="epg_rai.xml")
    args = parser.parse_args()
    print(f"Genero EPG Rai per {len(CHANNELS)} canali, {args.days} giorni...\n")
    channels_data = []
    for slug, xmltv_id in CHANNELS.items():
        channels_data.append(fetch_channel_full(slug, xmltv_id, args.days))
    xml_content = build_xmltv(channels_data)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml_content)
    total_programs = sum(len(c["programs"]) for c in channels_data)
    print(f"\n✅ Scritto {args.out}: {len(channels_data)} canali, {total_programs} programmi totali.")


if __name__ == "__main__":
    main()
