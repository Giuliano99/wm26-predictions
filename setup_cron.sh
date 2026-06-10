#!/bin/bash
# setup_cron.sh  –  Cron-Jobs auf dem Raspberry Pi einrichten
#
# Aufruf:
#   chmod +x setup_cron.sh
#   ./setup_cron.sh

WM_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$WM_DIR/.venv/bin/python"
LOG_DIR="$WM_DIR/logs"

mkdir -p "$LOG_DIR"

echo "WM 2026 – Cron Setup"
echo "Verzeichnis: $WM_DIR"
echo "Python:      $PYTHON"
echo ""

# Prüfen ob venv existiert
if [ ! -f "$PYTHON" ]; then
    echo "FEHLER: Kein .venv gefunden. Bitte zuerst:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Bestehende WM-Cron-Jobs entfernen
crontab -l 2>/dev/null | grep -v "scraper.py\|predict.py" | crontab -

# Neue Jobs hinzufügen
(
  crontab -l 2>/dev/null
  echo ""
  echo "# WM 2026 – Daten + Vorhersage (3x täglich: 7:00, 13:00, 20:00)"
  echo "0 7  * * * cd $WM_DIR && $PYTHON scraper.py >> $LOG_DIR/scraper.log 2>&1 && $PYTHON predict.py >> $LOG_DIR/predict.log 2>&1"
  echo "0 13 * * * cd $WM_DIR && $PYTHON scraper.py >> $LOG_DIR/scraper.log 2>&1 && $PYTHON predict.py >> $LOG_DIR/predict.log 2>&1"
  echo "0 20 * * * cd $WM_DIR && $PYTHON scraper.py >> $LOG_DIR/scraper.log 2>&1 && $PYTHON predict.py >> $LOG_DIR/predict.log 2>&1"
) | crontab -

echo "Cron-Jobs eingerichtet:"
crontab -l | grep "predict.py"
echo ""
echo "Logs werden geschrieben nach:"
echo "  $LOG_DIR/scraper.log"
echo "  $LOG_DIR/predict.log"
echo ""
echo "Flask-Server starten:"
echo "  .venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 app:app"
