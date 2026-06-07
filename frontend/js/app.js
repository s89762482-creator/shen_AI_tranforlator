const App = {
    isRunning: false,
    outputMode: 'subtitle',  // 输出模式: subtitle(字幕), voice(语音), both(混合)
    sourceLang: CONFIG.DEFAULT_SOURCE_LANG,  // 当前源语言
    targetLang: CONFIG.DEFAULT_TARGET_LANG,  // 当前目标语言
    elements: {},
    overlayWindow: null,

    async init() {
        this._cacheElements();
        this._renderLanguageSelectors();
        this._bindEvents();
        this._registerCallbacks();
        Translator.initChannel();
        await Translator.init();
    },

    _cacheElements() {
        this.elements = {
            startBtn: document.getElementById('startBtn'),
            btnIcon: document.getElementById('btnIcon'),
            btnText: document.getElementById('btnText'),
            statusDot: document.getElementById('statusDot'),
            statusText: document.getElementById('statusText'),
            originalText: document.getElementById('originalText'),
            translatedText: document.getElementById('translatedText'),
            historyList: document.getElementById('historyList'),
            videoHint: document.getElementById('videoHint'),
            clearHistoryBtn: document.getElementById('clearHistoryBtn'),
            engineName: document.getElementById('engineName'),
            outputModeBtns: document.querySelectorAll('.output-mode-btn'),
            sourceLangSelect: document.getElementById('sourceLangSelect'),
            targetLangSelect: document.getElementById('targetLangSelect'),
        };
    },

    _renderLanguageSelectors() {
        // 渲染源语言选择器
        if (this.elements.sourceLangSelect) {
            this.elements.sourceLangSelect.innerHTML = CONFIG.SUPPORTED_SOURCE_LANGUAGES.map(lang => `
                <option value="${lang.code}" ${lang.code === this.sourceLang ? 'selected' : ''}>
                    ${lang.flag} ${lang.name}
                </option>
            `).join('');
        }
        
        // 渲染目标语言选择器（根据源语言动态更新）
        this._updateTargetLanguages();
    },

    _updateTargetLanguages() {
        if (this.elements.targetLangSelect) {
            const targetLanguages = CONFIG.SUPPORTED_TARGET_LANGUAGES[this.sourceLang] || [];
            
            // 检查当前目标语言是否在可用列表中，如果不在，自动选择第一个
            const isCurrentLangAvailable = targetLanguages.some(lang => lang.code === this.targetLang);
            if (!isCurrentLangAvailable && targetLanguages.length > 0) {
                this.targetLang = targetLanguages[0].code;
                Translator.setTargetLang(this.targetLang);
                console.log('[App] 目标语言自动切换为:', this.targetLang);
            }
            
            this.elements.targetLangSelect.innerHTML = targetLanguages.map(lang => `
                <option value="${lang.code}" ${lang.code === this.targetLang ? 'selected' : ''}>
                    ${lang.flag} ${lang.name}
                </option>
            `).join('');
        }
    },

    _bindEvents() {
        this.elements.startBtn.addEventListener('click', () => this._toggleTranslation());
        this.elements.outputModeBtns.forEach(btn => btn.addEventListener('click', () => this._switchMode(btn.dataset.mode)));
        
        // 源语言选择事件
        if (this.elements.sourceLangSelect) {
            this.elements.sourceLangSelect.addEventListener('change', (e) => {
                this.sourceLang = e.target.value;
                this._updateTargetLanguages();
                Translator.setSourceLang(this.sourceLang);
                console.log('[App] 源语言切换为:', this.sourceLang);
            });
        }
        
        // 目标语言选择事件
        if (this.elements.targetLangSelect) {
            this.elements.targetLangSelect.addEventListener('change', (e) => {
                this.targetLang = e.target.value;
                Translator.setTargetLang(this.targetLang);
                console.log('[App] 目标语言切换为:', this.targetLang);
            });
        }
        
        if (this.elements.clearHistoryBtn) this.elements.clearHistoryBtn.addEventListener('click', () => Translator.clearHistory());
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && e.target === document.body) { e.preventDefault(); this._toggleTranslation(); }
        });
    },

    _registerCallbacks() {
        AudioCapture.onAudioChunk = async (audioBlob) => {
            const result = await Translator.processAudio(audioBlob, this.sourceLang);
            // 根据输出模式决定是否语音播报
            if (result && (this.outputMode === 'voice' || this.outputMode === 'both')) {
                Translator.speak(result.translated);
            }
        };
        AudioCapture.onStatusChange = (running) => {
            this.isRunning = running;
            this._updateUIState();
            Translator._broadcast('status', { running });
        };
        Translator.onOriginalText = (text) => { this.elements.originalText.textContent = text; };
        Translator.onTranslatedToken = (t) => { this.elements.translatedText.textContent = t; };
        Translator.onTranslatedDone = () => {};
        Translator.onHistoryUpdate = (h) => { this._renderHistory(h); };
        Translator.onEngineReady = (e) => { this.elements.engineName.textContent = e; };
    },

    async _toggleTranslation() {
        if (this.isRunning) { 
            AudioCapture.stop(); 
            // 停止监听时关闭悬浮窗
            try {
                const result = await API.stopOverlay();
                console.log('[App] 悬浮窗关闭结果:', result);
            } catch (e) {
                console.error('[App] 关闭悬浮窗失败:', e);
            }
            return; 
        }
        try { 
            await AudioCapture.start('system');
            // 启动系统音频监听
            try {
                const result = await API.startOverlay();
                console.log('[App] 悬浮窗启动结果:', result);
            } catch (e) {
                console.error('[App] 启动悬浮窗失败:', e);
            }
        }
        catch (error) { alert('启动失败，请检查权限设置。'); }
    },

    _switchMode(mode) {
        this.outputMode = mode;
        this.elements.outputModeBtns.forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
        console.log('[App] 输出模式切换为:', mode);
    },

    _updateUIState() {
        if (this.isRunning) {
            this.elements.startBtn.classList.add('running');
            this.elements.btnIcon.textContent = '⏸️';
            this.elements.btnText.textContent = '停止监听';
            this.elements.statusDot.classList.add('active');
            this.elements.statusText.textContent = '监听系统音频中...';
            this.elements.originalText.textContent = '正在监听语音...';
            this.elements.translatedText.textContent = '';
        } else {
            this.elements.startBtn.classList.remove('running');
            this.elements.btnIcon.textContent = '▶️';
            this.elements.btnText.textContent = '开始监听';
            this.elements.statusDot.classList.remove('active');
            this.elements.statusText.textContent = '待机中';
            this.elements.originalText.textContent = '等待语音输入...';
            this.elements.translatedText.textContent = '';
        }
    },

    _renderHistory(h) {
        if (!h || !h.length) {
            this.elements.historyList.innerHTML = '<div class="history-empty">开始翻译后，历史记录将在此显示</div>';
            return;
        }
        this.elements.historyList.innerHTML = h.map(i => `
            <div class="history-item"><div class="time">${i.time}</div><div class="content">
            <div class="original">${this._e(i.original)}</div><div class="translated">${this._e(i.translated)}</div>
            </div></div>
        `).join('');
    },

    _e(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; },

    _openOverlay() {
        if (this.overlayWindow && !this.overlayWindow.closed) { this.overlayWindow.focus(); return; }
        const w = 650, h = 160;
        this.overlayWindow = window.open('/caption-overlay.html', '_blank',
            `width=${w},height=${h},left=${(screen.width-w)/2},top=${screen.height-h-80},` +
            'toolbar=0,location=0,menubar=0,status=0,scrollbars=0,resizable=0');
        const t = setInterval(() => { if (this.overlayWindow?.closed) { clearInterval(t); this.overlayWindow = null; } }, 500);
    },

    _closeOverlay() {
        if (this.overlayWindow && !this.overlayWindow.closed) this.overlayWindow.close();
        this.overlayWindow = null;
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());