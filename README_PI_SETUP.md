# WM 2026 – Raspberry Pi Setup

## Architektur

```
scraper.py   → results.csv + odds.json
predict.py   → predictions.json
app.py       → Flask-Server (liest predictions.json)

Cron: 3x täglich scraper.py + predict.py
Flask: läuft dauerhaft als systemd-Service
```

---

## 1 · Installation

```bash
# Ins Projektverzeichnis
cd /home/pi/wm2026

# Dependencies installieren
pip install flask pandas numpy statsmodels scipy requests python-dotenv

# Optional: gunicorn für Produktion
pip install gunicorn
```

---

## 2 · .env anlegen (API Keys)

```bash
nano /home/pi/wm2026/.env
```

```env
KAGGLE_USERNAME=dein_kaggle_username
KAGGLE_KEY=dein_kaggle_key
ODDS_API_KEY=dein_odds_api_key
```

---

## 3 · Erster Test

```bash
# Daten holen
python scraper.py

# Vorhersagen berechnen (~45 Sekunden)
python predict.py

# Server starten
python app.py
# → http://localhost:5000
```

---

## 4 · Cron einrichten (3x täglich)

```bash
crontab -e
```

Folgende Zeilen einfügen:

```cron
# WM 2026 – Daten + Vorhersagen aktualisieren
# Täglich um 07:00, 13:00 und 19:00 Uhr
0 7  * * * cd /home/pi/wm2026 && python scraper.py >> logs/scraper.log 2>&1
5 7  * * * cd /home/pi/wm2026 && python predict.py >> logs/predict.log 2>&1

0 13 * * * cd /home/pi/wm2026 && python scraper.py >> logs/scraper.log 2>&1
5 13 * * * cd /home/pi/wm2026 && python predict.py >> logs/predict.log 2>&1

0 19 * * * cd /home/pi/wm2026 && python scraper.py >> logs/scraper.log 2>&1
5 19 * * * cd /home/pi/wm2026 && python predict.py >> logs/predict.log 2>&1
```

Log-Verzeichnis anlegen:

```bash
mkdir -p /home/pi/wm2026/logs
```

---

## 5 · Flask als systemd-Service (dauerhaft laufen)

```bash
sudo nano /etc/systemd/system/wm2026.service
```

```ini
[Unit]
Description=WM 2026 Tipp-App
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/wm2026
ExecStart=/usr/bin/python3 /home/pi/wm2026/app.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
# Service aktivieren und starten
sudo systemctl daemon-reload
sudo systemctl enable wm2026
sudo systemctl start wm2026

# Status prüfen
sudo systemctl status wm2026

# Logs anschauen
journalctl -u wm2026 -f
```

---

## 6 · Vom Handy / anderen Geräten erreichbar

```bash
# IP des Pi herausfinden
hostname -I
# z.B. 192.168.1.42
```

Dann im Browser auf dem Handy:
```
http://192.168.1.42:5000
```

> Alle Geräte müssen im gleichen WLAN sein.

### Optional: Von überall erreichbar (Tailscale – einfachste Lösung)

```bash
# Tailscale installieren (kostenloses VPN)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Dann ist der Pi unter seiner Tailscale-IP erreichbar
# z.B. http://100.x.x.x:5000
```

---

## 7 · Produktion mit gunicorn (stabiler als dev-Server)

Service-Datei anpassen:

```ini
ExecStart=/usr/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

```bash
sudo systemctl restart wm2026
```

---

## 8 · Dateistruktur

```
wm2026/
├── scraper.py        # Daten-Updater (Kaggle + Odds API)
├── predict.py        # Vorhersage-Engine → predictions.json
├── app.py            # Flask-Server
├── results.csv       # Historische Spielergebnisse
├── odds.json         # Aktuelle Wettquoten
├── predictions.json  # Berechnete Vorhersagen (wird von app.py gelesen)
├── .env              # API Keys (nicht ins Git!)
├── logs/
│   ├── scraper.log
│   └── predict.log
└── README_PI_SETUP.md
```

---

## 9 · Troubleshooting

**predict.py läuft zu lange (>2min auf Pi)?**
```bash
# TEAM_FILTER_YEARS in predict.py erhöhen (weniger Teams = schneller)
# z.B. TEAM_FILTER_YEARS = 4
```

**Flask nicht von außen erreichbar?**
```bash
# Sicherstellen dass host=0.0.0.0 in app.py gesetzt ist (bereits so)
# Firewall prüfen:
sudo ufw allow 5000
```

**Logs prüfen:**
```bash
tail -f logs/scraper.log
tail -f logs/predict.log
journalctl -u wm2026 -f
```