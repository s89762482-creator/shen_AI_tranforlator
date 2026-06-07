const CONFIG = {
    API_BASE_URL: 'http://localhost:5000',
    
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
    }
};