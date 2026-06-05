"""
scraper.py  –  WM 2026 Daten-Updater
======================================
Holt täglich zwei Dinge:
  1. results.csv   – Spielergebnisse seit 1872 (Kaggle: martj42)
  2. odds.json     – aktuelle Wettquoten (The Odds API)

Einmalige Einrichtung:
  a) Kaggle API-Token:
       → kaggle.com/settings/api → "Create New API Token" → kaggle.json
       → Datei speichern als:  ~/.kaggle/kaggle.json
       → Oder: KAGGLE_USERNAME + KAGGLE_KEY direkt unten eintragen

  b) The Odds API Key (kostenlos, 500 Req/Monat):
       → the-odds-api.com → Free Tier registrieren
       → ODDS_API_KEY unten eintragen

Aufruf:
  python scraper.py              # alles aktualisieren
  python scraper.py --results    # nur results.csv
  python scraper.py --odds       # nur odds.json
  python scraper.py --demo       # Testmodus ohne Keys

Cron (täglich 6 Uhr morgens):
  0 6 * * * cd /home/pi/wm2026 && python scraper.py >> logs/scraper.log 2>&1
"""

import requests
import json
import argparse
import zipfile
import io
import shutil
import os
import csv
from datetime import datetime, timezone
from pathlib import Path

# .env laden falls vorhanden (pip install python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ══════════════════════════════════════════════════════════════════════════════
#  KONFIGURATION  –  Keys in .env eintragen (nie ins Git einchecken!)
#                    Fallback: direkt hier eintragen
# ══════════════════════════════════════════════════════════════════════════════

# Kaggle-Zugangsdaten
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME", "DEIN_KAGGLE_USERNAME")
KAGGLE_KEY      = os.getenv("KAGGLE_KEY",      "DEIN_KAGGLE_KEY")

# The Odds API
ODDS_API_KEY    = os.getenv("ODDS_API_KEY",    "DEIN_ODDS_API_KEY")

# Ausgabedateien (relativ zum Script)
BASE_DIR        = Path(__file__).parent
RESULTS_FILE    = BASE_DIR / "results.csv"
ODDS_FILE       = BASE_DIR / "odds.json"

# Kaggle Dataset
KAGGLE_OWNER    = "martj42"
KAGGLE_DATASET  = "international-football-results-from-1872-to-2017"

# The Odds API
SPORT_KEY            = "soccer_fifa_world_cup"
PREFERRED_BOOKMAKERS = ["pinnacle", "bet365", "unibet", "williamhill", "betway"]


# ══════════════════════════════════════════════════════════════════════════════
#  TEIL 1: results.csv von Kaggle
# ══════════════════════════════════════════════════════════════════════════════

def load_kaggle_credentials() -> tuple[str, str]:
    """Liest Kaggle-Credentials: erst Config oben, dann ~/.kaggle/kaggle.json."""
    if KAGGLE_USERNAME != "DEIN_KAGGLE_USERNAME" and KAGGLE_KEY != "":
        return KAGGLE_USERNAME, KAGGLE_KEY

    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        creds = json.loads(kaggle_json.read_text())
        return creds["username"], creds["key"]

    raise ValueError(
        "Keine Kaggle-Credentials gefunden.\n"
        "  KAGGLE_KEY ist leer – trage deinen Key in scraper.py ein:\n"
        "  Option B: kaggle.json speichern unter ~/.kaggle/kaggle.json\n"
        "  Token erstellen: https://www.kaggle.com/settings/api"
    )


