"""
实时语音识别模块 - 使用免费 Google Web Speech API

功能：
- 将麦克风捕获的音频数据识别为英文文本
- 完全免费，无需 API Key，需要联网
- 支持静音过滤和噪音自适应
"""

import asyncio
import numpy as np
import speech_recognition as sr
from typing import Optional

from config import Config


class FreeASR:
    """
    使用 Google Web Speech API 进行语音识别
    完全免费，无需 API Key
    """

    def __init__(self):
        self.recognizer = sr.Recognizer()
        # 调整环境噪音阈值
        self.recognizer.energy_threshold = 300
        # 动态噪音调整
        self.recognizer.dynamic_energy_threshold = True

    async def recognize_from_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000
    ) -> Optional[str]:
        """
        将音频数据识别为文本

        Args:
            audio_data: 音频数据 (numpy array, float32, 范围 -1~1)
            sample_rate: 采样率

        Returns:
            识别出的英文文本，失败返回 None
        """
        if audio_data is None or len(audio_data) == 0:
            return None

        # 检查音量，过滤静音
        volume = np.abs(audio_data).mean()
        if volume < 0.005:
            return None

        try:
            # 将 float32 [-1, 1] 转换为 int16 [-32768, 32767]
            audio_int16 = (audio_data.flatten() * 32767).astype(np.int16)

            # 创建 AudioData 对象
            audio = sr.AudioData(
                audio_int16.tobytes(),
                sample_rate,
                2  # 16-bit 采样宽度
            )

            # 使用 Google Web Speech API 识别（免费）
            text = self.recognizer.recognize_google(audio, language="en-US")

            if text and text.strip():
                return text.strip()
            return None

        except sr.UnknownValueError:
            # 无法识别（可能是噪音或非英语）
            return None
        except sr.RequestError as e:
            print(f"❌ Google 语音识别服务错误: {e}")
            return None
        except Exception as e:
            print(f"❌ 识别失败: {e}")
            return None

    async def close(self):
        """关闭资源（Google API 无需关闭）"""
        pass


class MockASR:
    """
    模拟 ASR（用于测试，不需要 API）
    """

    def __init__(self):
        self._test_phrases = [
            "Hello world",
            "How are you",
            "This is a test",
            "I love programming",
            "Good morning",
            "Thank you very much",
            "What time is it",
            "Nice to meet you"
        ]
        self._index = 0

    async def recognize_from_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000
    ) -> Optional[str]:
        """模拟识别"""
        volume = np.abs(audio_data).mean()
        if volume < 0.01:
            return None

        result = self._test_phrases[self._index % len(self._test_phrases)]
        self._index += 1

        # 模拟 API 延迟
        await asyncio.sleep(0.3)
        return result

    async def close(self):
        pass


def create_asr(use_mock: bool = False):
    """
    创建 ASR 实例

    Args:
        use_mock: 是否使用模拟模式（测试用）

    Returns:
        ASR 实例
    """
    if use_mock:
        print("⚠️ 使用模拟 ASR 模式（测试用）")
        return MockASR()
    else:
        print("✅ 使用免费 Google 语音识别模式")
        return FreeASR()