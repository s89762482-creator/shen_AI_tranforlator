"""
音频捕获模块 - 麦克风/系统音频输入

支持：
- 麦克风音频流捕获
- 系统音频（扬声器）捕获（需要立体声混音驱动）
- 设备列表获取
- 异步音频回调
"""

import asyncio
import threading
from typing import Optional, Callable, List, Dict

import sounddevice as sd
import numpy as np

from config import Config


class AudioCapture:
    """音频捕获类，管理麦克风或系统音频输入"""

    def __init__(self):
        self._stream: Optional[sd.InputStream] = None
        self._callback: Optional[Callable] = None
        self._is_running = False
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._device_id: int = Config.AUDIO_DEVICE_INDEX

    def get_devices(self) -> List[Dict]:
        """
        获取所有可用的音频输入设备

        Returns:
            设备信息列表，每个设备包含 id, name, channels, samplerate
        """
        devices = []
        try:
            all_devices = sd.query_devices()
            for i, device in enumerate(all_devices):
                # 只列出有输入通道的设备
                if device['max_input_channels'] > 0:
                    devices.append({
                        'id': i,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'samplerate': int(device['default_samplerate']),
                        'is_default': (i == sd.default.device[0])
                    })
        except Exception as e:
            print(f"获取设备列表失败: {e}")
        return devices

    def list_devices(self) -> None:
        """打印所有可用设备"""
        devices = self.get_devices()
        print("\n========== 可用的音频输入设备 ==========")
        for device in devices:
            default_mark = " [默认]" if device['is_default'] else ""
            print(f"  [{device['id']}] {device['name']}{default_mark}")
            print(f"       通道: {device['channels']}, 采样率: {device['samplerate']} Hz")
        print("========================================\n")

    def set_device(self, device_id: int) -> bool:
        """
        设置音频输入设备

        Args:
            device_id: 设备索引，-1 表示默认设备

        Returns:
            是否设置成功
        """
        if device_id == -1:
            self._device_id = None
            print("已切换到默认音频设备")
            return True

        devices = self.get_devices()
        device_ids = [d['id'] for d in devices]

        if device_id in device_ids:
            self._device_id = device_id
            print(f"已切换到设备: {self._get_device_name(device_id)}")
            return True
        else:
            print(f"设备 {device_id} 不存在，使用当前设备")
            return False

    def _get_device_name(self, device_id) -> str:
        """获取设备名称"""
        if device_id is None:
            return "默认设备"
        try:
            device = sd.query_devices(device_id)
            return device['name']
        except:
            return f"设备 {device_id}"

    def _audio_callback(self, indata: np.ndarray, frames: int,
                        time_info: dict, status: Callable) -> None:
        """
        sounddevice 的回调函数，当有新的音频数据时被调用

        Args:
            indata: 音频数据数组
            frames: 帧数
            time_info: 时间信息
            status: 状态回调
        """
        if status:
            print(f"音频状态: {status}")

        if self._callback:
            # 同步回调，在异步环境中需要转发到事件循环
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._callback(indata.copy()),
                    self._loop
                )

    def set_callback(self, callback: Callable) -> None:
        """
        设置音频数据回调函数

        Args:
            callback: 异步回调函数，接收音频数据 numpy array
        """
        self._callback = callback

    async def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> bool:
        """
        开始捕获音频

        Args:
            loop: asyncio 事件循环，用于回调

        Returns:
            是否启动成功
        """
        if self._is_running:
            print("音频捕获已在运行中")
            return True

        self._loop = loop or asyncio.get_event_loop()

        try:
            # 配置音频流参数
            device = self._device_id if self._device_id != -1 else None
            samplerate = Config.SAMPLE_RATE
            blocksize = Config.CHUNK_SIZE

            # 创建输入流
            self._stream = sd.InputStream(
                device=device,
                channels=1,  # 单声道
                samplerate=samplerate,
                blocksize=blocksize,
                callback=self._audio_callback,
                dtype='float32'
            )

            self._stream.start()
            self._is_running = True

            device_name = self._get_device_name(device)
            print(f"✅ 音频捕获已启动: {device_name}")
            print(f"   采样率: {samplerate} Hz, 块大小: {blocksize}")
            return True

        except Exception as e:
            print(f"❌ 启动音频捕获失败: {e}")
            return False

    def stop(self) -> None:
        """停止音频捕获"""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self._is_running = False
        print("音频捕获已停止")

    def is_running(self) -> bool:
        """检查是否正在捕获"""
        return self._is_running

    async def get_audio_chunk(self) -> Optional[np.ndarray]:
        """
        异步获取一个音频块

        Returns:
            音频数据数组，如果没有数据则返回 None
        """
        try:
            return await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None


# 用于快速测试
async def test_audio():
    """测试音频捕获功能"""
    print("测试音频捕获模块...")

    capture = AudioCapture()
    capture.set_device(1)

    # 列出可用设备
    capture.list_devices()

    # 设置回调函数
    async def test_callback(data):
        print(f"收到音频数据: {data.shape}, 范围: [{data.min():.3f}, {data.max():.3f}]")
    capture.set_callback(test_callback)

    # 启动捕获
    success = await capture.start()
    if not success:
        print("启动失败")
        return

    # 运行 5 秒
    print("录音中... 5秒后停止")
    await asyncio.sleep(5)

    # 停止
    capture.stop()
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(test_audio())