"""init_db.py

Dieses Modul wird zur Initialisierung der SQLite Datenbank verwendet.
"""

import sqlite3
from pathlib import Path

def init_db() -> None:
    """Initialisiert die Datenbank mit dem SQL Skript aus `instance/init_db.sql`."""
    db_path = Path("instance/fitlog.db")
    sql_path = Path("instance/init_db.sql")

    # Ordner anlegen, falls dieser fehlt.
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'Datenbank wird unter "{db_path.resolve()}" initialisiert.')

    with sqlite3.connect(db_path) as connection:
        # Die SQL Datei wird eingelesen und alle Statements daraus ausgeführt.
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
        try:
            connection.executescript(sql_script)
            connection.commit()
        except sqlite3.OperationalError as e:
            # Ausgabe falls z.B. Syntaxfehler im SQL Skript existieren.
            print(f"Fehler beim Initialisieren der Datenbank: {e}")

    print("Datenbank wurde erfolgreich erstellt und initialisiert.")

if __name__ == "__main__":
    init_db()
