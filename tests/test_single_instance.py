import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
import pytest
from PySide6.QtWidgets import QApplication
from yanxi.core.single_instance import SingleInstance


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


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
