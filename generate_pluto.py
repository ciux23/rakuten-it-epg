#!/usr/bin/env python3
"""
Genera un file XMLTV con la programmazione (EPG) dei canali Pluto TV
Italia, interrogando l'API pubblica ufficiale:

    https://api.pluto.tv/v2/channels?start=...&stop=...

La risposta è una LISTA di canali (a differenza dell'API Rakuten, che
restituisce un canale alla volta), ognuno con il proprio campo
"timelines" contenente la programmazione nella finestra richiesta.

Nessuna autenticazione o sessione richiesta.

Uso:
    python3 generate_pluto.py [--hours N] [--out epg_pluto.xml]
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

CHANNEL_IDS = {
    "608aa17fb9f4490007e6419a": "pluto_film_tv",
    "608aa20a2e7f270007c4878d": "pluto_film_azione",
    "67ed14aaf7c5d70b9089c3bf": "pluto_serie_sci-fi",
}

BASE_URL = "https://api.pluto.tv/v2/channels"

DEFAULT_HOURS = 24


def fetch_all_channels(hours):
    now = datetime.now(timezone.utc)
    stop = now + timedelta(hours=hours)

    date_fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    params = {
        "start": now.strftime(date_fmt),
        "stop": stop.strftime(date_fmt),
    }
    url = BASE_URL + "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"⚠️  HTTP {e.code} interrogando Pluto TV", file=sys.stderr)
        return []
    except Exception as e:
        print(f"⚠️  Errore rete: {e}", file=sys.stderr)
        return []

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print("⚠️  Risposta non JSON da Pluto TV", file=sys.stderr)
        return []


def iso_to_xmltv(iso_string):
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    return dt.strftime("%Y%m%d%H%M%S %z")


def build_xmltv(channels_data):
    lines = []
    lines.append("<?xml version='1.0' encoding='utf-8'?>")
    lines.append(
        '<tv generator-info-name="pluto-epg" '
        'generator-info-url="https://api.pluto.tv">'
    )

    for ch in channels_data:
        lines.append(f'  <channel id="{escape(ch["xmltv_id"])}">')
        lines.append(f'    <display-name lang="it">{escape(ch["title"])}</display-name>')
        if ch["logo"]:
            lines.append(f'    <icon src="{escape(ch["logo"])}"></icon>')
        lines.append("  </channel>")

    for ch in channels_data:
        for prog in ch["programs"]:
            try:
                start_xmltv = iso_to_xmltv(prog["start"])
                stop_xmltv = iso_to_xmltv(prog["stop"])
            except (ValueError, KeyError):
                continue

            title = escape(prog.get("title") or "")
            desc = escape((prog.get("episode") or {}).get("description") or "")

            lines.append(
                f'  <programme start="{start_xmltv}" stop="{stop_xmltv}" '
                f'channel="{escape(ch["xmltv_id"])}">'
            )
            lines.append(f'    <title lang="it">{title}</title>')
            if desc:
                lines.append(f'    <desc lang="it">{desc}</desc>')
            lines.append("  </programme>")

    lines.append("</tv>")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Genera EPG XMLTV per canali Pluto TV Italia")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS, help=f"Ore di programmazione da recuperare (default: {DEFAULT_HOURS})")
    parser.add_argument("--out", default="epg_pluto.xml", help="File di output (default: epg_pluto.xml)")
    args = parser.parse_args()

    print(f"Recupero catalogo Pluto TV ({args.hours}h di programmazione)...\n")

    all_channels = fetch_all_channels(args.hours)
    print(f"   Canali totali nel catalogo ricevuto: {len(all_channels)}")
    if all_channels[:1]:
        print(f"   Esempio primo canale: id={all_channels[0].get('_id')!r} name={all_channels[0].get('name')!r}")
    if not all_channels:
        print("❌ Nessun dato ricevuto da Pluto TV.")
        sys.exit(1)

    by_id = {ch["_id"]: ch for ch in all_channels}

    channels_data = []
    for pluto_id, xmltv_id in CHANNEL_IDS.items():
        ch = by_id.get(pluto_id)

        if not ch:
            print(f"⚠️  Canale non trovato nel catalogo: {pluto_id}")
            continue

        logo = (ch.get("colorLogoPNG") or {}).get("path") or (ch.get("logo") or {}).get("path")

        channels_data.append({
            "xmltv_id": xmltv_id,
            "title": ch.get("name", xmltv_id),
            "logo": logo,
            "programs": ch.get("timelines", []),
        })

        print(f"→ {ch['name']}: {len(ch.get('timelines', []))} programmi")

    xml_content = build_xmltv(channels_data)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml_content)

    total_programs = sum(len(c["programs"]) for c in channels_data)
    print(f"\n✅ Scritto {args.out}: {len(channels_data)} canali, {total_programs} programmi totali.")


if __name__ == "__main__":
    main()
