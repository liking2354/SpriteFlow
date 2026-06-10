"""SpriteFlow CLI 入口"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="SpriteFlow — 2D 游戏素材生产管线")
    subparsers = parser.add_subparsers(dest="command")

    # serve 命令
    serve_parser = subparsers.add_parser("serve", help="启动 API 服务")
    serve_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    serve_parser.add_argument("--port", type=int, default=8000, help="监听端口")

    args = parser.parse_args()

    if args.command == "serve":
        _serve(args.host, args.port)
    else:
        parser.print_help()


def _serve(host: str, port: int) -> None:
    """启动 API 服务"""
    import uvicorn
    from .api.app import app
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
