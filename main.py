"""
AI同声传译助手 - 主程序入口

整合所有模块：
- 音频捕获
- 语音识别（DeepSeek API）
- 识别修正
- 翻译（中英日德互译）
- 字幕显示（Streamlit）
- TTS 语音合成

运行方式：
    streamlit run main.py
"""

import asyncio
import sys
import threading
import time
from typing import Optional, Dict

import streamlit as st
import numpy as np

# 导入各模块
from config import Config
from audio_capture import AudioCapture
from realtime_asr import create_asr
from correction import CorrectionManager
from translator import TranslationManager
from subtitle_manager import SubtitleManager
from subtitle_display import render_subtitle_ui
from tts_engine import create_tts


class RealtimeTranslator:
    """
    实时同声传译主控制器

    协调各模块工作，实现完整的实时翻译流程
    """

    def __init__(self):
        """初始化所有模块"""
        print("🚀 初始化 AI 同声传译助手...")

        # 配置验证
        if not Config.validate():
            print("⚠️ 配置验证失败，将使用模拟模式")

        # 初始化各模块
        self.audio_capture = AudioCapture()
        self.asr = create_asr(use_mock=not Config.DEEPSEEK_API_KEY)
        self.correction_manager = CorrectionManager()
        self.translator = TranslationManager(use_mock=not Config.DEEPSEEK_API_KEY)
        self.tts = create_tts(use_mock=not Config.DEEPSEEK_API_KEY)

        # 字幕管理器（Streamlit 状态）
        self.subtitle_manager = SubtitleManager()

        # 状态变量
        self.is_running = False
        self.is_paused = False
        self.current_audio_queue = asyncio.Queue()
        self._audio_task: Optional[asyncio.Task] = None
        self._process_task: Optional[asyncio.Task] = None

        # 时间戳缓存（用于延迟处理）
        self._last_audio_time = 0
        self._silence_counter = 0

        # 设置回调
        self._setup_callbacks()

        print("✅ 所有模块初始化完成")

    def _setup_callbacks(self):
        """设置各模块的回调函数"""

        # 音频捕获回调
        async def on_audio(audio_data: np.ndarray):
            if not self.is_paused and self.is_running:
                await self.current_audio_queue.put(audio_data)

        self.audio_capture.set_callback(on_audio)

        # 修正回调
        def on_correction(index, original, corrected):
            print(f"🔧 修正 [{index}]: {original} -> {corrected}")
            # 更新字幕中的对应条目
            if index < len(self.subtitle_manager.entries):
                entry = self.subtitle_manager.entries[index]
                self.subtitle_manager.update_subtitle(
                    entry.id,
                    new_source=corrected
                )

        self.correction_manager.on_correction = on_correction

        # 翻译回调
        def on_new_translation(source: str, translations: Dict[str, str]):
            print(f"📝 翻译: {source} -> {translations}")
            # 添加字幕
            entry = self.subtitle_manager.add_subtitle(source, translations)
            # 可选：TTS 朗读中文
            if self.tts.is_enabled() and "zh" in translations:
                asyncio.create_task(self.tts.speak(translations["zh"], lang="zh"))

        self.translator.on_new_translation = on_new_translation

        # 翻译修正回调
        def on_translation_correction(source: str, old: str, new: str):
            print(f"🔄 翻译修正: {old} -> {new}")

        self.translator.on_correction = on_translation_correction

    async def _process_audio(self):
        """处理音频队列（ASR + 修正 + 翻译）"""
        print("🎤 开始处理音频流...")

        # 音频累积缓存（用于静音检测）
        audio_buffer = []
        buffer_duration = 0
        min_duration = 1.0  # 最小处理时长（秒）
        sample_rate = Config.SAMPLE_RATE

        while self.is_running:
            try:
                # 获取音频数据
                audio_data = await asyncio.wait_for(
                    self.current_audio_queue.get(),
                    timeout=0.5
                )

                if audio_data is None:
                    continue

                # 检测是否有声音
                volume = np.abs(audio_data).mean()

                if volume > 0.01:  # 有声音
                    audio_buffer.append(audio_data)
                    buffer_duration += len(audio_data) / sample_rate
                    self._silence_counter = 0

                    # 达到最小时长或缓冲区太大时处理
                    if buffer_duration >= min_duration or len(audio_buffer) >= 10:
                        await self._recognize_buffer(audio_buffer)
                        audio_buffer = []
                        buffer_duration = 0
                else:
                    # 静音，计数
                    self._silence_counter += 1
                    # 如果静音超过 1 秒且缓冲区有内容，处理剩余部分
                    if buffer_duration > 0 and self._silence_counter > sample_rate / Config.CHUNK_SIZE:
                        await self._recognize_buffer(audio_buffer)
                        audio_buffer = []
                        buffer_duration = 0

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"❌ 处理音频失败: {e}")

        print("音频处理已停止")

    async def _recognize_buffer(self, audio_buffer: list):
        """识别音频缓冲区内容"""
        if not audio_buffer:
            return

        try:
            # 合并音频数据
            combined = np.concatenate(audio_buffer)

            # 语音识别
            recognized_text = await self.asr.recognize_from_audio(combined)

            if recognized_text and recognized_text.strip():
                print(f"🎤 识别: {recognized_text}")

                # 添加到修正管理器
                segment = self.correction_manager.add_recognition(recognized_text)

                # 尝试修正
                corrected = await self.correction_manager.correct_last()
                if corrected:
                    recognized_text = corrected

                # 获取上下文用于翻译
                context = self.correction_manager.get_current_text()

                # 翻译
                translations = await self.translator.translate_and_record(
                    recognized_text,
                    context
                )

        except Exception as e:
            print(f"❌ 识别失败: {e}")

    async def start(self):
        """启动实时翻译"""
        print("\n" + "=" * 50)
        print("🎙️ AI 同声传译助手已启动")
        print("=" * 50)
        print("\n控制方式：")
        print("  - 空格键: 暂停/恢复")
        print("  - 在侧边栏选择音频设备")
        print("  - 在侧边栏控制 TTS 开关")
        print("\n开始说话...\n")

        self.is_running = True

        # 显示可用设备
        self.audio_capture.list_devices()

        # 启动音频捕获
        success = await self.audio_capture.start()
        if not success:
            print("❌ 音频捕获启动失败")
            return

        # 启动处理任务
        self._process_task = asyncio.create_task(self._process_audio())

        # 等待停止信号
        try:
            while self.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

        await self.stop()

    async def stop(self):
        """停止实时翻译"""
        print("\n🛑 正在停止...")

        self.is_running = False

        if self._process_task:
            self._process_task.cancel()

        self.audio_capture.stop()

        await self.asr.close()
        await self.translator.close()
        await self.tts.shutdown()

        print("✅ 已停止")

    def toggle_pause(self):
        """切换暂停/恢复"""
        self.is_paused = not self.is_paused
        status = "已暂停" if self.is_paused else "已恢复"
        print(f"⏸️ {status}")


