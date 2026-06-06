"""
AI 同声传译 - 桌面悬浮窗
PyQt5 无边框毛玻璃窗口 + SocketIO 实时通信
"""
import sys
import json
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QLabel, QHBoxLayout, QGraphicsDropShadowEffect
)
from PySide6.QtCore import (
    Qt, QTimer, QPoint, Signal, QThread, QObject
)
from PySide6.QtGui import QColor

# 导入 SocketIO 客户端
import socketio

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
    
    # 如果锁文件已存在
    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    if _is_process_running(pid):
                        return False
            # 进程不存在，删除锁文件
            os.remove(lock_file)
        except:
            # 读取失败，删除锁文件
            try:
                os.remove(lock_file)
            except:
                pass
    
    # 创建新的锁文件
    try:
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except:
        return False

# ==================== SocketIO 客户端 ====================
class SocketIOClient(QThread):
    original_received = Signal(str)
    translation_token = Signal(str)
    translation_done = Signal(str)
    status_changed = Signal(bool)
    connected = Signal()
    disconnected = Signal()
    close_requested = Signal()

    def __init__(self, url="http://localhost:5000"):
        super().__init__()
        self.url = url
        print(f"[SocketIO] 连接地址: {self.url}")
        self.sio = None

    def run(self):
        # 创建 SocketIO 客户端
        self.sio = socketio.Client()
        
        @self.sio.event
        def connect():
            print("[SocketIO] 已连接")
            self.connected.emit()
        
        @self.sio.event
        def disconnect():
            print("[SocketIO] 已断开")
            self.disconnected.emit()
            # 3秒后重连
            QTimer.singleShot(3000, self._reconnect)
        
        @self.sio.event
        def connect_error(e):
            print(f"[SocketIO] 连接错误: {e}")
            QTimer.singleShot(3000, self._reconnect)
        
        @self.sio.event
        def captions(data):
            print(f"[SocketIO] 收到 captions 消息: {data}")
            msg_type = data.get('type', '')
            if msg_type == 'original' and 'text' in data:
                print(f"[SocketIO] 提取到原文: {data['text']}")
                self.original_received.emit(data['text'])
            elif msg_type == 'translation' and 'text' in data:
                print(f"[SocketIO] 提取到译文: {data['text']}")
                self.translation_token.emit(data['text'])
            elif msg_type == 'translation-done':
                print(f"[SocketIO] 翻译完成")
        
        @self.sio.event
        def close_overlay():
            print(f"[SocketIO] 收到关闭悬浮窗命令")
            self.close_requested.emit()
        
        # 连接到服务器
        try:
            self.sio.connect(self.url)
            # 保持线程运行
            self.sio.wait()
        except Exception as e:
            print(f"[SocketIO] 连接失败: {e}")
            QTimer.singleShot(3000, self._reconnect)

    def _reconnect(self):
        if self.sio:
            try:
                self.sio.connect(self.url)
            except Exception as e:
                print(f"[SocketIO] 重连失败: {e}")
                QTimer.singleShot(3000, self._reconnect)

    def stop(self):
        if self.sio:
            self.sio.disconnect()


# ==================== 悬浮窗主界面 ====================
class OverlayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        print("[Overlay] 初始化 OverlayWindow...")
        self._drag_pos = None
        self._current_translation = ""

        self._init_ui()
        self._init_socketio()
        print("[Overlay] OverlayWindow 初始化完成")

    def _init_ui(self):
        print("[Overlay] 开始构建 UI...")
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

        self.status_label = QLabel("连接中...")
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
                background: #6b7280;
                border-radius: 4px;
            }
        """)

        self.resize(600, 200)
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            screen.height() - self.height() - 80
        )

    def _init_socketio(self):
        self.sio_client = SocketIOClient()
        self.sio_client.original_received.connect(self._on_original)
        self.sio_client.translation_token.connect(self._on_token)
        self.sio_client.translation_done.connect(self._on_done)
        self.sio_client.connected.connect(self._on_sio_connected)
        self.sio_client.disconnected.connect(self._on_sio_disconnected)
        self.sio_client.close_requested.connect(self._on_close_requested)
        self.sio_client.start()

    def _on_sio_connected(self):
        self.status_label.setText("监听中")
        self.pulse_dot.setStyleSheet("#pulseDot { background: #34d399; border-radius: 4px; }")

    def _on_sio_disconnected(self):
        self.status_label.setText("重连中...")
        self.pulse_dot.setStyleSheet("#pulseDot { background: #6b7280; border-radius: 4px; }")

    def _on_original(self, text):
        self.original_label.setText(text)
        self.original_label.show()
        self.divider.show()

    def _on_token(self, token):
        self._current_translation = token
        self.translated_label.setText(self._current_translation)

    def _on_done(self, full_text):
        self._current_translation = full_text
        self.translated_label.setText(full_text)

    def _on_close_requested(self):
        print("[Overlay] 收到关闭请求，正在关闭悬浮窗...")
        # 停止 SocketIO 客户端
        self.sio_client.stop()
        self.sio_client.wait()
        # 关闭窗口
        self.close()

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
        if hasattr(self, 'sio_client'):
            self.sio_client.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    print("[Overlay] 检查单例...")
    result = check_single_instance()
    print(f"[Overlay] 单例检查结果: {result}")
    if not result:
        print("[Overlay] 已有实例运行中，退出")
        sys.exit(0)

    print("[Overlay] 创建应用...")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    print("[Overlay] 创建窗口...")
    window = OverlayWindow()
    
    print("[Overlay] 显示窗口...")
    window.show()
    print("[Overlay] 窗口已显示")
    
    print("[Overlay] 进入事件循环...")
    sys.exit(app.exec())
