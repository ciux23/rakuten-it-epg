#!/usr/bin/env python3
"""
Genera un file XMLTV con la programmazione (EPG) dei canali Rakuten TV
Italia, interrogando l'endpoint pubblico usato dal player web:

    https://gizmo.rakuten.tv/v3/live_channels/{CHANNEL_ID}
        ?device_identifier=web
        &epg_duration_minutes=...
        &epg_starts_at=...&epg_starts_at_timestamp=...
        &epg_ends_at=...&epg_ends_at_timestamp=...
        &locale=it&market_code=it

Va eseguito da una macchina con IP italiano (l'API applica geo-blocking
verso IP esteri) — sul Mac o sull'OMV, non da ambienti cloud esteri.

La risposta è un oggetto SINGOLO canale (data.id, data.title,
data.images, data.live_programs[]), non una lista.

Uso:
    python3 rakuten_epg_generate.py [--days N] [--out epg.xml]
"""

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

# ------------------------------------------------------------------
# Canali da includere. Ogni ID è lo slug ufficiale Rakuten (verificato
# con verify_rakuten_ids.py), usato sia per interrogare l'API sia come
# channel id nell'XMLTV finale — non vanno creati ID arbitrari.
# ------------------------------------------------------------------
CHANNEL_IDS = [
    "top-movies-rakuten-tv",
    "action-rakuten-tv",
    "comedy-rakuten-tv",
    "drama-rakuten-tv",
    "sci-fi-rakuten-tv",
    "filmrise-sci-fi-it",
    "crime-rakuten-tv",
]

BASE_URL = "https://gizmo.rakuten.tv/v3/live_channels/{channel_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://rakuten.tv",
    "Referer": "https://rakuten.tv/",
}

# L'API rifiuta finestre troppo ampie con exception.invalid_epg_ends_at:
# spezziamo il periodo totale in blocchi di questa durata (giorni).
BLOCK_DAYS = 3

# Timezone di riferimento per le date XMLTV (Italia).
TZ_ROME_OFFSET_HOURS = 2  # CEST; nota sotto per gestione DST


def iso_to_xmltv(iso_string):
    """
    Converte una data ISO 8601 con offset (es. 2026-08-26T19:37:41.000+02:00)
    nel formato XMLTV YYYYMMDDHHMMSS ±HHMM, preservando il timezone
    locale così come restituito dall'API (niente conversione a UTC).
    """
    dt = datetime.fromisoformat(iso_string)
    offset = dt.strftime("%z")  # es. "+0200"
    return dt.strftime("%Y%m%d%H%M%S") + " " + offset


def daterange_blocks(total_days, block_days):
    """
    Genera coppie (start, end) datetime timezone-aware (UTC), troncate
    a mezzanotte, che coprono da oggi a total_days nel futuro, spezzate
    in blocchi di block_days per rispettare il limite dell'API sulla
    lunghezza della finestra (verificato: ~7 giorni max, oltre restituisce
    exception.invalid_epg_ends_at).
    """
    now = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    blocks = []
    cursor = now
    remaining = total_days

    while remaining > 0:
        span = min(block_days, remaining)
        block_end = cursor + timedelta(days=span)
        blocks.append((cursor, block_end))
        cursor = block_end
        remaining -= span

    return blocks


