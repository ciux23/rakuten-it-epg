#!/usr/bin/env python3
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
BLOCK_HOURS = 12  # Chunk di 12 ore per evitare il limite nascosto dell'API

def get_time_blocks(total_hours, block_hours):
    now = datetime.now(timezone.utc)
    # Partiamo da 6 ore fa per catturare il programma già in onda
    cursor = now - timedelta(hours=6)
    end_target = now + timedelta(hours=total_hours)
    blocks = []
    
    while cursor < end_target:
        block_end = cursor + timedelta(hours=block_hours)
        if block_end > end_target:
            block_end = end_target
        blocks.append((cursor, block_end))
        cursor = block_end
    return blocks

def fetch_all_channels_chunked(total_hours):
    print(f"Recupero programmazione in blocchi da {BLOCK_HOURS}h per {total_hours}h totali...")
    all_channels_data = {}
    
    for start_time, end_time in get_time_blocks(total_hours, BLOCK_HOURS):
        date_fmt = "%Y-%m-%dT%H:%M:%S.000Z"
        params = {
            "start": start_time.strftime(date_fmt),
            "stop": end_time.strftime(date_fmt),
            "appVersion": "5.41.0",
            "deviceMake": "Chrome",
            "deviceModel": "Chrome",
            "deviceType": "web",
            "clientID": "pluto-epg-generator",
            "serverSideAds": "false"
        }
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "X-Forwarded-For": "151.29.0.1"
        })
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            channels = json.loads(body)
            
            for ch in channels:
                ch_id = ch.get("_id")
                if ch_id not in all_channels_data:
                    all_channels_data[ch_id] = {
                        "name": ch.get("name"),
                        "logo": (ch.get("colorLogoPNG") or {}).get("path") or (ch.get("logo") or {}).get("path"),
                        "timelines": []
                    }
                
                # Aggiungi i programmi evitando duplicati basati su start time
                existing_starts = {prog["start"] for prog in all_channels_data[ch_id]["timelines"]}
                for prog in ch.get("timelines", []):
                    if prog.get("start") not in existing_starts:
                        all_channels_data[ch_id]["timelines"].append(prog)
                        existing_starts.add(prog.get("start"))
                        
        except urllib.error.HTTPError as e:
            print(f"⚠️  HTTP {e.code} per il blocco {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Errore rete: {e}", file=sys.stderr)

    return all_channels_data

def iso_to_xmltv(iso_string):
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    dt_it = dt + timedelta(hours=2)
    return dt_it.strftime("%Y%m%d%H%M%S +0200")

def build_xmltv(channels_data):
    lines = []
    lines.append("<?xml version='1.0' encoding='utf-8'?>")
    lines.append('<tv generator-info-name="pluto-epg" generator-info-url="https://api.pluto.tv">')
    
    for ch in channels_data:
        lines.append(f'  <channel id="{escape(ch["xmltv_id"])}">')
        lines.append(f'    <display-name lang="it">{escape(ch["title"])}</display-name>')
        if ch["logo"]:
            lines.append(f'    <icon src="{escape(ch["logo"])}"></icon>')
        lines.append("  </channel>")
        
    for ch in channels_data:
        # Ordinamento cronologico fondamentale per IPTVnator
        sorted_programs = sorted(ch["programs"], key=lambda p: p.get("start", ""))
        
        for prog in sorted_programs:
            try:
                start_xmltv = iso_to_xmltv(prog["start"])
                stop_xmltv = iso_to_xmltv(prog["stop"])
            except (ValueError, KeyError):
                continue
            
            title = escape(prog.get("title") or "")
            desc = escape((prog.get("episode") or {}).get("description") or "")
            
            lines.append(f'  <programme start="{start_xmltv}" stop="{stop_xmltv}" channel="{escape(ch["xmltv_id"])}">')
            lines.append(f'    <title lang="it">{title}</title>')
            if desc:
                lines.append(f'    <desc lang="it">{desc}</desc>')
            lines.append("  </programme>")
            
    lines.append("</tv>")
    return "\n".join(lines) + "\n"

def main():
    parser = argparse.ArgumentParser(description="Genera EPG XMLTV per canali Pluto TV Italia")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--out", default="epg_pluto.xml")
    args = parser.parse_args()
    
    print(f"Avvio generazione EPG Pluto TV per {args.hours} ore...\n")
    raw_channels = fetch_all_channels_chunked(args.hours)
    
    channels_data = []
    for pluto_id, xmltv_id in CHANNEL_IDS.items():
        ch = raw_channels.get(pluto_id)
        if not ch:
            print(f"⚠️  Canale non trovato: {pluto_id}")
            continue
            
        channels_data.append({
            "xmltv_id": xmltv_id,
            "title": ch.get("name", xmltv_id),
            "logo": ch.get("logo"),
            "programs": ch.get("timelines", [])
        })
        print(f"→ {ch.get('name')}: {len(ch.get('timelines', []))} programmi")
        
    xml_content = build_xmltv(channels_data)
    
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    total_programs = sum(len(c["programs"]) for c in channels_data)
    print(f"\n✅ Scritto {args.out}: {len(channels_data)} canali, {total_programs} programmi totali.")

if __name__ == "__main__":
    main()
