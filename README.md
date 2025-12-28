# FitLog

**FitLog** ist eine Webanwendung zum Verwalten von Trainingsplänen sowie zur Visualisierung von Fortschritten.
Diese wurde mit **Flask** und **matplotlib** entwickelt.

---
## Voraussetzungen
- Python `>= 3.13`
- Die Module aus `requirements.txt`
---
## Setup 
### Windows
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
### Linux / macOS
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
---
## Initialisierung der Datenbank
Beim ersten Start muss die SQLite-Datenbank erstellt und mit Daten befüllt werden:
```
python init_db.py
python seed.py
```
Bei Erfolg wird diese unter `instance/fitlog.db` abgelegt.

---
# Start
```
python app.py
```

Danach den [Browser](http://127.0.0.1:5000/) öffnen. 


