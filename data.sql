-- PostgreSQL用のスキーマ定義

-- games テーブル
-- サーバーで起動するゲームセッションの基本情報を記録します。
CREATE TABLE IF NOT EXISTS games (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL, -- タイムゾーン付きの日時型に修正
  status TEXT NOT NULL,
  metadata JSONB -- JSON形式のデータを効率的に保存する型に修正
);

-- players テーブル
-- 各ゲームセッションに参加するプレイヤーの情報を記録します。
CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE, -- REFERENCESで外部キーを直接定義
  name TEXT,
  is_bot BOOLEAN DEFAULT FALSE, -- INTEGERからBOOLEAN(真偽値)型に修正
  finished_rank INTEGER,
  score INTEGER DEFAULT 0 -- record_round_resultsで使われるscoreカラムを最初から追加
);

-- messages テーブル
-- ゲーム内のチャットメッセージなどを記録します。
CREATE TABLE IF NOT EXISTS messages (
  id SERIAL PRIMARY KEY, -- AUTOINCREMENT を SERIAL に修正
  game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  player_id TEXT,
  name TEXT,
  text TEXT,
  ts TIMESTAMPTZ NOT NULL
);

-- plays テーブル
-- プレイヤーがどのカードを出したかなどのプレイ履歴を記録します。
CREATE TABLE IF NOT EXISTS plays (
  id SERIAL PRIMARY KEY, -- AUTOINCREMENT を SERIAL に修正
  game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  player_id TEXT,
  card_text TEXT,
  ts TIMESTAMPTZ NOT NULL,
  meta JSONB
);

-- events テーブル
-- ゲーム内で発生した特定のイベント（ゲーム終了など）を記録します。
CREATE TABLE IF NOT EXISTS events (
  id SERIAL PRIMARY KEY, -- AUTOINCREMENT を SERIAL に修正
  game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  payload JSONB,
  ts TIMESTAMPTZ NOT NULL
);