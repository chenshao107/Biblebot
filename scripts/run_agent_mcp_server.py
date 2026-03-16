#!/usr/bin/env python3
"""
Agent MCP 服务器启动脚本
支持 stdio 和 HTTP/SSE 两种模式

使用方法:

1. stdio 模式（本地使用，供 Claude Desktop 等客户端）:
    python scripts/run_agent_mcp_server.py

2. HTTP/SSE 模式（内网共享，供远程访问）:
    python scripts/run_agent_mcp_server.py --http --host 0.0.0.0 --port 8001

或者通过 MCP 客户端配置:
    {
        "mcpServers": {
            "biblebot-agent": {
                "command": "python",
                "args": ["/home/chenshao/Bibliobot/scripts/run_agent_mcp_server.py"]
            }
        }
    }

环境变量:
    - 自动加载项目根目录的 .env 文件
    - AGENT_MCP_HOST: HTTP 服务器主机 (默认: 0.0.0.0)
    - AGENT_MCP_PORT: HTTP 服务器端口 (默认: 8001)
"""
import os
import sys
import argparse

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from app.mcp_server import run_stdio_server, run_http_server


def main():
    parser = argparse.ArgumentParser(description="Agent MCP 服务器")
    parser.add_argument(
        "--http", 
        action="store_true",
        help="启用 HTTP/SSE 模式（内网共享）"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("AGENT_MCP_HOST", "0.0.0.0"),
        help="HTTP 服务器主机 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("AGENT_MCP_PORT", "8001")),
        help="HTTP 服务器端口 (默认: 8001)"
    )
    
    args = parser.parse_args()
    
    if args.http:
        # HTTP/SSE 模式
        run_http_server(host=args.host, port=args.port)
    else:
        # stdio 模式（默认）
        run_stdio_server()


if __name__ == "__main__":
    main()
