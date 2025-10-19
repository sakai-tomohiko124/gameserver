import uuid
import time
import threading
import random
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List

SHI_ROOMS: Dict[str, Dict[str, Any]] = {}
SHI_EVENTS: Dict[str, List[Dict[str, Any]]] = {}

# load candidate word lists keyed by starting kana unit (hiragana)
# Prefer an external JSON file data/shiri_words.json placed next to the project; fall back to a small built-in list.
SHI_WORDS = {}
_VOCAB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'shiri_words.json')
try:
    with open(_VOCAB_PATH, 'r', encoding='utf-8') as _f:
        SHI_WORDS = json.load(_f)
except Exception:
    # minimal fallback
    SHI_WORDS = {
        'あ': ['あさ', 'あめ', 'あお'],
        'い': ['いぬ', 'いす', 'いちご'],
        'か': ['かさ', 'かめ', 'かい'],
    }

# track scheduled bot timers to avoid duplicate scheduling
_BOT_TIMERS: Dict[str, threading.Timer] = {}
# track per-room per-player timeout timers (server-side enforcement of 60s auto-lose)
_PLAYER_TIMEOUTS: Dict[str, threading.Timer] = {}

# Small dictionary to handle natural long-vowel phonetics for common loanwords.
# Keys should be pre-normalized hiragana forms (katakana converted to hiragana).
LONG_VOWEL_DICT = {
    # katakana examples -> preferred hiragana with long vowel marker
    'らーめん': 'らーめん',
    'かれー': 'かれー',
    'こーひー': 'こーひー',
    'ぱーてぃー': 'ぱーてぃー',
    'しゅーくりーむ': 'しゅーくりーむ',
}


def emit_event(room_id: str, event_type: str, payload: Dict[str, Any]):
    # debug log
    try:
        print(f"[shiritori] emit_event room={room_id} type={event_type} payload_keys={list(payload.keys())}")
    except Exception:
        pass
    SHI_EVENTS.setdefault(room_id, []).append({"type": event_type, "payload": payload})


def pop_events(room_id: str):
    evs = SHI_EVENTS.pop(room_id, [])
    try:
        if evs:
            print(f"[shiritori] pop_events room={room_id} count={len(evs)} types={[e.get('type') for e in evs]}")
    except Exception:
        pass
    return evs


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_room(creator_name: str) -> Dict[str, Any]:
    room_id = uuid.uuid4().hex[:8]
    player_id = uuid.uuid4().hex
    room = {
        'id': room_id,
        'players': [
            {'id': player_id, 'name': creator_name, 'active': True}
        ],
        'creator': player_id,
        'started': False,
        'current_turn': 0,
        'used_words': [],
        'messages': [],
        'created_at': _now_iso(),
    }
    SHI_ROOMS[room_id] = room
    try:
        print(f"[shiritori] create_room id={room_id} creator={creator_name} player_id={player_id}")
    except Exception:
        pass
    return {'room': room, 'player_id': player_id}


def join_room(room_id: str, name: str) -> Dict[str, Any]:
    room = SHI_ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    if room.get('started'):
        raise RuntimeError('game already started')
    if len(room.get('players', [])) >= 8:
        raise RuntimeError('room full')
    pid = uuid.uuid4().hex
    room['players'].append({'id': pid, 'name': name, 'active': True})
    try:
        print(f"[shiritori] join_room room={room_id} name={name} player_id={pid}")
    except Exception:
        pass
    return {'room': room, 'player_id': pid}


def start_game(room_id: str) -> Dict[str, Any]:
    room = SHI_ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    if room.get('started'):
        return room
    if len(room.get('players', [])) < 2:
        raise RuntimeError('need at least 2 players')
    room['started'] = True
    room['used_words'] = []
    room['current_turn'] = 0
    # schedule server-side timeout for the first player (60s auto-lose)
    _schedule_player_timeout(room_id)
    emit_event(room_id, 'game_started', {'ts': _now_iso()})
    # if the first player to play is a bot, schedule its move
    try:
        players = room.get('players', [])
        if players:
            cur = players[room.get('current_turn', 0)]
            if cur.get('is_bot'):
                _schedule_bot_move(room_id, cur['id'])
    except Exception:
        pass
    return room


