# 跨平台划词翻译系统架构规范 (Architecture Specification)

本文档定义 言澈翻译 的系统架构与接口契约，严格遵循 Core-Adapter Decoupling（大脑与外壳解耦）原则。

---

## 1. 分层架构概览

```text
┌─────────────────────────────────────────────────────────────┐
│                       应用入口 (Entrypoint)                  │
│       src/yanche/main.py (Daemon / Tray / Panic)        │
│       src/yanche/cli/main.py (CLI Prototype)            │
└──────────────────────────────┬──────────────────────────────┘
                               │
       ┌───────────────────────┴───────────────────────┐
       ▼                                               ▼
┌──────────────────────────────┐        ┌──────────────────────────────┐
│       适配层 (Adapters)       │        │         核心层 (Core)         │
│                              │        │  (纯业务算法，无平台/GUI绑定)  │
│  1. 划词提取 (Selection)      │        │  1. 领域模型 (Models)         │
│     - Linux X11 (Primary)    │───────>│     - TranslationRequest     │
│     - Hotkey / Clipboard     │        │     - TranslationResult      │
│  2. 用户界面 (GUI / Shell)    │        │  2. 翻译引擎 (Translator)     │
│     - Popup Floating Window  │        │     - BaseTranslator         │
│     - System Tray Icon       │        │     - OpenAICompatible (LLM) │
│  3. 全局热键与应急防逃生      │        │  3. 缓存与持久化 (Cache)      │
│     - Panic Failsafe Listener│        │     - SQLiteCache (LRU/TTL)  │
│                              │        │  4. 配置管理 (Config)         │
│                              │        │     - AppConfig, ProviderCfg │
└──────────────────────────────┘        └──────────────────────────────┘
```

---

## 2. 核心层契约 (Core Domain Contracts)

### 2.1 领域实体 (`src/yanche/core/models.py`)
- `TranslationRequest`:
  - `text: str`: 待翻译原始文本（经过清洗与去噪）
  - `source_lang: str = "auto"`: 源语言代码（如 "auto", "en", "zh-CN"）
  - `target_lang: str = "zh-CN"`: 目标语言代码
  - `context: str | None`: 上下文信息（可选）
- `TranslationResult`:
  - `original_text: str`: 原始文本
  - `translated_text: str`: 翻译结果
  - `source_lang: str`: 检测或指定的源语言
  - `target_lang: str`: 目标语言
  - `provider: str`: 翻译服务提供商标识（如 "deepseek", "openai", "cache"）
  - `latency_ms: float`: 耗时（毫秒）
  - `from_cache: bool`: 是否命中本地缓存

### 2.2 翻译器抽象基类 (`src/yanche/core/translator/base.py`)
```python
class BaseTranslator(ABC):
    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """同步翻译方法（CLI/GUI 工作线程中执行）"""
        pass

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """连通性测试，返回 (是否成功, 详细信息)"""
        pass
```

### 2.3 缓存接口 (`src/yanche/core/cache/sqlite_cache.py`)
- SQLite 轻量数据库：`~/.config/yanche/cache.db`
- Key 计算：`SHA256(text.strip().lower() + ":" + source_lang + ":" + target_lang + ":" + provider)`
- 支持自动过期清除与容量淘汰（保护 8GB 内存与本地磁盘空间）。

---

## 3. 适配层契约 (Adapter Shell Contracts)

### 3.1 选词监听器 (`src/yanche/adapters/selection/base.py`)
- 回调机制：`on_text_selected(text: str, cursor_pos: tuple[int, int])`
- 职责：只负责从操作系统捕获待翻译文本和当前鼠标位置，不直接调用翻译核心，通过控制器分发。

### 3.2 悬浮窗设计 (`src/yanche/adapters/gui/popup.py`)
- 严格遵循 `agent.md` 防焦点窃取标准：
  - `Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus`
- 提供异步展示：接收到文本时显示 Loading 状态，翻译完成后平滑刷新，并提供一键复制与收起功能。
