from rooms import create_room, ROOMS, play_card, pass_turn


def test_straight_play_and_compare():
    res = create_room('Alice')
    room_id = res['room']['id']
    room = ROOMS[room_id]
    # deterministic players
    room['players'] = [ {'id':'p0','name':'P0','is_bot':False}, {'id':'p1','name':'P1','is_bot':False}, {'id':'p2','name':'P2','is_bot':False} ]
    # hands: p0 has a straight 3-4-5 of spades, p1 has 4-5-6 of hearts
    room['hands'] = {
        'p0': ['3♠','4♠','5♠'],
        'p1': ['4♥','5♥','6♥'],
        'p2': ['7♣']
    }
    room['started'] = True
    room['center'] = []
    room['current_turn'] = 0

    # p0 plays straight 3-4-5 spades
    play_card(room_id, 'p0', ['3♠','4♠','5♠'])
    assert room['center'] == ['3♠','4♠','5♠']
    # Because the play contains a 5, the next player (p1) is skipped.
    # Attempting to play as p1 should fail because it's not their turn.
    try:
        play_card(room_id, 'p1', ['4♥','5♥','6♥'])
        assert False, 'p1 should have been skipped and not allowed to play'
    except RuntimeError:
        pass

    # p2 cannot play (only single card), so pass
    pass_turn(room_id, 'p2')
    # Now it's p0's turn again; p0 cannot play a lower straight
    try:
        play_card(room_id, 'p0', ['3♠','4♠','5♠'])
        assert False, 'should not be able to play lower straight'
    except RuntimeError:
        pass