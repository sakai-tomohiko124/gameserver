import json
from rooms import create_room, ROOMS


def test_get_and_patch_rules():
    # create room
    res = create_room('Tester')
    room = res['room']
    rid = room['id']

    # initial rules exist and have expected keys
    rules = room.get('rules', {})
    assert 'spade3_over_joker' in rules

    # patch valid key
    from api import app
    client = app.test_client()
    r = client.patch(f'/api/rooms/{rid}/rules', json={'spade3_over_joker': False})
    assert r.status_code == 200
    data = r.get_json()
    assert data['rules']['spade3_over_joker'] is False

    # GET should reflect update
    g = client.get(f'/api/rooms/{rid}/rules')
    assert g.status_code == 200
    gd = g.get_json()
    assert gd['rules']['spade3_over_joker'] is False

    # patch invalid key
    b = client.patch(f'/api/rooms/{rid}/rules', json={'unknown_key': True})
    assert b.status_code == 400
