import os
import json
import psycopg2
import psycopg2.extras # 辞書形式で結果を取得するために必要
from typing import Optional
from datetime import datetime

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
    JAPAN_TZ = ZoneInfo('Asia/Tokyo')
except ImportError:
    # fallback: use UTC offset manually if zoneinfo not available
    from datetime import timezone, timedelta
    JAPAN_TZ = timezone(timedelta(hours=9))

# Netlifyの環境変数からデータベース接続URLを取得します
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_conn():
    """PostgreSQLデータベースへの接続を取得します。"""
    # DATABASE_URLを使って接続します
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db(schema_path: Optional[str] = None):
    """
    【注意】この関数はRenderの管理画面から手動でSQLを実行するため、通常は使いません。
    ローカルでのテスト用、または初回セットアップの参考として残しています。
    """
    if schema_path is None:
        # data.sqlは functions フォルダの外にあるため、パスの調整が必要になる場合があります
        # 例: ../data.sql
        schema_path = os.path.join(os.path.dirname(__file__), '..', 'data.sql')
    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            with open(schema_path, 'r', encoding='utf8') as f:
                # data.sqlファイルの内容を実行します
                sql = f.read()
                cur.execute(sql)
        conn.commit()
    finally:
        conn.close()
    return conn


def create_game(game_id: str, metadata: Optional[str] = None):
    conn = get_conn()
    ts = datetime.now(JAPAN_TZ).isoformat()
    # SQL文法を変更:
    # 1. プレースホルダーを '?' から '%s' に変更
    # 2. 'INSERT OR REPLACE' を PostgreSQL の 'ON CONFLICT DO UPDATE' 構文に変更
    sql = """
        INSERT INTO games(id, created_at, status, metadata) 
        VALUES(%s, %s, %s, %s)
        ON CONFLICT (id) 
        DO UPDATE SET created_at = EXCLUDED.created_at, status = EXCLUDED.status, metadata = EXCLUDED.metadata;
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (game_id, ts, 'created', metadata))
        conn.commit()
    finally:
        conn.close()


def add_message(game_id: str, player_id: Optional[str], name: Optional[str], text: str):
    conn = get_conn()
    ts = datetime.now(JAPAN_TZ).isoformat()
    # プレースホルダーを '?' から '%s' に変更
    sql = 'INSERT INTO messages(game_id, player_id, name, text, ts) VALUES(%s, %s, %s, %s, %s)'
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (game_id, player_id, name, text, ts))
        conn.commit()
    finally:
        conn.close()


def add_play(game_id: str, player_id: Optional[str], card_text: str, meta: Optional[str] = None):
    conn = get_conn()
    ts = datetime.now(JAPAN_TZ).isoformat()
    # プレースホルダーを '?' から '%s' に変更
    sql = 'INSERT INTO plays(game_id, player_id, card_text, ts, meta) VALUES(%s, %s, %s, %s, %s)'
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (game_id, player_id, card_text, ts, meta))
        conn.commit()
    finally:
        conn.close()


def set_player_finished(game_id: str, player_id: str, rank: int):
    conn = get_conn()
    # プレースホルダーを '?' から '%s' に変更
    sql = 'UPDATE players SET finished_rank = %s WHERE id = %s AND game_id = %s'
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (rank, player_id, game_id))
        conn.commit()
    finally:
        conn.close()


def set_game_finished(game_id: str, results):
    conn = get_conn()
    ts = datetime.now(JAPAN_TZ).isoformat()
    mapping = {}
    if isinstance(results, dict):
        mapping = results
    elif isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and 'player_id' in item and 'rank' in item:
                mapping[item['player_id']] = item['rank']
    
    try:
        with conn.cursor() as cur:
            # プレイヤーのランクを更新
            for pid, rank in mapping.items():
                cur.execute('UPDATE players SET finished_rank = %s WHERE id = %s AND game_id = %s', (rank, pid, game_id))
            
            # ゲームのステータスを更新
            cur.execute('UPDATE games SET status = %s WHERE id = %s', ('finished', game_id))
            
            # イベントを記録
            payload = json.dumps({'results': mapping})
            cur.execute('INSERT INTO events(game_id, type, payload, ts) VALUES(%s, %s, %s, %s)', (game_id, 'game_finished', payload, ts))
        conn.commit()
    finally:
        conn.close()


def record_round_results(game_id: str, results):
    conn = get_conn()
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # scoreカラムが存在しない場合、追加する (PostgreSQLでは IF NOT EXISTS が使える)
            # ただし、初回に手動でSQLを実行すれば、このコードは不要になる
            try:
                cur.execute('ALTER TABLE players ADD COLUMN score INTEGER DEFAULT 0')
                conn.commit()
            except psycopg2.errors.DuplicateColumn:
                conn.rollback() # エラーが出た場合はトランザクションをリセット

            mapping = {}
            if isinstance(results, dict):
                mapping = results
            elif isinstance(results, list):
                for item in results:
                    if isinstance(item, dict) and 'player_id' in item and 'rank' in item:
                        mapping[item['player_id']] = item['rank']

            # プレイヤー数を取得
            cur.execute('SELECT COUNT(*) as c FROM players WHERE game_id = %s', (game_id,))
            row = cur.fetchone()
            num_players = row['c'] if row else 0

            ts = datetime.now(JAPAN_TZ).isoformat()
            for pid, rank in mapping.items():
                points = max(0, num_players - int(rank))
                # ランクを更新
                cur.execute('UPDATE players SET finished_rank = %s WHERE id = %s AND game_id = %s', (rank, pid, game_id))
                # スコアを更新
                cur.execute('UPDATE players SET score = COALESCE(score, 0) + %s WHERE id = %s AND game_id = %s', (points, pid, game_id))
            
            # イベントを記録
            payload = json.dumps({'results': mapping})
            cur.execute('INSERT INTO events(game_id, type, payload, ts) VALUES(%s, %s, %s, %s)', (game_id, 'round_results', payload, ts))
        
        conn.commit()
    finally:
        conn.close()