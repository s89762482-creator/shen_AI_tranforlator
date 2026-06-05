"""
配置模块 - 环境变量和API密钥管理

支持中、英、日、德四种语言的互相翻译
"""

import os
from pathlib import Path
from typing import Optional, List

# 加载 .env 文件
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("警告: python-dotenv 未安装，请执行: pip install python-dotenv")


# 支持的语言列表
SUPPORTED_LANGUAGES = {
    "zh": {"name": "中文", "code": "zh"},
    "en": {"name": "英语", "code": "en"},
    "ja": {"name": "日语", "code": "ja"},
    "de": {"name": "德语", "code": "de"},
}

# 语言代码到显示名称的映射
LANGUAGE_NAMES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "de": "Deutsch",
}

# DeepSeek 支持的语言提示词映射
LANGUAGE_PROMPTS = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "de": "Deutsch",
}


class Config:
    """全局配置类"""

    # ========== API 密钥配置 ==========
    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # ========== 语言配置 ==========
    # 源语言（从哪种语言翻译）
    SOURCE_LANGUAGE: str = os.getenv("SOURCE_LANGUAGE", "en")

    # 目标语言（翻译成哪种语言）
    TARGET_LANGUAGE: str = os.getenv("TARGET_LANGUAGE", "zh")

    # 启用的语言对（支持同时翻译成多种语言）
    # 格式: 用逗号分隔，如 "zh,en,ja,de"
    TARGET_LANGUAGES: List[str] = os.getenv("TARGET_LANGUAGES", "zh,en,ja,de").split(",")

    # ========== 音频配置 ==========
    SAMPLE_RATE: int = int(os.getenv("SAMPLE_RATE", "16000"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1024"))
    AUDIO_DEVICE_INDEX: int = int(os.getenv("AUDIO_DEVICE_INDEX", "-1"))

    # ========== ASR 配置 ==========
    CORRECTION_WINDOW_SECONDS: int = int(os.getenv("CORRECTION_WINDOW_SECONDS", "15"))

    @classmethod
    def validate(cls) -> bool:
        """验证必要配置是否完整"""
        errors = []

        if not cls.DEEPSEEK_API_KEY:
            errors.append("DEEPSEEK_API_KEY 未设置，请在 .env 文件中配置")

        # 验证语言配置
        if cls.SOURCE_LANGUAGE not in SUPPORTED_LANGUAGES:
            errors.append(f"SOURCE_LANGUAGE '{cls.SOURCE_LANGUAGE}' 不支持。支持的语言: {list(SUPPORTED_LANGUAGES.keys())}")

        for lang in cls.TARGET_LANGUAGES:
            lang = lang.strip()
            if lang not in SUPPORTED_LANGUAGES:
                errors.append(f"目标语言 '{lang}' 不支持。支持的语言: {list(SUPPORTED_LANGUAGES.keys())}")

        if errors:
            print("❌ 配置验证失败:")
            for error in errors:
                print(f"   - {error}")
            return False

        print("✅ 配置验证通过")
        return True

    @classmethod
    def get_source_language_name(cls) -> str:
        """获取源语言的显示名称"""
        return SUPPORTED_LANGUAGES.get(cls.SOURCE_LANGUAGE, {}).get("name", cls.SOURCE_LANGUAGE)

    @classmethod
    def get_target_language_names(cls) -> List[str]:
        """获取所有目标语言的显示名称列表"""
        names = []
        for lang in cls.TARGET_LANGUAGES:
            lang = lang.strip()
            if lang in SUPPORTED_LANGUAGES:
                names.append(SUPPORTED_LANGUAGES[lang]["name"])
        return names

    @classmethod
    def get_language_prompt(cls, language_code: str) -> str:
        """获取用于 API 提示词的语言名称"""
        return LANGUAGE_PROMPTS.get(language_code, language_code)

    @classmethod
    def display_info(cls) -> None:
        """打印当前配置信息"""
        print("\n========== 当前配置 ==========")
        print(f"DeepSeek API Key: {'已配置' if cls.DEEPSEEK_API_KEY else '未配置'}")
        print(f"DeepSeek 模型: {cls.DEEPSEEK_MODEL}")
        print(f"源语言: {cls.get_source_language_name()} ({cls.SOURCE_LANGUAGE})")
        print(f"目标语言: {', '.join(cls.get_target_language_names())}")
        print(f"采样率: {cls.SAMPLE_RATE} Hz")
        print(f"块大小: {cls.CHUNK_SIZE}")
        print(f"修正窗口: {cls.CORRECTION_WINDOW_SECONDS} 秒")
        print("============================\n")


# 用于快速测试
if __name__ == "__main__":
    Config.display_info()
    Config.validate()