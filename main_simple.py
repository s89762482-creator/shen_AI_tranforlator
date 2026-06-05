"""
AI同声传译助手 - 极简测试版
运行：streamlit run main_simple.py
"""

import time
import streamlit as st

# 页面配置
st.set_page_config(page_title="AI同声传译助手", page_icon="🤖", layout="wide")

# 初始化
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_running" not in st.session_state:
    st.session_state.is_running = False

st.title("🤖 AI同声传译助手 - 测试版")

# 侧边栏控制
with st.sidebar:
    st.title("控制面板")

    if st.button("🚀 启动", key="start"):
        st.session_state.is_running = True
        st.rerun()

    if st.button("🛑 停止", key="stop"):
        st.session_state.is_running = False
        st.rerun()

    if st.button("🗑️ 清空", key="clear"):
        st.session_state.messages = []
        st.rerun()

    if st.button("📝 添加测试", key="test"):
        st.session_state.messages.append({
            "time": time.strftime("%H:%M:%S"),
            "source": "Hello world",
            "zh": "你好，世界"
        })
        st.rerun()

# 显示字幕区域
subtitle_container = st.container()

with subtitle_container:
    if not st.session_state.messages:
        st.info("💡 暂无字幕，点击「添加测试」")
    else:
        for msg in reversed(st.session_state.messages):
            col1, col2 = st.columns([1, 3])
            with col1:
                st.caption(msg["time"])
            with col2:
                st.write(f"**{msg['zh']}**")
                st.caption(msg["source"])
            st.divider()

# 模拟自动生成（如果正在运行）
if st.session_state.is_running:
    placeholder = st.empty()
    placeholder.info("🎙️ 正在监听...")

    # 自动添加模拟消息
    test_phrases = [
        ("Hello world", "你好，世界"),
        ("How are you", "你好吗"),
        ("Nice to meet you", "很高兴认识你"),
        ("What time is it", "几点了"),
        ("Thank you", "谢谢"),
    ]

    current_count = len(st.session_state.messages)
    if current_count < len(test_phrases):
        # 每2秒添加一条
        if "last_add" not in st.session_state:
            st.session_state.last_add = time.time()

        now = time.time()
        if now - st.session_state.last_add > 2:
            st.session_state.last_add = now
            source, zh = test_phrases[current_count]
            st.session_state.messages.append({
                "time": time.strftime("%H:%M:%S"),
                "source": source,
                "zh": zh
            })
            st.rerun()
    else:
        placeholder.success("✅ 测试完成")
        st.session_state.is_running = False