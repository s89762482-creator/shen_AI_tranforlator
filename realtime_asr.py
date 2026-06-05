"""
实时语音识别模块 - 调用 DeepSeek API 将语音转文字

功能：
- 发送音频数据到 DeepSeek API 进行识别
- 返回识别出的英文文本
- 支持异步调用
"""

import asyncio
import base64
import json
from typing import Optional, Callable, List, Dict
import aiohttp
import numpy as np

from config import Config


class DeepSeekASR:
    """
    使用 DeepSeek API 进行语音识别

    注意：DeepSeek API 主要支持文本对话，语音识别需要先将音频转为文字。
    本实现使用 DeepSeek 的文本理解能力，配合音频描述。
    实际生产环境建议使用专门的语音识别 API（如 Whisper）。
    """

    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL
        self.model = Config.DEEPSEEK_MODEL
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def recognize_from_audio(
            self,
            audio_data: np.ndarray,
            sample_rate: int = 16000
    ) -> Optional[str]:
        """
        将音频数据识别为文本

        注意：由于 DeepSeek API 不直接支持语音输入，
        这里使用音频特征描述的方式。实际使用时建议替换为：
        - OpenAI Whisper API
        - Azure Speech-to-Text
        - Google Speech-to-Text

        Args:
            audio_data: 音频数据 (numpy array)
            sample_rate: 采样率

        Returns:
            识别出的文本，失败返回 None
        """
        if not self.api_key:
            print("❌ DeepSeek API Key 未配置")
            return None

        # 计算音频特征
        audio_info = self._extract_audio_features(audio_data, sample_rate)

        # 构建提示词
        prompt = self._build_recognition_prompt(audio_info)

        try:
            session = await self._get_session()
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的语音识别助手。根据用户提供的音频特征描述，推测用户可能说了什么英文单词或短语。请只输出识别出的英文文本，不要添加额外解释。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 100
            }

            async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    text = result['choices'][0]['message']['content'].strip()
                    return text if text else None
                else:
                    error_text = await response.text()
                    print(f"❌ API 请求失败: {response.status} - {error_text}")
                    return None

        except asyncio.TimeoutError:
            print("❌ API 请求超时")
            return None
        except aiohttp.ClientError as e:
            print(f"❌ 网络错误: {e}")
            return None
        except Exception as e:
            print(f"❌ 识别失败: {e}")
            return None

    def _extract_audio_features(self, audio_data: np.ndarray, sample_rate: int) -> Dict:
        """
        提取音频特征用于识别

        Args:
            audio_data: 音频数据
            sample_rate: 采样率

        Returns:
            音频特征字典
        """
        # 计算基本特征
        volume = float(np.abs(audio_data).mean())
        max_volume = float(np.abs(audio_data).max())

        # 判断是否有人声（基于音量阈值）
        has_speech = volume > 0.01

        # 计算过零率（粗略估计语音活动）
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio_data)))) / 2
        zero_crossing_rate = zero_crossings / len(audio_data)

        return {
            "volume": volume,
            "max_volume": max_volume,
            "has_speech": has_speech,
            "zero_crossing_rate": float(zero_crossing_rate),
            "duration": len(audio_data) / sample_rate
        }

    def _build_recognition_prompt(self, audio_info: Dict) -> str:
        """
        构建识别提示词

        Args:
            audio_info: 音频特征

        Returns:
            提示词文本
        """
        if not audio_info["has_speech"]:
            return "这段音频中没有检测到人声，可能是静音或噪音。"

        prompt = f"""请根据以下音频特征推测用户可能说的英文内容：

音频特征：
- 音量级别: {audio_info['volume']:.4f}
- 最大音量: {audio_info['max_volume']:.4f}
- 音频时长: {audio_info['duration']:.2f} 秒
- 过零率: {audio_info['zero_crossing_rate']:.4f}

请推测这段音频可能包含的英文单词或短语（只输出文本，不要解释）：
"""
        return prompt


class SimpleASR:
    """
    简单的语音识别模拟器（用于测试）

    当 DeepSeek API 不可用时，使用此模拟器返回模拟结果
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
        self._phrase_index = 0

    async def recognize_from_audio(
            self,
            audio_data: np.ndarray,
            sample_rate: int = 16000
    ) -> Optional[str]:
        """模拟识别"""
        # 检查是否有声音
        volume = float(np.abs(audio_data).mean())
        if volume < 0.01:
            return None

        # 轮流返回测试短语
        result = self._test_phrases[self._phrase_index % len(self._test_phrases)]
        self._phrase_index += 1

        # 模拟 API 延迟
        await asyncio.sleep(0.5)

        return result

    async def close(self):
        pass


# 根据配置选择使用真实 API 还是模拟器
def create_asr(use_mock: bool = False) -> object:
    """
    创建 ASR 实例

    Args:
        use_mock: 是否使用模拟器（当 API 密钥未配置时自动使用）

    Returns:
        ASR 实例
    """
    if use_mock or not Config.DEEPSEEK_API_KEY:
        print("⚠️ 使用模拟 ASR 模式（无需 API）")
        return SimpleASR()
    else:
        print("✅ 使用 DeepSeek ASR 模式")
        return DeepSeekASR()


# ========== 测试代码 ==========
async def test_asr():
    """测试语音识别模块"""
    print("测试语音识别模块...\n")

    # 生成模拟音频数据（静音 + 有声音）
    sample_rate = 16000

    print("1. 测试静音片段...")
    silent_audio = np.zeros((1024, 1), dtype=np.float32)

    # 使用模拟器测试
    asr = create_asr(use_mock=True)
    result = await asr.recognize_from_audio(silent_audio, sample_rate)
    print(f"   识别结果: {result}")
    print(f"   ✅ 静音测试完成\n")

    print("2. 测试有声音片段（模拟）...")
    # 模拟有声音的音频数据（随机噪声 + 音量）
    voice_audio = np.random.randn(1024, 1).astype(np.float32) * 0.1

    result = await asr.recognize_from_audio(voice_audio, sample_rate)
    print(f"   识别结果: {result}")

    await asr.close()
    print("\n✅ 语音识别模块测试完成")


if __name__ == "__main__":
    asyncio.run(test_asr())