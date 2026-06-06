"""
AI 同声传译助手 - 完整版
Vosk 离线语音识别 + DeepSeek/GPT 流式翻译 + WebSocket 推送 + 悬浮字幕
"""

import os
import json
import io
import tempfile
import subprocess
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ==================== 客户端初始化 ====================

openai_client = None
if os.getenv("OPENAI_API_KEY"):
    try:
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except:
        pass

deepseek_client = None
if os.getenv("DEEPSEEK_API_KEY"):
    try:
        deepseek_client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
    except:
        pass

# Vosk 模型路径
VOSK_MODEL_PATH = r"C:\vosk-model"
if not os.path.exists(VOSK_MODEL_PATH):
    VOSK_MODEL_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'vosk-model-small-en-us-0.15'
    )

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')


# ==================== 语言提示词 ====================

def get_system_prompt(target_lang: str) -> str:
    prompts = {
        "zh": "你是一个专业的同声传译助手。将以下英文实时翻译成中文。要求：口语化、流畅自然、保留专业术语、只输出翻译结果、不要添加任何解释。",
        "en": "You are a professional simultaneous interpreter. Polish and refine the following English text in real-time. Requirements: natural and fluent, preserve technical terms, output only the refined text, no explanations.",
        "ja": "あなたはプロの同時通訳アシスタントです。以下の英語をリアルタイムで日本語に翻訳してください。要件：口語的で自然、専門用語を保持、翻訳結果のみを出力、説明は不要。"
    }
    return prompts.get(target_lang, prompts["zh"])


# ==================== 静态文件托管 ====================

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/caption-overlay.html')
def serve_overlay():
    return send_from_directory(FRONTEND_DIR, 'caption-overlay.html')


@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'js'), filename)


# ==================== RESTful API ====================

@app.route("/api/health", methods=["GET"])
def health_check():
    vosk_ok = os.path.exists(VOSK_MODEL_PATH)
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "openai": openai_client is not None,
            "deepseek": deepseek_client is not None,
            "vosk": vosk_ok
        }
    })


@app.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    """语音识别：Vosk 离线 > Whisper"""
    if "audio" not in request.files:
        return jsonify({"success": False, "error": "缺少音频文件"}), 400

    audio_file = request.files["audio"]
    audio_data = audio_file.read()

    if len(audio_data) == 0:
        return jsonify({"success": False, "error": "音频文件为空"}), 400

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_data)
        audio_path = tmp.name

    try:
        print(f"[Transcribe] 收到音频数据，大小: {len(audio_data)} 字节")
        
        if os.path.exists(VOSK_MODEL_PATH):
            print("[Transcribe] 尝试 Vosk 识别...")
            text = _transcribe_with_vosk(audio_path)
            if text:
                os.unlink(audio_path)
                print(f"[Transcribe] Vosk 识别成功: {text}")
                socketio.emit('recognition', {'text': text, 'engine': 'vosk'})
                return jsonify({
                    "success": True,
                    "data": {"text": text, "engine": "vosk"}
                })
            print("[Transcribe] Vosk 识别结果为空")

        if openai_client:
            print("[Transcribe] 尝试 Whisper 识别...")
            text = _transcribe_with_whisper(audio_path)
            if text:
                os.unlink(audio_path)
                print(f"[Transcribe] Whisper 识别成功: {text}")
                socketio.emit('recognition', {'text': text, 'engine': 'whisper-1'})
                return jsonify({
                    "success": True,
                    "data": {"text": text, "engine": "whisper-1"}
                })
            print("[Transcribe] Whisper 识别结果为空")

        os.unlink(audio_path)
        print("[Transcribe] 所有语音识别方案均失败")
        return jsonify({"success": False, "error": "所有语音识别方案均失败"}), 500

    except Exception as e:
        if os.path.exists(audio_path):
            os.unlink(audio_path)
        return jsonify({"success": False, "error": str(e)}), 500


