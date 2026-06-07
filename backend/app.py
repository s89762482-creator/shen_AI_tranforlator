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
from correction import CorrectionManager, SpokenEnglishNormalizer, SpokenChineseNormalizer

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

# Vosk 模型路径 - 支持英文、中文和日语
# 优先使用不含中文的路径，避免 Vosk 库编码问题
# 注意：中文模型有嵌套目录结构
VOSK_MODEL_PATH_EN = r"D:\vosk_models\vosk-model-small-en-us-0.15"
VOSK_MODEL_PATH_ZH = r"D:\vosk_models\vosk-model-small-cn-0.22\vosk-model-small-cn-0.22"
VOSK_MODEL_PATH_JA = r"D:\vosk_models\vosk-model-small-ja-0.22"

# 如果 D 盘路径不存在，尝试使用项目内的模型（如果有）
import os
_project_root = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(VOSK_MODEL_PATH_EN):
    _alt_en = os.path.join(_project_root, 'vosk-model-small-en-us-0.15')
    if os.path.exists(_alt_en):
        VOSK_MODEL_PATH_EN = _alt_en

if not os.path.exists(VOSK_MODEL_PATH_ZH):
    _alt_zh = os.path.join(_project_root, 'vosk-model-small-cn-0.22', 'vosk-model-small-cn-0.22')
    if os.path.exists(_alt_zh):
        VOSK_MODEL_PATH_ZH = _alt_zh

if not os.path.exists(VOSK_MODEL_PATH_JA):
    _alt_ja = os.path.join(_project_root, 'vosk-model-small-ja-0.22')
    if os.path.exists(_alt_ja):
        VOSK_MODEL_PATH_JA = _alt_ja

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')


# ==================== 语言提示词 ====================

