document.addEventListener('DOMContentLoaded', () => {
    // --- 要素の取得 ---
    const screens = {
        loading: document.getElementById('loading-screen'),
        start: document.getElementById('start-screen'),
        saveSlot: document.getElementById('save-slot-screen'),
        config: document.getElementById('config-screen'),
        main: document.getElementById('main-game-screen'),
        battle: document.getElementById('battle-screen'),
    };

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
    const battlePartyStatus = document.getElementById('battle-party-status');
    const saveSlotsContainer = document.getElementById('save-slots-container');
    const saveSlotTitle = document.getElementById('save-slot-title');
    const playerNameInput = document.getElementById('player-name');
    const bgmVolumeInput = document.getElementById('bgm-volume');

    const canvas = document.getElementById('game-canvas');
    const ctx = canvas.getContext('2d');

    const playerImage = new Image();
    playerImage.src = 'images/player/hero.png';
    let isPlayerImageLoaded = false;
    playerImage.onload = () => { isPlayerImageLoaded = true; console.log("プレイヤー画像を読み込みました。"); };
    playerImage.onerror = () => { console.error("プレイヤー画像の読み込みに失敗しました。"); };

    const tilesetImage = new Image();
    tilesetImage.src = 'images/tileset/field_tiles.png';
    let isTilesetLoaded = false;
    tilesetImage.onload = () => { isTilesetLoaded = true; console.log("タイルセット画像を読み込みました。"); };
    tilesetImage.onerror = () => { console.error("タイルセット画像の読み込みに失敗しました。"); };

    // --- ゲームの状態管理 ---
    let gameState = {};
    let monsterData = [];
    let currentMapData = null;
    let player = { x: 5, y: 5, size: 32 };
    const tileSize = 32;

    let isInBattle = false;
    let currentEnemy = null;
    let isPlayerTurn = true;
    
    let currentSaveSlot = -1;
    let isSaving = false;

    // --- 関数定義 ---

    // 画面を切り替える関数
    function switchScreen(screenName) {
        Object.values(screens).forEach(screen => screen.classList.remove('active'));
        screens[screenName].classList.add('active');
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
                    { name: playerNameInput.value, level: 1, hp: 20, maxHp: 20, attack: 15, defense: 8 },
                    { name: "せんし", level: 1, hp: 25, maxHp: 25, attack: 20, defense: 12 },
                    { name: "まほうつかい", level: 1, hp: 15, maxHp: 15, attack: 8, defense: 6 },
                    { name: "そうりょ", level: 1, hp: 18, maxHp: 18, attack: 10, defense: 7 },
                ],
                gold: 0,
                exp: 0,
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
        // 元のHTMLからボタンを除いた部分を更新する（少し複雑なので、簡略化）
        statusWindow.innerHTML = html + '<button id="save-button">冒険の書に記録する</button>';
        // ボタンに再度イベントリスナーを割り当てる必要があるので注意
        document.getElementById('save-button').addEventListener('click', () => {
             if (currentSaveSlot !== -1) {
                saveGame(currentSaveSlot);
            } else {
                showSaveSlotScreen('save');
            }
        });
    }

    // マップを描画する関数
    function drawMap() {
        ctx.fillStyle = 'black';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        if (!currentMapData || !isTilesetLoaded) return;

        const mapLayout = currentMapData.layout;
        const tileDef = currentMapData.tiles;
        const tileWidth = currentMapData.tileWidth;

        for (let y = 0; y < mapLayout.length; y++) {
            for (let x = 0; x < mapLayout[y].length; x++) {
                const tileId = mapLayout[y][x];
                const tileInfo = tileDef.find(t => t.sourceX === tileId);

                if (tileInfo) {
                    const sourceX = tileInfo.sourceX * tileWidth;
                    ctx.drawImage(tilesetImage, sourceX, 0, tileWidth, tileWidth, x * tileSize, y * tileSize, tileSize, tileSize);
                }
            }
        }
    }

    // プレイヤーを描画する関数
    function drawPlayer() {
        if (isPlayerImageLoaded) {
            ctx.drawImage(playerImage, player.x * tileSize, player.y * tileSize, player.size, player.size);
        } else {
            ctx.fillStyle = 'blue';
            ctx.fillRect(player.x * tileSize, player.y * tileSize, player.size, player.size);
        }
    }

    // ゲームループ (メインの処理)
    function gameLoop() {
        if (!canvas.isConnected) return;
        canvas.width = canvas.clientWidth;
        canvas.height = canvas.clientHeight;
        drawMap();
        drawPlayer();
        requestAnimationFrame(gameLoop);
    }

    // キーボード入力の処理
    function handleKeyDown(e) {
        if (isInBattle || !screens.main.classList.contains('active') || !currentMapData) return;

        let playerMoved = false;
        let nextX = player.x;
        let nextY = player.y;

        switch (e.key) {
            case 'ArrowUp': case 'w': nextY--; break;
            case 'ArrowDown': case 's': nextY++; break;
            case 'ArrowLeft': case 'a': nextX--; break;
            case 'ArrowRight': case 'd': nextX++; break;
            default: return;
        }

        const mapWidth = currentMapData.layout[0].length;
        const mapHeight = currentMapData.layout.length;

        if (nextX >= 0 && nextX < mapWidth && nextY >= 0 && nextY < mapHeight) {
            player.x = nextX;
            player.y = nextY;
            playerMoved = true;
        }

        if (playerMoved) {
            checkEncounter();
        }
    }

    // エンカウントをチェックする関数
    function checkEncounter() {
        const tileId = currentMapData.layout[player.y][player.x];
        const tileDef = currentMapData.tiles.find(t => t.sourceX === tileId);
        if (tileDef && tileDef.encounter) {
            const ENCOUNTER_RATE = 0.1; // 10%
            if (Math.random() < ENCOUNTER_RATE) {
                startBattle();
            }
        }
    }

    // 戦闘を開始する関数
    function startBattle() {
        isInBattle = true;
        isPlayerTurn = true;
        const enemyTemplate = monsterData[Math.floor(Math.random() * monsterData.length)];
        currentEnemy = { ...enemyTemplate };
        updateBattleMessage(`${currentEnemy.name} があらわれた！`);
        document.getElementById('battle-monster-area').innerHTML = `<img src="${currentEnemy.image}" alt="${currentEnemy.name}">`;
        updatePartyStatusUI();
        attackButton.disabled = false;
        switchScreen('battle');
    }
    
    // 戦闘を終了する関数
    function endBattle() {
        isInBattle = false;
        switchScreen('main');
    }
    
    // 戦闘メッセージを更新するヘルパー関数
    function updateBattleMessage(message) {
        document.getElementById('battle-message').textContent = message;
    }

    // 味方パーティのステータスUIを更新する関数
    function updatePartyStatusUI() {
        let html = '<ul>';
        gameState.party.forEach(member => {
            html += `<li>${member.name} HP: ${member.hp}/${member.maxHp}</li>`;
        });
        html += '</ul>';
        battlePartyStatus.innerHTML = html;
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
        const damage = calculateDamage(currentEnemy, target);
        target.hp = Math.max(0, target.hp - damage);
        updateBattleMessage(`${currentEnemy.name} のこうげき！ ${target.name} は ${damage} のダメージをうけた。`);
        updatePartyStatusUI();
        isPlayerTurn = true;
        attackButton.disabled = false;
    }

    // 勝利処理
    function handleVictory() {
        updateBattleMessage(`${currentEnemy.name} をやっつけた！`);
        gameState.exp += currentEnemy.exp;
        gameState.gold += currentEnemy.gold;
        console.log(`経験値: ${currentEnemy.exp}, ゴールド: ${currentEnemy.gold} を手に入れた！`);
        setTimeout(endBattle, 2000);
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
            console.log("マップデータを読み込みました:", currentMapData);
        } catch (error) { console.error('マップデータの読み込みに失敗:', error); }
    }

    // セーブ/ロード選択画面を表示
    function showSaveSlotScreen(mode) {
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
        if (isSaving) {
            if (clickedSlot.classList.contains('empty') || confirm(`冒険の書${slotId + 1}のデータに上書きしますか？`)) {
                currentSaveSlot = slotId;
                saveGame(slotId);
            }
        } else {
            loadGame(slotId);
        }
    });

    escapeButton.addEventListener('click', () => {
        alert("うまく にげきれた！");
        endBattle();
    });

    attackButton.addEventListener('click', () => {
        if (!isPlayerTurn || !currentEnemy) return;
        isPlayerTurn = false;
        attackButton.disabled = true;
        const attacker = gameState.party[0];
        const damage = calculateDamage(attacker, currentEnemy);
        currentEnemy.hp = Math.max(0, currentEnemy.hp - damage);
        updateBattleMessage(`${attacker.name} のこうげき！ ${currentEnemy.name} に ${damage} のダメージ！`);
        if (currentEnemy.hp <= 0) {
            handleVictory();
        } else {
            setTimeout(handleEnemyTurn, 1500);
        }
    });

    // --- 初期化処理 ---
    setTimeout(() => {
        switchScreen('start');
    }, 3000);

    loadMonsterData();
    loadMapData('field');
    gameLoop();
});