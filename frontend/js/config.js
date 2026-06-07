const CONFIG = {
    API_BASE_URL: 'http://127.0.0.1:5000',
    ENDPOINTS: {
        HEALTH: '/api/health',
        TRANSCRIBE: '/api/transcribe',
        TRANSLATE_STREAM: '/api/translate/stream',
        HISTORY: '/api/history',
    },
    VAD: { 
        THRESHOLD: 0.3, 
        SILENCE_TIMEOUT: 1500,  // 缩短静音超时，避免句子过长
        MIN_SPEECH_DURATION: 200, // 最小语音时长，过滤噪音
        NOISE_FLOOR_ADAPTATION: true // 自动适应噪音环境
    },
    TRANSLATE_ENGINE: 'deepseek',
    DEFAULT_TARGET_LANG: 'zh',
    SUPPORTED_LANGUAGES: [
        { code: 'zh', name: '中文', flag: '🇨🇳' },
        { code: 'en', name: 'English', flag: '🇺🇸' },
        { code: 'ja', name: '日本語', flag: '🇯🇵' },
    ],
    MAX_HISTORY: 50,
};