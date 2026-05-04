"""Auto-reload wrapper for MCP server — restarts on .py file changes."""

import os
import subprocess
import sys
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.join(_DIR, "server.py")


class _Reloader(FileSystemEventHandler):
    def __init__(self):
        self._proc = None
        self._start()

    def _start(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        self._proc = subprocess.Popen([sys.executable, _SERVER])
        print(f"[reload] server started (pid={self._proc.pid})", file=sys.stderr)

    def on_modified(self, event):
        if event.src_path.endswith(".py"):
            print(f"[reload] change detected: {event.src_path}", file=sys.stderr)
            self._start()

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc.wait(timeout=5)


def main():
    reloader = _Reloader()
    observer = Observer()
    observer.schedule(reloader, _DIR, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        reloader.stop()
    observer.join()


if __name__ == "__main__":
    main()
