"""
TTS 语音合成模块 - 使用 edge-tts 实现中文语音朗读

功能：
- 将中文翻译结果转为语音输出
- 支持异步播放，不阻塞主流程
- 支持开关控制


- 支持多语言语音（英语、日语、德语）
"""

import asyncio
import threading
from typing import Dict, Optional, Callable
from enum import Enum

import edge_tts


class VoiceType(Enum):
    """语音类型"""
    ZH_CN = "zh-CN-XiaoxiaoNeural"  # 中文女声
    ZH_CN_MALE = "zh-CN-YunxiNeural"  # 中文男声
    EN_US = "en-US-JennyNeural"  # 英语女声
    EN_UK = "en-GB-SoniaNeural"  # 英式英语
    JA_JP = "ja-JP-NanamiNeural"  # 日语女声
    DE_DE = "de-DE-KatjaNeural"  # 德语女声


# 语言到默认语音的映射
LANG_TO_VOICE = {
    "zh": VoiceType.ZH_CN,
    "en": VoiceType.EN_US,
    "ja": VoiceType.JA_JP,
    "de": VoiceType.DE_DE,
}


class TTSEngine:
    """
    TTS 语音合成引擎

    使用 edge-tts 将文本转换为语音并播放
    """

    def __init__(self):
        self._is_enabled = True
        self._current_task: Optional[asyncio.Task] = None
        self._play_queue = asyncio.Queue()
        self._is_playing = False
        self._worker_task: Optional[asyncio.Task] = None
        self._on_play_start: Optional[Callable] = None
        self._on_play_end: Optional[Callable] = None

    def enable(self):
        """启用 TTS"""
        self._is_enabled = True
        print("🔊 TTS 已启用")

    def disable(self):
        """禁用 TTS"""
        self._is_enabled = False
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        print("🔇 TTS 已禁用")

    def toggle(self) -> bool:
        """切换开关状态"""
        if self._is_enabled:
            self.disable()
        else:
            self.enable()
        return self._is_enabled

    def is_enabled(self) -> bool:
        return self._is_enabled

    def set_callbacks(self, on_start: Callable = None, on_end: Callable = None):
        """设置播放回调"""
        self._on_play_start = on_start
        self._on_play_end = on_end

    async def speak(self, text: str, voice: VoiceType = None, lang: str = "zh"):
        """
        播放语音

        Args:
            text: 要朗读的文本
            voice: 语音类型，默认使用语言对应的语音
            lang: 语言代码，用于自动选择语音
        """
        if not self._is_enabled:
            return

        if not text or text.strip() == "":
            return

        if voice is None:
            voice = LANG_TO_VOICE.get(lang, VoiceType.ZH_CN)

        # 取消当前正在播放的语音
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

        # 播放新语音
        self._current_task = asyncio.create_task(self._play(text, voice))

    async def _play(self, text: str, voice: VoiceType):
        """实际播放语音"""
        try:
            if self._on_play_start:
                self._on_play_start(text)

            # 创建 TTS 通信对象
            communicate = edge_tts.Communicate(text, voice.value)

            # 播放音频
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    # 这里可以添加音频播放逻辑
                    # 使用简单的方式：保存到临时文件并播放
                    await self._play_audio_chunk(chunk["data"])

            if self._on_play_end:
                self._on_play_end()

        except asyncio.CancelledError:
            # 被取消，正常处理
            pass
        except Exception as e:
            print(f"TTS 播放错误: {e}")

    async def _play_audio_chunk(self, audio_data: bytes):
        """播放音频块（简化版，实际生产环境需要更完善的音频播放）"""
        # 这里为了简化，使用系统命令播放
        # 实际项目中可以使用 pyaudio 播放
        import tempfile
        import subprocess
        import platform

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio_data)
                temp_path = f.name

            # 根据操作系统选择播放命令
            system = platform.system()
            if system == "Windows":
                subprocess.run(["start", temp_path], shell=True, capture_output=True)
            elif system == "Darwin":  # macOS
                subprocess.run(["afplay", temp_path], capture_output=True)
            else:  # Linux
                subprocess.run(["mpg123", temp_path], capture_output=True)

        except Exception as e:
            print(f"播放音频块失败: {e}")

    async def speak_sync(self, text: str, voice: VoiceType = None, lang: str = "zh"):
        """同步播放语音（阻塞直到播放完成）"""
        if not self._is_enabled:
            return

        if not text or text.strip() == "":
            return

        if voice is None:
            voice = LANG_TO_VOICE.get(lang, VoiceType.ZH_CN)

        try:
            communicate = edge_tts.Communicate(text, voice.value)

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    await self._play_audio_chunk(chunk["data"])

        except Exception as e:
            print(f"TTS 同步播放错误: {e}")

    async def shutdown(self):
        """关闭 TTS 引擎"""
        self.disable()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()


