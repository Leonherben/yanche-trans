"""兼容旧 Windows 控制台及 UTF-8 日志重定向。"""

import sys


def configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            options = {"errors": "replace"}
            if not stream.isatty():
                options["encoding"] = "utf-8"
            stream.reconfigure(**options)
