""" Der zentrale Einstiegspunkt für FitLog.

Die Flask Anwendung wird hier über die Application Factory `create_app()` erstellt.
Anschließend wird der Server gestartet.
"""

from fitlog import create_app

app = create_app()

if __name__ == "__main__":
    # Die App wird lokal (127.0.0.1) auf Port 5000 im Debug-Modus gestartet.
    app.run(host="127.0.0.1", port=5000,debug=True)
