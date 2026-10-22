"""Serve the SATOSA WSGI application with a single Waitress thread."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import sys

from waitress import create_server as create_waitress_server


def create_satosa_server(port: int, threads: int) -> tuple[Callable[[], None], Callable[[], None]]:
    """Create SATOSA's Waitress runner and its cross-thread shutdown callback.

    Args:
        port: Loopback port for the internal SATOSA endpoint.
        threads: Waitress request worker count.

    Returns:
        A function that runs Waitress and a function that closes its listener.
    """

    from satosa.wsgi import app

    server = create_waitress_server(
        app,
        host="127.0.0.1",
        port=port,
        threads=threads,
        url_scheme="https",
    )

    def run() -> None:
        """Run Waitress and drain active requests when its loop exits."""

        try:
            server.run()
        finally:
            server.task_dispatcher.shutdown(timeout=5)

    def stop() -> None:
        """Close the listener and wake the Waitress event loop."""

        server.close()

    return run, stop


def main(argv: Sequence[str] | None = None) -> int:
    """Run SATOSA on the internal loopback listener.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Exit status after the WSGI server stops.
    """

    parser = argparse.ArgumentParser(description="Run the SATOSA WSGI application.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--threads", type=int, default=1)
    arguments = parser.parse_args(argv)
    if arguments.port <= 0:
        parser.error("--port must be positive")
    if arguments.threads <= 0:
        parser.error("--threads must be positive")

    run, stop = create_satosa_server(arguments.port, arguments.threads)
    try:
        run()
    finally:
        stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
