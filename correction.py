"""
修正机制模块 - 滑动窗口 + 历史修正

核心功能：
- 维护最近 N 秒的识别文本缓存（带时间戳）
- 基于上下文的识别结果自动修正
- 口语化修正，使识别结果更符合日常口语表达
- 修正后通知 UI 更新
"""

import asyncio
import re
import time
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from collections import deque


class SpokenEnglishNormalizer:
    """
    口语化英文修正器 - 将语音识别结果转换为更自然的口语表达
    """

    # 口语缩写展开规则
    SPOKEN_CONTRACTIONS = {
        # 常见缩写
        "im": "I'm",
        "ive": "I've",
        "id": "I'd",
        "ill": "I'll",
        "youre": "you're",
        "youve": "you've",
        "youd": "you'd",
        "youll": "you'll",
        "hes": "he's",
        "shes": "she's",
        "its": "it's",
        "theyre": "they're",
        "theyve": "they've",
        "theyd": "they'd",
        "theyll": "they'll",
        "were": "we're",
        "weve": "we've",
        "wed": "we'd",
        "well": "we'll",
        "dont": "don't",
        "doesnt": "doesn't",
        "didnt": "didn't",
        "isnt": "isn't",
        "arent": "aren't",
        "wasnt": "wasn't",
        "werent": "weren't",
        "hasnt": "hasn't",
        "havent": "haven't",
        "hadnt": "hadn't",
        "wont": "won't",
        "wouldnt": "wouldn't",
        "couldnt": "couldn't",
        "shouldnt": "shouldn't",
        "cant": "can't",
        "mustnt": "mustn't",
        
        # 口语化表达
        "gonna": "going to",
        "wanna": "want to",
        "gotta": "got to",
        "hafta": "have to",
        "needta": "need to",
        "outta": "out of",
        "kinda": "kind of",
        "sorta": "sort of",
        "gimme": "give me",
        "lemme": "let me",
        "gotcha": "got you",
        "dunno": "don't know",
        "innit": "isn't it",
        "ain't": "isn't",
        "cuz": "because",
        "thru": "through",
        "tho": "though",
        "altho": "although",
        "ya": "you",
        "yer": "your",
        "yep": "yes",
        "nope": "no",
        "uh-huh": "yes",
        "uh-uh": "no",
        "okay": "OK",
        "alright": "all right",
        "anyways": "anyway",
        "besides": "besides",
        "regardless": "regardless",
        "nevertheless": "nevertheless",
        
        # 数字口语化
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
        "ten": "10",
        "eleven": "11",
        "twelve": "12",
        "thirteen": "13",
        "fourteen": "14",
        "fifteen": "15",
        "sixteen": "16",
        "seventeen": "17",
        "eighteen": "18",
        "nineteen": "19",
        "twenty": "20",
        "thirty": "30",
        "forty": "40",
        "fifty": "50",
        "sixty": "60",
        "seventy": "70",
        "eighty": "80",
        "ninety": "90",
        "hundred": "100",
        "thousand": "1000",
        "million": "1000000",
    }

    # 口语习惯表达修正
    SPOKEN_PHRASES = {
        # 填充词和口头禅
        "you know": "you know",
        "i mean": "I mean",
        "like": "like",
        "basically": "basically",
        "actually": "actually",
        "literally": "literally",
        "seriously": "seriously",
        "honestly": "honestly",
        "frankly": "frankly",
        "obviously": "obviously",
        "apparently": "apparently",
        "basically": "basically",
        "essentially": "essentially",
        "fundamentally": "fundamentally",
        "practically": "practically",
        "virtually": "virtually",
        "basically": "basically",
        
        # 连接短语
        "sort of": "sort of",
        "kind of": "kind of",
        "more or less": "more or less",
        "in fact": "in fact",
        "as a matter of fact": "as a matter of fact",
        "to be honest": "to be honest",
        "to tell you the truth": "to tell you the truth",
        "if you ask me": "if you ask me",
        "between you and me": "between you and me",
        "let me tell you": "let me tell you",
        "you see": "you see",
        "I think": "I think",
        "I guess": "I guess",
        "I suppose": "I suppose",
        "I believe": "I believe",
        "I feel": "I feel",
        "I wonder": "I wonder",
        "I hope": "I hope",
        "I'm sure": "I'm sure",
        "I'm not sure": "I'm not sure",
        "I don't know": "I don't know",
        "I don't think so": "I don't think so",
        "I think so": "I think so",
        "I mean": "I mean",
        "you know what I mean": "you know what I mean",
        "if you know what I mean": "if you know what I mean",
        
        # 日常表达
        "how are you": "how are you",
        "how are you doing": "how are you doing",
        "what's up": "what's up",
        "what's going on": "what's going on",
        "long time no see": "long time no see",
        "nice to meet you": "nice to meet you",
        "good to see you": "good to see you",
        "see you later": "see you later",
        "see you soon": "see you soon",
        "take care": "take care",
        "have a nice day": "have a nice day",
        "thank you": "thank you",
        "thanks": "thanks",
        "you're welcome": "you're welcome",
        "no problem": "no problem",
        "no worries": "no worries",
        "my pleasure": "my pleasure",
        "excuse me": "excuse me",
        "sorry": "sorry",
        "I'm sorry": "I'm sorry",
        "pardon me": "pardon me",
        "could you repeat that": "could you repeat that",
        "I didn't catch that": "I didn't catch that",
        "could you speak up": "could you speak up",
        "could you slow down": "could you slow down",
        "I need to go": "I need to go",
        "I have to go": "I have to go",
        "got to go": "got to go",
        "let's go": "let's go",
        "come on": "come on",
        "hold on": "hold on",
        "wait a second": "wait a second",
        "wait a minute": "wait a minute",
        "just a second": "just a second",
        "just a minute": "just a minute",
        "give me a second": "give me a second",
        "give me a minute": "give me a minute",
        "one second": "one second",
        "one minute": "one minute",
        "be right back": "be right back",
        "I'll be right back": "I'll be right back",
        "I'll be back": "I'll be back",
        "in a minute": "in a minute",
        "in a second": "in a second",
        "right away": "right away",
        "as soon as possible": "as soon as possible",
        "as soon as I can": "as soon as I can",
        "I'm on my way": "I'm on my way",
        "I'm coming": "I'm coming",
        "I'm almost there": "I'm almost there",
        "I'm running late": "I'm running late",
        "I'm on time": "I'm on time",
        "I'm early": "I'm early",
        "I'm late": "I'm late",
        "let's hurry": "let's hurry",
        "hurry up": "hurry up",
        "take your time": "take your time",
        "no rush": "no rush",
        "take it easy": "take it easy",
        "relax": "relax",
        "calm down": "calm down",
        "don't worry": "don't worry",
        "it's okay": "it's okay",
        "everything's fine": "everything's fine",
        "nothing to worry about": "nothing to worry about",
        "no problem": "no problem",
        "it's all good": "it's all good",
        "that's fine": "that's fine",
        "that's okay": "that's okay",
        "sure": "sure",
        "of course": "of course",
        "definitely": "definitely",
        "absolutely": "absolutely",
        "certainly": "certainly",
        "maybe": "maybe",
        "perhaps": "perhaps",
        "possibly": "possibly",
        "probably": "probably",
        "likely": "likely",
        "unlikely": "unlikely",
        "never mind": "never mind",
        "forget it": "forget it",
        "it doesn't matter": "it doesn't matter",
        "doesn't matter": "doesn't matter",
        "whatever": "whatever",
        "anyway": "anyway",
        "anyways": "anyway",
        "at least": "at least",
        "at most": "at most",
        "more importantly": "more importantly",
        "most importantly": "most importantly",
        "first of all": "first of all",
        "first": "first",
        "second": "second",
        "third": "third",
        "finally": "finally",
        "lastly": "lastly",
        "in conclusion": "in conclusion",
        "to summarize": "to summarize",
        "in summary": "in summary",
        "all in all": "all in all",
        "overall": "overall",
        "on the whole": "on the whole",
        "generally speaking": "generally speaking",
        "in general": "in general",
        "for the most part": "for the most part",
        "by and large": "by and large",
        "as a rule": "as a rule",
        "usually": "usually",
        "normally": "normally",
        "typically": "typically",
        "generally": "generally",
        "often": "often",
        "frequently": "frequently",
        "sometimes": "sometimes",
        "occasionally": "occasionally",
        "rarely": "rarely",
        "seldom": "seldom",
        "hardly ever": "hardly ever",
        "never": "never",
        "always": "always",
        "constantly": "constantly",
        "continually": "continually",
        "regularly": "regularly",
        "periodically": "periodically",
        "every now and then": "every now and then",
        "every once in a while": "every once in a while",
        "from time to time": "from time to time",
        "once in a while": "once in a while",
        "at times": "at times",
        "on occasion": "on occasion",
        "now and then": "now and then",
        "now and again": "now and again",
    }

    # 语法修正规则
    GRAMMAR_FIXES = [
        # 主谓一致
        (r"\bhe don't\b", "he doesn't"),
        (r"\bshe don't\b", "she doesn't"),
        (r"\bit don't\b", "it doesn't"),
        (r"\bthey don't\b", "they don't"),
        (r"\bwe don't\b", "we don't"),
        (r"\byou don't\b", "you don't"),
        (r"\bi don't\b", "I don't"),
        (r"\bhe is\b", "he's"),
        (r"\bshe is\b", "she's"),
        (r"\bit is\b", "it's"),
        (r"\bthey are\b", "they're"),
        (r"\bwe are\b", "we're"),
        (r"\byou are\b", "you're"),
        (r"\bi am\b", "I'm"),
        
        # 时态修正
        (r"\bwould of\b", "would have"),
        (r"\bcould of\b", "could have"),
        (r"\bshould of\b", "should have"),
        (r"\bmight of\b", "might have"),
        (r"\bmust of\b", "must have"),
        (r"\bhas went\b", "has gone"),
        (r"\bhave went\b", "have gone"),
        (r"\bhad went\b", "had gone"),
        (r"\bhas came\b", "has come"),
        (r"\bhave came\b", "have come"),
        (r"\bhad came\b", "had come"),
        (r"\bhas did\b", "has done"),
        (r"\bhave did\b", "have done"),
        (r"\bhad did\b", "had done"),
        
        # 介词修正
        (r"\bwait on\b", "wait for"),
        (r"\blisten on\b", "listen to"),
        (r"\blook on\b", "look at"),
        (r"\blook up to\b", "look up"),
        (r"\btalk on\b", "talk about"),
        (r"\bspeak on\b", "speak about"),
        (r"\bthink on\b", "think about"),
        (r"\bworry on\b", "worry about"),
        (r"\bcare on\b", "care about"),
        (r"\bdepend on\b", "depend on"),
        (r"\brely on\b", "rely on"),
        (r"\bfocus on\b", "focus on"),
        (r"\bconcentrate on\b", "concentrate on"),
        (r"\bwork on\b", "work on"),
        (r"\binsist on\b", "insist on"),
        (r"\bkeep on\b", "keep on"),
        (r"\bcarry on\b", "carry on"),
        (r"\bgo on\b", "go on"),
        (r"\bcome on\b", "come on"),
        (r"\bget on\b", "get on"),
        (r"\bput on\b", "put on"),
        (r"\btake on\b", "take on"),
        (r"\bturn on\b", "turn on"),
        (r"\bswitch on\b", "switch on"),
        (r"\btry on\b", "try on"),
        (r"\bhold on\b", "hold on"),
        (r"\bhang on\b", "hang on"),
        (r"\bwait on\b", "wait on"),
        (r"\bsit on\b", "sit on"),
        (r"\bstand on\b", "stand on"),
        (r"\blie on\b", "lie on"),
        (r"\bstay on\b", "stay on"),
        (r"\blive on\b", "live on"),
        (r"\bwork on\b", "work on"),
        (r"\bstudy on\b", "study on"),
        (r"\blearn on\b", "learn on"),
        (r"\bteach on\b", "teach on"),
        (r"\bhelp on\b", "help on"),
        (r"\bshow on\b", "show on"),
        (r"\bfind on\b", "find on"),
        (r"\blose on\b", "lose on"),
        (r"\bbuy on\b", "buy on"),
        (r"\bsell on\b", "sell on"),
        (r"\bstart on\b", "start on"),
        (r"\bstop on\b", "stop on"),
        (r"\bbegin on\b", "begin on"),
        (r"\bend on\b", "end on"),
        (r"\buse on\b", "use on"),
        (r"\bcreate on\b", "create on"),
        (r"\bbuild on\b", "build on"),
        (r"\brun on\b", "run on"),
        (r"\bwalk on\b", "walk on"),
        (r"\bdrive on\b", "drive on"),
        (r"\bfly on\b", "fly on"),
        (r"\beat on\b", "eat on"),
        (r"\bdrink on\b", "drink on"),
        (r"\bsleep on\b", "sleep on"),
        (r"\bwake on\b", "wake on"),
        (r"\bcome on\b", "come on"),
        (r"\bleave on\b", "leave on"),
        (r"\barrive on\b", "arrive on"),
        (r"\breturn on\b", "return on"),
        (r"\bchange on\b", "change on"),
        (r"\bkeep on\b", "keep on"),
        (r"\bput on\b", "put on"),
        (r"\bset on\b", "set on"),
        (r"\bget on\b", "get on"),
        (r"\bturn on\b", "turn on"),
        (r"\bmove on\b", "move on"),
        (r"\bstay on\b", "stay on"),
        (r"\blive on\b", "live on"),
        (r"\bbelieve on\b", "believe in"),
        (r"\bremember on\b", "remember"),
        (r"\bforget on\b", "forget"),
        (r"\bunderstand on\b", "understand"),
        (r"\bexplain on\b", "explain"),
        (r"\bdiscuss on\b", "discuss"),
        (r"\bdecide on\b", "decide"),
        (r"\bagree on\b", "agree"),
        (r"\bdisagree on\b", "disagree"),
        (r"\btry on\b", "try"),
        (r"\bhope on\b", "hope"),
        (r"\bexpect on\b", "expect"),
        (r"\bplan on\b", "plan"),
        (r"\bpromise on\b", "promise"),
        (r"\boffer on\b", "offer"),
        (r"\baccept on\b", "accept"),
        (r"\brefuse on\b", "refuse"),
        (r"\ballow on\b", "allow"),
        (r"\bdeny on\b", "deny"),
        (r"\bneed on\b", "need"),
        (r"\bmust on\b", "must"),
        (r"\bshould on\b", "should"),
        (r"\bwould on\b", "would"),
        (r"\bcould on\b", "could"),
        (r"\bmay on\b", "may"),
        (r"\bmight on\b", "might"),
        (r"\bcan on\b", "can"),
        (r"\bwill on\b", "will"),
        (r"\bshall on\b", "shall"),
    ]

    @classmethod
    def normalize(cls, text: str) -> str:
        """
        将语音识别结果转换为更自然的口语表达
        
        Args:
            text: 原始识别文本
            
        Returns:
            口语化修正后的文本
        """
        if not text or not text.strip():
            return text
            
        result = text.strip()
        
        # 1. 修复发音错误导致的识别错误
        result = cls._fix_pronunciation_errors(result)
        
        # 2. 展开口语缩写
        result = cls._expand_contractions(result)
        
        # 3. 应用语法修正
        result = cls._fix_grammar(result)
        
        # 4. 修复大小写
        result = cls._fix_capitalization(result)
        
        # 5. 修复标点
        result = cls._fix_punctuation(result)
        
        # 6. 去除重复单词
        result = cls._remove_repeats(result)
        
        # 7. 标准化空格
        result = re.sub(r'\s+', ' ', result).strip()
        
        return result

    @classmethod
    def _fix_pronunciation_errors(cls, text: str) -> str:
        """修复基于发音的常见识别错误"""
        fixes = {
            # 发音相似的单词
            r'\bthru\b': 'through',
            r'\btho\b': 'though',
            r'\baltho\b': 'although',
            r'\bcuz\b': 'because',
            r'\bcos\b': 'because',
            r'\bcause\b': 'because',
            r'\bkinda\b': 'kind of',
            r'\bsorta\b': 'sort of',
            r'\bgotta\b': 'got to',
            r'\bwanna\b': 'want to',
            r'\bgonna\b': 'going to',
            r'\bdunno\b': 'don\'t know',
            r'\binnit\b': 'isn\'t it',
            r'\bain\'t\b': 'isn\'t',
            r'\bya\b': 'you',
            r'\byer\b': 'your',
            r'\byep\b': 'yes',
            r'\bnope\b': 'no',
            r'\buh-huh\b': 'yes',
            r'\buh-uh\b': 'no',
            r'\bokay\b': 'OK',
            r'\balright\b': 'all right',
            r'\banyways\b': 'anyway',
            r'\breally\b': 'really',
            r'\bvery\b': 'very',
            r'\bso\b': 'so',
            r'\btoo\b': 'too',
            r'\balso\b': 'also',
            r'\bwell\b': 'well',
            r'\bjust\b': 'just',
            r'\bonly\b': 'only',
            r'\beven\b': 'even',
            r'\bstill\b': 'still',
            r'\balready\b': 'already',
            r'\byet\b': 'yet',
            r'\bnever\b': 'never',
            r'\balways\b': 'always',
            r'\bsometimes\b': 'sometimes',
            r'\boften\b': 'often',
            r'\bseldom\b': 'seldom',
            r'\brarely\b': 'rarely',
            r'\busually\b': 'usually',
            r'\bnormally\b': 'normally',
            r'\btypically\b': 'typically',
            r'\bgenerally\b': 'generally',
            r'\bfrequently\b': 'frequently',
            r'\boccasionally\b': 'occasionally',
            r'\bconstantly\b': 'constantly',
            r'\bcontinually\b': 'continually',
            r'\bregularly\b': 'regularly',
            r'\bperiodically\b': 'periodically',
            r'\bevery now and then\b': 'every now and then',
            r'\bevery once in a while\b': 'every once in a while',
            r'\bfrom time to time\b': 'from time to time',
            r'\bonce in a while\b': 'once in a while',
            r'\bat times\b': 'at times',
            r'\bon occasion\b': 'on occasion',
            r'\bnow and then\b': 'now and then',
            r'\bnow and again\b': 'now and again',
        }
        
        result = text
        for pattern, replacement in fixes.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def _expand_contractions(cls, text: str) -> str:
        """展开口语缩写"""
        result = text
        for spoken, standard in cls.SPOKEN_CONTRACTIONS.items():
            pattern = r'\b' + re.escape(spoken) + r'\b'
            result = re.sub(pattern, standard, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def _fix_grammar(cls, text: str) -> str:
        """应用语法修正规则"""
        result = text
        for pattern, replacement in cls.GRAMMAR_FIXES:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def _fix_capitalization(cls, text: str) -> str:
        """修复大小写问题"""
        if not text:
            return text
            
        result = text
        
        # 首字母大写
        result = result[0].upper() + result[1:]
        
        # 句子结尾后的首字母大写
        result = re.sub(r'([.!?])\s*([a-z])', lambda m: m.group(1) + ' ' + m.group(2).upper(), result)
        
        # I 应该大写
        result = re.sub(r'\bi\b', 'I', result)
        
        # I'm, I've, I'd, I'll 等应该大写
        result = re.sub(r'\bi\'([mvd]|ll)\b', lambda m: 'I' + m.group(0)[1:], result)
        
        return result

    @classmethod
    def _fix_punctuation(cls, text: str) -> str:
        """修复标点问题"""
        result = text
        
        # 去除重复标点
        result = re.sub(r'([.!?]){2,}', r'\1', result)
        
        # 标点后应该有空格
        result = re.sub(r'([.!?])([A-Za-z])', r'\1 \2', result)
        
        # 确保句子结尾有标点（如果看起来是完整句子）
        if len(result) > 0 and result[-1] not in '.!?。！？':
            if len(result.split()) >= 3:
                result = result + '.'
        
        return result

    @classmethod
    def _remove_repeats(cls, text: str) -> str:
        """去除连续重复的单词"""
        result = re.sub(r'\b(\w+)\s+\1\b', r'\1', text)
        return result


@dataclass
class TextSegment:
    """文本片段，带时间戳"""
    text: str
    timestamp: float
    is_corrected: bool = False
    original_text: Optional[str] = None


class CorrectionWindow:
    """滑动窗口缓存管理器"""

    def __init__(self, window_seconds: int = 15):
        self.window_seconds = window_seconds
        self.segments: deque = deque()
        self._correction_callback: Optional[Callable] = None

    def add_segment(self, text: str, timestamp: float = None) -> Optional[TextSegment]:
        """添加新的文本片段"""
        if not text or text.strip() == "":
            return None

        if timestamp is None:
            timestamp = time.time()

        segment = TextSegment(text=text.strip(), timestamp=timestamp)
        self.segments.append(segment)
        self._clean_expired()
        return segment

    def _clean_expired(self):
        """清理超出窗口的旧片段"""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        while self.segments and self.segments[0].timestamp < cutoff_time:
            self.segments.popleft()

    def get_all_text(self) -> str:
        """获取窗口内所有文本"""
        return " ".join([seg.text for seg in self.segments])

    def get_last_segment(self) -> Optional[TextSegment]:
        """获取最后一个文本片段"""
        return self.segments[-1] if self.segments else None

    def correct_segment(self, index: int, new_text: str, original_text: str = None) -> bool:
        """修正指定位置的文本片段"""
        if index < 0 or index >= len(self.segments):
            return False

        segment = self.segments[index]
        if not segment.is_corrected:
            segment.original_text = original_text or segment.text
        segment.text = new_text
        segment.is_corrected = True

        if self._correction_callback:
            self._correction_callback(index, segment)

        return True

    def get_segments_for_display(self) -> List[Dict]:
        """获取用于显示的片段信息"""
        return [
            {
                "text": seg.text,
                "is_corrected": seg.is_corrected,
                "original": seg.original_text
            }
            for seg in self.segments
        ]


class SimpleCorrector:
    """简单的本地修正器"""

    # 常见错误映射（错误 -> 正确）
    WORD_CORRECTIONS = {
        "bench": "bank",
        "meat": "meet",
        "there": "their",
        "your": "you're",
        "its": "it's",
        "youre": "you're",
        "dont": "don't",
        "wont": "won't",
        "cant": "can't",
        "couldnt": "couldn't",
        "wouldnt": "wouldn't",
        "shouldnt": "shouldn't",
        "isnt": "isn't",
        "arent": "aren't",
        "wasnt": "wasn't",
        "werent": "weren't",
        "hasnt": "hasn't",
        "havent": "haven't",
        "hadnt": "hadn't",
        "im": "I'm",
        "ive": "I've",
        "id": "I'd",
        "ill": "I'll",
        "hes": "he's",
        "shes": "she's",
        "its": "it's",
        "theyre": "they're",
        "theyve": "they've",
        "theyd": "they'd",
        "thatll": "that'll",
        "whats": "what's",
        "wheres": "where's",
        "whos": "who's",
        "whenre": "when're",
        "howre": "how're",
        "whyre": "why're",
        "gonna": "going to",
        "wanna": "want to",
        "gotta": "got to",
        "hafta": "have to",
        "needta": "need to",
        "outta": "out of",
        "kinda": "kind of",
        "sorta": "sort of",
        "gimme": "give me",
        "lemme": "let me",
        "gotcha": "got you",
        "wanna": "want to",
        "dunno": "don't know",
        "innit": "isn't it",
        "ain't": "isn't",
    }

    # 上下文触发规则：(错误词, 正确词, 上下文关键词)
    CONTEXT_RULES = [
        ("bench", "bank", ["money", "deposit", "withdraw", "loan", "account", "cash", "bank", "credit", "debit"]),
        ("meat", "meet", ["you", "him", "her", "them", "today", "tomorrow", "later", "yesterday", "tonight"]),
        ("there", "their", ["house", "car", "book", "money", "home", "family", "dog", "cat", "child"]),
        ("there", "they're", ["coming", "going", "here", "arriving", "leaving", "talking", "walking"]),
        ("to", "too", ["much", "many", "late", "early", "young", "old", "small", "big"]),
        ("two", "too", ["much", "many", "late", "early", "also", "as well"]),
        ("two", "to", ["go", "come", "walk", "run", "talk", "write", "read"]),
        ("for", "four", ["one", "two", "three", "five", "six", "seven", "eight", "nine", "ten", "number"]),
        ("four", "for", ["you", "me", "him", "her", "them", "us", "it", "buy", "sell", "give", "take"]),
        ("right", "write", ["letter", "email", "note", "document", "paper", "pen", "pencil", "keyboard"]),
        ("write", "right", ["correct", "yes", "okay", "direction", "turn", "way", "answer"]),
        ("no", "know", ["what", "who", "where", "when", "why", "how", "don't", "didn't"]),
        ("know", "no", ["thanks", "problem", "way", "time", "chance", "doubt"]),
        ("were", "where", ["is", "are", "was", "be", "going", "coming", "located", "find"]),
        ("where", "were", ["you", "they", "we", "people", "children", "animals", "at", "in", "there"]),
        ("than", "then", ["and", "after", "before", "next", "later", "soon", "when"]),
        ("then", "than", ["bigger", "smaller", "better", "worse", "more", "less", "older", "younger"]),
    ]

    # 常见英文缩写展开规则
    CONTRACTIONS = {
        "im": "I'm",
        "ive": "I've",
        "id": "I'd",
        "ill": "I'll",
        "youre": "you're",
        "youve": "you've",
        "youd": "you'd",
        "youll": "you'll",
        "hes": "he's",
        "hes": "he has",
        "shes": "she's",
        "its": "it's",
        "theyre": "they're",
        "theyve": "they've",
        "theyd": "they'd",
        "theyll": "they'll",
        "were": "we're",
        "weve": "we've",
        "wed": "we'd",
        "well": "we'll",
        "dont": "don't",
        "doesnt": "doesn't",
        "didnt": "didn't",
        "isnt": "isn't",
        "arent": "aren't",
        "wasnt": "wasn't",
        "werent": "weren't",
        "hasnt": "hasn't",
        "havent": "haven't",
        "hadnt": "hadn't",
        "wont": "won't",
        "wouldnt": "wouldn't",
        "couldnt": "couldn't",
        "shouldnt": "shouldn't",
        "cant": "can't",
        "mustnt": "mustn't",
        "neednt": "needn't",
        "daren't": "daren't",
        "mightnt": "mightn't",
        "oughtnt": "oughtn't",
        "shant": "shan't",
    }

    @classmethod
    def correct(cls, text: str, context: str = "") -> Optional[str]:
        """
        修正文本中的错误

        Args:
            text: 待修正的文本
            context: 上下文文本

        Returns:
            修正后的文本，如果没有修正则返回 None
        """
        if not text:
            return None

        original = text
        corrected = text

        # 1. 标准化处理：去除多余空格和换行
        corrected = re.sub(r'\s+', ' ', corrected).strip()

        # 2. 修复常见的语音识别错误（基于发音相似性）
        corrected = cls._fix_pronunciation_errors(corrected)

        # 3. 先应用简单单词替换
        for wrong, correct in cls.WORD_CORRECTIONS.items():
            # 使用单词边界匹配，避免部分匹配
            pattern = r'\b' + re.escape(wrong) + r'\b'
            if re.search(pattern, corrected, re.IGNORECASE):
                corrected = re.sub(pattern, correct, corrected, flags=re.IGNORECASE)

        # 4. 应用上下文规则
        context_lower = context.lower()
        for wrong, correct, triggers in cls.CONTEXT_RULES:
            pattern = r'\b' + re.escape(wrong) + r'\b'
            if re.search(pattern, corrected, re.IGNORECASE):
                # 检查上下文是否包含触发词
                if any(trigger in context_lower for trigger in triggers):
                    corrected = re.sub(pattern, correct, corrected, flags=re.IGNORECASE)

        # 5. 修复缩写
        corrected = cls._fix_contractions(corrected)

        # 6. 修复大小写问题
        corrected = cls._fix_capitalization(corrected)

        # 7. 修复标点问题
        corrected = cls._fix_punctuation(corrected)

        # 8. 去除重复单词（语音识别常见问题）
        corrected = cls._remove_repeats(corrected)

        # 9. 修复常见语法错误
        corrected = cls._fix_grammar(corrected)

        return corrected if corrected != original else None

    @classmethod
    def _fix_pronunciation_errors(cls, text: str) -> str:
        """修复基于发音相似性的常见错误"""
        # 发音相似的单词替换
        pronunciation_fixes = {
            # 基于英语发音相似性
            r'\b([bcdfghjklmnpqrstvwxyz]+)our\b': r'\1or',  # 英式/美式差异
            r'\bthru\b': 'through',
            r'\btho\b': 'though',
            r'\baltho\b': 'although',
            r'\bcuz\b': 'because',
            r'\btell\b': 'tell',
            r'\btold\b': 'told',
            r'\bwould of\b': 'would have',
            r'\bcould of\b': 'could have',
            r'\bshould of\b': 'should have',
            r'\bmight of\b': 'might have',
            r'\bmust of\b': 'must have',
        }
        
        result = text
        for pattern, replacement in pronunciation_fixes.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def _fix_contractions(cls, text: str) -> str:
        """修复缩写形式"""
        result = text
        for wrong, correct in cls.CONTRACTIONS.items():
            pattern = r'\b' + re.escape(wrong) + r'\b'
            result = re.sub(pattern, correct, result, flags=re.IGNORECASE)
        return result

    @classmethod
    def _fix_capitalization(cls, text: str) -> str:
        """修复大小写问题"""
        if not text:
            return text

        # 首字母大写
        result = text[0].upper() + text[1:]
        
        # 句子结尾后的首字母大写
        result = re.sub(r'([.!?])\s*([a-z])', lambda m: m.group(1) + ' ' + m.group(2).upper(), result)
        
        # I 应该大写
        result = re.sub(r'\bi\b', 'I', result)
        
        # I'm, I've, I'd, I'll 等应该大写
        result = re.sub(r'\bi\'([mvd]|ll)\b', lambda m: 'I' + m.group(0)[1:], result)
        
        return result

    @classmethod
    def _fix_punctuation(cls, text: str) -> str:
        """修复标点问题"""
        result = text
        
        # 确保句子结尾有标点（如果看起来是完整句子）
        if len(result) > 0 and result[-1] not in '.!?。！？':
            # 检查是否看起来像完整句子
            if len(result.split()) >= 3:
                result = result + '.'
        
        # 去除重复标点
        result = re.sub(r'([.!?]){2,}', r'\1', result)
        
        # 标点后应该有空格
        result = re.sub(r'([.!?])([A-Za-z])', r'\1 \2', result)
        
        return result

    @classmethod
    def _remove_repeats(cls, text: str) -> str:
        """去除重复单词（语音识别常见问题）"""
        # 去除连续重复的单词
        result = re.sub(r'\b(\w+)\s+\1\b', r'\1', text)
        return result

    @classmethod
    def _fix_grammar(cls, text: str) -> str:
        """修复常见语法错误"""
        result = text
        
        # 修复主谓一致问题
        fixes = [
            (r'\bhe don\'t\b', 'he doesn\'t'),
            (r'\bshe don\'t\b', 'she doesn\'t'),
            (r'\bit don\'t\b', 'it doesn\'t'),
            (r'\bthey don\'t\b', 'they don\'t'),  # 正确的，保持不变
            (r'\bwe don\'t\b', 'we don\'t'),      # 正确的，保持不变
            (r'\byou don\'t\b', 'you don\'t'),    # 正确的，保持不变
            (r'\bi don\'t\b', 'I don\'t'),        # 正确的，保持不变
        ]
        
        for pattern, replacement in fixes:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result


class CorrectionManager:
    """修正管理器"""

    def __init__(self, window_seconds: int = 15):
        self.window = CorrectionWindow(window_seconds)
        self.corrector = SimpleCorrector()
        self.on_correction: Optional[Callable] = None
        self.window._correction_callback = self._on_correction

    def add_recognition(self, text: str) -> Optional[TextSegment]:
        """添加新的识别结果"""
        return self.window.add_segment(text)

    async def correct_last(self) -> Optional[str]:
        """修正最后一个片段"""
        last = self.window.get_last_segment()
        if not last or last.is_corrected:
            return None

        # 获取完整上下文
        context = self.window.get_all_text()

        # 尝试修正
        corrected = self.corrector.correct(last.text, context)

        if corrected and corrected != last.text:
            # 找到索引并修正
            for i, seg in enumerate(self.window.segments):
                if seg is last:
                    self.window.correct_segment(i, corrected, last.text)
                    return corrected

        return None

    async def correct_all(self) -> List[str]:
        """修正所有未修正的片段"""
        results = []
        for i, seg in enumerate(self.window.segments):
            if not seg.is_corrected:
                context = self.window.get_all_text()
                corrected = self.corrector.correct(seg.text, context)
                if corrected and corrected != seg.text:
                    self.window.correct_segment(i, corrected, seg.text)
                    results.append(corrected)
        return results

    def _on_correction(self, index: int, segment: TextSegment):
        """修正回调"""
        if self.on_correction:
            original = segment.original_text or "未知"
            self.on_correction(index, original, segment.text)

    def get_current_text(self) -> str:
        """获取当前文本"""
        return self.window.get_all_text()

    def get_segments(self) -> List[Dict]:
        """获取片段信息"""
        return self.window.get_segments_for_display()


# ========== 测试代码 ==========
async def test_correction():
    """测试修正机制"""
    print("测试修正机制模块...\n")

    manager = CorrectionManager(window_seconds=10)

    # 设置回调
    def on_correction(index, original, corrected):
        print(f"   🔄 修正 [索引 {index}]: '{original}' → '{corrected}'")

    manager.on_correction = on_correction

    # 测试场景 1：bench → bank（有 money 上下文）
    print("1. 测试场景：bench -> bank（上下文包含 money）")
    manager.add_recognition("I went to the bench")
    manager.add_recognition("to deposit money")

    print(f"   原始文本: {manager.get_current_text()}")

    # 修正第一个片段
    first_seg = manager.window.segments[0]
    corrected = manager.corrector.correct(first_seg.text, manager.get_current_text())
    if corrected:
        manager.window.correct_segment(0, corrected, first_seg.text)

    print(f"   修正后文本: {manager.get_current_text()}\n")

    # 重置
    manager = CorrectionManager(window_seconds=10)
    manager.on_correction = on_correction

    # 测试场景 2：to 不应该被错误修正
    print("2. 测试场景：正确文本应该保持不变")
    manager.add_recognition("Hello")
    manager.add_recognition("how are you")

    print(f"   原始文本: {manager.get_current_text()}")

    # 尝试修正所有
    results = await manager.correct_all()
    if results:
        print(f"   ⚠️ 意外的修正: {results}")
    else:
        print(f"   ✅ 无需修正，文本保持不变")

    print(f"   最终文本: {manager.get_current_text()}\n")

    # 测试场景 3：批量修正
    print("3. 显示所有片段详情:")
    for i, seg in enumerate(manager.get_segments()):
        status = "✅已修正" if seg['is_corrected'] else "⏳未修正"
        original = f" (原: {seg['original']})" if seg['original'] else ""
        print(f"   [{i}] {seg['text']} {status}{original}")

    print("\n✅ 修正机制测试完成")


if __name__ == "__main__":
    asyncio.run(test_correction())