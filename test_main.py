"""测试主程序逻辑"""
import asyncio
from subtitle_manager import SubtitleManager
from realtime_asr import create_asr
from translator import TranslationManager


async def test():
    print("测试识别和翻译模块...")

    # 创建管理器
    manager = SubtitleManager()

    # 使用模拟模式
    asr = create_asr(use_mock=True)
    translator = TranslationManager(use_mock=True)

    # 设置翻译回调
    def on_translation(source, translations):
        print(f"📝 收到翻译: {source} -> {translations.get('zh', '')}")
        entry = manager.add_subtitle(source, translations)
        print(f"   字幕条目 ID: {entry.id}")

    translator.on_new_translation = on_translation

    # 模拟音频数据
    import numpy as np
    mock_audio = np.random.randn(16000, 1).astype(np.float32) * 0.1

    # 识别
    text = await asr.recognize_from_audio(mock_audio)
    print(f"🎤 识别结果: {text}")

    # 翻译
    if text:
        await translator.translate_and_record(text, "")

    # 显示字幕
    print(f"\n📺 当前字幕 ({len(manager.entries)} 条):")
    for entry in manager.entries:
        print(f"   [{entry.id}] {entry.source_text} -> {entry.translations.get('zh', '')}")

    await asr.close()
    await translator.close()


if __name__ == "__main__":
    asyncio.run(test())