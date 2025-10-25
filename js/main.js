// 画面を切り替える関数
function switchScreen(screenName) {
    // 現在のゲーム状態を保存
    localStorage.setItem('gameState', JSON.stringify(gameState));
    localStorage.setItem('currentMapName', currentMapName || 'field');
    localStorage.setItem('player', JSON.stringify(player));
    localStorage.setItem('currentEnemy', JSON.stringify(currentEnemy));
    localStorage.setItem('isInBattle', isInBattle);
    localStorage.setItem('isPlayerTurn', isPlayerTurn);
    localStorage.setItem('currentCommandIndex', currentCommandIndex);

    if (screens && screens[screenName]) {
        // 同じページ内の切り替え
        Object.values(screens).forEach(screen => screen.classList.remove('active'));
        screens[screenName].classList.add('active');
        if (screenName === 'start') {
            playBgm('title');
        }
    } else {
        // ページ遷移
        if (screenName === 'main') {
            window.location.href = 'index2.html';
        } else if (screenName === 'battle') {
            window.location.href = 'index3.html';
        } else {
            window.location.href = 'index4.html';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const buttons = {
        start: document.getElementById('start-button'),
        load: document.getElementById('load-button'),
        resume: document.getElementById('resume-button'),
        backToStart: document.getElementById('back-to-start-button'),
        configComplete: document.getElementById('config-complete-button'),
        save: document.getElementById('save-button'),
    };

    const attackButton = document.getElementById('attack-command');
    const escapeButton = document.getElementById('escape-button');
    const itemButton = document.getElementById('item-command');
    const spellButton = document.getElementById('spell-command');
    const defendButton = document.getElementById('defend-command');
    const battlePartyStatusTop = document.getElementById('battle-party-status-top');
    const battleMessageWindow = document.getElementById('battle-message-window');
    const battleCommandContainer = document.getElementById('battle-command-container');
    const battleMessage = document.getElementById('battle-message');
    const battleEnemyInfo = document.getElementById('battle-enemy-info');
    const saveSlotsContainer = document.getElementById('save-slots-container');
    const saveSlotTitle = document.getElementById('save-slot-title');
    const playerNameInput = document.getElementById('player-name');
    const bgmVolumeInput = document.getElementById('bgm-volume');

    const canvas = document.getElementById('game-canvas');
    const ctx = canvas ? canvas.getContext('2d') : null;

    const playerImage = new Image();
    playerImage.src = 'images/player/hero.png';
    let isPlayerImageLoaded = false;
    playerImage.onload = () => { isPlayerImageLoaded = true; console.log("プレイヤー画像を読み込みました。"); };
    playerImage.onerror = () => { console.error("プレイヤー画像の読み込みに失敗しました。"); };

    // 歩行アニメーション用
    const playerImages = [
        new Image(), new Image(), new Image(), new Image()
    ];
    playerImages[0].src = 'images/player/hero1.png';
    playerImages[1].src = 'images/player/hero2.png';
    playerImages[2].src = 'images/player/hero3.png';
    playerImages[3].src = 'images/player/hero4.png';

    // --- ゲームの状態管理 ---
    let gameState = {};
    let monsterData = [];
    let currentMapData = null;
    let player = { x: 5, y: 5, size: 32 };
    const tileSize = 32;

    let isInBattle = false;
    let currentEnemy = null;
    let isPlayerTurn = true;
    let isDefending = false; // 防御フラグ
    
    let currentCommandIndex = 0;
    const commands = ['attack', 'spell', 'defend', 'item', 'escape'];
    // 自動保存制御
    let enableAutosave = true; // セーブせず終了を選んだ場合 false にする
    let autosaveIntervalId = null;
    let saveSlotMode = 'load'; // 'save' | 'load' | 'delete'
    let isAutoSaving = false; // 自動保存中フラグ

    // 経験値テーブル (レベルnに必要な累積経験値)
    const expTable = [0, 10, 30, 70, 150, 250, 400, 600, 900, 1300, 1800, 2400, 3200, 4200, 5400, 6800, 8400, 10200, 12300, 14700];

    // BGM再生関数
    function playBgm(mapName) {
        // すべてのBGM停止
        document.querySelectorAll('audio[id^="bgm-"]').forEach(audio => audio.pause());
        let bgmId = `bgm-${mapName}`;
        if (mapName === 'title') {
            bgmId = 'bgm-title';
        } else if (mapName === 'battle') {
            const randomBattle = Math.random() < 0.5 ? 'battle1' : 'battle2';
            bgmId = `bgm-${randomBattle}`;
        }
        const bgm = document.getElementById(bgmId);
        if (bgm) {
            bgm.currentTime = 0;
            bgm.play();
        }
    }

    // SE再生関数
    function playSe(seName) {
        const se = document.getElementById(`se-${seName}`);
        if (se) {
            se.currentTime = 0;
            se.play();
        }
    }

    // --- 関数定義 ---

    // レベルアップ処理
    function levelUp(character) {
        character.level++;
        character.maxHp += 5; // HP +5
        character.maxMp += 2; // MP +2
        character.mp = character.maxMp; // MP全回復
        character.attack += 2; // ちから +2
        character.defense += 1; // みのまもり +1
        character.hp = character.maxHp; // HPを全回復
        console.log(`${character.name} はレベル ${character.level} に上がった！`);
        playSe('levelup'); // レベルアップSE
        showBattleMessage(`${character.name} はレベル ${character.level} に上がった！`);
        updateStatusWindow(); // ステータスウィンドウ更新
    }

    // レベルアップチェック
    function checkLevelUp() {
        gameState.party.forEach(character => {
            const nextLevelExp = expTable[character.level] || Infinity;
            if (gameState.exp >= nextLevelExp) {
                levelUp(character);
            }
        });
    }

    // インベントリを表示する関数
    function showInventory() {
        if (gameState.inventory.length === 0) {
            showBattleMessage("どうぐを持っていません。");
            return;
        }
        const itemNames = gameState.inventory.map(item => `${item.name} (${item.count})`);
        const selected = prompt(`どうぐを選んでください:\n${itemNames.join('\n')}\n(番号を入力)`);
        const index = parseInt(selected) - 1;
        if (isNaN(index) || index < 0 || index >= gameState.inventory.length) {
            showBattleMessage("キャンセルしました。");
            return;
        }
        const item = gameState.inventory[index];
        if (item.name === "やくそう") {
            useHerb();
        }
    }

    // やくそうを使用する関数
    function useHerb() {
        const target = gameState.party.find(member => member.hp < member.maxHp);
        if (!target) {
            showBattleMessage("回復する必要のあるメンバーがいません。");
            return;
        }
        const healAmount = 20; // 回復量
        target.hp = Math.min(target.maxHp, target.hp + healAmount);
        gameState.inventory.find(item => item.name === "やくそう").count--;
        if (gameState.inventory.find(item => item.name === "やくそう").count <= 0) {
            gameState.inventory = gameState.inventory.filter(item => item.name !== "やくそう" || item.count > 0);
        }
        showBattleMessage(`${target.name} のHPが ${healAmount} 回復した！`);
        updatePartyStatusUI();
        setTimeout(handleEnemyTurn, 1500);
    }

    // 魔法を使用する関数
    function castSpell() {
        const mage = gameState.party.find(member => member.name === "まほうつかい");
        if (!mage || mage.mp < 5) {
            showBattleMessage("MPが足りない！");
            return;
        }
        const spell = prompt("魔法を選んでください: 回復, 攻撃");
        if (spell === "回復") {
            const target = gameState.party.find(member => member.hp < member.maxHp);
            if (!target) {
                showBattleMessage("回復する必要のあるメンバーがいません。");
                return;
            }
            target.hp = Math.min(target.maxHp, target.hp + 20);
            mage.mp -= 5;
            showBattleMessage(`${target.name} のHPが20回復した！`);
            updatePartyStatusUI();
        } else if (spell === "攻撃") {
            const damage = 20;
            currentEnemy.hp = Math.max(0, currentEnemy.hp - damage);
            mage.mp -= 5;
            showBattleMessage(`まほうつかいのじゅもん！ ${currentEnemy.name} に ${damage} のダメージ！`);
            if (currentEnemy.hp <= 0) {
                handleVictory();
                return;
            }
        } else {
            showBattleMessage("キャンセルしました。");
            return;
        }
        setTimeout(handleEnemyTurn, 1500);
    }

    // コマンドを実行する関数
    function executeCommand(command) {
        if (!isPlayerTurn) return;
        switch (command) {
            case 'attack':
                attack();
                break;
            case 'spell':
                castSpell();
                break;
            case 'defend':
                defend();
                break;
            case 'item':
                showInventory();
                break;
            case 'escape':
                escapeBattle();
                break;
        }
    }

    // 攻撃する関数
    function attack() {
        if (!isPlayerTurn || !currentEnemy) return;
        isPlayerTurn = false;
        const attacker = gameState.party[0];
        const damage = calculateDamage(attacker, currentEnemy);
        currentEnemy.hp = Math.max(0, currentEnemy.hp - damage);
        playSe('attack'); // 攻撃SE
        showBattleMessage(`${attacker.name} のこうげき！ ${currentEnemy.name} に ${damage} のダメージ！`);
        
        setTimeout(() => {
            if (currentEnemy.hp <= 0) {
                handleVictory();
            } else {
                handleEnemyTurn();
            }
        }, 1500);
    }

    // 逃げる関数
    function escapeBattle() {
        alert("うまく にげきれた！");
        endBattle();
    }

    // コマンドUIを更新する関数
    function updateCommandUI() {
        const commandItems = document.querySelectorAll('#command-list li');
        commandItems.forEach((item, index) => {
            if (index === currentCommandIndex) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        });
    }

    // ゲームの初期化（またはロード）
    function initializeGame(saveData = null) {
        if (saveData) {
            gameState = saveData;
        } else {
            gameState = {
                playerName: playerNameInput.value,
                bgmVolume: bgmVolumeInput.value,
                party: [
                    { name: playerNameInput.value, level: 1, hp: 20, maxHp: 20, mp: 10, maxMp: 10, attack: 15, defense: 8 },
                    { name: "せんし", level: 1, hp: 25, maxHp: 25, mp: 5, maxMp: 5, attack: 20, defense: 12 },
                    { name: "まほうつかい", level: 1, hp: 15, maxHp: 15, mp: 20, maxMp: 20, attack: 8, defense: 6 },
                    { name: "そうりょ", level: 1, hp: 18, maxHp: 18, mp: 15, maxMp: 15, attack: 10, defense: 7 },
                ],
                gold: 0,
                exp: 0,
                inventory: [{ name: "やくそう", count: 3 }], // 初期アイテム
            };
        }
        console.log("ゲームを開始しました:", gameState);
        updateStatusWindow();
        switchScreen('main');
    }

    // ステータスウィンドウを更新する関数 (メイン画面用)
    function updateStatusWindow() {
        const statusWindow = document.getElementById('status-window');
        let html = '<ul>';
        gameState.party.forEach(member => {
            html += `<li>${member.name} LV:${member.level} HP:${member.hp}</li>`;
        });
        html += '</ul>';
        // セーブボタン、セーブせず終了ボタン、セーブ管理ボタンを追加
        statusWindow.innerHTML = html +
            '<div class="status-actions">' +
            '<button id="save-button">冒険の書に記録する</button>' +
            '<button id="exit-without-save-button">終了（セーブしない）</button>' +
            '<button id="manage-saves-button">冒険の書を管理</button>' +
            '</div>' +
            (isAutoSaving ? '<div id="autosave-indicator" style="color: yellow; font-weight: bold;">自動保存中...</div>' : '');
        // ボタンイベント
        document.getElementById('save-button').addEventListener('click', () => {
            if (currentSaveSlot !== -1) {
                saveGame(currentSaveSlot);
            } else {
                showSaveSlotScreen('save');
            }
        });
        document.getElementById('exit-without-save-button').addEventListener('click', () => {
            exitWithoutSaving();
        });
        document.getElementById('manage-saves-button').addEventListener('click', () => {
            showSaveSlotScreen('delete');
        });
    }

    // マップを描画する関数
    function drawMap() {
        if (!ctx) return;
        ctx.fillStyle = 'black';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        if (!currentMapData) return;

        const mapLayout = currentMapData.layout;
        const tileDef = currentMapData.tiles;

        for (let y = 0; y < mapLayout.length; y++) {
            for (let x = 0; x < mapLayout[y].length; x++) {
                const tileId = mapLayout[y][x];
                const tileInfo = tileDef[tileId];

                if (tileInfo && tileInfo.image) {
                    const img = new Image();
                    img.src = tileInfo.image;
                    img.onload = () => {
                        ctx.drawImage(img, x * tileSize, y * tileSize, tileSize, tileSize);
                    };
                } else if (tileInfo && tileInfo.color) {
                    ctx.fillStyle = tileInfo.color;
                    ctx.fillRect(x * tileSize, y * tileSize, tileSize, tileSize);
                } else {
                    ctx.fillStyle = 'green'; // デフォルト
                    ctx.fillRect(x * tileSize, y * tileSize, tileSize, tileSize);
                }
            }
        }
    }

    // プレイヤーを描画する関数
    function drawPlayer() {
        if (!ctx) return;
        let img = playerImage; // デフォルト
        if (isMoving && playerImages[currentFrame]) {
            img = playerImages[currentFrame];
        }
        if (img.complete) {
            ctx.drawImage(img, player.x * tileSize, player.y * tileSize, player.size, player.size);
        } else {
            ctx.fillStyle = 'blue';
            ctx.fillRect(player.x * tileSize, player.y * tileSize, player.size, player.size);
        }
    }

    // NPCを描画する関数
    function drawNpcs() {
        if (!ctx || !currentMapData.npcs) return;
        currentMapData.npcs.forEach(npc => {
            const npcImage = new Image();
            npcImage.src = npc.image;
            npcImage.onload = () => {
                ctx.drawImage(npcImage, npc.x * tileSize, npc.y * tileSize, tileSize, tileSize);
            };
        });
    }

    // オブジェクトを描画する関数
    function drawObjects() {
        if (!ctx || !currentMapData || !currentMapData.objects) return;
        currentMapData.objects.forEach(obj => {
            if (obj.type === 'chest') {
                ctx.fillStyle = obj.opened ? 'gray' : 'brown';
                ctx.fillRect(obj.x * tileSize, obj.y * tileSize, tileSize, tileSize);
                ctx.fillStyle = 'yellow';
                ctx.fillText(obj.opened ? '開' : '宝', obj.x * tileSize + 5, obj.y * tileSize + 20);
            } else if (obj.type === 'image') {
                const img = new Image();
                img.src = obj.image;
                img.onload = () => {
                    ctx.drawImage(img, obj.x * tileSize, obj.y * tileSize, tileSize, tileSize);
                };
            }
        });
    }

    // ゲームループ (メインの処理)
    function gameLoop() {
        if (!canvas || !canvas.isConnected) return;
        canvas.width = canvas.clientWidth;
        canvas.height = canvas.clientHeight;
        drawMap();
        drawObjects();
        drawNpcs();
        drawPlayer();
        if (isMoving) {
            currentFrame = (currentFrame + 1) % 4;
        }
        requestAnimationFrame(gameLoop);
    }

    // キーボード入力の処理
    function handleKeyDown(e) {
        if (isInBattle && screens.battle.classList.contains('active')) {
            // 戦闘中のコマンド選択
            if (e.key === 'ArrowUp') {
                currentCommandIndex = (currentCommandIndex - 1 + commands.length) % commands.length;
                updateCommandUI();
                e.preventDefault();
            } else if (e.key === 'ArrowDown') {
                currentCommandIndex = (currentCommandIndex + 1) % commands.length;
                updateCommandUI();
                e.preventDefault();
            } else if (e.key === 'Enter') {
                executeCommand(commands[currentCommandIndex]);
                e.preventDefault();
            }
            return;
        }

        if (isInBattle || !screens.main.classList.contains('active') || !currentMapData) return;

        let playerMoved = false;
        let nextX = player.x;
        let nextY = player.y;

        switch (e.key) {
            case 'ArrowUp': case 'w': nextY--; break;
            case 'ArrowDown': case 's': nextY++; break;
            case 'ArrowLeft': case 'a': nextX--; break;
            case 'ArrowRight': case 'd': nextX++; break;
            case 'Enter': checkInn(); checkNpc(); checkObject(); return; // Enterで宿屋、NPC、オブジェクトチェック
            default: return;
        }

        const mapWidth = currentMapData.layout[0].length;
        const mapHeight = currentMapData.layout.length;

        if (nextX >= 0 && nextX < mapWidth && nextY >= 0 && nextY < mapHeight) {
            player.x = nextX;
            player.y = nextY;
            isMoving = true;
            setTimeout(() => isMoving = false, 200); // 200ms後に停止
            playerMoved = true;
        }

        if (playerMoved) {
            checkEncounter();
            checkWarp();
        }
    }

    // エンカウントをチェックする関数
    function checkEncounter() {
        const tileId = currentMapData.layout[player.y][player.x];
        const tileDef = currentMapData.tiles[tileId];
        if (tileDef && tileDef.encounter) {
            const ENCOUNTER_RATE = 0.1; // 10%
            if (Math.random() < ENCOUNTER_RATE) {
                startBattle();
            }
        }
    }

    // ワープをチェックする関数
    function checkWarp() {
        if (!currentMapData.warps) return;
        const warp = currentMapData.warps.find(w => w.x === player.x && w.y === player.y);
        if (warp) {
            loadMapData(warp.to).then(() => {
                player.x = warp.destX;
                player.y = warp.destY;
                console.log(`ワープ: ${warp.to} に移動`);
            });
        }
    }

    // 宿屋をチェックする関数
    function checkInn() {
        const tileId = currentMapData.layout[player.y][player.x];
        const tileDef = currentMapData.tiles[tileId];
        if (tileDef && tileDef.type === 'inn') {
            const cost = 10; // 宿屋料金
            if (gameState.gold >= cost) {
                if (confirm(`宿屋に泊まりますか？ (${cost}ゴールド)`)) {
                    gameState.gold -= cost;
                    gameState.party.forEach(member => {
                        member.hp = member.maxHp;
                        member.mp = member.maxMp; // MPも回復
                    });
                    alert("パーティ全員のHPが回復しました！");
                    updateStatusWindow();
                }
            } else {
                alert("ゴールドが足りません。");
            }
        }
    }

    // 戦闘を開始する関数
    function startBattle() {
        isInBattle = true;
        isPlayerTurn = true;
        const enemyTemplate = monsterData[Math.floor(Math.random() * monsterData.length)];
        currentEnemy = { ...enemyTemplate };
        
        // UIの更新
        updatePartyStatusTopUI(); // 新しい上部ステータスを更新
        updateEnemyInfoUI();      // 敵情報を更新
        document.getElementById('battle-monster-area').innerHTML = `<img src="${currentEnemy.image}" alt="${currentEnemy.name}">`;
        
        // メッセージを表示してコマンドを隠す
        showBattleMessage(`${currentEnemy.name} があらわれた！`);

        // 1.5秒後にコマンド表示に切り替え
        setTimeout(() => {
            showCommandWindow();
            currentCommandIndex = 0; // コマンド選択をリセット
            updateCommandUI();
        }, 1500);

        playBgm('battle'); // 戦闘BGM
        switchScreen('battle');
    }
    
    // 戦闘を終了する関数
    function endBattle() {
        isInBattle = false;
        playBgm(currentMapName); // マップBGMに戻す
        switchScreen('main');
    }
    
    // メッセージウィンドウを表示し、コマンドウィンドウを隠す
    function showBattleMessage(message) {
        battleMessage.textContent = message;
        battleMessageWindow.style.visibility = 'visible';
        battleCommandContainer.style.visibility = 'hidden';
    }

    // コマンドウィンドウを表示し、メッセージウィンドウを隠す
    function showCommandWindow() {
        battleMessageWindow.style.visibility = 'hidden';
        battleCommandContainer.style.visibility = 'visible';
    }

    // 上部のパーティーステータスUIを更新する関数
    function updatePartyStatusTopUI() {
        let html = '';
        gameState.party.forEach(member => {
            html += `
                <div class="party-member-status">
                    <div>${member.name}</div>
                    <div>H ${member.hp}</div>
                    <div>M ${member.mp}</div>
                    <div>Lv: ${member.level}</div>
                </div>
            `;
        });
        battlePartyStatusTop.innerHTML = html;
    }
    
    // 敵情報UIを更新する関数
    function updateEnemyInfoUI() {
        if(currentEnemy) {
            battleEnemyInfo.textContent = `${currentEnemy.name}`;
        }
    }

    // ダメージ計算を行う関数
    function calculateDamage(attacker, defender) {
        const baseDamage = (attacker.attack / 2) - (defender.defense / 4);
        if (baseDamage <= 0) return Math.random() < 0.5 ? 0 : 1;
        const damageVariance = baseDamage * 0.2;
        const randomVariance = (Math.random() * damageVariance * 2) - damageVariance;
        return Math.round(baseDamage + randomVariance);
    }
    
    // 敵のターン処理
    function handleEnemyTurn() {
        if (!currentEnemy || currentEnemy.hp <= 0) return;
        const target = gameState.party[Math.floor(Math.random() * gameState.party.length)];
        let damage = calculateDamage(currentEnemy, target);
        if (isDefending) {
            damage = Math.floor(damage / 2); // 防御でダメージ半減
            isDefending = false; // 防御解除
        }
        target.hp = Math.max(0, target.hp - damage);
        playSe('damage'); // ダメージSE
        updatePartyStatusTopUI(); // ダメージを反映
        showBattleMessage(`${currentEnemy.name} のこうげき！ ${target.name} は ${damage} のダメージをうけた。`);
        
        setTimeout(() => {
            isPlayerTurn = true;
            showCommandWindow(); // プレイヤーのターンになったらコマンドを再表示
            updateCommandUI(); // コマンドUI更新
            attackButton.disabled = false;
        }, 1500);
    }

    // パーティ全滅判定
    function isPartyWiped() {
        return gameState.party.every(member => member.hp <= 0);
    }

    // ゲームオーバー処理
    function gameOver() {
        showBattleMessage("目の前が真っ暗になった...");
        setTimeout(() => {
            alert("ゲームオーバー！ 最後にセーブした状態に戻ります。");
            if (currentSaveSlot !== -1) {
                loadGame(currentSaveSlot);
            } else {
                // セーブがない場合、初期化
                initializeGame();
            }
        }, 2000);
    }

    // 勝利処理
    function handleVictory() {
        showBattleMessage(`${currentEnemy.name} をやっつけた！`);
        gameState.exp += currentEnemy.exp;
        gameState.gold += currentEnemy.gold;
        console.log(`経験値: ${currentEnemy.exp}, ゴールド: ${currentEnemy.gold} を手に入れた！`);
        checkLevelUp(); // レベルアップチェック
        setTimeout(endBattle, 2000);
    }

    // NPCをチェックする関数
    function checkNpc() {
        if (!currentMapData.npcs) return;
        const adjacentPositions = [
            { x: player.x, y: player.y - 1 }, // 上
            { x: player.x, y: player.y + 1 }, // 下
            { x: player.x - 1, y: player.y }, // 左
            { x: player.x + 1, y: player.y }, // 右
        ];
        const npc = currentMapData.npcs.find(n => adjacentPositions.some(pos => pos.x === n.x && pos.y === n.y));
        if (npc) {
            startConversation(npc);
        }
    }

    // 会話を開始する関数
    function startConversation(npc) {
        switchScreen('battle'); // battle screenに切り替え
        let messageIndex = 0;
        const showNextMessage = () => {
            if (messageIndex < npc.messages.length) {
                showBattleMessage(npc.messages[messageIndex]);
                messageIndex++;
                // クリックで次へ（簡易的にsetTimeout）
                setTimeout(showNextMessage, 2000);
            } else {
                showBattleMessage(""); // 会話終了
                setTimeout(() => switchScreen('main'), 1000); // mainに戻る
            }
        };
        showNextMessage();
    }

    // オブジェクトをチェックする関数
    function checkObject() {
        if (!currentMapData.objects) return;
        const adjacentPositions = [
            { x: player.x, y: player.y - 1 }, // 上
            { x: player.x, y: player.y + 1 }, // 下
            { x: player.x - 1, y: player.y }, // 左
            { x: player.x + 1, y: player.y }, // 右
        ];
        const obj = currentMapData.objects.find(o => adjacentPositions.some(pos => pos.x === o.x && pos.y === o.y));
        if (obj && obj.type === 'chest' && !obj.opened) {
            obj.opened = true;
            switchScreen('battle'); // battle screenに切り替え
            // アイテム追加
            const existingItem = gameState.inventory.find(item => item.name === obj.item);
            if (existingItem) {
                existingItem.count++;
            } else {
                gameState.inventory.push({ name: obj.item, count: 1 });
            }
            showBattleMessage(`${obj.item} を手に入れた！`);
            setTimeout(() => {
                showBattleMessage("");
                switchScreen('main'); // mainに戻る
            }, 2000);
        }
    }

    // データの読み込み関数
    async function loadMonsterData() {
        try {
            const response = await fetch('data/monsters.json');
            if (!response.ok) throw new Error('Network response was not ok');
            monsterData = await response.json();
            console.log("モンスターデータを読み込みました:", monsterData);
        } catch (error) { console.error('モンスターデータの読み込みに失敗:', error); }
    }
    
    async function loadMapData(mapName) {
        try {
            const response = await fetch(`data/maps/${mapName}.json`);
            if (!response.ok) throw new Error(`マップファイルが見つかりません: ${mapName}.json`);
            currentMapData = await response.json();
            currentMapName = mapName;
            console.log("マップデータを読み込みました:", currentMapData);
            playBgm(mapName); // BGM再生
        } catch (error) { console.error('マップデータの読み込みに失敗:', error); }
    }

    // セーブ/ロード選択画面を表示
    function showSaveSlotScreen(mode) {
        // mode: 'save' | 'load' | 'delete'
        saveSlotMode = mode;
        isSaving = (mode === 'save');
        saveSlotTitle.textContent = isSaving ? "どこに記録しますか？" : "どの冒険の書をよみますか？";
        saveSlotsContainer.innerHTML = '';
        for (let i = 0; i < 3; i++) {
            const slotDataJSON = localStorage.getItem(`saveData_${i}`);
            const slotDiv = document.createElement('div');
            slotDiv.classList.add('save-slot');
            slotDiv.dataset.slotId = i;
            if (slotDataJSON) {
                const slotData = JSON.parse(slotDataJSON);
                slotDiv.innerHTML = `冒険の書${i + 1} <br> ${slotData.playerName}  LV:${slotData.party[0].level}`;
                if (mode === 'delete') {
                    const delBtn = document.createElement('button');
                    delBtn.classList.add('delete-save');
                    delBtn.textContent = '削除';
                    delBtn.style.marginLeft = '8px';
                    slotDiv.appendChild(delBtn);
                }
            } else {
                slotDiv.textContent = `冒険の書${i + 1} (データがありません)`;
                slotDiv.classList.add('empty');
            }
            saveSlotsContainer.appendChild(slotDiv);
        }
        switchScreen('saveSlot');
    }

    // セーブ処理
    function saveGame(slotId) {
        if (!gameState.playerName) {
            alert("エラー: セーブするゲームデータがありません。");
            return;
        }
        localStorage.setItem(`saveData_${slotId}`, JSON.stringify(gameState));
        alert(`冒険の書${slotId + 1}に きろくしました！`);
        switchScreen('main');
    }

    // 自動保存処理（autosave）
    function autoSave() {
        if (!enableAutosave) return;
        isAutoSaving = true;
        updateStatusWindow(); // インジケーター表示
        try {
            localStorage.setItem('autosave', JSON.stringify(gameState));
            // 通常セーブとは別枠：currentSaveSlot への上書きはしない
            // console.log('自動保存しました');
        } catch (e) {
            console.error('自動保存に失敗しました:', e);
        } finally {
            setTimeout(() => {
                isAutoSaving = false;
                updateStatusWindow(); // インジケーター非表示
            }, 1000); // 1秒後に非表示（視覚フィードバック）
        }
    }

    function startAutoSaveInterval() {
        if (autosaveIntervalId) clearInterval(autosaveIntervalId);
        autosaveIntervalId = setInterval(autoSave, 900000); // 15分ごと
    }

    // 冒険の書を削除する関数
    function deleteSaveSlot(slotId) {
        if (!confirm(`本当に 冒険の書${slotId + 1} を削除しますか？ この操作は取り消せません。`)) return;
        localStorage.removeItem(`saveData_${slotId}`);
        alert(`冒険の書${slotId + 1} を削除しました。`);
        showSaveSlotScreen(saveSlotMode === 'delete' ? 'delete' : 'load');
    }

    // セーブせずに終了する（自動保存を無効化してタイトルに戻る）
    function exitWithoutSaving() {
        if (!confirm('セーブせずに終了しますか？ 進行は保存されません。')) return;
        enableAutosave = false;
        // 自動セーブのキーを削除（直前の自動保存を消す）
        localStorage.removeItem('autosave');
        if (autosaveIntervalId) { clearInterval(autosaveIntervalId); autosaveIntervalId = null; }
        // ゲーム状態を一旦クリアしてタイトルへ
        gameState = {};
        currentSaveSlot = -1;
        switchScreen('start');
    }

    // ロード処理
    function loadGame(slotId) {
        const savedDataJSON = localStorage.getItem(`saveData_${slotId}`);
        if (savedDataJSON) {
            const savedData = JSON.parse(savedDataJSON);
            currentSaveSlot = slotId;
            alert(`冒険の書${slotId + 1}をよみこみました。\nようこそ、${savedData.playerName}さん。`);
            initializeGame(savedData);
        } else {
            alert("この冒険の書にはデータがありません。");
        }
    }

    // 名前の入力チェック
    function validatePlayerName(name) {
        const regex = /^[ぁ-んァ-ヶーa-zA-Z0-9\s]+$/;
        return regex.test(name) && name.length > 0 && name.length <= 8;
    }

    // --- イベントリスナーの設定 ---
    document.addEventListener('keydown', handleKeyDown);

    buttons.start.addEventListener('click', () => switchScreen('config'));
    buttons.load.addEventListener('click', () => showSaveSlotScreen('load'));
    buttons.resume.addEventListener('click', () => showSaveSlotScreen('load'));
    buttons.backToStart.addEventListener('click', () => switchScreen('start'));

    buttons.configComplete.addEventListener('click', () => {
        const playerName = playerNameInput.value;
        if (validatePlayerName(playerName)) {
            initializeGame();
            showSaveSlotScreen('save');
        } else {
            alert("名前は1～8文字の、ひらがな、カタカナ、英数字で入力してください。");
        }
    });
    
    saveSlotsContainer.addEventListener('click', (event) => {
        const clickedSlot = event.target.closest('.save-slot');
        if (!clickedSlot) return;
        const slotId = parseInt(clickedSlot.dataset.slotId, 10);
        if (saveSlotMode === 'save') {
            if (clickedSlot.classList.contains('empty') || confirm(`冒険の書${slotId + 1}のデータに上書きしますか？`)) {
                currentSaveSlot = slotId;
                saveGame(slotId);
            }
        } else if (saveSlotMode === 'load') {
            loadGame(slotId);
        } else if (saveSlotMode === 'delete') {
            // 削除ボタンがクリックされた場合のみ削除、スロット領域クリックで詳細や確認も可
            if (event.target.classList.contains('delete-save')) {
                deleteSaveSlot(slotId);
            } else {
                if (confirm(`冒険の書${slotId + 1} を削除しますか？`)) {
                    deleteSaveSlot(slotId);
                }
            }
        }
    });

    // --- 初期化処理 ---
    playBgm('title'); // 読み込み画面でBGM再生
    setTimeout(() => {
        window.location.href = 'index4.html'; // スタート画面へ遷移
    }, 3000);

    loadMonsterData();
    // 自動保存間隔開始
    startAutoSaveInterval();

    // ページ離脱やタブ非表示のタイミングで自動保存（ただしセーブせず終了を選んだ場合は無効）
    window.addEventListener('beforeunload', (e) => {
        if (enableAutosave) autoSave();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && enableAutosave) autoSave();
    });

    // 起動時に自動保存があれば復元するか確認
    const autosaveJSON = localStorage.getItem('autosave');
    if (autosaveJSON) {
        if (confirm('自動保存のデータが見つかりました。前回の途中から再開しますか？')) {
            try {
                const saved = JSON.parse(autosaveJSON);
                currentSaveSlot = -1;
                initializeGame(saved);
                startAutoSaveInterval();
            } catch (e) { console.error('自動保存の復元に失敗しました:', e); }
        }
    }
});