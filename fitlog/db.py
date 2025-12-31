"""fitlog/db.py

Dieses Modul stellt den Zugriff auf die SQLite Datenbank bereit.

- `get_db()` liefert pro Request genau eine Connection.
- `close_db()` schließt diese Connection am Ende des Requests wieder.
"""

import sqlite3
from sqlite3 import Connection
from pathlib import Path

from flask import current_app, g

def get_db() -> Connection:
    """Liefert pro Request genau eine Connection.

        return -- gibt die SQLite Connection für aktuellen Request zurück
    """

    # Connection pro Request nur einmal öffnen und in `g` ablegen.
    if "db" not in g:
        db_path = Path(current_app.instance_path) / "fitlog.db"

        # Ermöglicht automatisches Parsen von Datum- und Zeitspalten
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)

        # Damit row["name"] statt row[0] möglich ist
        g.db.row_factory = sqlite3.Row

        # SQLite prüft Foreign Keys standardmäßig nicht, daher hier aktivieren
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(e: Exception | None = None) -> None:
    """Schließt die DB-Connection am Ende des Requests.

        e -- Fehler beim Teardown. (kann optional noch behandelt werden)
    """

    # Connection aus `g` entfernen und schließen, sofern vorhanden
    db = g.pop("db", None)
    if db is not None:
        db.close()
