// Improved client for しりとり game
let roomId = null
let playerId = null
let es = null
let reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 30 * 1000
// client-side per-turn visual countdown (seconds shown to the user)
const CLIENT_TURN_SECONDS = 5
let clientTurnInterval = null
let clientTurnRemaining = 0

function el(id){ return document.getElementById(id) }

function toast(msg, short=true){
  const t = document.createElement('div')
  t.className = 'toast show'
  t.textContent = msg
  document.body.appendChild(t)
  setTimeout(()=>{ t.classList.remove('show'); try{ t.remove() }catch(e){} }, short?2000:3500)
}

function appendMessage(obj){
  // deprecated: keep for some callers but route to chat append
  appendChat(obj)
}

function appendChat(obj){
  const list = el('messages')
  const line = document.createElement('div')
  line.className = 'chat-line'
  const time = obj.ts ? new Date(obj.ts).toLocaleTimeString() : (new Date()).toLocaleTimeString()
  line.innerHTML = `<span class="chat-time">${escapeHtml(time)}</span><strong>${escapeHtml(obj.name||obj.player_id)}</strong>: ${escapeHtml(obj.text||'')}`
  list.appendChild(line)
  list.scrollTop = list.scrollHeight
}

function appendWord(wordObj){
  // wordObj: {player_id, word, ts, name}
  const list = el('used_words')
  const d = document.createElement('div')
  const time = wordObj.ts ? new Date(wordObj.ts).toLocaleTimeString() : (new Date()).toLocaleTimeString()
  d.textContent = `[${time}] ${wordObj.name || wordObj.player_id}: ${wordObj.word}`
  list.appendChild(d)
  list.scrollTop = list.scrollHeight
}

function escapeHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }

async function createRoom(){
  const name = el('name').value || 'Player'
  const resp = await fetch('/api/shiritori', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})})
  const data = await resp.json()
  if (data.error){ return alert(data.error) }
  roomId = data.room_id
  playerId = data.player_id
  el('room_id').textContent = roomId
  toast('ルーム作成: ' + roomId)
  connectEvents()
  refreshState()
  // set invite link (assume same host/port)
  try{
    const url = new URL(window.location.href)
    url.pathname = '/game/shiritori'
    url.searchParams.set('room', roomId)
    const input = el('invite_link')
    if (input) input.value = url.toString()
  }catch(e){}
}

async function joinRoom(){
  const id = el('join_room').value
  const name = el('name').value || 'Player'
  const resp = await fetch(`/api/shiritori/${encodeURIComponent(id)}/join`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})})
  const data = await resp.json()
  if (data.error){ alert(data.error); return }
  roomId = data.room_id
  playerId = data.player_id
  el('room_id').textContent = roomId
  toast('参加: ' + roomId)
  connectEvents()
  refreshState()
  // set invite link as well
  try{ const input = el('invite_link'); if (input) input.value = window.location.origin + '/game/shiritori?room=' + encodeURIComponent(roomId) }catch(e){}
}

async function startGame(){
  if (!roomId) return alert('room id required')
  const resp = await fetch(`/api/shiritori/${encodeURIComponent(roomId)}/start`, {method:'POST'})
  const data = await resp.json()
  if (data.error) return alert(data.error)
  toast('ゲーム開始')
  refreshState()
}

function setSseStatus(connected){
  const elst = el('sse_status')
  if (!elst) return
  if (connected){ elst.className = 'sse-status sse-connected'; elst.textContent = '接続中' }
  else { elst.className = 'sse-status sse-disconnected'; elst.textContent = '切断中' }
}

function scheduleReconnect(){
  reconnectAttempts += 1
  const delay = Math.min(1000 * Math.pow(1.8, reconnectAttempts), MAX_RECONNECT_DELAY)
  setSseStatus(false)
  el('reconnect_info').textContent = `再接続試行 #${reconnectAttempts} (約 ${(delay/1000).toFixed(1)}s 後)`
  setTimeout(()=>{
    if (!roomId) return
    connectEvents()
  }, delay)
}

