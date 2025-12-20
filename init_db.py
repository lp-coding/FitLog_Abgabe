import sqlite3
from pathlib import Path

def init_db():
    """Initialisiert die SQLite-Datenbank mit der SQL-Datei 001_init.sql."""
    db_path = Path("instance/fitlog.db")
    sql_path = Path("instance/init_db.sql")

    print(f'Datenbank wird unter "{db_path.resolve()}" initialisiert.')

    with sqlite3.connect(db_path) as connection:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
        try:
            connection.executescript(sql_script)
            connection.commit()
        except sqlite3.OperationalError as e:
            print(f"Fehler beim Initialisieren der Datenbank: {e}")

    print("Datenbank wurde erfolgreich erstellt und initialisiert.")

if __name__ == "__main__":
    init_db()
