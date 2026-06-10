"""
app.py  –  WM 2026 Tipp-App (Flask)
=====================================
Liest predictions.json und zeigt:
  /           – Spielplan (alle Gruppenspiele)
  /match/<id> – Detail-Seite eines Spiels
  /elo        – Elo-Tabelle

Aufruf:
  python app.py
  → http://localhost:5000

Produktion (Raspberry Pi):
  gunicorn -w 2 -b 0.0.0.0:5000 app:app
"""

import json
import pickle
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, abort

app = Flask(__name__)

BASE_DIR         = Path(__file__).parent
PREDICTIONS_FILE = BASE_DIR / "predictions.json"
MODEL_FILE       = BASE_DIR / "model.pkl"


def load_predictions():
    if not PREDICTIONS_FILE.exists():
        return None
    with open(PREDICTIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_model_trained_at():
    """Liest trained_at aus model.pkl ohne das ganze Modell zu laden."""
    if not MODEL_FILE.exists():
        return None
    try:
        with open(MODEL_FILE, "rb") as f:
            payload = pickle.load(f)
        return payload.get("trained_at")
    except Exception:
        return None


def fmt_pct(v):
    if v is None: return "-"
    return f"{v*100:.1f}%"

def fmt_odds(v):
    if v is None: return "-"
    return f"{v:.2f}"

def fmt_dt(iso):
    if not iso: return "-"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d.%m. %H:%M")
    except Exception:
        return iso

def confidence_color(v):
    if v is None: return "secondary"
    if v >= 0.65: return "success"
    if v >= 0.50: return "warning"
    return "danger"

def source_badge(s):
    if s == "ensemble": return "primary"
    return "secondary"


# ── HTML-Base-Template ────────────────────────────────────────────────────────

BASE_HTML = """
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WM 2026 – Tipp-Vorhersage</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #0d1117; color: #e6edf3; }
    .card { background: #161b22; border: 1px solid #30363d; }
    .card-header { background: #1c2128; border-bottom: 1px solid #30363d; }
    .table { color: #e6edf3; }
    .table-hover tbody tr:hover { background: #1c2128; color: #e6edf3; }
    .table thead th { border-bottom: 2px solid #30363d; color: #8b949e; font-size: .8rem; text-transform: uppercase; }
    .nav-link { color: #8b949e; }
    .nav-link:hover, .nav-link.active { color: #e6edf3; }
    .badge-ensemble { background: #1f6feb; }
    .tipp-score { font-size: 1.4rem; font-weight: 700; letter-spacing: 2px; }
    .group-header { background: #1c2128; color: #f0883e; font-weight: 600; }
    .prob-bar-wrap { width: 100%; height: 6px; background: #30363d; border-radius: 3px; margin-top: 2px; }
    .prob-bar { height: 6px; border-radius: 3px; }
    a { color: #58a6ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .score-badge { font-size: .75rem; padding: 2px 6px; }
    .updated { font-size: .75rem; color: #8b949e; }
  </style>
</head>
<body>
<nav class="navbar navbar-dark" style="background:#161b22; border-bottom:1px solid #30363d">
  <div class="container">
    <a class="navbar-brand fw-bold" href="/">&#x26BD; WM 2026 Tipps</a>
    <div class="d-flex gap-3">
      <a class="nav-link {{ 'active' if active=='schedule' }}" href="/">Nach Datum</a>
      <a class="nav-link {{ 'active' if active=='groups' }}" href="/groups">Gruppen</a>
      <a class="nav-link {{ 'active' if active=='elo' }}" href="/elo">Elo-Tabelle</a>
    </div>
  </div>
</nav>
<div class="container py-4">
  {% block content %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


# ── Spielplan (nach Datum, Startseite) ──────────────────────────────────────

SCHEDULE_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">Spielplan WM 2026</h4>
  <div class="text-end updated">
    <div>&#x1F4CA; Vorhersage: {{ generated_at }}</div>
    <div>&#x1F4B9; Quoten: {{ odds_fetched_at }}</div>
    <div>&#x1F9E0; Modell: {{ model_trained_at }}</div>
  </div>
</div>

{% for day, matches in days.items() %}
<div class="card mb-3">
  <div class="card-header group-header">{{ day }}</div>
  <div class="table-responsive">
    <table class="table table-hover mb-0 align-middle">
      <thead>
        <tr>
          <th style="width:70px">Uhrzeit</th>
          <th style="width:60px">Gruppe</th>
          <th>Heim</th>
          <th class="text-center">Tipp</th>
          <th>Gast</th>
          <th class="text-center">1</th>
          <th class="text-center">X</th>
          <th class="text-center">2</th>
          <th class="text-center">Conf.</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for m in matches %}
        <tr>
          <td class="text-muted" style="font-size:.85rem">{{ m.time_display }}</td>
          <td><span class="badge bg-secondary">{{ m.group }}</span></td>
          <td>{{ m.home }}</td>
          <td class="text-center">
            <span class="tipp-score">{{ m.tipp_home }}:{{ m.tipp_away }}</span>
          </td>
          <td>{{ m.away }}</td>
          <td class="text-center">
            <div>{{ m.p_home_pct }}</div>
            <div class="prob-bar-wrap"><div class="prob-bar bg-success" style="width:{{ m.p_home_w }}%"></div></div>
          </td>
          <td class="text-center">
            <div>{{ m.p_draw_pct }}</div>
            <div class="prob-bar-wrap"><div class="prob-bar bg-warning" style="width:{{ m.p_draw_w }}%"></div></div>
          </td>
          <td class="text-center">
            <div>{{ m.p_away_pct }}</div>
            <div class="prob-bar-wrap"><div class="prob-bar bg-danger" style="width:{{ m.p_away_w }}%"></div></div>
          </td>
          <td class="text-center">
            <span class="badge bg-{{ m.conf_color }}">{{ m.conf_pct }}</span>
          </td>
          <td>
            <a href="/match/{{ m.match_id }}" class="btn btn-sm btn-outline-secondary py-0">Details</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endfor %}
{% endblock %}
""")


