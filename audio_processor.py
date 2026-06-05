"""
独立的音频处理进程
运行：python audio_processor.py
"""

import time
import json
import signal
import asyncio
import threading
import numpy as np
import sounddevice as sd
from realtime_asr import create_asr
from translator import TranslationManager
import os

# 临时文件作为通信桥梁
DATA_FILE = "subtitle_data.json"

# 全局变量
asr = None
translator = None
stream = None
running = True
loop = None


def signal_handler(signum, frame):
    """处理 Ctrl+C 信号"""
    global running
    print("\n正在停止音频处理器...")
    running = False


def cleanup():
    """清理资源"""
    global stream, loop
    print("清理资源...")

    if stream:
        try:
            stream.stop()
            stream.close()
        except:
            pass

    if loop and loop.is_running():
        loop.call_soon_threadsafe(loop.stop)

    print("资源清理完成")


async def process_audio(audio_buffer):
    """异步处理音频"""
    global asr, translator

    if not audio_buffer:
        return

    combined = np.concatenate(audio_buffer)

    try:
        # 识别
        text = await asr.recognize_from_audio(combined)

        if text and text.strip():
            print(f"🎤 识别: {text}")

            # 翻译
            results = await translator.translate_and_record(text, "")
            zh_text = results.get("zh", text)

            print(f"📝 翻译: {zh_text}")

            # 写入文件
            data = {
                "time": time.strftime("%H:%M:%S"),
                "source": text,
                "zh": zh_text
            }

            # 确保文件被写入
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

            # 强制刷新文件缓冲区
            f.flush()
            os.fsync(f.fileno())

            print(f"💾 已写入文件: {zh_text}")

    except Exception as e:
        print(f"❌ 处理失败: {e}")


def process_buffer_sync(audio_buffer):
    """同步包装器，在事件循环中运行异步函数"""
    global loop

    if not loop or loop.is_closed():
        print("❌ 事件循环已关闭")
        return

    # 在事件循环中运行异步任务
    asyncio.run_coroutine_threadsafe(
        process_audio(audio_buffer),
        loop
    )


def audio_callback(indata, frames, time_info, status):
    """音频回调"""
    global audio_buffer, last_process_time

    if status:
        pass

    volume = np.abs(indata).mean()

    if volume > 0.01:
        audio_buffer.append(indata.copy())
        last_process_time = time.time()
    elif audio_buffer and time.time() - last_process_time > 1.0:
        # 静音超过1秒，处理缓冲区
        buffer_to_process = audio_buffer.copy()
        audio_buffer = []
        print(f"📦 处理音频缓冲区，长度: {len(buffer_to_process)}")
        process_buffer_sync(buffer_to_process)


def run_event_loop():
    """在独立线程中运行事件循环"""
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("✅ 事件循环线程已启动")
    loop.run_forever()


# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# 初始化模块
print("初始化模块...")
asr = create_asr(use_mock=False)
translator = TranslationManager(use_mock=False)

# 启动独立的事件循环线程
event_thread = threading.Thread(target=run_event_loop, daemon=True)
event_thread.start()

# 等待事件循环启动
time.sleep(0.5)

# 初始化缓冲区
audio_buffer = []
last_process_time = time.time()
sample_rate = 16000

# 启动音频流
print("🎤 音频处理器已启动，等待麦克风输入...")
print(f"📁 数据文件: {os.path.abspath(DATA_FILE)}")

stream = sd.InputStream(
    device=None,
    channels=1,
    samplerate=sample_rate,
    blocksize=1024,
    callback=audio_callback
)
stream.start()

# 保持运行
try:
    while running:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    cleanup()
    print("音频处理器已停止")