def get_system_prompt(source_lang: str, target_lang: str) -> str:
    """根据源语言和目标语言获取翻译提示词"""
    
    # 英文 -> 中文
    if source_lang == "en" and target_lang == "zh":
        return """你是一个专业的同声传译助手，擅长将英文翻译成地道、自然的中文口语。

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

只输出翻译结果，不要添加任何解释。"""
    
    # 英文 -> 日语
    elif source_lang == "en" and target_lang == "ja":
        return """あなたはプロの同時通訳アシスタントです。以下の英語を自然で会話的な日本語に翻訳してください。

翻訳要求：
1. 提供された文脈を参考にして、意味の連続性を保つ
2. 日常的な口語表現を使用し、友人との会話のように自然に
3. 直訳を避け、日本語の表現習慣に合わせる
4. 短文を優先し、一文を長くしない
5. 原意を保ちつつ、意訳を主とする
6. スラングや慣用句は、対応する日本語の慣用表現に翻訳する

例：
- "I'm going to grab a bite to eat" -> "ちょっと食べに行くよ"
- "That's a great idea" -> "いいアイデアだね"
- "Let's call it a day" -> "今日はこれで終わりにしよう"
- "No worries" -> "気にしないで"

翻訳結果のみを出力し、説明は不要です。"""
    
    # 中文 -> 英文
    elif source_lang == "zh" and target_lang == "en":
        return """You are a professional simultaneous interpreter. Translate the following Chinese text into natural, conversational English.

Translation requirements:
1. Consider the provided context for coherent and natural translation
2. Use everyday conversational expressions, like chatting with friends
3. Avoid literal translation, follow English expression habits
4. Keep sentences short and natural
5. Preserve the original meaning, but prioritize sense-for-sense translation
6. Translate idioms into corresponding English expressions

Examples:
- "我去吃点东西" -> "I'm going to grab a bite"
- "这主意真不错" -> "That's a great idea"
- "今天就到这里吧" -> "Let's call it a day"
- "开玩笑啦" -> "I'm just kidding"
- "没事儿" -> "No worries"

Output only the translation, no explanations."""
    
    # 中文 -> 日语
    elif source_lang == "zh" and target_lang == "ja":
        return """あなたはプロの同時通訳アシスタントです。以下の中国語を自然で会話的な日本語に翻訳してください。

翻訳要求：
1. 提供された文脈を参考にして、意味の連続性を保つ
2. 日常的な口語表現を使用し、友人との会話のように自然に
3. 直訳を避け、日本語の表現習慣に合わせる
4. 短文を優先し、一文を長くしない
5. 原意を保ちつつ、意訳を主とする

例：
- "我去吃点东西" -> "ちょっと食べに行くよ"
- "这主意真不错" -> "いいアイデアだね"
- "今天就到这里吧" -> "今日はこれで終わりにしよう"
- "没事儿" -> "気にしないで"

翻訳結果のみを出力し、説明は不要です。"""
    
    # 日语 -> 中文
    elif source_lang == "ja" and target_lang == "zh":
        return """你是一个专业的同声传译助手，擅长将日语翻译成地道、自然的中文口语。

翻译要求：
1. 结合上下文进行翻译，保证语义连贯和自然
2. 使用日常口语表达，就像朋友之间聊天一样自然
3. 避免直译和书面语，要符合中文表达习惯
4. 可以适当使用语气词（啊、哦、啦、呢、吧、呗）
5. 短句优先，每句话不要太长
6. 保留原意，但不必逐字翻译，意译为主

示例对照：
- "ちょっと食べに行くよ" -> "我去吃点东西"
- "いいアイデアだね" -> "这主意真不错"
- "今日はこれで終わりにしよう" -> "今天就到这里吧"
- "気にしないで" -> "没事儿"

只输出翻译结果，不要添加任何解释。"""
    
    # 日语 -> 英文
    elif source_lang == "ja" and target_lang == "en":
        return """You are a professional simultaneous interpreter. Translate the following Japanese text into natural, conversational English.

Translation requirements:
1. Consider the provided context for coherent and natural translation
2. Use everyday conversational expressions, like chatting with friends
3. Avoid literal translation, follow English expression habits
4. Keep sentences short and natural
5. Preserve the original meaning, but prioritize sense-for-sense translation

Examples:
- "ちょっと食べに行くよ" -> "I'm going to grab a bite"
- "いいアイデアだね" -> "That's a great idea"
- "今日はこれで終わりにしよう" -> "Let's call it a day"
- "気にしないで" -> "No worries"

Output only the translation, no explanations."""
    
    # 默认：英文润色
    elif source_lang == "en" and target_lang == "en":
        return """You are a professional simultaneous interpreter. Polish and refine the following English text to be more natural and conversational. Consider the provided context for better accuracy. Output only the refined text, no explanations."""
    
    # 其他情况：通用翻译
    else:
        return f"""You are a professional simultaneous interpreter. Translate the following text into {target_lang}. Use natural, conversational expressions. Consider the provided context for better accuracy. Output only the translation, no explanations."""


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


