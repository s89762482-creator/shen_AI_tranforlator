"""
AI同声传译助手 - 真实版（修正版）
运行：streamlit run main_real.py
"""

import time
import streamlit as st
import numpy as np

# 音频模块使用同步方式
import sounddevice as sd
from realtime_asr import create_asr
from translator import TranslationManager

# 页面配置
st.set_page_config(page_title="AI同声传译助手", page_icon="🤖", layout="wide")

# --- 初始化 Session State (重要！) ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "audio_buffer" not in st.session_state:
    st.session_state.audio_buffer = []
if "last_process_time" not in st.session_state:
    st.session_state.last_process_time = time.time()
if "asr" not in st.session_state:
    # 使用模拟模式测试（无需 API Key）
    st.session_state.asr = create_asr(use_mock=True)
    st.session_state.translator = TranslationManager(use_mock=True)

# --- 音频回调函数（同步，在 Streamlit 主线程外运行）---
def audio_callback(indata, frames, time_info, status):
    """音频回调，将数据放入 Session State 的缓冲区"""
    if status:
        print(f"音频状态: {status}")
    # 将音频数据添加到全局缓冲区
    if st.session_state.is_running:
        st.session_state.audio_buffer.append(indata.copy())

# --- UI 组件 ---
st.title("🤖 AI同声传译助手")
st.caption("实时语音识别 + AI翻译 | 中、英、日、德四种语言 (模拟模式)")

# 侧边栏控制
with st.sidebar:
    st.title("控制面板")

    if not st.session_state.is_running:
        if st.button("🚀 启动", key="start", use_container_width=True):
            # 初始化音频流
            st.session_state.stream = sd.InputStream(
                device=None,  # 默认麦克风
                channels=1,
                samplerate=16000,
                blocksize=1024,
                callback=audio_callback
            )
            st.session_state.stream.start()
            st.session_state.is_running = True
            st.session_state.audio_buffer = []  # 清空旧缓冲区
            st.session_state.last_process_time = time.time()
            st.rerun()
    else:
        if st.button("🛑 停止", key="stop", use_container_width=True):
            if hasattr(st.session_state, 'stream'):
                st.session_state.stream.stop()
                st.session_state.stream.close()
            st.session_state.is_running = False
            st.rerun()

    if st.button("🗑️ 清空字幕", key="clear", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption(f"📊 字幕数量: {len(st.session_state.messages)}")

# --- 音频处理逻辑（在主循环中，每次 rerun 都会执行）---
if st.session_state.is_running:
    # 检查缓冲区是否有数据，并处理
    buffer = st.session_state.audio_buffer
    if buffer:
        # 合并缓冲区数据
        combined = np.concatenate(buffer)
        st.session_state.audio_buffer = []  # 清空缓冲区

        # 检查音量，判断是否有声音
        volume = np.abs(combined).mean()
        if volume > 0.01:
            # 调用 ASR 和翻译
            # 注意：这里需要同步调用异步函数，可以用 asyncio 或直接使用同步方法
            try:
                # 使用同步方式调用（简化）
                # 实际项目中，create_asr 返回的可能是一个同步类
                recognized_text = "Hello world"  # 临时模拟

                if recognized_text and recognized_text.strip():
                    # 模拟翻译
                    zh_text = "你好，世界"  # 临时模拟
                    # 添加字幕
                    st.session_state.messages.append({
                        "time": time.strftime("%H:%M:%S"),
                        "source": recognized_text,
                        "zh": zh_text
                    })
                    st.rerun()  # 强制刷新页面
            except Exception as e:
                st.error(f"处理出错: {e}")

    # 显示状态提示
    st.info("🎙️ 正在监听... 请对着麦克风说话")
else:
    if st.session_state.messages:
        st.success("✅ 已停止监听")
    else:
        st.info("💡 点击「启动」开始同声传译，对着麦克风说话")

# 显示字幕
if st.session_state.messages:
    for msg in reversed(st.session_state.messages):
        col1, col2 = st.columns([1, 3])
        with col1:
            st.caption(msg["time"])
        with col2:
            st.write(f"**{msg['zh']}**")
            st.caption(msg["source"])
        st.divider()