"""
翻译模块 - 实时翻译 + 修正

功能：
- 支持中、英、日、德四种语言的互相翻译
- 支持翻译修正（基于上下文重新翻译）
- 保留翻译历史，支持修正后更新
"""

import asyncio
import json
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field
from collections import deque

import aiohttp

from config import Config, SUPPORTED_LANGUAGES, LANGUAGE_NAMES


@dataclass
class TranslationSegment:
    """翻译片段"""
    source_text: str  # 原文
    target_text: str  # 译文
    timestamp: float  # 时间戳
    is_corrected: bool = False  # 是否已被修正
    original_target: Optional[str] = None  # 原始译文（修正前）


class TranslationHistory:
    """翻译历史缓存"""

    def __init__(self, max_size: int = 50):
        self.segments: deque = deque(maxlen=max_size)

    def add(self, source: str, target: str, timestamp: float = None) -> TranslationSegment:
        """添加翻译记录"""
        import time
        if timestamp is None:
            timestamp = time.time()

        segment = TranslationSegment(
            source_text=source,
            target_text=target,
            timestamp=timestamp
        )
        self.segments.append(segment)
        return segment

    def get_last(self) -> Optional[TranslationSegment]:
        """获取最后一条翻译"""
        return self.segments[-1] if self.segments else None

    def update_last(self, new_target: str) -> bool:
        """更新最后一条翻译"""
        last = self.get_last()
        if last and not last.is_corrected:
            last.original_target = last.target_text
            last.target_text = new_target
            last.is_corrected = True
            return True
        return False

    def get_all_text(self) -> str:
        """获取所有原文（用于上下文）"""
        return " ".join([seg.source_text for seg in self.segments])

    def clear(self):
        """清空历史"""
        self.segments.clear()


class DeepSeekTranslator:
    """使用 DeepSeek API 进行翻译"""

    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL
        self.model = Config.DEEPSEEK_MODEL
        self._session: Optional[aiohttp.ClientSession] = None

        # 源语言和目标语言
        self.source_lang = Config.SOURCE_LANGUAGE
        self.target_langs = [lang.strip() for lang in Config.TARGET_LANGUAGES]

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _build_prompt(self, text: str, target_lang: str, context: str = "") -> str:
        """
        构建翻译提示词

        Args:
            text: 待翻译文本
            target_lang: 目标语言代码 (zh, en, ja, de)
            context: 上下文文本
        """
        target_name = SUPPORTED_LANGUAGES.get(target_lang, {}).get("name", target_lang)
        source_name = SUPPORTED_LANGUAGES.get(self.source_lang, {}).get("name", self.source_lang)

        prompt = f"""请将以下{source_name}文本翻译成{target_name}。

原文：{text}
目标语言：{target_name}

要求：
1. 只输出翻译结果，不要添加任何解释
2. 保持原文的语气和风格
3. 如果是短句，翻译要自然流畅"""

        if context:
            prompt += f"\n\n上下文参考（仅用于理解语义）：{context}"

        return prompt

    async def translate(
            self,
            text: str,
            target_lang: str = None,
            context: str = ""
    ) -> Optional[str]:
        """
        翻译单个文本

        Args:
            text: 待翻译文本
            target_lang: 目标语言，默认使用配置的第一个目标语言
            context: 上下文文本

        Returns:
            翻译结果，失败返回 None
        """
        if not text or text.strip() == "":
            return None

        if not self.api_key:
            print("❌ DeepSeek API Key 未配置")
            return None

        if target_lang is None:
            target_lang = self.target_langs[0] if self.target_langs else "zh"

        prompt = self._build_prompt(text, target_lang, context)

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
                        "content": "你是一个专业的翻译助手，只输出翻译结果，不要添加任何额外内容。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 500
            }

            async with session.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    translated = result['choices'][0]['message']['content'].strip()
                    return translated
                else:
                    error_text = await response.text()
                    print(f"❌ 翻译 API 请求失败: {response.status}")
                    return None

        except asyncio.TimeoutError:
            print("❌ 翻译请求超时")
            return None
        except aiohttp.ClientError as e:
            print(f"❌ 网络错误: {e}")
            return None
        except Exception as e:
            print(f"❌ 翻译失败: {e}")
            return None

    async def translate_multi(
            self,
            text: str,
            context: str = ""
    ) -> Dict[str, Optional[str]]:
        """
        翻译成所有配置的目标语言

        Args:
            text: 待翻译文本
            context: 上下文文本

        Returns:
            {目标语言: 翻译结果} 的字典
        """
        results = {}
        for target_lang in self.target_langs:
            result = await self.translate(text, target_lang, context)
            results[target_lang] = result
        return results


