CREATE TABLE IF NOT EXISTS users (
  id             INTEGER PRIMARY KEY,
  study_id       TEXT UNIQUE NOT NULL,
  password_hash  TEXT NOT NULL,
  group_id       INTEGER NOT NULL CHECK (group_id IN (1, 2, 3)),
  login_count    INTEGER NOT NULL DEFAULT 0,
  first_login_at TEXT,
  last_login_at  TEXT
);

CREATE TABLE IF NOT EXISTS login_events (
  id         INTEGER PRIMARY KEY,
  study_id   TEXT NOT NULL,
  role       TEXT NOT NULL,
  login_at   TEXT NOT NULL,
  session_id TEXT NOT NULL,
  group_id   INTEGER
);

CREATE TABLE IF NOT EXISTS admin_meta (
  id             INTEGER PRIMARY KEY CHECK (id = 1),
  login_count    INTEGER NOT NULL DEFAULT 0,
  first_login_at TEXT,
  last_login_at  TEXT
);

CREATE TABLE IF NOT EXISTS admin_actions (
  id         INTEGER PRIMARY KEY,
  action     TEXT NOT NULL,
  target_study_id TEXT,
  detail     TEXT,
  created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO admin_meta (id, login_count) VALUES (1, 0);

CREATE TABLE IF NOT EXISTS auth_tokens (
  token           TEXT PRIMARY KEY,
  study_id        TEXT NOT NULL,
  role            TEXT NOT NULL,
  session_file_id TEXT NOT NULL,
  revoked         INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL
);
