# 划词翻译交互、防焦点窃取与状态机规范 (Interaction Specification)

本文档定义 QuickTrans 的屏幕交互时序、防焦点窃取策略以及异常状态下的逃生机制，严格对照 [agent.md](file:///home/malus/Project/Tts/agent.md) 的实战防坑守则。

---

## 1. 取词与悬浮窗时序 (Timing & Sequence Diagram)

```text
用户操作               Selection Adapter         Core Controller            Popup GUI
   │                          │                         │                       │
   │──[鼠标划选文本]─────────>│                         │                       │
   │                          │──[消抖 150ms 校验有效]─>│                       │
   │                          │                         │──[显示 Loading 状态]─>│ (WindowDoesNotAcceptFocus)
   │                          │                         │                       │ 鼠标原焦点保持不丢失
   │                          │                         │──[查本地 SQLite 缓存] │
   │                          │                         │       │ (未命中)      │
   │                          │                         │──[异步请求 API]──────>│
   │                          │                         │       │ (200 OK)      │
   │                          │                         │──[渲染译文/更新高度]─>│ 平滑呈现
   │                          │                         │                       │
   │──[点击空白处或 Esc]───────────────────────────────────────────────────────>│ 隐藏浮窗
```

---

## 2. 系统级硬核避坑实施细节

### 2.1 悬浮窗防焦点窃取 (Focus Stealing Prevention)
- **问题**：若悬浮窗以普通 Window 形式被映射或创建，操作系统窗口管理器（如 Mutter, Cinnamon Muffin, Windows DWM）会自动将当前键盘焦点转移给浮窗，导致用户打字被硬生生切断。
- **解决方案**：
  - PySide6 窗口标志组合：
    ```python
    self.setWindowFlags(
        Qt.WindowType.ToolTip
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.WindowDoesNotAcceptFocus
    )
    self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    ```
  - 当浮窗需要点击按钮（如“复制结果”）时，点击事件正常响应，但不会强行夺走父级应用的 ActiveFocus。

### 2.2 剪贴板保护与防死锁通道 (Clipboard Preservation & Failsafe)
- 在 Windows 或不支持 Primary Selection 的应用中，划词触发需模拟按键 `Ctrl+C`。
- **操作流程**：
  1. 临时保存用户系统当前剪贴板文本与格式 `old_clipboard = pyperclip.paste()`；
  2. 模拟发送 `Ctrl+C` 并等待剪贴板变化（超时 200ms）；
  3. 获取到新选中的文本；
  4. **异步/延迟恢复原剪贴板内容**，保证用户的复制历史不被划词查询污染。

### 2.3 紧急逃生通道 (Panic Failsafe)
- 全局常驻守护进程必须内置不可屏蔽的强制紧急终止快捷键：
  - 默认：`Ctrl + Alt + Escape`
  - 行为：触发后立即停止所有监听钩子，注销热键，关闭悬浮窗并退出进程。
- 退出钩子绑定：`atexit.register(...)` 与 `signal.signal(signal.SIGINT, ...)`，杜绝崩溃遗留僵尸钩子。
