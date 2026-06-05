"""
字幕显示模块 - 双语字幕 UI (Streamlit 版本)

功能：
- 实时显示英文原文和中文翻译
- 支持修正内容更新（标记已修正）
- 支持多种目标语言显示
- 支持暂停/恢复显示

运行方式：streamlit run subtitle_display.py
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import deque

import streamlit as st


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


# 语言配置
LANG_CONFIG = {
    "zh": {"name": "🇨🇳 中文", "color": "#ff6b6b"},
    "en": {"name": "🇬🇧 English", "color": "#4ecdc4"},
    "ja": {"name": "🇯🇵 日本語", "color": "#ffe66d"},
    "de": {"name": "🇩🇪 Deutsch", "color": "#95e77e"},
}


class SubtitleManager:
    """
    字幕管理器（Streamlit 版本）

    使用 st.session_state 存储状态
    """

    def __init__(self):
        """初始化字幕管理器"""
        # 初始化 session state
        if "subtitle_entries" not in st.session_state:
            st.session_state.subtitle_entries = []
        if "subtitle_counter" not in st.session_state:
            st.session_state.subtitle_counter = 0
        if "auto_scroll" not in st.session_state:
            st.session_state.auto_scroll = True
        if "paused" not in st.session_state:
            st.session_state.paused = False
        if "target_languages" not in st.session_state:
            st.session_state.target_languages = ["zh", "en", "ja", "de"]

        self.entries = st.session_state.subtitle_entries
        self.target_languages = st.session_state.target_languages

    def add_subtitle(
            self,
            source_text: str,
            translations: Dict[str, str]
    ) -> SubtitleEntry:
        """
        添加新的字幕条目

        Args:
            source_text: 原文
            translations: 翻译结果字典

        Returns:
            创建的字幕条目
        """
        if st.session_state.paused:
            return None

        st.session_state.subtitle_counter += 1
        entry = SubtitleEntry(
            id=st.session_state.subtitle_counter,
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
        st.session_state.subtitle_counter = 0

    def toggle_pause(self):
        """切换暂停/恢复"""
        st.session_state.paused = not st.session_state.paused

    def set_target_languages(self, languages: List[str]):
        """设置目标语言"""
        st.session_state.target_languages = languages
        self.target_languages = languages

    def get_recent_entries(self, count: int = 20) -> List[SubtitleEntry]:
        """获取最近的 N 条字幕"""
        return self.entries[-count:]


def render_subtitle_ui():
    """
    渲染字幕 UI

    在 Streamlit 应用中调用此函数
    """

    # 初始化管理器
    manager = SubtitleManager()

    # ========== 侧边栏控制面板 ==========
    with st.sidebar:
        st.title("🎛️ 控制面板")

        # 语言选择
        st.subheader("🌐 显示语言")
        selected_langs = []
        for lang_code, config in LANG_CONFIG.items():
            if st.checkbox(config["name"], value=(lang_code in manager.target_languages), key=f"lang_{lang_code}"):
                selected_langs.append(lang_code)

        if selected_langs != manager.target_languages:
            manager.set_target_languages(selected_langs)
            st.rerun()

        st.divider()

        # 控制按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⏸️ 暂停" if not st.session_state.paused else "▶️ 恢复", use_container_width=True):
                manager.toggle_pause()
                st.rerun()

        with col2:
            if st.button("🗑️ 清空", use_container_width=True):
                manager.clear()
                st.rerun()

        # 自动滚动开关
        st.session_state.auto_scroll = st.toggle("📜 自动滚动", value=st.session_state.auto_scroll)

        st.divider()

        # 状态显示
        st.subheader("📊 状态")
        st.info(f"📝 字幕数: {len(manager.entries)}")
        if st.session_state.paused:
            st.warning("⏸️ 已暂停")
        else:
            st.success("🎙️ 监听中...")

    # ========== 主内容区 ==========
    st.title("🤖 AI同声传译助手")
    st.caption("实时字幕 | 支持中、英、日、德四种语言互译")

    # 显示状态栏
    if st.session_state.paused:
        st.warning("⏸️ 字幕显示已暂停，点击「恢复」继续接收")

    # ========== 字幕显示区 ==========
    if not manager.entries:
        st.info("💡 等待识别结果...\n\n说话后字幕将在此处显示")
    else:
        # 创建标签页
        tabs = []
        for lang_code in manager.target_languages:
            if lang_code in LANG_CONFIG:
                tabs.append(LANG_CONFIG[lang_code]["name"])

        if tabs:
            tab_objects = st.tabs(tabs)

            for idx, lang_code in enumerate(manager.target_languages):
                if lang_code not in LANG_CONFIG:
                    continue

                with tab_objects[idx]:
                    config = LANG_CONFIG[lang_code]

                    # 显示最近的字幕
                    recent_entries = manager.get_recent_entries(50)

                    if not recent_entries:
                        st.info("暂无字幕")
                    else:
                        # 从新到旧显示
                        for entry in reversed(recent_entries):
                            translation = entry.translations.get(lang_code, "[翻译中...]")
                            timestamp = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))

                            # 修正标记
                            correction_mark = ""
                            if entry.is_corrected:
                                if entry.original_translations:
                                    original = entry.original_translations.get(lang_code, "")
                                    if original and original != translation:
                                        correction_mark = " ✏️"

                            # 显示字幕卡片
                            with st.container():
                                cols = st.columns([1, 8])
                                with cols[0]:
                                    st.caption(timestamp)
                                with cols[1]:
                                    if entry.is_corrected:
                                        st.markdown(
                                            f"<span style='color: {config['color']}; background-color: #2d2d30; padding: 2px 6px; border-radius: 4px;'>"
                                            f"{translation}{correction_mark}</span>",
                                            unsafe_allow_html=True
                                        )
                                        # 显示原文（可选）
                                        with st.expander(f"📝 原文: {entry.source_text}"):
                                            if entry.original_source:
                                                st.caption(f"修正前: {entry.original_source}")
                                    else:
                                        st.markdown(
                                            f"<span style='color: {config['color']}; font-size: 1rem;'>{translation}</span>",
                                            unsafe_allow_html=True
                                        )
                                st.divider()


# ========== 独立运行测试 ==========
def run_standalone():
    """独立运行测试"""
    st.set_page_config(
        page_title="AI同声传译助手",
        page_icon="🤖",
        layout="wide"
    )

    render_subtitle_ui()

    # 测试数据（仅用于演示）
    manager = SubtitleManager()

    # 如果没有任何字幕，添加测试数据
    if len(manager.entries) == 0:
        # 添加测试字幕
        test_entries = [
            ("Hello world", {"zh": "你好，世界", "en": "Hello world", "ja": "こんにちは世界", "de": "Hallo Welt"}),
            ("How are you", {"zh": "你好吗", "en": "How are you", "ja": "お元気ですか", "de": "Wie geht es dir"}),
            ("I went to the bank",
             {"zh": "我去了银行", "en": "I went to the bank", "ja": "銀行に行きました", "de": "Ich ging zur Bank"}),
        ]

        for source, trans in test_entries:
            manager.add_subtitle(source, trans)

        # 模拟修正
        time.sleep(0.1)
        for entry in manager.entries:
            if "bench" in entry.source_text:
                manager.update_subtitle(
                    entry.id,
                    new_source="I went to the bank",
                    new_translations={"zh": "我去了银行"}
                )


if __name__ == "__main__":
    run_standalone()