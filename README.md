# Ollama Chat UI

A desktop chat interface for [Ollama](https://ollama.com/) with streaming responses and Markdown rendering, built with PyQt6.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running locally (`ollama serve`)
- At least one model pulled, e.g. `ollama pull llama3`

## Installation

```bash
# Clone or download the project, then:
cd "Ollama-Chat-UI"

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows (CMD):
.venv\Scripts\activate
# /Windows (bash):
source .venv/Scripts/activate
# macOS/Linux/Windows (bash):
source .venv/bin/activate

# Install the app (and optionally dev tools)
pip install -e .          # runtime only
pip install -e ".[dev]"   # includes ruff + mypy
```

## Usage

```bash
ollama-chat
```

The app will automatically detect locally available models from Ollama.

## Development

```bash
# Lint
ruff check .

# Type-check
mypy .
```