def _normalize_to_hiragana(s: str) -> str:
    """Normalize input to a canonical hiragana-only string used for comparisons.

    Steps:
    - NFKC normalize to collapse full-width characters
    - convert katakana to hiragana (including converting prolonged sound mark 'ー' to the
      appropriate vowel of previous kana when possible)
    - convert small kana (ゃゅょぁぃぅぇぉっ) to their large equivalents for matching
    - remove punctuation, spaces and ASCII characters
    - return resulting hiragana string (lowercase where applicable)
    """
    import unicodedata

    if not s:
        return ''
    s = unicodedata.normalize('NFKC', s.strip())
    out_chars = []

    # helper: map hiragana char -> vowel
    vowel_map = {
        # a-row
        'あ':'あ','か':'あ','が':'あ','さ':'あ','ざ':'あ','た':'あ','だ':'あ','な':'あ','は':'あ','ば':'あ','ぱ':'あ','ま':'あ','や':'あ','ら':'あ','わ':'あ',
        # i-row
        'い':'い','き':'い','ぎ':'い','し':'い','じ':'い','ち':'い','ぢ':'い','に':'い','ひ':'い','び':'い','ぴ':'い','み':'い','り':'い',
        # u-row
        'う':'う','く':'う','ぐ':'う','す':'う','ず':'う','つ':'う','づ':'う','ぬ':'う','ふ':'う','ぶ':'う','ぷ':'う','む':'う','ゆ':'う','る':'う',
        # e-row
        'え':'え','け':'え','げ':'え','せ':'え','ぜ':'え','て':'え','で':'え','ね':'え','へ':'え','べ':'え','ぺ':'え','め':'え','れ':'え',
        # o-row
        'お':'お','こ':'お','ご':'お','そ':'お','ぞ':'お','と':'お','ど':'お','の':'お','ほ':'お','ぼ':'お','ぽ':'お','も':'お','よ':'お','ろ':'お','を':'お',
        # small/others
        'ぁ':'あ','ぃ':'い','ぅ':'う','ぇ':'え','ぉ':'お','ゃ':'あ','ゅ':'う','ょ':'お','っ':'つ','ゎ':'あ','ゐ':'い','ゑ':'え','ん':'ん'
    }

    # small kana set (preserve them to treat as yoon units)
    small_kana = set(['ゃ','ゅ','ょ','ぁ','ぃ','ぅ','ぇ','ぉ','っ','ゎ'])
    # small -> large mapping
    small_to_large = {'ゃ':'や', 'ゅ':'ゆ', 'ょ':'よ', 'ぁ':'あ', 'ぃ':'い', 'ぅ':'う', 'ぇ':'え', 'ぉ':'お', 'っ':'つ', 'ゎ':'わ'}

    def kata_to_hira(ch):
        c = ord(ch)
        if 0x30A1 <= c <= 0x30F4:
            return chr(c - 0x60)
        return ch

    prev_hira = None
    # build a temporary hiragana-only key to check LONG_VOWEL_DICT
    key_candidate = ''.join(kata_to_hira(c) for c in s if not unicodedata.category(c).startswith('P') and not c.isspace())
    key_candidate = key_candidate.lower()
    if key_candidate in LONG_VOWEL_DICT:
        # use dictionary-preferred normalized form
        return LONG_VOWEL_DICT[key_candidate]

    for ch in s:
        # convert katakana to hiragana
        ch = kata_to_hira(ch)
        # skip spaces and ascii punctuation
        cat = unicodedata.category(ch)
        if cat.startswith('P') or ch.isspace():
            continue
        # handle prolonged sound mark 'ー' by copying previous vowel if possible
        if ch == 'ー' or ch == '\u30FC':
            if prev_hira and prev_hira in vowel_map:
                out_chars.append(vowel_map[prev_hira])
            continue
        # keep small kana as-is so 'きゃ' remains two-char unit ('き'+'ゃ')
        # lower-case ascii if any
        ch = ch.lower()
        # ignore ascii letters/digits
        if 'a' <= ch <= 'z' or '0' <= ch <= '9':
            continue
        out_chars.append(ch)
        prev_hira = ch

    return ''.join(out_chars)


def _first_kana_unit(word: str) -> str:
    """Return the first kana unit (single kana or combination like 'きゃ')."""
    w = _normalize_to_hiragana(word)
    if not w:
        return ''
    if len(w) >= 2 and w[1] in ('ゃ','ゅ','ょ','ぁ','ぃ','ぅ','ぇ','ぉ'):
        return w[0:2]
    return w[0]