class MockTTSEngine:
    """
    模拟 TTS 引擎（用于测试）
    """

    def __init__(self):
        self._is_enabled = True
        self._on_play_start: Optional[Callable] = None
        self._on_play_end: Optional[Callable] = None

    def enable(self):
        self._is_enabled = True
        print("🔊 [模拟] TTS 已启用")

    def disable(self):
        self._is_enabled = False
        print("🔇 [模拟] TTS 已禁用")

    def toggle(self) -> bool:
        self._is_enabled = not self._is_enabled
        return self._is_enabled

    def is_enabled(self) -> bool:
        return self._is_enabled

    def set_callbacks(self, on_start: Callable = None, on_end: Callable = None):
        self._on_play_start = on_start
        self._on_play_end = on_end

    async def speak(self, text: str, voice: VoiceType = None, lang: str = "zh"):
        """模拟播放"""
        if not self._is_enabled:
            return

        if not text or text.strip() == "":
            return

        if self._on_play_start:
            self._on_play_start(text)

        # 模拟播放延迟
        await asyncio.sleep(0.3)
        print(f"🔊 [模拟] 朗读: {text}")

        if self._on_play_end:
            self._on_play_end()

    async def speak_sync(self, text: str, voice: VoiceType = None, lang: str = "zh"):
        """模拟同步播放"""
        await self.speak(text, voice, lang)

    async def shutdown(self):
        pass


def create_tts(use_mock: bool = False) -> object:
    """
    创建 TTS 引擎实例

    Args:
        use_mock: 是否使用模拟模式

    Returns:
        TTS 引擎实例
    """
    if use_mock:
        print("⚠️ 使用模拟 TTS 模式")
        return MockTTSEngine()
    else:
        print("✅ 使用 edge-tts 模式")
        return TTSEngine()


# ========== 测试代码 ==========
async def test_tts():
    """测试 TTS 模块"""
    print("测试 TTS 模块...\n")

    # 使用模拟模式测试
    tts = create_tts(use_mock=True)

    def on_start(text):
        print(f"   🎙️ 开始朗读: {text}")

    def on_end():
        print(f"   ✅ 朗读完成")

    tts.set_callbacks(on_start, on_end)

    # 测试中文
    print("\n1. 测试中文语音:")
    await tts.speak("你好，欢迎使用 AI 同声传译助手")
    await asyncio.sleep(0.5)

    # 测试英语
    print("\n2. 测试英语语音:")
    await tts.speak("Hello, welcome to AI real-time translation", lang="en")
    await asyncio.sleep(0.5)

    # 测试日语
    print("\n3. 测试日语语音:")
    await tts.speak("こんにちは、リアルタイム翻訳へようこそ", lang="ja")
    await asyncio.sleep(0.5)

    # 测试德语
    print("\n4. 测试德语语音:")
    await tts.speak("Hallo, willkommen bei der Echtzeitübersetzung", lang="de")
    await asyncio.sleep(0.5)

    # 测试开关
    print("\n5. 测试开关功能:")
    tts.disable()
    await tts.speak("这条不会被播放")
    print("   ✅ 禁用后不播放")

    tts.enable()
    await tts.speak("恢复播放测试")

    await tts.shutdown()
    print("\n✅ TTS 模块测试完成")


def run_test():
    """运行测试"""
    asyncio.run(test_tts())


if __name__ == "__main__":
    run_test()