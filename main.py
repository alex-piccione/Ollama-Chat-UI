"""
Entry point for Ollama Chat UI.
"""
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from chat_window import ChatWindow


def main() -> None:
    # Enable High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Ollama Chat")
    app.setOrganizationName("OllamaChat")

    window = ChatWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
