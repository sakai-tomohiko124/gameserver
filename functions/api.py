# api.py
from flask import Flask, render_template, request, jsonify
import uuid
import threading
from flask_socketio import SocketIO, join_room as sio_join_room, leave_room as sio_leave_room
import json
import re
import datetime
import logging
from scraper import fetch_novel_metadata
import rooms
import shiritori
from flask import Response
import time
import requests
import random
import click

# Flaskアプリを初期化
# テンプレートと静的フォルダはプロジェクトルートの `templates` / `static` を使う
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
# Socket.IO for interactive games
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# Simple in-memory rooms for babanuki websocket gameplay
# room_id -> {players: [{'id','name','sid','is_bot'}], hands: {pid: [cards]}, alive: [pid], turn_idx: int, running: bool, pending_action: None, bot_difficulties: {pid:diff}}
BABA_ROOMS = {}

# トップページ (小説への案内)
@app.route('/')
def index():
    # まずスクレイピングで取得を試みる（メタ情報のみ）
    source_url = 'https://www.alphapolis.co.jp/novel/31484585/380882757'
    meta = fetch_novel_metadata(source_url)
    if meta:
        novel_info = {
            'title': meta.get('title') or 'タイトル取得失敗',
            'author': meta.get('author') or '作者不明',
            'url': source_url,
            'description': meta.get('description') or '説明がありません',
            'cover': meta.get('cover') or '',
        }
    else:
        # フォールバック情報
        novel_info = {
            'title': 'あだなが242個ある男～こういうときはAREを使おう！～',
            'author': 'ともはる',
            'url': source_url,
            'description': 'ともはる先生の思い出がたくさん詰まった物語！！'
        }
    return render_template('index.html', novel=novel_info)

# 大富豪のゲームページ
@app.route('/game/daifugo')
def daifugo():
    return render_template('daifugo.html')


@app.route('/api/rooms', methods=['POST'])
def api_create_room():
    data = request.get_json() or {}
    name = data.get('name') or 'Player'
    result = rooms.create_room(name)
    # return room id and player id
    return jsonify({'room_id': result['room']['id'], 'player_id': result['player_id'], 'room': result['room']})


@app.route('/api/rooms/<room_id>/join', methods=['POST'])
def api_join_room(room_id):
    data = request.get_json() or {}
    name = data.get('name') or 'Player'
    try:
        result = rooms.join_room(room_id, name)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    resp = {'room_id': room_id, 'player_id': result['player_id'], 'room': result['room']}
    if result.get('already'):
        resp['already'] = True
    return jsonify(resp)


@app.route('/api/rooms/<room_id>/start', methods=['POST'])
def api_start_room(room_id):
    try:
        room = rooms.start_game(room_id)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/state', methods=['GET'])
def api_room_state(room_id):
    player_id = request.args.get('player_id')
    try:
        state = rooms.get_room_state(room_id, player_id)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    return jsonify(state)


@app.route('/api/rooms/<room_id>/rules', methods=['GET'])
def api_get_room_rules(room_id):
    room = rooms.ROOMS.get(room_id)
    if not room:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    return jsonify({'rules': room.get('rules', {})})


@app.route('/api/rooms/<room_id>/rules', methods=['PATCH'])
def api_patch_room_rules(room_id):
    room = rooms.ROOMS.get(room_id)
    if not room:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    data = request.get_json() or {}
    # allowed keys and expected type: boolean
    allowed_keys = {'spade3_over_joker', 'spade3_single_only', 'block_8_after_2', 'auto_pass_when_no_joker_vs_2'}
    rules = room.setdefault('rules', {})
    updates = {}
    for k, v in data.items():
        if k not in allowed_keys:
            return jsonify({'error': f'無効なルールキー: {k}'}), 400
        # coerce to boolean if possible
        if isinstance(v, bool):
            updates[k] = v
        else:
            if isinstance(v, (int, float)) and v in (0, 1):
                updates[k] = bool(v)
            elif isinstance(v, str):
                lv = v.strip().lower()
                if lv in ('true', '1', 'yes', 'on', 'enabled'):
                    updates[k] = True
                elif lv in ('false', '0', 'no', 'off', 'disabled'):
                    updates[k] = False
                else:
                    return jsonify({'error': f'ルール値が無効です: {k}'}), 400
            else:
                return jsonify({'error': f'ルール値が無効です: {k}'}), 400
    rules.update(updates)
    return jsonify({'rules': rules})


