#!/usr/bin/env python3
"""Minimal HTTP endpoint for saving raw POST request bodies to disk.

The server listens on all interfaces at TCP port 8000. Each POST body is saved
under ``./uploads`` relative to the process's working directory. Callers may
provide the output filename through the ``name`` query parameter.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import os

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class UploadHandler(BaseHTTPRequestHandler):
    """Handle HTTP POST requests containing a raw file body."""

    def do_POST(self):
        """Save the request body and return HTTP 201 with the destination."""
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)

        query = parse_qs(urlparse(self.path).query)
        requested_name = query.get("name", ["upload.bin"])[0]

        # Strip directory traversal and retain only the basename.
        filename = os.path.basename(requested_name) or "upload.bin"
        destination = UPLOAD_DIR / filename
        destination.write_bytes(data)

        response = f"Saved {len(data)} bytes to {destination}\n"
        self.send_response(201)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(response.encode())))
        self.end_headers()
        self.wfile.write(response.encode())


HTTPServer(("0.0.0.0", 8000), UploadHandler).serve_forever()
