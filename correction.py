"""
修正机制模块 - 滑动窗口 + 历史修正

核心功能：
- 维护最近 N 秒的识别文本缓存（带时间戳）
- 基于上下文的识别结果自动修正
- 修正后通知 UI 更新
"""

import asyncio
import re
import time
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from collections import deque


@dataclass
class TextSegment:
    """文本片段，带时间戳"""
    text: str
    timestamp: float
    is_corrected: bool = False
    original_text: Optional[str] = None


class CorrectionWindow:
    """滑动窗口缓存管理器"""

    def __init__(self, window_seconds: int = 15):
        self.window_seconds = window_seconds
        self.segments: deque = deque()
        self._correction_callback: Optional[Callable] = None

    def add_segment(self, text: str, timestamp: float = None) -> Optional[TextSegment]:
        """添加新的文本片段"""
        if not text or text.strip() == "":
            return None

        if timestamp is None:
            timestamp = time.time()

        segment = TextSegment(text=text.strip(), timestamp=timestamp)
        self.segments.append(segment)
        self._clean_expired()
        return segment

    def _clean_expired(self):
        """清理超出窗口的旧片段"""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        while self.segments and self.segments[0].timestamp < cutoff_time:
            self.segments.popleft()

    def get_all_text(self) -> str:
        """获取窗口内所有文本"""
        return " ".join([seg.text for seg in self.segments])

    def get_last_segment(self) -> Optional[TextSegment]:
        """获取最后一个文本片段"""
        return self.segments[-1] if self.segments else None

    def correct_segment(self, index: int, new_text: str, original_text: str = None) -> bool:
        """修正指定位置的文本片段"""
        if index < 0 or index >= len(self.segments):
            return False

        segment = self.segments[index]
        if not segment.is_corrected:
            segment.original_text = original_text or segment.text
        segment.text = new_text
        segment.is_corrected = True

        if self._correction_callback:
            self._correction_callback(index, segment)

        return True

    def get_segments_for_display(self) -> List[Dict]:
        """获取用于显示的片段信息"""
        return [
            {
                "text": seg.text,
                "is_corrected": seg.is_corrected,
                "original": seg.original_text
            }
            for seg in self.segments
        ]


class SimpleCorrector:
    """简单的本地修正器"""

    # 常见错误映射（错误 -> 正确）
    WORD_CORRECTIONS = {
        "bench": "bank",
        "meat": "meet",
        "there": "their",
        "your": "you're",
        "its": "it's",
    }

    # 上下文触发规则：(错误词, 正确词, 上下文关键词)
    CONTEXT_RULES = [
        ("bench", "bank", ["money", "deposit", "withdraw", "loan", "account", "cash"]),
        ("meat", "meet", ["you", "him", "her", "them", "today", "tomorrow", "later"]),
        ("there", "their", ["house", "car", "book", "money", "home", "family"]),
    ]

    @classmethod
    def correct(cls, text: str, context: str = "") -> Optional[str]:
        """
        修正文本中的错误

        Args:
            text: 待修正的文本
            context: 上下文文本

        Returns:
            修正后的文本，如果没有修正则返回 None
        """
        if not text:
            return None

        original = text
        corrected = text

        # 1. 先应用简单单词替换
        for wrong, correct in cls.WORD_CORRECTIONS.items():
            # 使用单词边界匹配，避免部分匹配
            pattern = r'\b' + re.escape(wrong) + r'\b'
            if re.search(pattern, corrected, re.IGNORECASE):
                corrected = re.sub(pattern, correct, corrected, flags=re.IGNORECASE)

        # 2. 应用上下文规则
        context_lower = context.lower()
        for wrong, correct, triggers in cls.CONTEXT_RULES:
            pattern = r'\b' + re.escape(wrong) + r'\b'
            if re.search(pattern, corrected, re.IGNORECASE):
                # 检查上下文是否包含触发词
                if any(trigger in context_lower for trigger in triggers):
                    corrected = re.sub(pattern, correct, corrected, flags=re.IGNORECASE)

        # 3. 特殊规则：检查 to/too 的上下文（只修正明显的错误）
        # 如果 "to" 后面跟着动词，通常是对的；如果 "too" 在形容词前，通常是对的
        # 这里不做自动转换，避免误判

        return corrected if corrected != original else None


