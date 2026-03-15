# Minecraft Wiki Chatbot

A voice-activated, local AI assistant for Minecraft that answers questions by searching a local copy of the Minecraft Wiki.

## Features

- **Voice Interface**: Uses `faster-whisper` for Speech-to-Text (STT) and `KittenTTS` for Text-to-Speech (TTS).
- **Local RAG**: Employs a "Retrieval-Augmented Generation" approach using `ripgrep` to search through Markdown-formatted wiki pages.
- **Local LLM Integration**: Compatible with LM Studio (or any OpenAI-compatible API) to process queries and generate responses.
- **Wiki Converter**: Includes a utility to transform MediaWiki XML exports into clean Markdown.

## Project Structure

- `bot.py`: The main application loop (Listen -> Search -> Think -> Speak).
- `convert_wiki.py`: Utility to convert a Minecraft Wiki XML dump into searchable Markdown pages.
- `minecraft_markdown_pages/`: Directory containing the converted Markdown wiki pages.
- `pyproject.toml`: Project dependencies and configuration.

## Setup

### Prerequisites

1.  **Python 3.14+**
2.  **LM Studio**: Running a model (e.g., `qwen/qwen3.5-9b`) with the local server enabled.
3.  **ripgrep (`rg`)**: Required for the wiki search tool. Install via `brew install ripgrep` (macOS) or your package manager.
4.  **Pandoc**: Required by the converter. Install via `brew install pandoc`.

### Installation

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install .
```

## Usage

### 1. Preparing the Wiki Data

If you have a MediaWiki XML export:
1.  Update the `input_xml` path in `convert_wiki.py`.
2.  Run the converter:
    ```bash
    python convert_wiki.py
    ```
    This will populate the `minecraft_markdown_pages/` directory.

### 2. Running the Bot

1.  Ensure LM Studio is running and the API URL in `bot.py` (`LM_STUDIO_URL`) matches your setup.
2.  Start the bot:
    ```bash
    python bot.py
    ```
3.  Press **Enter** to speak. Ask questions like "How do I breed villagers?" or "What does a mace do?".

## Configuration

In `bot.py`, you can adjust:
- `LM_STUDIO_URL`: The endpoint for your local LLM.
- `WHISPER_MODEL`: The size of the Whisper model (default: `base.en`).
- `WIKI_DIR`: Path to your Markdown wiki files.

## Dependencies

- `openai`: Client for LLM interaction.
- `faster-whisper`: High-performance STT.
- `kittentts`: Local TTS engine.
- `sounddevice`: For audio recording and playback.
- `ripgrep`: For fast text searching.
