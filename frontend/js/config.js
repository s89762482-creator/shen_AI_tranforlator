const CONFIG = {
    API_BASE_URL: 'http://127.0.0.1:5000',
    ENDPOINTS: {
        HEALTH: '/api/health',
        TRANSCRIBE: '/api/transcribe',
        TRANSLATE_STREAM: '/api/translate/stream',
        HISTORY: '/api/history',
    },
    VAD: { THRESHOLD: 0.3, SILENCE_TIMEOUT: 2000 },
    TRANSLATE_ENGINE: 'deepseek',
    DEFAULT_TARGET_LANG: 'zh',
    SUPPORTED_LANGUAGES: [
        { code: 'zh', name: '中文', flag: '🇨🇳' },
        { code: 'en', name: 'English', flag: '🇺🇸' },
        { code: 'ja', name: '日本語', flag: '🇯🇵' },
    ],
    MAX_HISTORY: 50,
};