def is_chinese_sentence_complete(text: str) -> bool:
    """
    中文句子完整性判断
    
    Args:
        text: 中文文本
        
    Returns:
        True: 句子完整
        False: 句子不完整
    """
    if not text or not text.strip():
        return False
    
    text = text.strip()
    
    # 中文连接词（这些词后面不应该断句）
    chinese_connecting_words = [
        '和', '跟', '与', '同', '及', '以及',
        '但是', '可是', '不过', '然而', '却',
        '因为', '所以', '如果', '假如', '要是',
        '虽然', '尽管', '即使', '哪怕',
        '当', '在', '从', '向', '往', '到',
        '对', '对于', '关于', '通过', '经过',
        '把', '被', '让', '给', '叫',
        '着', '了', '过',  # 动词后缀，可能还有后续内容
    ]
    
    # 检查是否以连接词结尾
    for word in chinese_connecting_words:
        if text.endswith(word):
            print(f"[SentenceCheck-ZH] ✋ 以连接词 '{word}' 结尾，继续等待 | 原文: {text}")
            return False
    
    # 检查是否以句子结束标点结尾
    sentence_end_punctuation = ['.', '!', '?', '。', '！', '？', '…']
    if text and text[-1] in sentence_end_punctuation:
        print(f"[SentenceCheck-ZH] ✅ 以结束标点结尾，判定为完整 | 原文: {text}")
        return True
    
    # 检查是否以逗号结尾（可能是句子中间）
    if text.endswith(',') or text.endswith('，'):
        print(f"[SentenceCheck-ZH] ✋ 以逗号结尾，继续等待 | 原文: {text}")
        return False
    
    # 中文句子长度判断：如果句子足够长（>=10个字），认为完整
    if len(text) >= 10:
        print(f"[SentenceCheck-ZH] ✅ 句子较长（{len(text)}字），判定为完整 | 原文: {text}")
        return True
    
    # 短句子：检查是否有完整的主谓结构
    # 常见中文动词
    chinese_verbs = ['是', '有', '在', '去', '来', '做', '说', '看', '听', '想', 
                     '要', '能', '会', '可以', '应该', '需要', '喜欢', '知道', '觉得']
    
    has_verb = False
    for verb in chinese_verbs:
        if verb in text:
            has_verb = True
            break
    
    if has_verb and len(text) >= 4:
        print(f"[SentenceCheck-ZH] ✅ 有动词且长度足够，判定为完整 | 原文: {text}")
        return True
    
    # 其他情况：继续等待
    print(f"[SentenceCheck-ZH] ⏳ 句子不完整，继续等待（{len(text)}字）| 原文: {text}")
    return False


def is_sentence_complete(text: str, language: str = "en") -> bool:
    """
    智能判断句子是否完整（结合主谓宾检测），支持多语言
    
    Args:
        text: 识别出的文本
        language: 语言代码（en/zh/ja）
        
    Returns:
        True: 句子完整，可以翻译
        False: 句子不完整，需要继续等待
    """
    if not text or not text.strip():
        return False
    
    original_text = text
    text = text.strip()
    
    # 中文句子完整性判断
    if language == "zh":
        return is_chinese_sentence_complete(text)
    
    # 日文句子完整性判断
    if language == "ja":
        # 日语句子通常以です/ます结尾，或者以句号。结尾
        if text.endswith('。') or text.endswith('！') or text.endswith('？'):
            return True
        if text.endswith('です') or text.endswith('ます') or text.endswith('でした') or text.endswith('ました'):
            return True
        # 短句子判断
        if len(text) >= 10:
            return True
        return False
    
    # 英文句子完整性判断（原有逻辑）
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
    vosk_en_ok = os.path.exists(VOSK_MODEL_PATH_EN)
    vosk_zh_ok = os.path.exists(VOSK_MODEL_PATH_ZH)
    vosk_ja_ok = os.path.exists(VOSK_MODEL_PATH_JA)
    
    return jsonify({
        "status": "healthy",
        "vosk_en": vosk_en_ok,
        "vosk_zh": vosk_zh_ok,
        "vosk_ja": vosk_ja_ok,
        "openai_api": openai_client is not None,
        "deepseek_api": deepseek_client is not None,
    })


@app.route("/api/translate", methods=["POST"])
def translate_text():
    """翻译文本（单次请求）"""
    data = request.get_json()
    text = data.get("text", "")
    source_lang = data.get("source_lang", "en")
    target_lang = data.get("target_lang", "zh")
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    print(f"[API] 收到翻译请求: {text} ({source_lang} -> {target_lang})")
    
    # 获取翻译结果
    result = translate_text_with_api(text, source_lang, target_lang)
    
    if result:
        return jsonify({"text": text, "translation": result, "source_lang": source_lang, "target_lang": target_lang})
    else:
        return jsonify({"error": "Translation failed"}), 500


