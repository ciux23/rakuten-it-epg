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
            "X-Forwarded-For": "151.29.0.1",
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
    lines.append('<tv generator-info-name="pluto-epg" generator-info-url="https://api.pluto.tv">')

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
                lines.append(f'
