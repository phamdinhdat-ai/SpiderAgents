#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Start the OpenSpider server with SpiderAgent — FastAPI + Console UI.

This is equivalent to ``openspider app`` or ``python -m openspider app``,
but provides a dedicated entry point with sensible defaults.

Usage:
    # Start server on default http://127.0.0.1:8088
    python scripts/run_spider_server.py

    # Custom host and port
    python scripts/run_spider_server.py --host 0.0.0.0 --port 9000

    # Development mode with auto-reload
    python scripts/run_spider_server.py --reload

    # Debug logging
    python scripts/run_spider_server.py --log-level debug

Requirements:
    - ``pip install -e ".[dev]"`` (or ``pip install openspider``)
    - A valid ``~/.openspider/config.json`` (run ``openspider init --defaults`` first)
    - API key set via env var (e.g. ``OPENAI_API_KEY``) or config.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so we can import openspider.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the OpenSpider server with SpiderAgent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("OPENSPIDER_HOST", "127.0.0.1"),
        help="Bind host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("OPENSPIDER_PORT", "8088")),
        help="Bind port (default: 8088).",
    )
    parser.add_argument(
        "--reload", "-r",
        action="store_true",
        help="Enable auto-reload for development.",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("OPENSPIDER_LOG_LEVEL", "info"),
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Log level (default: info).",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open the browser on startup.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import uvicorn

    from openspider.constant import LOG_LEVEL_ENV
    from openspider.config.utils import write_last_api
    from openspider.utils.logging import setup_logger, SuppressPathAccessLogFilter

    # Persist host/port for other terminal commands
    host_for_api = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    write_last_api(host_for_api, args.port)

    # Set log level env so child processes (reload) pick it up
    os.environ[LOG_LEVEL_ENV] = args.log_level

    # Signal reload mode for Windows Playwright compatibility
    if args.reload:
        os.environ["OPENSPIDER_RELOAD_MODE"] = "1"
    else:
        os.environ.pop("OPENSPIDER_RELOAD_MODE", None)

    setup_logger(args.log_level)

    # Suppress noisy access log paths
    logging.getLogger("uvicorn.access").addFilter(
        SuppressPathAccessLogFilter(["/console/push-messages"]),
    )

    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                    🕷️  OpenSpider Server                      ║
║                                                              ║
║   SpiderAgent is running at:                                 ║
║   ➜  http://{host_for_api}:{args.port:<5}                                  ║
║                                                              ║
║   Open the console in your browser to get started.            ║
║   Press Ctrl+C to stop.                                       ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)

    uvicorn.run(
        "openspider.app._app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=1,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    import logging
    main()