def _transcribe_with_vosk(audio_path: str) -> str:
    """Vosk 离线识别"""
    try:
        from vosk import Model, KaldiRecognizer
        from pydub import AudioSegment

        audio = AudioSegment.from_file(audio_path)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        wav_buffer.seek(0)
        wav_buffer.read(44)
        pcm_data = wav_buffer.read()

        if len(pcm_data) == 0:
            return ""

        model = Model(VOSK_MODEL_PATH)
        rec = KaldiRecognizer(model, 16000)
        rec.SetWords(False)

        full_text = ""
        chunk_size = 8000
        for i in range(0, len(pcm_data), chunk_size):
            chunk = pcm_data[i:i + chunk_size]
            if rec.AcceptWaveform(chunk):
                result = json.loads(rec.Result())
                if result.get("text"):
                    full_text += result["text"] + " "

        final = json.loads(rec.FinalResult())
        if final.get("text"):
            full_text += final["text"]

        full_text = full_text.strip()
        print(f"[Vosk] 识别: {full_text}")
        return full_text

    except Exception as e:
        print(f"[Vosk] 失败: {e}")
        return ""


def _transcribe_with_whisper(audio_path: str) -> str:
    """Whisper 识别"""
    try:
        with open(audio_path, "rb") as f:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en",
                response_format="text"
            )
        return transcript
    except Exception as e:
        print(f"[Whisper] 失败: {e}")
        return ""


@app.route("/api/translate/stream", methods=["POST"])
def translate_stream():
    """流式翻译（SSE）"""
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"success": False, "error": "缺少翻译文本"}), 400

    text = data["text"].strip()
    target_lang = data.get("target_lang", "zh")
    engine = data.get("engine", "deepseek")

    if not text:
        return jsonify({"success": False, "error": "翻译文本为空"}), 400

    system_prompt = get_system_prompt(target_lang)

    if engine == "openai" and openai_client:
        client, model = openai_client, "gpt-4o"
    elif engine == "deepseek" and deepseek_client:
        client, model = deepseek_client, "deepseek-chat"
    elif openai_client:
        client, model = openai_client, "gpt-4o"
    elif deepseek_client:
        client, model = deepseek_client, "deepseek-chat"
    else:
        return jsonify({"success": False, "error": "未配置翻译服务"}), 503

    def generate():
        full_text = ""
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=500,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_text += token
                    socketio.emit('token', {'token': token})
                    yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            socketio.emit('translation', {
                'original': text,
                'translated': full_text,
                'target_lang': target_lang
            })

            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


# ==================== WebSocket 事件 ====================

@socketio.on('connect')
def handle_connect():
    print('[WebSocket] 客户端已连接')


@socketio.on('disconnect')
def handle_disconnect():
    print('[WebSocket] 客户端已断开')


@socketio.on('captions')
def handle_captions(data):
    try:
        print(f'[WebSocket] 收到字幕消息: {data}')
        # 转发给所有连接的客户端（包括悬浮窗）
        emit('captions', data, broadcast=True)
        print(f'[WebSocket] 已转发字幕消息')
    except Exception as e:
        print(f'[WebSocket] 转发字幕消息失败: {e}')


# ==================== 历史记录 ====================

translation_history = []

@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify({"success": True, "data": translation_history[-50:]})

@app.route("/api/history", methods=["DELETE"])
def clear_history():
    count = len(translation_history)
    translation_history.clear()
    return jsonify({"success": True, "message": f"已清空 {count} 条"})


# ==================== 测试接口 ====================

@app.route("/api/test-captions", methods=["POST"])
def test_captions():
    data = request.get_json()
    if data and 'text' in data:
        text = data['text']
        print(f'[Test] 手动发送字幕: {text}')
        # 在 HTTP 请求上下文中发送消息，需要使用 server.emit
        # 发送完整的消息格式，包含 type 字段
        socketio.server.emit('captions', {'type': 'translation', 'text': text}, namespace='/')
        print(f'[Test] 已发送字幕消息')
        return jsonify({"success": True, "message": f"已发送字幕: {text}"})
    return jsonify({"success": False, "error": "缺少 text 参数"}), 400


# ==================== 悬浮窗控制 ====================

