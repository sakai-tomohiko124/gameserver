# smoke_test.py
# Simple smoke tests using Flask test_client to verify key endpoints and game flow.

import json
import os
import sys
# ensure project root is on sys.path when running this script directly from scripts/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from api import app
from rooms import ROOMS


def run():
    client = app.test_client()

    print('GET /')
    r = client.get('/')
    print('status', r.status_code)
    assert r.status_code == 200

    print('GET /game/daifugo')
    r = client.get('/game/daifugo')
    print('status', r.status_code)
    assert r.status_code == 200

    print('POST /api/rooms -> create room')
    r = client.post('/api/rooms', json={'name': 'Tester'})
    assert r.status_code == 200
    data = r.get_json()
    room_id = data['room_id']
    player_id = data['player_id']
    print('created', room_id, player_id)

    print('POST /api/rooms/<room>/start')
    r = client.post(f'/api/rooms/{room_id}/start')
    assert r.status_code == 200
    start_data = r.get_json()
    print('start ok')

    print('GET /api/rooms/<room>/state')
    r = client.get(f'/api/rooms/{room_id}/state', query_string={'player_id': player_id})
    assert r.status_code == 200
    s = r.get_json()
    print('state players:', [p['name'] for p in s['players']])

    # try to play a card if available for our player
    your_hand = s.get('your_hand')
    if your_hand:
        card = your_hand[0]
        print('try play', card)
        r = client.post(f'/api/rooms/{room_id}/play', json={'player_id': player_id, 'cards': [card]})
        print('play status', r.status_code)
        # can be 200 or 400 depending on turn/order; just print
        try:
            print('play response', r.get_json())
        except Exception:
            print('non-json response')
    else:
        print('no cards in hand (unexpected)')

    print('Smoke test finished')


if __name__ == '__main__':
    run()