def fetch_channel_block(channel_id, starts_at, ends_at):
    """
    Interroga l'API per un canale e una finestra temporale specifica.
    Restituisce il dict "data" del canale, o None in caso di errore.

    Formato verificato dall'utente via curl diretto: date troncate a
    mezzanotte UTC con suffisso Z (non offset locale), es.
    2026-08-26T00:00:00.000Z — non l'ora esatta di generazione.
    """
    duration_minutes = int((ends_at - starts_at).total_seconds() // 60)

    date_fmt = "%Y-%m-%dT%H:%M:%S.000Z"

    params = {
        "device_identifier": "web",
        "device_stream_audio_quality": "2.0",
        "device_stream_hdr_type": "NONE",
        "device_stream_video_quality": "HD",
        "epg_duration_minutes": str(duration_minutes),
        "epg_starts_at": starts_at.strftime(date_fmt),
        "epg_starts_at_timestamp": str(int(starts_at.timestamp())),
        "epg_ends_at": ends_at.strftime(date_fmt),
        "epg_ends_at_timestamp": str(int(ends_at.timestamp())),
        "locale": "it",
        "market_code": "it",
    }
    url = BASE_URL.format(channel_id=channel_id) + "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers=HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_body = resp.read()
            content_encoding = resp.headers.get("Content-Encoding", "")

        # urllib non decomprime automaticamente la risposta (a
        # differenza di requests): va fatto esplicitamente in base
        # al Content-Encoding, altrimenti su payload compressi il
        # decode utf-8 restituisce byte illeggibili e il parsing
        # JSON fallisce con "risposta non JSON".
        try:
            if content_encoding == "gzip":
                raw_body = gzip.decompress(raw_body)
            elif content_encoding == "deflate":
                raw_body = zlib.decompress(raw_body)
        except OSError as e:
            print(f"  ⚠️  Errore decompressione ({content_encoding}) per {channel_id}: {e}", file=sys.stderr)
            return None

        body = raw_body.decode("utf-8")
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        print(f"  ⚠️  HTTP {e.code} per {channel_id} "
              f"[{starts_at.date()} → {ends_at.date()}] — {error_body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ⚠️  Errore rete per {channel_id}: {e}", file=sys.stderr)
        return None

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(f"  ⚠️  Risposta non JSON per {channel_id}", file=sys.stderr)
        return None

    if "error" in payload:
        err_type = payload["error"].get("type", "sconosciuto")
        print(f"  ⚠️  API error per {channel_id}: {err_type}", file=sys.stderr)
        return None

    data = payload.get("data")
    if not data or not data.get("id"):
        print(f"  ⚠️  Campo data mancante per {channel_id}", file=sys.stderr)
        return None

    return data


def fetch_channel_full(channel_id, total_days):
    """
    Recupera title/logo/live_programs di un canale, unendo più blocchi
    temporali e deduplicando i programmi che si sovrappongono tra
    blocchi consecutivi (dedup per starts_at+title).
    """
    print(f"→ {channel_id}")

    title = None
    logo = None
    programs = []
    seen_program_keys = set()

    for starts_at, ends_at in daterange_blocks(total_days, BLOCK_DAYS):
        data = fetch_channel_block(channel_id, starts_at, ends_at)
        time.sleep(0.4)  # non martellare l'API

        if not data:
            continue

        if title is None:
            title = data.get("title", channel_id)
            logo = (data.get("images") or {}).get("artwork")

        for prog in data.get("live_programs", []):
            key = (prog.get("starts_at"), prog.get("title"))
            if key in seen_program_keys:
                continue
            seen_program_keys.add(key)
            programs.append(prog)

    programs.sort(key=lambda p: p.get("starts_at", ""))

    print(f"   {len(programs)} programmi recuperati"
          + (f" — titolo: {title!r}" if title else " — NESSUN DATO"))

    return {
        "id": channel_id,
        "title": title or channel_id,
        "logo": logo,
        "programs": programs,
    }


def build_xmltv(channels):
    """
    Costruisce il documento XMLTV completo, indentato a 2 spazi,
    con blocchi <channel> seguiti da tutti i <programme>.
    """
    lines = []
    lines.append("<?xml version='1.0' encoding='utf-8'?>")
    lines.append(
        '<tv generator-info-name="rakuten-epg" '
        'generator-info-url="https://github.com/ciux23/rakuten-it-epg">'
    )

    for ch in channels:
        lines.append(f'  <channel id="{escape(ch["id"])}">')
        lines.append(f'    <display-name lang="it">{escape(ch["title"])}</display-name>')
        if ch["logo"]:
            lines.append(f'    <icon src="{escape(ch["logo"])}"></icon>')
        lines.append("  </channel>")

    for ch in channels:
        for prog in ch["programs"]:
            starts_raw = prog.get("starts_at")
            ends_raw = prog.get("ends_at")
            if not starts_raw or not ends_raw:
                continue

            try:
                start_xmltv = iso_to_xmltv(starts_raw)
                stop_xmltv = iso_to_xmltv(ends_raw)
            except ValueError:
                continue

            title = escape(prog.get("title") or "")
            desc = escape(prog.get("description") or "")

            lines.append(
                f'  <programme start="{start_xmltv}" stop="{stop_xmltv}" '
                f'channel="{escape(ch["id"])}">'
            )
            lines.append(f'    <title lang="it">{title}</title>')
            if desc:
                lines.append(f'    <desc lang="it">{desc}</desc>')
            lines.append("  </programme>")

    lines.append("</tv>")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Genera EPG XMLTV per canali Rakuten TV Italia")
    parser.add_argument("--days", type=int, default=5, help="Giorni di programmazione da recuperare (default: 5)")
    parser.add_argument("--out", default="epg.xml", help="File di output (default: epg.xml)")
    parser.add_argument("--channels", nargs="*", default=None, help="Override della lista canali (slug)")
    args = parser.parse_args()

    channel_ids = args.channels or CHANNEL_IDS

    print(f"Genero EPG per {len(channel_ids)} canali, {args.days} giorni...\n")

    channels_data = []
    for channel_id in channel_ids:
        channels_data.append(fetch_channel_full(channel_id, args.days))

    xml_content = build_xmltv(channels_data)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml_content)

    total_programs = sum(len(c["programs"]) for c in channels_data)
    print(f"\n✅ Scritto {args.out}: {len(channels_data)} canali, {total_programs} programmi totali.")


if __name__ == "__main__":
    main()
