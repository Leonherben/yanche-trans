import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
import subprocess
import sys
import uuid
from yanxi.core.single_instance import SingleInstance


def test_single_instance_workflow(qapp):
    """测试单实例检测与唤醒信号流程"""
    test_key = "test_yanxi_single_instance_unit"

    # 1. 初始状态下无运行实例
    guard1 = SingleInstance(test_key)
    assert not guard1.is_already_running(timeout_ms=100)

    # 2. 启动首个实例的本地监听
    assert guard1.start_listen()

    # 3. 模拟第二个实例尝试启动
    guard2 = SingleInstance(test_key)
    wakeup_called = False

    def on_wakeup():
        nonlocal wakeup_called
        wakeup_called = True

    guard1.wakeup_received.connect(on_wakeup)

    # 第二个实例应检测到已在运行并触发唤醒
    assert guard2.is_already_running(timeout_ms=500)

    # 驱动事件循环处理 IPC 消息
    for _ in range(15):
        qapp.processEvents()
        time.sleep(0.01)

    assert wakeup_called

    # 清理关闭
    guard1.close()
    guard2.close()


def test_wakeup_from_process_that_exits_immediately(qapp):
    key = f"yanxi_test_{uuid.uuid4().hex}"
    guard = SingleInstance(key)
    assert guard.start_listen()
    wakeups = []
    guard.wakeup_received.connect(lambda: wakeups.append(True))
    script = (
        "from PySide6.QtWidgets import QApplication; "
        "from yanxi.core.single_instance import SingleInstance; "
        "app = QApplication([]); "
        f"guard = SingleInstance({key!r}); "
        "raise SystemExit(0 if guard.is_already_running(1000) else 1)"
    )
    child = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and (child.poll() is None or not wakeups):
            qapp.processEvents()
            time.sleep(.01)
        stdout, stderr = child.communicate(timeout=2)
        assert child.returncode == 0, (stdout, stderr)
        assert wakeups == [True]
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        guard.close()
