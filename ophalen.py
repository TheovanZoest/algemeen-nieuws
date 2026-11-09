"""Algemeen Nieuws – robot.
Haalt Nederlandse nieuwsfeeds (landelijk en regionaal Limburg/Brabant),
Google Nieuws-zoekwoorden, het weer voor Weert en de weerwaarschuwingen op
en schrijft alles naar nieuws.json. Gebruikt alleen standaard-Python."""
import json, re, html, time, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (algemeen-nieuws-dashboard; GitHub Actions)"}
ATOM = "{http://www.w3.org/2005/Atom}"

# Per bron: een of meer feed-adressen (de eerste die werkt wordt gebruikt).
# "google": als geen enkel feed-adres werkt, zoeken we de bron via Google Nieuws.
BRONNEN = {
    # --- Landelijk ---
    "nos":      {"urls": ["https://feeds.nos.nl/nosnieuwsalgemeen"]},
    "nosbi":    {"urls": ["https://feeds.nos.nl/nosnieuwsbinnenland"]},
    "nosbu":    {"urls": ["https://feeds.nos.nl/nosnieuwsbuitenland"]},
    "nospol":   {"urls": ["https://feeds.nos.nl/nosnieuwspolitiek"]},
    "nossport": {"urls": ["https://feeds.nos.nl/nossportalgemeen"]},
    "noscult":  {"urls": ["https://feeds.nos.nl/nosnieuwscultuurenmedia"]},
    "nostech":  {"urls": ["https://feeds.nos.nl/nosnieuwstech"]},
    "nu":       {"urls": ["https://www.nu.nl/rss/Algemeen"]},
    "nusport":  {"urls": ["https://www.nu.nl/rss/Sport"]},
    "nuopm":    {"urls": ["https://www.nu.nl/rss/Opmerkelijk"]},
    "rtl":      {"urls": ["https://www.rtlnieuws.nl/rss.xml",
                          "https://www.rtl.nl/rss.xml",
                          "https://www.rtlnieuws.nl/service/rss/nieuws/index.xml"],
                 "google": "site:rtl.nl"},
    "tel":      {"urls": ["https://www.telegraaf.nl/rss"], "google": "site:telegraaf.nl"},
    "ad":       {"urls": ["https://www.ad.nl/nieuws/rss.xml", "https://www.ad.nl/home/rss.xml"],
                 "google": "site:ad.nl"},
    "vk":       {"urls": ["https://www.volkskrant.nl/voorpagina/rss.xml"], "google": "site:volkskrant.nl"},
    "trouw":    {"urls": ["https://www.trouw.nl/voorpagina/rss.xml"], "google": "site:trouw.nl"},
    "parool":   {"urls": ["https://www.parool.nl/voorpagina/rss.xml"], "google": "site:parool.nl"},
    "nrc":      {"urls": ["https://www.nrc.nl/rss/"], "google": "site:nrc.nl"},
    # --- Regio Limburg ---
    "l1":       {"urls": ["https://www.l1nieuws.nl/rss", "https://www.l1nieuws.nl/rss/nieuws",
                          "https://l1nieuws.nl/feed"],
                 "google": "site:l1nieuws.nl"},
    "limburger": {"urls": ["https://www.limburger.nl/rss", "https://www.limburger.nl/rss.xml"],
                  "google": "site:limburger.nl"},
    # --- Regio Brabant ---
    "obrabant": {"urls": ["https://www.omroepbrabant.nl/rss", "https://www.omroepbrabant.nl/rss/nieuws",
                          "https://www.omroepbrabant.nl/feed"],
                 "google": "site:omroepbrabant.nl"},
    "ed":       {"urls": ["https://www.ed.nl/home/rss.xml", "https://www.ed.nl/rss.xml"],
                 "google": "site:ed.nl"},
}

WEERT = (51.2517, 5.7069)
REGIO_WAARSCHUWING = ("limburg", "brabant")


