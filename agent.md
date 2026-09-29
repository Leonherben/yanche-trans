# Agent Operating Manual & Engineering Protocols (agent.md)
> 通用智能体开发规约与工程行动指南 —— 适用于全生命周期软硬件与系统级项目

本规范是为所有参与本项目的 AI 智能体（Agent）制定的最高操作准则。在进入任何新项目或执行新任务前，智能体必须严格遵循以下原则与规约。

---

## 1. 核心定位与行为守则 (Prime Directives)

1. **务实完整，拒绝半成品**：
   - 提供的代码与修改必须完整、可运行、语法严密，严禁留下未经实现的 `// TODO: 实现这里` 占位符。
   - 所有的脚本与执行指令必须能够在目标环境下一次性执行成功。
2. **规范先导 (Specification First)**：
   - 在直接编写核心业务逻辑之前，必须先理清并输出**系统架构**、**数据流转图**与**交互状态机**（如在 `docs/` 中建立规范）。
   - 严禁在未搞清边界条件和数据结构时盲目编写业务代码。
3. **大脑与外壳解耦 (Core-Adapter Decoupling)**：
   - **核心层（Core / Domain Engine）**：必须是纯粹的业务逻辑与数据算法，严禁混入特定操作系统 API、网络协议或特定 GUI 框架代码。
   - **适配层（Adapter / Shell）**：负责特定系统（Linux / Windows / macOS）、界面（CLI / Web / GTK / Qt）或守护进程（Daemon）的胶水代码。
   - 核心与适配层之间通过极简、明确的抽象接口（Clean Interface / C-ABI / IPC）通信，确保核心具备 100% 的可移植性与单测便利性。

---

## 2. 宿主环境与硬件边界认知 (Hardware & System Baseline)

在执行任何开发与运维指令前，智能体必须主动识别并适应以下物理与系统边界：

1. **操作系统与图形上下文**：
   - 默认环境基于现代 Linux（如 Ubuntu 24.04 / Linux Mint 等），桌面窗口管理器（X11 / Wayland）。
   - 处理全局热键、焦点管理或屏幕坐标时，必须考虑显示服务（Display Server）差异与终端模拟器的特异性（例如 Terminal 粘贴常用 `Ctrl+Shift+V`，普通应用为 `Ctrl+V`）。
2. **内存与计算保护 (8GB 内存与无独立显卡红线)**：
   - **严禁**：在无内存保护的前提下执行未经限流的高并发构建、拉起大量高消耗容器、或加载参数量超过 3B 的本地大语言模型。
   - **轻量化首选**：
     - 数据检索优先采用紧凑结构：如前缀树（Trie）、内存映射（mmap）或轻量嵌入式数据库（SQLite / LMDB），避免冷启动时全量加载巨型 JSON/文本挤占物理内存。
     - AI/深度学习模型优先使用 INT8/INT4 量化模型（如 Sherpa-ONNX、GGUF），且在待机空闲时保持 CPU/GPU 占用为 0%。
3. **安全与最小权限原则 (Sandboxed-first)**：
   - 严禁滥用 `sudo` 提权；开发与运行环境均以普通用户权限执行。
   - 编译产物、用户级工具统一放置于 `~/.local/bin` 或项目专用虚环境。

---

## 3. 开发工具链与规范 (Toolchains & Best Practices)

1. **Python 生态规范**：
   - **强制 uv-first**：统一使用现代工具链 `uv`（`uv run`、`uv venv .venv`、`uv add`、`uv sync`）管理依赖和虚拟环境。
   - 绝对禁止使用无保护的全局 `pip install` 污染宿主系统。
2. **Node.js 生态规范**：
   - 统一使用 NVM 纳管的 LTS 版本（如 Node v20），推荐使用 `npm` / `yarn` 并保持依赖锁文件（`lockfile`）版本受控。
3. **Git 协作与提交规范**：
   - 默认分支为 `main`。
   - 严格遵循 **Conventional Commits** 提交规范：
     - `feat(<scope>): ...` 新功能引入
     - `fix(<scope>): ...` 缺陷修复
     - `docs(<scope>): ...` 文档与规范修订
     - `refactor(<scope>): ...` 代码重构
     - `test(<scope>): ...` 单元与集成测试补充
   - 提交粒度清晰，一次提交只做一件事，保持提交树清晰可追溯。

---

## 4. 阶段化渐进式交付范式 (Phased Progressive Delivery)

任何中大型项目开发，智能体必须严格遵循以下阶段化演进模型，杜绝“一步到位”导致的失控与调试黑洞：

```text
[Phase 0: 规范先行] ───> [Phase 1: CLI 原型] ───> [Phase 2: 核心引擎]
                                                         │
[Phase 5: 全局集成与容灾] <─── [Phase 4: 硬件/AI集成] <─── [Phase 3: GUI沙盒]
```

- **Phase 0: 规格定义 (Spec & Architecture)**
  - 编写项目愿景、模块分工文档与交互按键/状态机文档（如 `docs/architecture.md`, `docs/interaction.md`）。
- **Phase 1: 最小可运行终端原型 (Headless / CLI First)**
  - 脱离复杂的窗口和全局环境，在终端实现最基础的输入输出闭环，快速验证核心设计。