function connectEvents(){
  if (!roomId) return
  if (es){ try{ es.close() }catch(e){} es = null }
  try{
    es = new EventSource(`/api/shiritori/${encodeURIComponent(roomId)}/events`)
  }catch(e){ scheduleReconnect(); return }
  es.onopen = ()=>{ reconnectAttempts = 0; setSseStatus(true); el('reconnect_info').textContent = '' ; toast('SSE接続しました') }
  es.onerror = (ev)=>{ try{ es.close() }catch(e){} scheduleReconnect() }
  es.addEventListener('word_played', e=>{ const d = safeParse(e.data); console.log('SSE word_played', d); appendChat({name: getPlayerName(d.player_id), text: d.word, ts: d.ts}); refreshState() })
  es.addEventListener('player_lost', e=>{ const d = safeParse(e.data); appendChat({name:getPlayerName(d.player_id), text:'負けました'}); refreshState() })
  es.addEventListener('game_over', e=>{ const d = safeParse(e.data); appendMessage({name:'system', text:'ゲーム終了'}); refreshState() })
  es.addEventListener('message', e=>{ const d = safeParse(e.data); appendChat(d); })
  es.addEventListener('game_started', e=>{ appendMessage({name:'system', text:'ゲーム開始'}); refreshState() })

  // debug logging for other events
  es.addEventListener('word_played', e=>{ /* also logged above */ })
  es.addEventListener('player_lost', e=>{ console.log('SSE player_lost', safeParse(e.data)) })
  es.addEventListener('game_over', e=>{ console.log('SSE game_over', safeParse(e.data)) })
  // clear client-side countdown when bot stops or other events arrive
  es.addEventListener('bot_typing_stop', e=>{ if (clientTurnInterval){ clearInterval(clientTurnInterval); clientTurnInterval = null } try{ const ts = el('turn_status'); if (ts) ts.textContent = '' }catch(e){} })
}

function safeParse(s){ try{ return JSON.parse(s) }catch(e){ return {} } }

function getPlayerName(pid){ if(!pid) return pid; try{ const list = Array.from(document.querySelectorAll('#player_list li')); for(const li of list){ if(li.dataset.pid===pid) return li.dataset.name } }catch(e){} return pid }

async function refreshState(){
  if (!roomId) return
  try{
    const resp = await fetch(`/api/shiritori/${encodeURIComponent(roomId)}/state?player_id=${encodeURIComponent(playerId||'')}`)
    if (!resp.ok){
      // room not found or other error
      try{
        const err = await resp.json()
        toast(err.error || ('状態取得エラー: ' + resp.status), false)
      }catch(e){ toast('状態取得でエラーが発生しました', false) }
      // stop SSE and clear local room state
      try{ if (es){ try{ es.close() }catch(e){} es = null } }catch(e){}
      // clear UI
      try{ el('player_list').innerHTML = ''; el('messages').innerHTML=''; el('used_words').innerHTML=''; el('room_id').textContent = '' }catch(e){}
      roomId = null
      playerId = null
      return
    }
    const st = await resp.json()
    // players: render into narrow player list, show bots with small marker
    const pl = el('player_list')
    if (pl){
      pl.innerHTML = ''
      (st.players||[]).forEach((p, idx)=>{
        const li = document.createElement('li')
        li.dataset.pid = p.id
        li.dataset.name = p.name
        li.style.padding = '6px'
        li.style.borderBottom = '1px solid #eee'
        li.textContent = p.name + (p.active ? '' : ' (脱落)')
        if (p.is_bot){
          const b = document.createElement('span')
          b.textContent = ' BOT'
          b.style.fontSize = '12px'
          b.style.color = '#666'
          b.style.marginLeft = '6px'
          li.appendChild(b)
        }
        if (st.current_turn === idx){ li.className = 'current-turn'; li.insertAdjacentHTML('beforeend', ' <span class="badge">あなたの番</span>') }
        pl.appendChild(li)
      })
    }
    // used words
    const uw = el('used_words')
    uw.innerHTML = ''
    (st.used_words||[]).slice(-30).reverse().forEach(w=>{ const d=document.createElement('div'); d.textContent = w; uw.appendChild(d) })
    // messages
    const msgs = el('messages')
    msgs.innerHTML = ''
    (st.messages||[]).forEach(m=> appendMessage(m))
    
      // client-side per-turn countdown: if it's your turn, start a short visual timer
      try{
        // clear existing interval
        if (clientTurnInterval){ clearInterval(clientTurnInterval); clientTurnInterval = null }
        const isYourTurn = st.started && st.players && st.players[st.current_turn] && st.players[st.current_turn].id === playerId && st.players[st.current_turn].active
        // ensure a UI element exists to show turn countdown
        let ts = el('turn_status')
        if (!ts){ ts = document.createElement('div'); ts.id = 'turn_status'; ts.style.marginTop = '6px'; ts.style.fontWeight = '700'; ts.style.color = '#064e63'; const container = el('bot-status') || msgs; container.insertAdjacentElement('afterend', ts) }
        if (isYourTurn){
          clientTurnRemaining = CLIENT_TURN_SECONDS
          ts.textContent = `あなたの番 — 残り ${clientTurnRemaining}s`;
          // enable input while countdown running
          el('play').disabled = false
          el('word').disabled = false
          clientTurnInterval = setInterval(()=>{
            clientTurnRemaining -= 1
            if (clientTurnRemaining <= 0){
              clearInterval(clientTurnInterval); clientTurnInterval = null
              ts.textContent = `時間切れ — サーバーは1分で失格を判定します`;
              // after the short visual window, disable the play UI to indicate missed fast turn
              try{ el('play').disabled = true; el('word').disabled = true }catch(e){}
            }else{
              ts.textContent = `あなたの番 — 残り ${clientTurnRemaining}s`;
            }
          }, 1000)
        }else{
          // hide/clear
          ts.textContent = ''
          try{ el('play').disabled = false; el('word').disabled = false }catch(e){}
        }
      }catch(e){ console.error('turn countdown error', e) }
  }catch(e){ console.error(e) }
}

