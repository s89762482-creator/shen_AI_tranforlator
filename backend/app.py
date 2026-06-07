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

# 导入修正模块
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from correction import CorrectionManager, SpokenEnglishNormalizer

load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 修正管理器 - 维护最近15秒的识别文本，用于上下文修正
correction_manager = CorrectionManager(window_seconds=15)


# 上下文管理器 - 维护最近的对话历史，用于翻译上下文
class TranslationContextManager:
    """翻译上下文管理器，维护最近的对话历史"""
    
    def __init__(self, max_history=5):
        self.max_history = max_history
        self.history = []  # [(original_text, translated_text), ...]
        
    def add(self, original_text, translated_text):
        """添加翻译结果到历史"""
        if original_text and translated_text:
            self.history.append((original_text, translated_text))
            # 保持历史长度限制
            if len(self.history) > self.max_history:
                self.history.pop(0)
    
    def get_context_prompt(self):
        """获取上下文提示"""
        if not self.history:
            return ""
        
        context_parts = []
        for orig, trans in self.history:
            context_parts.append(f"原文: {orig}")
            context_parts.append(f"译文: {trans}")
        
        context_text = "\n".join(context_parts)
        return f"""
--- 上下文 ---
{context_text}
--- 当前翻译 ---
"""
    
    def clear(self):
        """清空上下文"""
        self.history = []


# 初始化上下文管理器（保留最近5条对话）
translation_context = TranslationContextManager(max_history=5)

def on_correction(index, original, corrected):
    """修正回调 - 推送修正信息到客户端"""
    print(f"[Correction] 自动修正: '{original}' -> '{corrected}'")
    socketio.emit('correction', {
        'index': index,
        'original': original,
        'corrected': corrected,
        'timestamp': datetime.now().isoformat()
    })

correction_manager.on_correction = on_correction

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
        "zh": """你是一个专业的同声传译助手，擅长将英文翻译成地道、自然的中文口语。

翻译要求：
1. 结合上下文进行翻译，保证语义连贯和自然
2. 使用日常口语表达，就像朋友之间聊天一样自然
3. 避免直译和书面语，要符合中文表达习惯
4. 可以适当使用语气词（啊、哦、啦、呢、吧、呗）
5. 短句优先，每句话不要太长
6. 保留原意，但不必逐字翻译，意译为主
7. 遇到俚语或习语，翻译成对应的中文俗语
8. 如果上下文有相关对话，请参考上下文进行更准确的翻译

示例对照：
- "I'm going to grab a bite to eat" -> "我去吃点东西"
- "That's a great idea" -> "这主意真不错"
- "Let's call it a day" -> "今天就到这里吧"
- "I'm kidding" -> "开玩笑啦"
- "No worries" -> "没事儿"
- "Long time no see" -> "好久不见啊"

只输出翻译结果，不要添加任何解释。""",
        "en": "You are a professional simultaneous interpreter. Polish and refine the following English text to be more natural and conversational. Consider the provided context for better accuracy. Output only the refined text, no explanations.",
        "ja": "あなたはプロの同時通訳アシスタントです。以下の英語を自然で会話的な日本語に翻訳してください。提供された文脈を参考にしてより正確な翻訳を行ってください。説明は不要で、翻訳結果のみを出力してください。"
    }
    return prompts.get(target_lang, prompts["zh"])