- **Phase 2: 领域模型与高性能索引 (Core Engine & Data Store)**
  - 实现紧凑算法结构、本地持久化（如 SQLite/Trie）、动态自学习逻辑，并完成第一批纯逻辑单元测试。
- **Phase 3: 桌面与界面沙盒 (Isolated Sandbox GUI)**
  - 开发带独立窗口的测试沙盒，验证 UI 响应、触控/鼠标、无焦点浮窗、高对比度样式等交互体验，此时不接入全局系统拦截。
- **Phase 4: 硬件与扩展引擎集成 (Audio / Hardware / AI)**
  - 接入音频输入（PortAudio/ALSA）、模型推理（Sherpa-ONNX INT8）等外设功能，严格实现“按需唤醒、即用即走”。
- **Phase 5: 全局常驻与系统级整合 (System-wide Daemon & Failsafe)**
  - 编写全局守护进程、系统托盘指示器、开机自启动与全局热键钩子，并配备紧急逃生机制。

---

## 5. 系统级与桌面开发硬核避坑守则 (Hard-Learned Lessons)

以下是从复杂桌面与系统级交互开发中提炼出的实战防坑守则，必须融入日常编码：

1. **悬浮窗焦点防窃取 (Focus Stealing Prevention)**：
   - 凡是作为候选框、指示窗、取词条等附属窗口，必须在窗口创建时彻底禁用焦点夺取：
     - GTK: `set_accept_focus(False)`、`set_can_focus(False)`、`set_focus_on_map(False)`、窗口提示设为 `POPUP_MENU`。
     - Qt: 设置 `Qt::ToolTip` 或 `Qt::WindowDoesNotAcceptFocus`。
   - 否则附属窗口一弹出就会抢占用户正在输入的文本框焦点，造成灾难性打字中断。
2. **事件循环与剪贴板注入防死锁 (Event Loop & Ungrab Pipeline)**：
   - 通过剪贴板与模拟按键（如 XTEST `Ctrl+V`）向目标应用注入文本时：
     - **步骤 1**：更新剪贴板内容后，必须主动驱动事件循环（如 `while Gtk.events_pending(): Gtk.main_iteration()`），确保操作系统 SelectionOwner 及时就绪。
     - **步骤 2**：在发送粘贴按键前，必须显式释放底层的键盘抢占（如 `display.ungrab_keyboard()`），并主动合成物理释放那些可能正被用户按住的按键（如 Space、Enter、数字键），避免按键事件被全局 Grab 拦截或形成死锁。
     - **步骤 3**：根据目标窗口类型判断快捷键（例如普通 GUI 窗口为 `Ctrl+V`，终端模拟器为 `Ctrl+Shift+V`）。
3. **全局热键安全逃生通道 (Emergency Panic Failsafe)**：
   - 凡是接管系统全局输入流（X11 Grab, EVDEV, Windows Hook 等）的守护进程，**必须内置不可屏蔽的强制紧急终止与放行快捷键**（如 `Ctrl + Alt + Escape` 或 `Win + Y`）。
   - 发生未捕获异常时，必须在退出钩子（`atexit` / 信号处理器 `SIGINT/SIGTERM`）中无条件释放全局 Grab 并关闭 PID 文件，严禁因程序崩溃而锁死用户键盘桌面。
4. **长按与轻敲按键消抖 (Push-to-Talk & Debounce)**：
   - 复合功能按键（例如兼顾单击选词与长按语音听写）必须设计定时器阈值（如 150ms 延迟）：
     - 按下且在阈值前释放：判定为普通轻击，触发默认单键行为。
     - 按下超过阈值：取消轻击，激活长按状态（如启动流式录音），按键释放时执行完成上屏逻辑。

---

## 6. 测试与质量验证守则 (Verification & Testing Protocol)

1. **单测先行与隔离验证 (Mocking System Calls)**：
   - 对系统底层依赖（如 X11 Display、音频麦克风、系统剪贴板），单元测试中必须设计可注入的隔离接口或 Mock，保证在无真实图形服务/无麦克风的 CI 环境下亦能 100% 跑通。
2. **交付验证自闭环**：
   - Agent 在声称功能完成前，必须在终端亲自运行全量测试套件（如 `uv run --project <dir> python -m unittest`）。
   - 出现失败用例时，应主动修复并二次验证，不得将错误甩给用户排查。

---

## 7. 智能体工作交付自检清单 (Agent Delivery Checklist)

在向用户提交成果前，智能体必须在内心完成以下 7 项逐一核对：

- [ ] **1. 架构合规**：纯算法/业务引擎是否独立于界面与平台 API？
- [ ] **2. 资源安全**：是否有耗尽 8GB 内存或导致 CPU 持续飙升的隐患？
- [ ] **3. 错误兜底**：系统级钩子与后台守护是否有异常退出保护与逃生按键？
- [ ] **4. 依赖洁净**：所有新增依赖是否均通过 `uv` 记录至 `pyproject.toml` / `lockfile`？
- [ ] **5. 测试完备**：是否有对应的自动化单元测试覆盖关键逻辑？测试是否通过？
- [ ] **6. 提交规范**：Git Commit 信息是否清晰遵循 Conventional Commits 格式？
- [ ] **7. 文档同步**：核心改动是否已更新至相关设计文档或 `README.md`？
