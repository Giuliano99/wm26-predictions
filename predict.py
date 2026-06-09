"""
predict.py  –  WM 2026 Vorhersage-Engine
=========================================
Liest results.csv + odds.json, berechnet Vorhersagen
und schreibt predictions.json fuer den Flask-Server.

Aufruf:
  python predict.py
"""

import json
import re
import warnings
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import statsmodels.api as sm
from scipy.stats import poisson

warnings.filterwarnings("ignore")

BASE_DIR         = Path(__file__).parent
RESULTS_FILE     = BASE_DIR / "results.csv"
ODDS_FILE        = BASE_DIR / "odds.json"
PREDICTIONS_FILE = BASE_DIR / "predictions.json"

# ── Konfiguration ─────────────────────────────────────────────────────────────
ODDS_WEIGHT       = 0.70
MODEL_WEIGHT      = 1.0 - ODDS_WEIGHT
TEAM_FILTER_YEARS = 20
RHO               = 0.07
INITIAL_ELO       = 1500

GROUPS = {
    "A": ["Mexico",        "South Africa",           "South Korea",   "Czech Republic"],
    "B": ["Canada",        "Bosnia and Herzegovina", "Qatar",         "Switzerland"],
    "C": ["Brazil",        "Morocco",                "Haiti",         "Scotland"],
    "D": ["United States", "Paraguay",               "Australia",     "Turkey"],
    "E": ["Germany",       "Curacao",                "Ivory Coast",   "Ecuador"],
    "F": ["Netherlands",   "Japan",                  "Sweden",        "Tunisia"],
    "G": ["Belgium",       "Egypt",                  "Iran",          "New Zealand"],
    "H": ["Spain",         "Cape Verde",             "Saudi Arabia",  "Uruguay"],
    "I": ["France",        "Senegal",                "Iraq",          "Norway"],
    "J": ["Argentina",     "Algeria",                "Austria",       "Jordan"],
    "K": ["Portugal",      "DR Congo",               "Uzbekistan",    "Colombia"],
    "L": ["England",       "Croatia",                "Ghana",         "Panama"],
}

ODDS_TO_MODEL = {
    "USA":                  "United States",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Ivory Coast":          "Ivory Coast",
    "DR Congo":             "DR Congo",
    "Czech Republic":       "Czech Republic",
    "South Korea":          "South Korea",
    "New Zealand":          "New Zealand",
    "Saudi Arabia":         "Saudi Arabia",
    "Cape Verde":           "Cape Verde",
    "South Africa":         "South Africa",
    "Curacao":              "Curacao",
}

