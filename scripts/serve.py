#!/usr/bin/env python3
"""Serve the static crossword site with clean puzzle URL support."""

from __future__ import annotations

import argparse
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).parents[1]
DEFAULT_WEB_ROOT = ROOT / "web"
PUZZLE_ROUTE = re.compile(r"/puzzle/[a-z0-9]+(?:-[a-z0-9]+)*/?")


def routed_path(path: str) -> str:
    """Map a clean puzzle URL to the single-page app document."""
    request_path = urlsplit(path).path
    return "/index.html" if PUZZLE_ROUTE.fullmatch(request_path) else path


class PuzzleSiteHandler(SimpleHTTPRequestHandler):
    """Static file handler that sends puzzle routes to the browser app."""

    def send_head(self):  # type: ignore[no-untyped-def]
        original_path = self.path
        self.path = routed_path(self.path)
        try:
            return super().send_head()
        finally:
            self.path = original_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", help="Address to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve")
    parser.add_argument(
        "--directory",
        type=Path,
        default=DEFAULT_WEB_ROOT,
        help="Static site directory",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    handler = partial(PuzzleSiteHandler, directory=str(args.directory.resolve()))
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    print(f"Serving crosswords at http://{args.bind}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
