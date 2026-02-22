"""seed.py

Dieses Modul befüllt die Tabellen `exercises` und `training_plans` mit Beispieldaten.
"""

import sqlite3
from sqlite3 import Connection
from pathlib import Path

# Pfad zur SQLite Datenbank
DB_PATH = Path("instance/fitlog.db")

# Typische Fitness Übungen
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

# Beispiel Trainingspläne
PLANS = ["Oberkörper", "Beine", "Ganzkörper"]

def seed_exercises_plans(conn: Connection) -> None:
    """Fügt Übungen und Trainingspläne in die Datenbank ein.

    conn -- für die DB Connection benötigt.
    """
    # Für SQLite Foreign Keys explizit aktivieren.
    conn.execute("PRAGMA foreign_keys = ON;")

    # `INSERT OR IGNORE` verhindern Duplikate, sodass das Skript auch mehrfach ausgeführt werden könnte.
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

    # Ausgabe für den Nutzer, ob Daten jetzt vorhanden sind.
    count_exercises = conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
    count_plans = conn.execute("SELECT COUNT(*) FROM training_plans").fetchone()[0]

    print(f"Tabelle `exercises` enthält jetzt {count_exercises} Übungen.")
    print(f"Tabelle `training_plans` enthält jetzt {count_plans} Pläne.")


def main() -> None:
    """Einstiegspunkt um die DB zu prüfen, Daten einzufügen und Verbindung zu schließen."""
    if not DB_PATH.exists():
        print(f"Datenbank '{DB_PATH}' existiert nicht.")
        print("Bitte zuerst `python init_db.py` ausführen.")
        return

    print(f"Verwende Datenbank: {DB_PATH.resolve()}")

    conn = sqlite3.connect(DB_PATH)
    try:
        seed_exercises_plans(conn)
        conn.commit()
        print("Einfügen der Beispieldaten abgeschlossen.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
