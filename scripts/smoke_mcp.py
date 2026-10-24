"""冒烟自检：经真实 HTTP 跑一遍 /mcp 的握手、工具清单和几个工具调用。

用法（后端已启动的前提下）：
    .venv\\Scripts\\python.exe scripts\\smoke_mcp.py --url http://127.0.0.1:8000/mcp
    uv run python scripts/smoke_mcp.py --port 8000
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx


def rpc(
    client: httpx.Client, url: str, method: str, params: dict | None, seq: int
) -> dict:
    payload: dict = {"jsonrpc": "2.0", "id": seq, "method": method}
    if params is not None:
        payload["params"] = params
    response = client.post(
        url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="aio-backend MCP 冒烟自检")
    parser.add_argument("--url", default=None, help="MCP 端点，默认按 --port 拼")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--username", default=None, help="给了就顺带验证登录 + 带 token 调接口"
    )
    parser.add_argument("--password", default=None)
    args = parser.parse_args()
    url = args.url or f"http://127.0.0.1:{args.port}/mcp"

    with httpx.Client(trust_env=False, timeout=60) as client:
        init = rpc(
            client,
            url,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "0"},
            },
            seq=1,
        )
        print("initialize:", init["result"]["serverInfo"])

        tools = rpc(client, url, "tools/list", None, seq=2)["result"]["tools"]
        names = [tool["name"] for tool in tools]
        print("tools:", names)
        expected = {
            "list_endpoints",
            "describe_endpoint",
            "login",
            "api_request",
            "db_tables",
            "db_columns",
            "db_query",
            "db_exec",
        }
        if not expected.issubset(set(names)):
            print("缺少工具:", sorted(expected - set(names)), file=sys.stderr)
            return 1

        calls: list[tuple[str, dict]] = [
            ("list_endpoints", {}),
            ("db_tables", {}),
            ("api_request", {"method": "GET", "path": "/api/health"}),
        ]
        if args.username and args.password:
            calls.append(
                (
                    "api_request",
                    {
                        "method": "GET",
                        "path": "/api/users/me",
                        "username": args.username,
                        "password": args.password,
                    },
                )
            )

        for index, (name, arguments) in enumerate(calls, start=3):
            result = rpc(
                client,
                url,
                "tools/call",
                {"name": name, "arguments": arguments},
                seq=index,
            )
            text = result["result"]["content"][0]["text"]
            json.loads(text)
            shown = json.dumps(arguments, ensure_ascii=False)
            print(f"ok  {name}({shown}) -> {len(text)} 字符")

    print("MCP 冒烟通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