# ── Match-Detail ──────────────────────────────────────────────────────────────

DETAIL_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
{% block content %}
<a href="/" class="btn btn-sm btn-outline-secondary mb-3">&larr; Spielplan</a>

<div class="card mb-4">
  <div class="card-header group-header">Gruppe {{ m.group }} &nbsp;|&nbsp; {{ m.date_display }}</div>
  <div class="card-body">
    <div class="row align-items-center text-center">
      <div class="col-5">
        <div style="font-size:1.6rem; font-weight:700">{{ m.home }}</div>
        <div class="text-muted" style="font-size:.85rem">Elo {{ m.elo_home }}</div>
      </div>
      <div class="col-2">
        <div class="tipp-score" style="font-size:2.2rem">{{ m.tipp_home }}:{{ m.tipp_away }}</div>
        <div class="text-muted" style="font-size:.75rem">Tipp</div>
      </div>
      <div class="col-5">
        <div style="font-size:1.6rem; font-weight:700">{{ m.away }}</div>
        <div class="text-muted" style="font-size:.85rem">Elo {{ m.elo_away }}</div>
      </div>
    </div>
  </div>
</div>

<div class="row g-3 mb-4">

  <!-- Wahrscheinlichkeiten -->
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-header">Wahrscheinlichkeiten
        <span class="badge bg-{{ m.src_color }} float-end">{{ m.source }}</span>
      </div>
      <div class="card-body">
        <table class="table table-sm mb-0">
          <thead><tr><th></th><th class="text-center">Ensemble</th><th class="text-center">Modell</th><th class="text-center">Quoten</th></tr></thead>
          <tbody>
            <tr>
              <td>{{ m.home }} Sieg</td>
              <td class="text-center"><strong>{{ m.p_home_pct }}</strong></td>
              <td class="text-center text-muted">{{ m.p_home_model_pct }}</td>
              <td class="text-center text-muted">{{ m.p_home_odds_pct }}</td>
            </tr>
            <tr>
              <td>Unentschieden</td>
              <td class="text-center"><strong>{{ m.p_draw_pct }}</strong></td>
              <td class="text-center text-muted">{{ m.p_draw_model_pct }}</td>
              <td class="text-center text-muted">{{ m.p_draw_odds_pct }}</td>
            </tr>
            <tr>
              <td>{{ m.away }} Sieg</td>
              <td class="text-center"><strong>{{ m.p_away_pct }}</strong></td>
              <td class="text-center text-muted">{{ m.p_away_model_pct }}</td>
              <td class="text-center text-muted">{{ m.p_away_odds_pct }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Modell-Details -->
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-header">Modell-Details</div>
      <div class="card-body">
        <table class="table table-sm mb-0">
          <tbody>
            <tr><td>Erwartete Tore</td>
                <td class="text-end"><strong>{{ m.exp_goals_home }}</strong> – <strong>{{ m.exp_goals_away }}</strong></td></tr>
            <tr><td>Elo</td>
                <td class="text-end">{{ m.elo_home }} – {{ m.elo_away }}</td></tr>
            <tr><td>Form (0–1)</td>
                <td class="text-end">{{ m.form_home }} – {{ m.form_away }}</td></tr>
            <tr><td>Confidence</td>
                <td class="text-end"><span class="badge bg-{{ m.conf_color }}">{{ m.conf_pct }}</span></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Wettquoten -->
  {% if m.has_odds %}
  <div class="col-md-6">
    <div class="card">
      <div class="card-header">Wettquoten (Buchmacher)</div>
      <div class="card-body">
        <table class="table table-sm mb-0">
          <thead><tr><th>{{ m.home }}</th><th class="text-center">Unentschieden</th><th class="text-end">{{ m.away }}</th></tr></thead>
          <tbody>
            <tr>
              <td><strong>{{ m.odds_home }}</strong></td>
              <td class="text-center"><strong>{{ m.odds_draw }}</strong></td>
              <td class="text-end"><strong>{{ m.odds_away }}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
  {% endif %}

  <!-- Top-10 Ergebnisse -->
  <div class="col-md-6">
    <div class="card">
      <div class="card-header">Wahrscheinlichste Ergebnisse</div>
      <div class="card-body">
        <table class="table table-sm mb-0">
          <thead><tr><th>Ergebnis</th><th class="text-end">Wahrscheinlichkeit</th></tr></thead>
          <tbody>
            {% for s in m.top10 %}
            <tr {% if loop.first %}class="table-active"{% endif %}>
              <td>{{ m.home }} <strong>{{ s.home }}:{{ s.away }}</strong> {{ m.away }}</td>
              <td class="text-end">{{ s.prob_pct }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>
{% endblock %}
""")


# ── Gruppen-Ansicht ─────────────────────────────────────────────────────────

GROUPS_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">Gruppenphase – Alle Spiele</h4>
  <span class="updated">Stand: {{ generated_at }}</span>
</div>

{% for group, matches in groups.items() %}
<div class="card mb-3">
  <div class="card-header group-header">Gruppe {{ group }}</div>
  <div class="table-responsive">
    <table class="table table-hover mb-0 align-middle">
      <thead>
        <tr>
          <th style="width:110px">Datum</th>
          <th>Heim</th>
          <th class="text-center">Tipp</th>
          <th>Gast</th>
          <th class="text-center">1</th>
          <th class="text-center">X</th>
          <th class="text-center">2</th>
          <th class="text-center">Conf.</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for m in matches %}
        <tr>
          <td class="text-muted" style="font-size:.85rem">{{ m.date_display }}</td>
          <td>{{ m.home }}</td>
          <td class="text-center">
            <span class="tipp-score">{{ m.tipp_home }}:{{ m.tipp_away }}</span>
          </td>
          <td>{{ m.away }}</td>
          <td class="text-center">
            <div>{{ m.p_home_pct }}</div>
            <div class="prob-bar-wrap"><div class="prob-bar bg-success" style="width:{{ m.p_home_w }}%"></div></div>
          </td>
          <td class="text-center">
            <div>{{ m.p_draw_pct }}</div>
            <div class="prob-bar-wrap"><div class="prob-bar bg-warning" style="width:{{ m.p_draw_w }}%"></div></div>
          </td>
          <td class="text-center">
            <div>{{ m.p_away_pct }}</div>
            <div class="prob-bar-wrap"><div class="prob-bar bg-danger" style="width:{{ m.p_away_w }}%"></div></div>
          </td>
          <td class="text-center">
            <span class="badge bg-{{ m.conf_color }}">{{ m.conf_pct }}</span>
          </td>
          <td>
            <a href="/match/{{ m.match_id }}" class="btn btn-sm btn-outline-secondary py-0">Details</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endfor %}
{% endblock %}
""")


# ── Elo-Tabelle ───────────────────────────────────────────────────────────────

ELO_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">Elo-Rangliste (Top 50)</h4>
  <span class="updated">Stand: {{ generated_at }}</span>
</div>
<div class="card">
  <div class="table-responsive">
    <table class="table table-hover mb-0">
      <thead><tr><th>#</th><th>Team</th><th class="text-end">Elo</th></tr></thead>
      <tbody>
        {% for row in elo_table %}
        <tr>
          <td class="text-muted">{{ loop.index }}</td>
          <td>{{ row.team }}</td>
          <td class="text-end"><strong>{{ row.elo }}</strong></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
""")


# ── Routen ──────────────────────────────────────────────────────────────────

@app.route("/")
def schedule():
    data = load_predictions()
    if not data:
        return "<h2>Keine Vorhersagen gefunden. Bitte predict.py ausfuehren.</h2>", 503

    generated_at    = fmt_dt(data["generated_at"])
    odds_fetched_at = fmt_dt(data.get("odds_fetched_at"))
    model_trained_at = fmt_dt(load_model_trained_at())

    # Matches nach Datum sortieren und nach Tag gruppieren
    from collections import OrderedDict
    dated, undated = [], []
    for m in data["matches"]:
        iso = m.get("date_iso")
        if iso:
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                dated.append((dt, m))
            except Exception:
                undated.append(m)
        else:
            undated.append(m)

    dated.sort(key=lambda x: x[0])

    days = OrderedDict()
    for dt, m in dated:
        day_key = dt.strftime("%A, %d.%m.%Y")
        if day_key not in days:
            days[day_key] = []
        match_id = f"{m['home'].lower().replace(' ','-')}--{m['away'].lower().replace(' ','-')}"
        days[day_key].append({
            "match_id":    match_id,
            "group":       m["group"],
            "home":        m["home"],
            "away":        m["away"],
            "tipp_home":   m["tipp_home"],
            "tipp_away":   m["tipp_away"],
            "time_display": dt.strftime("%H:%M"),
            "p_home_pct":  fmt_pct(m["p_home"]),
            "p_draw_pct":  fmt_pct(m["p_draw"]),
            "p_away_pct":  fmt_pct(m["p_away"]),
            "p_home_w":    round(m["p_home"] * 100, 1),
            "p_draw_w":    round(m["p_draw"] * 100, 1),
            "p_away_w":    round(m["p_away"] * 100, 1),
            "conf_pct":    fmt_pct(m["confidence"]),
            "conf_color":  confidence_color(m["confidence"]),
            "source":      m["source"],
            "src_color":   source_badge(m["source"]),
        })

    return render_template_string(
        SCHEDULE_HTML,
        days=days,
        generated_at=generated_at,
        odds_fetched_at=odds_fetched_at,
        model_trained_at=model_trained_at,
        active="schedule"
    )


@app.route("/match/<match_id>")
def match_detail(match_id):
    data = load_predictions()
    if not data:
        abort(503)

    match = None
    for m in data["matches"]:
        mid = f"{m['home'].lower().replace(' ','-')}--{m['away'].lower().replace(' ','-')}"
        if mid == match_id:
            match = m
            break

    if not match:
        abort(404)

    top10 = [{
        "home":     s["home"],
        "away":     s["away"],
        "prob_pct": fmt_pct(s["prob"])
    } for s in match["top10_scores"]]

    ctx = {
        "m": {
            "group":             match["group"],
            "home":              match["home"],
            "away":              match["away"],
            "tipp_home":         match["tipp_home"],
            "tipp_away":         match["tipp_away"],
            "date_display":      fmt_dt(match.get("date_iso")),
            "p_home_pct":        fmt_pct(match["p_home"]),
            "p_draw_pct":        fmt_pct(match["p_draw"]),
            "p_away_pct":        fmt_pct(match["p_away"]),
            "p_home_model_pct":  fmt_pct(match.get("p_home_model")),
            "p_draw_model_pct":  fmt_pct(match.get("p_draw_model")),
            "p_away_model_pct":  fmt_pct(match.get("p_away_model")),
            "p_home_odds_pct":   fmt_pct(match.get("p_home_odds")),
            "p_draw_odds_pct":   fmt_pct(match.get("p_draw_odds")),
            "p_away_odds_pct":   fmt_pct(match.get("p_away_odds")),
            "exp_goals_home":    match["expected_goals_home"],
            "exp_goals_away":    match["expected_goals_away"],
            "elo_home":          match["elo_home"],
            "elo_away":          match["elo_away"],
            "form_home":         match["form_home"],
            "form_away":         match["form_away"],
            "conf_pct":          fmt_pct(match["confidence"]),
            "conf_color":        confidence_color(match["confidence"]),
            "source":            match["source"],
            "src_color":         source_badge(match["source"]),
            "has_odds":          match.get("odds_home") is not None,
            "odds_home":         fmt_odds(match.get("odds_home")),
            "odds_draw":         fmt_odds(match.get("odds_draw")),
            "odds_away":         fmt_odds(match.get("odds_away")),
            "top10":             top10,
        },
        "active": "schedule"
    }
    return render_template_string(DETAIL_HTML, **ctx)


@app.route("/groups")
def groups_view():
    data = load_predictions()
    if not data:
        return "<h2>Keine Vorhersagen gefunden. Bitte predict.py ausfuehren.</h2>", 503

    generated_at = fmt_dt(data["generated_at"])
    groups_out   = {}

    for m in data["matches"]:
        g = m["group"]
        if g not in groups_out:
            groups_out[g] = []
        match_id = f"{m['home'].lower().replace(' ','-')}--{m['away'].lower().replace(' ','-')}"
        groups_out[g].append({
            "match_id":    match_id,
            "home":        m["home"],
            "away":        m["away"],
            "tipp_home":   m["tipp_home"],
            "tipp_away":   m["tipp_away"],
            "date_display": fmt_dt(m.get("date_iso")),
            "p_home_pct":  fmt_pct(m["p_home"]),
            "p_draw_pct":  fmt_pct(m["p_draw"]),
            "p_away_pct":  fmt_pct(m["p_away"]),
            "p_home_w":    round(m["p_home"] * 100, 1),
            "p_draw_w":    round(m["p_draw"] * 100, 1),
            "p_away_w":    round(m["p_away"] * 100, 1),
            "conf_pct":    fmt_pct(m["confidence"]),
            "conf_color":  confidence_color(m["confidence"]),
        })

    return render_template_string(
        GROUPS_HTML,
        groups=groups_out,
        generated_at=generated_at,
        active="groups"
    )


@app.route("/elo")
def elo_table():
    data = load_predictions()
    if not data:
        abort(503)
    return render_template_string(
        ELO_HTML,
        elo_table=data["elo_table"],
        generated_at=fmt_dt(data["generated_at"]),
        active="elo"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)