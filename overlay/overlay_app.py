#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
悬浮字幕应用 - 显示实时翻译结果
"""

import sys
import os
import time
import json
import requests
import threading

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QLabel, QVBoxLayout,
        QHBoxLayout, QSizePolicy
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
    from PyQt5.QtGui import QFont, QColor
except ImportError:
    print("请安装 PyQt5: pip install pyqt5")
    sys.exit(1)

API_BASE_URL = "http://localhost:5000"

class TranscriptionHistory:
    """管理翻译历史记录"""
    
    def __init__(self, max_entries=10):
        self.entries = []
        self.max_entries = max_entries
    
    def add(self, index, original, translation, timestamp):
        entry = {
            'index': index,
            'original': original,
            'translation': translation,
            'timestamp': timestamp
        }
        self.entries.append(entry)
        
        # 保持最大记录数
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)
    
    def get_latest(self, count=3):
        """获取最近的记录"""
        return self.entries[-count:]
    
    def clear(self):
        self.entries = []

class OverlayWindow(QWidget):
    """悬浮字幕窗口"""
    
    new_transcription = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.history = TranscriptionHistory(max_entries=10)
        self.init_ui()
        self.init_polling()
        
        # 连接信号
        self.new_transcription.connect(self.update_subtitles)
    
    def init_ui(self):
        # 设置窗口属性 - 无边框、置顶、透明背景
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # 设置布局
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(self.layout)
        
        # 创建字幕标签
        self.subtitle_labels = []
        for i in range(3):
            label = QLabel()
            label.setFont(QFont('Microsoft YaHei', 24, QFont.Bold))
            label.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: rgba(0, 0, 0, 0.7);
                    padding: 8px 16px;
                    border-radius: 8px;
                }
            """)
            label.setAlignment(Qt.AlignCenter)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            label.setWordWrap(True)
            self.subtitle_labels.append(label)
            self.layout.addWidget(label)
        
        # 设置初始位置（屏幕底部居中）
        self.resize(800, 150)
        self.move_to_bottom_center()
        
        # 监听鼠标事件用于拖动
        self.dragging = False
        self.drag_start = None
    
    def move_to_bottom_center(self):
        """将窗口移动到屏幕底部居中位置"""
        screen_geometry = QApplication.desktop().screenGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = screen_geometry.height() - self.height() - 50
        self.move(x, y)
    
    def update_subtitles(self, data):
        """更新字幕显示"""
        # 添加到历史
        self.history.add(
            data.get('index', 0),
            data.get('original', ''),
            data.get('translation', ''),
            data.get('timestamp', '')
        )
        
        # 获取最近3条记录
        latest = self.history.get_latest(3)
        
        # 更新标签
        for i, label in enumerate(self.subtitle_labels):
            if i < len(latest):
                entry = latest[i]
                text = f"{entry['translation']}"
                label.setText(text)
                label.show()
            else:
                label.hide()
    
    def init_polling(self):
        """初始化轮询线程"""
        self.polling_thread = threading.Thread(target=self.polling_loop, daemon=True)
        self.polling_thread.start()
    
    def polling_loop(self):
        """轮询后端获取翻译结果"""
        last_index = 0
        
        while True:
            try:
                # 轮询获取最新翻译
                response = requests.get(
                    f"{API_BASE_URL}/api/translations",
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data and isinstance(data, list):
                        # 查找未显示的新记录
                        for entry in data:
                            if entry.get('index', 0) > last_index:
                                last_index = entry['index']
                                # 发送信号更新UI
                                self.new_transcription.emit(entry)
            
            except Exception as e:
                # 连接失败时打印日志但继续轮询
                print(f"[Polling] 连接失败: {str(e)}")
            
            # 每100ms轮询一次（优化同步速度）
            time.sleep(0.1)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_start = event.globalPos() - self.pos()
    
    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPos() - self.drag_start)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 设置应用程序属性
    app.setApplicationName('AI Translation Overlay')
    app.setQuitOnLastWindowClosed(True)
    
    window = OverlayWindow()
    window.show()
    
    print("🖥️  悬浮字幕窗口已启动")
    print("💡 提示：可以拖动窗口到任意位置")
    
    sys.exit(app.exec_())