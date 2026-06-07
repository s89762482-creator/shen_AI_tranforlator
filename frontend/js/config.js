const CONFIG = {
    API_BASE_URL: 'http://127.0.0.1:5000',
    ENDPOINTS: {
        HEALTH: '/api/health',
        TRANSCRIBE: '/api/transcribe',
        TRANSLATE_STREAM: '/api/translate/stream',
        HISTORY: '/api/history',
        CONTEXT_CLEAR: '/api/context/clear',
        CONTEXT_INFO: '/api/context/info',
    },
    VAD: { 
        THRESHOLD: 0.3, 
        SILENCE_TIMEOUT: 1500,  // 缩短静音超时，避免句子过长
        MIN_SPEECH_DURATION: 200, // 最小语音时长，过滤噪音
        NOISE_FLOOR_ADAPTATION: true // 自动适应噪音环境
    },
    TRANSLATE_ENGINE: 'deepseek',
    DEFAULT_SOURCE_LANG: 'en',  // 默认源语言：英文
    DEFAULT_TARGET_LANG: 'zh',  // 默认目标语言：中文
    SUPPORTED_SOURCE_LANGUAGES: [
        { code: 'en', name: 'English', flag: '🇺🇸' },
        { code: 'zh', name: '中文', flag: '🇨🇳' },
    ],
    SUPPORTED_TARGET_LANGUAGES: {
        'en': [  // 当源语言是英文时，可选的目标语言
            { code: 'zh', name: '中文', flag: '🇨🇳' },
            { code: 'ja', name: '日本語', flag: '🇯🇵' },
        ],
        'zh': [  // 当源语言是中文时，可选的目标语言
            { code: 'en', name: 'English', flag: '🇺🇸' },
            { code: 'ja', name: '日本語', flag: '🇯🇵' },
        ],
    },
    // 旧的语言列表（兼容旧代码）
    SUPPORTED_LANGUAGES: [
        { code: 'zh', name: '中文', flag: '🇨🇳' },
        { code: 'en', name: 'English', flag: '🇺🇸' },
        { code: 'ja', name: '日本語', flag: '🇯🇵' },
    ],
    MAX_HISTORY: 50,
};