def has_complete_svo(text: str) -> bool:
    """
    检测句子是否具有完整的主谓宾结构
    
    Args:
        text: 识别出的文本
        
    Returns:
        True: 具有完整主谓宾结构
        False: 缺少主语、谓语或宾语
    """
    if not text or not text.strip():
        return False
    
    text = text.strip().lower()
    words = text.split()
    
    # 主语列表
    subjects = {
        # 代词主语
        'i', 'you', 'he', 'she', 'it', 'we', 'they',
        'me', 'him', 'her', 'us', 'them',
        'this', 'that', 'these', 'those',
        'something', 'anything', 'everything', 'nothing',
        'someone', 'anyone', 'everyone', 'no one',
        'nobody', 'anybody', 'everybody', 'somebody',
        # 常见名词主语（语音识别常见）
        'i', 'you', 'we', 'they', 'people', 'person', 'man', 'woman', 'child',
        'company', 'team', 'group', 'organization', 'government',
        'time', 'day', 'week', 'month', 'year',
        'money', 'work', 'job', 'life', 'world',
        'way', 'thing', 'problem', 'solution', 'idea',
        'system', 'process', 'method', 'approach', 'plan',
        # 地点
        'home', 'office', 'school', 'store', 'market', 'restaurant', 'hotel',
        # 动作相关
        'meeting', 'call', 'email', 'message', 'report', 'document', 'file',
    }
    
    # 谓语动词列表（常见动作动词）
    verbs = {
        # 基本动作
        'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had',
        'do', 'does', 'did',
        'go', 'goes', 'went', 'going',
        'get', 'gets', 'got', 'getting',
        'make', 'makes', 'made',
        'take', 'takes', 'took',
        'give', 'gives', 'gave',
        'say', 'says', 'said',
        'see', 'sees', 'saw', 'seen',
        'know', 'knows', 'knew', 'known',
        'think', 'thinks', 'thought',
        'want', 'wants', 'wanted',
        'need', 'needs', 'needed',
        'like', 'likes', 'liked',
        'love', 'loves', 'loved',
        'hate', 'hates', 'hated',
        'feel', 'feels', 'felt',
        'look', 'looks', 'looked',
        'hear', 'hears', 'heard',
        'read', 'reads', 'read',
        'write', 'writes', 'wrote', 'written',
        'speak', 'speaks', 'spoke', 'spoken',
        'talk', 'talks', 'talked',
        'tell', 'tells', 'told',
        'ask', 'asks', 'asked',
        'answer', 'answers', 'answered',
        'work', 'works', 'worked',
        'study', 'studies', 'studied',
        'learn', 'learns', 'learned',
        'teach', 'teaches', 'taught',
        'help', 'helps', 'helped',
        'show', 'shows', 'showed', 'shown',
        'find', 'finds', 'found',
        'lose', 'loses', 'lost',
        'buy', 'buys', 'bought',
        'sell', 'sells', 'sold',
        'start', 'starts', 'started',
        'stop', 'stops', 'stopped',
        'begin', 'begins', 'began', 'begun',
        'end', 'ends', 'ended',
        'use', 'uses', 'used',
        'create', 'creates', 'created',
        'build', 'builds', 'built',
        'run', 'runs', 'ran', 'running',
        'walk', 'walks', 'walked',
        'drive', 'drives', 'drove', 'driven',
        'fly', 'flies', 'flew', 'flown',
        'eat', 'eats', 'ate', 'eaten',
        'drink', 'drinks', 'drank', 'drunk',
        'sleep', 'sleeps', 'slept',
        'wake', 'wakes', 'woke', 'woken',
        'come', 'comes', 'came', 'come',
        'leave', 'leaves', 'left',
        'arrive', 'arrives', 'arrived',
        'return', 'returns', 'returned',
        'change', 'changes', 'changed',
        'keep', 'keeps', 'kept',
        'put', 'puts', 'put',
        'set', 'sets', 'set',
        'get', 'gets', 'got', 'getting',
        'turn', 'turns', 'turned',
        'move', 'moves', 'moved',
        'stay', 'stays', 'stayed',
        'live', 'lives', 'lived',
        'believe', 'believes', 'believed',
        'remember', 'remembers', 'remembered',
        'forget', 'forgets', 'forgot', 'forgotten',
        'understand', 'understands', 'understood',
        'explain', 'explains', 'explained',
        'discuss', 'discusses', 'discussed',
        'decide', 'decides', 'decided',
        'agree', 'agrees', 'agreed',
        'disagree', 'disagrees', 'disagreed',
        'try', 'tries', 'tried',
        'hope', 'hopes', 'hoped',
        'expect', 'expects', 'expected',
        'plan', 'plans', 'planned',
        'promise', 'promises', 'promised',
        'offer', 'offers', 'offered',
        'accept', 'accepts', 'accepted',
        'refuse', 'refuses', 'refused',
        'allow', 'allows', 'allowed',
        'deny', 'denies', 'denied',
        'need', 'needs', 'needed',
        'must', 'should', 'would', 'could', 'may', 'might', 'can', 'will', 'shall',
    }
    
    # 宾语名词列表
    objects = {
        # 代词宾语
        'me', 'him', 'her', 'us', 'them', 'it',
        # 常见名词（与主语类似，但更侧重于作为宾语）
        'money', 'time', 'work', 'job', 'life', 'world',
        'thing', 'problem', 'solution', 'idea', 'plan',
        'information', 'data', 'report', 'document', 'file',
        'email', 'message', 'call', 'meeting',
        'home', 'office', 'school', 'store',
        'food', 'water', 'drink', 'meal',
        'book', 'paper', 'pen', 'computer', 'phone',
        'help', 'advice', 'support',
        'question', 'answer', 'reply',
        'decision', 'choice', 'option',
        'opportunity', 'chance', 'risk',
        'result', 'effect', 'impact',
        'change', 'difference', 'improvement',
        'service', 'product', 'quality',
        'price', 'cost', 'value',
        'customer', 'client', 'user',
        'team', 'group', 'company',
        'system', 'process', 'method',
        'way', 'path', 'direction',
        'reason', 'cause', 'purpose',
        'goal', 'target', 'objective',
    }
    
    # 检测是否有主语
    has_subject = False
    subject_pos = -1
    for i, word in enumerate(words):
        word_clean = word.rstrip('.,;:!?"\'-')
        if word_clean in subjects:
            has_subject = True
            subject_pos = i
            break
    
    # 检测是否有谓语动词（在主语之后）
    has_verb = False
    verb_pos = -1
    if has_subject:
        for i in range(subject_pos + 1, len(words)):
            word_clean = words[i].rstrip('.,;:!?"\'-')
            if word_clean in verbs:
                has_verb = True
                verb_pos = i
                break
    
    # 检测是否有宾语（在谓语之后）
    has_object = False
    if has_verb:
        for i in range(verb_pos + 1, len(words)):
            word_clean = words[i].rstrip('.,;:!?"\'-')
            if word_clean in objects:
                has_object = True
                break
    
    # 特殊情况：动词后直接跟介词短语也算完整（如 "I go to school"）
    if has_verb and not has_object:
        prepositions = {'to', 'for', 'with', 'at', 'in', 'on', 'from', 'by', 'about', 'into'}
        for i in range(verb_pos + 1, len(words)):
            word_clean = words[i].rstrip('.,;:!?"\'-')
            if word_clean in prepositions:
                # 如果介词后面还有名词，也算完整
                if i + 1 < len(words):
                    has_object = True
                    break
    
    # 特殊情况：系动词后接形容词也算完整（如 "I am happy"）
    if has_verb and not has_object:
        adjectives = {
            'happy', 'sad', 'angry', 'tired', 'hungry', 'thirsty',
            'good', 'bad', 'great', 'nice', 'beautiful', 'ugly',
            'big', 'small', 'large', 'little', 'long', 'short',
            'fast', 'slow', 'quick', 'slowly',
            'new', 'old', 'young', 'old',
            'hot', 'cold', 'warm', 'cool',
            'easy', 'hard', 'difficult', 'simple',
            'important', 'necessary', 'possible', 'impossible',
            'ready', 'busy', 'free', 'available',
            'late', 'early', 'on time',
            'right', 'wrong', 'correct', 'true', 'false',
        }
        for i in range(verb_pos + 1, len(words)):
            word_clean = words[i].rstrip('.,;:!?"\'-')
            if word_clean in adjectives:
                has_object = True
                break
    
    result = has_subject and has_verb and has_object
    print(f"[SVO Check] 主语:{has_subject} 谓语:{has_verb} 宾语:{has_object} | 完整:{result} | {text}")
    return result


