import pytest
from rooms import make_deck, _is_straight, _straight_top_idx, _play_meta, ROOMS, create_room


def test_joker_as_wild_simple_straight():
    # 10♠, JOKER, Q♠ should be a straight with top Q index
    cards = ['10♠', 'JOKER', 'Q♠']
    assert _is_straight(cards) is True
    top = _straight_top_idx(cards)
    # Q index is 9 in order ['3'..'2'] -> but helper returns numeric index; ensure top is >= index of Q (9)
    assert top >= 9


def test_all_jokers_straight():
    cards = ['JOKER', 'JOKER', 'JOKER']
    assert _is_straight(cards) is True
    top = _straight_top_idx(cards)
    assert top == 12  # highest possible top (2)


def test_joker_invalid_different_suits():
    # non-joker cards must share suit; here suits differ -> invalid
    cards = ['10♠', 'JOKER', 'Q♥']
    assert _is_straight(cards) is False


def test_mass_discard_effect_and_event():
    # simulate a room and perform mass_discard via play_card path
    # create simple room with two players
    r = create_room('Alice')
    room = r['room']
    p1 = r['player_id']
    # add second player
    import uuid
    p2 = uuid.uuid4().hex
    room['players'].append({'id': p2, 'name': 'Bot', 'is_bot': True})
    # setup hands: give both players some '5' and other cards
    room['started'] = True
    room['hands'][p1] = ['3♠', 'Q♠']
    room['hands'][p2] = ['Q♥', '4♦']
    # player 1 plays a Q (mass_discard) and targets 'Q'
    from rooms import play_card, pop_events
    # playing a single Q as set should be allowed when center empty
    # represent card as 'Q♠' in hand
    res = play_card(room['id'], p1, ['Q♠'], target_rank='Q')
    # after mass_discard, p2 should have discarded their Q (Q♥)
    assert 'Q♥' not in room['hands'][p2]
    # check room events contain a mass_discard event
    evts = pop_events(room['id'])
    types = [e['type'] for e in evts]
    assert 'mass_discard' in types
