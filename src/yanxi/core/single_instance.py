"""跨平台单实例运行保护机制 (Single Instance Protection)

基于 Qt QLocalServer / QLocalSocket 实现：
- Windows: 基于本地命名管道 (Named Pipe)
- Linux / macOS: 基于本地 Unix Domain Socket
实现进程互斥，并在多开时自动唤醒已运行的主实例，防止进程泛滥与快捷键冲突。
"""

from __future__ import annotations
import getpass
import hashlib
import os
import sys
from typing import Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    """跨平台单实例锁与唤醒监听器"""

    wakeup_received = Signal()

    def __init__(self, app_key: str = "yanxi_single_instance", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.app_key = app_key
        self.server_name = self._generate_server_name()
        self._server: Optional[QLocalServer] = None

    def _generate_server_name(self) -> str:
        """生成结合当前系统用户的唯一本地服务端名称"""
        try:
            user = getpass.getuser()
        except Exception:
            user = str(os.getuid()) if hasattr(os, "getuid") else "default"
        raw = f"{self.app_key}_{user}"
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
        return f"{self.app_key}_{digest}"

    def is_already_running(self, timeout_ms: int = 400) -> bool:
        """检测系统中是否已有运行中的实例，若存在则发送唤醒指令并返回 True"""
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        connected = socket.waitForConnected(timeout_ms)

        if connected:
            try:
                socket.write(b"WAKEUP\n")
                socket.waitForBytesWritten(500)
            except Exception:
                pass
            finally:
                socket.disconnectFromServer()
            return True

        return False

    def start_listen(self) -> bool:
        """在主实例中启动本地监听服务，等待后续多开进程的唤醒通知"""
        # 清理异常崩溃残留的同名管道或 socket 文件
        QLocalServer.removeServer(self.server_name)

        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handle_new_connection)
        success = self._server.listen(self.server_name)
        return success

    def _handle_new_connection(self) -> None:
        """接收二次启动实例发送的唤醒信号"""
        if not self._server:
            return
        client = self._server.nextPendingConnection()
        if not client:
            return

        def _on_ready_read():
            try:
                data = bytes(client.readAll()).decode("utf-8", errors="ignore")
                if "WAKEUP" in data:
                    self.wakeup_received.emit()
            except Exception:
                pass
            finally:
                client.disconnectFromServer()

        client.readyRead.connect(_on_ready_read)
        # 若已有数据可读直接处理
        if client.bytesAvailable() > 0:
            _on_ready_read()

    def close(self) -> None:
        """释放并关闭本地监听服务"""
        if self._server:
            self._server.close()
            QLocalServer.removeServer(self.server_name)
            self._server = None
