# 言蹊翻译 (YanXi Trans)

轻量、极速的跨平台桌面划词翻译工具，支持 Linux (X11) 与 Windows。

名称取自“桃李不言，下自成蹊”。默认内置免费微软翻译（无需注册任何账号或申请 API 密钥，开箱即用），同时支持接入 DeepSeek、OpenAI、智谱 GLM、本地 Ollama 等大模型。悬浮窗采用无焦点置顶设计，划词查词时不会抢占键盘输入焦点，不影响写代码、敲终端命令或日常打字。

---

## 主要功能

- **免配置开箱即用**：默认内置微软翻译服务，下载即可直接使用，无需任何前置 API 配置。
- **聚合多翻译源**：支持在悬浮窗左上角下拉菜单秒级切换翻译引擎，包括微软翻译、DeepSeek、OpenAI、智谱 GLM 与本地 Ollama（Qwen 等）。
- **无焦点悬浮窗**：翻译气泡弹出时绝不抢占键盘焦点，正在进行的文本输入与光标位置不中断。
- **灵活取词方式**：
  - **快捷键取词**：选中文本后按下 `Alt + D` 即可翻译，支持在配置文件中设置多个备用快捷键（如 `Alt + Q`）。
  - **鼠标侧键取词**：支持鼠标前后侧键一键触发划词翻译。
  - **自动划词翻译**：选中文本松开鼠标左键自动弹出翻译（可在托盘菜单随时开启或关闭）。
  - **手动查词框**：未选词时按下快捷键，或双击系统托盘图标，均可呼出输入框手动查词。
- **悬浮窗实用特性**：
  - **固定位置 (Pin)**：可将悬浮窗固定在屏幕任意坐标，后续查词直接在固定位置显示。
  - **纯译文模式**：支持隐藏原文仅展示译文，视觉更清爽。
  - **统计与耗时**：实时展示单词数、字符数以及翻译请求的毫秒耗时。
  - **透明度调节**：支持在托盘中按百分比调节窗口透明度（40% ~ 100%）。
  - **多主题适配**：提供亮色（Light）、暗黑（Dark）与毛玻璃（Glass）三套现代主题。
  - **快捷收起**：按下 `Esc` 键或点击悬浮窗外部空白区域即可收起窗口。
- **可视化偏好设置中心**：托盘与悬浮窗内置图形设置窗口，可直接在界面中输入与管理各服务商 API Key（带防窥密码切换）、自定义模型参数、一键测试 API 连通性、配置快捷键与外观，完全无需接触命令行。
- **离线本地缓存**：内置 SQLite 缓存，相同词句 0ms 秒级响应，节省大模型 API 资费与网络开销。
- **终端命令行工具**：提供 `yanxi-cli`，支持在终端中快速查词与交互式翻译。

---

## 软件下载

各平台独立运行包已预编译打包，无需安装 Python 环境，解压即可运行：

👉 **前往 [GitHub Releases](https://github.com/Leonherben/yanxi-trans/releases) 下载最新版本**

| 平台 | 下载文件 | 使用说明 |
| :--- | :--- | :--- |
| **Windows** (Win10 / Win11) | `yanxi-v*-windows-x86_64.zip` | 解压后双击 `启动言蹊翻译.bat` 或 `yanxi.exe` 即可（绿色免安装，无控制台黑框后台常驻） |
| **Linux** (Mint / Ubuntu / Debian 等) | `yanxi-v*-linux-x86_64.tar.gz` | 解压后直接运行 `./install.sh` 安装到系统应用程序菜单，或直接运行 `./yanxi` |

---

## 常用操作与快捷键

| 操作 / 快捷键 | 功能 | 说明 |
| :--- | :--- | :--- |
| `Alt + D` | 划词翻译 / 打开查词框 | 选中文本时触发翻译；未选词时呼出手动查词框 |
| 鼠标前后侧键 | 划词翻译 | 支持大部分带有侧键的鼠标 |
| 鼠标划选松开 | 划选自动翻译 | 可在托盘菜单勾选“划选自动翻译”启用 |
| 双击托盘图标 | 打开查词框 | 快速手动输入翻译内容 |
| 托盘右键 / 浮窗更多菜单 | ⚙ 偏好设置 | 打开图形配置中心，修改 API Key、模型、快捷键与主题 |
| `Esc` | 收起翻译悬浮窗 | 悬浮窗显示时有效 |
| `Ctrl + Alt + Escape` | 紧急退出程序 | 后台守护进程异常时的全局强制退出键 |

---

## 服务配置与 API Key

默认无需修改任何配置即可使用微软翻译。若需使用 DeepSeek、OpenAI、智谱 GLM 或本地 Ollama 等模型，可通过以下方式配置：

### 方式一：图形界面配置（推荐）
点击右下角系统托盘菜单中的 **⚙ 偏好设置**（或悬浮窗左上角引擎下拉菜单中的 **⚙ 管理服务与 API Key**），即可直接填入 API Key、修改模型名称与 Base URL，并可点击 **“⚡ 测试当前服务连通性”** 即时验证。

### 方式二：命令行或配置文件
配置文件路径：
- **Linux**：`~/.config/yanche/config.json`
- **Windows**：`%APPDATA%/yanche/config.json`

亦可通过终端命令快速设定：

```bash
# 配置 DeepSeek API Key
yanxi-cli --set-key deepseek sk-your-deepseek-api-key

# 配置 OpenAI API Key
yanxi-cli --set-key openai sk-your-openai-api-key

# 配置 智谱 GLM API Key
yanxi-cli --set-key zhipu your-zhipu-api-key

# 查看所有已配置的提供商状态
yanxi-cli --list-providers
```

---

## 命令行用法 (yanxi-cli)

```bash
# 单次翻译文本
yanxi-cli "Standing on the shoulders of giants."

# 指定源语言与目标语言（如翻译为日语）
yanxi-cli "Good morning!" -t ja

# 指定使用的翻译引擎
yanxi-cli "Hello world" -p deepseek

# 进入终端交互式翻译模式
yanxi-cli -i
```

---

## 源码运行与开发

本项目推荐使用 [uv](https://github.com/astral-sh/uv) 管理 Python 虚拟环境与依赖（Python 3.12+）：

```bash
# 1. Linux 前置依赖 (Linux 专属，用于 X11 取词)
sudo apt update && sudo apt install -y xsel libxcb-cursor0

# 2. 安装 Python 依赖
uv sync

# 3. 运行 GUI 划词主程序
uv run yanxi

# 4. 运行命令行查词工具
uv run yanxi-cli "Hello world"

# 5. 执行单元测试
uv run pytest

# 6. 本地打包构建独立发布包
uv run python scripts/build.py
```

---

## 开源协议

本项目采用 MIT 协议开源。