class MockTranslator:
    """模拟翻译器（用于测试）"""

    def __init__(self):
        self.source_lang = Config.SOURCE_LANGUAGE
        self.target_langs = [lang.strip() for lang in Config.TARGET_LANGUAGES]

    async def translate(self, text: str, target_lang: str = None, context: str = "") -> Optional[str]:
        """模拟翻译"""
        if not text or text.strip() == "":
            return None

        # 模拟 API 延迟
        await asyncio.sleep(0.3)

        # 返回模拟翻译结果
        mock_translations = {
            ("en", "zh"): f"[中文] {text}",
            ("en", "ja"): f"[日本語] {text}",
            ("en", "de"): f"[Deutsch] {text}",
            ("zh", "en"): f"[English] {text}",
            ("zh", "ja"): f"[日本語] {text}",
            ("zh", "de"): f"[Deutsch] {text}",
            ("ja", "zh"): f"[中文] {text}",
            ("ja", "en"): f"[English] {text}",
            ("ja", "de"): f"[Deutsch] {text}",
            ("de", "zh"): f"[中文] {text}",
            ("de", "en"): f"[English] {text}",
            ("de", "ja"): f"[日本語] {text}",
        }

        key = (self.source_lang, target_lang or self.target_langs[0])
        return mock_translations.get(key, f"[翻译] {text}")

    async def translate_multi(self, text: str, context: str = "") -> Dict[str, Optional[str]]:
        """翻译成所有目标语言"""
        results = {}
        for target_lang in self.target_langs:
            results[target_lang] = await self.translate(text, target_lang, context)
        return results

    async def close(self):
        pass


class TranslationManager:
    """翻译管理器"""

    def __init__(self, use_mock: bool = False):
        """
        初始化翻译管理器

        Args:
            use_mock: 是否使用模拟模式
        """
        if use_mock or not Config.DEEPSEEK_API_KEY:
            print("⚠️ 使用模拟翻译模式（无需 API）")
            self.translator = MockTranslator()
        else:
            print("✅ 使用 DeepSeek 翻译模式")
            self.translator = DeepSeekTranslator()

        self.history = TranslationHistory()
        self.on_new_translation: Optional[Callable] = None
        self.on_correction: Optional[Callable] = None

    async def translate_and_record(
            self,
            source_text: str,
            context: str = ""
    ) -> Dict[str, Optional[str]]:
        """
        翻译并记录到历史

        Args:
            source_text: 原文
            context: 上下文

        Returns:
            翻译结果字典
        """
        if not source_text or source_text.strip() == "":
            return {}

        # 执行翻译
        results = await self.translator.translate_multi(source_text, context)

        # 记录到历史（使用第一个目标语言的翻译作为主要记录）
        primary_lang = self.translator.target_langs[0] if self.translator.target_langs else "zh"
        primary_result = results.get(primary_lang)

        if primary_result:
            segment = self.history.add(source_text, primary_result)

            # 触发回调
            if self.on_new_translation:
                self.on_new_translation(source_text, results)

        return results

    async def correct_last(self, context: str = "") -> bool:
        """
        修正最后一条翻译

        Args:
            context: 上下文文本

        Returns:
            是否修正成功
        """
        last = self.history.get_last()
        if not last or last.is_corrected:
            return False

        # 使用上下文重新翻译
        new_target = await self.translator.translate(
            last.source_text,
            self.translator.target_langs[0],
            context
        )

        if new_target and new_target != last.target_text:
            success = self.history.update_last(new_target)
            if success and self.on_correction:
                self.on_correction(last.source_text, last.target_text, new_target)
            return success

        return False

    def get_display_segments(self) -> List[Dict]:
        """获取用于显示的翻译历史"""
        return [
            {
                "source": seg.source_text,
                "target": seg.target_text,
                "is_corrected": seg.is_corrected,
                "original": seg.original_target
            }
            for seg in self.history.segments
        ]

    async def close(self):
        """关闭资源"""
        await self.translator.close()


# ========== 测试代码 ==========
async def test_translator():
    """测试翻译模块"""
    print("测试翻译模块...\n")

    # 使用模拟模式测试
    manager = TranslationManager(use_mock=True)

    # 设置回调
    def on_new(source, results):
        print(f"   📝 新翻译: {source} → {results}")

    def on_correction(source, old, new):
        print(f"   🔄 修正: {old} → {new}")

    manager.on_new_translation = on_new
    manager.on_correction = on_correction

    # 测试单条翻译
    print("1. 测试单条翻译:")
    results = await manager.translate_and_record("Hello world")
    print(f"   结果: {results}\n")

    # 测试多条翻译
    print("2. 测试多条翻译:")
    await manager.translate_and_record("How are you")
    await manager.translate_and_record("Nice to meet you")

    # 显示历史
    print("\n3. 翻译历史:")
    for i, seg in enumerate(manager.get_display_segments()):
        print(f"   [{i}] {seg['source']} → {seg['target']}")

    # 测试修正
    print("\n4. 测试翻译修正:")
    # 模拟一个需要修正的场景
    manager.history.add("I went to the bank", "我去了长凳")
    print(f"   修正前: 我去了长凳")

    await manager.correct_last(context="deposit money")
    last = manager.history.get_last()
    print(f"   修正后: {last.target_text}")

    await manager.close()
    print("\n✅ 翻译模块测试完成")


if __name__ == "__main__":
    asyncio.run(test_translator())