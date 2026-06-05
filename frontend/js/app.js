const App = {
    isRunning: false,
    outputMode: 'subtitle',
    elements: {},
    overlayWindow: null,

    async init() {
        this._cacheElements();
        this._renderLanguageSelector();
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
            sourceBtns: document.querySelectorAll('.source-btn'),
            modeBtns: document.querySelectorAll('.mode-btn'),
        };
    },

    _renderLanguageSelector() {
        const container = document.getElementById('languageSelector');
        if (!container) return;
        container.innerHTML = CONFIG.SUPPORTED_LANGUAGES.map(lang => `
            <button class="lang-btn ${lang.code === CONFIG.DEFAULT_TARGET_LANG ? 'active' : ''}"
                    data-lang="${lang.code}">${lang.flag} ${lang.name}</button>
        `).join('');
    },

    _bindEvents() {
        this.elements.startBtn.addEventListener('click', () => this._toggleTranslation());
        this.elements.sourceBtns.forEach(btn => btn.addEventListener('click', () => this._switchSource(btn.dataset.source)));
        this.elements.modeBtns.forEach(btn => btn.addEventListener('click', () => this._switchMode(btn.dataset.mode)));
        const langContainer = document.getElementById('languageSelector');
        if (langContainer) langContainer.addEventListener('click', (e) => {
            const btn = e.target.closest('.lang-btn');
            if (btn) this._switchLanguage(btn.dataset.lang);
        });
        if (this.elements.clearHistoryBtn) this.elements.clearHistoryBtn.addEventListener('click', () => Translator.clearHistory());
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && e.target === document.body) { e.preventDefault(); this._toggleTranslation(); }
        });
    },

    _registerCallbacks() {
        AudioCapture.onAudioChunk = async (audioBlob) => {
            const result = await Translator.processAudio(audioBlob);
            if (result && (this.outputMode === 'voice' || this.outputMode === 'both')) Translator.speak(result.translated);
        };
        AudioCapture.onStatusChange = (running) => {
            this.isRunning = running;
            this._updateUIState();
            Translator._broadcast('status', { running });
            if (running && AudioCapture.audioSource === 'system') this._openOverlay();
            else if (!running) this._closeOverlay();
        };
        Translator.onOriginalText = (text) => { this.elements.originalText.textContent = text; };
        Translator.onTranslatedToken = (t) => { this.elements.translatedText.textContent = t; };
        Translator.onTranslatedDone = () => {};
        Translator.onHistoryUpdate = (h) => { this._renderHistory(h); };
        Translator.onEngineReady = (e) => { this.elements.engineName.textContent = e; };
    },

    async _toggleTranslation() {
        if (this.isRunning) { AudioCapture.stop(); return; }
        const source = (document.querySelector('.source-btn.active') || {}).dataset?.source || 'mic';
        try { await AudioCapture.start(source); }
        catch (error) { alert('启动失败，请检查权限设置。'); }
    },

    _switchSource(source) {
        if (this.isRunning) { alert('请先停止当前监听。'); return; }
        this.elements.sourceBtns.forEach(b => b.classList.toggle('active', b.dataset.source === source));
        this.elements.videoHint.classList.toggle('visible', source === 'system');
    },

    _switchMode(mode) {
        this.outputMode = mode;
        this.elements.modeBtns.forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    },

    _switchLanguage(code) {
        document.querySelectorAll('.lang-btn').forEach(b => b.classList.toggle('active', b.dataset.lang === code));
        Translator.setTargetLang(code);
    },

    _updateUIState() {
        if (this.isRunning) {
            this.elements.startBtn.classList.add('running');
            this.elements.btnIcon.textContent = '⏸️';
            this.elements.btnText.textContent = '停止监听';
            this.elements.statusDot.classList.add('active');
            const src = document.querySelector('.source-btn.active');
            this.elements.statusText.textContent = src && src.dataset.source === 'system' ? '监听系统音频中...' : '监听麦克风中...';
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
        const w = 600, h = 280;
        this.overlayWindow = window.open('/caption-overlay.html', 'TranslatorCaptions',
            `width=${w},height=${h},left=${(screen.width-w)/2},top=${screen.height-h-80},` +
            'frame=false,titlebar=false,menubar=false,toolbar=false,location=false,status=false,resizable=false,alwaysOnTop=true');
        const t = setInterval(() => { if (this.overlayWindow?.closed) { clearInterval(t); this.overlayWindow = null; } }, 500);
    },

    _closeOverlay() {
        if (this.overlayWindow && !this.overlayWindow.closed) this.overlayWindow.close();
        this.overlayWindow = null;
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());