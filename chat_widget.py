"""
Chat display widget using QWebEngineView.

Renders messages as styled HTML bubbles with full markdown support.
New content is injected via JavaScript so the page never reloads.
"""
from __future__ import annotations

import html

import markdown2
from PyQt6.QtCore import QUrl, pyqtSlot
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QSizePolicy

# ---------------------------------------------------------------------------
# HTML page template — loaded once at startup
# ---------------------------------------------------------------------------

_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chat</title>
<link rel="stylesheet"
  href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
  :root {
    --bg:           #121212;
    --surface:      #1F1F1F;
    --surface2:     #2A2A2A;
    --accent:       #FF8C00;
    --accent-glow:  rgba(255,140,0,0.25);
    --user-bg:      #FF8C00;
    --user-fg:      #000000;
    --bot-bg:       #2A2A2A;
    --bot-fg:       #F2F2F2;
    --text-muted:   #777777;
    --border:       #333333;
    --radius:       18px;
    --font:         'Segoe UI', system-ui, -apple-system, sans-serif;
    --mono:         'Cascadia Code', 'Consolas', monospace;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  html, body {
    background: var(--bg);
    color: var(--bot-fg);
    font-family: var(--font);
    font-size: 15px;
    line-height: 1.65;
    height: 100%;
    overflow-x: hidden;
  }

  #chat {
    display: flex;
    flex-direction: column;
    gap: 18px;
    padding: 24px 20px 36px;
    min-height: 100%;
  }

  /* ── Row wrapper ── */
  .msg-row {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    animation: fadeSlide 0.22s ease;
  }
  .msg-row.user  { flex-direction: row-reverse; }
  .msg-row.bot   { flex-direction: row; }

  @keyframes fadeSlide {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* ── Avatar ── */
  .avatar {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
    user-select: none;
  }
  .msg-row.user .avatar { background: var(--accent); }
  .msg-row.bot  .avatar { background: var(--surface2); border: 1px solid var(--border); }

  /* ── Bubble ── */
  .bubble-wrapper {
    position: relative;
    max-width: min(680px, 78%);
  }
  .bubble {
    width: 100%;
    padding: 12px 16px;
    border-radius: var(--radius);
    word-break: break-word;
    overflow-wrap: break-word;
  }
  .msg-row.bot .bubble {
    padding-right: 36px;
  }

  .toggle-raw-btn {
    position: absolute;
    top: 6px;
    right: 6px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 11px;
    font-family: var(--mono);
    padding: 4px;
    border-radius: 4px;
    opacity: 0;
    transition: opacity 0.2s, color 0.2s, background 0.2s;
    z-index: 10;
  }
  .msg-row.bot:hover .toggle-raw-btn {
    opacity: 1;
  }
  .toggle-raw-btn:hover {
    color: var(--bot-fg);
    background: rgba(255, 255, 255, 0.1);
  }
  .toggle-raw-btn.active {
    color: var(--accent);
    opacity: 1;
  }

  .msg-row.user .bubble {
    background: var(--user-bg);
    color: var(--user-fg);
    border-bottom-right-radius: 4px;
    box-shadow: 0 4px 20px var(--accent-glow);
  }
  .msg-row.bot .bubble {
    background: var(--bot-bg);
    color: var(--bot-fg);
    border-bottom-left-radius: 4px;
    border: 1px solid var(--border);
  }

  /* ── Markdown inside bubbles ── */
  .bubble p     { margin: 0 0 8px; }
  .bubble p:last-child { margin-bottom: 0; }
  .bubble h1, .bubble h2, .bubble h3,
  .bubble h4, .bubble h5, .bubble h6 {
    margin: 12px 0 6px;
    font-weight: 600;
    line-height: 1.3;
  }
  .bubble h1 { font-size: 1.4em; }
  .bubble h2 { font-size: 1.2em; }
  .bubble h3 { font-size: 1.05em; }
  .bubble ul, .bubble ol { margin: 6px 0 6px 18px; }
  .bubble li { margin: 2px 0; }
  .bubble strong { font-weight: 700; }
  .bubble em     { font-style: italic; }
  .bubble a      { color: #FFB732; }
  .bubble hr     { border: none; border-top: 1px solid var(--border); margin: 10px 0; }
  .bubble blockquote {
    border-left: 3px solid var(--accent);
    margin: 8px 0;
    padding: 4px 12px;
    color: var(--text-muted);
    font-style: italic;
  }

  /* Inline code */
  .bubble code:not(pre code) {
    background: rgba(0,0,0,0.3);
    border-radius: 4px;
    padding: 1px 5px;
    font-family: var(--mono);
    font-size: 0.88em;
  }
  .msg-row.user .bubble code:not(pre code) {
    background: rgba(255,255,255,0.15);
  }

  /* Code blocks */
  .bubble pre {
    margin: 10px 0;
    border-radius: 10px;
    overflow: hidden;
  }
  .bubble pre code.hljs {
    font-family: var(--mono);
    font-size: 0.85em;
    padding: 14px 16px;
    border-radius: 10px;
    border: 1px solid var(--border);
  }

  /* Tables */
  .bubble table {
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
    font-size: 0.9em;
  }
  .bubble th, .bubble td {
    border: 1px solid var(--border);
    padding: 6px 10px;
    text-align: left;
  }
  .bubble th { background: rgba(0,0,0,0.25); font-weight: 600; }

  /* ── Typing cursor ── */
  .cursor {
    display: inline-block;
    width: 2px;
    height: 1em;
    background: var(--accent);
    margin-left: 2px;
    vertical-align: text-bottom;
    animation: blink 0.8s step-end infinite;
  }
  @keyframes blink {
    50% { opacity: 0; }
  }

  /* ── Error bubble ── */
  .error-bubble {
    background: rgba(220, 60, 60, 0.15);
    border: 1px solid rgba(220, 60, 60, 0.4);
    color: #ff8080;
    border-radius: 10px;
    padding: 10px 14px;
    margin: 0 auto;
    max-width: 600px;
    font-size: 0.9em;
    text-align: center;
    animation: fadeSlide 0.2s ease;
  }

  /* ── Welcome message ── */
  #welcome {
    text-align: center;
    color: var(--text-muted);
    margin: auto;
    padding: 40px 20px;
    user-select: none;
  }
  #welcome .logo { font-size: 52px; margin-bottom: 12px; }
  #welcome h2 { font-size: 1.3em; font-weight: 600; color: var(--bot-fg); margin-bottom: 6px; }
  #welcome p  { font-size: 0.95em; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar       { width: 7px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
</style>
</head>
<body>
<div id="chat">
  <div id="welcome">
    <div class="logo">🦙</div>
    <h2>Ollama Chat</h2>
    <p>Select a model above and start typing to begin.</p>
  </div>
</div>

<script>
  function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  function toggleFormat(btn) {
    const wrapper = btn.closest('.bubble-wrapper');
    const bubble = wrapper.querySelector('.bubble');
    const isRaw = bubble.classList.contains('is-raw');
    if (isRaw) {
      bubble.innerHTML = bubble.dataset.formatted;
      bubble.classList.remove('is-raw');
      btn.classList.remove('active');
    } else {
      bubble.innerHTML = '<pre style="margin:0; white-space:pre-wrap; font-family:var(--mono); color:var(--bot-fg); font-size:0.95em;">' + escapeHtml(bubble.dataset.raw) + '</pre>';
      bubble.classList.add('is-raw');
      btn.classList.add('active');
    }
    hljs.highlightAll();
  }

  // Remove welcome message on first message
  function removeWelcome() {
    const w = document.getElementById('welcome');
    if (w) w.remove();
  }

  // Add a complete, finalized message bubble
  function addMessage(role, htmlContent, rawContent) {
    removeWelcome();
    const chat = document.getElementById('chat');
    const row = document.createElement('div');
    row.className = 'msg-row ' + role;
    const avatar = role === 'user' ? '🧑' : '🦙';
    
    let inner = `<div class="avatar">${avatar}</div>`;
    if (role === 'bot') {
      inner += `
        <div class="bubble-wrapper">
          <button class="toggle-raw-btn" onclick="toggleFormat(this)" title="Toggle Raw Text">&lt;/&gt;</button>
          <div class="bubble">${htmlContent}</div>
        </div>
      `;
    } else {
      inner += `<div class="bubble-wrapper"><div class="bubble">${htmlContent}</div></div>`;
    }
    row.innerHTML = inner;
    
    if (role === 'bot') {
      const bubble = row.querySelector('.bubble');
      bubble.dataset.formatted = htmlContent;
      bubble.dataset.raw = rawContent || '';
    }
    
    chat.appendChild(row);
    hljs.highlightAll();
    row.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  // Begin a streaming bot bubble (returns the bubble element id)
  let _streamId = null;
  let _streamRaw = '';

  function beginStream() {
    removeWelcome();
    _streamRaw = '';
    const chat = document.getElementById('chat');
    _streamId = 'stream_' + Date.now();
    const row = document.createElement('div');
    row.className = 'msg-row bot';
    row.id = _streamId;
    row.innerHTML = `
      <div class="avatar">🦙</div>
      <div class="bubble-wrapper">
        <button class="toggle-raw-btn" onclick="toggleFormat(this)" title="Toggle Raw Text" style="display:none;">&lt;/&gt;</button>
        <div class="bubble"><span class="cursor"></span></div>
      </div>
    `;
    chat.appendChild(row);
    row.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function appendStream(text) {
    if (!_streamId) return;
    _streamRaw += text;
    const row = document.getElementById(_streamId);
    if (!row) return;
    const bubble = row.querySelector('.bubble');
    // Update with raw text + cursor for performance; finalize on endStream
    bubble.textContent = _streamRaw;
    bubble.innerHTML += '<span class="cursor"></span>';
    row.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function endStream(htmlContent) {
    if (!_streamId) return;
    const row = document.getElementById(_streamId);
    if (row) {
      const bubble = row.querySelector('.bubble');
      bubble.innerHTML = htmlContent;
      bubble.dataset.formatted = htmlContent;
      bubble.dataset.raw = _streamRaw;
      
      const btn = row.querySelector('.toggle-raw-btn');
      if (btn) btn.style.display = '';
      
      hljs.highlightAll();
      row.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    _streamId = null;
    _streamRaw = '';
  }

  function showError(msg) {
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = 'error-bubble';
    div.textContent = '⚠️ ' + msg;
    chat.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function clearChat() {
    const chat = document.getElementById('chat');
    chat.innerHTML = `
      <div id="welcome">
        <div class="logo">🦙</div>
        <h2>Ollama Chat</h2>
        <p>Select a model above and start typing to begin.</p>
      </div>`;
    _streamId = null;
    _streamRaw = '';
  }
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Markdown converter (extras for tables, fenced-code, etc.)
# ---------------------------------------------------------------------------

_md = markdown2.Markdown(
    extras=[
        "fenced-code-blocks",
        "tables",
        "strike",
        "task_list",
        "code-friendly",
        "break-on-newline",
    ]
)


def _md_to_html(text: str) -> str:
    return _md.convert(text)


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class ChatWidget(QWebEngineView):
    """Web-based chat display with streaming support."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setHtml(_PAGE_HTML, QUrl("about:blank"))
        self._stream_buffer = ""

    # ── Public API ──────────────────────────────────────────────────────────

    def render_history(self, history: list[dict]) -> None:
        self.clear()
        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                self.add_user_message(content)
            else:
                self.add_assistant_message(content)

    def add_user_message(self, text: str) -> None:
        """Render a user bubble (plain text, escaped)."""
        safe = html.escape(text).replace("\n", "<br>")
        self._run_js(f"addMessage('user', {repr(safe)})")

    def begin_assistant_stream(self) -> None:
        """Start an empty streaming bot bubble."""
        self._stream_buffer = ""
        self._run_js("beginStream()")

    @pyqtSlot(str)
    def append_token(self, token: str) -> None:
        """Append a streamed token (raw text; displayed as-is until finalized)."""
        self._stream_buffer += token
        safe = token.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        self._run_js(f"appendStream(`{safe}`)")

    def add_assistant_message(self, content: str) -> None:
        """Render a completed assistant bubble directly."""
        import json
        html_content = _md_to_html(content)
        self._run_js(f"addMessage('bot', {json.dumps(html_content)}, {json.dumps(content)})")

    def finalize_assistant_stream(self) -> None:
        """Convert accumulated text/markdown to HTML and replace the streaming bubble."""
        import json
        html_content = _md_to_html(self._stream_buffer)
        self._run_js(f"endStream({json.dumps(html_content)})")
        self._stream_buffer = ""

    def show_error(self, message: str) -> None:
        safe = html.escape(message)
        self._run_js(f"showError({repr(safe)})")

    def clear(self) -> None:
        self._stream_buffer = ""
        self._run_js("clearChat()")

    # ── Private ─────────────────────────────────────────────────────────────

    def _run_js(self, script: str) -> None:
        self.page().runJavaScript(script)