def translate_text_with_api(text: str, source_lang: str, target_lang: str) -> str:
    """调用翻译 API 进行翻译"""
    system_prompt = get_system_prompt(source_lang, target_lang)
    context_prompt = translation_context.get_context_prompt()
    
    full_prompt = f"{system_prompt}\n{context_prompt}\n{text}"
    
    # 尝试 DeepSeek API
    if deepseek_client:
        try:
            response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{context_prompt}\n{text}"}
                ],
                temperature=0.3,
                max_tokens=500
            )
            result = response.choices[0].message.content.strip()
            print(f"[DeepSeek] 翻译成功: {text} -> {result}")
            
            # 添加到上下文
            translation_context.add(text, result)
            
            return result
        except Exception as e:
            print(f"[DeepSeek] 失败: {str(e)}")
    
    # 尝试 OpenAI API
    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{context_prompt}\n{text}"}
                ],
                temperature=0.3,
                max_tokens=500
            )
            result = response.choices[0].message.content.strip()
            print(f"[OpenAI] 翻译成功: {text} -> {result}")
            
            # 添加到上下文
            translation_context.add(text, result)
            
            return result
        except Exception as e:
            print(f"[OpenAI] 失败: {str(e)}")
    
    return None


@app.route("/api/translate/stream", methods=["POST"])
def translate_stream():
    """流式翻译 API"""
    data = request.get_json()
    text = data.get("text", "")
    source_lang = data.get("source_lang", "en")
    target_lang = data.get("target_lang", "zh")
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    def generate():
        system_prompt = get_system_prompt(source_lang, target_lang)
        context_prompt = translation_context.get_context_prompt()
        
        # 尝试 DeepSeek 流式翻译
        if deepseek_client:
            try:
                stream = deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{context_prompt}\n{text}"}
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    stream=True
                )
                
                full_result = ""
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_result += content
                        yield f"data: {json.dumps({'content': content, 'done': False})}\n\n"
                
                # 添加到上下文
                translation_context.add(text, full_result)
                
                yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
                return
            except Exception as e:
                print(f"[DeepSeek Stream] 失败: {str(e)}")
        
        # 尝试 OpenAI 流式翻译
        if openai_client:
            try:
                stream = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{context_prompt}\n{text}"}
                    ],
                    temperature=0.3,
                    max_tokens=500,
                    stream=True
                )
                
                full_result = ""
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_result += content
                        yield f"data: {json.dumps({'content': content, 'done': False})}\n\n"
                
                # 添加到上下文
                translation_context.add(text, full_result)
                
                yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
                return
            except Exception as e:
                print(f"[OpenAI Stream] 失败: {str(e)}")
        
        # 回退到非流式翻译
        result = translate_text_with_api(text, source_lang, target_lang)
        if result:
            yield f"data: {json.dumps({'content': result, 'done': True})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ==================== WebSocket 实时识别和翻译 ====================

# 存储识别会话状态
recognition_sessions = {}

@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f"[WebSocket] 客户端已连接")