def is_sentence_complete(text: str) -> bool:
    """
    智能判断句子是否完整（结合主谓宾检测）
    
    Args:
        text: 识别出的文本
        
    Returns:
        True: 句子完整，可以翻译
        False: 句子不完整，需要继续等待
    """
    if not text or not text.strip():
        return False
    
    original_text = text
    text = text.strip()
    
    # 连接词列表（这些词后面不应该断句）
    connecting_words = {
        # 并列连词
        'and': 'and',
        'but': 'but', 
        'or': 'or',
        'nor': 'nor',
        'so': 'so',
        'yet': 'yet',
        'for': 'for',
        
        # 介词（常见于句子中间）
        'with': 'with',
        'without': 'without',
        'by': 'by',
        'from': 'from',
        'to': 'to',
        'into': 'into',
        'onto': 'onto',
        'upon': 'upon',
        'over': 'over',
        'under': 'under',
        'through': 'through',
        'during': 'during',
        'before': 'before',
        'after': 'after',
        'since': 'since',
        'until': 'until',
        
        # 从属连词
        'because': 'because',
        'although': 'although',
        'though': 'though',
        'while': 'while',
        'whereas': 'whereas',
        'if': 'if',
        'unless': 'unless',
        'when': 'when',
        'whenever': 'whenever',
        'where': 'where',
        'wherever': 'wherever',
        'whether': 'whether',
        
        # 关系词
        'that': 'that',
        'which': 'which',
        'who': 'who',
        'whom': 'whom',
        'whose': 'whose',
        'what': 'what',
        'how': 'how',
        'why': 'why',
        
        # 其他常用词
        'as': 'as',
        'like': 'like',
        'than': 'than',
        'rather': 'rather',
        'also': 'also',
        'then': 'then',
        'thus': 'thus',
        'therefore': 'therefore',
        'however': 'however',
        'moreover': 'moreover',
        'furthermore': 'furthermore',
        'besides': 'besides',
        'except': 'except',
        'including': 'including',
        'regarding': 'regarding',
        'concerning': 'concerning',
        
        # 口语常用
        'you know': 'you know',
        'i mean': 'i mean',
        'let me': 'let me',
        'i think': 'i think',
        'i guess': 'i guess',
        'sort of': 'sort of',
        'kind of': 'kind of',
    }
    
    # 检查是否以连接词结尾
    words = text.split()
    if words:
        last_word = words[-1].lower().strip()
        # 去除可能的标点后检查
        last_word_clean = last_word.rstrip('.,;:!?"\'-')
        
        # 检查最后一个单词
        if last_word_clean in connecting_words:
            print(f"[SentenceCheck] ✋ 以连接词 '{last_word_clean}' 结尾，继续等待 | 原文: {original_text}")
            return False
        
        # 检查最后两个词（短语）
        if len(words) >= 2:
            last_two = ' '.join(words[-2:]).lower().strip()
            last_two_clean = last_two.rstrip('.,;:!?"\'-')
            if last_two_clean in connecting_words:
                print(f"[SentenceCheck] ✋ 以连接词短语 '{last_two_clean}' 结尾，继续等待 | 原文: {original_text}")
                return False
    
    # 检查是否以句子结束标点结尾
    sentence_end_punctuation = ['.', '!', '?', '。', '！', '？']
    if text and text[-1] in sentence_end_punctuation:
        print(f"[SentenceCheck] ✅ 以结束标点结尾，判定为完整 | 原文: {original_text}")
        return True
    
    # 检查是否以逗号结尾（可能是句子中间）
    if text.endswith(','):
        print(f"[SentenceCheck] ✋ 以逗号结尾，继续等待 | 原文: {original_text}")
        return False
    
    # 检查是否是短句（少于4个词），可能是未完成的句子
    if len(words) < 4:
        print(f"[SentenceCheck] ⏳ 句子过短（{len(words)}词），继续等待 | 原文: {original_text}")
        return False
    
    # 检查是否以常见不完整模式结尾
    incomplete_patterns = [
        'i am', 'im', 'you are', 'youre', 'he is', 'hes', 'she is', 'shes',
        'it is', 'its', 'we are', 'were', 'they are', 'theyre',
        'this is', 'that is', 'there is', 'theres', 'here is',
        'going to', 'wanna', 'gonna', 'gotta', 'kinda', 'sorta',
        'i think', 'i guess', 'i believe', 'i suppose',
        'let me', 'i want', 'i need', 'i have',
        'can you', 'could you', 'would you', 'will you',
        'do you', 'did you', 'have you', 'are you',
    ]
    
    last_phrase = ' '.join(words[-2:]).lower() if len(words) >= 2 else words[-1].lower()
    for pattern in incomplete_patterns:
        if last_phrase.endswith(pattern) or last_phrase == pattern:
            print(f"[SentenceCheck] ✋ 以不完整模式 '{pattern}' 结尾，继续等待 | 原文: {original_text}")
            return False
    
    # 主谓宾结构检测：只有具有完整主谓宾结构才认为句子完整
    has_svo = has_complete_svo(text)
    
    # 如果有完整主谓宾结构，判定为完整句子
    if has_svo:
        print(f"[SentenceCheck] ✅ 具有完整主谓宾结构，判定为完整 | 原文: {original_text}")
        return True
    
    # 如果句子足够长（>=10个词）且没有明显不完整模式，也认为完整（避免过度等待）
    if len(words) >= 10:
        print(f"[SentenceCheck] ⏳ 句子较长（{len(words)}词）但无完整主谓宾，继续等待 | 原文: {original_text}")
        # 对于长句子，即使没有检测到完整主谓宾，也允许翻译（防止无限等待）
        return True
    
    # 其他情况：继续等待
    print(f"[SentenceCheck] ⏳ 句子不完整（无完整主谓宾），继续等待（{len(words)}词）| 原文: {original_text}")
    return False


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


