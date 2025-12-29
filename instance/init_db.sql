PRAGMA foreign_keys = ON;

-- ============================
--  Trainingspläne (Soft-Delete)
-- ============================
CREATE TABLE IF NOT EXISTS training_plans (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,                    -- kein UNIQUE direkt auf der Spalte
    deleted_at TEXT DEFAULT NULL,                -- Soft-Delete: NULL = aktiv
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Nur aktive Pläne müssen einen einzigartigen Namen haben. (kein blockieren durch gelöschte Pläne)
-- Da SQLite kein where unterstützt, kann das Statement nicht ins create table eingefügt werden.
CREATE UNIQUE INDEX IF NOT EXISTS uq_training_plans_name
  ON training_plans(name)
  WHERE deleted_at IS NULL;


-- ============================
--  Übungen
-- ============================
CREATE TABLE IF NOT EXISTS exercises (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);


-- ============================
--  Zuordnung: Plan ↔ Übungen
-- ============================
CREATE TABLE IF NOT EXISTS plan_exercises (
    plan_id            INTEGER NOT NULL,
    exercise_id        INTEGER NOT NULL,
    position           INTEGER,                  -- Reihenfolge im Plan
    default_sets       INTEGER DEFAULT 3,
    default_reps       INTEGER DEFAULT 10,
    default_weight_kg  REAL    DEFAULT 0,
    note               TEXT,
    PRIMARY KEY (plan_id, exercise_id),
    FOREIGN KEY (plan_id)     REFERENCES training_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id)      ON DELETE RESTRICT
);


-- ============================
--  Trainings-Sessions (Kopf)
-- ============================
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id    INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, --alt: (datetime('now')) daher noch testen!
    ended_at   TEXT,
    FOREIGN KEY (plan_id) REFERENCES training_plans(id) ON DELETE RESTRICT
);


-- ============================
--  Trainings-Sessions (Einträge)
--  (eine Zeile pro Übung in der Session)
-- ============================
CREATE TABLE IF NOT EXISTS session_entries (
    session_id  INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    weight_kg   REAL,
    reps        INTEGER,
    sets        INTEGER DEFAULT 3,
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, --alt: (datetime('now')) daher noch testen!
    PRIMARY KEY (session_id, exercise_id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)   ON DELETE CASCADE,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE RESTRICT,
    CHECK (reps IS NULL OR reps >= 0),
    CHECK (weight_kg IS NULL OR weight_kg >= 0)
);