# ========== Streamlit UI 集成 ==========

def init_session_state():
    """初始化 Streamlit session state"""
    if "translator_engine" not in st.session_state:
        st.session_state.translator_engine = None
    if "is_running" not in st.session_state:
        st.session_state.is_running = False
    if "is_paused" not in st.session_state:
        st.session_state.is_paused = False


def render_control_panel():
    """渲染控制面板"""
    st.sidebar.title("🎛️ 控制面板")

    # 启动/停止按钮
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if not st.session_state.is_running:
            if st.button("🚀 启动", type="primary", use_container_width=True):
                st.session_state.is_running = True
                st.rerun()
        else:
            if st.button("🛑 停止", type="secondary", use_container_width=True):
                st.session_state.is_running = False
                st.rerun()

    with col2:
        if st.session_state.is_running:
            pause_label = "▶️ 恢复" if st.session_state.is_paused else "⏸️ 暂停"
            if st.button(pause_label, use_container_width=True):
                st.session_state.is_paused = not st.session_state.is_paused
                if st.session_state.translator_engine:
                    st.session_state.translator_engine.toggle_pause()
                st.rerun()

    st.sidebar.divider()

    # 音频设备选择
    st.sidebar.subheader("🎤 音频设备")
    if st.sidebar.button("🔄 刷新设备列表"):
        if st.session_state.translator_engine:
            st.session_state.translator_engine.audio_capture.list_devices()

    # TTS 开关
    st.sidebar.subheader("🔊 TTS 语音")
    if st.sidebar.toggle("启用 TTS", value=True):
        if st.session_state.translator_engine and st.session_state.translator_engine.tts:
            st.session_state.translator_engine.tts.enable()
    else:
        if st.session_state.translator_engine and st.session_state.translator_engine.tts:
            st.session_state.translator_engine.tts.disable()

    # 状态显示
    st.sidebar.divider()
    st.sidebar.subheader("📊 状态")

    if st.session_state.is_running:
        if st.session_state.is_paused:
            st.sidebar.warning("⏸️ 已暂停")
        else:
            st.sidebar.success("🎙️ 运行中")
    else:
        st.sidebar.info("⏹️ 未启动")


async def run_engine():
    """在后台运行翻译引擎"""
    engine = RealtimeTranslator()
    st.session_state.translator_engine = engine
    await engine.start()


def run_async(coro):
    """在 Streamlit 中运行异步函数"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def main():
    """主函数"""
    st.set_page_config(
        page_title="AI同声传译助手",
        page_icon="🤖",
        layout="wide"
    )

    init_session_state()

    # 标题
    st.title("🤖 AI同声传译助手")
    st.caption("实时语音识别 + AI翻译 + 字幕显示 | 支持中、英、日、德四种语言")

    # 控制面板
    render_control_panel()

    # 字幕显示区域
    render_subtitle_ui()

    # 启动引擎（在单独的线程中运行）
    if st.session_state.is_running:
        if st.session_state.translator_engine is None:
            with st.spinner("正在启动翻译引擎..."):
                # 在新线程中运行异步引擎
                import threading
                thread = threading.Thread(
                    target=run_async,
                    args=(run_engine(),),
                    daemon=True
                )
                thread.start()
                st.success("✅ 引擎已启动，开始说话吧！")
                time.sleep(1)
    else:
        if st.session_state.translator_engine:
            st.session_state.translator_engine = None


if __name__ == "__main__":
    main()