"""
train_model.py  –  Poisson-Modell Training (nur auf Laptop ausfuehren!)
=========================================================================
Trainiert das Poisson-Modell mit TEAM_FILTER_YEARS = 20 Jahren Daten
und speichert es als model.pkl fuer den Raspberry Pi.

Aufruf (Laptop):
  python train_model.py

Danach model.pkl auf den Pi kopieren:
  scp model.pkl pi@raspberrypi.local:/home/pi/wm2026/
"""

import pickle
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm

# Aus predict.py importieren
from predict import (
    RESULTS_FILE, BASE_DIR,
    TEAM_FILTER_YEARS,
    compute_elo, compute_form, train_poisson,
)

warnings.filterwarnings("ignore")

MODEL_FILE = BASE_DIR / "model.pkl"


def main():
    print(f"\n{'='*55}")
    print(f"  WM 2026 – Modell Training")
    print(f"  TEAM_FILTER_YEARS = {TEAM_FILTER_YEARS}")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"{'='*55}")

    # Daten laden
    print("\n[1/4] Daten laden ...")
    all_matches = pd.read_csv(RESULTS_FILE)
    all_matches["date"] = pd.to_datetime(all_matches["date"])
    all_matches = all_matches.sort_values("date").reset_index(drop=True)
    all_matches = all_matches.dropna(subset=["home_score", "away_score"])
    all_matches["home_score"] = all_matches["home_score"].astype(int)
    all_matches["away_score"] = all_matches["away_score"].astype(int)

    cutoff        = pd.Timestamp.now() - pd.DateOffset(years=TEAM_FILTER_YEARS)
    model_matches = all_matches[all_matches["date"] >= cutoff].copy()
    print(f"  {len(all_matches)} Spiele gesamt | {len(model_matches)} fuer Modell ({TEAM_FILTER_YEARS} Jahre)")

    # Elo
    print("\n[2/4] Elo berechnen ...")
    elo, all_matches = compute_elo(all_matches)

    # Form
    print("\n[3/4] Form berechnen ...")
    recent, all_matches = compute_form(all_matches)

    # Poisson trainieren
    print("\n[4/4] Poisson-Modell trainieren (dauert etwas) ...")
    t_start = datetime.now()
    poisson_model = train_poisson(all_matches, model_matches)
    duration = (datetime.now() - t_start).seconds
    print(f"  Training abgeschlossen in {duration}s")

    # Modell speichern
    payload = {
        "poisson_model":    poisson_model,
        "elo":              elo,
        "recent":           dict(recent),   # defaultdict -> dict fuer pickle
        "trained_at":       datetime.now().isoformat(),
        "team_filter_years": TEAM_FILTER_YEARS,
        "num_matches":      len(model_matches),
    }
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(payload, f)

    print(f"\n  Modell gespeichert → {MODEL_FILE}")
    print(f"  Groesse: {MODEL_FILE.stat().st_size / 1024:.1f} KB")
    print(f"\n  Jetzt auf den Pi kopieren:")
    print(f"  scp model.pkl pi@raspberrypi.local:/home/pi/wm2026/")
    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    main()