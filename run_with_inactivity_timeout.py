#!/usr/bin/env python3
"""Run a command while enforcing a wall-clock output inactivity timeout."""

from __future__ import annotations

import argparse
import os
import selectors
import signal
import subprocess
import sys
import time


def terminate_group(process: subprocess.Popen[bytes], grace_s: float = 10.0) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=grace_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait()


def run(command: list[str], inactivity_timeout_s: float) -> int:
    if inactivity_timeout_s <= 0:
        raise ValueError("inactivity timeout must be positive")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        bufsize=0,
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    last_output = time.monotonic()
    try:
        while True:
            events = selector.select(timeout=0.5)
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 65536)
                if chunk:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    last_output = time.monotonic()
                else:
                    selector.unregister(key.fileobj)
            status = process.poll()
            if status is not None:
                for key in list(selector.get_map().values()):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if chunk:
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                return status
            if time.monotonic() - last_output > inactivity_timeout_s:
                print(
                    f"inactivity_timeout_s={inactivity_timeout_s:g}; terminating command",
                    file=sys.stderr,
                    flush=True,
                )
                terminate_group(process)
                return 124
    finally:
        selector.close()
        if process.poll() is None:
            terminate_group(process)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inactivity-timeout-s", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    return run(command, args.inactivity_timeout_s)


if __name__ == "__main__":
    raise SystemExit(main())
