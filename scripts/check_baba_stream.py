import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api import app

client = app.test_client()
resp = client.post('/api/babanuki/stream', json={'names': ['Alice','BOT1']})
print('status:', resp.status_code)
print(resp.get_data(as_text=True)[:400])
resp2 = client.post('/api/babanuki/stream', json={'names': ['BOT1','BOT2','BOT3']})
print('status2:', resp2.status_code)
body = resp2.get_data(as_text=True)
print('body preview:', body[:400])
