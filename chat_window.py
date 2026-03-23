"""
Main application window for Ollama Chat UI.

Layout
------
┌─────────────────────────────────────────────────────┐
│  🦙 Ollama Chat          [Model ▼]  [New]  [Stop]   │  ← toolbar
├─────────────────────────────────────────────────────┤
│                                                     │
│                   chat display                      │  ← QWebEngineView
│                                                     │
├─────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────┐ [Send ➤]      │  ← input area
│  │  Type a message…                │               │
│  └──────────────────────────────────┘               │
└─────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPalette, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import config
import ollama_client
from chat_widget import ChatWidget

# ---------------------------------------------------------------------------
# Styled sub-widgets
# ---------------------------------------------------------------------------

class _SendBox(QPlainTextEdit):
    """Multi-line input that sends on Enter and inserts newline on Shift+Enter."""

    def __init__(self, on_send, parent=None):
        super().__init__(parent)
        self._on_send = on_send
        self.setPlaceholderText("Type a message… (Enter to send, Shift+Enter for newline)")
        self.setMaximumHeight(120)
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setFont(QFont("Segoe UI", 11))
        self.setStyleSheet("""
            QPlainTextEdit {
                background: #2A2A2A;
                color: #F2F2F2;
                border: 1px solid #333333;
                border-radius: 12px;
                padding: 10px 14px;
                selection-background-color: #FF8C00;
            }
            QPlainTextEdit:focus {
                border: 1px solid #FF8C00;
            }
        """)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self._on_send()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class ChatWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._cfg = config.load()
        self._history: list[dict] = []          # [{role, content}, …]
        self._worker: ollama_client.ChatWorker | None = None
        self._is_streaming = False

        self._build_ui()
        self._load_models()
        self._restore_geometry()
        self._init_log_file()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setWindowTitle("Ollama Chat")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "icon.png")))
        self.setMinimumSize(800, 600)
        self._apply_dark_palette()

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setStyleSheet("""
            QToolBar {
                background: #181818;
                border-bottom: 1px solid #333333;
                padding: 6px 12px;
                spacing: 8px;
            }
        """)
        self.addToolBar(toolbar)

        # Logo label
        logo = QLabel("🦙  <b>Ollama Chat</b>")
        logo.setStyleSheet("color: #F2F2F2; font-size: 15px; padding-right: 16px;")
        toolbar.addWidget(logo)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Model selector
        model_label = QLabel("Model:")
        model_label.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        toolbar.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(220)
        self._model_combo.setStyleSheet("""
            QComboBox {
                background: #2A2A2A;
                color: #F2F2F2;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 5px 12px;
                font-size: 13px;
            }
            QComboBox:hover  { border-color: #FF8C00; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow { image: none; }
            QComboBox QAbstractItemView {
                background: #2A2A2A;
                color: #F2F2F2;
                selection-background-color: #FF8C00;
                border: 1px solid #333333;
                border-radius: 8px;
            }
        """)
        toolbar.addWidget(self._model_combo)

        # New chat button
        self._btn_new = QPushButton("✦  New Chat")
        self._btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_new.clicked.connect(self._new_chat)
        self._btn_new.setStyleSheet(self._btn_style("#333333", "#FF8C00"))
        toolbar.addWidget(self._btn_new)

        # Stop button
        self._btn_stop = QPushButton("⏹  Stop")
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop.clicked.connect(self._stop_generation)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(self._btn_style("#333333", "#c0392b"))
        toolbar.addWidget(self._btn_stop)

        # ── Central widget ───────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet("background: #121212;")

        v_layout = QVBoxLayout(central)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)

        # Chat display
        self._chat = ChatWidget()
        v_layout.addWidget(self._chat, stretch=1)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #333333; max-height: 1px;")
        v_layout.addWidget(sep)

        # ── Input area ───────────────────────────────────────────────────────
        input_frame = QWidget()
        input_frame.setStyleSheet("background: #181818;")
        input_frame.setContentsMargins(0, 0, 0, 0)
        h_input = QHBoxLayout(input_frame)
        h_input.setContentsMargins(16, 12, 16, 14)
        h_input.setSpacing(10)

        self._input = _SendBox(self._send_message)
        h_input.addWidget(self._input)

        self._btn_send = QPushButton("Send ➤")
        self._btn_send.setFixedSize(90, 48)
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.clicked.connect(self._send_message)
        self._btn_send.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #FF8C00, stop:1 #FFB732);
                color: black;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: 600;
                padding: 8px 0;
            }
            QPushButton:hover   { background: #FF9900; }
            QPushButton:pressed { background: #E67E22; }
            QPushButton:disabled{ background: #333333; color: #777777; }
        """)
        h_input.addWidget(self._btn_send, alignment=Qt.AlignmentFlag.AlignBottom)

        v_layout.addWidget(input_frame)

        # ── Status bar ───────────────────────────────────────────────────────
        self._status = QStatusBar()
        self._status.setStyleSheet("""
            QStatusBar {
                background: #181818;
                color: #777777;
                font-size: 12px;
                border-top: 1px solid #333333;
            }
        """)
        self.setStatusBar(self._status)
        self._status.showMessage("Ready")

    # ── Models ───────────────────────────────────────────────────────────────

    def _load_models(self) -> None:
        self._status.showMessage("Fetching models from Ollama…")
        models = ollama_client.list_models()
        self._model_combo.clear()
        if not models:
            self._model_combo.addItem("(no models found)")
            self._status.showMessage("⚠ No models found — is Ollama running?")
            return
        self._model_combo.addItems(models)

        # Restore last-used model
        last = self._cfg.get("last_model")
        if last and last in models:
            self._model_combo.setCurrentText(last)
        else:
            self._model_combo.setCurrentIndex(0)

        self._status.showMessage(f"{len(models)} model(s) available")

    def _current_model(self) -> str:
        return self._model_combo.currentText()

    # ── Chat logic ───────────────────────────────────────────────────────────

    def _send_message(self) -> None:
        if self._is_streaming:
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        model = self._current_model()
        if not model or model.startswith("("):
            self._status.showMessage("Please select a valid model first.")
            return

        # Save last-used model
        self._cfg["last_model"] = model
        config.save(self._cfg)

        self._input.clear()
        self._history.append({"role": "user", "content": text})
        self._chat.add_user_message(text)
        self._log_message("user", text)

        self._set_streaming(True)
        self._chat.begin_assistant_stream()
        self._status.showMessage(f"Generating with {model}…")

        self._worker = ollama_client.ChatWorker(model, list(self._history))
        self._worker.token.connect(self._chat.append_token)
        self._worker.finished.connect(self._on_stream_finished)
        self._worker.error.connect(self._on_stream_error)
        self._worker.start()

    def _on_stream_finished(self) -> None:
        # Capture full response text before finalizing
        full_text = self._chat._stream_buffer
        self._chat.finalize_assistant_stream()
        self._history.append({"role": "assistant", "content": full_text})
        self._log_message("assistant", full_text)
        self._set_streaming(False)
        self._status.showMessage("Ready")

    def _on_stream_error(self, message: str) -> None:
        self._chat.finalize_assistant_stream()   # close any open bubble
        self._chat.show_error(message)
        self._set_streaming(False)
        self._status.showMessage(f"Error: {message}")

    def _stop_generation(self) -> None:
        if self._worker and self._is_streaming:
            self._worker.abort()
            self._status.showMessage("Stopped.")

    def _new_chat(self) -> None:
        self._history.clear()
        self._chat.clear()
        self._status.showMessage("New conversation started")
        self._input.setFocus()
        self._init_log_file()

    def _set_streaming(self, streaming: bool) -> None:
        self._is_streaming = streaming
        self._btn_send.setEnabled(not streaming)
        self._btn_stop.setEnabled(streaming)
        self._input.setEnabled(not streaming)

    # ── Logging ──────────────────────────────────────────────────────────────

    def _init_log_file(self) -> None:
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._current_log_file = log_dir / f"chat_{timestamp}.txt"
        try:
            with open(self._current_log_file, "w", encoding="utf-8") as f:
                f.write(f"--- Chat Session Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n\n")
        except OSError:
            pass

    def _log_message(self, role: str, content: str) -> None:
        if not hasattr(self, "_current_log_file"):
            self._init_log_file()
        try:
            with open(self._current_log_file, "a", encoding="utf-8") as f:
                f.write(f"[{role.upper()}]\n{content}\n\n")
        except OSError:
            pass

    # ── Window geometry ──────────────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        w = self._cfg.get("window_width", 1100)
        h = self._cfg.get("window_height", 780)
        self.resize(w, h)
        x = self._cfg.get("window_x")
        y = self._cfg.get("window_y")
        if x is not None and y is not None:
            self.move(x, y)
        else:
            # Center on screen
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(
                (screen.width() - w) // 2,
                (screen.height() - h) // 2,
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        geo = self.geometry()
        self._cfg["window_width"] = geo.width()
        self._cfg["window_height"] = geo.height()
        self._cfg["window_x"] = geo.x()
        self._cfg["window_y"] = geo.y()
        config.save(self._cfg)
        if self._worker and self._is_streaming:
            self._worker.abort()
            self._worker.wait(1000)
        super().closeEvent(event)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _btn_style(bg: str, hover: str) -> str:
        return f"""
            QPushButton {{
                background: {bg};
                color: #F2F2F2;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 6px 14px;
                font-size: 13px;
            }}
            QPushButton:hover   {{ background: {hover}; color: white; border-color: {hover}; }}
            QPushButton:pressed {{ opacity: 0.85; }}
            QPushButton:disabled{{ color: #777777; }}
        """

    @staticmethod
    def _apply_dark_palette() -> None:
        pal = QPalette()
        dark = QColor("#121212")
        pal.setColor(QPalette.ColorRole.Window, dark)
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#F2F2F2"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#2A2A2A"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1F1F1F"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, dark)
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#F2F2F2"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#F2F2F2"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#2A2A2A"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#F2F2F2"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#FF8C00"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
        QApplication.setPalette(pal)
