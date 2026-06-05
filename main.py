# main.py - 模拟测试版 (用于验证字幕自动生成)

import time
import streamlit as st
from subtitle_manager import SubtitleManager

# --- 页面配置 ---
st.set_page_config(page_title="AI同声传译助手", page_icon="🤖", layout="wide")

# --- 初始化 ---
if "subtitle_manager" not in st.session_state:
    st.session_state.subtitle_manager = SubtitleManager()
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "last_sim_time" not in st.session_state:
    st.session_state.last_sim_time = 0

# --- UI 组件 (保持不变) ---
def render_sidebar():
    with st.sidebar:
        st.title("🎛️ 控制面板")
        if st.session_state.is_running:
            st.success("🎙️ 模拟运行中")
            if st.button("🛑 停止模拟", key="stop_btn", use_container_width=True):
                st.session_state.is_running = False
                st.rerun()
        else:
            st.info("⏹️ 未启动")
            if st.button("🚀 启动模拟", key="start_btn", use_container_width=True):
                st.session_state.is_running = True
                st.session_state.last_sim_time = time.time()
                st.rerun()

        if st.button("🗑️ 清空字幕", key="clear_btn", use_container_width=True):
            st.session_state.subtitle_manager.clear()
            st.rerun()
        st.caption(f"📊 字幕数量: {len(st.session_state.subtitle_manager.entries)}")

def render_subtitle_display():
    st.title("🤖 AI同声传译助手")
    st.caption("模拟模式 | 中、英、日、德")
    manager = st.session_state.subtitle_manager
    entries = manager.get_recent_entries(50)
    if not entries:
        st.info("💡 暂无字幕，点击「启动模拟」开始生成测试字幕")
        return
    tabs = st.tabs(["🇨🇳 中文", "🇬🇧 English", "🇯🇵 日本語", "🇩🇪 Deutsch"])
    lang_codes = ["zh", "en", "ja", "de"]
    for tab, lang_code in zip(tabs, lang_codes):
        with tab:
            for entry in reversed(entries):
                translation = entry.translations.get(lang_code, "")
                if not translation:
                    continue
                timestamp = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
                with st.container():
                    c1, c2 = st.columns([1, 5])
                    with c1:
                        st.caption(timestamp)
                    with c2:
                        if entry.is_corrected:
                            st.markdown(f"**{translation}** ✏️")
                        else:
                            st.write(translation)
                    st.divider()

# --- 主程序：模拟实时数据 ---
def main():
    render_sidebar()
    render_subtitle_display()

    if st.session_state.is_running:
        # 模拟每3秒生成一条新字幕
        now = time.time()
        if now - st.session_state.last_sim_time > 3:
            st.session_state.last_sim_time = now
            manager = st.session_state.subtitle_manager

            # 模拟一条从“识别 -> 修正 -> 翻译”生成的字幕
            mock_sentences = [
                ("Hello world", {"zh": "你好，世界", "en": "Hello world", "ja": "こんにちは", "de": "Hallo Welt"}),
                ("How are you", {"zh": "你好吗", "en": "How are you", "ja": "お元気ですか", "de": "Wie geht es dir"}),
                ("I went to the bank", {"zh": "我去了银行", "en": "I went to the bank", "ja": "銀行に行きました", "de": "Ich ging zur Bank"}),
                ("What time is it", {"zh": "几点了", "en": "What time is it", "ja": "今何時ですか", "de": "Wie spät ist es"}),
            ]
            # 按顺序循环添加模拟字幕
            idx = len(manager.entries) % len(mock_sentences)
            source, trans = mock_sentences[idx]
            manager.add_subtitle(source, trans)
            st.rerun()  # 强制刷新页面以显示新字幕

if __name__ == "__main__":
    main()