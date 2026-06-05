"""
AI同声传译助手 - 最终版
运行：streamlit run main_final.py
"""

import time
import json
import os
import streamlit as st

DATA_FILE = "subtitle_data.json"

# 页面配置
st.set_page_config(page_title="AI同声传译助手", page_icon="🤖", layout="wide")

# 初始化 session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "last_check" not in st.session_state:
    st.session_state.last_check = 0


def check_new_subtitle():
    """检查是否有新字幕"""
    if not os.path.exists(DATA_FILE):
        return None

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 读取成功后删除文件，避免重复读取
        os.remove(DATA_FILE)

        # 验证数据完整性
        if data and "source" in data and "zh" in data:
            return data
        return None
    except Exception as e:
        print(f"读取文件错误: {e}")
        return None


# UI 标题
st.title("🤖 AI同声传译助手")
st.caption("实时语音识别 + AI翻译 | 支持中、英、日、德四种语言")

# 侧边栏控制
with st.sidebar:
    st.title("控制面板")

    if not st.session_state.is_running:
        if st.button("🚀 启动监听", key="start", use_container_width=True):
            st.session_state.is_running = True
            st.session_state.messages = []  # 清空旧消息
            st.rerun()
    else:
        if st.button("🛑 停止监听", key="stop", use_container_width=True):
            st.session_state.is_running = False
            st.rerun()

    if st.button("🗑️ 清空字幕", key="clear", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption(f"📊 字幕数量: {len(st.session_state.messages)}")

    if st.session_state.is_running:
        st.success("🎙️ 正在监听...")
        st.info("💡 请对着麦克风说英文")
    else:
        st.info("⏹️ 未启动，点击「启动监听」开始")

# 自动刷新检查新字幕
if st.session_state.is_running:
    # 每秒检查一次新字幕
    current_time = time.time()
    if current_time - st.session_state.last_check > 0.5:
        st.session_state.last_check = current_time
        new_subtitle = check_new_subtitle()
        if new_subtitle:
            st.session_state.messages.append(new_subtitle)
            st.rerun()

# 显示字幕
if not st.session_state.messages:
    if st.session_state.is_running:
        st.info("🎤 正在等待语音输入...")
    else:
        st.info("💡 点击「启动监听」开始同声传译")
else:
    # 从新到旧显示
    for msg in reversed(st.session_state.messages):
        col1, col2 = st.columns([1, 3])
        with col1:
            st.caption(msg["time"])
        with col2:
            st.write(f"**{msg['zh']}**")
            st.caption(f"📝 {msg['source']}")
        st.divider()

# 自动刷新页面
if st.session_state.is_running:
    time.sleep(0.5)
    st.rerun()