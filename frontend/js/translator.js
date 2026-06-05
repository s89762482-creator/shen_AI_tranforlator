const Translator = {
    history: [],
    targetLang: CONFIG.DEFAULT_TARGET_LANG,
    _currentTranslation: '',
    _channel: null,

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
            return true;
        } catch (error) {
            if (this.onEngineReady) this.onEngineReady('连接失败');
            return false;
        }
    },

    initChannel() {
        try {
            this._channel = new BroadcastChannel('translator-captions');
        } catch (e) {}
    },

    _broadcast(type, data = {}) {
        if (this._channel) this._channel.postMessage({ type, ...data });
    },

    setTargetLang(langCode) {
        this.targetLang = langCode;
        const langNames = { zh: '🇨🇳 中文', en: '🇺🇸 English', ja: '🇯🇵 日本語' };
        this._broadcast('lang', { text: langNames[langCode] || langCode });
    },

    async processAudio(audioBlob) {
        try {
            const originalText = await this._recognizeWithBackend(audioBlob);
            if (!originalText || !originalText.trim()) return;

            if (this.onOriginalText) this.onOriginalText(originalText);
            this._broadcast('original', { text: originalText });
            this._currentTranslation = '';

            await API.translateStream(
                originalText, this.targetLang,
                (token) => {
                    this._currentTranslation += token;
                    if (this.onTranslatedToken) this.onTranslatedToken(this._currentTranslation);
                    this._broadcast('translation', { text: this._currentTranslation });
                },
                () => {
                    this.addHistory(originalText, this._currentTranslation);
                    if (this.onTranslatedDone) this.onTranslatedDone(this._currentTranslation);
                    this._broadcast('translation-done', {});
                },
                (error) => { console.error('[Translator] 翻译失败:', error); }
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