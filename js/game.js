// ゲーム状態の定義
const GameState = {
    MESSAGE: 'MESSAGE',
    COMMAND_SELECT: 'COMMAND_SELECT',
    SKILL_SELECT: 'SKILL_SELECT',
    SPELL_SELECT: 'SPELL_SELECT',
    ITEM_SELECT: 'ITEM_SELECT',
    EQUIP_SELECT: 'EQUIP_SELECT',
    TARGET_SELECT: 'TARGET_SELECT',
    EVENT: 'EVENT'
};

// キャラクタークラス
class Character {
    constructor(name, level, hp, mp, attack, defense, imagePath, options = {}) {
        this.name = name;
        this.level = level;
        this.hp = hp;
        this.maxHp = hp;
        this.mp = mp;
        this.maxMp = mp;
        this.baseAttack = attack;
        this.defense = defense;
        this.imagePath = imagePath;
        
        this.skills = options.skills || [];
        this.spells = options.spells || [];
        this.equipment = options.equipment || null;
        this.weaponName = options.weaponName || null;
        
        this.isDefending = false;
        this.isNioDachi = false;
        this.dazzleTurns = 0;
        this.laughingTurns = 0;
        
        this.recalculateStats();
    }
    
    isAlive() {
        return this.hp > 0;
    }
    
    recalculateStats() {
        const weaponAttack = this.equipment ? this.equipment.attack : 0;
        this.attack = this.baseAttack + weaponAttack;
    }
    
    equip(weaponItem, weaponName) {
        this.equipment = weaponItem;
        this.weaponName = weaponName;
        this.recalculateStats();
    }
    
    unequip() {
        this.equipment = null;
        this.weaponName = null;
        this.recalculateStats();
    }
}

// ゲームクラス
class Game {
    constructor() {
        this.canvas = document.getElementById('battle-canvas');
        this.ctx = this.canvas.getContext('2d');
        
        this.gameState = GameState.MESSAGE;
        this.selectedCommandIndex = 0;
        this.selectedSubmenuIndex = 0;
        this.selectedTargetIndex = 0;
        
        this.currentAttacker = null;
        this.nioDachiCharacter = null;
        this.activeItem = null;
        this.lastCommand = null;
        
        this.currentTurnIndex = 0;
        this.turnOrder = [];
        
        this.bgm = document.getElementById('bgm');
        
        this.commandDescriptions = {
            'こうげき': '装備している武器で 敵に攻撃する。',
            'とくぎ': 'MPを消費して 特殊な技を使う。',
            'じゅもん': 'MPを消費して 魔法をとなえる。',
            'どうぐ': '持っている道具を使って さまざまな効果を発揮する。',
            'ぼうぎょ': '次のターン受けるダメージを 半分にする。',
            'そうび': '武器を装備したり 外したりする。(ターンは消費しない)'
        };
        
        this.abilityDescriptions = {
            'バーカード': 'すべての攻撃を自分に引きつけ、仲間を守る。',
            'ひらめく': 'とんちんかんな答えで 敵を笑わせ、1回動けなくする。',
            'ライム斬り': 'ゴライム系の敵に 通常の2倍のダメージを与える。',
            'ハレタ': 'まばゆい光で 敵の目をくらませ、攻撃を当たりにくくする。',
            'ムテラル': '仲間全員のHPとMPを すべて回復する。',
            'マジックダンス': '不思議な踊りで 仲間全員のMPを すべて回復する。',
            'アホ草': '仲間ひとりのHPとMPを 少しだけ回復する。'
        };
        
        this.weapons = {
            'オバカーノ剣': { attack: 100 },
            '手羽先': { attack: 50 },
            'マジックステッキ': { attack: 30 }
        };
        
        this.characterWeapons = {
            'アリス': 'オバカーノ剣',
            'キーミー': '手羽先',
            'ソリベル': 'マジックステッキ'
        };
        
        this.inventory = { 'アホ草': 10 };
        
        // 元の姿をランダムに設定
        const originalImages = ['images/monsters/doraky.png', 'images/monsters/slime.png', 'images/player/hero.png'];
        this.originalGolimeImagePath = originalImages[Math.floor(Math.random() * originalImages.length)];
        this.originalGolimeName = "仲間キャラ";
        
        this.images = {};
        this.loadImages();
    }
    
