# QuickTrans 跨平台智能划词翻译软件 (Linux & Windows)

> 基于 Python 3.12 + PySide6 构建的轻量级、无焦点窃取的桌面划词翻译工具，深度聚合 OpenAI 兼容大模型 API 与传统翻译服务。

---

## 🌟 核心特性

1. **🧠 大脑与外壳彻底解耦 (Core-Adapter Decoupling)**：
   - 核心层包含领域模型、统一翻译接口契约与本地 SQLite 高性能缓存，纯粹独立，无任何 GUI 或平台 API 依赖；
   - 适配层负责 Linux X11 Primary 选区监听、Windows 全局热键捕获与 PySide6 现代悬浮窗渲染。
2. **🛡️ 悬浮窗焦点防窃取 (Focus Stealing Prevention)**：
   - 严格遵循 `agent.md` 规范，采用 `Qt.WindowType.ToolTip | WindowDoesNotAcceptFocus` 属性，无论在终端敲命令、浏览器表单输入还是 IDE 编写代码，划词弹出浮窗时**绝不抢占键盘输入焦点**，打字永不中断。
3. **⚡ 跨平台无感划词体验**：
   - **Linux (X11)**：基于 Primary Selection，鼠标选中文本松开即刻弹出，无需按键，不污染系统剪贴板；
   - **Windows / 通用**：支持按下全局热键（默认 `<ctrl>+<alt>+t`）自动提取，带有剪贴板保全机制，取词完成后自动恢复用户原有剪贴板数据。
4. **💾 本地零延迟缓存 (SQLite Cache)**：
   - 翻译结果自动进行 SHA256 紧凑指纹归一化缓存，相同词句 0ms 秒开，省时省 API 资费。
5. **🚨 紧急逃生通道 (Panic Failsafe)**：
   - 内置全局最高优先级逃生键（`<ctrl>+<alt>+<esc>`），触发后瞬间注销所有底层钩子并安全退出，保障系统稳定。
6. **🪶 极轻量资源占用**：
   - 适配 8GB 物理内存环境，待机内存仅 ~35MB，空闲 CPU 占用 0%。

---

## 🚀 快速上手

本项目严格采用现代工具链 `uv` 纳管虚拟环境。

### 1. 安装依赖与环境构建
```bash
# 自动创建 .venv 并安装所有依赖
uv sync
```

### 2. 配置翻译 API Key
QuickTrans 原生支持所有兼容 OpenAI 规范的提供商（DeepSeek、智谱 GLM、OpenAI、Moonshot/Kimi、Ollama 本地大模型等）。

可以通过命令行快速配置 API 密钥：
```bash
# 配置 DeepSeek Key
uv run quicktrans-cli --set-key deepseek sk-your-deepseek-api-key

# 或配置 OpenAI Key
uv run quicktrans-cli --set-key openai sk-your-openai-api-key

# 或配置 智谱 GLM Key
uv run quicktrans-cli --set-key zhipu your-zhipu-api-key
```
配置文件将持久化存储于 `~/.config/quicktrans/config.json`（Linux）或 `%APPDATA%/quicktrans/config.json`（Windows）。

### 3. 测试 API 连通性
```bash
uv run quicktrans-cli --test
```

### 4. 运行终端 CLI 翻译
```bash
# 单次快速翻译
uv run quicktrans-cli "Artificial Intelligence is reshaping software development."

# 指定目标语言（如日语）
uv run quicktrans-cli "Good morning!" -t ja

# 进入终端交互模式
uv run quicktrans-cli -i
```

### 5. 启动桌面常驻划词服务 (GUI + 托盘)
```bash
uv run quicktrans
```
启动后：
- 屏幕右下角任务栏出现托盘图标；
- 鼠标在任意文本中划选，松开后即可在鼠标旁弹出悬浮卡片；
- 支持点击“📌”固定浮窗、点击“复制译文”快速复制、按 `Esc` 快捷隐藏；
- 遇到任何异常，可随时按下 `Ctrl + Alt + Escape` 紧急安全退出。

---

## 🛠️ 常用快捷键

| 快捷键 | 功能 | 说明 |
| :--- | :--- | :--- |
| **鼠标左键划词松开** | 触发自动翻译 | Linux X11 原生支持，零按键 |
| `Ctrl + Alt + T` | 通用划词/剪贴板翻译 | 跨平台全局热键模式 |
| `Esc` | 关闭当前翻译浮窗 | 浮窗打开时有效 |
| `Ctrl + Alt + Escape` | **紧急逃生键 (Panic Exit)** | 强制注销钩子并关闭程序 |

---

## 📁 目录结构

```text
├── agent.md                    # 最高工程规范守则
├── docs/
│   ├── architecture.md         # 架构设计与领域模型规范
│   └── interaction.md          # 划词交互、防焦点抢占时序规范
├── src/quicktrans/
│   ├── core/                   # 纯业务核心层
│   │   ├── models.py           # 翻译请求/响应实体
│   │   ├── config.py           # 跨平台配置持久化
│   │   ├── translator/         # 翻译引擎抽象与 OpenAI 协议实现
│   │   └── cache/              # SQLite 本地缓存引擎
│   ├── adapters/               # 平台与界面适配层
│   │   ├── gui/                # PySide6 悬浮窗与系统托盘
│   │   └── selection/          # Linux X11 原生与通用热键取词器
│   ├── cli/                    # CLI 原型工具
│   └── main.py                 # 全局常驻守护进程与主入口
├── tests/                      # 自动化测试套件与沙盒
│   ├── test_translator.py      # 网络与翻译逻辑 Mock 单测
│   ├── test_cache.py           # 本地 SQLite 缓存单测
│   ├── test_selection.py       # 划词文本过滤单测
│   ├── test_cli.py             # CLI 命令行单测
│   └── sandbox_gui.py          # 桌面无焦点浮窗独立沙盒
└── pyproject.toml              # uv 项目依赖与入口声明
```

---

## 🧪 自动化测试

运行全量单元测试套件：
```bash
uv run pytest tests/ -v
```