@app.route("/api/overlay/start", methods=["POST"])
def start_overlay():
    overlay_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'overlay', 'overlay_app.py')
    overlay_pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'overlay.pid')
    overlay_lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'overlay', 'overlay.lock')
    
    # 强制删除旧的锁文件（避免之前的进程退出后锁文件残留）
    try:
        if os.path.exists(overlay_lock_file):
            os.remove(overlay_lock_file)
            print("[Backend] 已清理旧的锁文件")
    except Exception as e:
        print(f"[Backend] 删除锁文件失败: {e}")
    
    # 强制删除旧的PID文件
    try:
        if os.path.exists(overlay_pid_file):
            os.remove(overlay_pid_file)
            print("[Backend] 已清理旧的PID文件")
    except Exception as e:
        print(f"[Backend] 删除PID文件失败: {e}")
    
    if os.path.exists(overlay_path):
        try:
            # 修改：移除 CREATE_NO_WINDOW，让悬浮窗的输出可见
            proc = subprocess.Popen(['python', overlay_path], 
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True)
            
            # 读取悬浮窗的输出（非阻塞方式）
            def read_overlay_output():
                while True:
                    line = proc.stdout.readline()
                    if line:
                        print(f"[Overlay] {line}", end='')
                    else:
                        break
            
            # 在后台线程中读取输出
            import threading
            threading.Thread(target=read_overlay_output, daemon=True).start()
            
            with open(overlay_pid_file, 'w') as f:
                f.write(str(proc.pid))
            print(f"[Backend] 悬浮窗进程已启动，PID: {proc.pid}")
            return jsonify({"success": True, "message": "悬浮窗已启动", "pid": proc.pid})
        except Exception as e:
            print(f"[Backend] 启动悬浮窗失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": False, "error": "悬浮窗程序不存在"}), 404


@app.route("/api/overlay/stop", methods=["POST"])
def stop_overlay():
    overlay_pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'overlay.pid')
    overlay_lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'overlay', 'overlay.lock')
    
    success = False
    message = "悬浮窗未运行"
    
    if os.path.exists(overlay_pid_file):
        try:
            with open(overlay_pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            if os.name == 'nt':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle != 0:
                    # 发送关闭消息
                    try:
                        socketio.emit('close_overlay', {})
                    except:
                        pass
                    # 强制终止进程
                    kernel32.TerminateProcess(handle, 0)
                    kernel32.CloseHandle(handle)
                    success = True
                    message = "悬浮窗已关闭"
            
            os.remove(overlay_pid_file)
            print(f"[Backend] 悬浮窗进程已终止，PID: {pid}")
            
        except Exception as e:
            print(f"[Backend] 终止悬浮窗进程失败: {e}")
            try:
                os.remove(overlay_pid_file)
            except:
                pass
    
    if os.path.exists(overlay_lock_file):
        try:
            os.remove(overlay_lock_file)
        except:
            pass
    
    return jsonify({"success": success, "message": message})


# ==================== 启动 ====================

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = False
    use_reloader = False

    if os.path.exists(VOSK_MODEL_PATH):
        print("[OK] Vosk 模型已就绪:", VOSK_MODEL_PATH)
    else:
        print("[WARN] Vosk 模型未找到:", VOSK_MODEL_PATH)

    print("[RUN] 服务启动: http://localhost:", port)
    print(f"[RUN] Debug模式: {debug}, 热重载: {use_reloader}")
    
    # 打印所有已注册的路由
    print("[RUN] 已注册的路由:")
    for rule in app.url_map.iter_rules():
        methods = [m for m in rule.methods if m not in ['OPTIONS', 'HEAD']]
        print(f"  - {rule.rule} ({', '.join(methods)})")
    
    try:
        socketio.run(app, host="0.0.0.0", port=port, debug=debug, use_reloader=use_reloader)
    except KeyboardInterrupt:
        print("[INFO] 服务已停止")
    except Exception as e:
        print(f"[ERROR] 服务启动失败: {e}")
        import traceback
        traceback.print_exc()