    loadImages() {
        const imageList = [
            { key: 'background', src: 'images/mon2.jpg' },
            { key: 'enemy', src: 'images/monsters/ゴライム.png' },
            { key: 'hero1', src: 'images/player/hero.png' },
            { key: 'hero2', src: 'images/player/hero2.png' },
            { key: 'hero3', src: 'images/player/hero3.png' },
            { key: 'lime', src: this.originalGolimeImagePath }
        ];
        
        let loadedCount = 0;
        
        imageList.forEach(item => {
            const img = new Image();
            img.onload = () => {
                this.images[item.key] = img;
                loadedCount++;
                if (loadedCount === imageList.length) {
                    this.init();
                }
            };
            img.onerror = () => {
                console.error(`画像の読み込みエラー: ${item.src}`);
                loadedCount++;
                if (loadedCount === imageList.length) {
                    this.init();
                }
            };
            img.src = item.src;
        });
    }
    
    init() {
        // 敵の強さをランダムに設定
        const enemyTypes = [
            { name: '弱いゴライム', hp: 1000, attack: 20, defense: 20 },
            { name: 'ゴライム', hp: 2000, attack: 50, defense: 50 },
            { name: '強いゴライム', hp: 3000, attack: 100, defense: 100 }
        ];
        const randomEnemyType = enemyTypes[Math.floor(Math.random() * enemyTypes.length)];
        
        // 敵の強さに応じてプレイヤーのステータスを調整
        let heroStats;
        if (randomEnemyType.name === '弱いゴライム') {
            heroStats = {
                alice: { level: 25, hp: 450, mp: 250, attack: 80, defense: 80 },
                keimi: { level: 25, hp: 300, mp: 100, attack: 45, defense: 40 },
                soribel: { level: 25, hp: 140, mp: 400, attack: 30, defense: 40 }
            };
        } else if (randomEnemyType.name === 'ゴライム') {
            heroStats = {
                alice: { level: 50, hp: 600, mp: 400, attack: 100, defense: 80 },
                keimi: { level: 50, hp: 550, mp: 200, attack: 50, defense: 40 },
                soribel: { level: 50, hp: 380, mp: 450, attack: 40, defense: 35 }
            };
        } else { // 強いゴライム
            heroStats = {
                alice: { level: 99, hp: 900, mp: 600, attack: 350, defense: 220 },
                keimi: { level: 99, hp: 750, mp: 500, attack: 200, defense: 200 },
                soribel: { level: 99, hp: 500, mp: 680, attack: 150, defense: 180 }
            };
        }
        
        this.heroes = [
            new Character('アリス', heroStats.alice.level, heroStats.alice.hp, heroStats.alice.mp, heroStats.alice.attack, heroStats.alice.defense, 'images/player/hero.png', {
                equipment: this.weapons['オバカーノ剣'],
                weaponName: 'オバカーノ剣',
                spells: [{ name: 'バーカード', mp: 150 }],
                skills: [{ name: 'ひらめく', mp: 30 }]
            }),
            new Character('キーミー', heroStats.keimi.level, heroStats.keimi.hp, heroStats.keimi.mp, heroStats.keimi.attack, heroStats.keimi.defense, 'images/player/hero2.png', {
                equipment: this.weapons['手羽先'],
                weaponName: '手羽先',
                spells: [{ name: 'ライム斬り', mp: 100 }],
                skills: [{ name: 'ハレタ', mp: 50 }]
            }),
            new Character('ソリベル', heroStats.soribel.level, heroStats.soribel.hp, heroStats.soribel.mp, heroStats.soribel.attack, heroStats.soribel.defense, 'images/player/hero3.png', {
                equipment: this.weapons['マジックステッキ'],
                weaponName: 'マジックステッキ',
                spells: [{ name: 'ムテラル', mp: 200 }],
                skills: [{ name: 'マジックダンス', mp: 100 }]
            })
        ];
        
        this.enemies = [
            new Character(randomEnemyType.name, 50, randomEnemyType.hp, 0, randomEnemyType.attack, randomEnemyType.defense, 'images/monsters/ゴライム.png')
        ];
        
        this.turnOrder = [...this.heroes, ...this.enemies];
        this.shuffleArray(this.turnOrder);
        
        this.setupEventListeners();
        this.updateStatusDisplay();
        this.drawBattleField();
        
        this.showMessage(`${this.enemies[0].name}が あらわれた！`);
        
        // BGM を選択（強いゴライムのときは battle4.mp3 を確実に選択）
        let selectedBgm;
        if (randomEnemyType.name === '強いゴライム') {
            selectedBgm = 'battle4.mp3';
        } else {
            const bgmFiles = ['battle1.mp3', 'battle2.mp3', 'battle3.mp3'];
            selectedBgm = bgmFiles[Math.floor(Math.random() * bgmFiles.length)];
        }
        this.bgm.src = `bgm/${selectedBgm}`;
        
        // BGM 再生を試みる。自動再生がブロックされた場合は
        // ユーザーの最初の操作（クリックまたはキー押下）で再生を再試行する。
        if (this.bgm) {
            this.bgm.play().catch(e => {
                console.log('BGM自動再生エラー:', e);
                const tryPlayOnGesture = () => {
                    this.bgm.play().then(() => {
                        // 再生成功したら何もしない（イベントは once で自動解除）
                        console.log('BGM: ユーザー操作で再生開始');
                    }).catch(err => {
                        console.log('BGM: ユーザー操作でも再生できませんでした', err);
                    });
                };

                document.addEventListener('click', tryPlayOnGesture, { once: true });
                document.addEventListener('keydown', tryPlayOnGesture, { once: true });
            });
        }
        
        setTimeout(() => this.nextTurn(), 2000);
    }
    