def download_results(username: str, key: str) -> bool:
    """
    Lädt results.csv von Kaggle herunter.
    Gibt True zurück wenn neue Daten vorhanden, False wenn bereits aktuell.
    """
    url = (
        f"https://www.kaggle.com/api/v1/datasets/download"
        f"/{KAGGLE_OWNER}/{KAGGLE_DATASET}"
    )

    resp = requests.get(url, auth=(username, key), timeout=30)

    if resp.status_code == 401:
        raise ValueError("Kaggle-Authentifizierung fehlgeschlagen – Key prüfen.")
    if resp.status_code == 403:
        raise ValueError("Kein Zugriff – Dataset-Nutzungsbedingungen auf Kaggle akzeptieren.")
    resp.raise_for_status()

    # Kaggle liefert immer ein ZIP zurück, auch für einzelne Dateien
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = next((n for n in z.namelist() if n.endswith("results.csv")), None)
        if not csv_name:
            raise ValueError(f"results.csv nicht im ZIP gefunden. Enthält: {z.namelist()}")

        new_content = z.read(csv_name)

    # Nur überschreiben wenn sich etwas geändert hat
    if RESULTS_FILE.exists():
        old_lines = len(RESULTS_FILE.read_bytes().splitlines())
        new_lines = len(new_content.splitlines())
        if old_lines == new_lines:
            print(f"  results.csv bereits aktuell ({old_lines - 1} Spiele)")
            return False
        print(f"  Update: {old_lines - 1} → {new_lines - 1} Spiele (+{new_lines - old_lines})")
    else:
        lines = len(new_content.splitlines())
        print(f"  Erstmalig heruntergeladen: {lines - 1} Spiele")

    RESULTS_FILE.write_bytes(new_content)
    return True



def print_recent_results() -> None:
    """Zeigt die letzten 10 Spiele mit echtem Ergebnis aus results.csv."""
    if not RESULTS_FILE.exists():
        return
    with open(RESULTS_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    played = [
        r for r in rows
        if r["home_score"].strip().lstrip("-").isdigit()
        and r["away_score"].strip().lstrip("-").isdigit()
    ]
    recent = played[-10:]
    print(f"\n  Letzte 10 Spiele:")
    print(f"  {'Datum':<12} {'Heim':<25} {'Gast':<25} {'Erg.':<8} {'Turnier'}")
    print("  " + "─" * 85)
    for r in recent:
        score = f"{r['home_score']}:{r['away_score']}"
        print(f"  {r['date']:<12} {r['home_team']:<25} {r['away_team']:<25} {score:<8} {r['tournament']}")

def update_results(demo: bool = False) -> None:
    print("\n── results.csv (Kaggle) " + "─" * 35)

    if demo:
        print("  Demo-Modus: results.csv wird nicht heruntergeladen")
        if not RESULTS_FILE.exists():
            # Minimales Demo-CSV anlegen damit das Notebook nicht crasht
            RESULTS_FILE.write_text(
                "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
                "2026-06-12,Germany,Scotland,2,1,FIFA World Cup,New York,USA,True\n"
                "2026-06-12,Spain,Croatia,1,0,FIFA World Cup,Los Angeles,USA,True\n"
            )
            print("  Demo-CSV angelegt (2 Beispielspiele)")
        return

    username, key = load_kaggle_credentials()
    print(f"  Kaggle-User: {username}")
    download_results(username, key)
    print(f"  Gespeichert → {RESULTS_FILE}")
    print_recent_results()


# ══════════════════════════════════════════════════════════════════════════════
#  TEIL 2: Wettquoten von The Odds API
# ══════════════════════════════════════════════════════════════════════════════

def odds_to_prob(home: float, draw: float, away: float) -> dict:
    """Dezimalquoten → normalisierte Wahrscheinlichkeiten (Overround entfernt)."""
    raw   = {"home": 1/home, "draw": 1/draw, "away": 1/away}
    total = sum(raw.values())
    return {k: round(v / total, 4) for k, v in raw.items()}


def best_bookmaker(bookmakers: list) -> dict | None:
    by_key = {b["key"]: b for b in bookmakers}
    for pref in PREFERRED_BOOKMAKERS:
        if pref in by_key:
            return by_key[pref]
    return bookmakers[0] if bookmakers else None


def fetch_odds(api_key: str) -> list[dict]:
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds/"
    resp = requests.get(url, params={
        "apiKey": api_key, "regions": "eu",
        "markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso",
    }, timeout=10)
    resp.raise_for_status()
    print(f"  API-Requests verbleibend: {resp.headers.get('x-requests-remaining', '?')}")
    return resp.json()


def parse_games(raw: list) -> list[dict]:
    games = []
    for event in raw:
        bm     = best_bookmaker(event.get("bookmakers", []))
        market = next((m for m in bm["markets"] if m["key"] == "h2h"), None) if bm else None
        if not market:
            continue
        outcomes  = {o["name"]: o["price"] for o in market["outcomes"]}
        home, away = event["home_team"], event["away_team"]
        if not all(k in outcomes for k in [home, away, "Draw"]):
            continue
        probs = odds_to_prob(outcomes[home], outcomes["Draw"], outcomes[away])
        games.append({
            "id":            event["id"],
            "commence_time": event["commence_time"],
            "home_team":     home,
            "away_team":     away,
            "bookmaker":     bm["key"],
            "odds":  {"home": outcomes[home], "draw": outcomes["Draw"], "away": outcomes[away]},
            "prob":  {"home_win": probs["home"], "draw": probs["draw"], "away_win": probs["away"]},
        })
    return games


def demo_odds() -> list[dict]:
    return parse_games([
        {"id": "d1", "commence_time": "2026-06-12T18:00:00Z",
         "home_team": "Germany", "away_team": "Scotland",
         "bookmakers": [{"key": "bet365", "markets": [{"key": "h2h", "outcomes": [
             {"name": "Germany", "price": 1.45}, {"name": "Draw", "price": 4.50},
             {"name": "Scotland", "price": 7.00}]}]}]},
        {"id": "d2", "commence_time": "2026-06-12T21:00:00Z",
         "home_team": "Spain", "away_team": "Croatia",
         "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
             {"name": "Spain", "price": 1.80}, {"name": "Draw", "price": 3.60},
             {"name": "Croatia", "price": 4.20}]}]}]},
    ])