def _last_kana_unit(word: str) -> str:
    """Return the last kana unit for shiritori comparison.

    - If ends with long vowel marker 'ー', return vowel of previous kana.
    - If ends with small kana, return previous+small as unit (e.g., 'きゃ').
    - Otherwise return last kana.
    """
    w = _normalize_to_hiragana(word)
    if not w:
        return ''
    # if ends with long vowel marker
    if w[-1] == 'ー':
        # find previous kana vowel
        if len(w) >= 2:
            prev = w[-2]
            # map prev to its vowel
            vowel_map = {
                'あ':'あ','か':'あ','が':'あ','さ':'あ','ざ':'あ','た':'あ','だ':'あ','な':'あ','は':'あ','ば':'あ','ぱ':'あ','ま':'あ','や':'あ','ら':'あ','わ':'あ',
                'い':'い','き':'い','ぎ':'い','し':'い','じ':'い','ち':'い','ぢ':'い','に':'い','ひ':'い','び':'い','ぴ':'い','み':'い','り':'い',
                'う':'う','く':'う','ぐ':'う','す':'う','ず':'う','つ':'う','づ':'う','ぬ':'う','ふ':'う','ぶ':'う','ぷ':'う','む':'う','ゆ':'う','る':'う',
                'え':'え','け':'え','げ':'え','せ':'え','ぜ':'え','て':'え','で':'え','ね':'え','へ':'え','べ':'え','ぺ':'え','め':'え','れ':'え',
                'お':'お','こ':'お','ご':'お','そ':'お','ぞ':'お','と':'お','ど':'お','の':'お','ほ':'お','ぼ':'お','ぽ':'お','も':'お','よ':'お','ろ':'お','を':'お',
            }
            return vowel_map.get(prev, prev)
        return ''
    # if ends with small kana, return previous+last as a unit
    if w[-1] in ('ゃ','ゅ','ょ','ぁ','ぃ','ぅ','ぇ','ぉ') and len(w) >= 2:
        return w[-2] + w[-1]
    return w[-1]


def _last_kana(word: str) -> str:
    """Return the normalized final kana to compare in shiritori.

    We operate on the normalized hiragana string. If the last character is a small kana
    it has been expanded already by _normalize_to_hiragana; otherwise return the last char.
    """
    w = _normalize_to_hiragana(word)
    if not w:
        return ''
    # if ends with long vowel placeholder (converted earlier), just return final char
    return w[-1]


def play_word(room_id: str, player_id: str, word: str) -> Dict[str, Any]:
    room = SHI_ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    if not room.get('started'):
        raise RuntimeError('game not started')
    players = room.get('players', [])
    # find active players order list
    active_players = [p for p in players if p.get('active')]
    if not any(p['id'] == player_id for p in players):
        raise KeyError('player not in room')
    # check turn
    cur_player = players[room.get('current_turn', 0)]
    if cur_player['id'] != player_id:
        raise RuntimeError('not your turn')
    w = word.strip()
    if not w:
        raise RuntimeError('empty word')
    # keep original for display, use normalized for logic
    norm = _normalize_to_hiragana(w)
    if not norm:
        raise RuntimeError('invalid word')
    # Use kana-unit comparison (yoon units preserved)
    start_unit = _first_kana_unit(norm)
    # used_words stored as list of {'orig': ..., 'norm': ...}
    used_objs = room.get('used_words', [])
    used_norm = [u.get('norm') for u in used_objs]
    if used_norm:
        prev_norm = used_norm[-1]
        prev_last_unit = _last_kana_unit(prev_norm)
        # If prev_last_unit is a yoon (e.g., 'きゃ'), then accept either the same yoon or the
        # corresponding large kana of the small part (e.g., 'や').
        acceptable = {prev_last_unit}
        if len(prev_last_unit) == 2 and prev_last_unit[1] in ('ゃ','ゅ','ょ','ぁ','ぃ','ぅ','ぇ','ぉ'):
            # allow 'や' for 'きゃ' etc.
            acceptable.add(prev_last_unit[1].replace('\u3099',''))
            # also allow the large form of the small kana
            mapping = {'ゃ':'や','ゅ':'ゆ','ょ':'よ','ぁ':'あ','ぃ':'い','ぅ':'う','ぇ':'え','ぉ':'お'}
            acceptable.add(mapping.get(prev_last_unit[1], prev_last_unit[1]))
        if start_unit not in acceptable:
            raise RuntimeError('word does not start with required kana')
    # check already used (normalized)
    if norm in used_norm:
        raise RuntimeError('word already used')
    # record normalized word for logic, and save original for UI
    room.setdefault('used_words', []).append({'orig': w, 'norm': norm})
    # add message
    ts = _now_iso()
    room.setdefault('messages', []).append({'id': uuid.uuid4().hex, 'player_id': player_id, 'name': next((p['name'] for p in players if p['id']==player_id), player_id), 'text': w, 'ts': ts})
    emit_event(room_id, 'word_played', {'player_id': player_id, 'word': w, 'ts': ts})
    try:
        print(f"[shiritori] play_word room={room_id} player={player_id} word={w}")
    except Exception:
        pass
    # cancel any pending player timeout for this room (player acted)
    try:
        tkey = f"{room_id}:{player_id}"
        timer = _PLAYER_TIMEOUTS.pop(tkey, None)
        if timer:
            try: timer.cancel()
            except Exception: pass
    except Exception:
        pass
    # check lose by ending in ん (U+3093)
    last = _last_kana(w)
    if last == 'ん':
        # player loses: mark inactive
        for p in players:
            if p['id'] == player_id:
                p['active'] = False
                break
        emit_event(room_id, 'player_lost', {'player_id': player_id, 'reason': 'ends with ん'})
    # advance turn to next active player
    n = len(players)
    if n == 0:
        return room
    next_idx = room.get('current_turn', 0)
    for i in range(1, n+1):
        cand = (room.get('current_turn', 0) + i) % n
        if players[cand].get('active'):
            room['current_turn'] = cand
            break
    # if next player is a bot, schedule its automated move
    try:
        next_player = room['players'][room['current_turn']]
        if next_player.get('is_bot') and room.get('started'):
            _schedule_bot_move(room_id, next_player['id'])
        else:
            # schedule server-side 60s timeout for the next human player
            _schedule_player_timeout(room_id)
    except Exception:
        pass
    # check victory (only one active left)
    active_count = sum(1 for p in players if p.get('active'))
    if active_count <= 1:
        winner = next((p for p in players if p.get('active')), None)
        emit_event(room_id, 'game_over', {'winner': winner and winner['id']})
        room['started'] = False
    return room