def haal(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def schoon(tekst):
    tekst = html.unescape(re.sub(r"<[^>]+>", " ", tekst or ""))
    return re.sub(r"\s+", " ", tekst).strip()


def iso(datum):
    if not datum:
        return ""
    try:
        return parsedate_to_datetime(datum).astimezone(timezone.utc).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(datum.strip().replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except Exception:
            return datum


def lees_feed(xml_bytes, google=False, maximum=30):
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item") or root.findall(".//" + ATOM + "entry")
    if not items:
        raise ValueError("geen artikelen in feed")
    uit = []
    for it in items[:maximum]:
        def g(naam):
            el = it.find(naam)
            if el is None:
                el = it.find(ATOM + naam)
            return (el.text or "") if el is not None else ""
        link = g("link").strip()
        if not link:
            el = it.find(ATOM + "link")
            link = el.get("href", "") if el is not None else ""
        titel, bron = schoon(g("title")), ""
        if google:
            m = re.match(r"^(.*) - ([^-]+)$", titel)
            if m:
                titel, bron = m.group(1).strip(), m.group(2).strip()
        cat = schoon(g("category"))
        uit.append({"titel": titel,
                    "desc": schoon(g("description") or g("summary"))[:220],
                    "link": link.strip(),
                    "datum": iso(g("pubDate") or g("published") or g("updated")
                                 or g("{http://purl.org/dc/elements/1.1/}date")),
                    "bronNaam": bron, "cat": cat[:40]})
    return uit


def google_url(zoek, dagen=1):
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote(f"{zoek} when:{dagen}d")
            + "&hl=nl&gl=NL&ceid=NL:nl")


def haal_bron(bid, b):
    fouten = []
    for url in b["urls"]:
        try:
            return {"items": lees_feed(haal(url)), "ok": True, "via": url}
        except Exception as e:
            fouten.append(f"{url}: {str(e)[:60]}")
        time.sleep(0.3)
    if b.get("google"):
        try:
            items = lees_feed(haal(google_url(b["google"])), google=True, maximum=25)
            for it in items:
                it["bronNaam"] = ""          # bron is al bekend
            return {"items": items, "ok": True, "via": "Google Nieuws"}
        except Exception as e:
            fouten.append("Google: " + str(e)[:60])
    return {"items": [], "ok": False, "fout": " | ".join(fouten)[:300]}


def zoektermen():
    try:
        with open("zoektermen.txt", encoding="utf-8") as f:
            return [r.strip() for r in f if r.strip() and not r.lstrip().startswith("#")]
    except FileNotFoundError:
        return ["Weert"]


def weer():
    lat, lon = WEERT
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,precipitation"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=Europe%%2FAmsterdam&forecast_days=4" % (lat, lon))
    return json.loads(haal(url))


def waarschuwingen():
    """Weerwaarschuwingen van het KNMI via MeteoAlarm (Limburg en Noord-Brabant)."""
    url = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-netherlands"
    root = ET.fromstring(haal(url))
    cap = "{urn:oasis:names:tc:emergency:cap:1.2}"
    uit = []
    for e in root.findall(ATOM + "entry"):
        def g(naam, ns=cap):
            el = e.find(ns + naam)
            return (el.text or "").strip() if el is not None else ""
        gebied = g("areaDesc")
        titel = g("title", ATOM)
        tekst = (gebied + " " + titel).lower()
        if not any(r in tekst for r in REGIO_WAARSCHUWING):
            continue
        uit.append({"gebied": gebied, "titel": titel, "soort": g("event"),
                    "ernst": g("severity"), "van": g("onset") or g("effective"),
                    "tot": g("expires")})
    return uit


def main():
    nu = datetime.now(timezone.utc).isoformat()
    data = {"bijgewerkt": nu, "bronnen": {}, "zoektermen": zoektermen()}
    for bid, b in BRONNEN.items():
        data["bronnen"][bid] = haal_bron(bid, b)
        time.sleep(0.4)
    google = []
    for term in data["zoektermen"]:
        try:
            google += [dict(i, zoekterm=term)
                       for i in lees_feed(haal(google_url(term, 2)), google=True, maximum=12)]
        except Exception as e:
            print("Google", term, "mislukt:", str(e)[:60])
        time.sleep(0.5)
    data["bronnen"]["gnews"] = {"items": google, "ok": bool(google)}
    try:
        data["weer"] = weer()
    except Exception as e:
        print("Weer mislukt:", str(e)[:80])
    try:
        data["waarschuwingen"] = waarschuwingen()
    except Exception as e:
        data["waarschuwingen"] = None
        print("Waarschuwingen mislukt:", str(e)[:80])
    if not any(b["items"] for b in data["bronnen"].values()):
        print("Geen enkele bron gelukt; nieuws.json niet overschreven")
        return
    with open("nieuws.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("Klaar:", {k: (len(v["items"]), v.get("via", "")[:30]) for k, v in data["bronnen"].items()})


if __name__ == "__main__":
    main()
