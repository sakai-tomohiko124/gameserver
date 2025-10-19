import sqlite3
import os
from typing import Optional
from datetime import datetime
import json
try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
    JAPAN_TZ = ZoneInfo('Asia/Tokyo')
except Exception:
    # fallback: use UTC offset manually if zoneinfo not available
    from datetime import timezone, timedelta
    JAPAN_TZ = timezone(timedelta(hours=9))

DB_PATH = os.environ.get('GAMESERVER_DB') or os.path.join(os.path.dirname(__file__), 'gameserver.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(schema_path: Optional[str] = None):
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(__file__), 'data.sql')
    conn = get_conn()
    with open(schema_path, 'r', encoding='utf8') as f:
        sql = f.read()
    conn.executescript(sql)
    conn.commit()
    return conn


def create_game(game_id: str, metadata: Optional[str] = None):
    conn = get_conn()
    # use Japan local time (timezone-aware)
    ts = datetime.now(JAPAN_TZ).isoformat()
    conn.execute('INSERT OR REPLACE INTO games(id, created_at, status, metadata) VALUES(?,?,?,?)', (game_id, ts, 'created', metadata))
    conn.commit()


def add_message(game_id: str, player_id: Optional[str], name: Optional[str], text: str):
    conn = get_conn()
    # use Japan local time (timezone-aware)
    ts = datetime.now(JAPAN_TZ).isoformat()
    conn.execute('INSERT INTO messages(game_id, player_id, name, text, ts) VALUES(?,?,?,?,?)', (game_id, player_id, name, text, ts))
    conn.commit()


def add_play(game_id: str, player_id: Optional[str], card_text: str, meta: Optional[str] = None):
    conn = get_conn()
    # use Japan local time (timezone-aware)
    ts = datetime.now(JAPAN_TZ).isoformat()
    conn.execute('INSERT INTO plays(game_id, player_id, card_text, ts, meta) VALUES(?,?,?,?,?)', (game_id, player_id, card_text, ts, meta))
    conn.commit()


def set_player_finished(game_id: str, player_id: str, rank: int):
    conn = get_conn()
    conn.execute('UPDATE players SET finished_rank = ? WHERE id = ? AND game_id = ?', (rank, player_id, game_id))
    conn.commit()


def set_game_finished(game_id: str, results):
    """
    Persist final game results and mark game as finished.
    `results` may be a dict mapping player_id->rank or a list of dicts like [{'player_id':..., 'rank':...}, ...]
    This will update players.finished_rank where possible, update games.status, and insert an event record.
    """
    conn = get_conn()
    ts = datetime.now(JAPAN_TZ).isoformat()
    # normalize results to dict of player_id->rank
    mapping = {}
    if isinstance(results, dict):
        mapping = results
    elif isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and 'player_id' in item and 'rank' in item:
                mapping[item['player_id']] = item['rank']
    # update player rows
    for pid, rank in mapping.items():
        try:
            conn.execute('UPDATE players SET finished_rank = ? WHERE id = ? AND game_id = ?', (rank, pid, game_id))
        except Exception:
            pass
    # mark game finished
    conn.execute('UPDATE games SET status = ? WHERE id = ?', ('finished', game_id))
    # insert event payload
    payload = json.dumps({'results': mapping})
    conn.execute('INSERT INTO events(game_id, type, payload, ts) VALUES(?,?,?,?)', (game_id, 'game_finished', payload, ts))
    conn.commit()


def record_round_results(game_id: str, results):
    """
    Record a round's results and update cumulative scores.
    `results` is a list of {'player_id':..., 'rank':...} or a dict player_id->rank.
    Scoring rule: points = max(0, num_players - rank)
    """
    conn = get_conn()
    # ensure players table has score column
    try:
        conn.execute('ALTER TABLE players ADD COLUMN score INTEGER DEFAULT 0')
        conn.commit()
    except Exception:
        # column may already exist
        pass

    # normalize results to list of dicts
    mapping = {}
    if isinstance(results, dict):
        mapping = results
    elif isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and 'player_id' in item and 'rank' in item:
                mapping[item['player_id']] = item['rank']

    # count players in the game
    cur = conn.execute('SELECT COUNT(*) as c FROM players WHERE game_id = ?', (game_id,))
    row = cur.fetchone()
    num_players = row['c'] if row else 0

    ts = datetime.now(JAPAN_TZ).isoformat()
    # update each player's finished_rank and score
    for pid, rank in mapping.items():
        try:
            points = max(0, num_players - int(rank))
        except Exception:
            points = 0
        # update finished_rank
        try:
            conn.execute('UPDATE players SET finished_rank = ? WHERE id = ? AND game_id = ?', (rank, pid, game_id))
        except Exception:
            pass
        # add to cumulative score
        try:
            conn.execute('UPDATE players SET score = COALESCE(score,0) + ? WHERE id = ? AND game_id = ?', (points, pid, game_id))
        except Exception:
            pass
    # insert event
    try:
        payload = json.dumps({'results': mapping})
        conn.execute('INSERT INTO events(game_id, type, payload, ts) VALUES(?,?,?,?)', (game_id, 'round_results', payload, ts))
    except Exception:
        pass
    conn.commit()