async function playWord(){
  if (!roomId || !playerId) return alert('先にルームに参加してください')
  const word = el('word').value
  if (!word) return
  const resp = await fetch(`/api/shiritori/${encodeURIComponent(roomId)}/play`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id:playerId, word})})
  const data = await resp.json()
  if (data.error) { alert(data.error); return }
  el('word').value = ''
  refreshState()
}

async function sendMessage(){
  if (!roomId || !playerId) return
  const t = el('chat').value
  if (!t) return
  await fetch(`/api/shiritori/${encodeURIComponent(roomId)}/message`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id:playerId, text:t})})
  el('chat').value=''
}

window.addEventListener('load', ()=>{
  el('create').addEventListener('click', createRoom)
  el('join').addEventListener('click', joinRoom)
  el('start').addEventListener('click', startGame)
  el('play').addEventListener('click', playWord)
  el('sendmsg').addEventListener('click', sendMessage)
  // periodic state refresh to keep UI in sync
  setInterval(()=>{ if (roomId) refreshState() }, 3000)
  // copy invite button
  try{
    const cb = el('copy_invite')
    if (cb){ cb.addEventListener('click', async ()=>{ const input = el('invite_link'); if (!input) return; try{ await navigator.clipboard.writeText(input.value||''); toast('招待リンクをコピーしました'); }catch(e){ // fallback
        input.select(); document.execCommand('copy'); toast('招待リンクをコピーしました'); } }) }
  }catch(e){}
  // prefill join_room from query param ?room=xxxx if present and offer auto-join with confirmation
  try{
    const params = new URL(window.location.href).searchParams
    const r = params.get('room')
    if (r){ 
      const jr = el('join_room'); if (jr) jr.value = r
      // show a confirmation dialog for security before auto-joining
      const nameVal = (el('name') && el('name').value) ? el('name').value : 'Player'
      const msg = `招待リンクを検出しました。\nルーム「${r}」に参加しますか？\n参加者名: ${nameVal}\n\nOKで参加、キャンセルで中止します。`
      if (window.confirm(msg)){
        // perform join (uses join_room input and name input)
        try{ joinRoom() }catch(e){}
      }
    }
  }catch(e){}
})
