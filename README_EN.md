# YanXi Trans (言蹊翻译)

<p align="left">
  <a href="README.md">简体中文</a> | <b>English</b>
</p>

A lightweight, blazing-fast cross-platform desktop text-selection translation tool supporting Linux (X11) and Windows.

Current source version: **v0.1.9**. See the [release notes (Chinese)](docs/release-0.1.9.md) for the interaction improvements.

Named after the Chinese proverb *"Peaches and plums do not speak, yet a path is formed beneath them"* (signifying quiet excellence). It comes with built-in free Microsoft Translator (works out of the box without any API key or account registration), while supporting seamless integration with modern LLMs such as DeepSeek, OpenAI, Zhipu GLM, and local Ollama. The floating bubble utilizes a focus-preserving, always-on-top architecture that never steals keyboard focus from your terminal, code editor, or writing apps.

---

## Key Features

- **Zero-Config Out-of-the-Box**: Bundled with free Microsoft Translator. Download, run, and start translating immediately with no upfront setup.
- **Multi-Provider Aggregation**: Effortlessly switch translation backends on the fly from the floating header menu—Microsoft Translator, DeepSeek, OpenAI, Zhipu GLM, and local Ollama (e.g. Qwen).
- **Non-Stealing Floating Bubble**: The popup never steals keyboard input focus or interrupts your active typing session.
- **System-Native Font Adaptation**: Automatically adapts to modern platform UI typography (Microsoft YaHei UI on Windows, Noto Sans CJK on Linux), ensuring clean and crisp rendering.
- **Single-Instance Protection**: Built-in IPC process locking prevents multiple instances from spawning when repeatedly clicking the executable or shortcut. Repeated launches seamlessly bring the existing instance to the foreground.
- **Flexible Text Selection**:
  - **Global Hotkey**: Press `Alt + Q` on selected text. Features modifier key release and focus-loss mitigation specifically optimized for Windows. Alternate hotkeys can be registered.
  - **Mouse Side Buttons**: Trigger translation instantly using mouse forward/backward side buttons (X1/X2).
  - **Auto-Popup Mode**: Automatically translates whenever a mouse selection is released (can be toggled in the system tray).
  - **Manual Query Box**: Press the hotkey without a selection, or double-click the system tray icon to reveal an instant manual query box.
- **Floating Window Ergonomics**:
  - **Pin to Screen**: Lock the bubble to any specific screen coordinates.
  - **Translation-Only Mode**: Hide the original text and show only the translation for a cleaner view.
  - **Live Latency & Word Count**: Real-time display of word count, character count, and network latency in milliseconds.
  - **Opacity Slider**: Adjust transparency from 40% to 100% via the tray menu.
  - **Themes**: Modern Light, Dark, and Glass (translucent) themes.
  - **Quick Dismiss**: Press `Esc` or click outside to dismiss the window.
- **Visual Settings Center**: Intuitive preferences dialog in the tray and popup menu. Configure API keys (with password toggle), customize base URLs and model names, test API connectivity with one click, and manage hotkeys—no command line needed.
- **Offline SQLite Cache**: Built-in local cache gives instant 0ms responses for repeated queries, saving LLM API tokens and bandwidth.
- **Terminal CLI Tool**: Includes `yanxi-cli` for quick terminal translations and interactive shell sessions.

---

## Download & Installation

Pre-compiled standalone packages are available for Windows and Linux with no Python runtime required:

👉 **Download the latest release from [GitHub Releases](https://github.com/Leonherben/yanxi-trans/releases)**

| Platform | Download File | Instructions |
| :--- | :--- | :--- |
| **Windows** (10 / 11) | `yanxi-v*-windows-x86_64.zip` | Extract and run `启动言蹊翻译.bat` or `yanxi.exe` (portable green build, runs silently in tray) |
| **Linux** (Mint / Ubuntu / Debian, etc.) | `yanxi-v*-linux-x86_64.tar.gz` | Extract and run `./install.sh` to install to application launcher, or run `./yanxi` directly |

---

## Operations & Shortcuts

| Action / Shortcut | Function | Description |
| :--- | :--- | :--- |
| `Alt + D` | Translate selection / Toggle popup | Translates selected text; toggles popup display when no text is selected |
| Mouse Selection Release | Companion Reading Mode | Auto-translates in-place when popup is open; stays completely silent when popup is closed |
| Mouse Side Buttons | Selection Translation | Supported on most mice with X1/X2 side buttons |
| Double-click Tray Icon | Open Query Box | Rapidly input text manually |
| Tray Right-Click / Popup Menu | ⚙ Preferences | Open graphical settings for API keys, models, hotkeys, startup & themes |
| `Esc` / Popup `✕` Button | Dismiss Popup | Closes the companion window and restores silent mode |
| `Ctrl + Alt + Escape` | Panic Failsafe Exit | Global emergency shutdown shortcut |

---

## Service Configuration & API Keys

Microsoft Translator works immediately by default. If you wish to use DeepSeek, OpenAI, Zhipu GLM, or local Ollama:

### Option 1: Graphical Settings (Recommended)
Click **⚙ Preferences** in the tray menu or **⚙ Manage Providers & API Keys** in the floating window. Enter your API key and model name, then click **"⚡ Test Provider Connectivity"** to verify in real time.

### Option 2: Command Line or Config File
Configuration file location:
- **Linux**: `~/.config/yanxi/config.json`
- **Windows**: `%APPDATA%/yanxi/config.json`

You can also configure keys via the terminal:

```bash
# Configure DeepSeek API Key
yanxi-cli --set-key deepseek sk-your-deepseek-api-key

# Configure OpenAI API Key
yanxi-cli --set-key openai sk-your-openai-api-key

# Configure Zhipu GLM API Key
yanxi-cli --set-key zhipu your-zhipu-api-key

# List status of all configured providers
yanxi-cli --list-providers
```

---

## CLI Usage (yanxi-cli)

```bash
# Translate a single string
yanxi-cli "Standing on the shoulders of giants."

# Specify target language (e.g. Japanese)
yanxi-cli "Good morning!" -t ja

# Specify translation provider
yanxi-cli "Hello world" -p deepseek

# Enter interactive terminal translation mode
yanxi-cli -i
```

---

## Development & Building from Source

This project uses [uv](https://github.com/astral-sh/uv) for fast, deterministic Python environment management (Python 3.12+):

```bash
# 1. Linux system dependencies (Linux only, for X11 clipboard & cursor)
sudo apt update && sudo apt install -y xsel libxcb-cursor0

# 2. Sync virtual environment dependencies
uv sync

# 3. Launch GUI application
uv run yanxi

# 4. Run CLI tool
uv run yanxi-cli "Hello world"

# 5. Run test suite
uv run pytest

# 6. Build standalone release package locally
uv run python scripts/build.py
```

---

## License

This project is open-source under the [MIT License](LICENSE).
