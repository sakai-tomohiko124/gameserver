// グローバル変数
let bgmPlayed = false;
let tileImages = {}; // タイル画像キャッシュ

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
        Object.values(screens).forEach(screen => screen.classList.remove('active'));
        screens[screenName].classList.add('active');
    } else {
        console.error(`Screen '${screenName}' not found`);
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
        deleteSave: document.getElementById('delete-save-button'),
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
    playerImage.onload = () => {
        isPlayerImageLoaded = true;
        tileImages['images/player/hero.png'] = playerImage;
        console.log('プレイヤー画像を読み込みました。');
    };
    playerImage.onerror = () => {
        console.error('プレイヤー画像の読み込みに失敗しました。');
    };

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
    const commands = ['attack', 'spell', 'defend', 'item', 'escape', 'move'];
    // 自動保存制御
    let enableAutosave = true; // セーブせず終了を選んだ場合 false にする
    let autosaveIntervalId = null;
    let saveSlotMode = 'load'; // 'save' | 'load' | 'delete'
    let isAutoSaving = false; // 自動保存中フラグ

    // 経験値テーブル (レベルnに必要な累積経験値)
    const expTable = [0, 10, 30, 70, 150, 250, 400, 600, 900, 1300, 1800, 2400, 3200, 4200, 5400, 6800, 8400, 10200, 12300, 14700];

    // BGM再生関数
    function playBgm(mapName) {
        const bgmAudio = document.getElementById('bgm');
        if (!bgmAudio) return;
        const bgmSrc = `bgm/${mapName}.mp3`;
        bgmAudio.src = bgmSrc;
        bgmAudio.volume = parseFloat(localStorage.getItem('bgmVolume')) || 0.3;
        bgmAudio.muted = true; // 自動再生ポリシーを回避するため最初はmute
        bgmAudio.play().catch(e => console.error('BGM play failed:', e));
    }

    // SE再生関数
    function playSe(seName) {
        const seAudio = document.getElementById('se');
        if (!seAudio) return;
        seAudio.src = `se/${seName}.mp3`;
        seAudio.volume = 0.5;
        seAudio.play().catch(e => console.log('SE play failed:', e));
    }

    // モンスターデータ読み込み関数
    async function loadMonsterData() {
        try {
            const response = await fetch('data/monsters.json');
            monsterData = await response.json();
            console.log('モンスターデータを読み込みました:', monsterData);
        } catch (error) {
            console.error('モンスターデータの読み込みに失敗しました:', error);
        }
    }

    // マップデータ読み込み関数
    async function loadMapData(mapName) {
        try {
            const response = await fetch(`data/maps/${mapName}.json`);
            currentMapData = await response.json();
            console.log(`マップデータを読み込みました: ${mapName}`, currentMapData);
            // マップサイズ設定
            currentMapData.width = currentMapData.layout[0].length;
            currentMapData.height = currentMapData.layout.length;
            // タイル画像をキャッシュ
            currentMapData.tiles.forEach(tile => {
                if (tile.image) {
                    tileImages[tile.image] = new Image();
                    tileImages[tile.image].src = tile.image;
                }
            });
        } catch (error) {
            console.error(`マップデータの読み込みに失敗しました: ${mapName}`, error);
        }
    }

    // ゲーム状態保存関数
    function saveGameState(slot) {
        const state = {
            gameState,
            currentMapName,
            player,
            currentEnemy,
            isInBattle,
            isPlayerTurn,
            currentCommandIndex,
            playerName: localStorage.getItem('playerName'),
            bgmVolume: localStorage.getItem('bgmVolume')
        };
        localStorage.setItem(`saveSlot${slot}`, JSON.stringify(state));
        console.log(`ゲーム状態をセーブしました: スロット ${slot}`);
    }

    // ゲーム状態読み込み関数
    function loadGameState(slot) {
        const stateStr = localStorage.getItem(`saveSlot${slot}`);
        if (!stateStr) return false;
        const state = JSON.parse(stateStr);
        gameState = state.gameState || {};
        currentMapName = state.currentMapName || 'field';
        player = state.player || { x: 5, y: 5, size: 32 };
        currentEnemy = state.currentEnemy || null;
        isInBattle = state.isInBattle || false;
        isPlayerTurn = state.isPlayerTurn || true;
        currentCommandIndex = state.currentCommandIndex || 0;
        localStorage.setItem('playerName', state.playerName || 'ヒーロー');
        localStorage.setItem('bgmVolume', state.bgmVolume || 0.3);
        console.log(`ゲーム状態をロードしました: スロット ${slot}`);
        return true;
    }

    // 自動保存関数
    function startAutosave() {
        if (autosaveIntervalId) clearInterval(autosaveIntervalId);
        autosaveIntervalId = setInterval(() => {
            if (enableAutosave && !isAutoSaving) {
                isAutoSaving = true;
                saveGameState('auto');
                setTimeout(() => isAutoSaving = false, 1000);
            }
        }, 30000); // 30秒ごとに自動保存
    }

    // 自動保存停止関数
    function stopAutosave() {
        if (autosaveIntervalId) {
            clearInterval(autosaveIntervalId);
            autosaveIntervalId = null;
        }
    }

    // ステータスウィンドウ更新関数
    function updateStatusWindow() {
        const statusWindow = document.getElementById('status-window');
        if (!statusWindow) return;
        const playerName = localStorage.getItem('playerName') || 'ヒーロー';
        const level = gameState.level || 1;
        const hp = gameState.hp || 100;
        const mp = gameState.mp || 50;
        const exp = gameState.exp || 0;
        statusWindow.innerHTML = `
            <p>名前: ${playerName}</p>
            <p>レベル: ${level}</p>
            <p>HP: ${hp}</p>
            <p>MP: ${mp}</p>
            <p>経験値: ${exp}</p>
        `;
    }

    // コマンドリスト表示関数
    function showCommandList() {
        const commandList = document.getElementById('command-list');
        if (!commandList) return;
        commandList.classList.remove('hidden');
        currentCommandIndex = 0;
        updateCommandSelection();
    }

    // コマンドリスト非表示関数
    function hideCommandList() {
        const commandList = document.getElementById('command-list');
        if (!commandList) return;
        commandList.classList.add('hidden');
    }

    // コマンド選択更新関数
    function updateCommandSelection() {
        const commandList = document.getElementById('command-list');
        if (!commandList) return;
        const lis = commandList.querySelectorAll('li');
        lis.forEach((li, index) => {
            li.classList.toggle('selected', index === currentCommandIndex);
        });
    }

    // コマンド実行関数
    function executeCommand(command) {
        switch (command) {
            case 'attack':
                if (isInBattle) {
                    performAttack();
                } else {
                    console.log('攻撃コマンド実行');
                }
                break;
            case 'spell':
                console.log('呪文コマンド実行');
                break;
            case 'defend':
                console.log('防御コマンド実行');
                break;
            case 'item':
                console.log('道具コマンド実行');
                break;
            case 'escape':
                console.log('逃げるコマンド実行');
                break;
            case 'move':
                hideCommandList();
                break;
        }
    }

    // 攻撃実行関数
    function performAttack() {
        if (!currentEnemy) return;
        const damage = Math.floor(Math.random() * 20) + 10;
        currentEnemy.hp -= damage;
        console.log(`攻撃: ${damage} ダメージ与えた`);
        if (currentEnemy.hp <= 0) {
            console.log('敵を倒した');
            isInBattle = false;
            currentEnemy = null;
            playBgm('field');
            window.location.href = 'index2.html';
        } else {
            isPlayerTurn = false;
            enemyTurn();
        }
    }

    // 敵ターン関数
    function enemyTurn() {
        if (!currentEnemy) return;
        const damage = Math.floor(Math.random() * 15) + 5;
        gameState.hp -= damage;
        console.log(`敵の攻撃: ${damage} ダメージ受けた`);
        if (gameState.hp <= 0) {
            console.log('プレイヤー敗北');
            // ゲームオーバー処理
        } else {
            isPlayerTurn = true;
        }
    }

    // ゲーム初期化関数
    async function initializeGame() {
        await loadMonsterData();
        await loadMapData('field');
        gameState = {
            level: 1,
            hp: 100,
            mp: 50,
            exp: 0
        };
        player = { x: 5, y: 5, size: 32 };
        currentMapName = 'field';
        isInBattle = false;
        currentEnemy = null;
        isPlayerTurn = true;
        currentCommandIndex = 0;
        console.log('ゲームを開始しました:', gameState);
        updateStatusWindow();
        playBgm('field');
        startAutosave();
        renderGame();
    }

    // ゲームレンダリング関数
    function renderGame() {
        if (!ctx || !currentMapData) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        // マップ描画
        currentMapData.layout.forEach((row, y) => {
            row.forEach((tileIndex, x) => {
                const tile = currentMapData.tiles[tileIndex];
                if (tile) {
                    if (tile.image && tileImages[tile.image]) {
                        ctx.drawImage(tileImages[tile.image], x * tileSize, y * tileSize, tileSize, tileSize);
                    } else if (tile.color) {
                        ctx.fillStyle = tile.color;
                        ctx.fillRect(x * tileSize, y * tileSize, tileSize, tileSize);
                    }
                }
            });
        });
        // プレイヤー描画
        if (tileImages['images/player/hero.png']) {
            ctx.drawImage(tileImages['images/player/hero.png'], player.x * tileSize, player.y * tileSize, player.size, player.size);
        }
    }    // キー入力処理関数
    function handleKeyDown(event) {
        if (!bgmPlayed) {
            const bgmAudio = document.getElementById('bgm');
            if (bgmAudio) {
                bgmAudio.muted = false; // ユーザー操作後にunmute
            }
            bgmPlayed = true;
        }
        if (isInBattle) return;
        const commandList = document.getElementById('command-list');
        if (!commandList) return;
        switch (event.key) {
            case 'ArrowUp':
                if (commandList.classList.contains('hidden')) {
                    const newY = player.y - 1;
                    if (newY >= 0 && newY < currentMapData.height) {
                        const tileIndex = currentMapData.layout[newY][player.x];
                        const tile = currentMapData.tiles[tileIndex];
                        if (tile.walkable) {
                            player.y = newY;
                            if (tile.encounter) {
                                // 戦闘開始
                                startBattle();
                            }
                        }
                    }
                } else {
                    currentCommandIndex = Math.max(0, currentCommandIndex - 1);
                    updateCommandSelection();
                }
                break;
            case 'ArrowDown':
                if (commandList.classList.contains('hidden')) {
                    const newY = player.y + 1;
                    if (newY >= 0 && newY < currentMapData.height) {
                        const tileIndex = currentMapData.layout[newY][player.x];
                        const tile = currentMapData.tiles[tileIndex];
                        if (tile.walkable) {
                            player.y = newY;
                            if (tile.encounter) {
                                startBattle();
                            }
                        }
                    }
                } else {
                    currentCommandIndex = Math.min(commands.length - 1, currentCommandIndex + 1);
                    updateCommandSelection();
                }
                break;
            case 'ArrowLeft':
                const newXLeft = player.x - 1;
                if (newXLeft >= 0 && newXLeft < currentMapData.width) {
                    const tileIndex = currentMapData.layout[player.y][newXLeft];
                    const tile = currentMapData.tiles[tileIndex];
                    if (tile.walkable) {
                        player.x = newXLeft;
                        if (tile.encounter) {
                            startBattle();
                        }
                    }
                }
                break;
            case 'ArrowRight':
                const newXRight = player.x + 1;
                if (newXRight >= 0 && newXRight < currentMapData.width) {
                    const tileIndex = currentMapData.layout[player.y][newXRight];
                    const tile = currentMapData.tiles[tileIndex];
                    if (tile.walkable) {
                        player.x = newXRight;
                        if (tile.encounter) {
                            startBattle();
                        }
                    }
                }
                break;
            case 'Enter':
                if (!commandList.classList.contains('hidden')) {
                    executeCommand(commands[currentCommandIndex]);
                    hideCommandList();
                } else {
                    showCommandList();
                }
                break;
            case 'Escape':
                hideCommandList();
                break;
        }
        renderGame();
    }

    // イベントリスナー設定
    document.addEventListener('keydown', handleKeyDown);

    if (buttons.start) buttons.start.addEventListener('click', () => switchScreen('config'));
    if (buttons.load) buttons.load.addEventListener('click', () => {
        saveSlotMode = 'load';
        switchScreen('saveSlot');
    });
    if (buttons.resume) buttons.resume.addEventListener('click', () => {
        if (loadGameState('auto')) {
            switchScreen('game');
            renderGame();
        }
    });
    if (buttons.backToStart) buttons.backToStart.addEventListener('click', () => switchScreen('start'));
    if (buttons.configComplete) {
        buttons.configComplete.addEventListener('click', () => {
            // 名前とBGM音量を保存
            const playerName = playerNameInput ? playerNameInput.value : 'ヒーロー';
            const bgmVolume = bgmVolumeInput ? bgmVolumeInput.value : 0.3;
            localStorage.setItem('playerName', playerName);
            localStorage.setItem('bgmVolume', bgmVolume);
            // index2.html に遷移
            window.location.href = 'index2.html';
        });
    }
    if (buttons.save) buttons.save.addEventListener('click', () => {
        saveSlotMode = 'save';
        switchScreen('saveSlot');
    });
    if (buttons.deleteSave) buttons.deleteSave.addEventListener('click', () => {
        saveSlotMode = 'delete';
        switchScreen('saveSlot');
    });

    if (attackButton) attackButton.addEventListener('click', () => executeCommand('attack'));
    if (escapeButton) escapeButton.addEventListener('click', () => executeCommand('escape'));
    if (itemButton) itemButton.addEventListener('click', () => executeCommand('item'));
    if (spellButton) spellButton.addEventListener('click', () => executeCommand('spell'));
    if (defendButton) defendButton.addEventListener('click', () => executeCommand('defend'));

    // セーブスロット生成関数
    function generateSaveSlots() {
        if (!saveSlotsContainer) return;
        saveSlotsContainer.innerHTML = '';
        for (let i = 1; i <= 3; i++) {
            const slotDiv = document.createElement('div');
            slotDiv.className = 'save-slot';
            const stateStr = localStorage.getItem(`saveSlot${i}`);
            let slotText = `スロット ${i}: `;
            if (stateStr) {
                const state = JSON.parse(stateStr);
                slotText += `${state.playerName || 'ヒーロー'} Lv.${state.gameState?.level || 1}`;
            } else {
                slotText += '空き';
            }
            slotDiv.textContent = slotText;
            slotDiv.addEventListener('click', () => {
                if (saveSlotMode === 'save') {
                    saveGameState(i);
                    alert(`セーブしました: スロット ${i}`);
                    switchScreen('game');
                } else if (saveSlotMode === 'load') {
                    if (loadGameState(i)) {
                        switchScreen('game');
                        renderGame();
                    } else {
                        alert('セーブデータがありません');
                    }
                } else if (saveSlotMode === 'delete') {
                    if (confirm(`スロット ${i} のデータを削除しますか？`)) {
                        localStorage.removeItem(`saveSlot${i}`);
                        generateSaveSlots();
                    }
                }
            });
            saveSlotsContainer.appendChild(slotDiv);
        }
    }

    // セーブスロット画面表示関数
    function showSaveSlotScreen(mode) {
        saveSlotMode = mode;
        if (saveSlotTitle) saveSlotTitle.textContent = mode === 'load' ? '冒険の書をえらんでください' : mode === 'save' ? 'セーブスロットをえらんでください' : '削除するスロットをえらんでください';
        generateSaveSlots();
        switchScreen('saveSlot');
    }

    // 戦闘開始関数
    function startBattle() {
        const monster = monsterData[Math.floor(Math.random() * monsterData.length)];
        currentEnemy = { ...monster, hp: monster.hp };
        isInBattle = true;
        isPlayerTurn = true;
        currentCommandIndex = 0;
        window.location.href = 'index3.html';
    }

    // ゲームループ関数
    function gameLoop() {
        renderGame();
        requestAnimationFrame(gameLoop);
    }

    // 初期化
    loadMonsterData();
    loadMapData('field');
});