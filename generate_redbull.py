#!/usr/bin/env python3
"""
Genera un file XMLTV con la programmazione (EPG) dei canali Red Bull TV,
interrogando l'endpoint pubblico usato dalla pagina Guida TV:

    https://tv-api.redbull.com/guides/v5.1/rbtv/{locale}/{lang}/rrn:content:video-channels:{uuid}

La risposta contiene "cards[]", ognuna con title, start_time, end_time,
long_description — già in ISO 8601 UTC (Z), niente calcolo aggiuntivo.

Uso:
    python3 generate_redbull.py [--out epg_redbull.xml]
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from xml.sax.saxutils import escape

# ------------------------------------------------------------------
# Canali Red Bull, mappati UUID (lo stesso usato per gli URL stream
# in config.yaml) -> xmltv_id (coerente con gli slug redbull_* usati
# nei canali direct_channels).
# ------------------------------------------------------------------
CHANNELS = {
    "c81f8686-ab67-4965-ba04-5f6658bb96cc": ("redbull_tv", "Red Bull TV"),
    "ee30c528-32b1-4604-8976-e3bcee4ae7f0": ("redbull_bike", "Red Bull Bike"),
    "870bcfa8-62b1-4e84-9c85-39f083df368a": ("redbull_adventure", "Red Bull Adventure"),
    "fd4ed3c9-1800-477b-9909-53255da06632": ("redbull_motorsports", "Red Bull Motorsports"),
    "69a66f02-21fd-42a1-be5b-6965541cfe6a": ("redbull_action_reel", "Red Bull Action Reel"),
}

BASE_URL = "https://tv-api.redbull.com/guides/v5.1/rbtv/it_IT/it/rrn:content:video-channels:{uuid}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def fetch_channel(uuid):
    url = BASE_URL.format(uuid=uuid)
    req = urllib.request.Request(url, headers=HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"  ⚠️  HTTP {e.code} per {uuid}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  ⚠️  Errore rete per {uuid}: {e}", file=sys.stderr)
        return []

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"  ⚠️  Risposta non JSON per {uuid}", file=sys.stderr)
        return []

    return data.get("cards", [])


def iso_to_xmltv(iso_string):
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    return dt.strftime("%Y%m%d%H%M%S %z")


def build_xmltv(channels_data):
    lines = []
    lines.append("<?xml version='1.0' encoding='utf-8'?>")
    lines.append(
        '<tv generator-info-name="redbull-epg" '
        'generator-info-url="https://tv-api.redbull.com">'
    )

    for ch in channels_data:
        lines.append(f'  <channel id="{escape(ch["xmltv_id"])}">')
        lines.append(f'    <display-name lang="it">{escape(ch["title"])}</display-name>')
        lines.append("  </channel>")

    for ch in channels_data:
        for card in ch["programs"]:
            start_raw = card.get("start_time")
            stop_raw = card.get("end_time")
            if not start_raw or not stop_raw:
                continue

            try:
                start_xmltv = iso_to_xmltv(start_raw)
                stop_xmltv = iso_to_xmltv(stop_raw)
            except ValueError:
                continue

            title = escape(card.get("title") or "")
            desc = escape(card.get("long_description") or card.get("short_description") or "")

            lines.append(f'  <programme start="{start_xmltv}" stop="{stop_xmltv}" channel="{escape(ch["xmltv_id"])}">')
            lines.append(f'    <title lang="it">{title}</title>')
            if desc:
                lines.append(f'    <desc lang="it">{desc}</desc>')
            lines.append("  </programme>")

    lines.append("</tv>")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Genera EPG XMLTV per i canali Red Bull TV")
    parser.add_argument("--out", default="epg_redbull.xml", help="File di output (default: epg_redbull.xml)")
    args = parser.parse_args()

    print(f"Genero EPG Red Bull per {len(CHANNELS)} canali...\n")

    channels_data = []
    for uuid, (xmltv_id, title) in CHANNELS.items():
        print(f"→ {title}")
        cards = fetch_channel(uuid)
        print(f"   {len(cards)} programmi recuperati")
        channels_data.append({"xmltv_id": xmltv_id, "title": title, "programs": cards})
        time.sleep(0.3)

    xml_content = build_xmltv(channels_data)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml_content)

    total_programs = sum(len(c["programs"]) for c in channels_data)
    print(f"\n✅ Scritto {args.out}: {len(channels_data)} canali, {total_programs} programmi totali.")


if __name__ == "__main__":
    main()
