"""
Seed-Skript für FitLog.

Dieses Skript fügt typische Fitnessstudio-Übungen in die Tabelle `exercises` ein.

Ausführung:
    python seed.py

Voraussetzung:
    - Die Datenbank wurde vorher mit `init_db.py` und `instance/init_db.sql`
      initialisiert.
"""

import sqlite3
from pathlib import Path

# Pfad zur SQLite-Datenbank – konsistent zu init_db.py / create_app
DB_PATH = Path("instance/fitlog.db")

# Typische Studio-Übungen (deutschsprachige Namen)
EXERCISES = [
    "Kniebeugen",
    "Beinpresse",
    "Kreuzheben",
    "Bankdrücken",
    "Schrägbankdrücken",
    "Rudern vorgebeugt",
    "Latziehen zur Brust",
    "Rudern am Kabel",
    "Schulterdrücken",
    "Seitheben",
    "Bizepscurls",
    "Trizepsdrücken am Kabel",
    "Plank",
    "Crunches",
]

PLANS = ["Oberkörper", "Beine", "Ganzkörper"]

def seed_exercises_plans(conn):
    """Fügt typische Übungen in `exercises` ein (idempotent)."""
    conn.execute("PRAGMA foreign_keys = ON;")

    for name in EXERCISES:
        conn.execute(
            "INSERT OR IGNORE INTO exercises (name) VALUES (?)",
            (name,),
        )

    for plan in PLANS:
        conn.execute(
            "INSERT OR IGNORE INTO training_plans (name) VALUES (?)",
            (plan,),
        )

    count_exercises = conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
    count_plans = conn.execute("SELECT COUNT(*) FROM training_plans").fetchone()[0]

    print(f"Tabelle `exercises` enthält jetzt {count_exercises} Übungen.")
    print(f"Tabelle `training_plans` enthält jetzt {count_plans} Übungen.")


def main() -> None:
    if not DB_PATH.exists():
        print(f"Datenbank '{DB_PATH}' existiert nicht.")
        print("Bitte zuerst `python init_db.py` ausführen.")
        return

    print(f"Verwende Datenbank: {DB_PATH.resolve()}")

    conn = sqlite3.connect(DB_PATH)
    try:
        seed_exercises_plans(conn)
        conn.commit()
        print("Seeding abgeschlossen.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
