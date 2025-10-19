-- Schema for gameserver persistence
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS games (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  metadata TEXT
);

CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL,
  name TEXT,
  is_bot INTEGER DEFAULT 0,
  finished_rank INTEGER,
  FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  player_id TEXT,
  name TEXT,
  text TEXT,
  ts TEXT NOT NULL,
  FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plays (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  player_id TEXT,
  card_text TEXT,
  ts TEXT NOT NULL,
  meta TEXT,
  FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  type TEXT NOT NULL,
  payload TEXT,
  ts TEXT NOT NULL,
  FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
);
