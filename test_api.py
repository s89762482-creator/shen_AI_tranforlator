from config import Config
from realtime_asr import DeepSeekASR
import numpy as np
import asyncio


async def test():
    Config.validate()
    asr = DeepSeekASR()

    # 模拟音频数据（静音测试）
    test_audio = np.zeros((16000, 1), dtype=np.float32)

    result = await asr.recognize_from_audio(test_audio, 16000)
    print(f"API 测试结果: {result}")

    await asr.close()


asyncio.run(test())