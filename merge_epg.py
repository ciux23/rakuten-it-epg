#!/usr/bin/env python3
import argparse
import gzip
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# IT1_URL = "https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"
IT1_URL = "https://iptv-epg.org/files/epg-it.xml"
IT1_KEEP_IDS = {
    "TV8.HD.it", "cielo.it", "Sky.TG24.it", "Rete.4.it", "Canale.5.it",
    "Italia.1.it", "LA7.HD.it", "Nove.it", "20.it", "Iris.it",
    "27Twentyseven.it", "La5.it", "Real.Time.it", "Cine34.it",
    "Focus.it", "Discovery.Channel.it", "Giallo.TV.it", "Top.Crime.it",
    "Italia.2.it", "TGCom.it", "DMAX.it", "Mediaset.Extra.it",
    "Motor.Trend.it",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def fetch_it1_filtered():
    req = urllib.request.Request(IT1_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw_data = resp.read()
    except urllib.error.HTTPError as e:
        print(f"⚠️  HTTP {e.code} scaricando epg_ripper_IT1", file=sys.stderr)
        return [], []
    except Exception as e:
        print(f"⚠️  Errore rete scaricando epg_ripper_IT1: {e}", file=sys.stderr)
        return [], []

    # Controlla se il file è compresso (gzip) o è un XML puro
    if raw_data.startswith(b'\x1f\x8b'):
        try:
            xml_bytes = gzip.decompress(raw_data)
        except OSError as e:
            print(f"⚠️  Errore decompressione epg_ripper_IT1: {e}", file=sys.stderr)
            return [], []
    else:
        xml_bytes = raw_data

    root = ET.fromstring(xml_bytes)
    channels = [el for el in root.findall("channel") if el.get("id") in IT1_KEEP_IDS]
    programmes = [el for el in root.findall("programme") if el.get("channel") in IT1_KEEP_IDS]
    found_ids = {el.get("id") for el in channels}
    missing = IT1_KEEP_IDS - found_ids
    if missing:
        print(f"⚠️  tvg_id non trovati in epg_ripper_IT1: {sorted(missing)}", file=sys.stderr)
    print(f"→ epg_ripper_IT1: {len(channels)} canali, {len(programmes)} programmi (filtrati)")
    return channels, programmes


def parse_local_xmltv(path):
    try:
        tree = ET.parse(path)
    except (FileNotFoundError, ET.ParseError) as e:
        print(f"⚠️  Impossibile leggere {path}: {e}", file=sys.stderr)
        return [], []
    root = tree.getroot()
    channels = root.findall("channel")
    programmes = root.findall("programme")
    print(f"→ {path}: {len(channels)} canali, {len(programmes)} programmi")
    return channels, programmes


def main():
    parser = argparse.ArgumentParser(description="Unisce gli EPG Rai/Rakuten/Pluto/IT1-filtrato in un unico file")
    parser.add_argument("--rai", default="epg_rai.xml")
    parser.add_argument("--rakuten", default="epg_rakuten.xml")
    parser.add_argument("--pluto", default="epg_pluto.xml")
    parser.add_argument("--skip-it1", action="store_true")
    parser.add_argument("--out", default="epg_finale.xml")
    args = parser.parse_args()
    all_channels = []
    all_programmes = []
    for label, path in [("Rai", args.rai), ("Rakuten", args.rakuten), ("Pluto", args.pluto)]:
        ch, pr = parse_local_xmltv(path)
        all_channels.extend(ch)
        all_programmes.extend(pr)
    if not args.skip_it1:
        ch, pr = fetch_it1_filtered()
        all_channels.extend(ch)
        all_programmes.extend(pr)
    seen_channel_ids = set()
    deduped_channels = []
    for ch in all_channels:
        cid = ch.get("id")
        if cid in seen_channel_ids:
            continue
        seen_channel_ids.add(cid)
        deduped_channels.append(ch)
    root = ET.Element("tv", {"generator-info-name": "merged-epg", "generator-info-url": "local"})
    for ch in deduped_channels:
        root.append(ch)
    for pr in all_programmes:
        root.append(pr)
    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    tree.write(args.out, encoding="utf-8", xml_declaration=True)
    print(f"\n✅ Scritto {args.out}: {len(deduped_channels)} canali, {len(all_programmes)} programmi totali.")


if __name__ == "__main__":
    main()