@app.route("/api/context/clear", methods=["POST"])
def clear_context():
    """清空翻译上下文，开始新对话"""
    translation_context.clear()
    print("[Context] 上下文已清空")
    return jsonify({
        "success": True,
        "message": "上下文已清空"
    })


@app.route("/api/context/info", methods=["GET"])
def get_context_info():
    """获取当前上下文信息"""
    return jsonify({
        "success": True,
        "context_length": len(translation_context.history),
        "history": translation_context.history
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
                
                # 应用口语化修正，使识别结果更符合日常口语表达
                normalized_text = SpokenEnglishNormalizer.normalize(text)
                if normalized_text != text:
                    print(f"[Transcribe] 口语化修正: '{text}' -> '{normalized_text}'")
                    text = normalized_text
                
                # 智能判断句子是否完整
                is_complete = is_sentence_complete(text)
                
                # 将识别结果添加到修正管理器
                correction_manager.add_recognition(text)
                
                # 尝试自动修正（异步执行，不阻塞主流程）
                import asyncio
                asyncio.ensure_future(correction_manager.correct_last())
                
                socketio.emit('recognition', {
                    'text': text, 
                    'engine': 'vosk',
                    'is_complete': is_complete
                })
                return jsonify({
                    "success": True,
                    "data": {
                        "text": text, 
                        "engine": "vosk",
                        "is_complete": is_complete
                    }
                })
            print("[Transcribe] Vosk 识别结果为空")

        if openai_client:
            print("[Transcribe] 尝试 Whisper 识别...")
            text = _transcribe_with_whisper(audio_path)
            if text:
                os.unlink(audio_path)
                print(f"[Transcribe] Whisper 识别成功: {text}")
                
                # 应用口语化修正，使识别结果更符合日常口语表达
                normalized_text = SpokenEnglishNormalizer.normalize(text)
                if normalized_text != text:
                    print(f"[Transcribe] 口语化修正: '{text}' -> '{normalized_text}'")
                    text = normalized_text
                
                # 智能判断句子是否完整
                is_complete = is_sentence_complete(text)
                
                # 将识别结果添加到修正管理器
                correction_manager.add_recognition(text)
                
                # 尝试自动修正（异步执行，不阻塞主流程）
                import asyncio
                asyncio.ensure_future(correction_manager.correct_last())
                
                socketio.emit('recognition', {'text': text, 'engine': 'whisper-1', 'is_complete': is_complete})
                return jsonify({
                    "success": True,
                    "data": {"text": text, "engine": "whisper-1", "is_complete": is_complete}
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
    """流式翻译（SSE） - 结合上下文"""
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"success": False, "error": "缺少翻译文本"}), 400

    text = data["text"].strip()
    target_lang = data.get("target_lang", "zh")
    engine = data.get("engine", "deepseek")

    if not text:
        return jsonify({"success": False, "error": "翻译文本为空"}), 400

    system_prompt = get_system_prompt(target_lang)
    
    # 获取上下文
    context_prompt = translation_context.get_context_prompt()
    
    # 构建用户消息，包含上下文
    user_message = f"{context_prompt}{text}" if context_prompt else text
    
    print(f"[Translate] 上下文长度: {len(translation_context.history)}")
    if context_prompt:
        print(f"[Translate] 使用上下文进行翻译")

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
                    {"role": "user", "content": user_message}
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

            # 将本次翻译结果添加到上下文
            translation_context.add(text, full_text)
            print(f"[Translate] 上下文已更新，当前长度: {len(translation_context.history)}")

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


# ==================== 修正功能接口 ====================

@app.route("/api/correct", methods=["POST"])
def trigger_correction():
    """手动触发自动修正"""
    try:
        import asyncio
        results = asyncio.run(correction_manager.correct_all())
        
        return jsonify({
            "success": True,
            "message": f"已修正 {len(results)} 处",
            "corrected": results
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/correct/segments", methods=["GET"])
def get_segments():
    """获取当前所有片段信息"""
    segments = correction_manager.get_segments()
    return jsonify({
        "success": True,
        "data": segments,
        "total": len(segments)
    })


@app.route("/api/correct/manual", methods=["POST"])
def manual_correction():
    """手动修正特定片段"""
    data = request.get_json()
    if not data or "index" not in data or "text" not in data:
        return jsonify({"success": False, "error": "缺少必要参数 (index, text)"}), 400
    
    index = data["index"]
    text = data["text"].strip()
    
    if not text:
        return jsonify({"success": False, "error": "修正文本不能为空"}), 400
    
    # 获取原始文本
    segments = correction_manager.get_segments()
    if index < 0 or index >= len(segments):
        return jsonify({"success": False, "error": "索引超出范围"}), 400
    
    original = segments[index].get("original") or segments[index].get("text", "")
    
    # 执行修正
    success = correction_manager.window.correct_segment(index, text, original)
    
    if success:
        return jsonify({
            "success": True,
            "message": "修正成功",
            "index": index,
            "original": original,
            "corrected": text
        })
    else:
        return jsonify({"success": False, "error": "修正失败"}), 500


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
                    # 发送关闭消息（在HTTP上下文中需要使用server.emit）
                    try:
                        socketio.server.emit('close_overlay', {}, namespace='/')
                        print("[Backend] 已发送关闭悬浮窗命令")
                    except Exception as e:
                        print(f"[Backend] 发送关闭命令失败: {e}")
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