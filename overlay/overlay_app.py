"""
AI 同声传译 - 桌面悬浮窗
PySide6 无边框毛玻璃窗口 + QTimer 主线程文件轮询
"""
import sys
import json
import os
import tempfile
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QHBoxLayout, QGraphicsDropShadowEffect, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor


def _is_process_running(pid):
    try:
        if os.name == 'nt':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle != 0:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            return os.path.exists(f'/proc/{pid}')
    except:
        return False


def check_single_instance():
    lock_file = os.path.join(os.path.dirname(__file__), 'overlay.lock')
    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    if _is_process_running(pid):
                        return False
            os.remove(lock_file)
        except:
            try:
                os.remove(lock_file)
            except:
                pass
    try:
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except:
        return False


# 字幕缓存文件路径（与后端一致，使用项目根目录）
CAPTION_CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'caption_cache.json')
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'overlay_debug.log')

def _log(msg):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            import datetime
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}\n")
    except:
        pass


class OverlayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._drag_pos = None
        self._current_translation = ""
        self._last_timestamp = 0
        self._first_caption = True

        self._init_ui()
        self._start_polling()

    def _init_ui(self):
        self.setWindowTitle("翻译字幕")
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
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

        # 关闭按钮
        self.close_button = QPushButton("x")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(self.close)
        self.content_layout.addWidget(self.close_button, 0, Qt.AlignTop | Qt.AlignRight)

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
        self.translated_label = QLabel("等待翻译...")
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
                font-family: "Microsoft YaHei", sans-serif;
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
                font-family: "Microsoft YaHei", sans-serif;
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
            #closeButton {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 8px;
                color: rgba(255, 255, 255, 0.6);
                font-size: 20px;
                font-weight: 300;
                padding: 0;
                margin: 0;
            }
            #closeButton:hover {
                background: rgba(239, 68, 68, 0.6);
                color: #ffffff;
            }
        """)

        self.resize(600, 200)

        screen = QApplication.primaryScreen().availableGeometry()
        window_x = (screen.width() - self.width()) // 2
        window_y = screen.height() - self.height() - 120
        self.move(window_x, window_y)
        
        # Windows API: 强制置顶
        try:
            import ctypes
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            ctypes.windll.user32.SetWindowPos(
                int(self.winId()), HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE
            )
        except Exception:
            pass

    def _start_polling(self):
        """使用 QTimer 在主线程中轮询文件，避免线程问题"""
        _log("QTimer 轮询启动")
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_file)
        self._poll_timer.start(50)  # 每 50ms 轮询一次

    def _poll_file(self):
        """主线程中读取字幕文件并更新 UI"""
        try:
            if not os.path.exists(CAPTION_CACHE_FILE):
                return

            with open(CAPTION_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            timestamp = data.get('timestamp', 0)
            if timestamp <= self._last_timestamp:
                return

            self._last_timestamp = timestamp
            msg_type = data.get('type', '')
            original = data.get('original', '')
            translation = data.get('translation', '')

            _log(f"新字幕: type={msg_type}, original={original[:30]}, translation={translation[:30]}")

            # 更新原文
            if original and original.strip():
                self.original_label.setText(original)
                if not self.original_label.isVisible():
                    self.original_label.show()
                    self.divider.show()
            
            # 更新译文
            if translation and translation.strip():
                self._current_translation = translation
                self.translated_label.setText(translation)
                self.translated_label.repaint()
                # 确保窗口可见
                if not self.isVisible():
                    self.show()
                self.raise_()
                QApplication.processEvents()
                _log(f"UI已更新: {translation[:50]}")

        except (json.JSONDecodeError, Exception) as e:
            _log(f"轮询错误: {e}")

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
        if hasattr(self, '_poll_timer'):
            self._poll_timer.stop()
        lock_file = os.path.join(os.path.dirname(__file__), 'overlay.lock')
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    if not check_single_instance():
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = OverlayWindow()
    window.show()

    sys.exit(app.exec())