@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开连接"""
    print(f"[WebSocket] 客户端已断开连接")

@socketio.on('start_recognition')
def handle_start_recognition(data):
    """开始语音识别"""
    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'zh')
    
    print(f"[WebSocket] 开始识别: {source_lang} -> {target_lang}")
    
    # 初始化识别会话
    session_id = request.sid
    recognition_sessions[session_id] = {
        'source_lang': source_lang,
        'target_lang': target_lang,
        'buffer': '',
        'last_translate_time': datetime.now(),
        'sentence_index': 0
    }
    
    emit('recognition_started', {'message': 'Recognition started'})

@socketio.on('audio_data')
def handle_audio_data(data):
    """处理音频数据"""
    session_id = request.sid
    session = recognition_sessions.get(session_id)
    
    if not session:
        emit('error', {'message': 'No active recognition session'})
        return
    
    audio_bytes = data.get('audio')
    source_lang = session['source_lang']
    target_lang = session['target_lang']
    
    if audio_bytes:
        print(f"[Transcribe] 收到音频数据，大小: {len(audio_bytes)} 字节, 源语言: {source_lang}")
        
        # 尝试使用 Vosk 进行离线识别
        try:
            result = transcribe_audio(audio_bytes, source_lang)
            if result:
                session['buffer'] += result + ' '
                
                # 检查是否需要翻译（句子完整检测）
                if is_sentence_complete(session['buffer'], source_lang):
                    # 翻译完整句子
                    translation = translate_text_with_api(session['buffer'].strip(), source_lang, target_lang)
                    
                    if translation:
                        session['sentence_index'] += 1
                        emit('transcription', {
                            'index': session['sentence_index'],
                            'original': session['buffer'].strip(),
                            'translation': translation,
                            'timestamp': datetime.now().isoformat()
                        })
                        
                        # 清空缓冲区
                        session['buffer'] = ''
        except Exception as e:
            print(f"[Transcribe] 识别失败: {str(e)}")

@socketio.on('stop_recognition')
def handle_stop_recognition():
    """停止语音识别"""
    session_id = request.sid
    if session_id in recognition_sessions:
        del recognition_sessions[session_id]
    print(f"[WebSocket] 停止识别")
    emit('recognition_stopped', {'message': 'Recognition stopped'})


def transcribe_audio(audio_bytes, language='en'):
    """使用 Vosk 进行离线语音识别"""
    # 根据语言选择模型
    if language == "en":
        vosk_model_path = VOSK_MODEL_PATH_EN
    elif language == "zh":
        vosk_model_path = VOSK_MODEL_PATH_ZH
    elif language == "ja":
        vosk_model_path = VOSK_MODEL_PATH_JA
    else:
        vosk_model_path = VOSK_MODEL_PATH_EN
    
    # 检查模型是否存在
    if not os.path.exists(vosk_model_path):
        print(f"[Vosk] 模型路径不存在: {vosk_model_path}")
        return None
    
    print(f"[Transcribe] 尝试 Vosk 识别 ({language})...")
    
    try:
        # 使用 vosk 进行识别
        from vosk import Model, KaldiRecognizer
        import wave
        
        # 创建临时文件保存音频
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_file = f.name
            f.write(audio_bytes)
        
        # 读取音频文件
        wf = wave.open(temp_file, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
            print("[Vosk] 音频格式错误，需要单声道 PCM")
            wf.close()
            os.unlink(temp_file)
            return None
        
        # 加载模型并识别
        model = Model(vosk_model_path)
        rec = KaldiRecognizer(model, wf.getframerate())
        
        result_text = ""
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if 'text' in result and result['text']:
                    result_text += result['text'] + ' '
        
        # 获取最后的结果
        final_result = json.loads(rec.FinalResult())
        if 'text' in final_result and final_result['text']:
            result_text += final_result['text']
        
        wf.close()
        os.unlink(temp_file)
        
        if result_text.strip():
            print(f"[Vosk] 识别成功: {result_text.strip()}")
            return result_text.strip()
        else:
            print(f"[Vosk] 未识别到内容")
            return None
            
    except Exception as e:
        print(f"[Vosk] 识别失败: {str(e)}")
        return None


# ==================== 主函数 ====================

if __name__ == "__main__":
    print("🚀 AI 同声传译助手启动中...")
    print(f"📦 英文模型路径: {VOSK_MODEL_PATH_EN}")
    print(f"📦 中文模型路径: {VOSK_MODEL_PATH_ZH}")
    print(f"📦 日语模型路径: {VOSK_MODEL_PATH_JA}")
    print(f"🌐 OpenAI API: {'✓ 已配置' if openai_client else '✗ 未配置'}")
    print(f"🌐 DeepSeek API: {'✓ 已配置' if deepseek_client else '✗ 未配置'}")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)