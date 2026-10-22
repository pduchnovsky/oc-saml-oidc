"""Serve the SATOSA WSGI application with a single Waitress thread."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys

from waitress import serve


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

    from satosa.wsgi import app

    serve(
        app,
        host="127.0.0.1",
        port=arguments.port,
        threads=arguments.threads,
        url_scheme="https",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
