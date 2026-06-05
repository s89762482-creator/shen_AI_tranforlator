"""
AI 同声传译 - 桌面悬浮窗
PyQt5 无边框毛玻璃窗口 + WebSocket 实时通信
"""
import sys
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QHBoxLayout, QGraphicsDropShadowEffect
)
from PySide6.QtCore import (
    Qt, QTimer, QPoint, Signal, QThread,
    QPropertyAnimation, QEasingCurve, QUrl
)
from PySide6.QtGui import QColor
from PySide6.QtWebSockets import QWebSocket

# ==================== WebSocket 客户端 ====================
class WebSocketClient(QThread):
    original_received = Signal(str)
    translation_token = Signal(str)
    translation_done = Signal(str)
    status_changed = Signal(bool)
    connected = Signal()
    disconnected = Signal()

    def __init__(self, url="ws://127.0.0.1:5000"):
        super().__init__()
        self.url = url
        self.ws = None
        self._buffer = ""

    def run(self):
        self.ws = QWebSocket()
        self.ws.connected.connect(self._on_connected)
        self.ws.disconnected.connect(self._on_disconnected)
        self.ws.textMessageReceived.connect(self._on_message)
        self.ws.open(QUrl(self.url))

    def _on_connected(self):
        print("[WS] 已连接")
        self.connected.emit()

    def _on_disconnected(self):
        print("[WS] 已断开, 3秒后重连...")
        self.disconnected.emit()
        QTimer.singleShot(3000, self._reconnect)

    def _reconnect(self):
        if self.ws:
            self.ws.open(QUrl(self.url))

    def _on_message(self, message):
        try:
            data = json.loads(message)
            if 'text' in data and 'engine' in data:
                self.original_received.emit(data['text'])
            elif 'token' in data:
                self.translation_token.emit(data['token'])
            elif 'original' in data and 'translated' in data:
                self.original_received.emit(data['original'])
                self.translation_done.emit(data['translated'])
        except:
            pass

    def stop(self):
        if self.ws:
            self.ws.close()


# ==================== 悬浮窗主界面 ====================
class OverlayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._drag_pos = None
        self._current_translation = ""

        self._init_ui()
        self._init_websocket()

    def _init_ui(self):
        self.setWindowTitle("翻译字幕")
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # 主控件
        self.central = QWidget()
        self.central.setObjectName("mainContainer")
        self.setCentralWidget(self.central)

        self.main_layout = QVBoxLayout(self.central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 内容容器
        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentWidget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(24, 20, 24, 18)
        self.content_layout.setSpacing(10)

        # 原文
        self.original_label = QLabel()
        self.original_label.setObjectName("originalLabel")
        self.original_label.setAlignment(Qt.AlignCenter)
        self.original_label.setWordWrap(True)
        self.original_label.setMaximumWidth(700)
        self.original_label.hide()

        # 分隔线
        self.divider = QWidget()
        self.divider.setObjectName("divider")
        self.divider.setFixedHeight(1)
        self.divider.setFixedWidth(40)
        self.divider.hide()

        # 译文
        self.translated_label = QLabel()
        self.translated_label.setObjectName("translatedLabel")
        self.translated_label.setAlignment(Qt.AlignCenter)
        self.translated_label.setWordWrap(True)
        self.translated_label.setMaximumWidth(700)

        # 状态栏
        self.status_widget = QWidget()
        self.status_widget.setObjectName("statusWidget")
        status_layout = QHBoxLayout(self.status_widget)
        status_layout.setContentsMargins(12, 7, 12, 7)
        status_layout.setSpacing(8)

        self.pulse_dot = QLabel()
        self.pulse_dot.setObjectName("pulseDot")
        self.pulse_dot.setFixedSize(8, 8)

        self.status_label = QLabel("监听中")
        self.status_label.setObjectName("statusLabel")

        status_layout.addStretch()
        status_layout.addWidget(self.pulse_dot)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        # 组装
        self.content_layout.addWidget(self.original_label)
        self.content_layout.addWidget(self.divider, 0, Qt.AlignCenter)
        self.content_layout.addWidget(self.translated_label)

        self.main_layout.addWidget(self.content_widget)
        self.main_layout.addSpacing(12)
        self.main_layout.addWidget(self.status_widget, 0, Qt.AlignCenter)

        # 阴影
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 8)
        self.content_widget.setGraphicsEffect(shadow)

        # 样式
        self.setStyleSheet("""
            #contentWidget {
                background: rgba(22, 22, 30, 0.82);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
            }
            #originalLabel {
                color: rgba(255, 255, 255, 0.5);
                font-size: 14px;
                font-weight: 400;
                font-family: -apple-system, "Microsoft YaHei", sans-serif;
                padding: 2px 0;
            }
            #divider {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 transparent,
                    stop:0.5 rgba(255,255,255,0.12),
                    stop:1 transparent
                );
            }
            #translatedLabel {
                color: #ffffff;
                font-size: 20px;
                font-weight: 700;
                font-family: -apple-system, "Microsoft YaHei", sans-serif;
                padding: 2px 0;
            }
            #statusWidget {
                background: rgba(10, 10, 16, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 16px;
            }
            #statusLabel {
                color: rgba(255, 255, 255, 0.35);
                font-size: 10px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            #pulseDot {
                background: #34d399;
                border-radius: 4px;
            }
        """)

        self.resize(600, 200)
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            screen.height() - self.height() - 80
        )

    def _init_websocket(self):
        self.ws_client = WebSocketClient()
        self.ws_client.original_received.connect(self._on_original)
        self.ws_client.translation_token.connect(self._on_token)
        self.ws_client.translation_done.connect(self._on_done)
        self.ws_client.connected.connect(self._on_ws_connected)
        self.ws_client.disconnected.connect(self._on_ws_disconnected)
        self.ws_client.start()

    def _on_ws_connected(self):
        self.status_label.setText("监听中")
        self.pulse_dot.setStyleSheet("#pulseDot { background: #34d399; border-radius: 4px; }")

    def _on_ws_disconnected(self):
        self.status_label.setText("重连中...")
        self.pulse_dot.setStyleSheet("#pulseDot { background: #6b7280; border-radius: 4px; }")

    def _on_original(self, text):
        self.original_label.setText(text)
        self.original_label.show()
        self.divider.show()

    def _on_token(self, token):
        self._current_translation += token
        self.translated_label.setText(self._current_translation)

    def _on_done(self, full_text):
        self._current_translation = full_text
        self.translated_label.setText(full_text)

    # ---------- 拖拽 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        if hasattr(self, 'ws_client'):
            self.ws_client.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = OverlayWindow()
    window.show()

    sys.exit(app.exec_())