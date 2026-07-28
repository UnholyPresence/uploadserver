#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import os

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class UploadHandler(BaseHTTPRequestHandler):
    def do_POST(self):
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
