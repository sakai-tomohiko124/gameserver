// daifugo.js - client that talks to server-side rooms API
document.addEventListener('DOMContentLoaded', ()=>{
    const createBtn = document.getElementById('createRoom');
    const joinBtn = document.getElementById('joinRoom');
    const startBtn = document.getElementById('startGame');
    const playerNameInput = document.getElementById('playerName');
    const roomIdInput = document.getElementById('roomIdInput');
    const inviteArea = document.getElementById('inviteArea');
    const playersList = document.getElementById('playersList');
    const handRow = document.getElementById('handRow');
    const centerPile = document.getElementById('centerPile');

    let roomId = null;
    let playerId = null;
    let pollHandle = null;
    // polling intervals (ms)
    let pollIntervalMs = 2000; // online default
    const POLL_ONLINE = 2000;
    const POLL_OFFLINE = 800;
    // seen message ids to avoid duplicates across SSE and polling
    if(!window.__seenMessageIds) window.__seenMessageIds = new Set();
    let selectedCards = new Set();
    let evtSource = null;

    function connectSSE(){
        if(!roomId) return;
        // close existing
        try{ if(evtSource) evtSource.close(); }catch(e){}
        evtSource = new EventSource(`/api/rooms/${roomId}/events`);
        evtSource.addEventListener('open', ()=>{
            console.log('SSE open');
            const s = document.getElementById('sseStatus');
            if(s){ s.textContent = 'SSE: 接続中'; s.classList.remove('sse-disconnected'); s.classList.add('sse-connected'); }
            // when SSE opens, restore online poll interval
            if(pollIntervalMs !== POLL_ONLINE){
                pollIntervalMs = POLL_ONLINE;
                if(pollHandle) { clearInterval(pollHandle); pollHandle = setInterval(pollState, pollIntervalMs); }
            }
        });
        evtSource.addEventListener('error', (e)=>{
            console.warn('SSE error', e);
            const s = document.getElementById('sseStatus');
            if(s){ s.textContent = 'SSE: 切断（再接続中）'; s.classList.remove('sse-connected'); s.classList.add('sse-disconnected'); }
            // attempt reconnect after delay
            try{ evtSource.close(); }catch(_){ }
            // if SSE is repeatedly failing, use offline poll interval to be more responsive
            if(pollIntervalMs !== POLL_OFFLINE){ pollIntervalMs = POLL_OFFLINE; if(pollHandle){ clearInterval(pollHandle); pollHandle = setInterval(pollState, pollIntervalMs); } }
            setTimeout(()=>{ if(roomId) connectSSE(); }, 1500);
        });
        evtSource.addEventListener('close', ()=>{
            const s = document.getElementById('sseStatus');
            if(s){ s.textContent = 'SSE: 切断'; s.classList.remove('sse-connected'); s.classList.add('sse-disconnected'); }
        });
        evtSource.addEventListener('player_finished', e=>{
            try{
                const payload = JSON.parse(e.data);
                const pid = payload.player_id;
                const rank = payload.rank;
                showToast(`${payload.player_id} が ${rank} 位になりました` , 3000);
                markPlayerFinished(pid, rank);
            }catch(err){ console.error('player_finished parse', err); }
        });
    evtSource.addEventListener('card_given', e=>{
            try{
                const payload = JSON.parse(e.data);
                showToast(`カードが渡されました: ${payload.card}` , 2500);
                // If this client is either sender or recipient, refresh state
                if(payload.from === playerId || payload.to === playerId){
                    pollState();
                }
            }catch(err){ console.error('card_given parse', err); }
        });
        // server notifies when a card is played (by human or bot)
        evtSource.addEventListener('card_played', e=>{
            try{
                const payload = JSON.parse(e.data);
                const pid = payload.player_id;
                try{ hideBotThinking(pid); }catch(_){ }
                const cards = payload.cards || [];
                let name = pid;
                try{ if(window.__lastState){ const p = window.__lastState.players.find(x=>x.id===pid); if(p) name = p.display_name||p.name||name; } }catch(_){ }
                const time = payload.ts? new Date(payload.ts).toLocaleTimeString() : new Date().toLocaleTimeString();
                if(chatBox){
                    const el = document.createElement('div');
                    el.className = 'chat-line';
                    const header = document.createElement('span');
                    header.innerHTML = `<span class="chat-time muted small">${time}</span> <strong>${escapeHtml(name)}:</strong> `;
                    el.appendChild(header);
                    if(cards.length){
                        cards.forEach(c=>{
                            const chip = createCardChip(c);
                            el.appendChild(chip);
                        });
                    } else {
                        const span = document.createElement('span'); span.textContent = ' 出しました'; el.appendChild(span);
                    }
                    chatBox.appendChild(el);
                        try{
                            // Prefer server-provided message id for dedupe; fallback to synthesized id
                            if(payload.msg_id){
                                window.__seenMessageIds.add(String(payload.msg_id));
                            } else {
                                const synthTxt = cards.length ? ('出した: ' + cards.join(',')) : '出した:';
                                const synth = { ts: payload.ts, text: synthTxt, name: name };
                                const mid = messageIdFor(synth);
                                if(mid) window.__seenMessageIds.add(mid);
                            }
                        }catch(_){ }
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
                try{
                    if(centerPile){
                        centerPile.innerHTML = '';
                        if(cards.length){
                            cards.forEach(c=>{
                                const chipWrap = document.createElement('div');
                                chipWrap.className = 'card-ui';
                                const chip = createCardChip(c);
                                chipWrap.appendChild(chip);
                                centerPile.appendChild(chipWrap);
                            });
                            const first = centerPile.children[0];
                            if(first){
                                first.classList.add('played-anim');
                                setTimeout(()=>{ try{ first.classList.remove('played-anim'); }catch(_){ } }, 700);
                            }
                        }
                    }
                }catch(_){ }
                pollState();
            }catch(err){ console.error('card_played parse', err); }
        });
        // bot thinking: server notifies when a bot starts 'thinking' and provides delay seconds
        evtSource.addEventListener('bot_thinking', e=>{
            try{
                const payload = JSON.parse(e.data);
                const pid = payload.player_id;
                const serverDelay = Number(payload.delay) || 10;
                // prefer client-side configured delay if present
                let useDelay = serverDelay;
                try{
                    const stored = sessionStorage.getItem('botThinkDelay');
                    if(stored){ const v = Number(stored); if(!isNaN(v)) useDelay = v; }
                }catch(_){ }
                // show thinking indicator for this player for the specified delay
                try{ showBotThinking(pid, useDelay*1000); }catch(_){ }
            }catch(err){ console.error('bot_thinking parse', err); }
        });
        evtSource.addEventListener('card_discarded', e=>{
            try{
                const payload = JSON.parse(e.data);
                showToast(`カードが捨てられました: ${payload.card}` , 2500);
                if(payload.player_id === playerId) pollState();
            }catch(err){ console.error('card_discarded parse', err); }
        });
        evtSource.addEventListener('revolution', e=>{
            try{
                const payload = JSON.parse(e.data);
                if(payload.active){
                    showToast('革命が発生しました！カードの強さが逆転します', 4000);
                    try{
                        // Prefer server-provided message id for dedupe; fallback to synthesized id
                        if(payload.msg_id){
                            window.__seenMessageIds.add(String(payload.msg_id));
                        } else {
                            const synth = { ts: payload.ts, text: payload.text || '', name: payload.name || 'System' };
                            const mid = messageIdFor(synth);
                            if(mid) window.__seenMessageIds.add(mid);
                        }
                    }catch(_){ }
                }
                pollState();
            }catch(err){ console.error('revolution parse', err); }
        });
        evtSource.addEventListener('direction', e=>{
            try{
                const payload = JSON.parse(e.data);
                showToast(`進行方向が ${payload.direction==='clockwise'?'時計回り':'反時計回り'} に変わりました`, 3000);
                pollState();
            }catch(err){ console.error('direction parse', err); }
        });
        evtSource.addEventListener('mass_discard', e=>{
            try{
                const payload = JSON.parse(e.data);
                showToast(`全員捨て: ${payload.target_rank} が捨てられました`, 4000);
                pollState();
            }catch(err){ console.error('mass_discard parse', err); }
        });
        evtSource.addEventListener('auto_transfer', e=>{
            try{
                const payload = JSON.parse(e.data);
                showToast(`自動交換: ${payload.from} -> ${payload.to} : ${payload.cards.join(', ')}`, 4000);
                pollState();
            }catch(err){ console.error('auto_transfer parse', err); }
        });
        evtSource.addEventListener('give_submitted', e=>{
            try{
                const payload = JSON.parse(e.data);
                showToast(`カードを渡しました: ${payload.cards.join(', ')}`, 3000);
                pollState();
            }catch(err){ console.error('give_submitted parse', err); }
        });
        // bot_chat: short text messages emitted by server-side bots (tone-driven)
        evtSource.addEventListener('bot_chat', e=>{
            try{
                const payload = JSON.parse(e.data);
                // payload should contain: { player_id, text, ts? , name? }
                const pid = payload.player_id;
                // try to resolve a friendly display name from last polled state
                let name = payload.name || pid || 'Bot';
                try{
                    if(window.__lastState && Array.isArray(window.__lastState.players)){
                        const found = window.__lastState.players.find(p=> p.id === pid || p.player_id === pid);
                        if(found) name = found.display_name || found.name || name;
                    }
                }catch(_){ }
                const ts = payload.ts ? new Date(payload.ts) : new Date();
                if(chatBox){
                    const el = document.createElement('div');
                    el.className = 'chat-line';
                    const time = ts.toLocaleTimeString();
                    el.innerHTML = `<span class="chat-time muted small">${time}</span> <strong>${escapeHtml(name)}:</strong> ${escapeHtml(payload.text)}`;
                    chatBox.appendChild(el);
                    // mark synthesized message id as seen to avoid duplicate when polling returns same message
                    try{
                        const synth = { ts: payload.ts, text: payload.text || '', name: name };
                        const mid = messageIdFor(synth);
                        if(mid) window.__seenMessageIds.add(mid);
                    }catch(_){ }
                    // auto-scroll
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            }catch(err){ console.error('bot_chat parse', err); }
        });
        evtSource.addEventListener('game_finished', e=>{
            try{
                const payload = JSON.parse(e.data);
                showToast('ゲーム終了', 3000);
                renderResults(payload.results || payload);
            }catch(err){ console.error('game_finished parse', err); }
        });
    }

    function setInviteLink(rid){
        const url = `${location.origin}/game/daifugo?room=${rid}`;
        inviteArea.textContent = url;
    }

    async function createRoom(){
        const name = playerNameInput.value || 'Player';
        const res = await fetch('/api/rooms', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})});
        const data = await res.json();
        roomId = data.room_id;
        playerId = data.player_id;
        setInviteLink(roomId);
        roomIdInput.value = roomId;
        startPolling();
    }

    async function joinRoom(){
        const name = playerNameInput.value || 'Player';
        const rid = roomIdInput.value.trim();
        if(!rid) return showToast('ルームIDを入力してください');
        const res = await fetch(`/api/rooms/${rid}/join`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})});
        if(!res.ok) return showToast('ルーム参加に失敗しました');
        const data = await res.json();
        roomId = data.room_id;
        playerId = data.player_id;
        setInviteLink(roomId);
        if(data.already){
            showToast('あなたは既にこのルームに参加しています（重複参加は無効化しました）');
        } else {
            showToast('ルームに参加しました');
        }
        startPolling();
    }

    async function startRoom(){
        if(!roomId) return alert('ルームがありません');
        const res = await fetch(`/api/rooms/${roomId}/start`, {method:'POST'});
        if(!res.ok) return alert('開始に失敗しました');
        // state will update on next poll
    }

    async function pollState(){
        if(!roomId) return;
        const url = `/api/rooms/${roomId}/state?player_id=${playerId || ''}`;
        const res = await fetch(url);
        if(!res.ok) return;
        const state = await res.json();
        renderState(state);
    }

    function renderState(state){
        // keep last state globally for small helpers (used to decide whether '渡す' button should be shown)
        try{ window.__lastState = state; }catch(e){}
        // players
        playersList.innerHTML = '';
        (state.players||[]).forEach((p, idx)=>{
            const li = document.createElement('li');
            li.dataset.playerId = p.id || '';
            if(state.current_turn === idx) li.className = 'current-turn';
            // display name: prefer display_name if provided by server player object (for bots)
            const display = p.display_name || p.name || 'Unknown';
            li.textContent = `${display} ${p.is_bot?'(Bot)':''} — ${p.hand_count!=null?p.hand_count+'枚':''}`;
            // if bot, add edit button
            if(p.is_bot){
                const edit = document.createElement('button');
                edit.className = 'btn btn-small';
                edit.textContent = '編集';
                edit.style.marginLeft = '8px';
                edit.addEventListener('click', (ev)=>{
                    ev.stopPropagation();
                    openBotEditModal(p);
                });
                li.appendChild(edit);
                // if game not started, allow removing bot
                if(!state.started){
                    const del = document.createElement('button');
                    del.className = 'btn btn-small btn-danger';
                    del.textContent = '削除';
                    del.style.marginLeft = '6px';
                    del.addEventListener('click', async (ev)=>{
                        ev.stopPropagation();
                        if(!confirm('このボットをルームから削除しますか？')) return;
                        const res = await fetch(`/api/rooms/${roomId}/bots/${p.id}`, {method:'DELETE'});
                        if(!res.ok){ const d = await res.json().catch(()=>({})); return showToast(d.error || '削除に失敗しました'); }
                        showToast('ボットを削除しました', 1000);
                        await pollState();
                    });
                    li.appendChild(del);
                }
            }
            playersList.appendChild(li);
        });
        // show current direction badge
        const dirBadge = document.getElementById('directionBadge');
        if(dirBadge){
            dirBadge.textContent = state.direction === 'counterclockwise' ? '進行: 反時計回り' : '進行: 時計回り';
        }
        // center
        centerPile.innerHTML = '';
        if(state.center && state.center.length){
            const el = document.createElement('div');
            el.className = 'card-ui';
            el.textContent = state.center[0];
            centerPile.appendChild(el);
        }
        // update current turn banner
        try{
            const banner = document.getElementById('currentTurnBanner');
            if(banner){
                const curIdx = state.current_turn;
                let curName = '--';
                if(Array.isArray(state.players) && typeof curIdx === 'number'){
                    const curP = state.players[curIdx];
                    if(curP) curName = curP.display_name || curP.name || '--';
                }
                banner.textContent = `${curName} のターン`;
                // highlight banner color if it's this player's turn
                if(state.players && state.players[state.current_turn] && state.players[state.current_turn].id === playerId){
                    banner.style.background = '#e6fffa';
                    banner.style.border = '1px solid #2c7a7b';
                    banner.style.padding = '6px 10px';
                    banner.style.borderRadius = '6px';
                } else {
                    banner.style.background = 'transparent';
                    banner.style.border = 'none';
                    banner.style.padding = '';
                }
            }
        }catch(e){}

        // your hand
        handRow.innerHTML = '';
        if(state.your_hand){
            // ensure selectedCards only contains cards still in hand
            const handSet = new Set(state.your_hand || []);
            for(const s of Array.from(selectedCards)) if(!handSet.has(s)) selectedCards.delete(s);
            state.your_hand.forEach(card=>{
                const el = document.createElement('div');
                el.className = 'card-ui';
                el.textContent = card;
                // restore selection state if previously selected
                if(selectedCards.has(card)) el.classList.add('selected');
                // multi-select logic (persistent until toggled or played)
                el.addEventListener('click', ()=>{
                    // only allow selecting when it's this client's turn
                    if(!(state.players && state.players[state.current_turn] && state.players[state.current_turn].id === playerId)){
                        return showToast('現在は出せません — あなたのターンになるまでお待ちください');
                    }
                    if(selectedCards.has(card)){
                        selectedCards.delete(card);
                        el.classList.remove('selected');
                    } else {
                        selectedCards.add(card);
                        el.classList.add('selected');
                    }
                });
                // small give button: only show if server indicates this player is allowed to give (last_player and center contains 7)
                const showGive = (()=>{
                    try{
                        // state is in outer scope through renderState; check last_player and center
                        if(!window.__lastState) return false;
                        const st = window.__lastState;
                        if(st.last_player !== playerId) return false;
                        // check center meta contains 7
                        const center = st.center || [];
                        if(!center || center.length === 0) return false;
                        // simple detection: any card in center whose rank is '7' (prefix '7')
                        return center.some(c => (c !== 'JOKER') && c.startsWith('7'));
                    }catch(e){ return false; }
                })();
                if(showGive){
                    const giveBtn = document.createElement('button');
                    giveBtn.className = 'btn btn-small give-btn';
                    giveBtn.textContent = '渡す';
                    giveBtn.style.marginLeft = '6px';
                    giveBtn.addEventListener('click', async (ev)=>{
                        ev.stopPropagation();
                        // confirm and call API to give this card
                        if(!roomId || !playerId) return showToast('ルームに参加してください');
                        const ok = confirm(`このカードを渡しますか？ ${card}`);
                        if(!ok) return;
                        const res = await fetch(`/api/rooms/${roomId}/give`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id: playerId, card: card})});
                        const d = await res.json().catch(()=>({}));
                        if(!res.ok){
                            return showToast(d.error || 'カードを渡せませんでした');
                        }
                        // refresh state
                        await pollState();
                    });
                    el.appendChild(giveBtn);
                }
                handRow.appendChild(el);
            });
            // add Play / Clear buttons when it's player's turn
            const isMyTurn = state.players && state.players[state.current_turn] && state.players[state.current_turn].id === playerId;
            let controlRow = document.getElementById('handControls');
            if(!controlRow){ controlRow = document.createElement('div'); controlRow.id = 'handControls'; controlRow.style.marginTop = '8px'; handRow.parentNode.insertBefore(controlRow, handRow.nextSibling); }
            controlRow.innerHTML = '';
            if(isMyTurn){
                const playBtn = document.createElement('button'); playBtn.className='btn btn-primary'; playBtn.textContent='出す';
                playBtn.style.marginRight='8px';
                playBtn.addEventListener('click', async ()=>{
                    if(!roomId || !playerId) return showToast('ルームに参加してください');
                    const cards = Array.from(selectedCards);
                    if(cards.length === 0) return showToast('出すカードを選択してください');
                    try{
                        const res = await fetch(`/api/rooms/${roomId}/play`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id: playerId, cards})});
                        const d = await res.json().catch(()=>({}));
                        if(!res.ok){ showToast(d.error || 'カードを出せませんでした'); return; }
                        // on success, animate selected cards flying to center, then clear selection and refresh
                        try{ animateSelectedToCenter(Array.from(cards)); }catch(_){ }
                        selectedCards.clear();
                        await pollState();
                    }catch(err){ console.error('play error', err); showToast('通信エラー'); }
                });
                const clearBtn = document.createElement('button'); clearBtn.className='btn btn-secondary'; clearBtn.textContent='選択解除';
                clearBtn.addEventListener('click', ()=>{ selectedCards.clear(); pollState(); });
                controlRow.appendChild(playBtn); controlRow.appendChild(clearBtn);
            } else {
                // hide controls when not turn
            }
        }

    // animate given card tokens from their card-ui element to the centerPile
    function animateSelectedToCenter(cards){
        try{
            // for each token, find a matching .card-ui in handRow and clone
            cards.forEach((token, idx)=>{
                // find an element whose textContent equals token
                const elems = Array.from(handRow.querySelectorAll('.card-ui'));
                let src = elems.find(el=> (el.textContent||'').trim().startsWith(token));
                if(!src) src = elems[idx] || elems[0];
                if(!src) return;
                const rect = src.getBoundingClientRect();
                const clone = src.cloneNode(true);
                clone.classList.add('fly-clone');
                clone.style.left = rect.left + 'px';
                clone.style.top = rect.top + 'px';
                clone.style.width = rect.width + 'px';
                clone.style.height = rect.height + 'px';
                clone.style.margin = '0';
                document.body.appendChild(clone);
                // compute center target
                const centerRect = centerPile.getBoundingClientRect();
                const targetX = centerRect.left + (centerRect.width/2) - (rect.width/2) + (idx*8 - (cards.length-1)*4);
                const targetY = centerRect.top + (centerRect.height/2) - (rect.height/2);
                // force reflow then transform
                window.getComputedStyle(clone).transform;
                clone.style.transform = `translate(${targetX - rect.left}px, ${targetY - rect.top}px) scale(0.9)`;
                clone.style.opacity = '0.95';
                setTimeout(()=>{
                    clone.style.opacity = '0';
                    setTimeout(()=>{ try{ clone.remove(); }catch(_){ } }, 420);
                }, 520);
            });
        }catch(e){ console.error('animateSelectedToCenter', e); }
    }
        // if server indicates this player must submit give cards, show modal
        if(state.pending_give && state.pending_give.allowed){
            openGiveModal(state.pending_give.count, state.your_hand || [], state.pending_give.to_name || null, { to_hand_count: state.pending_give.to_hand_count, to_is_bot: state.pending_give.to_is_bot });
        }
        // messages
        if(state.messages){
            renderMessages(state.messages);
        }
        // highlight current turn player in list
        Array.from(playersList.children).forEach((li, idx)=>{
            if(state.current_turn === idx) li.classList.add('current-turn'); else li.classList.remove('current-turn');
        });
    }

    // create Bot Add modal markup dynamically if not present
    (function createBotAddModal(){
        // area where button will be inserted
        const area = document.getElementById('botAddArea') || document.getElementById('playersListArea');
        if(!area) return;
        const btn = document.createElement('button');
        btn.className = 'btn';
        btn.textContent = 'ボットを追加';
        btn.style.marginTop = '8px';
        area.appendChild(btn);

        // modal container
        let modal = document.getElementById('botAddModal');
        if(!modal){
            modal = document.createElement('div');
            modal.id = 'botAddModal';
            modal.className = 'modal';
            modal.style.display = 'none';
            modal.innerHTML = `
                <div class="modal-content">
                    <h3 style="margin-top:0;">ボットを追加</h3>
                    <div style="display:flex; flex-direction:column; gap:8px; margin-top:8px;">
                        <label>表示名</label>
                        <input id="botAddDisplayName" type="text" placeholder="例: イジヒコ">
                        <label>口調</label>
                        <select id="botAddTone">
                            <option>真面目くん</option>
                            <option>不思議ちゃん</option>
                            <option selected>いじわる</option>
                        </select>
                        <label>難易度</label>
                        <select id="botAddDifficulty">
                            <option>弱い</option>
                            <option selected>ふつう</option>
                            <option>強い</option>
                        </select>
                    </div>
                    <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:12px;">
                        <button id="botAddCancel" class="btn btn-secondary">キャンセル</button>
                        <button id="botAddSave" class="btn btn-primary">追加</button>
                    </div>
                </div>`;
            document.body.appendChild(modal);
        }

        const inputName = document.getElementById('botAddDisplayName');
        const inputTone = document.getElementById('botAddTone');
        const inputDiff = document.getElementById('botAddDifficulty');
        const cancel = document.getElementById('botAddCancel');
        const save = document.getElementById('botAddSave');

        btn.addEventListener('click', ()=>{
            if(!roomId) return showToast('ルームに参加してください');
            if(inputName) inputName.value = '';
            if(inputTone) inputTone.value = 'いじわる';
            if(inputDiff) inputDiff.value = 'ふつう';
            modal.style.display = 'block';
        });
        if(cancel) cancel.addEventListener('click', ()=>{ modal.style.display = 'none'; });
        if(save) save.addEventListener('click', async ()=>{
            const name = inputName ? inputName.value.trim() || undefined : undefined;
            const tone = inputTone ? inputTone.value : 'いじわる';
            const difficulty = inputDiff ? inputDiff.value : 'ふつう';
            try{
                const res = await fetch(`/api/rooms/${roomId}/bots`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({display_name: name, tone: tone, difficulty: difficulty})});
                const d = await res.json().catch(()=> ({}));
                if(!res.ok) return showToast(d.error || 'ボット追加に失敗しました');
                showToast('ボットを追加しました', 1000);
                modal.style.display = 'none';
                await pollState();
            }catch(err){ console.error('add bot', err); showToast('ボット追加エラー'); }
        });
    })();

    // Modal logic for pending give
    const giveModal = document.getElementById('giveModal');
    const giveHand = document.getElementById('giveHand');
    const giveCancel = document.getElementById('giveCancel');
    const giveSubmit = document.getElementById('giveSubmit');
    let giveSelection = new Set();
    function openGiveModal(count, hand, toName, toInfo){
        giveSelection.clear();
        giveHand.innerHTML = '';
        const namePart = toName ? `（→ ${toName} さんへ）` : '';
        document.getElementById('giveModalTitle').textContent = `返礼として ${count} 枚を選んでください ${namePart}`;
        // recipient avatar and info
        const avatar = document.getElementById('giveRecipientAvatar');
        const info = document.getElementById('giveRecipientInfo');
        if(avatar){
            // initials: prefer ASCII-first two chars, otherwise use last two chars (better for Japanese names)
            let initials = '?';
            if(toName){
                if(/[A-Za-z]/.test(toName)){
                    initials = toName.slice(0,2).toUpperCase();
                } else {
                    initials = toName.slice(-2);
                }
            }
            avatar.textContent = initials;
            // compute deterministic color from name
            const colors = nameToGradient(toName || '');
            avatar.style.background = `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`;
        }
        if(info){
            const handCount = toInfo && typeof toInfo.to_hand_count === 'number' ? `${toInfo.to_hand_count}枚` : '--';
            const botMark = toInfo && toInfo.to_is_bot ? '（Bot）' : '';
            const parts = [];
            parts.push(`受取: ${handCount}`);
            if(botMark) parts.push(botMark);
            if(toInfo && (toInfo.to_rank != null)) parts.push(`順位: ${toInfo.to_rank}位`);
            if(toInfo && (toInfo.to_score != null)) parts.push(`総合得点: ${toInfo.to_score}点`);
            info.textContent = parts.join(' ・ ');
        }
        hand.forEach(card=>{
            const el = document.createElement('div');
            el.className = 'card-ui';
            el.textContent = card;
            el.addEventListener('click', ()=>{
                if(giveSelection.has(card)){
                    giveSelection.delete(card);
                    el.classList.remove('selected');
                } else {
                    if(giveSelection.size >= count) return showToast(`最大 ${count} 枚まで選択可能です`);
                    giveSelection.add(card);
                    el.classList.add('selected');
                }
            });
            giveHand.appendChild(el);
        });
        giveModal.style.display = 'block';
    }
    function closeGiveModal(){
        giveModal.style.display = 'none';
        giveHand.innerHTML = '';
        giveSelection.clear();
    }

    function nameToGradient(name){
        // simple hash -> H,H2 values
        let h = 0;
        for(let i=0;i<name.length;i++) h = (h<<5) - h + name.charCodeAt(i);
        const hue1 = Math.abs(h) % 360;
        const hue2 = (hue1 + 60) % 360;
        const c1 = `hsl(${hue1} 90% 60%)`;
        const c2 = `hsl(${hue2} 80% 50%)`;
        return [c1, c2];
    }
    giveCancel.addEventListener('click', ()=>{ closeGiveModal(); });
    giveSubmit.addEventListener('click', async ()=>{
        if(!roomId || !playerId) return showToast('ルームに参加してください');
        const cards = Array.from(giveSelection);
        if(cards.length === 0) return showToast('カードを選択してください');
        const res = await fetch(`/api/rooms/${roomId}/submit_give`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id: playerId, cards})});
        const d = await res.json().catch(()=> ({}));
        if(!res.ok){
            showToast(d.error || '送信に失敗しました');
            return;
        }
        closeGiveModal();
        await pollState();
    });

    function markPlayerFinished(player_id, rank){
        const li = playersList.querySelector(`[data-player-id="${player_id}"]`);
        if(li){
            li.classList.add('finished');
            // append rank badge
            let badge = li.querySelector('.rank-badge');
            if(!badge){
                badge = document.createElement('span');
                badge.className = 'rank-badge';
                badge.style.marginLeft = '8px';
                badge.style.fontWeight = 'bold';
                li.appendChild(badge);
            }
            badge.textContent = `${rank}位`;
        }
        // also add to results area
        const ra = document.getElementById('resultsArea');
        if(ra){
            const el = document.createElement('div');
            el.className = 'result-line';
            el.textContent = `player ${player_id} — ${rank}位`;
            ra.appendChild(el);
        }
    }

    function renderResults(results){
        // results: list of {player_id, rank}
        const ra = document.getElementById('resultsArea');
        if(!ra) return;
        ra.innerHTML = '';
        const header = document.createElement('div'); header.className='results-header'; header.textContent = '最終順位'; ra.appendChild(header);
        if(Array.isArray(results)){
            results.sort((a,b)=> (a.rank||0)-(b.rank||0));
            results.forEach(r=>{
                const el = document.createElement('div');
                el.className = 'result-line';
                el.textContent = `${r.player_id} — ${r.rank}位`;
                ra.appendChild(el);
                markPlayerFinished(r.player_id, r.rank);
            });
        } else if(typeof results === 'object'){
            for(const pid in results){
                const el = document.createElement('div');
                el.className = 'result-line';
                el.textContent = `${pid} — ${results[pid]}位`;
                ra.appendChild(el);
                markPlayerFinished(pid, results[pid]);
            }
        }
    }

    // Bot 編集モーダル handlers
    const botEditModal = document.getElementById('botEditModal');
    const botDisplayNameInput = document.getElementById('botDisplayName');
    const botToneSelect = document.getElementById('botTone');
    const botDifficultySelect = document.getElementById('botDifficulty');
    const botEditCancel = document.getElementById('botEditCancel');
    const botEditSave = document.getElementById('botEditSave');
    let _editingBot = null;
    function openBotEditModal(bot){
        _editingBot = bot;
        if(!botEditModal) return;
        botDisplayNameInput.value = bot.display_name || bot.name || '';
        botToneSelect.value = bot.tone || 'いじわる';
        botDifficultySelect.value = bot.difficulty || 'ふつう';
        botEditModal.style.display = 'block';
    }
    function closeBotEditModal(){
        _editingBot = null;
        if(botEditModal) botEditModal.style.display = 'none';
    }
    if(botEditCancel) botEditCancel.addEventListener('click', ()=> closeBotEditModal());
    if(botEditSave) botEditSave.addEventListener('click', async ()=>{
        if(!_editingBot) return closeBotEditModal();
        const payload = {
            display_name: botDisplayNameInput.value.trim() || undefined,
            tone: botToneSelect.value,
            difficulty: botDifficultySelect.value
        };
        try{
            const res = await fetch(`/api/rooms/${roomId}/bots/${_editingBot.id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
            const d = await res.json().catch(()=> ({}));
            if(!res.ok){ showToast(d.error || 'ボット編集に失敗しました'); return; }
            showToast('ボットを更新しました', 1500);
            closeBotEditModal();
            await pollState();
        }catch(err){ console.error('update bot', err); showToast('ボット更新エラー'); }
    });

    const chatBox = document.getElementById('chatBox');
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChat');
    const copyInviteBtn = document.getElementById('copyInvite');
    const shareInviteBtn = document.getElementById('shareInvite');
    const refreshRecommendedBtn = document.getElementById('refreshRecommended');
    const externalServersInput = document.getElementById('externalServers');

    // Utility: copy text to clipboard with Clipboard API and a fallback
    async function copyToClipboard(text){
        // Try modern async clipboard API first
        if(navigator.clipboard && navigator.clipboard.writeText){
            try{
                await navigator.clipboard.writeText(text);
                return true;
            }catch(e){
                // fallthrough to legacy method
            }
        }
        // Fallback: use a hidden textarea + document.execCommand('copy')
        try{
            const ta = document.createElement('textarea');
            ta.value = text;
            // Prevent scrolling to bottom
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.top = '0';
            ta.setAttribute('readonly', '');
            document.body.appendChild(ta);
            ta.select();
            ta.setSelectionRange(0, ta.value.length);
            const ok = document.execCommand && document.execCommand('copy');
            document.body.removeChild(ta);
            return !!ok;
        }catch(e){
            return false;
        }
    }

    // If automatic copy fails, select the inviteArea text to help user copy manually
    function selectInviteText(){
        try{
            if(!inviteArea) return;
            // create range and select content
            if(window.getSelection && document.createRange){
                const range = document.createRange();
                range.selectNodeContents(inviteArea);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            } else if(document.body.createTextRange){
                // IE
                const range = document.body.createTextRange();
                range.moveToElementText(inviteArea);
                range.select();
            }
            // focus so user can press Ctrl+C immediately
            inviteArea.focus && inviteArea.focus();
            showToast('リンクを選択しました — Ctrl/Cmd+C でコピーしてください', 3000);
        }catch(e){ console.warn('selectInviteText failed', e); }
    }

    // dedupe messages by id (or by synthetic id if server doesn't provide one)
    function messageIdFor(m){
        if(!m) return null;
        if(m.id) return String(m.id);
        // fallback: use ts + text hash
        try{
            const key = `${m.ts||''}::${(m.text||'')}`;
            // simple hash
            let h = 0; for(let i=0;i<key.length;i++){ h = ((h<<5)-h) + key.charCodeAt(i); h |= 0; }
            return 'synth_'+String(h);
        }catch(e){ return null }
    }

    function renderMessages(msgs){
        if(!chatBox) return;
        if(!Array.isArray(msgs)) return;
        // msgs may be full history; iterate and append only unseen messages
        msgs.forEach(m => {
            const mid = messageIdFor(m);
            if(mid && window.__seenMessageIds.has(mid)) return; // skip duplicate
            // mark seen early to avoid races
            if(mid) window.__seenMessageIds.add(mid);
            const el = document.createElement('div');
            el.className = 'chat-line';
            const time = new Date(m.ts).toLocaleTimeString();
            const header = document.createElement('span');
            header.innerHTML = `<span class="chat-time muted small">${time}</span> <strong>${escapeHtml(m.name)}:</strong>`;
            el.appendChild(header);
            const txt = (m.text || '').toString();
            if(txt.startsWith('出した')){
                const parts = txt.split(':');
                let rest = parts.slice(1).join(':').trim();
                if(rest){
                    const tokens = rest.split(/[,、\s]+/).filter(Boolean);
                    tokens.forEach(t=>{ const chip = createCardChip(t); el.appendChild(chip); });
                } else { const span = document.createElement('span'); span.textContent = ' 出しました'; el.appendChild(span); }
            } else {
                const body = document.createElement('span'); body.style.marginLeft = '8px'; body.textContent = m.text; el.appendChild(body);
            }
            chatBox.appendChild(el);
        });
        // scroll to bottom
        chatBox.scrollTop = chatBox.scrollHeight;
    }

        function createCardChip(token){
            const chip = document.createElement('span');
            const suit = token.slice(-1);
            const rank = token.slice(0, token.length-1);
            const isRed = (suit === '♦' || suit === '♥');
            chip.className = 'card-chip ' + (isRed? 'chip-red':'chip-black');
            // Prefer external SVG assets (assets/icons/{suit}.svg) provided by a designer.
            // Fallback to an inline SVG path if assets are not present or fail to load.
            const suitMap = {'♠':'spade','♥':'heart','♦':'diamond','♣':'club'};
            const assetName = suitMap[suit] || 'club';
            const img = document.createElement('img');
            img.className = 'chip-icon';
            img.alt = suit;
            // try to load PNG/SVG from a relative assets folder; server may serve static files
            img.src = `/static/assets/icons/${assetName}.svg`;
            // set a small size and fallback handler
            img.width = 20; img.height = 20;
            img.addEventListener('error', ()=>{
                // replace with inline SVG if asset fails
                const ns = 'http://www.w3.org/2000/svg';
                const svg = document.createElementNS(ns, 'svg');
                svg.setAttribute('viewBox', '0 0 24 24');
                const path = document.createElementNS(ns, 'path');
                if(suit === '♠'){
                    path.setAttribute('d', 'M12 2C10 6 6 8 6 11c0 3 3 4 6 9 3-5 6-6 6-9 0-3-4-5-6-9zM9 20c0 1 3 2 3 2s3-1 3-2');
                } else if(suit === '♥'){
                    path.setAttribute('d', 'M12 21s-7-4.6-9-7.1C-0.6 10.6 4 6 7 8.5 9.5 10.6 12 12 12 12s2.5-1.4 5-3.5C20 6 24.6 10.6 22 13.9 20 16.4 12 21 12 21z');
                } else if(suit === '♦'){
                    path.setAttribute('d', 'M12 2l8 10-8 10-8-10z');
                } else { // clubs
                    path.setAttribute('d', 'M12 6a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm-6 6a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm12 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6z');
                }
                path.setAttribute('fill', isRed ? '#9b2c2c' : '#0a3b66');
                svg.appendChild(path);
                // replace image with svg
                img.replaceWith(svg);
            });
            chip.appendChild(img);
            const rankEl = document.createElement('span'); rankEl.textContent = rank;
            chip.appendChild(rankEl);
            // tooltip on hover
            chip.addEventListener('mouseenter', (ev)=>{
                showCardTooltip(ev.currentTarget, token);
            });
            chip.addEventListener('mouseleave', (ev)=>{
                hideCardTooltip();
            });
            return chip;
        }

        // tooltip element singleton
        let _chipTooltip = null;
        function ensureTooltip(){
            if(!_chipTooltip){
                _chipTooltip = document.createElement('div');
                _chipTooltip.className = 'chip-tooltip';
                document.body.appendChild(_chipTooltip);
            }
        }
        function showCardTooltip(target, token){
            ensureTooltip();
            // compute details: rank strength index, description
            const rank = token.slice(0, token.length-1);
            const suit = token.slice(-1);
            const strength = (()=>{
                const order = ['3','4','5','6','7','8','9','10','J','Q','K','A','2'];
                const idx = order.indexOf(rank);
                return idx >=0 ? (idx+1) : null;
            })();
            _chipTooltip.innerHTML = `<div><strong>${token}</strong></div><div style="margin-top:6px">強さ: ${strength!=null?strength:'—'}</div><div style="margin-top:6px; font-size:12px" class="muted">スート: ${suit}</div>`;
            _chipTooltip.style.display = 'block';
            const rect = target.getBoundingClientRect();
            // preferred placement: right of chip; fall back to left/top/bottom to avoid overflow
            const padding = 8;
            const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
            const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
            // measure tooltip size after setting content (but before showing we can read offsetWidth/Height)
            _chipTooltip.style.left = '0px';
            _chipTooltip.style.top = '0px';
            const tW = Math.min(_chipTooltip.offsetWidth || 220, Math.round(vw * 0.6));
            const tH = Math.min(_chipTooltip.offsetHeight || 80, Math.round(vh * 0.4));
            // try right
            let left = rect.right + padding;
            let top = rect.top;
            let placement = 'right';
            if(left + tW > vw - padding){
                // try left
                const leftTry = rect.left - padding - tW;
                if(leftTry >= padding){
                    left = leftTry;
                    placement = 'left';
                    top = rect.top;
                } else {
                    // try below
                    const belowTop = rect.bottom + padding;
                    if(belowTop + tH <= vh - padding){
                        left = Math.max(padding, Math.min(rect.left, vw - tW - padding));
                        top = belowTop;
                        placement = 'bottom';
                    } else {
                        // try above
                        const aboveTop = rect.top - padding - tH;
                        if(aboveTop >= padding){
                            left = Math.max(padding, Math.min(rect.left, vw - tW - padding));
                            top = aboveTop;
                            placement = 'top';
                        } else {
                            // fallback clamp
                            left = Math.max(padding, Math.min(rect.left, vw - tW - padding));
                            top = Math.max(padding, Math.min(rect.top, vh - tH - padding));
                        }
                    }
                }
            }
            // clamp
            left = Math.max(padding, Math.min(left, vw - tW - padding));
            top = Math.max(padding, Math.min(top, vh - tH - padding));
            _chipTooltip.style.left = left + 'px';
            _chipTooltip.style.top = top + 'px';
            _chipTooltip.setAttribute('data-placement', placement);
        }
        function hideCardTooltip(){ if(_chipTooltip) _chipTooltip.style.display = 'none'; }

        // countdown timer for current turn
        function updateTurnTimer(){
            try{
                const banner = document.getElementById('currentTurnBanner');
                if(!banner || !window.__lastState) return;
                const started = window.__lastState.turn_started_at;
                if(!started) return;
                const start = new Date(started).getTime();
                const now = Date.now();
                const elapsed = Math.max(0, (now - start)/1000);
                const remain = Math.max(0, 60 - elapsed);
                // ensure timer bar exists
                let bar = document.getElementById('turnTimerBar');
                if(!bar){
                    const wrap = document.createElement('span'); wrap.className = 'turn-timer';
                    const inner = document.createElement('span'); inner.id = 'turnTimerBar'; inner.className = 'turn-progress'; inner.style.width = '100%';
                    wrap.appendChild(inner);
                    banner.appendChild(wrap);
                }
                const pct = (remain/60) * 100;
                const inner = document.getElementById('turnTimerBar');
                if(inner) inner.style.width = pct + '%';
                // if expired, show 0 and let server-side force-pass handle turn
                if(remain <= 0){
                    // optional flash
                    banner.style.opacity = '0.6';
                } else {
                    banner.style.opacity = '1';
                }
            }catch(e){}
        }
        setInterval(updateTurnTimer, 500);

    function escapeHtml(s){
        return String(s).replace(/[&<>"']/g, function(c){
            return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c];
        });
    }

    async function sendChat(){
        if(!roomId || !playerId) return showToast('ルームに参加してください');
        const text = chatInput.value.trim();
        if(!text) return;
        const res = await fetch(`/api/rooms/${roomId}/message`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id: playerId, text})});
        if(!res.ok){
            const d = await res.json().catch(()=>({}));
            return showToast(d.error || '送信に失敗しました');
        }
        chatInput.value = '';
        // Refresh immediately
        await pollState();
    }

    sendChatBtn.addEventListener('click', sendChat);
    chatInput.addEventListener('keydown', (e)=>{ if(e.key === 'Enter') sendChat(); });

    copyInviteBtn.addEventListener('click', async ()=>{
        if(!roomId) return showToast('招待リンクがありません');
        const link = `${location.origin}/game/daifugo?room=${roomId}`;
        const ok = await copyToClipboard(link);
        if(ok){
            copyInviteBtn.textContent = 'コピーしました';
            setTimeout(()=> copyInviteBtn.textContent = '招待リンクをコピー', 1500);
        } else {
            // assist manual copy by selecting the invite text
            selectInviteText();
            alert('自動コピーに失敗しました。リンクを選択状態にしました。Ctrl/Cmd+C でコピーしてください。');
        }
    });

    shareInviteBtn.addEventListener('click', async ()=>{
        if(!roomId) return showToast('招待リンクがありません');
        const link = `${location.origin}/game/daifugo?room=${roomId}`;
        if(navigator.share){
            navigator.share({title: '大富豪へ招待', text: '一緒に遊ぼう！', url: link}).catch(()=>{});
        } else {
            // fallback: copy to clipboard using helper
            const ok = await copyToClipboard(link);
            if(ok) alert('リンクをコピーしました'); else { selectInviteText(); alert('共有できません — 自動コピーに失敗しました。リンクを選択状態にしました。Ctrl/Cmd+C でコピーしてください。'); }
        }
    });

    // clock
    const clockEl = document.getElementById('clock');
    function updateClock(){
        const now = new Date();
        clockEl.textContent = now.toLocaleTimeString();
    }
    setInterval(updateClock, 1000);
    updateClock();

    // recommended rooms: fetch and render
    async function fetchRecommended(){
        const ext = (externalServersInput && externalServersInput.value.trim()) || '';
        const url = `/api/recommended_rooms` + (ext ? `?external=${encodeURIComponent(ext)}` : '');
        try{
            const res = await fetch(url);
            if(!res.ok) return showToast('おすすめルームの取得に失敗しました');
            const data = await res.json();
            renderRecommended(data);
        }catch(e){ console.error('fetchRecommended', e); showToast('おすすめルームの取得に失敗しました'); }
    }

    // botThinkDelay UI initialization: allow user to pick 2..20 seconds
    function initBotThinkDelayUI(){
        const sel = document.getElementById('botThinkDelay');
        if(!sel) return;
        // populate options if empty
        if(sel.children.length === 0){
            for(let s=2;s<=20;s++){
                const o = document.createElement('option'); o.value = String(s); o.textContent = s + ' 秒';
                sel.appendChild(o);
            }
        }
        // load stored value or default 10
        try{
            const stored = sessionStorage.getItem('botThinkDelay');
            if(stored && sel.querySelector(`option[value="${stored}"]`)) sel.value = stored; else sel.value = '10';
        }catch(e){ sel.value = '10'; }
        sel.addEventListener('change', ()=>{
            try{ sessionStorage.setItem('botThinkDelay', sel.value); }catch(e){}
            showToast('ボット思考時間を ' + sel.value + ' 秒に設定しました', 1200);
        });
    }

    // call init on load
    try{ setTimeout(initBotThinkDelayUI, 120); }catch(e){}

    function renderRecommended(data){
        const area = document.getElementById('recommendedArea');
        if(!area) return;
        area.innerHTML = '';
        // local
        const local = data.local || [];
        if(local.length === 0){
            const p = document.createElement('div'); p.className='muted small'; p.textContent = '現在、途中参加可能なローカルルームはありません'; area.appendChild(p);
        } else {
            local.forEach(r=>{
                const card = document.createElement('div'); card.className='card small';
                const title = document.createElement('div'); title.className='title small'; title.textContent = `ローカル: ${r.room_id} — プレイヤー ${r.player_count} 人`;
                card.appendChild(title);
                const botsWrap = document.createElement('div'); botsWrap.style.display='flex'; botsWrap.style.flexWrap='wrap'; botsWrap.style.gap='6px'; botsWrap.style.marginTop='6px';
                r.bots.forEach(b=>{
                    const bdiv = document.createElement('div'); bdiv.className='bot-slot'; bdiv.style.display='flex'; bdiv.style.alignItems='center'; bdiv.style.gap='8px';
                    const name = document.createElement('div'); name.textContent = (b.display_name||b.name||'Bot'); name.style.fontWeight='bold';
                    const joinBtn = document.createElement('button'); joinBtn.className='btn btn-small'; joinBtn.textContent = 'このボットと入れ替わる';
                    joinBtn.addEventListener('click', async ()=>{
                        // open modal with room/bot info
                        const modal = document.getElementById('joinBotModal');
                        const text = document.getElementById('joinBotText');
                        const ridInput = document.getElementById('joinBotRoomId');
                        const bidInput = document.getElementById('joinBotBotId');
                        if(text) text.textContent = `ボット "${name.textContent}" のスロットに途中参加しますか？`;
                        if(ridInput) ridInput.value = r.room_id;
                        if(bidInput) bidInput.value = b.id;
                        if(modal) modal.style.display = 'block';
                    });
                    bdiv.appendChild(name);
                    bdiv.appendChild(joinBtn);
                    botsWrap.appendChild(bdiv);
                });
                card.appendChild(botsWrap);
                area.appendChild(card);
            });
        }
        // external results (friendly cards)
        const ext = data.external_results || [];
        if(ext.length){
            const header = document.createElement('div'); header.className='muted small'; header.textContent = '外部サーバーの候補'; area.appendChild(header);
            ext.forEach(server=>{
                const base = server.base || server.url || '';
                const block = document.createElement('div'); block.className = 'card small'; block.style.marginTop = '8px';
                const head = document.createElement('div'); head.className = 'title small'; head.textContent = base; block.appendChild(head);
                const payload = server.data || server;
                // expecting payload.local or an array of rooms
                const roomsList = payload.local || payload.rooms || payload;
                if(Array.isArray(roomsList) && roomsList.length){
                    const roomsWrap = document.createElement('div'); roomsWrap.style.display='flex'; roomsWrap.style.flexDirection='column'; roomsWrap.style.gap='8px'; roomsWrap.style.marginTop='8px';
                    roomsList.forEach(rr=>{
                        // rr expected: { room_id, bots: [...], player_count }
                        const rcard = document.createElement('div'); rcard.className = 'card small'; rcard.style.display='flex'; rcard.style.justifyContent='space-between'; rcard.style.alignItems='center';
                        const left = document.createElement('div');
                        const rid = rr.room_id || rr.id || rr.room || '(不明)';
                        const pc = rr.player_count != null ? `${rr.player_count}人` : '';
                        left.innerHTML = `<div style="font-weight:800">${escapeHtml(String(rid))}</div><div class="muted small">${escapeHtml(String(pc))}</div>`;
                        rcard.appendChild(left);
                        const right = document.createElement('div'); right.style.display='flex'; right.style.gap='8px';
                        const joinExt = document.createElement('button'); joinExt.className='btn btn-small'; joinExt.textContent = '外部で途中参加';
                        joinExt.addEventListener('click', ()=>{
                            // construct a reasonable target URL: prefer rr.join_url, else base + /game/daifugo?room=<id>
                            let target = rr.join_url || rr.url || '';
                            if(!target){
                                try{ target = base.replace(/\/$/, '') + '/game/daifugo?room=' + encodeURIComponent(rid); }catch(e){ target = base; }
                            }
                            // optionally append name param
                            const name = (playerNameInput && playerNameInput.value) ? encodeURIComponent(playerNameInput.value) : null;
                            if(name){
                                // if url already has query, append &name=...
                                target += (target.indexOf('?') === -1 ? '?' : '&') + 'name=' + name;
                            }
                            // open in new tab to let external server handle join flow
                            window.open(target, '_blank');
                        });
                        right.appendChild(joinExt);
                        // show bot count or first bot names
                        if(rr.bots && Array.isArray(rr.bots) && rr.bots.length){
                            const info = document.createElement('div'); info.className='muted small'; info.style.marginLeft='8px'; info.textContent = `${rr.bots.length} ボット`; right.appendChild(info);
                        }
                        rcard.appendChild(right);
                        roomsWrap.appendChild(rcard);
                    });
                    block.appendChild(roomsWrap);
                } else {
                    // fallback: raw preview
                    const pre = document.createElement('pre'); pre.textContent = JSON.stringify(payload, null, 2);
                    block.appendChild(pre);
                }
                area.appendChild(block);
            });
        }
    }

    if(refreshRecommendedBtn) refreshRecommendedBtn.addEventListener('click', fetchRecommended);
    // auto fetch on page load
    setTimeout(fetchRecommended, 500);
    // auto-restore playerId from session storage
    try{
        const stored = sessionStorage.getItem('playerId');
        const storedRoom = sessionStorage.getItem('roomId');
        if(stored && storedRoom){ playerId = stored; roomId = storedRoom; roomIdInput.value = roomId; setInviteLink(roomId); startPolling(); }
    }catch(e){ }

    // join modal handlers
    const joinBotModal = document.getElementById('joinBotModal');
    const joinBotCancel = document.getElementById('joinBotCancel');
    const joinBotConfirm = document.getElementById('joinBotConfirm');
    // Accessibility: modal helpers
    function openModal(modal){
        if(!modal) return;
        modal.setAttribute('aria-hidden','false');
        const content = modal.querySelector('.modal-content');
        // save last focused element
        modal._lastFocus = document.activeElement;
        // make modal visible
        try{ modal.style.display = 'flex'; }catch(e){}
        // focus first focusable element inside modal or content
        setTimeout(()=>{
            const focusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            if(focusable) focusable.focus(); else if(content) content.focus();
        }, 40);
        // trap tab
        modal.addEventListener('keydown', modal._trap = function(e){
            if(e.key === 'Escape') { e.preventDefault(); closeModal(modal); return; }
            if(e.key === 'Tab'){
                const focusables = Array.from(modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')).filter(x=> !x.disabled);
                if(focusables.length === 0) { e.preventDefault(); return; }
                const idx = focusables.indexOf(document.activeElement);
                if(e.shiftKey){ // backward
                    if(idx === 0){ focusables[focusables.length-1].focus(); e.preventDefault(); }
                } else {
                    if(idx === focusables.length-1){ focusables[0].focus(); e.preventDefault(); }
                }
            }
        });
    }
    function closeModal(modal){
        if(!modal) return;
        modal.setAttribute('aria-hidden','true');
        try{ modal.style.display = 'none'; }catch(e){}
        // remove trap listener
        if(modal._trap) modal.removeEventListener('keydown', modal._trap);
        // restore focus
        try{ if(modal._lastFocus) modal._lastFocus.focus(); }catch(e){}
    }

    if(joinBotCancel) joinBotCancel.addEventListener('click', ()=>{ closeModal(joinBotModal); });
    if(joinBotConfirm) joinBotConfirm.addEventListener('click', async ()=>{
        const rid = document.getElementById('joinBotRoomId').value;
        const bid = document.getElementById('joinBotBotId').value;
        if(!rid || !bid) return showToast('不足した情報です');
        try{
            const res = await fetch(`/api/rooms/${rid}/join_bot_slot`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot_id: bid, name: (playerNameInput.value||'Player')})});
            const d = await res.json().catch(()=>({}));
            if(!res.ok){ showToast(d.error || '途中参加に失敗しました'); return; }
            // store in session and redirect to room view
            playerId = d.player_id;
            roomId = rid;
            try{ sessionStorage.setItem('playerId', playerId); sessionStorage.setItem('roomId', roomId); }catch(e){}
            closeModal(joinBotModal);
            showToast('途中参加しました。ルームに移動します', 1200);
            // redirect to the same page with ?room= param to ensure fresh load
            setTimeout(()=>{ location.href = `${location.origin}/game/daifugo?room=${roomId}`; }, 800);
        }catch(err){ console.error('join bot slot confirm', err); showToast('途中参加に失敗しました'); }
    });

    // ensure any programmatic modal open uses openModal
    // hook into places where we previously directly set modal.style.display = 'block'
    const origOpen = window.openModal || openModal;
    window.openModal = openModal;
    window.closeModal = closeModal;

    async function playCard(card){
        // Deprecated single-card play: use playSelected
        return await playSelectedCards([card]);
    }

    async function playSelectedCards(list){
        if(!roomId || !playerId) return alert('ルームに参加してください');
        if(!list || !list.length) return alert('カードを選択してください');
        // if list contains a Q, ask for target rank (mass discard)
        let payload = {player_id: playerId, cards: list};
        // mass discard modal flow
        if(list.some(c=> c.startsWith('Q'))){
            // open modal and wait for selection
            const target = await showMassDiscardModal();
            if(!target){
                // user cancelled
                return;
            }
            payload.target_rank = target;
        }
        const res = await fetch(`/api/rooms/${roomId}/play`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
        const data = await res.json();
        if(!res.ok){
            return alert(data.error || 'カードを出せませんでした');
        }
        // simple animation: add played class briefly
        // remove selected markers
        selectedCards.clear();
        // update immediately
        const state = roomsStateFromResponse(data);
        renderState(state);
        // if server indicates a pending discard (10 played), prompt the user
        if(state && state.pending_discard && state.pending_discard.player_id === playerId){
            // ask whether to discard
            setTimeout(async ()=>{
                const want = confirm('10を出したので、任意で手札を1枚捨てられます。捨てますか？');
                if(!want) return;
                // choose a card to discard: show a prompt with comma-separated hand
                const hand = state.your_hand || [];
                const choice = prompt('捨てるカードを正確に入力してください（例: 7♠）。手札: ' + hand.join(', '));
                if(!choice) return;
                const res = await fetch(`/api/rooms/${roomId}/discard`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id: playerId, card: choice})});
                const d = await res.json().catch(()=>({}));
                if(!res.ok){
                    return showToast(d.error || '捨てに失敗しました');
                }
                await pollState();
            }, 200);
        }
        // flash center
        const c = centerPile.firstElementChild;
        if(c){
            c.classList.add('played-anim');
            setTimeout(()=> c.classList.remove('played-anim'), 600);
        }
        return state;
        // handle mass_discard event from server
        // (SSE will also notify; this is just a fallback refresh)
        return state;
    }

    async function passTurn(){
        if(!roomId || !playerId) return showToast('ルームに参加してください');
        const res = await fetch(`/api/rooms/${roomId}/pass`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({player_id: playerId})});
        const data = await res.json();
        if(!res.ok) return showToast(data.error || 'パスに失敗しました');
        // update immediately
        renderState(roomsStateFromResponse(data));
    }

    // toast helper
    const toastEl = document.getElementById('toast');
    function showToast(msg, ms=2000){
        if(!toastEl) return alert(msg);
        toastEl.textContent = msg;
        toastEl.style.display = 'block';
        toastEl.classList.add('show');
        setTimeout(()=>{
            toastEl.classList.remove('show');
            toastEl.style.display = 'none';
        }, ms);
    }

    // Bot thinking indicator helpers
    function showBotThinking(playerId, ms){
        if(!playersList) return;
        const li = playersList.querySelector(`[data-player-id="${playerId}"]`);
        if(!li) return;
        let indicator = li.querySelector('.bot-thinking');
        if(!indicator){
            indicator = document.createElement('span');
            indicator.className = 'bot-thinking';
            indicator.setAttribute('aria-hidden', 'true');
            li.appendChild(indicator);
        }
        // reset timeout
        try{ if(indicator._timeout) clearTimeout(indicator._timeout); }catch(_){ }
        indicator._timeout = setTimeout(()=>{ try{ hideBotThinking(playerId); }catch(_){ } }, ms + 200);
    }

    function hideBotThinking(playerId){
        if(!playersList) return;
        const li = playersList.querySelector(`[data-player-id="${playerId}"]`);
        if(!li) return;
        const indicator = li.querySelector('.bot-thinking');
        if(indicator){ try{ if(indicator._timeout) clearTimeout(indicator._timeout); }catch(_){ } indicator.remove(); }
    }

    function roomsStateFromResponse(data){
        // some responses include room object; map it to state shape
        if(data.room){
            const r = data.room;
            const players = (r['players']||[]).map(p=>({
                id: p['id'],
                name: p['name'],
                display_name: p['display_name'] || p['name'],
                tone: p['tone'],
                difficulty: p['difficulty'],
                is_bot: p['is_bot'],
                hand_count: r['hands'] ? (r['hands'][p['id']]? r['hands'][p['id']].length : 0) : null
            }));
            return {
                players: players,
                center: r['center']||[],
                current_turn: r['current_turn'],
                your_hand: r['hands']? r['hands'][playerId] : null,
                started: r['started'],
                messages: r['messages'] || []
            };
        }
        return data;
    }

    function startPolling(){
        if(pollHandle) clearInterval(pollHandle);
        pollState();
        pollHandle = setInterval(pollState, pollIntervalMs || 1500);
        // also open SSE connection for real-time events
        try{ connectSSE(); }catch(e){ console.warn('SSE connect failed', e); }
    }

    // Room rules UI: load and save
    async function loadRoomRules(){
        if(!roomId) return;
        try{
            const res = await fetch(`/api/rooms/${roomId}/rules`);
            if(!res.ok) return;
            const d = await res.json();
            const r = d.rules || {};
            // set checkboxes
            const map = {
                'spade3_over_joker': 'rule_spade3_over_joker',
                'spade3_single_only': 'rule_spade3_single_only',
                'block_8_after_2': 'rule_block_8_after_2',
                'auto_pass_when_no_joker_vs_2': 'rule_auto_pass_no_joker_vs_2'
            };
            Object.keys(map).forEach(k=>{
                const el = document.getElementById(map[k]);
                if(el) el.checked = !!r[k];
            });
        }catch(e){ console.warn('loadRoomRules failed', e); }
    }

    async function saveRoomRules(){
        if(!roomId) return showToast('ルームに参加してください');
        const payload = {
            spade3_over_joker: !!(document.getElementById('rule_spade3_over_joker') && document.getElementById('rule_spade3_over_joker').checked),
            spade3_single_only: !!(document.getElementById('rule_spade3_single_only') && document.getElementById('rule_spade3_single_only').checked),
            block_8_after_2: !!(document.getElementById('rule_block_8_after_2') && document.getElementById('rule_block_8_after_2').checked),
            auto_pass_when_no_joker_vs_2: !!(document.getElementById('rule_auto_pass_no_joker_vs_2') && document.getElementById('rule_auto_pass_no_joker_vs_2').checked),
        };
        try{
            const res = await fetch(`/api/rooms/${roomId}/rules`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
            const d = await res.json().catch(()=>({}));
            if(!res.ok) return showToast(d.error || 'ルール保存に失敗しました');
            showToast('ルールを保存しました', 1200);
            // reload to reflect server-normalized values
            await loadRoomRules();
        }catch(e){ console.error('saveRoomRules', e); showToast('ルール保存エラー'); }
    }

    // wire up save/reload buttons
    const saveRulesBtn = document.getElementById('saveRulesBtn');
    const reloadRulesBtn = document.getElementById('reloadRulesBtn');
    if(saveRulesBtn) saveRulesBtn.addEventListener('click', saveRoomRules);
    if(reloadRulesBtn) reloadRulesBtn.addEventListener('click', loadRoomRules);

    // ensure rules are loaded after join/create
    const origStartPolling = startPolling;
    startPolling = function(){ origStartPolling(); setTimeout(loadRoomRules, 300); };

    createBtn.addEventListener('click', createRoom);
    joinBtn.addEventListener('click', joinRoom);
    startBtn.addEventListener('click', startRoom);
    const playBtn = document.getElementById('playSelected');
    if(playBtn) playBtn.addEventListener('click', ()=>{
        // only allow when it's this player's turn
        if(!window.__lastState || !window.__lastState.players || !window.__lastState.players[window.__lastState.current_turn]) return showToast('状態を取得中です');
        const cur = window.__lastState.players[window.__lastState.current_turn];
        if(!cur || cur.id !== playerId) return showToast('現在はあなたのターンではありません');
        const list = Array.from(selectedCards);
        playSelectedCards(list);
    });
    const passBtn = document.getElementById('passTurn');
    if(passBtn) passBtn.addEventListener('click', ()=>{
        if(!window.__lastState || !window.__lastState.players || !window.__lastState.players[window.__lastState.current_turn]) return showToast('状態を取得中です');
        const cur = window.__lastState.players[window.__lastState.current_turn];
        if(!cur || cur.id !== playerId) return showToast('現在はあなたのターンではありません');
        passTurn();
    });

    // If the page was opened with ?room=ID, auto-fill
    const params = new URLSearchParams(location.search);
    if(params.get('room')){
        roomIdInput.value = params.get('room');
    }
});

// ---- Mass discard modal helpers (outside DOMContentLoaded scope for simplicity) ----
function showMassDiscardModal(){
    return new Promise((resolve)=>{
        const modal = document.getElementById('massDiscardModal');
        const btnContainer = document.getElementById('massRankButtons');
        const custom = document.getElementById('massRankCustom');
        const cancel = document.getElementById('massDiscardCancel');
        const submit = document.getElementById('massDiscardSubmit');
        if(!modal || !btnContainer || !custom || !cancel || !submit) return resolve(null);
        btnContainer.innerHTML = '';
        // sensible common ranks first
        const common = ['A','K','10','9','8','7','5','4','3','2','J','Q'];
        common.forEach(r=>{
            const b = document.createElement('button');
            b.className = 'btn small';
            b.textContent = r;
            b.addEventListener('click', ()=>{
                // toggle active
                Array.from(btnContainer.children).forEach(ch=> ch.classList.remove('active'));
                b.classList.add('active');
                custom.value = r;
            });
            btnContainer.appendChild(b);
        });
        modal.style.display = 'flex';
        // handlers
        const onCancel = ()=>{
            modal.style.display = 'none';
            cleanup();
            resolve(null);
        };
        const onSubmit = ()=>{
            const val = (custom.value || '').trim();
            modal.style.display = 'none';
            cleanup();
            resolve(val || null);
        };
        function cleanup(){
            cancel.removeEventListener('click', onCancel);
            submit.removeEventListener('click', onSubmit);
        }
        cancel.addEventListener('click', onCancel);
        submit.addEventListener('click', onSubmit);
    });
}

function closeMassDiscardModal(){
    const modal = document.getElementById('massDiscardModal');
    if(modal) modal.style.display = 'none';
}
