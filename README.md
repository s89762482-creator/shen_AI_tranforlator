# AI同声传译助手

## 项目简介
基于AI的同声传译助手，支持中、英、日、德四种语言的实时语音识别与翻译。采用 Vosk 离线语音识别 + DeepSeek/GPT 流式翻译引擎，配合 PySide6 桌面悬浮窗实时显示字幕，实现低延迟的同声传译体验。

## 依赖说明
### 安装依赖
```bash
pip install -r requirements.txt
```

### 核心依赖
| 依赖 | 用途 |
|------|------|
| Flask / Flask-CORS / Flask-SocketIO | 后端 API 服务与 WebSocket 实时推送 |
| PySide6 | 桌面悬浮字幕窗口 |
| sounddevice / numpy | 音频采集与处理 |
| requests / aiohttp | HTTP 请求与流式翻译 |
| python-dotenv | 环境变量管理 |
| edge-tts | TTS 语音合成 |
| streamlit | Web 前端 UI 界面 |

## 原创功能说明
- **多语言实时翻译**：支持中、英、日、德四种语言互相翻译，可同时翻译成多种目标语言
- **离线语音识别**：基于 Vosk 离线模型，无需联网即可完成语音识别，保护隐私
- **流式翻译引擎**：集成 DeepSeek 和 OpenAI 双引擎，支持流式输出，逐字显示翻译结果
- **桌面悬浮字幕窗**：PySide6 无边框毛玻璃窗口，始终置顶，实时显示原文与译文
- **口语纠错修正**：内置口语化英语/中文规范化处理，提升翻译质量
- **上下文感知翻译**：结合上下文语境进行翻译，避免逐句翻译的生硬感
- **TTS 语音合成**：支持将翻译结果通过语音朗读输出

## 运行方式
### 1. 配置环境变量
复制 `.env.example` 为 `.env`，填写 API 密钥：
```bash
cp .env.example .env
```
编辑 `.env` 文件，配置 DeepSeek 或 OpenAI API 密钥，以及源语言和目标语言。

### 2. 启动后端服务
```bash
python backend/app.py
```
后端服务默认运行在 `http://localhost:5000`。

### 3. 启动前端界面
```bash
streamlit run translator.py
```

### 4. 启动悬浮字幕窗口
```bash
python overlay/overlay_app.py
```
悬浮窗会自动读取翻译结果并实时显示原文和译文。

## 项目结构
```
├── backend/               # 后端服务
│   ├── app.py             # Flask 主服务 (API + WebSocket)
│   ├── templates/         # 前端模板
│   └── requirements.txt
├── overlay/               # 桌面悬浮窗
│   ├── overlay_app.py     # PySide6 悬浮字幕窗口
│   └── requirements.txt
├── translator.py          # Streamlit 前端主界面
├── audio_capture.py       # 音频采集模块
├── realtime_asr.py        # 实时语音识别 (Vosk)
├── correction.py          # 口语纠错修正模块
├── tts_engine.py          # TTS 语音合成
├── config.py              # 全局配置管理
├── .env.example           # 环境变量模板
└── requirements.txt       # 项目依赖
```

## Demo视频
- 待补充
https://t.bilibili.com/1211219505244536848?share_source=pc_native