class CorrectionManager:
    """修正管理器"""

    def __init__(self, window_seconds: int = 15):
        self.window = CorrectionWindow(window_seconds)
        self.corrector = SimpleCorrector()
        self.on_correction: Optional[Callable] = None
        self.window._correction_callback = self._on_correction

    def add_recognition(self, text: str) -> Optional[TextSegment]:
        """添加新的识别结果"""
        return self.window.add_segment(text)

    async def correct_last(self) -> Optional[str]:
        """修正最后一个片段"""
        last = self.window.get_last_segment()
        if not last or last.is_corrected:
            return None

        # 获取完整上下文
        context = self.window.get_all_text()

        # 尝试修正
        corrected = self.corrector.correct(last.text, context)

        if corrected and corrected != last.text:
            # 找到索引并修正
            for i, seg in enumerate(self.window.segments):
                if seg is last:
                    self.window.correct_segment(i, corrected, last.text)
                    return corrected

        return None

    async def correct_all(self) -> List[str]:
        """修正所有未修正的片段"""
        results = []
        for i, seg in enumerate(self.window.segments):
            if not seg.is_corrected:
                context = self.window.get_all_text()
                corrected = self.corrector.correct(seg.text, context)
                if corrected and corrected != seg.text:
                    self.window.correct_segment(i, corrected, seg.text)
                    results.append(corrected)
        return results

    def _on_correction(self, index: int, segment: TextSegment):
        """修正回调"""
        if self.on_correction:
            original = segment.original_text or "未知"
            self.on_correction(index, original, segment.text)

    def get_current_text(self) -> str:
        """获取当前文本"""
        return self.window.get_all_text()

    def get_segments(self) -> List[Dict]:
        """获取片段信息"""
        return self.window.get_segments_for_display()


# ========== 测试代码 ==========
async def test_correction():
    """测试修正机制"""
    print("测试修正机制模块...\n")

    manager = CorrectionManager(window_seconds=10)

    # 设置回调
    def on_correction(index, original, corrected):
        print(f"   🔄 修正 [索引 {index}]: '{original}' → '{corrected}'")

    manager.on_correction = on_correction

    # 测试场景 1：bench → bank（有 money 上下文）
    print("1. 测试场景：bench -> bank（上下文包含 money）")
    manager.add_recognition("I went to the bench")
    manager.add_recognition("to deposit money")

    print(f"   原始文本: {manager.get_current_text()}")

    # 修正第一个片段
    first_seg = manager.window.segments[0]
    corrected = manager.corrector.correct(first_seg.text, manager.get_current_text())
    if corrected:
        manager.window.correct_segment(0, corrected, first_seg.text)

    print(f"   修正后文本: {manager.get_current_text()}\n")

    # 重置
    manager = CorrectionManager(window_seconds=10)
    manager.on_correction = on_correction

    # 测试场景 2：to 不应该被错误修正
    print("2. 测试场景：正确文本应该保持不变")
    manager.add_recognition("Hello")
    manager.add_recognition("how are you")

    print(f"   原始文本: {manager.get_current_text()}")

    # 尝试修正所有
    results = await manager.correct_all()
    if results:
        print(f"   ⚠️ 意外的修正: {results}")
    else:
        print(f"   ✅ 无需修正，文本保持不变")

    print(f"   最终文本: {manager.get_current_text()}\n")

    # 测试场景 3：批量修正
    print("3. 显示所有片段详情:")
    for i, seg in enumerate(manager.get_segments()):
        status = "✅已修正" if seg['is_corrected'] else "⏳未修正"
        original = f" (原: {seg['original']})" if seg['original'] else ""
        print(f"   [{i}] {seg['text']} {status}{original}")

    print("\n✅ 修正机制测试完成")


if __name__ == "__main__":
    asyncio.run(test_correction())