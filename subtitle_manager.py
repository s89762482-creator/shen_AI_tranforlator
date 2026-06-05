"""
字幕管理器 - 独立模块

避免与 UI 模块循环导入
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class SubtitleEntry:
    """单条字幕条目"""
    id: int
    source_text: str  # 原文
    translations: Dict[str, str]  # 翻译结果 {语言代码: 文本}
    timestamp: float  # 时间戳
    is_corrected: bool = False  # 是否被修正过
    original_source: Optional[str] = None
    original_translations: Optional[Dict[str, str]] = None


class SubtitleManager:
    """
    字幕管理器

    管理字幕条目，供 UI 和主程序使用
    """

    def __init__(self):
        self.entries: List[SubtitleEntry] = []
        self._counter = 0
        self.paused = False

    def add_subtitle(
            self,
            source_text: str,
            translations: Dict[str, str]
    ) -> Optional[SubtitleEntry]:
        """
        添加新的字幕条目

        Args:
            source_text: 原文
            translations: 翻译结果字典

        Returns:
            创建的字幕条目
        """
        if self.paused:
            return None

        self._counter += 1
        entry = SubtitleEntry(
            id=self._counter,
            source_text=source_text,
            translations=translations.copy(),
            timestamp=time.time()
        )

        self.entries.append(entry)

        # 限制条目数量（保留最近 100 条）
        if len(self.entries) > 100:
            self.entries.pop(0)

        return entry

    def update_subtitle(
            self,
            entry_id: int,
            new_source: str = None,
            new_translations: Dict[str, str] = None
    ) -> bool:
        """
        更新字幕条目（用于修正）

        Args:
            entry_id: 条目 ID
            new_source: 修正后的原文
            new_translations: 修正后的翻译

        Returns:
            是否更新成功
        """
        for entry in self.entries:
            if entry.id == entry_id:
                if not entry.is_corrected:
                    entry.original_source = entry.source_text
                    entry.original_translations = entry.translations.copy()

                if new_source:
                    entry.source_text = new_source
                if new_translations:
                    entry.translations.update(new_translations)

                entry.is_corrected = True
                return True
        return False

    def clear(self):
        """清空所有字幕"""
        self.entries.clear()
        self._counter = 0

    def toggle_pause(self):
        """切换暂停/恢复"""
        self.paused = not self.paused

    def get_recent_entries(self, count: int = 20) -> List[SubtitleEntry]:
        """获取最近的 N 条字幕"""
        return self.entries[-count:]

    def get_entries(self) -> List[SubtitleEntry]:
        """获取所有字幕"""
        return self.entries