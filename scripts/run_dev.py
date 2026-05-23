#!/usr/bin/env python3
"""Run OpenSpider backend (Python) and console frontend (npm) together."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSOLE_DIR = REPO_ROOT / "console"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start backend and frontend dev servers in one command.",
    )
    parser.add_argument(
        "--backend-cmd",
        default=f'"{sys.executable}" -m openspider app',
        help="Backend command to run (default: python -m openspider app).",
    )
    parser.add_argument(
        "--frontend-cmd",
        default="npm run dev",
        help="Frontend command to run inside ./console (default: npm run dev).",
    )
    parser.add_argument(
        "--no-backend",
        action="store_true",
        help="Only run frontend.",
    )
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="Only run backend.",
    )
    return parser.parse_args()


def stream_output(process: subprocess.Popen[str], name: str) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{name}] {line.rstrip()}")


def terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def start_process(name: str, cmd: str, cwd: Path) -> subprocess.Popen[str]:
    print(f"[launcher] starting {name}: {cmd}")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def main() -> int:
    args = parse_args()

    if args.no_backend and args.no_frontend:
        print("[launcher] nothing to run: both backend and frontend are disabled")
        return 1

    processes: list[tuple[str, subprocess.Popen[str]]] = []

    try:
        if not args.no_backend:
            backend = start_process("backend", args.backend_cmd, REPO_ROOT)
            processes.append(("backend", backend))

        if not args.no_frontend:
            if not CONSOLE_DIR.exists():
                print(f"[launcher] frontend directory not found: {CONSOLE_DIR}")
                return 1
            frontend = start_process("frontend", args.frontend_cmd, CONSOLE_DIR)
            processes.append(("frontend", frontend))

        if not processes:
            print("[launcher] no process started")
            return 1

        threads = [
            threading.Thread(target=stream_output, args=(proc, name), daemon=True)
            for name, proc in processes
        ]
        for thread in threads:
            thread.start()

        while True:
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"[launcher] {name} exited with code {code}")
                    return code
    except KeyboardInterrupt:
        print("\n[launcher] stopping processes...")
        return 0
    finally:
        for _, proc in processes:
            terminate_process(proc)


if __name__ == "__main__":
    raise SystemExit(main())