    shuffleArray(array) {
        for (let i = array.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [array[i], array[j]] = [array[j], array[i]];
        }
    }
  setupEventListeners() {
        document.addEventListener('keydown', (e) => this.handleKeyInput(e));
        
        // コマンドアイテムのクリックイベント
        document.querySelectorAll('.command-item').forEach(item => {
            item.addEventListener('click', () => {
                if (this.gameState === GameState.COMMAND_SELECT) {
                    const index = parseInt(item.dataset.index);
                    this.selectedCommandIndex = index;
                    this.updateCommandCursor();
                    this.executeCommand();
                }
            });
        });
    }
    
    handleKeyInput(e) {
        if (this.gameState === GameState.COMMAND_SELECT) {
            this.handleCommandInput(e);
        } else if (this.gameState === GameState.SKILL_SELECT || 
                   this.gameState === GameState.SPELL_SELECT ||
                   this.gameState === GameState.ITEM_SELECT ||
                   this.gameState === GameState.EQUIP_SELECT) {
            this.handleSubmenuInput(e);
        } else if (this.gameState === GameState.TARGET_SELECT) {
            this.handleTargetInput(e);
        }
    }
    
    handleCommandInput(e) {
        const oldIndex = this.selectedCommandIndex;
        
        switch(e.key) {
            case 'ArrowUp':
                if (this.selectedCommandIndex >= 2) this.selectedCommandIndex -= 2;
                break;
            case 'ArrowDown':
                if (this.selectedCommandIndex < 4) this.selectedCommandIndex += 2;
                break;
            case 'ArrowLeft':
                if (this.selectedCommandIndex % 2 === 1) this.selectedCommandIndex -= 1;
                break;
            case 'ArrowRight':
                if (this.selectedCommandIndex % 2 === 0) this.selectedCommandIndex += 1;
                break;
            case 'Enter':
                this.executeCommand();
                return;
            case 'Escape':
                return;
        }
        
        if (oldIndex !== this.selectedCommandIndex) {
            this.updateCommandCursor();
            this.showCommandDescription();
        }
    }
    
    handleSubmenuInput(e) {
        const items = document.querySelectorAll('.submenu-item');
        const oldIndex = this.selectedSubmenuIndex;
        
        switch(e.key) {
            case 'ArrowUp':
                if (this.selectedSubmenuIndex > 0) this.selectedSubmenuIndex--;
                break;
            case 'ArrowDown':
                if (this.selectedSubmenuIndex < items.length - 1) this.selectedSubmenuIndex++;
                break;
            case 'Enter':
                this.executeSubmenuCommand();
                return;
            case 'Escape':
                this.showCommandWindow(this.currentAttacker);
                return;
        }
        
        if (oldIndex !== this.selectedSubmenuIndex) {
            this.updateSubmenuCursor();
            this.showSubmenuDescription();
        }
    }
    
    handleTargetInput(e) {
        switch(e.key) {
            case 'ArrowLeft':
                if (this.selectedTargetIndex > 0) this.selectedTargetIndex--;
                break;
            case 'ArrowRight':
                if (this.selectedTargetIndex < this.heroes.length - 1) this.selectedTargetIndex++;
                break;
            case 'Enter':
                this.executeTargetSelection();
                return;
            case 'Escape':
                this.hideTargetCursor();
                this.executeCommand(this.lastCommand);
                return;
        }
        
        this.updateTargetCursor();
    }
    
