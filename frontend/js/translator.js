const Translator = {
    history: [],
    sourceLang: CONFIG.DEFAULT_SOURCE_LANG,  // 源语言
    targetLang: CONFIG.DEFAULT_TARGET_LANG,  // 目标语言
    _currentTranslation: '',
    _channel: null,
    _socket: null,
    _pendingText: '',  // 缓存未完成的句子片段
    _pendingTimeout: null,  // 超时定时器

    onOriginalText: null,
    onTranslatedToken: null,
    onTranslatedDone: null,
    onHistoryUpdate: null,
    onEngineReady: null,

    // 设置源语言
    setSourceLang(lang) {
        this.sourceLang = lang;
        console.log('[Translator] 源语言设置为:', lang);
    },

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

    async processAudio(audioBlob, sourceLang = null) {
        // 使用传入的源语言或默认源语言
        const lang = sourceLang || this.sourceLang;
        
        try {
            const result = await this._recognizeWithBackend(audioBlob, lang);
            if (!result || !result.text || !result.text.trim()) return;

            const { text, is_complete } = result;
            console.log('[Translator] 语音识别结果:', text, '是否完整:', is_complete, '源语言:', lang);
            
            // 智能断句处理
            if (!is_complete) {
                // 句子不完整，缓存文本并等待下一次音频
                this._pendingText += (this._pendingText ? ' ' : '') + text;
                console.log('[Translator] 句子不完整，缓存:', this._pendingText);
                
                // 设置超时：如果5秒内没有新音频，强制翻译缓存的内容
                this._setPendingTimeout();
                
                // 显示缓存的原文（让用户看到正在识别的内容）
                if (this.onOriginalText) this.onOriginalText(this._pendingText + '...');
                this._broadcast('original', { text: this._pendingText + '...' });
                
                return { original: this._pendingText, translated: '', pending: true };
            }
            
            // 句子完整，清除超时并翻译
            this._clearPendingTimeout();
            
            // 合并缓存的文本和当前文本
            const fullText = this._pendingText + (this._pendingText ? ' ' : '') + text;
            this._pendingText = '';  // 清空缓存
            
            console.log('[Translator] 句子完整，翻译:', fullText);
            
            if (this.onOriginalText) this.onOriginalText(fullText);
            this._broadcast('original', { text: fullText });
            
            // 调用翻译API进行翻译（包含源语言参数）
            this._currentTranslation = '';
            
            await API.translateStream(
                fullText,
                lang,  // 源语言
                this.targetLang,  // 目标语言
                // onToken - 流式翻译token
                (token) => {
                    this._currentTranslation += token;
                    if (this.onTranslatedToken) this.onTranslatedToken(this._currentTranslation);
                    this._broadcast('translation', { text: this._currentTranslation });
                },
                // onDone - 翻译完成
                () => {
                    console.log('[Translator] 翻译完成:', this._currentTranslation);
                    this.addHistory(fullText, this._currentTranslation);
                    if (this.onTranslatedDone) this.onTranslatedDone(this._currentTranslation);
                    this._broadcast('translation-done', {});
                },
                // onError - 翻译错误
                (error) => {
                    console.error('[Translator] 翻译失败:', error);
                    // 翻译失败时，使用原文
                    this._currentTranslation = fullText;
                    if (this.onTranslatedToken) this.onTranslatedToken(this._currentTranslation);
                    this._broadcast('translation', { text: this._currentTranslation });
                    this.addHistory(fullText, this._currentTranslation);
                    if (this.onTranslatedDone) this.onTranslatedDone(this._currentTranslation);
                    this._broadcast('translation-done', {});
                }
            );
            
            return { original: fullText, translated: this._currentTranslation };
        } catch (error) {
            console.error('[Translator] 处理音频出错:', error);
        }
    },

    async _recognizeWithBackend(audioBlob, sourceLang = 'en') {
        try {
            const result = await API.transcribe(audioBlob, sourceLang);
            if (result.success && result.data.text) {
                return {
                    text: result.data.text,
                    is_complete: result.data.is_complete !== undefined ? result.data.is_complete : true
                };
            }
        } catch (error) {}
        return null;
    },

    _setPendingTimeout() {
        // 清除之前的超时
        this._clearPendingTimeout();
        
        // 设置5秒超时，强制翻译缓存的内容
        this._pendingTimeout = setTimeout(() => {
            if (this._pendingText) {
                console.log('[Translator] 超时，强制翻译缓存:', this._pendingText);
                this._forceTranslatePending();
            }
        }, 5000);
    },

    _clearPendingTimeout() {
        if (this._pendingTimeout) {
            clearTimeout(this._pendingTimeout);
            this._pendingTimeout = null;
        }
    },

    async _forceTranslatePending() {
        if (!this._pendingText) return;
        
        const fullText = this._pendingText;
        this._pendingText = '';
        this._clearPendingTimeout();
        
        if (this.onOriginalText) this.onOriginalText(fullText);
        this._broadcast('original', { text: fullText });
        
        this._currentTranslation = '';
        
        try {
            await API.translateStream(
                fullText,
                this.sourceLang,
                this.targetLang,
                (token) => {
                    this._currentTranslation += token;
                    if (this.onTranslatedToken) this.onTranslatedToken(this._currentTranslation);
                    this._broadcast('translation', { text: this._currentTranslation });
                },
                () => {
                    console.log('[Translator] 强制翻译完成:', this._currentTranslation);
                    this.addHistory(fullText, this._currentTranslation);
                    if (this.onTranslatedDone) this.onTranslatedDone(this._currentTranslation);
                    this._broadcast('translation-done', {});
                },
                (error) => {
                    console.error('[Translator] 强制翻译失败:', error);
                    this._currentTranslation = fullText;
                    if (this.onTranslatedToken) this.onTranslatedToken(this._currentTranslation);
                    this._broadcast('translation', { text: this._currentTranslation });
                    this.addHistory(fullText, this._currentTranslation);
                    if (this.onTranslatedDone) this.onTranslatedDone(this._currentTranslation);
                    this._broadcast('translation-done', {});
                }
            );
        } catch (error) {
            console.error('[Translator] 强制翻译出错:', error);
        }
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