import uuid
import random
import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List
import threading
import smtplib
from email.message import EmailMessage
import os as _os
try:
    import db
except Exception:
    db = None
try:
    # prefer the modern psycopg (psycopg) if available, otherwise fall back to psycopg2
    try:
        import psycopg  # type: ignore
        _psycopg = psycopg
    except Exception:
        import psycopg2 as _psycopg  # type: ignore
except Exception:
    _psycopg = None



QA_PAIRS: List[Dict[str, str]] = []
try:
    # QA.jsonのパスを絶対パス基準で解決するように修正
    # __file__ は functions/rooms.py を指すため、プロジェクトルートに戻る必要がある
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    qa_path = os.path.join(base_dir, 'static', 'QA.json')
    if os.path.exists(qa_path):
        with open(qa_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    QA_PAIRS.append({'q': str(k), 'a': str(v)})
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        if 'q' in item and 'a' in item:
                            QA_PAIRS.append({'q': str(item['q']), 'a': str(item['a'])})
                        else:
                            for k, v in item.items():
                                QA_PAIRS.append({'q': str(k), 'a': str(v)})
except Exception:
    QA_PAIRS = []


# BOT_QA: structured list for quick selection by intent/tone
BOT_QA: List[Dict[str, str]] = []
try:
    # Prefer a top-level QA.json if present; already loaded into QA_PAIRS above
    if QA_PAIRS:
        BOT_QA = list(QA_PAIRS)
    else:
        # try to load alternate path inside static if present
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        alt = os.path.join(base_dir, 'static', 'QA.json')
        if os.path.exists(alt):
            with open(alt, 'r', encoding='utf-8') as af:
                data = json.load(af)
                if isinstance(data, dict):
                    for k, v in data.items():
                        BOT_QA.append({'q': str(k), 'a': str(v)})
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'q' in item and 'a' in item:
                            BOT_QA.append({'q': str(item['q']), 'a': str(item['a'])})
except Exception:
    BOT_QA = []


def pick_bot_reply(topic: str = None, tone: str = None) -> str:
    """Pick a short reply string for bots.

    - If BOT_QA contains entries whose question (q) is a substring of topic, prefer those answers.
    - Otherwise prefer a canned phrase based on tone ('いじわる','真面目くん', etc.).
    - Always return a short safe string.
    """
    try:
        t = (topic or '').lower()
        candidates = []
        for qa in BOT_QA:
            q = (qa.get('q') or '').lower()
            a = qa.get('a')
            if not q or not a:
                continue
            if q in t:
                candidates.append(str(a))
        if candidates:
            return random.choice(candidates)
    except Exception:
        pass

    # Fallback canned replies by tone
    tone = (tone or '').lower()
    if 'いじ' in tone or tone == 'いじわる':
        pool = ['ふふ、そうくるか。', 'またそんな手を出すの？', '残念だったねー']
    elif '真面目' in tone or tone == '真面目くん':
        pool = ['了解しました。', '分かりました。', '承知しました。']
    else:
        pool = ['うん、いいね。', 'やった！', '次はあなたの番だよ。']
    try:
        return random.choice(pool)
    except Exception:
        return pool[0]


# Load bot display name pool from static/name.json (if present). Each entry may be an object with 'name' field or a plain string.
BOT_NAME_POOL: List[str] = []
try:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _name_path = os.path.join(base_dir, 'static', 'name.json')
    if os.path.exists(_name_path):
        with open(_name_path, 'r', encoding='utf-8') as _nf:
            _ndata = json.load(_nf)
            if isinstance(_ndata, list):
                for it in _ndata:
                    if isinstance(it, dict) and 'name' in it:
                        BOT_NAME_POOL.append(str(it['name']))
                    elif isinstance(it, str):
                        BOT_NAME_POOL.append(it)
except Exception:
    BOT_NAME_POOL = []


def pick_bot_display_name(used_names: set = None) -> str:
    """Pick a display name for a bot from BOT_NAME_POOL avoiding any names in used_names.

    If no pool is available or all names are exhausted, fall back to a default Japanese name.
    """
    used = set(used_names or set())
    try:
        candidates = [n for n in BOT_NAME_POOL if n not in used]
        if candidates:
            return random.choice(candidates)
    except Exception:
        pass
    # fallback
    return 'イジヒコ'


def _send_contact_notification(player: Dict[str, Any], room_id: str, reason: str = 'takeover'):
    """Send a simple notification to player's contact_email if configured.
    Looks for SMTP env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM.
    If not configured, write an entry to 'notifications.log' as a fallback.
    reason: 'takeover' or 'released'
    """
    try:
        contact_email = player.get('contact_email')
        contact_phone = player.get('contact_phone')
        name = player.get('name') or player.get('display_name') or 'Player'
        if contact_email:
            host = _os.environ.get('SMTP_HOST')
            port = int(_os.environ.get('SMTP_PORT', '25'))
            user = _os.environ.get('SMTP_USER')
            pwd = _os.environ.get('SMTP_PASS')
            frm = _os.environ.get('EMAIL_FROM') or (user or 'no-reply@example.com')
            subject = ''
            body = ''
            if reason == 'takeover':
                subject = f'ゲーム代行開始のお知らせ — ルーム {room_id}'
                body = f'{name} 様\n\n大富豪のプレイ中に接続が途切れたため、代行ボットがあなたの代わりにプレイしています。\nルームID: {room_id}\n\n再接続すると自動的に操作権が戻ります。'
            else:
                subject = f'ゲーム操作の復帰のお知らせ — ルーム {room_id}'
                body = f'{name} 様\n\n接続が復帰したため、ゲーム操作をあなたに戻しました。\nルームID: {room_id}\n\n引き続きゲームをお楽しみください。'
            if host and user and pwd:
                msg = EmailMessage()
                msg['Subject'] = subject
                msg['From'] = frm
                msg['To'] = contact_email
                msg.set_content(body)
                try:
                    with smtplib.SMTP(host, port, timeout=10) as s:
                        s.starttls()
                        s.login(user, pwd)
                        s.send_message(msg)
                except Exception:
                    # Netlifyのファイルシステムは書き込み不可のため、ログ記録はエラーになる可能性がある
                    # loggingモジュールを使う方が望ましい
                    pass
            else:
                pass
        elif contact_phone:
            pass
    except Exception:
        pass

                                      
TITLE_MAP = {
    1: '大富豪',
    2: '富豪',
    3: '平民',
    4: '貧民',
    5: '大貧民',
}


def title_for_rank(rank: int) -> str:
    return TITLE_MAP.get(rank, f'Rank{rank}')


# Bot utterance pools: used to present more varied pre-/post-play messages.
BOT_PRE_THINK_PHRASES = [
    'うーん……どうしようかな。',
    'ちょっと悩むね。',
    'ここは慎重に……',
    'うーん、選択肢が多いな。',
    '……考えています。',
    'むむむ、迷うなぁ。',
    'よし、少し考えよう。',
    'うーん、直感で行くか。',
    'あれこれ試してみる。',
    '待っててね、考えるよ。',
]

BOT_POST_PLAY_PHRASES = [
    'これで決まり！',
    '出してみたよ。',
    'うまくいくといいな。',
    'どうだ、これで！',
    'さあ、次は君の番だよ。',
    'うまくいったかな？',
    'はは、出したよ〜',
    'よし、これで行こう。',
    '出したよ、よろしく！',
    'さあ、勝負だ！',
]

                                        
ROOMS: Dict[str, Dict[str, Any]] = {}
                               
ROOM_EVENTS: Dict[str, List[Dict[str, Any]]] = {}


def emit_event(room_id: str, event_type: str, payload: Dict[str, Any]):
    """Append an event to the room's event queue. Clients poll via SSE endpoint."""
    ROOM_EVENTS.setdefault(room_id, []).append({'type': event_type, 'payload': payload})


def pop_events(room_id: str):
    return ROOM_EVENTS.pop(room_id, [])


def _row_to_dict(cur, row):
    """Convert a DB row to a dict mapping column names to values.

    Works for both psycopg (psycopg) and psycopg2 or generic cursor.row tuples.
    If row is already a mapping (supports keys), return as-is.
    """
    try:
        # psycopg2.extras.DictRow behaves like a mapping
        if hasattr(row, 'keys'):
            return dict(row)
    except Exception:
        pass
    # fall back to using cursor.description to map column names
    try:
        desc = [d[0] for d in cur.description] if cur and getattr(cur, 'description', None) else []
        if desc and isinstance(row, (list, tuple)):
            return {k: v for k, v in zip(desc, row)}
    except Exception:
        pass
    # last resort: attempt to coerce to dict
    try:
        return dict(row)
    except Exception:
        return {}


def make_deck() -> List[str]:
                                                               
    suits = ['♠', '♣', '♦', '♥']
    ranks = ['3','4','5','6','7','8','9','10','J','Q','K','A','2']
    cards = [f"{r}{s}" for s in suits for r in ranks]
                                             
    cards.extend(['JOKER', 'JOKER'])
    return cards


def _make_message(player_id: str, name: str, text: str, ts: str = None) -> Dict[str, Any]:
    """Create a message dict with a stable unique id for client dedupe."""
    if not ts:
        ts = datetime.utcnow().isoformat() + 'Z'
    return {'id': uuid.uuid4().hex, 'player_id': player_id, 'name': name, 'text': text, 'ts': ts}


def create_room(creator_name: str) -> Dict[str, Any]:
    room_id = uuid.uuid4().hex[:8]
    player_id = uuid.uuid4().hex
    room = {
        'id': room_id,
        'players': [
            {'id': player_id, 'name': creator_name, 'is_bot': False, 'contact_email': None, 'contact_phone': None}
        ],
        'creator': player_id,
        # per-room rule toggles (default values)
        'rules': {
            # whether the special-case "スペード3 が JOKER に勝つ" is enabled
            'spade3_over_joker': True,
            # if True, the spade3 special-case only applies to 単発 (単体1枚) plays
            'spade3_single_only': True,
            # whether playing 8 over a center that contains 2 is blocked
            'block_8_after_2': True,
            # whether humans are auto-passed when they don't have JOKER and center contains 2
            'auto_pass_when_no_joker_vs_2': True,
        },
        'started': False,
        'current_turn': 0,
        'hands': {},                              
        'center': [],
        'deck': [],
        'messages': [],
        'last_player': None,
        # last player who actually played a card (even if center was cleared)
        'last_non_null_player': None,
        'consecutive_passes': 0,
        'next_rank': 1,
        'direction': 'clockwise',
    }
    ROOMS[room_id] = room
    if db:
        try:
            db.create_game(room_id, metadata=json.dumps({'creator': creator_name}))
        except Exception:
            # データベースへの書き込み失敗は、ゲームの進行に影響を与えないようにする
            pass
    return {'room': room, 'player_id': player_id}


def add_bot(room_id: str, display_name: str = None, tone: str = 'いじわる', difficulty: str = 'ふつう') -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('ルームが見つかりません')
    if room.get('started'):
        raise RuntimeError('ゲームは既に開始されています')
    pid = uuid.uuid4().hex
    name = f'Bot{len(room.get("players", []))+1}'
    # choose a human-friendly display name from pool if not explicitly provided
    used_names = set(p.get('display_name') or p.get('name') for p in room.get('players', []))
    chosen_display = display_name or pick_bot_display_name(used_names)
    bot = {'id': pid, 'name': name, 'is_bot': True, 'display_name': chosen_display, 'tone': tone, 'difficulty': difficulty, 'contact_email': None, 'contact_phone': None}
    room.setdefault('players', []).append(bot)
    return bot


def remove_bot(room_id: str, bot_id: str) -> bool:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('ルームが見つかりません')
    if room.get('started'):
        raise RuntimeError('ゲームは既に開始されています')
    before = len(room.get('players', []))
    room['players'] = [p for p in room.get('players', []) if not (p.get('is_bot') and p.get('id') == bot_id)]
    after = len(room.get('players', []))
    return after < before


def join_room(room_id: str, name: str) -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('ルームが見つかりません')
                                 
    pid = uuid.uuid4().hex
    room['players'].append({'id': pid, 'name': name, 'is_bot': False, 'contact_email': None, 'contact_phone': None})
    return {'room': room, 'player_id': pid}


def join_bot_slot(room_id: str, bot_id: str, name: str) -> Dict[str, Any]:
    """Replace a bot with a human player in the given room if that bot exists.
    Returns the room and new player_id. Raises KeyError if room not found or ValueError if bot not found.
    """
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    for i, p in enumerate(room.get('players', [])):
        if p.get('id') == bot_id and p.get('is_bot'):
            pid = uuid.uuid4().hex
            human = {'id': pid, 'name': name, 'is_bot': False, 'contact_email': None, 'contact_phone': None}
            room['players'][i] = human
            # preserve hands mapping: move bot's hand to human
            hands = room.get('hands', {})
            if p['id'] in hands:
                hands[pid] = hands.pop(p['id'])
            # emit event
            try:
                emit_event(room_id, 'bot_slot_joined', {'bot_id': bot_id, 'player_id': pid, 'name': name})
            except Exception:
                pass
            return {'room': room, 'player_id': pid}
    raise ValueError('bot not found')


def find_local_rooms_with_bot_slots() -> List[Dict[str, Any]]:
    """Return list of rooms that have at least one bot (available slot).
    Each entry: {'room_id': id, 'bots': [ {id,name,tone,difficulty} ], 'player_count': n }
    """
    out = []
    for room_id, room in ROOMS.items():
        bots = [ { 'id': p['id'], 'name': p.get('name'), 'display_name': p.get('display_name'), 'tone': p.get('tone'), 'difficulty': p.get('difficulty') } for p in room.get('players', []) if p.get('is_bot') ]
        if bots:
            out.append({'room_id': room_id, 'bots': bots, 'player_count': len(room.get('players', []))})
    return out


def start_game(room_id: str) -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('ルームが見つかりません')
                                                                    
    players = room.get('players', [])
    TARGET_PLAYERS = 5
    if len(players) < TARGET_PLAYERS:
        existing_names = set(p.get('name') for p in players)
        next_idx = 1
                                                                            
        while f'Bot{next_idx}' in existing_names:
            next_idx += 1
        while len(players) < TARGET_PLAYERS:
            pid = uuid.uuid4().hex
            name = f'Bot{next_idx}'
            # pick a display name from pool avoiding duplicates within the room
            used_names = set(p.get('display_name') or p.get('name') for p in players)
            display = pick_bot_display_name(used_names)
            players.append({'id': pid, 'name': name, 'is_bot': True, 'display_name': display, 'tone': 'いじわる', 'difficulty': 'ふつう'})
            existing_names.add(name)
            next_idx += 1
        room['players'] = players
                             
    deck = make_deck()
    random.shuffle(deck)
                                  
    players = room.get('players', [])
    if not players:
        raise RuntimeError('プレイヤーがいません')
    hands = {p['id']: [] for p in players}
    i = 0
    while deck:
        pid = players[i % len(players)]['id']
        hands[pid].append(deck.pop())
        i += 1
    room['hands'] = hands
    room['deck'] = deck
    room['started'] = True
    room['center'] = []
    room['current_turn'] = 0
    room['turn_started_at'] = datetime.now(timezone.utc).isoformat()
    room['last_player'] = None
    room['consecutive_passes'] = 0
    room['next_rank'] = 1
    room['revolution'] = False
    room['game_over'] = False
                                                 
                                                                                                      
                                                
    finished = room.get('finished', {})
    if finished:
                                        
        rank_to_pid = {r: pid for pid, r in finished.items()}
                                                             
                                                            
        daifugo = rank_to_pid.get(1)
        fugou = rank_to_pid.get(2)
        heimin = rank_to_pid.get(3)
        hinmin = rank_to_pid.get(4)
        daihinmin = rank_to_pid.get(5)

        def strongest_cards(pid, n=1):
            hand = list(room['hands'].get(pid, []))
                                                                             
            sorted_hand = sorted(hand, key=lambda c: _rank_value(c))
            return sorted_hand[-n:][::-1] if sorted_hand else []

                                                     
        if daihinmin and daifugo:
            to_transfer = strongest_cards(daihinmin, 2)
            if to_transfer:
                for c in to_transfer:
                    try:
                        room['hands'][daihinmin].remove(c)
                    except ValueError:
                        pass
                room['hands'].setdefault(daifugo, []).extend(to_transfer)
                try:
                    emit_event(room_id, 'auto_transfer', {'from': daihinmin, 'to': daifugo, 'cards': to_transfer})
                except Exception:
                    pass

                                                  
        if hinmin and fugou:
            to_transfer = strongest_cards(hinmin, 1)
            if to_transfer:
                for c in to_transfer:
                    try:
                        room['hands'][hinmin].remove(c)
                    except ValueError:
                        pass
                room['hands'].setdefault(fugou, []).extend(to_transfer)
                try:
                    emit_event(room_id, 'auto_transfer', {'from': hinmin, 'to': fugou, 'cards': to_transfer})
                except Exception:
                    pass

                                                                                                            
        if fugou and hinmin:
            room['pending_give'] = room.get('pending_give', {})
            room['pending_give'][fugou] = {'to': hinmin, 'count': 1, 'allowed': True}
        if daifugo and daihinmin:
            room['pending_give'] = room.get('pending_give', {})
            room['pending_give'][daifugo] = {'to': daihinmin, 'count': 2, 'allowed': True}

    return room


def _rank_value(card: str) -> int:
                                                             
    if card == 'JOKER':
                                      
        return 999
    rank = card[:-1]
    order = ['3','4','5','6','7','8','9','10','J','Q','K','A','2']
    try:
        return order.index(rank)
    except ValueError:
        return -1


def _rank_index_from_rank(rank: str) -> int:
    order = ['3','4','5','6','7','8','9','10','J','Q','K','A','2']
    if not rank:
        return -1
    if rank == 'JOKER':
        return 999
    try:
        return order.index(rank)
    except ValueError:
        return -1


def _rank_greater(a_idx: int, b_idx: int, revolution: bool = False) -> bool:
    """Return True if rank index a is considered greater than b under current revolution state.
    Normally higher index wins; under revolution the ordering is inverted.
    """
    # Note: special-case handling (スペードの3がJOKERより強い) is applied outside where rank indexes
    # alone are insufficient. This function preserves the base comparison behavior; callers may
    # check special cards (e.g., spade 3 vs JOKER) before invoking this.
    if revolution:
        return a_idx < b_idx
    return a_idx > b_idx


def _contains_spade_three(cards: List[str]) -> bool:
    """Return True if the card list contains the spade 3 (represented as '3♠' or similar)."""
    for c in cards:
        try:
            if c == 'JOKER':
                continue
            # card string format: rank + suit (e.g., '3♠' or '10♣')
            rank = c[:-1]
            suit = c[-1]
            if rank == '3' and suit == '♠':
                return True
        except Exception:
            continue
    return False


def _is_straight(cards: List[str]) -> bool:
                                              
    if len(cards) < 3:
        return False
                                               
    n = len(cards)
                            
    nonjoker = [c for c in cards if c != 'JOKER']
                                                  
    if nonjoker:
        suits = [c[-1] for c in nonjoker]
        if len(set(suits)) != 1:
            return False
                                         
    nonjoker_idxs = sorted([_rank_value(c) for c in nonjoker])
                                                                              
    if len(set(nonjoker_idxs)) != len(nonjoker_idxs):
        return False
    jokers = len([c for c in cards if c == 'JOKER'])
                                                                                      
    max_rank = 12                             
    for start in range(0, max_rank - n + 2):
        end = start + n - 1
        ok = True
        for idx in nonjoker_idxs:
            if idx < start or idx > end:
                ok = False
                break
        if ok:
            return True
    return False


def _straight_top_idx(cards: List[str]) -> int:
    """If cards can form a straight (with jokers), return the maximum possible top index.
    Returns -1 if not possible.
    """
    n = len(cards)
    nonjoker = [c for c in cards if c != 'JOKER']
    if not _is_straight(cards):
        return -1
                                                         
    if not nonjoker:
        return 12
    nonjoker_idxs = sorted([_rank_value(c) for c in nonjoker])
    max_rank = 12
    best_top = -1
    for start in range(0, max_rank - n + 2):
        end = start + n - 1
        ok = True
        for idx in nonjoker_idxs:
            if idx < start or idx > end:
                ok = False
                break
        if ok:
            best_top = max(best_top, end)
    return best_top


def _play_meta(cards: List[str]) -> Dict[str, Any]:
                                                                         
    if not cards:
        return {'type': 'empty'}
                   
    ranks = [ (c[:-1] if c!='JOKER' else 'JOKER') for c in cards]
    suits = [ (c[-1] if c!='JOKER' else 'JOKER') for c in cards]
    all_spades = all(s == '♠' for s in suits)
    contains_8 = any((c[:-1] if c!='JOKER' else '') == '8' for c in cards)
    contains_2 = any((c[:-1] if c!='JOKER' else '') == '2' for c in cards)
    contains_5 = any((c[:-1] if c!='JOKER' else '') == '5' for c in cards)
    contains_7 = any((c[:-1] if c!='JOKER' else '') == '7' for c in cards)
    contains_9 = any((c[:-1] if c!='JOKER' else '') == '9' for c in cards)
    contains_10 = any((c[:-1] if c!='JOKER' else '') == '10' for c in cards)
    contains_K = any((c[:-1] if c!='JOKER' else '') == 'K' for c in cards)
    contains_4 = any((c[:-1] if c!='JOKER' else '') == '4' for c in cards)
    contains_A = any((c[:-1] if c!='JOKER' else '') == 'A' for c in cards)
    contains_Q = any((c[:-1] if c!='JOKER' else '') == 'Q' for c in cards)
    contains_J = any((c[:-1] if c!='JOKER' else '') == 'J' for c in cards)
    contains_joker = any(c == 'JOKER' for c in cards)

                                                                           
                                           
    base_ranks = [r for r in ranks if r != 'JOKER']
    if len(base_ranks) == 0:
                                                      
        set_ok = True
        base_rank = 'JOKER'
    else:
        set_ok = len(set(base_ranks)) == 1
        base_rank = base_ranks[0] if base_ranks else None
    if set_ok and len(cards) >= 1:
        return {
            'type': 'set',
            'count': len(cards),
                                                                      
            'rank_idx': (_rank_index_from_rank(base_rank) if base_rank else 999),
            'suits': suits,
            'all_spades': all_spades,
            'contains_8': contains_8,
            'contains_2': contains_2,
            'contains_5': contains_5,
            'contains_7': contains_7,
            'contains_10': contains_10,
            'contains_J': contains_J,
            'contains_Q': contains_Q,
            'contains_K': contains_K,
            'contains_4': contains_4,
            'contains_A': contains_A,
            'contains_joker': contains_joker,
        }

              
    if _is_straight(cards):
        top = _straight_top_idx(cards)
                                                                                                 
        nonjoker = [c for c in cards if c != 'JOKER']
        suits = [c[-1] for c in nonjoker] if nonjoker else suits
        all_spades = all(s == '♠' for s in suits) if suits else False
        return {
            'type': 'straight',
            'count': len(cards),
            'top_idx': top,
            'suits': suits,
            'all_spades': all_spades,
            'contains_8': contains_8,
            'contains_2': contains_2,
            'contains_5': contains_5,
            'contains_7': contains_7,
            'contains_9': contains_9,
            'contains_10': contains_10,
            'contains_J': contains_J,
            'contains_Q': contains_Q,
            'contains_K': contains_K,
            'contains_4': contains_4,
            'contains_A': contains_A,
        }

    return {'type': 'invalid', 'contains_8': contains_8, 'contains_5': contains_5, 'contains_7': contains_7, 'contains_9': contains_9, 'contains_10': contains_10, 'contains_J': contains_J, 'contains_K': contains_K, 'contains_Q': contains_Q, 'contains_joker': contains_joker}


def _allowed_play_against(center_meta: Dict[str, Any], play_meta: Dict[str, Any]) -> bool:
    """Return False if play_meta is not allowed against center_meta by special rules.

    Rule added: if the center contains a '2' (contains_2), then playing an '8' is not allowed
    unless the play includes a Joker. In that case only Joker or pass is allowed.
    """
    try:
        # The caller should pass in room rules context when available; by default enforce block
        room_rules = play_meta.get('_room_rules') if isinstance(play_meta, dict) else None
        block_setting = True
        if isinstance(room_rules, dict):
            block_setting = room_rules.get('block_8_after_2', True)
        if center_meta and center_meta.get('contains_2') and block_setting:
            # If attempting to play an 8 (contains_8) and the play does not include Joker, disallow
            if play_meta.get('contains_8') and not play_meta.get('contains_joker'):
                return False
        return True
    except Exception:
        return True


def play_card(room_id: str, player_id: str, cards, target_rank: str = None) -> Dict[str, Any]:
    """
    cards: either a single card string or a list of card strings
    Simple rules implemented:
      - can play n cards if they all have the same rank
      - if center is empty: any valid set allowed
      - if center has m cards: you must play exactly m cards and higher rank
    """
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('ルームが見つかりません')
    if not room['started']:
        raise RuntimeError('ゲームが開始されていません')
                
    if room['players'][room['current_turn']]['id'] != player_id:
        raise RuntimeError('not your turn')
    hand = room['hands'].get(player_id, [])
    if isinstance(cards, str):
        play_list = [cards]
    else:
        play_list = list(cards)
                               
    for c in play_list:
        if c not in hand:
            raise RuntimeError('card not in hand')
                                           
    meta = _play_meta(play_list)
    if meta['type'] == 'invalid':
        raise RuntimeError('invalid combination of cards')
                  
    center = room.get('center') or []
    if center:
        center_meta = _play_meta(center)
                                            
        # enforce same type and special allowed play rules
        if center_meta['type'] != meta['type']:
            raise RuntimeError('must play same type as center')
        # attach room rules to meta so helpers can consult per-room toggles
        meta['_room_rules'] = room.get('rules', {})
        center_meta['_room_rules'] = room.get('rules', {})
        if not _allowed_play_against(center_meta, meta):
            raise RuntimeError('その手は許可されていません')
        if meta['type'] == 'set':
                                            
            if meta['count'] != center_meta['count']:
                raise RuntimeError('must play same number of cards as center')
                                                            
            if meta.get('contains_8'):
                                                                            
                pass
            else:
                                                                                            
                if meta.get('all_spades') and not center_meta.get('all_spades'):
                    pass
                else:
                                                                     
                    revolution = room.get('revolution', False)
                    # special-case: spade-3 beats JOKER even if rank indexes say otherwise
                    try:
                        # consult room rule toggle
                        rules = room.get('rules', {})
                        spade3_enabled = bool(rules.get('spade3_over_joker', True))
                        spade3_single_only = bool(rules.get('spade3_single_only', True))
                        # Only allow the special-case when enabled. If "single only" is set, require play count == 1
                        spade3_applicable = spade3_enabled and (not spade3_single_only or (spade3_single_only and meta.get('count') == 1))
                        if spade3_applicable and center_meta.get('contains_joker') and _contains_spade_three(meta.get('suits') or meta.get('cards') or meta.get('')):
                            # allow play (spade3 beats joker)
                            pass
                        elif not _rank_greater(meta['rank_idx'], center_meta['rank_idx'], revolution=revolution):
                            raise RuntimeError('played rank is not higher than center')
                    except Exception:
                        if not _rank_greater(meta['rank_idx'], center_meta['rank_idx'], revolution=revolution):
                            raise RuntimeError('played rank is not higher than center')
                    # enforce special rule: cannot play 8 over a center that contains 2
                    if not _allowed_play_against(center_meta, meta):
                        raise RuntimeError('その手は許可されていません')
        elif meta['type'] == 'straight':
                                   
            if meta['count'] != center_meta['count']:
                raise RuntimeError('must play same number of cards as center (straight length)')
                                                            
            if meta.get('contains_8'):
                pass
            else:
                                                                                                 
                if meta.get('all_spades') and not center_meta.get('all_spades'):
                    pass
                else:
                                                                          
                    revolution = room.get('revolution', False)
                    if not _rank_greater(meta['top_idx'], center_meta['top_idx'], revolution=revolution):
                        raise RuntimeError('played straight is not higher than center')
                  
    for c in play_list:
        hand.remove(c)

    room.setdefault('player_pass_streaks', {})[player_id] = 0

    try:
        if db:
            for c in play_list:
                db.add_play(room_id, player_id, c, meta=None)
    except Exception:
        pass

    # mark this player as the last who actually played cards (used when all other players pass)
    room['last_non_null_player'] = player_id

    # handle 8 (clear) vs normal play
    if meta.get('contains_8'):
        # playing an 8 clears the center
        if room['players'][room['current_turn']]['id'] != player_id:
            raise RuntimeError('あなたの番ではありません')
        # clear the center so the effect is visible to all clients
        room['center'] = []
        room['last_player'] = None
        room['consecutive_passes'] = 0
        if room.get('revolution'):
            room['revolution'] = False
            try:
                emit_event(room_id, 'revolution', {'active': False})
            except Exception:
                pass
    else:
        # normal play: set center and last_player
        room['center'] = play_list
        room['last_player'] = player_id
        room['consecutive_passes'] = 0

        if meta.get('contains_J'):
            room['revolution'] = not room.get('revolution', False)
            try:
                emit_event(room_id, 'revolution', {'active': room['revolution']})
            except Exception:
                pass

        if meta.get('contains_K'):
            cur = room.get('direction', 'clockwise')
            newd = 'counterclockwise' if cur == 'clockwise' else 'clockwise'
            room['direction'] = newd
            try:
                emit_event(room_id, 'direction', {'direction': newd})
            except Exception:
                pass
                                                                           
    if meta.get('contains_10'):
                                                                                               
        room['pending_discard'] = {'player_id': player_id, 'allowed': True}
                                                                         
    else:
        room.pop('pending_discard', None)
                                                                              
    if meta.get('contains_9'):
        _shuffle_hands(room)
                                                     
    if meta.get('contains_Q') and target_rank:
                                                                                  
                                                             
        discarded = []
        for p in room['players']:
            pid = p['id']
            hand = list(room['hands'].get(pid, []))
            to_remove = [c for c in hand if (c != 'JOKER' and c[:-1] == target_rank) or (c == 'JOKER' and target_rank == 'JOKER')]
            for c in to_remove:
                try:
                    room['hands'][pid].remove(c)
                except ValueError:
                    pass
            if to_remove:
                discarded.extend([{'player_id': pid, 'cards': to_remove}])
        try:
            emit_event(room_id, 'mass_discard', {'target_rank': target_rank, 'discarded': discarded})
        except Exception:
            pass
                                                     
    if len(room['hands'].get(player_id, [])) == 0:
        rank = room.get('next_rank', 1)
        room.setdefault('finished', {})[player_id] = rank
        room['next_rank'] = rank + 1
        try:
            if db:
                db.set_player_finished(room_id, player_id, rank)
        except Exception:
            pass
                               
        try:
            emit_event(room_id, 'player_finished', {'player_id': player_id, 'rank': rank})
        except Exception:
            pass
                                                                                                                                                                 
    try:
                                               
        ranks_played = [ (c[:-1] if c!='JOKER' else 'JOKER') for c in play_list ]
        nonjoker_ranks = [r for r in ranks_played if r != 'JOKER']
        if len(play_list) == 2 and len(nonjoker_ranks) <= 2:
                                                                       
            def two_of(rank_symbol):
                                                                   
                return (sum(1 for r in nonjoker_ranks if r == rank_symbol) + sum(1 for r in ranks_played if r == 'JOKER')) >= 2
            if two_of('4'):
                                                                
                _apply_instant_grade_rotation(room_id, player_id, rank_type='4')
            elif two_of('A'):
                _apply_instant_grade_rotation(room_id, player_id, rank_type='A')
    except Exception:
        pass
                                                       
                                                                                            
    if meta.get('contains_4'):
                                                                                  
        room['pending_swap'] = {'player_id': player_id, 'allowed': True}
                                                                                       
    if meta.get('contains_A'):
        room['pending_take'] = {'player_id': player_id, 'allowed': True}
                                        
                                                                                            
    if not meta.get('contains_8'):
        _advance_to_next_active(room)
        room['turn_started_at'] = datetime.now(timezone.utc).isoformat()
        try:
            if meta.get('contains_5'):
                _advance_to_next_active(room)
        except Exception:
            pass
                                   
                                                                                                      
    try:
        if play_list:
            msg_txt = ','.join(play_list)
            ts = datetime.now(timezone.utc).isoformat()
            name = next((p.get('display_name') or p.get('name') for p in room['players'] if p['id']==player_id), player_id)
            msg = _make_message(player_id, name, f'出した: {msg_txt}', ts=ts)
            room.setdefault('messages', []).append(msg)
            emit_event(room_id, 'card_played', {'player_id': player_id, 'cards': play_list, 'ts': ts, 'msg_id': msg['id']})
    except Exception:
        pass
    process_bots(room)
                                                   
    _end_game_if_finished(room_id)
    return room


def discard_card(room_id: str, player_id: str, card: str) -> Dict[str, Any]:
    """
    Player discards one card when allowed (e.g., after playing a 10). Discard is optional.
    """
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    pd = room.get('pending_discard')
    if not pd or pd.get('player_id') != player_id or not pd.get('allowed'):
        raise RuntimeError('no discard allowed')
    hand = room['hands'].get(player_id, [])
    if card not in hand:
        raise RuntimeError('card not in hand')
                                                                  
    try:
        room['hands'][player_id].remove(card)
    except ValueError:
        raise RuntimeError('card not in hand')
    try:
        emit_event(room_id, 'card_discarded', {'player_id': player_id, 'card': card})
    except Exception:
        pass
                                             
    room.pop('pending_discard', None)
                                                               
    room.setdefault('player_pass_streaks', {})[player_id] = 0
    _advance_to_next_active(room)
                                   
    process_bots(room)
                                                
    try:
        if db:
            db.add_message(room_id, player_id, next((p['name'] for p in room['players'] if p['id']==player_id), None), f'discarded {card}')
    except Exception:
        pass
                        
    _end_game_if_finished(room_id)
    return room


def pass_turn(room_id: str, player_id: str) -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    if not room['started']:
        raise RuntimeError('game not started')
                
    if room['players'][room['current_turn']]['id'] != player_id:
        raise RuntimeError('not your turn')
                                                          
    room['consecutive_passes'] = room.get('consecutive_passes', 0) + 1
                                      
    room.setdefault('player_pass_streaks', {})[player_id] = room.setdefault('player_pass_streaks', {}).get(player_id, 0) + 1
                                                         
    active_players = [p for p in room['players'] if len(room['hands'].get(p['id'], [])) > 0]
    n_active = max(1, len(active_players))
                                                                   
                                                                                     
    # determine which last-player reference to use: prefer last_non_null_player if present
    last_ref = room.get('last_non_null_player') or room.get('last_player')

    if last_ref:
        if room['consecutive_passes'] >= max(0, (n_active - 1)):
            # all others passed: clear center and let the last non-null player (if still has cards) play freely
            room['center'] = []
            idx = next((i for i, p in enumerate(room['players']) if p['id'] == last_ref), None)
            if idx is not None and len(room['hands'].get(last_ref, [])) > 0:
                room['current_turn'] = idx
            else:
                _advance_to_next_active(room)
            room['consecutive_passes'] = 0

            for pid in list(room.get('player_pass_streaks', {}).keys()):
                room['player_pass_streaks'][pid] = 0
            return room
                                 
                                   
    _advance_to_next_active(room)
                           
    room['turn_started_at'] = datetime.now(timezone.utc).isoformat()
                                   
    process_bots(room)
                                            
    if all(len(room['hands'].get(p['id'], [])) == 0 for p in room['players']):
                                                  
        for p in room['players']:
            pid = p['id']
            if pid not in room.get('finished', {}) and len(room['hands'].get(pid, [])) == 0:
                rank = room.get('next_rank', 1)
                room.setdefault('finished', {})[pid] = rank
                room['next_rank'] = rank + 1
                try:
                    if db:
                        db.set_player_finished(room_id, pid, rank)
                except Exception:
                    pass
                                                                  
        _end_game_if_finished(room_id)
    return room


def add_message(room_id: str, player_id: str, text: str) -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
                      
    pname = None
    for p in room['players']:
        if p['id'] == player_id:
            pname = p.get('display_name') or p['name']
            break
    if pname is None:
        pname = 'Unknown'
    
    ts = datetime.now(timezone.utc).isoformat()
    msg = _make_message(player_id, pname, text, ts=ts)
    room.setdefault('messages', []).append(msg)
                          
    if len(room['messages']) > 200:
        room['messages'] = room['messages'][-200:]
    try:
        if db:
            db.add_message(room_id, player_id, pname, text)
    except Exception:
        pass
                                                                           
    try:
        _trigger_bot_auto_reply(room_id, player_id, text)
    except Exception:
        pass
    return msg


def _trigger_bot_auto_reply(room_id: str, sender_id: str, text: str):
    """If QA_PAIRS contains a match for the incoming text, choose a bot to reply.
    Matching is simple substring (case-insensitive). Replies are rate-limited per-bot and
    influenced by bot difficulty.
    """
    if not QA_PAIRS:
        return
    room = ROOMS.get(room_id)
    if not room:
        return
    t = (text or '').lower()
    answers = []
    for qa in QA_PAIRS:
        q = qa.get('q') or ''
        if not q:
            continue
        if q.lower() in t:
            a = qa.get('a')
            if a:
                answers.append(str(a))
    if not answers:
        return
                       
    answer = random.choice(answers)
                                          
    candidates = [p for p in room.get('players', []) if p.get('is_bot') and p.get('id') != sender_id]
    if not candidates:
        return
                                                                  
    weight_map = {'弱い': 0.2, 'ふつう': 0.6, '強い': 0.9}
    now = time.time()
    room.setdefault('bot_last_reply', {})
                                                      
    attempts = 0
    while attempts < 6 and candidates:
        attempts += 1
        bot = random.choice(candidates)
        diff = bot.get('difficulty', 'ふつう')
        chance = weight_map.get(diff, 0.6)
        last = room['bot_last_reply'].get(bot['id'], 0)
                                                        
        if now - last < 3:
                                   
            candidates = [c for c in candidates if c['id'] != bot['id']]
            continue
        if random.random() <= chance:
            payload_ts = datetime.now(timezone.utc).isoformat()
            payload = {'player_id': bot['id'], 'text': answer, 'ts': payload_ts}
            try:
                bot_msg = _make_message(bot['id'], bot.get('display_name') or bot.get('name'), answer, ts=payload_ts)
                room.setdefault('messages', []).append(bot_msg)
                payload['msg_id'] = bot_msg['id']
                emit_event(room_id, 'bot_chat', payload)
                room['bot_last_reply'][bot['id']] = now
            except Exception:
                pass
            return
        else:
            candidates = [c for c in candidates if c['id'] != bot['id']]
    return


def process_bots(room: Dict[str, Any]):
                                                                           
    # If current player is a bot, schedule a visible 'thinking' period and perform the action after a delay.
    # This prevents immediate skips and lets clients show the bot's thinking/playing animation.
    n = len(room.get('players', []))
    safety = 0
    while True:
        if safety > 500:
            break
        safety += 1
        cur_idx = room.get('current_turn', 0)
        cur = room['players'][cur_idx] if 0 <= cur_idx < len(room['players']) else None
        if not cur or not cur.get('is_bot'):
            break
        # If a bot action is already scheduled for this room, don't schedule another
        if room.get('_bot_scheduled'):
            break
        # schedule bot thinking -> emit event for clients to show animation
        pid = cur['id']
        delay = room.get('_bot_think_delay', 10)
        try:
            emit_event(room['id'], 'bot_thinking', {'player_id': pid, 'delay': delay})
        except Exception:
            pass
        # schedule intermediate bot chat/emote to show '悩む' scenes
        def _emit_stage(msg):
            try:
                ts = datetime.now(timezone.utc).isoformat()
                bot_msg = _make_message(pid, cur.get('display_name') or cur.get('name'), msg, ts=ts)
                room.setdefault('messages', []).append(bot_msg)
                emit_event(room['id'], 'bot_chat', {'player_id': pid, 'text': msg, 'ts': ts, 'msg_id': bot_msg['id']})
            except Exception:
                pass
        try:
            # prefer QA-based reply for pre-think, fallback to canned phrase
            try:
                pre = pick_bot_reply(topic='thinking', tone=cur.get('tone'))
            except Exception:
                pre = None
            if not pre:
                pre = random.choice(BOT_PRE_THINK_PHRASES)
            threading.Timer(max(1, int(delay * 0.3)), lambda: _emit_stage(pre)).start()
        except Exception:
            pass
        # mark scheduled and start timer to perform actual action
        room['_bot_scheduled'] = True
        def _run_bot():
            try:
                room.pop('_bot_scheduled', None)
                _bot_act(room['id'], pid)
            except Exception:
                room.pop('_bot_scheduled', None)
        t = threading.Timer(delay, _run_bot)
        room['_bot_timer'] = t
        t.start()
        break
        pid = cur['id']
        hand = room['hands'].get(pid, [])
        if not hand:
                                                  
            _advance_to_next_active(room)
            continue

        played = None
        center = room.get('center') or []
        center_meta = _play_meta(center) if center else {'type': 'empty'}

                                   
        bot_info = cur or {}
        difficulty = bot_info.get('difficulty', 'ふつう')
        tone = bot_info.get('tone', 'いじわる')
                                                                    
        if difficulty == '弱い':
            joker_allowed_streak = 4
            aggressive = False
        elif difficulty == '強い':
            joker_allowed_streak = 1
            aggressive = True
        else:
            joker_allowed_streak = 3
            aggressive = False

        def remove_from_hand(p_id, cards):
            for c in cards:
                try:
                    room['hands'][p_id].remove(c)
                except ValueError:
                    pass

                                            
        if center:
            if center_meta['type'] == 'set':
                cnt = center_meta['count']
                               
                rank_map = {}
                for c in hand:
                    rank_map.setdefault(c[:-1], []).append(c)
                                                           
                candidates = []
                for r, cards in rank_map.items():
                    if len(cards) >= cnt:
                        candidates.append(( _rank_value(cards[0]), sorted(cards, key=lambda x: _rank_value(x)) ))
                candidates.sort()
                for _, cards in candidates:
                    attempt = cards[:cnt]
                    meta = _play_meta(attempt)
                    try:
                        meta['_room_rules'] = room.get('rules', {})
                    except Exception:
                        pass
                    if meta.get('contains_8'):
                        played = attempt
                        break
                    if meta.get('all_spades') and not center_meta.get('all_spades'):
                        played = attempt
                        break
                    revolution = room.get('revolution', False)
                    try:
                        if center_meta.get('contains_joker') and _contains_spade_three(attempt):
                            played = attempt
                        elif _rank_greater(meta['rank_idx'], center_meta.get('rank_idx', -1), revolution=revolution):
                            played = attempt
                    except Exception:
                        if _rank_greater(meta['rank_idx'], center_meta.get('rank_idx', -1), revolution=revolution):
                            played = attempt
                        break
            elif center_meta['type'] == 'straight':
                cnt = center_meta['count']
                by_suit = {}
                jokers = [c for c in hand if c == 'JOKER']
                for c in hand:
                    if c == 'JOKER':
                        continue
                    by_suit.setdefault(c[-1], []).append(c)
                                                                                                                         
                candidates = []
                for s, cards in by_suit.items():
                                                                                             
                    cards_with_jokers = list(cards) + list(jokers)
                    cards_sorted = sorted(cards_with_jokers, key=lambda x: _rank_value(x))
                    for i in range(len(cards_sorted) - cnt + 1):
                        seq = cards_sorted[i:i+cnt]
                        if _is_straight(seq):
                            meta = _play_meta(seq)
                            try:
                                meta['_room_rules'] = room.get('rules', {})
                            except Exception:
                                pass
                            contains_joker = any(c == 'JOKER' for c in seq)
                            streak = room.get('player_pass_streaks', {}).get(pid, 0)
                            if contains_joker and streak < joker_allowed_streak:
                                continue
                                                                                                             
                                                                                            
                            sort_top = meta.get('top_idx', -1)
                            sort_key = (0 if not contains_joker else 1, (-sort_top if aggressive else sort_top))
                            candidates.append((sort_key, seq, meta))
                                                      
                candidates.sort(key=lambda x: x[0])
                for _, seq, meta in candidates:
                    if meta.get('contains_8'):
                        played = seq
                        break
                    if meta.get('all_spades') and not center_meta.get('all_spades'):
                        played = seq
                        break
                    revolution = room.get('revolution', False)
                    # special-case: spade-3 beats JOKER even for straights
                    try:
                        if center_meta.get('contains_joker') and _contains_spade_three(seq):
                            played = seq
                        elif _rank_greater(meta.get('top_idx', -1), center_meta.get('top_idx', -1), revolution=revolution):
                            played = seq
                    except Exception:
                        try:
                            if center_meta.get('contains_joker') and _contains_spade_three(seq):
                                played = seq
                            elif _rank_greater(meta.get('top_idx', -1), center_meta.get('top_idx', -1), revolution=revolution):
                                played = seq
                        except Exception:
                            if _rank_greater(meta.get('top_idx', -1), center_meta.get('top_idx', -1), revolution=revolution):
                                played = seq
                        break
        else:
                                                                      
            hand_sorted = sorted(hand, key=lambda x: _rank_value(x))
                                                                      
            found = False
            by_suit = {}
            jokers = [c for c in hand_sorted if c == 'JOKER']
            for c in hand_sorted:
                if c == 'JOKER':
                    continue
                by_suit.setdefault(c[-1], []).append(c)
                                                      
            candidates = []
            for s, cards in by_suit.items():
                cards_with_jokers = list(cards) + list(jokers)
                cards_sorted = sorted(cards_with_jokers, key=lambda x: _rank_value(x))
                for length in range(3, len(cards_sorted)+1):
                    for i in range(len(cards_sorted)-length+1):
                        seq = cards_sorted[i:i+length]
                        if _is_straight(seq):
                            meta = _play_meta(seq)
                            try:
                                meta['_room_rules'] = room.get('rules', {})
                            except Exception:
                                pass
                            contains_joker = any(c == 'JOKER' for c in seq)
                            streak = room.get('player_pass_streaks', {}).get(pid, 0)
                            if contains_joker and streak < joker_allowed_streak:
                                continue
                            top = meta.get('top_idx', -1)
                            key = (0 if not contains_joker else 1, -top if aggressive else top)
                            candidates.append((key, seq, meta))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                played = candidates[0][1]
            if not played:
                                     
                if aggressive:
                                           
                    played = [hand_sorted[-1]]
                else:
                    played = [hand_sorted[0]]

                if not played:
                    try:
                        # pick reply from QA if available, otherwise tone-based canned
                        msg = pick_bot_reply(topic='pass', tone=tone)
                    except Exception:
                        msg = None
                    try:
                        if not msg:
                            if tone == 'いじわる':
                                msg = 'またパスかよ、残念〜'
                            elif tone == '真面目くん':
                                msg = '仕方ありません、パスします。'
                            else:
                                msg = 'うーん…今回はパスしようかな？'
                        if random.random() < (0.6 if aggressive else 0.25):
                            payload = {'player_id': pid, 'text': msg, 'ts': datetime.now(timezone.utc).isoformat()}
                            try:
                                bot_msg = _make_message(pid, cur.get('display_name') or cur.get('name'), msg, ts=payload['ts'])
                                room.setdefault('messages', []).append(bot_msg)
                                payload['msg_id'] = bot_msg['id']
                            except Exception:
                                pass
                            emit_event(room['id'], 'bot_chat', payload)
                    except Exception:
                        pass
            try:
                pass_turn(room['id'], pid)
            except Exception:
                                                                              
                _advance_to_next_active(room)
            continue

                                                             
                          
        remove_from_hand(pid, played)
                                                         
        try:
            pmsg = None
            if tone == 'いじわる':
                pmsg = 'こんなもんでどう？'
            elif tone == '真面目くん':
                pmsg = '出しました。'
            else:
                pmsg = 'やったー、出せたよ♪'
            if random.random() < (0.9 if aggressive else 0.4):
                payload = {'player_id': pid, 'text': pmsg, 'ts': datetime.now(timezone.utc).isoformat()}
                try:
                    bot_msg = _make_message(pid, cur.get('display_name') or cur.get('name'), pmsg, ts=payload['ts'])
                    room.setdefault('messages', []).append(bot_msg)
                    payload['msg_id'] = bot_msg['id']
                except Exception:
                    pass
                emit_event(room['id'], 'bot_chat', payload)
        except Exception:
            pass
                                                                
        room.setdefault('player_pass_streaks', {})[pid] = 0
                                     
        pmeta = _play_meta(played)
        # record who actually played
        room['last_non_null_player'] = pid

        if pmeta.get('contains_8'):
            room['center'] = []
            room['last_player'] = None
            room['consecutive_passes'] = 0
        else:
            room['center'] = played
            room['last_player'] = pid
            room['consecutive_passes'] = 0
                                             
        if pmeta.get('contains_9'):
            _shuffle_hands(room)
                            
        try:
            if db:
                for c in played:
                    db.add_play(room['id'], pid, c, meta=None)
        except Exception:
            pass
                                       
        # create a message entry for the bot's play so clients see what cards the bot played
        try:
            if played:
                msg_txt = ','.join(played)
                ts = datetime.now(timezone.utc).isoformat()
                name = next((p.get('display_name') or p.get('name') for p in room['players'] if p['id']==pid), pid)
                msg = _make_message(pid, name, f'出した: {msg_txt}', ts=ts)
                room.setdefault('messages', []).append(msg)
                try:
                    emit_event(room['id'], 'card_played', {'player_id': pid, 'cards': played, 'ts': ts, 'msg_id': msg['id']})
                except Exception:
                    pass
        except Exception:
            pass

        _advance_to_next_active(room)

        try:
            if pmeta.get('contains_5'):
                _advance_to_next_active(room)
        except Exception:
            pass
                                           
    return room


def _bot_act(room_id: str, pid: str):
    """Perform a single bot action for player pid in room room_id.
    This is called from a Timer thread after a thinking delay.
    """
    room = ROOMS.get(room_id)
    if not room:
        return
    # ensure this player still is at current_turn and is bot
    try:
        cur_idx = room.get('current_turn')
        if cur_idx is None:
            return
        cur = room['players'][cur_idx]
        if cur.get('id') != pid or not cur.get('is_bot'):
            return
    except Exception:
        return

    hand = list(room['hands'].get(pid, []))
    if not hand:
        try:
            _advance_to_next_active(room)
        except Exception:
            pass
        return

    center = room.get('center') or []
    center_meta = _play_meta(center) if center else {'type': 'empty'}

    # choose play similarly to original process_bots logic
    played = None
    bot_info = cur or {}
    difficulty = bot_info.get('difficulty', 'ふつう')
    tone = bot_info.get('tone', 'いじわる')
    if difficulty == '弱い':
        joker_allowed_streak = 4
        aggressive = False
    elif difficulty == '強い':
        joker_allowed_streak = 1
        aggressive = True
    else:
        joker_allowed_streak = 3
        aggressive = False

    def remove_from_hand(p_id, cards):
        for c in cards:
            try:
                room['hands'][p_id].remove(c)
            except Exception:
                pass

    # selection logic -- mirror synchronous code
    if center:
        if center_meta['type'] == 'set':
            cnt = center_meta['count']
            rank_map = {}
            for c in hand:
                rank_map.setdefault(c[:-1], []).append(c)
            candidates = []
            for r, cards in rank_map.items():
                if len(cards) >= cnt:
                    candidates.append(( _rank_value(cards[0]), sorted(cards, key=lambda x: _rank_value(x)) ))
            candidates.sort()
            for _, cards in candidates:
                attempt = cards[:cnt]
                meta = _play_meta(attempt)
                    # annotate with room rules for downstream helpers
                meta['_room_rules'] = room.get('rules', {})
                if meta.get('contains_8'):
                    played = attempt
                    break
                if meta.get('all_spades') and not center_meta.get('all_spades'):
                    played = attempt
                    break
                revolution = room.get('revolution', False)
                if _rank_greater(meta['rank_idx'], center_meta.get('rank_idx', -1), revolution=revolution):
                    played = attempt
                    break
        elif center_meta['type'] == 'straight':
            cnt = center_meta['count']
            by_suit = {}
            jokers = [c for c in hand if c == 'JOKER']
            for c in hand:
                if c == 'JOKER':
                    continue
                by_suit.setdefault(c[-1], []).append(c)
            candidates = []
            for s, cards in by_suit.items():
                cards_with_jokers = list(cards) + list(jokers)
                cards_sorted = sorted(cards_with_jokers, key=lambda x: _rank_value(x))
                for i in range(len(cards_sorted) - cnt + 1):
                    seq = cards_sorted[i:i+cnt]
                    if _is_straight(seq):
                            meta = _play_meta(seq)
                            meta['_room_rules'] = room.get('rules', {})
                    contains_joker = any(c == 'JOKER' for c in seq)
                    streak = room.get('player_pass_streaks', {}).get(pid, 0)
                    if contains_joker and streak < joker_allowed_streak:
                            continue
                    sort_top = meta.get('top_idx', -1)
                    sort_key = (0 if not contains_joker else 1, (-sort_top if aggressive else sort_top))
                    candidates.append((sort_key, seq, meta))
            candidates.sort(key=lambda x: x[0])
            for _, seq, meta in candidates:
                if meta.get('contains_8'):
                    played = seq
                    break
                if meta.get('all_spades') and not center_meta.get('all_spades'):
                    played = seq
                    break
                revolution = room.get('revolution', False)
                if _rank_greater(meta.get('top_idx', -1), center_meta.get('top_idx', -1), revolution=revolution):
                    played = seq
                    break
    else:
        hand_sorted = sorted(hand, key=lambda x: _rank_value(x))
        found = False
        by_suit = {}
        jokers = [c for c in hand_sorted if c == 'JOKER']
        for c in hand_sorted:
            if c == 'JOKER':
                continue
            by_suit.setdefault(c[-1], []).append(c)
        candidates = []
        for s, cards in by_suit.items():
            cards_with_jokers = list(cards) + list(jokers)
            cards_sorted = sorted(cards_with_jokers, key=lambda x: _rank_value(x))
            for length in range(3, len(cards_sorted)+1):
                for i in range(len(cards_sorted)-length+1):
                    seq = cards_sorted[i:i+length]
                    if _is_straight(seq):
                            meta = _play_meta(seq)
                            meta['_room_rules'] = room.get('rules', {})
                    contains_joker = any(c == 'JOKER' for c in seq)
                    streak = room.get('player_pass_streaks', {}).get(pid, 0)
                    if contains_joker and streak < joker_allowed_streak:
                            continue
                    top = meta.get('top_idx', -1)
                    key = (0 if not contains_joker else 1, -top if aggressive else top)
                    candidates.append((key, seq, meta))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            played = candidates[0][1]
        if not played:
            if aggressive:
                played = [hand_sorted[-1]]
            else:
                played = [hand_sorted[0]]

    if not played:
        # choose a brief pass message via QA or fallback
        try:
            msg = pick_bot_reply(topic='pass', tone=tone)
        except Exception:
            msg = None
        try:
            if not msg:
                if tone == 'いじわる':
                    msg = '今回はパスしますよ。'
                elif tone == '真面目くん':
                    msg = '申し訳ありません、パスします。'
                else:
                    msg = 'うーん、今回はパスかな。'
            payload = {'player_id': pid, 'text': msg, 'ts': datetime.now(timezone.utc).isoformat()}
            try:
                bot_msg = _make_message(pid, cur.get('display_name') or cur.get('name'), msg, ts=payload['ts'])
                room.setdefault('messages', []).append(bot_msg)
                payload['msg_id'] = bot_msg['id']
                emit_event(room['id'], 'bot_chat', payload)
            except Exception:
                pass
        except Exception:
            pass
        try:
            pass_turn(room['id'], pid)
        except Exception:
            try:
                _advance_to_next_active(room)
            except Exception:
                pass
        return

    # perform play
    remove_from_hand(pid, played)
    # choose a single post-play phrase to announce the play (QA preferred)
    try:
        try:
            post = pick_bot_reply(topic='played', tone=tone)
        except Exception:
            post = None
        if not post:
            post = random.choice(BOT_POST_PLAY_PHRASES)
        payload = {'player_id': pid, 'text': post, 'ts': datetime.now(timezone.utc).isoformat()}
        try:
            bot_msg = _make_message(pid, cur.get('display_name') or cur.get('name'), post, ts=payload['ts'])
            room.setdefault('messages', []).append(bot_msg)
            payload['msg_id'] = bot_msg['id']
            emit_event(room['id'], 'bot_chat', payload)
        except Exception:
            pass
    except Exception:
        pass

    room.setdefault('player_pass_streaks', {})[pid] = 0
    pmeta = _play_meta(played)
    room['last_non_null_player'] = pid
    if pmeta.get('contains_8'):
        room['center'] = []
        room['last_player'] = None
        room['consecutive_passes'] = 0
    else:
        room['center'] = played
        room['last_player'] = pid
        room['consecutive_passes'] = 0

    if pmeta.get('contains_9'):
        _shuffle_hands(room)

    try:
        # create message and emit card_played
        if played:
            msg_txt = ','.join(played)
            ts = datetime.now(timezone.utc).isoformat()
            name = next((p.get('display_name') or p.get('name') for p in room['players'] if p['id']==pid), pid)
            msg = _make_message(pid, name, f'出した: {msg_txt}', ts=ts)
            room.setdefault('messages', []).append(msg)
            try:
                emit_event(room['id'], 'card_played', {'player_id': pid, 'cards': played, 'ts': ts, 'msg_id': msg['id']})
            except Exception:
                pass
    except Exception:
        pass

    # handle special effects similar to play_card
    if pmeta.get('contains_J'):
        room['revolution'] = not room.get('revolution', False)
        try:
            emit_event(room['id'], 'revolution', {'active': room['revolution']})
        except Exception:
            pass

    if pmeta.get('contains_K'):
        curd = room.get('direction', 'clockwise')
        newd = 'counterclockwise' if curd == 'clockwise' else 'clockwise'
        room['direction'] = newd
        try:
            emit_event(room['id'], 'direction', {'direction': newd})
        except Exception:
            pass

    if pmeta.get('contains_10'):
        room['pending_discard'] = {'player_id': pid, 'allowed': True}
        # schedule bot discard if bot played the 10
        def _bot_discard_after():
            try:
                # pick a discard card: choose lowest non-10 preferably
                h = room['hands'].get(pid, [])
                if not h:
                    return
                # prefer non-JOKER and non-10
                candidates = [c for c in h if c != 'JOKER' and not c.startswith('10')]
                if not candidates:
                    candidates = h[:]
                choice = sorted(candidates, key=lambda x: _rank_value(x))[0]
                discard_card(room['id'], pid, choice)
            except Exception:
                pass
        try:
            threading.Timer(4, _bot_discard_after).start()
        except Exception:
            pass

    if pmeta.get('contains_Q'):
        # bot chooses a target rank (pick the rank that appears most in opponents' hands)
        counts = {}
        for p in room['players']:
            if p['id'] == pid:
                continue
            for c in room['hands'].get(p['id'], []):
                r = 'JOKER' if c == 'JOKER' else c[:-1]
                counts[r] = counts.get(r, 0) + 1
        # choose rank with max count, prefer numeric order if tie
        if counts:
            target_rank = max(sorted(counts.items(), key=lambda x: (_rank_index_from_rank(x[0]) if x[0] != 'JOKER' else 999, x[1])), key=lambda x: x[1])[0]
            # perform mass discard similar to play_card's logic
            discarded = []
            for p in room['players']:
                pid2 = p['id']
                hand2 = list(room['hands'].get(pid2, []))
                to_remove = [c for c in hand2 if (c != 'JOKER' and c[:-1] == target_rank) or (c == 'JOKER' and target_rank == 'JOKER')]
                for c in to_remove:
                    try:
                        room['hands'][pid2].remove(c)
                    except Exception:
                        pass
                if to_remove:
                    discarded.extend([{'player_id': pid2, 'cards': to_remove}])
            try:
                emit_event(room_id, 'mass_discard', {'target_rank': target_rank, 'discarded': discarded})
            except Exception:
                pass

    if len(room['hands'].get(pid, [])) == 0:
        rank = room.get('next_rank', 1)
        room.setdefault('finished', {})[pid] = rank
        room['next_rank'] = rank + 1
        try:
            if db:
                db.set_player_finished(room_id, pid, rank)
        except Exception:
            pass
        try:
            emit_event(room_id, 'player_finished', {'player_id': pid, 'rank': rank})
        except Exception:
            pass

    try:
        if pmeta.get('contains_4'):
            room['pending_swap'] = {'player_id': pid, 'allowed': True}
    except Exception:
        pass
    try:
        if pmeta.get('contains_A'):
            room['pending_take'] = {'player_id': pid, 'allowed': True}
    except Exception:
        pass

    _advance_to_next_active(room)
    room['turn_started_at'] = datetime.now(timezone.utc).isoformat()
    try:
        if pmeta.get('contains_5'):
            _advance_to_next_active(room)
    except Exception:
        pass

    _end_game_if_finished(room_id)


def get_room_state(room_id: str, player_id: str = None) -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
                                            
    try:
        if player_id:
            room.setdefault('last_seen', {})[player_id] = datetime.now(timezone.utc).isoformat()
    except Exception:
        pass
                                                                                  
                                                                                   
                                                               
                                                       
    public_players = [
        {
            'id': p['id'],
            'name': p['name'],
            'display_name': p.get('display_name', p.get('name')),
            'tone': p.get('tone'),
            'difficulty': p.get('difficulty'),
            'is_bot': p['is_bot'],
            'hand_count': len(room['hands'].get(p['id'], [])) if room.get('started') else None,
        }
        for p in room['players']
    ]
    your_hand = None
    if player_id and room.get('hands'):
        your_hand = list(room['hands'].get(player_id, []))
                                                                             
    pending_give = None
    if player_id:
        pg = room.get('pending_give', {})
        cfg = pg.get(player_id)
        if cfg:
            to_pid = cfg.get('to')
            to_name = next((p['name'] for p in room['players'] if p['id'] == to_pid), None)
            to_player = next((p for p in room['players'] if p['id'] == to_pid), None)
            to_hand_count = len(room['hands'].get(to_pid, [])) if to_pid else None
            to_is_bot = to_player.get('is_bot') if to_player else False
            to_rank = None
            if room.get('finished') and to_pid in room.get('finished', {}):
                try:
                    to_rank = int(room['finished'][to_pid])
                except Exception:
                    to_rank = None
            to_score = None
            if db and to_pid:
                try:
                    conn = db.get_conn()
                    cur = conn.cursor()
                    cur.execute('SELECT score, finished_rank FROM players WHERE id = %s AND game_id = %s', (to_pid, room['id']))
                    row = cur.fetchone()
                    rowd = _row_to_dict(cur, row) if row is not None else {}
                    if rowd:
                        try:
                            to_score = int(rowd.get('score')) if rowd.get('score') is not None else None
                        except Exception:
                            to_score = None
                        if to_rank is None:
                            try:
                                fr = rowd.get('finished_rank')
                                to_rank = int(fr) if fr is not None else None
                            except Exception:
                                pass
                except Exception:
                    pass
                finally:
                    if 'conn' in locals() and conn:
                        conn.close()
            pending_give = {'to': to_pid, 'to_name': to_name, 'count': cfg.get('count'), 'allowed': cfg.get('allowed'), 'to_hand_count': to_hand_count, 'to_is_bot': to_is_bot, 'to_rank': to_rank, 'to_score': to_score}
    return {
        'id': room['id'],
        'players': public_players,
        'started': room['started'],
        'current_turn': room['current_turn'],
        'center': room['center'],
        'your_hand': your_hand,
        'messages': list(room.get('messages', [])),
        'turn_started_at': room.get('turn_started_at'),
        'revolution': room.get('revolution', False),
        'pending_discard': room.get('pending_discard'),
        'pending_give': pending_give,
        'last_player': room.get('last_player'),
        'direction': room.get('direction', 'clockwise'),
    }


def _advance_to_next_active(room: Dict[str, Any]):
    """Advance current_turn to the next player index that still has cards. If none, leave as is."""
    n = len(room.get('players', []))
    if n == 0:
        return
    dir_setting = room.get('direction', 'clockwise')
    current_turn = room.get('current_turn', 0)
    for _ in range(n):
        if dir_setting == 'clockwise':
            current_turn = (current_turn + 1) % n
        else:
            current_turn = (current_turn - 1 + n) % n # マイナスにならないように +n
        
        room['current_turn'] = current_turn
        pid = room['players'][current_turn]['id']
        if len(room['hands'].get(pid, [])) > 0:
            room['turn_started_at'] = datetime.now(timezone.utc).isoformat()
            return


class RoomMonitor(threading.Thread):
    """Background thread that enforces accurate timeouts for turns and takeover."""
    def __init__(self, poll_interval: float = 0.5, takeover_threshold: float = 30.0, pass_threshold: float = 60.0):
        super().__init__(daemon=True)
        self.interval = poll_interval
        self.takeover_threshold = takeover_threshold
        self.pass_threshold = pass_threshold
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                now = datetime.now(timezone.utc)
                for room_id, room in list(ROOMS.items()):
                    try:
                        if not room.get('started'):
                            continue
                        cur_idx = room.get('current_turn')
                        if cur_idx is None:
                            continue
                        if not (0 <= cur_idx < len(room.get('players', []))):
                            continue
                        cur_player = room['players'][cur_idx]
                        cur_pid = cur_player.get('id')
                                                                               
                        if cur_player and not cur_player.get('is_bot'):
                            last_iso = room.get('last_seen', {}).get(cur_pid)
                            if last_iso:
                                        last_dt = datetime.fromisoformat(last_iso.replace('Z', ''))
                                        if (now - last_dt).total_seconds() > self.takeover_threshold:
                                                          
                                            cur_player['is_bot'] = True
                                            cur_player['taken_over'] = True
                                            cur_player['takeover_at'] = datetime.now(timezone.utc).isoformat()
                                        try:
                                            emit_event(room_id, 'player_taken_over', {'player_id': cur_pid, 'by_bot': True})
                                        except Exception:
                                            pass
                                                                                   
                                        try:
                                            contact = cur_player.get('contact_email') or cur_player.get('contact_phone')
                                            if contact:
                                                _send_contact_notification(cur_player, room_id, reason='takeover')
                                        except Exception:
                                            pass
                                                                                                    
                                        except Exception:
                                            pass
                        else:
                                                                                                                                      
                            if cur_player and cur_player.get('taken_over'):
                                last_iso = room.get('last_seen', {}).get(cur_player.get('id'))
                                if last_iso:
                                        last_dt = datetime.fromisoformat(last_iso.replace('Z', ''))
                                                                                                             
                                        if (now - last_dt).total_seconds() <= (self.takeover_threshold / 2.0):
                                                                              
                                            cur_player['is_bot'] = False
                                            cur_player.pop('taken_over', None)
                                            cur_player.pop('takeover_at', None)
                                            try:
                                                emit_event(room_id, 'player_released', {'player_id': cur_player.get('id')})
                                            except Exception:
                                                pass
                                                                                                        
                                            try:
                                                contact = cur_player.get('contact_email') or cur_player.get('contact_phone')
                                                if contact:
                                                    _send_contact_notification(cur_player, room_id, reason='released')
                                            except Exception:
                                                pass
                                                                                        
                        if cur_player and not cur_player.get('is_bot'):
                            ts = room.get('turn_started_at')
                            if ts:
                                try:
                                    started = datetime.fromisoformat(ts.replace('Z', ''))
                                    if (now - started).total_seconds() >= self.pass_threshold:
                                        try:
                                            pass_turn(room_id, cur_pid)
                                        except Exception:
                                                                                     
                                            pass
                                except Exception:
                                    pass
                        # Auto-pass rule: if center contains a 2 and the human current player does NOT have any Joker, automatically pass
                        try:
                            center = room.get('center') or []
                            center_meta = _play_meta(center) if center else {'type':'empty'}
                            if center_meta.get('contains_2') and cur_player and not cur_player.get('is_bot'):
                                # check player's hand for Joker
                                hand = room.get('hands', {}).get(cur_pid, [])
                                has_joker = any(c == 'JOKER' or (isinstance(c, str) and c == 'JOKER') for c in hand)
                                if not has_joker:
                                    try:
                                        pass_turn(room_id, cur_pid)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                                                                                                     
                                                                                          
                        try:
                                                                                 
                            cur_idx = room.get('current_turn')
                            if cur_idx is not None and 0 <= cur_idx < len(room.get('players', [])):
                                if room['players'][cur_idx].get('is_bot'):
                                    process_bots(room)
                        except Exception:
                            pass
                    except Exception:
                                                                           
                        pass
            except Exception:
                pass
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()


                                            
_GLOBAL_MONITOR: RoomMonitor = None
def _ensure_monitor_started():
    global _GLOBAL_MONITOR
    if _GLOBAL_MONITOR is None:
        try:
            _GLOBAL_MONITOR = RoomMonitor()
            _GLOBAL_MONITOR.start()
        except Exception:
            _GLOBAL_MONITOR = None


                 
_ensure_monitor_started()


def _shuffle_hands(room: Dict[str, Any]):
    """Collect all cards from players' hands, shuffle, and redistribute preserving counts."""
                    
    counts = {p['id']: len(room['hands'].get(p['id'], [])) for p in room['players']}
    all_cards = []
    for pid in counts:
        all_cards.extend(room['hands'].get(pid, []))
    random.shuffle(all_cards)
                  
    new_hands = {}
    idx = 0
    for pid, cnt in counts.items():
        new_hands[pid] = all_cards[idx:idx+cnt]
        idx += cnt
    room['hands'] = new_hands
    try:
        emit_event(room['id'], 'hands_shuffled', {'counts': counts})
    except Exception:
        pass
    return room


def give_card(room_id: str, from_player_id: str, card: str, direction: str = None) -> Dict[str, Any]:
    """
    Transfer a single card from from_player to their neighbor optionally.
    Allowed only if the from_player was the last to play and that play contained a 7.
    direction: optional 'left' or 'right' to override room direction.
    """
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
                              
    if card not in room['hands'].get(from_player_id, []):
        raise RuntimeError('card not in hand')
                                                           
    center = room.get('center') or []
    center_meta = _play_meta(center) if center else {'type': 'empty'}
    if room.get('last_player') != from_player_id or not center_meta.get('contains_7'):
        raise RuntimeError('can only give after you played a 7')

                               
    n = len(room['players'])
    idx = next((i for i,p in enumerate(room['players']) if p['id'] == from_player_id), None)
    if idx is None:
        raise RuntimeError('player not in room')
    if direction:
        if direction == 'left':
            ridx = (idx + 1) % n
        elif direction == 'right':
            ridx = (idx - 1 + n) % n # マイナスにならないように
        else:
            raise RuntimeError('invalid direction')
    else:
                                                
        dir_setting = room.get('direction', 'clockwise')
        if dir_setting == 'clockwise':
                            
            ridx = (idx - 1 + n) % n
        else:
                                               
            ridx = (idx + 1) % n

    recipient = room['players'][ridx]
                      
    try:
        room['hands'][from_player_id].remove(card)
    except ValueError:
        raise RuntimeError('card not in hand')
    room['hands'].setdefault(recipient['id'], []).append(card)
                
    try:
        emit_event(room_id, 'card_given', {'from': from_player_id, 'to': recipient['id'], 'card': card, 'direction': direction or room.get('direction', 'clockwise')})
    except Exception:
        pass
                              
    try:
        if db:
            db.add_message(room_id, from_player_id, next((p['name'] for p in room['players'] if p['id']==from_player_id), None), f'gave {card} to {recipient["id"]}')
    except Exception:
        pass
    return room


def swap_cards(room_id: str, player_id: str, target_player_id: str, give_card: str, take_card: str) -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    pd = room.get('pending_swap')
    if not pd or pd.get('player_id') != player_id or not pd.get('allowed'):
        raise RuntimeError('no swap allowed')
                        
    if give_card not in room['hands'].get(player_id, []):
        raise RuntimeError('give_card not in hand')
    if take_card not in room['hands'].get(target_player_id, []):
        raise RuntimeError('take_card not in target hand')
                  
    room['hands'][player_id].remove(give_card)
    room['hands'][target_player_id].remove(take_card)
    room['hands'][player_id].append(take_card)
    room['hands'][target_player_id].append(give_card)
                                  
    room.pop('pending_swap', None)
    try:
        emit_event(room_id, 'cards_swapped', {'from': player_id, 'to': target_player_id, 'gave': give_card, 'took': take_card})
    except Exception:
        pass
    return room


def take_card(room_id: str, player_id: str, target_player_id: str, take_card: str) -> Dict[str, Any]:
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    pd = room.get('pending_take')
    if not pd or pd.get('player_id') != player_id or not pd.get('allowed'):
        raise RuntimeError('no take allowed')
    if take_card not in room['hands'].get(target_player_id, []):
        raise RuntimeError('take_card not in target hand')
              
    room['hands'][target_player_id].remove(take_card)
    room['hands'].setdefault(player_id, []).append(take_card)
    room.pop('pending_take', None)
    try:
        emit_event(room_id, 'card_taken', {'by': player_id, 'from': target_player_id, 'card': take_card})
    except Exception:
        pass
    return room


def submit_give(room_id: str, player_id: str, cards: List[str]) -> Dict[str, Any]:
    """Player (富豪 or 大富豪) submits cards to give back to poorer players as configured in pending_give."""
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    pending = room.get('pending_give', {})
    cfg = pending.get(player_id)
    if not cfg or not cfg.get('allowed'):
        raise RuntimeError('no give pending for player')
    to_pid = cfg.get('to')
    count = cfg.get('count', 1)
    if not isinstance(cards, list) or len(cards) != count:
        raise RuntimeError(f'expected {count} card(s) to give')
                        
    for c in cards:
        if c not in room['hands'].get(player_id, []):
            raise RuntimeError('card not in hand')
                      
    for c in cards:
        room['hands'][player_id].remove(c)
    room['hands'].setdefault(to_pid, []).extend(cards)
                                   
    room['pending_give'].pop(player_id, None)
    try:
        emit_event(room_id, 'give_submitted', {'from': player_id, 'to': to_pid, 'cards': cards})
    except Exception:
        pass
    return room


def takeover_for_player(room_id: str, player_id: str) -> Dict[str, Any]:
    """Manually start a bot takeover for a given player_id in the room.
    This marks the player as taken_over and is_bot True so process_bots will act for them.
    Returns the updated player dict.
    """
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    p = next((x for x in room['players'] if x['id'] == player_id), None)
    if not p:
        raise KeyError('player not found')
    p['is_bot'] = True
    p['taken_over'] = True
    p['takeover_at'] = datetime.now(timezone.utc).isoformat()
    try:
        emit_event(room_id, 'player_taken_over', {'player_id': player_id, 'by_bot': True})
    except Exception:
        pass
    return p


def release_takeover(room_id: str, player_id: str) -> Dict[str, Any]:
    """Revoke a takeover previously applied (if player reconnects). This will mark the player back to human.
    Note: does not restore original hand ownership — this is a light-weight flag toggle.
    """
    room = ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    p = next((x for x in room['players'] if x['id'] == player_id), None)
    if not p:
        raise KeyError('player not found')
    p['is_bot'] = False
    p.pop('taken_over', None)
    p.pop('takeover_at', None)
    try:
        emit_event(room_id, 'player_released', {'player_id': player_id})
    except Exception:
        pass
    return p


def _apply_instant_grade_rotation(room_id: str, actor_player_id: str, rank_type: str = '4'):
    """When double-4 or double-A occurs, rotate ranks: 大富豪 -> 大貧民 (drop), 貧民->平民->富豪->... per user's description.
    We will implement a simple mapping: if someone is currently 大富豪 (rank==1), they become 大貧民 (max rank), others shift up one grade. For simplicity use finished mapping if available; otherwise apply no-op.
    """
    room = ROOMS.get(room_id)
    if not room:
        return
    finished = room.get('finished', {})
    if not finished:
                                                                                     
        try:
            emit_event(room_id, 'instant_grade_rotation', {'by': actor_player_id, 'type': rank_type})
        except Exception:
            pass
        return
                                                                           
    max_rank = max(finished.values()) if finished else 0
                             
    daifugo = next((pid for pid, r in finished.items() if r == 1), None)
    if not daifugo:
        try:
            emit_event(room_id, 'instant_grade_rotation', {'by': actor_player_id, 'type': rank_type})
        except Exception:
            pass
        return
                                             
                                                                                     
    new_finished = {}
    for pid, r in finished.items():
        if pid == daifugo:
            new_finished[pid] = max_rank
        else:
                                                                        
            new_finished[pid] = max(1, r - 1)
    room['finished'] = new_finished
    try:
        if db:
            db.record_round_results(room_id, new_finished)
    except Exception:
        pass
                   
    titled = [{'player_id': pid, 'rank': r, 'title': title_for_rank(r)} for pid, r in new_finished.items()]
    try:
        emit_event(room_id, 'instant_grade_rotation', {'by': actor_player_id, 'new_finished': new_finished, 'titled': titled})
    except Exception:
        pass


def _end_game_if_finished(room_id: str):
    """
    Check if the game is finished (all players have finished or only one left with cards).
    If finished, persist results to DB and mark room as not started (ready for next round).
    """
    room = ROOMS.get(room_id)
    if not room:
        return
                              
    finished = room.get('finished', {})
                                           
    players_with_cards = [p for p in room['players'] if len(room['hands'].get(p['id'], [])) > 0]
                                                                     
    if len(players_with_cards) == 0 and len(finished) > 0:
                                                                      
        next_rank = room.get('next_rank', 1)
        for p in room['players']:
            pid = p['id']
            if pid not in finished:
                finished[pid] = next_rank
                next_rank += 1
        room['finished'] = finished
        room['next_rank'] = next_rank
                                       
        results = [{'player_id': pid, 'rank': rank, 'title': title_for_rank(rank)} for pid, rank in finished.items()]
                                             
        try:
            if db:
                db.set_game_finished(room['id'], results)
        except Exception:
            pass
                                                                                    
        room['started'] = False
        room['game_over'] = True
                                  
        try:
            emit_event(room_id, 'game_finished', {'results': results})
        except Exception:
            pass
                                                                                     
                                                  
        room['current_turn'] = 0
        room['last_player'] = None
        room['consecutive_passes'] = 0
        return room