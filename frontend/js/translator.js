const Translator = {
    history: [],
    targetLang: CONFIG.DEFAULT_TARGET_LANG,
    _currentTranslation: '',
    _channel: null,
    _socket: null,

    onOriginalText: null,
    onTranslatedToken: null,
    onTranslatedDone: null,
    onHistoryUpdate: null,
    onEngineReady: null,

    async init() {
        try {
            const result = await API.healthCheck();
            let engineName = '未配置';
            if (result.services.deepseek) engineName = 'DeepSeek';
            else if (result.services.openai) engineName = 'OpenAI';
            if (this.onEngineReady) this.onEngineReady(engineName);
            
            this._initSocket();
            return true;
        } catch (error) {
            if (this.onEngineReady) this.onEngineReady('连接失败');
            return false;
        }
    },

    _initSocket() {
        try {
            this._socket = io('http://localhost:5000');
            this._socket.on('connect', () => {
                console.log('[Translator] Socket.IO 已连接');
            });
            this._socket.on('disconnect', () => {
                console.log('[Translator] Socket.IO 已断开');
            });
            this._socket.on('connect_error', (error) => {
                console.error('[Translator] Socket.IO 连接失败:', error);
            });
        } catch (e) {
            console.error('[Translator] Socket.IO 初始化失败:', e);
        }
    },

    initChannel() {
        try {
            this._channel = new BroadcastChannel('translator-captions');
            console.log('[Translator] BroadcastChannel 已初始化');
        } catch (e) {
            console.error('[Translator] BroadcastChannel 初始化失败:', e);
        }
    },

    _broadcast(type, data = {}) {
        if (this._channel) {
            console.log('[Translator] 发送消息 (BroadcastChannel):', { type, ...data });
            this._channel.postMessage({ type, ...data });
        }
        // 通过 Socket.IO 发送给后端，后端再转发给悬浮窗
        // 转发所有类型的消息（original, translation, translation-done）
        if (this._socket && (type === 'original' || type === 'translation' || type === 'translation-done')) {
            console.log('[Translator] 发送消息 (Socket.IO):', { type, ...data });
            this._socket.emit('captions', { type, ...data });
        }
    },

    setTargetLang(langCode) {
        this.targetLang = langCode;
        const langNames = { 
            zh: '🇨🇳 中文', 
            en: '🇺🇸 English', 
            ja: '🇯🇵 日本語' 
        };
        const langLabels = {
            zh: 'ZH',
            en: 'EN', 
            ja: 'JA'
        };
        this._broadcast('lang', { 
            text: langNames[langCode] || langCode,
            code: langLabels[langCode] || langCode
        });
        console.log('[Translator] 目标语言已切换为:', langCode);
    },

    async processAudio(audioBlob) {
        try {
            const originalText = await this._recognizeWithBackend(audioBlob);
            if (!originalText || !originalText.trim()) return;

            console.log('[Translator] 语音识别结果:', originalText);
            
            if (this.onOriginalText) this.onOriginalText(originalText);
            this._broadcast('original', { text: originalText });
            
            // 调用翻译API进行翻译
            this._currentTranslation = '';
            
            await API.translateStream(
                originalText,
                this.targetLang,
                // onToken - 流式翻译token
                (token) => {
                    this._currentTranslation += token;
                    if (this.onTranslatedToken) this.onTranslatedToken(this._currentTranslation);
                    this._broadcast('translation', { text: this._currentTranslation });
                },
                // onDone - 翻译完成
                () => {
                    console.log('[Translator] 翻译完成:', this._currentTranslation);
                    this.addHistory(originalText, this._currentTranslation);
                    if (this.onTranslatedDone) this.onTranslatedDone(this._currentTranslation);
                    this._broadcast('translation-done', {});
                },
                // onError - 翻译错误
                (error) => {
                    console.error('[Translator] 翻译失败:', error);
                    // 翻译失败时，使用原文
                    this._currentTranslation = originalText;
                    if (this.onTranslatedToken) this.onTranslatedToken(this._currentTranslation);
                    this._broadcast('translation', { text: this._currentTranslation });
                    this.addHistory(originalText, this._currentTranslation);
                    if (this.onTranslatedDone) this.onTranslatedDone(this._currentTranslation);
                    this._broadcast('translation-done', {});
                }
            );
            
            return { original: originalText, translated: this._currentTranslation };
        } catch (error) {
            console.error('[Translator] 处理音频出错:', error);
        }
    },

    async _recognizeWithBackend(audioBlob) {
        try {
            const result = await API.transcribe(audioBlob);
            if (result.success && result.data.text) return result.data.text;
        } catch (error) {}
        return '';
    },

    addHistory(original, translated) {
        const record = {
            id: Date.now(),
            time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            original, translated,
        };
        this.history.unshift(record);
        if (this.history.length > CONFIG.MAX_HISTORY) this.history.pop();
        if (this.onHistoryUpdate) this.onHistoryUpdate([...this.history]);
    },

    async loadHistory() {
        try {
            const result = await API.getHistory();
            if (result.success && result.data.length > 0) {
                this.history = result.data;
                if (this.onHistoryUpdate) this.onHistoryUpdate([...this.history]);
            }
        } catch (error) {}
    },

    async clearHistory() {
        try { await API.clearHistory(); this.history = []; if (this.onHistoryUpdate) this.onHistoryUpdate([]); } catch (error) {}
    },

    speak(text) {
        if (!('speechSynthesis' in window)) return;
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        const langMap = { 'zh': 'zh-CN', 'en': 'en-US', 'ja': 'ja-JP' };
        utterance.lang = langMap[this.targetLang] || 'zh-CN';
        utterance.rate = 1.1; utterance.volume = 0.9;
        const voices = window.speechSynthesis.getVoices();
        const targetVoice = voices.find(v => v.lang.startsWith(utterance.lang));
        if (targetVoice) utterance.voice = targetVoice;
        window.speechSynthesis.speak(utterance);
    },
};