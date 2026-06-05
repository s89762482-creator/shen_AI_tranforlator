"""
测试麦克风和语音识别
"""

import speech_recognition as sr


def test_mic():
    r = sr.Recognizer()

    with sr.Microphone() as source:
        print("🎤 请说话...")
        r.adjust_for_ambient_noise(source)
        audio = r.listen(source)

    print("⏳ 识别中...")

    try:
        text = r.recognize_google(audio, language="en-US")
        print(f"✅ 识别结果: {text}")
    except sr.UnknownValueError:
        print("❌ 无法识别")
    except sr.RequestError as e:
        print(f"❌ 服务错误: {e}")


if __name__ == "__main__":
    test_mic()