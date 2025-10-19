import random
from typing import List, Dict, Any


def _make_deck() -> List[Dict[str, Any]]:
    # ranks 1-13, four suits, plus one Joker named 'ザコ'
    suits = ['♠', '♥', '♦', '♣']
    ranks = [str(i) for i in range(1, 14)]
    deck = []
    for r in ranks:
        for s in suits:
            deck.append({'rank': r, 'suit': s, 'name': f'{r}{s}'})
    # single joker
    deck.append({'rank': 'JOKER', 'suit': None, 'name': 'ザコ'})
    return deck


def _remove_pairs(hand: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # remove pairs by rank (only for non-JOKER ranks)
    by_rank = {}
    for c in hand:
        by_rank.setdefault(c['rank'], []).append(c)
    new_hand = []
    for rank, cards in by_rank.items():
        if rank == 'JOKER':
            new_hand.extend(cards)
            continue
        # if odd count, leave one card
        if len(cards) % 2 == 1:
            new_hand.append(cards[0])
    # shuffle to avoid ordering bias
    random.shuffle(new_hand)
    return new_hand


def simulate(names: List[str]) -> Dict[str, Any]:
    """Simulate a simple ババ抜き game.

    - Ensure at least 3 players by adding bots named BOT1/BOT2...
    - Deal a 52+J deck evenly in round-robin
    - Remove initial pairs from each hand
    - Players in turn draw a random card from next alive player
    - Remove pairs when formed
    - When a player's hand becomes empty they are finished and skipped
    - Continue until one player remains; that player holding the Joker ('ザコ') is the loser

    Returns a dict with keys: players (list), log (list of strings), final_hands (map), loser (name)
    """
    log = []
    # ensure at least 3 players
    players = []
    for i, n in enumerate(names, start=1):
        players.append({'id': f'p{i}', 'name': n, 'is_bot': False})
    bot_idx = 1
    while len(players) < 3:
        players.append({'id': f'bot{bot_idx}', 'name': f'BOT{bot_idx}', 'is_bot': True})
        bot_idx += 1

    # prepare deck and deal
    deck = _make_deck()
    random.shuffle(deck)
    hands = {p['id']: [] for p in players}
    pid_list = [p['id'] for p in players]
    # round robin deal
    i = 0
    for card in deck:
        hands[pid_list[i % len(pid_list)]].append(card)
        i += 1

    # initial pair removal
    for pid in pid_list:
        before = len(hands[pid])
        hands[pid] = _remove_pairs(hands[pid])
        removed = before - len(hands[pid])
        if removed:
            log.append(f"{_name_for_pid(pid, players)} は初期の{removed}枚の組を捨てました")

    alive = [p['id'] for p in players if len(hands[p['id']]) > 0]
    # players who already emptied their hands are considered finished
    turn_idx = 0
    # Protect against pathological infinite loops by a high iteration cap
    cap = 10000
    iter_count = 0
    while len(alive) > 1 and iter_count < cap:
        iter_count += 1
        pid = alive[turn_idx % len(alive)]
        # determine next player to draw from
        if len(alive) == 1:
            break
        next_idx = (turn_idx + 1) % len(alive)
        target_pid = alive[next_idx]
        # if target has no cards (shouldn't be in alive), skip
        if not hands.get(target_pid):
            # remove from alive
            alive.pop(next_idx)
            if next_idx < turn_idx:
                turn_idx -= 1
            continue

        # draw a random card from target
        drawn = random.choice(hands[target_pid])
        hands[target_pid].remove(drawn)
        log.append(f"{_name_for_pid(pid, players)} は { _name_for_pid(target_pid, players)} から 1枚引きました ({drawn['name']})")

        # check for pair in pid's hand
        pair_found = None
        for c in list(hands[pid]):
            if c['rank'] == drawn['rank'] and c['rank'] != 'JOKER':
                pair_found = c
                break
        if pair_found:
            hands[pid].remove(pair_found)
            # drawn is paired and removed
            log.append(f"{_name_for_pid(pid, players)} は {pair_found['name']} と {drawn['name']} の組を作り捨てました")
        else:
            hands[pid].append(drawn)

        # if target has become empty, they finish
        if len(hands[target_pid]) == 0:
            # remove target from alive
            log.append(f"{_name_for_pid(target_pid, players)} は手札がなくなり上がりました")
            alive.pop(next_idx)
            # if next_idx < turn_idx adjust
            if next_idx < turn_idx:
                turn_idx -= 1

        # if current player has emptied hand, remove them as well
        if len(hands[pid]) == 0:
            log.append(f"{_name_for_pid(pid, players)} は手札がなくなり上がりました")
            # find pid index in alive (might have been shifted)
            try:
                rem_idx = alive.index(pid)
                alive.pop(rem_idx)
                if rem_idx <= turn_idx and turn_idx > 0:
                    turn_idx -= 1
            except ValueError:
                pass
        else:
            # advance only if current player still alive (they keep turn order)
            turn_idx += 1

    # determine loser: the one who remains with the Joker
    final_hands = { _name_for_pid(pid, players): [c['name'] for c in hands.get(pid, [])] for pid in pid_list }
    loser = None
    for pid in pid_list:
        for c in hands.get(pid, []):
            if c['rank'] == 'JOKER':
                loser = _name_for_pid(pid, players)
                break
        if loser:
            break

    if not loser and alive:
        # fallback: last alive
        loser = _name_for_pid(alive[0], players)

    return {'players': players, 'log': log, 'final_hands': final_hands, 'loser': loser}


def _name_for_pid(pid: str, players: List[Dict[str, Any]]) -> str:
    for p in players:
        if p['id'] == pid:
            return p['name']
    return pid


def simulate_stream(names: List[str], bot_difficulties: Dict[str, str] = None, thinking_seconds: int = 5):
    """Generator that yields event dicts for SSE streaming.

    Events yielded are dicts containing at least a 'type' key. Types used:
    - 'log': one-line text progress
    - 'thinking': indicates a bot is thinking with seconds
    - 'finish': final summary with final_hands and loser
    """
    import time

    bot_difficulties = bot_difficulties or {}

    # prepare players and ensure >=3
    players = []
    for i, n in enumerate(names, start=1):
        players.append({'id': f'p{i}', 'name': n, 'is_bot': False})
    bot_idx = 1
    while len(players) < 3:
        players.append({'id': f'bot{bot_idx}', 'name': f'BOT{bot_idx}', 'is_bot': True})
        bot_idx += 1

    # prepare deck and deal
    deck = _make_deck()
    random.shuffle(deck)
    hands = {p['id']: [] for p in players}
    pid_list = [p['id'] for p in players]
    i = 0
    for card in deck:
        hands[pid_list[i % len(pid_list)]].append(card)
        i += 1

    # initial pair removal
    for pid in pid_list:
        before = len(hands[pid])
        hands[pid] = _remove_pairs(hands[pid])
        removed = before - len(hands[pid])
        if removed:
            yield {'type': 'log', 'text': f"{_name_for_pid(pid, players)} は初期の{removed}枚の組を捨てました"}

    # emit initial state
    def _build_state():
        lst = []
        for p in players:
            pid = p['id']
            lst.append({
                'id': pid,
                'name': p['name'],
                'is_bot': bool(p.get('is_bot')),
                'count': len(hands.get(pid, [])),
                # reveal full hand only for non-bot in this simple UI
                'hand': [c['name'] for c in hands.get(pid, [])] if not p.get('is_bot') else []
            })
        return lst

    yield {'type': 'state', 'players': _build_state(), 'turn': None}

    alive = [p['id'] for p in players if len(hands[p['id']]) > 0]
    turn_idx = 0
    cap = 10000
    iter_count = 0
    while len(alive) > 1 and iter_count < cap:
        iter_count += 1
        pid = alive[turn_idx % len(alive)]
        if len(alive) == 1:
            break
        next_idx = (turn_idx + 1) % len(alive)
        target_pid = alive[next_idx]

        # if target has no cards, remove them
        if not hands.get(target_pid):
            try:
                alive.pop(next_idx)
            except Exception:
                pass
            if next_idx < turn_idx:
                turn_idx -= 1
            continue

        # If current player is a bot, simulate thinking
        cur_player = next((p for p in players if p['id'] == pid), None)
        is_bot = bool(cur_player and cur_player.get('is_bot'))
        difficulty = bot_difficulties.get(pid) if bot_difficulties else None
        if is_bot:
            # announce thinking with per-second ticks so client can animate countdown
            for s in range(thinking_seconds, 0, -1):
                yield {'type': 'thinking', 'player': _name_for_pid(pid, players), 'seconds': s}
                time.sleep(1)

        # Choose a card from the target according to difficulty
        chosen = None
        target_hand = hands[target_pid]
        # defensive copy
        cand = list(target_hand)
        if is_bot:
            diff = difficulty or bot_difficulties.get(cur_player['name']) or 'ふつう'
            # strong: prefer to give the bot a card that matches ranks in its own hand (to form pair)
            if diff == '強い':
                own_ranks = {c['rank'] for c in hands[pid] if c['rank'] != 'JOKER'}
                # find card in target whose rank is in own_ranks and is not Joker
                match = next((c for c in cand if c['rank'] in own_ranks and c['rank'] != 'JOKER'), None)
                if match:
                    chosen = match
            # normal: avoid picking Joker if possible
            if chosen is None and diff in ('ふつう', '強い'):
                non_jokers = [c for c in cand if c['rank'] != 'JOKER']
                if non_jokers:
                    chosen = random.choice(non_jokers)
            # weak: pick completely random
            if chosen is None:
                chosen = random.choice(cand)
        else:
            # human (simulated): pick random
            chosen = random.choice(cand)

        # perform draw
        hands[target_pid].remove(chosen)
        yield {'type': 'log', 'text': f"{_name_for_pid(pid, players)} は {_name_for_pid(target_pid, players)} から 1枚引きました ({chosen['name']})"}

        # check for pair in pid's hand
        pair_found = None
        for c in list(hands[pid]):
            if c['rank'] == chosen['rank'] and c['rank'] != 'JOKER':
                pair_found = c
                break
        if pair_found:
            hands[pid].remove(pair_found)
            yield {'type': 'log', 'text': f"{_name_for_pid(pid, players)} は {pair_found['name']} と {chosen['name']} の組を作り捨てました"}
        else:
            hands[pid].append(chosen)

        # if target has become empty
        if len(hands[target_pid]) == 0:
            yield {'type': 'log', 'text': f"{_name_for_pid(target_pid, players)} は手札がなくなり上がりました"}
            try:
                alive.pop(next_idx)
            except Exception:
                pass
            if next_idx < turn_idx:
                turn_idx -= 1

        # if current player has emptied hand
        if len(hands[pid]) == 0:
            yield {'type': 'log', 'text': f"{_name_for_pid(pid, players)} は手札がなくなり上がりました"}
            try:
                rem_idx = alive.index(pid)
                alive.pop(rem_idx)
                if rem_idx <= turn_idx and turn_idx > 0:
                    turn_idx -= 1
            except ValueError:
                pass
        else:
            turn_idx += 1

    # final
    final_hands = { _name_for_pid(pid, players): [c['name'] for c in hands.get(pid, [])] for pid in pid_list }
    loser = None
    for pid in pid_list:
        for c in hands.get(pid, []):
            if c['rank'] == 'JOKER':
                loser = _name_for_pid(pid, players)
                break
        if loser:
            break
    if not loser and alive:
        loser = _name_for_pid(alive[0], players)

    yield {'type': 'finish', 'final_hands': final_hands, 'loser': loser}