@app.route('/api/rooms/<room_id>/events')
def api_room_events(room_id):
    # Simple SSE endpoint. Clients should keep connection open.
    def gen():
        # initial handshake
        yield 'retry: 2000\n\n'
        while True:
            events = rooms.pop_events(room_id)
            if events:
                for ev in events:
                    # Use a safe serializer that handles unicode, datetimes and
                    # falls back to a minimal payload if serialization fails.
                    data = _safe_json_dumps(ev.get('payload'))
                    # SSE format: event: <type>\ndata: <json>\n\n
                    yield f"event: {ev['type']}\n"
                    for line in data.splitlines():
                        yield f"data: {line}\n"
                    yield "\n"
            time.sleep(0.5)
    return Response(gen(), mimetype='text/event-stream')


def _safe_json_dumps(obj):
    """Safe JSON serialization for SSE payloads.

    - Convert datetimes to ISO strings.
    - Fall back to str() for unknown objects.
    - If serialization fails, return a minimal error JSON as fallback.
    - keep unicode characters (ensure_ascii=False).
    """
    def default(o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        try:
            return str(o)
        except Exception:
            return None

    try:
        return json.dumps(obj, ensure_ascii=False, default=default)
    except Exception as e:
        logging.exception('Failed to JSON serialize SSE payload')
        try:
            fallback = {'error': 'シリアライズエラー', 'msg': str(e)}
            return json.dumps(fallback, ensure_ascii=False)
        except Exception:
            return '{"error": "serialize_failed"}'


def _translate_error(msg: str) -> str:
    """Translate known English runtime error messages from rooms into Japanese for client display.
    If the message already contains non-ascii characters (likely already Japanese), return as-is.
    """
    try:
        # If message likely contains Japanese (non-ascii), return it unchanged
        if any(ord(c) > 127 for c in (msg or "")):
            return msg
    except Exception:
        pass

    mapping = {
        'not your turn': 'あなたの番ではありません',
        'card not in hand': '指定されたカードは手札にありません',
        'invalid combination of cards': '無効なカードの組み合わせです',
        'must play same type as center': '場と同じ種類の役を出してください',
        'must play same number of cards as center': '場と同じ枚数のカードを出してください',
        'must play same number of cards as center (straight length)': '場と同じ長さのストレートを出してください',
        'played rank is not higher than center': '場のカードより強いカードを出してください',
        'played straight is not higher than center': '場のストレートより強いストレートを出してください',
        'no discard allowed': '捨てる権利がありません',
        'game not started': 'ゲームが開始されていません',
        'no swap allowed': '交換は許可されていません',
        'give_card not in hand': '渡すカードが手札にありません',
        'take_card not in target hand': '取得対象の手札にそのカードはありません',
        'can only give after you played a 7': '7を出した後にのみカードを渡せます',
        'invalid direction': '方向が無効です',
        'no take allowed': '取得は許可されていません',
        'no give pending for player': 'カードを渡す権利がありません',
    }

    if msg in mapping:
        return mapping[msg]

    # special-case patterns
    # expected N card(s) to give
    m = re.search(r'expected\s+(\d+)', msg)
    if m and 'to give' in msg:
        n = m.group(1)
        return f'{n}枚のカードを指定する必要があります'

    # fallback: return original message
    return msg


def _translate_shiritori_error(msg: str) -> str:
    """Translate common shiritori module error messages to Japanese for clients."""
    try:
        if any(ord(c) > 127 for c in (msg or "")):
            return msg
    except Exception:
        pass

    mapping = {
        'not your turn': 'あなたの番ではありません',
        'empty word': '単語が入力されていません',
        'invalid word': '無効な単語です',
        'word does not start with required kana': '必要な文字（仮名）で始まっていません',
        'word already used': 'その単語はすでに使用されています',
        'game not started': 'ゲームが開始されていません',
        'need at least 2 players': 'プレイヤーが2人必要です',
        'room full': 'ルームが満員です',
        'game already started': 'ゲームは既に開始されています',
        'player not in room': 'プレイヤーがルームに参加していません',
    }

    if msg in mapping:
        return mapping[msg]

    # fallback: return original message
    return msg


@app.route('/api/rooms/<room_id>/next_round', methods=['POST'])
def api_next_round(room_id):
    # Reset hands and start a new round keeping players list intact
    try:
        # persist previous round results if available
        room_obj = rooms.ROOMS.get(room_id)
        if room_obj and hasattr(rooms, 'ROOMS') and room_obj.get('finished'):
            try:
                if rooms.db:
                    rooms.db.record_round_results(room_id, room_obj.get('finished'))
            except Exception:
                pass
        room = rooms.start_game(room_id)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/play', methods=['POST'])
def api_play(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    cards = data.get('cards') or data.get('card')
    target_rank = data.get('target_rank')
    if not player_id or not cards:
        return jsonify({'error': 'player_idまたはカードが指定されていません'}), 400
    try:
        room = rooms.play_card(room_id, player_id, cards, target_rank=target_rank)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/give', methods=['POST'])
def api_give(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    card = data.get('card')
    direction = data.get('direction')
    if not player_id or not card:
        return jsonify({'error': 'player_idまたはカードが指定されていません'}), 400
    try:
        room = rooms.give_card(room_id, player_id, card, direction=direction)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/discard', methods=['POST'])
def api_discard(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    card = data.get('card')
    if not player_id or not card:
        return jsonify({'error': 'player_idまたはカードが指定されていません'}), 400
    try:
        room = rooms.discard_card(room_id, player_id, card)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/swap', methods=['POST'])
def api_swap(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    target_player = data.get('target_player')
    give_card = data.get('give_card')
    take_card = data.get('take_card')
    if not player_id or not target_player or not give_card or not take_card:
        return jsonify({'error': 'パラメータが不足しています'}), 400
    try:
        room = rooms.swap_cards(room_id, player_id, target_player, give_card, take_card)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/take', methods=['POST'])
def api_take(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    target_player = data.get('target_player')
    take_card = data.get('take_card')
    if not player_id or not target_player or not take_card:
        return jsonify({'error': 'パラメータが不足しています'}), 400
    try:
        room = rooms.take_card(room_id, player_id, target_player, take_card)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/submit_give', methods=['POST'])
def api_submit_give(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    cards = data.get('cards')
    if not player_id or not cards:
        return jsonify({'error': 'パラメータが不足しています'}), 400
    try:
        room = rooms.submit_give(room_id, player_id, cards)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/message', methods=['POST'])
def api_message(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    text = data.get('text')
    if not player_id or text is None:
        return jsonify({'error': 'player_idまたはメッセージが指定されていません'}), 400
    try:
        msg = rooms.add_message(room_id, player_id, text)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    return jsonify({'message': msg})


@app.route('/api/recommended_rooms', methods=['GET'])
def api_recommended_rooms():
    """Return recommended rooms to join. Query params:
    - external: optional comma-separated list of other server base URLs to query (e.g. https://example.com)
    Response includes local rooms with bot slots plus any reachable external results under 'external_results'.
    """
    external = request.args.get('external')
    results = {'local': rooms.find_local_rooms_with_bot_slots(), 'external_results': []}
    if external:
        urls = [u.strip() for u in external.split(',') if u.strip()]
        for base in urls:
            try:
                resp = requests.get(f"{base.rstrip('/')}/api/recommended_rooms_local", timeout=2)
                if resp.status_code == 200:
                    results['external_results'].append({'base': base, 'data': resp.json()})
            except Exception:
                # just skip unreachable external server
                continue
    return jsonify(results)


@app.route('/api/rooms/<room_id>/join_bot_slot', methods=['POST'])
def api_join_bot_slot(room_id):
    data = request.get_json() or {}
    bot_id = data.get('bot_id')
    name = data.get('name') or 'Player'
    if not bot_id:
        return jsonify({'error': 'bot_idが指定されていません'}), 400
    try:
        res = rooms.join_bot_slot(room_id, bot_id, name)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except ValueError:
        return jsonify({'error': '指定したボットスロットは存在しません'}), 400
    return jsonify({'room': res['room'], 'player_id': res['player_id']})



@app.route('/api/rooms/<room_id>/pass', methods=['POST'])
def api_pass(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    if not player_id:
        return jsonify({'error': 'player_idが指定されていません'}), 400
    try:
        room = rooms.pass_turn(room_id, player_id)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'room': room})


@app.route('/api/rooms/<room_id>/bots/<bot_id>', methods=['PATCH'])
def api_update_bot(room_id, bot_id):
    data = request.get_json() or {}
    display_name = data.get('display_name')
    tone = data.get('tone')
    difficulty = data.get('difficulty')
    room = rooms.ROOMS.get(room_id)
    if not room:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    bot = next((p for p in room['players'] if p['id'] == bot_id and p.get('is_bot')), None)
    if not bot:
        return jsonify({'error': 'ボットが見つかりません'}), 404
    # validate inputs (simple)
    if display_name is not None:
        bot['display_name'] = str(display_name)[:32]
    if tone is not None:
        if tone not in ['真面目くん', '不思議ちゃん', 'いじわる']:
            return jsonify({'error': '無効なトーンです'}), 400
        bot['tone'] = tone
    if difficulty is not None:
        if difficulty not in ['弱い', 'ふつう', '強い']:
            return jsonify({'error': '無効な難易度です'}), 400
        bot['difficulty'] = difficulty
    return jsonify({'bot': bot})


@app.route('/api/rooms/<room_id>/bots', methods=['POST'])
def api_add_bot(room_id):
    data = request.get_json() or {}
    display_name = data.get('display_name')
    tone = data.get('tone') or 'いじわる'
    difficulty = data.get('difficulty') or 'ふつう'
    try:
        bot = rooms.add_bot(room_id, display_name=display_name, tone=tone, difficulty=difficulty)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'bot': bot})


@app.route('/api/rooms/<room_id>/bots/<bot_id>', methods=['DELETE'])
def api_remove_bot(room_id, bot_id):
    try:
        ok = rooms.remove_bot(room_id, bot_id)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 400
    if not ok:
        return jsonify({'error': 'ボットが削除されませんでした'}), 400
    return jsonify({'removed': True})


@app.route('/api/rooms/<room_id>/takeover/<player_id>', methods=['POST'])
def api_takeover_player(room_id, player_id):
    try:
        player = rooms.takeover_for_player(room_id, player_id)
    except KeyError:
        return jsonify({'error': 'ルームまたはプレイヤーが見つかりません'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'player': player})


@app.route('/api/rooms/<room_id>/takeover/<player_id>', methods=['DELETE'])
def api_release_takeover(room_id, player_id):
    try:
        player = rooms.release_takeover(room_id, player_id)
    except KeyError:
        return jsonify({'error': 'ルームまたはプレイヤーが見つかりません'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'player': player})


@app.route('/game/babanuki')
def babanuki():
    return render_template('babanuki.html')


@app.route('/game/babanuki/join/<room_id>')
def babanuki_join(room_id):
    # Redirect to the canonical babanuki page with ?room=... so client-side auto-join logic triggers.
    from flask import redirect, url_for
    target = url_for('babanuki') + '?room=' + room_id
    return redirect(target)


@app.route('/api/babanuki/simulate', methods=['POST'])
def api_babanuki_simulate():
    data = request.get_json() or {}
    names = data.get('names') or []
    # fallback: if no names provided, create three bots
    if not names:
        names = ['Player1', 'Player2', 'Player3']
    # If any provided name looks like a human (not a BOT###), refuse full-automatic simulate
    # Bot names produced by the server typically look like BOT1, BOT2, ...
    human_present = any(not re.match(r'^(?:BOT|bot)\d+$', n) for n in names)
    if human_present:
        return jsonify({'error': '人間プレイヤーが含まれているため全自動シミュレーションは許可されていません。インタラクティブな Socket.IO モードを利用してください。'}), 400
    try:
        import babanuki
        res = babanuki.simulate(names)
    except Exception as e:
        # translate common error messages to Japanese for client display
        return jsonify({'error': _translate_error(str(e))}), 500
    return jsonify(res)


@app.route('/api/babanuki/stream', methods=['POST'])
def api_babanuki_stream():
    data = request.get_json() or {}
    names = data.get('names') or []
    if not names:
        names = ['Player1', 'Player2', 'Player3']
    # Prevent full-automatic streaming when any non-bot (human) name is present.
    # Bot names from server are like BOT1/BOT2 — treat anything else as human.
    human_present = any(not re.match(r'^(?:BOT|bot)\d+$', n) for n in names)
    if human_present:
        return jsonify({'error': '人間プレイヤーが含まれているため全自動プレイは許可されていません。Socket.IO を使ったインタラクティブモードを使用してください。'}), 400
    bot_difficulties = data.get('bot_difficulties') or {}
    thinking_seconds = int(data.get('thinking_seconds') or 5)

    def gen():
        # initial handshake
        yield 'retry: 2000\n\n'
        try:
            import babanuki
            for ev in babanuki.simulate_stream(names, bot_difficulties=bot_difficulties, thinking_seconds=thinking_seconds):
                # each ev is a dict with type
                etype = ev.get('type', 'log')
                data = _safe_json_dumps(ev)
                yield f"event: {etype}\n"
                for line in data.splitlines():
                    yield f"data: {line}\n"
                yield "\n"
        except Exception as e:
            err = {'type': 'error', 'msg': _translate_error(str(e))}
            data = _safe_json_dumps(err)
            yield f"event: error\n"
            for line in data.splitlines():
                yield f"data: {line}\n"
            yield "\n"

    return Response(gen(), mimetype='text/event-stream')


@app.route('/game/shiritori')
def shiritori_page():
    return render_template('shiritori.html')


@app.route('/api/shiritori', methods=['POST'])
def api_shi_create():
    data = request.get_json() or {}
    name = data.get('name') or 'Player'
    # create room via shiritori module
    res = shiritori.create_room(name)
    room = res['room']
    player_id = res['player_id']

    # If only one human player, automatically add a bot (simple AI) by joining and marking as bot
    try:
        if len(room.get('players', [])) == 1:
            # choose a bot name from shared pool if available
            bot_name = data.get('auto_bot_name') or (rooms.pick_bot_display_name(set(p.get('name') for p in room.get('players', []))))
            bot_res = shiritori.join_room(room['id'], bot_name)
            # mark last joined player as bot for UI
            bot_player_id = bot_res['player_id']
            for p in room.get('players', []):
                if p['id'] == bot_player_id:
                    p['is_bot'] = True
                    break
    except Exception:
        # if bot addition fails, ignore and return created room anyway
        pass

    return jsonify({'room_id': room['id'], 'player_id': player_id, 'room': room})


@app.route('/api/shiritori/<room_id>/join', methods=['POST'])
def api_shi_join(room_id):
    data = request.get_json() or {}
    name = data.get('name') or 'Player'
    try:
        res = shiritori.join_room(room_id, name)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_shiritori_error(str(e))}), 400
    return jsonify({'room_id': room_id, 'player_id': res['player_id'], 'room': res['room']})


@app.route('/api/shiritori/<room_id>/start', methods=['POST'])
def api_shi_start(room_id):
    try:
        room = shiritori.start_game(room_id)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_shiritori_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/shiritori/<room_id>/play', methods=['POST'])
def api_shi_play(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    word = data.get('word')
    if not player_id or not word:
        return jsonify({'error': 'player_idまたはwordが指定されていません'}), 400
    try:
        room = shiritori.play_word(room_id, player_id, word)
    except KeyError:
        return jsonify({'error': 'ルームまたはプレイヤーが見つかりません'}), 404
    except RuntimeError as e:
        return jsonify({'error': _translate_shiritori_error(str(e))}), 400
    return jsonify({'room': room})


@app.route('/api/shiritori/<room_id>/state', methods=['GET'])
def api_shi_state(room_id):
    player_id = request.args.get('player_id')
    try:
        state = shiritori.get_room_state(room_id, player_id)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    return jsonify(state)


@app.route('/api/shiritori/<room_id>/message', methods=['POST'])
def api_shi_message(room_id):
    data = request.get_json() or {}
    player_id = data.get('player_id')
    text = data.get('text')
    if not player_id or text is None:
        return jsonify({'error': 'player_idまたはメッセージが指定されていません'}), 400
    try:
        msg = shiritori.add_message(room_id, player_id, text)
    except KeyError:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    return jsonify({'message': msg})


@app.route('/api/shiritori/<room_id>/events')
def api_shi_events(room_id):
    def gen():
        yield 'retry: 1500\n\n'
        while True:
            events = shiritori.pop_events(room_id)
            if events:
                for ev in events:
                    data = _safe_json_dumps(ev.get('payload'))
                    yield f"event: {ev['type']}\n"
                    for line in data.splitlines():
                        yield f"data: {line}\n"
                    yield "\n"
            time.sleep(0.5)
    return Response(gen(), mimetype='text/event-stream')


@app.route('/quiz')
def quiz():
    return render_template('quiz.html')

# Netlify Functionsで動かすためのおまじない
def handler(event, context):
    try:
        import awsgi
    except Exception:
        # awsgi is optional in local/dev environments. Return a minimal response.
        return {
            'statusCode': 500,
            'body': 'awsgi not installed in this environment'
        }
    return awsgi.response(app, event, context)


# CLI helper: initialize the sqlite database using db.init_db
@app.cli.command('init-db')
@click.option('--schema', default=None, help='Path to SQL schema file (default: data.sql)')
def init_db_cli(schema):
    """Initialize the application's SQLite database using the schema SQL file.

    Example:
        flask --app api init-db
        flask --app api init-db --schema ./my_schema.sql
    """
    try:
        from db import init_db
    except Exception as e:
        click.echo(f'Failed to import db module: {e}', err=True)
        raise
    try:
        init_db(schema)
        click.echo('Database initialized.')
    except Exception as e:
        click.echo(f'Failed to initialize database: {e}', err=True)
        raise


### Socket.IO handlers for babanuki
@socketio.on('baba:create')
def on_baba_create(data):
    name = data.get('name') or 'Player'
    room_id = str(uuid.uuid4())
    pid = 'p1'
    player = {'id': pid, 'name': name, 'sid': request.sid, 'is_bot': False}
    BABA_ROOMS[room_id] = {'players': [player], 'hands': {}, 'alive': [], 'turn_idx': 0, 'running': False, 'pending': None, 'bot_difficulties': {}}
    sio_join_room(room_id)
    socketio.emit('baba:created', {'room_id': room_id, 'player': player}, room=request.sid)


@socketio.on('baba:join')
def on_baba_join(data):
    room_id = data.get('room_id')
    name = data.get('name') or 'Player'
    room = BABA_ROOMS.get(room_id)
    if not room:
        socketio.emit('baba:error', {'msg': 'ルームが見つかりません'}, room=request.sid)
        return
    pid = f'p{len(room['"'"'players'"'"'])+1}'
    player = {'id': pid, 'name': name, 'sid': request.sid, 'is_bot': False}
    room['players'].append(player)
    sio_join_room(room_id)
    socketio.emit('baba:joined', {'room_id': room_id, 'player': player}, room=room_id)


def _emit_state(room_id):
    room = BABA_ROOMS.get(room_id)
    if not room:
        return
    # build state similar to simulate_stream
    players_state = []
    for p in room['players']:
        pid = p['id']
        players_state.append({'id': pid, 'name': p.get('display_name') or p.get('name'), 'display_name': p.get('display_name') or p.get('name'), 'is_bot': p.get('is_bot', False), 'count': len(room['hands'].get(pid, [])), 'hand': []})
    socketio.emit('baba:state', {'players': players_state, 'turn': room['turn_idx']}, room=room_id)


def _check_for_winner(room_id):
    """Check if any player in the room has an empty hand and emit a 'baba:win' event.

    This is called after actions that can reduce a player's hand to zero so clients
    can display an immediate victory message like “○○さんが勝利しました”.
    """
    room = BABA_ROOMS.get(room_id)
    if not room:
        return False
    winners = []
    for p in room.get('players', []):
        pid = p.get('id')
        if len(room.get('hands', {}).get(pid, [])) == 0:
            # prefer display_name if present
            winners.append(p.get('display_name') or p.get('name'))
    if winners:
        # emit a win event for the room (clients may show toast/log once per winner)
        for w in winners:
            try:
                socketio.emit('baba:win', {'winner': w, 'room_id': room_id}, room=room_id)
            except Exception:
                # don't let emission failure break game loop
                pass
        return True
    return False


@socketio.on('baba:start')
def on_baba_start(data):
    room_id = data.get('room_id')
    thinking_seconds = int(data.get('thinking_seconds') or 5)
    room = BABA_ROOMS.get(room_id)
    if not room:
        socketio.emit('baba:error', {'msg': 'ルームが見つかりません'}, room=request.sid)
        return
    # ensure at least 3 players: add bots
    bot_idx = 1
    while len(room['players']) < 3:
        bid = f'bot{bot_idx}'
        # pick display name avoiding duplicates
        used = set(p.get('name') for p in room['players']) | set(p.get('display_name') for p in room['players'])
        display = rooms.pick_bot_display_name(used)
        room['players'].append({'id': bid, 'name': f'BOT{bot_idx}', 'sid': None, 'is_bot': True, 'display_name': display})
        bot_idx += 1

    # deal
    import babanuki as bb
    deck = bb._make_deck()
    random.shuffle(deck)
    hands = {p['id']: [] for p in room['players']}
    pid_list = [p['id'] for p in room['players']]
    i = 0
    for c in deck:
        hands[pid_list[i % len(pid_list)]].append(c)
        i += 1
    # remove pairs
    for pid in pid_list:
        hands[pid] = bb._remove_pairs(hands[pid])

    room['hands'] = hands
    room['alive'] = [p for p in pid_list if len(hands.get(p, [])) > 0]
    room['turn_idx'] = 0
    room['running'] = True

    # broadcast initial state
    _emit_state(room_id)
    socketio.emit('baba:log', {'text': 'ゲームを開始しました'}, room=room_id)

    # start background thread to run the turn loop
    def run_loop():
        cap = 10000
        iter_count = 0
        while room['running'] and len(room['alive']) > 1 and iter_count < cap:
            iter_count += 1
            pid = room['alive'][room['turn_idx'] % len(room['alive'])]
            # determine target
            next_idx = (room['turn_idx'] + 1) % len(room['alive'])
            target_pid = room['alive'][next_idx]
            # if bot's turn, do thinking then draw
            cur_player = next((p for p in room['players'] if p['id'] == pid), None)
            is_bot = bool(cur_player and cur_player.get('is_bot'))
            if is_bot:
                # thinking ticks
                for s in range(thinking_seconds, 0, -1):
                    socketio.emit('baba:thinking', {'player': cur_player['name'], 'seconds': s}, room=room_id)
                    time.sleep(1)
                # choose card according to simple logic
                cand = list(room['hands'][target_pid])
                chosen = random.choice(cand)
                room['hands'][target_pid].remove(chosen)
                # handle pairing
                pair = next((c for c in list(room['hands'][pid]) if c['rank'] == chosen['rank'] and c['rank'] != 'JOKER'), None)
                if pair:
                    room['hands'][pid].remove(pair)
                    socketio.emit('baba:log', {'text': f"{cur_player['name']} は {pair['name']} と {chosen['name']} の組を作り捨てました"}, room=room_id)
                else:
                    room['hands'][pid].append(chosen)
                socketio.emit('baba:log', {'text': f"{cur_player['name']} は {target_pid} から 1枚引きました ({chosen['name']})"}, room=room_id)
            else:
                # human: set pending and wait for client to send baba:draw
                room['pending'] = {'player': pid, 'target': target_pid}
                # find target player display name for client-side highlighting
                target_player_obj = next((p for p in room['players'] if p['id'] == target_pid), None)
                target_name = (target_player_obj.get('display_name') or target_player_obj.get('name')) if target_player_obj else target_pid
                socketio.emit('baba:request_draw', {'player': cur_player['name'], 'target_count': len(room['hands'][target_pid]), 'target_name': target_name}, room=room_id)
                # wait until pending is cleared by client's action
                wait_count = 0
                while room.get('pending') and wait_count < 300:
                    time.sleep(0.5)
                    wait_count += 1

            # cleanup empty hands
            for p in list(room['alive']):
                if len(room['hands'].get(p, [])) == 0:
                    try:
                        room['alive'].remove(p)
                        socketio.emit('baba:log', {'text': f"{p} は手札がなくなり上がりました"}, room=room_id)
                        # Emit immediate win event for UI when someone empties their hand
                        try:
                            _check_for_winner(room_id)
                        except Exception:
                            pass
                    except ValueError:
                        pass

            # advance turn
            if room['turn_idx'] < len(room['alive']):
                room['turn_idx'] = (room['turn_idx'] + 1) % max(1, len(room['alive']))

            _emit_state(room_id)

        # finish
        final_hands = {p['name']: [c['name'] for c in room['hands'].get(p['id'], [])] for p in room['players']}
        loser = None
        for p in room['players']:
            for c in room['hands'].get(p['id'], []):
                if c['rank'] == 'JOKER':
                    loser = p['name']
                    break
            if loser:
                break
        if not loser and room['alive']:
            loser = room['alive'][0]
        socketio.emit('baba:finish', {'final_hands': final_hands, 'loser': loser}, room=room_id)

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()


@socketio.on('baba:setup')
def on_baba_setup(data):
    """Prepare the room: deal cards and remove initial pairs, but DO NOT start the turn loop.

    Emits 'baba:state' and initial 'baba:log' messages. Useful for auto-setup then manual play.
    """
    room_id = data.get('room_id')
    room = BABA_ROOMS.get(room_id)
    if not room:
        socketio.emit('baba:error', {'msg': 'ルームが見つかりません'}, room=request.sid)
        return
    # ensure at least 3 players by adding bots
    bot_idx = 1
    while len(room['players']) < 3:
        bid = f'bot{bot_idx}'
        used = set(p.get('name') for p in room['players']) | set(p.get('display_name') for p in room['players'])
        display = rooms.pick_bot_display_name(used)
        room['players'].append({'id': bid, 'name': f'BOT{bot_idx}', 'sid': None, 'is_bot': True, 'display_name': display})
        bot_idx += 1

    # deal and initial pair removal (reuse babanuki helpers)
    import babanuki as bb
    deck = bb._make_deck()
    random.shuffle(deck)
    hands = {p['id']: [] for p in room['players']}
    pid_list = [p['id'] for p in room['players']]
    i = 0
    for c in deck:
        hands[pid_list[i % len(pid_list)]].append(c)
        i += 1
    # initial pair removal
    for pid in pid_list:
        before = len(hands[pid])
        hands[pid] = bb._remove_pairs(hands[pid])
        removed = before - len(hands[pid])
        if removed:
            player_obj = next((p for p in room['players'] if p['id'] == pid), None)
            player_name = (player_obj.get('display_name') or player_obj.get('name')) if player_obj else pid
            socketio.emit('baba:log', {'text': f"{player_name} は初期の{removed}枚の組を捨てました"}, room=room_id)

    room['hands'] = hands
    room['alive'] = [p for p in pid_list if len(hands.get(p, [])) > 0]
    room['turn_idx'] = 0
    room['running'] = False

    # emit state
    players_state = []
    for p in room['players']:
        pid = p['id']
        players_state.append({'id': pid, 'name': p.get('display_name') or p.get('name'), 'display_name': p.get('display_name') or p.get('name'), 'is_bot': p.get('is_bot', False), 'count': len(room['hands'].get(pid, [])), 'hand': []})
    socketio.emit('baba:state', {'players': players_state, 'turn': room['turn_idx']}, room=room_id)


@socketio.on('baba:add_bots')
def on_baba_add_bots(data):
    """Add bot players to an existing BABA_ROOMS room until it reaches target count.

    data: {room_id: str, target: int}
    Emits baba:log and baba:state to the room.
    """
    room_id = data.get('room_id')
    target = int(data.get('target') or 3)
    room = BABA_ROOMS.get(room_id)
    if not room:
        socketio.emit('baba:error', {'msg': 'ルームが見つかりません'}, room=request.sid)
        return
    # find existing bot index start
    existing_ids = set(p['id'] for p in room['players'])
    bot_idx = 1
    # pick a start index larger than existing bot ids if any
    while f'bot{bot_idx}' in existing_ids:
        bot_idx += 1

    while len(room['players']) < target:
        bid = f'bot{bot_idx}'
        used = set(p.get('name') for p in room['players']) | set(p.get('display_name') for p in room['players'])
        try:
            display = rooms.pick_bot_display_name(used)
        except Exception:
            display = f'Bot {bot_idx}'
        room['players'].append({'id': bid, 'name': f'BOT{bot_idx}', 'sid': None, 'is_bot': True, 'display_name': display})
        socketio.emit('baba:log', {'text': f"ボット {display} を参加させました（{bid}）"}, room=room_id)
        bot_idx += 1

    # emit updated state
    players_state = []
    for p in room['players']:
        pid = p['id']
        players_state.append({'id': pid, 'name': p.get('display_name') or p.get('name'), 'display_name': p.get('display_name') or p.get('name'), 'is_bot': p.get('is_bot', False), 'count': len(room.get('hands', {}).get(pid, [])), 'hand': []})
    socketio.emit('baba:state', {'players': players_state, 'turn': room.get('turn_idx', 0)}, room=room_id)


@app.route('/api/rooms/<room_id>/setup', methods=['POST'])
def api_setup_room(room_id):
    room = BABA_ROOMS.get(room_id)
    if not room:
        return jsonify({'error': 'ルームが見つかりません'}), 404
    # ensure at least 3 players
    bot_idx = 1
    while len(room['players']) < 3:
        bid = f'bot{bot_idx}'
        used = set(p.get('name') for p in room['players']) | set(p.get('display_name') for p in room['players'])
        display = rooms.pick_bot_display_name(used)
        room['players'].append({'id': bid, 'name': f'BOT{bot_idx}', 'sid': None, 'is_bot': True, 'display_name': display})
        bot_idx += 1
    try:
        import babanuki as bb
        deck = bb._make_deck()
        random.shuffle(deck)
        hands = {p['id']: [] for p in room['players']}
        pid_list = [p['id'] for p in room['players']]
        i = 0
        for c in deck:
            hands[pid_list[i % len(pid_list)]].append(c)
            i += 1
        for pid in pid_list:
            before = len(hands[pid])
            hands[pid] = bb._remove_pairs(hands[pid])
        room['hands'] = hands
        room['alive'] = [p for p in pid_list if len(hands.get(p, [])) > 0]
        room['turn_idx'] = 0
        room['running'] = False
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'room': room})


@socketio.on('baba:draw')
def on_baba_draw(data):
    room_id = data.get('room_id')
    room = BABA_ROOMS.get(room_id)
    if not room or not room.get('pending'):
        socketio.emit('baba:error', {'msg': '描画できません'}, room=request.sid)
        return
    pending = room['pending']
    pid = pending['player']
    target_pid = pending['target']
    # simulate draw
    if not room['hands'].get(target_pid):
        socketio.emit('baba:error', {'msg': '対象にカードがありません'}, room=request.sid)
        room['pending'] = None
        return
    chosen = random.choice(room['hands'][target_pid])
    room['hands'][target_pid].remove(chosen)
    pair = next((c for c in list(room['hands'][pid]) if c['rank'] == chosen['rank'] and c['rank'] != 'JOKER'), None)
    if pair:
        room['hands'][pid].remove(pair)
        socketio.emit('baba:log', {'text': f"{pid} は {pair['name']} と {chosen['name']} の組を作り捨てました"}, room=room_id)
    else:
        room['hands'][pid].append(chosen)
    socketio.emit('baba:log', {'text': f"{pid} は {target_pid} から 1枚引きました ({chosen['name']})"}, room=room_id)
    room['pending'] = None
    _emit_state(room_id)
    # After changing hands, check whether anyone emptied their hand -> victory
    try:
        _check_for_winner(room_id)
    except Exception:
        pass


# Note: legacy generic game handlers (next page, start_game) removed.
# babanuki-specific Socket.IO handlers (baba:create/join/start/setup/add_bots/draw) are authoritative.


if __name__ == '__main__':
    # ローカルでのデバッグ実行用 (Windows / Cloud Shell での確認に便利)
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)