    drawBattleField() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        if (this.images.background) {
            this.ctx.drawImage(this.images.background, 0, 0, 800, 450);
        }
        
        if (this.enemies[0].isAlive()) {
            const enemyImg = this.images.enemy;
            if (enemyImg) {
                this.ctx.drawImage(enemyImg, 325, 210, 150, 150);
            }
            
            this.ctx.font = 'bold 20px "MS Gothic", monospace';
            this.ctx.fillStyle = '#fff';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(`${this.enemies[0].name} A`, 400, 380);
        }
    }
    
    updateStatusDisplay() {
        const container = document.getElementById('hero-status-container');
        container.innerHTML = '';
        
        this.heroes.forEach((hero, index) => {
            const statusDiv = document.createElement('div');
            statusDiv.className = 'hero-status';
            statusDiv.id = `hero-status-${index}`;
            if (!hero.isAlive()) statusDiv.classList.add('dead');
            
            const headerDiv = document.createElement('div');
            headerDiv.className = 'hero-status-header';
            headerDiv.textContent = hero.name;
            
            const bodyDiv = document.createElement('div');
            bodyDiv.className = 'hero-status-body';
            
            const imageKey = `hero${index + 1}`;
            if (this.images[imageKey]) {
                const img = document.createElement('img');
                img.src = this.images[imageKey].src;
                img.className = 'hero-image';
                img.alt = hero.name || 'hero';
                bodyDiv.appendChild(img);
            } else if (hero.name === this.originalGolimeName && this.images.lime) {
                const img = document.createElement('img');
                img.src = this.images.lime.src;
                img.className = 'hero-image';
                img.alt = this.originalGolimeName || 'lime';
                bodyDiv.appendChild(img);
            }
            
            const statsDiv = document.createElement('div');
            statsDiv.className = 'hero-stats';
            
            const hpRow = document.createElement('div');
            hpRow.className = 'stat-row';
            hpRow.innerHTML = `<span class="stat-label">ＨＰ</span><span class="stat-value">${hero.hp.toString().padStart(3, ' ')}</span>`;
            
            const mpRow = document.createElement('div');
            mpRow.className = 'stat-row';
            mpRow.innerHTML = `<span class="stat-label">ＭＰ</span><span class="stat-value">${hero.mp.toString().padStart(3, ' ')}</span>`;
            
            const levelDiv = document.createElement('div');
            levelDiv.className = 'hero-level';
            levelDiv.textContent = `Lv ${hero.level.toString().padStart(2, ' ')}`;
            
            statsDiv.appendChild(hpRow);
            statsDiv.appendChild(mpRow);
            statsDiv.appendChild(levelDiv);
            
            bodyDiv.appendChild(statsDiv);
            
            statusDiv.appendChild(headerDiv);
            statusDiv.appendChild(bodyDiv);
            
            container.appendChild(statusDiv);
        });
    }
    
    showMessage(message) {
        document.getElementById('message-text').textContent = message;
        this.gameState = GameState.MESSAGE;
    }
    
    showCommandWindow(hero) {
        this.currentAttacker = hero;
        document.getElementById('message-text').textContent = '';
        document.getElementById('submenu-window').style.display = 'none';
        document.getElementById('command-window').style.display = 'block';
        document.getElementById('command-char-name').textContent = hero.name;
        
        this.gameState = GameState.COMMAND_SELECT;
        this.selectedCommandIndex = 0;
        this.updateCommandCursor();
        this.showCommandDescription();
    }
    
    showCommandDescription() {
        const commands = ['こうげき', 'とくぎ', 'じゅもん', 'どうぐ', 'ぼうぎょ', 'そうび'];
        const command = commands[this.selectedCommandIndex];
        const description = this.commandDescriptions[command] || '';
        document.getElementById('message-text').textContent = description;
    }
    
    updateCommandCursor() {
        const items = document.querySelectorAll('.command-item');
        items.forEach((item, index) => {
            if (index === this.selectedCommandIndex) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        });
        
        const cursor = document.getElementById('command-cursor');
        const selectedItem = items[this.selectedCommandIndex];
        const rect = selectedItem.getBoundingClientRect();
        const gridRect = document.getElementById('command-grid').getBoundingClientRect();
        
        cursor.style.left = (rect.left - gridRect.left) + 'px';
        cursor.style.top = (rect.top - gridRect.top) + 'px';
    }
    
    showSubmenu(title, items, state, initialMessage = null) {
        const submenuWindow = document.getElementById('submenu-window');
        const submenuTitle = document.getElementById('submenu-title');
        const submenuItems = document.getElementById('submenu-items');
        
        submenuTitle.textContent = title;
        submenuItems.innerHTML = '';
        
        items.forEach((item, index) => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'submenu-item';
            itemDiv.textContent = item;
            itemDiv.dataset.index = index;
            itemDiv.addEventListener('click', () => {
                this.selectedSubmenuIndex = index;
                this.updateSubmenuCursor();
                this.executeSubmenuCommand();
            });
            submenuItems.appendChild(itemDiv);
        });
        
        document.getElementById('command-window').style.display = 'none';
        submenuWindow.style.display = 'block';
        
        this.gameState = state;
        this.selectedSubmenuIndex = 0;
        this.updateSubmenuCursor();
        
        if (initialMessage !== null) {
            document.getElementById('message-text').textContent = initialMessage;
        } else {
            this.showSubmenuDescription();
        }
    }
    
    showSubmenuDescription() {
        const items = document.querySelectorAll('.submenu-item');
        if (items.length === 0) return;
        
        const selectedText = items[this.selectedSubmenuIndex].textContent;
        let description = '';
        
        if (selectedText === 'もどる') {
            description = 'ひとつまえの コマンドに もどります。';
        } else if (this.gameState === GameState.SKILL_SELECT) {
            const abilityName = this.currentAttacker.skills[this.selectedSubmenuIndex].name;
            description = this.abilityDescriptions[abilityName] || '';
        } else if (this.gameState === GameState.SPELL_SELECT) {
            const abilityName = this.currentAttacker.spells[this.selectedSubmenuIndex].name;
            description = this.abilityDescriptions[abilityName] || '';
        } else if (this.gameState === GameState.ITEM_SELECT) {
            const itemName = Object.keys(this.inventory)[this.selectedSubmenuIndex];
            description = this.abilityDescriptions[itemName] || '';
        } else if (this.gameState === GameState.EQUIP_SELECT) {
            if (selectedText === 'はずす') {
                description = 'そうびを はずして すでの じょうたいに なる。';
            } else if (selectedText !== 'もどる') {
                description = `${selectedText}を そうびする。`;
            }
        }
        
        document.getElementById('message-text').textContent = description;
    }
    
    updateSubmenuCursor() {
        const items = document.querySelectorAll('.submenu-item');
        items.forEach((item, index) => {
            if (index === this.selectedSubmenuIndex) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        });
        
        const cursor = document.getElementById('submenu-cursor');
        const selectedItem = items[this.selectedSubmenuIndex];
        if (selectedItem) {
            cursor.style.top = selectedItem.offsetTop + 'px';
        }
    }
   updateTargetCursor() {
        const cursor = document.getElementById('target-cursor');
        const statusDivs = document.querySelectorAll('.hero-status');
        
        statusDivs.forEach((div, index) => {
            if (index === this.selectedTargetIndex) {
                div.style.backgroundColor = '#333';
                const rect = div.getBoundingClientRect();
                const containerRect = document.getElementById('status-window').getBoundingClientRect();
                cursor.style.left = (rect.left - containerRect.left - 12) + 'px';
                cursor.style.top = (rect.top - containerRect.top + 30) + 'px';
                cursor.style.display = 'block';
            } else {
                div.style.backgroundColor = '#000';
            }
        });
    }
    
    hideTargetCursor() {
        document.getElementById('target-cursor').style.display = 'none';
        document.querySelectorAll('.hero-status').forEach(div => {
            div.style.backgroundColor = '#000';
        });
    }
    
    executeCommand(commandText = null) {
        const commands = ['こうげき', 'とくぎ', 'じゅもん', 'どうぐ', 'ぼうぎょ', 'そうび'];
        const command = commandText || commands[this.selectedCommandIndex];
        this.lastCommand = command;
        
        const attacker = this.currentAttacker;
        
        if (command === 'こうげき') {
            this.playerAttack();
        } else if (command === 'どうぐ') {
            if (Object.keys(this.inventory).length === 0) {
                this.showMessage('どうぐを もっていない！');
                setTimeout(() => this.showCommandWindow(attacker), 1500);
            } else {
                const items = Object.entries(this.inventory).map(([name, num]) => `${name} (${num})`);
                items.push('もどる');
                this.showSubmenu('どのどうぐを つかう？', items, GameState.ITEM_SELECT);
            }
        } else if (command === 'とくぎ') {
            if (attacker.skills.length === 0) {
                this.showMessage('とくぎを おぼえていない！');
                setTimeout(() => this.showCommandWindow(attacker), 1500);
            } else {
                const skills = attacker.skills.map(s => `${s.name} (MP:${s.mp})`);
                skills.push('もどる');
                this.showSubmenu(`${attacker.name}の とくぎ`, skills, GameState.SKILL_SELECT);
            }
        } else if (command === 'じゅもん') {
            if (attacker.spells.length === 0) {
                this.showMessage('じゅもんを おぼえていない！');
                setTimeout(() => this.showCommandWindow(attacker), 1500);
            } else {
                const spells = attacker.spells.map(s => `${s.name} (MP:${s.mp})`);
                spells.push('もどる');
                this.showSubmenu(`${attacker.name}の じゅもん`, spells, GameState.SPELL_SELECT);
            }
        } else if (command === 'そうび') {
            const weaponName = this.characterWeapons[attacker.name];
            if (!weaponName) {
                this.showMessage(`${attacker.name}は そうびできる ぶきがない！`);
                setTimeout(() => this.showCommandWindow(attacker), 1500);
                return;
            }
            
            const message = attacker.weaponName 
                ? `現在のそうび： ${attacker.weaponName}`
                : 'なにもそうびしていません。';
            
            const equipOptions = [weaponName, 'はずす', 'もどる'];
            this.showSubmenu('どうしますか？', equipOptions, GameState.EQUIP_SELECT, message);
        } else if (command === 'ぼうぎょ') {
            this.playerDefend();
        }
    }
    
    executeSubmenuCommand() {
        const items = document.querySelectorAll('.submenu-item');
        const selectedText = items[this.selectedSubmenuIndex].textContent;
        
        if (selectedText === 'もどる') {
            this.showCommandWindow(this.currentAttacker);
            return;
        }
        
        const state = this.gameState;
        const attacker = this.currentAttacker;
        
        if (state === GameState.ITEM_SELECT) {
            const itemName = Object.keys(this.inventory)[this.selectedSubmenuIndex];
            this.activeItem = itemName;
            this.showMessage(`${itemName}を だれに つかいますか？`);
            this.gameState = GameState.TARGET_SELECT;
            this.selectedTargetIndex = 0;
            this.updateTargetCursor();
        } else if (state === GameState.SKILL_SELECT || state === GameState.SPELL_SELECT) {
            const abilityList = state === GameState.SKILL_SELECT ? attacker.skills : attacker.spells;
            const ability = abilityList[this.selectedSubmenuIndex];
            
            if (attacker.mp < ability.mp) {
                this.showMessage('ＭＰが たりない！');
                setTimeout(() => this.showCommandWindow(attacker), 1500);
                return;
            }
            
            attacker.mp -= ability.mp;
            this.updateStatusDisplay();
            
            this.executeAbility(ability);
        } else if (state === GameState.EQUIP_SELECT) {
            if (selectedText === 'はずす') {
                attacker.unequip();
                this.showMessage(`${attacker.name}は ぶきを はずした！`);
            } else {
                const weaponData = this.weapons[selectedText];
                attacker.equip(weaponData, selectedText);
                this.showMessage(`${attacker.name}は ${selectedText}を そうびした！`);
            }
            setTimeout(() => this.showCommandWindow(attacker), 1500);
        }
    }
    
    executeAbility(ability) {
        const attacker = this.currentAttacker;
        const enemy = this.enemies[0];
        
        if (ability.name === 'ひらめく') {
            this.showMessage(`${attacker.name}は なにか ひらめいた！`);
            setTimeout(() => {
                this.showMessage('「いいこと思いついた！」');
                setTimeout(() => {
                    const messages = [
                        'たたかいの おわりに チキンを たべれば へいわになる！',
                        'このつるぎを じめんにさせば きっと おんせんが わきでるぞ！',
                        'ぼうしを さかさまに かぶると こうげきりょくが あがる……きがする！',
                        'ゴライムの なみだは きっと しょっぱい！ なぜなら うみと おなじ いろだから！',
                        'あしたに なれば、きっと このたたかいは ゆめだったことに なるはずだ！'
                    ];
                    const message = messages[Math.floor(Math.random() * messages.length)];
                    this.showMessage(`「${message}」`);
                    setTimeout(() => {
                        enemy.laughingTurns = 2;
                        this.showMessage(`${enemy.name}は おもわず わらってしまった！`);
                        setTimeout(() => this.nextTurn(), 2000);
                    }, 2500);
                }, 1500);
            }, 1500);
        } else if (ability.name === 'ハレタ') {
            enemy.dazzleTurns = Math.floor(Math.random() * 3) + 3;
            this.showMessage(`${attacker.name}は ハレタを となえた！\nまばゆい光が ${enemy.name}の目をくらませる！`);
            setTimeout(() => this.nextTurn(), 2000);
        } else if (ability.name === 'マジックダンス') {
            this.showMessage(`${attacker.name}は マジックダンスを おどった！`);
            setTimeout(() => {
                this.heroes.forEach(hero => {
                    if (hero.isAlive()) hero.mp = hero.maxMp;
                });
                this.updateStatusDisplay();
                this.showMessage('みかたぜんいんの ＭＰが かいふくした！');
                setTimeout(() => this.nextTurn(), 2000);
            }, 1500);
        } else if (ability.name === 'バーカード') {
            attacker.isNioDachi = true;
            this.nioDachiCharacter = attacker;
            this.showMessage(`${attacker.name}は バーカードを となえた！\nすべてのこうげきを うけとめる かまえだ！`);
            setTimeout(() => this.nextTurn(), 2000);
        } else if (ability.name === 'ムテラル') {
            this.showMessage(`${attacker.name}は ムテラルを となえた！`);
            setTimeout(() => {
                this.heroes.forEach(hero => {
                    if (hero.isAlive()) {
                        hero.hp = hero.maxHp;
                        hero.mp = hero.maxMp;
                    }
                });
                this.updateStatusDisplay();
                this.showMessage('なかまぜんいんの ＨＰとＭＰが かんぜんに かいふくした！');
                setTimeout(() => this.nextTurn(), 2000);
            }, 1500);
        } else if (ability.name === 'ライム斬り') {
            const target = enemy;
            const baseDamage = Math.max(1, attacker.attack - Math.floor(target.defense / 2) + Math.floor(Math.random() * 7) - 3);
            const damage = baseDamage * 2;
            target.hp = Math.max(0, target.hp - damage);
            this.updateStatusDisplay();
            this.showMessage(`${attacker.name}は ライム斬りを はなった！\n${target.name}に ${damage}のダメージ！`);
            setTimeout(() => this.nextTurn(), 2000);
        }
    }
    
    executeTargetSelection() {
        const target = this.heroes[this.selectedTargetIndex];
        this.hideTargetCursor();
        
        if (this.activeItem === 'アホ草') {
            this.inventory['アホ草']--;
            if (this.inventory['アホ草'] === 0) delete this.inventory['アホ草'];
            
            const hpHeal = Math.min(10, target.maxHp - target.hp);
            const mpHeal = Math.min(10, target.maxMp - target.mp);
            target.hp += hpHeal;
            target.mp += mpHeal;
            this.updateStatusDisplay();
            this.showMessage(`${this.currentAttacker.name}は ${target.name}に アホ草をつかった！\n${target.name}のＨＰが ${hpHeal}、ＭＰが ${mpHeal}かいふくした！`);
            setTimeout(() => this.nextTurn(), 2500);
        }
    }
    
    playerDefend() {
        const attacker = this.currentAttacker;
        attacker.isDefending = true;
        this.showMessage(`${attacker.name}は みをまもっている！`);
        setTimeout(() => this.nextTurn(), 1500);
    }
    
    playerAttack() {
        const attacker = this.currentAttacker;
        const target = this.enemies[0];
        const damage = Math.max(1, attacker.attack - Math.floor(target.defense / 2) + Math.floor(Math.random() * 7) - 3);
        target.hp = Math.max(0, target.hp - damage);
        this.updateStatusDisplay();
        this.showMessage(`${attacker.name}の こうげき！\n${target.name}に ${damage}のダメージ！`);
        setTimeout(() => this.nextTurn(), 2000);
    }
    
    nextTurn() {
        if (this.currentAttacker) {
            this.currentAttacker.isDefending = false;
            if (this.currentAttacker.isNioDachi) {
                this.currentAttacker.isNioDachi = false;
                this.nioDachiCharacter = null;
            }
        }
        
        if (this.enemies[0].dazzleTurns > 0) {
            this.enemies[0].dazzleTurns--;
        }
        
        if (!this.heroes.some(h => h.isAlive())) {
            this.showMessage('アリスたちは ぜんめつした…');
            setTimeout(() => {
                this.bgm.pause();
                alert('GAME OVER');
            }, 3000);
            return;
        }
        
        if (!this.enemies.some(e => e.isAlive())) {
            this.handleVictory();
            return;
        }
        
        let char = this.turnOrder[this.currentTurnIndex];
        while (!char.isAlive()) {
            this.currentTurnIndex = (this.currentTurnIndex + 1) % this.turnOrder.length;
            char = this.turnOrder[this.currentTurnIndex];
        }
        
        this.currentTurnIndex = (this.currentTurnIndex + 1) % this.turnOrder.length;
        
        if (this.heroes.includes(char)) {
            this.playerTurn(char);
        } else {
            this.enemyTurn(char);
        }
    }
    
    playerTurn(hero) {
        this.showCommandWindow(hero);
    }
    
    enemyTurn(enemy) {
        this.currentAttacker = enemy;
        
        if (enemy.laughingTurns > 0) {
            enemy.laughingTurns--;
            if (enemy.laughingTurns > 0) {
                this.showMessage(`${enemy.name}は わらっていて うごけない！`);
                setTimeout(() => this.nextTurn(), 2000);
                return;
            }
        }
        
        this.showMessage(`${enemy.name}の こうげき！`);
        setTimeout(() => this.enemyAttackAction(enemy), 1500);
    }
    
    enemyAttackAction(enemy) {
        if (enemy.dazzleTurns > 0 && Math.random() < 0.5) {
            this.showMessage(`しかし ${enemy.name}のこうげきは はずれた！`);
            setTimeout(() => this.nextTurn(), 1500);
            return;
        }
        
        const aliveHeroes = this.heroes.filter(h => h.isAlive());
        if (aliveHeroes.length === 0) return;
        
        const target = this.nioDachiCharacter && this.nioDachiCharacter.isAlive()
            ? this.nioDachiCharacter
            : aliveHeroes[Math.floor(Math.random() * aliveHeroes.length)];
        
        let damage = Math.max(1, enemy.attack - Math.floor(target.defense / 2) + Math.floor(Math.random() * 11) - 5);
        if (target.isDefending) damage = Math.floor(damage / 2);
        
        target.hp = Math.max(0, target.hp - damage);
        this.updateStatusDisplay();
        this.showMessage(`${target.name}は ${damage}のダメージを うけた！`);
        setTimeout(() => this.nextTurn(), 2000);
    }
    
    handleVictory() {
        this.gameState = GameState.EVENT;
        this.drawBattleField();
        this.showMessage(`${this.enemies[0].name}を やっつけた！`);
        setTimeout(() => this.eventStep1(), 2000);
    }
    
    eventStep1() {
        this.showMessage(`${this.enemies[0].name}が まばゆい光に つつまれた！`);
        setTimeout(() => this.eventStep2(), 2500);
    }
    
    eventStep2() {
        this.showMessage('ゴライムは 本来のすがたに もどった！');
        
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        if (this.images.background) {
            this.ctx.drawImage(this.images.background, 0, 0, 800, 450);
        }
        if (this.images.lime) {
            this.ctx.drawImage(this.images.lime, 325, 210, 150, 150);
        }
        
        setTimeout(() => this.eventStep3(), 2500);
    }
    
    eventStep3() {
        this.showMessage(`「ぼくは ${this.originalGolimeName}！\n  いっしょに つれていってよ！」`);
        setTimeout(() => this.eventStep4(), 3000);
    }
    
    eventStep4() {
        this.showMessage(`${this.originalGolimeName}が 仲間に くわわった！`);
        
        setTimeout(() => {
            const lime = new Character(
                this.originalGolimeName,
                99, 1, 1, 1, 1,
                this.originalGolimeImagePath
            );
            
            this.heroes.push(lime);
            this.updateStatusDisplay();
            
            setTimeout(() => {
                this.bgm.pause();
                alert('ゲームクリア！ おめでとう！');
                // 5秒後に結果ページへ遷移（index3.html）
                // alert の後に遷移するため、setTimeout を使って遅延移動
                setTimeout(() => {
                    window.location.href = 'index3.html';
                }, 5000);
            }, 5000);
        }, 2000);
    }
}

// ゲーム開始
window.addEventListener('load', () => {
    new Game();
});