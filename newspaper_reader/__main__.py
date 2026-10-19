from __future__ import annotations

import argparse
import webbrowser

import uvicorn

from . import config


def main() -> None:
    config.ensure_dirs()
    parser = argparse.ArgumentParser(description="电子报纸阅读工具")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print("=" * 56)
    print("  电子报纸阅读工具 · 图片转排版 PDF")
    print(f"  访问地址: {url}")
    print(f"  运行目录: {config.RUNTIME_DIR}")
    print("=" * 56)

    if args.open:
        import threading

        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    uvicorn.run("newspaper_reader.app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
