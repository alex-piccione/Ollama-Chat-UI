"""
Async wrapper around the `ollama` Python library.

Runs blocking Ollama calls in a QThread so the UI never freezes.
Emits Qt signals for:
  - each streamed token (chunk)
  - completion
  - errors
"""
from __future__ import annotations

import ollama
from PyQt6.QtCore import QThread, pyqtSignal

# ---------------------------------------------------------------------------
# Model listing (synchronous, fast)
# ---------------------------------------------------------------------------

def list_models() -> list[str]:
    """Return sorted list of locally available model names."""
    try:
        response = ollama.list()
        models = [m.model for m in response.models]
        return sorted(models)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Streaming chat worker
# ---------------------------------------------------------------------------

class ChatWorker(QThread):
    """
    Runs a streaming chat request in a background thread.

    Signals
    -------
    token(str)      — emitted for each streamed token
    finished()      — emitted when the full response is done
    error(str)      — emitted on any exception
    """

    token: pyqtSignal = pyqtSignal(str)
    finished: pyqtSignal = pyqtSignal()
    error: pyqtSignal = pyqtSignal(str)

    def __init__(self, model: str, messages: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._messages = messages
        self._abort = False

    def abort(self) -> None:
        """Request cancellation (best-effort)."""
        self._abort = True

    def run(self) -> None:
        try:
            stream = ollama.chat(
                model=self._model,
                messages=self._messages,
                stream=True,
            )
            for chunk in stream:
                if self._abort:
                    break
                text = chunk.message.content or ""
                if text:
                    self.token.emit(text)
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))