GROUP_TO_MODEL = {
    "Czech Republic":         "Czech Republic",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "United States":          "United States",
    "Ivory Coast":            "Ivory Coast",
    "New Zealand":            "New Zealand",
    "Saudi Arabia":           "Saudi Arabia",
    "Cape Verde":             "Cape Verde",
    "South Africa":           "South Africa",
    "South Korea":            "South Korea",
    "DR Congo":               "DR Congo",
    "Curacao":                "Curacao",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def model_name(team):
    return GROUP_TO_MODEL.get(team, team)

def odds_name(team):
    rev = {v: k for k, v in ODDS_TO_MODEL.items()}
    return rev.get(team, team)


# ── 1. Quoten laden ───────────────────────────────────────────────────────────

def load_odds():
    with open(ODDS_FILE, "rb") as f:
        raw = f.read()
    text = raw.decode("latin-1")
    text = re.sub(r"Cura.{1,4}ao", "Curacao", text)
    data = json.loads(text)

    lookup    = {}
    date_map  = {}
    odds_map  = {}

    for g in data["games"]:
        p     = g["prob"]
        total = p["home_win"] + p["draw"] + p["away_win"]
        key   = (g["home_team"], g["away_team"])
        lookup[key] = {
            "home_win": p["home_win"] / total,
            "draw":     p["draw"]     / total,
            "away_win": p["away_win"] / total,
        }
        date_map[(g["home_team"], g["away_team"])] = g["commence_time"]
        date_map[(g["away_team"], g["home_team"])] = g["commence_time"]
        odds_map[key] = g.get("odds", {})

    print(f"  Quoten geladen: {len(lookup)} Spiele")
    return lookup, date_map, odds_map, data["fetched_at"]


def get_odds_probs(lookup, team1, team2):
    t1o, t2o = odds_name(team1), odds_name(team2)
    if (t1o, t2o) in lookup:
        p = lookup[(t1o, t2o)]
        return p["home_win"], p["draw"], p["away_win"]
    if (t2o, t1o) in lookup:
        p = lookup[(t2o, t1o)]
        return p["away_win"], p["draw"], p["home_win"]
    return None


# ── 2. Elo-Berechnung ─────────────────────────────────────────────────────────

def get_k_factor(tournament):
    t = str(tournament)
    if t == "FIFA World Cup":            return 60
    if "UEFA Euro" in t:                 return 50
    if "Copa Am" in t:                   return 50
    if "African Cup of Nations" in t:    return 50
    if "AFC Asian Cup" in t:             return 50
    if "OFC Nations Cup" in t:           return 50
    if "Nations League" in t:            return 40
    if "qualification" in t.lower():     return 30
    if "Friendly" in t:                  return 15
    return 25

def mov_multiplier(goal_diff, elo_diff_winner):
    if goal_diff == 0: return 1.0
    return np.log(goal_diff + 1) * (2.2 / (elo_diff_winner * 0.001 + 2.2))

def compute_elo(all_matches):
    elo = {}
    def get_elo(t): return elo.get(t, INITIAL_ELO)

    elo_home_before, elo_away_before = [], []
    current_year = None

    for _, row in all_matches.iterrows():
        year = row["date"].year
        if current_year is None: current_year = year
        if year > current_year:
            for t in elo: elo[t] = INITIAL_ELO + (elo[t] - INITIAL_ELO) * 0.98
            current_year = year

        home, away = row["home_team"], row["away_team"]
        eh, ea = get_elo(home), get_elo(away)
        elo_home_before.append(eh)
        elo_away_before.append(ea)

        expected_home = 1 / (1 + 10 ** ((ea - eh) / 400))
        hs, as_ = row["home_score"], row["away_score"]
        goal_diff = abs(hs - as_)

        if hs > as_:
            actual_home = 1.0
            mov = mov_multiplier(goal_diff, max(eh - ea, 0))
        elif hs < as_:
            actual_home = 0.0
            mov = mov_multiplier(goal_diff, max(ea - eh, 0))
        else:
            actual_home = 0.5
            mov = 1.0

        k = get_k_factor(row["tournament"])
        elo[home] = eh + k * mov * (actual_home - expected_home)
        elo[away] = ea + k * mov * ((1.0 - actual_home) - (1.0 - expected_home))

    all_matches = all_matches.copy()
    all_matches["elo_home"] = elo_home_before
    all_matches["elo_away"] = elo_away_before
    all_matches["elo_diff"] = all_matches["elo_home"] - all_matches["elo_away"]
    print(f"  Elo berechnet: {len(elo)} Teams")
    return elo, all_matches


# ── 3. Form-Feature ───────────────────────────────────────────────────────────

FORM_WEIGHTS = np.array([0.40, 0.25, 0.17, 0.11, 0.07])
FORM_N       = len(FORM_WEIGHTS)

def weighted_form(dq):
    pts = list(dq)
    if not pts: return 0.5
    w = FORM_WEIGHTS[:len(pts)].copy()
    w /= w.sum()
    return float(np.dot(pts, w))

def compute_form(all_matches):
    recent = defaultdict(lambda: deque(maxlen=FORM_N))
    form_home_list, form_away_list = [], []

    for _, row in all_matches.iterrows():
        home, away = row["home_team"], row["away_team"]
        hs, as_ = row["home_score"], row["away_score"]
        form_home_list.append(weighted_form(recent[home]))
        form_away_list.append(weighted_form(recent[away]))
        recent[home].appendleft(1.0 if hs > as_ else (0.5 if hs == as_ else 0.0))
        recent[away].appendleft(1.0 if as_ > hs else (0.5 if hs == as_ else 0.0))

    all_matches = all_matches.copy()
    all_matches["form_home"] = form_home_list
    all_matches["form_away"] = form_away_list
    all_matches["form_diff"] = all_matches["form_home"] - all_matches["form_away"]
    print("  Form-Feature berechnet")
    return recent, all_matches


# ── 4. Poisson-Modell ─────────────────────────────────────────────────────────

def tournament_weight(tournament):
    t = str(tournament)
    if "FIFA World Cup" in t:           return 20
    if "UEFA Euro" in t:                return 15
    if "Copa Am" in t:                  return 15
    if "African Cup of Nations" in t:   return 15
    if "AFC Asian Cup" in t:            return 15
    if "OFC Nations Cup" in t:          return 15
    if "Nations League" in t:           return 8
    if "qualification" in t.lower():    return 8
    if "Friendly" in t:                 return 1
    return 2

def train_poisson(all_matches, model_matches):
    model_matches = model_matches.join(
        all_matches[["elo_home", "elo_away", "elo_diff", "form_home", "form_away", "form_diff"]],
        how="left"
    )
    model_matches["tournament_weight"] = model_matches["tournament"].apply(tournament_weight)
    days_old = (pd.Timestamp.now() - model_matches["date"]).dt.days
    model_matches["time_weight"] = np.exp(-days_old / 1460)
    model_matches["weight"] = model_matches["tournament_weight"] * model_matches["time_weight"]

    home_df = model_matches[["home_team","away_team","home_score","weight","elo_diff","form_diff"]].copy()
    home_df.columns = ["team","opponent","goals","weight","elo_diff","form_diff"]
    away_df = model_matches[["away_team","home_team","away_score","weight","elo_diff","form_diff"]].copy()
    away_df.columns = ["team","opponent","goals","weight","elo_diff","form_diff"]
    away_df["elo_diff"]  = -away_df["elo_diff"]
    away_df["form_diff"] = -away_df["form_diff"]
    goal_model_data = pd.concat([home_df, away_df], ignore_index=True)

    cutoff_teams = pd.Timestamp.now() - pd.DateOffset(years=TEAM_FILTER_YEARS)
    active_teams = set(
        all_matches[all_matches["date"] >= cutoff_teams]["home_team"].tolist() +
        all_matches[all_matches["date"] >= cutoff_teams]["away_team"].tolist()
    )
    goal_model_data = goal_model_data[
        goal_model_data["team"].isin(active_teams) &
        goal_model_data["opponent"].isin(active_teams)
    ].copy()

    poisson_model = smf.glm(
        formula="goals ~ team + opponent + elo_diff + form_diff",
        data=goal_model_data,
        family=sm.families.Poisson(),
        freq_weights=goal_model_data["weight"]
    ).fit()

    print(f"  Poisson-Modell trainiert: {len(poisson_model.params)} Parameter")
    return poisson_model


# ── 5. Vorhersagefunktionen ───────────────────────────────────────────────────

def dixon_coles_tau(x, y, mu1, mu2):
    if   x == 0 and y == 0: return 1.0 - mu1 * mu2 * RHO
    elif x == 1 and y == 0: return 1.0 + mu2 * RHO
    elif x == 0 and y == 1: return 1.0 + mu1 * RHO
    elif x == 1 and y == 1: return 1.0 - RHO
    return 1.0

def predict_goals(poisson_model, elo, recent, team, opponent):
    params    = poisson_model.params
    elo_diff  = elo.get(team, INITIAL_ELO) - elo.get(opponent, INITIAL_ELO)
    form_diff = weighted_form(recent[team]) - weighted_form(recent[opponent])
    lp  = float(params.get("Intercept", 0.0))
    lp += float(params.get(f"team[T.{team}]", 0.0))
    lp += float(params.get(f"opponent[T.{opponent}]", 0.0))
    lp += float(params.get("elo_diff", 0.0)) * elo_diff
    lp += float(params.get("form_diff", 0.0)) * form_diff
    return float(np.exp(lp))

def dc_matrix(poisson_model, elo, recent, team1, team2, max_goals=8):
    g1 = predict_goals(poisson_model, elo, recent, model_name(team1), model_name(team2))
    g2 = predict_goals(poisson_model, elo, recent, model_name(team2), model_name(team1))
    matrix = np.outer(
        poisson.pmf(range(max_goals + 1), g1),
        poisson.pmf(range(max_goals + 1), g2)
    )
    for x in range(2):
        for y in range(2):
            matrix[x, y] *= dixon_coles_tau(x, y, g1, g2)
    matrix /= matrix.sum()
    return matrix, g1, g2

def predict_match(poisson_model, elo, recent, odds_lookup, odds_raw_map, team1, team2):
    matrix, mu1, mu2 = dc_matrix(poisson_model, elo, recent, team1, team2)

    pm1 = float(np.sum(np.tril(matrix, -1)))
    pdm = float(np.sum(np.diag(matrix)))
    pm2 = float(np.sum(np.triu(matrix,  1)))

    odds_p = get_odds_probs(odds_lookup, team1, team2)

    if odds_p is not None:
        po1, pdo, po2 = odds_p
        p1  = MODEL_WEIGHT * pm1 + ODDS_WEIGHT * po1
        pd_ = MODEL_WEIGHT * pdm + ODDS_WEIGHT * pdo
        p2  = MODEL_WEIGHT * pm2 + ODDS_WEIGHT * po2
        source = "ensemble"
    else:
        p1, pd_, p2 = pm1, pdm, pm2
        source = "model_only"

    total = p1 + pd_ + p2
    p1, pd_, p2 = p1/total, pd_/total, p2/total

    # Bestes Ergebnis
    outcome = max([("win1", p1), ("draw", pd_), ("win2", p2)], key=lambda x: x[1])[0]
    best_score, best_prob = None, -1
    for i in range(9):
        for j in range(9):
            p = matrix[i, j]
            if outcome == "win1" and i > j and p > best_prob:
                best_score, best_prob = (i, j), p
            elif outcome == "draw" and i == j and p > best_prob:
                best_score, best_prob = (i, j), p
            elif outcome == "win2" and j > i and p > best_prob:
                best_score, best_prob = (i, j), p

    g1_tipp, g2_tipp = best_score

    # Top-10 Ergebnisse
    score_probs = []
    for i in range(9):
        for j in range(9):
            score_probs.append({"home": i, "away": j, "prob": round(float(matrix[i, j]), 4)})
    score_probs.sort(key=lambda x: x["prob"], reverse=True)

    # Rohe Quoten holen
    t1o, t2o = odds_name(team1), odds_name(team2)
    raw_odds = odds_raw_map.get((t1o, t2o)) or odds_raw_map.get((t2o, t1o)) or {}

    return {
        "tipp_home":     g1_tipp,
        "tipp_away":     g2_tipp,
        "p_home":        round(p1,  4),
        "p_draw":        round(pd_, 4),
        "p_away":        round(p2,  4),
        "p_home_model":  round(pm1, 4),
        "p_draw_model":  round(pdm, 4),
        "p_away_model":  round(pm2, 4),
        "p_home_odds":   round(odds_p[0], 4) if odds_p else None,
        "p_draw_odds":   round(odds_p[1], 4) if odds_p else None,
        "p_away_odds":   round(odds_p[2], 4) if odds_p else None,
        "expected_goals_home": round(mu1, 3),
        "expected_goals_away": round(mu2, 3),
        "elo_home":      round(elo.get(model_name(team1), INITIAL_ELO)),
        "elo_away":      round(elo.get(model_name(team2), INITIAL_ELO)),
        "form_home":     round(weighted_form(recent[model_name(team1)]), 3),
        "form_away":     round(weighted_form(recent[model_name(team2)]), 3),
        "source":        source,
        "odds_home":     raw_odds.get("home"),
        "odds_draw":     raw_odds.get("draw"),
        "odds_away":     raw_odds.get("away"),
        "top10_scores":  score_probs[:10],
        "confidence":    round(max(p1, pd_, p2), 4),
        "outcome":       outcome,
    }


# ── 6. Hauptfunktion ─────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  WM 2026 Predict  –  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"{'='*55}")

    # Daten laden
    print("\n[1/5] Daten laden ...")
    all_matches = pd.read_csv(RESULTS_FILE)
    all_matches["date"] = pd.to_datetime(all_matches["date"])
    all_matches = all_matches.sort_values("date").reset_index(drop=True)
    all_matches = all_matches.dropna(subset=["home_score", "away_score"])
    all_matches["home_score"] = all_matches["home_score"].astype(int)
    all_matches["away_score"] = all_matches["away_score"].astype(int)

    cutoff        = pd.Timestamp.now() - pd.DateOffset(years=20)
    model_matches = all_matches[all_matches["date"] >= cutoff].copy()
    print(f"  {len(all_matches)} Spiele gesamt | {len(model_matches)} fuer Modell")

    # Quoten
    print("\n[2/5] Quoten laden ...")
    odds_lookup, odds_date_map, odds_raw_map, odds_fetched_at = load_odds()

    # Elo
    print("\n[3/5] Elo berechnen ...")
    elo, all_matches = compute_elo(all_matches)

    # Form
    print("\n[4/5] Form berechnen ...")
    recent, all_matches = compute_form(all_matches)

    # Poisson
    print("\n[5/5] Poisson-Modell trainieren ...")
    poisson_model = train_poisson(all_matches, model_matches)

    # Vorhersagen
    print("\n  Vorhersagen berechnen ...")
    schedule = [
        (gname, teams[i], teams[j])
        for gname, teams in GROUPS.items()
        for i in range(len(teams))
        for j in range(i + 1, len(teams))
    ]

    matches_out = []
    for gname, t1, t2 in schedule:
        pred = predict_match(poisson_model, elo, recent, odds_lookup, odds_raw_map, t1, t2)

        t1o, t2o  = odds_name(t1), odds_name(t2)
        datum_raw = odds_date_map.get((t1o, t2o)) or odds_date_map.get((t2o, t1o))
        datum_dt  = pd.to_datetime(datum_raw) if datum_raw else None

        matches_out.append({
            "group":      gname,
            "home":       t1,
            "away":       t2,
            "date_iso":   datum_raw,
            "date_local": datum_dt.strftime("%d.%m.%Y") if datum_dt else "-",
            "time_local": datum_dt.strftime("%H:%M") if datum_dt else "-",
            **pred,
        })

    # Elo-Tabelle
    elo_table = sorted(elo.items(), key=lambda x: x[1], reverse=True)

    # predictions.json schreiben
    out = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "odds_fetched_at": odds_fetched_at,
        "odds_weight":     ODDS_WEIGHT,
        "model_weight":    MODEL_WEIGHT,
        "groups":          GROUPS,
        "matches":         matches_out,
        "elo_table":       [{"team": t, "elo": round(e)} for t, e in elo_table[:50]],
    }

    PREDICTIONS_FILE.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    ensemble_count = sum(1 for m in matches_out if m["source"] == "ensemble")
    print(f"\n  {len(matches_out)} Spiele vorhergesagt")
    print(f"  Ensemble: {ensemble_count} | Nur Modell: {len(matches_out)-ensemble_count}")
    print(f"  Gespeichert → {PREDICTIONS_FILE}")
    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    main()