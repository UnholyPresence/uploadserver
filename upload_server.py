#!/usr/bin/env python3
"""Minimal HTTP endpoint for saving raw POST request bodies to disk.

Each POST body is streamed to a file under the configured upload directory
(``./uploads`` by default). Callers may provide the output filename through
the ``name`` query parameter.
"""

import argparse
import os
import re
import tempfile
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_PORT = 8000
DEFAULT_MAX_SIZE = 1024**3  # 1 GiB
CHUNK_SIZE = 64 * 1024

_ILLEGAL_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


def sanitize_filename(name):
    """Reduce a caller-supplied name to a safe basename, or None if unusable."""
    name = name.strip()
    if not name:
        return None
    # Treat backslashes as separators too, since os.path.basename only
    # strips them on Windows and this server may run on POSIX.
    name = name.replace("\\", "/")
    name = os.path.basename(name)
    name = _ILLEGAL_CHARS.sub("_", name).rstrip(". ")
    if name in ("", ".", ".."):
        return None
    return name


def default_filename():
    """A collision-resistant name for uploads that don't specify one."""
    stamp = time.strftime("%Y%m%dT%H%M%S")
    return f"upload-{stamp}-{uuid.uuid4().hex[:8]}.bin"


def allocate_destination(upload_dir, filename, allow_overwrite):
    """Return the path to write to, adding a numeric suffix to avoid collisions."""
    destination = upload_dir / filename
    if allow_overwrite or not destination.exists():
        return destination

    stem, suffix = destination.stem, destination.suffix
    n = 1
    while True:
        candidate = upload_dir / f"{stem}.{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


class UploadServer(HTTPServer):
    def __init__(self, server_address, handler_cls, upload_dir, max_size, allow_overwrite):
        super().__init__(server_address, handler_cls)
        self.upload_dir = upload_dir
        self.max_size = max_size
        self.allow_overwrite = allow_overwrite


class UploadHandler(BaseHTTPRequestHandler):
    """Handle HTTP POST requests containing a raw file body."""

    def do_POST(self):
        start = time.monotonic()

        length = self._read_content_length()
        if length is None:
            return

        if self.server.max_size and length > self.server.max_size:
            self._finish(413, f"Body exceeds maximum size of {self.server.max_size} bytes", None, 0, start)
            return

        query = parse_qs(urlparse(self.path).query)
        requested_name = query.get("name", [""])[0]
        filename = sanitize_filename(requested_name) or default_filename()
        destination = allocate_destination(self.server.upload_dir, filename, self.server.allow_overwrite)

        bytes_written, error = self._stream_to_disk(destination, length)
        if error is not None:
            self._finish(400, error, destination.name, bytes_written, start)
            return

        self._finish(201, f"Saved {bytes_written} bytes to {destination}", destination.name, bytes_written, start)

    def _read_content_length(self):
        header = self.headers.get("Content-Length")
        if header is None:
            self._send_plain(411, "Content-Length header is required")
            return None
        try:
            length = int(header)
        except ValueError:
            self._send_plain(400, "Content-Length must be an integer")
            return None
        if length < 0:
            self._send_plain(400, "Content-Length must not be negative")
            return None
        return length

    def _stream_to_disk(self, destination, length):
        """Write the request body to a temp file, then atomically publish it."""
        fd, tmp_path = tempfile.mkstemp(dir=self.server.upload_dir, prefix=".upload-", suffix=".part")
        written = 0
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ConnectionError("client closed the connection before sending the full body")
                    tmp_file.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
        except Exception as exc:
            os.unlink(tmp_path)
            return written, str(exc)

        os.replace(tmp_path, destination)
        return written, None

    def _finish(self, status, message, saved_name, byte_count, start):
        elapsed = time.monotonic() - start
        try:
            self._send_plain(status, message)
        except Exception:
            pass  # connection may already be gone
        self.log_message(
            "%s",
            f"name={saved_name!r} bytes={byte_count} status={status} elapsed={elapsed:.3f}s",
        )

    def _send_plain(self, status, message):
        body = (message + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Save raw POST request bodies to disk.")
    parser.add_argument("--bind", default="0.0.0.0", help="address to listen on (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"TCP port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--dir", default="uploads", help="directory to write uploads to (default: uploads)")
    parser.add_argument(
        "--max-size",
        type=int,
        default=DEFAULT_MAX_SIZE,
        help=f"maximum accepted body size in bytes, 0 for unlimited (default: {DEFAULT_MAX_SIZE})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing files with the same name instead of adding a numeric suffix",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    upload_dir = Path(args.dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    server = UploadServer((args.bind, args.port), UploadHandler, upload_dir, args.max_size, args.overwrite)
    print(f"Listening on {args.bind}:{args.port}, saving to {upload_dir.resolve()}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