def _schedule_bot_move(room_id: str, bot_player_id: str, delay_range=(1.0, 2.5)):
    """Schedule a bot move after a short randomized delay. If already scheduled, ignore."""
    # avoid scheduling multiple timers for same room
    if _BOT_TIMERS.get(room_id):
        return

    delay = random.uniform(*delay_range)

    def worker():
        try:
            # ensure room and bot still valid
            room = SHI_ROOMS.get(room_id)
            if not room or not room.get('started'):
                return
            # confirm it's bot's turn
            cur_idx = room.get('current_turn', 0)
            cur = room['players'][cur_idx]
            if cur['id'] != bot_player_id or not cur.get('is_bot') or not cur.get('active'):
                return

            # indicate typing started
            try:
                emit_event(room_id, 'bot_typing_start', {'player_id': bot_player_id})
            except Exception:
                pass

            # small typing delay
            typing_delay = random.uniform(0.6, 1.6)
            threading.Event().wait(typing_delay)

            # determine required starting unit
            used = room.get('used_words', [])
            if used:
                prev_norm = used[-1].get('norm') if isinstance(used[-1], dict) else used[-1]
                start_unit = _last_kana_unit(prev_norm)
            else:
                start_unit = None

            # pick candidate words
            candidate = None
            used_norm = [u.get('norm') for u in room.get('used_words', []) if isinstance(u, dict)]
            if start_unit:
                # try candidates starting with start_unit
                pool = SHI_WORDS.get(start_unit, [])[:]
                random.shuffle(pool)
                for w in pool:
                    # normalize w to check not used
                    nw = _normalize_to_hiragana(w)
                    if nw and nw not in used_norm:
                        candidate = w
                        break
            if not candidate:
                # fallback: choose any word whose norm not used
                all_words = [w for words in SHI_WORDS.values() for w in words]
                random.shuffle(all_words)
                for w in all_words:
                    nw = _normalize_to_hiragana(w)
                    if nw and nw not in used_norm:
                        candidate = w
                        break
            if not candidate:
                # last resort: construct synthetic word from start_unit
                if start_unit:
                    candidate = start_unit + 'あ'
                else:
                    candidate = 'しりとり'

            # attempt play
            try:
                play_word(room_id, bot_player_id, candidate)
                try:
                    emit_event(room_id, 'bot_typing_stop', {'player_id': bot_player_id, 'word': candidate})
                except Exception:
                    pass
            except Exception:
                # if bot fails, mark inactive and emit failure
                try:
                    for p in room.get('players', []):
                        if p['id'] == bot_player_id:
                            p['active'] = False
                            break
                    emit_event(room_id, 'bot_failed', {'bot_id': bot_player_id, 'word': candidate})
                except Exception:
                    pass
        finally:
            # clear timer record
            try:
                _BOT_TIMERS.pop(room_id, None)
            except Exception:
                pass

    t = threading.Timer(delay, worker)
    _BOT_TIMERS[room_id] = t
    t.daemon = True
    t.start()


