"""以 stdio 方式跑同一套 MCP 工具（供 DSH 直接拉起，不需要先起 HTTP 服务）。

HTTP 那套（uvicorn 里的 /mcp）适合 curl / 别的客户端；DSH 用 stdio 更稳：
进程由 DSH 自己拉起，不会出现「DSH 先启动、后端还没起」导致连接失败又静默的情况。

用法：
    .venv\\Scripts\\python.exe scripts\\mcp_stdio.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.mcp import mcp  # noqa: E402  （必须先补 sys.path 才能 import core）

if __name__ == "__main__":
    mcp.run()
