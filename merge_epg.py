#!/usr/bin/env python3
import argparse
import gzip
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

IT1_URL = "https://iptv-epg.org/files/epg-it.xml"

# Dizionario per tradurre i NUOVI id di iptv-epg.org nei VECCHI id della tua playlist M3U
ID_TRANSLATION = {
    "Mediaset20.it": "20.it",
    "TV8.it": "TV8.HD.it",
    "SkyTG24.it": "Sky.TG24.it",
    "Rete4.it": "Rete.4.it",
    "Canale5.it": "Canale.5.it",
    "Italia1.it": "Italia.1.it",
    "La7.it": "LA7.HD.it",
    "NOVE.it": "Nove.it",
    "Mediaset27Twentyseven.it": "27Twentyseven.it",
    "RealTime.it": "Real.Time.it",
    "Discovery.it": "Discovery.Channel.it",
    "GIALLO.it": "Giallo.TV.it",
    "TOPcrime.it": "Top.Crime.it",
    "Italia2.it": "Italia.2.it",
    "TgCom24.it": "TGCom.it",
    "MediasetExtra.it": "Mediaset.Extra.it",
    "MotorTrend.it": "Motor.Trend.it",
    "DMAX.it": "DMAX.it",
    "Iris.it": "Iris.it",
    "Cine34.it": "Cine34.it",
    "Focus.it": "Focus.it",
    "La5.it": "La5.it",
    "cielo.it": "cielo.it",
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
    
    channels = []
    programmes = []
    valid_new_ids = set(ID_TRANSLATION.keys())
    
    # 1. Elaboriamo i Canali
    for ch in root.findall("channel"):
        raw_id = ch.get("id")
        if raw_id is None: continue
        clean_id = raw_id.strip() # Rimuove gli spazi vuoti di iptv-epg.org
        
        if clean_id in valid_new_ids:
            old_id = ID_TRANSLATION[clean_id] # Traduce nel vecchio ID
            ch.set("id", old_id) 
            channels.append(ch)
            
    # 2. Elaboriamo i Programmi
    for pr in root.findall("programme"):
        raw_id = pr.get("channel")
        if raw_id is None: continue
        clean_id = raw_id.strip() # Rimuove gli spazi vuoti
        
        if clean_id in valid_new_ids:
            old_id = ID_TRANSLATION[clean_id] # Traduce nel vecchio ID
            pr.set("channel", old_id)
            programmes.append(pr)

    print(f"→ epg_ripper_IT1: {len(channels)} canali, {len(programmes)} programmi (filtrati e tradotti)")
    return channels, programmes

# ... (da qui in poi lascia tutto il resto del tuo script invariato: parse_local_xmltv e main) ...


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
    # 1. Aggiunto "RedBull" alla descrizione
    parser = argparse.ArgumentParser(description="Unisce gli EPG Rai/Rakuten/Pluto/RedBull/IT1-filtrato in un unico file")
    parser.add_argument("--rai", default="epg_rai.xml")
    parser.add_argument("--rakuten", default="epg_rakuten.xml")
    parser.add_argument("--pluto", default="epg_pluto.xml")
    
    # 2. AGGIUNTO: Registrazione dell'argomento --redbull
    parser.add_argument("--redbull", default="epg_redbull.xml")
    
    parser.add_argument("--skip-it1", action="store_true")
    parser.add_argument("--out", default="epg_finale.xml")
    args = parser.parse_args()
    
    all_channels = []
    all_programmes = []
    
    # 3. AGGIUNTO: ("RedBull", args.redbull) alla lista dei file da processare
    for label, path in [("Rai", args.rai), ("Rakuten", args.rakuten), ("Pluto", args.pluto), ("RedBull", args.redbull)]:
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