def _schedule_player_timeout(room_id: str, timeout_seconds: int = 60):
    """Schedule a server-side timeout for the current player in the room.

    If the player does not play within timeout_seconds, they are marked inactive (lost)
    and appropriate events are emitted. Existing timeout for that room/player will be
    cancelled when the player acts.
    """
    room = SHI_ROOMS.get(room_id)
    if not room or not room.get('started'):
        return
    players = room.get('players', [])
    if not players:
        return
    cur_idx = room.get('current_turn', 0)
    cur = players[cur_idx]
    if not cur or not cur.get('active'):
        return

    # cancel any existing timeout for this room
    # timeouts keyed by room:playerid
    try:
        # remove previous timers for this room
        to_remove = [k for k in list(_PLAYER_TIMEOUTS.keys()) if k.startswith(room_id+':')]
        for k in to_remove:
            t = _PLAYER_TIMEOUTS.pop(k, None)
            if t:
                try: t.cancel()
                except Exception: pass
    except Exception:
        pass

    player_id = cur['id']
    key = f"{room_id}:{player_id}"

    def timeout_worker():
        # re-check room and current turn validity
        try:
            r = SHI_ROOMS.get(room_id)
            if not r or not r.get('started'):
                return
            # if player already inactive, nothing to do
            p = next((pp for pp in r.get('players', []) if pp['id']==player_id), None)
            if not p or not p.get('active'):
                return
            # mark player inactive (lost)
            p['active'] = False
            emit_event(room_id, 'player_lost', {'player_id': player_id, 'reason': 'timeout'})
            # advance turn to next active player
            n = len(r.get('players', []))
            if n:
                for i in range(1, n+1):
                    cand = (r.get('current_turn', 0) + i) % n
                    if r['players'][cand].get('active'):
                        r['current_turn'] = cand
                        break
            # if next player is a bot, schedule bot move
            try:
                next_player = r['players'][r['current_turn']]
                if next_player.get('is_bot') and r.get('started'):
                    _schedule_bot_move(room_id, next_player['id'])
                else:
                    # schedule next human timeout
                    _schedule_player_timeout(room_id)
            except Exception:
                pass
            # if only one active left, end game
            active_count = sum(1 for p in r.get('players', []) if p.get('active'))
            if active_count <= 1:
                winner = next((p for p in r.get('players', []) if p.get('active')), None)
                emit_event(room_id, 'game_over', {'winner': winner and winner['id']})
                r['started'] = False
        finally:
            # cleanup timer entry
            try: _PLAYER_TIMEOUTS.pop(key, None)
            except Exception: pass

    t = threading.Timer(timeout_seconds, timeout_worker)
    t.daemon = True
    _PLAYER_TIMEOUTS[key] = t
    t.start()


def get_room_state(room_id: str, player_id: str = None) -> Dict[str, Any]:
    room = SHI_ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    # include is_bot flag so clients can show bot entries
    public_players = [{'id': p['id'], 'name': p['name'], 'active': p.get('active', True), 'is_bot': p.get('is_bot', False)} for p in room['players']]
    your_id = player_id
    # prepare used_words for UI: show original words (most recent first)
    used_for_ui = [u.get('orig') if isinstance(u, dict) else u for u in room.get('used_words', [])]
    return {
        'id': room['id'],
        'players': public_players,
        'started': room.get('started', False),
        'current_turn': room.get('current_turn', 0),
        'used_words': list(used_for_ui),
        'your_id': your_id,
        'messages': list(room.get('messages', [])),
    }


def add_message(room_id: str, player_id: str, text: str) -> Dict[str, Any]:
    room = SHI_ROOMS.get(room_id)
    if not room:
        raise KeyError('room not found')
    ts = _now_iso()
    msg = {'id': uuid.uuid4().hex, 'player_id': player_id, 'name': next((p['name'] for p in room['players'] if p['id']==player_id), player_id), 'text': text, 'ts': ts}
    room.setdefault('messages', []).append(msg)
    emit_event(room_id, 'message', msg)
    return msg
