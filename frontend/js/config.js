const CONFIG = {
    API_BASE_URL: 'http://localhost:5000',
    
    // 默认语言设置
    DEFAULT_SOURCE_LANG: 'en',  // 默认源语言：英文
    DEFAULT_TARGET_LANG: 'zh',  // 默认目标语言：中文
    
    // 翻译引擎
    TRANSLATE_ENGINE: 'deepseek',  // 翻译引擎：deepseek 或 openai
    
    // 历史记录
    MAX_HISTORY: 50,
    
    SUPPORTED_SOURCE_LANGUAGES: [
        { code: 'en', name: 'English', flag: '🇺🇸' },
        { code: 'zh', name: '中文', flag: '🇨🇳' },
        { code: 'ja', name: '日本語', flag: '🇯🇵' },
    ],
    
    SUPPORTED_TARGET_LANGUAGES: {
        'en': [
            { code: 'zh', name: '中文', flag: '🇨🇳' },
            { code: 'ja', name: '日本語', flag: '🇯🇵' },
        ],
        'zh': [
            { code: 'en', name: 'English', flag: '🇺🇸' },
            { code: 'ja', name: '日本語', flag: '🇯🇵' },
        ],
        'ja': [
            { code: 'zh', name: '中文', flag: '🇨🇳' },
            { code: 'en', name: 'English', flag: '🇺🇸' },
        ],
    },
    
    AUDIO_CONFIG: {
        sampleRate: 16000,
        channelCount: 1,
        sampleSize: 16,
    },
    
    SUBTITLE_CONFIG: {
        maxLines: 3,
        fadeDuration: 2000,
        fontSize: 24,
    },
    
    // VAD (Voice Activity Detection) 配置
    VAD: {
        SILENCE_TIMEOUT: 1500,       // 静音超时时间（毫秒）
        MIN_SPEECH_DURATION: 200,    // 最小语音时长（毫秒）
    },
    
    // API 端点
    ENDPOINTS: {
        HEALTH: '/api/health',
        TRANSCRIBE: '/api/transcribe',
        TRANSLATE_STREAM: '/api/translate/stream',
        HISTORY: '/api/history',
        CONTEXT_CLEAR: '/api/context/clear',
        CONTEXT_INFO: '/api/context/info',
        OVERLAY_START: '/api/overlay/start',
        OVERLAY_STOP: '/api/overlay/stop',
        OVERLAY_STATUS: '/api/overlay/status',
        OVERLAY_TEST: '/api/overlay/test',
        OVERLAY_BROADCAST: '/api/overlay/broadcast',
    }
};