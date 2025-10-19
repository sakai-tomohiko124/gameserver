import pytest
from rooms import create_room, start_game, play_card, pass_turn, ROOMS


def test_multiple_card_play_and_pass():
    # create room and start
    res = create_room('Taro')
    room_id = res['room']['id']
    player_id = res['player_id']
    # join 4 more players
    for i in range(4):
        join = None
        try:
            join = create_room(f'BotJoin{i}')
        except Exception:
            pass
    # Instead of using create_room for others, directly set players and hands for deterministic test
    room = ROOMS[room_id]
    # set deterministic players p0..p4
    room['players'] = [
        {'id': 'p0', 'name': 'P0', 'is_bot': False},
        {'id': 'p1', 'name': 'P1', 'is_bot': False},
        {'id': 'p2', 'name': 'P2', 'is_bot': False},
        {'id': 'p3', 'name': 'P3', 'is_bot': False},
        {'id': 'p4', 'name': 'P4', 'is_bot': False},
    ]
    # assign explicit hands so p0 has a pair of 4s
    room['hands'] = {
        'p0': ['4♠','4♥','7♠'],
        'p1': ['3♠','5♥','8♠'],
        'p2': ['3♥','6♠'],
        'p3': ['5♠','6♥'],
        'p4': ['7♥','8♥'],
    }
    room['started'] = True
    room['center'] = []
    room['current_turn'] = 0

    # Player0 plays a pair of 4s
    p0 = room['players'][0]['id']
    assert '4♠' in room['hands'][p0]
    # play two 4s
    play_card(room_id, p0, ['4♠','4♥'])
    assert room['center'] == ['4♠','4♥']

    # Next player passes
    p1 = room['players'][1]['id']
    pass_turn(room_id, p1)
    # Next passes until all others have passed => center reset and turn back to p0
    p2 = room['players'][2]['id']
    pass_turn(room_id, p2)
    p3 = room['players'][3]['id']
    pass_turn(room_id, p3)
    p4 = room['players'][4]['id']
    pass_turn(room_id, p4)

    assert room['center'] == []
    # current turn should be p0
    assert room['players'][room['current_turn']]['id'] == p0