def update_odds(demo: bool = False) -> None:
    print("\n── odds.json (The Odds API) " + "─" * 31)

    if demo:
        print("  Demo-Modus: Beispieldaten")
        games = demo_odds()
    elif ODDS_API_KEY == "DEIN_ODDS_API_KEY":
        print("  ⚠ Kein Odds-API-Key → Demo-Daten")
        games = demo_odds()
    else:
        games = parse_games(fetch_odds(ODDS_API_KEY))
        print(f"  {len(games)} Spiele gefunden")

    ODDS_FILE.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source":     "the-odds-api.com",
        "games":      games,
    }, indent=2, ensure_ascii=False))

    print(f"  Gespeichert → {ODDS_FILE}  ({len(games)} Spiele)")

    # Vorschau
    print(f"\n  {'Spiel':<35} {'Heim':>6}  {'X':>6}  {'Gast':>6}")
    print("  " + "─" * 56)
    for g in games:
        p = g["prob"]
        print(f"  {g['home_team']+' vs '+g['away_team']:<35}"
              f" {p['home_win']:>5.1%}  {p['draw']:>5.1%}  {p['away_win']:>5.1%}")


# ══════════════════════════════════════════════════════════════════════════════
#  EINSTIEGSPUNKT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="WM 2026 Daten-Updater")
    parser.add_argument("--results", action="store_true", help="Nur results.csv aktualisieren")
    parser.add_argument("--odds",    action="store_true", help="Nur odds.json aktualisieren")
    parser.add_argument("--demo",    action="store_true", help="Testmodus ohne API-Keys")
    args = parser.parse_args()

    run_results = args.results or (not args.results and not args.odds)
    run_odds    = args.odds    or (not args.results and not args.odds)

    print(f"\n{'═'*58}")
    print(f"  WM 2026 Daten-Updater  –  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"{'═'*58}")

    try:
        if run_results:
            update_results(demo=args.demo)
    except Exception as e:
        print(f"  FEHLER (results): {e}")

    try:
        if run_odds:
            update_odds(demo=args.demo)
    except Exception as e:
        print(f"  FEHLER (odds): {e}")

    print(f"\n{'═'*58}\n")


if __name__ == "__main__":
    main()